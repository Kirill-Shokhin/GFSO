"""A verdict is about a DELIVERY, so there has to be one standing (§14.5).

The rule existed and covered one end of the interval: a settled node "is not being judged, so a
verdict about it changes nothing". The other end was open, and a stranger on the CLI door walked
through it in four calls (wave 23, 2026-09-03):

    FAIL                      -> node goes to REWORKING, generation moves to iteration=1
    record_verdict PASS       -> accepted, naming a reviewer invented in the same second
    DELIVER "nothing changed" -> "an independent verdict for THIS delivery is already on the record"
    PASS by its own executor  -> accepted, DONE

The generation stamp cannot catch this by itself — it moves AT the rework, so a verdict written just
after the move carries the fresh numbers and reads as current for a delivery that has not happened.
`docs/USING_GFSO.md` §5 promises the opposite in as many words ("a rework, a reopen or a revision
under it makes the record about an earlier delivery"), which is what made it worth closing rather
than documenting: the door said the true thing and did the other one.

Reproduced by hand before the fix, in the same four calls, with the same result.
"""
from __future__ import annotations

import pytest

from gfso import tools as T
from gfso.core.types import TaskId
from tests.support import UNMODELLED_FAULT, make_engine


def _reworking(e, tid="leaf"):
    """A node whose first delivery was refused — the state the exploit needs."""
    T.create_task(e, tid, {"description": "a leaf",
                           "criteria": [{"name": "c", "description": "C"}],
                           "accepted_risks": [{"item": UNMODELLED_FAULT.item,
                                               "predictability": "EXTRAORDINARY"}]},
                  assignee="exec-1")
    e.wait_idle()
    T.signal(e, tid, "ACCEPT", "exec-1")
    T.signal(e, tid, "DELIVER", "exec-1", result="first try")
    T.record_verdict(e, tid, "FAIL", reviewer="judge", failed_criteria=["c"],
                     observed={"c": "ran the check, it printed NOT-OK"})
    T.signal(e, tid, "FAIL", "exec-1", failed_criteria=["c"])
    e.wait_idle()
    assert e.get_state(TaskId(tid)).name == "REWORKING"


def test_no_verdict_is_recorded_while_the_work_is_being_redone():
    e = make_engine()
    e.start()
    _reworking(e)

    out = T.record_verdict(e, "leaf", "PASS", reviewer="phantom-qa",
                           observed={"c": "I checked it and the content was there as required"})

    assert out.get("recorded") is False, out
    assert "no delivery standing" in (out.get("error") or ""), out
    e.stop()


def test_and_the_next_delivery_does_not_inherit_one():
    """The consequence that mattered: the re-delivery must not announce a verdict it does not have."""
    e = make_engine()
    e.start()
    _reworking(e)
    T.record_verdict(e, "leaf", "PASS", reviewer="phantom-qa",
                     observed={"c": "I checked it and the content was there as required"})

    delivered = T.signal(e, "leaf", "DELIVER", "exec-1", result="same delivery, nothing changed")
    signed = T.signal(e, "leaf", "PASS", "exec-1")

    assert "already on the record" not in (delivered.get("awaiting_verdict") or "")
    assert signed["accepted"] is False, "the executor closed its own node on a verdict from before"
    assert e.get_state(TaskId("leaf")).name == "VALIDATING"
    e.stop()


def test_a_verdict_on_the_delivery_being_judged_is_recorded_exactly_as_before():
    """The negative control: the ordinary act — judge what was just delivered — must be untouched."""
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

    out = T.record_verdict(e, "ok", "PASS", reviewer="judge",
                           observed={"c": "ran the check, it printed OK"})

    assert out.get("recorded") is True, out
    assert T.signal(e, "ok", "PASS", "exec-1")["accepted"] is True
    e.stop()
