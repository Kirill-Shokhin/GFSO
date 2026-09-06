"""A human reviewer who saw one criterion red and one green could not record it.

`record_verdict` is the human counterpart of the machine validator's report, and the machine's report
has always carried a verdict per criterion. The human verb painted EVERY observed criterion with the
OVERALL verdict -- so recording `FAIL` with `failed_criteria=["parses"]` while also saying what
`matches` printed built a red set of BOTH, and the invariant refused the caller for a shape the verb
itself had made:

    failed_criteria ['parses'] != the report's own non-pass criteria ['matches', 'parses']

Observing only the failing criterion fails too, from the other side: the unspoken one has no verdict,
and an unevaluated conjunct is ⊥, never pass (§10/§11.2). So the honest partial FAIL had no route at
all -- on the door a person actually uses (found 2026-09-05 while probing Inv-3).

`failed_criteria` IS the red set (Inv-3). Everything else the reviewer observed passed.
"""
from __future__ import annotations

import pytest

import gfso.tools as T
from tests.support import UNMODELLED_FAULT, make_engine

_RISK = [{"item": UNMODELLED_FAULT.item, "predictability": "EXTRAORDINARY"}]
_OBSERVED = {"parses": "ran the parser suite: 3 red", "matches": "ran the matcher suite: green"}


@pytest.fixture(autouse=True)
def _no_plan_gate(monkeypatch):
    monkeypatch.setenv("GFSO_L2_GATE", "0")


def _recorded(verdict, failed, observed=None):
    e = make_engine(validate_signals=True, state_timeout=0)
    e.start()
    T.create_task(e, "n", {"description": "the work",
                           "criteria": [{"name": "parses", "description": "P"},
                                        {"name": "matches", "description": "M"}],
                           "accepted_risks": _RISK}, assignee="worker")
    T.signal(e, "n", "ACCEPT", "worker")
    T.signal(e, "n", "DELIVER", "worker", result="did it")
    e.record_reviewer_verdict("n", verdict, list(failed), reviewer="judge",
                              observed=dict(observed if observed is not None else _OBSERVED))
    out = {c["criterion"]: c["verdict"] for c in e.get_exec_verdict("n")["per_criterion"]}
    e.stop()
    return out


def test_one_red_among_two_is_recordable():
    assert _recorded("FAIL", ["parses"]) == {"parses": "fail", "matches": "pass"}


def test_a_whole_red_set_is_still_whole():
    assert _recorded("FAIL", ["parses", "matches"]) == {"parses": "fail", "matches": "fail"}


def test_a_pass_stays_a_pass_over_everything():
    """The control: the red set is empty, so nothing may come back failed."""
    assert _recorded("PASS", []) == {"parses": "pass", "matches": "pass"}


def test_the_evidence_the_reviewer_gave_is_what_is_stored():
    """Their own words per criterion -- the record answers "on what" for a person exactly as it does
    for the instrument, which is the whole point of this verb existing."""
    e = make_engine(validate_signals=True, state_timeout=0)
    e.start()
    T.create_task(e, "n", {"description": "the work",
                           "criteria": [{"name": "parses", "description": "P"},
                                        {"name": "matches", "description": "M"}],
                           "accepted_risks": _RISK}, assignee="worker")
    T.signal(e, "n", "ACCEPT", "worker")
    T.signal(e, "n", "DELIVER", "worker", result="did it")
    e.record_reviewer_verdict("n", "FAIL", ["parses"], reviewer="judge", observed=dict(_OBSERVED))
    ev = {c["criterion"]: c["evidence"] for c in e.get_exec_verdict("n")["per_criterion"]}
    assert ev["parses"].startswith("ran the parser suite")
    assert ev["matches"].startswith("ran the matcher suite")
    e.stop()
