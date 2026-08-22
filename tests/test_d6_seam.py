"""D6 (canon §14.5) — validation at the SEAM, not at every node.

Public node ⟺ delegation seam: a root, or Del(child) ≠ Del(parent). The verifier≠executor
gate fires there. An INTERNAL node (same Del as its parent) is the agent's private
decomposition — it self-verifies (DELIVER carries self_validation) and its guarantee is
carried by the validation of the public result it rolls up into (Thm 1 non-redundancy).
The root always stays gated: "done" never completes on a self-stamp.
"""
import pytest

from gfso.engine import Engine
from gfso.adapters.storage.memory import MemoryStorage
from gfso.adapters.agents.human import HumanAgent
import gfso.delegate as D
from gfso import tools as T
from gfso.core.types import (AcceptedRiskItem, CriterionMapping, Predictability, State, Signal,
                             SignalData, TaskId, AgentId, Spec, Criteria, Verdict)


def _spec(desc="goal", crit="c1"):
    return Spec(description=desc, criteria=(Criteria(crit, f"{crit} description"),),
                accepted_risks=(AcceptedRiskItem("an unmodelled environment fault",
                                                 Predictability.EXTRAORDINARY),))


@pytest.fixture
def engine():
    e = Engine(MemoryStorage(), HumanAgent(), llm=None, check_interval=10_000)
    e.start()
    yield e
    e.stop()


