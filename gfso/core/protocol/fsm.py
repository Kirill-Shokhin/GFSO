"""THE TABLE. (State, Signal, Guard) → (NewState, [Effects])."""
from __future__ import annotations

from typing import Callable, Optional

from gfso.core.protocol.validation import Role, required_role
from gfso.core.types import (
    State, Signal, DoneReason, MutationType,
    GuardContext, Effect, SignalData,
    MutateGraph, RunChecks, Dispatch,
    NON_TERMINAL_STATES, REASSIGNABLE_STATES, QUASI_TERMINAL_STATES, TaskId, DEFAULT_MAX_ITERATIONS,
)


def _mg(task_id: TaskId, new_state: State, done_reason: DoneReason | None = None) -> MutateGraph:
    return MutateGraph(
        task_id=task_id,
        mutation=MutationType.SET_STATE,
        new_state=new_state,
        done_reason=done_reason,
    )


def _lapse(task_id: TaskId) -> TransitionResult:
    """A first timeout of a wait (OFFERED, CHALLENGED, EXECUTING, REWORKING) → ESCALATED at once.

    There used to be a transit between them, OVERDUE, where the miss had been handed to nobody:
    it admitted no progress signal and no revision, so its owner held only CANCEL, and its one
    exit was a second timeout into the state where the issuer actually decides. A wait that ends
    in a wait that decides nothing is a delay, not a state — the lapse is handed over directly."""
    return (State.ESCALATED, [_mg(task_id, State.ESCALATED)])


# (State, Signal) → builder(task_id, guard) → Optional[(NewState, [Effect])]
# None return = guard rejected
TransitionResult = Optional[tuple[State, list[Effect]]]

_TABLE: list[tuple] = []


def _row(state: State, signal: Signal):
    """Decorator to register a transition row."""
    def decorator(fn):
        """Register `fn` as the handler for this (state, signal) pair and return it unchanged."""
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
# BY NAME ("every non-terminal state except IDLE", §12.12) and is not breached here, because an IDLE
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
    return _lapse(tid)


# === CHALLENGED ===

@_row(State.CHALLENGED, Signal.ACCEPT_CHALLENGE)
def _(tid: TaskId, ctx: GuardContext) -> TransitionResult:
    # Through APPLY_SPEC even when it carries no new spec (`None` = keep the contract): §12.3 puts
    # ACCEPT_CHALLENGE beside the ASSIGNs as an entry into OFFERED that must carry a deadline lying
    # ahead of it, and the bare row set the state and nothing else — so a dispute accepted after the
    # contract's time had run re-offered work that was overdue on arrival.
    return (State.OFFERED, [
        MutateGraph(tid, MutationType.APPLY_SPEC, max_iterations=None),
        _mg(tid, State.OFFERED),
        RunChecks(tid),
        Dispatch(tid, Signal.ACCEPT_CHALLENGE),
    ])


@_row(State.CHALLENGED, Signal.REJECT_CHALLENGE)
def _(tid: TaskId, ctx: GuardContext) -> TransitionResult:
    # BACK TO THE WAIT THE CHALLENGE INTERRUPTED. The contract stands, so nothing about it moves —
    # packet, deadline and rework count as they were, no new version. What differs is whether the
    # executor had consented to it: a challenge raised from OFFERED interrupted an offer, and
    # sending him on to EXECUTING put him to work on terms he never ACCEPTed. He owes that answer
    # still, and the offer is where he gives it.
    back = State.EXECUTING if ctx.consented else State.OFFERED
    return (back, [
        _mg(tid, back),
        Dispatch(tid, Signal.REJECT_CHALLENGE),
    ])


@_row(State.CHALLENGED, Signal.TIMEOUT)
def _(tid: TaskId, ctx: GuardContext) -> TransitionResult:
    # A challenge is NOT auto-accepted in the executor's favour — that would silently resolve a
    # disputed spec; the lapse hands the undecided dispute to its issuer.
    return _lapse(tid)


# === EXECUTING ===

@_row(State.EXECUTING, Signal.DELIVER)
def _(tid: TaskId, ctx: GuardContext) -> TransitionResult:
    return (State.VALIDATING, [
        _mg(tid, State.VALIDATING),
        Dispatch(tid, Signal.DELIVER),
    ])


