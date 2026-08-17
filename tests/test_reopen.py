"""R′ (canon §14.3 "Финальность") — the gated quasi-terminal exit.

DONE→OFFERED and ABANDONED→OFFERED are ONE re-ASSIGN mechanism (not a 13th signal) under a
double gate: (i) the finality-gate — the terminal is not CONSUMED in the graph (positive:
the parent staked its aggregate on V=pass / a Dep-consumer built on the result; negative:
the cascade settled AND the parent replanned around the hole); (ii) max_reopens — one
sign-agnostic per-node counter (Inv-5). The verdict is RE-EARNED in OFFERED, never
resurrected: V=pass drops, the recorded independent verdict goes stale by generation, and
a fresh run that FAILs after a same-criteria pass-reopen is q_V's pass→later-fail member.
"""
from datetime import datetime, timedelta

import pytest

from gfso.engine import Engine
from gfso.adapters.storage.memory import MemoryStorage
from gfso.adapters.storage.sqlite import SqliteStorage
from gfso.adapters.agents.human import HumanAgent
from gfso.core.types import (
    AcceptedRiskItem, State, Signal, SignalData, TaskId, AgentId, Spec, Criteria, DoneReason,
    Predictability,
)
from gfso.core.graph.metrics import q_V


def _spec(desc="goal", crit="c1"):
    return Spec(description=desc, criteria=(Criteria(crit, f"{crit} description"),),
                accepted_risks=(AcceptedRiskItem("an unmodelled environment fault",
                                                 Predictability.EXTRAORDINARY),))


@pytest.fixture
def engine():
    e = Engine(MemoryStorage(), HumanAgent(), llm=None, check_interval=10_000)
    e.start()
    yield e
    e.stop()


def _drive_to_done(e: Engine, tid="n1", issuer="boss", worker="w"):
    """ASSIGN→ACCEPT→DELIVER→PASS a standalone root (issuer = its own creator context)."""
    e.assign_task(TaskId(tid), _spec(), AgentId(issuer))
    e.wait_idle()
    for sd in (
        SignalData(signal=Signal.ACCEPT, task_id=TaskId(tid), source=AgentId(issuer)),
        SignalData(signal=Signal.DELIVER, task_id=TaskId(tid), source=AgentId(issuer), result="r"),
    ):
        e.send_signal(sd)
        e.wait_idle()
    e.record_reviewer_verdict(TaskId(tid), "PASS", [], "reviewer")
    e.send_signal(SignalData(signal=Signal.PASS, task_id=TaskId(tid), source=AgentId(issuer)))
    e.wait_idle()
    assert e.get_state(TaskId(tid)) == State.DONE
    return e.get_task(TaskId(tid))


def _cancel(e: Engine, tid, issuer, executor=None):
    e.send_signal(SignalData(signal=Signal.CANCEL, task_id=TaskId(tid), source=AgentId(issuer)))
    e.wait_idle()
    e.send_signal(SignalData(signal=Signal.CONFIRM_CANCEL, task_id=TaskId(tid),
                             source=AgentId(executor or issuer)))
    e.wait_idle()


# ── the edge itself ──────────────────────────────────────────────────────────

def test_reopen_done_to_review_spends_counter_and_drops_verdict(engine):
    t = _drive_to_done(engine)
    assert t.done_reason == DoneReason.PASS and t.reopens == 0
    engine.reopen(TaskId("n1"), AgentId("boss"))
    t = engine.get_task(TaskId("n1"))
    assert t.state == State.OFFERED           # re-earn, not resurrect (§14.3)
    assert t.reopens == 1                    # counter spent
    assert t.done_reason is None             # V=pass NOT carried forward
    assert t.reopened_from_pass              # same criteria → q_V marker armed


def test_reopen_cancelled_to_review(engine):
    engine.assign_task(TaskId("c1"), _spec(), AgentId("boss"))
    engine.wait_idle()
    _cancel(engine, "c1", "boss")
    assert engine.get_state(TaskId("c1")) == State.ABANDONED
    engine.reopen(TaskId("c1"), AgentId("boss"))
    t = engine.get_task(TaskId("c1"))
    assert t.state == State.OFFERED and t.reopens == 1
    assert not t.reopened_from_pass          # negative terminal — no pass to refute


def test_escalated_stays_fully_terminal(engine):
    engine.assign_task(TaskId("e1"), _spec(), AgentId("boss"))
    engine.wait_idle()
    for _ in range(2):  # OFFERED → OVERDUE → ESCALATED
        engine.send_signal(SignalData(signal=Signal.TIMEOUT, task_id=TaskId("e1")))
        engine.wait_idle()
    assert engine.get_state(TaskId("e1")) == State.ESCALATED
    with pytest.raises(ValueError):
        engine.reopen(TaskId("e1"), AgentId("boss"))