def _deliver(e, tid, actor, self_check=Verdict.PASS):
    """ACCEPT + DELIVER. The delivery carries the executor's own decided self-check by default —
    §14.5 D6 says an internal node self-verifies THROUGH that field, and a PASS with nothing behind
    it is ⊥ (§11.2). Pass `self_check=None` for the delivery that checked nothing."""
    for sd in (
        SignalData(signal=Signal.ACCEPT, task_id=TaskId(tid), source=AgentId(actor)),
        SignalData(signal=Signal.DELIVER, task_id=TaskId(tid), source=AgentId(actor), result="r",
                   self_validation=self_check),
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
    """The agent's own internal node self-verifies — no INDEPENDENT verdict demanded (§14.5 D6);
    what its delivery must carry is its own decided self-check, which is the record it is judged on.
    A delivery that checked nothing leaves the node in VALIDATING for its issuer (§11.2)."""
    engine.assign_task(TaskId("root"), _spec("root", "rc"), AgentId("agent"))
    engine.wait_idle()
    engine.decompose_task(TaskId("root"), [(TaskId("in1"), _spec("in", "ic"), AgentId("agent"))],
                          criterion_mappings=[CriterionMapping("rc", TaskId("in1"))])
    engine.wait_idle()
    _deliver(engine, "in1", "agent", self_check=None)          # nothing checked → ⊥, not a pass
    engine.send_signal(SignalData(signal=Signal.PASS, task_id=TaskId("in1"), source=AgentId("agent")))
    engine.wait_idle()
    assert engine.get_state(TaskId("in1")) == State.VALIDATING

    # …saying what was checked settles it, through either door: the executor's own recorded verdict
    engine.record_reviewer_verdict(TaskId("in1"), Verdict.PASS, [], reviewer="agent",
                                   observed={"ic": "ran it and read the output"})
    engine.send_signal(SignalData(signal=Signal.PASS, task_id=TaskId("in1"), source=AgentId("agent")))
    engine.wait_idle()
    assert engine.get_state(TaskId("in1")) == State.DONE        # no independent verdict required
    assert engine.get_exec_verdict(TaskId("in1"))["verdict"] == Verdict.PASS   # …and it left a record


def test_an_internal_delivery_that_carries_its_self_check_needs_nothing_else(engine):
    """The other door: `self_validation` in the DELIVER packet IS the record (§14.5 D6)."""
    engine.assign_task(TaskId("root"), _spec("root", "rc"), AgentId("agent"))
    engine.wait_idle()
    engine.decompose_task(TaskId("root"), [(TaskId("in2"), _spec("in", "ic"), AgentId("agent"))],
                          criterion_mappings=[CriterionMapping("rc", TaskId("in2"))])
    engine.wait_idle()
    _deliver(engine, "in2", "agent")                            # carries self_validation=PASS
    engine.send_signal(SignalData(signal=Signal.PASS, task_id=TaskId("in2"), source=AgentId("agent")))
    engine.wait_idle()
    assert engine.get_state(TaskId("in2")) == State.DONE
    rec = engine.get_exec_verdict(TaskId("in2"))
    assert rec["verdict"] == Verdict.PASS and rec["validator"] == "agent"


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
    """A delegated (different-Del) child keeps the full separation — and the separation is not the
    evidence. Its executor cannot PASS it at all (issuer role); the ISSUER's PASS needs a verdict
    for this delivery on the record, because §14.5 asks for independent VALIDATION at a seam, not
    for a signer whose name differs from the executor's. This test used to assert the opposite
    ("the issuer's PASS needs no gate change"), and that belief was the false PASS the agent door
    walked into on 2026-08-22."""
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
    # the issuer PASSes across the seam — refused while nothing is on the record…
    engine.send_signal(SignalData(signal=Signal.PASS, task_id=TaskId("d1"), source=AgentId("pm")))
    engine.wait_idle()
    assert engine.get_state(TaskId("d1")) == State.VALIDATING
    # …and accepted once the issuer says what they observed (a person may judge by hand; what is
    # refused is a PASS standing on nothing)
    engine.record_reviewer_verdict(TaskId("d1"), Verdict.PASS, [], reviewer="pm",
                                   observed={"dc": "ran it, printed 42"})
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
    """§13.4 moved from advice to enforcement: a child cannot start executing (ACCEPT) while its
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
    assert engine.get_state(TaskId("ch")) == State.OFFERED
    # complete the plan (map the child) → now execution is admitted
    engine.map_criterion(TaskId("root"), TaskId("ch"), "rc")
    engine.wait_idle()
    r = engine.send_signal_sync(SignalData(signal=Signal.ACCEPT, task_id=TaskId("ch"), source=AgentId("agent")))
    assert not r.rejected and engine.get_state(TaskId("ch")) == State.EXECUTING


def test_empty_accepted_risks_does_not_gate_execution(engine):
    """CHECK-4 (ACCEPTED_RISKS) is completeness DOCUMENTATION, not a correctness gate — an empty ACCEPTED_RISKS
    must NOT block execution (gating it forced a fake ACCEPTED_RISKS and drove edit_accepted_risks churn, live)."""
    engine.assign_task(TaskId("root"), _spec("root", "rc"), AgentId("agent"))
    engine.wait_idle()
    engine.decompose_task(TaskId("root"), [(TaskId("ch"), _spec("child", "cc"), AgentId("agent"))],
                          criterion_mappings=[CriterionMapping("rc", TaskId("ch"))])
    engine.wait_idle()  # mapped but NO ACCEPTED_RISKS authored on root
    r = engine.send_signal_sync(SignalData(signal=Signal.ACCEPT, task_id=TaskId("ch"), source=AgentId("agent")))
    assert not r.rejected and engine.get_state(TaskId("ch")) == State.EXECUTING


def test_an_internal_node_completes_on_its_own_self_check(engine):
    """§14.5 D6, read literally: an internal node self-verifies and is NOT independently validated.

    "DELIVER carries `self_validation`" … "the guarantee for the whole internal decomposition is
    carried by the validation of the agent's public result" … the agent "stakes all internal work on
    one public validation". So there is no second party owed a verdict on an internal node — its
    issuer IS its executor's scope, by the definition that makes it internal.

    Measured 2026-08-20: nothing relayed that self-check, so a subtree delegated to ONE role
    deadlocked — the delivery landed in 57 seconds and the graph stood still for half an hour. The
    field was in the report schema and in `SignalData`, and was dropped between them.

    The three conditions are tested together, because each alone would be a different rule:
    internal only, a DECIDED self-check only (⊥ is not a pass, §11.2), and never when independent
    validation is going to run anyway.
    """
    e = engine
    T.create_task(e, "par", {"description": "parent", "criteria": [{"name": "g", "description": "G"}],
                             "accepted_risks": [{"item": "an unmodelled environment fault",
                                                 "predictability": "EXTRAORDINARY"}]},
                  assignee="exec-1")
    T.create_task(e, "kid", {"description": "internal child",
                             "criteria": [{"name": "k", "description": "K"}]},
                  assignee="exec-1", parent_id="par")          # same Del as its parent → INTERNAL
    T.map_criterion(e, "par", "kid", "g")
    T.signal(e, "kid", "ACCEPT", "exec-1")
    T.signal(e, "kid", "DELIVER", "exec-1", result="built it")

    said = []
    D._settle_internal(e, TaskId("kid"), "", said.append)       # no self-check → ⊥, not a pass
    e.wait_idle()
    assert e.get_state(TaskId("kid")).name == "VALIDATING"

    D._settle_internal(e, TaskId("kid"), "ran its check, it printed what it should", said.append)
    e.wait_idle()
    assert e.get_state(TaskId("kid")).name == "DONE"            # …the self-check settles it
    assert any("§14.5 D6" in m for m in said)

    # …and the PUBLIC node above it is untouched: that is where the independent verdict is owed.
    T.signal(e, "par", "ACCEPT", "exec-1")
    T.signal(e, "par", "DELIVER", "exec-1", result="integrated")
    D._settle_internal(e, TaskId("par"), "I checked it myself", said.append)
    e.wait_idle()
    assert e.get_state(TaskId("par")).name == "VALIDATING"      # a seam is never self-signed
