"""The Level-0 gate was a precondition on one instant, not a property of the run.

§13.4: "a decomposition that fails the Syntactic level is not admitted to execution." That gate fired
in exactly one place -- a CHILD's ACCEPT, read against its PARENT's plan. Break the plan afterwards
and nothing re-read it; and a ROOT, having no parent, was gated by it nowhere at any point in its life.

Thm 1 (§11.1) makes a parent's PASS the conjunction over its children, and that conjunction
establishes the PARENT only because the children jointly cover its criteria -- which is what L0
checks. So the letter held while the purpose did not, and two ordinary supported calls demonstrate it
(audited and probed 2026-09-05, F2):

  * CANCEL a criterion's only coverer after the children have started. `get_active_children` correctly
    drops an ABANDONED child, CHECK-1 goes red, and the root reached DONE/PASS with one criterion
    covered by nothing at all.
  * `edit_criteria` an uncovered criterion in. Inv-1 returns the root to OFFERED, the root's own
    re-ACCEPT is gated by nothing, and it closes the same way.

`list_holes` showed the hole in both cases, the whole time. Surfacing is not enforcement.
"""
from __future__ import annotations

import pytest

import gfso.tools as T
from tests.support import UNMODELLED_FAULT, make_engine

_RISK = [{"item": UNMODELLED_FAULT.item, "predictability": "EXTRAORDINARY"}]


@pytest.fixture(autouse=True)
def _no_plan_gate(monkeypatch):
    monkeypatch.setenv("GFSO_L2_GATE", "0")


def _two_children():
    e = make_engine(validate_signals=True, state_timeout=0)
    e.start()
    T.create_task(e, "r", {"description": "goal",
                           "criteria": [{"name": "c1", "description": "C1"},
                                        {"name": "c2", "description": "C2"}],
                           "accepted_risks": _RISK}, assignee="me")
    T.decompose(e, "r", [
        {"task_id": "r.a", "spec": {"description": "a",
                                    "criteria": [{"name": "k", "description": "K"}]},
         "assignee": "w", "covers": ["c1"]},
        {"task_id": "r.b", "spec": {"description": "b",
                                    "criteria": [{"name": "k", "description": "K"}]},
         "assignee": "w", "covers": ["c2"]}])
    e.wait_idle()
    for n in ("r.a", "r.b"):
        T.signal(e, n, "ACCEPT", "w")          # …both admitted while the plan is clean
    return e


def _pass(e, node, signer, observed):
    e.record_reviewer_verdict(node, "PASS", [], reviewer=signer, observed=observed)
    return T.signal(e, node, "PASS", "me" if node != "r" else "me")


def _finish(e, live):
    for n in live:
        T.signal(e, n, "DELIVER", "w", result="x")
        _pass(e, n, "me", {"k": "ran it, green"})
    e.wait_idle()
    T.signal(e, "r", "ACCEPT", "me")
    T.signal(e, "r", "DELIVER", "me", result="aggregate")
    return _pass(e, "r", "judge", {c.name: "ok" for c in e.get_task("r").spec.criteria})


def test_a_cancelled_coverer_stops_the_aggregate():
    e = _two_children()
    T.signal(e, "r.b", "CANCEL", "me")
    T.signal(e, "r.b", "CONFIRM_CANCEL", "w")
    e.wait_idle()

    out = _finish(e, ["r.a"])

    assert out.get("accepted") is False, "c2 was covered by nothing and the root closed anyway"
    assert e.get_state("r").name == "VALIDATING"
    assert "Syntactic level NOW" in (out.get("error") or "")
    assert T.list_holes(e, "r"), "the hole the gate refused on must also be listable"
    e.stop()


def test_an_uncovered_criterion_added_later_stops_it_too():
    """The same class with no CANCEL, and on the node the old gate could never see: a root."""
    e = _two_children()
    _ = _finish  # …the edit happens after the children pass, below
    for n in ("r.a", "r.b"):
        T.signal(e, n, "DELIVER", "w", result="x")
        _pass(e, n, "me", {"k": "ran it, green"})
    e.wait_idle()
    T.edit_criteria(e, "r", [{"name": "c1", "description": "C1"},
                             {"name": "c2", "description": "C2"},
                             {"name": "c3", "description": "C3, covered by nobody"}], "me")
    e.wait_idle()
    T.signal(e, "r", "ACCEPT", "me")
    T.signal(e, "r", "DELIVER", "me", result="aggregate")
    out = _pass(e, "r", "judge", {c.name: "ok" for c in e.get_task("r").spec.criteria})

    assert out.get("accepted") is False
    assert e.get_state("r").name == "VALIDATING"
    e.stop()


def test_a_plan_that_stayed_whole_still_closes():
    """The control, and it is the one that matters: a rule that refuses every aggregate would pass
    both tests above and destroy the product."""
    e = _two_children()
    out = _finish(e, ["r.a", "r.b"])
    assert out.get("accepted") is True, out.get("error")
    assert e.get_state("r").name == "DONE"
    e.stop()


def test_a_childless_node_has_no_plan_to_read():
    """`_l0_holes` is empty where there is no decomposition, so a leaf is untouched by this rule --
    otherwise every leaf in the graph would have acquired a coverage obligation it cannot have."""
    e = make_engine(validate_signals=True, state_timeout=0)
    e.start()
    T.create_task(e, "leaf", {"description": "the work",
                              "criteria": [{"name": "k", "description": "K"}],
                              "accepted_risks": _RISK}, assignee="w")
    T.signal(e, "leaf", "ACCEPT", "w")
    T.signal(e, "leaf", "DELIVER", "w", result="did it")
    e.record_reviewer_verdict("leaf", "PASS", [], reviewer="me", observed={"k": "ran it, green"})
    assert T.signal(e, "leaf", "PASS", "w").get("accepted") is True
    assert e.get_state("leaf").name == "DONE"
    e.stop()
