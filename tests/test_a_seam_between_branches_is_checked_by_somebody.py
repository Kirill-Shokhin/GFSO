"""CHECK-2 and CHECK-3 quantify over Dep, not over siblings — and `vacuous` describes what was seen.

The canon states both rows over the whole relation (§13.4: `CHECK-2 (acyclicity): the graph of D is
a DAG`, `CHECK-3 (deadlines): ∀ (t_a, t_b) ∈ Dep: deadline(t_a) < deadline(t_b)`). The implementation
quantified over a strict subset:

* `check_dag` seeded its walk from the node's CHILDREN and refused to step onto any endpoint outside
  that set, so a seam between two BRANCHES terminated the walk in silence;
* `check_deadlines` built its deadline map from the children alone, so a pair with an endpoint under
  a different parent had no entry and was `continue`d — skipped, not reported;
* and the two doors that run these checks fed them DIFFERENT populations — the cache every edge in
  the graph, the execution gate only sibling-internal ones — so one node carried opposite `vacuous`
  claims in the same second, and neither described the pairs actually compared.

The measured consequence: a cross-branch Dep whose producer's deadline is LATER than its consumer's
was accepted through the ordinary door and read clean on `list_holes`, on `get_checks` at every node,
and at the execution gate, while `check_dag` over the whole graph named the cycle those surfaces
called absent. That is FM-5 admitted by the gate whose row maps to FM-5.

Controls: filter `dep_scope`'s edges to the direct children again, or read `vacuous` off the supplied
list rather than the examined pairs, and the cases below go red.
"""
import pytest

from gfso import tools as T
from gfso.core.graph.model import dep_scope
from gfso.core.handlers.structural import check_deadlines
from gfso.engine.validation import _l0_holes
from gfso.core.types import AgentId, Criteria, Spec, Task, TaskId
from tests.support import make_engine

RISKS = [{"item": "an unmodelled environment fault", "predictability": "EXTRAORDINARY"}]


def _crit(*names):
    return [{"name": n, "description": n + " d"} for n in names]


@pytest.fixture
def two_branches():
    """root -> {P -> a1, Q -> b1}: a seam between a1 and b1 crosses two parents."""
    e = make_engine()
    e.start()
    T.create_task(e, "root", {"description": "root", "criteria": _crit("gP", "gQ"),
                              "accepted_risks": RISKS},
                  assignee="agent", deadline="2030-01-20T00:00:00")
    for branch, covered in (("P", "gP"), ("Q", "gQ")):
        T.create_task(e, branch, {"description": branch, "criteria": _crit(branch + "1"),
                                  "accepted_risks": RISKS},
                      assignee="agent", parent_id="root", deadline="2030-01-10T00:00:00")
        T.map_criterion(e, "root", branch, covered)
    T.create_task(e, "a1", {"description": "a1", "criteria": _crit("ca1")},
                  assignee="agent", parent_id="P", deadline="2030-01-09T00:00:00")
    T.create_task(e, "b1", {"description": "b1", "criteria": _crit("cb1")},
                  assignee="agent", parent_id="Q", deadline="2030-01-02T00:00:00")
    T.map_criterion(e, "P", "a1", "P1")
    T.map_criterion(e, "Q", "b1", "Q1")
    e.wait_idle()
    try:
        yield e
    finally:
        e.stop()


def test_the_seam_is_inside_the_common_ancestors_population(two_branches):
    edges, deadlines = dep_scope(two_branches._graph, TaskId("root"))
    assert [(str(a.from_id), str(a.to_id)) for a in edges] == []
    T.add_dependency(two_branches, "a1", "b1", glue="b1 links the object a1 emits")
    two_branches.wait_idle()

    edges, deadlines = dep_scope(two_branches._graph, TaskId("root"))
    assert [(str(a.from_id), str(a.to_id)) for a in edges] == [("a1", "b1")]
    assert set(deadlines) >= {"a1", "b1"}, "the endpoints' deadlines come with the population"
    # …and the branches do not claim it: it is not inside either of their subtrees.
    assert dep_scope(two_branches._graph, TaskId("P"))[0] == []


