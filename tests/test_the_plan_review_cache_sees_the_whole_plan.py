"""A re-run that returns the previous verdict must be about the previous plan.

The per-criterion cache exists for a good reason: keyed on the whole plan, ANY edit anywhere threw
away every decision, and a criterion certified in round 2 came back in round 3 with itself untouched.
What it was keyed on was too little — the parent criterion's TEXT, the covering children, and those
children's criterion NAMES. Rewrite a child's criterion to anything at all under the same name and
the stamp does not move.

Measured on the CLI door (wave 25, 2026-09-05). A child's only criterion was replaced by "parse_kv
exists and is callable" against a parent demanding three behaviours including two ValueError paths;
`edit_criteria` honestly staled the review, the caller honestly re-ran it, and the re-run answered
`sufficient` because *"w25cli-kv's criterion is textually identical to the parent"* — a sentence
false against the graph's own stored data. Reproduced with "the developer has thought about parsing
and feels reasonably confident about it". Appending " (rev2)" to the PARENT's text forced a real
re-derivation, which was immediately correct — the checker was capable, it was simply never asked.

A gate that re-runs and hands back a lie is worse than one that does not re-run: the caller did the
right thing and was told the plan was fine.
"""
from __future__ import annotations

from gfso import tools as T
from gfso.critic.runner import _criterion_stamps
from gfso.core.types import TaskId
from tests.support import criterion, make_engine, REGISTER


def _parent_with_one_covering_child(e):
    """`parse_contract` covered by one child; a second criterion, `x`, by another — the room an unrelated sibling
    is admitted into (§11.5: every child of a split covers a criterion of its parent)."""
    T.create_task(e, "root", {"description": "goal",
                              "criteria": [criterion("parse_contract",
                                                     "parse_kv raises ValueError on a missing "
                                                     "separator and on an empty key"), criterion("x", "X")]},
                  assignee="agent")
    T.decompose(e, "root", [
        {"task_id": "root.kv", "spec": {"description": "the kv child",
                                        "criteria": [criterion("parse_behaviour",
                                                               "parse_kv raises ValueError on a "
                                                               "missing separator and on an empty key")]},
         "assignee": "agent", "covers": ["parse_contract"]},
        {"task_id": "root.x", "spec": {"description": "x", "criteria": [criterion("x", "X")]},
         "assignee": "agent", "covers": ["x"]}], accepted_risks=REGISTER)
    e.wait_idle()


def test_rewriting_a_child_criterion_under_the_same_name_changes_the_stamp():
    e = make_engine()
    e.start()
    _parent_with_one_covering_child(e)
    before = _criterion_stamps(e, e.graph.get_task(TaskId("root")))

    T.edit_criteria(e, "root.kv", [criterion("parse_behaviour",           # the SAME name
                                             "parse_kv exists and is callable.")], "agent")
    e.wait_idle()
    after = _criterion_stamps(e, e.graph.get_task(TaskId("root")))

    assert before != after, (
        "the plan changed under the review and the stamp did not move — the next round will hand "
        "back the previous verdict, whose stored reason is now false")
    e.stop()


def test_the_stamp_carries_the_text_and_not_only_the_name():
    """Stated directly, because it is the one thing the docstring already promised and did not do."""
    e = make_engine()
    e.start()
    _parent_with_one_covering_child(e)

    stamp = _criterion_stamps(e, e.graph.get_task(TaskId("root")))["parse_contract"]

    flat = repr(stamp)
    assert "parse_behaviour" in flat, "the child's criterion NAME is part of the question"
    assert "missing separator" in flat, "the child's criterion TEXT is what the question is ABOUT"
    e.stop()


def test_a_plan_nobody_touched_still_keeps_its_decisions():
    """The negative control — the whole point of a per-criterion stamp is that it does not churn."""
    e = make_engine()
    e.start()
    _parent_with_one_covering_child(e)
    before = _criterion_stamps(e, e.graph.get_task(TaskId("root")))

    T.create_task(e, "root.other", {"description": "an unrelated sibling",
                                    "criteria": [criterion("x", "X")]},
                  assignee="agent", parent_id="root", covers=["x"])
    e.wait_idle()

    assert _criterion_stamps(e, e.graph.get_task(TaskId("root")))["parse_contract"] == \
        before["parse_contract"], "an edit elsewhere in the plan re-litigated an untouched criterion"
    e.stop()
