"""L2 critic runner — the STRUCTURAL gate + the semantic diff-search + the validate storage/dirty-flag.
The gate blocks the semantic pass; a clean node with no usable LLM produces NO semantic verdict (never
read as clean); with an LLM, ONE search-in-diff-mode call yields ALREADY-COVERED or advisory findings."""
from gfso.engine import Engine
from gfso.adapters.storage.memory import MemoryStorage
from gfso.adapters.agents.human import HumanAgent
from gfso.adapters.llm.stub import StubLLM
from gfso.core.types import TaskId, AgentId, Spec, Criteria, CriterionMapping, NeglectedItem, Predictability
from gfso.critic.runner import critique_node, validate_decomposition


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


class _SearchLLM:
    """Fake searcher: records the diff-mode input, returns a scripted reply."""
    def __init__(self, reply: str):
        self.reply, self.seen = reply, []

    def complete(self, prompt: str, context: str = "") -> str:
        self.seen.append(prompt)
        return self.reply


def test_semantic_search_covered():
    e = _engine()
    _decompose_clean(e)
    llm = _SearchLLM("ALREADY-COVERED — the requirement space is covered.")
    crit = critique_node(e, TaskId("p"), llm=llm)
    assert crit.gate_passed and crit.semantic_covered is True and crit.semantic_findings == ""
    # diff mode: the searcher received the node's projection as the CURRENT DECOMPOSITION
    assert "CURRENT DECOMPOSITION" in llm.seen[0] and "Decomposition under review" in llm.seen[0]


def test_semantic_search_reports_findings():
    e = _engine()
    _decompose_clean(e)
    llm = _SearchLLM("Missing: rollback path when b fails after a committed.")
    crit = critique_node(e, TaskId("p"), llm=llm)
    assert crit.gate_passed and crit.semantic_covered is False
    assert "rollback" in crit.semantic_findings


def test_semantic_search_gated_by_structure():
    """L2 presupposes a structurally-complete graph: a failing gate must not spend the LLM."""
    e = _engine()
    e.assign_task(TaskId("p"), Spec("p", (Criteria("c", "x"),)), AgentId("pm"))
    e.wait_idle()
    e.decompose_task(TaskId("p"), [(TaskId("a"), Spec("a", ()), AgentId("d1"))])
    e.wait_idle()
    llm = _SearchLLM("should never be called")
    crit = critique_node(e, TaskId("p"), llm=llm)
    assert not crit.gate_passed and llm.seen == []


def test_validate_stores_and_sets_verified_then_dirties():
    e = _engine()
    _decompose_clean(e)
    assert e.get_task(TaskId("p")).verified is False
    crit = validate_decomposition(e, TaskId("p"))
    assert crit.gate_passed
    assert e.get_task(TaskId("p")).verified is True            # validated → fresh
    assert e.get_critique(TaskId("p"))["gate_passed"] is True  # stored record
    e.remove_dependency(TaskId("a"), TaskId("b"))              # a decomposition change must dirty it
    assert e.get_task(TaskId("p")).verified is False


def test_child_reassign_dirties_parent():
    """Cross-node invalidation: a re-assigned child changes the parent's CHECK-1/7 → parent recomputed
    and marked stale."""
    e = _engine()
    _decompose_clean(e)
    validate_decomposition(e, TaskId("p"))
    assert e.get_task(TaskId("p")).verified is True
    e.assign_task(TaskId("a"), Spec("a v2", (Criteria("c1", "x"),)), AgentId("d1"), parent_id=TaskId("p"))
    e.wait_idle()
    assert e.get_task(TaskId("p")).verified is False
