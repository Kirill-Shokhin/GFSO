"""The user's STOP on a project's run and the TECH REPORT channel.

A stop is the user's act on the run, not a protocol move: the system starts no new session of any role, the sessions
already running finish and their signals land, the clock fires no timeout — and nothing in the graph changes, while its
time is left off the project's clocks: no party could move in it, so no bound runs out in it (`project_now`). The run has ONE state, read off the stop and
the work in flight: `running` → `stopping` (who still works) → `stopped`. A tech report is about the system, not the
task: filed by any role, it moves nothing and no packet reads it back."""
from __future__ import annotations

import queue
import threading
import time

import gfso.engine.loop as L
import gfso.tools as T
import gfso.tools_llm as TL
from gfso.core.types import TaskId
from gfso.delegate import Dispatcher
from gfso.inflight import _inflight
from gfso.packets import _executor_packet, file_tech_reports
from datetime import datetime, timedelta

from gfso.adapters.storage.memory import MemoryStorage
from gfso.core.graph.model import CLOCK_BEAT_KEY, clock_off_s, keep_off, project_now
from tests.support import criterion, make_engine
from tests.test_a_cut_call_does_not_spend_the_nodes_retry import _an_offer
from tests.test_delegate import _agents
from tests.test_ports_runtime import _await_state, _mk


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


def test_a_stop_leaves_its_time_off_the_clocks_so_no_bound_runs_out_in_it():
    """Measured: a row stopped 6.5 h woke with every work node ESCALATED, an extension spent on each — on time nobody
    could work in. The bound counts the time the project runs: past it on the wall, inside the stop, it has not run out;
    running again, it does."""
    e = make_engine(llm=None, validate_signals=True, check_interval=0.1, state_timeout=1.5)
    e.start()
    _mk(e)
    e.pause("the-user", "")
    time.sleep(2.5)
    e.resume("the-user")
    time.sleep(0.4)
    assert e.graph.get_state(TaskId("n")).name == "OFFERED", "the stop's time ran the bound out"
    assert _await_state(e, "n", {"ESCALATED", "CANCELLING", "ABANDONED"}, timeout=5) != "OFFERED", "running, it ends"
    e.stop()


def test_time_no_engine_ticked_over_a_project_is_left_off_its_clocks_once():
    """A server down, a host asleep, a project not loaded: the gap since its last beat is left off at the engine's start
    — once: not again by an engine started seconds later (the beat is kept at the start), and once with a stop standing
    over it (no second carrier for the same seconds)."""
    for stopped in (False, True):
        gone = MemoryStorage()
        gone.store_setting(CLOCK_BEAT_KEY, str(time.time() - 3600))
        e = make_engine(storage=gone, llm=None, check_interval=0.1)
        if stopped:
            e.pause("the-user", "")
        e.start()
        assert abs(clock_off_s(e.graph) - 3600) < 2
        assert abs((datetime.now() - project_now(e.graph)).total_seconds() - clock_off_s(e.graph)) < 1
        e.resume("the-user")
        e.stop()
        again = make_engine(storage=gone, llm=None, check_interval=0.1)
        again.start()
        assert abs(clock_off_s(again.graph) - 3600) < 2, "a gap was counted twice"
        again.stop()


class _Gate:
    """A clock port the test ticks by hand."""
    def __init__(self):
        self.ev = threading.Semaphore(0)

    def now(self):
        return time.time()

    def wait(self, _s):
        self.ev.acquire()


def test_a_host_asleep_around_a_stop_or_a_start_is_off_once(monkeypatch):
    """The click right after a wake, before the next tick (critic over the clock, round 2): stopped before the sleep
    and started after it was counted twice; running before it and stopped after it, not at all."""
    shift = {"s": 0.0}
    monkeypatch.setattr(L, "time", type("T", (), {"time": staticmethod(lambda: time.time() + shift["s"])}))
    for before, after in (("stopped", "start"), ("running", "stop")):
        e = make_engine(llm=None)
        gate, halt = _Gate(), threading.Event()
        if before == "stopped":
            e.pause("u", "")
        shift["s"] = -3600.0                                 # the last tick: an hour ago on the wall
        th = threading.Thread(target=L.timeout_monitor, args=(e.graph, queue.Queue(), 10.0, halt, None, gate),
                              daemon=True)
        th.start()
        time.sleep(0.2)
        e.resume("u") if after == "start" else e.pause("u", "")
        shift["s"] = 0.0
        gate.ev.release()
        time.sleep(0.3)
        halt.set()
        gate.ev.release()
        th.join(2)
        assert abs(clock_off_s(e.graph) - 3600) < 15, (before, after, clock_off_s(e.graph))


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


def test_outside_a_deadline_reads_as_the_walls_and_a_typed_one_is_put_on_the_projects_clocks():
    """Inside, every deadline is on the project's clocks; at the doors it is the wall's both ways — a date a person
    types reads back as typed, and stands as live as the wall says it is."""
    e = make_engine(llm=None, validate_signals=True, state_timeout=0)
    e.start()
    keep_off(e.graph, 3600)
    due = (datetime.now() + timedelta(hours=2)).replace(microsecond=0)
    T.create_task(e, "d", {"description": "x", "criteria": [criterion("a", "A")]}, "w", deadline=due.isoformat())
    e.wait_idle()
    assert T.task_out(e.graph.get_task(TaskId("d")), e)["deadline"] == due.isoformat()
    reply = T.revise(e, "d", deadline=due.isoformat(), agent="w")       # a date copied from a reply, fed back
    assert reply["deadline"] == due.isoformat(), "a reply read on the project's clock shortened the date fed back"
    inside = e.graph.get_task(TaskId("d")).deadline
    assert abs((due - inside).total_seconds() - 3600) < 1 and inside > project_now(e.graph)
    e.stop()


def test_a_bound_read_between_two_ticks_already_sees_the_sleep_off():
    """Right after a wake, before the next tick, a delivery read its deadline against the whole sleep and escalated the
    node (critic over the clock, r3): the time pending since the last beat is off by the same rule, for every reader."""
    e = make_engine(llm=None)                       # not started: no monitor ticks over it
    e.graph.store_setting(CLOCK_BEAT_KEY, str(time.time() - 3600))
    assert abs(clock_off_s(e.graph) - 3600) < 2
    e.pause("the-user", "")
    e.graph.store_setting(CLOCK_BEAT_KEY, str(time.time() - 5))
    assert 4 < clock_off_s(e.graph) < 7, "under a stop every pending second is off"
