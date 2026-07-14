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
        except Exception:
            pass
        if progress is not None:
            progress(msg)
    return _cb


class EventBus:
    def __init__(self):
        self._on_transition: list[TransitionCallback] = []
        self._on_error: list[ErrorCallback] = []
        self._on_reject: list[RejectCallback] = []
        self._on_info: list[InfoCallback] = []

    def on_transition(self, callback: TransitionCallback) -> None:
        self._on_transition.append(callback)

    def on_error(self, callback: ErrorCallback) -> None:
        self._on_error.append(callback)

    def on_reject(self, callback: RejectCallback) -> None:
        self._on_reject.append(callback)

    def on_info(self, callback: InfoCallback) -> None:
        self._on_info.append(callback)

    def emit_transition(self, task_id: TaskId, old_state: State, new_state: State, signal: Signal) -> None:
        for cb in self._on_transition:
            try:
                cb(task_id, old_state, new_state, signal)
            except Exception:
                log.exception(f"callback error in on_transition for {task_id}")

    def emit_error(self, task_id: TaskId, signal: Signal, error: Exception) -> None:
        for cb in self._on_error:
            try:
                cb(task_id, signal, error)
            except Exception:
                log.exception(f"callback error in on_error for {task_id}")

    def emit_reject(self, task_id: TaskId, signal: Signal, state: State) -> None:
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
