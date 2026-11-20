"""Work ends by CANCEL → CONFIRM_CANCEL (§12.6), and its record is one append-only log (§11.1): deleting a project
whose nodes are issued and not terminal ended the work with no cancel and erased the log. A stop is no end — its nodes
stay issued — so it is refused stopped too, and the refusal names the lift; once every node is terminal it goes."""
from __future__ import annotations

import os

import pytest

import gfso.tools as T
import gfso.tools_llm as TL
from gfso.config import CALLER, Principal
from gfso.core.types import AgentId, Mode, State, TaskId
from gfso.runtime import ProjectRegistry
from tests.support import criterion


def test_a_project_with_an_issued_node_is_not_deleted_until_its_work_has_ended(tmp_path, monkeypatch):
    monkeypatch.setenv("GFSO_DATA_DIR", str(tmp_path))
    monkeypatch.setenv("GFSO_HOME", str(tmp_path))
    reg = ProjectRegistry(default_storage="sqlite", default_llm="stub", seed=False)
    e = reg.engine("doomed")
    T.create_task(e, "root", {"description": "a goal", "criteria": [criterion("c1", "C1 holds")]}, assignee="me")
    e.wait_idle()
    e.pause("me")
    with pytest.raises(ValueError, match="CANCEL") as ex:
        reg.delete("doomed")
    assert "root" in str(ex.value)
    assert os.path.exists(tmp_path / "doomed.db") and "doomed" in reg.names(), "the refusal deleted it anyway"
    t = e.graph.get_task(TaskId("root"))
    t.state = State.ABANDONED
    e._graph.save_task(t)
    reg.delete("doomed")
    assert "doomed" not in reg.names()


@pytest.mark.parametrize("mode", [None, Mode.SOLO, Mode.SEMI, Mode.AUTO])
def test_the_refusals_own_route_ends_in_a_deletion(tmp_path, monkeypatch, mode):
    """The refusal names the route the project's mode admits, and walking its words at the doors deletes it. Under AUTO
    the customer's CANCEL on the root is refused (the mode lock), so "CANCEL its root" alone sent him into a refusal:
    the person changes the mode from their page first."""
    monkeypatch.setenv("GFSO_DATA_DIR", str(tmp_path))
    monkeypatch.setenv("GFSO_HOME", str(tmp_path))
    monkeypatch.setattr(TL, "mode_staffing", lambda *a: {"ready": True, "executors": ["exec-1", "exec-2"],
                                                          "dispatch": False})
    reg = ProjectRegistry(default_storage="sqlite", default_llm="stub", seed=False)
    e = reg.engine("doomed")
    if mode is not None:
        e.set_mode(mode, None, AgentId("user"))
    e.workforce.publish_executor_pool({"exec-1": "doomed", "exec-2": "doomed"})   # …after: setting it reads the roster
    T.create_task(e, "root", {"description": "a goal", "criteria": [criterion("c1", "C1 holds")]},
                  **({} if mode else {"assignee": "user"}))
    e.wait_idle()
    with pytest.raises(ValueError) as ex:
        reg.delete("doomed")
    said = str(ex.value)
    page = CALLER.set(Principal("user", ("user",), "session", "a page", "local"))
    try:
        if "from their page" in said:                                    # …the words' first step, where they name it
            assert not TL.set_mode(e, "solo").get("refused")
        assert "CANCEL its root" in said, said
        out = TL.TOOLS["signal"](e, "root", "CANCEL", str(e.graph.issuer_of(TaskId("root"))), reason="not wanted")
        assert out.get("accepted"), out
    finally:
        CALLER.reset(page)
    e.wait_idle()
    if (t := e.graph.get_task(TaskId("root"))).state == State.CANCELLING:          # …the executor's confirmation
        T.signal(e, "root", "CONFIRM_CANCEL", str(t.assignee), in_flight="nothing yet")
        e.wait_idle()
    assert e.graph.get_task(TaskId("root")).state == State.ABANDONED
    reg.delete("doomed")
    assert "doomed" not in reg.names()
