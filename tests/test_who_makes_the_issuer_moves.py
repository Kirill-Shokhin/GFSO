"""Who makes a node's issuer moves is ONE answer (ortho audit, D-F9).

Four places answered it four ways — the dispatcher resolving blocks, the machine issuer, the holder's own plan moves,
the holder signing — and they differed exactly where nothing named the difference: no mode set, and the standing
agent with a role registered under its own id. `validation.party_kind` is the owner; this pins its table.
"""
from __future__ import annotations

import pytest

import gfso.tools as T
from gfso.core.types import AgentId, Mode, TaskId
from gfso.engine.validation import party_kind
from tests.support import REGISTER, criterion, make_engine


@pytest.fixture
def e():
    eng = make_engine()
    eng.start()
    T.create_task(eng, "root", {"description": "goal", "criteria": [criterion("g", "G")], "accepted_risks": REGISTER},
                  assignee="agent")
    yield eng
    eng.stop()


@pytest.mark.parametrize("mode, kind", [(None, "legacy"), (Mode.SOLO, "holder"), (Mode.SEMI, "holder"),
                                        (Mode.AUTO, "machine")])
def test_the_standing_agent_holds_by_the_mode(e, mode, kind):
    if mode is not None:
        e.set_mode(mode, None, AgentId("agent"))
    assert e.issuer_kind(TaskId("root")) == kind
    assert e.holder_signs(TaskId("root")) is (kind == "holder")


def test_a_role_under_the_users_own_id_does_not_make_it_a_machine(e):
    e.set_mode(Mode.SEMI, None, AgentId("agent"))
    assert e.issuer_kind(TaskId("root"), {"agent": "llm-validator"}) == "holder"


def test_anyone_else_is_a_machine_only_when_registered(e):
    assert party_kind(e.graph, "someone") == "person"
    assert party_kind(e.graph, "exec-1", {"exec-1": "llm-executor"}) == "machine"
