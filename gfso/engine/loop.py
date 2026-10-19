"""Event loop — processes signal queue via FSM table."""
from __future__ import annotations

import json
import logging
import queue
import threading
from dataclasses import replace
from datetime import datetime
from typing import Optional

from gfso.core.types import (
    Signal, State, SignalData, TaskId, MutationType, Verdict,
    MutateGraph, RunChecks, Recommend, Dispatch,
    LLMProviderPort, AgentPort, ClockPort, SystemClock,
    TERMINAL_STATES, GuardContext,
)
from gfso.core.protocol.fsm import transition, not_admissible_here
from gfso.core.protocol.invariants import content_words, is_pure_assent
from gfso.core.protocol.procedure import admission_defects, criterionless
from gfso.core.graph import Graph
from gfso.core.graph.model import dep_scope, non_leaf_ids, standing_split
from gfso.core.graph.mutations import apply as apply_mutation, InvariantViolation
from gfso.core.handlers import run_all_checks, recommend
from gfso.config import state_bound

from .audit import AuditLog, AuditEntry, VERSION_INSTALLING, consented_on_current_version
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
        revision_reason=sd.revision_reason.name if sd.revision_reason is not None else None,
        retire_findings=tuple(sd.retire_findings),
    )


def _spec_json(sd: SignalData) -> Optional[str]:
    """The contract a version-installing signal puts in force, serialized onto its log row (Inv-1/Inv-7) —
    an ASSIGN's, and an ACCEPT_CHALLENGE's new spec, the one act that rewrites criteria in place: its
    version reached the node and never the log, so what a dispute replaced could not be read back.

    Without it the log records THAT a node was revised and never WHAT it became, so the superseded
    version is unrecoverable — which is how one session's `create_task` erased another's live root
    with nothing left to restore from. Best-effort by design: a log row is provenance, and failing
    to serialize a spec must never refuse a signal.
    """
    sp = sd.new_spec if sd.signal == Signal.ACCEPT_CHALLENGE else sd.spec
    if sd.signal not in VERSION_INSTALLING or sp is None:
        return None
    try:
        return json.dumps({
            "name": sp.name, "description": sp.description,
            # …WITH THE PROCEDURE EACH CRITERION PINS. The log is what `claim_drift` reads to say
            # how a claim moved between authoring and closing; a version stored without its
            # procedures reports every later version as having changed them, which is a false
            # finding in the one place built to catch a real one.
            "criteria": [{"name": c.name, "description": c.description,
                          "depends_on": str(c.depends_on) if c.depends_on else None,
                          "check": [p.to_dict() for p in (c.check or ())]}
                         for c in sp.criteria],
            "accepted_risks": [r.to_dict() for r in (sp.accepted_risks or ())],
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
        try:
            process_signal(signal_data, graph, agents, get_llm(), signal_queue, audit, events,
                           validate)
        except Exception:
            # ONE BAD STEP IS NOT THE END OF THE ENGINE. A malformed value that reached the graph
            # made the DAG check raise, the exception left this pump, and the thread ended — after
            # which every verb on that engine answered about a rule nobody had consulted ("the FSM
            # refused ASSIGN in OFFERED") while the real cause sat in a traceback on a stream nobody
            # was reading (agent door, 2026-09-02: the tester spent the rest of the run working
            # around a wall that was not there). The step is lost and said so; the protocol keeps
            # serving, which is what lets the next call report the truth.
            log.error(f"the step for {signal_data.task_id} raised and was dropped; the engine is "
                      f"still serving", exc_info=True)
        signal_queue.task_done()


def _refused(signal_data: SignalData, state: State, why: str, audit: AuditLog,
             events: EventBus) -> None:
    """A signal that moved nothing, on the record with its REASON (Inv-7/Thm 11).

    One writer for every refusal in the step: three branches wrote the same six-line row, and the
    one that did not carry `error` logged that something had been refused without a word about what
    would be admissible instead — measured on a live run, five rework rounds spent against a silent
    no."""
    audit.record(AuditEntry(
        timestamp=datetime.now(), task_id=signal_data.task_id, signal=signal_data.signal,
        old_state=state, new_state=None, effects=(), rejected=True, error=why,
        **_payload_fields(signal_data),
    ))
    events.emit_reject(signal_data.task_id, signal_data.signal, state)


def _keep_the_self_check(signal_data, graph, task_id, audit) -> None:
    """Store what an INTERNAL node's DELIVER said about itself (§10.3).

    Not a verdict on a seam and not stored as one — independence is owed there. Split out of
    the protocol step because it is a record about ONE signal, while the step around it is
    the transition every signal makes.
    """
    if signal_data.signal == Signal.DELIVER and signal_data.self_validation is not None:
        # THE SELF-CHECK AN INTERNAL NODE CARRIES IS THE RECORD IT IS VALIDATED ON (§10.3). The
        # field was in the packet, in `SignalData` and in the report schema, and it landed nowhere:
        # a node whose Del is its parent's could reach DONE/PASS with `get_verdict` answering "it
        # has not been validated" in the same object (measured on the human door 2026-08-21). On a
        # SEAM it is not a verdict and is not stored as one — independence is owed there, and the
        # PASS gate says so.
        task = graph.get_task(task_id)
        # …AND NOT ABOUT A NODE WITH NO CRITERIA. `record_exec_verdict` refuses that by name
        # — V is the conjunction over the node's criteria (§2.3) and over the empty set it is
        # vacuously true, which is not a verdict — and the comment there says the rule now
        # lives "where every verdict lands, so a second door cannot be written past it".
        # This IS the second door: it calls `store_verdict` directly. An outside audit inferred
        # the path and a probe walked it end to end (2026-09-05): a child with `criteria: []`
        # was accepted as the declared coverer of a parent criterion, left L0 clean, took a PASS
        # record through here, closed DONE on its own self-report, and satisfied its parent's
        # AND. A conjunct that forbids nothing, standing inside Thm 1.
        if task is not None and criterionless(task.spec.criteria):
            log.info(f"{task_id}: self-check not recorded — the node has no criteria, so there "
                     f"is nothing a verdict could be ABOUT (§2.2). Give it criteria and deliver "
                     f"again; the self-report is kept in the DELIVER result either way.")
            return
        # …AND A SELF-PASS THAT RECORDS NOTHING IS NOT A RECORD. `record_verdict` refuses a PASS
        # whose observations only restate the verdict — "a PASS needs to say what was OBSERVED" —
        # while this path, the one the product PUSHES an executor down, took `self_validation=PASS`
        # with `result="yep"` and closed a node carrying a criterion it did not meet (HTTP door,
        # wave 26, 2026-09-06: "the door the product pushes you to is weaker than the one it
        # guards"). §10.3 makes the DELIVER report the record an internal node is validated on, so
        # the demand is the same demand, at the same grade: the report has to say something. A FAIL
        # is not gated — an executor reporting their own failure is the honest direction, and §2.3
        # keeps ⊥ from being a pass anyway.
        # WHERE THE FLOOR IS SET, and why not higher. `record_verdict`'s three-content-word floor is
        # calibrated for a PROSE ARGUMENT (a dispute); a delivery report is not prose, and the first
        # cut at three words here refused "ran it: K holds" — an honest short observation, which is
        # exactly the case the strict form must never break (measured against this suite, minutes
        # after writing it; the same over-strict floor was built and reverted once already on
        # 2026-09-04). What stays is the ASSERTION floor — text that says "it passed" in other words
        # — plus a hair of substance so that noise ("r", "x") is not a report either.
        _report = str(signal_data.result or "")
        if (task is not None and signal_data.self_validation == Verdict.PASS
                and (is_pure_assent(_report) or len("".join(content_words(_report))) < 3)):
            log.info(f"{task_id}: self-check not recorded — a PASS on your own delivery has to SAY "
                     f"what you checked and what it showed, and this report records nothing "
                     f"({_report!r}). The same demand `record_verdict` makes of a reviewer "
                     f"(§10.3: the DELIVER report IS this node's record). Deliver again with a "
                     f"report, or have someone validate it.")
            return
        if task is not None and not graph.is_public(task):
            try:
                store_verdict(graph._storage, task_id, task, str(signal_data.self_validation), (),
                              str(signal_data.source or task.assignee or "executor"),
                              graph.generation_of(task_id), len(audit),
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
                                              f" — not an independent check (§10.3: an internal "
                                              f"node self-verifies). Their report: "
                                              + (signal_data.result or "(no report text)")}])
            except Exception:
                log.warning(f"could not record the self-check on {task_id}", exc_info=True)