@_row(State.EXECUTING, Signal.CHALLENGE)
def _(tid: TaskId, ctx: GuardContext) -> TransitionResult:
    # THE SPEC DEFECT MET AT CONTACT (§12.4). v4.0 admitted CHALLENGE only before consent, so an
    # executor who found the contract wrong while working had to route it through BLOCK — and the
    # dispute then lost both of its §16.12 closures: REJECT_CHALLENGE with a justification, and
    # ACCEPT_CHALLENGE as the positive one. That is exactly where most spec defects arrive: the
    # a-priori battery cannot see FM-1.d, FM-2 or FM-3's form, and §11.3 names CHALLENGE as one of
    # the two backward carriers. What ACCEPT protects is untouched — the contract binds until the
    # issuer answers, and REJECT_CHALLENGE returns the node here under the same packet version.
    return (State.CHALLENGED, [
        _mg(tid, State.CHALLENGED),
        Dispatch(tid, Signal.CHALLENGE),
    ])


@_row(State.REWORKING, Signal.CHALLENGE)
def _(tid: TaskId, ctx: GuardContext) -> TransitionResult:
    # …and from rework, for the reason REWORKING carries BLOCK (§12.4): it is a work-active state
    # under the same contract, so a defect met in it must be reportable through the channel that
    # answers it. Measured before the edge existed: an executor five rounds into an unsatisfiable
    # criterion reached for CHALLENGE, was refused, and re-delivered instead.
    return (State.CHALLENGED, [
        _mg(tid, State.CHALLENGED),
        Dispatch(tid, Signal.CHALLENGE),
    ])


@_row(State.EXECUTING, Signal.BLOCK)
def _(tid: TaskId, ctx: GuardContext) -> TransitionResult:
    return (State.BLOCKED, [
        _mg(tid, State.BLOCKED),
        Dispatch(tid, Signal.BLOCK),
    ])


@_row(State.EXECUTING, Signal.TIMEOUT)
def _(tid: TaskId, ctx: GuardContext) -> TransitionResult:
    return _lapse(tid)


# === BLOCKED ===

@_row(State.BLOCKED, Signal.RESOLVE_BLOCK)
def _(tid: TaskId, ctx: GuardContext) -> TransitionResult:
    # ADJUDICATE_DEP with no payload = CONFIRM any provisional discovered-Dep this task's BLOCK recorded
    # (§15.5: RESOLVE_BLOCK adjudicates truth; the re-attribute/retract variants carry payload → transition()).
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
    # ESCALATION trigger (§12.15: "the FAIL↔REWORKING loop bounded by max_iterations", with
    # escalation as its exit), not a terminal acceptance: the canon carries NO terminal for
    # "V = fail, settled" — its negative terminals are ABANDONED (V = ⊥, cancelled) and ESCALATED
    # (attention needed) — and §12.4 states as fact that DONE is reached through acceptance
    # (PASS ∨ auto_pass), never through fail. A DONE(fail) also becomes CONSUMABLE under R′
    # (§12.14), letting a Dep-consumer read-and-build on a failure, and buries the exact event
    # §19.1's third mode exists to surface. Closes corner #3 of `formal/README.md`.
    if ctx.iteration < ctx.max_iterations:
        return (State.REWORKING, [
            MutateGraph(tid, MutationType.INCREMENT_ITERATION),
            _mg(tid, State.REWORKING),
            Dispatch(tid, Signal.FAIL),
        ])
    # The settlement REASON is carried onto the terminal: ESCALATED is reached by this route and by
    # the timeouts of the waits, and only this one is a VERDICT. Without the
    # reason the metric populations that read "a standing FAIL" (q_D's exhausted arm,
    # `false_fail_share`) would silently empty out — a blind metric reads as a clean one.
    return (State.ESCALATED, [
        _mg(tid, State.ESCALATED, DoneReason.FAIL),
        Dispatch(tid, Signal.FAIL),
    ])


