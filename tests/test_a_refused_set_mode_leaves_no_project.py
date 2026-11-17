"""A refused `set_mode` on a name nobody made leaves no project behind, on every door: the mode is chosen before the
plan, so `set_mode` may bring a project into existence (`PROJECT_CREATING_VERBS`) — but a refusal (no validator, no
executor yet) made one anyway, an empty graph listed among the person's projects, one per name tried."""
import asyncio

from fastapi.testclient import TestClient

from gfso.api.server import create_app
from gfso.mcp.server import _bind
from gfso.runtime import ProjectRegistry
from gfso import tools_llm as TL


def _reg(monkeypatch, tmp_path):
    monkeypatch.setenv("GFSO_DATA_DIR", str(tmp_path))
    monkeypatch.delenv("GFSO_PROJECT", raising=False)
    monkeypatch.setenv("GFSO_STORAGE", "memory")
    return ProjectRegistry()


def _stop(reg):
    for e in list(reg._engines.values()):
        e.stop()


def test_a_refused_set_mode_leaves_no_project_on_the_http_door(monkeypatch, tmp_path):
    reg = _reg(monkeypatch, tmp_path)
    try:
        with TestClient(create_app(reg.engine(), registry=reg)) as c:
            out = c.post("/api/run/set_mode?project=never_made", json={"mode": "auto"}).json()
            assert out.get("refused"), out
            assert "never_made" not in c.get("/api/projects").json()["projects"]
        assert not (tmp_path / "never_made.db").exists()
    finally:
        _stop(reg)


def test_a_refused_set_mode_leaves_no_project_on_the_mcp_door(monkeypatch, tmp_path):
    reg = _reg(monkeypatch, tmp_path)
    try:
        out = asyncio.run(_bind(reg, TL.TOOLS["set_mode"])(mode="auto", project="never_made"))
        assert out.get("refused"), out
        assert "never_made" not in reg.list()["projects"]
        assert not (tmp_path / "never_made.db").exists()
    finally:
        _stop(reg)


def test_a_read_on_the_mcp_door_makes_no_project(monkeypatch, tmp_path):
    """The same door made the project any verb named — a read included, one project per typo — where the HTTP door
    refuses an unknown name to every verb that does not author."""
    reg = _reg(monkeypatch, tmp_path)
    try:
        out = asyncio.run(_bind(reg, TL.TOOLS["get_graph"])(project="typo_read"))
        assert out.get("refused") and "no such project" in out["error"], out
        assert "typo_read" not in reg.list()["projects"]
    finally:
        _stop(reg)


def test_an_accepted_set_mode_still_makes_the_project(monkeypatch, tmp_path):
    """The pair: the same door, staffed, makes the project — the refusal is what leaves none."""
    reg = _reg(monkeypatch, tmp_path)
    try:
        with TestClient(create_app(reg.engine(), registry=reg)) as c:
            for a, k in (("p-val", "llm-validator"), ("p-exec-1", "llm-executor"), ("p-exec-2", "llm-executor")):
                c.post("/api/run/register_agent?project=made", json={"agent_id": a, "kind": k, "workdir": str(tmp_path)})
            out = c.post("/api/run/set_mode?project=made", json={"mode": "auto"}).json()
            assert out.get("mode") == "auto", out
            assert "made" in c.get("/api/projects").json()["projects"]
    finally:
        _stop(reg)
