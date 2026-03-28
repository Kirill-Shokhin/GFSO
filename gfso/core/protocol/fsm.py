"""THE TABLE. (State, Signal, Guard) → (NewState, [Effects])."""
from __future__ import annotations

from typing import Callable, Optional

from gfso.core.types import (
    State, Signal, DoneReason, MutationType,
    GuardContext, Effect, SignalData,
    MutateGraph, RunChecks, Recommend, Dispatch,
    NON_TERMINAL_STATES, TaskId,
)


def _mg(task_id: TaskId, new_state: State, done_reason: DoneReason | None = None) -> MutateGraph:
    return MutateGraph(
        task_id=task_id,
        mutation=MutationType.SET_STATE,
        new_state=new_state,
        done_reason=done_reason,
    )


# (State, Signal) → builder(task_id, guard) → Optional[(NewState, [Effect])]
# None return = guard rejected
TransitionResult = Optional[tuple[State, list[Effect]]]

_TABLE: list[tuple] = []


def _row(state: State, signal: Signal):
    """Decorator to register a transition row."""
    def decorator(fn):
        _TABLE.append((state, signal, fn))
        return fn
    return decorator


# === IDLE ===

@_row(State.IDLE, Signal.ASSIGN)
def _(tid: TaskId, ctx: GuardContext) -> TransitionResult:
    return (State.REVIEW, [
        _mg(tid, State.REVIEW),
        RunChecks(tid),
        Recommend(tid),
        Dispatch(tid, Signal.ASSIGN),
    ])


# === REVIEW ===

@_row(State.REVIEW, Signal.ACCEPT)
def _(tid: TaskId, ctx: GuardContext) -> TransitionResult:
    return (State.EXECUTING, [
        _mg(tid, State.EXECUTING),
        Dispatch(tid, Signal.ACCEPT),
    ])


@_row(State.REVIEW, Signal.CHALLENGE)
def _(tid: TaskId, ctx: GuardContext) -> TransitionResult:
    return (State.CHALLENGED, [
        _mg(tid, State.CHALLENGED),
        Dispatch(tid, Signal.CHALLENGE),
    ])


@_row(State.REVIEW, Signal.TIMEOUT)
def _(tid: TaskId, ctx: GuardContext) -> TransitionResult:
    return (State.TIMEOUT, [
        _mg(tid, State.TIMEOUT),
    ])


# === CHALLENGED ===

@_row(State.CHALLENGED, Signal.ACCEPT_CHALLENGE)
def _(tid: TaskId, ctx: GuardContext) -> TransitionResult:
    return (State.REVIEW, [
        _mg(tid, State.REVIEW),
        RunChecks(tid),
        Dispatch(tid, Signal.ACCEPT_CHALLENGE),
    ])


@_row(State.CHALLENGED, Signal.REJECT_CHALLENGE)
def _(tid: TaskId, ctx: GuardContext) -> TransitionResult:
    return (State.EXECUTING, [
        _mg(tid, State.EXECUTING),
        Dispatch(tid, Signal.REJECT_CHALLENGE),
    ])


@_row(State.CHALLENGED, Signal.TIMEOUT)
def _(tid: TaskId, ctx: GuardContext) -> TransitionResult:
    # Auto-accept challenge → return to REVIEW
    return (State.REVIEW, [
        _mg(tid, State.REVIEW),
    ])


# === EXECUTING ===

@_row(State.EXECUTING, Signal.DELIVER)
def _(tid: TaskId, ctx: GuardContext) -> TransitionResult:
    return (State.VALIDATING, [
        _mg(tid, State.VALIDATING),
        Dispatch(tid, Signal.DELIVER),
    ])


@_row(State.EXECUTING, Signal.BLOCK)
def _(tid: TaskId, ctx: GuardContext) -> TransitionResult:
    return (State.BLOCKED, [
        _mg(tid, State.BLOCKED),
        Dispatch(tid, Signal.BLOCK),
    ])


