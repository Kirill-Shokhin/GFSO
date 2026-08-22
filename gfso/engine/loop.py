"""Event loop — processes signal queue via FSM table."""
from __future__ import annotations

import logging
import queue
import threading
from datetime import datetime
from typing import Optional

from gfso.core.types import (
    Signal, State, SignalData, TaskId, MutationType, Verdict,
    MutateGraph, RunChecks, Recommend, Dispatch,
    LLMProviderPort, AgentPort, ClockPort, SystemClock,
    TERMINAL_STATES,
)
from gfso.core.protocol.fsm import transition, available_signals, not_admissible_here
from gfso.core.protocol.validation import Role, required_role
from gfso.core.graph import Graph
from gfso.core.graph.mutations import apply as apply_mutation, InvariantViolation
from gfso.core.handlers import run_all_checks, recommend

from .audit import AuditLog, AuditEntry
from .verdicts import store_verdict
from .events import EventBus
from .validation import validate_signal, ValidationError

log = logging.getLogger(__name__)


def _payload_fields(sd: SignalData) -> dict:
    """SignalData payload carried onto the audit entry (who/why, Thm 11)."""
    return dict(
        source=sd.source, reason=sd.reason, justification=sd.justification,
        result=sd.result, failed_criteria=sd.failed_criteria, action=sd.action,
        in_flight=sd.in_flight, spec=_spec_json(sd),
    )


def _spec_json(sd: SignalData) -> Optional[str]:
    """The contract an ASSIGN installs, serialized onto its log row (Inv-1/Inv-7).

    Without it the log records THAT a node was revised and never WHAT it became, so the superseded
    version is unrecoverable — which is how one session's `create_task` erased another's live root
    with nothing left to restore from. Best-effort by design: a log row is provenance, and failing
    to serialize a spec must never refuse a signal.
    """
    if sd.signal != Signal.ASSIGN or getattr(sd, "spec", None) is None:
        return None
    try:
        import json
        sp = sd.spec
        return json.dumps({
            "name": sp.name, "description": sp.description,
            "criteria": [{"name": c.name, "description": c.description,
                          "depends_on": str(c.depends_on) if c.depends_on else None}
                         for c in sp.criteria],
            "accepted_risks": [{"item": r.item,
                                "predictability": r.predictability.name if r.predictability else None,
                                "justification": r.justification,
                                "invalidation_condition": r.invalidation_condition}
                               for r in (sp.accepted_risks or ())],
            "scope": list(sp.scope or ()),
        }, ensure_ascii=False)
    except Exception:
        return None


def event_loop(
    graph: Graph,
    agents: AgentPort,
    get_llm,  # Callable[[], Optional[LLMProviderPort]] — mutable reference
    signal_queue: queue.Queue[SignalData],
    audit: AuditLog,
    events: EventBus,
    validate: bool = True,
) -> None:
    """THE default pump (ThreadRunner substrate): blocking queue.get until the poison pill.
    The protocol step itself is `process_signal` — substrate-free; another RunnerPort host
    (asyncio, distributed) drives THAT from its own loop and never calls this function."""
    while True:
        signal_data = signal_queue.get()
        if signal_data is None:
            break  # poison pill
        process_signal(signal_data, graph, agents, get_llm(), signal_queue, audit, events, validate)
        signal_queue.task_done()


