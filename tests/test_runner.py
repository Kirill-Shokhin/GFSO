"""L2 critic runner — the STRUCTURAL gate + the causal-correctness CHECKER + validate storage/dirty-flag.
The gate blocks the checker; a clean node with no usable LLM produces NO verdict (never read as clean);
with an LLM, ONE zero-tool call yields per-parent-criterion sufficient/insufficient/uncertain + FM-2
conflicts; an INCOMPLETE verdict (a parent criterion unjudged) is treated as NO verdict."""
from gfso.engine import Engine
from gfso.adapters.storage.memory import MemoryStorage
from gfso.adapters.agents.human import HumanAgent
from gfso.adapters.llm.stub import StubLLM
from gfso.core.types import TaskId, AgentId, Spec, Criteria, CriterionMapping, NeglectedItem, Predictability
from gfso.critic.runner import critique_node, review_decomposition


def _engine() -> Engine:
    e = Engine(MemoryStorage(), HumanAgent(), StubLLM(), validate_signals=False)
    e.start()
    return e


def _decompose_clean(e: Engine):
    # genuinely L0/L1-clean: every child mapped, NEGLECTED present (a classified RISK event — v3.7 §5.1:
    # a scope boundary would not belong here, and an unclassified record fails the STD-2 guard), seam has glue.
    e.assign_task(
        TaskId("p"),
        Spec("p", (Criteria("c1", "x"), Criteria("c2", "y")),
             (NeglectedItem("provider rate-limit spike", Predictability.STATISTICAL, "P<1%, off-peak run"),)),
        AgentId("pm"),
    )
    e.wait_idle()
    e.decompose_task(TaskId("p"), [
        (TaskId("a"), Spec("a", ()), AgentId("d1")),
        (TaskId("b"), Spec("b", ()), AgentId("d2")),
    ], criterion_mappings=[CriterionMapping("c1", TaskId("a")), CriterionMapping("c2", TaskId("b"))])
    e.wait_idle()
    e.add_dependency(TaskId("a"), TaskId("b"), glue="b reads a's total")


def test_gate_blocks_leaf():
    e = _engine()
    e.assign_task(TaskId("leaf"), Spec("x", ()), AgentId("d"))
    e.wait_idle()
    crit = critique_node(e, TaskId("leaf"))
    assert not crit.gate_passed and "leaf" in crit.l0l1_failures[0]


def test_gate_blocks_on_l0l1_failure():
    e = _engine()
    # parent with a criterion but NO mapping → CHECK-1 coverage FAIL
    e.assign_task(TaskId("p"), Spec("p", (Criteria("c", "x"),)), AgentId("pm"))
    e.wait_idle()
    e.decompose_task(TaskId("p"), [(TaskId("a"), Spec("a", ()), AgentId("d1"))])
    e.wait_idle()
    crit = critique_node(e, TaskId("p"))
    assert not crit.gate_passed
    assert any("CHECK-1" in f for f in crit.l0l1_failures)


def test_clean_node_passes_gate_no_semantic_without_llm():
    """A structurally-clean non-leaf passes the gate; with no LLM (or a stub returning nothing) the
    semantic verdict stays None — an absent hunt is NEVER read as clean."""
    e = _engine()
    _decompose_clean(e)
    crit = critique_node(e, TaskId("p"))
    assert crit.gate_passed
    assert crit.semantic_covered is None and crit.semantic_findings == ""


class _CheckerLLM:
    """Fake checker: records the input, returns a scripted JSON verdict."""
    def __init__(self, reply: str):
        self.reply, self.seen = reply, []

    def complete(self, prompt: str, context: str = "") -> str:
        self.seen.append((prompt, context))
        return self.reply


def _verdict_json(criteria, conflicts=()):
    import json
    return "```json\n" + json.dumps({"criteria": list(criteria), "conflicts": list(conflicts)}) + "\n```"


def test_checker_all_sufficient_is_covered():
    e = _engine()
    _decompose_clean(e)
    llm = _CheckerLLM(_verdict_json([
        {"criterion": "c1", "verdict": "sufficient", "why": "a's pass carries it"},
        {"criterion": "c2", "verdict": "sufficient", "why": "b's pass carries it"}]))
    crit = critique_node(e, TaskId("p"), llm=llm)
    assert crit.gate_passed and crit.semantic_covered is True and crit.semantic_findings == ""
    assert len(crit.criteria_verdicts) == 2
    # the checker judges the node's ONE canonical read (the projection), under the checker role
    prompt, context = llm.seen[0]
    assert "DECOMPOSITION LEVEL UNDER CHECK" in prompt and "CHECKER, not a decomposer" in context