def _log_the_transition(graph, task_id, signal_data, state, new_state) -> None:
    """Write the human-facing line for this step — the strip a person actually reads.

    Swallowing is deliberate and is the whole reason this is separate: observation is
    presentation, and a failure to describe a step must never break the step.
    """
    try:
        # …and the INTENT, where the signal's name alone misleads. A reopen is a re-ASSIGN under the
        # standing contract (§12.14: R′ is restoration, not a 13th signal) — protocol-correct, and it
        # logged as "ASSIGN … DONE → OFFERED" to a person who had called `reopen` and saw a verb they
        # never used (measured on the human door 2026-08-21).
        _intent = (" (reopen: R′ restoration — a re-ASSIGN under the node's standing contract)"
                   if signal_data.signal == Signal.ASSIGN and state in TERMINAL_STATES else "")
        # A REVISION THAT MOVES NOTHING IS NOT A TRANSITION. Binding coverage re-ASSIGNs the child
        # under the same state, and twelve `map_criterion` calls wrote twelve identical
        # "OFFERED → OFFERED" lines over the ones a reader was watching for (measured 2026-08-22).
        # The audit keeps every signal; this is the human-facing strip, and it says what happened. A same-state
        # re-ASSIGN is a revision: a coverage binding re-ASSIGNs no child any more — it is the split's re-admission,
        # which says so itself (`Engine.map_criterion`) — so sixteen mapping calls no longer write sixteen lines
        # claiming a revision that never happened (CLI door, 2026-09-02; critic r16).
        _same = state == new_state and signal_data.signal == Signal.ASSIGN
        _what, _note = "contract revised", ""
        graph._storage.log_pipeline(
            datetime.now().isoformat(sep=" ", timespec="seconds"), "signal",
            f"{task_id}: {_what} by {signal_data.source or 'system'}{_note} — still {state.name}"
            if _same else
            f"{task_id}: {signal_data.signal.name} by {signal_data.source or 'system'} "
            f"— {state.name} → {new_state.name}{_intent}")
    except Exception:
        pass                      # observation is presentation — never break the protocol step


