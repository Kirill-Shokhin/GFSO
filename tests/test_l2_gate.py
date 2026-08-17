"""The pre-execution causal gate — an ENGINEERING corner (`formal/README.md` #10), not a canon row.

The canon gates execution on the SYNTACTIC level (§13.4) and files the Pragmatic level as runtime
detection; what is mechanised here is its verify-vs-explore decision (§13.5) taken once: the causal
check must have RUN over this version of the plan and its findings must be dispositioned.

L0 gates topology: a parent criterion needs a covering child. It cannot see whether that child's
criteria, taken as facts about the world, actually CARRY the parent criterion — an L0-clean plan can
be causally hollow, and the hole then surfaces only after the code exists, as a refused delivery
(q_D↓, rework). The checker sees that class before contact, so the engine refuses the FIRST execution
step (a child's ACCEPT) while its parent's decomposition has no current, discharged Level-2 verdict.

What is gated is that the check RAN and its findings were DISPOSITIONED — never that the checker is
right (L2 is an approximation over the faithfulness axis; contact keeps the last word, §13.5).
Hence two discharges: fix the plan (any edit stales the review — with its disputes) or record why the
finding is wrong (`dispute_finding`). `GFSO_L2_GATE=0` is the explicit EXPLORE opt-out.

These tests drive REAL review records through the storage the checker writes to (no model runs).
"""
import json
import os

import pytest

from gfso import tools
from gfso.engine import Engine
from gfso.adapters.storage.memory import MemoryStorage
from gfso.adapters.agents.human import HumanAgent
from gfso.core.types import (AcceptedRiskItem, AgentId, Criteria, CriterionMapping, Predictability,
                             Signal, SignalData, Spec, State, TaskId)


@pytest.fixture(autouse=True)
def _gate_on():
    """This module owns the gate-ON behavior (the suite default is OFF — see conftest)."""
    prior = os.environ.get("GFSO_L2_GATE")
    os.environ["GFSO_L2_GATE"] = "1"
    yield
    os.environ["GFSO_L2_GATE"] = prior if prior is not None else "0"


@pytest.fixture
def engine():
    e = Engine(MemoryStorage(), HumanAgent(), llm=None, check_interval=10_000)
    e.start()
    yield e
    e.stop()


def _spec(desc, *crits, risks=True):
    return Spec(description=desc, criteria=tuple(Criteria(c, f"{c} description") for c in crits),
                accepted_risks=(AcceptedRiskItem("an unmodelled environment fault",
                                                 Predictability.EXTRAORDINARY),) if risks else ())


def _plan(e, risks=True):
    """root(c1,c2) → child covering both. L0-clean; nothing reviewed yet."""
    e.assign_task(TaskId("root"), _spec("goal", "c1", "c2", risks=risks), AgentId("agent"))
    e.wait_idle()
    e.decompose_task(TaskId("root"), [(TaskId("kid"), _spec("part", "k1"), AgentId("agent"))],
                     criterion_mappings=[CriterionMapping("c1", TaskId("kid")),
                                         CriterionMapping("c2", TaskId("kid"))])
    e.wait_idle()
    from gfso.engine.validation import _l0_holes
    holes = _l0_holes(e._graph, e.get_task(TaskId("root")))
    assert holes == ([] if risks else holes)      # clean with the register; without it, CHECK-4 alone
    assert risks or [h.check_name for h in holes] == ["CHECK-4:accepted_risks"]


def _review(e, node="root", covered=True, verdicts=(), conflicts=()):
    """Write the record `review_decomposition` would write, and mark the node reviewed."""
    rec = {"node_id": node, "gate_passed": True, "semantic_covered": covered,
           "criteria_verdicts": list(verdicts), "conflicts": list(conflicts),
           "model": "test", "ts": "2026-07-19 00:00:00"}
    e._graph._storage.store_critique(TaskId(node), json.dumps(rec))
    t = e.get_task(TaskId(node))
    t.verified = True
    e._graph.save_task(t)


def _accept(e, tid="kid"):
    e.send_signal(SignalData(signal=Signal.ACCEPT, task_id=TaskId(tid), source=AgentId("agent")))
    e.wait_idle()
    return e.get_task(TaskId(tid)).state


# ── the gate itself ───────────────────────────────────────────────────────────────────────────

