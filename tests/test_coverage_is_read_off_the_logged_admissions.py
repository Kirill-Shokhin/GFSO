"""Coverage is the split's (§2.4): a remap is a re-admission (§11.5), revises no child, and every reader of "the
coverage changed" reads the logged admissions — not a child's ASSIGN, which a remap no longer makes.

Each test names the reader it holds: R′'s consumption legs (§12.14), the refuted-coverage gate on a parent's
re-delivery, the rebuild's round, the machine issuer's remap with a revision."""
from datetime import datetime, timedelta

import pytest

from gfso.core.types import AgentId, CriterionMapping, Signal, SignalData, State, TaskId
from gfso.decompose import decompose_into, refine
from gfso.issuer import _revise_child
from tests.support import criterion, make_engine, reviewer_passes, spec, REGISTER_SPLIT
from tests.test_decompose_loop import FakeLLM, _eng, _init_patch


@pytest.fixture
def engine():
    e = make_engine(llm=None, check_interval=10_000)
    e.start()
    yield e
    e.stop()


def _send(e, *signals):
    for sd in signals:
        e.send_signal(sd)
        e.wait_idle()


def _pass(e, tid):
    _send(e, SignalData(signal=Signal.ACCEPT, task_id=TaskId(tid), source=AgentId("w")),
          SignalData(signal=Signal.DELIVER, task_id=TaskId(tid), source=AgentId("w"), result=f"{tid} done"))
    reviewer_passes(e, TaskId(tid))
    _send(e, SignalData(signal=Signal.PASS, task_id=TaskId(tid), source=AgentId("pm")))
    assert e.graph.get_state(TaskId(tid)) == State.DONE


def _co_covered(e):
    """root(rc) split into ch and co, both covering rc from the first admission; ch passed."""
    e.assign_task(TaskId("root"), spec("root goal", "rc"), AgentId("pm"))
    e.wait_idle()
    e.decompose_task(TaskId("root"), [(TaskId("ch"), spec("child", "cc"), AgentId("w")),
                                      (TaskId("co"), spec("co-cover", "oc"), AgentId("w"))],
                     criterion_mappings=[CriterionMapping("rc", TaskId("ch")), CriterionMapping("rc", TaskId("co"))],
                     register=REGISTER_SPLIT)
    e.wait_idle()
    _pass(e, "ch")


def test_a_node_a_re_admission_mapped_to_nothing_stays_consumed_when_mapped_back(engine):
    """"Mapped to no criterion of the parent's current version" consumes, and once logged it stands (§12.14): a later
    remap does not give the node back — read as the standing mappings, it did (critic r17)."""
    _co_covered(engine)
    engine.decompose_task(TaskId("root"), [], criterion_mappings=[CriterionMapping("rc", TaskId("co"))])
    engine.wait_idle()
    engine.map_criterion(TaskId("root"), {"ch": ["rc"]})
    assert {(m.criterion_name, str(m.child_id)) for m in engine.graph.get_task(TaskId("root")).criterion_mappings} \
        >= {("rc", "ch")}
    with pytest.raises(ValueError):
        engine.reopen(TaskId("ch"), AgentId("pm"))


def test_a_co_covering_siblings_revision_consumes_nothing(engine):
    """Covered around is read off the admissions: a sibling co-covering from the first admission whose CONTRACT is
    revised is no replan (§12.14) — the ASSIGN proxy, run beside the logged admissions, called it one (critic r17)."""
    _co_covered(engine)
    engine._revise(TaskId("co"), spec("co-cover, restated", "oc", "oc2"), AgentId("pm"))
    engine.wait_idle()
    engine.reopen(TaskId("ch"), AgentId("pm"))
    assert engine.graph.get_state(TaskId("ch")) == State.OFFERED


def test_a_refuted_criterion_remapped_onto_a_finished_child_is_a_repair(engine):
    """After a parent's FAIL over passing children, a re-admission that changes the refuted criterion's coverage is the
    decomposition's repair (§11.5) — with no child's ASSIGN to mark it, the gate called it "untouched" and refused the
    re-delivery."""
    engine.assign_task(TaskId("root"), spec("root goal", "rc", "rd"), AgentId("pm"))
    engine.wait_idle()
    engine.decompose_task(TaskId("root"), [(TaskId("ch"), spec("child", "cc"), AgentId("w")),
                                           (TaskId("co"), spec("other", "oc"), AgentId("w"))],
                          criterion_mappings=[CriterionMapping("rc", TaskId("ch")), CriterionMapping("rd", TaskId("co"))],
                          register=REGISTER_SPLIT)
    engine.wait_idle()
    _pass(engine, "ch")
    _pass(engine, "co")
    _send(engine, SignalData(signal=Signal.ACCEPT, task_id=TaskId("root"), source=AgentId("pm")),
          SignalData(signal=Signal.DELIVER, task_id=TaskId("root"), source=AgentId("pm"), result="agg"))
    engine.record_exec_verdict(TaskId("root"), "FAIL", ["rc"], "validate_result")
    _send(engine, SignalData(signal=Signal.FAIL, task_id=TaskId("root"), source=AgentId("pm"), failed_criteria=("rc",)))
    assert engine.graph.get_state(TaskId("root")) == State.REWORKING
    _send(engine, SignalData(signal=Signal.DELIVER, task_id=TaskId("root"), source=AgentId("pm"), result="agg-v2"))
    assert engine.graph.get_state(TaskId("root")) == State.REWORKING          # unrepaired: refused, as before
    engine.map_criterion(TaskId("root"), {"co": ["rc"]})
    _send(engine, SignalData(signal=Signal.DELIVER, task_id=TaskId("root"), source=AgentId("pm"), result="agg-v3"))
    assert engine.graph.get_state(TaskId("root")) == State.VALIDATING


