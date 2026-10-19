"""FM-1 repair routing at a contact-refuted decomposition (canon §8.3, §12.3, §15.4).

A parent criterion that FAILs while every mapped child passes its own is the q_D event and an FM-1
defect of the DECOMPOSITION (FM-1.d: `⋀criteria(tⱼ) ⊭ cᵢ`; FM-1.f: a criterion nobody wrote). The
engine refuses the re-delivery of an unchanged aggregate — and routes the repair to a REVISION OF
THE PARENT under Inv-1, which does not cascade and never reaches the consumption gate.

The repair and its false twin wear the same shape at the re-delivery: adding coverage so the
children carry cᵢ, versus lowering cᵢ to what they already deliver. Each test below plants exactly
one class and asserts the engine tells them apart; without the discriminator both moves would have
to be forbidden and the only legal repair would go with them.
"""
import json

import pytest

from gfso.engine import Engine
from gfso.core.types import (
    State, Signal, SignalData, TaskId, AgentId, Spec, Criteria, CriterionMapping,
)
from gfso.engine.validation import ValidationError, validate_signal
from tests.support import REGISTER_SPLIT, REGISTER_ITEMS, make_engine, pinned, reviewer_passes


@pytest.fixture(autouse=True)
def _l2_gate_on(monkeypatch):
    """The suite-wide default is the EXPLORE opt-out (`conftest`); the discriminator's undecidable
    middle is exactly the branch that leans on the checker, so this module runs the gate ON — the
    two EXPLORE tests below turn it back off and own that half."""
    monkeypatch.setenv("GFSO_L2_GATE", "1")


@pytest.fixture
def engine():
    e = make_engine(llm=None, check_interval=10_000)
    e.start()
    yield e
    e.stop()


def _refuted(e: Engine, root_criterion="rc", description="rc description"):
    """root(criterion) ← child that PASSes its own criteria; then contact FAILs the root on it.

    Leaves the root in REWORKING with a generation-stamped FAIL verdict — the state every test starts
    from, and the state the live `markdown_renderer` run reached (`EVIDENCE_LOG` §13.3).
    """
    e.assign_task(TaskId("root"), Spec("root goal", (Criteria(root_criterion, description,
                                                 check=pinned(root_criterion)),),
                                     accepted_risks=REGISTER_ITEMS),
                  AgentId("pm"))
    e.wait_idle()
    e.decompose_task(TaskId("root"),
                     [(TaskId("ch"), Spec("child goal", (Criteria("cc", "cc description", check=pinned("cc")),)),
                       AgentId("w"))],
                     criterion_mappings=[CriterionMapping(root_criterion, TaskId("ch"))], register=REGISTER_SPLIT)
    e.wait_idle()
    _review(e)                              # the plan was reviewed clean — and contact refuted it anyway
    for sd in (
        SignalData(signal=Signal.ACCEPT, task_id=TaskId("ch"), source=AgentId("w")),
        SignalData(signal=Signal.DELIVER, task_id=TaskId("ch"), source=AgentId("w"), result="r"),
    ):
        e.send_signal(sd)
        e.wait_idle()
    reviewer_passes(e, TaskId("ch"))
    e.send_signal(SignalData(signal=Signal.PASS, task_id=TaskId("ch"), source=AgentId("pm")))
    e.wait_idle()
    for sd in (
        SignalData(signal=Signal.ACCEPT, task_id=TaskId("root"), source=AgentId("pm")),
        SignalData(signal=Signal.DELIVER, task_id=TaskId("root"), source=AgentId("pm"), result="agg"),
    ):
        e.send_signal(sd)
        e.wait_idle()
    e.record_exec_verdict(TaskId("root"), "FAIL", [root_criterion], "validate_result")
    e.send_signal(SignalData(signal=Signal.FAIL, task_id=TaskId("root"), source=AgentId("pm"),
                             failed_criteria=(root_criterion,)))
    e.wait_idle()
    assert e.graph.get_state(TaskId("root")) == State.REWORKING


def _revise_root(e: Engine, criteria):
    """Repair by the canonical route: re-ASSIGN the parent under Inv-1, then re-accept it."""
    e.edit_criteria(TaskId("root"), criteria, AgentId("pm"))
    e.wait_idle()
    assert e.graph.get_state(TaskId("root")) == State.OFFERED      # revision → re-consent, no cascade
    assert e.graph.get_state(TaskId("ch")) == State.DONE          # subtree retained (Inv-1)
    e.send_signal(SignalData(signal=Signal.ACCEPT, task_id=TaskId("root"), source=AgentId("pm")))
    e.wait_idle()


