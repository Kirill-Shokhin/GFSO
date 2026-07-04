"""Tests for graph/mutations.py."""
import pytest
from gfso.core.types import (
    TaskId, AgentId, Task, State, DoneReason, MutationType, Spec, Criteria,
    MutateGraph,
)
from gfso.core.graph import Graph
from gfso.core.graph.mutations import apply, InvariantViolation
from gfso.adapters.storage.memory import MemoryStorage


def _graph() -> Graph:
    return Graph(MemoryStorage())


def _task(tid="t1", state=State.IDLE, parent_id=None) -> Task:
    return Task(
        id=TaskId(tid),
        spec=Spec("test", (Criteria("c1", "c1"),)),
        state=state,
        parent_id=TaskId(parent_id) if parent_id else None,
        assignee=AgentId("a1"),
    )


def test_set_state():
    g = _graph()
    t = _task()
    g.save_task(t)

    effect = MutateGraph(TaskId("t1"), MutationType.SET_STATE, new_state=State.REVIEW)
    affected = apply(g, effect)

    assert g.get_state(TaskId("t1")) == State.REVIEW
    assert affected == []


def test_set_state_done_with_reason():
    g = _graph()
    t = _task(state=State.VALIDATING)
    g.save_task(t)

    effect = MutateGraph(TaskId("t1"), MutationType.SET_STATE, new_state=State.DONE, done_reason=DoneReason.PASS)
    apply(g, effect)

    task = g.get_task(TaskId("t1"))
    assert task.state == State.DONE
    assert task.done_reason == DoneReason.PASS


def test_cancel_cascade_fires_on_entering_cancelling():
    """v3.7 §6.2: the cascade fires on CANCEL (= entering CANCELLING) — non-terminal, not-yet-cancelling
    children are returned for the loop to CANCEL (each runs its own handshake)."""
    g = _graph()
    parent = _task("parent", state=State.EXECUTING)
    child1 = _task("c1", state=State.EXECUTING, parent_id="parent")
    child2 = _task("c2", state=State.DONE, parent_id="parent")
    child3 = _task("c3", state=State.CANCELLING, parent_id="parent")
    for t in (parent, child1, child2, child3):
        g.save_task(t)

    affected = apply(g, MutateGraph(TaskId("parent"), MutationType.SET_STATE, new_state=State.CANCELLING))

    assert TaskId("c1") in affected      # live child → cascade CANCEL
    assert TaskId("c2") not in affected  # terminal untouched
    assert TaskId("c3") not in affected  # already settling its own handshake

    # settling the handshake (CANCEL_ACK → CANCELLED) does NOT re-cascade
    affected2 = apply(g, MutateGraph(TaskId("parent"), MutationType.SET_STATE, new_state=State.CANCELLED))
    assert affected2 == []


def test_active_children_excludes_cancellation():
    """CANCELLED nodes persist (provenance, §7.3.1) but leave the ACTIVE decomposition — at CANCEL
    already (cancellation is authoritative, §6.3), so CANCELLING is excluded too. DONE(PASS/FAIL)
    stay active (delivered work)."""
    g = _graph()
    parent = _task("parent", state=State.EXECUTING)
    active = _task("a1c", state=State.EXECUTING, parent_id="parent")
    done_pass = _task("a2c", state=State.DONE, parent_id="parent")
    done_pass.done_reason = DoneReason.PASS
    cancelled = _task("a3c", state=State.CANCELLED, parent_id="parent")
    cancelling = _task("a4c", state=State.CANCELLING, parent_id="parent")
    for t in (parent, active, done_pass, cancelled, cancelling):
        g.save_task(t)

    all_ids = {c.id for c in g.get_children(TaskId("parent"))}
    active_ids = {c.id for c in g.get_active_children(TaskId("parent"))}

    assert all_ids == {TaskId("a1c"), TaskId("a2c"), TaskId("a3c"), TaskId("a4c")}  # provenance keeps all
    assert active_ids == {TaskId("a1c"), TaskId("a2c")}   # cancellation (both phases) excluded from active


def test_increment_iteration():
    g = _graph()
    t = _task()
    g.save_task(t)

    effect = MutateGraph(TaskId("t1"), MutationType.INCREMENT_ITERATION)
    apply(g, effect)

    assert g.get_task(TaskId("t1")).iteration == 1


def test_create_task():
    g = _graph()
    spec = Spec("new task", (Criteria("c1", "c1"),))
    effect = MutateGraph(
        TaskId("new1"), MutationType.CREATE_TASK,
        spec=spec, assignee=AgentId("a1"),
    )
    apply(g, effect)

    task = g.get_task(TaskId("new1"))
    assert task is not None
    assert task.spec.description == "new task"


# === Invariant enforcement ===

def test_criteria_immutability_violation():
    g = _graph()
    t = _task()
    g.save_task(t)

    new_spec = Spec("test", (Criteria("DIFFERENT", "changed"),))
    effect = MutateGraph(
        TaskId("t1"), MutationType.SET_STATE,
        new_state=State.REVIEW, spec=new_spec,
    )
    with pytest.raises(InvariantViolation):
        apply(g, effect)


def test_challenge_sets_was_challenged():
    g = _graph()
    t = _task()
    g.save_task(t)

    # Transition to CHALLENGED
    effect = MutateGraph(TaskId("t1"), MutationType.SET_STATE, new_state=State.CHALLENGED)
    apply(g, effect)

    assert g.get_task(TaskId("t1")).was_challenged is True
