"""The pre-execution causal gate — an ENGINEERING corner (`formal/README.md` #10), not a canon row.

The canon gates execution on the SYNTACTIC level (§11.5) and files the Pragmatic level as runtime
detection; what is mechanised here is its verify-vs-explore decision (§9.9) taken once: the causal
check must have RUN over this version of the plan and its findings must be dispositioned.

L0 gates topology: a parent criterion needs a covering child. It cannot see whether that child's
criteria, taken as facts about the world, actually CARRY the parent criterion — an L0-clean plan can
be causally hollow, and the hole then surfaces only after the code exists, as a refused delivery
(q_D↓, rework). The checker sees that class before contact, so the engine refuses the FIRST execution
step (a child's ACCEPT) while its parent's decomposition has no current, discharged Level-2 verdict.

What is gated is that the check RAN and its findings were DISPOSITIONED — never that the checker is
right (L2 is an approximation over the faithfulness axis; contact keeps the last word, §9.9).
Hence two discharges: fix the plan (any edit stales the review — with its disputes) or record why the
finding is wrong (`dispute_finding`). `GFSO_L2_GATE=0` is the explicit EXPLORE opt-out.

These tests drive REAL review records through the storage the checker writes to (no model runs).
"""
import json
import os

import pytest

from gfso import tools
from gfso import tools_llm as TL
from gfso.critic.runner import (_goal_changed, _obligation_words, _same_obligation, critique_node,
                                _still_undecided, _undecided_obligations)
from gfso.core.types import Spec, Criteria, Register, TaskId
from gfso.critic.types import NodeCritique
from tests.support import REGISTER, REGISTER_SPLIT, criterion, make_engine, pinned, spec, DENIAL_ENTRY

from gfso.critic import runner as _runner
from gfso.core.graph.model import generation_of_task, stamped_with
from gfso.engine.validation import AdmissionRefused, _l2_undischarged, _l0_holes
import gfso.tools as T
from gfso.critic import runner as R
from gfso.critic.runner import _already_decided, _criterion_stamps, _plan_generation
from gfso.core.graph.review import finding_keys
from gfso.core.types import AgentId, CriterionMapping, Signal, SignalData, State, TaskId


@pytest.fixture(autouse=True)
def _gate_on():
    """This module owns the gate-ON behavior (the suite default is OFF — see conftest)."""
    prior = os.environ.get("GFSO_L2_GATE")
    os.environ["GFSO_L2_GATE"] = "1"
    yield
    os.environ["GFSO_L2_GATE"] = prior if prior is not None else "0"


@pytest.fixture
def engine():
    e = make_engine(llm=None, check_interval=10_000)
    e.start()
    yield e
    e.stop()


_KID = [(TaskId("kid"), spec("part", "k1"), AgentId("agent"))]
_BOTH = [CriterionMapping("c1", TaskId("kid")), CriterionMapping("c2", TaskId("kid"))]


def _root(e):
    e.assign_task(TaskId("root"), spec("goal", "c1", "c2"), AgentId("agent"))
    e.wait_idle()


def _plan(e):
    """root(c1,c2) → child covering both, admitted whole with its register (§11.5). L0-clean; nothing reviewed yet."""
    _root(e)
    e.decompose_task(TaskId("root"), _KID, _BOTH, register=REGISTER_SPLIT)
    e.wait_idle()
    assert _l0_holes(e._graph, e.graph.get_task(TaskId("root"))) == []


def _review(e, node="root", covered=True, verdicts=(), conflicts=()):
    """Write the record `review_decomposition` would write, and mark the node reviewed."""
    rec = {"node_id": node, "gate_passed": True, "semantic_covered": covered,
           "criteria_verdicts": list(verdicts), "conflicts": list(conflicts),
           "model": "test", "ts": "2026-07-19 00:00:00"}
    e._graph._storage.store_critique(TaskId(node), json.dumps(rec))
    t = e.graph.get_task(TaskId(node))
    t.verified = True
    e._graph.save_task(t)


def _accept(e, tid="kid"):
    e.send_signal(SignalData(signal=Signal.ACCEPT, task_id=TaskId(tid), source=AgentId("agent")))
    e.wait_idle()
    return e.graph.get_task(TaskId(tid)).state


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
    (§4.5). So a node the executor takes as a LEAF starts work with no atomicity verdict demanded; the
    root seam still validates the whole result against the issuer's criteria. (Removed: an earlier gate
    made a leaf justify being atomic — that set the subtask count from outside and deadlocked
    auto_decompose's own builder.)"""
    engine.assign_task(TaskId("solo"), spec("goal", "c1", "c2"), AgentId("agent"))
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
    assert set(stored) == {"c1", "c2"} and stored["c1"]["by"] == "agent"  # provenance, §19.3


def test_dispute_needs_a_current_verdict_naming_that_finding(engine):
    # A WRITTEN reason throughout: this test is about the ENGINE's two refusals, and the door now
    # refuses a dispute that only restates the conclusion — which a placeholder "…" is. The
    # placeholder became meaningful, so it is replaced rather than the rule relaxed.
    _why = "k1's contract already entails c1, so the checker's reading of the mapping is the gap"
    _plan(engine)
    with pytest.raises(ValueError, match="no current Level-2 verdict"):
        tools.dispute_finding(engine, "root", "c1", _why)
    _review(engine, covered=False,
            verdicts=[{"criterion": "c2", "verdict": "insufficient", "why": "gap"}])
    with pytest.raises(ValueError, match="not an open Level-2 finding"):
        tools.dispute_finding(engine, "root", "c1", _why)   # not flagged — nothing to dispute