def _deliver(e: Engine):
    """The re-delivery, taken through the validator directly so the refusal is readable."""
    validate_signal(SignalData(signal=Signal.DELIVER, task_id=TaskId("root"),
                               source=AgentId("pm"), result="agg-v2"), e._graph, e._audit)


def _review(e: Engine, node="root", covered=True, verdicts=()):
    rec = {"node_id": node, "gate_passed": True, "semantic_covered": covered,
           "criteria_verdicts": list(verdicts), "conflicts": [], "model": "test",
           "ts": "2026-08-11 00:00:00"}
    e._graph._storage.store_critique(TaskId(node), json.dumps(rec))
    t = e.graph.get_task(TaskId(node))
    t.verified = True
    e._graph.save_task(t)


# ── the refusal names the canonical repair (corner #5: it used to route the repair DOWN) ──────

def test_unrepaired_redeliver_is_refused_and_routed_to_parent_revision(engine):
    _refuted(engine)
    with pytest.raises(ValidationError) as ex:
        _deliver(engine)
    msg = str(ex.value)
    assert "re-admit root's split with a corrected mapping" in msg   # the canonical repair, named (§11.5, §2.4)
    assert "Rework flows DOWN" not in msg                      # the route that hit the wall
    assert "reopen the covering child" not in msg


# ── false closes: the two moves that wear the repair's shape ──────────────────────────────────

def test_dropping_the_refuted_criterion_is_refused(engine):
    """FM-1.f in reverse: a criterion with no fail-extension forbids nothing (§1.3)."""
    _refuted(engine)
    _revise_root(engine, (Criteria("other", "an unrelated criterion", check=pinned("other")),))
    with pytest.raises(ValidationError) as ex:
        _deliver(engine)
    assert "REMOVED rather than covered" in str(ex.value)


def test_loosening_a_numeric_bound_is_refused(engine):
    """The bound moves, the work does not — decidable on the numeric tier (CHECK-7, §9.6)."""
    _refuted(engine, description="latency < 200")
    _revise_root(engine, (Criteria("rc", "latency < 300", check=pinned("rc")),))
    with pytest.raises(ValidationError) as ex:
        _deliver(engine)
    assert "LOOSENED" in str(ex.value)


def test_tightening_a_numeric_bound_is_not_a_false_close(engine):
    """The negative control of the control: a STRICTER bound is not a shrunk fail-extension, so it
    must not be refused as one — it takes the ordinary edited route (a fresh verdict)."""
    _refuted(engine, description="latency < 200")
    _revise_root(engine, (Criteria("rc", "latency < 100", check=pinned("rc")),))
    _review(engine)
    _deliver(engine)                                           # admitted


# ── the undecidable middle: admitted once the checks have spoken again ────────────────────────

def test_edited_criterion_needs_a_current_level2_verdict(engine):
    _refuted(engine)
    _revise_root(engine, (Criteria("rc", "rc description, sharpened after contact", check=pinned("rc")),))
    with pytest.raises(ValidationError) as ex:
        _deliver(engine)
    assert "no CURRENT Level-2 verdict" in str(ex.value)


def test_edited_criterion_with_open_gaps_is_refused(engine):
    _refuted(engine)
    _revise_root(engine, (Criteria("rc", "rc description, sharpened after contact", check=pinned("rc")),))
    _review(engine, covered=False,
            verdicts=[{"criterion": "rc", "verdict": "insufficient"}])
    with pytest.raises(ValidationError) as ex:
        _deliver(engine)
    assert "still open" in str(ex.value)


def test_edited_criterion_passes_once_the_review_is_clean(engine):
    """The legal repair must survive: revise the parent, re-run the check, re-aggregate."""
    _refuted(engine)
    _revise_root(engine, (Criteria("rc", "rc description, sharpened after contact", check=pinned("rc")),))
    _review(engine)
    _deliver(engine)                                           # no refusal
    engine.send_signal(SignalData(signal=Signal.DELIVER, task_id=TaskId("root"),
                                  source=AgentId("pm"), result="agg-v2"))
    engine.wait_idle()
    assert engine.graph.get_state(TaskId("root")) == State.VALIDATING


