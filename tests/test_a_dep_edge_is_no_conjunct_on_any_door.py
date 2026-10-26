"""A Dep edge is no conjunct of its consumer on any door of the verdict (§2.7): the issuer is not told FAIL is refused
for it, and a FAIL record an older engine's door wrote naming the edge's old entry (`dep__x`, kept among the criteria
then) blocks no correct repair — the name was no criterion of the contract the FAIL read, so nothing was dropped
(critic over 657ea68)."""
from gfso.core.types import AgentId, Criteria, CriterionMapping, DepEdge, Signal, SignalData, Spec, State, TaskId
from tests.support import REGISTER_ITEMS, REGISTER_SPLIT, make_engine, pinned, reviewer_passes
from gfso.engine.validation import _refuted_coverage_refusal
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
                                  (T_("p"), Spec("consumer", (Criteria("rc", "rc", check=pinned("rc")),),
                                                 accepted_risks=REGISTER_ITEMS), A_("pm"))],
                     criterion_mappings=[CriterionMapping("g", T_("x")), CriterionMapping("g", T_("p"))],
                     register=REGISTER_SPLIT, deps={"p": (DepEdge(T_("x"), T_("p"), glue="p reads x"),)})
    e.wait_idle()
    _review(e)
    e.decompose_task(T_("p"), [(T_("ch"), Spec("child", (Criteria("cc", "cc", check=pinned("cc")),)), A_("w"))],
                     criterion_mappings=[CriterionMapping("rc", T_("ch"))],
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


def test_the_issuer_is_not_told_fail_is_refused_for_the_edge():
    e = _consumer_validating()
    assert [c.name for c in e.graph.get_task(T_("p")).spec.criteria] == ["rc"]
    assert e.refusal_for(T_("p"), Signal.FAIL) is None
    e.stop()


def test_a_fail_record_naming_the_edges_old_entry_reads_as_no_criterion_dropped():
    e = _consumer_validating()
    rec = e.record_exec_verdict(T_("p"), "FAIL", ["rc", "dep__x"], "rev")
    _go(e, SignalData(signal=Signal.FAIL, task_id=T_("p"), source=A_("pm"), failed_criteria=("rc",)))
    why = _refuted_coverage_refusal(e.graph, e.graph.get_task(T_("p")), rec, e._audit) or ""
    assert "REMOVED" not in why and "dep__x" not in why, why
    e.stop()
