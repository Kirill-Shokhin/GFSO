"""The most expensive loop in the product, and the one fact that could shorten it.

Measured across every run this installation has recorded (2026-09-05, 414 project databases):

    total recorded spend        $782.10 over 2,922 calls
    of it the JUDGE             $441.77  (56.5%)  904 calls
    reports that decided NOTHING            151
      of those, "behaviours named but never probed"   140

The rule that refuses those reports is load-bearing — an unobserved conjunct cannot carry a pass
(§11.2) — and the failure is not capability. The report was well-formed, its commands were real, and
it simply did not run one per behaviour it had listed. The retry then re-judged the whole node from
scratch at a HIGHER tier, paying twice for a bookkeeping gap, while the one thing that would close
it — the list of what went unobserved — sat in the record and reached nobody: the validator's packet
carried the contract, the seams, the risks and the delivery, and nothing about its own last attempt.

An ordinary user had all three nodes of an honest run refused on the first report, at a paid round
each, and named the validation loop the worst part of the honest path (wave 25).

Scoped to the delivery, because a refusal from before a rework is about work nobody did.
"""
from __future__ import annotations

from gfso import tools as T, tools_llm as TL
from gfso.core.types import TaskId
from tests.support import UNMODELLED_FAULT, make_engine

_REFUSAL = "not a verdict on leaf: criterion 'c' - unobserved: the file exists, the file is readable"


def _delivered(e, tid="leaf"):
    T.create_task(e, tid, {"description": "a leaf",
                           "criteria": [{"name": "c", "description": "C"}],
                           "accepted_risks": [{"item": UNMODELLED_FAULT.item,
                                               "predictability": "EXTRAORDINARY"}]},
                  assignee="agent")
    e.wait_idle()
    T.signal(e, tid, "ACCEPT", "agent")
    T.signal(e, tid, "DELIVER", tid and "agent", result="built it")
    e.wait_idle()


def _packet(e, tid="leaf"):
    return TL._validator_packet(e, e.get_task(TaskId(tid)), "built it", ".")


def test_a_first_attempt_carries_no_such_section():
    """The negative control: nothing is invented for a judge that has not failed yet."""
    e = make_engine()
    e.start()
    _delivered(e)

    assert "PREVIOUS REPORT" not in _packet(e)
    e.stop()


def test_a_retry_is_handed_the_exact_gap_and_the_attempt_number():
    e = make_engine()
    e.start()
    _delivered(e)
    e.record_rejected_report(TaskId("leaf"), _REFUSAL, None)

    said = _packet(e)

    assert "PREVIOUS REPORT ON THIS DELIVERY WAS REFUSED" in said
    assert "unobserved: the file exists, the file is readable" in said, (
        "the retry is told it failed and not what was missing")
    assert "this is attempt 2" in said.lower(), said[-400:]
    assert "for every behaviour you name" in said, "the repair is not stated"
    e.stop()


def test_the_gap_does_not_survive_a_rework():
    """A refusal from before a rework describes a delivery nobody made."""
    e = make_engine()
    e.start()
    _delivered(e)
    e.record_rejected_report(TaskId("leaf"), _REFUSAL, None)
    T.record_verdict(e, "leaf", "FAIL", reviewer="judge", failed_criteria=["c"],
                     observed={"c": "ran the check, it printed NOT-OK"})
    T.signal(e, "leaf", "FAIL", "agent", failed_criteria=["c"])
    T.signal(e, "leaf", "DELIVER", "agent", result="fixed it")
    e.wait_idle()

    assert e.refused_report_for_this_delivery(TaskId("leaf")) is None
    assert "PREVIOUS REPORT" not in _packet(e)
    e.stop()
