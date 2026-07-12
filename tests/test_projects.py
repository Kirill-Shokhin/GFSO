"""Multi-project registry: a project = one GRAPH (forest) in its OWN DB file — physical isolation
(cross-project Dep unrepresentable by construction); verbs route per-call via `project` or follow
the ACTIVE project; back-compat: default project = the env-configured engine, nothing changes."""
import inspect

import pytest

from gfso.runtime import ProjectRegistry
from gfso import tools as T


def _reg(monkeypatch, tmp_path):
    monkeypatch.setenv("GFSO_DATA_DIR", str(tmp_path))
    monkeypatch.delenv("GFSO_PROJECT", raising=False)
    monkeypatch.setenv("GFSO_STORAGE", "memory")   # default project in-memory for test speed
    return ProjectRegistry()


def _mk(engine, tid):
    T.create_task(engine, tid, {"description": tid, "criteria": [{"name": "a", "description": "A"}]}, "x")


def test_projects_are_isolated_graphs(monkeypatch, tmp_path):
    monkeypatch.setenv("GFSO_DATA_DIR", str(tmp_path))
    monkeypatch.delenv("GFSO_STORAGE", raising=False)  # named projects: real sqlite files
    reg = ProjectRegistry()                            # default project never materialized here
    a, b = reg.engine("proj_a"), reg.engine("proj_b")
    _mk(a, "t1")
    assert a.get_task(T.TaskId("t1")) is not None
    assert b.get_task(T.TaskId("t1")) is None          # physical isolation
    assert (tmp_path / "proj_a.db").exists() and (tmp_path / "proj_b.db").exists()
    # same name → same engine (cached, one owner per process)
    assert reg.engine("proj_a") is a
    a.stop(); b.stop()


def test_active_project_switch_and_list(monkeypatch, tmp_path):
    reg = _reg(monkeypatch, tmp_path)
    assert reg.active == "default"
    default_eng = reg.engine()
    eng_a = reg.use("alpha")
    assert reg.active == "alpha" and reg.engine() is eng_a and reg.engine() is not default_eng
    lst = reg.list()
    assert lst["active"] == "alpha" and "default" in lst["projects"] and "alpha" in lst["projects"]
    default_eng.stop(); eng_a.stop()


def test_registry_fires_on_create_hook_for_new_projects(monkeypatch, tmp_path):
    """A new project is an EVENT, not a poll target: the registry calls its `_on_create` hook once per
    genuinely-new project — the server broadcasts that so every UI refreshes its project list live (no reload)."""
    reg = _reg(monkeypatch, tmp_path)
    created = []
    reg._on_create = created.append
    reg.engine("alpha"); reg.engine("alpha")               # second access is cached → no duplicate event
    reg.use("beta")
    assert created == ["alpha", "beta"]                    # exactly one event per newly created project


def test_bad_project_name_rejected(monkeypatch, tmp_path):
    reg = _reg(monkeypatch, tmp_path)
    for bad in ("../evil", "a b", "x" * 65, ""):
        with pytest.raises(ValueError):
            reg.use(bad) if bad else reg.use("../also")


def test_mcp_bind_gains_project_param_and_routes(monkeypatch, tmp_path):
    from gfso.mcp.server import _bind
    reg = _reg(monkeypatch, tmp_path)
    w = _bind(reg, T.get_task)
    params = inspect.signature(w).parameters
    assert "project" in params and params["project"].default is None
    _mk(reg.engine("p1"), "n1")
    assert w("n1", project="p1")["id"] == "n1"         # explicit per-call routing
    assert w("n1") is None                              # active = default — isolated
    reg.use("p1")
    assert w("n1")["id"] == "n1"                        # follows the active switch
    for e in list(reg._engines.values()):
        e.stop()


