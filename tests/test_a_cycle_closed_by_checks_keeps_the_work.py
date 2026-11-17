"""A refuted order whose backward waits came from a child's own checks running its consumers keeps every piece of work.

Measured (AUTO c_compiler, every role Haiku 5.5, GB_c_compiler_tobsku412): `root.preproc`, 9 of 11 parts passed,
carried criteria whose pinned checks built and ran the whole compiler; its BLOCK named all 8 of them as needing the
parser and codegen of the parts reading it — a cycle (§15.5). The one repair, a reshape, cancelled it, and again
`root.decls` (6 parts, one criterion needing floating point). `split_off` is the re-decomposition that keeps the work:
the parent's split gains a sibling carrying exactly those criteria and their checks, after the consumers they run,
and the child is re-authored in place without them, its subtree kept (§2.7: the edge is the criterion's).

CONTROLS: return (True, "") from `_split_off` before acting and the first test goes red; read every discovered wait
as closable (`ns <= names` → `ns`) and the partial move is accepted; match names on `\\w` boundaries and the prefix
case is accepted.
"""
from __future__ import annotations

import pytest

from gfso import issuer as I, tools as T
from gfso.core.types import Mode, RevisionReason, State, TaskId
from tests.support import criterion
from tests.test_the_mode_decides_who_holds_what import _admit, _engine, _kid

_BLOCKED = ("The end-to-end pinned checks for macros-and-conditionals and include-resolution need the parser and "
            "codegen of root.b")


def _cycle(on_its_parent: bool = False, glue: str = _BLOCKED, own: bool = True):
    """root.a (its parts DONE) carries two whole-compiler checks; root.b reads a; contact confirmed a needs b."""
    e = _engine(Mode.AUTO)
    T.TOOLS["create_task"](e, "root", {"description": "the compiler", "criteria": [
        criterion("g", "G holds"), criterion("h", "H holds")]})
    _admit(e, "root", _kid("root.a", ["g"], *([criterion("macros", "it expands macros")] if own else []),
                           criterion("macros-and-conditionals", "the whole expands them"),
                           criterion("include-resolution", "the whole includes")),
           _kid("root.b", ["h"], criterion("kb", "it parses")))
    T.TOOLS["add_dependency"](e, "root.a", "root.b")
    _admit(e, "root.a", _kid("root.a.x", ["macros-and-conditionals", *(["macros"] if own else [])],
                                criterion("kx", "macros expand")),
           _kid("root.a.y", ["include-resolution"], criterion("ky", "includes resolve")))
    for tid in ("root.a.x", "root.a.y"):
        t = e.graph.get_task(TaskId(tid))
        t.state = State.DONE
        e.graph.save_task(t)
    e.add_dependency(TaskId("root.b"), TaskId("root.a"), discovered=True, glue=glue)
    e.add_dependency(TaskId("root.b"), TaskId("root.a.x"), discovered=True, glue="kx reads root.b's token table")
    if on_its_parent:   # a second BLOCK named its own parent: a wait no record from root.b's side closes
        e.add_dependency(TaskId("root"), TaskId("root.a"), discovered=True, glue="the whole")
    e.wait_idle()
    root = e.graph.get_task(TaskId("root"))
    assert e.dep_order_refuted(root.id) and e.dep_order_cycle_children(root.id) == [["root.a", "root.b"]]
    return e, root


def _move(**kw):
    return {"move": "split_off", "child_id": "root.a", "items": ["macros-and-conditionals", "include-resolution"],
            "child": {"name": "preproc_whole", "description": "the preprocessor as the whole compiler runs it"},
            "justification": "both build and run the whole compiler: they are checked after root.b", **kw}


def _discovered_into_a(e) -> set:
    return {(str(x.from_id), str(x.to_id)) for x in e.graph.dep_edges() if x.discovered and str(x.to_id) != "root"
            and str(x.to_id).startswith("root.a")}


def _state(e) -> tuple:
    a = e.graph.get_task(TaskId("root.a"))
    return (a.state, [c.name for c in a.spec.criteria], len(e.audit_log(TaskId("root.a"))), _discovered_into_a(e),
            {str(k.id): k.state for k in e.graph.subtree(None)}, len(e.graph.dep_edges()))


def _checks(t, names) -> dict:
    return {c.name: [p.to_dict() for p in c.check] for c in t.spec.criteria if c.name in names}