def test_editing_the_plan_stales_the_review_and_its_disputes(engine):
    """A dispute never launders a finding across plan versions."""
    _plan(engine)
    _review(engine, covered=False,
            verdicts=[{"criterion": "c2", "verdict": "insufficient", "why": "gap"}])
    tools.dispute_finding(engine, "root", "c2", "holds via the child's documented output")
    assert _accept(engine) == State.EXECUTING

    tools.edit_criteria(engine, "kid", [criterion("k1", "changed"),
                                        criterion("k2", "added")], agent="agent")
    engine.wait_idle()
    assert engine.graph.get_task(TaskId("root")).verified is False    # review staled by the edit
    with pytest.raises(ValueError, match="no current Level-2 verdict"):
        tools.dispute_finding(engine, "root", "c2", "same reason again")


def test_a_child_leaving_the_plan_stales_the_review_as_its_revision_does(engine):
    """A cancelled child's settlement takes it out of the split the review read (§12.6) — the plan changed, as on a
    revision of the child's contract, so the verdict is no longer current; while it is only CANCELLING it is still
    active and the verdict stands (critic r12)."""
    _root(engine)
    kids = [(TaskId("a"), spec("part a", "ka"), AgentId("agent")), (TaskId("b"), spec("part b", "kb"), AgentId("agent"))]
    maps = [CriterionMapping("c1", TaskId("a")), CriterionMapping("c2", TaskId("a")),
            CriterionMapping("c1", TaskId("b"))]
    engine.decompose_task(TaskId("root"), kids, maps, register=REGISTER_SPLIT)
    engine.wait_idle()
    _review(engine)
    engine.send_signal(SignalData(signal=Signal.CANCEL, task_id=TaskId("b"), source=AgentId("agent"), reason="not needed"))
    engine.wait_idle()
    assert engine.graph.get_task(TaskId("root")).verified is True            # still active while CANCELLING
    engine.send_signal(SignalData(signal=Signal.CONFIRM_CANCEL, task_id=TaskId("b"), source=AgentId("agent")))
    engine.wait_idle()
    assert engine.graph.get_task(TaskId("b")).state == State.ABANDONED
    assert engine.graph.get_task(TaskId("root")).verified is False           # the plan it read is gone
    assert _accept(engine, "a") == State.OFFERED                             # the decomposer's own child waits


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
    a fabricated register as the only escape. It is not one. §9.2 says a decomposition without the
    register is incomplete BY DEFINITION, so the escape is to write the register the plan was always
    missing, and the engine names exactly that hole rather than a generic refusal. What would make it
    a deadlock is a hole the operator cannot see; what makes it a step is `list_holes`.

    Canon v4.1 (§11.5, §9.2, §12.10): a split carrying no register of its own — the packet's pre-fill is not one — is
    refused at its admission, naming CHECK-4, and no child is issued; a register emptied after admission is a flag
    both levels read and name.
    Canon v4.1 §11.5 ("its register — changes only by a re-admission"): emptying it is refused naming CHECK-4 and
    the admitted register stands; the empty one both levels must still name is a row written behind that gate, as an
    older build left it (no door reaches it now), and the decomposer's complete register is what lifts it."""
    _root(engine)                                   # the packet carries a pre-filled register: task data
    with pytest.raises(AdmissionRefused, match="CHECK-4"):
        engine.decompose_task(TaskId("root"), _KID, _BOTH)      # decomposed, no register with the split
    assert engine.graph.get_task(TaskId("kid")) is None         # execution refused: nothing was issued
    engine.decompose_task(TaskId("root"), _KID, _BOTH, register=REGISTER_SPLIT)
    with pytest.raises(AdmissionRefused, match="CHECK-4"):     # its decomposer empties it: refused, not a flag
        engine.admit_register(TaskId("root"), Register(), AgentId("agent"))
    assert engine.graph.get_task(TaskId("root")).register.items == REGISTER_SPLIT.items
    t = engine._graph.get_task(TaskId("root"))
    t.register = Register()                                     # behind the gate: an older build's row
    engine._graph.save_task(t)
    engine._recompute_checks(TaskId("root"))
    assert any(c.check_name.startswith("CHECK-4") and not c.passed
               for c in engine.get_checks(TaskId("root")))
    crit = critique_node(engine, TaskId("root"))
    assert not crit.gate_passed and any("CHECK-4" in f for f in crit.l0l1_failures)
    assert any("CHECK-4" in h["check"] for h in tools.list_holes(engine, "root")["holes"])   # named, not opaque

    tools.edit_accepted_risks(engine, "root", REGISTER, agent="agent")
    engine.wait_idle()
    assert not [c for c in engine.get_checks(TaskId("root"))
                if c.check_name.startswith("CHECK-4") and not c.passed]   # the step, taken


