"""Tests for HTTP API endpoints."""
from fastapi.testclient import TestClient
from gfso.engine import Engine
from gfso.adapters.storage.memory import MemoryStorage
from gfso.adapters.llm.stub import StubLLM
from gfso.adapters.agents.human import HumanAgent
from gfso.api.server import create_app
from gfso.api.models import CheckResultOut
import gfso.tools as T


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
    r = c.post("/api/run/create_task", json={
        "spec": {"description": "build feature", "criteria": [{"name": "works", "description": "it works"}]},
        "assignee": "dev",
    })
    assert r.status_code == 200
    d = r.json()
    assert d["description"] == "build feature"
    assert d["state"] == "OFFERED"


def test_list_tasks():
    c = _client()
    c.post("/api/run/create_task", json={"spec": {"description": "a"}, "assignee": "d1"})
    c.post("/api/run/create_task", json={"spec": {"description": "b"}, "assignee": "d2"})
    r = c.get("/api/tasks")
    assert len(r.json()) == 2


def test_list_tasks_filter_assignee():
    c = _client()
    c.post("/api/run/create_task", json={"spec": {"description": "a"}, "assignee": "alice"})
    c.post("/api/run/create_task", json={"spec": {"description": "b"}, "assignee": "bob"})
    r = c.get("/api/tasks?assignee=alice")
    tasks = r.json()
    assert len(tasks) == 1
    assert tasks[0]["assignee"] == "alice"


def test_upper_authoring_endpoints():
    """The upper-layer authoring verbs over the generic dispatch (same surface UI + MCP ride): RMW edits."""
    c = _client()
    c.post("/api/run/create_task", json={"task_id": "n", "spec": {"description": "node",
           "criteria": [{"name": "k", "description": "keep"}]}, "assignee": "alice"})

    r = c.post("/api/run/edit_accepted_risks", json={"task_id": "n", "accepted_risks": [{"item": "out of scope"}], "agent": "alice"})
    assert r.status_code == 200 and r.json()["accepted_risks"] == ["out of scope"]

    r = c.post("/api/run/edit_criteria",
               json={"task_id": "n", "criteria": [{"name": "k2", "description": "tighter"}], "agent": "alice"})
    assert r.status_code == 200 and [x["name"] for x in r.json()["criteria"]] == ["k2"]

    # `revise` replaces the WHOLE contract, so the register set two calls up has to be passed again
    # to survive — omitting it is now REFUSED rather than performed silently (a person lost a
    # five-criterion contract that way on 2026-08-21).
    gone = c.post("/api/run/revise", json={"task_id": "n", "spec": {"description": "node2",
                  "criteria": [{"name": "k3", "description": "d"}]}, "agent": "alice"})
    assert gone.status_code == 422 and gone.json()["would_delete"] == ["ACCEPTED_RISKS"]

    r = c.post("/api/run/revise", json={"task_id": "n", "spec": {"description": "node2",
               "criteria": [{"name": "k3", "description": "d"}],
               "accepted_risks": [{"item": "out of scope"}]}, "agent": "alice"})
    assert r.status_code == 200 and r.json()["description"] == "node2"

    r = c.post("/api/run/reassign", json={"task_id": "n", "assignee": "bob"})
    assert r.status_code == 200 and r.json()["assignee"] == "bob"