def test_a_child_whose_checks_ran_its_consumers_hands_them_to_a_sibling_and_keeps_its_passed_parts():
    e, root = _cycle()
    moved = ["macros-and-conditionals", "include-resolution"]
    was = _checks(e.graph.get_task(TaskId("root.a")), moved)
    assert "split_off" in I.moves_for(e, root, "repair")
    ask = I.QUESTIONS["repair"]["ask"]
    assert ask.index("split_off") < ask.index("reshape")
    # the issuer is SHOWN which criteria the BLOCK names: the refutation's line carries no reason
    assert ("root.a's BLOCK from root.b names these of its criteria as unable to pass before them: "
            "include-resolution, macros-and-conditionals") in I.what_contact_refuted(e, root.id)
    ok, why = I.apply_move(e, root.id, "repair", str(root.assignee), _move())
    e.wait_idle()
    assert ok, why
    a, sib = e.graph.get_task(TaskId("root.a")), e.graph.get_task(TaskId("root.preproc_whole"))
    assert [c.name for c in a.spec.criteria] == ["macros"]
    assert RevisionReason.SPEC_DEFECT.name in [x.revision_reason for x in e.audit_log(a.id)]
    # nothing leaves the plan: every moved criterion stands on the sibling with its very checks
    assert sib is not None and str(sib.parent_id) == "root" and _checks(sib, moved) == was
    assert {m.criterion_name for m in e.graph.get_task(root.id).criterion_mappings if str(m.child_id) == str(sib.id)} \
        == {"g"}
    assert {str(x.from_id) for x in e.graph.declared_edges(sib.id)} == {"root.a", "root.b"}
    assert not [x for x in e.graph.dep_edges() if str(x.from_id) == str(sib.id)]      # read by nobody: no cycle
    # …and no work is lost: the passed parts stand, nothing cancelled
    assert {str(k.id): k.state for k in e.graph.get_active_children(a.id)} == {
        "root.a.x": State.DONE, "root.a.y": State.DONE}
    assert not [t for t in e.graph.subtree(None) if t.state in (State.CANCELLING, State.ABANDONED)]
    assert _discovered_into_a(e) == {("root.b", "root.a.x")}       # a wait no moved criterion made stays open
    assert e.dep_order_refuted(root.id) is None
    assert any("moved to root.preproc_whole" in r["message"] and "checked after root.b" in r["message"]
               for r in e.pipeline_log())
    e.stop()


def test_a_child_whose_every_criterion_ran_its_consumers_is_given_its_own_unit_to_keep():
    """preproc's live shape: its BLOCK named all its criteria; it keeps its parts under a check of its own unit."""
    e, root = _cycle(own=False)
    ok, why = I.apply_move(e, root.id, "repair", str(root.assignee), _move())
    assert not ok and "give it in `criteria`" in why, why
    ok, why = I.apply_move(e, root.id, "repair", str(root.assignee),
                           _move(criteria=[criterion("expands-alone", "cc -E expands the pinned input")]))
    e.wait_idle()
    assert ok, why
    assert [c.name for c in e.graph.get_task(TaskId("root.a")).spec.criteria] == ["expands-alone"]
    assert e.graph.get_task(TaskId("root.preproc_whole")) is not None and e.dep_order_refuted(root.id) is None
    e.stop()


@pytest.mark.parametrize("answer, said", [
    (_move(child_id="root.c"), "not a child"),
    (_move(items=["g"]), "not criteria of root.a"),           # the root's own criterion is not the child's to move
    (_move(items=[]), "names none"),
    (_move(items=["macros"]), "take it out of `items` — its BLOCKs name include-resolution, macros-and-conditionals"),     # the real work, named by no BLOCK (nor inside a name)
    (_move(items=["macros-and-conditionals"]), "also names include-resolution"),   # half of what the wait names
    (_move(justification=""), "say why"),
    (_move(criteria=[criterion("macros", "again")]), "already root.a's"),
])
def test_a_split_off_that_cannot_hold_is_refused_and_changes_nothing(answer, said):
    e, root = _cycle()
    was = _state(e)
    ok, why = I.apply_move(e, root.id, "repair", str(root.assignee), answer)
    e.wait_idle()
    assert not ok and said in why, why
    assert _state(e) == was and e.graph.get_task(TaskId("root.preproc_whole")) is None
    e.stop()


