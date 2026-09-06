"""COMPLETE has to say what kind of party judged, because that is the whole of what this measures.

Three doors, two waves, one address (2026-09-04/05):

* HTTP: *"the completion surface carries no provenance — for a root closed on an invented reviewer's
  word it returns exactly the same string as for my honestly-validated root."*
* MCP: *"`next_steps` and `get_graph` report COMPLETE without consulting it."*
* CLI: *"the two surfaces a user or manager actually reads show the same unqualified `[x]` /
  `complete: true` as the honestly-earned root, plus `q_V = 1.0`."*

All three then noted that the product does say it — in `get_verdict` (`by_hand`, `provenance`) and in
`gfso log` (*"This is a person's word, not an instrument's judgement"*). One surface knew and the two
a reader consults did not, which is the sixth instance of that shape in three days.

Withholding COMPLETE would be wrong: a person judging their own project by hand is the documented
solo path, and §13.6 says no structural check can establish a self-named reviewer's independence. So
this is carried BESIDE the answer, never instead of it.
"""
from __future__ import annotations

from gfso import tools as T
from gfso.core.types import TaskId
from tests.support import UNMODELLED_FAULT, make_engine


def _closed_by_hand(e, tid="leaf"):
    T.create_task(e, tid, {"description": "a leaf",
                           "criteria": [{"name": "c", "description": "C"}],
                           "accepted_risks": [{"item": UNMODELLED_FAULT.item,
                                               "predictability": "EXTRAORDINARY"}]},
                  assignee="exec-1")
    e.wait_idle()
    T.signal(e, tid, "ACCEPT", "exec-1")
    T.signal(e, tid, "DELIVER", "exec-1", result="claimed done")
    T.record_verdict(e, tid, "PASS", reviewer="inspector",
                     observed={"c": "I ran the check myself and read OK"})
    T.signal(e, tid, "PASS", "exec-1")
    e.wait_idle()
    assert e.get_state(TaskId(tid)).name == "DONE"


def _closed_by_an_instrument(e, tid="ok"):
    T.create_task(e, tid, {"description": "a leaf",
                           "criteria": [{"name": "c", "description": "C"}],
                           "accepted_risks": [{"item": UNMODELLED_FAULT.item,
                                               "predictability": "EXTRAORDINARY"}]},
                  assignee="exec-1")
    e.wait_idle()
    T.signal(e, tid, "ACCEPT", "exec-1")
    T.signal(e, tid, "DELIVER", "exec-1", result="built it")
    e.record_exec_verdict(TaskId(tid), "PASS", [], "val-1",
                          per_criterion=[{"criterion": "c", "verdict": "pass",
                                          "evidence": "ran the check, it printed OK",
                                          "behaviours": ["C holds"],
                                          "probe": [{"command": "check", "expect": "OK",
                                                     "behaviour": "C holds"}]}])
    T.signal(e, tid, "PASS", "exec-1")
    e.wait_idle()


def test_a_root_closed_by_hand_is_named_beside_complete():
    e = make_engine()
    e.start()
    _closed_by_hand(e)

    out = e.next_steps()

    assert out["complete"] is True, "the documented solo path must still be able to finish"
    assert out["closures_by_hand"] == ["leaf"], out
    assert "§13.6" in out["closures_by_hand_note"], out["closures_by_hand_note"]
    e.stop()


def test_a_root_an_instrument_judged_carries_nothing_extra():
    """The negative control — the earned green must not acquire a qualifier it did not earn."""
    e = make_engine()
    e.start()
    _closed_by_an_instrument(e)

    out = e.next_steps()

    assert out["complete"] is True
    assert "closures_by_hand" not in out, out
    e.stop()


def test_the_two_kinds_are_told_apart():
    """A hand verdict that DISPLACED an instrument's is the sharper fact and keeps its own name."""
    e = make_engine()
    e.start()
    _closed_by_hand(e, "leaf")

    assert e.closures_by_hand() == ["leaf"]
    assert e.hand_overruled_closures() == [], (
        "nothing was displaced here — that name is for the case where an instrument said otherwise")
    e.stop()
