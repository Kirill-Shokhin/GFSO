"""D6 (canon §10.3) — validation at the SEAM, not at every node.

Public node ⟺ delegation seam: a root, or Del(child) ≠ Del(parent). The verifier≠executor
gate fires there. An INTERNAL node (same Del as its parent) is the agent's private
decomposition — it self-verifies (DELIVER carries self_validation) and its guarantee is
carried by the validation of the public result it rolls up into (Thm 1 non-redundancy).
The root always stays gated: "done" never completes on a self-stamp.
"""
import pytest

import gfso.delegate as D
from gfso import reports
from gfso import tools as T
from gfso.core.types import (CriterionMapping, Register, State, Signal,
                             SignalData, TaskId, AgentId, Verdict)
from gfso.engine.validation import AdmissionRefused
from tests.support import REGISTER_SPLIT, criterion, make_engine, spec, reviewer_passes, REGISTER
from gfso.delegate import Dispatcher
from gfso.roster import AgentRegistry


@pytest.fixture
def engine():
    e = make_engine(llm=None, check_interval=10_000)
    e.start()
    yield e
    e.stop()


def _deliver(e, tid, actor, self_check=Verdict.PASS):
    """ACCEPT + DELIVER. The delivery carries the executor's own decided self-check by default —
    §10.3 says an internal node self-verifies THROUGH that field, and a PASS with nothing behind
    it is ⊥ (§2.3). Pass `self_check=None` for the delivery that checked nothing."""
    for sd in (
        SignalData(signal=Signal.ACCEPT, task_id=TaskId(tid), source=AgentId(actor)),
        SignalData(signal=Signal.DELIVER, task_id=TaskId(tid), source=AgentId(actor),
                   result="ran the leaf's check, it printed OK",
                   self_validation=self_check),
    ):
        e.send_signal(sd)
        e.wait_idle()


def test_is_public_classification(engine):
    engine.assign_task(TaskId("root"), spec("root", "rc"), AgentId("agent"))
    engine.wait_idle()
    engine.decompose_task(TaskId("root"), [
        (TaskId("mine"), spec("mine", "mc"), AgentId("agent")),      # same Del → internal
        (TaskId("theirs"), spec("theirs", "tc"), AgentId("worker")),  # Del seam → public
    ], [CriterionMapping("rc", TaskId("mine")), CriterionMapping("rc", TaskId("theirs"))], register=REGISTER_SPLIT)
    engine.wait_idle()
    g = engine._graph
    assert g.is_public(engine.graph.get_task(TaskId("root")))      # a root is always a seam
    assert not g.is_public(engine.graph.get_task(TaskId("mine")))  # internal: private decomposition
    assert g.is_public(engine.graph.get_task(TaskId("theirs")))    # delegation seam


def test_internal_same_del_node_may_self_pass(engine):
    """The agent's own internal node self-verifies — no INDEPENDENT verdict demanded (§10.3);
    what its delivery must carry is its own decided self-check, which is the record it is validated on.
    A delivery that checked nothing leaves the node in VALIDATING for its issuer (§2.3)."""
    engine.assign_task(TaskId("root"), spec("root", "rc"), AgentId("agent"))
    engine.wait_idle()
    engine.decompose_task(TaskId("root"), [(TaskId("in1"), spec("in", "ic"), AgentId("agent"))],
                          criterion_mappings=[CriterionMapping("rc", TaskId("in1"))], register=REGISTER_SPLIT)
    engine.wait_idle()
    _deliver(engine, "in1", "agent", self_check=None)          # nothing checked → ⊥, not a pass
    engine.send_signal(SignalData(signal=Signal.PASS, task_id=TaskId("in1"), source=AgentId("agent")))
    engine.wait_idle()
    assert engine.graph.get_state(TaskId("in1")) == State.VALIDATING

    # …saying what was checked settles it, through either door: the executor's own recorded verdict.
    # A criterion now carries the procedure that decides it (A1/§2), so the observation names which
    # of the PINNED commands was run — nothing is decided by a probe invented at validation time.
    engine.record_reviewer_verdict(TaskId("in1"), Verdict.PASS, [], reviewer="agent",
                                   observed={"ic": {"note": "ran it and read the output",
                                                    "ran": ["check ic"]}})
    engine.send_signal(SignalData(signal=Signal.PASS, task_id=TaskId("in1"), source=AgentId("agent")))
    engine.wait_idle()
    assert engine.graph.get_state(TaskId("in1")) == State.DONE        # no independent verdict required
    assert engine.get_exec_verdict(TaskId("in1"))["verdict"] == Verdict.PASS   # …and it left a record


