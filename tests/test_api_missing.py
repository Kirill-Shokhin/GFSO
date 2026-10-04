"""Tests for the completed API surface: deadline, Dep CRUD, audit who/why,
predictability, per-role actions, solver split. Engine + HTTP (via /api/run)."""
from datetime import datetime, timedelta

from fastapi.testclient import TestClient

from gfso.engine import Engine
from gfso.adapters.llm.stub import StubLLM
from gfso.api.server import create_app
from gfso.core.types import (TaskId, AgentId, Spec, Signal, SignalData, Criteria, CriterionMapping,
                             AcceptedRiskItem, Predictability, Register)
from tests.support import REGISTER_SPLIT, criterion, make_engine, pinned
from gfso.core.handlers.structural import check_anti_mock


def _engine() -> Engine:
    e = make_engine(llm=StubLLM(), validate_signals=False)
    e.start()
    return e


def _client(e: Engine) -> TestClient:
    return TestClient(create_app(e))


# === Item 1: deadline ===

def test_assign_task_sets_deadline():
    e = _engine()
    dl = datetime.now() + timedelta(days=3)
    e.assign_task(TaskId("t1"), Spec("x", (Criteria("c", "C", check=pinned("c")),)), AgentId("d"), deadline=dl)
    e.wait_idle()
    assert e.graph.get_task(TaskId("t1")).deadline == dl


def test_create_task_deadline_via_api():
    dl = (datetime.now() + timedelta(days=2)).isoformat()
    e = _engine()
    c = _client(e)
    r = c.post("/api/run/create_task", json={
        "task_id": "t1", "spec": {"description": "x", "criteria": [criterion("c", "C")]}, "assignee": "d", "deadline": dl,
    })
    assert r.status_code == 200
    # create_task's tool dict omits deadline; verify the ISO deadline round-tripped into the engine
    assert e.graph.get_task(TaskId("t1")).deadline == datetime.fromisoformat(dl)


def test_decompose_per_child_deadline():
    e = _engine()
    e.assign_task(TaskId("p"), Spec("p", (Criteria("c", "C", check=pinned("c")),)), AgentId("pm"))
    e.wait_idle()
    dl = datetime.now() + timedelta(hours=12)       # inside the parent's default (§11.5 item (6))
    e.decompose_task(TaskId("p"), [(TaskId("c1"), Spec("c", (Criteria("c", "C", check=pinned("c")),)), AgentId("d"), dl)], register=REGISTER_SPLIT)
    assert e.graph.get_task(TaskId("c1")).deadline == dl


# === Item 2: dependency CRUD + cycle rejection ===

def test_declared_cycle_rejected():
    e = _engine()
    e.assign_task(TaskId("goal"), Spec("the goal", (Criteria("c", "C", check=pinned("c")),)), AgentId("d"))
    e.assign_task(TaskId("t1"), Spec("a", (Criteria("c", "C", check=pinned("c")),)), AgentId("d"), parent_id=TaskId("goal"))
    e.assign_task(TaskId("t2"), Spec("b", (Criteria("c", "C", check=pinned("c")),)), AgentId("d"), parent_id=TaskId("goal"))
    e.wait_idle()
    e.add_dependency(TaskId("t1"), TaskId("t2"))
    try:
        e.add_dependency(TaskId("t2"), TaskId("t1"))
        assert False, "expected cycle rejection"
    except ValueError:
        pass


def test_remove_dependency():
    e = _engine()
    e.assign_task(TaskId("goal"), Spec("the goal", (Criteria("c", "C", check=pinned("c")),)), AgentId("d"))
    e.assign_task(TaskId("t1"), Spec("a", (Criteria("c", "C", check=pinned("c")),)), AgentId("d"), parent_id=TaskId("goal"))
    e.assign_task(TaskId("t2"), Spec("b", (Criteria("c", "C", check=pinned("c")),)), AgentId("d"), parent_id=TaskId("goal"))
    e.wait_idle()
    e.add_dependency(TaskId("t1"), TaskId("t2"))
    assert len(e.get_dependencies()) == 1
    e.remove_dependency(TaskId("t1"), TaskId("t2"))
    assert len(e.get_dependencies()) == 0


