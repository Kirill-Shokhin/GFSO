"""Tests for protocol/fsm.py — every row of THE TABLE."""
import pytest
from gfso.core.types import (
    State, Signal, DoneReason, GuardContext, SignalData, TaskId,
    MutateGraph, RunChecks, Recommend, Dispatch,
    NON_TERMINAL_STATES,
)
from gfso.core.protocol.fsm import transition, _LOOKUP


TID = TaskId("t1")
CTX = GuardContext(iteration=0, max_iterations=3)


def _sd(signal: Signal, **kw) -> SignalData:
    return SignalData(signal=signal, task_id=TID, **kw)


def _transition(state, signal, ctx=CTX, **kw):
    return transition(state, _sd(signal, **kw), ctx)


# === Table row count ===

def test_table_has_21_explicit_rows():
    # 19 + (CANCELLING, CONFIRM_CANCEL) + (CANCELLING, TIMEOUT) — v3.7 §6.3 two-step cancellation.
    # There is NO (IDLE, TIMEOUT) row: Inv-5 exempts IDLE by name (§14.4) — the pre-contract state
    # carries no clock, and a crash orphan is recovered by finishing its interrupted ASSIGN.
    # Plus the catch-alls in transition(): universal CANCEL → CANCELLING, revision re-ASSIGN →
    # OFFERED, and the R′ REOPEN (quasi-terminal re-ASSIGN under the finality gate, §14.3).
    assert len(_LOOKUP) == 21


def test_idle_has_no_timeout_row():
    """IDLE is the ONE non-terminal Inv-5 exempts (§14.4): no clock before the contract."""
    assert (State.IDLE, Signal.TIMEOUT) not in _LOOKUP


def test_signal_alphabet_frozen_at_12_p2p_plus_timeout():
    """The protocol alphabet is CLOSED: 12 canonical P2P signals (§14.2) + the system TIMEOUT. Authoring
    operations (create / revise / abandon) are NOT signals — they desugar to these. This lock makes a 13th
    signal impossible by construction, so neither a new agent nor a reader can mistake an authoring op for
    a protocol primitive."""
    p2p = {
        Signal.ASSIGN, Signal.ACCEPT, Signal.CHALLENGE, Signal.BLOCK, Signal.DELIVER,
        Signal.CONFIRM_CANCEL, Signal.ACCEPT_CHALLENGE, Signal.REJECT_CHALLENGE, Signal.PASS,
        Signal.FAIL, Signal.CANCEL, Signal.RESOLVE_BLOCK,
    }
    assert len(p2p) == 12
    assert set(Signal) == p2p | {Signal.TIMEOUT}


# === IDLE ===

def test_idle_assign():
    new_state, effects = _transition(State.IDLE, Signal.ASSIGN)
    assert new_state == State.OFFERED
    assert any(isinstance(e, MutateGraph) for e in effects)
    assert any(isinstance(e, RunChecks) for e in effects)
    assert not any(isinstance(e, Recommend) for e in effects)  # deferred human-L2 convenience, off the agentic path
    assert any(isinstance(e, Dispatch) for e in effects)


# === OFFERED ===

def test_review_accept():
    new_state, effects = _transition(State.OFFERED, Signal.ACCEPT)
    assert new_state == State.EXECUTING

def test_review_challenge():
    new_state, effects = _transition(State.OFFERED, Signal.CHALLENGE)
    assert new_state == State.CHALLENGED

def test_review_timeout():
    new_state, effects = _transition(State.OFFERED, Signal.TIMEOUT)
    assert new_state == State.OVERDUE


# === CHALLENGED ===

def test_challenged_accept_challenge():
    new_state, effects = _transition(State.CHALLENGED, Signal.ACCEPT_CHALLENGE)
    assert new_state == State.OFFERED
    assert any(isinstance(e, RunChecks) for e in effects)