def test_a_rebuild_round_that_only_remaps_is_admitted():
    """A refine whose fold only remaps changes the split, so it is its re-admission: the mapping lands and the child
    keeps its work — no child having changed, the round was dropped in silence (critic r17)."""
    res = decompose_into(_eng(), "task", root_id="root", llm=FakeLLM(texts=["holes1"], specs=[_init_patch()]))
    e = res.engine
    signals_b = len(e.audit_log(TaskId("root.b")))
    refine(e, root_id="root", llm=FakeLLM(texts=["b covers A too"],
                                         specs=[{"add_mappings": [{"criterion": "rc1", "child_id": "b"}]}]))
    assert ("rc1", "root.b") in {(m.criterion_name, str(m.child_id))
                                 for m in e.graph.get_task(TaskId("root")).criterion_mappings}
    assert len(e.audit_log(TaskId("root.b"))) == signals_b                    # no child revised


def test_a_remap_with_a_refused_revision_makes_neither(engine):
    """The machine issuer's `revise_child` with `covers` is two acts — the split's re-admission and the child's
    revision — so every refusal of both is read before either writes: a revision refused after the remap left the
    coverage moved and the contract as it was (critic r17)."""
    engine.assign_task(TaskId("root"), spec("root goal", "rc", "rd"), AgentId("pm"))
    engine.wait_idle()
    engine.decompose_task(TaskId("root"), [(TaskId("ch"), spec("child", "cc"), AgentId("w")),
                                           (TaskId("co"), spec("other", "oc"), AgentId("w"))],
                          criterion_mappings=[CriterionMapping("rc", TaskId("ch")), CriterionMapping("rd", TaskId("co"))],
                          register=REGISTER_SPLIT)
    engine.wait_idle()
    before = set(engine.graph.get_task(TaskId("root")).criterion_mappings)
    root = engine.graph.get_task(TaskId("root"))
    # a criterion with no procedure: the revision pins nothing, which the revision refuses (A1)
    ok, why = _revise_child(engine, root, "pm", {"child_id": "ch", "covers": ["rd"],
                                                 "criteria": [{"name": "cc", "description": "cc description"},
                                                              {"name": "new", "description": "unpinned"}]},
                            "", ())
    assert not ok and "refused" in why
    assert set(engine.graph.get_task(TaskId("root")).criterion_mappings) == before
    assert engine.graph.get_task(TaskId("ch")).spec == spec("child", "cc")


def test_a_remap_whose_revision_lapsed_with_its_deadline_makes_neither(engine):
    """The dry run asks the revision the move will make — no deadline typed, the child's own kept — so a child whose
    deadline has passed, under a parent past its own, is refused before the remap writes (critic C1: the dry run sent a
    live deadline of its own, approved, and the remap landed beside a refused revision)."""
    engine.assign_task(TaskId("root"), spec("root", "r1", "r2"), AgentId("pm"))
    engine.wait_idle()
    engine.decompose_task(TaskId("root"), [(TaskId("a"), spec("a", "ca"), AgentId("w")),
                                           (TaskId("b"), spec("b", "cb"), AgentId("w"))],
                          criterion_mappings=[CriterionMapping("r1", TaskId("a")), CriterionMapping("r2", TaskId("b"))],
                          register=REGISTER_SPLIT)
    engine.wait_idle()
    for tid in ("root", "a"):
        t = engine.graph.get_task(TaskId(tid))
        t.deadline = datetime.now() - timedelta(minutes=5)
        engine.graph.save_task(t)
        _send(engine, SignalData(signal=Signal.TIMEOUT, task_id=TaskId(tid)))
    before = set(engine.graph.get_task(TaskId("root")).criterion_mappings)
    ok, why = _revise_child(engine, engine.graph.get_task(TaskId("root")), "pm",
                            {"child_id": "a", "covers": ["r2"], "criteria": [criterion("ca"), criterion("ca2")]}, "", ())
    assert not ok and "nothing of this move was made" in why
    assert set(engine.graph.get_task(TaskId("root")).criterion_mappings) == before
    assert [c.name for c in engine.graph.get_task(TaskId("a")).spec.criteria] == ["ca"]