def test_l0_is_checked_before_l2(engine):
    """Staging: the structural hole is named first — L2 presupposes a complete plan.

    Canon v4.1: the holed split is refused at its admission, naming CHECK-1, and no child is issued (§11.5); a hole a
    revision makes after it is flagged (§12.10), and the checker stops at it before Level 2."""
    _root(engine)
    with pytest.raises(AdmissionRefused, match="CHECK-1"):     # c2 uncovered
        engine.decompose_task(TaskId("root"), _KID, _BOTH[:1], register=REGISTER_SPLIT)
    assert engine.graph.get_task(TaskId("kid")) is None
    engine.decompose_task(TaskId("root"), _KID, _BOTH, register=REGISTER_SPLIT)
    tools.edit_criteria(engine, "root", [criterion("c1"), criterion("c2"), criterion("c3")], agent="agent")
    holes = [h["check"] for h in tools.list_holes(engine, "root")["holes"]]
    assert any("CHECK-1" in h for h in holes)
    crit = critique_node(engine, TaskId("root"))
    assert not crit.gate_passed and any("CHECK-1" in f for f in crit.l0l1_failures)


def test_a_goal_whose_own_criteria_decide_nothing_does_not_reach_execution(engine):
    """The question no gate asked: does this node's OWN criteria set decide its OWN goal?

    Level 2 checks that the CHILDREN's criteria carry the parent's. Nothing checked that the parent's
    carry the GOAL — which is FM-1.f, "the goal needed a criterion nobody wrote", the one failure
    mode of the seven with no gate on it. Measured 2026-08-21 on two closed measurement runs: a regex
    engine reached root DONE/PASS on two root criteria — "does not import `re`" and "parses
    consistently" — neither of which requires it to MATCH anything, with 21 hidden tests failing; and
    a whole `sed` interpreter had run under a single root criterion. Seven runs, root contracts of
    one to four criteria, every verdict over them honest and complete.

    A named gap is discharged the same two ways as any other finding: change the plan, or record in
    writing why the finding is wrong. What is gated is that the check HAPPENED and its findings were
    dispositioned — never that the checker is right (§9.9)."""
    e = engine
    _plan(e)                                  # a structurally clean parent with mapped children
    node = e.graph.get_task(TaskId("root"))

    rec = {"node_id": "root", "gate_passed": True, "semantic_covered": False,
           "criteria_verdicts": [{"criterion": "c1", "verdict": "sufficient", "why": "carried"},
                                 {"criterion": "c2", "verdict": "sufficient", "why": "carried"}],
           "conflicts": [],
           "undecided_obligations": [{"obligation": "the engine must actually match patterns",
                                 "admits": "a module that imports nothing and parses consistently, "
                                           "and matches nothing at all"}]}
    e._graph._storage.store_critique(TaskId("root"), json.dumps(rec))
    node.verified = True
    e._graph.save_task(node)

    open_now = _l2_undischarged(e._graph, e.graph.get_task(TaskId("root")))
    assert open_now == ["undecided: the engine must actually match patterns"]

    out = e.dispute_review_finding(TaskId("root"), "undecided: the engine must actually match patterns",
                                   "the matching obligation is carried by the child's criteria",
                                   AgentId("agent"))
    assert out["open_findings"] == []
    assert _l2_undischarged(e._graph, e.graph.get_task(TaskId("root"))) == []


def test_a_current_pass_means_the_same_thing_everywhere(engine):
    """"Does a fresh independent verdict stand here" was asked in four places with three arities.

    One compared reopens only, one iteration and reopens, one added revisions, one asked nothing
    about the generation at all — and they gate a self-PASS at the seam, void a verdict on revision,
    and feed q_V. A disagreement between them is a disagreement about whether work is accepted.

    The generation is (iteration, reopens, revisions): a rework moves the first, a REOPEN the second
    — §12.14's anti-fake rule, so a pre-reopen pass cannot re-open the gate from the past — and a
    revision the third, because a validator still running on a voided delivery lands its verdict
    afterwards carrying the same first two."""
    e = engine
    e.assign_task(TaskId("n"), spec("goal", "c"), AgentId("agent"))
    e.wait_idle()
    t = e.graph.get_task(TaskId("n"))

    gen = generation_of_task(t)
    assert stamped_with(None, gen) is False                                 # nothing recorded
    fresh = {"verdict": "PASS", "iteration": 0, "reopens": 0, "revisions": 0}
    assert stamped_with(fresh, gen) is True
    for stale in ({**fresh, "iteration": 1}, {**fresh, "reopens": 1}, {**fresh, "revisions": 1}):
        assert stamped_with(stale, gen) is False, stale


def test_a_checker_verdict_that_flipped_says_so(engine, monkeypatch):
    """A criterion went `sufficient` in one round and `insufficient` in the next with nothing about
    it or its children touched between them.

    The checker is an approximation (§9.9) and may legitimately change its mind — but if it does so
    silently, a plan can be admitted on the round that happened to be kind, and nobody can see that
    is what happened. This does not decide anything about the churn; it stops it being invisible."""
    e = engine
    _plan(e)
    monkeypatch.setattr(_runner, "llm_factory", lambda m: object(), raising=False)

    def _run(verdict):
        monkeypatch.setattr(_runner, "critique_node",
                            lambda *a, **k: NodeCritique("root", gate_passed=True, semantic_covered=True,
                                                         goal_read=True, criteria_verdicts=(
                                {"criterion": "c1", "verdict": verdict, "why": "…"},)))
        _runner.review_decomposition(e, TaskId("root"), llm=object())
        return json.loads(e._graph._storage.get_critique(TaskId("root")))

    first = _run("sufficient")
    assert "changed_from" not in first["criteria_verdicts"][0]      # nothing to compare against yet

    second = _run("insufficient")
    assert second["criteria_verdicts"][0]["changed_from"] == "sufficient"

    third = _run("insufficient")
    assert "changed_from" not in third["criteria_verdicts"][0]      # …only a CHANGE is marked