# ── gate (ii): max_reopens, sign-agnostic ────────────────────────────────────

def test_max_reopens_exhaustion_locks_the_node(engine):
    _drive_to_done(engine)
    engine.reopen(TaskId("n1"), AgentId("boss"))          # 1st reopen: ok (default max=1)
    _cancel(engine, "n1", "boss")                          # settle it negatively this time
    assert engine.get_state(TaskId("n1")) == State.ABANDONED
    with pytest.raises(ValueError):                        # counter is sign-agnostic and spent
        engine.reopen(TaskId("n1"), AgentId("boss"))
    assert engine.get_task(TaskId("n1")).reopens == 1


# ── gate (i): the finality-gate of consumption ───────────────────────────────

def _parent_child(e: Engine, deliver_parent=False):
    """root(boss→pm) with child(pm→w); child driven to DONE(pass)."""
    from gfso.core.types import CriterionMapping
    e.assign_task(TaskId("root"), _spec("root goal", "rc"), AgentId("pm"))
    e.wait_idle()
    e.decompose_task(TaskId("root"), [(TaskId("ch"), _spec("child goal", "cc"), AgentId("w"))],
                     criterion_mappings=[CriterionMapping("rc", TaskId("ch"))])  # §13.4: L0-complete before exec
    e.wait_idle()
    for sd in (
        SignalData(signal=Signal.ACCEPT, task_id=TaskId("ch"), source=AgentId("w")),
        SignalData(signal=Signal.DELIVER, task_id=TaskId("ch"), source=AgentId("w"), result="r"),
    ):
        e.send_signal(sd)
        e.wait_idle()
    e.record_reviewer_verdict(TaskId("ch"), "PASS", [], "reviewer")
    e.send_signal(SignalData(signal=Signal.PASS, task_id=TaskId("ch"), source=AgentId("pm")))
    e.wait_idle()
    assert e.get_state(TaskId("ch")) == State.DONE
    if deliver_parent:  # the parent stakes its aggregate on the child's pass
        for sd in (
            SignalData(signal=Signal.ACCEPT, task_id=TaskId("root"), source=AgentId("pm")),
            SignalData(signal=Signal.DELIVER, task_id=TaskId("root"), source=AgentId("pm"), result="agg"),
        ):
            e.send_signal(sd)
            e.wait_idle()
        assert e.get_state(TaskId("root")) == State.VALIDATING


def test_unconsumed_child_reopens(engine):
    _parent_child(engine, deliver_parent=False)  # parent still EXECUTING — no stake yet
    engine.reopen(TaskId("ch"), AgentId("pm"))
    assert engine.get_state(TaskId("ch")) == State.OFFERED


def test_parent_delivered_aggregate_locks_child(engine):
    _parent_child(engine, deliver_parent=True)   # parent staked the aggregate upward
    with pytest.raises(ValueError):
        engine.reopen(TaskId("ch"), AgentId("pm"))
    assert engine.get_state(TaskId("ch")) == State.DONE  # finally locked (consumed)


def test_refuted_coverage_gates_parent_redeliver(engine):
    """q_D made structural (§15.2): a parent FAIL on a criterion COVERED by a PASSed child refutes
    the mapping's entailment — re-DELIVERing the same aggregate over the untouched subtree is
    REFUSED (the decomposition is indicted, not the artifact); touching the child (reopen) re-opens
    the gate. Removing any prompt line changes nothing — the engine enforces it."""
    import time as _t
    from gfso.core.types import CriterionMapping
    engine.assign_task(TaskId("root"), _spec("root goal", "rc"), AgentId("pm"))
    engine.wait_idle()
    engine.decompose_task(TaskId("root"), [(TaskId("ch"), _spec("child goal", "cc"), AgentId("w"))],
                          criterion_mappings=[CriterionMapping("rc", TaskId("ch"))])
    engine.wait_idle()
    for sd in (
        SignalData(signal=Signal.ACCEPT, task_id=TaskId("ch"), source=AgentId("w")),
        SignalData(signal=Signal.DELIVER, task_id=TaskId("ch"), source=AgentId("w"), result="r"),
    ):
        engine.send_signal(sd)
        engine.wait_idle()
    engine.record_reviewer_verdict(TaskId("ch"), "PASS", [], "reviewer")
    engine.send_signal(SignalData(signal=Signal.PASS, task_id=TaskId("ch"), source=AgentId("pm")))
    engine.wait_idle()
    for sd in (
        SignalData(signal=Signal.ACCEPT, task_id=TaskId("root"), source=AgentId("pm")),
        SignalData(signal=Signal.DELIVER, task_id=TaskId("root"), source=AgentId("pm"), result="agg"),
    ):
        engine.send_signal(sd)
        engine.wait_idle()
    engine.record_exec_verdict(TaskId("root"), "FAIL", ["rc"], "validate_result")
    _t.sleep(0.01)                                   # the FAIL restamps root AFTER ch's DONE stamp
    engine.send_signal(SignalData(signal=Signal.FAIL, task_id=TaskId("root"),
                                  source=AgentId("pm"), failed_criteria=("rc",)))
    engine.wait_idle()
    assert engine.get_state(TaskId("root")) == State.REWORKING
    # same aggregate over the untouched subtree — the engine refuses (no prompt involved)
    engine.send_signal(SignalData(signal=Signal.DELIVER, task_id=TaskId("root"),
                                  source=AgentId("pm"), result="agg-v2"))
    engine.wait_idle()
    assert engine.get_state(TaskId("root")) == State.REWORKING   # DELIVER rejected
    # rework flows DOWN: the refused delivery released the child — reopen it
    engine.reopen(TaskId("ch"), AgentId("pm"))
    assert engine.get_state(TaskId("ch")) == State.OFFERED
    # decomposition re-authored (child touched) — the parent may re-aggregate again
    engine.send_signal(SignalData(signal=Signal.DELIVER, task_id=TaskId("root"),
                                  source=AgentId("pm"), result="agg-v3"))
    engine.wait_idle()
    assert engine.get_state(TaskId("root")) == State.VALIDATING


