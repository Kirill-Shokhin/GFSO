"""THE TABLE. (State, Signal, Guard) → (NewState, [Effects])."""
from __future__ import annotations

from typing import Callable, Optional

from gfso.core.types import (
    State, Signal, DoneReason, MutationType,
    GuardContext, Effect, SignalData,
    MutateGraph, RunChecks, Dispatch,
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
    # No Recommend effect: the AI-recommendation panel is a deferred human-L2/UI convenience, not part of
    # the agentic path — it must not fire a System-LLM call per ASSIGN. Recompute on-demand when built.
    return (State.REVIEW, [
        _mg(tid, State.REVIEW),
        RunChecks(tid),
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
    # Canon §6.3: a first timeout in any non-terminal (except BLOCKED) → TIMEOUT. A challenge is NOT
    # auto-accepted in the executor's favour — that would silently resolve a disputed spec; it escalates.
    return (State.TIMEOUT, [
        _mg(tid, State.TIMEOUT),
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


def available_signals(state: State) -> list[Signal]:
    """Signals that have a transition row from this state (+ CANCEL for non-terminals).

    Pure on State. Used to expose valid actions per (state, role) to UIs/agents (§6.2).
    """
    sigs = [signal for (st, signal) in _LOOKUP if st == state]
    if state in NON_TERMINAL_STATES and Signal.CANCEL not in sigs:
        sigs.append(Signal.CANCEL)
    return sigs


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

    # ACCEPT_CHALLENGE carrying a renegotiated spec — APPLY it (sanctioned pre-acceptance revision,
    # §6.2/§6.6; the only in-place spec change allowed to alter criteria). Needs signal_data, so it is
    # handled here; the no-spec case falls through to the table row (which also registers the affordance).
    if signal == Signal.ACCEPT_CHALLENGE and state == State.CHALLENGED and signal_data.new_spec is not None:
        return (State.REVIEW, [
            MutateGraph(task_id, MutationType.APPLY_SPEC, spec=signal_data.new_spec),
            _mg(task_id, State.REVIEW),
            RunChecks(task_id),
            Dispatch(task_id, Signal.ACCEPT_CHALLENGE),
        ])

    # ASSIGN carries the packet and CREATES the node as a logged effect (§7.1 "ASSIGN adds a node").
    # Needs signal_data, so handled here; the no-spec case falls through to the table row (legacy /
    # affordance). This is what closes the unlogged pre-save: creation is now the ASSIGN transition.
    if signal == Signal.ASSIGN and state == State.IDLE and signal_data.spec is not None:
        return (State.REVIEW, [
            MutateGraph(task_id, MutationType.CREATE_TASK, spec=signal_data.spec,
                        assignee=signal_data.assignee, parent_id=signal_data.parent_id,
                        deadline=signal_data.deadline, max_iterations=signal_data.max_iterations,
                        covers=signal_data.covers),
            _mg(task_id, State.REVIEW),
            RunChecks(task_id),
            Dispatch(task_id, Signal.ASSIGN),
        ])

    # re-ASSIGN after CANCEL — canon §6.4 Inv-1: a spec/Del is IMMUTABLE after ASSIGN, so a change is
    # CANCEL + re-ASSIGN, NOT an in-place edit. The id-slot is reused (the cancelled contract stays a logged
    # tombstone, §7.3.1; refs to this node remain valid — re-id would break deps/mappings). Only a CANCELLED
    # DONE is re-assignable (PASS/FAIL are real completions). The single in-place spec change is
    # ACCEPT_CHALLENGE (above) — executor-initiated (FM-7→FM-5), never a self/issuer edit (self-CHALLENGE
    # violates IC, §6.6). There is deliberately no REVIEW→ASSIGN: editing always goes through CANCEL first.
    if (signal == Signal.ASSIGN and state == State.DONE
            and ctx.done_reason == DoneReason.CANCELLED and signal_data.spec is not None):
        return (State.REVIEW, [
            MutateGraph(task_id, MutationType.APPLY_SPEC, spec=signal_data.spec,
                        assignee=signal_data.assignee,   # carries a new executor for reassign; None = keep
                        covers=signal_data.covers),      # (re)declared coverage of parent criteria (§2.2)
            _mg(task_id, State.REVIEW),
            RunChecks(task_id),
            Dispatch(task_id, Signal.ASSIGN),
        ])

    fn = _LOOKUP.get((state, signal))
    if fn is None:
        return None
    return fn(task_id, ctx)
