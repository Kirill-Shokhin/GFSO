"""L2 critic runner — the STRUCTURAL gate + the validate storage/dirty-flag. The semantic (search⊕audit)
pass is deferred, so the gate returns no holes on a clean node; it must never spend an LLM."""
from gfso.engine import Engine
from gfso.adapters.storage.memory import MemoryStorage
from gfso.adapters.agents.human import HumanAgent
from gfso.adapters.llm.stub import StubLLM
from gfso.core.types import TaskId, AgentId, Spec, Criteria, CriterionMapping, NeglectedItem
from gfso.critic.runner import critique_node


def _engine() -> Engine:
    e = Engine(MemoryStorage(), HumanAgent(), StubLLM(), validate_signals=False)
    e.start()
    return e


def _decompose_clean(e: Engine):
    # genuinely L0/L1-clean: every child mapped, NEGLECTED present, seam has glue.
    e.assign_task(
        TaskId("p"),
        Spec("p", (Criteria("c1", "x"), Criteria("c2", "y")), (NeglectedItem("scaling out of scope"),)),
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


def test_clean_node_passes_gate_no_semantic_yet():
    """A structurally-clean non-leaf passes the gate; the semantic hole-hunt (search⊕audit) is deferred,
    so no holes are produced and NO LLM is consulted."""
    e = _engine()
    _decompose_clean(e)
    crit = critique_node(e, TaskId("p"))
    assert crit.gate_passed
    assert crit.holes == () and crit.verdicts == ()


def test_validate_stores_and_sets_verified_then_dirties():
    e = _engine()
    _decompose_clean(e)
    assert e.get_task(TaskId("p")).verified is False
    crit = e.validate_decomposition(TaskId("p"))
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
    e.validate_decomposition(TaskId("p"))
    assert e.get_task(TaskId("p")).verified is True
    e.assign_task(TaskId("a"), Spec("a v2", (Criteria("c1", "x"),)), AgentId("d1"), parent_id=TaskId("p"))
    e.wait_idle()
    assert e.get_task(TaskId("p")).verified is False
