""""The Level-2 obligations are frozen at first reading" — what two doors were actually seeing.

Wave 26 (2026-09-06), reported independently by the HTTP and fresh-install doors: *fixing the plan
does not close the findings, only `dispute_finding` does — which contradicts both the docs and the
text of the refusal itself.*

Probed here rather than believed: a fix DOES land — every edit to the plan (the parent's own
criteria, a child's criteria, a new mapped child) stales the review, and `open_l2_findings` goes from
`['c1']` to `None`. What it does NOT do is discharge the finding: `None` is "no current verdict",
which is fail-closed, so execution stays shut until `review_decomposition` speaks again. The two
exits are real and asymmetric — one discharges in place, the other retires the verdict and costs a
re-run — and every surface promised them as equals.

So this pins the mechanism (the asymmetry is deliberate: a lowered criterion and an added coverage
look alike until the checker reads them) and pins that the surfaces now SAY it.
"""
from __future__ import annotations

import json

import pytest

from gfso import tools as T
from gfso.core.types import TaskId
from tests.support import UNMODELLED_FAULT, make_engine

@pytest.fixture(autouse=True)
def _l2_gate_on(monkeypatch):
    """The suite default is the EXPLORE opt-out (`conftest`); this module is ABOUT the gate."""
    monkeypatch.setenv("GFSO_L2_GATE", "1")


_RISKS = [{"item": UNMODELLED_FAULT.item, "predictability": "EXTRAORDINARY"}]
_FINDING = {"semantic_covered": False, "gate_passed": True,
            "criteria_verdicts": [{"criterion": "c1", "verdict": "insufficient",
                                   "why": "the child does not carry c1"}],
            "conflicts": [], "model": "probe", "ts": "now"}


def _reviewed_plan():
    """A root with one mapped child and a CURRENT Level-2 verdict naming one open finding."""
    e = make_engine()
    e.start()
    T.create_task(e, "root", {"description": "r", "criteria": [{"name": "c1", "description": "C1"}],
                              "accepted_risks": _RISKS}, assignee="agent")
    T.create_task(e, "kid", {"description": "k", "criteria": [{"name": "k1", "description": "K1"}]},
                  assignee="agent", parent_id="root")
    T.map_criterion(e, "root", "kid", "c1")
    e.wait_idle()
    e._graph._storage.store_critique(TaskId("root"), json.dumps(_FINDING))
    node = e.get_task(TaskId("root"))
    node.verified = True
    e._graph.save_task(node)
    assert e.open_l2_findings(TaskId("root")) == ["c1"]
    return e


def test_fixing_the_parents_own_criteria_retires_the_verdict():
    e = _reviewed_plan()

    assert not T.edit_criteria(e, "root", [{"name": "c1",
                                            "description": "C1, narrowed to what kid delivers"}]
                               ).get("error")
    e.wait_idle()

    assert e.get_task(TaskId("root")).verified is False, "the fix staled the review"
    assert e.open_l2_findings(TaskId("root")) is None, (
        "NOT `[]` — the finding is not discharged, the verdict is retired: no current verdict is "
        "fail-closed, which is the whole reason a fix cannot silently admit execution")
    e.stop()


def test_fixing_a_child_or_adding_one_retires_it_too():
    """The other two shapes of the same fix — neither was frozen, both retire."""
    e = _reviewed_plan()
    assert not T.edit_criteria(e, "kid", [{"name": "k1", "description": "K1 and it carries C1"}]
                               ).get("error")
    e.wait_idle()
    assert e.open_l2_findings(TaskId("root")) is None
    e.stop()

    e = _reviewed_plan()
    T.create_task(e, "kid2", {"description": "k2", "criteria": [{"name": "k2", "description": "K2"}]},
                  assignee="agent", parent_id="root")
    T.map_criterion(e, "root", "kid2", "c1")
    e.wait_idle()
    assert e.open_l2_findings(TaskId("root")) is None
    e.stop()


def test_the_refusal_says_the_fix_takes_two_steps():
    """What the doors were owed: the exits are not equals, and the live refusal now says so."""
    e = _reviewed_plan()

    refused = T.signal(e, "kid", "ACCEPT", "agent")

    assert refused["accepted"] is False
    said = refused["error"]
    assert "re-run" in said and "RETIRES this verdict" in said, said
    assert "dispute_finding" in said, "…and the exit that DOES discharge is still named"
    assert T.dispute_finding.__doc__ and "retires the whole verdict" in T.dispute_finding.__doc__, (
        "the verb that IS the other exit must say what the first one costs")
    e.stop()