def test_the_sufficiency_check_reads_the_goal_several_times_and_unions_what_it_finds():
    """It was discovering its objections one round at a time.

    Measured on the MCP door 2026-08-21: eight review rounds, ~20 minutes, ~$1.50, findings
    7→5→2→2→1→1→1→0 — each round naming a FRESH obligation out of a new reading of the same
    unchanged goal text. Every finding was true; the cost was the shape of the loop. Independent
    readings unioned pay for that discovery in parallel instead of in rounds — the harness, not a
    rewrite of the question (same prompt, same schema), and a repeated obligation folds by its own
    words rather than arriving twice."""
    class _Reader:
        """Three readings of one goal: two overlap, one is new — exactly the observed behaviour."""
        rounds = [
            json.dumps({"gaps": [{"obligation": "reports missing keys", "why": "w", "admits": "a"}]}),
            json.dumps({"gaps": [{"obligation": "Reports  missing keys", "why": "w", "admits": "a"},
                                 {"obligation": "exits non-zero", "why": "w", "admits": "a"}]}),
            json.dumps({"gaps": [{"obligation": "documents the schema format", "why": "w",
                                  "admits": "a"}]}),
        ]

        def __init__(self):
            self.n = 0

        def complete(self, prompt, context=None, **kw):
            self.n += 1
            return self.rounds[(self.n - 1) % len(self.rounds)]

    task = type("T", (), {"id": TaskId("root"),
                          "spec": Spec("a goal", (Criteria("c1", "one", check=pinned("c1")),), (), scope=())})()
    gaps = _undecided_obligations(None, task, _Reader())
    named = [g["obligation"] for g in gaps]
    assert named == ["reports missing keys", "exits non-zero", "documents the schema format"]


def test_one_obligation_in_three_phrasings_is_one_finding():
    """The union's own cost, measured before it could be paid by a user.

    Three readings of one goal returned "CLI invoked as `python -m linestat FILE`", "package
    structure runnable as `python -m linestat FILE`" and "package is invocable as `python -m linestat
    FILE`" — one obligation, three wordings (2026-08-21). Exact-text dedup let all three through, so
    the pass that was supposed to save rounds handed back the same gap three times."""
    class _Reader:
        said = [
            json.dumps({"gaps": [{"obligation": "CLI invoked as `python -m linestat FILE`",
                                  "why": "w", "admits": "a"},
                                 {"obligation": "a README exists", "why": "w", "admits": "a"}]}),
            json.dumps({"gaps": [{"obligation": "package is invocable as `python -m linestat FILE`",
                                  "why": "w", "admits": "a"},
                                 {"obligation": "a README is provided", "why": "w", "admits": "a"},
                                 {"obligation": "--json produces machine-readable output",
                                  "why": "w", "admits": "a"}]}),
        ]

        def __init__(self):
            self.n = 0

        def complete(self, prompt, context=None, **kw):
            self.n += 1
            return self.said[(self.n - 1) % len(self.said)]

    task = type("T", (), {"id": TaskId("root"),
                          "spec": Spec("a goal", (Criteria("c1", "one", check=pinned("c1")),), (), scope=())})()
    named = [g["obligation"] for g in _undecided_obligations(None, task, _Reader())]
    assert named == ["CLI invoked as `python -m linestat FILE`", "a README exists",
                     "--json produces machine-readable output"]


def test_a_shorter_naming_of_the_same_obligation_folds_into_the_longer_one():
    """The case a similarity ratio cannot see, measured on a live pass 2026-08-21.

    "a README exists" against "README documenting the package" shares every word of the shorter one
    and scores 0.33 — because the longer phrasing simply says more ABOUT the same obligation. Without
    containment the union handed the caller eight findings for five requirements; with it, five."""
    assert _same_obligation(_obligation_words("a README exists"),
                            _obligation_words("README documenting the package"))
    assert _same_obligation(_obligation_words("invocation as `python -m linestat FILE`"),
                            _obligation_words("module invocable as `python -m linestat FILE`"))
    # …and two genuinely different obligations stay two
    assert not _same_obligation(_obligation_words("a README exists"),
                                _obligation_words("--json produces machine-readable output"))


def test_the_review_answers_with_one_number_and_what_changed(engine, monkeypatch):
    """The findings live in three fields and a reader's own summary missed two of them.

    Measured on the agent door 2026-08-21: a round read `undecided: 0` while the gate was still shut
    on per-criterion verdicts and a conflict, and there was no single "how many are open". The gate's
    own list is that number. And because the checker is an approximation that may differ between runs
    over the SAME plan — measured on byte-identical criteria, one finding gone and another new — the
    reply says which findings are new since the last review and which closed, so a reader can tell a
    plan that is converging from one that is being re-read."""
    monkeypatch.setenv("GFSO_L2_GATE", "1")
    e = engine
    tools.create_task(e, "root", {"name": "root", "description": "a goal",
                                  "criteria": [criterion("c1", "the thing")]}, "agent")
    tools.decompose(e, "root", [{"task_id": "kid", "spec": {"description": "child", "criteria": [criterion("k", "K")]},
                                 "assignee": "agent", "covers": ["c1"]}],
                    accepted_risks=[{"item": "fixture", "predictability": "extraordinary", "justification": "accepted", "invalidation_condition": "never", "p": 0.01, "impact": "the run stops and is resumed"}, DENIAL_ENTRY])
    e._graph._storage.store_critique(TaskId("root"), json.dumps({
        "node_id": "root", "gate_passed": True, "semantic_covered": False,
        "criteria_verdicts": [{"criterion": "c1", "verdict": "insufficient", "why": "not carried"}],
        "conflicts": [], "undecided_obligations": [],
        "iteration": 0, "reopens": 0, "revisions": 0}))
    root = e.graph.get_task(TaskId("root")); root.verified = True; e._graph.save_task(root)
    assert e.open_l2_findings(TaskId("root")) == ["c1"]        # the one list the gate reads