def process_signal(
    signal_data: SignalData,
    graph: Graph,
    agents: AgentPort,
    llm,
    signal_queue,  # any object with .put(SignalData) — the sink for follow-up signals
    audit: AuditLog,
    events: EventBus,
    validate: bool = True,
) -> None:
    """ONE protocol step: validate → FSM transition → pre-validated effects → audit → events.
    Pure of the execution substrate (no thread, no blocking get): follow-up signals (cascade
    CANCELs, dispatch responses) go to `signal_queue.put(...)`. This is the unit a RunnerPort
    host schedules; `transition` and the mutations under it stay the portable core."""
    task_id = signal_data.task_id
    state = graph.get_state(task_id)

    # New task via ASSIGN
    if state is None:
        if signal_data.signal == Signal.ASSIGN:
            state = State.IDLE
        else:
            log.warning(f"signal {signal_data.signal.name} for unknown task {task_id}")
            return

    # Signal validation
    if validate:
        try:
            validate_signal(signal_data, graph)
        except ValidationError as e:
            log.warning(f"validation failed: {e}")
            audit.record(AuditEntry(
                timestamp=datetime.now(), task_id=task_id,
                signal=signal_data.signal, old_state=state,
                new_state=None, effects=(), rejected=True, error=str(e),
                **_payload_fields(signal_data),
            ))
            events.emit_reject(task_id, signal_data.signal, state)
            return

    # FSM transition
    ctx = graph.get_guard_context(task_id)
    result = transition(state, signal_data, ctx)

    if result is None:
        # WHY IT WAS REFUSED, ON THE RECORD. This branch wrote `rejected=True` with no `error` at
        # all, so the log — the one thing that is supposed to carry provenance (Inv-7/Thm 11) —
        # said a signal had been refused and not a word about what would be admissible instead.
        # Measured on a live run 2026-08-22: an executor five rework rounds into an unsatisfiable
        # criterion reached for CHALLENGE, got a silent "no", and the run stalled with the artifact
        # scoring 0.972 on the held-out suite. The route out is not a secret; it just was never said.
        _why = not_admissible_here(signal_data.signal, state)
        log.info(f"rejected: {signal_data.signal.name} in {state.name} for {task_id} — {_why}")
        audit.record(AuditEntry(
            timestamp=datetime.now(), task_id=task_id,
            signal=signal_data.signal, old_state=state,
            new_state=None, effects=(), rejected=True, error=_why,
            **_payload_fields(signal_data),
        ))
        events.emit_reject(task_id, signal_data.signal, state)
        return

    new_state, effects = result
    effect_names = tuple(type(e).__name__ for e in effects)

    # Pre-validate: check all MutateGraph effects for invariant violations
    # BEFORE executing any, to prevent partial application
    try:
        _validate_effects(effects, graph)
    except InvariantViolation as e:
        log.error(f"invariant violation (pre-check): {e}")
        audit.record(AuditEntry(
            timestamp=datetime.now(), task_id=task_id,
            signal=signal_data.signal, old_state=state,
            new_state=None, effects=effect_names, error=str(e),
            **_payload_fields(signal_data),
        ))
        events.emit_error(task_id, signal_data.signal, e)
        return

    # Execute effects (invariants already validated). Revision (re-ASSIGN, §14.4 Inv-1) never returns
    # cascade children — only entering CANCELLING does (§14.2: CANCEL cascades the subtree).
    _execute_effects(effects, graph, agents, llm, signal_queue)

    # Success
    log.info(f"{task_id}: {state.name} + {signal_data.signal.name} -> {new_state.name}")
    audit.record(AuditEntry(
        timestamp=datetime.now(), task_id=task_id,
        signal=signal_data.signal, old_state=state,
        new_state=new_state, effects=effect_names,
        **_payload_fields(signal_data),
    ))
    # THE OBSERVATION PANEL MUST SHOW THE HUMAN'S OWN WORK. `gfso log` and the UI panel read the
    # pipeline log, which only ever carried AI-side progress (decomposer, L2 checker, validator), so
    # a person who drove a whole graph by hand saw two lines about a model and not one of their own
    # fourteen signals. Measured 2026-08-20 on the human door: "the panel shows the one thing he did
    # not do." A transition is the cheapest true line there is — who moved what, and where it went.
    try:
        # …and the INTENT, where the signal's name alone misleads. A reopen is a re-ASSIGN under the
        # standing contract (§14.3: R′ is restoration, not a 13th signal) — protocol-correct, and it
        # logged as "ASSIGN … DONE → OFFERED" to a person who had called `reopen` and saw a verb they
        # never used (measured on the human door 2026-08-21).
        _intent = (" (reopen: R′ restoration — a re-ASSIGN under the node's standing contract)"
                   if signal_data.signal == Signal.ASSIGN and state in TERMINAL_STATES else "")
        # A REVISION THAT MOVES NOTHING IS NOT A TRANSITION. Binding coverage re-ASSIGNs the child
        # under the same state, and twelve `map_criterion` calls wrote twelve identical
        # "OFFERED → OFFERED" lines over the ones a reader was watching for (measured 2026-08-22).
        # The audit keeps every signal; this is the human-facing strip, and it says what happened.
        _same = state == new_state and signal_data.signal == Signal.ASSIGN
        graph._storage.log_pipeline(
            datetime.now().isoformat(sep=" ", timespec="seconds"), "signal",
            f"{task_id}: contract revised by {signal_data.source or 'system'} — still {state.name}"
            if _same else
            f"{task_id}: {signal_data.signal.name} by {signal_data.source or 'system'} "
            f"— {state.name} → {new_state.name}{_intent}")
    except Exception:
        pass                      # observation is presentation — never break the protocol step
    if signal_data.signal == Signal.DELIVER and signal_data.result:
        try:  # the deliverable pointer must survive a server restart (it is the validator's input)
            graph._storage.store_deliver_result(task_id, signal_data.result)
        except Exception:
            pass
    if signal_data.signal == Signal.DELIVER and signal_data.self_validation is not None:
        # THE SELF-CHECK AN INTERNAL NODE CARRIES IS THE RECORD IT IS JUDGED ON (§14.5 D6). The
        # field was in the packet, in `SignalData` and in the report schema, and it landed nowhere:
        # a node whose Del is its parent's could reach DONE/PASS with `get_verdict` answering "it
        # has not been validated" in the same object (measured on the human door 2026-08-21). On a
        # SEAM it is not a verdict and is not stored as one — independence is owed there, and the
        # PASS gate says so.
        task = graph.get_task(task_id)
        if task is not None and not graph.is_public(task):
            try:
                store_verdict(graph._storage, task_id, task, str(signal_data.self_validation), (),
                              str(signal_data.source or task.assignee or "executor"),
                              graph.generation_of(task_id),
                              # ONE self-report, recorded ONCE — not copied into a slot per
                              # criterion. Writing the delivery's whole prose into every criterion's
                              # `evidence` made the record READ like a per-criterion attestation
                              # that nobody made: eight criteria, eight identical blobs, in the
                              # field a reader trusts to say what was observed for each (measured on
                              # the human door 2026-08-22 — "that is the shape of a false green").
                              # What is true is what is stored: the executor said PASS, and this is
                              # the report they said it from. `get_verdict` shows the delivery
                              # itself beside it.
                              per_criterion=[{
                                  "criterion": "(the delivery as a whole)",
                                  "verdict": "pass" if signal_data.self_validation == Verdict.PASS
                                  else "fail",
                                  "evidence": f"SELF-REPORTED by {signal_data.source or task.assignee}"
                                              f" — not an independent check (§14.5 D6: an internal "
                                              f"node self-verifies). Their report: "
                                              + (signal_data.result or "(no report text)")}])
            except Exception:
                log.warning(f"could not record the self-check on {task_id}", exc_info=True)
    events.emit_transition(task_id, state, new_state, signal_data.signal)


