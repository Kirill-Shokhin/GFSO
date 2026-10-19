"""A role put on the server-wide roster can be taken off it — and only by whoever staffed it.

`register_agent` could add roles and nothing on any door removed them, so every run left its executors
and validators behind (34 dead roles on the operator's server, 2026-09-22).
"""
from __future__ import annotations

import gfso.tools as T
import gfso.tools_llm as TL
from gfso.config import DEFAULT_PROJECT
from tests.support import criterion, make_engine


def test_a_role_comes_off_and_the_answer_names_the_live_work_it_leaves():
    e = make_engine()
    e.start()
    TL.TOOLS["register_agent"](e, "off-exec", "external")
    T.create_task(e, "root", {"description": "goal", "criteria": [criterion("c")]}, assignee="off-exec")
    e.wait_idle()
    out = TL.TOOLS["unregister_agent"](e, "off-exec")
    assert out.get("unregistered") and out["assigned_live"] == ["root"]
    assert out["issued_live"] == ["root"], "a root is its own issuer and now waits for a person"
    assert "off-exec" not in TL.TOOLS["list_agents"](e, limit=0)["agents"]
    e.stop()


def test_another_projects_role_is_not_removed_without_its_workdir():
    e = make_engine()
    TL.TOOLS["register_agent"](e, "their-exec", "external")
    roster = TL.TOOLS["list_agents"](e, limit=0)["agents"]
    if not roster.get("their-exec", {}).get("project"):
        # a bare engine registers roles unscoped; scope it the way a project's door does
        TL._roster().register("their-exec", "external", project="someone-else")
    out = TL.TOOLS["unregister_agent"](e, "their-exec")
    assert out.get("unregistered") is None and "someone-else" in out.get("error", "")
    assert "their-exec" in TL.TOOLS["list_agents"](e, limit=0)["agents"]


def test_this_projects_own_role_comes_off_without_its_workdir():
    e = make_engine()
    TL._roster().register("my-exec", "external", project=e.project_name or DEFAULT_PROJECT)
    out = TL.TOOLS["unregister_agent"](e, "my-exec")
    assert out.get("unregistered"), f"the caller's own scoped role was refused: {out}"