def _guard_context(graph: Graph, audit: AuditLog, task_id: TaskId, state: State) -> GuardContext:
    """What the transition's guards read: the graph's counters, and — in CHALLENGED only, where
    REJECT_CHALLENGE reads it — consent to the current version, from the log that records it.
    Asked there alone because a scan of the node's history would otherwise be paid by every step."""
    ctx = graph.get_guard_context(task_id)
    if state == State.CHALLENGED:
        ctx = replace(ctx, consented=consented_on_current_version(audit.get_entries(task_id)))
    return ctx


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

    if _the_clock_speaks_first(signal_data, graph, state, signal_queue, audit, events, validate):
        return

    # Signal validation
    if validate:
        try:
            validate_signal(signal_data, graph, audit)
        except ValidationError as e:
            log.warning(f"validation failed: {e}")
            _refused(signal_data, state, str(e), audit, events)
            return

    # FSM transition
    result = transition(state, signal_data, _guard_context(graph, audit, task_id, state))

    if result is None:
        # WHY IT WAS REFUSED, ON THE RECORD. This branch wrote `rejected=True` with no `error` at
        # all, so the log — the one thing that is supposed to carry provenance (Inv-7/Thm 11) —
        # said a signal had been refused and not a word about what would be admissible instead.
        # Measured on a live run 2026-08-22: an executor five rework rounds into an unsatisfiable
        # criterion reached for CHALLENGE, got a silent "no", and the run stalled with the artifact
        # scoring 0.972 on the held-out suite. The route out is not a secret; it just was never said.
        _why = not_admissible_here(signal_data.signal, state)
        log.info(f"rejected: {signal_data.signal.name} in {state.name} for {task_id} — {_why}")
        _refused(signal_data, state, _why, audit, events)
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
            # REFUSED, and said so in the flag every reader keys on — written without it, an invariant
            # break read as an accepted move (`accepted_moves`, the challenge and authoring readers)
            new_state=None, effects=effect_names, rejected=True, error=str(e),
            **_payload_fields(signal_data),
        ))
        events.emit_error(task_id, signal_data.signal, e)
        return

    # Execute effects (invariants already validated). Revision (re-ASSIGN, §12.3 Inv-1) never returns
    # cascade children — only entering CANCELLING does (§12.6: CANCEL cascades the subtree).
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
    _log_the_transition(graph, task_id, signal_data, state, new_state)
    if signal_data.signal == Signal.DELIVER and signal_data.result:
        try:  # the deliverable pointer must survive a server restart (it is the validator's input)
            graph._storage.store_deliver_result(task_id, signal_data.result)
        except Exception as e:
            # A WARNING IS NOT A RETRY, and this pointer is load-bearing: it is what a validator reads
            # after a restart. The fallback below is real (`_last_deliver_result` reads the audit log,
            # which the same step has already appended), so the delivery is not lost — but if that
            # log entry is ever the thing that fails, this line is the only trace left.
            log.warning(f"{task_id}: DELIVER result not persisted ({e}) — validation falls back to "
                        f"the audit log, which is the only copy left of what was delivered")
    _keep_the_self_check(signal_data, graph, task_id, audit)
    events.emit_transition(task_id, state, new_state, signal_data.signal)