def test_dependency_endpoints():
    e = _engine()
    e.assign_task(TaskId("goal"), Spec("the goal", (Criteria("c", "C", check=pinned("c")),)), AgentId("d"))
    e.assign_task(TaskId("t1"), Spec("a", (Criteria("c", "C", check=pinned("c")),)), AgentId("d"), parent_id=TaskId("goal"))
    e.assign_task(TaskId("t2"), Spec("b", (Criteria("c", "C", check=pinned("c")),)), AgentId("d"), parent_id=TaskId("goal"))
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
    c.post("/api/run/create_task", json={"task_id": "t1", "spec": {"description": "x", "criteria": [criterion("c", "C")]}, "assignee": "dev"})
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
        "spec": {"description": "x", "criteria": [criterion("c", "C")], "accepted_risks": [{"item": "rare outage", "predictability": "STATISTICAL", "justification": "P<1%", "p": 0.01, "impact": "the run stops and is resumed", "invalidation_condition": "one occurs"}]},
    })
    assert r.status_code == 200
    # dict-form ACCEPTED_RISKS is accepted (structured parse doesn't crash); the item is extracted — as the packet's
    # pre-fill, task data, not the split's register (canon v4.1 §9.2: a leaf has none)
    assert [n["item"] for n in r.json().get("prefilled_accepted_risks", [])] == ["rare outage"]
    assert r.json()["accepted_risks"] == []


def test_plain_string_accepted_risks_still_accepted():
    c = _client(_engine())
    r = c.post("/api/run/create_task", json={
        "task_id": "t1", "assignee": "d",
        "spec": {"description": "x", "criteria": [criterion("c", "C")], "accepted_risks": ["legacy text"]},
    })
    assert r.status_code == 200
    assert [n["item"] for n in r.json().get("prefilled_accepted_risks", [])] == ["legacy text"]   # §9.2: task data


# === Item 5: per-role actions ===

def test_available_actions_by_role():
    e = _engine()
    # root task: assignee = executor
    e.assign_task(TaskId("t1"), Spec("x", (Criteria("c", "C", check=pinned("c")),)), AgentId("dev"))
    e.wait_idle()  # now in OFFERED
    exec_actions = e.available_actions(TaskId("t1"), AgentId("dev"))
    assert Signal.ACCEPT in exec_actions  # executor can accept in OFFERED
    assert Signal.PASS not in exec_actions  # PASS is an issuer signal


def test_actions_endpoint():
    e = _engine()
    e.assign_task(TaskId("t1"), Spec("x", (Criteria("c", "C", check=pinned("c")),)), AgentId("dev"))
    e.wait_idle()
    c = _client(e)
    r = c.get("/api/tasks/t1/actions?role=dev")
    assert r.status_code == 200
    names = r.json()["actions"]   # the verb's answer (D-F16)
    assert "ACCEPT" in names
    assert "TIMEOUT" not in names  # system signal never offered


def test_the_actions_door_lists_only_what_the_machine_takes():
    """The HTTP door listed the FSM's set, so a delivered seam offered PASS with no verdict on the record — which
    the machine refuses (§10.3). It reads `Engine.refusal_for`, as the tool surface does (ortho audit, D-F1)."""
    e = _engine()
    e.assign_task(TaskId("t1"), Spec("x", (Criteria("c", "x", check=pinned("c")),)), AgentId("dev"))
    e.wait_idle()
    for sig in (Signal.ACCEPT, Signal.DELIVER):
        e.send_signal_sync(SignalData(
            signal=sig, task_id=TaskId("t1"), source=AgentId("dev"), result="done"))
    assert e.graph.get_state(TaskId("t1")).name == "VALIDATING"
    names = _client(e).get("/api/tasks/t1/actions").json()["actions"]
    assert "FAIL" in names and "PASS" not in names, names


