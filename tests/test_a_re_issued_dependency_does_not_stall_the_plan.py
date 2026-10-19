"""A machine re-issue writes its deadline inside its parent's, and a crossing it makes refuses nothing (v4.1 §2.5,
§11.5, §12.10; sync audit 2026-10-04, B-F1).

The machine issuer re-issued a child at min(now + 24 h, the parent's deadline): two Dep-linked siblings re-issued got
ONE deadline, CHECK-3 read a crossing, and the execution gate refused the consumer's ACCEPT and later the root's PASS —
with no move of the machine able to lift it, so the root was closed. And a deadline already passed was admitted, the
node entering OFFERED only to lapse on the next tick.

CONTROL: put CHECK-3 back in `_EXEC_GATING_CHECKS`, or let `_reassign` write ON the parent's deadline, or drop the
spent-deadline refusal — and these go red.
"""
import dataclasses
from datetime import datetime, timedelta

import pytest

import gfso.tools as T
from gfso import issuer as I
from gfso.core.graph import q_Del, q_T
from gfso.core.types import AgentId, Criteria, DoneReason, Signal, SignalData, State, TaskId
from gfso.engine.validation import _l0_holes
from tests.support import REGISTER, criterion, make_engine


@pytest.fixture(autouse=True)
def _no_plan_gate(monkeypatch):
    monkeypatch.setenv("GFSO_L2_GATE", "0")


def _plan():
    e = make_engine()
    e.start()
    T.create_task(e, "root", {"description": "goal", "criteria": [criterion("a", "A"), criterion("b", "B")],
                              "accepted_risks": REGISTER}, assignee="lead",
                  deadline=(datetime.now() + timedelta(days=1)).isoformat())
    T.decompose(e, "root", [
        {"task_id": "root.x", "spec": {"description": "x", "criteria": [criterion("x1", "X")]}, "assignee": "w",
         "covers": ["a"]},
        {"task_id": "root.y", "spec": {"description": "y", "criteria": [criterion("y1", "Y")]}, "assignee": "w",
         "covers": ["b"]}], accepted_risks=REGISTER)
    T.add_dependency(e, "root.x", "root.y", glue="y reads x")
    e.wait_idle()
    return e


def test_re_issued_siblings_are_given_deadlines_inside_their_parent_and_the_plan_does_not_stall(monkeypatch):
    e = _plan()
    monkeypatch.setattr(I, "seam_keeping_executor", lambda engine, task, other: task.assignee)
    root = e.graph.get_task(TaskId("root"))
    for k in ("root.x", "root.y"):
        ok, why = I._reassign(e, e.graph.get_task(TaskId(k)), "lead", {"extend_hours": 48}, "re-issue", None)
        assert ok, why
        assert e.graph.get_task(TaskId(k)).deadline < root.deadline, "written ON the parent's deadline"
    assert not _l0_holes(e._graph, e.graph.get_task(TaskId("root"))), "a crossing the re-issue made gates the plan"
    e.send_signal(SignalData(signal=Signal.ACCEPT, task_id=TaskId("root.y"), source=AgentId("w")))
    e.wait_idle()
    assert e.graph.get_state(TaskId("root.y")).name == "EXECUTING"
    e.stop()


@pytest.mark.parametrize("order", [("root.x", "root.y"), ("root.y", "root.x")])
def test_the_machine_re_issue_keeps_the_dep_order_it_writes(monkeypatch, order):
    """Both re-issued on the parent's deadline less one margin, producer and consumer got one deadline — a CHECK-3
    crossing the machine issuer made itself (critic r7, B2). It leaves room for the consumers below along Dep; re-issued
    first, under a producer already on the parent's bound, the consumer takes the parent's margin rather than the
    producer's deadline — CHECK-3 is the canon's, the margin only the implementation's."""
    e = _plan()
    monkeypatch.setattr(I, "seam_keeping_executor", lambda engine, task, other: task.assignee)
    for k in order:
        ok, why = I._reassign(e, e.graph.get_task(TaskId(k)), "lead", {"extend_hours": 48}, "re-issue", None)
        assert ok, why
    x, y = (e.graph.get_task(TaskId(k)).deadline for k in ("root.x", "root.y"))
    assert x < y < e.graph.get_task(TaskId("root")).deadline
    e.wait_idle()
    assert {c["check"]: c["verdict"] for c in T.get_checks(e, "root")}["CHECK-3:deadlines"] != "unmet"
    e.stop()