def _validate_effects(effects: list, graph: Graph) -> None:
    """Pre-validate all MutateGraph effects for invariant violations."""
    for effect in effects:
        # Guard only the DEFAULT path (SET_STATE carrying a spec). APPLY_SPEC is the sanctioned
        # CHALLENGE-channel revision (§12.4/§14.3) and is allowed to change criteria.
        if (isinstance(effect, MutateGraph) and effect.mutation == MutationType.SET_STATE
                and effect.spec is not None):
            task = graph.get_task(effect.task_id)
            if task and task.spec.criteria != effect.spec.criteria:
                raise InvariantViolation(
                    f"criteria immutability violated for {effect.task_id}: "
                    f"criteria change requires CANCEL + re-ASSIGN or the CHALLENGE channel"
                )
        # …AND THE CONTRACT A REVISION INSTALLS IS ADMITTED ON THE SAME TERMS AS THE FIRST ONE.
        # ACCEPT_CHALLENGE is the one act that rewrites criteria in place, and it reached the graph
        # past both admission rules: an outside reviewer drove a node admitted WITH pinned checks
        # through a post-consent CHALLENGE, an ACCEPT_CHALLENGE whose criteria pinned none, and a
        # PASS — the gate that makes the promise checkable, lifted by the move that answers a
        # dispute. The rule belongs where the packet lands, not on the doors that happen to call it.
        # …a contract being INSTALLED: one that keeps the criteria in force re-presents what was admitted (§12.10).
        if (isinstance(effect, MutateGraph) and effect.mutation == MutationType.APPLY_SPEC
                and effect.spec is not None
                and ((standing := graph.get_task(effect.task_id)) is None
                     or standing.spec.criteria != effect.spec.criteria)):
            if defects := admission_defects(effect.spec.criteria):
                raise InvariantViolation(f"this contract for {effect.task_id} is not admitted — a revision, the answer "
                                         f"to a dispute included, installs a contract on the same terms as the first "
                                         f"one: " + "; ".join(defects))
        # …AND NO DOOR INSTALLS A PACKET OVER NO CRITERIA. The ladder above is held at the doors for a first ASSIGN
        # and a reopen; §2.2's nonempty set is held here too, where every packet lands, since an empty contract is
        # one nothing can fail whichever door it came through.
        if (isinstance(effect, MutateGraph) and effect.mutation in (MutationType.CREATE_TASK, MutationType.REOPEN)
                and effect.spec is not None and (why := criterionless(effect.spec.criteria))):
            raise InvariantViolation(f"{effect.task_id} cannot be assigned: {why}")


