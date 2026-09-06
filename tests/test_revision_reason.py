"""§24.5 — causal typing of revisions in the packet.

q_T's canon numerator includes «criteria изменены по дефекту спеки»; q_Del counts only
re-ASSIGN(capability_mismatch). Both members require the revision REASON typed on the
re-ASSIGN. Untyped revisions keep each metric's documented bias: q_T under-approximates
(challenges only), q_Del over-approximates (every untyped Del change counts).
"""
import pytest

from gfso.adapters.storage.sqlite import SqliteStorage
from gfso.core.types import (
    TaskId, AgentId, RevisionReason, SignalData, Signal,
)
from gfso.core.graph.metrics import q_T, q_Del
from tests.support import make_engine, spec
from gfso import tools as T
from gfso.engine.validation import ValidationError


@pytest.fixture
def engine():
    e = make_engine(check_interval=10_000)
    e.start()
    yield e
    e.stop()


def test_revision_from_validating_is_admitted_and_voids_the_delivery(engine):
    """§14.3 lists ASSIGN→OFFERED in VALIDATING's admissible set, and §6.3 prices it: the issuer may
    revise with the delivery in hand, "at the price of a logged event, a voided delivery and a fresh
    consent and re-delivery". The engine used to REFUSE the edge over measured churn (BCB/120) — an
    argument about what an agent does under a rule, not about whose rule it is.

    What must hold instead is the PRICE: the recorded PASS of the pre-revision delivery is voided, so
    the node cannot complete on a verdict about a contract it no longer carries (§14.5 self-PASS
    gate). A recorded FAIL is NOT voided — it opens no gate and carries the criteria snapshot the
    re-delivery disposition reads."""
    engine.assign_task(TaskId("v1"), spec("goal", "c1", risks=False), AgentId("boss"))
    engine.send_signal_sync(SignalData(signal=Signal.ACCEPT, task_id=TaskId("v1"), source=AgentId("boss")))
    engine.send_signal_sync(SignalData(signal=Signal.DELIVER, task_id=TaskId("v1"),
                                       source=AgentId("boss"), result="done"))
    engine.wait_idle()
    assert engine.get_state(TaskId("v1")).name == "VALIDATING"
    engine.record_exec_verdict(TaskId("v1"), "PASS", [], "val-1")

    engine.revise(TaskId("v1"), spec("goal", "c1_changed", risks=False), AgentId("boss"))
    engine.wait_idle()
    assert engine.get_state(TaskId("v1")).name == "OFFERED"          # re-consent, §14.4 Inv-1
    assert engine.get_task(TaskId("v1")).spec.criteria[0].name == "c1_changed"
    rec = engine.get_exec_verdict(TaskId("v1"))
    assert rec["verdict"] == "VOID" and rec["superseded_verdict"] == "PASS"

    # a FAIL record survives a revision intact (it gates nothing and its snapshot is load-bearing)
    engine.assign_task(TaskId("v2"), spec("goal", "c1", risks=False), AgentId("boss"))
    engine.send_signal_sync(SignalData(signal=Signal.ACCEPT, task_id=TaskId("v2"), source=AgentId("boss")))
    engine.send_signal_sync(SignalData(signal=Signal.DELIVER, task_id=TaskId("v2"),
                                       source=AgentId("boss"), result="done"))
    engine.wait_idle()
    engine.record_exec_verdict(TaskId("v2"), "FAIL", ["c1"], "val-1")
    engine.revise(TaskId("v2"), spec("goal", "c1_changed", risks=False), AgentId("boss"))
    engine.wait_idle()
    assert engine.get_exec_verdict(TaskId("v2"))["verdict"] == "FAIL"


def test_spec_defect_criteria_change_counts_in_qt(engine):
    engine.assign_task(TaskId("t1"), spec("goal", "c1", risks=False), AgentId("boss"))
    engine.wait_idle()
    assert q_T(engine._graph) == 1.0
    engine.revise(TaskId("t1"), spec("goal", "c1_fixed", risks=False), AgentId("boss"),
                  reason=RevisionReason.SPEC_DEFECT)
    assert engine.get_task(TaskId("t1")).spec_defect_criteria_change
    assert q_T(engine._graph) == 0.0  # the one contract was defective


def test_scope_expansion_never_counts(engine):
    engine.assign_task(TaskId("t1"), spec("goal", "c1", risks=False), AgentId("boss"))
    engine.wait_idle()
    engine.revise(TaskId("t1"), spec("goal", "c1_wider", risks=False), AgentId("boss"),
                  reason=RevisionReason.SCOPE_EXPANSION)
    assert not engine.get_task(TaskId("t1")).spec_defect_criteria_change
    assert q_T(engine._graph) == 1.0  # sanctioned §13.1 — not a defect


