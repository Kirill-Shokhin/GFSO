"""The user's STOP on a project's run and the TECH REPORT channel.

A stop is the user's act on the run, not a protocol move: the system starts no new session of any role, the sessions
already running finish and their signals land, the clock fires no timeout — and nothing in the graph changes, so a
bound passed while stopped fires on the first tick after the start (§12.2). The run has ONE state, read off the stop and
the work in flight: `running` → `stopping` (who still works) → `stopped`. A tech report is about the system, not the
task: filed by any role, it moves nothing and no packet reads it back."""
from __future__ import annotations

import time

import gfso.tools as T
import gfso.tools_llm as TL
from gfso.core.types import TaskId
from gfso.delegate import Dispatcher
from gfso.inflight import _inflight
from gfso.packets import _executor_packet, file_tech_reports
from tests.support import criterion, make_engine
from tests.test_a_cut_call_does_not_spend_the_nodes_retry import _an_offer
from tests.test_delegate import _agents
from tests.test_ports_runtime import FakeClock, _await_state, _mk


def test_a_stopped_project_starts_no_session_and_a_running_one_still_lands(tmp_path):
    e = make_engine(validate_signals=True, state_timeout=0)
    e.start()
    agents = _agents(tmp_path, ("exec-1", "llm-executor"), ("val-1", "llm-validator"))
    _an_offer(e)
    runs = []
    d = Dispatcher(e, agents, runner=lambda *a: runs.append(1) or {"status": "unparsed"})
    TL.TOOLS["stop_project"](e, why="look at a bug", by="the-user")
    for _ in range(3):
        d.dispatch_once()
        time.sleep(0.3)
    assert not runs, "nothing new starts while the project is stopped"
    assert T.signal(e, "kid", "ACCEPT", "exec-1")["accepted"], "a session already running still lands its signal"
    TL.TOOLS["start_project"](e, by="the-user")
    for _ in range(3):
        d.dispatch_once()
        time.sleep(0.3)
    assert runs, "started again, the dispatcher spawns"
    e.stop()


def test_no_timeout_fires_while_stopped_and_a_passed_bound_fires_after_the_start():
    e = make_engine(llm=None, validate_signals=True, check_interval=1800, state_timeout=3600, clock=FakeClock())
    e.pause("the-user", "")
    e.start()
    _mk(e)
    time.sleep(0.5)
    assert e.graph.get_state(TaskId("n")).name == "OFFERED", "the clock waits with the run"
    e.resume("the-user")
    assert _await_state(e, "n", {"ESCALATED", "CANCELLING", "ABANDONED"}) != "OFFERED"
    e.stop()


def test_the_run_has_one_state_running_stopping_stopped():
    e = make_engine(validate_signals=True, state_timeout=0)
    assert TL.run_state(e)["state"] == "running"
    with _inflight("delegated_execution", e, "kid"):
        got = TL.TOOLS["stop_project"](e, why="w", by="u")
        assert got["state"] == "stopping" and [w["task_id"] for w in got["working"]] == ["kid"], got
        assert TL.TOOLS["next_steps"](e)["run"]["state"] == "stopping"
    assert TL.run_state(e)["state"] == "stopped"
    assert TL.TOOLS["start_project"](e, by="u")["state"] == "running"


def test_a_tech_report_is_filed_counted_and_read_back_into_no_packet():
    e = make_engine(validate_signals=True, state_timeout=0)
    e.start()
    T.create_task(e, "kid", {"description": "the work", "criteria": [criterion("k", "K")]}, "exec-1")
    e.wait_idle()
    file_tech_reports(e, {"status": "delivered", "summary": "s",
                          "tech_report": "the pinned check contradicts the contract"}, "executor", "exec-1", "kid")
    file_tech_reports(e, {"nodes": [{"task_id": "kid", "tech_report": "a tool cannot run"}]}, "scope-executor",
                      "exec-1", "root")
    file_tech_reports(e, {"status": "delivered", "summary": "s", "tech_report": "  "}, "executor", "exec-1", "kid")
    T.TOOLS["tech_report"](e, "the answer ignored what I showed", task_id="kid")
    got = T.TOOLS["tech_reports"](e)
    assert got["count"] == 3 and [r["role"] for r in got["reports"]] == ["executor", "scope-executor", "mcp"], got
    assert got["reports"][1]["node"] == "kid"
    packet = _executor_packet(e, e.graph.get_task(TaskId("kid")), None, [])
    assert "contradicts the contract" not in packet and "tool cannot run" not in packet
    e.stop()
