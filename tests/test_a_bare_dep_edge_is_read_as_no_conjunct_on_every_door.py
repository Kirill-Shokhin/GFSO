"""A bare Dep edge (`dep__x` with no check) is no conjunct of its consumer (`Spec.conjuncts`, §2.7) on every door of the
verdict: the issuer is not told FAIL is refused because the edge is listed first, and a FAIL record naming the edge — from
a door without entries, or from before the edge left V — neither stores it nor blocks a correct repair (critic over
657ea68)."""
from gfso.core.types import AgentId, Criteria, CriterionMapping, Signal, SignalData, Spec, State, TaskId
from tests.support import REGISTER_ITEMS, REGISTER_SPLIT, make_engine, pinned, reviewer_passes
from tests.test_fm1_repair import _review

T_, A_ = TaskId, AgentId


def _go(e, *sds):
    for sd in sds:
        e.send_signal(sd)
        e.wait_idle()


def _consumer_validating():
    e = make_engine(llm=None, check_interval=10_000)
    e.start()
    e.assign_task(T_("root"), Spec("root goal", (Criteria("g", "g", check=pinned("g")),), accepted_risks=REGISTER_ITEMS), A_("pm"))
    e.wait_idle()
    e.decompose_task(T_("root"), [(T_("x"), Spec("producer", (Criteria("px", "px", check=pinned("px")),)), A_("w")),
                                  (T_("p"), Spec("consumer", (Criteria("dep__x", "p reads x", depends_on=T_("x")),
                                                               Criteria("rc", "rc", check=pinned("rc"))),
                                                 accepted_risks=REGISTER_ITEMS), A_("pm"))],
                     criterion_mappings=[CriterionMapping("g", T_("x")), CriterionMapping("g", T_("p"))],
                     register=REGISTER_SPLIT)
    e.wait_idle()
    _review(e)
    e.decompose_task(T_("p"), [(T_("ch"), Spec("child", (Criteria("cc", "cc", check=pinned("cc")),)), A_("w"))],
                     criterion_mappings=[CriterionMapping("rc", T_("ch")), CriterionMapping("dep__x", T_("ch"))],
                     register=REGISTER_SPLIT)
    e.wait_idle()
    _review(e, node="p")
    for n in ("x", "ch"):
        _go(e, SignalData(signal=Signal.ACCEPT, task_id=T_(n), source=A_("w")),
            SignalData(signal=Signal.DELIVER, task_id=T_(n), source=A_("w"), result="r"))
        reviewer_passes(e, T_(n))
        _go(e, SignalData(signal=Signal.PASS, task_id=T_(n), source=A_("pm")))
    _go(e, SignalData(signal=Signal.ACCEPT, task_id=T_("p"), source=A_("pm")),
        SignalData(signal=Signal.DELIVER, task_id=T_("p"), source=A_("pm"), result="agg"))
    assert e.graph.get_state(T_("p")) == State.VALIDATING
    return e


def test_the_issuer_is_not_told_fail_is_refused_when_the_edge_is_listed_first():
    e = _consumer_validating()
    assert e.refusal_for(T_("p"), Signal.FAIL) is None
    e.stop()


def test_a_fail_record_naming_the_edge_stores_only_the_conjuncts():
    e = _consumer_validating()
    rec = e.record_exec_verdict(T_("p"), "FAIL", ["rc", "dep__x"], "rev")
    assert list(rec.get("failed_criteria") or e.get_exec_verdict(T_("p"))["failed_criteria"]) == ["rc"]
    e.stop()
