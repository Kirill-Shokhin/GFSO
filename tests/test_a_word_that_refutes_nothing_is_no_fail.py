"""A criterion the report leaves neither passed nor failed is ⊥, never a FAIL: the FAIL payload is what it refuted.

By §2.3 a criterion nothing decided has no value; by Thm 2 a FAIL absorbs it, so the FAIL names the criteria the
report REFUTED (Inv-3) and any other non-pass word is ⊥. Read as a fail, a validator's `undecidable` sent the node to
rework charged to the executor, who had nothing to fix — the slugify/dedupe class the engine already cured for gaps it
finds itself. With nothing refuted the report is no verdict: refused through that same path (retry, then park).

CONTROL: drop the word clause from `accounting.unaccounted_for` and both tests go red.
"""
from __future__ import annotations

import pytest

from gfso import tools as T
from tests.support import criterion, make_engine


def _delivered():
    e = make_engine(check_interval=10_000)
    e.start()
    T.create_task(e, "n", {"description": "leaf", "criteria": [criterion("a", "A"), criterion("b", "B")]},
                  assignee="worker")
    T.signal(e, "n", "ACCEPT", "worker")
    T.signal(e, "n", "DELIVER", "worker", result="did it")
    return e


def _entry(name, word, evidence):
    return {"criterion": name, "verdict": word, "evidence": evidence, "behaviours": [f"{name} holds"],
            "probe": [{"behaviour": f"{name} holds", "command": f"check {name}",
                       "expect": "it holds"}], "divergences": []}


def test_an_undecidable_that_refutes_nothing_is_refused_never_reworked():
    e = _delivered()
    with pytest.raises(ValueError) as bottom:
        e.record_exec_verdict("n", "FAIL", ["a"], "val-1", require_probe=True, per_criterion=[
            _entry("a", "undecidable", "not decidable as written: 'feels fast' names nothing to observe"),
            _entry("b", "pass", "it holds")])
    assert "⊥" in str(bottom.value) and "'a'" in str(bottom.value), str(bottom.value)
    assert e.get_exec_verdict("n") is None, "no FAIL was written behind the refusal"
    assert e.graph.get_task("n").state.name == "VALIDATING", "nothing moved: there is no verdict to move on"
    e.stop()


def test_a_fail_beside_an_undecidable_names_only_what_was_refuted():
    e = _delivered()
    out = e.record_exec_verdict("n", "FAIL", ["a", "b"], "val-1", require_probe=True, per_criterion=[
        _entry("a", "undecidable", "not decidable as written"), _entry("b", "fail", "check b printed nothing")])
    assert out == {"verdict": "FAIL", "failed_criteria": ["b"]}, out
    e.stop()