# === Dep glue (anti-mock truth-maker) + ACCEPTED_RISKS invalidation ===

def test_dep_glue_persists_and_checks():
    e = _engine()
    e.assign_task(TaskId("p"), Spec("p", (Criteria("c", "x", check=pinned("c")),)), AgentId("pm"))
    e.wait_idle()
    e.decompose_task(TaskId("p"), [
        (TaskId("a"), Spec("a", (Criteria("c", "C", check=pinned("c")),)), AgentId("d1")),
        (TaskId("b"), Spec("b", (Criteria("c", "C", check=pinned("c")),)), AgentId("d2")),
    ], criterion_mappings=[CriterionMapping("c", TaskId("a"))], register=REGISTER_SPLIT)
    e.wait_idle()
    children = e.graph.get_children(TaskId("p"))
    # seam with no glue → anti-mock FAIL
    e.add_dependency(TaskId("b"), TaskId("a"))
    assert not check_anti_mock(children, e.get_dependencies()).passed
    # seam with glue → PASS
    e.remove_dependency(TaskId("b"), TaskId("a"))
    e.add_dependency(TaskId("b"), TaskId("a"), glue="b reads a's output total; breaks if total is gross not net")
    assert check_anti_mock(children, e.get_dependencies()).passed
    assert e.get_dependencies()[0].glue.startswith("b reads")


def test_projection_shows_glue_and_invalidation():
    e = _engine()
    e.assign_task(TaskId("p"), Spec("p", (Criteria("c", "x", check=pinned("c")),)), AgentId("pm"))
    e.wait_idle()
    # the invalidation condition is the split's register's, written with it (canon v4.1 §9.2), not the packet's
    fx = AcceptedRiskItem("fx rates", Predictability.STATISTICAL, "external", "if multi-currency added")
    e.decompose_task(TaskId("p"), [
        (TaskId("a"), Spec("a", (Criteria("c", "C", check=pinned("c")),)), AgentId("d1")),
        (TaskId("b"), Spec("b", (Criteria("c", "C", check=pinned("c")),)), AgentId("d2")),
    ], criterion_mappings=[CriterionMapping("c", TaskId("a"))], register=Register((fx,) + REGISTER_SPLIT.items))
    e.wait_idle()
    e.add_dependency(TaskId("b"), TaskId("a"), glue="net total must be event-time")
    md = e.project(TaskId("p"))
    assert "glue (what must match" in md and "net total must be event-time" in md
    assert "invalidation: if multi-currency added" in md
    assert "CHECK-1c:anti_mock" in md


# === Read-projection (critic input contract) ===

def test_projection_renders_decomposition():
    e = _engine()
    e.assign_task(
        TaskId("p"),
        Spec("ship release", (Criteria("tested", "all tests pass", check=pinned("tested")),)),
        AgentId("pm"),
    )
    e.wait_idle()
    e.decompose_task(
        TaskId("p"),
        [(TaskId("c1"), Spec("write tests", (Criteria("coverage", "coverage >= 80%", check=pinned("coverage")),)), AgentId("qa"))],
        criterion_mappings=[CriterionMapping("tested", TaskId("c1"))],
        register=Register(("legacy browsers",) + REGISTER_SPLIT.items)   # the split's, §9.2
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
    e.assign_task(TaskId("p"), Spec("x", (Criteria("c", "C", check=pinned("c")),)), AgentId("pm"))
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
    e.assign_task(TaskId("p"), Spec("p", (Criteria("c", "C", check=pinned("c")),), ()), AgentId("pm"))
    e.wait_idle()
    e.decompose_task(TaskId("p"), [(TaskId("c1"), Spec("c", (Criteria("c", "C", check=pinned("c")),)), AgentId("d"))], register=REGISTER_SPLIT)
    e.wait_idle()
    c = _client(e)
    r = c.get("/api/tasks/p/solver")
    assert r.status_code == 200
    # all solver items are deterministic check findings
    for item in r.json()["recommendations"]:
        assert item["kind"] == "solver"
        assert item["check"]
