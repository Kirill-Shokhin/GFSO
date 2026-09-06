"""The warning about irreversible loss has to arrive BEFORE the loss, not in the same reply as it.

`edit_criteria` on a node whose criteria are mapped to FINISHED children destroys those mappings for
good: a terminal node's contract cannot take a new `covers` (Inv-1), so re-adding the criterion does
not restore the coverage and CHECK-1 fails on that node from then on. The verb knew all of this — it
computed exactly which children were terminal — and computed it AFTER acting, so the reply explained
that the graph could never close again in the same breath as making that true.

A stranger on the MCP door reworded one criterion on a finished project and quoted the reply back
(wave 23, 2026-09-03): *"IRREVERSIBLE: w23mcp-cli, w23mcp-parser, w23mcp-suite are terminal … CHECK-1
will fail on this node from here on."* They then confirmed there was no way back — restoring the
criteria verbatim left four uncovered, and `map_criterion` refused every one. One call, no
confirmation, permanent.

The guard did not need to be invented; it needed to be moved to the other side of the act. This is
the fourth time in two days that sentence has been written into this codebase, which is why the test
carries it rather than the commit message.
"""
from __future__ import annotations

from gfso import tools as T
from gfso.core.types import TaskId
from tests.support import UNMODELLED_FAULT, make_engine


def _finished_child_covering_its_parent(e):
    T.create_task(e, "par", {"description": "the parent",
                             "criteria": [{"name": "g", "description": "G holds"},
                                          {"name": "h", "description": "H holds"}],
                             "accepted_risks": [{"item": UNMODELLED_FAULT.item,
                                                 "predictability": "EXTRAORDINARY"}]},
                  assignee="exec-1")
    T.create_task(e, "par.kid", {"description": "the child",
                                 "criteria": [{"name": "k", "description": "K holds"}]},
                  assignee="exec-1", parent_id="par")
    T.map_criterion(e, "par", "par.kid", "g")
    T.map_criterion(e, "par", "par.kid", "h")   # both, or CHECK-1 holds the plan and nothing executes
    e.wait_idle()
    T.signal(e, "par.kid", "ACCEPT", "exec-1")
    T.signal(e, "par.kid", "DELIVER", "exec-1", result="child built")
    T.record_verdict(e, "par.kid", "PASS", reviewer="judge",
                     observed={"k": "ran the k check and read K-OK"})
    T.signal(e, "par.kid", "PASS", "exec-1")
    e.wait_idle()
    assert e.get_task(TaskId("par.kid")).state.name == "DONE"


def test_dropping_a_finished_child_s_coverage_is_refused_before_it_happens():
    e = make_engine()
    e.start()
    _finished_child_covering_its_parent(e)

    out = T.edit_criteria(e, "par", [{"name": "h", "description": "H holds"}], "exec-1")

    assert out.get("refused") is True, out
    assert out.get("would_destroy_coverage") == ["par.kid"], out
    assert "cannot be undone" in out.get("error", ""), out
    assert [c.name for c in e.get_task(TaskId("par")).spec.criteria] == ["g", "h"], (
        "the contract was changed by the call that was supposed to refuse it")
    assert [(m.criterion_name, str(m.child_id))
            for m in (e.get_task(TaskId("par")).criterion_mappings or ())] == [("g", "par.kid"),
                                                                              ("h", "par.kid")]
    e.stop()


def test_the_refusal_names_a_route_that_keeps_the_work_and_one_that_does_not():
    """A refusal with no exit is a wall; this one has to carry both kinds of exit."""
    e = make_engine()
    e.start()
    _finished_child_covering_its_parent(e)

    err = T.edit_criteria(e, "par", [{"name": "h", "description": "H holds"}], "exec-1")["error"]

    assert "auto_decompose" in err, err                    # the canon's recovery, keeps the result
    assert "accept_coverage_loss=true" in err, err         # and the way to mean it anyway
    e.stop()


def test_saying_you_mean_it_still_works():
    """The opt-in is a real door, not a decoration: the loss is the caller's to accept."""
    e = make_engine()
    e.start()
    _finished_child_covering_its_parent(e)

    out = T.edit_criteria(e, "par", [{"name": "h", "description": "H holds"}], "exec-1",
                          accept_coverage_loss=True)

    assert out.get("refused") is not True, out
    assert [c.name for c in e.get_task(TaskId("par")).spec.criteria] == ["h"]
    e.stop()


def test_an_edit_that_destroys_nothing_irreversible_is_untouched():
    """The negative control: while the mapped child is still OPEN, `map_criterion` puts it back."""
    e = make_engine()
    e.start()
    T.create_task(e, "p2", {"description": "the parent",
                            "criteria": [{"name": "g", "description": "G holds"},
                                         {"name": "h", "description": "H holds"}],
                            "accepted_risks": [{"item": UNMODELLED_FAULT.item,
                                                "predictability": "EXTRAORDINARY"}]},
                  assignee="exec-1")
    T.create_task(e, "p2.kid", {"description": "the child",
                                "criteria": [{"name": "k", "description": "K holds"}]},
                  assignee="exec-1", parent_id="p2")
    T.map_criterion(e, "p2", "p2.kid", "g")
    T.map_criterion(e, "p2", "p2.kid", "h")
    e.wait_idle()

    out = T.edit_criteria(e, "p2", [{"name": "h", "description": "H holds"}], "exec-1")

    assert out.get("refused") is not True, out
    assert [c.name for c in e.get_task(TaskId("p2")).spec.criteria] == ["h"]
    e.stop()
