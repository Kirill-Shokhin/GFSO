"""A project sets for itself what differs between projects of one server: the system's model, the Level-2 gate, the
deadline nobody typed — on the door that sets its mode, recorded with it.

They were the server's switches (GFSO_SYSTEM_MODEL read at import, GFSO_L2_GATE, GFSO_DEFAULT_DEADLINE_S), so two rows of
different models could not share a server and the harness restarted the one :8000 per row — under the page the author
watches and a neighbour's work (the author, 2026-10-25: «сервер один»).
"""
from datetime import datetime, timedelta

import pytest

from gfso import tools_llm as TL
from gfso.config import MODEL_DEFAULT
from gfso.core.types import AgentId, Mode
from gfso.core.graph.model import project_deadline_s
from gfso.engine.validation import l2_gate_on
from tests.support import criterion
from tests.test_the_mode_decides_who_holds_what import _engine
from gfso import tools as T


@pytest.fixture
def e():
    eng = _engine()
    yield eng
    eng.stop()


def test_unset_the_server_decides(e, monkeypatch):
    monkeypatch.setenv("GFSO_L2_GATE", "0")
    monkeypatch.setenv("GFSO_DEFAULT_DEADLINE_S", "123")
    assert e.system_model() == MODEL_DEFAULT and not l2_gate_on(e.graph) and project_deadline_s(e.graph) == 123


def test_the_projects_own_choice_holds_whatever_the_server_says(e, monkeypatch):
    monkeypatch.setenv("GFSO_L2_GATE", "1")
    monkeypatch.setenv("GFSO_DEFAULT_DEADLINE_S", "86400")
    rec = e.set_mode(Mode.AUTO, None, AgentId("agent"),
                     settings={"system_model": "claude-haiku-4-5", "l2_gate": "0", "deadline_s": 3600.0})
    assert rec["settings"]["system_model"] == "claude-haiku-4-5"
    assert e.system_model() == "claude-haiku-4-5" and not l2_gate_on(e.graph) and project_deadline_s(e.graph) == 3600
    assert l2_gate_on(), "the server's switch, read without a project, is untouched"
    T.TOOLS["create_task"](e, "root", {"description": "g", "criteria": [criterion("c", "C")]})
    e.wait_idle()
    dl = e.graph.get_task("root").deadline
    assert dl is not None and dl - datetime.now() < timedelta(seconds=3700), "the project's deadline was written"


def test_the_door_takes_them_and_refuses_a_deadline_in_the_past(e, monkeypatch):
    monkeypatch.setattr(TL, "mode_staffing", lambda *a: {"ready": True, "executors": ["exec-1", "exec-2"],
                                                          "dispatch": False})
    assert TL.set_mode(e, "auto", deadline_s=-1)["refused"]
    got = TL.set_mode(e, "auto", system_model="claude-haiku-4-5", l2_gate=False, deadline_s=0)
    assert got["settings"] == {"system_model": "claude-haiku-4-5", "l2_gate": "0", "deadline_s": 0.0}
    assert project_deadline_s(e.graph) == 0 and not l2_gate_on(e.graph)
