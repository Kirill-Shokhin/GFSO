"""Tests for handlers/structural.py — CHECK-1 through CHECK-6."""
from datetime import datetime, timedelta
from gfso.core.types import (
    Task, TaskId, AgentId, Spec, Criteria, CriterionMapping,
    NeglectedItem, Predictability,
)
from gfso.core.handlers.structural import (
    check_coverage, check_dag, check_deadlines,
    check_neglected, check_risk_nodes, check_delegation,
    check_non_redundancy,
    run_structural,
)


def _task(tid: str, desc: str = "", criteria=(), neglected=(), assignee=None, deadline=None, mappings=(), risk_components=()) -> Task:
    return Task(
        id=TaskId(tid),
        spec=Spec(desc, tuple(Criteria(c, c) for c in criteria), tuple(neglected), tuple(risk_components)),
        assignee=AgentId(assignee) if assignee else None,
        deadline=deadline,
        criterion_mappings=tuple(mappings),
    )


# === CHECK-1: Coverage (explicit mapping) ===

def test_coverage_pass():
    parent = _task("p", criteria=["perf", "security"], mappings=[
        CriterionMapping("perf", TaskId("c1")),
        CriterionMapping("security", TaskId("c2")),
    ])
    c1 = _task("c1", desc="perf optimization")
    c2 = _task("c2", desc="security audit")
    assert check_coverage(parent, [c1, c2]).passed

def test_coverage_fail_uncovered():
    parent = _task("p", criteria=["perf", "security"], mappings=[
        CriterionMapping("perf", TaskId("c1")),
    ])
    c1 = _task("c1", desc="perf optimization")
    result = check_coverage(parent, [c1])
    assert not result.passed
    assert "security" in result.details

def test_coverage_fail_no_mappings():
    parent = _task("p", criteria=["perf"])
    c1 = _task("c1")
    result = check_coverage(parent, [c1])
    assert not result.passed
    assert "no criterion mappings" in result.details

def test_coverage_fail_invalid_child():
    parent = _task("p", criteria=["perf"], mappings=[
        CriterionMapping("perf", TaskId("nonexistent")),
    ])
    c1 = _task("c1")
    result = check_coverage(parent, [c1])
    assert not result.passed
    assert "not found" in result.details

def test_coverage_leaf_skipped():
    parent = _task("p", criteria=["perf"])
    result = check_coverage(parent, [])
    assert result.skipped  # leaf tasks don't need children coverage

def test_coverage_no_criteria():
    parent = _task("p")
    assert check_coverage(parent, []).passed


# === CHECK-2: DAG ===

def test_dag_no_cycle():
    children = [_task("a"), _task("b"), _task("c")]
    edges = [("a", "b"), ("b", "c")]
    assert check_dag(children, edges).passed

def test_dag_cycle():
    children = [_task("a"), _task("b"), _task("c")]
    edges = [("a", "b"), ("b", "c"), ("c", "a")]
    assert not check_dag(children, edges).passed

def test_dag_empty():
    assert check_dag([], []).passed


# === CHECK-3: Deadlines ===

def test_deadlines_consistent():
    now = datetime.now()
    parent = _task("p", deadline=now + timedelta(days=10))
    c1 = _task("c1", deadline=now + timedelta(days=3))
    c2 = _task("c2", deadline=now + timedelta(days=7))
    edges = [("c1", "c2")]
    assert check_deadlines(parent, [c1, c2], edges).passed

def test_deadlines_violated():
    now = datetime.now()
    parent = _task("p", deadline=now + timedelta(days=10))
    c1 = _task("c1", deadline=now + timedelta(days=7))
    c2 = _task("c2", deadline=now + timedelta(days=3))
    edges = [("c1", "c2")]  # c1 depends on c2, but c1.deadline > c2.deadline → violation
    result = check_deadlines(parent, [c1, c2], edges)
    assert not result.passed


# === CHECK-4: NEGLECTED (v3.7 §5.1: gates DECOMPOSED nodes only — per-decomposition) ===

def test_neglected_present():
    t = _task("t", neglected=[NeglectedItem("api rate limit", Predictability.EXTRAORDINARY)])
    assert check_neglected(t, [_task("c1")]).passed

def test_neglected_empty_on_decomposed_fails():
    t = _task("t")
    assert not check_neglected(t, [_task("c1")]).passed

def test_neglected_leaf_skipped():
    """A leaf (D=∅) has no decomposition → NEGLECTED vacuous, CHECK-4 does not gate it (§5.1)."""
    assert check_neglected(_task("t"), []).skipped