def test_checker_gap_and_conflict_are_advisory_findings():
    e = _engine()
    _decompose_clean(e)
    llm = _CheckerLLM(_verdict_json(
        [{"criterion": "c1", "verdict": "insufficient",
          "why": "a can pass with stale data and c1 still fails"},
         {"criterion": "c2", "verdict": "uncertain", "why": "depends on the retention policy"}],
        [{"between": ["a", "b"], "why": "a demands sync writes, b demands async-only"}]))
    crit = critique_node(e, TaskId("p"), llm=llm)
    assert crit.gate_passed and crit.semantic_covered is False
    assert "stale data" in crit.semantic_findings and "conflict" in crit.semantic_findings
    assert len(crit.conflicts) == 1


def test_checker_incomplete_verdict_is_no_verdict():
    """A parent criterion the checker did not judge ⇒ semantic_covered=None — an incomplete
    certificate is NEVER read as clean."""
    e = _engine()
    _decompose_clean(e)
    llm = _CheckerLLM(_verdict_json([{"criterion": "c1", "verdict": "sufficient", "why": "ok"}]))
    crit = critique_node(e, TaskId("p"), llm=llm)
    assert crit.gate_passed and crit.semantic_covered is None
    assert "INCOMPLETE" in crit.semantic_findings and "c2" in crit.semantic_findings


def test_checker_unparseable_is_no_verdict():
    e = _engine()
    _decompose_clean(e)
    llm = _CheckerLLM("I think it looks fine overall!")
    crit = critique_node(e, TaskId("p"), llm=llm)
    assert crit.gate_passed and crit.semantic_covered is None


def test_checker_gated_by_structure():
    """L2 presupposes a structurally-complete graph: a failing gate must not spend the LLM."""
    e = _engine()
    e.assign_task(TaskId("p"), Spec("p", (Criteria("c", "x"),)), AgentId("pm"))
    e.wait_idle()
    e.decompose_task(TaskId("p"), [(TaskId("a"), Spec("a", ()), AgentId("d1"))])
    e.wait_idle()
    llm = _CheckerLLM("should never be called")
    crit = critique_node(e, TaskId("p"), llm=llm)
    assert not crit.gate_passed and llm.seen == []


def test_validate_stores_and_sets_verified_then_dirties():
    e = _engine()
    _decompose_clean(e)
    assert e.get_task(TaskId("p")).verified is False
    crit = review_decomposition(e, TaskId("p"))
    assert crit.gate_passed
    assert e.get_task(TaskId("p")).verified is True            # validated → fresh
    assert e.get_critique(TaskId("p"))["gate_passed"] is True  # stored record
    e.remove_dependency(TaskId("a"), TaskId("b"))              # a decomposition change must dirty it
    assert e.get_task(TaskId("p")).verified is False


def test_review_record_carries_provenance_and_get_review_reads_it():
    """Re-validation UX: the stored record says WHO judged (model) and WHEN (ts); get_review is the
    free read (no LLM) agents/UI consume; a shape change stales freshness but KEEPS the record
    (so a re-run has something to be compared against)."""
    from gfso import tools as T
    e = _engine()
    _decompose_clean(e)
    llm = _CheckerLLM(_verdict_json([
        {"criterion": "c1", "verdict": "sufficient", "why": "ok"},
        {"criterion": "c2", "verdict": "sufficient", "why": "ok"}]))
    llm.model = "sonnet-test"
    review_decomposition(e, TaskId("p"), llm=llm)
    out = T.get_review(e, "p")
    assert out["verified"] is True
    assert out["review"]["model"] == "sonnet-test" and out["review"]["ts"]
    assert out["review"]["semantic_covered"] is True
    e.remove_dependency(TaskId("a"), TaskId("b"))
    out2 = T.get_review(e, "p")
    assert out2["verified"] is False                    # stale…
    assert out2["review"]["model"] == "sonnet-test"     # …but the record survives for comparison


def test_edit_criteria_on_child_stales_parent_review():
    """The freshness contract: ANY shape change — including a CHILD's criteria edit — stales the
    parent's stored review (the checker judged a mapping that no longer exists)."""
    from gfso import tools as T
    e = _engine()
    _decompose_clean(e)
    review_decomposition(e, TaskId("p"))
    assert e.get_task(TaskId("p")).verified is True
    T.edit_criteria(e, "a", [{"name": "x2", "description": "tighter"}], "pm")
    assert e.get_task(TaskId("p")).verified is False


def test_child_reassign_dirties_parent():
    """Cross-node invalidation: a re-assigned child changes the parent's CHECK-1/7 → parent recomputed
    and marked stale."""
    e = _engine()
    _decompose_clean(e)
    review_decomposition(e, TaskId("p"))
    assert e.get_task(TaskId("p")).verified is True
    e.assign_task(TaskId("a"), Spec("a v2", (Criteria("c1", "x"),)), AgentId("d1"), parent_id=TaskId("p"))
    e.wait_idle()
    assert e.get_task(TaskId("p")).verified is False
