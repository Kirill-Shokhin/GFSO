"""The time a stop held is left off the project's clocks, so every live deadline reads that much later on the wall — and
the record says so (Thm 11: every decision has a record; §12.2: the deadline is never suspended). The shift is no
revision: no packet field moved, so the node keeps its version and the consent standing for it (Inv-1)."""
from __future__ import annotations

import sqlite3
import time
from datetime import datetime, timedelta

import gfso.driver as D
import gfso.engine.loop as L
import gfso.tools as T
from gfso.adapters.storage.memory import MemoryStorage
from gfso.adapters.storage.sqlite import SqliteStorage
from gfso.roster import AgentRegistry
from gfso.core.types import AgentId, Mode, TaskId
from gfso.core.graph.model import CLOCK_BEAT_KEY, clock_off_s, keep_off
from tests.support import criterion, make_engine
from tests.test_the_run_stops_and_starts import _Gate


def test_a_stop_lifted_on_a_system_carried_project_records_each_live_deadlines_shift():
    e = make_engine(validate_signals=True, state_timeout=0)
    e.start()
    T.create_task(e, "n", {"description": "x", "criteria": [criterion("a", "A")]}, "w")
    e.wait_idle()
    assert T.signal(e, "n", "ACCEPT", "w")["accepted"]
    e.set_mode(Mode.AUTO, None, AgentId("user"))      # the system carries the work: the stop holds the project's time
    assert e.system_carries_work()
    was = T.get_task(e, "n")["deadline"]
    e.stops.pause("the-user", "look at a bug")
    keep_off(e.graph, 3600)                     # an hour the stop held, left off as the monitor's ticks leave it
    e.stops.resume("the-user")
    got = T.get_task(e, "n")
    held = (datetime.fromisoformat(got["deadline"]) - datetime.fromisoformat(was)).total_seconds()
    assert abs(held - 3600) < 5, held
    moves = got.get("deadline_moves") or []
    assert len(moves) == 1, f"the deadline read {held:.0f} s later on the wall and no record says so: {got}"
    m = moves[0]
    assert (m["was"], m["now"]) == (was, got["deadline"]) and abs(m["held_s"] - 3600) < 5, m
    assert m["stopped_by"] == "the-user" and m["started_by"] == "the-user", m
    assert any(x["message"].startswith("n: ") and "deadline" in x["message"] for x in e.pipeline_log(about="n: ")), \
        "the feed says it on the node"
    assert e.graph.get_state(TaskId("n")).name == "EXECUTING", "the consented work goes on: nothing was re-offered"
    e.stop()


def test_the_systems_own_stop_lifting_by_itself_records_it_too_and_a_stop_that_held_nothing_records_nothing():
    e = make_engine(validate_signals=True, state_timeout=0)
    e.start()
    T.create_task(e, "n", {"description": "x", "criteria": [criterion("a", "A")]}, "w")
    e.wait_idle()
    e.set_mode(Mode.AUTO, None, AgentId("user"))
    e.stops.pause("the-user", "")
    e.stops.resume("the-user")
    assert e.stops.deadline_moves("n") == [], "a stop that held no time moves no deadline"
    e.stops.stop_for_the_limit("executor", time.time() - 60)
    keep_off(e.graph, 600)
    e.stops.lift_the_system_stop(time.time())
    assert not e.stops.paused()
    [m] = e.stops.deadline_moves("n")
    assert m["stopped_by"] == m["started_by"] == "system" and "limit" in m["why"] and abs(m["held_s"] - 600) < 5, m
    e.stop()


def _consented(storage=None, **kw):
    e = make_engine(storage=storage, validate_signals=True, state_timeout=0, **kw)
    e.start()
    T.create_task(e, "n", {"description": "x", "criteria": [criterion("a", "A")]}, "w")
    e.wait_idle()
    assert T.signal(e, "n", "ACCEPT", "w")["accepted"]
    e.set_mode(Mode.AUTO, None, AgentId("user"))
    return e


def test_a_server_down_left_off_at_the_engines_start_is_on_each_deadlines_record_once():
    """Case 2: the gap since the last beat is left off at the start; the record names the cause. With a stop standing
    across it, the stop's lift records it (case 3: one carrier) and the start records nothing."""
    for stopped in (False, True):
        kept = MemoryStorage()
        e = _consented(kept)
        if stopped:
            e.stops.pause("the-user", "")
        e.stop()
        kept.store_setting(CLOCK_BEAT_KEY, str(time.time() - 3600))
        again = make_engine(storage=kept, validate_signals=True, state_timeout=0)
        again.start()
        if stopped:
            assert again.stops.deadline_moves("n") == [], "the gap under a stop is the stop's, recorded at its lift"
            again.stops.resume("the-user")
        [m] = again.stops.deadline_moves("n")
        assert abs(m["held_s"] - 3600) < 5, m
        assert m["stopped_by"] == ("the-user" if stopped else "the server was down"), m
        assert stopped or any("the server was down" in x["message"] for x in again.pipeline_log(about="n: "))
        again.stop()