# === CHECK-5: Risk nodes (STD-3) ===

def test_risk_nodes_covered():
    t = _task("t", risk_components=["drought", "supply_chain"])
    c1 = _task("c1", desc="handle drought mitigation")
    c2 = _task("c2", desc="supply_chain backup plan")
    assert check_risk_nodes(t, [c1, c2]).passed

def test_risk_nodes_uncovered():
    t = _task("t", risk_components=["drought", "supply_chain"])
    c1 = _task("c1", desc="handle drought mitigation")
    result = check_risk_nodes(t, [c1])
    assert not result.passed
    assert "supply_chain" in result.details

def test_risk_nodes_no_components():
    t = _task("t")
    assert check_risk_nodes(t, []).passed

def test_risk_nodes_no_children():
    t = _task("t", risk_components=["drought"])
    assert not check_risk_nodes(t, []).passed


# === CHECK-6: Delegation ===

def test_delegation_all_assigned():
    children = [_task("c1", assignee="a1"), _task("c2", assignee="a2")]
    assert check_delegation(children).passed

def test_delegation_missing():
    children = [_task("c1", assignee="a1"), _task("c2")]
    result = check_delegation(children)
    assert not result.passed
    assert "c2" in result.details


# === CHECK-1b: Non-redundancy (second side of FM-1) ===

def test_non_redundancy_pass():
    parent = _task("p", criteria=["perf"], mappings=[CriterionMapping("perf", TaskId("c1"))])
    c1 = _task("c1", desc="perf work")
    assert check_non_redundancy(parent, [c1]).passed

def test_non_redundancy_fail_superfluous_child():
    parent = _task("p", criteria=["perf"], mappings=[CriterionMapping("perf", TaskId("c1"))])
    c1 = _task("c1", desc="perf work")
    c2 = _task("c2", desc="unrelated extra")  # mapped to nothing
    result = check_non_redundancy(parent, [c1, c2])
    assert not result.passed
    assert "c2" in result.details

def test_non_redundancy_leaf_skipped():
    assert check_non_redundancy(_task("p", criteria=["x"]), []).skipped


# === CHECK-4 record form (§5.1/Ст. I.10: an incomplete record is not a NEGLECTED record) ===

def _task_neg(neglected):
    return Task(id=TaskId("t"), spec=Spec("t", (), tuple(neglected)))

_KID = [Task(id=TaskId("k"), spec=Spec("k", ()))]  # decomposed → CHECK-4 gates

def test_neglected_record_unclassified_fails_on_decomposed():
    """The predictability verdict is mandatory per factor (§5.1) — it doubles as the risk-vs-scope
    discriminator: no materialization P → scope boundary (goal criteria/CHECK-1), not NEGLECTED."""
    r = check_neglected(_task_neg([NeglectedItem("x")]), _KID)
    assert not r.passed and "predictability" in r.details

def test_neglected_record_ordinary_contradiction_fails():
    """A self-declared ORDINARY factor in NEGLECTED is an internal contradiction of the record (§5.2)."""
    r = check_neglected(_task_neg([NeglectedItem("drought", Predictability.ORDINARY)]), _KID)
    assert not r.passed and "ORDINARY" in r.details

def test_neglected_record_statistical_needs_justification():
    bad = _task_neg([NeglectedItem("rare outage", Predictability.STATISTICAL)])
    assert not check_neglected(bad, _KID).passed
    ok = _task_neg([NeglectedItem("rare outage", Predictability.STATISTICAL, "P<1%, out of budget")])
    assert check_neglected(ok, _KID).passed

def test_neglected_record_extraordinary_ok():
    t = _task_neg([NeglectedItem("meteorite", Predictability.EXTRAORDINARY)])
    assert check_neglected(t, _KID).passed


# === Full run ===

def test_run_structural_returns_all_checks():
    # The check set is the CANON's L0 list (§5.4): CHECK-1, 1b, 2–6 — no invented check names.
    parent = _task("p", criteria=["perf"], neglected=["risks"], mappings=[
        CriterionMapping("perf", TaskId("c1")),
    ])
    child = _task("c1", desc="perf work", assignee="a1")
    results = run_structural(parent, [child])
    names = [r.check_name for r in results]
    assert len(results) == 7
    for expected in (
        "CHECK-1:coverage", "CHECK-1b:non_redundancy", "CHECK-2:dag",
        "CHECK-3:deadlines", "CHECK-4:neglected",
        "CHECK-5:risk_nodes", "CHECK-6:delegation",
    ):
        assert expected in names
