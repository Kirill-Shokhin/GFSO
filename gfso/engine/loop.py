"""Event loop — processes signal queue via FSM table."""
from __future__ import annotations

import logging
import queue
import time
import threading
from datetime import datetime
from typing import Optional

from gfso.core.types import (
    Signal, State, SignalData, TaskId,
    MutateGraph, RunChecks, Recommend, Dispatch,
    LLMProviderPort, AgentPort,
    TERMINAL_STATES,
)
from gfso.core.protocol.fsm import transition
from gfso.core.graph import Graph
from gfso.core.graph.mutations import apply as apply_mutation, InvariantViolation
from gfso.core.handlers import run_checks, recommend

from .audit import AuditLog, AuditEntry
from .events import EventBus
from .validation import validate_signal, ValidationError

log = logging.getLogger(__name__)


def event_loop(
    graph: Graph,
    agents: AgentPort,
    get_llm,  # Callable[[], Optional[LLMProviderPort]] — mutable reference
    signal_queue: queue.Queue[SignalData],
    audit: AuditLog,
    events: EventBus,
    validate: bool = True,
) -> None:
    """THE event loop. Processes signals via FSM table."""
    while True:
        signal_data = signal_queue.get()
        if signal_data is None:
            break  # poison pill

        task_id = signal_data.task_id
        state = graph.get_state(task_id)

        # New task via ASSIGN
        if state is None:
            if signal_data.signal == Signal.ASSIGN:
                state = State.IDLE
            else:
                log.warning(f"signal {signal_data.signal.name} for unknown task {task_id}")
                signal_queue.task_done()
                continue

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
                ))
                events.emit_reject(task_id, signal_data.signal, state)
                signal_queue.task_done()
                continue

        # FSM transition
        ctx = graph.get_guard_context(task_id)
        result = transition(state, signal_data, ctx)

        if result is None:
            log.info(f"rejected: {signal_data.signal.name} in {state.name} for {task_id}")
            audit.record(AuditEntry(
                timestamp=datetime.now(), task_id=task_id,
                signal=signal_data.signal, old_state=state,
                new_state=None, effects=(), rejected=True,
            ))
            events.emit_reject(task_id, signal_data.signal, state)
            signal_queue.task_done()
            continue

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
            ))
            events.emit_error(task_id, signal_data.signal, e)
            signal_queue.task_done()
            continue

        # Execute effects (invariants already validated)
        _execute_effects(effects, graph, agents, get_llm(), signal_queue)

        # Success
        log.info(f"{task_id}: {state.name} + {signal_data.signal.name} -> {new_state.name}")
        audit.record(AuditEntry(
            timestamp=datetime.now(), task_id=task_id,
            signal=signal_data.signal, old_state=state,
            new_state=new_state, effects=effect_names,
        ))
        events.emit_transition(task_id, state, new_state, signal_data.signal)
        signal_queue.task_done()


def _validate_effects(effects: list, graph: Graph) -> None:
    """Pre-validate all MutateGraph effects for invariant violations."""
    for effect in effects:
        if isinstance(effect, MutateGraph) and effect.spec is not None:
            task = graph.get_task(effect.task_id)
            if task and task.spec.criteria != effect.spec.criteria:
                raise InvariantViolation(
                    f"criteria immutability violated for {effect.task_id}: "
                    f"criteria change requires CANCEL + re-ASSIGN"
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
                for child_id in affected:
                    signal_queue.put(SignalData(
                        signal=Signal.CANCEL, task_id=child_id,
                        reason="cascade from parent cancel",
                    ))

            case RunChecks(task_id=tid):
                task = graph.get_task(tid)
                children = graph.get_children(tid)
                if task:
                    dep_edges = [(e.from_id, e.to_id) for e in graph._storage.get_dep_edges()]
                    results = run_checks(task, children, dep_edges)
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
) -> None:
    """Background thread: checks deadlines, emits timeout signals.

    Dedup by (task_id, state): fires once per state. When state changes
    (e.g. REVIEW → TIMEOUT), a new timeout can fire for the same task,
    enabling TIMEOUT → ESCALATED via repeated timeout.
    """
    last_timeout_state: dict[TaskId, State] = {}
    while True:
        if stop_event and stop_event.is_set():
            break
        time.sleep(check_interval)
        for task in graph.active_tasks():
            if task.deadline and time.time() > task.deadline.timestamp():
                if task.state not in TERMINAL_STATES:
                    prev = last_timeout_state.get(task.id)
                    if prev != task.state:
                        last_timeout_state[task.id] = task.state
                        signal_queue.put(SignalData(
                            signal=Signal.TIMEOUT, task_id=task.id,
                        ))
        # Clean up terminal tasks
        last_timeout_state = {tid: s for tid, s in last_timeout_state.items()
                              if graph.get_state(tid) not in TERMINAL_STATES}
