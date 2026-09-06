"""A dependency edge is removed by the verb for removing edges, not by leaving it out of a spec.

A Dep seam is stored as a criterion (`dep__{producer}`, carrying `depends_on`), so a wholesale
replacement of a node's criteria takes the graph's EDGES with it. `edit_criteria` has carried those
across since 2026-08-20, and the argument is written out beside it: nobody editing what a node must
ACHIEVE is asking to sever what it WAITS FOR, and the loss is invisible until a consumer runs against
an input nothing connected it to (FM-5).

That rule sat on one door. `revise` — the verb whose whole contract IS wholesale replacement — went
straight past it, so the defect the comment describes happened through the widest door onto the same
edge. Two strangers hit it the same afternoon (2026-09-05), one through `revise` and one through a
path that reached it, and both reported the same second half: the graph then read CLEAN. `list_holes`
returned `[]` and CHECK-2 answered *"D acyclic; no dependency edges"* — a check passing because its
subject had been destroyed.

Removing an edge stays possible and stays explicit: `remove_dependency` names the producer it is
severing, and nothing else can. That half is not decoration — the first cut of the carry had no such
exemption, and since `remove_dependency` works by RE-AUTHORING the consumer without the criterion,
the carry put the edge straight back and the verb for deleting edges stopped deleting them.
"""
from __future__ import annotations

import pytest

from gfso import tools as T
from gfso.core.types import TaskId
from tests.support import UNMODELLED_FAULT, make_engine

_RISKS = [{"item": UNMODELLED_FAULT.item, "predictability": "EXTRAORDINARY"}]


@pytest.fixture(autouse=True)
def _no_plan_gate(monkeypatch):
    monkeypatch.setenv("GFSO_L2_GATE", "0")


def _a_producer_and_a_consumer(e):
    T.create_task(e, "root", {"description": "parent",
                              "criteria": [{"name": "g", "description": "G"},
                                           {"name": "p", "description": "P"}],
                              "accepted_risks": _RISKS}, assignee="agent")
    T.create_task(e, "root.prod", {"description": "producer",
                                   "criteria": [{"name": "pp", "description": "PP"}]},
                  assignee="agent", parent_id="root")
    T.create_task(e, "root.cons", {"description": "consumer",
                                   "criteria": [{"name": "c", "description": "C"}]},
                  assignee="agent", parent_id="root")
    T.map_criterion(e, "root", "root.prod", "p")
    T.map_criterion(e, "root", "root.cons", "g")
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
                              "criteria": [{"name": "c", "description": "C, tightened"}],
                              "accepted_risks": _RISKS}, "agent")
    e.wait_idle()

    assert _edges(e) == [("root.prod", "root.cons")], "the edge was deleted by omission"
    assert "dep__root.prod" in [c.name for c in e.get_task(TaskId("root.cons")).spec.criteria]
    e.stop()


def test_edit_criteria_still_carries_it_too():
    """The door that already had the rule keeps it — the fix moved the rule, it did not move the door."""
    e = make_engine()
    e.start()
    _a_producer_and_a_consumer(e)

    T.edit_criteria(e, "root.cons", [{"name": "c", "description": "C, tightened"}], "agent")
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
