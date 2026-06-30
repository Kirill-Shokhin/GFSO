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


def test_cancel_cascade():
    g = _graph()
    parent = _task("parent", state=State.EXECUTING)
    child1 = _task("c1", state=State.EXECUTING, parent_id="parent")
    child2 = _task("c2", state=State.DONE, parent_id="parent")
    g.save_task(parent)
    g.save_task(child1)
    g.save_task(child2)

    effect = MutateGraph(
        TaskId("parent"), MutationType.SET_STATE,
        new_state=State.DONE, done_reason=DoneReason.CANCELLED,
    )
    affected = apply(g, effect)

    # Only non-terminal children returned for cascade
    assert TaskId("c1") in affected
    assert TaskId("c2") not in affected


def test_active_children_excludes_cancelled_tombstone():
    """B1 realization: CANCELLED nodes persist (provenance, §7.3.1) but leave the ACTIVE decomposition.
    get_children = all (provenance); get_active_children = excludes only DONE(CANCELLED); DONE(PASS/FAIL)
    stay active (delivered work)."""
    g = _graph()
    parent = _task("parent", state=State.EXECUTING)
    active = _task("a1c", state=State.EXECUTING, parent_id="parent")
    done_pass = _task("a2c", state=State.DONE, parent_id="parent")
    done_pass.done_reason = DoneReason.PASS
    cancelled = _task("a3c", state=State.DONE, parent_id="parent")
    cancelled.done_reason = DoneReason.CANCELLED
    for t in (parent, active, done_pass, cancelled):
        g.save_task(t)

    all_ids = {c.id for c in g.get_children(TaskId("parent"))}
    active_ids = {c.id for c in g.get_active_children(TaskId("parent"))}

    assert all_ids == {TaskId("a1c"), TaskId("a2c"), TaskId("a3c")}   # provenance keeps the tombstone
    assert active_ids == {TaskId("a1c"), TaskId("a2c")}                # cancelled excluded from active
    assert TaskId("a2c") in active_ids                                 # DONE(PASS) is active, not filtered


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
