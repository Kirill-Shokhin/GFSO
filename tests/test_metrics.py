"""Tests for graph/metrics.py — all 5 metrics from paper §7.2."""
from gfso.core.types import TaskId, AgentId, Task, Spec, Criteria, State, DoneReason, DepEdge
from gfso.core.graph import Graph, q_T, q_D, q_V, q_Dep, q_Del
from gfso.adapters.storage.memory import MemoryStorage


def _task(tid, state=State.EXECUTING, assignee="a1", done_reason=None, was_challenged=False, parent_id=None):
    t = Task(
        id=TaskId(tid), spec=Spec("t", ()), state=state,
        assignee=AgentId(assignee) if assignee else None,
        done_reason=done_reason, parent_id=TaskId(parent_id) if parent_id else None,
    )
    t.was_challenged = was_challenged
    return t


def _graph(*tasks):
    g = Graph(MemoryStorage())
    for t in tasks:
        g.save_task(t)
    return g


# === q_T: spec quality ===

def test_q_T_perfect():
    g = _graph(
        _task("t1", State.DONE, done_reason=DoneReason.PASS),
        _task("t2", State.DONE, done_reason=DoneReason.PASS),
    )
    assert q_T(g) == 1.0

def test_q_T_half_challenged():
    g = _graph(
        _task("t1", State.DONE, done_reason=DoneReason.PASS, was_challenged=True),
        _task("t2", State.DONE, done_reason=DoneReason.PASS),
    )
    assert q_T(g) == 0.5

def test_q_T_empty():
    g = _graph()
    assert q_T(g) == 1.0


# === q_D: decomposition quality ===

def test_q_D_good_decomposition():
    g = _graph(
        _task("p", State.DONE, done_reason=DoneReason.PASS),
        _task("c1", State.DONE, done_reason=DoneReason.PASS, parent_id="p"),
        _task("c2", State.DONE, done_reason=DoneReason.PASS, parent_id="p"),
    )
    assert q_D(g) == 1.0

def test_q_D_bad_decomposition():
    # All children pass but parent fails → decomposition missed something
    g = _graph(
        _task("p", State.DONE, done_reason=DoneReason.FAIL),
        _task("c1", State.DONE, done_reason=DoneReason.PASS, parent_id="p"),
        _task("c2", State.DONE, done_reason=DoneReason.PASS, parent_id="p"),
    )
    assert q_D(g) == 0.0

def test_q_D_atomic_tasks_ignored():
    # Atomic tasks (no children) don't count
    g = _graph(
        _task("t1", State.DONE, done_reason=DoneReason.PASS),
    )
    assert q_D(g) == 1.0


# === q_V: validation quality (1 - false_positives / passed) ===

def test_q_V_no_false_positives():
    g = _graph(
        _task("t1", State.DONE, done_reason=DoneReason.PASS),
        _task("t2", State.DONE, done_reason=DoneReason.PASS),
    )
    assert q_V(g) == 1.0

def test_q_V_half_false_positive():
    t1 = _task("t1", State.DONE, done_reason=DoneReason.PASS)
    t1.false_positive = True
    g = _graph(t1, _task("t2", State.DONE, done_reason=DoneReason.PASS))
    assert q_V(g) == 0.5

def test_q_V_auto_pass_counts():
    # auto-pass included in denominator (can also be false positive)
    t1 = _task("t1", State.DONE, done_reason=DoneReason.AUTO)
    t1.false_positive = True
    g = _graph(t1, _task("t2", State.DONE, done_reason=DoneReason.PASS))
    assert q_V(g) == 0.5

def test_q_V_ignores_fail():
    g = _graph(
        _task("t1", State.DONE, done_reason=DoneReason.PASS),
        _task("t2", State.DONE, done_reason=DoneReason.FAIL),
    )
    assert q_V(g) == 1.0


# === q_Dep: dependency health ===

def test_q_Dep_all_declared():
    g = _graph(_task("t1"), _task("t2"))
    g._storage.add_dep_edge(DepEdge(TaskId("t1"), TaskId("t2"), discovered=False))
    assert q_Dep(g) == 1.0

def test_q_Dep_half_discovered():
    g = _graph(_task("t1"), _task("t2"), _task("t3"))
    g._storage.add_dep_edge(DepEdge(TaskId("t1"), TaskId("t2"), discovered=False))
    g._storage.add_dep_edge(DepEdge(TaskId("t2"), TaskId("t3"), discovered=True))
    assert q_Dep(g) == 0.5

def test_q_Dep_no_deps():
    g = _graph(_task("t1"))
    assert q_Dep(g) == 1.0


# === q_Del: delegation quality (1 - reassigned/done) ===

def test_q_Del_no_reassignment():
    g = _graph(
        _task("t1", State.DONE, done_reason=DoneReason.PASS),
        _task("t2", State.DONE, done_reason=DoneReason.PASS),
    )
    assert q_Del(g) == 1.0

def test_q_Del_half_reassigned():
    t1 = _task("t1", State.DONE, done_reason=DoneReason.PASS)
    t1.was_reassigned = True
    g = _graph(
        t1,
        _task("t2", State.DONE, done_reason=DoneReason.PASS),
    )
    assert q_Del(g) == 0.5

def test_q_Del_empty():
    g = _graph()
    assert q_Del(g) == 1.0
