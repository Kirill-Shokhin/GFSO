"""Coverage an edit drops from a finished child is put back by `map_criterion` — the mapping is the split's.

`edit_criteria` replaces the set, and a criterion it does not name takes its mapping with it. That loss was refused
as irreversible ("a finished node's contract cannot take a new `covers`", Inv-1), on a reading of the mapping as the
child's contract — while the canon puts it in the split: "a split maps each child to the criteria of t it is
responsible for" (§2.4), and Inv-1's packet fields carry no coverage (§12.3). A remap is a re-admission of the split
(§11.5), so a passed child takes a mapping again, keeping its pass (critic r15).

The reply still says, in the same breath, which mappings went (wave 23, 2026-09-03: a caller reworded a criterion on
a finished project and learned of the loss only afterwards).
"""
from __future__ import annotations

from gfso import tools as T
from gfso.core.types import TaskId
from tests.support import criterion, make_engine, REGISTER


def _finished_child_covering_its_parent(e):
    T.create_task(e, "par", {"description": "the parent",
                             "criteria": [criterion("g", "G holds"), criterion("h", "H holds")],
                             "accepted_risks": REGISTER},
                  assignee="exec-1")
    T.decompose(e, "par", [{"task_id": "par.kid", "spec": {"description": "the child",
                                 "criteria": [criterion("k", "K holds")]}, "assignee": "exec-1", "covers": ["g", "h"]}],
                accepted_risks=REGISTER)
    e.wait_idle()
    T.signal(e, "par.kid", "ACCEPT", "exec-1")
    T.signal(e, "par.kid", "DELIVER", "exec-1", result="child built")
    T.record_verdict(e, "par.kid", "PASS", reviewer="validator",
                     observed={"k": {"note": "ran the k check and read K-OK", "ran": ["check k"]}})
    T.signal(e, "par.kid", "PASS", "exec-1")
    e.wait_idle()
    assert e.graph.get_task(TaskId("par.kid")).state.name == "DONE"


def test_an_edit_that_drops_a_finished_childs_coverage_says_so_and_is_not_refused():
    e = make_engine()
    e.start()
    _finished_child_covering_its_parent(e)
    out = T.edit_criteria(e, "par", [criterion("h", "H holds")], "exec-1")
    assert out.get("refused") is not True, out
    assert out["coverage_dropped"] == ["g -> par.kid"] and "can re-make them" in out["coverage_dropped_note"]
    e.stop()


def test_the_dropped_coverage_is_put_back_on_the_finished_child_keeping_its_pass():
    e = make_engine()
    e.start()
    _finished_child_covering_its_parent(e)
    T.edit_criteria(e, "par", [criterion("h", "H holds")], "exec-1")
    T.edit_criteria(e, "par", [criterion("g", "G holds"), criterion("h", "H holds")], "exec-1")
    e.wait_idle()
    assert [h["check"] for h in T.list_holes(e)["holes"]] == ["CHECK-1:coverage"]
    out = T.map_criterion(e, "par", "par.kid", "g")
    e.wait_idle()
    assert out["still_uncovered"] == [] and T.list_holes(e)["holes"] == []
    kid = e.graph.get_task(TaskId("par.kid"))
    assert (kid.state.name, kid.revisions, kid.reopens) == ("DONE", 0, 0)
    e.stop()
