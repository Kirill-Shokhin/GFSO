"""Four rules an outside review found stated and not implemented. Each test is that reproduction.

They share one subject: after v4.1 the clock decides more than it used to (every state carries a
bound, every packet carries a deadline) and the issuer's own moves are what the protocol leans on —
so a move that is admitted and inert, or a bound enforced one predicate off, costs exactly what the
removal of auto_pass was for.
"""
from __future__ import annotations

import time
from datetime import datetime, timedelta

import pytest

import gfso.tools as T
from gfso.core.types import (AgentId, Criteria, CriterionMapping, Signal, SignalData,
                             Spec, State, TaskId)
from tests.support import REGISTER_SPLIT, criterion, make_engine, pinned, REGISTER

_RISK = REGISTER


@pytest.fixture(autouse=True)
def _no_l2(monkeypatch):
    monkeypatch.setenv("GFSO_L2_GATE", "0")


def _waits_for(e, tid, state, limit=4.0):
    until = time.time() + limit
    while time.time() < until:
        st = e.graph.get_state(TaskId(tid))
        if st is not None and st.name == state:
            return True
        time.sleep(0.02)
    return False


def _root(e, tid="root", max_iterations=None, **kw):
    T.create_task(e, tid, {"description": "a goal", "criteria": [criterion("c", "C")],
                           "accepted_risks": _RISK}, assignee="worker", **kw)
    e.wait_idle()
    if max_iterations is not None:
        t = e._graph.get_task(TaskId(tid))      # the forecast the issuer set on the first packet
        t.max_iterations = max_iterations
        e._graph.save_task(t)


def test_the_issuers_bare_re_assign_out_of_escalated_actually_applies():
    """§12.5: out of ESCALATED the re-ASSIGN may omit the SPEC — never its effect.

    It carried the raised rework bound and the live deadline into a mutation that bailed on
    `spec is None`, so the node went back to OFFERED with the old budget, the old deadline and no
    new version: the one work-keeping move the state admits was inert, and the node re-escalated on
    the next FAIL for ever."""
    e = make_engine()
    e.start()
    try:
        _root(e, max_iterations=1)
        T.signal(e, "root", "ACCEPT", "worker")
        T.signal(e, "root", "DELIVER", "worker", result="v1")
        T.signal(e, "root", "FAIL", "worker", failed_criteria=["c"])
        e.wait_idle()
        T.signal(e, "root", "DELIVER", "worker", result="v2")
        T.signal(e, "root", "FAIL", "worker", failed_criteria=["c"])
        e.wait_idle()
        assert e.graph.get_state(TaskId("root")) == State.ESCALATED

        later = datetime.now() + timedelta(hours=6)
        e.send_signal_sync(SignalData(signal=Signal.ASSIGN, task_id=TaskId("root"),
                                      source=AgentId("worker"), max_iterations=9, deadline=later))
        t = e.graph.get_task("root")
        assert t.state == State.OFFERED
        assert t.max_iterations == 9, "the issuer raised the forecast and nothing took it"
        assert t.iteration == 0, "a new packet version starts the rework budget over (Φ3)"
        assert t.deadline == later
        assert t.revisions == 1, "a state move without a new version is not a revision (Inv-1)"
    finally:
        e.stop()


def test_a_state_entered_on_a_spent_deadline_admits_nothing():
    """§12.2's own worked case: REWORKING entered after a FAIL past the deadline times out at once
    (to ESCALATED) — otherwise each rework round buys a fresh T_validate and the loop outruns the
    deadline."""
    e = make_engine(check_interval=0.05)
    e.start()
    try:
        _root(e, deadline=(datetime.now() + timedelta(seconds=1)).isoformat())
        T.signal(e, "root", "ACCEPT", "worker")
        T.signal(e, "root", "DELIVER", "worker", result="v1")
        time.sleep(1.2)                                  # the contract's time runs out in VALIDATING
        T.signal(e, "root", "FAIL", "worker", failed_criteria=["c"])
        e.wait_idle()
        out = T.signal(e, "root", "DELIVER", "worker", result="v2")
        assert out.get("accepted") is False, "work went on under a contract whose time was spent"
        assert _waits_for(e, "root", "ESCALATED")
    finally:
        e.stop()


