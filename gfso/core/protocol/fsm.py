"""THE TABLE. (State, Signal, Guard) → (NewState, [Effects])."""
from __future__ import annotations

from typing import Callable, Optional

from gfso.core.protocol.validation import Role, required_role
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
    return (State.OFFERED, [
        _mg(tid, State.OFFERED),
        RunChecks(tid),
        Dispatch(tid, Signal.ASSIGN),
    ])


# NO (IDLE, TIMEOUT) ROW — deliberately, and the canon says why (corner #1, closed). Deadlines
# attach at ASSIGN, so IDLE, the pre-contract state, carries no clock of its own; Inv-5 exempts it
# BY NAME ("every non-terminal state except IDLE", §14.4) and is not breached here, because an IDLE
# child gates its parent only through the parent's AND and the parent's contract carries the clock
# — starvation surfaces as the PARENT's timeout. The row that used to sit here came from the v3.9
# reading of Inv-5 as TOTAL over non-terminals. What it was actually written for — a crash orphan,
# observable in IDLE because CREATE_TASK persisted and the ASSIGN's landing did not — is now met
# where the defect lives: `Engine._recover_orphans` finishes the interrupted transition at startup.


# === OFFERED ===

@_row(State.OFFERED, Signal.ACCEPT)
def _(tid: TaskId, ctx: GuardContext) -> TransitionResult:
    return (State.EXECUTING, [
        _mg(tid, State.EXECUTING),
        Dispatch(tid, Signal.ACCEPT),
    ])


@_row(State.OFFERED, Signal.CHALLENGE)
def _(tid: TaskId, ctx: GuardContext) -> TransitionResult:
    return (State.CHALLENGED, [
        _mg(tid, State.CHALLENGED),
        Dispatch(tid, Signal.CHALLENGE),
    ])


@_row(State.OFFERED, Signal.TIMEOUT)
def _(tid: TaskId, ctx: GuardContext) -> TransitionResult:
    return (State.OVERDUE, [
        _mg(tid, State.OVERDUE),
    ])


# === CHALLENGED ===

