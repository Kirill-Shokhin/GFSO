"""A part the plan already rests on is repaired around, not revised (§12.14).

When the whole FAILs over passing parts (contact refutes the split), the issuer is asked to repair it. A part that
passed is consumed once its whole delivered over it — a reopen would reverse its downstream cone — so the engine
refuses to revise it. The issuer was told only "the covering child must carry what failed": every `revise_child`
was refused, three unproductive answers closed the node, and a run on the plan's own denial event ended NOT DONE
(critic r5, 2026-10-04). Its context now marks such a part SETTLED and its refusal names `add_child`.

CONTROL: drop the `_settled` check from `_revise_child`, or the mark from `_split_lines`, and these go red.
"""
from gfso import issuer as I
from gfso.core.types import AgentId, Criteria, CriterionMapping, Signal, SignalData, Spec, TaskId
from tests.support import REGISTER_SPLIT, REGISTER_ITEMS, instrument_passes, make_engine, pinned


def _send(e, sig, tid, src, **kw):
    e.send_signal(SignalData(signal=sig, task_id=TaskId(tid), source=AgentId(src), **kw))
    e.wait_idle()


def _whole_delivered_over_passed_parts():
    e = make_engine()
    e.start()
    e.assign_task(TaskId("root"), Spec("a parser", (Criteria("g", "parses", check=pinned("g")),),
                                       accepted_risks=REGISTER_ITEMS), AgentId("lead"))
    e.wait_idle()
    _send(e, Signal.ACCEPT, "root", "lead")
    e.decompose_task(TaskId("root"), [
        (TaskId("root.a"), Spec("part a", (Criteria("ga", "a", check=pinned("ga")),)), AgentId("w")),
        (TaskId("root.b"), Spec("part b", (Criteria("gb", "b", check=pinned("gb")),)), AgentId("w"))],
        criterion_mappings=[CriterionMapping("g", TaskId("root.a")), CriterionMapping("g", TaskId("root.b"))], register=REGISTER_SPLIT)
    e.wait_idle()
    for k in ("root.a", "root.b"):
        _send(e, Signal.ACCEPT, k, "w")
        _send(e, Signal.DELIVER, k, "w", result="done")
        instrument_passes(e, k, "validator")
        _send(e, Signal.PASS, k, "lead")
    _send(e, Signal.DELIVER, "root", "lead", result="the whole")   # the whole rests on its parts' passes
    return e


def test_a_settled_part_is_marked_in_the_issuers_context():
    e = _whole_delivered_over_passed_parts()
    lines = I._split_lines(e, e.graph.get_task(TaskId("root")))
    assert lines.count("SETTLED") == 2 and "add_child" in lines, lines
    e.stop()


def test_revising_a_settled_part_is_refused_with_the_move_that_repairs_around_it():
    e = _whole_delivered_over_passed_parts()
    ok, why = I._revise_child(e, e.graph.get_task(TaskId("root")), AgentId("lead"),
                              {"child_id": "root.a", "criteria": [{"name": "ga", "description": "a, stricter"}]},
                              "repair", None)
    assert ok is False and "add_child" in why and "§12.14" in why, why
    e.stop()


def test_a_new_child_under_a_settled_ones_name_takes_a_fresh_id():
    """"exists — revise it" and "settled — add one" must not point at each other on a reused name (critic r6)."""
    e = _whole_delivered_over_passed_parts()
    ok, why = I._add_child(e, e.graph.get_task(TaskId("root")), AgentId("lead"),
                           {"child": {"name": "a", "covers": ["g"], "criteria": [
                               {"name": "ga2", "description": "a, what the whole needed",
                                "check": [{"behaviour": "it holds", "command": "check ga2", "expect": "it holds"}]}]}},
                           "repair", None)
    assert ok, why
    assert e.graph.get_task(TaskId("root.a_2")) is not None
    e.stop()