def test_mcp_bind_project_param_with_var_keyword(monkeypatch, tmp_path):
    """A tool with a VAR_KEYWORD — the injected `project` must precede it or the signature is invalid
    (this crashed the whole MCP server on startup with -32000, live 2026-07-03; `signal` has since
    moved to explicit params — a transport bug: **payload never decodes over the MCP schema — but the
    binding invariant stays locked here on a synthetic tool)."""
    from gfso.mcp.server import _bind
    reg = _reg(monkeypatch, tmp_path)

    def varkw_tool(engine, task_id: str, **payload) -> dict:
        return {"task_id": task_id, "n": len(payload)}

    w = _bind(reg, varkw_tool)                          # must not raise
    kinds = [p.kind for p in inspect.signature(w).parameters.values()]
    assert kinds.index(inspect.Parameter.KEYWORD_ONLY) < kinds.index(inspect.Parameter.VAR_KEYWORD)
    # the REAL signal verb: `source` is PINNED to the agent's own id (impersonation impossible over
    # this door) and gone from the signature; payload params route intact
    ws = _bind(reg, T.signal)
    assert "source" not in inspect.signature(ws).parameters
    T.create_task(reg.engine("pk"), "s1", {"description": "mine",
                                           "criteria": [{"name": "a", "description": "A"}]})  # Del=agent
    assert ws("s1", "ACCEPT", project="pk")["state"] == "EXECUTING"
    assert ws("s1", "DELIVER", result="paths…", project="pk")["state"] == "VALIDATING"
    # a node delegated to someone else does NOT move on the agent's signal (FSM: source ≠ Del)
    _mk(reg.engine("pk"), "his")                        # Del="x"
    assert ws("his", "ACCEPT", project="pk")["accepted"] is False
    for e in list(reg._engines.values()):
        e.stop()


def test_create_server_with_registry_builds_all_tools(monkeypatch, tmp_path):
    """The whole-server smoke that would have caught the -32000 startup crash."""
    import pytest
    pytest.importorskip("mcp")
    import asyncio
    from gfso.mcp.server import create_server
    reg = _reg(monkeypatch, tmp_path)
    listed = asyncio.run(create_server(reg).list_tools())
    tools = {t.name for t in listed}
    assert {"signal", "use_project", "list_projects", "auto_decompose", "validate_node",
            "register_agent", "list_agents"} <= tools
    # signal's payload is EXPLICIT typed params on the wire (a **payload never decodes over MCP —
    # DELIVER results silently vanished, observed live 2026-07-03); `source` is PINNED off the wire
    sig_props = next(t for t in listed if t.name == "signal").inputSchema["properties"]
    assert {"result", "failed_criteria", "reason",
            "blocker_task_id", "blocker_task_ids"} <= set(sig_props)
    assert "source" not in sig_props                    # the agent's door signs as the agent, always
    for e in list(reg._engines.values()):
        e.stop()


def test_api_projects_endpoints(monkeypatch, tmp_path):
    from fastapi.testclient import TestClient
    from gfso.api.server import create_app
    reg = _reg(monkeypatch, tmp_path)
    app = create_app(reg.engine(), registry=reg)
    with TestClient(app) as c:
        d = c.get("/api/projects").json()
        assert d["active"] == "default"
        assert c.post("/api/projects/use", json={"name": "beta"}).json()["active"] == "beta"
        _mk(reg.engine(), "in_beta")                    # active engine = beta now
        assert c.get("/api/tasks/in_beta").json()["id"] == "in_beta"   # UI follows the switch
        assert c.post("/api/projects/use", json={"name": "../evil"}).status_code == 422
    for e in list(reg._engines.values()):
        e.stop()