def test_a_revision_whose_criteria_close_a_dep_cycle_is_refused():
    """§12.10: of the guards a revision re-runs only CHECK-2's Dep clause refuses. Through `add_dependency` it did; a
    revision writing the same `depends_on` straight into the producer's criteria was admitted (sync audit, A-F4)."""
    e = _plan()
    x = e.graph.get_task(TaskId("root.x"))
    back = {**criterion("dep__root.y", "x reads y"), "depends_on": "root.y"}
    with pytest.raises(ValueError, match="Dep cycle"):
        T.revise(e, "root.x", {"description": "x", "criteria": [criterion("x1", "X"), back]}, agent="lead")
    assert not any(c.depends_on for c in e.graph.get_task(TaskId("root.x")).spec.criteria)
    e.stop()


def test_the_answer_to_a_dispute_closing_a_dep_cycle_is_refused_too():
    """§12.16: what an implementation requires of a packet it requires of `new_spec` — the dispute's answer rode past the
    cycle rule, which read `spec` only (critic over session 475ba784)."""
    e = _plan()
    for sig in ("ACCEPT", "CHALLENGE"):
        e.send_signal_sync(SignalData(signal=Signal[sig], task_id=TaskId("root.x"), source=AgentId("w"), reason="r"))
    x = e.graph.get_task(TaskId("root.x"))
    back = Criteria("dep__root.y", "x reads y", depends_on=TaskId("root.y"), check=x.spec.criteria[0].check)
    e.send_signal_sync(SignalData(signal=Signal.ACCEPT_CHALLENGE, task_id=TaskId("root.x"), source=AgentId("lead"),
                                  new_spec=dataclasses.replace(x.spec, criteria=x.spec.criteria + (back,))))
    assert e.graph.get_state(TaskId("root.x")) == State.CHALLENGED
    e.stop()


def test_a_split_whose_children_depend_on_each_other_is_refused_naming_check_2():
    """A ring among the admission's own children has no order at all; the feasibility read recursed without end."""
    e = make_engine()
    e.start()
    T.create_task(e, "root", {"description": "goal", "criteria": [criterion("a", "A"), criterion("b", "B")],
                              "accepted_risks": REGISTER}, assignee="lead",
                  deadline=(datetime.now() + timedelta(days=3)).isoformat())
    kid = lambda k, other, cov, d: {"task_id": k, "covers": [cov], "assignee": "w",
                                    "deadline": (datetime.now() + timedelta(days=d)).isoformat(),
                                    "spec": {"description": k, "criteria": [
                                        criterion(f"{k}1", k), {**criterion(f"dep__{other}", "r"), "depends_on": other}]}}
    with pytest.raises(ValueError, match="CHECK-2"):
        T.decompose(e, "root", [kid("ka", "kb", "a", 1), kid("kb", "ka", "b", 2)], accepted_risks=REGISTER)
    e.stop()


def test_the_reopen_door_answers_a_spent_deadline_in_words():
    """`reopen` carries no deadline; with the standing one spent and no default inside the parent's, it raised out of
    the door (critic over session 475ba784). It answers, and names the door that reopens with one."""
    e = _plan()
    t = e.graph.get_task(TaskId("root.x"))
    t.state, t.done_reason, t.deadline = State.DONE, DoneReason.PASS, datetime.now() - timedelta(hours=1)
    e._graph.save_task(t)
    r = e.graph.get_task(TaskId("root"))
    r.deadline = datetime.now() + timedelta(minutes=2)
    e._graph.save_task(r)
    out = T.reopen(e, "root.x", "lead")
    assert "revise" in out.get("error", "") and "deadline" in out["error"], out
    e.stop()


def test_a_reopen_through_revise_keeps_the_issuing_condition():
    """§12.14: REOPEN is admissible, below a root, only under the issuing condition (§12.7). `reopen` checked it at its
    door; `revise` on a terminal child — the same re-issue — went around it under a parent in CANCELLING (B-F3)."""
    e = _plan()
    for tid, st in (("root.x", State.DONE), ("root", State.CANCELLING)):
        t = e.graph.get_task(TaskId(tid))
        t.state = st
        e._graph.save_task(t)
    with pytest.raises(ValueError, match="§12.7"):
        T.revise(e, "root.x", {"description": "x", "criteria": [criterion("x1", "X")]}, agent="lead")
    assert e.graph.get_state(TaskId("root.x")) == State.DONE
    e.stop()


