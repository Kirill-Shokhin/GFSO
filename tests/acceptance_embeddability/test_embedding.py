"""The six acceptance points of docs/embeddability_acceptance.md — pass/fail, fixed BEFORE any
embedding attempt. Green here (plus the layer gate) = the embeddability claim holds for this
host; anything the embedder had to ask a human = a documentation defect, logged separately."""
from datetime import datetime, timedelta

import pytest

from gfso.core.graph.model import dep_order_refutations
from gfso.core.types import (TaskId, AgentId, Probe, Signal, SignalData, Spec, Criteria,
                             AcceptedRiskItem, Predictability, Register)


W = AgentId("host-worker")
R = AgentId("host-reviewer")


def _pinned(name):
    """The procedure a criterion of this name pins (§2/A1) — a contract whose criteria decide
    nothing is not admitted to execution, so the host contract is driven with real ones."""
    return (Probe(f"{name} holds", f"check {name}", "it holds"),)


def _spec(desc, *crit):
    return Spec(desc, tuple(Criteria(n, d, check=_pinned(n)) for n, d in crit))


# A SPLIT carries the register, its decomposer's (§9.2), admitted with it (§11.5); a leaf has none.
_REGISTER = Register((AcceptedRiskItem("an unmodelled environment fault", Predictability.EXTRAORDINARY,
                                       "no precedent here", "one occurs", 0.01, "the run is resumed"),
                      AcceptedRiskItem.denial_of(0.1, "the host's stated estimate")))


def _build(host):
    """Root + two children with one sibling Dep seam (consumer depends on producer)."""
    host.send(SignalData(signal=Signal.ASSIGN, task_id=TaskId("root"), source=W,
                         spec=_spec("goal", ("g", "both parts done")), assignee=W))
    host.admit("root", [SignalData(signal=Signal.ASSIGN, task_id=TaskId("prod"), source=W,
                         parent_id=TaskId("root"), covers=("g",),
                         deadline=datetime.now() + timedelta(minutes=30),
                         spec=_spec("produce", ("p", "artifact exists")), assignee=W),
                        SignalData(signal=Signal.ASSIGN, task_id=TaskId("cons"), source=W,
                         parent_id=TaskId("root"), covers=("g",),
                         spec=Spec("consume", (Criteria("c", "uses the artifact",
                                                        check=_pinned("c")),
                                               # a seam criterion is exempt from pinning a check:
                                               # what decides it is the producer's own verdict
                                               Criteria("dep__prod", "reads prod's output",
                                                        depends_on=TaskId("prod")))), assignee=W)],
               _REGISTER, str(W))


def _drive_done(host, tid):
    host.send(SignalData(signal=Signal.ACCEPT, task_id=TaskId(tid), source=W))
    host.send(SignalData(signal=Signal.DELIVER, task_id=TaskId(tid), source=W,
                         result=f"{tid}: done"))
    host.record_verdict(tid, "PASS", [], str(R))   # the gate needs the independent record
    host.send(SignalData(signal=Signal.PASS, task_id=TaskId(tid), source=W))


def test_1_build_lands_in_the_log(host):
    _build(host)
    assert host.state("root") == "OFFERED" and host.state("cons") == "OFFERED"
    signals = [r["signal"] for r in host.audit_rows()]
    assert signals.count("ASSIGN") == 3                      # every mutation IS a logged signal


def test_2_drive_respects_the_dep_order(host):
    _build(host)
    # the consumer cannot deliver against a producer that has not delivered: the host's own
    # frontier/gating must hold the order (however it implements it) — prod first, then cons
    _drive_done(host, "prod")
    assert host.state("prod") == "DONE"
    _drive_done(host, "cons")
    assert host.state("cons") == "DONE"
    _drive_done(host, "root")
    assert host.state("root") == "DONE"


def test_3_foreign_executor_signal_is_rejected_and_audited(host):
    _build(host)
    host.send(SignalData(signal=Signal.ACCEPT, task_id=TaskId("prod"), source=AgentId("mallory")))
    assert host.state("prod") == "OFFERED"                    # did not move
    rej = [r for r in host.audit_rows() if r.get("rejected")]
    assert rej and rej[-1]["signal"] == "ACCEPT"             # the refusal is ON THE RECORD


def test_4_virtual_clock_escalates_a_missed_deadline(host, monkeypatch):
    monkeypatch.setenv("GFSO_L2_GATE", "0")     # the plan's verification bought by contact (§9.9): prod may start
    _build(host)
    host.send(SignalData(signal=Signal.ACCEPT, task_id=TaskId("prod"), source=W))   # in work, bounded by its deadline
    host.advance_clock(45 * 60)           # past prod's TYPED 30-minute deadline, short of any other bound
    assert host.state("prod") == "ESCALATED"                 # the lapse hands over at once
    host.advance_clock(10 ** 7)                              # the issuer's silence closes it
    assert host.state("prod") in ("CANCELLING", "ABANDONED")


def test_5_cyclic_declaration_refused_discovered_cycle_named(host):
    _build(host)
    # a BLOCK naming the consumer as the producer's prerequisite = a discovered edge OPPOSITE
    # to the declared seam → the graph NAMES it as the plan's order refuted by contact (§15.5).
    # It is a provisional record, not an edge of E_Dep: CHECK-2 is not red over it, and the
    # plan it would have frozen stays admitted.
    host.send(SignalData(signal=Signal.ACCEPT, task_id=TaskId("prod"), source=W))
    host.send(SignalData(signal=Signal.BLOCK, task_id=TaskId("prod"), source=W,
                         reason="actually needs cons", blocker_task_ids=(TaskId("cons"),)))
    refuted = dep_order_refutations(host.graph)
    assert [(str(e.from_id), str(e.to_id)) for e in refuted] == [("cons", "prod")]
    assert not [h for h in host.graph_holes() if h["check"] == "CHECK-2:dag"]


def test_6_restart_hydrates_the_log_and_continues(host):
    _build(host)
    _drive_done(host, "prod")
    n_before = len(host.audit_rows())
    host2 = host.restart()
    assert host2.state("prod") == "DONE"                     # state = fold(log) survived
    assert len(host2.audit_rows()) == n_before               # nothing lost, nothing invented
    _drive_done(host2, "cons")
    assert host2.state("cons") == "DONE"


def test_7_an_admission_takes_no_other_nodes_child_and_writes_nothing_it_refuses(host):
    """The host's admission is the engine's act (§11.5: whole or nothing; §15.3: one parent): a split naming a node
    that is already another's child is refused before anything is written."""
    a_ = lambda k, s, cov=(), parent="root": SignalData(signal=Signal.ASSIGN, task_id=TaskId(k), source=W,
                                                        parent_id=TaskId(parent), spec=s, assignee=W, covers=cov)
    host.send(SignalData(signal=Signal.ASSIGN, task_id=TaskId("root"), source=W, spec=_spec("goal", ("g1", "one"), ("g2", "two")),
                         assignee=W))
    host.admit("root", [a_("a", _spec("a", ("a_ok", "a")), ("g1",)), a_("b", _spec("b", ("b_ok", "b")), ("g2",))], _REGISTER, str(W))
    for tid in ("a", "b"):
        host.send(SignalData(signal=Signal.ACCEPT, task_id=TaskId(tid), source=W))
    assert host.state("b") == "EXECUTING"
    with pytest.raises(ValueError, match="one parent"):
        host.admit("a", [a_("b", _spec("sub of a", ("s_ok", "s")), ("a_ok",), parent="a")], _REGISTER, str(W))
    assert host.state("b") == "EXECUTING" and not host.graph_holes()     # b's contract was not re-offered
