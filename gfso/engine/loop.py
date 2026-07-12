"""Event loop — processes signal queue via FSM table."""
from __future__ import annotations

import logging
import queue
import threading
from datetime import datetime
from typing import Optional

from gfso.core.types import (
    Signal, State, SignalData, TaskId, MutationType,
    MutateGraph, RunChecks, Recommend, Dispatch,
    LLMProviderPort, AgentPort, ClockPort, SystemClock,
    TERMINAL_STATES,
)
from gfso.core.protocol.fsm import transition
from gfso.core.graph import Graph
from gfso.core.graph.mutations import apply as apply_mutation, InvariantViolation
from gfso.core.handlers import run_all_checks, recommend

from .audit import AuditLog, AuditEntry
from .events import EventBus
from .validation import validate_signal, ValidationError

log = logging.getLogger(__name__)


def _payload_fields(sd: SignalData) -> dict:
    """SignalData payload carried onto the audit entry (who/why, Th.11)."""
    return dict(
        source=sd.source, reason=sd.reason, justification=sd.justification,
        result=sd.result, failed_criteria=sd.failed_criteria, action=sd.action,
        in_flight=sd.in_flight,
    )


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
        log.info(f"rejected: {signal_data.signal.name} in {state.name} for {task_id}")
        audit.record(AuditEntry(
            timestamp=datetime.now(), task_id=task_id,
            signal=signal_data.signal, old_state=state,
            new_state=None, effects=(), rejected=True,
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

    # Execute effects (invariants already validated). Revision (re-ASSIGN, §6.4 Inv-1) never returns
    # cascade children — only entering CANCELLING does (§6.2: CANCEL cascades the subtree).
    _execute_effects(effects, graph, agents, llm, signal_queue)

    # Success
    log.info(f"{task_id}: {state.name} + {signal_data.signal.name} -> {new_state.name}")
    audit.record(AuditEntry(
        timestamp=datetime.now(), task_id=task_id,
        signal=signal_data.signal, old_state=state,
        new_state=new_state, effects=effect_names,
        **_payload_fields(signal_data),
    ))
    if signal_data.signal == Signal.DELIVER and signal_data.result:
        try:  # the deliverable pointer must survive a server restart (it is the validator's input)
            graph._storage.store_deliver_result(task_id, signal_data.result)
        except Exception:
            pass
    events.emit_transition(task_id, state, new_state, signal_data.signal)


def _validate_effects(effects: list, graph: Graph) -> None:
    """Pre-validate all MutateGraph effects for invariant violations."""
    for effect in effects:
        # Guard only the DEFAULT path (SET_STATE carrying a spec). APPLY_SPEC is the sanctioned
        # CHALLENGE-channel revision (§6.2/§6.6) and is allowed to change criteria.
        if (isinstance(effect, MutateGraph) and effect.mutation == MutationType.SET_STATE
                and effect.spec is not None):
            task = graph.get_task(effect.task_id)
            if task and task.spec.criteria != effect.spec.criteria:
                raise InvariantViolation(
                    f"criteria immutability violated for {effect.task_id}: "
                    f"criteria change requires CANCEL + re-ASSIGN or the CHALLENGE channel"
                )


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
                            pt = graph.get_task(pid)
                            if pt:
                                graph.store_check_results(
                                    pid, run_all_checks(pt, graph.get_children(pid), graph.dep_edges()))
                if affected:
                    # The subtree cascade (canon §6.2/§7.1: CANCEL cascades — the protocol sends CANCEL to
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
                    results = run_all_checks(task, children, graph.dep_edges())
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



def timeout_monitor(
    graph: Graph,
    signal_queue: queue.Queue[SignalData],
    check_interval: float = 10.0,
    stop_event: threading.Event | None = None,
    state_timeout: float | None = None,
    clock: ClockPort | None = None,
) -> None:
    """Background thread: checks deadlines AND per-state age, emits timeout signals.

    Инв-5 (§6.4): EVERY non-terminal state is finite. Two clocks feed the same TIMEOUT trigger:
    (a) the task's own deadline (exact, when set); (b) the per-STATE clock — a state older than
    `state_timeout` seconds fires regardless of deadline, so a deadline-less node can never sit
    in a non-terminal state forever (observed live: a stuck VALIDATING root with deadline=None
    had NO escape). The sub-FSM routes the trigger per state (first → TIMEOUT, repeat →
    ESCALATED; BLOCKED→ESCALATED, CANCELLING→CANCELLED, VALIDATING→DONE(auto_pass) — §6.3).

    Dedup by (task_id, state): fires once per state. When state changes
    (e.g. REVIEW → TIMEOUT), a new timeout can fire for the same task,
    enabling TIMEOUT → ESCALATED via repeated timeout.
    """
    clock = clock or SystemClock()   # Инв-5 reads the ClockPort, never the wall clock directly
    last_timeout_state: dict[TaskId, State] = {}
    while True:
        if stop_event and stop_event.is_set():
            break
        clock.wait(check_interval)
        now = clock.now()
        for task in graph.active_tasks():
            overdue = task.deadline and now > task.deadline.timestamp()
            state_age = now - getattr(task, "state_entered_at", task.created_at).timestamp()
            stale = state_timeout is not None and state_timeout > 0 and state_age > state_timeout
            if (overdue or stale) and task.state not in TERMINAL_STATES:
                prev = last_timeout_state.get(task.id)
                if prev != task.state:
                    last_timeout_state[task.id] = task.state
                    signal_queue.put(SignalData(
                        signal=Signal.TIMEOUT, task_id=task.id,
                    ))
        # Clean up terminal tasks
        last_timeout_state = {tid: s for tid, s in last_timeout_state.items()
                              if graph.get_state(tid) not in TERMINAL_STATES}