def test_a_goal_that_has_not_moved_is_not_mined_again(engine):
    """Twenty-six rounds, fifty-one criteria, $19.44 on the gate, and not one executor call.

    Measured to its conclusion on the E3 arm 2026-08-21: the sufficiency check asks a question ABOUT
    THE GOAL — what does this text require that no criterion decides — and re-asking it open-endedly
    after every criteria edit made it discover a fresh corner each round, growing the contract until
    the run died in the gate without writing any code. The answer belongs to the text: when the goal
    has not moved, later rounds re-check the obligations already named instead of reading it again,
    and nothing new can be invented."""
    e = engine
    tools.create_task(e, "root", {"name": "root", "description": "build the thing",
                                  "criteria": [criterion("c1", "the thing")]}, "agent")
    task = e.graph.get_task(TaskId("root"))
    assert _goal_changed(None, task)                              # never reviewed → read the goal
    prior = {"goal_text": "build the thing", "goal_read": True,
             "undecided_obligations": [{"obligation": "it is installable"},
                                       {"obligation": "it has a README"}]}
    assert not _goal_changed(prior, task)                         # same text → check the list
    # a record from before `goal_read` cannot say whether its round read the goal: read once more
    assert _goal_changed({k: v for k, v in prior.items() if k != "goal_read"}, task)
    assert _goal_changed({**prior, "goal_text": "build something else"}, task)

    class _Checker:
        def complete(self, prompt, context=None, **kw):
            assert "OBLIGATIONS NAMED EARLIER" in prompt          # …the fixed list, not the goal
            return json.dumps({"decided": ["1"]})

    left = _still_undecided(e, task, _Checker(), tuple(prior["undecided_obligations"]))
    assert [g["obligation"] for g in left] == ["it has a README"]


def test_a_count_that_was_not_measured_is_not_zero(engine, monkeypatch):
    """`open_count: 0` was printed beside six hard Level-0 failures.

    When the Syntactic level fails, the Level-2 checker is gated out and names nothing — and the
    count read zero, which a reader glancing at it takes for a clean plan (measured on the human door
    2026-08-22). A number that cannot tell "none" from "unmeasured" must not be a number, and the
    delta against the last check is not a comparison either when nothing was compared.
    Canon v4.1: the hole is a revision's, flagged after a clean admission (§11.5, §12.10)."""
    monkeypatch.setenv("GFSO_L2_GATE", "1")
    e = engine
    _plan(e)
    tools.edit_criteria(e, "root", [criterion("c1"), criterion("c2"), criterion("c3")], agent="agent")  # c3: CHECK-1
    out = TL.review_decomposition(e, "root")
    assert out["gate_passed"] is False
    assert out["open_count"] is None and "not measured" in out["open_count_note"]
    assert out["execution_admitted"] is False


def test_the_checker_reads_the_plan_several_times_on_its_first_pass(engine, monkeypatch):
    """With the contract steady at twelve criteria, the checker still found one NEW thing per round.

    Measured on the E3 arm 2026-08-22: three rounds, one new finding each, and the run ended
    `l2_not_discharged` without a line of code. One reading of a plan is one sample of an assessment
    that varies; a doubt raised by ANY reading is a doubt to answer, so the first pass takes several
    and unions them. Later rounds read once — by then the plan has changed, and what they check is
    the change."""
    monkeypatch.setattr("gfso.critic.runner.CHECKER_READINGS", 3)
    e = engine
    tools.create_task(e, "root", {"name": "root", "description": "a goal",
                                  "criteria": [criterion("c1", "one"),
                                               criterion("c2", "two")]}, "agent")
    tools.decompose(e, "root", [{"task_id": "kid", "spec": {"description": "child", "criteria": [criterion("k", "K")]},
                                 "assignee": "agent", "covers": ["c1", "c2"]}],
                    accepted_risks=[{"item": "fixture", "predictability": "extraordinary", "justification": "a", "invalidation_condition": "n", "p": 0.01, "impact": "the run stops and is resumed"}, DENIAL_ENTRY])

    rounds = [
        {"criteria": [{"criterion": "c1", "verdict": "sufficient", "why": "carried"},
                      {"criterion": "c2", "verdict": "sufficient", "why": "carried"}], "conflicts": []},
        {"criteria": [{"criterion": "c1", "verdict": "insufficient", "why": "the child does not carry it"},
                      {"criterion": "c2", "verdict": "sufficient", "why": "carried"}], "conflicts": []},
        {"criteria": [{"criterion": "c1", "verdict": "sufficient", "why": "carried"},
                      {"criterion": "c2", "verdict": "uncertain", "why": "cannot tell from the packet"}],
         "conflicts": []},
    ]

    class _Varying:
        def __init__(self):
            self.n = 0

        def complete(self, prompt, context=None, **kw):
            if "OBLIGATIONS" in prompt or "obligations of the GOAL" in prompt:
                return json.dumps({"gaps": []})
            self.n += 1
            return json.dumps(rounds[(self.n - 1) % len(rounds)])

    out = critique_node(e, TaskId("root"), llm=_Varying())
    named = {v["criterion"]: v["verdict"] for v in out.criteria_verdicts}
    assert named == {"c1": "insufficient", "c2": "uncertain"}    # …every reading's doubt, in one pass
    assert out.semantic_covered is False


