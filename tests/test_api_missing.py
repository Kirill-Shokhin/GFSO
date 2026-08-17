"""Tests for the completed API surface: deadline, Dep CRUD, audit who/why,
predictability, per-role actions, solver split. Engine + HTTP (via /api/run)."""
from datetime import datetime, timedelta

from fastapi.testclient import TestClient

from gfso.engine import Engine
from gfso.adapters.storage.memory import MemoryStorage
from gfso.adapters.llm.stub import StubLLM
from gfso.adapters.agents.human import HumanAgent
from gfso.api.server import create_app
from gfso.core.types import TaskId, AgentId, Spec, Signal


def _engine() -> Engine:
    e = Engine(MemoryStorage(), HumanAgent(), StubLLM(), validate_signals=False)
    e.start()
    return e


def _client(e: Engine) -> TestClient:
    return TestClient(create_app(e))


# === Item 1: deadline ===

def test_assign_task_sets_deadline():
    e = _engine()
    dl = datetime.now() + timedelta(days=3)
    e.assign_task(TaskId("t1"), Spec("x", ()), AgentId("d"), deadline=dl)
    e.wait_idle()
    assert e.get_task(TaskId("t1")).deadline == dl


def test_create_task_deadline_via_api():
    dl = (datetime.now() + timedelta(days=2)).isoformat()
    e = _engine()
    c = _client(e)
    r = c.post("/api/run/create_task", json={
        "task_id": "t1", "spec": {"description": "x"}, "assignee": "d", "deadline": dl,
    })
    assert r.status_code == 200
    # create_task's tool dict omits deadline; verify the ISO deadline round-tripped into the engine
    assert e.get_task(TaskId("t1")).deadline == datetime.fromisoformat(dl)


def test_decompose_per_child_deadline():
    e = _engine()
    e.assign_task(TaskId("p"), Spec("p", ()), AgentId("pm"))
    e.wait_idle()
    dl = datetime.now() + timedelta(days=1)
    e.decompose_task(TaskId("p"), [(TaskId("c1"), Spec("c", ()), AgentId("d"), dl)])
    assert e.get_task(TaskId("c1")).deadline == dl


# === Item 2: dependency CRUD + cycle rejection ===

def test_declared_cycle_rejected():
    e = _engine()
    e.assign_task(TaskId("t1"), Spec("a", ()), AgentId("d"))
    e.assign_task(TaskId("t2"), Spec("b", ()), AgentId("d"))
    e.wait_idle()
    e.add_dependency(TaskId("t1"), TaskId("t2"))
    try:
        e.add_dependency(TaskId("t2"), TaskId("t1"))
        assert False, "expected cycle rejection"
    except ValueError:
        pass


def test_remove_dependency():
    e = _engine()
    e.assign_task(TaskId("t1"), Spec("a", ()), AgentId("d"))
    e.assign_task(TaskId("t2"), Spec("b", ()), AgentId("d"))
    e.wait_idle()
    e.add_dependency(TaskId("t1"), TaskId("t2"))
    assert len(e.get_dependencies()) == 1
    e.remove_dependency(TaskId("t1"), TaskId("t2"))
    assert len(e.get_dependencies()) == 0


def test_dependency_endpoints():
    e = _engine()
    e.assign_task(TaskId("t1"), Spec("a", ()), AgentId("d"))
    e.assign_task(TaskId("t2"), Spec("b", ()), AgentId("d"))
    e.wait_idle()
    c = _client(e)
    r = c.post("/api/run/add_dependency", json={"from_id": "t1", "to_id": "t2"})
    assert r.status_code == 200 and r.json()["ok"] is True
    r = c.post("/api/run/add_dependency", json={"from_id": "t2", "to_id": "t1"})
    assert r.status_code == 422  # cycle → ValueError
    r = c.post("/api/run/remove_dependency", json={"from_id": "t1", "to_id": "t2"})
    assert r.status_code == 200 and r.json()["ok"] is True
    assert len(e.get_dependencies()) == 0


# === Item 3: audit carries who/why ===

def test_audit_carries_source_and_reason():
    e = _engine()
    c = _client(e)
    c.post("/api/run/create_task", json={"task_id": "t1", "spec": {"description": "x"}, "assignee": "dev"})
    c.post("/api/run/signal", json={"task_id": "t1", "signal": "ACCEPT", "source": "dev", "reason": "looks good"})
    audit = c.get("/api/audit?task_id=t1").json()
    accepts = [a for a in audit if a["signal"] == "ACCEPT"]
    assert accepts and accepts[-1]["source"] == "dev"
    assert accepts[-1]["reason"] == "looks good"


# === Item 4: predictability via API ===

def test_create_task_structured_accepted_risks():
    c = _client(_engine())
    r = c.post("/api/run/create_task", json={
        "task_id": "t1", "assignee": "d",
        "spec": {"description": "x", "accepted_risks": [
            {"item": "rare outage", "predictability": "STATISTICAL", "justification": "P<1%"},
        ]},
    })
    assert r.status_code == 200
    # dict-form ACCEPTED_RISKS is accepted (structured parse doesn't crash); the item is extracted
    assert r.json()["accepted_risks"] == ["rare outage"]


def test_plain_string_accepted_risks_still_accepted():
    c = _client(_engine())
    r = c.post("/api/run/create_task", json={
        "task_id": "t1", "assignee": "d",
        "spec": {"description": "x", "accepted_risks": ["legacy text"]},
    })
    assert r.status_code == 200
    assert r.json()["accepted_risks"] == ["legacy text"]