def test_a_child_off_the_refuted_cycle_is_refused():
    e, root = _cycle()
    _admit(e, "root", _kid("root.c", ["g"], criterion("kc", "it links")))
    was = _state(e)
    ok, why = I.apply_move(e, root.id, "repair", str(root.assignee), _move(child_id="root.c"))
    assert not ok and "no refuted cycle" in why, why
    assert _state(e) == was
    e.stop()


def test_a_cycle_that_stands_without_the_waits_from_its_consumers_is_left_to_a_reshape():
    e, root = _cycle(on_its_parent=True)
    was = _state(e)
    ok, why = I.apply_move(e, root.id, "repair", str(root.assignee), _move())
    assert not ok and "`reshape`" in why, why
    assert _state(e) == was
    e.stop()


def test_a_child_blocked_on_its_consumers_again_after_an_answer_is_re_issued_in_place():
    """The live path: the BLOCK answered once (worked around), raised again on the same contract — held to, it refutes
    the order (§15.5). The move answers it: the child is OFFERED anew, the discovery closed, still counted."""
    e = _engine(Mode.AUTO)
    T.TOOLS["create_task"](e, "root", {"description": "c", "criteria": [criterion("g", "G"), criterion("h", "H")]})
    _admit(e, "root", _kid("root.a", ["g"], criterion("ka", "a"), criterion("c-whole", "w")),
           _kid("root.b", ["h"], criterion("kb", "b")))
    T.TOOLS["add_dependency"](e, "root.a", "root.b")
    a, issuer = e.graph.get_task(TaskId("root.a")), str(e.graph.issuer_of(TaskId("root.a")))
    T.signal(e, "root.a", "ACCEPT", str(a.assignee))
    T.signal(e, "root.a", "BLOCK", str(a.assignee), reason="c-whole runs b's parser", blocker_task_id="root.b")
    T.signal(e, "root.a", "RESOLVE_BLOCK", issuer, external=True, action="worked around")
    T.signal(e, "root.a", "BLOCK", str(a.assignee), reason="c-whole runs b's parser, still", blocker_task_id="root.b")
    e.wait_idle()
    root = e.graph.get_task(TaskId("root"))
    assert e.graph.get_state(a.id) == State.BLOCKED and e.dep_order_refuted(root.id)
    ok, why = I.apply_move(e, root.id, "repair", str(root.assignee), _move(items=["c-whole"]))
    e.wait_idle()
    assert ok, why
    assert e.graph.get_state(a.id) == State.OFFERED and e.dep_order_refuted(root.id) is None
    assert not _discovered_into_a(e)
    assert ("root.b", "root.a") in {(str(x.from_id), str(x.to_id)) for x in e.graph.dep_edges(closed=True)
                                    if x.discovered}
    e.stop()


def _block_twice(e, first: str, again: str):
    a, issuer = e.graph.get_task(TaskId("root.a")), str(e.graph.issuer_of(TaskId("root.a")))
    T.signal(e, "root.a", "ACCEPT", str(a.assignee))
    T.signal(e, "root.a", "BLOCK", str(a.assignee), reason=first, blocker_task_id="root.b")
    T.signal(e, "root.a", "RESOLVE_BLOCK", issuer, external=True, action="worked around")
    T.signal(e, "root.a", "BLOCK", str(a.assignee), reason=again, blocker_task_id="root.b")
    e.wait_idle()