def test_parent_rework_releases_child_for_reopen(engine):
    """A REFUSED delivery is a dead stake: parent FAIL→REWORKING must RELEASE the child —
    rework flows DOWN through reopen, the graph keeps telling the truth about where the
    defect lives (observed live: BCB/93 run 9 — the agent could only mutate the artifact
    under frozen-DONE children because the consumed-gate still counted the failed stake)."""
    _parent_child(engine, deliver_parent=True)   # parent VALIDATING — stake pending
    with pytest.raises(ValueError):
        engine.reopen(TaskId("ch"), AgentId("pm"))   # pending stake still locks
    engine.send_signal(SignalData(signal=Signal.FAIL, task_id=TaskId("root"),
                                  source=AgentId("pm"), failed_criteria=("rc",)))
    engine.wait_idle()
    assert engine.get_state(TaskId("root")) == State.REWORKING
    engine.reopen(TaskId("ch"), AgentId("pm"))       # refused stake releases the child
    assert engine.get_state(TaskId("ch")) == State.OFFERED


def test_dep_consumer_built_on_result_locks_producer(engine):
    prod = _drive_to_done(engine, tid="prod", issuer="boss")
    # consumer declares the dep and ACCEPTs into work — it read-and-built on prod's result
    spec = Spec(description="consumer", criteria=(
        Criteria("uses", "builds on prod output", depends_on=TaskId("prod")),))
    engine.assign_task(TaskId("cons"), spec, AgentId("boss"))
    engine.wait_idle()
    engine.send_signal(SignalData(signal=Signal.ACCEPT, task_id=TaskId("cons"), source=AgentId("boss")))
    engine.wait_idle()
    assert engine.get_state(TaskId("cons")) == State.EXECUTING
    with pytest.raises(ValueError):
        engine.reopen(TaskId("prod"), AgentId("boss"))
    # consumer still in OFFERED (not yet built on it) would NOT consume:
    assert engine.get_task(TaskId("prod")).reopens == 0


def test_cancelled_consumed_only_when_settled_and_replanned(engine):
    """Negative finality: consumed ⟺ cascade settled ∧ the hole replanned around (FM-1.e)."""
    engine.assign_task(TaskId("root"), _spec("root goal", "rc"), AgentId("pm"))
    engine.wait_idle()
    engine.decompose_task(TaskId("root"), [(TaskId("a"), _spec("a", "ac"), AgentId("w"))])
    engine.wait_idle()
    engine.map_criterion(TaskId("root"), TaskId("a"), "rc")
    _cancel(engine, "a", "pm", executor="w")
    assert engine.get_state(TaskId("a")) == State.ABANDONED
    # settled (leaf, no descendants) but NOT replanned → still reopenable
    assert not engine._graph.is_consumed(engine.get_task(TaskId("a")))
    # the parent replans around the hole: a replacement child covering the same criterion
    engine.decompose_task(TaskId("root"), [(TaskId("b"), _spec("b", "bc"), AgentId("w"))])
    engine.wait_idle()
    engine.map_criterion(TaskId("root"), TaskId("b"), "rc")
    assert engine._graph.is_consumed(engine.get_task(TaskId("a")))  # revival = double coverage
    with pytest.raises(ValueError):
        engine.reopen(TaskId("a"), AgentId("pm"))