def _validate_effects(effects: list, graph: Graph) -> None:
    """Pre-validate all MutateGraph effects for invariant violations."""
    for effect in effects:
        # Guard only the DEFAULT path (SET_STATE carrying a spec). APPLY_SPEC is the sanctioned
        # CHALLENGE-channel revision (§14.2/§14.6) and is allowed to change criteria.
        if (isinstance(effect, MutateGraph) and effect.mutation == MutationType.SET_STATE
                and effect.spec is not None):
            task = graph.get_task(effect.task_id)
            if task and task.spec.criteria != effect.spec.criteria:
                raise InvariantViolation(
                    f"criteria immutability violated for {effect.task_id}: "
                    f"criteria change requires CANCEL + re-ASSIGN or the CHALLENGE channel"
                )


def _refresh_parent_checks(graph: Graph, node_id: Optional[TaskId]) -> None:
    """Recompute one node's cached L0/L1 checks over its ACTIVE decomposition.

    Two facts meet here and used to be answered differently in two places. First, the checks are
    read from a CACHE, so whatever fails to invalidate it gates execution on a decomposition that no
    longer exists. Second, a cancelled node leaves the decomposition at CANCEL (§14.3; V = ⊥, and
    Thm 1 operates only on tasks with V ≠ ⊥) while remaining in the graph as provenance — so the
    checks range over the ACTIVE children, exactly as `Engine._recompute_checks` has always done.
    The Dep-refresh path here ranged over ALL children instead, which put the tombstones back into
    the cache on the next dependency change.
    """
    if not node_id:
        return
    node = graph.get_task(node_id)
    if node is None:
        return
    kids = graph.get_active_children(node_id)
    graph.store_check_results(
        node_id, run_all_checks(node, kids, graph.dep_edges(), graph.non_leaf_ids(kids)))


