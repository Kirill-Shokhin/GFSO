"""A verdict passed every criterion and waived, in its own prose, the divergences it had observed.

Measured on `c_compiler` (2026-09-20/21): the closing verdict recorded every criterion "pass" while
its text set aside what it had actually seen by citing the ACCEPTED_RISKS register — and six of the
waived items were behaviours the contract REQUIRES. Nothing structural could see it, because the
divergences lived in sentences.

§12.8 Inv-2 as v4.1 states it: "a divergence the validator observes between the result and what the
criterion states is that criterion's value, fail; and no register entry turns either into pass",
and what the protocol CAN refuse is "where the record carries observed divergences per criterion as
data, a non-empty one under pass". So they are carried as data — `divergences` on the per-criterion
entry — and the refusal is at the record, which is where every door lands. A waiver remains
possible and remains the ISSUER's act (`edit_criteria`, `edit_accepted_risks`), logged; it is never
a sentence inside a pass.
"""
from __future__ import annotations

import pytest

from gfso import tools as T
from gfso.core.protocol.invariants import verdict_report_defects
from tests.support import criterion, make_engine

_PROBE = [{"behaviour": "C holds", "command": "check c", "expect": "it holds"}]


def _entry(verdict="pass", divergences=()):
    e = {"criterion": "c", "verdict": verdict, "evidence": "ran it", "behaviours": ["C holds"],
         "probe": list(_PROBE)}
    if divergences:
        e["divergences"] = list(divergences)
    return e


def _delivered(assignee="worker"):
    e = make_engine(check_interval=10_000)
    e.start()
    T.create_task(e, "n", {"description": "leaf", "criteria": [criterion("c", "C")]},
                  assignee=assignee)
    T.signal(e, "n", "ACCEPT", assignee)
    T.signal(e, "n", "DELIVER", assignee, result="did it")
    return e


# ── the invariant itself ─────────────────────────────────────────────────────

def test_a_pass_over_a_recorded_divergence_is_not_a_verdict():
    defects = verdict_report_defects(["c"], "PASS", [_entry(divergences=["-O2 is ignored"])], [])
    assert defects, "a criterion marked pass beside an observed divergence decides nothing"
    assert "Inv-2" in defects[0] and "-O2 is ignored" in defects[0]
    assert "ACCEPTED_RISKS" in defects[0], \
        "the message has to say what the register cannot do — that is the sentence the waived " \
        "verdict was written against"


def test_the_same_divergence_under_a_fail_is_a_well_formed_verdict_and_is_kept():
    """The negative control: recording what you saw is the point, and it must stay possible —
    and it has to survive into the STORED record, which is the trail a later reader re-validates from
    (Thm 11). A field the schema asks for and the record drops is a field nobody can audit."""
    assert verdict_report_defects(["c"], "FAIL", [_entry("fail", ["-O2 is ignored"])], ["c"]) == []

    e = _delivered()
    e.record_exec_verdict("n", "FAIL", ["c"], "val-1",
                          per_criterion=[_entry("fail", ["-O2 is ignored"])])
    stored = e.get_exec_verdict("n")["per_criterion"]
    assert stored[0]["divergences"] == ["-O2 is ignored"]
    e.stop()


def test_an_empty_list_is_not_a_divergence():
    assert verdict_report_defects(["c"], "PASS", [_entry(divergences=[])], []) == []
    assert verdict_report_defects(["c"], "PASS", [_entry()], []) == []


# ── and the refusal lands at the record, on both doors ───────────────────────

def test_the_instruments_pass_carrying_a_divergence_is_refused_at_the_record():
    e = _delivered()
    with pytest.raises(ValueError, match="Inv-2"):
        e.record_exec_verdict("n", "PASS", [], "val-1",
                              per_criterion=[_entry(divergences=["the flag is ignored"])])
    assert T.get_verdict(e, "n").get("verdict") is None, \
        "nothing may be stored as a verdict here — a refused report is ⊥, not a pass"
    e.stop()


def test_a_hand_recorded_pass_carrying_a_divergence_is_refused_too():
    """The hand door is where a waiver is easiest to write, so it is where the field must reach."""
    e = _delivered()
    out = T.record_verdict(e, "n", "PASS", reviewer="somebody",
                           observed={"c": {"note": "ran it", "ran": ["check c"],
                                           "divergences": ["the flag is ignored"]}})
    assert not out.get("recorded"), out
    assert "Inv-2" in str(out.get("error") or out)
    e.stop()
