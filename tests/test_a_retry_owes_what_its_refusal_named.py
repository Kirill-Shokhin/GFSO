"""A retry owes every behaviour the refused report on the same delivery named under a criterion: naming fewer decides
nothing (§2.3 — which behaviours a criterion's words state does not shrink between two readings of one delivery). A
second report that simply dropped «stable under ties» passed where the first was refused over it (critic over f73c2c2).
And at the lapse the issuer is told such a gap — the validator's word `pass`, the behaviour unobserved — not an empty
list."""
import pytest

import gfso.tools as T
from gfso.core.protocol.accounting import refused_why
from gfso.core.types import TaskId
from tests.support import DENIAL_ENTRY, UNMODELLED_FAULT, make_engine

_C = "sorts"
_RISK = [{"item": UNMODELLED_FAULT.item, "predictability": "EXTRAORDINARY", "justification": "no precedent",
          "invalidation_condition": "one occurs", "p": 0.01, "impact": "x"}, DENIAL_ENTRY]
_ASC, _STABLE = "sorts ascending", "stable under ties"


def _node(monkeypatch):
    monkeypatch.setenv("GFSO_L2_GATE", "0")
    e = make_engine()
    e.start()
    T.create_task(e, "root", {"description": "sort", "accepted_risks": _RISK, "criteria": [
        {"name": _C, "description": "sorts ascending and is stable under ties",
         "check": [{"command": "python -c \"print(sorted([2, 1]))\"", "expect": "[1, 2]", "behaviour": _ASC}]}]},
                  assignee="me")
    T.signal(e, "root", "ACCEPT", "me")
    T.signal(e, "root", "DELIVER", "me", result="built")
    e.wait_idle()
    return e


def _entry(*behaviours):
    return {"criterion": _C, "verdict": "pass", "evidence": "printed [1, 2]", "behaviours": list(behaviours),
            "probe": [{"command": "python -c \"print(sorted([2, 1]))\"", "expect": "[1, 2]", "behaviour": _ASC}],
            "divergences": []}


def _record(e, entry):
    return e.record_exec_verdict(TaskId("root"), "PASS", [], "validator", per_criterion=[entry], require_probe=True,
                                 tools_used={"Bash": 1})


def test_a_retry_that_names_fewer_behaviours_decides_nothing(monkeypatch):
    e = _node(monkeypatch)
    with pytest.raises(ValueError) as first:
        _record(e, _entry(_ASC, _STABLE))
    e.record_rejected_report(TaskId("root"), str(first.value), [_entry(_ASC, _STABLE)])
    with pytest.raises(ValueError, match="stable under ties"):
        _record(e, _entry(_ASC))
    e.stop()


def test_control_without_a_refusal_before_it_one_named_behaviour_observed_passes(monkeypatch):
    e = _node(monkeypatch)
    assert str(_record(e, _entry(_ASC))["verdict"]).upper().endswith("PASS")
    e.stop()


def test_the_lapse_names_a_pass_whose_behaviour_no_probe_observed():
    why = refused_why([_entry(_ASC, _STABLE)])
    assert why and _STABLE in why[0] and "undecided" in why[0], why
