"""A canon RULE with no canon CHECK acquired the authority to refuse execution, under another name.

§3.4 item (6) -- every child's deadline before its parent's -- is stated by the canon and given no
CHECK of its own. `formal/README.md` #6 says exactly that, and adds: *"any prose that credits it to
CHECK-3 is wrong about the canon"*. The rule was nevertheless appended to `CHECK-3:deadlines`' own
result, tagged only inside the details string.

`_EXEC_GATING_CHECKS` matches on the NAME. So the vertical rule gated execution, and the refusal cited
§13.4 for a rule §13.4 does not carry -- inside the very gate whose comment keeps CHECK-1c out because
"the gate is exactly the canon's level, in both directions" (audited 2026-09-05, F4).

The mechanism is the finding, not the rule: a name-prefix filter cannot say no to the next rule
someone writes into an existing result's details. This pins the split, in both directions.
"""
from __future__ import annotations

import pytest

import gfso.tools as T
from gfso.engine.validation import _EXEC_GATING_CHECKS
from tests.support import UNMODELLED_FAULT, make_engine

_RISK = [{"item": UNMODELLED_FAULT.item, "predictability": "EXTRAORDINARY"}]


@pytest.fixture(autouse=True)
def _no_plan_gate(monkeypatch):
    monkeypatch.setenv("GFSO_L2_GATE", "0")


def _plan(x_deadline, dep=False):
    """A root due 2026-10-01 with two children, one of which may be late or may produce out of order."""
    e = make_engine()
    e.start()
    T.create_task(e, "root", {"description": "goal",
                              "criteria": [{"name": "a", "description": "A"},
                                           {"name": "b", "description": "B"}],
                              "accepted_risks": _RISK}, assignee="me", deadline="2026-10-01")
    T.decompose(e, "root", [
        {"task_id": "root.x",
         "spec": {"description": "x", "criteria": [{"name": "x1", "description": "X"}]},
         "assignee": "me", "covers": ["a"], "deadline": x_deadline},
        {"task_id": "root.y",
         "spec": {"description": "y", "criteria": [{"name": "y1", "description": "Y"}]},
         "assignee": "me", "covers": ["b"], "deadline": "2026-09-05"}])
    if dep:
        T.add_dependency(e, "root.x", "root.y", glue="y reads x")
    e.wait_idle()
    return e


def _verdicts(e):
    return {c["check"]: c["verdict"] for c in T.get_checks(e, "root")}


def test_the_vertical_rule_is_said_and_refuses_nothing():
    e = _plan("2026-12-01")                              # the child outlives its parent
    assert _verdicts(e)["§3.4(6):vertical_deadlines"] == "unmet", "the violation went unsaid"
    assert T.signal(e, "root.x", "ACCEPT", "me").get("accepted") is True, (
        "a rule the canon gives no CHECK for refused execution")
    e.stop()


def test_the_horizontal_rule_still_gates():
    """The control. Without it, the test above passes on a gate that has stopped enforcing anything:
    CHECK-3 IS a canon row (§13.4) and a Dep whose producer is due after its consumer is a real L0
    failure."""
    e = _plan("2026-09-20", dep=True)
    assert _verdicts(e)["CHECK-3:deadlines"] == "unmet"
    assert T.signal(e, "root.x", "ACCEPT", "me").get("accepted") is False
    e.stop()


def test_the_two_rules_do_not_answer_for_each_other():
    e = _plan("2026-12-01")
    v = _verdicts(e)
    assert v["CHECK-3:deadlines"] in ("met", "met_vacuously"), (
        "CHECK-3 reported a violation that is not its row — `met_vacuously` is the same answer "
        "with the emptiness of its subject said out loud (there are no Dep edges in this plan)")
    assert v["§3.4(6):vertical_deadlines"] == "unmet"
    e.stop()


def test_no_rule_outside_the_canons_level_0_is_in_the_gate():
    """The mechanism, not the instance: the gate is a name filter, so the names are the boundary."""
    assert {p.rstrip(":") for p in _EXEC_GATING_CHECKS} == {
        "CHECK-1", "CHECK-1b", "CHECK-2", "CHECK-3", "CHECK-4", "CHECK-5", "CHECK-6"}