def test_an_internal_delivery_that_carries_its_self_check_needs_nothing_else(engine):
    """The other door: `self_validation` in the DELIVER packet IS the record (§10.3)."""
    engine.assign_task(TaskId("root"), spec("root", "rc"), AgentId("agent"))
    engine.wait_idle()
    engine.decompose_task(TaskId("root"), [(TaskId("in2"), spec("in", "ic"), AgentId("agent"))],
                          criterion_mappings=[CriterionMapping("rc", TaskId("in2"))], register=REGISTER_SPLIT)
    engine.wait_idle()
    _deliver(engine, "in2", "agent")                            # carries self_validation=PASS
    engine.send_signal(SignalData(signal=Signal.PASS, task_id=TaskId("in2"), source=AgentId("agent")))
    engine.wait_idle()
    assert engine.graph.get_state(TaskId("in2")) == State.DONE
    rec = engine.get_exec_verdict(TaskId("in2"))
    assert rec["verdict"] == Verdict.PASS and rec["validator"] == "agent"


def test_root_self_pass_still_gated(engine):
    """The root is the one seam "done" must cross — a self-stamp never completes it."""
    engine.assign_task(TaskId("solo"), spec(), AgentId("agent"))
    engine.wait_idle()
    _deliver(engine, "solo", "agent")
    engine.send_signal(SignalData(signal=Signal.PASS, task_id=TaskId("solo"), source=AgentId("agent")))
    engine.wait_idle()
    assert engine.graph.get_state(TaskId("solo")) == State.VALIDATING  # rejected without a verdict
    reviewer_passes(engine, TaskId("solo"))
    engine.send_signal(SignalData(signal=Signal.PASS, task_id=TaskId("solo"), source=AgentId("agent")))
    engine.wait_idle()
    assert engine.graph.get_state(TaskId("solo")) == State.DONE


def test_seam_child_unaffected_by_d6(engine):
    """A delegated (different-Del) child keeps the full separation — and the separation is not the
    evidence. Its executor cannot PASS it at all (issuer role); the ISSUER's PASS needs a verdict
    for this delivery on the record, because §10.3 asks for independent VALIDATION at a seam, not
    for a signer whose name differs from the executor's. This test used to assert the opposite
    ("the issuer's PASS needs no gate change"), and that belief was the false PASS the agent door
    walked into on 2026-08-22."""
    engine.assign_task(TaskId("root"), spec("root", "rc"), AgentId("pm"))
    engine.wait_idle()
    engine.decompose_task(TaskId("root"), [(TaskId("d1"), spec("d", "dc"), AgentId("w"))],
                          criterion_mappings=[CriterionMapping("rc", TaskId("d1"))], register=REGISTER_SPLIT)
    engine.wait_idle()
    _deliver(engine, "d1", "w")
    # the executor's own PASS on a seam node → rejected by the ISSUER role rule
    engine.send_signal(SignalData(signal=Signal.PASS, task_id=TaskId("d1"), source=AgentId("w")))
    engine.wait_idle()
    assert engine.graph.get_state(TaskId("d1")) == State.VALIDATING
    # the issuer PASSes across the seam — refused while nothing is on the record…
    engine.send_signal(SignalData(signal=Signal.PASS, task_id=TaskId("d1"), source=AgentId("pm")))
    engine.wait_idle()
    assert engine.graph.get_state(TaskId("d1")) == State.VALIDATING
    # …and accepted once the issuer says what they observed (a person may validate by hand; what is
    # refused is a PASS standing on nothing)
    # …naming the pinned command it ran: a criterion carries its own procedure (A1/§2), and a hand
    # PASS that skips it is a pass on a procedure invented at validation time.
    engine.record_reviewer_verdict(TaskId("d1"), Verdict.PASS, [], reviewer="pm",
                                   observed={"dc": {"note": "ran it, printed 42",
                                                    "ran": ["check dc"]}})
    engine.send_signal(SignalData(signal=Signal.PASS, task_id=TaskId("d1"), source=AgentId("pm")))
    engine.wait_idle()
    assert engine.graph.get_state(TaskId("d1")) == State.DONE