def test_a_finding_is_named_the_same_way_by_every_surface():
    """The gate, the dispute verb and the delta baseline each built the finding key themselves.

    Three spellings of one name is three chances for a dispute to be refused as "not an open
    finding" against a finding the gate is holding the node shut on (register 2026-08-22, finding
    4). One author now names them: `core.graph.review.finding_keys`."""
    rec = {"semantic_covered": False,
           "criteria_verdicts": [{"criterion": "c1", "verdict": "insufficient", "why": "…"},
                                 {"criterion": "c2", "verdict": "sufficient", "why": "…"}],
           "conflicts": [{"between": ["kid-a", "kid-b"],
                          "why": "kid-a must leave the file untouched while kid-b rewrites it"}],
           "undecided_obligations": [{"obligation": "the package imports", "why": "…"}],
           "disputes": {"c1": {"why": "answered in writing"}}}

    # …AND A CONFLICT CARRIES ITS REASON IN ITS NAME. Keyed on the participants alone, two
    # separately reasoned conflicts between the same pair were one finding, and one dispute closed
    # both (adversary, wave 25). The reason is what tells them apart, so it is in the key — handed
    # back verbatim under `dispute_keys`, never typed from memory.
    assert finding_keys(rec) == [
        "conflict: kid-a, kid-b — kid-a must leave the file untouched while kid-b rewrites it",
        "undecided: the package imports"]
    # …and the same names WITHOUT the dispute filter, which is what a delta baseline reads
    assert finding_keys(rec, exclude_disputed=False)[0] == "c1"


def test_a_check_already_running_is_not_offered_as_a_step(engine, monkeypatch):
    """The frontier kept saying "call review_decomposition" while one was mid-flight.

    A duplicate paid round over a plan that had not changed — and the other in-flight surface
    (`validate_result`) had suppressed exactly this for a while (measured on the human door
    2026-08-22, where the two surfaces disagreed about the same node)."""
    monkeypatch.setenv("GFSO_L2_GATE", "1")
    _plan(engine)
    key = engine.claims.begin_review(TaskId("root"))
    assert key is not None and engine.claims.begin_review(TaskId("root")) is None   # one per plan version

    out = T.next_steps(engine)
    assert not [s for s in out.get("steps", [])
                if s["task_id"] == "root" and "PLAN" in s["directive"]]
    assert any("plan being checked" in w["why"] for w in out.get("in_flight", []))
    engine.claims.end_review(key)


def test_the_checker_does_not_relitigate_a_plan_it_already_checked(engine, monkeypatch):
    """The gate was non-monotone, and that is what made discharging it feel like whack-a-mole.

    Measured on the agent door 2026-08-22: a criterion was ruled `sufficient` twice with a stated
    reason, and after an edit touching a DIFFERENT node's criteria it came back `insufficient` with
    the opposite claim — three rounds, $0.86, each closing findings while opening others that had
    been true from the first. A criterion decided against a plan that has not changed since is
    carried forward; anything else is checked afresh, and a changed plan is checked whole."""
    _plan(engine)
    task = engine.graph.get_task(TaskId("root"))
    prior = {"plan_generation": list(_plan_generation(task)),
             "criteria_verdicts": [{"criterion": "c1", "verdict": "sufficient", "why": "carried"},
                                   {"criterion": "c2", "verdict": "insufficient", "why": "a gap"}]}

    decided = _already_decided(prior, task)
    assert list(decided) == ["c1"], "only what was SETTLED is carried; a gap is asked again"

    # …and a plan that changed is checked whole: a new criterion moves the stamp
    T.edit_criteria(engine, "root", [criterion("c1", "one"),
                                     criterion("c2", "two"),
                                     criterion("c3", "three")], agent="agent")
    assert _already_decided(prior, engine.graph.get_task(TaskId("root"))) == {}


def test_a_criterion_untouched_by_an_edit_elsewhere_is_not_re_litigated(engine):
    """Rounds 3 and 4 reopened what rounds 2 and 3 had certified — five rounds and ~$1.30 on one plan.

    Keyed on a WHOLE-plan stamp, any edit anywhere threw away every earlier decision, so closing one
    finding re-opened the question about criteria nobody had touched. Whether the children mapped to
    `c` entail `c` depends on `c`'s text and on those children's criteria and on nothing else, so
    that is what the stamp is made of. (FM-2 conflicts stay out of the carry-forward: mutual
    satisfiability is a property of ALL the children together, and a criterion added elsewhere really
    can create one.)"""
    _plan(engine)
    task = engine.graph.get_task(TaskId("root"))
    prior = {"plan_generation": list(_plan_generation(task)),
             "criteria_stamps": _criterion_stamps(engine, task),
             "criteria_verdicts": [{"criterion": "c1", "verdict": "sufficient", "why": "carried"},
                                   {"criterion": "c2", "verdict": "sufficient", "why": "carried"}]}

    # an edit that adds a THIRD criterion — c1 and c2 keep their text and their coverage
    T.edit_criteria(engine, "root", [criterion("c1", "c1 description"),
                                     criterion("c2", "c2 description"),
                                     criterion("c3", "the new obligation")],
                    agent="agent")
    after = engine.graph.get_task(TaskId("root"))
    assert _already_decided(prior, after) == {}, "the OLD whole-plan rule threw both away — the control"
    assert sorted(_already_decided(prior, after, engine)) == ["c1", "c2"]

    # …but a criterion whose OWN text changed is a different question, and is asked again
    T.edit_criteria(engine, "root", [criterion("c1", "something else entirely"),
                                     criterion("c2", "c2 description")],
                    agent="agent")
    assert sorted(_already_decided(prior, engine.graph.get_task(TaskId("root")), engine)) == ["c2"]