def test_explore_branch_opts_out_of_the_level2_half(monkeypatch):
    """`GFSO_L2_GATE=0` is the canon's EXPLORE branch (§9.9) — it drops the L2 requirement and
    nothing else: the two false closes stay refused (they are decided, not reviewed)."""
    monkeypatch.setenv("GFSO_L2_GATE", "0")
    e = make_engine(llm=None, check_interval=10_000)
    e.start()
    try:
        _refuted(e)
        _revise_root(e, (Criteria("rc", "rc description, sharpened after contact", check=pinned("rc")),))
        _deliver(e)                                            # admitted with no fresh review at all
    finally:
        e.stop()


def test_explore_branch_still_refuses_a_dropped_criterion(monkeypatch):
    monkeypatch.setenv("GFSO_L2_GATE", "0")
    e = make_engine(llm=None, check_interval=10_000)
    e.start()
    try:
        _refuted(e)
        _revise_root(e, (Criteria("other", "an unrelated criterion", check=pinned("other")),))
        with pytest.raises(ValidationError) as ex:
            _deliver(e)
        assert "REMOVED rather than covered" in str(ex.value)
    finally:
        e.stop()


def _co_covered(when: str):
    """`rc` co-covered by `root.a` (passed) and `root.h`; `h` is cancelled and settled BEFORE the root's FAIL on `rc`, or
    after it, or never (it passes)."""
    e = make_engine(llm=None, check_interval=10_000)
    e.start()
    s = lambda sig, tid, src, **kw: (e.send_signal(SignalData(signal=sig, task_id=TaskId(tid), source=AgentId(src),
                                                              **kw)), e.wait_idle())
    e.assign_task(TaskId("root"), Spec("root goal", (Criteria("rc", "rc description", check=pinned("rc")),),
                                       accepted_risks=REGISTER_ITEMS), AgentId("pm"))
    e.wait_idle()
    s(Signal.ACCEPT, "root", "pm")
    e.decompose_task(TaskId("root"), [
        (TaskId("root.a"), Spec("part a", (Criteria("ca", "a", check=pinned("ca")),)), AgentId("w")),
        (TaskId("root.h"), Spec("part h", (Criteria("ch", "h", check=pinned("ch")),)), AgentId("w"))],
        criterion_mappings=[CriterionMapping("rc", TaskId("root.a")), CriterionMapping("rc", TaskId("root.h"))],
        register=REGISTER_SPLIT)
    e.wait_idle()
    _review(e)
    for kid in ("root.a",) + (("root.h",) if when == "never" else ()):
        s(Signal.ACCEPT, kid, "w"), s(Signal.DELIVER, kid, "w", result="r")
        reviewer_passes(e, TaskId(kid)), s(Signal.PASS, kid, "pm")
    cancel = lambda: (s(Signal.ACCEPT, "root.h", "w"), s(Signal.CANCEL, "root.h", "pm", reason="closed"),
                      s(Signal.CONFIRM_CANCEL, "root.h", "w"))
    if when == "before":
        cancel()
    s(Signal.DELIVER, "root", "pm", result="agg")
    e.record_exec_verdict(TaskId("root"), "FAIL", ["rc"], "validate_result")
    s(Signal.FAIL, "root", "pm", failed_criteria=("rc",))
    if when == "after":
        cancel()
    return e


@pytest.mark.parametrize("when, refuted", [("never", True), ("before", True), ("after", False)])
def test_a_coverer_out_of_the_plan_before_the_fail_leaves_the_split_refuted(when, refuted):
    """GB_coreutils_tmiy4m001: the machine issuer CANCELled `head`, which co-covered root criteria. Read off the raw
    mappings, a coverer that was never DONE made no failed criterion read as refuted, so the root's FAIL opened no
    repair and its executor was sent to write `head` inside the aggregate. The split as it stands (§12.6) is what the
    FAIL refutes; a child that left the plan AFTER the FAIL is a changed coverage — a repair — as before."""
    e = _co_covered(when)
    try:
        assert bool(e.decomposition_refuted(TaskId("root"))) is refuted, e.decomposition_refuted(TaskId("root"))
    finally:
        e.stop()
