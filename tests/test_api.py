"""Tests for HTTP API endpoints."""
from fastapi.testclient import TestClient
from gfso.engine import Engine
from gfso.adapters.storage.memory import MemoryStorage
from gfso.adapters.llm.stub import StubLLM
from gfso.adapters.agents.human import HumanAgent
from gfso.api.server import create_app


def _client() -> TestClient:
    engine = Engine(MemoryStorage(), HumanAgent(), StubLLM(), validate_signals=False)
    engine.start()
    app = create_app(engine)
    return TestClient(app)


def test_index_serves_html():
    c = _client()
    r = c.get("/")
    assert r.status_code == 200
    assert "GFSO" in r.text


def test_create_task():
    c = _client()
    r = c.post("/api/tasks", json={
        "spec": {"description": "build feature", "criteria": [{"name": "works", "description": "it works"}]},
        "assignee": "dev",
    })
    assert r.status_code == 201
    d = r.json()
    assert d["description"] == "build feature"
    assert d["state"] == "REVIEW"


def test_list_tasks():
    c = _client()
    c.post("/api/tasks", json={"spec": {"description": "a"}, "assignee": "d1"})
    c.post("/api/tasks", json={"spec": {"description": "b"}, "assignee": "d2"})
    r = c.get("/api/tasks")
    assert len(r.json()) == 2


def test_list_tasks_filter_assignee():
    c = _client()
    c.post("/api/tasks", json={"spec": {"description": "a"}, "assignee": "alice"})
    c.post("/api/tasks", json={"spec": {"description": "b"}, "assignee": "bob"})
    r = c.get("/api/tasks?assignee=alice")
    tasks = r.json()
    assert len(tasks) == 1
    assert tasks[0]["assignee"] == "alice"


def test_get_task_detail():
    c = _client()
    r = c.post("/api/tasks", json={
        "task_id": "t1",
        "spec": {"description": "build", "criteria": [{"name": "c1", "description": "d1"}]},
        "assignee": "dev",
    })
    r = c.get("/api/tasks/t1")
    assert r.status_code == 200
    d = r.json()
    assert d["id"] == "t1"
    assert "checks" in d
    assert "audit" in d


def test_get_task_not_found():
    c = _client()
    r = c.get("/api/tasks/nope")
    assert r.status_code == 404


def test_send_signal():
    c = _client()
    c.post("/api/tasks", json={"task_id": "t1", "spec": {"description": "x"}, "assignee": "dev"})
    # Task is in REVIEW after create. Send ACCEPT.
    r = c.post("/api/tasks/t1/signal", json={"signal": "ACCEPT", "source": "dev"})
    assert r.status_code == 200
    d = r.json()
    assert d["new_state"] == "EXECUTING"


def test_send_signal_rejected():
    c = _client()
    c.post("/api/tasks", json={"task_id": "t1", "spec": {"description": "x"}, "assignee": "dev"})
    # PASS is invalid in REVIEW state
    r = c.post("/api/tasks/t1/signal", json={"signal": "PASS", "source": "dev"})
    assert r.status_code == 200
    assert r.json()["rejected"] is True


def test_graph_endpoint():
    c = _client()
    c.post("/api/tasks", json={"task_id": "t1", "spec": {"description": "root"}, "assignee": "dev"})
    r = c.get("/api/graph")
    assert r.status_code == 200
    g = r.json()
    assert len(g["nodes"]) >= 1
    assert g["nodes"][0]["id"] == "t1"


def test_metrics_endpoint():
    c = _client()
    r = c.get("/api/metrics")
    assert r.status_code == 200
    m = r.json()
    assert "q_T" in m and "q_D" in m


def test_audit_endpoint():
    c = _client()
    c.post("/api/tasks", json={"task_id": "t1", "spec": {"description": "x"}, "assignee": "dev"})
    r = c.get("/api/audit?task_id=t1")
    assert r.status_code == 200
    assert len(r.json()) >= 1


def test_full_flow_via_api():
    c = _client()
    c.post("/api/tasks", json={"task_id": "t1", "spec": {"description": "x"}, "assignee": "dev"})
    c.post("/api/tasks/t1/signal", json={"signal": "ACCEPT"})
    c.post("/api/tasks/t1/signal", json={"signal": "DELIVER", "result": "done"})
    r = c.post("/api/tasks/t1/signal", json={"signal": "PASS"})
    assert r.json()["new_state"] == "DONE"


def test_decompose():
    c = _client()
    c.post("/api/tasks", json={"task_id": "p", "spec": {"description": "parent", "criteria": [{"name": "perf", "description": "fast"}]}, "assignee": "pm"})
    r = c.post("/api/tasks/p/decompose", json={
        "children": [
            {"task_id": "c1", "spec": {"description": "child 1"}, "assignee": "dev1"},
            {"task_id": "c2", "spec": {"description": "child 2"}, "assignee": "dev2"},
        ]
    })
    assert r.status_code == 200
    assert len(r.json()) == 2
    # Graph should show parent-child edges
    g = c.get("/api/graph").json()
    parent_edges = [e for e in g["edges"] if e["source"] == "p"]
    assert len(parent_edges) == 2
