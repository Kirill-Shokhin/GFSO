"""Three doors, in one wave, were told to wait for a validator that could never run.

`validated_by_instrument` answers "will an instrument validate this delivery without being asked", and the
reply a DELIVER carries is built on it: *"an independent validator is bound to this node and validates
this delivery by itself — wait for it … Recording your own verdict here would race it."*

It was asking a different question: is ANY validator on the roster. The roster is one server-wide
file, so a project that had registered nothing inherited the answer from twenty-five roles belonging
to seventeen other projects. Wave 26 (2026-09-06) reported it from the HTTP door and from a fresh
install independently, both as their worst moment: the user waits forever for a validator that will never
come, and the same sentence warns them off `validate_result`, which is the thing that would have
worked. The reply's own `next` field said the opposite in the same object.

The scope rule already existed one layer over, in `validator_for`: this project's roles, then UNSCOPED
ones (shared by design), never another project's. This says it in the place the promise is made.
"""
from __future__ import annotations

import pytest

import gfso.tools as T
from tests.support import criterion, make_engine, REGISTER

_RISK = REGISTER


@pytest.fixture(autouse=True)
def _no_plan_gate(monkeypatch):
    monkeypatch.setenv("GFSO_L2_GATE", "0")


def _delivered_internal_node(whose: dict):
    """An INTERNAL node (Del == its parent's) a machine issued, delivered while `whose` is the published roster. A
    machine's, since only there is the instrument's verdict the signal: a person signs his own (§10.1)."""
    e = make_engine()
    e.start()
    e.project_name = "mine"
    e.workforce.publish_roster({"exec-1": "llm-executor"})
    T.create_task(e, "p", {"description": "parent",
                           "criteria": [criterion("g", "G")],
                           "accepted_risks": _RISK}, assignee="exec-1")
    T.decompose(e, "p", [{"task_id": "k", "spec": {"description": "kid",
                           "criteria": [criterion("c", "C")]}, "assignee": "exec-1", "covers": ["g"]}],
                accepted_risks=REGISTER, agent="exec-1")
    T.signal(e, "k", "ACCEPT", "exec-1")
    e._graph.authorized_validators = set(whose)
    e.workforce.publish_validator_projects(whose)
    said = T.signal(e, "k", "DELIVER", "exec-1", result="v1").get("awaiting_verdict") or ""
    e.stop()
    return said


def test_another_projects_validator_is_not_a_promise():
    said = _delivered_internal_node({"other-val": "someone-elses-project"})
    assert "an independent validator is bound" not in said, said
    assert "self-verify" in said, "the honest instruction for an internal node is what belongs here"


def test_this_projects_validator_is():
    """The control: without it the rule above is satisfied by never promising anything."""
    assert "an independent validator is bound" in _delivered_internal_node({"my-val": "mine"})


def test_an_unscoped_validator_still_is():
    """Unscoped roles are shared BY DESIGN — the measurement arm registers through the library and
    carries no project. Excluding them once ended a run in `validation_stalled`."""
    assert "an independent validator is bound" in _delivered_internal_node({"shared-val": None})


def test_nothing_published_yet_falls_back_to_what_is_known():
    """A graph nobody has dispatched over has an empty map, which is ⊥ about ownership rather than a
    statement that no instrument exists — so the older, coarser answer stands there."""
    e = make_engine()
    e.start()
    e.project_name = "mine"
    e._graph.authorized_validators = {"val-1"}
    assert e.workforce.has_an_instrument() is True
    e.workforce.publish_validator_projects({"val-1": "somebody-else"})
    assert e.workforce.has_an_instrument() is False
    e.stop()
