"""A refuted pass is recovered, and by whom (§12.14: REOPEN leads into OFFERED, not DONE — the verdict is re-earned by
fresh contact; REOPEN is the issuer's re-ASSIGN, §10.1).

Three rests of one rule (`frontier.refuted_reading`). The node reopened and re-earning its PASS is no refuted pass; an
ancestor reopened and re-earning its PASS over a delivery made after the refuting record covers it, so COMPLETE is
answered and its reopen is not offered again. Under a mode, the reopen is the system's move where the system holds the
issuer role, and where it does not and nothing else may make it, the run's customer is told in one line. The machine
issuer's own signatures read the same rule: a PASS over a reopenable refuted part is refused, its FAIL is not.
"""
from __future__ import annotations

import pytest

from gfso import delegate as DG
from gfso import issuer as I
from gfso import tools as T
from gfso import tools_llm as TL
from gfso.core.types import AgentId, Signal, State, TaskId
from tests.support import REGISTER, carried_by_the_system, make_engine, reviewer_passes
from tests.test_a_refuted_pass_withholds_only_what_rests_on_it import _a_root, _child, _on, _passed, _refuted


@pytest.fixture(autouse=True)
def _no_plan_gate(monkeypatch):
    monkeypatch.setenv("GFSO_L2_GATE", "0")


@pytest.fixture
def e():
    e = make_engine()
    e.start()
    yield e
    e.stop()


def _root_passes(e, by="boss"):
    T.signal(e, "root", "DELIVER", by, result="integrated")
    e.wait_idle()
    reviewer_passes(e, TaskId("root"), reviewer="validator")
    T.signal(e, "root", "PASS", e.graph.issuer_of(TaskId("root")))
    e.wait_idle()


def test_the_refuted_node_reopened_and_passed_again_is_no_refuted_pass(e):
    _a_root(e, ["a", "b"], {"root.c0": "a", "root.c1": "b"})
    _passed(e, "root.c0", "boss")
    _passed(e, "root.c1", "boss")
    _refuted(e, "root.c1")
    e.reopen(TaskId("root.c1"), AgentId("boss"))
    e.wait_idle()
    _passed(e, "root.c1", "boss")

    assert not e.refuted_passes(), "a PASS re-earned on a new delivery after its reopen still read as refuted"
    assert _on(e.next_steps(), "root", "deliver")
    _root_passes(e)
    assert e.next_steps()["complete"] is True


def test_the_goal_reopened_and_passed_again_over_a_fresh_delivery_answers_complete(e):
    _a_root(e, ["a", "b"], {"root.c0": "a", "root.c1": "b"})
    _passed(e, "root.c0", "boss")
    _passed(e, "root.c1", "boss")
    _root_passes(e)
    _refuted(e, "root.c1")
    assert e.next_steps()["complete"] is False

    e.reopen(TaskId("root"), AgentId(str(e.graph.issuer_of(TaskId("root")))))
    e.wait_idle()
    T.signal(e, "root", "ACCEPT", "boss")
    e.wait_idle()
    _root_passes(e)
    assert e.refuted_passes() == ["root.c1"], "the record stays on the log"
    out = e.next_steps()
    assert out["complete"] is True, "the goal's PASS re-earned after its reopen held COMPLETE back for good"
    assert e.nothing_left(), "the goal's end was not read where the mode's hold lapses"


def test_a_whole_reopened_and_passed_again_is_not_offered_its_reopen_again(e):
    _a_root(e, ["a", "b"], {"root.x": "a", "root.y": "b"}, by={"root.x": "mid"})
    T.signal(e, "root.x", "ACCEPT", "mid")
    T.decompose(e, "root.x", [_child("root.x.0", "a"), _child("root.x.1", "a")], accepted_risks=REGISTER)
    e.wait_idle()
    _passed(e, "root.x.0", "mid")
    _passed(e, "root.x.1", "mid")
    _passed(e, "root.x", "boss", by="mid")
    _refuted(e, "root.x.0")
    e.reopen(TaskId("root.x"), AgentId("boss"))
    e.wait_idle()
    _passed(e, "root.x", "boss", by="mid")

    out = e.next_steps()
    assert not _on(out, "root", "revise"), "a whole that re-earned its PASS over the refuted part was offered its reopen again"
    assert "re-earned" in out["refuted_passes_note"]


