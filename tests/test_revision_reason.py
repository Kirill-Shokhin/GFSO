"""§16.5 — causal typing of revisions in the packet.

q_T's canon numerator includes «criteria изменены по дефекту спеки»; q_Del counts only
re-ASSIGN(capability_mismatch). Both members require the revision REASON typed on the
re-ASSIGN. Untyped revisions keep each metric's documented bias: q_T under-approximates
(challenges only), q_Del over-approximates (every untyped Del change counts).
"""
import pytest

from gfso.engine import Engine
from gfso.adapters.storage.memory import MemoryStorage
from gfso.adapters.storage.sqlite import SqliteStorage
from gfso.adapters.agents.human import HumanAgent
from gfso.core.types import (
    TaskId, AgentId, Spec, Criteria, RevisionReason, SignalData, Signal,
)
from gfso.core.graph.metrics import q_T, q_Del


def _spec(crit="c1"):
    return Spec(description="goal", criteria=(Criteria(crit, f"{crit} d"),))


@pytest.fixture
def engine():
    e = Engine(MemoryStorage(), HumanAgent(), llm=None, check_interval=10_000)
    e.start()
    yield e
    e.stop()


def test_revision_refused_while_validating(engine):
    """A node cannot be revised while it is VALIDATING — the contract cannot change under the validator
    (§6.4). Observed live (BCB/120): an agent reneglected the ROOT mid-validation, bouncing it out of
    VALIDATING three times and re-running the validator each time — pure churn. Enforced at the
    validation layer (the FSM table / TLA model is untouched)."""
    from gfso.engine.validation import ValidationError
    engine.assign_task(TaskId("v1"), _spec(), AgentId("boss"))
    engine.send_signal_sync(SignalData(signal=Signal.ACCEPT, task_id=TaskId("v1"), source=AgentId("boss")))
    engine.send_signal_sync(SignalData(signal=Signal.DELIVER, task_id=TaskId("v1"),
                                       source=AgentId("boss"), result="done"))
    engine.wait_idle()
    assert engine.get_state(TaskId("v1")).name == "VALIDATING"
    try:
        engine.revise(TaskId("v1"), _spec("c1_changed"), AgentId("boss"))
    except (ValidationError, Exception):
        pass
    # refused: still VALIDATING, contract unchanged (not bounced to REVIEW)
    assert engine.get_state(TaskId("v1")).name == "VALIDATING"
    assert engine.get_task(TaskId("v1")).spec.criteria[0].name == "c1"
    # after the verdict, revision is allowed again
    engine.send_signal_sync(SignalData(signal=Signal.FAIL, task_id=TaskId("v1"),
                                        source=AgentId("boss"), failed_criteria=("c1",)))
    engine.wait_idle()
    engine.revise(TaskId("v1"), _spec("c1_changed"), AgentId("boss"))
    assert engine.get_task(TaskId("v1")).spec.criteria[0].name == "c1_changed"


def test_spec_defect_criteria_change_counts_in_qt(engine):
    engine.assign_task(TaskId("t1"), _spec(), AgentId("boss"))
    engine.wait_idle()
    assert q_T(engine._graph) == 1.0
    engine.revise(TaskId("t1"), _spec("c1_fixed"), AgentId("boss"),
                  reason=RevisionReason.SPEC_DEFECT)
    assert engine.get_task(TaskId("t1")).spec_defect_criteria_change
    assert q_T(engine._graph) == 0.0  # the one contract was defective


def test_scope_expansion_never_counts(engine):
    engine.assign_task(TaskId("t1"), _spec(), AgentId("boss"))
    engine.wait_idle()
    engine.revise(TaskId("t1"), _spec("c1_wider"), AgentId("boss"),
                  reason=RevisionReason.SCOPE_EXPANSION)
    assert not engine.get_task(TaskId("t1")).spec_defect_criteria_change
    assert q_T(engine._graph) == 1.0  # sanctioned §5.1 — not a defect


def test_untyped_criteria_change_stays_uncounted(engine):
    """The documented q_T under-approximation, now confined to untyped acts."""
    engine.assign_task(TaskId("t1"), _spec(), AgentId("boss"))
    engine.wait_idle()
    engine.revise(TaskId("t1"), _spec("c1_other"), AgentId("boss"))
    assert q_T(engine._graph) == 1.0


def test_qdel_counts_only_typed_capability_mismatch(engine):
    for tid in ("a", "b", "c"):
        engine.assign_task(TaskId(tid), _spec(), AgentId("boss"))
        engine.wait_idle()
    engine.reassign(TaskId("a"), AgentId("w1"), reason=RevisionReason.CAPABILITY_MISMATCH)
    engine.reassign(TaskId("b"), AgentId("w2"), reason=RevisionReason.OTHER)  # handoff — not a defect
    assert q_Del(engine._graph) == pytest.approx(1 - 1 / 3)  # only the mismatch counts


def test_untyped_del_change_keeps_overapproximation(engine):
    """An untyped Del change still counts — the metric never silently improves by omission."""
    engine.assign_task(TaskId("a"), _spec(), AgentId("boss"))
    engine.wait_idle()
    engine.reassign(TaskId("a"), AgentId("w1"))
    assert q_Del(engine._graph) == 0.0


def test_reason_persists_sqlite(tmp_path):
    st = SqliteStorage(str(tmp_path / "rr.db"))
    e = Engine(st, HumanAgent(), llm=None, check_interval=10_000)
    e.start()
    try:
        e.assign_task(TaskId("p1"), _spec(), AgentId("boss"))
        e.wait_idle()
        e.revise(TaskId("p1"), _spec("cx"), AgentId("boss"), reason=RevisionReason.SPEC_DEFECT)
        e.reassign(TaskId("p1"), AgentId("w"), reason=RevisionReason.CAPABILITY_MISMATCH)
    finally:
        e.stop()
    st2 = SqliteStorage(str(tmp_path / "rr.db"))
    t = st2.get_task(TaskId("p1"))
    assert t.spec_defect_criteria_change and t.reassign_reason_typed and t.reassign_capability_mismatch
    st2.close()


def test_transport_reason_string_mapping(engine):
    from gfso import tools as T
    T.create_task(engine, "x1", {"description": "g", "criteria": [{"name": "c", "description": "d"}]},
                  assignee="boss")
    engine.wait_idle()
    T.reassign(engine, "x1", "w9", reason="capability_mismatch")
    assert engine.get_task(TaskId("x1")).reassign_capability_mismatch
    with pytest.raises(ValueError, match="unknown revision reason"):
        T.reassign(engine, "x1", "w10", reason="because")
