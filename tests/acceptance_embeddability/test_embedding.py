"""The six acceptance points of docs/embeddability_acceptance.md — pass/fail, fixed BEFORE any
embedding attempt. Green here (plus the layer gate) = the embeddability claim holds for this
host; anything the embedder had to ask a human = a documentation defect, logged separately."""
from datetime import datetime, timedelta

from gfso.core.types import (TaskId, AgentId, Signal, SignalData, Spec, Criteria,
                             AcceptedRiskItem, Predictability)


W = AgentId("host-worker")
R = AgentId("host-reviewer")


def _spec(desc, *crit, risks=False):
    # A DECOMPOSED node carries the register (§13.1); a leaf does not (CHECK-4 exempts D(t)=∅).
    return Spec(desc, tuple(Criteria(n, d) for n, d in crit),
                accepted_risks=(AcceptedRiskItem("an unmodelled environment fault",
                                                 Predictability.EXTRAORDINARY),) if risks else ())


def _build(host):
    """Root + two children with one sibling Dep seam (consumer depends on producer)."""
    host.send(SignalData(signal=Signal.ASSIGN, task_id=TaskId("root"), source=W,
                         spec=_spec("goal", ("g", "both parts done"), risks=True), assignee=W))
    host.send(SignalData(signal=Signal.ASSIGN, task_id=TaskId("prod"), source=W,
                         parent_id=TaskId("root"), covers=("g",),
                         deadline=datetime.now() + timedelta(hours=1),
                         spec=_spec("produce", ("p", "artifact exists")), assignee=W))
    host.send(SignalData(signal=Signal.ASSIGN, task_id=TaskId("cons"), source=W,
                         parent_id=TaskId("root"), covers=("g",),
                         spec=Spec("consume", (Criteria("c", "uses the artifact"),
                                               Criteria("dep__prod", "reads prod's output",
                                                        depends_on=TaskId("prod")))), assignee=W))


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


def test_4_virtual_clock_escalates_a_missed_deadline(host):
    _build(host)
    host.advance_clock(10 ** 7)                              # far past prod's 1h deadline
    st = host.state("prod")
    assert st in ("OVERDUE", "ESCALATED")
    host.advance_clock(10 ** 7)
    assert host.state("prod") == "ESCALATED"                 # repeated timeout → terminal


def test_5_cyclic_declaration_refused_discovered_cycle_named(host):
    _build(host)
    # a BLOCK naming the consumer as the producer's prerequisite = a discovered edge OPPOSITE
    # to the declared seam → CHECK-2 must NAME the cycle in the holes
    host.send(SignalData(signal=Signal.ACCEPT, task_id=TaskId("prod"), source=W))
    host.send(SignalData(signal=Signal.BLOCK, task_id=TaskId("prod"), source=W,
                         reason="actually needs cons", blocker_task_ids=(TaskId("cons"),)))
    dag = [h for h in host.graph_holes() if h["check"] == "CHECK-2:dag"]
    assert dag and "prod" in dag[0]["details"] and "cons" in dag[0]["details"]


def test_6_restart_hydrates_the_log_and_continues(host):
    _build(host)
    _drive_done(host, "prod")
    n_before = len(host.audit_rows())
    host2 = host.restart()
    assert host2.state("prod") == "DONE"                     # state = fold(log) survived
    assert len(host2.audit_rows()) == n_before               # nothing lost, nothing invented
    _drive_done(host2, "cons")
    assert host2.state("cons") == "DONE"