def test_the_machine_issuer_promotes_a_producible_blocker_into_a_node():
    """§11.3: promoting a producible in-scope blocker is mandatory, owed by the blocked task's issuer, by changing the
    split he holds. The machine issuer could only resolve, re-issue or close (sync audit, A-F8)."""
    e = _plan()
    # x's deadline typed by its issuer, so only the producer's own can keep the order
    T.revise(e, "root.x", {"description": "x", "criteria": [criterion("x1", "X")]}, agent="lead",
             deadline=(e.graph.get_task(TaskId("root")).deadline - timedelta(hours=1)).isoformat())
    for sig in ("ACCEPT", "BLOCK"):
        T.signal(e, "root.x", sig, "w", reason="the lexer it parses with does not exist")
    e.wait_idle()
    assert e.graph.get_state(TaskId("root.x")).name == "BLOCKED"
    lexer = {"name": "lexer", "description": "the lexer x parses with", "criteria": [criterion("l1", "it lexes")]}
    ok, why = I._promote(e, e.graph.get_task(TaskId("root.x")), "lead", {"child": lexer}, "x needs a lexer", None)
    assert ok, why
    assert e.graph.get_task(TaskId("root.lexer")) is not None
    assert ("root.lexer", "root.x") in {(str(d.from_id), str(d.to_id)) for d in e.get_dependencies()}
    # due before the node it unblocks: born with the parent's default, it came due after it (critic r2, F3)
    assert e.graph.get_task(TaskId("root.lexer")).deadline < e.graph.get_task(TaskId("root.x")).deadline
    ok, why = I._promote(e, e.graph.get_task(TaskId("root")), "lead", {"child": lexer}, "the root lacks it", None)
    assert not ok and "§15.2" in why
    e.stop()


def test_a_re_issued_consumer_is_given_a_deadline_after_its_producer(monkeypatch):
    """§2.7 both ways: bounded only by consumers and the parent, a consumer re-issued for 2 h landed before a producer
    re-issued for 48 h (critic over session 475ba784)."""
    e = make_engine()
    e.start()
    T.create_task(e, "root", {"description": "goal", "criteria": [criterion("a", "A"), criterion("b", "B")],
                              "accepted_risks": REGISTER}, assignee="lead",
                  deadline=(datetime.now() + timedelta(days=4)).isoformat())
    T.decompose(e, "root", [
        {"task_id": "root.x", "spec": {"description": "x", "criteria": [criterion("x1", "X")]}, "assignee": "w",
         "covers": ["a"]},
        {"task_id": "root.y", "spec": {"description": "y", "criteria": [criterion("y1", "Y")]}, "assignee": "w",
         "covers": ["b"]}], accepted_risks=REGISTER)
    T.add_dependency(e, "root.x", "root.y", glue="y reads x")
    e.wait_idle()
    monkeypatch.setattr(I, "seam_keeping_executor", lambda engine, task, other: task.assignee)
    for k, h in (("root.x", 48), ("root.y", 2)):
        ok, why = I._reassign(e, e.graph.get_task(TaskId(k)), "lead", {"extend_hours": h}, "re-issue", None)
        assert ok, why
    assert e.graph.get_task(TaskId("root.x")).deadline < e.graph.get_task(TaskId("root.y")).deadline
    e.stop()


def test_a_re_issued_producer_is_not_squeezed_under_a_consumer_already_due(monkeypatch):
    """A contract shorter than one margin is no contract anybody meets: under a consumer due in three minutes the
    producer got 90 seconds, ordered and lapsing at once (critic over F3, B1). It takes the parent's bound, the
    crossing flagged to the consumer's issuer (§12.10)."""
    e = _plan()
    y = e.graph.get_task(TaskId("root.y"))
    y.deadline, y.deadline_supplied = datetime.now() + timedelta(minutes=3), False
    e._graph.save_task(y)
    monkeypatch.setattr(I, "seam_keeping_executor", lambda engine, task, other: task.assignee)
    ok, why = I._reassign(e, e.graph.get_task(TaskId("root.x")), "lead", {"extend_hours": 24}, "re-issue", None)
    assert ok, why
    assert e.graph.get_task(TaskId("root.x")).deadline > datetime.now() + timedelta(hours=1)
    e.stop()


