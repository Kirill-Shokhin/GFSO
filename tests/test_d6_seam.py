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
from gfso.core.types import State, Signal, SignalData, TaskId, AgentId, Spec, Criteria


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
    engine.decompose_task(TaskId("root"), [(TaskId("in1"), _spec("in", "ic"), AgentId("agent"))])
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
    engine.decompose_task(TaskId("root"), [(TaskId("d1"), _spec("d", "dc"), AgentId("w"))])
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
