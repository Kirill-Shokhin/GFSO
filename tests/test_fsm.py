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

def test_table_has_19_explicit_rows():
    assert len(_LOOKUP) == 19  # + CANCEL catch-all = 20 transitions


# === IDLE ===

def test_idle_assign():
    new_state, effects = _transition(State.IDLE, Signal.ASSIGN)
    assert new_state == State.REVIEW
    assert any(isinstance(e, MutateGraph) for e in effects)
    assert any(isinstance(e, RunChecks) for e in effects)
    assert any(isinstance(e, Recommend) for e in effects)
    assert any(isinstance(e, Dispatch) for e in effects)


# === REVIEW ===

def test_review_accept():
    new_state, effects = _transition(State.REVIEW, Signal.ACCEPT)
    assert new_state == State.EXECUTING

def test_review_challenge():
    new_state, effects = _transition(State.REVIEW, Signal.CHALLENGE)
    assert new_state == State.CHALLENGED

def test_review_timeout():
    new_state, effects = _transition(State.REVIEW, Signal.TIMEOUT)
    assert new_state == State.TIMEOUT


# === CHALLENGED ===

def test_challenged_accept_challenge():
    new_state, effects = _transition(State.CHALLENGED, Signal.ACCEPT_CHALLENGE)
    assert new_state == State.REVIEW
    assert any(isinstance(e, RunChecks) for e in effects)

def test_challenged_reject_challenge():
    new_state, effects = _transition(State.CHALLENGED, Signal.REJECT_CHALLENGE)
    assert new_state == State.EXECUTING

def test_challenged_timeout():
    new_state, effects = _transition(State.CHALLENGED, Signal.TIMEOUT)
    assert new_state == State.REVIEW  # auto-accept


# === EXECUTING ===

def test_executing_deliver():
    new_state, _ = _transition(State.EXECUTING, Signal.DELIVER)
    assert new_state == State.VALIDATING

def test_executing_block():
    new_state, _ = _transition(State.EXECUTING, Signal.BLOCK)
    assert new_state == State.BLOCKED

def test_executing_timeout():
    new_state, effects = _transition(State.EXECUTING, Signal.TIMEOUT)
    assert new_state == State.TIMEOUT


# === BLOCKED ===

def test_blocked_resolve():
    new_state, _ = _transition(State.BLOCKED, Signal.RESOLVE_BLOCK)
    assert new_state == State.EXECUTING

def test_blocked_timeout():
    new_state, _ = _transition(State.BLOCKED, Signal.TIMEOUT)
    assert new_state == State.ESCALATED  # direct, no TIMEOUT intermediate


# === VALIDATING ===

def test_validating_pass():
    new_state, effects = _transition(State.VALIDATING, Signal.PASS)
    assert new_state == State.DONE
    mg = [e for e in effects if isinstance(e, MutateGraph) and e.done_reason is not None][0]
    assert mg.done_reason == DoneReason.PASS

def test_validating_fail_rework():
    ctx = GuardContext(iteration=1, max_iterations=3)
    new_state, _ = _transition(State.VALIDATING, Signal.FAIL, ctx, failed_criteria=("c1",))
    assert new_state == State.REWORK

def test_validating_fail_done():
    ctx = GuardContext(iteration=3, max_iterations=3)
    new_state, effects = _transition(State.VALIDATING, Signal.FAIL, ctx, failed_criteria=("c1",))
    assert new_state == State.DONE
    mg = [e for e in effects if isinstance(e, MutateGraph) and e.done_reason is not None][0]
    assert mg.done_reason == DoneReason.FAIL

def test_validating_timeout():
    new_state, effects = _transition(State.VALIDATING, Signal.TIMEOUT)
    assert new_state == State.DONE
    mg = [e for e in effects if isinstance(e, MutateGraph) and e.done_reason is not None][0]
    assert mg.done_reason == DoneReason.AUTO
    assert any(isinstance(e, Dispatch) for e in effects)  # executor notified


# === REWORK ===

def test_rework_deliver():
    new_state, _ = _transition(State.REWORK, Signal.DELIVER)
    assert new_state == State.VALIDATING

def test_rework_block():
    new_state, _ = _transition(State.REWORK, Signal.BLOCK)
    assert new_state == State.BLOCKED

def test_rework_timeout():
    new_state, _ = _transition(State.REWORK, Signal.TIMEOUT)
    assert new_state == State.TIMEOUT


# === TIMEOUT ===

def test_timeout_repeated_timeout():
    new_state, _ = _transition(State.TIMEOUT, Signal.TIMEOUT)
    assert new_state == State.ESCALATED


# === CANCEL catch-all ===

@pytest.mark.parametrize("state", list(NON_TERMINAL_STATES))
def test_cancel_from_any_non_terminal(state):
    new_state, effects = _transition(state, Signal.CANCEL)
    assert new_state == State.DONE
    mg = [e for e in effects if isinstance(e, MutateGraph) and e.done_reason is not None][0]
    assert mg.done_reason == DoneReason.CANCELLED


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
    for sig in Signal:
        if sig in (Signal.ASSIGN, Signal.CANCEL):
            continue
        result = _transition(State.IDLE, sig)
        assert result is None, f"IDLE should reject {sig.name}"
