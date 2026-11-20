"""The time a stop held is left off the project's clocks, so every live deadline reads that much later on the wall — and
the record says so (Thm 11: every decision has a record; §12.2: the deadline is never suspended). The shift is no
revision: no packet field moved, so the node keeps its version and the consent standing for it (Inv-1)."""
from __future__ import annotations

import time
from datetime import datetime

import gfso.engine.loop as L
import gfso.tools as T
from gfso.adapters.storage.memory import MemoryStorage
from gfso.core.types import AgentId, Mode, TaskId
from gfso.core.graph.model import CLOCK_BEAT_KEY, clock_off_s, keep_off
from tests.support import criterion, make_engine


def test_a_stop_lifted_on_a_system_carried_project_records_each_live_deadlines_shift():
    e = make_engine(validate_signals=True, state_timeout=0)
    e.start()
    T.create_task(e, "n", {"description": "x", "criteria": [criterion("a", "A")]}, "w")
    e.wait_idle()
    assert T.signal(e, "n", "ACCEPT", "w")["accepted"]
    e.set_mode(Mode.AUTO, None, AgentId("user"))      # the system carries the work: the stop holds the project's time
    assert e.system_carries_work()
    was = T.get_task(e, "n")["deadline"]
    e.pause("the-user", "look at a bug")
    keep_off(e.graph, 3600)                     # an hour the stop held, left off as the monitor's ticks leave it
    e.resume("the-user")
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
    e.pause("the-user", "")
    e.resume("the-user")
    assert e.deadline_moves("n") == [], "a stop that held no time moves no deadline"
    e.stop_for_the_limit("executor", time.time() - 60)
    keep_off(e.graph, 600)
    e.lift_the_system_stop(time.time())
    assert not e.paused()
    [m] = e.deadline_moves("n")
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
            e.pause("the-user", "")
        e.stop()
        kept.store_setting(CLOCK_BEAT_KEY, str(time.time() - 3600))
        again = make_engine(storage=kept, validate_signals=True, state_timeout=0)
        again.start()
        if stopped:
            assert again.deadline_moves("n") == [], "the gap under a stop is the stop's, recorded at its lift"
            again.resume("the-user")
        [m] = again.deadline_moves("n")
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
    again.pause("the-user", "")
    shift["s"] = 1800.0                                  # half an hour under the stop, between two of its ticks
    time.sleep(0.3)
    again.resume("the-user")
    time.sleep(0.2)
    got = T.get_task(again, "n")
    again.stop()
    assert clock_off_s(again.graph) < 1 and got["deadline"] == was, (clock_off_s(again.graph), was, got["deadline"])
    assert again.deadline_moves("n") == [], again.deadline_moves("n")


def test_a_host_asleep_between_two_ticks_is_on_each_deadlines_record(monkeypatch):
    """Case 4: a gap between two of the monitor's ticks over NO_TICK_S is left off at the next tick, and recorded."""
    e = _consented(check_interval=0.05)
    shift = {"s": 0.0}
    monkeypatch.setattr(L, "time", type("T", (), {"time": staticmethod(lambda: time.time() + shift["s"])}))
    time.sleep(0.2)
    shift["s"] = 3600.0                                  # the wall jumps an hour between two ticks
    deadline = time.time() + 3
    while not e.deadline_moves("n") and time.time() < deadline:
        time.sleep(0.05)
    moves = e.deadline_moves("n")
    e.stop()
    assert len(moves) == 1 and moves[0]["stopped_by"] == "the host slept" and abs(moves[0]["held_s"] - 3600) < 5, moves