def test_a_graph_people_hold_runs_on_absolute_time_through_a_server_down_and_a_stop(monkeypatch):
    """The author, 2026-11-15: «там очевидно и часы вести не для кого». No mode, the node held by a person: an hour of
    the server down and half an hour of a person's stop leave nothing off its clocks and record nothing (§12.2)."""
    shift = {"s": 0.0}
    monkeypatch.setattr(L, "time", type("T", (), {"time": staticmethod(lambda: time.time() + shift["s"])}))
    kept = MemoryStorage()
    e = make_engine(storage=kept, validate_signals=True, state_timeout=0, check_interval=0.05)
    e.start()
    T.create_task(e, "n", {"description": "x", "criteria": [criterion("a", "A")]}, "w")
    e.wait_idle()
    e.stop()
    kept.store_setting(CLOCK_BEAT_KEY, str(time.time() - 3600))
    again = make_engine(storage=kept, validate_signals=True, state_timeout=0, check_interval=0.05)
    assert not again.system_carries_work()
    again.start()
    was = T.get_task(again, "n")["deadline"]
    again.stops.pause("the-user", "")
    shift["s"] = 1800.0                                  # half an hour under the stop, between two of its ticks
    time.sleep(0.3)
    again.stops.resume("the-user")
    time.sleep(0.2)
    got = T.get_task(again, "n")
    again.stop()
    assert clock_off_s(again.graph) < 1 and got["deadline"] == was, (clock_off_s(again.graph), was, got["deadline"])
    assert again.stops.deadline_moves("n") == [], again.stops.deadline_moves("n")


def test_two_engines_on_one_store_leave_each_held_second_off_once_and_record_it_once(tmp_path, monkeypatch):
    """A server and a stdio MCP process open one .db: each monitor measured its tick from its own last, so a 1800 s stop
    left 3600 s off and a host asleep was recorded twice (critic's probe). The gap is decided over the STORED beat."""
    shift = {"s": 0.0}
    monkeypatch.setattr(L, "time", type("T", (), {"time": staticmethod(lambda: time.time() + shift["s"])}))
    db = str(tmp_path / "one.db")
    a = _consented(SqliteStorage(db), check_interval=0.05)
    b = make_engine(storage=SqliteStorage(db), validate_signals=True, state_timeout=0, check_interval=0.05)
    b.start()
    time.sleep(0.2)
    a.stops.pause("the-user", "")
    shift["s"] = 1800.0                                  # half an hour under the stop, between two ticks of each
    time.sleep(0.4)
    a.stops.resume("the-user")
    time.sleep(0.2)
    shift["s"] = 1800.0 + 3600.0                         # …then the host sleeps an hour
    time.sleep(0.4)
    moves = a.stops.deadline_moves("n")
    a.stop(), b.stop()
    assert [m["stopped_by"] for m in moves] == ["the-user", "the host slept"], moves
    assert abs(moves[0]["held_s"] - 1800) < 5 and abs(moves[1]["held_s"] - 3600) < 5, moves


def test_the_cli_path_keeps_the_server_down_gap_of_a_project_a_registered_executor_holds(tmp_path, monkeypatch):
    """No mode, the live node a registered executor's: the system carries the work. The CLI opened the engine before
    anyone published the roster, read the node as a person's and let the server-down hour run on the wall."""
    for k, v in (("GFSO_DATA_DIR", tmp_path / "data"), ("GFSO_HOME", tmp_path), ("GFSO_AGENTS_PATH", tmp_path / "a.json"),
                 ("GFSO_DB_PATH", tmp_path / "data" / "gfso.db"), ("GFSO_STORAGE", "sqlite"), ("GFSO_LLM", "none")):
        monkeypatch.setenv(k, str(v))
    monkeypatch.delenv("GFSO_PROJECT", raising=False)
    AgentRegistry().register("x-exec", "llm-executor", workdir=str(tmp_path))
    e = make_engine(storage=SqliteStorage(str(tmp_path / "data" / "gfso.db")), validate_signals=True, state_timeout=0)
    e.start()
    T.create_task(e, "n", {"description": "x", "criteria": [criterion("a", "A")]}, "x-exec")
    e.wait_idle()
    e.stop()
    e.graph.store_setting(CLOCK_BEAT_KEY, str(time.time() - 3600))
    opened, real = [], D.build_engine_from_env
    monkeypatch.setattr(D, "build_engine_from_env", lambda **k: opened.append(real(**k)) or opened[-1])
    D._locally(T.TOOLS["get_task"], None, ["n"], {})
    [cli] = opened
    moves, off = cli.stops.deadline_moves("n"), clock_off_s(cli.graph)
    cli.stop()
    assert cli.system_carries_work() and abs(off - 3600) < 5, off
    assert [m["stopped_by"] for m in moves] == ["the server was down"], moves