@_row(State.EXECUTING, Signal.TIMEOUT)
def _(tid: TaskId, ctx: GuardContext) -> TransitionResult:
    return (State.TIMEOUT, [
        _mg(tid, State.TIMEOUT),
    ])


# === BLOCKED ===

@_row(State.BLOCKED, Signal.RESOLVE_BLOCK)
def _(tid: TaskId, ctx: GuardContext) -> TransitionResult:
    return (State.EXECUTING, [
        _mg(tid, State.EXECUTING),
        Dispatch(tid, Signal.RESOLVE_BLOCK),
    ])


@_row(State.BLOCKED, Signal.TIMEOUT)
def _(tid: TaskId, ctx: GuardContext) -> TransitionResult:
    # Direct to ESCALATED — block IS the escalation signal
    return (State.ESCALATED, [
        _mg(tid, State.ESCALATED),
    ])


# === VALIDATING ===

@_row(State.VALIDATING, Signal.PASS)
def _(tid: TaskId, ctx: GuardContext) -> TransitionResult:
    return (State.DONE, [
        _mg(tid, State.DONE, DoneReason.PASS),
        Dispatch(tid, Signal.PASS),
    ])


@_row(State.VALIDATING, Signal.FAIL)
def _(tid: TaskId, ctx: GuardContext) -> TransitionResult:
    # Guarded: iteration < max → REWORK, else → DONE(fail)
    if ctx.iteration < ctx.max_iterations:
        return (State.REWORK, [
            MutateGraph(tid, MutationType.INCREMENT_ITERATION),
            _mg(tid, State.REWORK),
            Dispatch(tid, Signal.FAIL),
        ])
    return (State.DONE, [
        _mg(tid, State.DONE, DoneReason.FAIL),
        Dispatch(tid, Signal.FAIL),
    ])


@_row(State.VALIDATING, Signal.TIMEOUT)
def _(tid: TaskId, ctx: GuardContext) -> TransitionResult:
    # Auto-pass
    return (State.DONE, [
        _mg(tid, State.DONE, DoneReason.AUTO),
        Dispatch(tid, Signal.TIMEOUT),
    ])


# === REWORK ===

@_row(State.REWORK, Signal.DELIVER)
def _(tid: TaskId, ctx: GuardContext) -> TransitionResult:
    return (State.VALIDATING, [
        _mg(tid, State.VALIDATING),
        Dispatch(tid, Signal.DELIVER),
    ])


@_row(State.REWORK, Signal.BLOCK)
def _(tid: TaskId, ctx: GuardContext) -> TransitionResult:
    return (State.BLOCKED, [
        _mg(tid, State.BLOCKED),
        Dispatch(tid, Signal.BLOCK),
    ])


@_row(State.REWORK, Signal.TIMEOUT)
def _(tid: TaskId, ctx: GuardContext) -> TransitionResult:
    return (State.TIMEOUT, [
        _mg(tid, State.TIMEOUT),
    ])


# === TIMEOUT ===

@_row(State.TIMEOUT, Signal.TIMEOUT)
def _(tid: TaskId, ctx: GuardContext) -> TransitionResult:
    # Repeated timeout in TIMEOUT state → escalate
    return (State.ESCALATED, [
        _mg(tid, State.ESCALATED),
    ])


# === Build lookup ===

_LOOKUP: dict[tuple[State, Signal], Callable] = {
    (state, signal): fn for state, signal, fn in _TABLE
}


def transition(
    state: State,
    signal_data: SignalData,
    ctx: GuardContext,
) -> TransitionResult:
    """THE transition function. Pure on (State, Signal, Guard)."""
    signal = signal_data.signal
    task_id = signal_data.task_id

    # ANY_NON_TERMINAL + CANCEL catch-all
    if signal == Signal.CANCEL and state in NON_TERMINAL_STATES:
        return (State.DONE, [
            _mg(task_id, State.DONE, DoneReason.CANCELLED),
            Dispatch(task_id, Signal.CANCEL),
        ])

    fn = _LOOKUP.get((state, signal))
    if fn is None:
        return None
    return fn(task_id, ctx)
