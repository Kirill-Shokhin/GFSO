"""Two surfaces of one database may not disagree about one node in silence.

On a decomposed node the plan gate holds the CHILDREN until every Level-2 finding is dispositioned,
so a parent cannot pass over an open review. A leaf root has no children to hold: the review is
advisory, nothing consults it, and `next_steps` answers COMPLETE while `get_review` on the same node
answers `execution_admitted: false`.

Two doors reached it independently on the same day (wave 25, 2026-09-05). The MCP tester closed a
goal reading "Ship the billing rewrite — rewrite the entire billing subsystem, migrate all customers,
and prove no revenue is lost" twice with no billing system in existence: once on "`pytest -q` exits 0
with at least 400 passed", satisfied by four hundred generated `def test_case_N(): assert True`, and
once on "Trivially true: the string 'ok' equals 'ok'". The instrument ran honestly both times — every
command was real and every report was true. The break is between the CRITERION and the GOAL, and the
product ships a checker that names it: *"the criterion sets no requirement that the passing tests
exercise billing or migration logic at all."* Their sentence for it is the one worth keeping: **the
one that says done is the one that never asks.**

This does not withhold `complete`. The checker is an a-priori approximation (§13.5) and the real
Level-2 verdict belongs to contact — a leaf whose review is merely unanswered is not thereby unfinished.
What it stops is the silence.
"""
from __future__ import annotations

import json

from gfso import tools as T
from gfso.core.types import TaskId
from tests.support import UNMODELLED_FAULT, make_engine


def _a_leaf_that_passed_with_its_review_unanswered(e):
    T.create_task(e, "leaf", {"description": "Ship the billing rewrite",
                              "criteria": [{"name": "suite_green",
                                            "description": "pytest -q exits 0 with >= 400 passed"}],
                              "accepted_risks": [{"item": UNMODELLED_FAULT.item,
                                                  "predictability": "EXTRAORDINARY"}]},
                  assignee="exec-1")
    e.wait_idle()
    # A review that RAN and named a gap — the shape `review_decomposition` stores for a leaf.
    e._graph._storage.store_critique(TaskId("leaf"), json.dumps({
        "gate_passed": True, "semantic_covered": False, "criteria_verdicts": [],
        "undecided_obligations": [{"obligation": "the tests must exercise billing",
                                   "admits": "400 `assert True` tests satisfy the criterion"}],
        "conflicts": [], "plan_generation": [0, ["suite_green"], []]}))
    t = e.get_task(TaskId("leaf"))
    t.verified = True
    e._graph.save_task(t)
    T.signal(e, "leaf", "ACCEPT", "exec-1")
    T.signal(e, "leaf", "DELIVER", "exec-1", result="400 tests, all passing")
    T.record_verdict(e, "leaf", "PASS", reviewer="judge",
                     observed={"suite_green": "ran `pytest -q`: 400 passed, exit 0"})
    T.signal(e, "leaf", "PASS", "exec-1")
    e.wait_idle()
    assert e.get_state(TaskId("leaf")).name == "DONE"
    assert T.get_review(e, "leaf")["execution_admitted"] is False, (
        "the probe never produced the disagreement it is about")


def test_completion_names_the_review_it_passed_over():
    e = make_engine()
    e.start()
    _a_leaf_that_passed_with_its_review_unanswered(e)

    out = e.next_steps()

    assert out["complete"] is True, "an advisory review must not make a leaf unfinishable"
    assert out["closed_over_an_open_plan_review"] == ["leaf"], out
    assert "get_review" in out["closed_over_an_open_plan_review_note"]
    e.stop()


def test_a_leaf_whose_review_was_answered_carries_nothing():
    """The negative control: this must not fire on a plan whose findings were dispositioned."""
    e = make_engine()
    e.start()
    T.create_task(e, "ok", {"description": "a leaf",
                            "criteria": [{"name": "c", "description": "C"}],
                            "accepted_risks": [{"item": UNMODELLED_FAULT.item,
                                                "predictability": "EXTRAORDINARY"}]},
                  assignee="exec-1")
    e.wait_idle()
    T.signal(e, "ok", "ACCEPT", "exec-1")
    T.signal(e, "ok", "DELIVER", "exec-1", result="built it")
    T.record_verdict(e, "ok", "PASS", reviewer="judge",
                     observed={"c": "ran the check, it printed OK"})
    T.signal(e, "ok", "PASS", "exec-1")
    e.wait_idle()

    out = e.next_steps()

    assert out["complete"] is True
    assert "closed_over_an_open_plan_review" not in out, out
    e.stop()
