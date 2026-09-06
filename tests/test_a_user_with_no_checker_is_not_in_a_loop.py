"""Without a checker, the product told the user to run the verb that had just answered.

The Level-2 execution gate is ON by default, and it is fail-closed for a good reason: no verdict is
never read as clean. But every way out was addressed to someone who already has a checker. Probed
2026-09-05 with the Claude CLI off the PATH -- i.e. the state of a fresh install, and of anyone using
the graph without a model:

    review_decomposition(site)  ->  gate_passed: true, open_count: 0, execution_admitted: false
    signal site.r ACCEPT        ->  "Run review_decomposition(site) first"

Zero findings, execution refused, and the fix offered is the verb that just ran. Nothing anywhere
named `GFSO_L2_GATE=0` -- the canon's own EXPLORE branch (§13.5), where the plan's verification is
bought with contact instead of with the checker. The engine's own comment beside the gate has said so
since the gate was written; it never reached the person reading the refusal.

`open_count: 0` was the second half: a number that cannot tell "none" from "not measured". The branch
directly above it in the same function fixes exactly that for the other case.
"""
from __future__ import annotations

import pytest

import gfso.tools as T
import gfso.tools_llm as TL
from tests.support import UNMODELLED_FAULT, make_engine

_RISK = [{"item": UNMODELLED_FAULT.item, "predictability": "EXTRAORDINARY"}]


@pytest.fixture(autouse=True)
def _the_gate_is_on(monkeypatch):
    monkeypatch.setenv("GFSO_L2_GATE", "1")
    monkeypatch.setenv("PATH", r"C:\Windows\System32")     # …no `claude`: a fresh install


def _a_plan():
    e = make_engine()
    e.start()
    T.create_task(e, "site", {"description": "a static site generator",
                              "criteria": [{"name": "r", "description": "R"}],
                              "accepted_risks": _RISK}, assignee="me")
    T.decompose(e, "site", [{"task_id": "site.r",
                             "spec": {"description": "renderer",
                                      "criteria": [{"name": "md", "description": "M"}]},
                             "assignee": "me", "covers": ["r"]}])
    e.wait_idle()
    return e


def test_a_review_that_judged_nothing_does_not_report_zero_findings():
    e = _a_plan()
    out = TL.TOOLS["review_decomposition"](e, "site")
    assert out["execution_admitted"] is False
    assert out["open_count"] is None, "zero findings and execution refused, with no reason given"
    assert "GFSO_L2_GATE=0" in out["open_count_note"]
    e.stop()


def test_the_refusal_names_the_way_out_once_the_advice_has_been_taken():
    e = _a_plan()
    TL.TOOLS["review_decomposition"](e, "site")
    err = str(T.signal(e, "site.r", "ACCEPT", "me").get("error") or "")
    assert "GFSO_L2_GATE=0" in err and "§13.5" in err
    assert "running it again changes nothing by itself" in err
    e.stop()


def test_before_any_review_the_advice_is_still_to_run_it():
    """The control. "Run the review" is the right answer when no review has been run, and a rule that
    printed the escape hatch every time would teach people to turn the gate off first."""
    e = _a_plan()
    err = str(T.signal(e, "site.r", "ACCEPT", "me").get("error") or "")
    assert "Run review_decomposition(site) first" in err
    assert "GFSO_L2_GATE=0" not in err
    e.stop()


def test_the_explore_branch_actually_opens_the_gate(monkeypatch):
    """And it must be a real way on, not a sentence: the canon's EXPLORE branch is a supported
    deployment, so a plan that is structurally clean executes under it."""
    monkeypatch.setenv("GFSO_L2_GATE", "0")
    e = _a_plan()
    assert T.signal(e, "site.r", "ACCEPT", "me").get("accepted") is True
    e.stop()
