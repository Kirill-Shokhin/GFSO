"""A node closed DONE/PASS on a record that said nothing about any of its criteria.

Reproduced 2026-09-07 through ordinary verbs, nothing patched and nothing private reached:
`add_dependency(A, B)` makes the engine author a `dep__A` criterion on B; `edit_criteria(B, [])`
then wipes B's own criteria and the authored one survives; a reviewer records
`PASS, observed={}`; the issuer signs it; B is DONE/PASS with `per_criterion: []` — beside a record
whose own `independence` line says its weight IS the observation text next to each criterion.

Two independent absences had to line up, and each is the same shape — a rule that is vacuously true
when the thing it quantifies over is empty:

* the floor that demands one observation per criterion computes its requirement as the criteria
  that are NOT dependency links. Every criterion B had left was one, so the requirement was empty
  and the floor was met by observing nothing. The defect there is the CONTRACT — a node with no
  obligation of its own — and it is named as one rather than papered over by demanding evidence for
  glue, whose truth is the producer's passing;
* the engine's report battery ran under `if per_criterion is not None`, and the reviewer path
  passed `... or None` for an empty observation set. So observing nothing did not fail the battery,
  it switched the battery off — the defensive default disabling its own guard.

The controls matter as much as the rules: a rule tightened for a defect has to be tried on honest
work, or it silences the thing it was meant to sharpen.
"""
from __future__ import annotations

import pytest

import gfso.tools as T
from tests.support import make_engine

_RISK = [{"item": "an unmodelled environment fault", "predictability": "EXTRAORDINARY"}]


def _graph():
    e = make_engine(validate_signals=True, state_timeout=0)
    e.start()
    T.create_task(e, "root", {"description": "a goal", "accepted_risks": _RISK,
                              "criteria": [{"name": "g", "description": "G holds"}]},
                  assignee="agent")
    T.create_task(e, "A", {"description": "producer",
                           "criteria": [{"name": "a", "description": "A holds"}]},
                  assignee="agent", parent_id="root")
    T.create_task(e, "B", {"description": "consumer",
                           "criteria": [{"name": "b", "description": "B holds"}]},
                  assignee="agent", parent_id="root")
    T.map_criterion(e, "root", "A", "g")
    T.map_criterion(e, "root", "B", "g")
    return e


def _delivered(e, node="B"):
    T.signal(e, node, "ACCEPT", "agent")
    T.signal(e, node, "DELIVER", "agent", result="something")


def test_a_node_left_holding_only_glue_cannot_be_passed():
    e = _graph()
    T.add_dependency(e, "A", "B")
    T.edit_criteria(e, "B", [])                       # the contract is wiped; `dep__A` survives
    assert [c.name for c in e.get_task("B").spec.criteria] == ["dep__A"], \
        "the setup no longer produces the shape under test — re-derive it before trusting the rest"
    _delivered(e)

    out = T.record_verdict(e, "B", "PASS", reviewer="stranger", observed={})
    assert out.get("recorded") is False, \
        "a PASS was recorded over a contract that asks for nothing — the empty requirement met " \
        "itself, which is the rule's absence wearing its name"
    assert "obligation of its own" in out.get("error", ""), \
        "the refusal must name the CONTRACT as the defect; a verdict cannot repair one"
    assert e.get_task("B").state.name == "VALIDATING", "the node must not have closed"
    e.stop()


def test_a_pass_that_speaks_to_no_criterion_is_refused_at_the_record():
    """The second absence, reached directly: the engine is the one writer, and the battery it runs
    must not be switchable off by having nothing to say."""
    e = _graph()
    _delivered(e)
    with pytest.raises(ValueError, match="says nothing about any of its"):
        e.record_exec_verdict("B", "PASS", [], "stranger", per_criterion=[])
    with pytest.raises(ValueError, match="says nothing about any of its"):
        e.record_exec_verdict("B", "PASS", [], "stranger", per_criterion=None)
    e.stop()


def test_honest_work_still_records():
    """The control. A PASS that says what it observed goes in, and a FAIL is not asked for a line
    per conjunct — Inv-3 asks it for the red set, and tightening that would refuse honest work."""
    e = _graph()
    _delivered(e)
    ok = T.record_verdict(e, "B", "PASS", reviewer="a-reviewer",
                          observed={"b": "ran `pytest -k b`: 3 passed, exit 0"})
    assert ok.get("recorded") is True, f"an observed PASS must still be recordable: {ok}"

    e2 = _graph()
    _delivered(e2, "A")
    bad = T.record_verdict(e2, "A", "FAIL", reviewer="a-reviewer", failed_criteria=["a"],
                           observed={"a": "ran it: AssertionError on the first case"})
    assert bad.get("recorded") is True, f"an honest FAIL must still be recordable: {bad}"
    e.stop()
    e2.stop()
