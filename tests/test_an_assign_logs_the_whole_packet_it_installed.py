"""Each ASSIGN installs a version of the task's packet (§11.3), and the log is that version's record (Thm 11): a
re-ASSIGN that moves only the deadline or the rework bound installs a version the row must be able to say."""
from __future__ import annotations

import json
from datetime import datetime, timedelta

import gfso.tools as T
from gfso.core.types import Signal, TaskId
from tests.support import criterion, make_engine, REGISTER

_SPEC = {"description": "a goal", "accepted_risks": REGISTER, "criteria": [criterion("c1", "C1 holds")]}


def test_a_re_assign_moving_only_the_deadline_and_bound_logs_what_it_installed():
    e = make_engine(validate_signals=True, state_timeout=0)
    e.start()
    T.create_task(e, "root", dict(_SPEC), assignee="user",
                  deadline=(datetime.now() + timedelta(days=5)).isoformat())
    e.wait_idle()
    T.revise(e, "root", dict(_SPEC), agent="user",
             deadline=(datetime.now() + timedelta(days=14)).isoformat(), max_iterations=3)
    e.wait_idle()
    t = e.graph.get_task(TaskId("root"))
    rows = [json.loads(a.spec) for a in e.audit_log(t.id) if a.signal == Signal.ASSIGN and not a.rejected]
    assert len(rows) == 2
    first, last = rows
    assert last.get("deadline") == t.deadline.isoformat() and last.get("max_iterations") == 3, last
    assert last.get("assignee") == str(t.assignee) and last.get("deadline_supplied") is t.deadline_supplied, last
    assert first.get("deadline") != last.get("deadline"), "two versions, two deadlines on the log"
    e.stop()
