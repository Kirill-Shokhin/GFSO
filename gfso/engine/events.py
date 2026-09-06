"""Event/callback system for engine observers."""
from __future__ import annotations

import logging
from typing import Callable

from gfso.core.types import State, Signal, TaskId

log = logging.getLogger(__name__)

# Callback signatures
TransitionCallback = Callable[[TaskId, State, State, Signal], None]
ErrorCallback = Callable[[TaskId, Signal, Exception], None]
RejectCallback = Callable[[TaskId, Signal, State], None]
InfoCallback = Callable[[str, str], None]  # (source, message) — pipeline progress, not graph state


def emit_cb(engine, source: str, progress: Callable[[str], None] | None = None) -> Callable[[str], None]:
    """One observation callback for the LLM-run verbs (review_decomposition / validate_result / auto_decompose /
    run_executor): emit_info to the UI strip — never breaking the caller — plus the optional
    transport fan-out (MCP progress). Four verbs used to hand-roll this identically."""
    def _cb(msg: str) -> None:
        try:
            engine.emit_info(source, msg)
        # this callback IS the observation fan-out — the strip must never break the verb it narrates
        except Exception:
            pass
        if progress is not None:
            progress(msg)
    return _cb


class EventBus:
    """Who to tell when the graph moves — subscriptions in, emissions out.

    A CALLBACK MAY NOT BREAK THE PROTOCOL. Every emission swallows what its subscribers raise and
    logs it: observation is presentation, and a UI socket that died must not roll back a transition
    the log has already recorded (Inv-7). That is why the `emit_*` methods look defensive and the
    `on_*` methods do not — the asymmetry is the rule, not an oversight.
    """

    def __init__(self):
        self._on_transition: list[TransitionCallback] = []
        self._on_error: list[ErrorCallback] = []
        self._on_reject: list[RejectCallback] = []
        self._on_info: list[InfoCallback] = []

    def on_transition(self, callback: TransitionCallback) -> None:
        """Subscribe to state changes: `cb(task_id, old, new, signal)`."""
        self._on_transition.append(callback)

    def on_error(self, callback: ErrorCallback) -> None:
        """Subscribe to errors raised while handling a signal: `cb(task_id, signal, exc)`."""
        self._on_error.append(callback)

    def on_reject(self, callback: RejectCallback) -> None:
        """Subscribe to REFUSED signals — the FSM said no: `cb(task_id, signal, state)`."""
        self._on_reject.append(callback)

    def on_info(self, callback: InfoCallback) -> None:
        """Subscribe to the observation stream a long verb writes: `cb(source, message)`."""
        self._on_info.append(callback)

    def emit_transition(self, task_id: TaskId, old_state: State, new_state: State, signal: Signal) -> None:
        """Tell every subscriber the node moved. Their failures are logged, never raised."""
        for cb in self._on_transition:
            try:
                cb(task_id, old_state, new_state, signal)
            except Exception:
                log.exception(f"callback error in on_transition for {task_id}")

    def emit_error(self, task_id: TaskId, signal: Signal, error: Exception) -> None:
        """Tell every subscriber a signal raised. Their failures are logged, never raised."""
        for cb in self._on_error:
            try:
                cb(task_id, signal, error)
            except Exception:
                log.exception(f"callback error in on_error for {task_id}")

    def emit_reject(self, task_id: TaskId, signal: Signal, state: State) -> None:
        """Tell every subscriber a signal was refused. Their failures are logged, never raised."""
        for cb in self._on_reject:
            try:
                cb(task_id, signal, state)
            except Exception:
                log.exception(f"callback error in on_reject for {task_id}")

    def emit_info(self, source: str, message: str) -> None:
        """Pipeline progress (e.g. the decompose stages) — presentation events for live observers
        (the UI status strip), NOT graph mutations."""
        for cb in self._on_info:
            try:
                cb(source, message)
            except Exception:
                log.exception(f"callback error in on_info from {source}")
