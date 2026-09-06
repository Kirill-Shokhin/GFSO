"""A node whose instrument keeps coming back with ⊥ must say so where the work is driven.

All three doors of wave 23 measured the same symptom and none of them recognised it as one defect:
a node sitting in VALIDATING for twelve minutes, for forty-five minutes, or "forever", with
`next_steps` cheerfully naming `validate` the whole time. The MCP tester even filed the underlying
refusal under things the product got RIGHT — the instrument refused a vacuous pass twice and gave up,
which is fail-closed and correct — without connecting it to the node that then never moved.

The engine had the fact the whole time. `record_rejected_report` stores every refused report on the
node with a count, and `validate_result` tells ITS caller exactly what a second ⊥ means. But the
caller of a hand-driven validation is not the person who comes back to the graph an hour later, and
the step they read said "VALIDATE this" as though nothing had been tried. The dispatcher's own path
has said it since August (`_validation_parked`); the hand-driven one had the fact and no reader.

The count is scoped to the delivery it is about — a lifetime total would tell a driver "two reports
could not decide" about a delivery nobody had attempted yet.
"""
from __future__ import annotations

from gfso import tools as T
from gfso.core.types import TaskId
from tests.support import UNMODELLED_FAULT, make_engine

_BOTTOM = "not a verdict on leaf (⊥, not pass — §10): the report names behaviours it never observed"


def _delivered(e, tid="leaf"):
    T.create_task(e, tid, {"description": "a leaf",
                           "criteria": [{"name": "c", "description": "C"}],
                           "accepted_risks": [{"item": UNMODELLED_FAULT.item,
                                               "predictability": "EXTRAORDINARY"}]},
                  assignee="exec-1")
    e.wait_idle()
    T.signal(e, tid, "ACCEPT", "exec-1")
    T.signal(e, tid, "DELIVER", "exec-1", result="built it")
    e.wait_idle()


def _directive(e, tid="leaf"):
    steps = e.next_steps().get("steps") or []
    return next((s["directive"] for s in steps if s["task_id"] == tid), "")


def test_one_refused_report_is_named_in_the_step_with_the_move_that_follows_it():
    e = make_engine()
    e.start()
    _delivered(e)
    e.record_rejected_report(TaskId("leaf"), _BOTTOM, [{"criterion": "c", "verdict": "pass"}])

    said = _directive(e)

    assert "produced no verdict" in said, said
    assert "stronger model" in said or "record your own verdict" in said, said
    e.stop()


def test_the_second_one_says_the_contract_is_the_suspect_rather_than_the_run():
    """The same escalation `validate_result` gives its own caller, said where a driver reads."""
    e = make_engine()
    e.start()
    _delivered(e)
    for _ in range(2):
        e.record_rejected_report(TaskId("leaf"), _BOTTOM, [])

    said = _directive(e)

    assert "2 instrument report(s)" in said, said
    assert "Do NOT run the same tier again" in said, said
    assert "edit_criteria" in said, "the repair that is actually available is not named"
    e.stop()


def test_the_count_belongs_to_the_delivery_it_was_about():
    """A refusal from before a rework must not advise the driver about the delivery after it."""
    e = make_engine()
    e.start()
    _delivered(e)
    e.record_rejected_report(TaskId("leaf"), _BOTTOM, [])
    T.record_verdict(e, "leaf", "FAIL", reviewer="judge", failed_criteria=["c"],
                     observed={"c": "ran the check, it printed NOT-OK"})
    T.signal(e, "leaf", "FAIL", "exec-1", failed_criteria=["c"])
    T.signal(e, "leaf", "DELIVER", "exec-1", result="fixed it")
    e.wait_idle()

    assert e.get_state(TaskId("leaf")).name == "VALIDATING"
    assert "produced no verdict" not in _directive(e), (
        "a count carried across the rework advises about a delivery nobody attempted")
    e.stop()


def test_a_node_nobody_has_tried_to_judge_reads_exactly_as_before():
    """The negative control: the ordinary validate step must not grow a warning it has not earned."""
    e = make_engine()
    e.start()
    _delivered(e)

    assert "produced no verdict" not in _directive(e)
    e.stop()