def test_a_persons_stop_on_a_graph_people_hold_does_not_suspend_a_deadline(monkeypatch):
    """§12.2: the deadline runs across every state and is never suspended. On a graph people hold a stop stops the
    system's own spending, of which there is none — a deadline passing during it fires then, not at the Start."""
    e = make_engine(validate_signals=True, state_timeout=0, check_interval=0.05)
    e.start()
    due = (datetime.now() + timedelta(seconds=1)).isoformat(timespec="seconds")
    T.create_task(e, "n", {"description": "x", "criteria": [criterion("a", "A")]}, "w", deadline=due)
    e.wait_idle()
    assert not e.system_carries_work()
    e.stops.pause("the-user", "")
    deadline = time.time() + 5
    while e.graph.get_state(TaskId("n")).name == "OFFERED" and time.time() < deadline:
        time.sleep(0.05)
    st, stopped = e.graph.get_state(TaskId("n")).name, e.stops.paused()
    e.stop()
    assert stopped and st != "OFFERED", st


def test_a_start_or_a_stop_right_after_a_wake_records_the_sleep_once():
    """Before the next tick: a Start counted the sleep in the stop's held time and again as the host's; a Stop left it
    off and recorded it nowhere. Both keep the beat before they act (`keep_the_beat`)."""
    for stopped in (True, False):
        gate = _Gate()
        e = _consented(clock=gate)
        if stopped:
            e.stops.pause("the-user", "")
        e.graph.store_setting(CLOCK_BEAT_KEY, str(time.time() - 3600))   # the host slept an hour, no tick since
        e.stops.resume("the-user") if stopped else e.stops.pause("the-user", "")
        if not stopped:
            e.stops.resume("the-user")
        gate.ev.release()                                                   # …the monitor's next tick
        time.sleep(0.3)
        moves = e.stops.deadline_moves("n")
        off = clock_off_s(e.graph)
        e.stop()
        gate.ev.release()
        assert len(moves) == 1 and abs(moves[0]["held_s"] - 3600) < 5 and abs(off - 3600) < 5, (stopped, off, moves)
        assert moves[0]["stopped_by"] == ("the-user" if stopped else "the host slept"), moves


class _LockedOnce(MemoryStorage):
    """A store another writer holds past SQLite's busy timeout, once."""

    def __init__(self):
        super().__init__()
        self.armed = False

    def swap_settings(self, change):
        """Raises once when armed, as `database is locked` does."""
        if self.armed:
            self.armed = False
            raise sqlite3.OperationalError("database is locked")
        super().swap_settings(change)


def test_a_store_locked_at_a_tick_leaves_the_monitor_ticking():
    kept = _LockedOnce()
    e = _consented(kept, check_interval=0.05)
    kept.armed = True
    time.sleep(0.3)
    e.graph.store_setting(CLOCK_BEAT_KEY, str(time.time() - 3600))
    deadline = time.time() + 3
    while not e.stops.deadline_moves("n") and time.time() < deadline:
        time.sleep(0.05)
    moves = e.stops.deadline_moves("n")
    e.stop()
    assert not kept.armed and [m["stopped_by"] for m in moves] == ["the host slept"], "the monitor died at the lock"


def test_a_host_asleep_between_two_ticks_is_on_each_deadlines_record(monkeypatch):
    """Case 4: a gap between two of the monitor's ticks over NO_TICK_S is left off at the next tick, and recorded."""
    e = _consented(check_interval=0.05)
    shift = {"s": 0.0}
    monkeypatch.setattr(L, "time", type("T", (), {"time": staticmethod(lambda: time.time() + shift["s"])}))
    time.sleep(0.2)
    shift["s"] = 3600.0                                  # the wall jumps an hour between two ticks
    deadline = time.time() + 3
    while not e.stops.deadline_moves("n") and time.time() < deadline:
        time.sleep(0.05)
    moves = e.stops.deadline_moves("n")
    e.stop()
    assert len(moves) == 1 and moves[0]["stopped_by"] == "the host slept" and abs(moves[0]["held_s"] - 3600) < 5, moves
