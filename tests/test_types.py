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
    assert State.DONE in TERMINAL_STATES
    assert State.ESCALATED in TERMINAL_STATES
    assert State.ABANDONED in TERMINAL_STATES  # v3.7 §14.3: terminal, V=⊥
    assert len(TERMINAL_STATES) == 3


def test_non_terminal_states():
    assert len(NON_TERMINAL_STATES) == 9
    assert State.CANCELLING in NON_TERMINAL_STATES  # v3.7 §14.3: handshake in flight
    assert State.DONE not in NON_TERMINAL_STATES


def test_task_defaults():
    spec = Spec("test", (Criteria("c1", "desc"),))
    t = Task(id=TaskId("t1"), spec=spec)
    assert t.state == State.IDLE
    assert t.iteration == 0
    assert t.max_iterations == 3
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
