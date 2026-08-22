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
from gfso import tools_llm as TL
from gfso.critic.runner import (_goal_changed, _obligation_words, _same_obligation, critique_node,
                                _still_undecided, _undecided_obligations)
from gfso.core.types import Spec, Criteria, TaskId
from gfso.engine import Engine
from gfso.adapters.storage.memory import MemoryStorage
from gfso.adapters.agents.human import HumanAgent
from dataclasses import dataclass

from gfso.critic import runner as _runner
from gfso.core.graph.model import verdict_is_current_pass
from gfso.engine.validation import _l2_undischarged
import gfso.tools as T
from gfso.critic.runner import _already_decided, _plan_generation
from gfso.core.graph.review import finding_keys
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
    dispositioned — never that the checker is right (§13.5)."""
    e = engine
    _plan(e)                                  # a structurally clean parent with mapped children
    node = e.get_task(TaskId("root"))

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

    open_now = _l2_undischarged(e._graph, e.get_task(TaskId("root")))
    assert open_now == ["undecided: the engine must actually match patterns"]

    out = e.dispute_review_finding(TaskId("root"), "undecided: the engine must actually match patterns",
                                   "the matching obligation is carried by the child's criteria",
                                   AgentId("agent"))
    assert out["open_findings"] == []
    assert _l2_undischarged(e._graph, e.get_task(TaskId("root"))) == []


def test_a_current_pass_means_the_same_thing_everywhere(engine):
    """"Does a fresh independent verdict stand here" was asked in four places with three arities.

    One compared reopens only, one iteration and reopens, one added revisions, one asked nothing
    about the generation at all — and they gate a self-PASS at the seam, void a verdict on revision,
    and feed q_V. A disagreement between them is a disagreement about whether work is accepted.

    The generation is (iteration, reopens, revisions): a rework moves the first, a REOPEN the second
    — §14.3's anti-fake rule, so a pre-reopen pass cannot re-open the gate from the past — and a
    revision the third, because a validator still running on a voided delivery lands its verdict
    afterwards carrying the same first two."""
    e = engine
    e.assign_task(TaskId("n"), _spec("goal", "c"), AgentId("agent"))
    e.wait_idle()
    t = e.get_task(TaskId("n"))

    assert verdict_is_current_pass(None, t) is False                       # nothing recorded
    assert verdict_is_current_pass({"verdict": "FAIL"}, t) is False         # a refusal is not a pass
    fresh = {"verdict": "PASS", "iteration": 0, "reopens": 0, "revisions": 0}
    assert verdict_is_current_pass(fresh, t) is True
    for stale in ({**fresh, "iteration": 1}, {**fresh, "reopens": 1}, {**fresh, "revisions": 1}):
        assert verdict_is_current_pass(stale, t) is False, stale


def test_a_checker_verdict_that_flipped_says_so(engine, monkeypatch):
    """A criterion went `sufficient` in one round and `insufficient` in the next with nothing about
    it or its children touched between them.

    The checker is an approximation (§13.5) and may legitimately change its mind — but if it does so
    silently, a plan can be admitted on the round that happened to be kind, and nobody can see that
    is what happened. This does not decide anything about the churn; it stops it being invisible."""
    @dataclass
    class _Out:
        node_id: str = "root"
        gate_passed: bool = True
        semantic_covered: bool = True
        semantic_findings: str = ""
        criteria_verdicts: tuple = ()
        conflicts: tuple = ()
        undecided_obligations: tuple = ()
        l0l1_failures: tuple = ()

    e = engine
    _plan(e)
    monkeypatch.setattr(_runner, "llm_factory", lambda m: object(), raising=False)

    def _run(verdict):
        monkeypatch.setattr(_runner, "critique_node",
                            lambda *a, **k: _Out(criteria_verdicts=(
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
                          "spec": Spec("a goal", (Criteria("c1", "one"),), (), scope=())})()
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
                          "spec": Spec("a goal", (Criteria("c1", "one"),), (), scope=())})()
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
                                  "criteria": [{"name": "c1", "description": "the thing"}],
                                  "accepted_risks": [{"item": "fixture", "predictability": "extraordinary",
                                                      "justification": "accepted", "invalidation_condition": "never"}]},
                      "agent")
    tools.create_task(e, "kid", {"description": "child", "criteria": [{"name": "k", "description": "K"}]},
                      assignee="agent", parent_id="root")
    tools.map_criterion(e, "root", "kid", "c1")
    e._graph._storage.store_critique(TaskId("root"), json.dumps({
        "node_id": "root", "gate_passed": True, "semantic_covered": False,
        "criteria_verdicts": [{"criterion": "c1", "verdict": "insufficient", "why": "not carried"}],
        "conflicts": [], "undecided_obligations": [],
        "iteration": 0, "reopens": 0, "revisions": 0}))
    root = e.get_task(TaskId("root")); root.verified = True; e._graph.save_task(root)
    assert e.open_l2_findings(TaskId("root")) == ["c1"]        # the one list the gate reads


def test_a_goal_that_has_not_moved_is_not_mined_again(engine):
    """Twenty-six rounds, fifty-one criteria, $19.44 on the gate, and not one executor call.

    Measured to its conclusion on the E3 arm 2026-08-21: the sufficiency check asks a question ABOUT
    THE GOAL — what does this text require that no criterion decides — and re-asking it open-endedly
    after every criteria edit made it discover a fresh corner each round, growing the contract until
    the run died in the gate without writing any code. The answer belongs to the text: when the goal
    has not moved, later rounds re-judge the obligations already named instead of reading it again,
    and nothing new can be invented."""
    e = engine
    tools.create_task(e, "root", {"name": "root", "description": "build the thing",
                                  "criteria": [{"name": "c1", "description": "the thing"}]}, "agent")
    task = e.get_task(TaskId("root"))
    assert _goal_changed(None, task)                              # never reviewed → read the goal
    prior = {"goal_text": "build the thing",
             "undecided_obligations": [{"obligation": "it is installable"},
                                       {"obligation": "it has a README"}]}
    assert not _goal_changed(prior, task)                         # same text → judge the list
    assert _goal_changed({**prior, "goal_text": "build something else"}, task)

    class _Judge:
        def complete(self, prompt, context=None, **kw):
            assert "OBLIGATIONS NAMED EARLIER" in prompt          # …the fixed list, not the goal
            return json.dumps({"decided": ["1"]})

    left = _still_undecided(e, task, _Judge(), tuple(prior["undecided_obligations"]))
    assert [g["obligation"] for g in left] == ["it has a README"]


def test_a_count_that_was_not_measured_is_not_zero(engine, monkeypatch):
    """`open_count: 0` was printed beside six hard Level-0 failures.

    When the Syntactic level fails, the Level-2 checker is gated out and names nothing — and the
    count read zero, which a reader glancing at it takes for a clean plan (measured on the human door
    2026-08-22). A number that cannot tell "none" from "unmeasured" must not be a number, and the
    delta against the last check is not a comparison either when nothing was compared."""
    monkeypatch.setenv("GFSO_L2_GATE", "1")
    e = engine
    tools.create_task(e, "root", {"name": "root", "description": "a goal",
                                  "criteria": [{"name": "c1", "description": "the thing"}]}, "agent")
    tools.create_task(e, "kid", {"description": "child", "criteria": [{"name": "k", "description": "K"}]},
                      assignee="agent", parent_id="root")     # …unmapped: CHECK-1 fails
    out = TL.review_decomposition(e, "root")
    assert out["gate_passed"] is False
    assert out["open_count"] is None and "not measured" in out["open_count_note"]
    assert out["execution_admitted"] is False


def test_the_checker_reads_the_plan_several_times_on_its_first_pass(engine, monkeypatch):
    """With the contract steady at twelve criteria, the checker still found one NEW thing per round.

    Measured on the E3 arm 2026-08-22: three rounds, one new finding each, and the run ended
    `l2_not_discharged` without a line of code. One reading of a plan is one sample of a judgement
    that varies; a doubt raised by ANY reading is a doubt to answer, so the first pass takes several
    and unions them. Later rounds read once — by then the plan has changed, and what they judge is
    the change."""
    monkeypatch.setattr("gfso.critic.runner.CHECKER_READINGS", 3)
    e = engine
    tools.create_task(e, "root", {"name": "root", "description": "a goal",
                                  "criteria": [{"name": "c1", "description": "one"},
                                               {"name": "c2", "description": "two"}],
                                  "accepted_risks": [{"item": "fixture", "predictability": "extraordinary",
                                                      "justification": "a", "invalidation_condition": "n"}]},
                      "agent")
    tools.create_task(e, "kid", {"description": "child", "criteria": [{"name": "k", "description": "K"}]},
                      assignee="agent", parent_id="root")
    tools.map_criterion(e, "root", "kid", "c1")
    tools.map_criterion(e, "root", "kid", "c2")

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
           "conflicts": [{"between": ["kid-a", "kid-b"], "why": "…"}],
           "undecided_obligations": [{"obligation": "the package imports", "why": "…"}],
           "disputes": {"c1": {"why": "answered in writing"}}}

    assert finding_keys(rec) == ["conflict: kid-a, kid-b", "undecided: the package imports"]
    # …and the same names WITHOUT the dispute filter, which is what a delta baseline reads
    assert finding_keys(rec, exclude_disputed=False)[0] == "c1"


def test_a_check_already_running_is_not_offered_as_a_step(engine, monkeypatch):
    """The frontier kept saying "call review_decomposition" while one was mid-flight.

    A duplicate paid round over a plan that had not changed — and the other in-flight surface
    (`validate_result`) had suppressed exactly this for a while (measured on the human door
    2026-08-22, where the two surfaces disagreed about the same node)."""
    monkeypatch.setenv("GFSO_L2_GATE", "1")
    _plan(engine)
    key = engine.begin_review(TaskId("root"))
    assert key is not None and engine.begin_review(TaskId("root")) is None   # one per plan version

    out = T.next_steps(engine)
    assert not [s for s in out.get("steps", [])
                if s["task_id"] == "root" and "PLAN" in s["directive"]]
    assert any("plan being checked" in w["why"] for w in out.get("in_flight", []))
    engine.end_review(key)


def test_the_checker_does_not_relitigate_a_plan_it_already_judged(engine, monkeypatch):
    """The gate was non-monotone, and that is what made discharging it feel like whack-a-mole.

    Measured on the agent door 2026-08-22: a criterion was ruled `sufficient` twice with a stated
    reason, and after an edit touching a DIFFERENT node's criteria it came back `insufficient` with
    the opposite claim — three rounds, $0.86, each closing findings while opening others that had
    been true from the first. A criterion decided against a plan that has not changed since is
    carried forward; anything else is judged afresh, and a changed plan is judged whole."""
    _plan(engine)
    task = engine.get_task(TaskId("root"))
    prior = {"plan_generation": list(_plan_generation(task)),
             "criteria_verdicts": [{"criterion": "c1", "verdict": "sufficient", "why": "carried"},
                                   {"criterion": "c2", "verdict": "insufficient", "why": "a gap"}]}

    decided = _already_decided(prior, task)
    assert list(decided) == ["c1"], "only what was SETTLED is carried; a gap is asked again"

    # …and a plan that changed is judged whole: a new criterion moves the stamp
    T.edit_criteria(engine, "root", [{"name": "c1", "description": "one"},
                                     {"name": "c2", "description": "two"},
                                     {"name": "c3", "description": "three"}], agent="agent")
    assert _already_decided(prior, engine.get_task(TaskId("root"))) == {}
