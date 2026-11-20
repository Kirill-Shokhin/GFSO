"""Who makes a node's issuer moves is ONE answer (ortho audit, D-F9).

Four places answered it four ways — the dispatcher resolving blocks, the machine issuer, the holder's own plan moves,
the holder signing — and they differed exactly where nothing named the difference: no mode set, and the standing
agent with a role registered under its own id. `validation.party_kind` is the owner; this pins its table.
"""
from __future__ import annotations

import pytest

import gfso.tools as T
from gfso import issuer as I
from gfso.core.types import AgentId, Mode, TaskId
from gfso.delegate import Dispatcher
from gfso.engine.validation import party_kind
from gfso.roster import AgentRegistry
from tests.support import REGISTER, criterion, make_engine


@pytest.fixture
def e():
    eng = make_engine()
    eng.start()
    T.create_task(eng, "root", {"description": "goal", "criteria": [criterion("g", "G")], "accepted_risks": REGISTER},
                  assignee="user")
    yield eng
    eng.stop()


@pytest.mark.parametrize("mode, kind", [(None, "person"), (Mode.SOLO, "holder"), (Mode.SEMI, "holder"),
                                        (Mode.AUTO, "machine")])
def test_the_standing_agent_holds_by_the_mode(e, mode, kind):
    if mode is not None:
        e.set_mode(mode, None, AgentId("user"))
    assert e.issuer_kind(TaskId("root")) == kind
    assert e.holder_signs(TaskId("root")) is (kind == "holder")


def test_a_role_under_the_users_own_id_does_not_make_it_a_machine(e):
    e.set_mode(Mode.SEMI, None, AgentId("user"))
    assert e.issuer_kind(TaskId("root"), {"user": "llm-validator"}) == "holder"


def test_with_no_mode_the_system_makes_none_of_the_persons_issuer_moves(tmp_path):
    """§10.1: Del names the role's holder. With no mode the person issues his nodes and the system holds no role there:
    it answers none of his disputes, resolves none of his blocks and signs none of his verdicts — his agent moves only
    when he writes (USING_GFSO). A machine holding a role still moves for it."""
    agents = AgentRegistry(path=str(tmp_path / "agents.json"))
    agents.register("exec-1", "llm-executor", workdir=str(tmp_path))
    e = make_engine()
    e.start()
    T.create_task(e, "given", {"description": "part", "criteria": [criterion("k", "K")], "accepted_risks": REGISTER},
                  assignee="exec-1", agent="user")
    d = Dispatcher(e, agents, poll=30, runner=lambda *a, **k: None, validator_runner=lambda *a, **k: None)
    kid = TaskId("given")
    assert str(e.graph.issuer_of(kid)) == "user"
    assert I.system_mover(e, agents.list(), kid, "dispute") is None, "the system answered the person's dispute"
    assert not d._resolves_blocks_for(kid), "the system resolved the person's block"
    assert not d._issuer_is_automated(kid), "the system signed the person's verdict"
    e.stop()


def test_anyone_else_is_a_machine_only_when_registered(e):
    assert party_kind(e.graph, "someone") == "person"
    assert party_kind(e.graph, "exec-1", {"exec-1": "llm-executor"}) == "machine"
