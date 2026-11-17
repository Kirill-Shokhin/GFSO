"""A project sets for itself how long its waiting states wait and how many rework rounds a node gets — the
canon fixes neither (§12.16: the bound values lie outside conformance; §12.15: max_iterations is the issuer's forecast),
and they differ by who waits: a run's validator answers in minutes, a person signing a stream in days.

They were the server's (`GFSO_BOUND_<STATE>`, one default rework bound), so a graph held by a person over weeks
escalated in an hour and was abandoned in a day on the same :8000 where runs need short waits (the author, 2026-11-12:
«с таймаутами … как и с количеством реворков. я всегда говорил что это вопрос проекта а никак не сервера»).
Inv-5 stays: a project may lengthen or shorten a bound, never remove one.
"""
import json
import time

import pytest

from gfso import tools_llm as TL
from gfso.adapters.llm.stub import StubLLM
from gfso.core.graph.model import project_max_iterations, project_state_bound
from gfso.core.types import AgentId, Criteria, CriterionMapping, Signal, SignalData, Spec, TaskId, DEFAULT_MAX_ITERATIONS
from tests.support import REGISTER_SPLIT, make_engine, pinned

SPEC = Spec("a wait", (Criteria("c", "C", check=pinned("c")),))


@pytest.fixture
def e():
    eng = make_engine(llm=StubLLM(), validate_signals=True, check_interval=0.05, state_timeout=0)
    eng.start()
    yield eng
    eng.stop()


def _bounds(e, **b):
    e.set_settings({"bounds": json.dumps(b)}, AgentId("user"))


def _route(e, tid):
    return [(a.old_state.name, a.new_state.name) for a in e.audit_log(TaskId(tid))
            if a.signal == Signal.TIMEOUT and not a.rejected]


def _wait(e, tid, name, timeout=6.0):
    t0 = time.time()
    while time.time() - t0 < timeout:
        if e.graph.get_state(TaskId(tid)).name == name:
            return True
        time.sleep(0.03)
    return False


def test_unset_the_server_decides(e, monkeypatch):
    monkeypatch.setenv("GFSO_BOUND_VALIDATING", "77")
    assert project_state_bound(e.graph, "VALIDATING") == 77
    assert project_max_iterations(e.graph) == DEFAULT_MAX_ITERATIONS


def test_the_projects_short_bound_fires(e):
    _bounds(e, OFFERED=0.3)
    e.assign_task(TaskId("n"), SPEC, AgentId("human"))
    assert _wait(e, "n", "ESCALATED") and _route(e, "n")[0] == ("OFFERED", "ESCALATED")


@pytest.mark.parametrize("own", [None, 7 * 86_400])
def test_the_projects_long_bound_holds_where_the_servers_would_fire(e, monkeypatch, own):
    monkeypatch.setenv("GFSO_BOUND_OFFERED", "0.3")
    if own:
        _bounds(e, OFFERED=own)
    e.assign_task(TaskId("n"), SPEC, AgentId("human"))
    fired = _wait(e, "n", "ESCALATED", timeout=1.5)
    assert fired is (own is None), "the server's short bound fires only where the project sets none"


def test_the_door_refuses_an_unbounded_or_misplaced_bound(e):
    for bad in ({"OFFERED": 0}, {"VALIDATING": -5}, {"ESCALATED": float("inf")}, {"VALIDATING": float("nan")}, {"CANCELLING": 10 ** 400}, {"BLOCKED": 365 * 86_400 + 1}, {"EXECUTING": 3600}, {"IDLE": 60}, {"OFFERED": True},
                {"OFFERED": "1d"}, [("OFFERED", 60)]):
        got = TL.set_mode(e, bounds=bad)
        assert got.get("refused"), bad
    assert "deadline_s" in TL.set_mode(e, bounds={"REWORKING": 60})["error"], "the work states point at the deadline"
    for bad in (0, -1, True, 2.5, 1_001, 10 ** 19):
        assert TL.set_mode(e, max_iterations=bad).get("refused"), bad
    got = TL.set_mode(e, bounds={"VALIDATING": 604_800, "ESCALATED": 1_209_600}, max_iterations=5)
    assert not got.get("refused"), got
    assert e.settings()["bounds"] == {"VALIDATING": 604_800, "ESCALATED": 1_209_600}
    assert e.settings()["max_iterations"] == 5
    assert project_state_bound(e.graph, "VALIDATING") == 604_800
    assert project_state_bound(e.graph, "CANCELLING") == 120, "a state the project leaves out keeps the server's"
    TL.set_mode(e, bounds={}, user_said="back to the server's")
    assert project_state_bound(e.graph, "VALIDATING") == 3_600


