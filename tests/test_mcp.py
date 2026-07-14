"""MCP tool layer — logic tested directly (no MCP transport needed)."""
import inspect
from gfso.engine import Engine
from gfso.adapters.storage.memory import MemoryStorage
from gfso.adapters.agents.human import HumanAgent
from gfso.adapters.llm.stub import StubLLM
from gfso import tools as T
from gfso import tools_llm as TL
from gfso.mcp.server import _bind


def _eng():
    e = Engine(MemoryStorage(), HumanAgent(), StubLLM(), validate_signals=True)
    e.start()
    return e


def test_agent_loop_through_tools():
    """The agent's authoring loop driven entirely through the MCP tool functions → JSON-able dicts."""
    e = _eng()
    root = T.create_task(e, "r", {"description": "root", "criteria": [{"name": "a", "description": "A"}]}, "alice")
    assert root["state"] == "REVIEW" and root["id"] == "r"

    proj = T.project(e, "r")
    assert isinstance(proj, str) and "root" in proj

    kids = T.decompose(e, "r",
                       [{"task_id": "c1", "spec": {"description": "c1", "criteria": [{"name": "x", "description": "X"}]}, "assignee": "alice"},
                        {"task_id": "c2", "spec": {"description": "c2", "criteria": [{"name": "y", "description": "Y"}]}, "assignee": "alice"}],
                       [{"criterion_name": "a", "child_id": "c1"}])
    assert {k["id"] for k in kids} == {"c1", "c2"}

    # declared dep (criteria-content) + read back derived
    T.add_dependency(e, "c1", "c2", glue="c2 uses c1 output")
    deps = T.get_dependencies(e)
    assert any(d["from"] == "c1" and d["to"] == "c2" for d in deps)

    # RMW edits via tools
    T.edit_criteria(e, "c1", [{"name": "x2", "description": "tighter"}], "alice")
    assert [c["name"] for c in T.get_task(e, "c1")["criteria"]] == ["x2"]
    T.reassign(e, "c2", "bob")
    assert T.get_task(e, "c2")["assignee"] == "bob"

    # lifecycle signal + L2 validate both return JSON-able dicts
    assert T.signal(e, "r", "ACCEPT", "alice")["state"] == "EXECUTING"
    assert isinstance(TL.review_decomposition(e, "r"), dict)
    e.stop()


def test_get_task_exposes_name():
    """get_task returns the short `name` (BUG-4: it was omitted, so the label looked lost across readers)."""
    e = _eng()
    T.create_task(e, "r", {"name": "Root Label", "description": "root", "criteria": [{"name": "a", "description": "A"}]}, "alice")
    assert T.get_task(e, "r")["name"] == "Root Label"
    e.stop()


def test_signal_rejection_reports_reason():
    """A rejected signal returns WHY + the structural gate, not a silent accepted:false (BUG-3)."""
    e = _eng()
    T.create_task(e, "r", {"description": "root", "criteria": [{"name": "a", "description": "A"}]}, "alice")
    # decompose it (CHECK-4 gates decomposed nodes only, v3.7 §5.1) — root has no NEGLECTED → open hole
    T.decompose(e, "r", [{"task_id": "k", "spec": {"description": "k"}, "assignee": "alice"}],
                [{"criterion_name": "a", "child_id": "k"}])
    res = T.signal(e, "r", "PASS", "alice")            # PASS is invalid in REVIEW
    assert res["accepted"] is False
    assert "error" in res and "PASS" in res["error"]   # names the offending signal / valid set
    assert res.get("failing_checks")                   # surfaces CHECK-4 (empty NEGLECTED on a decomposed node)
    e.stop()


def test_list_holes_surfaces_graph_gaps():
    """list_holes aggregates every unmet structural check across the graph — check the decomposer's output
    BEFORE driving signals (a decomposed graph can come back with holes)."""
    e = _eng()
    T.create_task(e, "r", {"description": "root", "criteria": [{"name": "a", "description": "A"}]}, "alice")
    holes = T.list_holes(e)
    assert not any(h["task_id"] == "r" and h["check"].startswith("CHECK-4") for h in holes)  # leaf: not gated (§5.1)
    T.decompose(e, "r", [{"task_id": "k", "spec": {"description": "k"}, "assignee": "alice"}],
                [{"criterion_name": "a", "child_id": "k"}])
    holes = T.list_holes(e)                 # decomposed root with no NEGLECTED → CHECK-4 is an open hole
    assert any(h["task_id"] == "r" and h["check"].startswith("CHECK-4") for h in holes)
    e.stop()


