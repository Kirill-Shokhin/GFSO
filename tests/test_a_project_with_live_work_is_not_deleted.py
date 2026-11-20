"""Work ends by CANCEL → CONFIRM_CANCEL (§12.6), and its record is one append-only log (§11.1): deleting a project
whose nodes are issued and not terminal ended the work with no cancel and erased the log. A stop is no end — its nodes
stay issued — so it is refused stopped too, and the refusal names the lift; once every node is terminal it goes."""
from __future__ import annotations

import os

import pytest

import gfso.tools as T
from gfso.core.types import State, TaskId
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