def test_a_node_issued_without_its_own_bound_gets_the_projects(e):
    e.set_settings({"max_iterations": 5}, AgentId("user"))
    e.assign_task(TaskId("p"), Spec("p", (Criteria("c", "C", check=pinned("c")),)), AgentId("pm"))
    e.wait_idle()
    e.decompose_task(TaskId("p"), [(TaskId("c1"), SPEC, AgentId("d"))], [CriterionMapping("c", TaskId("c1"))],
                     register=REGISTER_SPLIT)
    e.wait_idle()
    assert e.graph.get_task(TaskId("p")).max_iterations == 5
    assert e.graph.get_task(TaskId("c1")).max_iterations == 5
    e.decompose_task(TaskId("p"), [(TaskId("c2"), SPEC, AgentId("d"))], [CriterionMapping("c", TaskId("c1")),
                     CriterionMapping("c", TaskId("c2"))], max_iterations=2, register=REGISTER_SPLIT)
    e.wait_idle()
    assert e.graph.get_task(TaskId("c2")).max_iterations == 2, "the issuer's own bound wins over the project's"


def test_a_persons_week_to_sign_is_not_a_model_validators_process_cap(e):
    """VALIDATING's bound in a project is how long its issuer may take to sign; a model validator's process is the
    machine's, capped by the server's T_validate whatever the project waits (critic: a week-long hung validator)."""
    _bounds(e, VALIDATING=7 * 86_400)
    e.assign_task(TaskId("v"), SPEC, AgentId("human"))
    e.send_signal_sync(SignalData(signal=Signal.ACCEPT, task_id=TaskId("v"), source=AgentId("human")))
    e.send_signal_sync(SignalData(signal=Signal.DELIVER, task_id=TaskId("v"), source=AgentId("human"), result="done"))
    t = e.graph.get_task(TaskId("v"))
    assert t.state.name == "VALIDATING"
    assert TL._validation_cap(t, e.graph) <= 3_600
    e.send_signal_sync(SignalData(signal=Signal.FAIL, task_id=TaskId("v"), source=AgentId("human"), failed_criteria=["c"]))
    t = e.graph.get_task(TaskId("v"))
    assert t.state.name != "VALIDATING" and TL._validation_cap(t, e.graph) == 3_600, "out of VALIDATING too"
    assert project_state_bound(e.graph, "VALIDATING") == 7 * 86_400, "the wait itself is the project's"


def test_a_stored_value_the_clock_cannot_read_leaves_the_clock_running(e):
    """What the reader cannot hold as finite seconds is dropped, never raised into the monitor (critic: 10**400 stored
    killed the timeout thread, every wait in the project unbounded after it)."""
    e.graph.store_setting("bounds", '{"OFFERED": 0.3, "CANCELLING": 1' + "0" * 400 + "}")
    e.assign_task(TaskId("n"), SPEC, AgentId("human"))
    assert _wait(e, "n", "ESCALATED"), "the monitor still fires on the readable bound"


def test_a_standing_child_re_issued_keeps_its_own_bound(e):
    """A re-admission re-issuing a standing child does not undo its issuer's raised forecast (critic: the project's
    default overwrote it, in projects that set nothing too)."""
    e.assign_task(TaskId("p"), Spec("p", (Criteria("c", "C", check=pinned("c")),)), AgentId("pm"))
    e.wait_idle()
    m = [CriterionMapping("c", TaskId("c1"))]
    e.decompose_task(TaskId("p"), [(TaskId("c1"), SPEC, AgentId("d"))], m, register=REGISTER_SPLIT)
    e.wait_idle()
    e.revise(TaskId("c1"), SPEC, AgentId("pm"), max_iterations=30)
    e.wait_idle()
    assert e.graph.get_task(TaskId("c1")).max_iterations == 30
    e.decompose_task(TaskId("p"), [(TaskId("c1"), SPEC, AgentId("d2"))], m, register=REGISTER_SPLIT)
    e.wait_idle()
    t = e.graph.get_task(TaskId("c1"))
    assert t.assignee == "d2" and t.max_iterations == 30
