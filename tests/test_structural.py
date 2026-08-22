"""Tests for handlers/structural.py — CHECK-1 through CHECK-6."""
from datetime import datetime, timedelta
from gfso.core.types import (
    Task, TaskId, AgentId, Spec, Criteria, CriterionMapping,
    AcceptedRiskItem, Predictability,
)
from gfso.core.handlers.structural import (
    check_coverage, check_dag, check_deadlines,
    check_accepted_risks, check_risk_nodes, check_delegation,
    check_non_redundancy,
    run_structural,
)


def _task(tid: str, desc: str = "", criteria=(), accepted_risks=(), assignee=None, deadline=None, mappings=(), risk_components=()) -> Task:
    return Task(
        id=TaskId(tid),
        spec=Spec(desc, tuple(Criteria(c, c) for c in criteria), tuple(accepted_risks), tuple(risk_components)),
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
    result = check_dag(children, edges)
    assert not result.passed
    # the cycle is NAMED — an anonymous "cycle detected" gives the repair no locus
    for n in ("a", "b", "c"):
        assert n in result.details

def test_dag_empty():
    assert check_dag([], []).passed

def test_dag_checks_D_not_only_dep():
    """§13.4's row is "the graph of D is a DAG" — which this check did not look at at all: it walked
    the Dep edges and reported them under CHECK-2, so §10's "a cycle → infinite recursion → an A1
    violation" was verified nowhere. What one split can decide: a node that is its own child, and a
    child repeated in the split."""
    parent = _task("p")
    assert not check_dag([_task("p"), _task("c")], [], parent).passed
    assert not check_dag([_task("c"), _task("c")], [], parent).passed
    assert check_dag([_task("c1"), _task("c2")], [], parent).passed


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


# === CHECK-4: ACCEPTED_RISKS (v3.7 §13.1: gates DECOMPOSED nodes only — per-decomposition) ===

def test_accepted_risks_present():
    t = _task("t", accepted_risks=[AcceptedRiskItem("api rate limit", Predictability.EXTRAORDINARY)])
    assert check_accepted_risks(t, [_task("c1")]).passed

def test_accepted_risks_empty_on_decomposed_fails():
    t = _task("t")
    assert not check_accepted_risks(t, [_task("c1")]).passed

def test_accepted_risks_leaf_skipped():
    """A leaf (D=∅) has no decomposition → ACCEPTED_RISKS vacuous, CHECK-4 does not gate it (§13.1)."""
    assert check_accepted_risks(_task("t"), []).skipped


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

def test_delegation_quantifies_over_leaves_only():
    """§13.4: "∀ leaf t: Del(t) ≠ ∅". A child that decomposes FURTHER is accountable through its own
    children (§10 Del is per node); demanding an executor for it reads Del as a label. Without the
    caller's leaf information every child is treated as a leaf — the conservative read."""
    children = [_task("leaf", assignee="a1"), _task("branch")]
    assert check_delegation(children, None, {"branch"}).passed
    assert not check_delegation(children, None, set()).passed

def test_delegation_covers_the_node_itself_when_it_is_a_leaf():
    """The literal case §13.4 names, and the one nobody ran: a leaf with no parent to check it."""
    assert not check_delegation([], _task("root")).passed
    assert check_delegation([], _task("root", assignee="a1")).passed


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


# === CHECK-4 record form (§13.1: an incomplete record is not an ACCEPTED_RISKS record) ===

def _task_neg(accepted_risks):
    return Task(id=TaskId("t"), spec=Spec("t", (), tuple(accepted_risks)))

_KID = [Task(id=TaskId("k"), spec=Spec("k", ()))]  # decomposed → CHECK-4 gates

def test_accepted_risks_record_unclassified_fails_on_decomposed():
    """The predictability verdict is mandatory per factor (§13.1) — it doubles as the risk-vs-scope
    discriminator: no materialization P → scope boundary (goal criteria/CHECK-1), not ACCEPTED_RISKS."""
    r = check_accepted_risks(_task_neg([AcceptedRiskItem("x")]), _KID)
    assert not r.passed and "predictability" in r.details

def test_accepted_risks_record_ordinary_contradiction_fails():
    """A self-declared ORDINARY factor in ACCEPTED_RISKS is an internal contradiction of the record (§13.2)."""
    r = check_accepted_risks(_task_neg([AcceptedRiskItem("drought", Predictability.ORDINARY)]), _KID)
    assert not r.passed and "ORDINARY" in r.details

def test_accepted_risks_record_statistical_needs_justification():
    bad = _task_neg([AcceptedRiskItem("rare outage", Predictability.STATISTICAL)])
    assert not check_accepted_risks(bad, _KID).passed
    ok = _task_neg([AcceptedRiskItem("rare outage", Predictability.STATISTICAL, "P<1%, out of budget")])
    assert check_accepted_risks(ok, _KID).passed

def test_accepted_risks_record_extraordinary_ok():
    t = _task_neg([AcceptedRiskItem("meteorite", Predictability.EXTRAORDINARY)])
    assert check_accepted_risks(t, _KID).passed


def test_accepted_risks_naming_own_criterion_is_a_contract_amendment_not_a_risk():
    """Measured live (BCB/93, 2026-07-17): the agent wrote ACCEPTED_RISKS = "test_values criterion cannot
    pass — canonical test has design flaw" (EXTRAORDINARY, well-formed by every other rule) while
    `test_values` stayed a criterion of the SAME node; the validator then excused the red criterion by
    it → false PASS. A criterion is the obligation (§2.2), not an acceptable risk factor (§5.1) — the
    canon path for a criterion believed defective is CHALLENGE or the issuer's revision."""
    t = _task("t", criteria=["test_values", "shape"],
              accepted_risks=[AcceptedRiskItem("test_values criterion cannot pass - test has a design flaw",
                                       Predictability.EXTRAORDINARY)])
    r = check_accepted_risks(t, _KID)
    assert not r.passed and "test_values" in r.details and "CHALLENGE" in r.details
    # the same excuse hidden in the justification is the same amendment
    t2 = _task("t", criteria=["test_values"],
               accepted_risks=[AcceptedRiskItem("flaky expectations", Predictability.EXTRAORDINARY,
                                        "no implementation can ever satisfy test_values")])
    assert not check_accepted_risks(t2, _KID).passed


def test_accepted_risks_about_a_real_external_factor_still_passes():
    """The guard is word-boundary exact on THIS node's criterion names — a genuine risk record that
    merely shares vocabulary with the domain is not touched (no ritual, no false gate)."""
    t = _task("t", criteria=["docs", "tests_green"],
              accepted_risks=[AcceptedRiskItem("the vendor's docs_portal may be down at release",
                                       Predictability.STATISTICAL, "P<5%, mirror available")])
    assert check_accepted_risks(t, _KID).passed


# === Full run ===

def test_run_structural_returns_all_checks():
    # The check set is the CANON's L0 list (§13.4): CHECK-1, 1b, 2–6 — no invented check names.
    parent = _task("p", criteria=["perf"], accepted_risks=["risks"], mappings=[
        CriterionMapping("perf", TaskId("c1")),
    ])
    child = _task("c1", desc="perf work", assignee="a1")
    results = run_structural(parent, [child])
    names = [r.check_name for r in results]
    assert len(results) == 7
    for expected in (
        "CHECK-1:coverage", "CHECK-1b:no_orphan", "CHECK-2:dag",
        "CHECK-3:deadlines", "CHECK-4:accepted_risks",
        "CHECK-5:risk_nodes", "CHECK-6:delegation",
    ):
        assert expected in names


# === CHECK-7/8: the numeric-bound tier must DEGRADE, never crash ===

def test_numeric_bound_ignores_non_numbers():
    r"""`[\d.]+` also matched a run of dots: a markdown criterion ("`> ...` renders as a
    blockquote") reached float('...') and threw, taking a whole auto_decompose down with a 422.
    A tier that cannot machine-check something reports it — it does not raise."""
    from gfso.core.handlers.constraint import _parse_numeric_bound
    assert _parse_numeric_bound("`> ...` renders as a blockquote") is None
    assert _parse_numeric_bound("a line starting with > ... is quoted") is None
    assert _parse_numeric_bound("response_time < 200ms") == ("response_time", "<", 200.0)
    assert _parse_numeric_bound("coverage >= 80.5%") == ("coverage", ">=", 80.5)


def test_check7_survives_markdown_criteria():
    """End to end at the check level: the parent's markdown criterion must come back skipped
    (beyond tier), not blow up the caller."""
    from gfso.core.handlers.constraint import check_sufficiency, check_consistency
    parent = _task("p", criteria=["`> ...` renders as a blockquote"], mappings=[
        CriterionMapping("`> ...` renders as a blockquote", TaskId("c1"))])
    child = _task("c1", criteria=["emits <blockquote> for a quoted line"])
    assert check_sufficiency(parent, [child]).passed
    assert check_consistency([child]).passed


def test_check3_catches_a_child_outliving_its_parent():
    """The VERTICAL deadline rule (§3.4 item 6), which had no pre-exec check until now (§26.5-bis).

    A child whose deadline is not before its parent's cannot compose into it in time: the plan
    promises a passage the clock denies, and nothing before execution said so. CHECK-3 now carries
    both rules — the horizontal Dep one it always had, and this one.
    """
    from datetime import datetime, timedelta
    now = datetime(2026, 1, 1)
    parent = _task("p", criteria=["c1"], deadline=now + timedelta(days=5))
    late = _task("late", criteria=["k"], deadline=now + timedelta(days=9))
    ok = _task("ok", criteria=["k"], deadline=now + timedelta(days=2))

    bad = check_deadlines(parent, [late], [])
    assert not bad.passed and "child late" in bad.details
    assert check_deadlines(parent, [ok], []).passed


def test_check3_stays_silent_when_no_deadlines_are_set():
    """A deadline is a design decision, not a mandatory field (§10) — absence is not a violation."""
    parent = _task("p", criteria=["c1"])
    assert check_deadlines(parent, [_task("k", criteria=["k1"])], []).passed


# === The gate IS the canon's Syntactic level (§13.4) ===

def test_the_execution_gate_is_exactly_the_canons_syntactic_level():
    """§13.4 lists seven checks at Level 0 and then rules: "a decomposition that fails the Syntactic
    level is not admitted to execution". So the gate is the level — not a selection from it.

    Four of the seven used to gate. CHECK-4/5/6 were called "completeness documentation" and only
    surfaced, which made an empty ACCEPTED_RISKS register admissible where §13.1 says a decomposition
    without one is incomplete by definition. This pins both directions: every canon row gates, and
    CHECK-1c — an engineering addition with no canon row — does not.
    """
    from gfso.engine.validation import _EXEC_GATING_CHECKS

    canon_level_0 = {"CHECK-1", "CHECK-1b", "CHECK-2", "CHECK-3", "CHECK-4", "CHECK-5", "CHECK-6"}
    gated = {p.rstrip(":") for p in _EXEC_GATING_CHECKS}
    assert gated == canon_level_0

    produced = {r.check_name.split(":")[0] for r in run_structural(_task_neg(()), [])}
    assert produced - {"CHECK-1c"} <= canon_level_0        # the battery adds only the anti-mock check
    assert "CHECK-1c" not in gated                          # …and it stays out of the gate


def test_the_agent_door_can_declare_a_scope_boundary():
    """`scope` must be readable on input, not only reported on output.

    A scope BOUNDARY (a capability the goal deliberately excludes) has no materialization
    probability, so CHECK-4 refuses it in the risk register by design (§13.1). With the Syntactic
    level gating execution, a door that could not set `scope` left the agent nowhere legal to put
    one: the register the gate demands would have had to hold what the register forbids.
    """
    from gfso.adapters.agents.human import HumanAgent
    from gfso.adapters.storage.memory import MemoryStorage
    from gfso.engine import Engine
    from gfso import tools as T

    e = Engine(MemoryStorage(), HumanAgent(), llm=None)
    e.start()
    out = T.create_task(e, "goal", {"description": "billing computation",
                                    "criteria": [{"name": "c", "description": "totals are right"}],
                                    "scope": ["payment gateway — a separate goal"]}, "alice")
    assert out["scope"] == ["payment gateway — a separate goal"]
    assert e.get_task(T.TaskId("goal")).spec.scope == ("payment gateway — a separate goal",)
    e.stop()