def test_challenged_accept_challenge_with_new_spec_applies():
    """The sanctioned spec-revision channel (§14.2/§14.6): ACCEPT_CHALLENGE(new_spec) must APPLY the
    renegotiated spec (may change criteria) — emits an APPLY_SPEC mutation, not a guarded SET_STATE."""
    new = Spec("revised", (Criteria("c2", "tighter"),))
    new_state, effects = _transition(State.CHALLENGED, Signal.ACCEPT_CHALLENGE, new_spec=new)
    assert new_state == State.OFFERED
    applied = [e for e in effects if isinstance(e, MutateGraph) and e.mutation == MutationType.APPLY_SPEC]
    assert len(applied) == 1 and applied[0].spec is new

def test_challenged_reject_challenge():
    new_state, effects = _transition(State.CHALLENGED, Signal.REJECT_CHALLENGE)
    assert new_state == State.EXECUTING

def test_challenged_timeout():
    new_state, effects = _transition(State.CHALLENGED, Signal.TIMEOUT)
    assert new_state == State.OVERDUE  # canon §14.3: escalate, do NOT auto-accept the challenge


# === EXECUTING ===

def test_executing_deliver():
    new_state, _ = _transition(State.EXECUTING, Signal.DELIVER)
    assert new_state == State.VALIDATING

def test_executing_block():
    new_state, _ = _transition(State.EXECUTING, Signal.BLOCK)
    assert new_state == State.BLOCKED

def test_executing_timeout():
    new_state, effects = _transition(State.EXECUTING, Signal.TIMEOUT)
    assert new_state == State.OVERDUE


# === BLOCKED ===

def test_blocked_resolve():
    new_state, _ = _transition(State.BLOCKED, Signal.RESOLVE_BLOCK)
    assert new_state == State.EXECUTING

def test_blocked_timeout():
    new_state, _ = _transition(State.BLOCKED, Signal.TIMEOUT)
    assert new_state == State.ESCALATED  # direct, no OVERDUE intermediate


# === VALIDATING ===

def test_validating_pass():
    new_state, effects = _transition(State.VALIDATING, Signal.PASS)
    assert new_state == State.DONE
    mg = [e for e in effects if isinstance(e, MutateGraph) and e.done_reason is not None][0]
    assert mg.done_reason == DoneReason.PASS

def test_validating_fail_rework():
    ctx = GuardContext(iteration=1, max_iterations=3)
    new_state, _ = _transition(State.VALIDATING, Signal.FAIL, ctx, failed_criteria=("c1",))
    assert new_state == State.REWORKING

def test_validating_fail_exhausted_escalates():
    """Exhausting the rework loop ESCALATES (§14.3) — it does not settle as DONE: the canon has no
    terminal for "V = fail, settled", and DONE is reached through acceptance only (§12.2). The
    verdict is carried onto the terminal so this escalation stays distinguishable from a timeout."""
    ctx = GuardContext(iteration=3, max_iterations=3)
    new_state, effects = _transition(State.VALIDATING, Signal.FAIL, ctx, failed_criteria=("c1",))
    assert new_state == State.ESCALATED
    mg = [e for e in effects if isinstance(e, MutateGraph) and e.done_reason is not None][0]
    assert mg.done_reason == DoneReason.FAIL

def test_validating_timeout():
    new_state, effects = _transition(State.VALIDATING, Signal.TIMEOUT)
    assert new_state == State.DONE
    mg = [e for e in effects if isinstance(e, MutateGraph) and e.done_reason is not None][0]
    assert mg.done_reason == DoneReason.AUTO_PASS
    assert any(isinstance(e, Dispatch) for e in effects)  # executor notified


# === REWORKING ===

def test_rework_deliver():
    new_state, _ = _transition(State.REWORKING, Signal.DELIVER)
    assert new_state == State.VALIDATING

def test_rework_block():
    new_state, _ = _transition(State.REWORKING, Signal.BLOCK)
    assert new_state == State.BLOCKED

def test_rework_timeout():
    new_state, _ = _transition(State.REWORKING, Signal.TIMEOUT)
    assert new_state == State.OVERDUE


# === OVERDUE ===

def test_timeout_repeated_timeout():
    new_state, _ = _transition(State.OVERDUE, Signal.TIMEOUT)
    assert new_state == State.ESCALATED


# === Cancellation — two-step handshake (v3.7 §14.3) ===