def test_a_validation_stands_at_every_seam_and_at_the_top_of_every_one_session_scope(engine, monkeypatch):
    """Where κ ends (§3.7, §10.3): a seam, and the top of a scope one executor session carries. A node inside a
    scope — its parent's whole judged to fit one session — is that executor's own work, covered by the scope's
    validation at its top; an internal node nobody judged stays observed, as it always was. The per-piece
    validation turned a 2.6-minute task into 39 and 70 minutes. `GFSO_VALIDATE_INTERNAL=1` observes every one."""
    monkeypatch.delenv("GFSO_VALIDATE_INTERNAL", raising=False)
    reg = AgentRegistry.__new__(AgentRegistry)
    reg._agents = {}
    d = Dispatcher(engine, reg)
    engine.assign_task(TaskId("root"), spec("root", "rc"), AgentId("agent"))
    engine.wait_idle()
    engine.decompose_task(TaskId("root"), [
        (TaskId("mine"), spec("m", "mc"), AgentId("agent")),
        (TaskId("theirs"), spec("t", "tc"), AgentId("worker")),
    ], [CriterionMapping("rc", TaskId("mine")), CriterionMapping("rc", TaskId("theirs"))], register=REGISTER_SPLIT)
    engine.wait_idle()
    assert d._validate_here(engine.graph.get_task(TaskId("mine")))       # internal, nobody judged: observed
    assert d._validate_here(engine.graph.get_task(TaskId("theirs")))     # seam → instrument
    assert d._validate_here(engine.graph.get_task(TaskId("root")))       # root → instrument
    for t in ("root", "mine", "theirs"):
        engine.record_session_fit(TaskId(t), "~200 lines, 6 checks", True)
    assert not d._validate_here(engine.graph.get_task(TaskId("mine")))   # inside one session's scope
    assert d._validate_here(engine.graph.get_task(TaskId("theirs")))     # a seam stays a seam
    assert d._validate_here(engine.graph.get_task(TaskId("root")))       # the scope's top
    engine.record_session_fit(TaskId("theirs"), "~9000 lines, 80 checks", False)
    assert d._validate_here(engine.graph.get_task(TaskId("mine")))       # a part that does not fit: no scope
    monkeypatch.setenv("GFSO_VALIDATE_INTERNAL", "1")
    engine.record_session_fit(TaskId("theirs"), "~200 lines", True)
    assert d._validate_here(engine.graph.get_task(TaskId("mine")))       # measurement: every delivery


def test_execution_gated_on_plan_verification(engine):
    """§9.5 moved from advice to enforcement: a child cannot start executing (ACCEPT) while its
    parent's plan fails a CORRECTNESS check — here an uncovered parent criterion (CHECK-1). This is
    the systemic 'verify before you execute' — the agent physically cannot work a flawed plan, so the
    plan is completed and checked ONCE up front (no discover-after-delivery, no rework churn).
    Canon v4.1 (§11.5, §12.16 (ii), §12.10): the gate is the split's ADMISSION — a holed split issues no child;
    a hole a revision opens after it is a flag on the decomposer's plan, never a hold on the child's ACCEPT."""
    engine.assign_task(TaskId("root"), spec("root", "rc"), AgentId("agent"))
    engine.wait_idle()
    # unmapped child → parent CHECK-1 fails → the split is REFUSED whole (cannot execute an unverified plan)
    with pytest.raises(AdmissionRefused, match="CHECK-1"):
        engine.decompose_task(TaskId("root"), [(TaskId("ch"), spec("child", "cc"), AgentId("agent"))],
                              register=REGISTER_SPLIT)
    assert engine.graph.get_task(TaskId("ch")) is None, "a refused admission issued a child"
    # complete the plan (map the child) → now execution is admitted
    engine.decompose_task(TaskId("root"), [(TaskId("ch"), spec("child", "cc"), AgentId("agent"))],
                          [CriterionMapping("rc", TaskId("ch"))], register=REGISTER_SPLIT)
    engine.wait_idle()
    # a criterion added after admission opens a hole: flagged, and the issued child keeps working
    engine.edit_criteria(TaskId("root"), spec("root", "rc", "rd").criteria, AgentId("agent"))
    engine.wait_idle()
    assert any(c.check_name.startswith("CHECK-1:") and not c.passed for c in engine.get_checks(TaskId("root")))
    r = engine.send_signal_sync(SignalData(signal=Signal.ACCEPT, task_id=TaskId("ch"), source=AgentId("agent")))
    assert not r.rejected and engine.graph.get_state(TaskId("ch")) == State.EXECUTING