def refresh_checks(graph: Graph, node_id: Optional[TaskId], stale_review: bool = False) -> None:
    """Recompute one node's cached L0/L1 checks over its ACTIVE decomposition — the ONE writer of that cache
    (the RunChecks effect, the Dep-refresh path and `Engine._recompute_checks` all call it; the effect's own copy
    read every child and put an abandoned one back into CHECK-1b after a challenge's re-install, D-7).

    Two facts meet here and used to be answered differently in two places. First, the checks are
    read from a CACHE, so whatever fails to invalidate it gates execution on a decomposition that no
    longer exists. Second, a cancelled node leaves the decomposition at CANCEL (§12.6; V = ⊥, and
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
    node, kids = standing_split(graph, node)
    deps, deadlines = dep_scope(graph, node_id)
    graph.store_check_results(
        node_id, run_all_checks(node, kids, deps, non_leaf_ids(graph, kids), deadlines))
    stored = graph.get_task(node_id)
    if stale_review and stored.verified:   # the decomposition changed: a stored Level-2 verdict is no longer current
        stored.verified = False
        graph.save_task(stored)


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
                    # A Dep change moves the cached checks of every node whose SUBTREE holds the
                    # seam. Without this refresh a BLOCK-discovered edge contradicting a declared
                    # seam is a recorded-but-INVISIBLE cycle: graph_holes reads the cache, and
                    # nothing else recomputes it (observed live — list_holes stayed [] over a live
                    # 2-cycle). EVERY ANCESTOR, not the direct parents: CHECK-2/3 quantify over the
                    # Dep pairs inside a subtree (`dep_scope`), and a seam between two BRANCHES lies
                    # inside no direct parent's population — only inside their common ancestor's.
                    # Refreshing the parents alone left that ancestor's cache reading "no dependency
                    # edges" while the live gate refused execution over the violation it denied.
                    seen: set = set()
                    for nid in (mg.task_id, mg.dep_from, *mg.dep_froms):
                        t = graph.get_task(nid) if nid else None
                        while t is not None and t.parent_id is not None:
                            if t.parent_id in seen:
                                break              # this chain and its tail are already refreshed
                            seen.add(t.parent_id)
                            refresh_checks(graph, t.parent_id)
                            t = graph.get_task(t.parent_id)
                # A refused child (CANCEL → ABANDONED) leaves the decomposition (§12.6) — so the parent's coverage and
                # non-redundancy change, and nothing was recomputing them. Measured live: four
                # planned subtasks were refused after the goal was revised, went ABANDONED, and
                # CHECK-1b went on naming them as orphans out of the cache — the graph could never
                # be executed again, and the protocol's own way to drop planned work was unusable.
                # A child that LEAVES the plan changes it as a revision of its contract does, so the parent's
                # Level-2 verdict, read over the split with it, stales the same way (`mutations` on a new contract):
                # when its cancellation settles (CANCELLING keeps it active, §12.6) while the split still maps it to a
                # criterion. A child a re-admission dropped left at the drop, its mappings with it, and that admission
                # staled the verdict then — its settlement changes no plan the review read (critic r13).
                if (mg.mutation == MutationType.SET_STATE
                        and mg.new_state in (State.CANCELLING, State.ABANDONED)):
                    t = graph.get_task(mg.task_id)
                    _parent = graph.get_task(t.parent_id) if t and t.parent_id else None
                    refresh_checks(graph, _parent.id if _parent else None,
                                   stale_review=_parent is not None and mg.new_state == State.ABANDONED and any(
                                       str(m.child_id) == str(t.id) for m in _parent.criterion_mappings))
                if affected:
                    # The subtree cascade (canon §12.6/§15.1: CANCEL cascades — the protocol sends CANCEL to
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
                refresh_checks(graph, tid)

            case Recommend(task_id=tid):
                ctx = graph.build_context(tid)
                rec = recommend(ctx, llm)
                graph.store_recommendation(tid, rec)

            case Dispatch(task_id=tid, signal=sig):
                payload = graph.build_dispatch_payload(tid, sig)
                _t = graph.get_task(tid)
                assignee = _t.assignee if _t else None
                if assignee:
                    response = agents.dispatch(assignee, payload)
                    if response is not None:
                        signal_queue.put(response)



#: The states whose clock is their OWN bound and not the packet deadline (§12.2). VALIDATING is here
#: because letting the deadline cut it would let a last-moment delivery reach ESCALATED unvalidated — a
#: way around max_iterations through the clock; the protocol states are here because by the time a
#: node reaches them the deadline is spent by construction, so the wait they exist for would be no
#: wait at all (measured 2026-08-21 on CANCELLING: a person could not confirm, revise or escape a
#: node they had cancelled).
_OWN_BOUND_ONLY = (State.VALIDATING, State.ESCALATED, State.CANCELLING)


def state_bound_left(task, now: float) -> Optional[float]:
    """Seconds this visit has left under the state's OWN bound (§12.2) — None where there is none."""
    bound = state_bound(task.state.name)
    if not bound:
        return None
    return bound - (now - (task.state_entered_at or task.created_at).timestamp())


