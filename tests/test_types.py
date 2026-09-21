"""Tests for types/ module."""
import pytest

from gfso.core.types import (
    State, Signal, DoneReason, Verdict, FM, AutonomyLevel, MutationType,
    TERMINAL_STATES, NON_TERMINAL_STATES,
    TaskId, AgentId, Criteria, Spec, Task, GuardContext,
    CheckResult, Recommendation, GraphContext, SignalData,
    MutateGraph, RunChecks, Recommend, Dispatch, EmitSignal,
)


def test_state_count():
    assert len(State) == 12  # canon v3.7 §14.3: +CANCELLING (non-terminal), +ABANDONED (terminal, V=⊥)


def test_signal_count():
    assert len(Signal) == 13


def test_fm_count():
    assert len(FM) == 7


def test_terminal_states():
    """TERMINAL = the work is OVER. Two states qualify, and ESCALATED is not one of them.

    It used to be filed here, which conflated a SETTLEMENT (the work ended) with a HANDOVER (the
    executor's contract ended and the issuer's decision begins). ESCALATED is the second, and it is
    the issuer's waiting state — symmetric to OFFERED, where the executor owes the answer (Inv-4)."""
    assert State.DONE in TERMINAL_STATES
    assert State.ABANDONED in TERMINAL_STATES  # v3.7 §14.3: terminal, V=⊥
    assert State.ESCALATED not in TERMINAL_STATES
    assert len(TERMINAL_STATES) == 2


def test_non_terminal_states():
    assert len(NON_TERMINAL_STATES) == 10
    assert State.ESCALATED in NON_TERMINAL_STATES  # the issuer's waiting state, not a settlement
    assert State.CANCELLING in NON_TERMINAL_STATES  # v3.7 §14.3: handshake in flight
    assert State.DONE not in NON_TERMINAL_STATES


def test_task_defaults():
    spec = Spec("test", (Criteria("c1", "desc"),))
    t = Task(id=TaskId("t1"), spec=spec)
    assert t.state == State.IDLE
    assert t.iteration == 0
    # 12, not 3: Inv-5 demands the DELIVER→FAIL loop be FINITE, never a particular size, and
    # the size is chosen for the user this product has. A low bound protects a HUMAN issuer's
    # attention; in agent work issuer and executor are one, so it protected nobody and cost a
    # terminal node — at a root, a second root with no memory of the refusals (2026-09-20).
    assert t.max_iterations == 12
    assert t.done_reason is None


def test_spec_frozen():
    spec = Spec("test", (Criteria("c1", "desc"),), ("risk1",))
    with pytest.raises(AttributeError):
        spec.description = "changed"


def test_effects_frozen():
    mg = MutateGraph(TaskId("t1"), MutationType.SET_STATE, new_state=State.OFFERED)
    with pytest.raises(AttributeError):
        mg.task_id = TaskId("t2")


def test_guard_context():
    ctx = GuardContext(iteration=2, max_iterations=3)
    assert ctx.iteration == 2
    assert ctx.max_iterations == 3


def test_signal_data():
    sd = SignalData(signal=Signal.ASSIGN, task_id=TaskId("t1"))
    assert sd.signal == Signal.ASSIGN
    assert sd.spec is None
    assert sd.failed_criteria == ()
