"""D6 (canon §6.5) — validation at the SEAM, not at every node.

Public node ⟺ delegation seam: a root, or Del(child) ≠ Del(parent). The verifier≠executor
gate fires there. An INTERNAL node (same Del as its parent) is the agent's private
decomposition — it self-verifies (DELIVER carries self_validation) and its guarantee is
carried by the validation of the public result it rolls up into (T1 non-redundancy).
The root always stays gated: "done" never completes on a self-stamp.
"""
import pytest

from gfso.engine import Engine
from gfso.adapters.storage.memory import MemoryStorage
from gfso.adapters.agents.human import HumanAgent
from gfso.core.types import CriterionMapping, State, Signal, SignalData, TaskId, AgentId, Spec, Criteria


def _spec(desc="goal", crit="c1"):
    return Spec(description=desc, criteria=(Criteria(crit, f"{crit} description"),))


@pytest.fixture
def engine():
    e = Engine(MemoryStorage(), HumanAgent(), llm=None, check_interval=10_000)
    e.start()
    yield e
    e.stop()


def _deliver(e, tid, actor):
    for sd in (
        SignalData(signal=Signal.ACCEPT, task_id=TaskId(tid), source=AgentId(actor)),
        SignalData(signal=Signal.DELIVER, task_id=TaskId(tid), source=AgentId(actor), result="r"),
    ):
        e.send_signal(sd)
        e.wait_idle()


def test_is_public_classification(engine):
    engine.assign_task(TaskId("root"), _spec("root", "rc"), AgentId("agent"))
    engine.wait_idle()
    engine.decompose_task(TaskId("root"), [
        (TaskId("mine"), _spec("mine", "mc"), AgentId("agent")),      # same Del → internal
        (TaskId("theirs"), _spec("theirs", "tc"), AgentId("worker")),  # Del seam → public
    ])
    engine.wait_idle()
    g = engine._graph
    assert g.is_public(engine.get_task(TaskId("root")))      # a root is always a seam
    assert not g.is_public(engine.get_task(TaskId("mine")))  # internal: private decomposition
    assert g.is_public(engine.get_task(TaskId("theirs")))    # delegation seam


def test_internal_same_del_node_may_self_pass(engine):
    """The agent's own internal node self-verifies — no recorded verdict demanded (§6.5)."""
    engine.assign_task(TaskId("root"), _spec("root", "rc"), AgentId("agent"))
    engine.wait_idle()
    engine.decompose_task(TaskId("root"), [(TaskId("in1"), _spec("in", "ic"), AgentId("agent"))],
                          criterion_mappings=[CriterionMapping("rc", TaskId("in1"))])
    engine.wait_idle()
    _deliver(engine, "in1", "agent")
    engine.send_signal(SignalData(signal=Signal.PASS, task_id=TaskId("in1"), source=AgentId("agent")))
    engine.wait_idle()
    assert engine.get_state(TaskId("in1")) == State.DONE  # no independent verdict required


def test_root_self_pass_still_gated(engine):
    """The root is the one seam "done" must cross — a self-stamp never completes it."""
    engine.assign_task(TaskId("solo"), _spec(), AgentId("agent"))
    engine.wait_idle()
    _deliver(engine, "solo", "agent")
    engine.send_signal(SignalData(signal=Signal.PASS, task_id=TaskId("solo"), source=AgentId("agent")))
    engine.wait_idle()
    assert engine.get_state(TaskId("solo")) == State.VALIDATING  # rejected without a verdict
    engine.record_reviewer_verdict(TaskId("solo"), "PASS", [], "reviewer")
    engine.send_signal(SignalData(signal=Signal.PASS, task_id=TaskId("solo"), source=AgentId("agent")))
    engine.wait_idle()
    assert engine.get_state(TaskId("solo")) == State.DONE