@_row(State.VALIDATING, Signal.TIMEOUT)
def _(tid: TaskId, ctx: GuardContext) -> TransitionResult:
    # THE ISSUER DID NOT VALIDATE IN TIME, AND THE CLOCK DOES NOT VALIDATE FOR HIM (§16.14). Until v4.1
    # this closed DONE(auto_pass) — an acceptance nobody made, which AND then read upward as a
    # verdict, and which a parent's executor could obtain over his own child by simply letting its
    # VALIDATING lapse. It is the one timeout that invented a verdict, and the framework's whole
    # claim is that "done" exists only as a verdict at a seam. So the delivery stays in the log and
    # the decision goes back to the party who owes it: ESCALATED, where his re-ASSIGN re-presents
    # the delivery (Inv-1) and his second silence closes the node without ever passing it.
    return (State.ESCALATED, [
        _mg(tid, State.ESCALATED),
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
    return _lapse(tid)


# === ESCALATED (§12.5: the ISSUER's waiting state, symmetric to OFFERED) ===

@_row(State.ESCALATED, Signal.TIMEOUT)
def _(tid: TaskId, ctx: GuardContext) -> TransitionResult:
    # Inv-5 applies again now that this is a live state, and the destination is forced by what the
    # state means. The issuer was handed a decision and did not make it; the node may not sit for
    # ever (finiteness), and it may not drift toward PASS either — the VALIDATING auto-pass exists
    # because a delivered result with no verdict in time is an issuer-inaction ACCEPTANCE, whereas
    # here nothing is on the table to accept: the executor stopped. Silence therefore CLOSES.
    #
    # Through CANCELLING, not straight to ABANDONED, and the difference is the SUBTREE. Escalation
    # cascades nothing, so an escalated node's children are still live under their own contracts;
    # settling only the parent leaves the product handing out work under a goal nobody owns any
    # more — a silence this very edge would otherwise create. Silence IS the issuer's cancellation,
    # so it takes the cancellation's own path: the cascade reaches every live descendant, each runs
    # its own handshake, and CANCELLING's grace keeps the whole thing finite (Inv-5). The
    # settlement is the same ABANDONED either way; what differs is that the tree goes with it.
    return (State.CANCELLING, [
        _mg(tid, State.CANCELLING),
        # …and the node's OWN executor is told, like every cascaded child is. The children re-enter
        # through the CANCEL catch-all, which dispatches; this edge did not, so the one party whose
        # contract actually ended by the clock was the one nobody informed.
        Dispatch(tid, Signal.CANCEL),
    ])


# === CANCELLING (§12.6: cancellation is a two-step handshake, mirror of ASSIGN→ACCEPT) ===

@_row(State.CANCELLING, Signal.CONFIRM_CANCEL)
def _(tid: TaskId, ctx: GuardContext) -> TransitionResult:
    # Sole staffed exit from CANCELLING (CONFIRM_CANCEL's defect type = FSM-deadlock, §11.4). The in-flight
    # report rides on SignalData.in_flight → audit log (Thm 11); no done_reason — ABANDONED is its own state, V=⊥.
    return (State.ABANDONED, [
        _mg(tid, State.ABANDONED),
        Dispatch(tid, Signal.CONFIRM_CANCEL),
    ])


@_row(State.CANCELLING, Signal.TIMEOUT)
def _(tid: TaskId, ctx: GuardContext) -> TransitionResult:
    # Cancellation is authoritative (§12.6): executor silence still completes it, just without the in-flight report.
    return (State.ABANDONED, [
        _mg(tid, State.ABANDONED),
    ])


#: The states whose (state, BLOCK) row exists; the payload branch in `transition()` admits no
#: others (the table tests enumerate payloads, so a widening here goes red there).
_BLOCKABLE = (State.EXECUTING, State.REWORKING)


# === Build lookup ===

_LOOKUP: dict[tuple[State, Signal], Callable] = {
    (state, signal): fn for state, signal, fn in _TABLE
}


def available_signals(state: State) -> list[Signal]:
    """Signals that have a transition row from this state (+ the catch-alls: universal CANCEL for
    non-terminals except CANCELLING (§12.6: its sole staffed exit is CONFIRM_CANCEL), and re-ASSIGN for
    revisable states (§12.3 Inv-1)).

    Pure on State. Used to expose valid actions per (state, role) to UIs/agents (§11.2).
    """
    sigs = [signal for (st, signal) in _LOOKUP if st == state]
    if state in NON_TERMINAL_STATES and state != State.CANCELLING and Signal.CANCEL not in sigs:
        sigs.append(Signal.CANCEL)
    if state in REASSIGNABLE_STATES and Signal.ASSIGN not in sigs:
        sigs.append(Signal.ASSIGN)
    if state in QUASI_TERMINAL_STATES and Signal.ASSIGN not in sigs:
        sigs.append(Signal.ASSIGN)  # R′ REOPEN affordance (§12.14) — the finality-gate may still reject
    return sigs


def transition(
    state: State,
    signal_data: SignalData,
    ctx: GuardContext,
) -> TransitionResult:
    """THE transition function. Pure on (State, Signal, Guard).

    A re-ASSIGN or CANCEL that takes a node out of BLOCKED may carry the issuer's answer to the block's records — the
    payload RESOLVE_BLOCK carries (the confirmed source set, or `external`: refuted): §15.5 reads a discovery's
    latest adjudication off "RESOLVE_BLOCK's action or a re-ASSIGN's or CANCEL's reason". It is applied before the
    state change closes, as unanswered, whatever it leaves standing."""
    result = _transition(state, signal_data, ctx)
    if result is None:                       # inadmissible: nothing to answer
        return None
    new, effects = result
    # …out of BLOCKED, or out of ESCALATED, where a lapsed block hands the issuer the decision (§12.4, §12.5) and its
    # records already closed unanswered — the answer reaches those too (critic 5)
    if (state in (State.BLOCKED, State.ESCALATED) and new not in (State.BLOCKED, State.ESCALATED)
            and signal_data.signal in (Signal.ASSIGN, Signal.CANCEL) and (signal_data.blockers or signal_data.external)):
        effects = [MutateGraph(signal_data.task_id, MutationType.ADJUDICATE_DEP, dep_froms=signal_data.blockers,
                               dep_external=signal_data.external, dep_unanswered=True), *effects]
    return new, effects


def _transition(
    state: State,
    signal_data: SignalData,
    ctx: GuardContext,
) -> TransitionResult:
    signal = signal_data.signal
    task_id = signal_data.task_id

    # ANY_NON_TERMINAL + CANCEL catch-all → CANCELLING (§12.6: two-step handshake, mirror of ASSIGN→ACCEPT).
    # CANCELLING itself is excluded: its sole staffed exit is CONFIRM_CANCEL (re-CANCEL is a no-op, not a row).
    # The subtree cascade (§12.6: the protocol sends CANCEL to every descendant) fires HERE, on CANCEL —
    # mutations.apply returns the affected children for the loop to CANCEL, each running its own handshake.
    if signal == Signal.CANCEL and state in NON_TERMINAL_STATES and state != State.CANCELLING:
        return (State.CANCELLING, [
            _mg(task_id, State.CANCELLING),
            Dispatch(task_id, Signal.CANCEL),
        ])

    # BLOCK naming undeclared prerequisite NODE(s) — record a provisional discovered-Dep edge PER
    # prerequisite (§11.3/§15.5: real S\Ŝ edges falsifying the plan's implicit independence claim;
    # provenance = this BLOCK, Thm 11). One BLOCK may surface several blockers — collapsing them to one
    # edge starves q_Dep and blinds auto-resolve (observed live: a 3-blocker deadlock recorded 0 edges).
    # Payload-dependent → handled here; the bare-BLOCK case falls through to the table row (no edge).
    if signal == Signal.BLOCK and state in _BLOCKABLE and signal_data.blockers:
        return (State.BLOCKED, [
            *(MutateGraph(task_id, MutationType.RECORD_DEP, dep_from=b,
                          glue=signal_data.reason or "") for b in signal_data.blockers),
            _mg(task_id, State.BLOCKED),
            Dispatch(task_id, Signal.BLOCK),
        ])

    # RESOLVE_BLOCK adjudicating the provisional discovered-Dep(s) (§15.5): the passed blocker set is the
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
    # §11.3/§14.3; the only in-place spec change allowed to alter criteria). Needs signal_data, so it is
    # handled here; the no-spec case falls through to the table row (which also registers the affordance).
    if signal == Signal.ACCEPT_CHALLENGE and state == State.CHALLENGED and signal_data.new_spec is not None:
        return (State.OFFERED, [
            MutateGraph(task_id, MutationType.APPLY_SPEC, spec=signal_data.new_spec, max_iterations=None),
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
                        deadline=signal_data.deadline, deadline_supplied=signal_data.deadline_supplied,
                        max_iterations=(
                            DEFAULT_MAX_ITERATIONS if signal_data.max_iterations is None else signal_data.max_iterations),
                        covers=signal_data.covers),
            _mg(task_id, State.OFFERED),
            RunChecks(task_id),
            Dispatch(task_id, Signal.ASSIGN),
        ])

    # REVISION — canon v3.7 §12.3 Inv-1: a packet change on a LIVE node = re-ASSIGN under the SAME id →
    # OFFERED (the executor re-ACCEPTs/CHALLENGEs — the same IC protection as the first ASSIGN, §16.12).
    # NOT the CANCEL signal, no pass through CANCELLING, and NO cascade — the subtree is retained; staleness
    # surfaces via CHECK-1 + non-redundancy/CHECK-1b (dangling covers) + CHECK-3 (Dep consumers). Each
    # version is appended to the log (Inv-7: the immutable record is the LOG, not the node). Excluded:
    # IDLE (no packet to revise), CANCELLING (sole exit CONFIRM_CANCEL), terminals (no rows).
    # The single in-place spec change remains ACCEPT_CHALLENGE (above) — executor-initiated (CHALLENGE answers FM-1/FM-2, §11.2).
    # …and from ESCALATED a re-ASSIGN carrying NO spec is still a revision. On a live node a bare
    # ASSIGN means nothing and is refused (there is a contract and it did not change), but ESCALATED
    # is the issuer being asked to decide, and one of his three answers — "the forecast was short,
    # take more attempts" — changes only `max_iterations`. Demanding a spec there would force the
    # issuer to restate a contract he is not disputing in order to say the one thing he means.
    if (signal == Signal.ASSIGN and state in REASSIGNABLE_STATES
            and (signal_data.spec is not None or state == State.ESCALATED)):
        return (State.OFFERED, [
            MutateGraph(task_id, MutationType.APPLY_SPEC, spec=signal_data.spec,
                        assignee=signal_data.assignee,   # carries a new executor for reassign (Del change); None = keep
                        covers=signal_data.covers,       # (re)declared coverage of parent criteria (§2)
                        # …AND THE DEADLINE, which Inv-1 lists among the packet fields a revision
                        # exists to change ("criteria, deadline, ACCEPTED_RISKS, Del") and which
                        # this branch dropped on the floor. §14.3 walks the case end to end — a
                        # RESOLVE_BLOCK moving Feature B from d7 to d9, re-consented and re-checked
                        # against Testing's d12 — and none of it could happen: the revision was
                        # ACCEPTED, the node went to OFFERED, the executor re-consented, and the
                        # date did not move (probed 2026-09-07). None = keep, like `assignee`.
                        deadline=signal_data.deadline, deadline_supplied=signal_data.deadline_supplied,
                        # …AND THE REWORKING BOUND, dropped here for the same reason the deadline
                        # was. Exhausting the attempts has TWO readings and only the issuer can
                        # choose between them: the plan is wrong (change the plan), or the
                        # forecast was — fewer attempts were budgeted than the work needed. The
                        # engine decided the first for everyone by making the bound unrevisable,
                        # so a missed forecast broke the whole graph: the node escalated, and at
                        # a root the only way on was another root with no memory. An issuer who
                        # reads it as the second now simply says so. None = keep.
                        max_iterations=signal_data.max_iterations,
                        revision_reason=signal_data.revision_reason),  # causal typing (§15.4)
            _mg(task_id, State.OFFERED),
            RunChecks(task_id),
            Dispatch(task_id, Signal.ASSIGN),
        ])

    # R′ REOPEN — canon §12.14 "Финальность": DONE and ABANDONED are QUASI-terminal. A re-ASSIGN out of
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
            return None  # final: потреблён ∨ исчерпан счётчик (§12.14) — audit-rejected, Thm 11
        return (State.OFFERED, [
            MutateGraph(task_id, MutationType.REOPEN, spec=signal_data.spec,
                        assignee=signal_data.assignee, covers=signal_data.covers,
                        # …AND THE DEADLINE AND THE REWORKING BOUND. A REOPEN is a new packet version
                        # entering through OFFERED (§12.15), and every entry into OFFERED carries a
                        # live deadline; dropping them here reopened a node under the deadline it
                        # had already missed, which the entry check then spends on the spot.
                        deadline=signal_data.deadline, deadline_supplied=signal_data.deadline_supplied,
                        max_iterations=signal_data.max_iterations,
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
#: intent. Measured: an executor stuck on an unsatisfiable criterion reached for CHALLENGE, was
#: refused in silence, and re-delivered five times instead.
#: UNDER v4.1 THE ANSWER CHANGED, and this text is the thing an executor READS at the refusal.
#: It used to send a post-consent contract objection through BLOCK, on the ground that "CHALLENGE
#: is the pre-consent channel" — true of v4.0's admissible sets, false now: §12.4 admits CHALLENGE
#: from EXECUTING and REWORKING, for the reason those states carry BLOCK, and routing the dispute
#: through BLOCK instead loses both of its §16.12 closures (ACCEPT_CHALLENGE, REJECT_CHALLENGE with
#: its justification) exactly where most spec defects arrive. The table below moved with the rows;
#: this sentence did not, and a correct machine that tells its executor the wrong door is the same
#: stall by one more step.
_ROUTES = {
    (Signal.CHALLENGE, State.VALIDATING): (
        "the delivery is already with its issuer — a contract objection now travels with the FAIL "
        "you expect: put it in the re-DELIVER, or CHALLENGE from REWORKING once the FAIL lands "
        "(§12.4 admits it there; BLOCK is for a blocker, not for a contract you dispute)"),
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
    return (f"{signal.name} is not admitted by state {state.name} (§12.4) — admitted here: "
            + ", ".join(s.name for s in _valid)
            + (f". {_route}" if _route else ""))