def _execute_effects(
    effects: list,
    graph: Graph,
    agents: AgentPort,
    llm: Optional[LLMProviderPort],
    signal_queue: queue.Queue[SignalData],
) -> None:
    for effect in effects:
        match effect:
            case MutateGraph() as mg:
                affected = apply_mutation(graph, mg)
                if mg.mutation in (MutationType.RECORD_DEP, MutationType.ADJUDICATE_DEP):
                    # A Dep change moves the PARENT's cached checks (CHECK-2/3 run over the children's
                    # seams). Without this refresh a BLOCK-discovered edge contradicting a declared seam
                    # is a recorded-but-INVISIBLE cycle: graph_holes reads the cache, and nothing else
                    # recomputes it (observed live — list_holes stayed [] over a live 2-cycle).
                    seen: set = set()
                    for nid in (mg.task_id, mg.dep_from, *mg.dep_froms):
                        t = graph.get_task(nid) if nid else None
                        pid = t.parent_id if t else None
                        if pid and pid not in seen:
                            seen.add(pid)
                            _refresh_parent_checks(graph, pid)
                # A refused child (CANCEL → ABANDONED) leaves the decomposition (§14.3) — so the parent's coverage and
                # non-redundancy change, and nothing was recomputing them. Measured live: four
                # planned subtasks were refused after the goal was revised, went ABANDONED, and
                # CHECK-1b went on naming them as orphans out of the cache — the graph could never
                # be executed again, and the protocol's own way to drop planned work was unusable.
                if (mg.mutation == MutationType.SET_STATE
                        and mg.new_state in (State.CANCELLING, State.ABANDONED)):
                    t = graph.get_task(mg.task_id)
                    _refresh_parent_checks(graph, t.parent_id if t else None)
                if affected:
                    # The subtree cascade (canon §14.2/§15.1: CANCEL cascades — the protocol sends CANCEL to
                    # every descendant; each runs its own handshake). An issuer action: each child's issuer
                    # is the cancelling parent's assignee — carried as source so the cascade is a VALID
                    # issuer-CANCEL (else it is rejected under validate_signals).
                    parent = graph.get_task(mg.task_id)
                    src = parent.assignee if parent else None
                    for child_id in affected:
                        signal_queue.put(SignalData(
                            signal=Signal.CANCEL, task_id=child_id, source=src,
                            reason="cascade from parent cancel",
                        ))

            case RunChecks(task_id=tid):
                task = graph.get_task(tid)
                children = graph.get_children(tid)
                if task:
                    results = run_all_checks(task, children, graph.dep_edges(),
                                             graph.non_leaf_ids(children))
                    graph.store_check_results(tid, results)

            case Recommend(task_id=tid):
                ctx = graph.build_context(tid)
                rec = recommend(ctx, llm)
                graph.store_recommendation(tid, rec)

            case Dispatch(task_id=tid, signal=sig):
                payload = graph.build_dispatch_payload(tid, sig)
                assignee = graph.get_assignee(tid)
                if assignee:
                    response = agents.dispatch(assignee, payload)
                    if response is not None:
                        signal_queue.put(response)



