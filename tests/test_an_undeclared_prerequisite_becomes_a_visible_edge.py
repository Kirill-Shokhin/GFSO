"""§11.4, second half: a prerequisite nobody declared becomes a DISCOVERED edge, and it is counted.

The unit tests cover the multi-blocker mechanics. What had never been read end to end is the trio a
person actually sees: the edge appears and says it was discovered at runtime, `q_Dep` leaves ⊥ and
reports the discovery, and the frontier offers the producer's work and the consumer's RESOLVE rather
than rewriting anything. `q_Dep = 1.0` on every run so far said only that the path had never fired,
which is not the same as it working.

The control is the same graph one signal earlier: before the BLOCK there is no edge at all and
`q_Dep` is ⊥ — nothing declared, nothing discovered, nothing to score.
"""
from __future__ import annotations

from gfso import tools as T
from gfso.core.types import TaskId
from tests.support import UNMODELLED_FAULT, make_engine


def _two_leaves_and_no_declared_dependency(e):
    T.create_task(e, "root", {"description": "two leaves",
                              "criteria": [{"name": "g", "description": "G holds"},
                                           {"name": "p", "description": "P holds"}],
                              "accepted_risks": [{"item": UNMODELLED_FAULT.item,
                                                  "predictability": "EXTRAORDINARY"}]},
                  assignee="agent")
    T.create_task(e, "root.cons", {"description": "consumer",
                                   "criteria": [{"name": "c", "description": "C"}]},
                  assignee="cons-x", parent_id="root")
    T.create_task(e, "root.prod", {"description": "producer",
                                   "criteria": [{"name": "pp", "description": "PP"}]},
                  assignee="prod-x", parent_id="root")
    T.map_criterion(e, "root", "root.cons", "g")
    T.map_criterion(e, "root", "root.prod", "p")
    e.wait_idle()


def test_the_block_records_the_edge_the_plan_missed(monkeypatch):
    monkeypatch.setenv("GFSO_L2_GATE", "0")   # the plan gate is a different question from this one
    e = make_engine()
    e.start()
    _two_leaves_and_no_declared_dependency(e)

    assert T.get_dependencies(e) == [], "the control failed: something was declared up front"
    assert T.metrics(e).get("q_Dep") is None, "⊥ is the honest score with nothing to score"

    T.signal(e, "root.cons", "ACCEPT", "cons-x")
    out = T.signal(e, "root.cons", "BLOCK", "cons-x",
                   reason="C cannot be produced without PP, which nobody declared",
                   blocker_task_ids=["root.prod"])
    e.wait_idle()

    assert out["accepted"] is True and out["state"] == "BLOCKED"
    edges = T.get_dependencies(e)
    assert len(edges) == 1, edges
    edge = edges[0]
    assert (edge["producer"], edge["consumer"]) == ("root.prod", "root.cons")
    assert edge["discovered"] is True and edge["provisional"] is True
    assert "nobody declared" in edge["glue"], "the reason the executor gave is not on the edge"
    e.stop()


def test_and_the_metric_stops_reading_perfect(monkeypatch):
    """`q_Dep` is the count of declared-up-front against discovered-at-runtime — it has to move."""
    monkeypatch.setenv("GFSO_L2_GATE", "0")
    e = make_engine()
    e.start()
    _two_leaves_and_no_declared_dependency(e)
    T.signal(e, "root.cons", "ACCEPT", "cons-x")
    T.signal(e, "root.cons", "BLOCK", "cons-x", reason="needs PP",
             blocker_task_ids=["root.prod"])
    e.wait_idle()

    m = T.metrics(e)

    assert m["q_Dep"] == 0.0, m["q_Dep"]
    assert "discovered" in (m.get("means") or {}).get("q_Dep", ""), "the number arrives without its meaning"
    e.stop()


def test_the_frontier_offers_the_producer_and_the_resolution_not_a_rewrite(monkeypatch):
    """Nothing is silently patched: the work that unblocks it is offered, and so is the RESOLVE."""
    monkeypatch.setenv("GFSO_L2_GATE", "0")
    e = make_engine()
    e.start()
    _two_leaves_and_no_declared_dependency(e)
    T.signal(e, "root.cons", "ACCEPT", "cons-x")
    T.signal(e, "root.cons", "BLOCK", "cons-x", reason="needs PP",
             blocker_task_ids=["root.prod"])
    e.wait_idle()

    offered = {(s["task_id"], str(s["action"])) for s in (e.next_steps().get("steps") or ())}

    assert ("root.prod", "accept") in offered, offered
    assert ("root.cons", "resolve") in offered, offered
    assert e.get_state(TaskId("root.cons")).name == "BLOCKED"
    e.stop()
