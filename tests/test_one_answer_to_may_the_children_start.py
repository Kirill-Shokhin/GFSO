"""Three surfaces answered "may the children start?" three different ways, and two of them lied.

`review_decomposition` had the rule whole: no Level-0 holes, and either the gate is off or the
Level-2 findings are discharged. `get_task` read only the Level-2 findings — no structural level,
no gate flag. `get_review` wrote `t.verified and not open_findings`, and `not None` is TRUE, so ⊥ —
the state whose own doctrine in this codebase is "no verdict is never read as clean" — came back as
ADMITTED.

Probed 2026-09-07 with the gate on: a node whose checker returned an unreadable reply answered
`execution_admitted: True` at both reading doors while the engine, in the same second, refused its
child's ACCEPT and explained exactly why. The false green on the Level-2 panel — the class this
product catches for other people — on its own surface, at the door a person watches.

One owner now, on the engine, because that is where the refusal is decided. The two facts the tests
below keep apart: an unreadable review is not a discharged one (⊥ ≠ clean), and with the gate off
the children genuinely MAY start — a deployment taking the canon's EXPLORE branch (§13.5) is not a
graph with a bad plan, and a surface that says otherwise disagrees with its own machine.
"""
from __future__ import annotations

import json

import pytest

from gfso import tools as T
from gfso import tools_llm as TL
from gfso.core.types import TaskId
from tests.support import UNMODELLED_FAULT, make_engine

_RISK = [{"item": UNMODELLED_FAULT.item, "predictability": "EXTRAORDINARY"}]


def _reviewed(e, record: dict):
    """A node carrying a stored review of THIS version of its plan — the shape the checker writes."""
    T.create_task(e, "root", {"description": "a goal", "accepted_risks": _RISK,
                              "criteria": [{"name": "c1", "description": "C1 holds"}]},
                  assignee="pm")
    T.create_task(e, "kid", {"description": "the work",
                             "criteria": [{"name": "k", "description": "K holds"}]},
                  assignee="worker", parent_id="root")
    T.map_criterion(e, "root", "kid", "c1")
    e._graph._storage.store_critique(TaskId("root"), json.dumps(record))
    node = e.get_task(TaskId("root"))
    node.verified = True
    e._graph.save_task(node)
    return e


#: what the checker leaves when its reply could not be read — an INCOMPLETE verdict, not a clean one
_UNREADABLE = {"node_id": "root", "gate_passed": True, "semantic_covered": None,
               "criteria_verdicts": [], "conflicts": [], "undecided_obligations": []}
#: …and what it leaves when it ran and found nothing to say against the plan
_CLEAN = {**_UNREADABLE, "semantic_covered": True}


def test_an_unreadable_review_does_not_admit_execution(monkeypatch):
    monkeypatch.setenv("GFSO_L2_GATE", "1")
    e = make_engine(validate_signals=True, state_timeout=0)
    e.start()
    _reviewed(e, _UNREADABLE)
    assert e.open_l2_findings(TaskId("root")) is None, \
        "the probe must be looking at ⊥ — no readable verdict — and not at a review with findings"
    assert e.execution_admitted(TaskId("root")) is False
    assert T.get_review(e, "root")["execution_admitted"] is False, \
        "`not None` is true, and that is how ⊥ came back as admitted"
    assert T.get_task(e, "root")["execution_admitted"] is False
    refused = T.signal(e, "kid", "ACCEPT", "worker")
    assert refused.get("accepted") is False, \
        "the surfaces and the machine must not disagree about one node in the same second"
    e.stop()


def test_a_clean_review_admits_it(monkeypatch):
    """The control. A rule that says no to everything is not a rule."""
    monkeypatch.setenv("GFSO_L2_GATE", "1")
    e = make_engine(validate_signals=True, state_timeout=0)
    e.start()
    _reviewed(e, _CLEAN)
    assert e.execution_admitted(TaskId("root")) is True
    assert T.get_review(e, "root")["execution_admitted"] is True
    assert T.get_task(e, "root")["execution_admitted"] is True
    assert T.signal(e, "kid", "ACCEPT", "worker").get("accepted") is True
    e.stop()


@pytest.mark.parametrize("record,name", [(_UNREADABLE, "unreadable"), (_CLEAN, "clean")])
def test_with_the_gate_off_the_children_may_start_either_way(monkeypatch, record, name):
    """The EXPLORE branch (§13.5) is a deployment decision, not a skipped step: the machine admits
    the children, so every surface says so. Saying otherwise is the same disagreement, mirrored."""
    monkeypatch.setenv("GFSO_L2_GATE", "0")
    e = make_engine(validate_signals=True, state_timeout=0)
    e.start()
    _reviewed(e, record)
    assert e.execution_admitted(TaskId("root")) is True, name
    assert T.get_review(e, "root")["execution_admitted"] is True, name
    assert T.get_task(e, "root")["execution_admitted"] is True, name
    assert T.signal(e, "kid", "ACCEPT", "worker").get("accepted") is True, name
    # …and the unanswered review is still VISIBLE. What the gate decides is whether it BLOCKS.
    if record is _UNREADABLE:
        assert T.get_review(e, "root")["open_findings"] is None
    e.stop()