def test_untyped_criteria_change_stays_uncounted(engine):
    """The documented q_T under-approximation, now confined to untyped acts."""
    engine.assign_task(TaskId("t1"), spec("goal", "c1", risks=False), AgentId("boss"))
    engine.wait_idle()
    engine.revise(TaskId("t1"), spec("goal", "c1_other", risks=False), AgentId("boss"))
    assert q_T(engine._graph) == 1.0


def test_qdel_counts_only_typed_capability_mismatch(engine):
    for tid in ("a", "b", "c"):
        engine.assign_task(TaskId(tid), spec("goal", "c1", risks=False), AgentId("boss"))
        engine.wait_idle()
    engine.reassign(TaskId("a"), AgentId("w1"), reason=RevisionReason.CAPABILITY_MISMATCH)
    engine.reassign(TaskId("b"), AgentId("w2"), reason=RevisionReason.OTHER)  # handoff — not a defect
    assert q_Del(engine._graph) == pytest.approx(1 - 1 / 3)  # only the mismatch counts


def test_untyped_del_change_keeps_overapproximation(engine):
    """An untyped Del change still counts — the metric never silently improves by omission."""
    engine.assign_task(TaskId("a"), spec("goal", "c1", risks=False), AgentId("boss"))
    engine.wait_idle()
    engine.reassign(TaskId("a"), AgentId("w1"))
    assert q_Del(engine._graph) == 0.0


def test_reason_persists_sqlite(tmp_path):
    st = SqliteStorage(str(tmp_path / "rr.db"))
    e = make_engine(st, check_interval=10_000)
    e.start()
    try:
        e.assign_task(TaskId("p1"), spec("goal", "c1", risks=False), AgentId("boss"))
        e.wait_idle()
        e.revise(TaskId("p1"), spec("goal", "cx", risks=False), AgentId("boss"), reason=RevisionReason.SPEC_DEFECT)
        e.reassign(TaskId("p1"), AgentId("w"), reason=RevisionReason.CAPABILITY_MISMATCH)
    finally:
        e.stop()
    st2 = SqliteStorage(str(tmp_path / "rr.db"))
    t = st2.get_task(TaskId("p1"))
    assert t.spec_defect_criteria_change and t.reassign_reason_typed and t.reassign_capability_mismatch
    st2.close()


def test_transport_reason_string_mapping(engine):
    T.create_task(engine, "x1", {"description": "g", "criteria": [{"name": "c", "description": "d"}]},
                  assignee="boss")
    engine.wait_idle()
    T.reassign(engine, "x1", "w9", reason="capability_mismatch")
    assert engine.get_task(TaskId("x1")).reassign_capability_mismatch
    with pytest.raises(ValueError, match="unknown revision reason"):
        T.reassign(engine, "x1", "w10", reason="because")


def test_a_verdict_landing_after_a_revision_does_not_open_the_seam(engine):
    """The race the admitted edge opens: a validator already running on the pending delivery lands
    its PASS *after* the issuer revised the contract. Neither counter moves on a revision — iteration
    is the rework loop, reopens is R′ — so the generation stamp alone would let that verdict satisfy
    the verifier ≠ executor gate for a contract it never read. The record's own criteria snapshot is
    what settles it."""
    A = AgentId("solo")
    engine.assign_task(TaskId("r1"), spec("goal", "c1", risks=False), A)
    engine.send_signal_sync(SignalData(signal=Signal.ACCEPT, task_id=TaskId("r1"), source=A))
    engine.send_signal_sync(SignalData(signal=Signal.DELIVER, task_id=TaskId("r1"), source=A, result="x"))
    engine.wait_idle()
    generation = engine.generation_of(TaskId("r1"))          # the validator starts on THIS delivery
    engine.revise(TaskId("r1"), spec("goal", "c1_changed", risks=False), A)       # contract changes under it
    engine.wait_idle()
    engine.record_exec_verdict(TaskId("r1"), "PASS", [], "val-1", generation=generation)  # lands late

    # re-earn the delivery under the NEW contract, then try to self-PASS on that verdict
    engine.send_signal_sync(SignalData(signal=Signal.ACCEPT, task_id=TaskId("r1"), source=A))
    engine.send_signal_sync(SignalData(signal=Signal.DELIVER, task_id=TaskId("r1"), source=A, result="x2"))
    engine.wait_idle()
    entry = engine.send_signal_sync(SignalData(signal=Signal.PASS, task_id=TaskId("r1"), source=A))
    engine.wait_idle()
    assert entry is not None and entry.rejected
    assert engine.get_state(TaskId("r1")).name == "VALIDATING"