def test_a_verdict_that_took_longer_than_the_bound_is_still_the_issuers_verdict(monkeypatch):
    """The mirror of the rule above, and the one an over-eager reading broke: VALIDATING aging past
    T_validate is the MONITOR's business (it hands the node back, §16.14). The issuer's PASS arriving
    late is his own admissible move, and refusing it leaves him none — which §12.16's conformance
    clause forbids."""
    monkeypatch.setenv("GFSO_BOUND_VALIDATING", "0.2")
    e = make_engine(check_interval=30)       # the monitor will not tick inside this test
    e.start()
    try:
        # …and the CONTRACT's own time is spent too, which is the half that makes this a property
        # rather than a spelling: VALIDATING runs on T_validate ALONE (§12.2), so neither clock
        # takes the verdict out of the issuer's hands once the delivery is on the table.
        _root(e, deadline=(datetime.now() + timedelta(seconds=1)).isoformat())
        T.signal(e, "root", "ACCEPT", "worker")
        T.signal(e, "root", "DELIVER", "worker", result="v1")
        e.wait_idle()
        time.sleep(1.3)                       # past T_validate AND past the packet deadline
        e.record_exec_verdict("root", "PASS", [], "validator", per_criterion=[
            {"criterion": "c", "verdict": "pass", "evidence": "ran the pinned probe",
             "behaviours": ["c holds"],
             "probe": [{"behaviour": "c holds", "command": "check c", "expect": "it holds"}]}])
        out = T.signal(e, "root", "PASS", "worker")
        assert out.get("accepted") is True, out
        assert e.graph.get_state(TaskId("root")) == State.DONE
    finally:
        e.stop()


def test_a_child_is_never_born_past_its_own_deadline():
    """The default is written INSIDE the parent's, and under a parent with minutes left the margin
    lands in the past: the child was then born overdue, its first ACCEPT refused by the entry rule,
    with no admissible move at all — and invisible to CHECK-3, because a supplied deadline states no
    ordering. Where no default fits, none is written — and a packet with none does not conform: the issuer types one
    (§12.16), so the admission is refused whole until he does (critic r7, B-F5)."""
    e = make_engine()
    e.start()
    try:
        _root(e, tid="p", deadline=(datetime.now() + timedelta(minutes=2)).isoformat())
        T.signal(e, "p", "ACCEPT", "worker")
        kid = (TaskId("p.kid"), Spec("a child", (Criteria("k", "K", check=pinned("k")),)), AgentId("worker"))
        with pytest.raises(ValueError, match="types one"):
            e.decompose_task(TaskId("p"), [kid], criterion_mappings=[CriterionMapping("c", TaskId("p.kid"))], register=REGISTER_SPLIT)
        assert e.graph.get_task("p.kid") is None
        e.decompose_task(TaskId("p"), [kid + (datetime.now() + timedelta(minutes=1),)],
                         criterion_mappings=[CriterionMapping("c", TaskId("p.kid"))], register=REGISTER_SPLIT)
        e.wait_idle()
        assert e.graph.get_task("p.kid").deadline > datetime.now()
    finally:
        e.stop()


def test_the_contract_a_dispute_installs_is_admitted_on_the_same_terms():
    """ACCEPT_CHALLENGE is the one act that rewrites criteria in place, and it reached the graph
    past both admission rules: a node admitted WITH pinned checks could be re-authored without
    any — the gate that makes the promise checkable, lifted by the move that answers a dispute."""
    e = make_engine()
    e.start()
    try:
        _root(e)
        T.signal(e, "root", "ACCEPT", "worker")
        T.signal(e, "root", "CHALLENGE", "worker", reason="c cannot be met as written")
        e.wait_idle()
        e.send_signal_sync(SignalData(
            signal=Signal.ACCEPT_CHALLENGE, task_id=TaskId("root"), source=AgentId("worker"),
            new_spec=Spec("a goal", (Criteria("c", "C, reworded"),))))
        assert e.graph.get_task("root").spec.criteria[0].check, "the contract lost its pinned procedure"
    finally:
        e.stop()