# === Item 5: per-role actions ===

def test_available_actions_by_role():
    e = _engine()
    # root task: assignee = executor
    e.assign_task(TaskId("t1"), Spec("x", ()), AgentId("dev"))
    e.wait_idle()  # now in OFFERED
    exec_actions = e.available_actions(TaskId("t1"), AgentId("dev"))
    assert Signal.ACCEPT in exec_actions  # executor can accept in OFFERED
    assert Signal.PASS not in exec_actions  # PASS is an issuer signal


def test_actions_endpoint():
    e = _engine()
    e.assign_task(TaskId("t1"), Spec("x", ()), AgentId("dev"))
    e.wait_idle()
    c = _client(e)
    r = c.get("/api/tasks/t1/actions?role=dev")
    assert r.status_code == 200
    names = [a["signal"] for a in r.json()]
    assert "ACCEPT" in names
    assert "TIMEOUT" not in names  # system signal never offered


# === Dep glue (anti-mock truth-maker) + ACCEPTED_RISKS invalidation ===

def test_dep_glue_persists_and_checks():
    from gfso.core.types import Criteria, CriterionMapping
    from gfso.core.handlers.structural import check_anti_mock
    e = _engine()
    e.assign_task(TaskId("p"), Spec("p", (Criteria("c", "x"),)), AgentId("pm"))
    e.wait_idle()
    e.decompose_task(TaskId("p"), [
        (TaskId("a"), Spec("a", ()), AgentId("d1")),
        (TaskId("b"), Spec("b", ()), AgentId("d2")),
    ], criterion_mappings=[CriterionMapping("c", TaskId("a"))])
    e.wait_idle()
    children = e.get_children(TaskId("p"))
    # seam with no glue → anti-mock FAIL
    e.add_dependency(TaskId("b"), TaskId("a"))
    assert not check_anti_mock(children, e.get_dependencies()).passed
    # seam with glue → PASS
    e.remove_dependency(TaskId("b"), TaskId("a"))
    e.add_dependency(TaskId("b"), TaskId("a"), glue="b reads a's output total; breaks if total is gross not net")
    assert check_anti_mock(children, e.get_dependencies()).passed
    assert e.get_dependencies()[0].glue.startswith("b reads")


def test_projection_shows_glue_and_invalidation():
    from gfso.core.types import Criteria, CriterionMapping, AcceptedRiskItem, Predictability
    e = _engine()
    e.assign_task(
        TaskId("p"),
        Spec("p", (Criteria("c", "x"),),
             (AcceptedRiskItem("fx rates", Predictability.STATISTICAL, "external", "if multi-currency added"),)),
        AgentId("pm"),
    )
    e.wait_idle()
    e.decompose_task(TaskId("p"), [
        (TaskId("a"), Spec("a", ()), AgentId("d1")),
        (TaskId("b"), Spec("b", ()), AgentId("d2")),
    ], criterion_mappings=[CriterionMapping("c", TaskId("a"))])
    e.wait_idle()
    e.add_dependency(TaskId("b"), TaskId("a"), glue="net total must be event-time")
    md = e.project(TaskId("p"))
    assert "glue (what must match" in md and "net total must be event-time" in md
    assert "invalidation: if multi-currency added" in md
    assert "CHECK-1c:anti_mock" in md


# === Read-projection (critic input contract) ===

def test_projection_renders_decomposition():
    from gfso.core.types import Criteria, CriterionMapping
    e = _engine()
    e.assign_task(
        TaskId("p"),
        Spec("ship release", (Criteria("tested", "all tests pass"),), ("legacy browsers",)),
        AgentId("pm"),
    )
    e.wait_idle()
    e.decompose_task(
        TaskId("p"),
        [(TaskId("c1"), Spec("write tests", (Criteria("coverage", "coverage >= 80%"),)), AgentId("qa"))],
        criterion_mappings=[CriterionMapping("tested", TaskId("c1"))],
    )
    e.wait_idle()
    md = e.project(TaskId("p"))
    assert "# Decomposition under review — node `p`" in md
    assert "ship release" in md            # goal
    assert "tested" in md and "coverage" in md  # parent + child criteria
    assert "`c1`" in md                    # subtask
    assert "tested** → c1" in md           # criterion coverage
    assert "legacy browsers" in md         # ACCEPTED_RISKS
    assert "CHECK-1:coverage" in md        # Solver results embedded


def test_projection_endpoint():
    e = _engine()
    e.assign_task(TaskId("p"), Spec("x", ()), AgentId("pm"))
    e.wait_idle()
    c = _client(e)
    r = c.get("/api/tasks/p/projection")
    assert r.status_code == 200
    assert r.json()["node_id"] == "p"
    assert "Decomposition under review" in r.json()["projection"]
    assert c.get("/api/tasks/nope/projection").status_code == 404


# === Item 6: solver split (deterministic) ===

def test_solver_reports_failed_checks():
    e = _engine()
    # parent with a criterion but a decomposition that fails coverage
    e.assign_task(TaskId("p"), Spec("p", (), ()), AgentId("pm"))
    e.wait_idle()
    e.decompose_task(TaskId("p"), [(TaskId("c1"), Spec("c", ()), AgentId("d"))])
    e.wait_idle()
    c = _client(e)
    r = c.get("/api/tasks/p/solver")
    assert r.status_code == 200
    # all solver items are deterministic check findings
    for item in r.json()["recommendations"]:
        assert item["kind"] == "solver"
        assert item["check"]