def test_get_task_detail():
    c = _client()
    r = c.post("/api/run/create_task", json={
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
    c.post("/api/run/create_task", json={"task_id": "t1", "spec": {"description": "x"}, "assignee": "dev"})
    # Task is in OFFERED after create. Send ACCEPT.
    r = c.post("/api/run/signal", json={"task_id": "t1", "signal": "ACCEPT", "source": "dev"})
    assert r.status_code == 200
    d = r.json()
    assert d["accepted"] is True and d["state"] == "EXECUTING"
    # read-back via the unchanged read endpoint confirms the transition landed
    assert c.get("/api/tasks/t1").json()["state"] == "EXECUTING"


def test_send_signal_rejected():
    c = _client()
    c.post("/api/run/create_task", json={"task_id": "t1", "spec": {"description": "x"}, "assignee": "dev"})
    # PASS is not admitted in OFFERED → the FSM answers "no", which is a call this door PROCESSED:
    # HTTP 200 with the answer in the body. The act not happening is what the CLI's exit code says.
    r = c.post("/api/run/signal", json={"task_id": "t1", "signal": "PASS", "source": "dev"})
    assert r.status_code == 200
    assert r.json()["accepted"] is False and "not admitted by state OFFERED" in r.json()["error"]
    assert c.get("/api/tasks/t1").json()["state"] == "OFFERED"  # state unchanged


def test_graph_endpoint():
    c = _client()
    c.post("/api/run/create_task", json={"task_id": "t1", "spec": {"description": "root"}, "assignee": "dev"})
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
    c.post("/api/run/create_task", json={"task_id": "t1", "spec": {"description": "x"}, "assignee": "dev"})
    r = c.get("/api/audit?task_id=t1")
    assert r.status_code == 200
    assert len(r.json()) >= 1


def test_full_flow_via_api():
    c = _client()
    c.post("/api/run/create_task", json={"task_id": "t1", "spec": {"description": "x"}, "assignee": "dev"})
    c.post("/api/run/signal", json={"task_id": "t1", "signal": "ACCEPT", "source": "dev"})
    c.post("/api/run/signal", json={"task_id": "t1", "signal": "DELIVER", "source": "dev", "result": "done"})
    r = c.post("/api/run/signal", json={"task_id": "t1", "signal": "PASS", "source": "dev"})
    assert r.json()["accepted"] is True and r.json()["state"] == "DONE"
    assert c.get("/api/tasks/t1").json()["state"] == "DONE"


def test_decompose():
    c = _client()
    c.post("/api/run/create_task", json={"task_id": "p", "spec": {"description": "parent", "criteria": [{"name": "perf", "description": "fast"}]}, "assignee": "pm"})
    r = c.post("/api/run/decompose", json={
        "parent_id": "p",
        "children": [
            {"task_id": "c1", "spec": {"description": "child 1"}, "assignee": "dev1"},
            {"task_id": "c2", "spec": {"description": "child 2"}, "assignee": "dev2"},
        ],
    })
    assert r.status_code == 200
    assert len(r.json()) == 2
    # Graph should show parent-child edges
    g = c.get("/api/graph").json()
    parent_edges = [e for e in g["edges"] if e["source"] == "p"]
    assert len(parent_edges) == 2


def test_unified_app_shares_one_engine_with_mcp_tools():
    """UI (HTTP) and the agent (MCP tool layer) operate ONE Engine: a write through the MCP tools is
    read back via HTTP. `with_mcp=True` degrades gracefully when the MCP SDK is absent (mount skipped,
    no crash) — the /mcp transport mount itself is verified by the MCP suite."""
    from gfso import tools as T
    engine = Engine(MemoryStorage(), HumanAgent(), StubLLM(), validate_signals=True)
    engine.start()
    app = create_app(engine, with_mcp=True)          # SDK absent here → no /mcp mount, must not raise
    assert app.state.engine is engine                # HTTP surface holds the shared engine
    T.create_task(engine, "shared",                  # agent authors on the SAME object
                  {"description": "shared", "criteria": [{"name": "a", "description": "A"}]}, "alice")
    r = TestClient(app).get("/api/tasks/shared")
    assert r.status_code == 200 and r.json()["id"] == "shared"   # UI reads the agent's write


def test_the_verdict_reads_the_same_through_either_door():
    """`get_verdict` and `/api/tasks/{id}/verdict` answered with two different schemas.

    The verb carries state, currency, the delivery it judged and any refused reports; the endpoint
    returned the raw record. A caller moving from one door to the other crashed on `KeyError:
    'state'` (measured on the human door 2026-08-22: "same fact, two schemas")."""
    c = _client()
    c.post("/api/run/create_task", json={"task_id": "t1", "spec": {"description": "x",
           "criteria": [{"name": "c1", "description": "d"}]}, "assignee": "dev"})
    c.post("/api/run/signal", json={"task_id": "t1", "signal": "ACCEPT", "source": "dev"})
    c.post("/api/run/signal", json={"task_id": "t1", "signal": "DELIVER", "source": "dev",
                                    "result": "did it"})
    c.post("/api/run/record_verdict", json={"task_id": "t1", "verdict": "PASS",
                                            "reviewer": "someone-else",
                                            "observed": {"c1": "ran it, it printed what it should"}})
    door = c.get("/api/tasks/t1/verdict").json()
    verb = c.post("/api/run/get_verdict", json={"task_id": "t1"}).json()
    assert door == verb and door["state"] == "VALIDATING" and door["verdict"] == "PASS"
    assert door["current"] is True and door["delivered"] == "did it"


def test_the_roster_answers_with_a_map_of_roles_and_nothing_else_in_it():
    """A note added beside the roles put a STRING where every reader expects a role config.

    The measurement arm's preflight iterates the roster and calls `.get("kind")` on each value; with
    the scope note mixed into the same map it died on `'str' object has no attribute 'get'`
    (2026-08-22 — my own change, caught by the arm within the minute). A map of roles is a map of
    roles; anything else about the roster sits beside it."""
    c = _client()
    out = c.get("/api/agents").json()
    assert set(out) == {"agents", "scope"} and isinstance(out["agents"], dict)
    assert all(isinstance(v, dict) for v in out["agents"].values())


def test_a_skipped_check_is_not_reported_passed_on_the_http_door():
    """`passed=True` beside `skipped=True` is fail-open, and the UI reads `passed`.

    The tool door had been fixed to send None there; this one had not, so the same check answered
    differently depending on which door you came in by (register 2026-08-22, finding 7)."""
    class _Skipped:
        check_name, details, skipped, passed = "CHECK-7", "no composition declared", True, True

    row = CheckResultOut.of(_Skipped())
    assert row.passed is None and row.verdict == "skipped"

    class _Unmet:
        check_name, details, skipped, passed = "CHECK-1", "criterion c1 uncovered", False, False

    assert CheckResultOut.of(_Unmet()).verdict == "unmet"


def test_a_refusal_is_a_refusal_over_both_doors():
    """`record_verdict`'s refusal was exit code 1 over the CLI and HTTP 200 OK over the API.

    The verbs answer in several shapes for good reasons — a signal says `accepted`, a record says
    `recorded` — and each door read that its own way. Whether the act HAPPENED may not depend on
    which door you came in by (register 2026-08-22, finding 2)."""
    assert T.is_refusal({"recorded": False, "error": "a PASS needs what was observed"}) is True
    assert T.is_refusal({"accepted": False, "state": "VALIDATING", "error": "…"}) is True
    assert T.is_refusal({"error": "unknown task x"}) is True
    assert T.is_refusal({"accepted": True, "state": "DONE"}) is False
    assert T.is_refusal({"recorded": True}) is False

    # …and the DOORS answer different questions on purpose: this one is about the call (processed,
    # so 200 with the answer inside), the CLI's exit code is about the act (1, it did not happen).
    r = _client().post("/api/run/record_verdict",
                       json={"task_id": "nope", "verdict": "PASS", "reviewer": "someone"})
    assert r.status_code == 200 and T.is_refusal(r.json())
