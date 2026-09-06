"""The door the product pushes you to was weaker than the door it guards.

`record_verdict` refuses a PASS whose observations only restate the verdict — *"a PASS needs to say
what was OBSERVED, one line per criterion"*. `DELIVER(self_validation=PASS)` took `result="yep"` and
recorded a passing verdict on the node, which then closed carrying a criterion it did not meet (HTTP
door, wave 26, 2026-09-06). §14.5 D6 makes that report the record an internal node is judged on, so
it is the same demand at the same grade.

One owner for the floor (`gfso.core.protocol.invariants`), because two spellings of one rule is
exactly how these two doors came apart. The negative controls matter more than the rule here: an
honest short report must survive, and a FAIL must not be gated at all — an executor reporting their
own failure is the direction this product wants, and ⊥ is not a pass anyway (§11.2).
"""
from __future__ import annotations

from gfso import tools
from gfso import tools as T
from gfso.core.protocol.invariants import content_words, is_pure_assent
from gfso.core.types import TaskId
from tests.support import UNMODELLED_FAULT, make_engine

_RISKS = [{"item": UNMODELLED_FAULT.item, "predictability": "EXTRAORDINARY"}]


def _internal_leaf(e, tid):
    """A leaf whose Del is its parent's — the §14.5 internal node that self-verifies."""
    T.create_task(e, "root", {"description": "r", "criteria": [{"name": "c", "description": "C"}],
                              "accepted_risks": _RISKS}, assignee="agent")
    T.create_task(e, tid, {"description": "a leaf", "criteria": [{"name": "k", "description": "K"}]},
                  assignee="agent", parent_id="root")
    T.map_criterion(e, "root", tid, "c")
    e.wait_idle()
    T.signal(e, tid, "ACCEPT", "agent")


def _delivered_with(e, tid, report, verdict="PASS"):
    T.signal(e, tid, "DELIVER", "agent", result=report, self_validation=verdict)
    e.wait_idle()
    return e.get_exec_verdict(TaskId(tid))


def test_a_self_pass_over_a_report_that_records_nothing_is_not_recorded():
    e = make_engine()
    e.start()
    _internal_leaf(e, "thin")

    rec = _delivered_with(e, "thin", "yep")

    assert not rec, "the exact report measured at the door: a self-PASS over `yep`"
    assert e.get_state(TaskId("thin")).name == "VALIDATING", (
        "the DELIVER itself stands — what is refused is the RECORD, so the node now needs a real "
        "one before it can close")
    e.stop()


def test_an_honest_short_report_still_records():
    """The negative control that matters: a true short observation must not be refused."""
    e = make_engine()
    e.start()
    _internal_leaf(e, "real")

    rec = _delivered_with(e, "real", "ran pytest -q, 12 passed, no output on stderr")

    assert rec and rec.get("verdict") == "PASS", rec
    e.stop()


def test_a_self_fail_is_never_gated():
    """Reporting your own failure is the honest direction; a floor there would punish it."""
    e = make_engine()
    e.start()
    _internal_leaf(e, "honest")

    rec = _delivered_with(e, "honest", "nope", verdict="FAIL")

    assert rec and rec.get("verdict") == "FAIL", rec
    e.stop()


def test_the_two_doors_read_one_floor():
    """`record_verdict`'s refusal and the DELIVER refusal are the same predicate, not two."""
    assert tools._is_pure_assent is is_pure_assent, "aliased, not reimplemented"
    assert is_pure_assent("yep") and len(content_words("yep")) == 0
    assert not is_pure_assent("no output, exit 0"), "the honest short observation, again"
