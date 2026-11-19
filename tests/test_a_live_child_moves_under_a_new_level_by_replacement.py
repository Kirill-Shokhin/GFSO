"""A user puts a new level into a tree: a live child moves under a new intermediate node only by its issuer's acts —
dropped from its parent's split, and a copy issued under the intermediate that names it in `replaces` (§11.5, §15.1:
no act moves a parent). The copy carries on its work and its findings, its sibling consumers are handed to the copy in
the same act and re-offered, a consumer in another branch is named to its own issuer and left as it stands; a settled
child is moved by nothing, and another party's contract is not re-issued by this one.

CONTROLS: take `replaces` off `tools.decompose` and every test here goes red; make the hand-over of consumers return
nothing and the sibling test goes red; drop the issuer check and the other-party test goes red.
"""
from __future__ import annotations

import pytest

from gfso import tools as T
from gfso.core.types import State, TaskId
from tests.support import criterion
from tests.test_a_refuted_order_is_re_split_by_its_decomposer import _deps, _found
from tests.test_the_mode_decides_who_holds_what import _RISK, _admit, _engine, _kid


@pytest.fixture
def tree():
    """root: k1 covers g; k2 covers h; k3, a check of its own reading k2, covers h; b covers g, and b.x — another
    branch — reads k2. An edge alone is no packet field (§2.7): only k3's check makes its contract change with the move."""
    e = _engine()
    T.TOOLS["create_task"](e, "root", {"description": "the goal", "criteria": [criterion("g", "G holds"),
                                                                             criterion("h", "H holds")]})
    _admit(e, "root", _kid("root.k1", ["g"], criterion("k1", "K1")), _kid("root.k2", ["h"], criterion("k2", "K2")),
           _kid("root.k3", ["h"], criterion("k3", "K3")), _kid("root.b", ["g"], criterion("b", "B")))
    _admit(e, "root.b", _kid("root.b.x", ["b"], criterion("x", "X")))
    T.TOOLS["add_dependency"](e, "root.k2", "root.k3", check=criterion("reads_k2")["check"])  # …a check reading k2
    T.TOOLS["add_dependency"](e, "root.k2", "root.b.x")
    k3 = e.graph.get_task(TaskId("root.k3"))
    T.signal(e, "root.k3", "ACCEPT", str(k3.assignee))
    _found(e, "root.k2", "k2", "./k2 f.c; echo $?")
    e.wait_idle()
    yield e
    e.stop()


def _level(e, assignee=None):
    """The parent's re-admission: a new intermediate `root.grp` takes over `h`, `root.k2` dropped from the split."""
    out = T.TOOLS["decompose"](e, "root", [{**_kid("root.grp", ["h"], criterion("grp", "the group holds")),
                                            **({"assignee": assignee} if assignee else {})}], drops=["root.k2"])
    e.wait_idle()
    assert not (isinstance(out, dict) and out.get("error")), out
    return out


def _copy(e, replaces=("root.k2",)):
    out = T.TOOLS["decompose"](e, "root.grp", [{**_kid("root.grp.k2", ["grp"], criterion("k2", "K2")),
                                                "replaces": list(replaces)}], accepted_risks=_RISK)
    e.wait_idle()
    return out


def test_a_copy_under_the_new_level_carries_the_dropped_child_on(tree):
    e = tree
    _level(e)
    out = _copy(e)
    assert isinstance(out, list), out
    assert e.replaces(TaskId("root.grp.k2")) == ["root.k2"]
    assert "root.k2" in {str(t.id) for t in e.carried_work(TaskId("root.grp.k2"))}
    assert not e.carried_work(TaskId("root.grp"))            # …the copy carries it, not the intermediate
    assert [p["command"] for p in e.regression_probes(TaskId("root.grp.k2"))["k2"]] == ["./k2 f.c; echo $?"]


