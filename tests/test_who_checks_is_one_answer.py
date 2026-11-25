"""Who checks a node the person issues is one answer: `get_task`'s checker names the party the gate and the verdict read
(`Engine.appointee`, his appointment or its default) — a page reading the checker shows who really decides."""
from __future__ import annotations

import pytest

import gfso.tools as T
import gfso.tools_llm as TL
from gfso.core.types import TaskId
from gfso.delegate import ensure_dispatcher
from gfso.signin import PAGE
from tests.support import REGISTER, a_repository, criterion, make_engine
from tests.test_a_named_party_checks_a_seam import _call

SEAM = "root.s"


@pytest.fixture(autouse=True)
def _home(tmp_path, monkeypatch):
    monkeypatch.setenv("GFSO_AGENTS_PATH", str(tmp_path / "agents.json"))
    monkeypatch.setenv("GFSO_L2_GATE", "0")
    monkeypatch.delenv("GFSO_VALIDATE_INTERNAL", raising=False)


def _his_seam(tmp_path, holder, validator):
    """His root, a seam he issues from his page to `holder` (`bob` is on no roster: a human; `eng` a registered agent)."""
    a_repository(tmp_path)
    e = make_engine(validate_signals=True, state_timeout=0)
    e.start()
    e.project_name = "p"
    if validator:
        assert not TL.register_agent(e, "p-val", "llm-validator", workdir=str(tmp_path)).get("refused")
        ensure_dispatcher(e).stop()
    e.workforce.publish_roster({**e.workforce.roster(), "eng": "llm-executor", "rev": "external"})
    _call(PAGE, "create_task", e, "root", {"description": "g", "criteria": [criterion("g")]}, assignee="user")
    covers = [c.name for c in e.graph.get_task(TaskId("root")).spec.criteria]
    _call(PAGE, "decompose", e, "root", [{"task_id": SEAM, "assignee": holder, "covers": covers,
                                          "spec": {"description": "d", "criteria": [criterion("d")]}}],
          accepted_risks=REGISTER)
    e.wait_idle()
    return e


@pytest.mark.parametrize("holder", ["bob", "eng"])
@pytest.mark.parametrize("validator", [True, False])
@pytest.mark.parametrize("appointed", [None, "self", "validator", "rev"])
def test_the_checker_said_is_the_one_the_gate_reads(tmp_path, holder, validator, appointed):
    e = _his_seam(tmp_path, holder, validator)
    if appointed is not None:
        out = _call(PAGE, "set_checker", e, SEAM, appointed, agent="user")
        assert out.get("checker") == appointed, out
    said = T.get_task(e, SEAM)["checker"]
    assert said == e.appointee(TaskId(SEAM)), (said, e.appointee(TaskId(SEAM)))