def test_a_spent_deadline_is_refused_by_the_door_that_installs_it():
    e = _plan()
    x = e.graph.get_task(TaskId("root.x"))
    with pytest.raises(ValueError, match="refused"):
        e.revise(TaskId("root.x"), x.spec, AgentId("lead"), deadline=datetime.now() - timedelta(hours=1))
    last = [r for r in e.audit_log(TaskId("root.x")) if r.rejected][-1]
    assert "live deadline" in (last.error or ""), last
    e.stop()


def test_a_machine_re_issue_is_typed_and_no_mismatch_is_counted(monkeypatch):
    """§15.6 dial 3: the cause is the issuer's to give; untyped, every machine re-issue read as mis-delegation (C-F3)."""
    e = _plan()
    monkeypatch.setattr(I, "seam_keeping_executor", lambda engine, task, other: AgentId("w2"))
    ok, why = I._reassign(e, e.graph.get_task(TaskId("root.x")), "lead", {}, "re-issue", None)
    assert ok, why
    assert q_Del(e._graph) == 1.0
    e.stop()


def test_the_cause_the_machine_issuer_gives_is_the_cause_recorded(monkeypatch):
    """§15.6 dial 3: the cause is the issuer's own judgement; typed OTHER whatever it meant, a capability mismatch and a
    criterion the goal needed went unmeasured (critic r7, B3)."""
    e = _plan()
    n = len(e.all_tasks())
    monkeypatch.setattr(I, "seam_keeping_executor", lambda engine, task, other: AgentId("w2"))
    ok, why = I._reassign(e, e.graph.get_task(TaskId("root.x")), "lead", {"cause": "capability_mismatch"}, "re-issue", None)
    assert ok, why
    assert q_Del(e._graph) == 1.0 - 1 / n
    monkeypatch.setattr(I, "held_by_a_holder", lambda engine, issuer: False)
    ok, why = I._add_criterion(e, e.graph.get_task(TaskId("root.y")), "lead", {"criteria": [criterion("y2", "Y too")]},
                               "the goal needs it", None)
    assert ok, why
    assert q_T(e._graph) == 1.0 - 1 / n, "an unwritten criterion the issuer added is a spec defect (FM-1.f)"
    e.stop()


def test_a_refuted_challenge_is_off_q_T_and_an_answered_one_is_on_it():
    """§15.4 (v4.1): q_T counts "a CHALLENGE no REJECT_CHALLENGE refuted" (C-F2b)."""
    e = _plan()
    n = len(e.all_tasks())
    for sig, src in ((Signal.ACCEPT, "w"), (Signal.CHALLENGE, "w")):
        e.send_signal(SignalData(signal=sig, task_id=TaskId("root.x"), source=AgentId(src), reason="unclear"))
        e.wait_idle()
    e.send_signal(SignalData(signal=Signal.REJECT_CHALLENGE, task_id=TaskId("root.x"), source=AgentId("lead"),
                             reason="it is clear: see the criterion"))
    e.wait_idle()
    assert q_T(e._graph) == 1.0, "a refuted challenge counted"
    assert "q_T_from" not in T.metrics(e), "the explanation names a node the metric does not count (critic r7, B1)"
    e.send_signal(SignalData(signal=Signal.CHALLENGE, task_id=TaskId("root.x"), source=AgentId("w"), reason="still"))
    e.wait_idle()
    assert q_T(e._graph) == 1.0 - 1 / n, "a standing challenge did not count"
    assert T.metrics(e)["q_T_from"]["counted_against"] == ["root.x"]
    e.stop()


def test_an_accepted_dispute_keeps_the_rework_bound_in_force():
    """§12.3: `max_iterations` is a packet field only the issuer's act changes; every ACCEPT_CHALLENGE reset it to the
    default 12 (sync audit, A-F5)."""
    e = _plan()
    x = e.graph.get_task(TaskId("root.x"))
    e.revise(TaskId("root.x"), x.spec, AgentId("lead"), max_iterations=3)
    for sig, src in ((Signal.ACCEPT, "w"), (Signal.CHALLENGE, "w"), (Signal.ACCEPT_CHALLENGE, "lead")):
        e.send_signal(SignalData(signal=sig, task_id=TaskId("root.x"), source=AgentId(src), reason="unclear"))
        e.wait_idle()
    assert e.graph.get_state(TaskId("root.x")).name == "OFFERED"
    assert e.graph.get_task(TaskId("root.x")).max_iterations == 3
    e.stop()
