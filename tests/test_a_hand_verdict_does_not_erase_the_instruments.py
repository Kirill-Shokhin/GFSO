"""Two parties validating one delivery in opposite directions is a fact, and it has to survive.

Wave 24's CLI door, 2026-09-04. Nothing was built. The instrument validated the node and recorded FAIL
with running evidence. A `record_verdict` PASS naming a reviewer invented in that same call replaced
it, and the node closed:

    get_verdict  -> verdict PASS, failed_criteria [], current true   (the FAIL nowhere in it)
    gfso status  -> [x] ... DONE                                     (the tick an earned node gets)
    next_steps   -> {"complete": true, ...}
    metrics      -> q_V 1.0

Four of the five surfaces a person reads reported an earned green; the refutation survived only in
the chronological log. `refuted_passes` — built for exactly this shape — does not fire, because it is
about a verdict landing AFTER the close, and this one landed first and was overwritten.

That was answered, first, by keeping the displaced record and naming the closure. It is now answered at
the record (2026-09-27): a divergence an independent observer recorded IS that criterion's value, fail,
and no later record turns it into a pass (Inv-2, §12.8). A person who holds the instrument wrong has the
issuer's moves — FAIL, or a revision of the criteria (Inv-1) — and their observation stays on the log as
a report. What survives of the old machinery is its negative control: two records that agree leave no
trace of a conflict, and a rework ends a disagreement.
"""
from __future__ import annotations

from gfso import tools as T
from gfso.core.types import TaskId
from tests.support import criterion, make_engine, REGISTER

_INSTRUMENT_FAIL = [{"criterion": "ghost_runs", "verdict": "fail",
                     "evidence": "python -m ghost: No module named ghost",
                     "behaviours": ["python -m ghost prints 2.0.0"]}]


def _validated_fail_then_passed_by_hand(e, tid="leaf"):
    T.create_task(e, tid, {"description": "nothing was ever built",
                           "criteria": [criterion("ghost_runs",
                                                  "python -m ghost prints 2.0.0")],
                           "accepted_risks": REGISTER},
                  assignee="agent")
    e.wait_idle()
    T.signal(e, tid, "ACCEPT", "agent")
    T.signal(e, tid, "DELIVER", "agent", result="claimed done")
    e.wait_idle()
    e.record_exec_verdict(TaskId(tid), "FAIL", ["ghost_runs"], "val-1",
                          per_criterion=_INSTRUMENT_FAIL)
    return T.record_verdict(e, tid, "PASS", reviewer="alice-qa",
                            observed={"ghost_runs": {"note": "I ran python -m ghost myself and saw 2.0.0, exit 0",
                                                     "ran": ["check ghost_runs"]}})


def test_a_hand_pass_does_not_overrule_an_observed_fail():
    e = make_engine()
    e.start()
    out = _validated_fail_then_passed_by_hand(e)

    assert "Inv-2" in str(out), out
    v = T.get_verdict(e, "leaf")
    assert v["verdict"] == "FAIL" and v["validator"] == "val-1", v
    e.stop()


def test_a_node_cannot_close_over_an_observed_fail():
    e = make_engine()
    e.start()
    _validated_fail_then_passed_by_hand(e)
    r = T.signal(e, "leaf", "PASS", "agent")
    e.wait_idle()

    assert not r.get("accepted"), r
    assert e.next_steps()["complete"] is False
    assert e.hand_overruled_closures() == []
    e.stop()


def test_a_rework_under_it_ends_the_contradiction():
    """The disagreement belongs to ONE delivery: after a rework it is history, not a live conflict."""
    e = make_engine()
    e.start()
    _validated_fail_then_passed_by_hand(e)
    T.record_verdict(e, "leaf", "FAIL", reviewer="alice-qa", failed_criteria=["ghost_runs"],
                     observed={"ghost_runs": "checked again: no module"})
    T.signal(e, "leaf", "FAIL", "agent", failed_criteria=["ghost_runs"])
    T.signal(e, "leaf", "DELIVER", "agent", result="built it this time")
    e.wait_idle()

    assert e.overruled_verdict(TaskId("leaf")) is None
    assert "overruled" not in T.get_verdict(e, "leaf")
    e.stop()


def test_two_verdicts_that_AGREE_leave_no_trace_of_a_conflict():
    """The negative control: re-validating the same delivery the same way is not a disagreement."""
    e = make_engine()
    e.start()
    T.create_task(e, "ok", {"description": "a leaf",
                            "criteria": [criterion("c", "C")],
                            "accepted_risks": REGISTER},
                  assignee="agent")
    e.wait_idle()
    T.signal(e, "ok", "ACCEPT", "agent")
    T.signal(e, "ok", "DELIVER", "agent", result="built it")
    e.record_exec_verdict(TaskId("ok"), "PASS", [], "val-1",
                          per_criterion=[{"criterion": "c", "verdict": "pass",
                                          "evidence": "ran the check, it printed OK",
                                          "behaviours": ["C holds"],
                                          "probe": [{"command": "check c", "expect": "OK",
                                                     "behaviour": "C holds"}]}])
    T.record_verdict(e, "ok", "PASS", reviewer="alice-qa",
                     observed={"c": {"note": "ran the same check myself and read OK",
                                     "ran": ["check c"]}})

    assert "overruled" not in T.get_verdict(e, "ok")
    assert e.hand_overruled_closures() == []
    e.stop()