def state_bound_passed(task, now: float) -> bool:
    """Has this visit outlived the state's OWN bound (§12.2, Inv-5)? — the monitor's question."""
    left = state_bound_left(task, now)
    return left is not None and left < 0


def entered_on_a_spent_bound(task) -> bool:
    """Was the bound that governs this state ALREADY passed when the state was entered (§12.2)?

    A per-state bound cannot be: it starts at entry. What can be is the packet DEADLINE, which runs
    across every state of the contract — so this is the canon's own worked case, "REWORKING entered
    after a FAIL past the deadline" times out at once (to ESCALATED), and what it forecloses is the rework
    loop outrunning the deadline one round at a time, each round buying a fresh T_validate.

    It is deliberately NOT "this visit has aged out". That predicate is the monitor's, and used here
    it refused the owner's own move: a PASS arriving after a long validation was rejected and the
    node escalated — a refusal no admissible move of the refused party could lift, which §12.16's
    conformance clause forbids. Found by an outside reviewer with a reproduction."""
    return (task.deadline is not None and task.state not in _OWN_BOUND_ONLY
            and task.deadline < datetime.now())


def _the_clock_speaks_first(signal_data: SignalData, graph: Graph, state: State, signal_queue,
                           audit: AuditLog, events: EventBus, validate: bool) -> bool:
    """Does the CLOCK own this moment rather than the signal? (§12.2) — two rules, one answer.

    A timeout belongs to ONE VISIT of one state: the monitor stamps the visit it timed, and a
    trigger that arrives after the node has left it would spend a fresh contract's first moment on
    the previous one's expiry (a re-ASSIGN's new OFFERED carries its own deadline, §12.3).
    And a BOUND ALREADY PASSED FIRES ON ENTRY: a state entered after its bound has gone admits no
    signal before its own timeout — a zero-length transit rather than a wait, without which the
    rework loop outruns the deadline one tick at a time, REWORKING taking a DELIVER on a contract
    whose time is already spent."""
    task = graph.get_task(signal_data.task_id)
    if task is None:
        return False
    visit = (task.state, (task.state_entered_at or task.created_at))
    if (signal_data.signal == Signal.TIMEOUT and signal_data.visit is not None
            and signal_data.visit != visit):
        log.debug(f"a timeout for a visit already left is dropped: {task.id} {signal_data.visit}")
        return True
    if (not validate or signal_data.signal in (Signal.TIMEOUT, Signal.CANCEL)
            or state in TERMINAL_STATES or not entered_on_a_spent_bound(task)):
        return False
    signal_queue.put(SignalData(signal=Signal.TIMEOUT, task_id=task.id, visit=visit))
    _refused(signal_data, state,
             f"{state.name} was entered on a deadline already spent (§12.2), so it is a "
             f"zero-length transit and admits no signal: the timeout it fires on entry is on its "
             f"way, and {signal_data.signal.name} belongs to the state that follows it",
             audit, events)
    return True