def test_empty_accepted_risks_does_not_gate_execution(engine):
    """CHECK-4 (ACCEPTED_RISKS) is completeness DOCUMENTATION, not a correctness gate — an empty ACCEPTED_RISKS
    must NOT block execution (gating it forced a fake ACCEPTED_RISKS and drove edit_accepted_risks churn, live).
    Canon v4.1 (§9.2, §11.5, §12.16 (ii)): CHECK-4 gates the split's ADMISSION — a split with no register issues no
    child; a register emptied after admission is a flag on the decomposer's plan, never a hold on issued work.
    Canon v4.1 §11.5 ("the split … and its register — changes only by a re-admission"): the emptying write is itself
    refused naming CHECK-4, the admitted register stands, and the issued child works on, never held."""
    engine.assign_task(TaskId("root"), spec("root", "rc"), AgentId("agent"))
    engine.wait_idle()
    split = ([(TaskId("ch"), spec("child", "cc"), AgentId("agent"))], [CriterionMapping("rc", TaskId("ch"))])
    with pytest.raises(AdmissionRefused, match="CHECK-4"):
        engine.decompose_task(TaskId("root"), *split)          # NO ACCEPTED_RISKS authored with the split
    assert engine.graph.get_task(TaskId("ch")) is None
    engine.decompose_task(TaskId("root"), *split, register=REGISTER_SPLIT)
    with pytest.raises(AdmissionRefused, match="CHECK-4"):     # its decomposer empties it afterwards: refused
        engine.admit_register(TaskId("root"), Register(), AgentId("agent"))
    engine.wait_idle()
    assert engine.graph.get_task(TaskId("root")).register.items == REGISTER_SPLIT.items   # nothing changed
    r = engine.send_signal_sync(SignalData(signal=Signal.ACCEPT, task_id=TaskId("ch"), source=AgentId("agent")))
    assert not r.rejected and engine.graph.get_state(TaskId("ch")) == State.EXECUTING
    complete = T._accepted_risks_from([{**REGISTER[0], "item": "a host restarts mid-run"}, REGISTER[1]])
    engine.admit_register(TaskId("root"), Register(complete), AgentId("agent"))   # … his complete one is admitted
    assert engine.graph.get_task(TaskId("root")).register.items == complete
    assert engine.graph.get_state(TaskId("ch")) == State.EXECUTING


def test_an_internal_node_completes_on_its_own_self_check(engine):
    """§10.3, read literally: an internal node self-verifies and is NOT independently validated.

    "DELIVER carries `self_validation`" … "the guarantee for the whole internal decomposition is
    carried by the validation of the agent's public result" … the agent "stakes all internal work on
    one public validation". So there is no second party owed a verdict on an internal node — its
    issuer IS its executor's scope, by the definition that makes it internal.

    Measured 2026-08-20: nothing relayed that self-check, so a subtree delegated to ONE role
    deadlocked — the delivery landed in 57 seconds and the graph stood still for half an hour. The
    field was in the report schema and in `SignalData`, and was dropped between them.

    The three conditions are tested together, because each alone would be a different rule:
    internal only, a DECIDED self-check only (⊥ is not a pass, §2.3), and never when independent
    validation is going to run anyway.
    """
    e = engine
    T.create_task(e, "par", {"description": "parent", "criteria": [criterion("g", "G")],
                             "accepted_risks": REGISTER},
                  assignee="exec-1")
    T.decompose(e, "par", [{"task_id": "kid", "spec": {"description": "internal child",
                             "criteria": [criterion("k", "K")]}, "assignee": "exec-1", "covers": ["g"]}], accepted_risks=REGISTER)          # same Del as its parent → INTERNAL
    T.signal(e, "kid", "ACCEPT", "exec-1")
    T.signal(e, "kid", "DELIVER", "exec-1", result="built it")

    said = []
    reports._settle_internal(e, TaskId("kid"), None, said.append)     # no self-check → ⊥, not a pass
    e.wait_idle()
    assert e.graph.get_state(TaskId("kid")).name == "VALIDATING"

    # THE WORD, not any text. This passed prose here and the node closed, because the caller mapped
    # every non-empty string to PASS — which also turned an executor's own `FAIL` into a pass
    # (probed 2026-09-05). §11.2 puts a VERDICT in this field; prose that decides nothing is ⊥ and
    # leaves the node exactly where an empty field leaves it. See
    # `test_the_self_check_is_read_not_counted.py` for the reading itself.
    reports._settle_internal(e, TaskId("kid"), Verdict.PASS, said.append)
    e.wait_idle()
    assert e.graph.get_state(TaskId("kid")).name == "DONE"            # …the self-check settles it
    assert any("§10.3" in m for m in said)          # v4.1 carries no "D6" label; §10.3 is the internal node

    # …and the PUBLIC node above it is untouched: that is where the independent verdict is owed.
    T.signal(e, "par", "ACCEPT", "exec-1")
    T.signal(e, "par", "DELIVER", "exec-1", result="integrated")
    reports._settle_internal(e, TaskId("par"), Verdict.PASS, said.append)
    e.wait_idle()
    assert e.graph.get_state(TaskId("par")).name == "VALIDATING"      # a seam is never self-signed