# ── anti-fake: the verdict is re-earned, never carried forward ───────────────

def test_stale_verdict_cannot_pass_self_pass_gate_after_reopen(engine):
    """The pre-reopen PASS verdict must not re-open the verifier≠executor gate (§14.3 anti-fake)."""
    e = engine
    e.assign_task(TaskId("s1"), _spec(), AgentId("me"))
    e.wait_idle()
    for sd in (
        SignalData(signal=Signal.ACCEPT, task_id=TaskId("s1"), source=AgentId("me")),
        SignalData(signal=Signal.DELIVER, task_id=TaskId("s1"), source=AgentId("me"), result="r"),
    ):
        e.send_signal(sd)
        e.wait_idle()
    e.record_reviewer_verdict(TaskId("s1"), "PASS", [], "reviewer")
    e.send_signal(SignalData(signal=Signal.PASS, task_id=TaskId("s1"), source=AgentId("me")))
    e.wait_idle()
    assert e.get_state(TaskId("s1")) == State.DONE

    e.reopen(TaskId("s1"), AgentId("me"))
    for sd in (
        SignalData(signal=Signal.ACCEPT, task_id=TaskId("s1"), source=AgentId("me")),
        SignalData(signal=Signal.DELIVER, task_id=TaskId("s1"), source=AgentId("me"), result="r2"),
    ):
        e.send_signal(sd)
        e.wait_idle()
    # self-PASS with only the GENERATION-STALE verdict on record → the gate refuses
    e.send_signal(SignalData(signal=Signal.PASS, task_id=TaskId("s1"), source=AgentId("me")))
    e.wait_idle()
    assert e.get_state(TaskId("s1")) == State.VALIDATING  # rejected, still validating
    # a FRESH independent verdict re-opens the way
    e.record_reviewer_verdict(TaskId("s1"), "PASS", [], "reviewer")
    e.send_signal(SignalData(signal=Signal.PASS, task_id=TaskId("s1"), source=AgentId("me")))
    e.wait_idle()
    assert e.get_state(TaskId("s1")) == State.DONE


def test_fresh_fail_after_pass_reopen_is_qv_member(engine):
    """§14.3: a DONE-reopen whose fresh run fails = exactly q_V's pass→later-fail member."""
    _drive_to_done(engine)
    assert q_V(engine._graph) == 1.0
    engine.reopen(TaskId("n1"), AgentId("boss"))
    for sd in (
        SignalData(signal=Signal.ACCEPT, task_id=TaskId("n1"), source=AgentId("boss")),
        SignalData(signal=Signal.DELIVER, task_id=TaskId("n1"), source=AgentId("boss"), result="r2"),
        SignalData(signal=Signal.FAIL, task_id=TaskId("n1"), source=AgentId("boss"),
                   failed_criteria=("c1",)),
    ):
        engine.send_signal(sd)
        engine.wait_idle()
    t = engine.get_task(TaskId("n1"))
    assert t.state == State.REWORKING
    assert t.false_positive          # the old pass is refuted by fresh contact
    assert not t.reopened_from_pass  # marker consumed at the first fresh verdict


# ── persistence ──────────────────────────────────────────────────────────────

def test_reopen_fields_roundtrip_sqlite(tmp_path):
    st = SqliteStorage(str(tmp_path / "r.db"))
    e = Engine(st, HumanAgent(), llm=None, check_interval=10_000)
    e.start()
    try:
        _drive_to_done(e, tid="p1", issuer="boss")
        e.reopen(TaskId("p1"), AgentId("boss"))
    finally:
        e.stop()
    st2 = SqliteStorage(str(tmp_path / "r.db"))
    t = st2.get_task(TaskId("p1"))
    assert t.state == State.OFFERED
    assert t.reopens == 1 and t.max_reopens == 1 and t.reopened_from_pass
    st2.close()


def test_reopen_is_offered_and_audited(engine):
    """The affordance shows on quasi-terminals; the rejected-final attempt lands in Thm 11."""
    t = _drive_to_done(engine)
    assert Signal.ASSIGN in engine.available_actions(TaskId("n1"))
    engine.reopen(TaskId("n1"), AgentId("boss"))
    _cancel(engine, "n1", "boss")
    with pytest.raises(ValueError):
        engine.reopen(TaskId("n1"), AgentId("boss"))  # exhausted → FSM guard rejects
    rejected = [a for a in engine.audit_log(TaskId("n1")) if a.rejected and a.signal == Signal.ASSIGN]
    assert rejected, "the refused reopen must be audit-visible (Thm 11)"