def test_the_criteria_are_read_from_the_blocks_of_the_contract_in_force_round_after_round():
    """A repeated BLOCK reopens its record with the FIRST reason, so the move read the first: a later BLOCK naming the
    criteria, and a second round after a split_off, both read as naming none, and only a reshape was left (critic
    over 01ac2c7). Read from the BLOCKs of the version in force, both rounds move what was named."""
    e = _engine(Mode.AUTO)
    T.TOOLS["create_task"](e, "root", {"description": "c", "criteria": [criterion("g", "G"), criterion("h", "H")]})
    _admit(e, "root", _kid("root.a", ["g"], criterion("ka", "a"), criterion("c-whole", "w")),
           _kid("root.b", ["h"], criterion("kb", "b")))
    T.TOOLS["add_dependency"](e, "root.a", "root.b")
    _block_twice(e, "the pinned checks need root.b's parser", "c-whole cannot pass before root.b's parser")
    root = e.graph.get_task(TaskId("root"))
    assert "split_off" in I.moves_for(e, root, "repair")
    ok, why = I.apply_move(e, root.id, "repair", str(root.assignee), _move(items=["c-whole"], child={"name": "w1"}))
    e.wait_idle()
    assert ok, why
    _block_twice(e, "ka needs root.b's parser", "ka needs root.b's parser, still")       # round 2, on the new version
    root = e.graph.get_task(TaskId("root"))
    assert e.dep_order_refuted(root.id) and "split_off" in I.moves_for(e, root, "repair")
    assert "names these of its criteria as unable to pass before them: ka " in I.what_contact_refuted(e, root.id)
    ok, why = I.apply_move(e, root.id, "repair", str(root.assignee),
                           _move(items=["ka"], child={"name": "w2"}, criteria=[criterion("ka-alone", "a alone")]))
    e.wait_idle()
    assert ok, why
    assert [c.name for c in e.graph.get_task(TaskId("root.a")).spec.criteria] == ["ka-alone"]
    assert {str(k.id) for k in e.graph.get_active_children(root.id)} == {"root.a", "root.b", "root.w1", "root.w2"}
    assert e.dep_order_refuted(root.id) is None
    e.stop()


@pytest.mark.parametrize("second", [None, "w1", "c"])
def test_a_second_split_off_adds_a_new_sibling_and_overwrites_none(second):
    """Round 2 under the default name, the first sibling's, or another sibling's must not revise that node in place:
    its criteria would leave the plan (critic over 996b1f0)."""
    e = _engine(Mode.AUTO)
    T.TOOLS["create_task"](e, "root", {"description": "c", "criteria": [criterion("g", "G"), criterion("h", "H")]})
    _admit(e, "root", _kid("root.a", ["g"], criterion("ka", "a"), criterion("c-whole", "w")),
           _kid("root.b", ["h"], criterion("kb", "b")), _kid("root.c", ["h"], criterion("kc", "c")))
    T.TOOLS["add_dependency"](e, "root.a", "root.b")
    _block_twice(e, "c-whole needs root.b", "c-whole needs root.b, still")
    root = e.graph.get_task(TaskId("root"))
    first = {"name": second} if second == "w1" else {}
    assert I.apply_move(e, root.id, "repair", str(root.assignee), _move(items=["c-whole"], child=first))[0]
    e.wait_idle()
    was = {str(k.id): [c.name for c in k.spec.criteria] for k in e.graph.get_active_children(root.id)}
    _block_twice(e, "ka needs root.b", "ka needs root.b, still")
    root = e.graph.get_task(TaskId("root"))
    ok, why = I.apply_move(e, root.id, "repair", str(root.assignee),
                           _move(items=["ka"], child={"name": second} if second else {},
                                 criteria=[criterion("ka-alone", "a alone")]))
    e.wait_idle()
    assert ok, why
    now = {str(k.id): [c.name for c in k.spec.criteria] for k in e.graph.get_active_children(root.id)}
    assert {k: v for k, v in now.items() if k != "root.a"} == {**{k: v for k, v in was.items() if k != "root.a"},
                                                              **{k: ["ka"] for k in set(now) - set(was)}}
    assert len(set(now) - set(was)) == 1
    e.stop()


def test_no_split_off_is_offered_where_no_block_names_a_criterion():
    e, root = _cycle(glue="the pinned checks need the parser of root.b")
    assert e.dep_order_refuted(root.id) and "split_off" not in I.moves_for(e, root, "repair")
    e.stop()


def test_a_plan_the_user_handed_in_is_not_split_off():
    e, root = _cycle()
    e.give_users_plan(root.id)
    was = _state(e)
    assert "split_off" not in I.moves_for(e, root, "repair")
    assert not I.apply_move(e, root.id, "repair", str(root.assignee), _move())[0]
    assert _state(e) == was
    e.stop()


def test_no_split_off_is_offered_where_no_order_is_refuted():
    e, root = _cycle()
    assert I.apply_move(e, root.id, "repair", str(root.assignee), _move())[0]
    e.wait_idle()
    assert "split_off" not in I.moves_for(e, root, "repair")
    e.stop()
