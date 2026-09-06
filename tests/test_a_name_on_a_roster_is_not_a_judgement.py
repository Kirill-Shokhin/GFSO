"""Registering an id and then signing with it closed any seam, with no verdict on the record.

The seam gate stepped aside for anyone on the validator roster: *"an authorized instrument signing
directly IS the independent verdict ... its signature is the judgement, not an impression about one,
so it opens the gate without a second record."* Wave 23 narrowed that to exclude the node's own
executor, which was right and left the class open.

A signature is a judgement only where it cannot be typed. `source` is CALLER-SUPPLIED on two of the
three doors -- HTTP passes the body straight through, so does the CLI; only MCP derives identity from
the transport. And `register_agent` is an ordinary documented verb. So two ordinary calls closed a
root that had delivered "nothing was actually written": DONE/PASS, no verdict record, provenance
`none`, and q_V reporting 1.0 over a seam nothing had judged.

An id on a roster is a CLAIM about who is signing. The record is the evidence that judging happened,
and ⊥ is not a pass (§11.2) whoever's name is on it.
"""
from __future__ import annotations

import pytest

import gfso.tools as T
from tests.support import make_engine

_RISK = [{"item": "an unmodelled environment fault", "predictability": "EXTRAORDINARY"}]
_PROBE = [{"command": "pytest -q", "expect": "ok"}]


@pytest.fixture(autouse=True)
def _no_plan_gate(monkeypatch):
    monkeypatch.setenv("GFSO_L2_GATE", "0")


def _a_delivered_root():
    e = make_engine(validate_signals=True, state_timeout=0)
    e.start()
    T.create_task(e, "root", {"description": "a goal",
                              "criteria": [{"name": "c", "description": "C"}],
                              "accepted_risks": _RISK}, assignee="me")
    T.signal(e, "root", "ACCEPT", "me")
    T.signal(e, "root", "DELIVER", "me", result="nothing was actually written")
    e._graph.authorized_validators = {"ghost-val"}      # what `register_agent` publishes
    return e


def test_a_registered_id_that_never_ran_cannot_close_a_seam():
    e = _a_delivered_root()
    T.signal(e, "root", "PASS", "ghost-val")
    assert e.get_state("root").name == "VALIDATING"
    assert e.get_exec_verdict("root") is None, "closed on a signature with nothing behind it"
    e.stop()


def test_the_refusal_names_what_is_missing():
    e = _a_delivered_root()
    out = T.signal(e, "root", "PASS", "ghost-val")
    assert "independent verdict" in str(out.get("error") or out)
    e.stop()


def test_an_instrument_that_actually_judged_still_closes_it():
    """The control, and the reason this is a narrowing rather than a removal: every instrument path
    in the product records its verdict and then signs it, so the requirement is one it already met.
    Without this test the rule above would also be satisfied by a gate that admits nobody."""
    e = _a_delivered_root()
    e.record_exec_verdict("root", "PASS", [], "ghost-val",
                          per_criterion=[{"criterion": "c", "verdict": "pass",
                                          "evidence": "ran it", "behaviours": ["b"],
                                          "probe": list(_PROBE)}],
                          tools_used={"Bash": 1})
    T.signal(e, "root", "PASS", "ghost-val")
    assert e.get_state("root").name == "DONE"
    e.stop()