def test_its_sibling_consumer_reads_the_copy_and_is_offered_it_anew(tree):
    e = tree
    assert e.graph.get_state(TaskId("root.k3")) == State.EXECUTING
    _level(e)
    _copy(e)
    assert _deps(e, "root.k3") == {"root.grp.k2"}
    assert e.graph.get_state(TaskId("root.k3")) == State.OFFERED


def test_a_consumer_in_another_branch_is_named_to_its_issuer_and_left_as_it_stands(tree):
    e = tree
    _level(e)
    out = _copy(e)
    assert _deps(e, "root.b.x") == {"root.k2"}
    copy = next(o for o in out if o["id"] == "root.grp.k2")
    issuer = str(e.graph.issuer_of(TaskId("root.b.x")))
    assert {"task_id": "root.b.x", "reads": "root.k2", "issuer": issuer} in copy["readers_elsewhere"], copy


def test_within_one_split_the_replacement_takes_the_consumers_too(tree):
    e = tree
    out = T.TOOLS["decompose"](e, "root", [{**_kid("root.k2b", ["h"], criterion("k2", "K2")),
                                            "replaces": ["root.k2"]}], drops=["root.k2"])
    e.wait_idle()
    assert isinstance(out, list), out
    assert e.replaces(TaskId("root.k2b")) == ["root.k2"] and _deps(e, "root.k3") == {"root.k2b"}


def test_a_settled_child_is_moved_by_nothing(tree):
    e = tree
    k1 = e.graph.get_task(TaskId("root.k1"))
    k1.state = State.DONE
    e.graph.save_task(k1)
    _level(e)
    with pytest.raises(ValueError) as no:
        _copy(e, replaces=("root.k1",))
    assert "root.k1" in str(no.value) and "settled" in str(no.value) and "REOPEN" in str(no.value), no.value
    assert e.graph.get_task(TaskId("root.grp.k2")) is None


def test_another_party_s_contract_is_not_re_issued_under_its_level(tree):
    e = tree
    _level(e, assignee="exec-1")
    with pytest.raises(ValueError) as no:
        _copy(e)
    assert "root.k2" in str(no.value) and str(e.graph.issuer_of(TaskId("root.k2"))) in str(no.value), no.value
    assert e.graph.get_task(TaskId("root.grp.k2")) is None


def test_get_task_shows_the_link_both_ways(tree):
    e = tree
    _level(e)
    _copy(e)
    assert T.get_task(e, "root.grp.k2")["replaces"] == ["root.k2"]
    assert T.get_task(e, "root.k2")["replaced_by"] == ["root.grp.k2"]


def test_dependent_children_moved_together_read_each_other_s_copies(tree):
    """k3 reads k2 and both move under the level: the copy of k3, restated as it stood, reads the copy of k2."""
    e = tree
    k3 = T.get_task(e, "root.k3")
    T.TOOLS["decompose"](e, "root", [_kid("root.grp", ["h"], criterion("grp", "the group holds"))],
                         drops=["root.k2", "root.k3"])
    e.wait_idle()
    out = T.TOOLS["decompose"](e, "root.grp", [
        {**_kid("root.grp.k2", ["grp"], criterion("k2", "K2")), "replaces": ["root.k2"]},
        {"task_id": "root.grp.k3", "covers": ["grp"], "replaces": ["root.k3"], "deps": k3["deps"],
         "spec": {"description": "root.k3", "criteria": k3["criteria"]}}], accepted_risks=_RISK)
    e.wait_idle()
    assert _deps(e, "root.grp.k3") == {"root.grp.k2"}
    assert "root.grp.k2" in {c["depends_on"] for c in T.get_task(e, "root.grp.k3")["criteria"]}
    assert not [r for o in out for r in o.get("readers_elsewhere", ()) if r["task_id"] == "root.grp.k3"], out