def test_single_project_backcompat(monkeypatch):
    """A bare Engine (no registry): /api/projects degrades gracefully, MCP _bind adds no param."""
    from gfso.engine import Engine
    from gfso.adapters.storage.memory import MemoryStorage
    from gfso.adapters.agents.human import HumanAgent
    from gfso.adapters.llm.stub import StubLLM
    from gfso.mcp.server import _bind
    from fastapi.testclient import TestClient
    from gfso.api.server import create_app

    e = Engine(MemoryStorage(), HumanAgent(), StubLLM(), validate_signals=True)
    e.start()
    assert "project" not in inspect.signature(_bind(e, T.get_task)).parameters
    with TestClient(create_app(e)) as c:
        assert c.get("/api/projects").json() == {"active": "default", "projects": ["default"]}
        assert c.post("/api/projects/use", json={"name": "x"}).status_code == 400
    e.stop()


def test_api_per_tab_project_scope(monkeypatch, tmp_path):
    """Two browser TABS = two projects at once: ?project= on any /api call (and the WS url) scopes THAT
    request to that project's engine — no global switching needed."""
    from fastapi.testclient import TestClient
    from gfso.api.server import create_app
    reg = _reg(monkeypatch, tmp_path)
    _mk(reg.engine("tab_a"), "in_a")
    _mk(reg.engine("tab_b"), "in_b")
    app = create_app(reg.engine(), registry=reg)
    with TestClient(app) as c:
        a = {t["id"] for t in c.get("/api/tasks?project=tab_a").json()}
        b = {t["id"] for t in c.get("/api/tasks?project=tab_b").json()}
        assert a == {"in_a"} and b == {"in_b"}
        assert c.get("/api/tasks").json() == []          # no param → the active (default) project
    for e in list(reg._engines.values()):
        e.stop()


def test_mcp_session_scoped_project_resolution(monkeypatch, tmp_path):
    """One shared server, several agent sessions: each session's use_project sets ITS default —
    resolution precedence = explicit `project` param → the session's project → the global active."""
    from gfso.mcp import server as S
    reg = _reg(monkeypatch, tmp_path)
    res = S._resolver(reg)

    class _Ctx:                                          # the shape _session_key reads
        def __init__(self):
            class RC: session = object()
            self.request_context = RC()

    s1, s2 = _Ctx(), _Ctx()
    S._SESSION_PROJECTS[S._session_key(s1)] = "sess_one"
    _mk(res(None, s1), "t_one")                          # lands in sess_one
    assert res(None, s1).get_task(T.TaskId("t_one")) is not None
    assert res(None, s2).get_task(T.TaskId("t_one")) is None      # s2 → global active (default)
    assert res("sess_one", s2).get_task(T.TaskId("t_one")) is not None  # explicit param outranks
    for e in list(reg._engines.values()):
        e.stop()


def test_lease_lifecycle_and_reaper(monkeypatch, tmp_path):
    """The shared server mirrors its sessions: leases renew via heartbeats; once ANY lease existed
    and the last one expires/drops, the reaper fires the exit; /api/shutdown = the manual `gfso down`."""
    import time
    from fastapi.testclient import TestClient
    from gfso.api.server import create_app, _start_reaper
    reg = _reg(monkeypatch, tmp_path)
    app = create_app(reg.engine(), registry=reg)
    exited = []
    app.state.exit_fn = lambda: exited.append(True)
    _start_reaper(app, grace=0.5, interval=0.05)
    with TestClient(app) as c:
        time.sleep(0.3)
        assert not exited                                      # no lease ever → never reaps (UI-only use)
        assert c.post("/api/lease", json={"id": "s1"}).json()["sessions"] == 1
        time.sleep(0.15)
        c.post("/api/lease", json={"id": "s1"})               # heartbeat keeps it alive
        time.sleep(0.15)
        assert not exited
        c.delete("/api/lease/s1")                              # last session gone
        for _ in range(60):
            if exited:
                break
            time.sleep(0.05)
        assert exited                                          # server exits itself
        # manual shutdown endpoint (gfso down)
        exited.clear()
        assert c.post("/api/shutdown").json()["ok"] is True
        for _ in range(60):
            if exited:
                break
            time.sleep(0.05)
        assert exited
    for e in list(reg._engines.values()):
        e.stop()
