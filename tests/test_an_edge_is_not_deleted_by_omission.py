"""A dependency edge is removed by the verb for removing edges, not by leaving it out of a spec.

While a Dep seam was stored as a criterion (`dep__{producer}`, carrying `depends_on`), a wholesale replacement of a
node's criteria took the graph's EDGES with it — and the graph then read CLEAN: `list_holes` returned `[]` and
CHECK-2 answered *"D acyclic; no dependency edges"*, a check passing because its subject had been destroyed (two
strangers, 2026-09-05). The edge is a record of its own now (§2.7), so no revision of the contract reaches it, and
`remove_dependency` stays the one verb that cuts one.
"""
from __future__ import annotations

import pytest

from gfso import tools as T
from gfso.core.types import TaskId
from tests.support import criterion, make_engine, REGISTER

_RISKS = REGISTER


@pytest.fixture(autouse=True)
def _no_plan_gate(monkeypatch):
    monkeypatch.setenv("GFSO_L2_GATE", "0")


def _a_producer_and_a_consumer(e):
    T.create_task(e, "root", {"description": "parent",
                              "criteria": [criterion("g", "G"),
                                           criterion("p", "P")],
                              "accepted_risks": _RISKS}, assignee="agent")
    T.decompose(e, "root", [{"task_id": "root.prod", "spec": {"description": "producer",
                                   "criteria": [criterion("pp", "PP")]}, "assignee": "agent", "covers": ["p"]},
        {"task_id": "root.cons", "spec": {"description": "consumer",
                                   "criteria": [criterion("c", "C")]}, "assignee": "agent", "covers": ["g"]}], accepted_risks=REGISTER)
    T.add_dependency(e, "root.prod", "root.cons", glue="cons reads prod's output")
    e.wait_idle()
    assert [(d["producer"], d["consumer"]) for d in T.get_dependencies(e)] == [("root.prod", "root.cons")]


def _edges(e):
    return [(d["producer"], d["consumer"]) for d in T.get_dependencies(e)]


def test_revise_does_not_sever_what_the_node_waits_for():
    e = make_engine()
    e.start()
    _a_producer_and_a_consumer(e)

    T.revise(e, "root.cons", {"description": "consumer, revised",
                              "criteria": [criterion("c", "C, tightened")],
                              "accepted_risks": _RISKS}, "agent")
    e.wait_idle()

    assert _edges(e) == [("root.prod", "root.cons")], "the edge was deleted by omission"
    assert [c.name for c in e.graph.get_task(TaskId("root.cons")).spec.criteria] == ["c"], "the edge is no criterion"
    e.stop()


def test_edit_criteria_still_carries_it_too():
    """The door that already had the rule keeps it — the fix moved the rule, it did not move the door."""
    e = make_engine()
    e.start()
    _a_producer_and_a_consumer(e)

    T.edit_criteria(e, "root.cons", [criterion("c", "C, tightened")], "agent")
    e.wait_idle()

    assert _edges(e) == [("root.prod", "root.cons")]
    e.stop()


def test_the_verb_for_removing_an_edge_still_removes_it():
    """The explicit path must stay open, or the carry is a cage. It was one, for about ten minutes."""
    e = make_engine()
    e.start()
    _a_producer_and_a_consumer(e)

    T.remove_dependency(e, "root.prod", "root.cons")
    e.wait_idle()

    assert _edges(e) == [], "the verb for removing an edge no longer removes it"
    e.stop()