def test_a_node_already_replaced_across_the_level_is_not_replaced_again(tree):
    e = tree
    _level(e)
    _copy(e)
    with pytest.raises(ValueError) as no:
        T.TOOLS["decompose"](e, "root.grp", [{**_kid("root.grp.k2b", ["grp"], criterion("k2", "K2")),
                                              "replaces": ["root.k2"]}])
    assert "replaced already, by root.grp.k2:" in str(no.value), no.value


def test_a_node_already_replaced_in_its_split_is_not_replaced_again(tree):
    e = tree
    T.TOOLS["decompose"](e, "root", [{**_kid("root.k2b", ["h"], criterion("k2", "K2")), "replaces": ["root.k2"]}],
                         drops=["root.k2"])
    e.wait_idle()
    with pytest.raises(ValueError) as no:
        T.TOOLS["decompose"](e, "root", [{**_kid("root.k2c", ["h"], criterion("k2", "K2")), "replaces": ["root.k2"]}])
    assert "replaced already, by root.k2b:" in str(no.value), no.value


def test_a_drop_with_no_copy_yet_names_the_readers_left_waiting_on_it(tree):
    e = tree
    out = _level(e)
    grp = next(o for o in out if o["id"] == "root.grp")
    assert {"dropped": "root.k2", "task_id": "root.k3"} in [
        {k: r[k] for k in ("dropped", "task_id")} for r in grp["readers_of_dropped"]], grp


def test_a_consumer_moved_first_reads_the_producer_s_copy_when_it_moves_later(tree):
    """k3 goes under the level first, still reading k2; when k2 follows, the copy of k3 — in the copy's own split — is
    handed to the copy of k2 in that act."""
    e = tree
    k3 = T.get_task(e, "root.k3")
    T.TOOLS["decompose"](e, "root", [_kid("root.grp", ["h"], criterion("grp", "the group holds"))], drops=["root.k3"])
    e.wait_idle()
    T.TOOLS["decompose"](e, "root.grp", [{"task_id": "root.grp.k3", "covers": ["grp"], "replaces": ["root.k3"],
                                          "deps": k3["deps"], "spec": {"description": "k3", "criteria": k3["criteria"]}}],
                         accepted_risks=_RISK)
    e.wait_idle()
    T.TOOLS["decompose"](e, "root", [], drops=["root.k2"])
    e.wait_idle()
    out = _copy(e)
    assert _deps(e, "root.grp.k3") == {"root.grp.k2"}
    assert not [r for o in out for r in o.get("readers_elsewhere", ()) if r["task_id"] == "root.grp.k3"], out


def test_a_reader_of_the_dropped_node_s_subtree_is_named_too(tree):
    e = tree
    _admit(e, "root.k2", _kid("root.k2.a", ["k2"], criterion("a", "A")))
    T.TOOLS["add_dependency"](e, "root.k2.a", "root.b.x")
    out = _level(e)
    grp = next(o for o in out if o["id"] == "root.grp")
    assert {"dropped": "root.k2", "reads": "root.k2.a", "task_id": "root.b.x"} in [
        {k: r.get(k) for k in ("dropped", "reads", "task_id")} for r in grp["readers_of_dropped"]], grp


def test_the_copy_carries_the_passed_parts_of_what_it_replaces(tree):
    """A dropped node's DONE parts are its committed work (§12.16 (ii)): the cancellation that drops it leaves them out
    of its subtree, and the copy must still carry them."""
    e = tree
    _admit(e, "root.k2", _kid("root.k2.a", ["k2"], criterion("a", "A")))
    a = e.graph.get_task(TaskId("root.k2.a"))
    a.state = State.DONE
    e.graph.save_task(a)
    _level(e)
    _copy(e)
    assert {"root.k2", "root.k2.a"} <= {str(t.id) for t in e.carried_work(TaskId("root.grp.k2"))}