def test_one_reason_can_answer_several_findings_in_one_call(engine):
    """A checker that names one obligation in three wordings cost three calls to answer.

    The paraphrase-fold catches most of them and keeps the other wordings under `also_phrased`, but
    the threshold is a heuristic and testers of both doors paid for the ones it missed — one call per
    duplicate, each carrying the same sentence they had already written (2026-09-02).
    """
    _plan(engine)
    _review(engine, covered=False,
            verdicts=[{"criterion": "c1", "verdict": "insufficient", "why": "gap A"},
                      {"criterion": "c2", "verdict": "uncertain", "why": "gap B"}])
    out = tools.dispute_finding(engine, "root", ["c1", "c2"],
                                "both name the same obligation, which k1's contract already carries")
    assert out["open_findings"] == [] and out["disputed"] == ["c1", "c2"]
    assert _accept(engine) == State.EXECUTING

    stored = engine.get_critique(TaskId("root"))["disputes"]
    assert set(stored) == {"c1", "c2"}, "each is recorded separately, with the same reason"


def test_a_key_that_names_no_finding_stops_the_batch_and_says_where(engine):
    """…and does not bury the caller's mistake under the ones that did land."""
    _plan(engine)
    _review(engine, covered=False,
            verdicts=[{"criterion": "c1", "verdict": "insufficient", "why": "gap A"},
                      {"criterion": "c2", "verdict": "uncertain", "why": "gap B"}])
    # A REAL reason, not a placeholder: the dispute floor now asks for three content words, so
    # "one reason" is refused before the batch ever reaches the key check this test is about — and a
    # test that dies on the guard in front of its subject tests the guard (2026-09-05).
    out = tools.dispute_finding(engine, "root", ["c1", "not-a-finding", "c2"],
                                "kid's own criteria already carry both c1 and c2")
    assert out.get("error") or out.get("refused")
    assert out["disputed_before_this"] == ["c1"]


def test_a_carried_finding_does_not_carry_its_old_argument(engine, monkeypatch):
    """The DECISION is current; the ARGUMENT was written against an earlier contract.

    A tester was told "No criterion mentions tests at all" while a criterion named
    `pytest_suite_runs_green` was in the set, because the finding's own text enumerated the pre-edit
    criteria (CLI door, 2026-09-02). The user acts on the text, so the text may not assert a state of
    the graph it has not re-read.
    """
    _plan(engine)
    task = engine.graph.get_task(TaskId("root"))
    prior = ({"obligation": "it must actually sort",
              "admits": "no criterion mentions sorting at all"},)
    monkeypatch.setattr(R, "parse_structured", lambda *a, **k: {"decided": []})

    class _LLM:
        def complete(self, prompt, context=""):
            return "{}"

    out = R._still_undecided(engine, task, _LLM(), prior)
    assert out[0]["carried"] is True
    assert "FIRST reading" in out[0]["admits"], "the stale argument is labelled as one"
    assert "no criterion mentions sorting" in out[0]["admits"], "…and is still shown, not dropped"

def test_a_silence_is_not_a_finding_that_your_fix_failed(engine, monkeypatch):
    """⊥ ≠ "still open". When the re-check cannot run, the list stands — and says that it does.

    Two doors reported these obligations as "frozen at the first reading: fixing the plan does not
    close them" (wave 26, 2026-09-06). Fixing them IS what closes them — each round re-checks the
    named list against the criteria as they stand — but a round whose checker did not answer kept
    every finding with no mark at all, so the two cases read identically to the person who had just
    done the work.
    """
    _plan(engine)
    task = engine.graph.get_task(TaskId("root"))
    prior = ({"obligation": "it must actually sort", "admits": "no criterion mentions sorting"},)

    class _Silent:
        def complete(self, prompt, context=""):
            raise RuntimeError("no checker on this machine")

    out = R._still_undecided(engine, task, _Silent(), prior)

    assert len(out) == 1, "a check that could not run closes nothing"
    assert out[0]["rechecked"] is False
    assert "NOT RE-CHECKED" in out[0]["admits"] and "not a finding that your fix failed" in out[0]["admits"]


