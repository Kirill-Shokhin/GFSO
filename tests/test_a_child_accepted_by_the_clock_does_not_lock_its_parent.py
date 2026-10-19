"""A child the CLOCK accepted: the edge is gone, and the rows it already wrote still have to read.

v4.1 removed auto_pass (§16.14): a timed-out VALIDATING now hands the decision back to its issuer in
ESCALATED, because the clock, answering for a silent party, may not invent a verdict — and this was
the one timeout that did. The first test below pins that.

What does not go away is a database written by an older build. Such a row is DONE(AUTO_PASS), and
the two facts this file was written for still hold of it: the parent's conjunction accepts it (the
canon's reading of acceptance — probed 2026-09-07, when asking instead whether the pass was EARNED
locked the whole ancestry with no exit from anywhere), and the closure says so out loud, because an
acceptance a parent stands on unremarked is the lock's mirror image — a green nobody can weigh.
"""
from __future__ import annotations

import gfso.tools as T
from gfso.core.types import DoneReason, Signal, SignalData, State, TaskId
from tests.support import criterion, make_engine, REGISTER

_RISK = REGISTER


def _graph():
    e = make_engine(validate_signals=True, state_timeout=0)
    e.start()
    T.create_task(e, "root", {"description": "a goal", "accepted_risks": _RISK,
                              "criteria": [criterion("g", "G holds")]},
                  assignee="agent")
    T.decompose(e, "root", [{"task_id": "kid", "spec": {"description": "the work",
                             "criteria": [criterion("k", "K holds")]}, "assignee": "agent", "covers": ["g"]}], accepted_risks=REGISTER)
    return e


def _child_a_clock_accepted(e):
    """A row as an older build left it: DONE(AUTO_PASS). No edge produces it any more (§16.14), so it
    is written the way a reader finds it — in the graph — rather than through a signal."""
    T.signal(e, "kid", "ACCEPT", "agent")
    T.signal(e, "kid", "DELIVER", "agent", result="did the work")
    e.wait_idle()
    t = e._graph.get_task(TaskId("kid"))
    t.state, t.done_reason = State.DONE, DoneReason.AUTO_PASS
    e._graph.save_task(t)


def test_the_clock_no_longer_accepts_for_the_issuer():
    """The edge itself: the timeout that used to close DONE(auto_pass) hands the node back (§16.14)."""
    e = _graph()
    T.signal(e, "kid", "ACCEPT", "agent")
    T.signal(e, "kid", "DELIVER", "agent", result="did the work")
    e.send_signal(SignalData(signal=Signal.TIMEOUT, task_id=TaskId("kid")))
    e.wait_idle()
    t = e.graph.get_task("kid")
    assert t.state.name == "ESCALATED" and t.done_reason is None
    e.stop()


def _parent_claims_the_aggregate(e):
    T.signal(e, "root", "ACCEPT", "agent")
    T.signal(e, "root", "DELIVER", "agent", result="the aggregate")
    T.record_verdict(e, "root", "PASS", reviewer="rev",
                     observed={"g": {"note": "read the child's artifact end to end; it holds",
                                    # …and the part's pinned probe over this delivery: g rests on it
                                    "ran": ["check g", "check k"]}})
    return T.signal(e, "root", "PASS", "agent")


def test_the_parents_conjunction_accepts_a_child_the_clock_accepted():
    e = _graph()
    _child_a_clock_accepted(e)
    out = _parent_claims_the_aggregate(e)
    assert out.get("accepted") is True, \
        f"the parent is locked behind a terminal child with no way back: {out.get('error')}"
    assert e.graph.get_task("root").state.name == "DONE"
    e.stop()


def test_the_completion_says_which_part_nobody_checked():
    e = _graph()
    _child_a_clock_accepted(e)
    _parent_claims_the_aggregate(e)
    assert e.auto_accepted_closures(TaskId("root")) == ["kid"], \
        "the scoped list must find it — a subtree is the parent edges, not a spelling of the ids"
    step = T.next_step(e, "root")
    assert step.get("complete") is True
    assert "kid" in (step.get("auto_accepted_closures") or []), \
        "a result standing on an unchecked part must say so where the reader already looks"
    assert "CLOCK" in (step.get("auto_accepted_note") or ""), \
        "the note has to name what happened, not merely flag the node"
    e.stop()


def test_a_child_that_actually_failed_still_blocks():
    """The control. The conjunction is narrowed to the canon's reading, not loosened in general:
    a child that did not settle positively must still hold its parent."""
    e = _graph()
    T.signal(e, "kid", "ACCEPT", "agent")
    T.signal(e, "kid", "DELIVER", "agent", result="a first attempt")
    T.record_verdict(e, "kid", "FAIL", reviewer="rev", failed_criteria=["k"],
                     observed={"k": {"note": "ran it: red on the first case",
                                   "ran": ["check k"]}})
    T.signal(e, "kid", "FAIL", "agent", failed_criteria=["k"])
    out = _parent_claims_the_aggregate(e)
    assert out.get("accepted") is False and "children" in str(out.get("error")), \
        f"a parent passed over a child in rework: {out}"
    e.stop()