@_row(State.CHALLENGED, Signal.ACCEPT_CHALLENGE)
def _(tid: TaskId, ctx: GuardContext) -> TransitionResult:
    return (State.OFFERED, [
        _mg(tid, State.OFFERED),
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
    # Canon §14.3: a first timeout in any non-terminal (except BLOCKED) → OVERDUE. A challenge is NOT
    # auto-accepted in the executor's favour — that would silently resolve a disputed spec; it escalates.
    return (State.OVERDUE, [
        _mg(tid, State.OVERDUE),
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
    return (State.OVERDUE, [
        _mg(tid, State.OVERDUE),
    ])


# === BLOCKED ===

@_row(State.BLOCKED, Signal.RESOLVE_BLOCK)
def _(tid: TaskId, ctx: GuardContext) -> TransitionResult:
    # ADJUDICATE_DEP with no payload = CONFIRM any provisional discovered-Dep this task's BLOCK recorded
    # (§14.2: RESOLVE_BLOCK adjudicates truth; the re-attribute/retract variants carry payload → transition()).
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
    # Guarded: iteration < max → REWORKING, else → ESCALATED. Exhausting the rework loop is the
    # ESCALATION trigger (§14.3: "the FAIL↔REWORKING loop bounded by max_iterations", with
    # escalation as its exit), not a terminal acceptance: the canon carries NO terminal for
    # "V = fail, settled" — its negative terminals are ABANDONED (V = ⊥, cancelled) and ESCALATED
    # (attention needed) — and §12.2 states as fact that DONE is reached through acceptance
    # (PASS ∨ auto_pass), never through fail. A DONE(fail) also becomes CONSUMABLE under R′
    # (§14.3), letting a Dep-consumer read-and-build on a failure, and buries the exact event
    # §1.1's third mode exists to surface. Closes corner #3 of `formal/README.md`.
    if ctx.iteration < ctx.max_iterations:
        return (State.REWORKING, [
            MutateGraph(tid, MutationType.INCREMENT_ITERATION),
            _mg(tid, State.REWORKING),
            Dispatch(tid, Signal.FAIL),
        ])
    # The settlement REASON is carried onto the terminal: ESCALATED is reached from three routes
    # (this one, BLOCKED's timeout, OVERDUE's repeat), and only this one is a VERDICT. Without the
    # reason the metric populations that read "a standing FAIL" (q_D's exhausted arm,
    # `false_fail_share`) would silently empty out — a blind metric reads as a clean one.
    return (State.ESCALATED, [
        _mg(tid, State.ESCALATED, DoneReason.FAIL),
        Dispatch(tid, Signal.FAIL),
    ])


@_row(State.VALIDATING, Signal.TIMEOUT)
def _(tid: TaskId, ctx: GuardContext) -> TransitionResult:
    # Auto-pass
    return (State.DONE, [
        _mg(tid, State.DONE, DoneReason.AUTO_PASS),
        Dispatch(tid, Signal.TIMEOUT),
    ])


# === REWORKING ===

@_row(State.REWORKING, Signal.DELIVER)
def _(tid: TaskId, ctx: GuardContext) -> TransitionResult:
    return (State.VALIDATING, [
        _mg(tid, State.VALIDATING),
        Dispatch(tid, Signal.DELIVER),
    ])


@_row(State.REWORKING, Signal.BLOCK)
def _(tid: TaskId, ctx: GuardContext) -> TransitionResult:
    return (State.BLOCKED, [
        _mg(tid, State.BLOCKED),
        Dispatch(tid, Signal.BLOCK),
    ])


@_row(State.REWORKING, Signal.TIMEOUT)
def _(tid: TaskId, ctx: GuardContext) -> TransitionResult:
    return (State.OVERDUE, [
        _mg(tid, State.OVERDUE),
    ])


# === OVERDUE ===

@_row(State.OVERDUE, Signal.TIMEOUT)
def _(tid: TaskId, ctx: GuardContext) -> TransitionResult:
    # Repeated timeout in OVERDUE state → escalate
    return (State.ESCALATED, [
        _mg(tid, State.ESCALATED),
    ])


# === CANCELLING (§14.3: cancellation is a two-step handshake, mirror of ASSIGN→ACCEPT) ===

@_row(State.CANCELLING, Signal.CONFIRM_CANCEL)
def _(tid: TaskId, ctx: GuardContext) -> TransitionResult:
    # Sole staffed exit from CANCELLING (CONFIRM_CANCEL's defect type = FSM-deadlock, §14.2). The in-flight
    # report rides on SignalData.in_flight → audit log (Thm 11); no done_reason — ABANDONED is its own state, V=⊥.
    return (State.ABANDONED, [
        _mg(tid, State.ABANDONED),
        Dispatch(tid, Signal.CONFIRM_CANCEL),
    ])


@_row(State.CANCELLING, Signal.TIMEOUT)
def _(tid: TaskId, ctx: GuardContext) -> TransitionResult:
    # Cancellation is authoritative (§14.3): executor silence still completes it, just without the in-flight report.
    return (State.ABANDONED, [
        _mg(tid, State.ABANDONED),
    ])


# === Build lookup ===

_LOOKUP: dict[tuple[State, Signal], Callable] = {
    (state, signal): fn for state, signal, fn in _TABLE
}


def available_signals(state: State) -> list[Signal]:
    """Signals that have a transition row from this state (+ the catch-alls: universal CANCEL for
    non-terminals except CANCELLING (§14.3: its sole staffed exit is CONFIRM_CANCEL), and re-ASSIGN for
    revisable states (§14.4 Inv-1)).

    Pure on State. Used to expose valid actions per (state, role) to UIs/agents (§14.2).
    """
    sigs = [signal for (st, signal) in _LOOKUP if st == state]
    if state in NON_TERMINAL_STATES and state != State.CANCELLING and Signal.CANCEL not in sigs:
        sigs.append(Signal.CANCEL)
    if state in REASSIGNABLE_STATES and Signal.ASSIGN not in sigs:
        sigs.append(Signal.ASSIGN)
    if state in QUASI_TERMINAL_STATES and Signal.ASSIGN not in sigs:
        sigs.append(Signal.ASSIGN)  # R′ REOPEN affordance (§14.3) — the finality-gate may still reject
    return sigs


def transition(
    state: State,
    signal_data: SignalData,
    ctx: GuardContext,
) -> TransitionResult:
    """THE transition function. Pure on (State, Signal, Guard)."""
    signal = signal_data.signal
    task_id = signal_data.task_id

    # ANY_NON_TERMINAL + CANCEL catch-all → CANCELLING (§14.3: two-step handshake, mirror of ASSIGN→ACCEPT).
    # CANCELLING itself is excluded: its sole staffed exit is CONFIRM_CANCEL (re-CANCEL is a no-op, not a row).
    # The subtree cascade (§14.2: the protocol sends CANCEL to every descendant) fires HERE, on CANCEL —
    # mutations.apply returns the affected children for the loop to CANCEL, each running its own handshake.
    if signal == Signal.CANCEL and state in NON_TERMINAL_STATES and state != State.CANCELLING:
        return (State.CANCELLING, [
            _mg(task_id, State.CANCELLING),
            Dispatch(task_id, Signal.CANCEL),
        ])

    # BLOCK naming undeclared prerequisite NODE(s) — record a provisional discovered-Dep edge PER
    # prerequisite (§14.2/§15.2: real S\Ŝ edges falsifying the plan's implicit independence claim;
    # provenance = this BLOCK, Thm 11). One BLOCK may surface several blockers — collapsing them to one
    # edge starves q_Dep and blinds auto-resolve (observed live: a 3-blocker deadlock recorded 0 edges).
    # Payload-dependent → handled here; the bare-BLOCK case falls through to the table row (no edge).
    if signal == Signal.BLOCK and state in (State.EXECUTING, State.REWORKING) and signal_data.blockers:
        return (State.BLOCKED, [
            *(MutateGraph(task_id, MutationType.RECORD_DEP, dep_from=b,
                          glue=signal_data.reason or "") for b in signal_data.blockers),
            _mg(task_id, State.BLOCKED),
            Dispatch(task_id, Signal.BLOCK),
        ])

    # RESOLVE_BLOCK adjudicating the provisional discovered-Dep(s) (§14.2): the passed blocker set is the
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
    # §14.2/§14.6; the only in-place spec change allowed to alter criteria). Needs signal_data, so it is
    # handled here; the no-spec case falls through to the table row (which also registers the affordance).
    if signal == Signal.ACCEPT_CHALLENGE and state == State.CHALLENGED and signal_data.new_spec is not None:
        return (State.OFFERED, [
            MutateGraph(task_id, MutationType.APPLY_SPEC, spec=signal_data.new_spec),
            _mg(task_id, State.OFFERED),
            RunChecks(task_id),
            Dispatch(task_id, Signal.ACCEPT_CHALLENGE),
        ])

    # ASSIGN carries the packet and CREATES the node as a logged effect (§15.1 "ASSIGN adds a node").
    # Needs signal_data, so handled here; the no-spec case falls through to the table row (legacy /
    # affordance). This is what closes the unlogged pre-save: creation is now the ASSIGN transition.
    if signal == Signal.ASSIGN and state == State.IDLE and signal_data.spec is not None:
        return (State.OFFERED, [
            MutateGraph(task_id, MutationType.CREATE_TASK, spec=signal_data.spec,
                        assignee=signal_data.assignee, parent_id=signal_data.parent_id,
                        deadline=signal_data.deadline, max_iterations=signal_data.max_iterations,
                        covers=signal_data.covers),
            _mg(task_id, State.OFFERED),
            RunChecks(task_id),
            Dispatch(task_id, Signal.ASSIGN),
        ])

    # REVISION — canon v3.7 §14.4 Inv-1: a packet change on a LIVE node = re-ASSIGN under the SAME id →
    # OFFERED (the executor re-ACCEPTs/CHALLENGEs — the same IC protection as the first ASSIGN, §14.3).
    # NOT the CANCEL signal, no pass through CANCELLING, and NO cascade — the subtree is retained; staleness
    # surfaces via CHECK-1 + non-redundancy/CHECK-1b (dangling covers) + CHECK-3 (Dep consumers). Each
    # version is appended to the log (Inv-7: the immutable record is the LOG, not the node). Excluded:
    # OVERDUE (no progress signals, §14.3), CANCELLING (sole exit CONFIRM_CANCEL), terminals (no rows).
    # The single in-place spec change remains ACCEPT_CHALLENGE (above) — executor-initiated (FM-7→FM-5).
    if (signal == Signal.ASSIGN and state in REASSIGNABLE_STATES
            and signal_data.spec is not None):
        return (State.OFFERED, [
            MutateGraph(task_id, MutationType.APPLY_SPEC, spec=signal_data.spec,
                        assignee=signal_data.assignee,   # carries a new executor for reassign (Del change); None = keep
                        covers=signal_data.covers,       # (re)declared coverage of parent criteria (§10)
                        revision_reason=signal_data.revision_reason),  # causal typing (§24.5)
            _mg(task_id, State.OFFERED),
            RunChecks(task_id),
            Dispatch(task_id, Signal.ASSIGN),
        ])

    # R′ REOPEN — canon §14.3 "Финальность": DONE and ABANDONED are QUASI-terminal. A re-ASSIGN out of
    # them (NOT a 13th signal — a named re-ASSIGN over a new edge) is admitted under a DOUBLE gate:
    # (i) the finality-gate — the terminal is not CONSUMED in the graph (positive: the parent has not
    # staked its aggregate on V=pass and no Dep-consumer built on the result; negative: the cascade
    # has not settled or the parent has not replanned around the hole); (ii) reopens remain
    # (max_reopens, sign-agnostic — restores finiteness for the new outgoing edge, Inv-5).
    # Both gate inputs arrive via GuardContext, computed at the chokepoint in the SAME atomic step
    # as this edge (Inv-7) — a concurrent DELIVER cannot consume the node between check and reopen.
    # Target is OFFERED, never the old terminal: the verdict is RE-EARNED by fresh contact (anti-fake);
    # for DONE this literally drops V=pass — the REOPEN mutation spends the counter and stales the
    # recorded verdict. spec=None reopens under the node's own standing contract.
    if signal == Signal.ASSIGN and state in QUASI_TERMINAL_STATES:
        if ctx.consumed or ctx.reopens >= ctx.max_reopens:
            return None  # final: потреблён ∨ исчерпан счётчик (§14.3) — audit-rejected, Thm 11
        return (State.OFFERED, [
            MutateGraph(task_id, MutationType.REOPEN, spec=signal_data.spec,
                        assignee=signal_data.assignee, covers=signal_data.covers,
                        revision_reason=signal_data.revision_reason),
            _mg(task_id, State.OFFERED),
            RunChecks(task_id),
            Dispatch(task_id, Signal.ASSIGN),
        ])

    fn = _LOOKUP.get((state, signal))
    if fn is None:
        return None
    return fn(task_id, ctx)


#: Where a signal that a state does not admit is ACTUALLY sent from — the route, not the list.
#: A bare "valid here: [...]" leaves the caller to work out which of five signals carries their
#: intent, and the one that matters most is not obvious: after ACCEPT the contract is disputed
#: through BLOCK, because CHALLENGE is the pre-consent channel (§14.3's admissible sets) and Inv-1
#: makes every contract change the issuer's re-ASSIGN — which is exactly what a RESOLVE_BLOCK that
#: moves a packet field is (§14.3). Measured: an executor stuck on an unsatisfiable criterion
#: reached for CHALLENGE, was refused in silence, and re-delivered five times instead.
_ROUTES = {
    (Signal.CHALLENGE, State.EXECUTING): (
        "the contract is disputed BEFORE it is accepted — CHALLENGE is admitted from OFFERED "
        "(§14.3). You have accepted this one, so a defect found in the work goes out as "
        "BLOCK(reason=\"…\"): its resolution by the issuer may change a packet field, and that IS "
        "a revision under Inv-1 — the node returns to OFFERED and you consent to the new contract"),
    (Signal.CHALLENGE, State.REWORKING): (
        "the contract is disputed BEFORE it is accepted — CHALLENGE is admitted from OFFERED "
        "(§14.3). Mid-rework the channel for \"this criterion is wrong\" is BLOCK(reason=\"…\"), "
        "which is reportable from here exactly so a defect met in the work is not unreportable "
        "(FM-7): the issuer's RESOLVE_BLOCK that changes the contract is a revision (Inv-1), and "
        "the node comes back to OFFERED for your consent"),
    (Signal.CHALLENGE, State.VALIDATING): (
        "the delivery is already with its issuer — a contract objection now travels with the FAIL "
        "you expect: put it in the re-DELIVER, or BLOCK from REWORKING once the FAIL lands"),
}


def not_admissible_here(signal: Signal, state: State) -> str:
    """Why this signal moves nothing here — and where the caller's intent actually goes.

    TWO REFUSALS, NOT ONE. A signal the STATE does not admit and a signal the state admits whose
    transition GUARD refused it are different facts, and one sentence for both printed "ASSIGN is
    not valid in state OFFERED — valid here: [… 'ASSIGN']", which contradicts itself and sends the
    reader looking for the wrong thing."""
    _valid = [s for s in available_signals(state) if required_role(s) != Role.SYSTEM]
    if signal in _valid:
        return (f"{signal.name} is admitted by state {state.name} but its transition GUARD refused "
                f"it — the precondition does not hold for this node")
    _route = _ROUTES.get((signal, state))
    return (f"{signal.name} is not admitted by state {state.name} (§14.3) — admitted here: "
            + ", ".join(s.name for s in _valid)
            + (f". {_route}" if _route else ""))
