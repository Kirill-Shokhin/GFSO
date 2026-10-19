"""A re-admission is ONE act over its children, its drops and its register (§11.5), and a child it drops is out of the
plan at the drop (§12.6: "active unless ABANDONED or dropped by a re-admission").

Critic r6 over the corner-9 branch: the register written inside the admission ran the battery a second time with the
dropped child read back in (CANCELLING, so still "active"), refusing the re-decomposition after its split had changed —
and every later admission while the drop's cancellation ran; a build that changed only the register let the refusal
escape the authoring loop.
"""
from __future__ import annotations

import gfso.tools as T
from gfso.core.types import AcceptedRiskItem, Predictability, Register, State, TaskId, register_of
from gfso.decompose.build import build_graph_live
from tests.support import DENIAL_ENTRY, REGISTER, criterion, make_engine

_R2 = [{"item": "a slow mirror", "predictability": "STATISTICAL", "p": 0.05, "impact": "a retry",
        "justification": "seen once a year", "invalidation_condition": "twice in a month"}, DENIAL_ENTRY]


def _plan(*maps, register=REGISTER):
    kids = sorted({c for c, _ in maps})
    return {"name": "g", "root_criteria": [criterion("g1", "one"), criterion("g2", "two")],
            "subtasks": [{"id": k, "name": k, "description": f"part {k}", "criteria": [criterion(f"{k}_ok", k)]}
                         for k in kids],
            "mappings": [{"criterion": g, "child_id": c} for c, g in maps], "deps": [],
            "accepted_risks": register, "scope": []}


def _built():
    e = make_engine()
    e.start()
    build_graph_live(_plan(("a", "g1"), ("b", "g2")), "the goal", e, root_id="root", assignee="me")
    e.wait_idle()
    return e


def test_a_re_decomposition_that_drops_a_child_is_admitted_with_its_register():
    e = _built()
    _, _, problems = build_graph_live(_plan(("a", "g1"), ("a", "g2"), register=_R2), "the goal", e,
                                      root_id="root", assignee="me")
    e.wait_idle()
    assert not [p for p in problems if "refused" in p], problems
    assert e.graph.get_state(TaskId("root.b")) in (State.CANCELLING, State.ABANDONED)
    assert [str(k.id) for k in e.graph.get_active_children(TaskId("root"))] == ["root.a"]
    assert [n.item for n in register_of(e.graph.get_task(TaskId("root"))).items if not n.denial] == ["a slow mirror"]
    _, _, again = build_graph_live(_plan(("a", "g1"), ("a", "g2"), register=_R2), "the goal", e,
                                   root_id="root", assignee="me")
    assert not [p for p in again if "refused" in p], again
    e.stop()


def test_while_the_dropped_childs_cancellation_runs_the_next_admission_is_not_refused_for_it():
    e = _built()
    build_graph_live(_plan(("a", "g1"), ("a", "g2")), "the goal", e, root_id="root", assignee="me")
    e.wait_idle()
    assert e.graph.get_state(TaskId("root.b")) == State.CANCELLING, "its executor has not confirmed"
    out = T.create_task(e, "root.c", {"description": "another part", "criteria": [criterion("c_ok", "c")]},
                        assignee="me", parent_id="root", covers=["g2"])
    assert not (out or {}).get("error"), out
    e.stop()


def test_a_build_that_changes_only_the_register_answers_its_refusal_as_a_problem():
    e = _built()
    no_denial = [AcceptedRiskItem("a slow mirror", Predictability.STATISTICAL, "seen once a year", "twice in a month",
                                  0.05, "a retry").to_dict()]
    _, _, problems = build_graph_live(_plan(("a", "g1"), ("b", "g2"), register=no_denial), "the goal", e,
                                      root_id="root", assignee="me")
    assert [p for p in problems if "the admission refused" in p and "CHECK-4" in p], problems
    assert register_of(e.graph.get_task(TaskId("root"))) == Register(tuple(
        AcceptedRiskItem.of(n) for n in REGISTER)), "the standing register is kept"
    e.stop()


def test_a_round_that_names_a_dropped_child_again_is_refused_whole():
    """Critic r7 (P5): read as a new child, a dropped id passed the battery, its ASSIGN was refused mid-issue and the
    rest of the split went out with a clean-looking cache. Now the admission names it before the first ASSIGN."""
    e = _built()
    build_graph_live(_plan(("a", "g1"), ("a", "g2")), "the goal", e, root_id="root", assignee="me")
    e.wait_idle()
    _, _, problems = build_graph_live(_plan(("a", "g1"), ("b", "g2"), ("c", "g2")), "the goal", e,
                                      root_id="root", assignee="me")
    e.wait_idle()
    assert [p for p in problems if "b was dropped" in p and "has left this split" in p], problems
    assert e.graph.get_task(TaskId("root.c")) is None, "nothing of a refused admission is issued"
    e.stop()


def test_a_child_already_being_cancelled_is_dropped_by_the_next_re_admission():
    """§11.5: a re-admission drops "one already being cancelled as the abandoned node it becomes" — left out of the
    drops, it stood in the battery as an orphan only its executor's confirmation lifted (critic r7, P3)."""
    e = _built()
    T.signal(e, "root.b", "CANCEL", "me", reason="not wanted")
    e.wait_idle()
    _, _, problems = build_graph_live(_plan(("a", "g1"), ("a", "g2")), "the goal", e, root_id="root", assignee="me")
    assert not [p for p in problems if "refused" in p], problems
    assert [str(k.id) for k in e.graph.get_active_children(TaskId("root"))] == ["root.a"]
    e.stop()
