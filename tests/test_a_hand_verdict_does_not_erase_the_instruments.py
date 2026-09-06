"""Two parties judging one delivery in opposite directions is a fact, and it has to survive.

Wave 24's CLI door, 2026-09-04. Nothing was built. The instrument judged the node and recorded FAIL
with running evidence. A `record_verdict` PASS naming a reviewer invented in that same call replaced
it, and the node closed:

    get_verdict  -> verdict PASS, failed_criteria [], current true   (the FAIL nowhere in it)
    gfso status  -> [x] ... DONE                                     (the tick an earned node gets)
    next_steps   -> {"complete": true, ...}
    metrics      -> q_V 1.0

Four of the five surfaces a person reads reported an earned green; the refutation survived only in
the chronological log. `refuted_passes` — built for exactly this shape — does not fire, because it is
about a verdict landing AFTER the close, and this one landed first and was overwritten.

Overruling is legitimate and stays: the verdict is the issuer's act (§14.5), and §13.6 says no
structural check can establish that a self-named reviewer is independent — a run where a person
correctly overrode a wrong instrument must still be able to finish. What is refused is doing it
SILENTLY. So the displaced record is kept (`overruled`), and the closure is named beside the answer
rather than instead of it.
"""
from __future__ import annotations

from gfso import tools as T
from gfso.core.types import TaskId
from tests.support import UNMODELLED_FAULT, make_engine

_INSTRUMENT_FAIL = [{"criterion": "ghost_runs", "verdict": "fail",
                     "evidence": "python -m ghost: No module named ghost",
                     "behaviours": ["python -m ghost prints 2.0.0"]}]


def _judged_fail_then_passed_by_hand(e, tid="leaf"):
    T.create_task(e, tid, {"description": "nothing was ever built",
                           "criteria": [{"name": "ghost_runs",
                                         "description": "python -m ghost prints 2.0.0"}],
                           "accepted_risks": [{"item": UNMODELLED_FAULT.item,
                                               "predictability": "EXTRAORDINARY"}]},
                  assignee="agent")
    e.wait_idle()
    T.signal(e, tid, "ACCEPT", "agent")
    T.signal(e, tid, "DELIVER", "agent", result="claimed done")
    e.wait_idle()
    e.record_exec_verdict(TaskId(tid), "FAIL", ["ghost_runs"], "val-1",
                          per_criterion=_INSTRUMENT_FAIL)
    T.record_verdict(e, tid, "PASS", reviewer="alice-qa",
                     observed={"ghost_runs": "I ran python -m ghost myself and saw 2.0.0, exit 0"})


def test_the_displaced_verdict_is_kept_and_read_back():
    e = make_engine()
    e.start()
    _judged_fail_then_passed_by_hand(e)

    out = T.get_verdict(e, "leaf")

    assert out["verdict"] == "PASS" and out["by_hand"] is True
    assert out["overruled"]["verdict"] == "FAIL", out
    assert out["overruled"]["validator"] == "val-1"
    assert out["overruled"]["by_hand"] is False
    assert "asserted by hand" in out["overruled_note"], out["overruled_note"]
    e.stop()


def test_the_closure_is_named_where_completeness_is_claimed():
    e = make_engine()
    e.start()
    _judged_fail_then_passed_by_hand(e)
    T.signal(e, "leaf", "PASS", "agent")
    e.wait_idle()

    out = e.next_steps()

    assert out["complete"] is True, "a legitimate override must not make the graph unfinishable"
    assert out["hand_overruled_closures"] == ["leaf"], out
    assert "§13.6" in out["hand_overruled_note"], out["hand_overruled_note"]
    e.stop()


def test_a_rework_under_it_ends_the_contradiction():
    """The disagreement belongs to ONE delivery: after a rework it is history, not a live conflict."""
    e = make_engine()
    e.start()
    _judged_fail_then_passed_by_hand(e)
    T.record_verdict(e, "leaf", "FAIL", reviewer="alice-qa", failed_criteria=["ghost_runs"],
                     observed={"ghost_runs": "checked again: no module"})
    T.signal(e, "leaf", "FAIL", "agent", failed_criteria=["ghost_runs"])
    T.signal(e, "leaf", "DELIVER", "agent", result="built it this time")
    e.wait_idle()

    assert e.overruled_verdict(TaskId("leaf")) is None
    assert "overruled" not in T.get_verdict(e, "leaf")
    e.stop()


def test_two_verdicts_that_AGREE_leave_no_trace_of_a_conflict():
    """The negative control: re-judging the same delivery the same way is not a disagreement."""
    e = make_engine()
    e.start()
    T.create_task(e, "ok", {"description": "a leaf",
                            "criteria": [{"name": "c", "description": "C"}],
                            "accepted_risks": [{"item": UNMODELLED_FAULT.item,
                                                "predictability": "EXTRAORDINARY"}]},
                  assignee="agent")
    e.wait_idle()
    T.signal(e, "ok", "ACCEPT", "agent")
    T.signal(e, "ok", "DELIVER", "agent", result="built it")
    e.record_exec_verdict(TaskId("ok"), "PASS", [], "val-1",
                          per_criterion=[{"criterion": "c", "verdict": "pass",
                                          "evidence": "ran the check, it printed OK",
                                          "behaviours": ["C holds"],
                                          "probe": [{"command": "check", "expect": "OK",
                                                     "behaviour": "C holds"}]}])
    T.record_verdict(e, "ok", "PASS", reviewer="alice-qa",
                     observed={"c": "ran the same check myself and read OK"})

    assert "overruled" not in T.get_verdict(e, "ok")
    assert e.hand_overruled_closures() == []
    e.stop()