def test_unreviewed_plan_blocks_execution(engine):
    """The defect the gate exists for: an L0-clean plan goes to code unchecked."""
    _plan(engine)
    assert _accept(engine) == State.OFFERED      # refused — no Level-2 verdict for this plan


def test_clean_review_admits_execution(engine):
    _plan(engine)
    _review(engine, covered=True)
    assert _accept(engine) == State.EXECUTING


def test_open_gap_blocks_execution(engine):
    _plan(engine)
    _review(engine, covered=False,
            verdicts=[{"criterion": "c1", "verdict": "sufficient", "why": "ok"},
                      {"criterion": "c2", "verdict": "insufficient", "why": "k1 does not carry c2"}])
    assert _accept(engine) == State.OFFERED


def test_conflict_blocks_execution(engine):
    """FM-2 residue: children whose criteria contradict each other (CHECK-8 cannot see it)."""
    _plan(engine)
    _review(engine, covered=False, verdicts=[{"criterion": "c1", "verdict": "sufficient", "why": ""},
                                             {"criterion": "c2", "verdict": "sufficient", "why": ""}],
            conflicts=[{"between": ["kid", "root"], "why": "return types contradict"}])
    assert _accept(engine) == State.OFFERED


def test_no_verdict_is_never_read_as_clean(engine):
    """Fail-CLOSED: the checker ran but returned nothing readable (or an INCOMPLETE verdict)."""
    _plan(engine)
    _review(engine, covered=None)
    assert _accept(engine) == State.OFFERED


def test_gate_off_is_the_explore_branch(engine):
    _plan(engine)
    os.environ["GFSO_L2_GATE"] = "0"
    assert _accept(engine) == State.EXECUTING


# ── the degenerate plan: "this goal is one unit of work" (D(t)=∅) ─────────────────────────────

def test_a_leaf_executes_freely_the_shape_is_the_executors_call(engine):
    """How many subtasks a goal splits into is the executor's domain call — NOT imposed from outside
    (§10). So a node the executor takes as a LEAF starts work with no atomicity verdict demanded; the
    root seam still validates the whole result against the issuer's criteria. (Removed: an earlier gate
    made a leaf justify being atomic — that set the subtask count from outside and deadlocked
    auto_decompose's own builder.)"""
    engine.assign_task(TaskId("solo"), _spec("goal", "c1", "c2"), AgentId("agent"))
    engine.wait_idle()
    step = tools.next_step(engine, "solo")          # before taking it, the frontier leaves the shape open
    assert step["action"] == "accept" and "YOUR call" in step["directive"]
    assert _accept(engine, "solo") == State.EXECUTING


def test_the_gate_still_holds_a_CHOSEN_decomposition(engine):
    """Removing the leaf gate does not weaken the core: a decomposition the executor DID choose still
    cannot run its children until its causal check is discharged."""
    _plan(engine)                        # root chose to split into `kid`
    assert _accept(engine) == State.OFFERED          # no L2 verdict on the chosen split yet
    _review(engine, "root", covered=True)
    assert _accept(engine) == State.EXECUTING


# ── discharging a finding ─────────────────────────────────────────────────────────────────────

def test_dispute_discharges_its_own_finding_only(engine):
    _plan(engine)
    _review(engine, covered=False,
            verdicts=[{"criterion": "c1", "verdict": "insufficient", "why": "gap A"},
                      {"criterion": "c2", "verdict": "uncertain", "why": "gap B"}])
    out = tools.dispute_finding(engine, "root", "c1", "k1 covers c1 through the documented contract")
    assert out["open_findings"] == ["c2"]
    assert _accept(engine) == State.OFFERED          # c2 still open
    tools.dispute_finding(engine, "root", "c2", "uncertainty is about wording, not entailment")
    assert _accept(engine) == State.EXECUTING

    stored = engine.get_critique(TaskId("root"))["disputes"]
    assert set(stored) == {"c1", "c2"} and stored["c1"]["by"] == "agent"  # provenance, §6.2


def test_dispute_needs_a_current_verdict_naming_that_finding(engine):
    _plan(engine)
    with pytest.raises(ValueError, match="no current Level-2 verdict"):
        tools.dispute_finding(engine, "root", "c1", "…")
    _review(engine, covered=False,
            verdicts=[{"criterion": "c2", "verdict": "insufficient", "why": "gap"}])
    with pytest.raises(ValueError, match="not an open Level-2 finding"):
        tools.dispute_finding(engine, "root", "c1", "…")   # not flagged — nothing to dispute