def test_the_copy_carries_a_passed_part_beneath_a_cancelled_part_named_by_hand(tree):
    """…a DONE part under a part the drop cancels, its id not spelling its ancestry: the live walk stops at the
    cancelled part, the copy still carries it."""
    e = tree
    _admit(e, "root.k2", _kid("m", ["k2"], criterion("m", "M")))
    _admit(e, "m", _kid("q", ["m"], criterion("q", "Q")))
    q = e.graph.get_task(TaskId("q"))
    q.state = State.DONE
    e.graph.save_task(q)
    _level(e)
    _copy(e)
    assert "q" in {str(t.id) for t in e.carried_work(TaskId("root.grp.k2"))}


def _restated(e, tid, as_id, covers, replaces=()):
    """`tid` named again as `as_id`, its deps and criteria as `get_task` gives them."""
    t = T.get_task(e, tid)
    return {"task_id": as_id, "covers": covers, "replaces": list(replaces), "deps": t["deps"],
            "spec": {"description": t["description"], "criteria": t["criteria"]}}


def _reads(e, tid) -> set:
    return _deps(e, tid) | {c["depends_on"] for c in T.get_task(e, tid)["criteria"] if c["depends_on"]}


def test_a_consumer_copied_after_its_producer_s_copy_reads_that_copy(tree):
    e = tree
    T.TOOLS["decompose"](e, "root", [_kid("root.grp", ["h"], criterion("grp", "the group holds"))],
                         drops=["root.k2", "root.k3"])
    e.wait_idle()
    _copy(e)
    T.TOOLS["decompose"](e, "root.grp", [_restated(e, "root.k3", "root.grp.k3", ["grp"], ["root.k3"])])
    e.wait_idle()
    assert _reads(e, "root.grp.k3") == {"root.grp.k2"}


def test_within_one_split_a_consumer_copied_later_reads_the_producer_s_copy(tree):
    e = tree
    T.TOOLS["decompose"](e, "root", [{**_kid("root.k2b", ["h"], criterion("k2", "K2")), "replaces": ["root.k2"]}],
                         drops=["root.k2", "root.k3"])
    e.wait_idle()
    T.TOOLS["decompose"](e, "root", [_restated(e, "root.k3", "root.k3b", ["h"], ["root.k3"])])
    e.wait_idle()
    assert _reads(e, "root.k3b") == {"root.k2b"}


def test_a_reference_follows_a_chain_of_replacements_to_its_live_end(tree):
    e = tree
    for was, now in (("root.k2", "root.k2b"), ("root.k2b", "root.k2c")):
        T.TOOLS["decompose"](e, "root", [{**_kid(now, ["h"], criterion("k2", "K2")), "replaces": [was]}], drops=[was])
        e.wait_idle()
    T.TOOLS["decompose"](e, "root.b", [{**_kid("root.b.y", ["b"], criterion("y", "Y")),
                                        "deps": [{"from": "root.k2", "glue": "reads k2"}]}])
    e.wait_idle()
    assert _deps(e, "root.b.y") == {"root.k2c"}


def test_a_child_naming_a_dropped_node_nothing_replaces_is_named_in_the_reply(tree):
    e = tree
    _level(e)
    out = T.TOOLS["decompose"](e, "root.grp", [{**_kid("root.grp.y", ["grp"], criterion("y", "Y")),
                                                "deps": [{"from": "root.k2", "glue": "reads k2"}]}], accepted_risks=_RISK)
    e.wait_idle()
    y = next(o for o in out if o["id"] == "root.grp.y")
    assert {"dropped": "root.k2", "task_id": "root.grp.y"} in [
        {k: r[k] for k in ("dropped", "task_id")} for r in y["readers_of_dropped"]], y


def test_a_standing_child_named_again_without_deps_reads_the_copy_of_what_its_edges_name(tree):
    e = tree
    _level(e)
    _copy(e)
    x = T.get_task(e, "root.b.x")
    T.TOOLS["decompose"](e, "root.b", [{"task_id": "root.b.x",
                                        "spec": {"description": x["description"], "criteria": x["criteria"]}}])
    e.wait_idle()
    assert _reads(e, "root.b.x") == {"root.grp.k2"}


