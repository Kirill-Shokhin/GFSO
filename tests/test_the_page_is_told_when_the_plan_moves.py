"""An open page redraws a node's state from its transition, and is told on the `graph` line whenever the PLAN's record
moved — from the one place every write of it passes (the store), whichever verb or loop step wrote it. Doors told one
by one left some silent and some false (critic rounds over wip/uinews): a contract re-issued unchanged said "revised",
an accepted dispute with a new spec said nothing. Here: a changed plan field or Dep record says so once; a state change
alone, a write that leaves the plan as it was, and the first write after a restart say nothing."""
from __future__ import annotations

import dataclasses

from gfso.core.types import DepEdge, Signal, SignalData, TaskId
from gfso.delegate import publish_the_workforce
from tests.support import make_engine
from tests.test_every_verb_answers import _seeded


def _watched(storage=None):
    e = make_engine(storage, llm=None, validate_signals=True, state_timeout=0)
    lines = []
    e.on_info(lambda source, msg: lines.append(msg) if source == "graph" else None)
    e.start()
    return e, lines


def test_a_changed_contract_is_told_and_an_unchanged_one_is_not():
    e, lines = _watched()
    _seeded(e)
    lines.clear()
    t = e.graph.get_task(TaskId("root"))
    e.revise(t.id, t.spec, t.assignee); e.wait_idle()
    assert lines == [], lines
    e.revise(t.id, dataclasses.replace(t.spec, description="the goal, sharper"), t.assignee); e.wait_idle()
    assert lines == ["root: the plan changed"], lines


def test_a_state_change_alone_says_nothing_here():
    e, lines = _watched()
    _seeded(e)
    lines.clear()
    t = e.graph.get_task(TaskId("root"))
    e.send_signal(SignalData(task_id=t.id, signal=Signal.ACCEPT, source=t.assignee)); e.wait_idle()
    assert e.graph.get_task(t.id).state.name == "EXECUTING" and lines == [], lines


def test_a_dependency_written_or_dropped_is_told():
    e, lines = _watched()
    _seeded(e)
    lines.clear()
    edge = DepEdge(TaskId("a"), TaskId("b"), True, "")
    e._storage.add_dep_edge(edge)
    e._storage.remove_dep_edge(edge)
    assert lines == ["b: a dependency record changed"] * 2, lines


def test_the_first_write_after_a_restart_is_not_a_change():
    e, _ = _watched()
    _seeded(e)
    e.stop()
    e2, lines = _watched(e._storage._s)
    t = e2.graph.get_task(TaskId("root"))
    e2.send_signal(SignalData(task_id=t.id, signal=Signal.ACCEPT, source=t.assignee)); e2.wait_idle()
    assert lines == [], lines


def test_a_role_on_or_off_the_roster_is_told_and_the_first_publication_is_not():
    e, lines = _watched()
    publish_the_workforce(e, {"exec-1": {"kind": "llm-executor"}})
    assert lines == [], lines
    publish_the_workforce(e, {"exec-1": {"kind": "llm-executor"}})
    assert lines == [], lines
    publish_the_workforce(e, {"exec-1": {"kind": "llm-executor"}, "val-1": {"kind": "llm-validator"}})
    assert lines == ["the roster changed"], lines
