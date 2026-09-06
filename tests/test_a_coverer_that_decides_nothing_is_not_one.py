"""A conjunct that forbids nothing may not stand inside Thm 1's AND.

An outside audit of the implementation against the canon INFERRED this path and said so plainly
rather than claiming it; a probe then walked it end to end (2026-09-05):

    map_criterion(root, root.kid, "g")   ->  "root.g is covered by root.kid"
    list_holes                            ->  []                      (the plan reads L0-clean)
    DELIVER(self_validation=PASS)         ->  accepted, VALIDATING
    get_verdict(root.kid)                 ->  PASS                    (on a node with NO criteria)
    signal PASS by its own executor       ->  accepted, DONE
    passed(root.kid)                      ->  True                    (it satisfies its parent's AND)

Two rules were one door wide. `record_exec_verdict` refuses a verdict about a criteria-less node by
name — and its own comment claims "the rule now lives where every verdict lands, so a second door
cannot be written past it". `engine/loop.py` is that second door: the §14.5 D6 self-check calls
`store_verdict` directly. And `check_coverage` asked only whether the covering child EXISTS, never
whether it decides anything, so a child with no criteria satisfied CHECK-1 for its parent and, being
a leaf, passed its own CHECK-1 as "no criteria defined".

By A1 a task is a goal plus a decidable predicate. A child carrying none secures nothing for anybody,
and the parent's criterion it was mapped to is not covered — it is unattended under a name that says
it is covered.
"""
from __future__ import annotations

import pytest

from gfso import tools as T
from gfso.core.types import TaskId, passed
from tests.support import UNMODELLED_FAULT, make_engine


@pytest.fixture(autouse=True)
def _no_plan_gate(monkeypatch):
    """The L2 gate is a different question; this is about Level 0 and the verdict write."""
    monkeypatch.setenv("GFSO_L2_GATE", "0")


def _parent_and_an_empty_child(e):
    T.create_task(e, "root", {"description": "the parent",
                              "criteria": [{"name": "g", "description": "G holds"}],
                              "accepted_risks": [{"item": UNMODELLED_FAULT.item,
                                                  "predictability": "EXTRAORDINARY"}]},
                  assignee="agent")
    T.create_task(e, "root.kid", {"description": "a child with no criteria", "criteria": []},
                  assignee="agent", parent_id="root")      # same Del as its parent => INTERNAL
    T.map_criterion(e, "root", "root.kid", "g")
    e.wait_idle()


def test_coverage_refuses_a_child_that_carries_no_criteria():
    e = make_engine()
    e.start()
    _parent_and_an_empty_child(e)

    holes = {h["check"]: h for h in T.list_holes(e)["holes"]}

    assert "CHECK-1:coverage" in holes, "the plan reads clean while one conjunct forbids nothing"
    assert "decides nothing" in holes["CHECK-1:coverage"]["details"], holes
    e.stop()


def test_the_self_check_writer_does_not_record_a_verdict_about_nothing():
    """The second door onto the verdict record — the one the first guard's comment promised about."""
    e = make_engine()
    e.start()
    _parent_and_an_empty_child(e)
    T.signal(e, "root.kid", "ACCEPT", "agent")
    T.signal(e, "root.kid", "DELIVER", "agent", result="nothing to do here", self_validation="PASS")
    e.wait_idle()

    assert T.get_verdict(e, "root.kid").get("verdict") is None, (
        "a PASS was stored about a node whose criteria set is empty")
    e.stop()


def test_and_such_a_child_cannot_satisfy_its_parents_AND():
    e = make_engine()
    e.start()
    _parent_and_an_empty_child(e)
    T.signal(e, "root.kid", "ACCEPT", "agent")
    T.signal(e, "root.kid", "DELIVER", "agent", result="nothing to do here", self_validation="PASS")
    T.signal(e, "root.kid", "PASS", "agent")
    e.wait_idle()

    assert passed(e.get_task(TaskId("root.kid"))) is False
    e.stop()


def test_a_child_WITH_criteria_covers_and_self_verifies_exactly_as_before():
    """The negative control: §14.5 D6 self-verification is legitimate and must be untouched."""
    e = make_engine()
    e.start()
    T.create_task(e, "root", {"description": "the parent",
                              "criteria": [{"name": "g", "description": "G holds"}],
                              "accepted_risks": [{"item": UNMODELLED_FAULT.item,
                                                  "predictability": "EXTRAORDINARY"}]},
                  assignee="agent")
    T.create_task(e, "root.kid", {"description": "a child that decides something",
                                  "criteria": [{"name": "k", "description": "K holds"}]},
                  assignee="agent", parent_id="root")
    T.map_criterion(e, "root", "root.kid", "g")
    e.wait_idle()
    T.signal(e, "root.kid", "ACCEPT", "agent")
    T.signal(e, "root.kid", "DELIVER", "agent", result="built it", self_validation="PASS")
    e.wait_idle()

    assert T.list_holes(e) == {"holes": [], "count": 0}
    assert T.get_verdict(e, "root.kid")["verdict"] == "PASS"
    assert T.signal(e, "root.kid", "PASS", "agent")["accepted"] is True
    assert passed(e.get_task(TaskId("root.kid"))) is True
    e.stop()