def test_a_standing_child_named_again_without_criteria_reads_the_copy_through_them(tree):
    e = tree
    T.TOOLS["add_dependency"](e, "root.k2", "root.b.x", check=criterion("reads_k2")["check"])
    _level(e)
    _copy(e)
    T.TOOLS["decompose"](e, "root.b", [{"task_id": "root.b.x", "spec": {"description": "root.b.x"},
                                        "deps": [{"from": "root.grp.k2", "glue": "reads k2's copy"}]}])
    e.wait_idle()
    assert _reads(e, "root.b.x") == {"root.grp.k2"}


def test_a_dependency_on_a_replaced_node_is_declared_on_its_copy(tree):
    e = tree
    _level(e)
    _copy(e)
    out = T.TOOLS["add_dependency"](e, "root.k2", "root.k1")
    assert _deps(e, "root.k1") == {"root.grp.k2"}, out


def test_a_dependency_on_a_dropped_node_nothing_replaces_is_refused(tree):
    e = tree
    _level(e)
    with pytest.raises(ValueError) as no:
        T.TOOLS["add_dependency"](e, "root.k2", "root.k1")
    assert "root.k2" in str(no.value) and "dropped" in str(no.value), no.value
    assert _deps(e, "root.k1") == set()


def _two_copies(e, **k3):
    T.TOOLS["decompose"](e, "root", [_kid("root.grp", ["h"], criterion("grp", "the group holds"))],
                         drops=["root.k2", "root.k3"])
    e.wait_idle()
    _copy(e)
    T.TOOLS["decompose"](e, "root.grp", [{**_kid("root.grp.k3", ["grp"], criterion("k3", "K3")),
                                          "replaces": ["root.k3"], **k3}])
    e.wait_idle()


def test_a_copy_given_no_deps_keeps_the_edges_of_what_it_replaces_each_resolved(tree):
    e = tree
    _two_copies(e)
    assert _deps(e, "root.grp.k3") == {"root.grp.k2"}


def test_a_copy_s_given_deps_win(tree):
    e = tree
    _two_copies(e, deps=[])
    assert _deps(e, "root.grp.k3") == set()


@pytest.mark.parametrize("door", ["edit_criteria", "revise", "create_task"])
def test_every_door_that_writes_a_criterion_reads_the_copy_of_a_dropped_producer(tree, door):
    """A criterion's `depends_on` enters through the one place every version of a packet enters (ASSIGN, revision):
    named onto a dropped node its copy stands in for, it reads the copy, whichever door wrote it (critic, 11-19)."""
    e = tree
    _level(e)
    _copy(e)
    reads = {**criterion("reads_k2"), "depends_on": "root.k2"}
    k1 = [{"name": c.name, "description": c.description,
           "check": [{"behaviour": x.behaviour, "command": x.command, "expect": x.expect} for x in c.check]}
          for c in e.graph.get_task(TaskId("root.k1")).spec.criteria]
    if door == "edit_criteria":
        out, at = T.TOOLS["edit_criteria"](e, "root.k1", k1 + [reads]), "root.k1"
    elif door == "revise":
        out, at = T.TOOLS["revise"](e, "root.k1", spec={"criteria": k1 + [reads]}, reason="scope_expansion"), "root.k1"
    else:
        out, at = T.TOOLS["create_task"](e, "root.b.z", {"description": "z", "criteria": [reads]},
                                         parent_id="root.b", covers=["b"]), "root.b.z"
    e.wait_idle()
    assert not (isinstance(out, dict) and (out.get("error") or out.get("refused"))), out
    assert {str(c.depends_on) for c in e.graph.get_task(TaskId(at)).spec.criteria if c.depends_on} == {"root.grp.k2"}


def test_a_new_criterion_on_a_dropped_node_nothing_replaces_is_refused(tree):
    e = tree
    _level(e)                                                 # …k2 dropped, no copy
    out = T.TOOLS["create_task"](e, "root.b.z", {"description": "z", "criteria": [{**criterion("r"),
                                                                                   "depends_on": "root.k2"}]},
                                 parent_id="root.b", covers=["b"])
    assert isinstance(out, dict) and "nothing replaces it" in str(out.get("error") or out), out