def timeout_monitor(
    graph: Graph,
    signal_queue: queue.Queue[SignalData],
    check_interval: float = 10.0,
    stop_event: threading.Event | None = None,
    state_timeout: float | None = None,
    clock: ClockPort | None = None,
) -> None:
    """Background thread: checks deadlines AND per-state age, emits timeout signals.

    Inv-5 (§12.12): EVERY non-terminal state is finite. Two clocks feed the same TIMEOUT trigger:
    (a) the task's own deadline (exact, when set); (b) the per-STATE clock — a state older than
    `state_timeout` seconds fires regardless of deadline, so a deadline-less node can never sit
    in a non-terminal state forever (observed live: a stuck VALIDATING root with deadline=None
    had NO escape). The table routes the trigger per state (every wait → ESCALATED,
    ESCALATED → CANCELLING, CANCELLING → ABANDONED — §12.4).

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
        try:
            _active = graph.active_tasks()
        except Exception as e:
            # THE ENGINE IT WATCHES IS GONE. `stop()` sets the event, but this thread may already be
            # inside its wait, and the storage can close under it — a `Cannot operate on a closed
            # database` then surfaces as an unhandled thread exception at the end of an unrelated
            # test, describing a shutdown as if it were a fault (surfaced by the import sweep,
            # 2026-09-02). A monitor whose graph has closed has nothing left to monitor: it leaves.
            log.debug(f"the timeout monitor is stopping: its graph is closed ({e})")
            break
        for task in _active:
            overdue = task.deadline and now > task.deadline.timestamp()
            # …EXCEPT in the issuer's waiting state, where the deadline is already spent by
            # construction: a node that reached ESCALATED by missing it would be settled on the very
            # next tick, so the "waiting state" would give the issuer no wait at all and record V=⊥
            # as "he did not decide" when he was never offered a window. His window is this state's
            # OWN grace, below — the same asymmetry CANCELLING's grace exists for.
            # …and in CANCELLING, for the same reason and now on the common path: the silence-close
            # of an overdue node enters the handshake with its deadline already spent, so the
            # executor would lose the window CONFIRM_CANCEL exists for — the in-flight report that
            # carries provenance (Thm 11). Both states are governed by their own grace, below.
            if task.state in _OWN_BOUND_ONLY:
                overdue = False
            state_age = now - (task.state_entered_at or task.created_at).timestamp()
            stale = state_timeout is not None and state_timeout > 0 and state_age > state_timeout
            # CANCELLING IS FINITE WHETHER OR NOT THE AGE CLOCK IS ON. Inv-5 demands finiteness of
            # every non-terminal state, and §12.6 gives this one exactly two exits: CONFIRM_CANCEL,
            # or the timeout. Both are the EXECUTOR's or the system's — the issuer who cancelled has
            # no move here — so with the age clock off (its default) a node whose executor never
            # answers stays in CANCELLING for good. Measured 2026-08-21: a person cancelled a
            # mistyped node assigned to nobody, could not confirm it (not their role), could not
            # revise it (no revision in CANCELLING), and got out only by impersonating the executor.
            # The handshake keeps its window; what it may not have is no bottom.
            # …AND THE STATE'S OWN BOUND, which every waiting state now carries and which the
            # opt-in age clock above never was: a bound that can be switched off is not a bound
            # (Inv-5 asks that every non-terminal state but IDLE have one).
            if state_bound_passed(task, now):
                stale = True
            if (overdue or stale) and task.state not in TERMINAL_STATES:
                visit = (task.state, (task.state_entered_at or task.created_at))
                if last_fired.get(task.id) != visit:
                    last_fired[task.id] = visit
                    # …NAMING THE VISIT IT BOUNDS. A timeout belongs to one visit of one state
                    # (§12.2): fired for an EXECUTING that a re-ASSIGN has since left, it would
                    # otherwise land on the fresh OFFERED and carry a new contract's first moment
                    # straight to ESCALATED.
                    signal_queue.put(SignalData(
                        signal=Signal.TIMEOUT, task_id=task.id, visit=visit,
                    ))
        # Clean up terminal tasks (memory hygiene; correctness now rides on the visit key)
        last_fired = {tid: v for tid, v in last_fired.items()
                      if graph.get_state(tid) not in TERMINAL_STATES}