def test_bind_drops_engine_from_signature():
    """The MCP shell exposes each tool WITHOUT the leading `engine` param (so the SDK infers a clean schema)."""
    e = _eng()
    w = _bind(e, T.create_task)
    params = list(inspect.signature(w).parameters)
    assert "engine" not in params and params[0] == "task_id"
    assert w.__doc__ == T.create_task.__doc__  # description preserved
    e.stop()


def test_tools_registry_complete():
    """Every authoring + read verb is registered for the agent surface — the COMPLETE registry
    is tools_llm.TOOLS (structural ∪ LLM); tools.TOOLS stays the structural subset (layer gate)."""
    for name in ("create_task", "decompose", "auto_decompose", "revise", "reneglect", "edit_criteria",
                 "reassign", "add_dependency", "remove_dependency", "map_criterion", "signal",
                 "review_decomposition", "project", "get_task", "next_step", "get_graph", "list_holes"):
        assert name in TL.TOOLS
    for name in ("auto_decompose", "review_decomposition", "validate_result"):
        assert name not in T.TOOLS                      # the LLM verbs live OFF the structural half


def test_agent_mutation_fires_the_ui_live_event():
    """The 'human watches live' path: a mutation through the MCP tool layer fires the engine's transition
    callback — the same one the UI's /ws/events WebSocket subscribes to — so the agent's actions show in the
    UI as they happen (one shared Engine; unified process)."""
    e = _eng()
    events = []
    e.on_transition(lambda tid, old, new, sig: events.append((str(tid), new.name, sig.name)))
    T.create_task(e, "live", {"description": "x", "criteria": [{"name": "a", "description": "A"}]}, "alice")
    e.wait_idle()
    assert any(t == "live" and new == "REVIEW" and sig == "ASSIGN" for t, new, sig in events)


def test_unified_mcp_transport_mounts_and_handshakes():
    """With the SDK present: the MCP streamable transport mounts at /mcp over the SAME Engine the UI uses,
    and an `initialize` handshake succeeds. Locks the two integration bugs: `_bind` must resolve string
    annotations (tools.py uses `from __future__ import annotations`) so the SDK can build tool schemas, and
    streamable_http_path must be "/" so the mount lands at /mcp (not /mcp/mcp)."""
    import pytest
    pytest.importorskip("mcp")
    from fastapi.testclient import TestClient
    from gfso.api.server import create_app

    e = _eng()
    T.create_task(e, "shared", {"description": "s", "criteria": [{"name": "a", "description": "A"}]}, "alice")
    app = create_app(e, with_mcp=True)
    assert any(str(getattr(r, "path", "")) == "/mcp" for r in app.routes)  # mounted, not /mcp/mcp
    with TestClient(app) as c:  # 'with' runs the lifespan → session manager
        r = c.post("/mcp",
                   json={"jsonrpc": "2.0", "id": 1, "method": "initialize",
                         "params": {"protocolVersion": "2025-06-18", "capabilities": {},
                                    "clientInfo": {"name": "t", "version": "1"}}},
                   headers={"Accept": "application/json, text/event-stream",
                            "Content-Type": "application/json", "Host": "127.0.0.1:8000"})
        assert r.status_code == 200
        assert any(k.lower() == "mcp-session-id" for k in r.headers)
        assert c.get("/api/tasks/shared").json()["id"] == "shared"  # one CORE: UI sees the agent's write


def test_default_assignee_is_the_calling_agent(monkeypatch):
    """Identity is TRANSPORT-derived, zero config: this tool surface is the AGENT's door, so an omitted
    assignee = `agent` out of the box (create_task / decompose children); GFSO_AGENT_ID only RENAMES;
    an explicit assignee = a real delegation and always wins."""
    e = _eng()
    monkeypatch.delenv("GFSO_AGENT_ID", raising=False)
    t = T.create_task(e, "self1", {"description": "x", "criteria": [{"name": "a", "description": "A"}]})
    assert t["assignee"] == "agent"                      # works with NO env at all
    kids = T.decompose(e, "self1", [{"task_id": "k1", "spec": {"description": "k"}}],
                       [{"criterion_name": "a", "child_id": "k1"}])
    assert kids[0]["assignee"] == "agent"
    t2 = T.create_task(e, "other", {"description": "y", "criteria": [{"name": "b", "description": "B"}]},
                       assignee="bob")
    assert t2["assignee"] == "bob"                       # explicit = real delegation, wins
    monkeypatch.setenv("GFSO_AGENT_ID", "claude-main")   # optional RENAME, not a requirement
    t3 = T.create_task(e, "named", {"description": "z", "criteria": [{"name": "c", "description": "C"}]})
    assert t3["assignee"] == "claude-main"
    e.stop()
