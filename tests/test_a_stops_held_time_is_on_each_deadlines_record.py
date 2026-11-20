"""The time a stop held is left off the project's clocks, so every live deadline reads that much later on the wall — and
the record says so (Thm 11: every decision has a record; §12.2: the deadline is never suspended). The shift is no
revision: no packet field moved, so the node keeps its version and the consent standing for it (Inv-1)."""
from __future__ import annotations

import time
from datetime import datetime

import gfso.tools as T
from gfso.core.types import AgentId, Mode, TaskId
from gfso.core.graph.model import keep_off
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
