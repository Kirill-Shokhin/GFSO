"""NodeProjection: typed DATA layer + pure render at the markdown boundary."""
from gfso.core.types import (
    Task, TaskId, AgentId, Spec, Criteria, CriterionMapping, DepEdge,
    AcceptedRiskItem, Predictability, CheckResult,
)
from gfso.core.graph.projection import (
    build, render, render_node_projection,
    NodeProjection, CoverageMarker, GlueMarker,
)


def _node():
    parent = Task(
        id=TaskId("p"),
        spec=Spec("ship", (Criteria("tested", "all pass"), Criteria("fast", "p99<1s")),
                  (AcceptedRiskItem("legacy", Predictability.STATISTICAL, "rare", "if IE returns"),)),
        assignee=AgentId("pm"),
        criterion_mappings=(CriterionMapping("tested", TaskId("c1")),),  # 'fast' unmapped
    )
    children = [
        Task(id=TaskId("c1"), spec=Spec("write tests", (Criteria("cov", ">=80%"),),
                                        (AcceptedRiskItem("flaky"),)), assignee=AgentId("qa")),
        Task(id=TaskId("c2"), spec=Spec("bench", ()), assignee=AgentId("perf")),
    ]
    deps = [DepEdge(TaskId("c2"), TaskId("c1"), False, "")]  # seam, no glue
    checks = [CheckResult("CHECK-1:tested", True), CheckResult("CHECK-1c:anti_mock", False, "no glue")]
    return parent, children, deps, checks


def test_build_captures_typed_markers():
    p = build(*_node())
    assert isinstance(p, NodeProjection) and not p.is_leaf
    cov = {c.criterion_name: c.owners for c in p.coverage}
    assert cov["tested"] == ("c1",)
    assert cov["fast"] is CoverageMarker.UNMAPPED          # typed, not a bare string
    assert p.seams[0].glue is GlueMarker.NONE_DECLARED     # typed, not a bare string


def test_render_equals_wrapper_and_keeps_text():
    parent, children, deps, checks = _node()
    md = render(build(parent, children, deps, checks))
    assert md == render_node_projection(parent, children, deps, checks)
    # sentinel constants surface in the rendered markdown
    assert "⚠ UNMAPPED" in md and "⚠ NONE DECLARED" in md
    assert "invalidation: if IE returns" in md
    assert "CHECK-1c:anti_mock: FAIL — no glue" in md


def test_leaf_short_circuit():
    parent = Task(id=TaskId("leaf"), spec=Spec("do it", ()), assignee=AgentId("a"))
    md = render(build(parent, [], [], []))
    assert "(leaf node — no decomposition to review)" in md
    assert "Criterion coverage" not in md