def _refuted_under_boss(e):
    _a_root(e, ["a", "b"], {"root.c0": "a", "root.c1": "b"})
    _passed(e, "root.c0", "boss")
    _passed(e, "root.c1", "boss")
    carried_by_the_system(e)
    _refuted(e, "root.c1")


def test_under_auto_the_system_reopens_where_it_holds_the_issuer_role(e):
    _refuted_under_boss(e)
    machine = {"boss": {"kind": "llm-executor"}}
    e.workforce.publish_roster({"boss": "llm-executor"})
    assert TL.needs_its_customer(TL.next_steps(e)) is None, "the customer was called to a move the system makes"
    DG.reopen_refuted_passes(e, machine)
    e.wait_idle()
    assert e.graph.get_state(TaskId("root.c1")) == State.OFFERED, "the system held the issuer role and made no reopen"


def test_under_auto_a_settled_goal_over_a_refuted_part_is_reopened_by_the_system(e):
    """The reopen climbs to the settled goal; its issuer a machine, the system makes it — a person, the customer hears."""
    _a_root(e, ["a", "b"], {"root.c0": "a", "root.c1": "b"})
    _passed(e, "root.c0", "boss")
    _passed(e, "root.c1", "boss")
    _root_passes(e)
    carried_by_the_system(e)
    _refuted(e, "root.c1")
    assert not e.nothing_left(), "the goal's end was read over a refuted pass it still rests on"
    assert "'root' for 'root.c1'" in TL.needs_its_customer(TL.next_steps(e))
    DG.reopen_refuted_passes(e, {"boss": {"kind": "llm-executor"}})
    e.wait_idle()
    assert e.graph.get_state(TaskId("root")) == State.OFFERED


def test_under_auto_a_reopen_nothing_in_the_system_makes_reaches_the_customer(e):
    _refuted_under_boss(e)
    DG.reopen_refuted_passes(e, {})
    e.wait_idle()
    assert e.graph.get_state(TaskId("root.c1")) == State.DONE, "the system reopened under a person's issuer role"
    why = TL.needs_its_customer(TL.next_steps(e))
    assert why and "root.c1" in why and "\n" not in why, "`gfso wait` stayed silent over a reopen nobody makes"


def test_under_auto_a_recovery_past_its_reopen_nothing_in_the_system_makes_reaches_the_customer(e):
    """The goal's reopen spent, a later FAIL refutes its part again: no reopen is open, COMPLETE never comes, and the
    one recovery — a new goal — is the customer's to hear, or `gfso wait` stood silent for good."""
    _a_root(e, ["a", "b"], {"root.c0": "a", "root.c1": "b"})
    _passed(e, "root.c0", "boss")
    _passed(e, "root.c1", "boss")
    _root_passes(e)
    e.reopen(TaskId("root"), AgentId(str(e.graph.issuer_of(TaskId("root")))))
    e.wait_idle()
    T.signal(e, "root", "ACCEPT", "boss")
    e.wait_idle()
    _root_passes(e)
    carried_by_the_system(e)
    _refuted(e, "root.c1")
    out = TL.next_steps(e)
    assert out["complete"] is False and not out["steps"] and not out.get("reopen_unmade")
    why = TL.needs_its_customer(out)
    assert why and "root.c1" in why and "new goal" in why and "\n" not in why, (
        "a refuted pass past its reopen with no maker in the system left `gfso wait` silent")


def test_the_machine_issuer_signs_no_pass_over_a_reopenable_refuted_part(e):
    _a_root(e, ["a", "b"], {"root.c0": "a", "root.c1": "b"})
    _passed(e, "root.c0", "boss")
    T.signal(e, "root.c1", "ACCEPT", "w")
    T.signal(e, "root", "DELIVER", "boss", result="integrated early")
    e.wait_idle()
    _passed(e, "root.c1", "boss")
    _refuted(e, "root.c1")
    reviewer_passes(e, TaskId("root"), reviewer="validator")
    issuer, why = str(e.graph.issuer_of(TaskId("root"))), []

    assert not I.signal_ok(e, TaskId("root"), Signal.PASS, issuer, _why=why)
    assert e.graph.get_state(TaskId("root")) == State.VALIDATING and "root.c1" in why[0]
    assert I.signal_ok(e, TaskId("root"), Signal.FAIL, issuer, failed_criteria=("b",))
    assert e.graph.get_state(TaskId("root")) == State.REWORKING
