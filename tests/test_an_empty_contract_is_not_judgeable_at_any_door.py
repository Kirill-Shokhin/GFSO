"""A node with no criteria cannot be judged — and that has to hold wherever a verdict is produced.

`record_verdict` has refused it by name since 2026-09-02, when a stranger closed a root called
"Everything is done" in four seconds over an empty conjunction. On 2026-09-03 another stranger, on
another door, walked around the same rule in one call: `validate_result` had no such check, so the
instrument signed `PASS` with `per_criterion: []` on a root delivered with the words "nothing to do
here", and every surface reported COMPLETE. Their own summary of it is the finding worth keeping:
*the engine articulates the exact reasoning that forbids it at one door and walks past it at another.*

So the rule moved to where every verdict lands — `Engine.record_exec_verdict` — and the doors keep
their own wording on top of it. A guard that is one door wide is not a guard.
"""
from __future__ import annotations

import pytest

from gfso import tools as T
from gfso.core.types import TaskId
from tests.support import UNMODELLED_FAULT, make_engine


def _delivered_with_no_criteria(e, tid="hollow"):
    T.create_task(e, tid, {"description": "no criteria at all",
                           "criteria": [],
                           "accepted_risks": [{"item": UNMODELLED_FAULT.item,
                                               "predictability": "EXTRAORDINARY"}]},
                  assignee="exec-1")
    e.wait_idle()
    T.signal(e, tid, "ACCEPT", "exec-1")
    T.signal(e, tid, "DELIVER", "exec-1", result="nothing to do here")
    e.wait_idle()
    assert e.get_state(TaskId(tid)).name == "VALIDATING"


def test_the_engine_refuses_to_store_a_verdict_about_nothing():
    """The chokepoint every door and the dispatcher's auto-validation go through."""
    e = make_engine()
    e.start()
    _delivered_with_no_criteria(e)

    with pytest.raises(ValueError) as caught:
        e.record_exec_verdict(TaskId("hollow"), "PASS", [], "instrument", per_criterion=[])

    assert "no criteria" in str(caught.value)
    e.stop()


def test_and_so_the_node_cannot_reach_DONE_on_that_verdict():
    """The consequence, which is the thing that actually mattered: no verdict, so no open seam."""
    e = make_engine()
    e.start()
    _delivered_with_no_criteria(e)

    out = T.signal(e, "hollow", "PASS", "exec-1")

    assert out["accepted"] is False, "a root with an empty contract reached DONE/PASS"
    assert e.get_state(TaskId("hollow")).name == "VALIDATING"
    e.stop()


def test_a_node_WITH_criteria_is_judged_exactly_as_before():
    """The negative control: this refusal must not reach a contract that exists."""
    e = make_engine()
    e.start()
    T.create_task(e, "real", {"description": "a leaf with a contract",
                              "criteria": [{"name": "c", "description": "C"}],
                              "accepted_risks": [{"item": UNMODELLED_FAULT.item,
                                                  "predictability": "EXTRAORDINARY"}]},
                  assignee="exec-1")
    e.wait_idle()
    T.signal(e, "real", "ACCEPT", "exec-1")
    T.signal(e, "real", "DELIVER", "exec-1", result="built it")

    rec = e.record_exec_verdict(TaskId("real"), "PASS", [], "instrument",
                                per_criterion=[{"criterion": "c", "verdict": "pass",
                                                "evidence": "ran the check, it printed OK",
                                                "behaviours": ["C holds"],
                                                "probe": [{"command": "check", "expect": "OK",
                                                           "behaviour": "C holds"}]}])

    assert rec["verdict"] == "PASS"
    assert T.signal(e, "real", "PASS", "exec-1")["accepted"] is True
    e.stop()