def test_the_decomposer_door_admits_on_the_same_terms_as_the_hand_door():
    """A rule that holds at one door and not at the next: `decompose_task` — the path behind
    `decompose` and `auto_decompose` — sent every child's ASSIGN past both admission guards."""
    e = make_engine()
    e.start()
    try:
        _root(e, tid="p")
        with pytest.raises(ValueError, match="pin no check"):
            e.decompose_task(TaskId("p"), [(TaskId("kid"),
                                            Spec("a child", (Criteria("k", "K"),)),
                                            AgentId("worker"))], [CriterionMapping("c", TaskId("kid"))],
                             register=REGISTER_SPLIT)
        T.signal(e, "p", "ACCEPT", "worker")
        T.signal(e, "p", "CANCEL", "worker", reason="the goal is off")
        e.wait_idle()
        assert e.graph.get_state(TaskId("p")) == State.CANCELLING
        with pytest.raises(ValueError, match="CANCELLING"):
            e.decompose_task(TaskId("p"), [(TaskId("kid2"),
                                            Spec("a child", (Criteria("k", "K", check=pinned("k")),)),
                                            AgentId("worker"))], [CriterionMapping("c", TaskId("kid2"))],
                             register=REGISTER_SPLIT)
    finally:
        e.stop()


def test_the_first_assign_door_refuses_a_child_under_a_dead_parent():
    """The same rule at the door the verification pass found untested.

    `decompose_task` was covered; the HAND door — `create_task` with a `parent_id` — was not, and
    a guard is only a guard at every door that reaches it (§12.7, 'Issuing children': a child
    issued after the cascade fired would escape it).
    """
    e = make_engine()
    e.start()
    try:
        _root(e, tid="p")
        T.signal(e, "p", "ACCEPT", "worker")
        T.signal(e, "p", "CANCEL", "worker", reason="the goal is off")
        e.wait_idle()
        assert e.graph.get_state(TaskId("p")) == State.CANCELLING
        # …and it REACHES the caller as an answer, not an exception: the tool door's standing rule
        # is that verbs answer rather than throw, so the refusal is only a refusal if it is readable
        # there. (The engine door raises; `tools` is what an agent actually calls.)
        out = T.create_task(e, "late", {"description": "a child",
                                        "criteria": [criterion("k", "K")]},
                            assignee="worker", parent_id="p")
        assert "error" in out, out
        assert "CANCELLING" in out["error"] and "§12.7" in out["error"], out["error"]
        assert e.graph.get_task(TaskId("late")) is None, "the refused child must not exist"
    finally:
        e.stop()


def test_the_reopen_door_refuses_a_child_under_a_dead_parent():
    """And the third door: a REOPEN re-issues a child, so it answers to the same parent rule."""
    e = make_engine()
    e.start()
    try:
        _root(e, tid="p")
        T.signal(e, "p", "ACCEPT", "worker")
        T.decompose(e, "p", [{"task_id": "kid", "spec": {"description": "a child", "criteria": [criterion("k", "K")]},
                              "assignee": "worker", "covers": ["c"]}], accepted_risks=_RISK)
        T.signal(e, "kid", "ACCEPT", "worker")
        T.signal(e, "kid", "CANCEL", "worker", reason="not needed")
        T.signal(e, "kid", "CONFIRM_CANCEL", "worker")
        e.wait_idle()
        assert e.graph.get_state(TaskId("kid")) == State.ABANDONED
        # now kill the parent, and the settled child must not be re-issuable beneath it
        T.signal(e, "p", "CANCEL", "worker", reason="the goal is off")
        e.wait_idle()
        assert e.graph.get_state(TaskId("p")) == State.CANCELLING
        # …AT THE DOOR AN AGENT CALLS, like the test above it. Asserting the ENGINE's raise here
        # hid the defect: `_reopen_gate` did not know this case, so `T.reopen` THREW where every
        # sibling verb answers — a 500 over HTTP against a 200-with-`error` next door.
        out = T.reopen(e, "kid", "worker")
        assert "error" in out, out
        assert "CANCELLING" in out["error"] and "§12.7" in out["error"], out["error"]
        assert e.graph.get_state(TaskId("kid")) == State.ABANDONED, "the refused node must not move"
    finally:
        e.stop()
