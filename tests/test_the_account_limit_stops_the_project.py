"""The account's limit window is a stop in substance (docs/notes/PROJECT_CLOCK.md, case 10): under AUTO every call is
refused, nobody can move, and the bounds ran on — so the system stops the project itself, through the one carrier a stop
already is, and starts it again when the limit lifts. And a date shown at a door during a stop round-trips exactly:
the off time a door converts with stands still while the project does."""
from __future__ import annotations

import io
import json
import time
from datetime import datetime, timedelta

import gfso.core.graph.model as M
import gfso.tools as T
from gfso.adapters import execution as E
from gfso.adapters.llm import headless as H
from gfso.adapters.storage.sqlite import SqliteStorage
from gfso.core.types import TaskId
from gfso.issuer import LIMIT_RETRY_S
from tests.support import criterion, make_engine

LIFT = 1791954000
#: The stream the CLI wrote for a refused call (agent trace 20261013T190621-25f01028, trimmed).
LIMIT_STREAM = [
    {"type": "rate_limit_event", "rate_limit_info": {"status": "rejected", "resetsAt": LIFT, "rateLimitType": "seven_day"}},
    {"type": "assistant", "message": {"model": "<synthetic>", "content": [{"type": "text", "text": "You've hit your limit"}]},
     "error": "rate_limit", "api_error": "usage_limit_reached",
     "api_error_params": {"rate_limit_info": {"status": "rejected", "resetsAt": LIFT}}},
    {"type": "result", "is_error": True, "subtype": "success", "terminal_reason": "api_error", "api_error_status": 429,
     "api_error": "usage_limit_reached", "result": "You've hit your monthly spend limit"}]
REFUSED = "api_error: usage_limit_reached: You've hit your session limit"


class _Proc:
    stdin = io.StringIO()

    def __init__(self, lines):
        self.stdout = iter(json.dumps(x) + "\n" for x in lines)

    def wait(self, timeout=None):
        return 0


def _refused(at=None) -> list:
    return [{"error": REFUSED, "ended": "limit", **({"limit_resets_at": at} if at else {})}]


def test_the_adapter_reads_when_the_limit_lifts(monkeypatch, tmp_path):
    monkeypatch.setattr(H.subprocess, "Popen", lambda args, **kw: _Proc(LIMIT_STREAM))
    for name in ("adopt", "kill_tree", "release"):
        monkeypatch.setattr(E, name, lambda p: p)
    llm = H.ClaudeCodeProvider()
    llm._cmd = "claude"
    assert llm.run_agent("sys", "packet", ("Read",), cwd=str(tmp_path)) == ""
    assert llm.calls[-1]["ended"] == "limit" and llm.calls[-1]["limit_resets_at"] == LIFT, llm.calls[-1]
    monkeypatch.setattr(H.subprocess, "Popen", lambda args, **kw: _Proc(LIMIT_STREAM[2:]))
    llm.run_agent("sys", "packet", ("Read",), cwd=str(tmp_path))
    assert llm.calls[-1].get("limit_resets_at") is None, "a lift time of an earlier call leaked into this one"


def test_a_refused_call_stops_the_project_until_the_limit_lifts():
    e = make_engine(llm=None)
    lift = time.time() + 3600
    e.record_llm_usage("executor", _refused(lift), TaskId("n"))
    stop = e.paused()
    assert stop and stop["until"] >= lift and "usage limit" in stop["why"] and "executor" in stop["why"], stop
    e.lift_the_system_stop(lift - 1)
    assert e.paused(), "started before the limit lifted"
    e.lift_the_system_stop(stop["until"])
    assert e.paused() is None, "the system did not start what it stopped"


def test_with_no_lift_time_known_the_limit_is_probed_after_the_retry_wait():
    e = make_engine(llm=None)
    t0 = time.time()
    e.record_llm_usage("validator", _refused(), TaskId("n"))
    assert t0 + LIMIT_RETRY_S <= e.paused()["until"] <= time.time() + LIMIT_RETRY_S + 60


def test_a_persons_stop_is_never_started_by_the_system_and_a_persons_start_is_honoured():
    e = make_engine(llm=None)
    e.pause("alice", "mine")
    e.record_llm_usage("executor", _refused(time.time()), TaskId("n"))
    e.lift_the_system_stop(time.time() + 10 ** 6)
    assert e.paused()["by"] == "alice", "the system took over a person's stop"
    e.resume("alice")
    e.record_llm_usage("executor", _refused(time.time()), TaskId("n"))
    e.pause("alice", "mine, over the limit's")                 # a person's stop over the system's is the person's
    e.lift_the_system_stop(time.time() + 10 ** 6)
    assert e.paused()["by"] == "alice", "the system started a stop a person had made over its own"
    e.resume("alice")
    assert e.paused() is None


def test_the_start_is_rearmed_from_the_stop_record_after_a_restart(tmp_path):
    db = str(tmp_path / "p.db")
    e = make_engine(storage=SqliteStorage(db), llm=None)
    e.record_llm_usage("executor", _refused(time.time() - 120), TaskId("n"))     # lifted while the server was down
    assert e.paused()
    e = make_engine(storage=SqliteStorage(db), llm=None, check_interval=0.1)
    e.start()
    t0 = time.time()
    while e.paused() and time.time() - t0 < 5:
        time.sleep(0.1)
    assert e.paused() is None, "a restarted engine never started the project the limit had stopped"
    e.stop()


def test_a_date_shown_during_a_stop_comes_back_as_it_was(monkeypatch):
    """Case (b): project time stands while the wall runs, so a deadline shown at a door grew every tick, and a client
    feeding it back (a re-admission of an unchanged child) had it taken off with a larger off — read as changed."""
    shift = {"s": 0.0}
    monkeypatch.setattr(M, "time", type("T", (), {"time": staticmethod(lambda: time.time() + shift["s"])}))
    e = make_engine(llm=None, validate_signals=True, state_timeout=0, check_interval=3600)
    e.start()
    due = (datetime.now() + timedelta(hours=2)).replace(microsecond=0)
    T.create_task(e, "d", {"description": "x", "criteria": [criterion("a", "A")]}, "w", deadline=due.isoformat())
    e.wait_idle()
    inside = e.graph.get_task(TaskId("d")).deadline
    e.pause("the-user", "")
    shift["s"] = 10.0
    shown = T.task_out(e.graph.get_task(TaskId("d")), e)["deadline"]
    shift["s"] = 100.0
    assert abs((T._deadline(shown, e.graph) - inside).total_seconds()) < 1e-3, "the round trip moved the date"
    assert abs((datetime.fromisoformat(shown) - due).total_seconds()) < 1, "a date read differently once stopped"
    e.resume("the-user")
    e.stop()


def test_a_round_the_limit_refused_comes_back_at_the_lift_not_on_its_own_timer():
    """A round given back on a fixed LIMIT_RETRY_S after a lift due sooner would spend project time with nobody moving
    (critic, 2026-10-26: up to ~570 s); it waits exactly until the system's limit stop lifts."""
    e = make_engine(llm=None)
    assert e.stop_wait_s() is None                            # no limit stop: each door keeps its own pace
    e.record_llm_usage("executor", _refused(time.time() + 120), TaskId("n"))
    assert 120 < e.stop_wait_s() < 200 < LIMIT_RETRY_S