def test_a_rechecked_carry_over_says_the_fix_is_what_closes_it(engine, monkeypatch):
    """The other half: the round DID check, the obligation is still open, and the exit is named."""
    _plan(engine)
    task = engine.graph.get_task(TaskId("root"))
    prior = ({"obligation": "it must actually sort", "admits": "no criterion mentions sorting"},)
    monkeypatch.setattr(R, "parse_structured", lambda *a, **k: {"decided": []})

    class _LLM:
        def complete(self, prompt, context=""):
            return "{}"

    out = R._still_undecided(engine, task, _LLM(), prior)

    assert out[0]["rechecked"] is True
    assert "RE-CHECKED" in out[0]["admits"] and "fixing the criteria IS what closes it" in out[0]["admits"]



def test_adding_a_criterion_to_a_covering_child_does_not_reopen_what_was_certified():
    """Adding is not changing: a conjunction only gets stronger when a conjunct is added.

    An integrator watched one criterion go sufficient → insufficient → sufficient over four rounds
    while the only edit was ADDING a criterion to the child that covers it, at ~4 minutes and ~$0.25
    each (HTTP door, wave 27, 2026-09-06: "I would not promise a CI budget on it"). If the children
    entailed the parent criterion before, they entail it with an extra criterion on one of them
    (§9.6 CHECK-7), so the certified verdict carries.
    """
    then = ["parent text", ["kid"], [["kid", [["c1", "does X"]]]]]
    grown = ["parent text", ["kid"], [["kid", [["c1", "does X"], ["c2", "also does Y"]]]]]

    assert R._still_entailed(then, then), "identity, the case that always held"
    assert R._still_entailed(then, grown)


def test_a_weakened_plan_is_re_derived():
    """The negative controls — each of these can make an earlier `sufficient` wrong."""
    then = ["parent text", ["kid"], [["kid", [["c1", "does X"], ["c2", "does Y"]]]]]

    reworded_child = ["parent text", ["kid"], [["kid", [["c1", "merely mentions X"], ["c2", "does Y"]]]]]
    dropped_child_criterion = ["parent text", ["kid"], [["kid", [["c1", "does X"]]]]]
    reworded_parent = ["parent text, weakened", ["kid"], [["kid", [["c1", "does X"], ["c2", "does Y"]]]]]
    coverer_removed = ["parent text", [], []]

    assert not R._still_entailed(then, reworded_child)
    assert not R._still_entailed(then, dropped_child_criterion)
    assert not R._still_entailed(then, reworded_parent)
    assert not R._still_entailed(then, coverer_removed)
    assert not R._still_entailed(then, None), "a criterion that no longer exists carries nothing"


def test_a_checker_that_keys_its_verdicts_by_the_whole_criterion_line_still_gives_a_verdict(engine):
    """The projection lists criteria as `name: description`; haiku copied the whole line as the key of every entry, so
    every criterion read as unchecked and a complete verdict was stored as "no verdict" — and such rounds counted toward
    closing the goal by its issuer (AUTO haiku coreutils, 2026-10-11: two of the three counts that closed the root)."""
    e = engine
    _plan(e)
    lines = {c.name: f"{c.name}: {c.description}" for c in e.graph.get_task(TaskId("root")).spec.criteria}

    class _Checker:
        def complete(self, prompt, context=None, **kw):
            if "DECOMPOSITION LEVEL UNDER CHECK" in prompt:
                return json.dumps({"criteria": [{"criterion": line, "verdict": "sufficient", "why": "w"}
                                                for line in lines.values()], "conflicts": []})
            return json.dumps({"gaps": []})

    got = critique_node(e, TaskId("root"), _Checker())
    assert got.semantic_covered is True
    assert {v["criterion"] for v in got.criteria_verdicts} == set(lines)


def test_a_split_one_session_carries_is_checked_by_contact_not_held_for_review(engine):
    """Within one executor session's scope (§3.7) the split is that executor's internal work, validated once at its top
    (§10.3): its parts are not held for an a-priori review (EXPLORE, §9.9) — measured, eight review rounds and 35 min
    held a goal one bare session finished in 12 (AUTO haiku coreutils, 2026-10-12). A part beyond the session still is."""
    e = engine
    _plan(e)
    assert e.execution_blocked_by(TaskId("kid")) is not None, "unreviewed and not judged within one session: held"
    e.record_session_fit(TaskId("kid"), "large", False)
    e.record_session_fit(TaskId("root"), "small", True)
    assert e.execution_blocked_by(TaskId("kid")) is not None, "a part beyond one session: still held"
    assert _accept(e) == State.OFFERED, "…by the machine too"
    e.record_session_fit(TaskId("kid"), "small", True)
    assert e.execution_blocked_by(TaskId("kid")) is None
    assert _accept(e) == State.EXECUTING, "the machine takes what the surface offers — one predicate, two readers"


def test_a_split_one_session_carries_still_answers_to_the_syntactic_level(engine):
    """Only the Level-2 review is EXPLOREd inside a scope; the Syntactic level is mechanical, cheap and mandated (§9.9)
    and gates execution (§11.5): a fitting split that gained a Level-0 hole after its admission is held (critic)."""
    e = engine
    _plan(e)
    e.record_session_fit(TaskId("root"), "small", True)
    e.record_session_fit(TaskId("kid"), "small", True)
    e.revise(TaskId("root"), spec("goal", "c1", "c2", "c3"), AgentId("agent"))   # c3: no child covers it (CHECK-1)
    e.wait_idle()
    if not _l0_holes(e._graph, e.graph.get_task(TaskId("root"))):
        pytest.skip("the revision left no Level-0 hole on this fixture")
    assert e.execution_blocked_by(TaskId("kid")) is not None
    assert _accept(e) != State.EXECUTING