def test_a_cross_branch_deadline_violation_is_named_at_every_door(two_branches):
    T.add_dependency(two_branches, "a1", "b1", glue="b1 links the object a1 emits")
    two_branches.wait_idle()

    holes = T.list_holes(two_branches)
    assert holes["count"] >= 1, holes
    assert any("CHECK-3" in h["check"] and h["task_id"] == "root" for h in holes["holes"]), holes

    gate = _l0_holes(two_branches._graph, two_branches._graph.get_task(TaskId("root")))
    assert any(c.check_name.startswith("CHECK-3") for c in gate), \
        "the execution gate admitted a plan whose seam runs backwards in time (FM-5)"

    cached = [c for c in T.get_checks(two_branches, "root") if c["check"].startswith("CHECK-3")]
    assert cached and cached[0]["passed"] is False, cached


def test_a_green_over_nothing_examined_says_vacuous(two_branches):
    """`passed=True, vacuous=False` is a positive claim that the dependencies were ordered."""
    T.add_dependency(two_branches, "a1", "b1", glue="b1 links the object a1 emits")
    two_branches.wait_idle()
    for branch in ("P", "Q"):
        rows = [c for c in T.get_checks(two_branches, branch) if c["check"].startswith("CHECK-3")]
        assert rows and rows[0]["passed"] and rows[0]["vacuous"], \
            f"{branch} compared no pair, so its green is vacuous: {rows}"


def test_vacuous_is_read_off_the_pairs_compared_not_the_list_supplied():
    """A pair whose ends carry no deadline is not a pair that was checked."""
    parent = Task(id=TaskId("p"), spec=Spec("p", (Criteria("c", "c"),), (), ()),
                  assignee=AgentId("a"))
    kids = [Task(id=TaskId(k), spec=Spec(k, (Criteria("x", "x"),), (), ()), assignee=AgentId("a"))
            for k in ("k1", "k2")]
    out = check_deadlines(parent, kids, [("k1", "k2")], {"k1": None, "k2": None})
    assert out.passed and out.vacuous, out


def test_a_cycle_closed_across_two_branches_is_named(two_branches):
    """The CYCLE half, through the canonical runtime path: BLOCK carries a discovered Dep.

    A declared cross-branch cycle is refused at `add_dependency` (it checks the whole graph), so the
    reachable shape is the one a run actually produces: a1 declares that b1 consumes its output, then
    contact refutes it and a1 BLOCKs naming b1 as ITS prerequisite. The reverse edge is stored on
    purpose — "the cycle IS the FM-4 finding to surface, not hide" — and it was surfaced nowhere.
    """
    T.add_dependency(two_branches, "a1", "b1", glue="b1 links the object a1 emits")
    two_branches.wait_idle()
    T.signal(two_branches, "a1", "ACCEPT", source="agent")
    T.signal(two_branches, "a1", "BLOCK", source="agent",
             reason="a1 cannot start without b1's schema", blocker_task_ids=["b1"])
    two_branches.wait_idle()

    edges = {(d["producer"], d["consumer"]) for d in T.get_dependencies(two_branches)}
    assert edges == {("a1", "b1"), ("b1", "a1")}, edges

    holes = T.list_holes(two_branches)
    assert any(h["check"].startswith("CHECK-2") and h["task_id"] == "root"
               for h in holes["holes"]), holes
    gate = _l0_holes(two_branches._graph, two_branches._graph.get_task(TaskId("root")))
    assert any(c.check_name.startswith("CHECK-2") for c in gate), \
        "the execution gate admitted a plan with a live Dep cycle (FM-4)"


def test_an_edge_naming_a_node_that_does_not_exist_leaves_the_green_vacuous(two_branches):
    """A dangling endpoint contributes no comparable pair, so CHECK-2's green is a vacuous one.

    `add_dependency` accepts a producer id no node has (the consumer is checked, the producer is
    not), and the edge then reaches the checks. It cannot form a cycle — nothing is on its other
    end — so CHECK-2 passes; what it must not do is pass NON-vacuously, because
    `api/models.py` renders that as "met" rather than "met_vacuously" and the panel then shows a
    positive claim about dependencies whose only pair names a node that is not in the graph.

    CONTROL: read CHECK-2's vacuity off `dep_edges` again instead of the population, and this
    goes red.
    """
    T.add_dependency(two_branches, "ghost_producer", "a1", glue="a1 reads what nobody writes")
    two_branches.wait_idle()

    rows = [c for c in T.get_checks(two_branches, "root") if c["check"].startswith("CHECK-2")]
    assert rows, "CHECK-2 is not reported at all"
    assert rows[0]["passed"] is True, rows
    assert rows[0]["vacuous"] is True, \
        f"a green over an unexamined population claimed to have examined one: {rows[0]}"
