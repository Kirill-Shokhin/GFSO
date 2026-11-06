"""A node whose forecast its log refuted is re-decomposed by its issuer, the decomposer of the split it is a part of.

κ is the issuer's forecast in the packet — its deadline and rework bound (§12.15 Φ3) — and only a logged event refutes
it: the bound spent without a PASS, ESCALATED. Its issuer then re-ASSIGNs with a larger bound, cancels, or re-makes
the split he holds in ONE re-admission (§11.5): the escalated child leaves, the children he names stand in for it, each
due before the parent (§4.5 item 6). There is no third party: measured (c_compiler × Haiku 5.5, the system's own
plan), the issuer's word ordered the system planner to split the node, and six one-part splits came back ($0.24).
A root has no split above it: its issuer re-ASSIGNs or cancels.

CONTROLS: take `redecompose` out of the escalation's moves and the offer and landing tests go red; drop the
root filter in `moves_for` and the root test goes red; drop the user's-plan filter and the user's-plan test goes red.
"""
from __future__ import annotations

from gfso import issuer as I, tools as T
from gfso.core.types import DoneReason, Mode, State, TaskId
from tests.support import criterion
from tests.test_the_mode_decides_who_holds_what import _admit, _engine, _kid


def _escalated(mode=Mode.AUTO):
    """root: part (covers g) → other (covers h, reads part); part's rework bound spent without a PASS."""
    e = _engine(mode)
    T.TOOLS["create_task"](e, "root", {"description": "the compiler", "criteria": [
        criterion("g", "G holds"), criterion("h", "H holds")]})
    _admit(e, "root", _kid("root.part", ["g"], criterion("k", "K holds")),
           _kid("root.other", ["h"], criterion("o", "O holds")))
    T.TOOLS["add_dependency"](e, "root.part", "root.other")
    e.wait_idle()
    t = e.graph.get_task(TaskId("root.part"))
    t.state, t.done_reason = State.ESCALATED, DoneReason.FAIL
    e.graph.save_task(t)
    e.wait_idle()
    return e, t


def test_an_escalated_childs_issuer_is_offered_the_re_decomposition_of_his_split():
    e, part = _escalated()
    assert I.moves_for(e, part, "escalation") == ("reassign", "redecompose", "cancel")
    ask = I.QUESTIONS["escalation"]["ask"]
    assert all(f"`{m}`" in ask for m in ("reassign", "redecompose", "cancel")), ask
    e.stop()


def test_the_re_decomposition_replaces_the_escalated_child_in_one_admission():
    e, part = _escalated()
    issuer = str(e.graph.issuer_of(part.id))
    assert issuer == str(e.graph.get_task(TaskId("root")).assignee), "the escalation's issuer is the parent's decomposer"
    ok, why = I.apply_move(e, part.id, "escalation", issuer, {"move": "redecompose", "justification": "too big", "children": [
        {"name": "lexer", "covers": ["g"], "criteria": [criterion("kl", "it lexes")]},
        {"name": "parser", "covers": ["g"], "reads": ["lexer"], "replaces": ["root.part"],
         "criteria": [criterion("kp", "it parses")]}]})
    e.wait_idle()
    assert ok, why
    assert e.graph.get_state(part.id) in (State.CANCELLING, State.ABANDONED)
    root = e.graph.get_task(TaskId("root"))
    live = {str(k.id): k for k in e.graph.get_active_children(root.id) if k.state != State.CANCELLING}
    assert set(live) == {"root.lexer", "root.parser", "root.other"}, live
    assert {str(x.from_id) for x in e.graph.declared_edges(TaskId("root.other"))} == {"root.parser"}
    assert {str(x.from_id) for x in e.graph.declared_edges(TaskId("root.parser"))} == {"root.lexer"}
    assert all(k.deadline < root.deadline for k in live.values() if root.deadline), "a child due after its parent"
    e.stop()


def test_a_re_decomposition_names_who_makes_what_the_consumers_read():
    """root.other reads root.part: replacements naming no `replaces` would leave it on a dropped producer to starve."""
    e, part = _escalated()
    issuer = str(e.graph.issuer_of(part.id))
    ok, why = I.apply_move(e, part.id, "escalation", issuer, {"move": "redecompose", "justification": "too big", "children": [
        {"name": "lexer", "covers": ["g"], "criteria": [criterion("kl", "it lexes")]},
        {"name": "parser", "covers": ["g"], "reads": ["lexer"], "criteria": [criterion("kp", "it parses")]}]})
    e.wait_idle()
    assert not ok and "root.other" in why and "replaces" in why, why
    assert e.graph.get_state(part.id) == State.ESCALATED, "a refused act changes nothing"
    e.stop()


def test_a_roots_escalation_has_no_split_above_it_to_re_make():
    e, _ = _escalated()
    root = e.graph.get_task(TaskId("root"))
    assert "redecompose" not in I.moves_for(e, root, "escalation")
    held = _engine(Mode.SOLO)
    T.TOOLS["create_task"](held, "root", {"description": "the goal", "criteria": [criterion("g", "G holds")]})
    assert I.moves_for(held, held.graph.get_task(TaskId("root")), "escalation") == ("reassign", "cancel")
    e.stop()
    held.stop()


def test_a_plan_the_user_gave_is_not_re_split_at_an_escalation():
    e, part = _escalated()
    e.give_users_plan("root")
    assert "redecompose" not in I.moves_for(e, part, "escalation")
    e.stop()