def test_seam_child_unaffected_by_d6(engine):
    """A delegated (different-Del) child keeps the full separation: its executor cannot PASS it
    at all (issuer role), and the issuer's PASS needs no gate change — the seam already exists."""
    engine.assign_task(TaskId("root"), _spec("root", "rc"), AgentId("pm"))
    engine.wait_idle()
    engine.decompose_task(TaskId("root"), [(TaskId("d1"), _spec("d", "dc"), AgentId("w"))],
                          criterion_mappings=[CriterionMapping("rc", TaskId("d1"))])
    engine.wait_idle()
    _deliver(engine, "d1", "w")
    # the executor's own PASS on a seam node → rejected by the ISSUER role rule
    engine.send_signal(SignalData(signal=Signal.PASS, task_id=TaskId("d1"), source=AgentId("w")))
    engine.wait_idle()
    assert engine.get_state(TaskId("d1")) == State.VALIDATING
    # the issuer PASSes across the seam — canon default separation
    engine.send_signal(SignalData(signal=Signal.PASS, task_id=TaskId("d1"), source=AgentId("pm")))
    engine.wait_idle()
    assert engine.get_state(TaskId("d1")) == State.DONE


def test_dispatcher_validates_seams_only_by_default(engine, monkeypatch):
    """The auto-validation instrument fires at seams; internal nodes are the opt-in dial."""
    from gfso.delegate import Dispatcher, AgentRegistry
    monkeypatch.delenv("GFSO_VALIDATE_INTERNAL", raising=False)
    reg = AgentRegistry.__new__(AgentRegistry)
    reg._agents = {}
    d = Dispatcher(engine, reg)
    engine.assign_task(TaskId("root"), _spec("root", "rc"), AgentId("agent"))
    engine.wait_idle()
    engine.decompose_task(TaskId("root"), [
        (TaskId("mine"), _spec("m", "mc"), AgentId("agent")),
        (TaskId("theirs"), _spec("t", "tc"), AgentId("worker")),
    ])
    engine.wait_idle()
    assert not d._validate_here(engine.get_task(TaskId("mine")))   # internal → self-validation
    assert d._validate_here(engine.get_task(TaskId("theirs")))     # seam → instrument
    assert d._validate_here(engine.get_task(TaskId("root")))       # root → instrument
    monkeypatch.setenv("GFSO_VALIDATE_INTERNAL", "1")
    assert d._validate_here(engine.get_task(TaskId("mine")))       # the opt-in dial


def test_execution_gated_on_plan_verification(engine):
    """§5.4 moved from advice to enforcement: a child cannot start executing (ACCEPT) while its
    parent's plan fails a CORRECTNESS check — here an uncovered parent criterion (CHECK-1). This is
    the systemic 'verify before you execute' — the agent physically cannot work a flawed plan, so the
    plan is completed and checked ONCE up front (no discover-after-delivery, no rework churn)."""
    engine.assign_task(TaskId("root"), _spec("root", "rc"), AgentId("agent"))
    engine.wait_idle()
    engine.decompose_task(TaskId("root"), [(TaskId("ch"), _spec("child", "cc"), AgentId("agent"))])
    engine.wait_idle()
    # unmapped child → parent CHECK-1 fails → ACCEPT is REFUSED (cannot execute an unverified plan)
    r = engine.send_signal_sync(SignalData(signal=Signal.ACCEPT, task_id=TaskId("ch"), source=AgentId("agent")))
    assert r.rejected and "Level-0" in (r.error or "")
    assert engine.get_state(TaskId("ch")) == State.REVIEW
    # complete the plan (map the child) → now execution is admitted
    engine.map_criterion(TaskId("root"), TaskId("ch"), "rc")
    engine.wait_idle()
    r = engine.send_signal_sync(SignalData(signal=Signal.ACCEPT, task_id=TaskId("ch"), source=AgentId("agent")))
    assert not r.rejected and engine.get_state(TaskId("ch")) == State.EXECUTING


def test_empty_neglected_does_not_gate_execution(engine):
    """CHECK-4 (NEGLECTED) is completeness DOCUMENTATION, not a correctness gate — an empty NEGLECTED
    must NOT block execution (gating it forced a fake NEGLECTED and drove reneglect churn, live)."""
    engine.assign_task(TaskId("root"), _spec("root", "rc"), AgentId("agent"))
    engine.wait_idle()
    engine.decompose_task(TaskId("root"), [(TaskId("ch"), _spec("child", "cc"), AgentId("agent"))],
                          criterion_mappings=[CriterionMapping("rc", TaskId("ch"))])
    engine.wait_idle()  # mapped but NO NEGLECTED authored on root
    r = engine.send_signal_sync(SignalData(signal=Signal.ACCEPT, task_id=TaskId("ch"), source=AgentId("agent")))
    assert not r.rejected and engine.get_state(TaskId("ch")) == State.EXECUTING
