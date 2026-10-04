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
cannot be written past it". `engine/loop.py` is that second door: the §10.3 self-check calls
`store_verdict` directly. And `check_coverage` asked only whether the covering child EXISTS, never
whether it decides anything, so a child with no criteria satisfied CHECK-1 for its parent and, being
a leaf, passed its own CHECK-1 as "no criteria defined".

By A1 a task is a goal plus a decidable predicate. A child carrying none secures nothing for anybody,
and the parent's criterion it was mapped to is not covered — it is unattended under a name that says
it is covered.

Canon v4.1 (§11.5, §2.2): such a split is refused at its admission and issues no child, and no revision empties an
admitted contract; the criteria-less child the rules below still meet is one stored before the admission held it.
"""
from __future__ import annotations

import pytest

from gfso import tools as T
from gfso.core.types import TaskId, passed
from tests.support import criterion, emptied, make_engine, REGISTER


@pytest.fixture(autouse=True)
def _no_plan_gate(monkeypatch):
    """The L2 gate is a different question; this is about Level 0 and the verdict write."""
    monkeypatch.setenv("GFSO_L2_GATE", "0")


def _kid(criteria):
    return [{"task_id": "root.kid", "spec": {"description": "a child", "criteria": criteria},
             "assignee": "agent", "covers": ["g"]}]                # same Del as its parent => INTERNAL


def _parent_and_an_empty_child(e):
    T.create_task(e, "root", {"description": "the parent", "criteria": [criterion("g", "G holds")]},
                  assignee="agent")
    T.decompose(e, "root", _kid([criterion("k", "K holds")]), accepted_risks=REGISTER)
    e.wait_idle()
    emptied(e, "root.kid")      # …and its contract emptied after admission, as stored before §2.2 was held there


def test_coverage_refuses_a_child_that_carries_no_criteria():
    e = make_engine()
    e.start()
    T.create_task(e, "root", {"description": "the parent", "criteria": [criterion("g", "G holds")]},
                  assignee="agent")
    with pytest.raises(ValueError, match="NONEMPTY"):
        T.decompose(e, "root", _kid([]), accepted_risks=REGISTER)
    assert e.graph.get_task(TaskId("root.kid")) is None, "the admission refused the split, yet issued its child"
    e.stop()
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

    assert passed(e.graph.get_task(TaskId("root.kid"))) is False
    e.stop()


def test_a_child_WITH_criteria_covers_and_self_verifies_exactly_as_before():
    """The negative control: §10.3 self-verification is legitimate and must be untouched."""
    e = make_engine()
    e.start()
    T.create_task(e, "root", {"description": "the parent",
                              "criteria": [criterion("g", "G holds")],
                              "accepted_risks": REGISTER},
                  assignee="agent")
    T.decompose(e, "root", [{"task_id": "root.kid", "spec": {"description": "a child that decides something",
                                  "criteria": [criterion("k", "K holds")]}, "assignee": "agent", "covers": ["g"]}], accepted_risks=REGISTER)
    e.wait_idle()
    T.signal(e, "root.kid", "ACCEPT", "agent")
    T.signal(e, "root.kid", "DELIVER", "agent", result="built it", self_validation="PASS")
    e.wait_idle()

    assert T.list_holes(e) == {"holes": [], "count": 0}
    assert T.get_verdict(e, "root.kid")["verdict"] == "PASS"
    assert T.signal(e, "root.kid", "PASS", "agent")["accepted"] is True
    assert passed(e.graph.get_task(TaskId("root.kid"))) is True
    e.stop()