# How long the cancellation handshake waits for the executor's CONFIRM_CANCEL before the system
# settles it (§14.3: CANCELLING exits by CONFIRM_CANCEL or timeout, and by nothing else). Held apart
# from the per-state age clock, which is opt-in and off by default — a bound that can be switched off
# is not a bound, and this is the one state whose only other exit belongs to a party that may never
# answer at all.
_CANCELLING_GRACE_S = 120.0


def timeout_monitor(
    graph: Graph,
    signal_queue: queue.Queue[SignalData],
    check_interval: float = 10.0,
    stop_event: threading.Event | None = None,
    state_timeout: float | None = None,
    clock: ClockPort | None = None,
) -> None:
    """Background thread: checks deadlines AND per-state age, emits timeout signals.

    Inv-5 (§14.4): EVERY non-terminal state is finite. Two clocks feed the same TIMEOUT trigger:
    (a) the task's own deadline (exact, when set); (b) the per-STATE clock — a state older than
    `state_timeout` seconds fires regardless of deadline, so a deadline-less node can never sit
    in a non-terminal state forever (observed live: a stuck VALIDATING root with deadline=None
    had NO escape). The sub-FSM routes the trigger per state (first → TIMEOUT, repeat →
    ESCALATED; BLOCKED→ESCALATED, CANCELLING→ABANDONED, VALIDATING→DONE(auto_pass) — §14.3).

    Dedup by state VISIT — (task_id, state, state_entered_at): fires once per visit of a
    state. Keying on the last-FIRED state alone is NOT enough once R′ exists: a node can
    leave a fired-in state through a terminal and RE-ENTER it via a gated REOPEN before any
    cleanup tick (e.g. CANCELLING → ABANDONED → reopen → … → CANCELLING again); with the old
    key the monitor stayed silent forever and a withheld CONFIRM_CANCEL stuck the node — an
    Inv-5 violation found by the TLC spike model, not by tests. Every state CHANGE restamps
    `state_entered_at` (mutations._set_state), so a re-entered state is a fresh visit and
    fires again; the same persisting visit stays deduped.
    """
    clock = clock or SystemClock()   # Inv-5 reads the ClockPort, never the wall clock directly
    last_fired: dict[TaskId, tuple[State, object]] = {}   # task → (state, entered_at) of the fired visit
    while True:
        if stop_event and stop_event.is_set():
            break
        clock.wait(check_interval)
        now = clock.now()
        for task in graph.active_tasks():
            overdue = task.deadline and now > task.deadline.timestamp()
            state_age = now - getattr(task, "state_entered_at", task.created_at).timestamp()
            stale = state_timeout is not None and state_timeout > 0 and state_age > state_timeout
            # CANCELLING IS FINITE WHETHER OR NOT THE AGE CLOCK IS ON. Inv-5 demands finiteness of
            # every non-terminal state, and §14.3 gives this one exactly two exits: CONFIRM_CANCEL,
            # or the timeout. Both are the EXECUTOR's or the system's — the issuer who cancelled has
            # no move here — so with the age clock off (its default) a node whose executor never
            # answers stays in CANCELLING for good. Measured 2026-08-21: a person cancelled a
            # mistyped node assigned to nobody, could not confirm it (not their role), could not
            # revise it (no revision in CANCELLING), and got out only by impersonating the executor.
            # The handshake keeps its window; what it may not have is no bottom.
            if task.state == State.CANCELLING and state_age > _CANCELLING_GRACE_S:
                stale = True
            if (overdue or stale) and task.state not in TERMINAL_STATES:
                visit = (task.state, getattr(task, "state_entered_at", task.created_at))
                if last_fired.get(task.id) != visit:
                    last_fired[task.id] = visit
                    signal_queue.put(SignalData(
                        signal=Signal.TIMEOUT, task_id=task.id,
                    ))
        # Clean up terminal tasks (memory hygiene; correctness now rides on the visit key)
        last_fired = {tid: v for tid, v in last_fired.items()
                      if graph.get_state(tid) not in TERMINAL_STATES}
