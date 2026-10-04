"""R′ (canon §12.14 "Финальность") — the gated quasi-terminal exit.

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
from gfso.adapters.storage.sqlite import SqliteStorage
from gfso.core.types import (
    State, Signal, SignalData, TaskId, AgentId, Spec, Criteria, DoneReason,
)
from gfso.core.graph.metrics import q_V
from gfso import tools as T
from tests.support import criterion, make_engine, pinned, reviewer_passes, spec, REGISTER, REGISTER_SPLIT
from gfso.core.types import CriterionMapping


@pytest.fixture
def engine():
    e = make_engine(llm=None, check_interval=10_000)
    e.start()
    yield e
    e.stop()


def _drive_to_done(e: Engine, tid="n1", issuer="boss", worker="w", parent=None):
    """ASSIGN→ACCEPT→DELIVER→PASS a node (issuer = its own creator context).

    `parent` hangs it under an existing node — needed wherever a test wants two nodes, since a
    project has exactly one root and a second parentless node is refused."""
    e.assign_task(TaskId(tid), spec(), AgentId(issuer),
                  parent_id=TaskId(parent) if parent else None)
    e.wait_idle()
    for sd in (
        SignalData(signal=Signal.ACCEPT, task_id=TaskId(tid), source=AgentId(issuer)),
        SignalData(signal=Signal.DELIVER, task_id=TaskId(tid), source=AgentId(issuer), result="r"),
    ):
        e.send_signal(sd)
        e.wait_idle()
    reviewer_passes(e, TaskId(tid))
    e.send_signal(SignalData(signal=Signal.PASS, task_id=TaskId(tid), source=AgentId(issuer)))
    e.wait_idle()
    assert e.graph.get_state(TaskId(tid)) == State.DONE
    return e.graph.get_task(TaskId(tid))


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
    t = engine.graph.get_task(TaskId("n1"))
    assert t.state == State.OFFERED           # re-earn, not resurrect (§12.14)
    assert t.reopens == 1                    # counter spent
    assert t.done_reason is None             # V=pass NOT carried forward
    assert t.reopened_from_pass              # same criteria → q_V marker armed


def test_reopen_cancelled_to_review(engine):
    engine.assign_task(TaskId("c1"), spec(), AgentId("boss"))
    engine.wait_idle()
    _cancel(engine, "c1", "boss")
    assert engine.graph.get_state(TaskId("c1")) == State.ABANDONED
    engine.reopen(TaskId("c1"), AgentId("boss"))
    t = engine.graph.get_task(TaskId("c1"))
    assert t.state == State.OFFERED and t.reopens == 1
    assert not t.reopened_from_pass          # negative terminal — no pass to refute


def test_escalated_is_not_reopened_because_it_never_settled(engine):
    """R′ restores a node that FINISHED. ESCALATED did not finish — it is waiting for the issuer.

    The verb is refused and the refusal names the acts that do exist, because the two are different
    objects: a reopen spends a counter against the finality gate, while the moves out of ESCALATED
    are the issuer answering a question the protocol put to him (§12.5)."""
    engine.assign_task(TaskId("e1"), spec(), AgentId("boss"))
    engine.wait_idle()
    engine.send_signal(SignalData(signal=Signal.TIMEOUT, task_id=TaskId("e1")))  # OFFERED → ESCALATED
    engine.wait_idle()
    assert engine.graph.get_state(TaskId("e1")) == State.ESCALATED
    with pytest.raises(ValueError, match="waiting for YOU"):
        engine.reopen(TaskId("e1"), AgentId("boss"))
    # …and the act that DOES exist works: the issuer revises, the node returns to OFFERED.
    engine._revise(TaskId("e1"), spec(), AgentId("boss"))
    engine.wait_idle()
    assert engine.graph.get_state(TaskId("e1")) == State.OFFERED


# ── gate (ii): max_reopens, sign-agnostic ────────────────────────────────────

def test_max_reopens_exhaustion_locks_the_node(engine):
    _drive_to_done(engine)
    engine.reopen(TaskId("n1"), AgentId("boss"))          # 1st reopen: ok (default max=1)
    _cancel(engine, "n1", "boss")                          # settle it negatively this time
    assert engine.graph.get_state(TaskId("n1")) == State.ABANDONED
    with pytest.raises(ValueError):                        # counter is sign-agnostic and spent
        engine.reopen(TaskId("n1"), AgentId("boss"))
    assert engine.graph.get_task(TaskId("n1")).reopens == 1


# ── gate (i): the finality-gate of consumption ───────────────────────────────

def _parent_child(e: Engine, deliver_parent=False):
    """root(boss→pm) with child(pm→w); child driven to DONE(pass)."""
    e.assign_task(TaskId("root"), spec("root goal", "rc"), AgentId("pm"))
    e.wait_idle()
    e.decompose_task(TaskId("root"), [(TaskId("ch"), spec("child goal", "cc"), AgentId("w"))],
                     criterion_mappings=[CriterionMapping("rc", TaskId("ch"))],  # §11.5: L0-complete before exec
                     register=REGISTER_SPLIT)
    e.wait_idle()
    for sd in (
        SignalData(signal=Signal.ACCEPT, task_id=TaskId("ch"), source=AgentId("w")),
        SignalData(signal=Signal.DELIVER, task_id=TaskId("ch"), source=AgentId("w"), result="r"),
    ):
        e.send_signal(sd)
        e.wait_idle()
    reviewer_passes(e, TaskId("ch"))
    e.send_signal(SignalData(signal=Signal.PASS, task_id=TaskId("ch"), source=AgentId("pm")))
    e.wait_idle()
    assert e.graph.get_state(TaskId("ch")) == State.DONE
    if deliver_parent:  # the parent stakes its aggregate on the child's pass
        for sd in (
            SignalData(signal=Signal.ACCEPT, task_id=TaskId("root"), source=AgentId("pm")),
            SignalData(signal=Signal.DELIVER, task_id=TaskId("root"), source=AgentId("pm"), result="agg"),
        ):
            e.send_signal(sd)
            e.wait_idle()
        assert e.graph.get_state(TaskId("root")) == State.VALIDATING


def test_unconsumed_child_reopens(engine):
    _parent_child(engine, deliver_parent=False)  # parent still EXECUTING — no stake yet
    engine.reopen(TaskId("ch"), AgentId("pm"))
    assert engine.graph.get_state(TaskId("ch")) == State.OFFERED


def test_parent_delivered_aggregate_locks_child(engine):
    _parent_child(engine, deliver_parent=True)   # parent staked the aggregate upward
    with pytest.raises(ValueError):
        engine.reopen(TaskId("ch"), AgentId("pm"))
    assert engine.graph.get_state(TaskId("ch")) == State.DONE  # finally locked (consumed)


def test_refuted_coverage_gates_parent_redeliver(engine):
    """q_D made structural (§15.4): a parent FAIL on a criterion COVERED by a PASSed child refutes
    the mapping's entailment — re-DELIVERing the same aggregate over the untouched subtree is
    REFUSED (the decomposition is indicted, not the artifact); the plan's repair — a covering child added by a
    re-admission — re-opens the gate. The child the parent delivered over stays final: consumption once logged
    stands (§12.14), and past it the recovery is the issuer's re-decomposition. Removing any prompt line changes
    nothing — the engine enforces it."""
    engine.assign_task(TaskId("root"), spec("root goal", "rc"), AgentId("pm"))
    engine.wait_idle()
    engine.decompose_task(TaskId("root"), [(TaskId("ch"), spec("child goal", "cc"), AgentId("w"))],
                          criterion_mappings=[CriterionMapping("rc", TaskId("ch"))], register=REGISTER_SPLIT)
    engine.wait_idle()
    for sd in (
        SignalData(signal=Signal.ACCEPT, task_id=TaskId("ch"), source=AgentId("w")),
        SignalData(signal=Signal.DELIVER, task_id=TaskId("ch"), source=AgentId("w"), result="r"),
    ):
        engine.send_signal(sd)
        engine.wait_idle()
    reviewer_passes(engine, TaskId("ch"))
    engine.send_signal(SignalData(signal=Signal.PASS, task_id=TaskId("ch"), source=AgentId("pm")))
    engine.wait_idle()
    for sd in (
        SignalData(signal=Signal.ACCEPT, task_id=TaskId("root"), source=AgentId("pm")),
        SignalData(signal=Signal.DELIVER, task_id=TaskId("root"), source=AgentId("pm"), result="agg"),
    ):
        engine.send_signal(sd)
        engine.wait_idle()
    engine.record_exec_verdict(TaskId("root"), "FAIL", ["rc"], "validate_result")
    engine.send_signal(SignalData(signal=Signal.FAIL, task_id=TaskId("root"),
                                  source=AgentId("pm"), failed_criteria=("rc",)))
    engine.wait_idle()
    assert engine.graph.get_state(TaskId("root")) == State.REWORKING
    # same aggregate over the untouched subtree — the engine refuses (no prompt involved)
    engine.send_signal(SignalData(signal=Signal.DELIVER, task_id=TaskId("root"),
                                  source=AgentId("pm"), result="agg-v2"))
    engine.wait_idle()
    assert engine.graph.get_state(TaskId("root")) == State.REWORKING   # DELIVER rejected
    # the child the parent delivered over is consumed: no reopen gives it back (§12.14)
    with pytest.raises(ValueError):
        engine.reopen(TaskId("ch"), AgentId("pm"))
    assert engine.graph.get_state(TaskId("ch")) == State.DONE
    # the plan is repaired instead — a re-admission adds the child that carries rc — and the parent re-aggregates
    engine.decompose_task(TaskId("root"), [(TaskId("fix"), spec("the missing passage", "fc"), AgentId("w"))],
                          criterion_mappings=[CriterionMapping("rc", TaskId("fix"))])
    engine.wait_idle()
    engine.send_signal(SignalData(signal=Signal.DELIVER, task_id=TaskId("root"),
                                  source=AgentId("pm"), result="agg-v3"))
    engine.wait_idle()
    assert engine.graph.get_state(TaskId("root")) == State.VALIDATING


def test_a_parents_fail_does_not_give_back_a_child_it_delivered_over(engine):
    """Consumption is logged and, once logged, stands (§12.14): the parent's DELIVER put its aggregate on the child's
    pass, and the parent's later FAIL does not unmake that — reopening the child would unmake a settlement the
    record shows was relied on. (The engine used to release it on the parent's rework — BCB/93 run 9 — admitting a
    move the canon does not, §12.16 (i).) The recoveries are the canon's: the whole's executor repairs what it
    delivers, and a part read on that delivery fails there (§8.4); or the issuer re-decomposes."""
    _parent_child(engine, deliver_parent=True)   # parent VALIDATING — the aggregate rests on the child
    with pytest.raises(ValueError):
        engine.reopen(TaskId("ch"), AgentId("pm"))
    engine.send_signal(SignalData(signal=Signal.FAIL, task_id=TaskId("root"),
                                  source=AgentId("pm"), failed_criteria=("rc",)))
    engine.wait_idle()
    assert engine.graph.get_state(TaskId("root")) == State.REWORKING
    with pytest.raises(ValueError):
        engine.reopen(TaskId("ch"), AgentId("pm"))
    assert engine.graph.get_state(TaskId("ch")) == State.DONE


def test_dep_consumer_built_on_result_locks_producer(engine):
    # Producer and consumer are SIBLINGS under the project's one root: a project has exactly one
    # (the root carries the goal's criteria, and V(root) is the goal's verdict), so two top-level
    # nodes with a Dep between them is not a shape the graph admits.
    engine.assign_task(TaskId("goal"), spec("the goal", "gc1", "gc2"), AgentId("boss"))
    engine.wait_idle()
    cons_spec = Spec(description="consumer", criteria=(
        Criteria("uses", "builds on prod output", depends_on=TaskId("prod")),
        Criteria("own", "the consumer's own result holds", check=pinned("own"))))
    # …the whole plan covers the goal BEFORE any child executes: admitted whole (CHECK-1, §9.5, §11.5)
    engine.decompose_task(TaskId("goal"), [(TaskId("prod"), spec(), AgentId("boss")),
                                           (TaskId("cons"), cons_spec, AgentId("boss"))],
                          [CriterionMapping("gc1", TaskId("prod")), CriterionMapping("gc2", TaskId("cons"))],
                          register=REGISTER_SPLIT)
    engine.wait_idle()
    for sd in (
        SignalData(signal=Signal.ACCEPT, task_id=TaskId("prod"), source=AgentId("boss")),
        SignalData(signal=Signal.DELIVER, task_id=TaskId("prod"), source=AgentId("boss"), result="r"),
    ):
        engine.send_signal(sd)
        engine.wait_idle()
    reviewer_passes(engine, TaskId("prod"))
    engine.send_signal(SignalData(signal=Signal.PASS, task_id=TaskId("prod"), source=AgentId("boss")))
    engine.wait_idle()
    assert engine.graph.get_state(TaskId("prod")) == State.DONE
    # consumer declares the dep and ACCEPTs into work — it read-and-built on prod's result
    engine.send_signal(SignalData(signal=Signal.ACCEPT, task_id=TaskId("cons"), source=AgentId("boss")))
    engine.wait_idle()
    assert engine.graph.get_state(TaskId("cons")) == State.EXECUTING
    with pytest.raises(ValueError):
        engine.reopen(TaskId("prod"), AgentId("boss"))
    # consumer still in OFFERED (not yet built on it) would NOT consume:
    assert engine.graph.get_task(TaskId("prod")).reopens == 0


def test_cancelled_consumed_only_when_settled_and_replanned(engine):
    """Negative finality: consumed ⟺ cascade settled ∧ the hole replanned around (FM-1.e)."""
    engine.assign_task(TaskId("root"), spec("root goal", "rc"), AgentId("pm"))
    engine.wait_idle()
    engine.decompose_task(TaskId("root"), [(TaskId("a"), spec("a", "ac"), AgentId("w"))],
                          [CriterionMapping("rc", TaskId("a"))], register=REGISTER_SPLIT)
    engine.wait_idle()
    _cancel(engine, "a", "pm", executor="w")
    assert engine.graph.get_state(TaskId("a")) == State.ABANDONED
    # settled (leaf, no descendants) but NOT replanned → still reopenable
    assert not engine._graph.is_consumed(engine.graph.get_task(TaskId("a")))
    # the parent replans around the hole: a replacement child admitted covering the same criterion (§11.5)
    engine.assign_task(TaskId("b"), spec("b", "bc"), AgentId("w"), parent_id=TaskId("root"), covers=("rc",))
    engine.wait_idle()
    assert engine._graph.is_consumed(engine.graph.get_task(TaskId("a")))  # revival = double coverage
    with pytest.raises(ValueError):
        engine.reopen(TaskId("a"), AgentId("pm"))


# ── anti-fake: the verdict is re-earned, never carried forward ───────────────

def test_stale_verdict_cannot_pass_self_pass_gate_after_reopen(engine):
    """The pre-reopen PASS verdict must not re-open the verifier≠executor gate (§12.14 anti-fake)."""
    e = engine
    e.assign_task(TaskId("s1"), spec(), AgentId("me"))
    e.wait_idle()
    for sd in (
        SignalData(signal=Signal.ACCEPT, task_id=TaskId("s1"), source=AgentId("me")),
        SignalData(signal=Signal.DELIVER, task_id=TaskId("s1"), source=AgentId("me"), result="r"),
    ):
        e.send_signal(sd)
        e.wait_idle()
    reviewer_passes(e, TaskId("s1"))
    e.send_signal(SignalData(signal=Signal.PASS, task_id=TaskId("s1"), source=AgentId("me")))
    e.wait_idle()
    assert e.graph.get_state(TaskId("s1")) == State.DONE

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
    assert e.graph.get_state(TaskId("s1")) == State.VALIDATING  # rejected, still validating
    # a FRESH independent verdict re-opens the way
    reviewer_passes(e, TaskId("s1"))
    e.send_signal(SignalData(signal=Signal.PASS, task_id=TaskId("s1"), source=AgentId("me")))
    e.wait_idle()
    assert e.graph.get_state(TaskId("s1")) == State.DONE


def _reopen_and_fail(engine, result: str):
    engine.reopen(TaskId("n1"), AgentId("boss"))
    for sd in (
        SignalData(signal=Signal.ACCEPT, task_id=TaskId("n1"), source=AgentId("boss")),
        SignalData(signal=Signal.DELIVER, task_id=TaskId("n1"), source=AgentId("boss"), result=result),
        SignalData(signal=Signal.FAIL, task_id=TaskId("n1"), source=AgentId("boss"),
                   failed_criteria=("c1",)),
    ):
        engine.send_signal(sd)
        engine.wait_idle()
    return engine.graph.get_task(TaskId("n1"))


def test_a_fresh_fail_on_another_artifact_refutes_nothing_of_the_old_pass(engine):
    """§15.4: "a PASS was recorded, later failed AS DELIVERED under the criteria it passed" — a fresh run on another
    artifact is a verdict on that artifact, not a refutation of the old PASS (§12.14)."""
    _drive_to_done(engine)
    t = _reopen_and_fail(engine, "r2")
    assert t.state == State.REWORKING and not t.false_positive and not t.reopened_from_pass
    assert q_V(engine._graph) == 1.0


def test_fresh_fail_after_pass_reopen_is_qv_member(engine):
    """§15.4: a DONE-reopen whose fresh run fails the re-delivered logged artifact = exactly q_V's pass→later-fail
    member."""
    _drive_to_done(engine)
    assert q_V(engine._graph) == 1.0
    engine.reopen(TaskId("n1"), AgentId("boss"))
    for sd in (
        SignalData(signal=Signal.ACCEPT, task_id=TaskId("n1"), source=AgentId("boss")),
        SignalData(signal=Signal.DELIVER, task_id=TaskId("n1"), source=AgentId("boss"), result="r"),
        SignalData(signal=Signal.FAIL, task_id=TaskId("n1"), source=AgentId("boss"),
                   failed_criteria=("c1",)),
    ):
        engine.send_signal(sd)
        engine.wait_idle()
    t = engine.graph.get_task(TaskId("n1"))
    assert t.state == State.REWORKING
    assert t.false_positive          # the old pass is refuted by fresh contact
    assert not t.reopened_from_pass  # marker consumed at the first fresh verdict
    # …AND THE TERM REACHES THE NUMBER. q_V's population was read off the CURRENT state
    # (`settled_positive`), and by now the node is REWORKING — so the refuted pass dropped out of
    # the numerator AND the denominator together, and the one event §15.4 names as q_V's carrier
    # moved the metric by exactly nothing. It read 1.0 over a pass that had just been taken back.
    assert q_V(engine._graph) == 0.0


# ── persistence ──────────────────────────────────────────────────────────────

def test_reopen_fields_roundtrip_sqlite(tmp_path):
    st = SqliteStorage(str(tmp_path / "r.db"))
    e = make_engine(st, llm=None, check_interval=10_000)
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


def test_passing_a_leaf_says_what_it_freezes():
    """The finality rule is right and it was learnt at the wrong moment.

    Once a parent stakes its aggregate on a child, that child is CONSUMED and cannot be reopened
    (§12.14) — so a defect later found in the code that leaf's contract owns is repaired by
    re-decomposing AROUND it. A tester met that rule only when the root's validator refuted a shared
    function, four round trips after the leaf had passed (CLI door, 2026-09-02). Said at the PASS it
    is something to plan around; said at the reopen it is only a wall.
    """
    e = make_engine(check_interval=10_000)
    e.start()
    T.create_task(e, "root", {"description": "r", "criteria": [criterion("c", "C")]}, assignee="boss")
    T.decompose(e, "root", [{"task_id": "kid", "spec": {"description": "k", "criteria": [criterion("k1", "K")]},
                             "assignee": "boss", "covers": ["c"]}], accepted_risks=REGISTER)
    T.signal(e, "kid", "ACCEPT", "boss")
    T.signal(e, "kid", "DELIVER", "boss", result="wrote the leaf; ran its check, it printed OK", self_validation="PASS")

    out = T.signal(e, "kid", "PASS", "boss")
    assert out["state"] == "DONE"
    assert "CONSUMED" in out["frozen_now"] and "re-decomposing around it" in out["frozen_now"]
    e.stop()


def test_reopen_drops_a_mapping_whose_child_is_gone():
    """A REOPEN is a re-authorship, so the mappings that point at nothing go with it.

    The code path existed with no test behind it (found by an outside verification pass over the
    v4.1 batch). What it guards: a node reopened after its child was cancelled kept COVERING its
    criterion through a tombstone, and CHECK-1 read that criterion as covered — a coverage claim
    resting on a node that is not there (FM-1.a, §8.3, read green).
    """
    e = make_engine()
    e.start()
    try:
        T.create_task(e, "p", {"description": "a goal", "criteria": [criterion("c", "C")]}, assignee="worker")
        e.wait_idle()
        T.signal(e, "p", "ACCEPT", "worker")
        T.decompose(e, "p", [{"task_id": "kid", "spec": {"description": "a child", "criteria": [criterion("k", "K")]},
                              "assignee": "worker", "covers": ["c"]}], accepted_risks=REGISTER)
        e.wait_idle()
        assert any(m.criterion_name == "c" for m in e.graph.get_task(TaskId("p")).criterion_mappings)

        # the parent settles, then the child is cancelled out from under the mapping
        T.signal(e, "kid", "ACCEPT", "worker")
        T.signal(e, "kid", "CANCEL", "worker", reason="not needed")
        T.signal(e, "kid", "CONFIRM_CANCEL", "worker")
        e.wait_idle()
        assert e.graph.get_state(TaskId("kid")) == State.ABANDONED

        T.signal(e, "p", "CANCEL", "worker", reason="park it")
        T.signal(e, "p", "CONFIRM_CANCEL", "worker")
        e.wait_idle()
        assert e.graph.get_state(TaskId("p")) == State.ABANDONED

        e.reopen(TaskId("p"), AgentId("worker"))
        e.wait_idle()
        kept = [m.criterion_name for m in e.graph.get_task(TaskId("p")).criterion_mappings]
        assert "c" not in kept, (
            f"the reopened node still covers 'c' through an ABANDONED child: {kept}")
    finally:
        e.stop()


def test_a_child_the_replan_covered_around_is_consumed(engine):
    """A re-admission after the child settled gives a criterion it is mapped to a responsible child it did not have
    before: the plan moved past it, and a reopen would put a live orphan beside the replanned cover (§12.14)."""
    _parent_child(engine, deliver_parent=False)
    engine.decompose_task(TaskId("root"), [(TaskId("cover"), spec("covers rc again", "vc"), AgentId("w"))],
                          criterion_mappings=[CriterionMapping("rc", TaskId("cover"))])
    engine.wait_idle()
    with pytest.raises(ValueError):
        engine.reopen(TaskId("ch"), AgentId("pm"))
    assert engine.graph.get_state(TaskId("ch")) == State.DONE


def test_a_sibling_covering_from_the_first_admission_consumes_nothing(engine):
    """The control: co-covering in the split as first admitted is no replan (§12.14)."""
    engine.assign_task(TaskId("root"), spec("root goal", "rc"), AgentId("pm"))
    engine.wait_idle()
    engine.decompose_task(TaskId("root"), [(TaskId("ch"), spec("child goal", "cc"), AgentId("w")),
                                           (TaskId("co"), spec("co-cover", "oc"), AgentId("w"))],
                          criterion_mappings=[CriterionMapping("rc", TaskId("ch")), CriterionMapping("rc", TaskId("co"))],
                          register=REGISTER_SPLIT)
    engine.wait_idle()
    for sd in (SignalData(signal=Signal.ACCEPT, task_id=TaskId("ch"), source=AgentId("w")),
               SignalData(signal=Signal.DELIVER, task_id=TaskId("ch"), source=AgentId("w"), result="r")):
        engine.send_signal(sd)
        engine.wait_idle()
    reviewer_passes(engine, TaskId("ch"))
    engine.send_signal(SignalData(signal=Signal.PASS, task_id=TaskId("ch"), source=AgentId("pm")))
    engine.wait_idle()
    engine.reopen(TaskId("ch"), AgentId("pm"))
    assert engine.graph.get_state(TaskId("ch")) == State.OFFERED


def test_a_child_mapped_to_no_criterion_of_the_parents_version_is_consumed(engine):
    """The parent's current version maps it to nothing: reopening it would put a live orphan in the split (§12.14)."""
    _parent_child(engine, deliver_parent=False)
    engine._revise(TaskId("root"), spec("root goal, restated", "rc2"), AgentId("pm"))
    engine.wait_idle()
    assert not [m for m in engine.graph.get_task(TaskId("root")).criterion_mappings if m.child_id == TaskId("ch")]
    with pytest.raises(ValueError):
        engine.reopen(TaskId("ch"), AgentId("pm"))
