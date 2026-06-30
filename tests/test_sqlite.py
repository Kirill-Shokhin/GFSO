"""Tests for SQLite StoragePort adapter."""
from datetime import datetime, timedelta
from gfso.core.types import (
    TaskId, AgentId, Task, State, DoneReason, Spec, Criteria,
    CriterionMapping, CheckResult, Recommendation, DepEdge,
)
from gfso.adapters.storage.sqlite import SqliteStorage


def _storage() -> SqliteStorage:
    return SqliteStorage(":memory:")


def _task(tid="t1", desc="test", criteria=(), parent_id=None, assignee="a1") -> Task:
    return Task(
        id=TaskId(tid),
        spec=Spec(desc, tuple(Criteria(c, c) for c in criteria), ("risk1",), ("drought",)),
        parent_id=TaskId(parent_id) if parent_id else None,
        assignee=AgentId(assignee) if assignee else None,
    )


def test_save_and_get():
    s = _storage()
    t = _task()
    s.save_task(t)
    got = s.get_task(TaskId("t1"))
    assert got is not None
    assert got.id == TaskId("t1")
    assert got.spec.description == "test"
    assert got.state == State.IDLE


def test_complex_spec_roundtrip():
    s = _storage()
    t = _task(criteria=["perf", "security"])
    s.save_task(t)
    got = s.get_task(TaskId("t1"))
    assert len(got.spec.criteria) == 2
    assert got.spec.criteria[0].name == "perf"
    assert got.spec.neglected[0].item == "risk1"
    assert got.spec.risk_components == ("drought",)


def test_get_nonexistent():
    s = _storage()
    assert s.get_task(TaskId("nope")) is None


def test_get_all_tasks():
    s = _storage()
    s.save_task(_task("t1"))
    s.save_task(_task("t2", desc="second"))
    assert len(s.get_all_tasks()) == 2


def test_children_and_parent():
    s = _storage()
    s.save_task(_task("p"))
    s.save_task(_task("c1", parent_id="p"))
    s.save_task(_task("c2", parent_id="p"))
    children = s.get_children(TaskId("p"))
    assert len(children) == 2
    parent = s.get_parent(TaskId("c1"))
    assert parent.id == TaskId("p")


def test_active_tasks():
    s = _storage()
    t1 = _task("t1")
    t1.state = State.EXECUTING
    t2 = _task("t2")
    t2.state = State.DONE
    s.save_task(t1)
    s.save_task(t2)
    active = s.get_active_tasks()
    assert len(active) == 1
    assert active[0].id == TaskId("t1")


def test_check_results():
    s = _storage()
    s.save_task(_task())
    results = [CheckResult("CHECK-1", True), CheckResult("CHECK-2", False, "cycle")]
    s.store_check_results(TaskId("t1"), results)
    got = s.get_check_results(TaskId("t1"))
    assert len(got) == 2
    assert got[0].check_name == "CHECK-1"
    assert got[1].passed is False


def test_check_results_overwrite():
    s = _storage()
    s.save_task(_task())
    s.store_check_results(TaskId("t1"), [CheckResult("old", True)])
    s.store_check_results(TaskId("t1"), [CheckResult("new", False)])
    got = s.get_check_results(TaskId("t1"))
    assert len(got) == 1
    assert got[0].check_name == "new"


def test_recommendation():
    s = _storage()
    s.save_task(_task())
    rec = Recommendation(("fix X", "add Y"))
    s.store_recommendation(TaskId("t1"), rec)
    got = s.get_recommendation(TaskId("t1"))
    assert got.suggestions == ("fix X", "add Y")


def test_dep_edges():
    s = _storage()
    s.add_dep_edge(DepEdge(TaskId("a"), TaskId("b"), discovered=False))
    s.add_dep_edge(DepEdge(TaskId("b"), TaskId("c"), discovered=True))
    edges = s.get_dep_edges()
    assert len(edges) == 2
    assert edges[1].discovered is True


def test_criterion_mappings():
    s = _storage()
    t = _task()
    t.criterion_mappings = (CriterionMapping("perf", TaskId("c1")),)
    s.save_task(t)
    got = s.get_task(TaskId("t1"))
    assert len(got.criterion_mappings) == 1
    assert got.criterion_mappings[0].criterion_name == "perf"


def test_task_flags():
    s = _storage()
    t = _task()
    t.was_challenged = True
    t.was_reassigned = True
    t.false_positive = True
    s.save_task(t)
    got = s.get_task(TaskId("t1"))
    assert got.was_challenged is True
    assert got.was_reassigned is True
    assert got.false_positive is True


def test_update_task():
    s = _storage()
    t = _task()
    s.save_task(t)
    t.state = State.REVIEW
    s.save_task(t)
    got = s.get_task(TaskId("t1"))
    assert got.state == State.REVIEW