def test_editing_the_plan_stales_the_review_and_its_disputes(engine):
    """A dispute never launders a finding across plan versions."""
    _plan(engine)
    _review(engine, covered=False,
            verdicts=[{"criterion": "c2", "verdict": "insufficient", "why": "gap"}])
    tools.dispute_finding(engine, "root", "c2", "holds via the child's documented output")
    assert _accept(engine) == State.EXECUTING

    tools.edit_criteria(engine, "kid", [{"name": "k1", "description": "changed"},
                                        {"name": "k2", "description": "added"}], agent="agent")
    engine.wait_idle()
    assert engine.get_task(TaskId("root")).verified is False    # review staled by the edit
    with pytest.raises(ValueError, match="no current Level-2 verdict"):
        tools.dispute_finding(engine, "root", "c2", "same reason again")


# ── the frontier NAMES the step (a gate that only refuses is a wall) ──────────────────────────

def _drive(e):
    """Bring the plan to the shape where children are waiting to start: root accepted, kid in OFFERED."""
    _plan(e)
    e.send_signal(SignalData(signal=Signal.ACCEPT, task_id=TaskId("root"), source=AgentId("agent")))
    e.wait_idle()


def test_frontier_asks_for_the_review_before_the_work(engine):
    _drive(engine)
    step = tools.next_step(engine)
    assert step["action"] == "review" and step["task_id"] == "root"
    assert "review_decomposition" in step["directive"]


def test_frontier_names_the_open_gaps(engine):
    _drive(engine)
    _review(engine, covered=False,
            verdicts=[{"criterion": "c2", "verdict": "insufficient", "why": "k1 does not carry c2"}])
    step = tools.next_step(engine)
    assert step["action"] == "review" and "c2" in step["directive"]
    assert "dispute_finding" in step["directive"]


def test_frontier_moves_on_once_discharged(engine):
    _drive(engine)
    _review(engine, covered=True)
    step = tools.next_step(engine)
    assert step["action"] == "accept" and step["task_id"] == "kid"


def test_an_empty_register_is_an_incomplete_plan_and_the_engine_says_which_hole(engine):
    """An empty ACCEPTED_RISKS on a decomposed node stops the plan at the Syntactic level, and both
    gates read that level the same way: execution is refused and the Level-2 checker refuses too.

    This used to be the argument for calling CHECK-4 advisory — the pair looked like a deadlock, with
    a fabricated register as the only escape. It is not one. §13.1 says a decomposition without the
    register is incomplete BY DEFINITION, so the escape is to write the register the plan was always
    missing, and the engine names exactly that hole rather than a generic refusal. What would make it
    a deadlock is a hole the operator cannot see; what makes it a step is `list_holes`."""
    from gfso.critic.runner import critique_node
    _plan(engine, risks=False)                      # decomposed, register empty
    assert any(c.check_name.startswith("CHECK-4") and not c.passed
               for c in engine.get_checks(TaskId("root")))
    assert _accept(engine) == State.OFFERED         # execution refused: the level is not clean
    crit = critique_node(engine, TaskId("root"))
    assert not crit.gate_passed and any("CHECK-4" in f for f in crit.l0l1_failures)
    assert any("CHECK-4" in h["check"] for h in tools.list_holes(engine, "root"))   # named, not opaque

    tools.edit_accepted_risks(engine, "root", [{"item": "an unmodelled environment fault",
                                                "predictability": "EXTRAORDINARY"}], agent="agent")
    engine.wait_idle()
    assert not [c for c in engine.get_checks(TaskId("root"))
                if c.check_name.startswith("CHECK-4") and not c.passed]   # the step, taken


def test_l0_is_checked_before_l2(engine):
    """Staging: the structural hole is named first — L2 presupposes a complete plan."""
    engine.assign_task(TaskId("root"), _spec("goal", "c1", "c2"), AgentId("agent"))
    engine.wait_idle()
    engine.decompose_task(TaskId("root"), [(TaskId("kid"), _spec("part", "k1"), AgentId("agent"))],
                          criterion_mappings=[CriterionMapping("c1", TaskId("kid"))])  # c2 uncovered
    engine.wait_idle()
    assert _accept(engine) == State.OFFERED
    holes = [h["check"] for h in tools.list_holes(engine, "root")]
    assert any("CHECK-1" in h for h in holes)
