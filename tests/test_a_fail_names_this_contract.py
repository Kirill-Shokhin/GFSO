"""Inv-3 counted the failed criteria and never asked what they were.

`validate_fail_has_criteria` was `len(signal_data.failed_criteria) > 0`, so any string satisfied it.
A FAIL naming "the tests", or a typo of a real criterion, was admitted: the node moved to REWORKING,
one of its bounded iterations (§14.3) was spent, and the executor was handed a list of obligations
that do not exist and cannot be fixed.

The identical rule was already binding one file over, for the machine validator's report -- *"'X' is
not a criterion of this node -- the contract's criteria are the entire obligation"*. So it was one
rule, enforced for the instrument and advisory for the person (audited 2026-09-05, F5).

AND THIS IS THE TYPE OF THE FIELD, NOT ENFORCEMENT ADDED ON TOP -- checked deliberately, because the
audit that found this also found the opposite defect (F4: a rule the canon gives no CHECK for had
acquired the authority to refuse execution), and closing one by committing the other would be worse
than leaving both. The canon writes the signal as `FAIL(criteria[])`, "cite the failed criteria",
and §10 defines V(t) as the conjunction over t's OWN criteria -- so a false conjunct IS a criterion
of t, and a name outside the contract denotes nothing at all. The worked example (§14.3) fails a root
on `[c2, c3]`, its own two. Membership is what `failed_criteria` MEANS.
"""
from __future__ import annotations

import pytest

import gfso.tools as T
from gfso.core.protocol.invariants import fail_names_this_contract
from tests.support import UNMODELLED_FAULT, make_engine

_RISK = [{"item": UNMODELLED_FAULT.item, "predictability": "EXTRAORDINARY"}]


@pytest.fixture(autouse=True)
def _no_plan_gate(monkeypatch):
    monkeypatch.setenv("GFSO_L2_GATE", "0")


def _delivered():
    e = make_engine(validate_signals=True, state_timeout=0)
    e.start()
    T.create_task(e, "n", {"description": "the work",
                           "criteria": [{"name": "parses", "description": "P"},
                                        {"name": "matches", "description": "M"}],
                           "accepted_risks": _RISK}, assignee="worker")
    T.signal(e, "n", "ACCEPT", "worker")
    T.signal(e, "n", "DELIVER", "worker", result="did it")
    return e


def _fail(e, names):
    """The signal alone: Inv-3 is a rule about the FAIL PAYLOAD, checked before anything is judged.

    Signed by the node's ISSUER, which for a root is its own assignee. The first cut of this sent it
    as `judge` and every negative assertion here went green — on "judge is not issuer for n", a
    refusal that never reached the rule under test.
    """
    out = T.signal(e, "n", "FAIL", "worker", failed_criteria=list(names))
    assert "not issuer" not in str(out.get("error") or ""), "the probe never reached the rule"
    return out


def test_a_fail_naming_something_else_is_refused():
    e = _delivered()
    out = _fail(e, ["the tests"])
    assert out.get("accepted") is False, "rework was spent on an obligation that does not exist"
    assert "not criteria of this node" in str(out.get("error") or ""), out
    assert e.get_state("n").name == "VALIDATING"
    e.stop()


def test_the_refusal_prints_the_actual_contract():
    e = _delivered()
    err = str(_fail(e, ["parsse"]).get("error") or "")     # a typo of a real one
    assert "parses" in err and "matches" in err, err
    e.stop()


def test_a_fail_on_a_real_criterion_still_works():
    """The control. Without it the rule above is satisfied by a gate that refuses every FAIL."""
    e = _delivered()
    assert _fail(e, ["parses"]).get("accepted") is True
    assert e.get_state("n").name == "REWORKING"
    e.stop()


def test_one_real_name_does_not_carry_a_foreign_one():
    """A payload is refused if ANY name is outside the contract -- the same reading the instrument's
    report already gets. A partly-valid list would still send the executor after a phantom."""
    e = _delivered()
    assert _fail(e, ["parses", "the tests"]).get("accepted") is False
    e.stop()


def test_the_predicate_refuses_nothing_when_the_contract_is_unknown():
    """An empty contract is a different defect with a different owner (it is refused at the record),
    and a rule that is vacuously true at zero X must not become a rule that refuses everything."""
    assert fail_names_this_contract(["anything"], []) == []
    assert fail_names_this_contract(["a"], ["a", "b"]) == []
    assert fail_names_this_contract(["a", "z"], ["a", "b"]) == ["z"]