@pytest.mark.parametrize("state", sorted(NON_TERMINAL_STATES - {State.CANCELLING}, key=lambda s: s.name))
def test_cancel_from_any_non_terminal_opens_handshake(state):
    new_state, effects = _transition(state, Signal.CANCEL)
    assert new_state == State.CANCELLING
    assert not any(e.done_reason for e in effects if isinstance(e, MutateGraph))  # V=⊥, no DONE reason


def test_cancelling_rejects_re_cancel():
    """CANCELLING's sole staffed exit is CONFIRM_CANCEL (§14.3) — a repeated CANCEL is not a row."""
    assert _transition(State.CANCELLING, Signal.CANCEL) is None


def test_cancelling_confirm_cancel_settles():
    new_state, effects = _transition(State.CANCELLING, Signal.CONFIRM_CANCEL, in_flight="half-done, rolled back")
    assert new_state == State.ABANDONED
    assert any(isinstance(e, MutateGraph) and e.new_state == State.ABANDONED for e in effects)


def test_cancelling_timeout_settles():
    """Cancellation is authoritative (§14.3): executor silence completes it via timeout."""
    new_state, _ = _transition(State.CANCELLING, Signal.TIMEOUT)
    assert new_state == State.ABANDONED


def test_cancelling_rejects_progress_signals():
    for sig in (Signal.ASSIGN, Signal.ACCEPT, Signal.DELIVER, Signal.PASS, Signal.BLOCK):
        assert _transition(State.CANCELLING, sig) is None, f"CANCELLING should reject {sig.name}"


# === Revision — re-ASSIGN same id (v3.7 §14.4 Inv-1) ===

from gfso.core.types import Spec, Criteria, MutationType, REASSIGNABLE_STATES

_NEW_SPEC = Spec("revised", (Criteria("c2", "tighter"),))


@pytest.mark.parametrize("state", sorted(REASSIGNABLE_STATES, key=lambda s: s.name))
def test_reassign_live_node_is_revision_to_offered(state):
    """Revision = re-ASSIGN under the SAME id → OFFERED (NOT the CANCEL signal, no CANCELLING pass)."""
    new_state, effects = _transition(state, Signal.ASSIGN, spec=_NEW_SPEC)
    assert new_state == State.OFFERED
    applied = [e for e in effects if isinstance(e, MutateGraph) and e.mutation == MutationType.APPLY_SPEC]
    assert len(applied) == 1 and applied[0].spec is _NEW_SPEC
    assert any(isinstance(e, RunChecks) for e in effects)


def test_no_revision_from_timeout_or_cancelling():
    """OVERDUE accepts no progress signals; CANCELLING's sole exit is CONFIRM_CANCEL (§14.3)."""
    assert _transition(State.OVERDUE, Signal.ASSIGN, spec=_NEW_SPEC) is None
    assert _transition(State.CANCELLING, Signal.ASSIGN, spec=_NEW_SPEC) is None


def test_no_revision_of_terminal_nodes():
    """Terminal is terminal (§14.3) — incl. ABANDONED: no resurrect-by-re-ASSIGN (revision is for live nodes)."""
    for st in (State.DONE, State.ESCALATED, State.ABANDONED):
        assert _transition(st, Signal.ASSIGN, spec=_NEW_SPEC) is None


# === Invalid transitions ===

def test_done_rejects_all():
    for sig in Signal:
        result = _transition(State.DONE, sig)
        assert result is None, f"DONE should reject {sig.name}"

def test_escalated_rejects_all():
    for sig in Signal:
        if sig == Signal.CANCEL:
            continue  # CANCEL catch-all won't fire for terminal
        result = _transition(State.ESCALATED, sig)
        assert result is None, f"ESCALATED should reject {sig.name}"

def test_idle_rejects_non_assign():
    # IDLE admits exactly: ASSIGN (creation), CANCEL (universal catch-all), TIMEOUT (Inv-5 total —
    # the crash-orphan escape). Everything else is rejected.
    for sig in Signal:
        if sig in (Signal.ASSIGN, Signal.CANCEL, Signal.TIMEOUT):
            continue
        result = _transition(State.IDLE, sig)
        assert result is None, f"IDLE should reject {sig.name}"
