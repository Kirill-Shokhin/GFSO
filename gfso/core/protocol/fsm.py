"""THE TABLE. (State, Signal, Guard) → (NewState, [Effects])."""
from __future__ import annotations

from typing import Callable, Optional

from gfso.core.types import (
    State, Signal, DoneReason, MutationType,
    GuardContext, Effect, SignalData,
    MutateGraph, RunChecks, Dispatch,
    NON_TERMINAL_STATES, REASSIGNABLE_STATES, QUASI_TERMINAL_STATES, TaskId,
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


@_row(State.IDLE, Signal.TIMEOUT)
def _(tid: TaskId, ctx: GuardContext) -> TransitionResult:
    # Инв-5 is TOTAL over non-terminals (§6.3/§6.4): IDLE is a non-terminal state and is not in the
    # spec-target exception list — first timeout → TIMEOUT like any other. Operationally a node is
    # only ever OBSERVABLE in IDLE as a crash orphan (creation persists mid-effects but the
    # SET_STATE→REVIEW did not land); this row is exactly its escape hatch. Closes the Lean-flagged
    # divergence (`idle_has_no_timeout` — now a theorem of the opposite sign).
    return (State.TIMEOUT, [
        _mg(tid, State.TIMEOUT),
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
    # ADJUDICATE_DEP with no payload = CONFIRM any provisional discovered-Dep this task's BLOCK recorded
    # (§6.2: RESOLVE_BLOCK adjudicates truth; the re-attribute/retract variants carry payload → transition()).
    return (State.EXECUTING, [
        MutateGraph(tid, MutationType.ADJUDICATE_DEP),
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


# === CANCELLING (§6.3: cancellation is a two-step handshake, mirror of ASSIGN→ACCEPT) ===

@_row(State.CANCELLING, Signal.CANCEL_ACK)
def _(tid: TaskId, ctx: GuardContext) -> TransitionResult:
    # Sole staffed exit from CANCELLING (CANCEL_ACK's defect type = FSM-deadlock, §6.2). The in-flight
    # report rides on SignalData.in_flight → audit log (T11); no done_reason — CANCELLED is its own state, V=⊥.
    return (State.CANCELLED, [
        _mg(tid, State.CANCELLED),
        Dispatch(tid, Signal.CANCEL_ACK),
    ])


@_row(State.CANCELLING, Signal.TIMEOUT)
def _(tid: TaskId, ctx: GuardContext) -> TransitionResult:
    # Cancellation is authoritative (§6.3): executor silence still completes it, just without the in-flight report.
    return (State.CANCELLED, [
        _mg(tid, State.CANCELLED),
    ])


# === Build lookup ===

_LOOKUP: dict[tuple[State, Signal], Callable] = {
    (state, signal): fn for state, signal, fn in _TABLE
}


def available_signals(state: State) -> list[Signal]:
    """Signals that have a transition row from this state (+ the catch-alls: universal CANCEL for
    non-terminals except CANCELLING (§6.3: its sole staffed exit is CANCEL_ACK), and re-ASSIGN for
    revisable states (§6.4 Inv-1)).

    Pure on State. Used to expose valid actions per (state, role) to UIs/agents (§6.2).
    """
    sigs = [signal for (st, signal) in _LOOKUP if st == state]
    if state in NON_TERMINAL_STATES and state != State.CANCELLING and Signal.CANCEL not in sigs:
        sigs.append(Signal.CANCEL)
    if state in REASSIGNABLE_STATES and Signal.ASSIGN not in sigs:
        sigs.append(Signal.ASSIGN)
    if state in QUASI_TERMINAL_STATES and Signal.ASSIGN not in sigs:
        sigs.append(Signal.ASSIGN)  # R′ REOPEN affordance (§6.3) — the finality-gate may still reject
    return sigs


def transition(
    state: State,
    signal_data: SignalData,
    ctx: GuardContext,
) -> TransitionResult:
    """THE transition function. Pure on (State, Signal, Guard)."""
    signal = signal_data.signal
    task_id = signal_data.task_id

    # ANY_NON_TERMINAL + CANCEL catch-all → CANCELLING (§6.3: two-step handshake, mirror of ASSIGN→ACCEPT).
    # CANCELLING itself is excluded: its sole staffed exit is CANCEL_ACK (re-CANCEL is a no-op, not a row).
    # The subtree cascade (§6.2: the protocol sends CANCEL to every descendant) fires HERE, on CANCEL —
    # mutations.apply returns the affected children for the loop to CANCEL, each running its own handshake.
    if signal == Signal.CANCEL and state in NON_TERMINAL_STATES and state != State.CANCELLING:
        return (State.CANCELLING, [
            _mg(task_id, State.CANCELLING),
            Dispatch(task_id, Signal.CANCEL),
        ])

    # BLOCK naming undeclared prerequisite NODE(s) — record a provisional discovered-Dep edge PER
    # prerequisite (§6.2/§7.2: real S\Ŝ edges falsifying the plan's implicit independence claim;
    # provenance = this BLOCK, T11). One BLOCK may surface several blockers — collapsing them to one
    # edge starves q_Dep and blinds auto-resolve (observed live: a 3-blocker deadlock recorded 0 edges).
    # Payload-dependent → handled here; the bare-BLOCK case falls through to the table row (no edge).
    if signal == Signal.BLOCK and state in (State.EXECUTING, State.REWORK) and signal_data.blockers:
        return (State.BLOCKED, [
            *(MutateGraph(task_id, MutationType.RECORD_DEP, dep_from=b,
                          glue=signal_data.reason or "") for b in signal_data.blockers),
            _mg(task_id, State.BLOCKED),
            Dispatch(task_id, Signal.BLOCK),
        ])

    # RESOLVE_BLOCK adjudicating the provisional discovered-Dep(s) (§6.2): the passed blocker set is the
    # corrected FULL set (SET semantics — unlisted provisionals retract, listed sources confirm; a single
    # id ≡ a set of one = the old re-attribute), or retract all (external / non-producible blocker → the
    # FM-5 currency line, not Dep edges). The plain confirm is the table row's payload-free ADJUDICATE_DEP.
    if (signal == Signal.RESOLVE_BLOCK and state == State.BLOCKED
            and (signal_data.blockers or signal_data.external)):
        return (State.EXECUTING, [
            MutateGraph(task_id, MutationType.ADJUDICATE_DEP, dep_froms=signal_data.blockers,
                        dep_external=signal_data.external),
            _mg(task_id, State.EXECUTING),
            Dispatch(task_id, Signal.RESOLVE_BLOCK),
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

    # REVISION — canon v3.7 §6.4 Inv-1: a packet change on a LIVE node = re-ASSIGN under the SAME id →
    # REVIEW (the executor re-ACCEPTs/CHALLENGEs — the same IC protection as the first ASSIGN, §6.3).
    # NOT the CANCEL signal, no pass through CANCELLING, and NO cascade — the subtree is retained; staleness
    # surfaces via CHECK-1 + non-redundancy/CHECK-1b (dangling covers) + CHECK-3 (Dep consumers). Each
    # version is appended to the log (Inv-7: the immutable record is the LOG, not the node). Excluded:
    # TIMEOUT (no progress signals, §6.3), CANCELLING (sole exit CANCEL_ACK), terminals (no rows).
    # The single in-place spec change remains ACCEPT_CHALLENGE (above) — executor-initiated (FM-7→FM-5).
    if (signal == Signal.ASSIGN and state in REASSIGNABLE_STATES
            and signal_data.spec is not None):
        return (State.REVIEW, [
            MutateGraph(task_id, MutationType.APPLY_SPEC, spec=signal_data.spec,
                        assignee=signal_data.assignee,   # carries a new executor for reassign (Del change); None = keep
                        covers=signal_data.covers,       # (re)declared coverage of parent criteria (§2.2)
                        revision_reason=signal_data.revision_reason),  # causal typing (§16.5)
            _mg(task_id, State.REVIEW),
            RunChecks(task_id),
            Dispatch(task_id, Signal.ASSIGN),
        ])

    # R′ REOPEN — canon §6.3 "Финальность": DONE and CANCELLED are QUASI-terminal. A re-ASSIGN out of
    # them (NOT a 13th signal — a named re-ASSIGN over a new edge) is admitted under a DOUBLE gate:
    # (i) the finality-gate — the terminal is not CONSUMED in the graph (positive: the parent has not
    # staked its aggregate on V=pass and no Dep-consumer built on the result; negative: the cascade
    # has not settled or the parent has not replanned around the hole); (ii) reopens remain
    # (max_reopens, sign-agnostic — restores finiteness for the new outgoing edge, Инв-5).
    # Both gate inputs arrive via GuardContext, computed at the chokepoint in the SAME atomic step
    # as this edge (Инв-7) — a concurrent DELIVER cannot consume the node between check and reopen.
    # Target is REVIEW, never the old terminal: the verdict is RE-EARNED by fresh contact (anti-fake);
    # for DONE this literally drops V=pass — the REOPEN mutation spends the counter and stales the
    # recorded verdict. spec=None reopens under the node's own standing contract.
    if signal == Signal.ASSIGN and state in QUASI_TERMINAL_STATES:
        if ctx.consumed or ctx.reopens >= ctx.max_reopens:
            return None  # final: потреблён ∨ исчерпан счётчик (§6.3) — audit-rejected, T11
        return (State.REVIEW, [
            MutateGraph(task_id, MutationType.REOPEN, spec=signal_data.spec,
                        assignee=signal_data.assignee, covers=signal_data.covers,
                        revision_reason=signal_data.revision_reason),
            _mg(task_id, State.REVIEW),
            RunChecks(task_id),
            Dispatch(task_id, Signal.ASSIGN),
        ])

    fn = _LOOKUP.get((state, signal))
    if fn is None:
        return None
    return fn(task_id, ctx)