def test_a_copy_merging_a_producer_and_its_reader_inherits_no_edge_onto_itself(tree):
    e = tree
    out = T.TOOLS["decompose"](e, "root", [_kid("root.grp", ["h"], criterion("grp", "the group holds"))],
                               drops=["root.k2", "root.k3"])
    e.wait_idle()
    assert not (isinstance(out, dict) and out.get("error")), out
    out = T.TOOLS["decompose"](e, "root.grp", [{**_kid("root.grp.m", ["grp"], criterion("m", "M")),
                                                "replaces": ["root.k2", "root.k3"]}], accepted_risks=_RISK)
    e.wait_idle()
    assert isinstance(out, list), out
    assert _deps(e, "root.grp.m") == set()


def test_a_reader_in_another_branch_revised_by_its_issuer_waits_on_the_copy_not_the_dropped(tree):
    """The reply sends another branch's reader to its own issuer's revision; that revision moves its wait with its read
    (critic over e164a12: the read moved onto the copy, the declared edge stayed on the dropped node, the reader never
    started)."""
    e = tree
    T.TOOLS["add_dependency"](e, "root.k2", "root.b.x", check=criterion("bx_reads_k2")["check"])
    _level(e)
    _copy(e)
    bx = e.graph.get_task(TaskId("root.b.x"))
    again = [{"name": c.name, "description": c.description, **({"depends_on": str(c.depends_on)} if c.depends_on else {}),
              "check": [{"behaviour": x.behaviour, "command": x.command, "expect": x.expect} for x in c.check]}
             for c in bx.spec.criteria]
    out = T.TOOLS["edit_criteria"](e, "root.b.x", again)
    e.wait_idle()
    assert not (isinstance(out, dict) and (out.get("error") or out.get("refused"))), out
    assert _deps(e, "root.b.x") == {"root.grp.k2"}


def _bx_read_moved(e):
    T.TOOLS["add_dependency"](e, "root.k2", "root.b.x", check=criterion("bx_reads_k2")["check"])
    T.signal(e, "root.b.x", "ACCEPT", str(e.graph.get_task(TaskId("root.b.x")).assignee))
    _level(e)
    _copy(e)
    e.wait_idle()
    bx = e.graph.get_task(TaskId("root.b.x"))
    return bx, [{"name": c.name, "description": c.description,
                 **({"depends_on": str(c.depends_on)} if c.depends_on else {}),
                 "check": [{"behaviour": x.behaviour, "command": x.command, "expect": x.expect} for x in c.check]}
                for c in bx.spec.criteria]


def _assigns(e, tid):
    return [a for a in e.audit_log(TaskId(tid)) if a.signal.name == "ASSIGN" and not a.rejected]


@pytest.mark.parametrize("how", ["pins_nothing", "not_the_issuer"])
def test_a_refused_revision_moves_no_edge_and_issues_no_version(tree, how):
    """Whole or nothing: the edges follow the reads only once the revision took (critic over dec95cf — a refused one
    still re-issued the node and re-offered its work, in the issuer's name)."""
    e = tree
    bx, again = _bx_read_moved(e)
    state, n, edges = e.graph.get_state(bx.id), len(_assigns(e, "root.b.x")), _deps(e, "root.b.x")
    with pytest.raises(ValueError):
        if how == "pins_nothing":
            T.TOOLS["edit_criteria"](e, "root.b.x", again + [{"name": "loose", "description": "no check"}])
        else:
            T.TOOLS["edit_criteria"](e, "root.b.x", again, agent="intruder")
    e.wait_idle()
    assert (e.graph.get_state(bx.id), len(_assigns(e, "root.b.x")), _deps(e, "root.b.x")) == (state, n, edges)

