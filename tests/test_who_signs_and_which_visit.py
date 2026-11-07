"""Who signs a move and which visit a timeout belongs to (canon audit 2026-10-26, docs/notes/CANON_AUDIT_2026-10-26.md).

A cascaded CANCEL is each descendant's issuer's (§12.6, §10.1); a new version is a new visit (§12.2); no re-ASSIGN out of
ESCALATED is counted below the AUTO root (§12.15); a root another executes keeps its creator as the goal's issuer
(§10.1, §10.3). CONTROLS: sign the cascade as the cancelled node's Del (loop.py), drop the restamp in `_apply_spec`, count
every node in `_reassign`, or record the root's issuer only under a mode — and the test of that rule goes red."""
from __future__ import annotations

import dataclasses
import time

import gfso.delegate as D
import gfso.tools as T
from gfso.core.types import Signal, SignalData, TaskId
from gfso.issuer import MAX_EXTENSIONS, _reassign, signal_ok
from gfso.roster import AgentRegistry
from tests.support import REGISTER, criterion, make_engine, reviewer_passes


def _kid(k, covers, who):
    return {"task_id": k, "spec": {"description": f"part {k}", "criteria": [criterion(f"{k}_ok", k)]},
            "assignee": who, "covers": covers}


def test_a_cascade_reaches_a_grandchild_under_a_settled_child_signed_by_its_own_issuer():
    e = make_engine()
    e.start()
    T.create_task(e, "root", {"description": "goal", "criteria": [criterion("a", "A")]}, "agent")
    e.wait_idle()
    T.signal(e, "root", "ACCEPT", "agent")
    T.decompose(e, "root", [_kid("k1", ["a"], "bob")], accepted_risks=REGISTER)
    e.wait_idle()
    T.signal(e, "k1", "ACCEPT", "bob")
    T.decompose(e, "k1", [_kid("g1", ["k1_ok"], "carol")], accepted_risks=REGISTER)
    e.wait_idle()
    T.signal(e, "g1", "ACCEPT", "carol")
    T.signal(e, "k1", "DELIVER", "bob", result="built k1 by hand")
    e.wait_idle()
    reviewer_passes(e, TaskId("k1"), "rev")
    T.signal(e, "k1", "PASS", "agent")
    e.wait_idle()
    assert e.graph.get_state(TaskId("k1")).name == "DONE"
    T.signal(e, "root", "CANCEL", str(e.graph.issuer_of(TaskId("root"))), reason="goal gone")
    e.wait_idle()
    assert e.graph.get_state(TaskId("g1")).name in ("CANCELLING", "ABANDONED"), "the grandchild kept working"
    assert [a.source for a in e.audit_log(TaskId("g1")) if a.signal == Signal.CANCEL and not a.rejected] == ["bob"]
    e.stop()


def test_a_new_version_is_a_new_visit_so_the_old_ones_timeout_moves_nothing():
    e = make_engine()
    e.start()
    T.create_task(e, "root", {"description": "goal", "criteria": [criterion("a", "A")], "accepted_risks": REGISTER},
                  "agent")
    e.wait_idle()
    t0 = e.graph.get_task(TaskId("root"))
    old = (t0.state, t0.state_entered_at)
    time.sleep(0.05)
    T.revise(e, "root", {"description": "goal v2", "criteria": [criterion("a", "A2")], "accepted_risks": REGISTER},
             agent=str(e.graph.issuer_of(TaskId("root"))))
    e.wait_idle()
    e.send_signal_sync(SignalData(signal=Signal.TIMEOUT, task_id=TaskId("root"), visit=old))
    e.wait_idle()
    assert e.graph.get_state(TaskId("root")).name == "OFFERED", "the old version's timeout landed on the new one"
    e.stop()


def test_no_re_issue_out_of_escalated_is_counted_below_the_auto_root():
    e = make_engine()
    e.start()
    T.create_task(e, "root", {"description": "goal", "criteria": [criterion("a", "A")], "accepted_risks": REGISTER},
                  "agent")
    e.wait_idle()
    e.workforce.publish_executor_pool({"agent": None})
    issuer = str(e.graph.issuer_of(TaskId("root")))
    for _ in range(MAX_EXTENSIONS + 1):
        t = e.graph.get_task(TaskId("root"))
        e.send_signal_sync(SignalData(signal=Signal.TIMEOUT, task_id=t.id, visit=(t.state, t.state_entered_at)))
        e.wait_idle()
        ok, why = _reassign(e, e.graph.get_task(TaskId("root")), issuer, {"move": "reassign", "extend_hours": 24},
                            "more time", None)
        e.wait_idle()
        assert ok, why
    e.stop()


def test_a_root_another_executes_keeps_its_creator_as_issuer_with_no_mode(tmp_path):
    e = make_engine(validate_signals=True, state_timeout=0)
    e.start()
    e.project_name = "p"
    agents = AgentRegistry(path=str(tmp_path / "agents.json"))
    agents.register("exec-1", "llm-executor", workdir=str(tmp_path), project="p")
    D.publish_the_workforce(e, agents.list())
    e.workforce.publish_roster({a: c.get("kind") for a, c in agents.list().items()})
    T.create_task(e, "root", {"description": "goal", "criteria": [criterion("x", "X"), criterion("y", "Y")],
                              "accepted_risks": REGISTER}, assignee="exec-1")
    assert str(e.graph.issuer_of(TaskId("root"))) != "exec-1"
    T.signal(e, "root", "ACCEPT", "exec-1")
    T.signal(e, "root", "CHALLENGE", "exec-1", reason="y cannot be met")
    t = e.graph.get_task(TaskId("root"))
    narrowed = dataclasses.replace(t.spec, criteria=tuple(c for c in t.spec.criteria if c.name != "y"))
    assert not signal_ok(e, TaskId("root"), Signal.ACCEPT_CHALLENGE, "exec-1", new_spec=narrowed), \
        "the root's executor answered its own dispute"
    assert [c.name for c in e.graph.get_task(TaskId("root")).spec.criteria] == ["x", "y"]
    e.stop()
