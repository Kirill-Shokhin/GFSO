"""The admission checks the split AS IT WILL STAND and then writes THAT split (§11.5) — one object, `admission.Split`.

Critic r8 over the corner-9 branch found the battery and the writes describing one act separately: a mapping onto a
child the act does not issue was counted and never stored; the node's contract was revised before an admission that
was then refused; a re-issued child's old Dep edge was read as standing, so a reversed seam was refused as a cycle.
Hence two properties, each per door: what stands after an admitted act is what the battery read, and a refused act
leaves the graph as it was.
"""
from __future__ import annotations

from datetime import datetime, timedelta

import pytest

import gfso.engine.admission as engine_module
import gfso.tools as T
from gfso.core.graph.model import dep_scope, standing_split
from gfso.core.types import AgentId, Criteria, Register, Signal, SignalData, Spec, TaskId
from gfso.decompose.build import build_graph_live
from tests.support import REGISTER, REGISTER_SPLIT, criterion, instrument_passes, make_engine, pinned


def _kid(tid, covers, dep=None, ok="ok"):
    crits = [criterion(f"{tid}_{ok}", tid)] + ([{"name": f"dep__{dep}", "description": "reads it", "depends_on": dep}]
                                               if dep else [])
    return {"task_id": tid, "assignee": "me", "covers": covers, "spec": {"description": tid, "criteria": crits}}


def _plan(crits, maps, deps=()):
    kids = sorted({c for c, _ in maps})
    return {"name": "g", "root_criteria": [criterion(c, c) for c in crits],
            "subtasks": [{"id": k, "name": k, "description": f"part {k}", "criteria": [criterion(f"{k}_ok", k)]}
                         for k in kids],
            "mappings": [{"criterion": g, "child_id": c} for c, g in maps], "deps": list(deps),
            "accepted_risks": REGISTER, "scope": []}


def _graph(e):
    """Everything an admission can write: every node's state, contract, Del, coverage, register and active children (a
    drop is recorded, not signalled); every Dep record; the log's length."""
    tasks = sorted((str(t.id), t.state.name, repr(t.spec), str(t.assignee), repr(t.register),
                    sorted((m.criterion_name, str(m.child_id)) for m in t.criterion_mappings),
                    sorted(str(k.id) for k in e.graph.get_active_children(t.id))) for t in e.all_tasks())
    edges = sorted((str(x.from_id), str(x.to_id), x.discovered, x.provisional) for x in e.graph.dep_edges(closed=True))
    return tasks, edges, len(e._audit)


@pytest.fixture
def checked(monkeypatch):
    """The Split each admission's battery read, in order."""
    seen = []
    real = engine_module.refuse_unless_syntactic

    def spy(*a, **kw):
        seen.append(real(*a, **kw))
        return seen[-1]
    monkeypatch.setattr(engine_module, "refuse_unless_syntactic", spy)
    return seen


def _stands_as_checked(e, split):
    node, kids = standing_split(e.graph, e.graph.get_task(split.node.id))
    assert {(m.criterion_name, str(m.child_id)) for m in node.criterion_mappings} == \
        {(m.criterion_name, str(m.child_id)) for m in split.node.criterion_mappings}
    assert {str(k.id) for k in kids} == {str(k.id) for k in split.children}
    assert [c.name for c in node.spec.criteria] == [c.name for c in split.node.spec.criteria]
    assert {(str(x.from_id), str(x.to_id)) for x in dep_scope(e.graph, node.id)[0]} == set(split.edges)
    assert node.register == split.node.register


# --- what stands is what was checked ---------------------------------------------------------------------------------

def test_a_mapping_onto_a_child_this_act_does_not_issue_is_written(checked):
    e = make_engine(); e.start()
    T.create_task(e, "root", {"description": "goal", "criteria": [criterion(c, c.upper()) for c in "abc"]}, "me")
    e.wait_idle()
    T.decompose(e, "root", [_kid("k1", ["a", "b"]), _kid("k3", ["c"])], accepted_risks=REGISTER); e.wait_idle()
    T.signal(e, "k3", "CANCEL", "me", reason="not needed"); e.wait_idle()
    T.signal(e, "k3", "CONFIRM_CANCEL", "me", in_flight="none"); e.wait_idle()
    # c moves onto k1, which this act does not re-issue — named only in the flat mappings
    T.decompose(e, "root", [_kid("k2", ["b"])], mappings=[{"criterion_name": "c", "child_id": "k1"}],
                accepted_risks=REGISTER)
    e.wait_idle()
    _stands_as_checked(e, checked[-1])
    assert ("c", "k1") in {(m.criterion_name, str(m.child_id)) for m in e.graph.get_task(TaskId("root")).criterion_mappings}
    assert not T.list_holes(e, "root")["holes"]
    e.stop()


@pytest.mark.parametrize("door", ["tools", "build"])
def test_a_re_admission_turning_a_seam_around_is_admitted_and_stands_turned(door, checked):
    e = make_engine(); e.start()
    if door == "tools":
        T.create_task(e, "root", {"description": "goal", "criteria": [criterion("a", "A"), criterion("b", "B")]}, "me")
        e.wait_idle()
        T.decompose(e, "root", [_kid("ka", ["a"]), _kid("kb", ["b"], dep="ka")], accepted_risks=REGISTER)
        e.wait_idle()
        T.decompose(e, "root", [_kid("ka", ["a"], dep="kb"), _kid("kb", ["b"])], accepted_risks=REGISTER)
        e.wait_idle()
        a, b = "ka", "kb"
    else:
        maps = [("a", "g1"), ("b", "g2")]
        build_graph_live(_plan(["g1", "g2"], maps, [{"from": "a", "to": "b", "glue": "b reads a"}]), "goal", e,
                         root_id="root", assignee="me"); e.wait_idle()
        _, _, problems = build_graph_live(_plan(["g1", "g2"], maps, [{"from": "b", "to": "a", "glue": "a reads b"}]),
                                          "goal", e, root_id="root", assignee="me"); e.wait_idle()
        assert not problems
        a, b = "root.a", "root.b"
    assert [(str(x.from_id), str(x.to_id)) for x in e.graph.dep_edges()] == [(b, a)]
    _stands_as_checked(e, checked[-1])
    e.stop()


def test_a_settled_childs_new_coverage_is_written(monkeypatch, checked):
    monkeypatch.setenv("GFSO_L2_GATE", "0")
    e = make_engine(); e.start()
    build_graph_live(_plan(["g1", "g2"], [("a", "g1"), ("b", "g2")]), "goal", e, root_id="root", assignee="me")
    e.wait_idle()
    T.signal(e, "root.a", "ACCEPT", "me"); e.wait_idle()
    T.signal(e, "root.a", "DELIVER", "me", result="ran it: ok", self_validation="PASS"); e.wait_idle()
    instrument_passes(e, TaskId("root.a"), "me")
    T.signal(e, "root.a", "PASS", "me"); e.wait_idle()
    assert e.graph.get_state(TaskId("root.a")).name == "DONE"
    _, _, problems = build_graph_live(_plan(["g1", "g2"], [("a", "g1"), ("a", "g2"), ("c", "g1")]), "goal", e,
                                      root_id="root", assignee="me")
    e.wait_idle()
    assert not any("admission refused" in p for p in problems)
    _stands_as_checked(e, checked[-1])
    assert ("g2", "root.a") in {(m.criterion_name, str(m.child_id))
                                for m in e.graph.get_task(TaskId("root")).criterion_mappings}
    e.stop()


# --- a refused act leaves the graph as it was, at every door ---------------------------------------------------------

def _two_children(e):
    T.create_task(e, "root", {"description": "goal", "criteria": [criterion("a", "A"), criterion("b", "B")]}, "me")
    e.wait_idle()
    T.decompose(e, "root", [_kid("ka", ["a"]), _kid("kb", ["b"], dep="ka")], accepted_risks=REGISTER); e.wait_idle()


def test_refused_at_decompose_nothing_moves():
    e = make_engine(); e.start()
    _two_children(e)
    before = _graph(e)
    # a re-issue that turns the seam around, a new child, a register — and one pair onto no criterion: refused whole
    with pytest.raises(ValueError):
        T.decompose(e, "root", [_kid("ka", ["a"], dep="kb", ok="new"), _kid("kb", ["b"]), _kid("kc", ["zz"])],
                    accepted_risks=REGISTER)
    e.wait_idle()
    assert _graph(e) == before
    e.stop()


def test_refused_at_create_task_under_a_parent_nothing_moves():
    e = make_engine(); e.start()
    _two_children(e)
    before = _graph(e)
    out = T.create_task(e, "kx", {"description": "x", "criteria": [criterion("x_ok", "X")]}, "me", parent_id="root")
    e.wait_idle()
    assert "error" in out
    assert _graph(e) == before
    e.stop()


def test_refused_at_the_build_nothing_moves_the_contract_included():
    e = make_engine(); e.start()
    build_graph_live(_plan(["g1", "g2"], [("a", "g1"), ("b", "g2")]), "goal", e, root_id="root", assignee="me")
    e.wait_idle()
    before = _graph(e)
    # the root's contract re-authored (g2 → g3) with a split leaving g1 uncovered
    _, _, problems = build_graph_live(_plan(["g1", "g3"], [("c", "g3")]), "goal", e, root_id="root", assignee="me")
    e.wait_idle()
    assert any("admission refused" in p for p in problems)
    assert _graph(e) == before
    e.stop()


def test_refused_at_the_register_nothing_moves():
    e = make_engine(); e.start()
    _two_children(e)
    before = _graph(e)
    with pytest.raises(ValueError):
        e.admit_register(TaskId("root"), Register(), AgentId("me"))
    assert _graph(e) == before
    e.stop()


# --- what the act names, classified before it writes (critic r9) -----------------------------------------------------

def _who(i, covers, who, desc=None):
    return {"task_id": i, "spec": {"description": desc or i, "criteria": [criterion(f"{i}_ok", desc or i)]},
            "assignee": who, "covers": covers}


@pytest.mark.parametrize("carol", ["bob", "carol"])
def test_another_parents_child_is_not_taken_and_neither_split_moves(carol):
    e = make_engine(); e.start()
    T.create_task(e, "root", {"description": "app", "criteria": [criterion("be", "back"), criterion("fe", "front")]}, "me")
    e.wait_idle()
    T.decompose(e, "root", [_who("backend", ["be"], "bob"), _who("frontend", ["fe"], carol)], accepted_risks=REGISTER)
    e.wait_idle()
    T.decompose(e, "backend", [_who("api", ["backend_ok"], "bob"), _who("tests", ["backend_ok"], "bob", "backend tests")],
                accepted_risks=REGISTER)
    e.wait_idle()
    before = _graph(e)
    with pytest.raises(ValueError, match="one parent"):
        T.decompose(e, "frontend", [_who("ui", ["frontend_ok"], carol),
                                    _who("tests", ["frontend_ok"], carol, "frontend tests")], accepted_risks=REGISTER)
    e.wait_idle()
    assert _graph(e) == before
    e.stop()


def test_a_settled_child_is_not_dropped(monkeypatch):
    monkeypatch.setenv("GFSO_L2_GATE", "0")
    e = make_engine(); e.start()
    build_graph_live(_plan(["g1", "g2"], [("a", "g1"), ("b", "g2")]), "goal", e, root_id="root", assignee="me")
    e.wait_idle()
    T.signal(e, "root.a", "ACCEPT", "me"); e.wait_idle()
    T.signal(e, "root.a", "DELIVER", "me", result="ran it: ok", self_validation="PASS"); e.wait_idle()
    instrument_passes(e, TaskId("root.a"), "me")
    T.signal(e, "root.a", "PASS", "me"); e.wait_idle()
    before = _graph(e)
    with pytest.raises(ValueError, match="drops only"):
        e.decompose_task(TaskId("root"), [], None, drops=(TaskId("root.a"),))
    assert _graph(e) == before
    e.stop()


@pytest.mark.parametrize("door", ["engine", "build"])
def test_an_act_that_leaves_no_split_takes_no_register_and_cancels_nothing(door):
    e = make_engine(); e.start()
    build_graph_live(_plan(["g1", "g2"], [("a", "g1"), ("b", "g2")]), "goal", e, root_id="root", assignee="me")
    e.wait_idle()
    before = _graph(e)
    if door == "engine":
        with pytest.raises(ValueError, match="no split"):
            e.decompose_task(TaskId("root"), [], None, register=REGISTER_SPLIT,
                             drops=(TaskId("root.a"), TaskId("root.b")))
    else:
        _, _, problems = build_graph_live(_plan(["g1", "g2"], []), "goal", e, root_id="root", assignee="me")
        assert any("no split" in p for p in problems)
    e.wait_idle()
    assert _graph(e) == before
    e.stop()


def test_the_contract_checked_is_the_one_written_with_its_seams():
    e = make_engine(); e.start()
    T.create_task(e, "root", {"description": "goal", "criteria": [criterion("r1", "one"), criterion("r2", "two")]}, "me")
    e.wait_idle()
    T.decompose(e, "root", [_who("P", ["r1"], "me"), _who("Q", ["r2"], "me")], accepted_risks=REGISTER); e.wait_idle()
    e.add_dependency(TaskId("Q"), TaskId("P"), glue="P reads Q's output"); e.wait_idle()
    before = _graph(e)
    # P re-authored by its issuer to [x] with a split covering x alone: the revision would carry dep__Q, uncovered
    plan = {"name": "p", "root_criteria": [criterion("x", "the part")],
            "subtasks": [{"id": "a", "name": "a", "description": "part a", "criteria": [criterion("a_ok", "a")]}],
            "mappings": [{"criterion": "x", "child_id": "a"}], "deps": [], "accepted_risks": REGISTER, "scope": []}
    _, _, problems = build_graph_live(plan, "split P", e, root_id="P", assignee="me")
    e.wait_idle()
    assert any("dep__Q" in p for p in problems)
    assert _graph(e) == before
    e.stop()


def test_a_closing_node_admits_no_act_on_its_split():
    e = make_engine(); e.start()
    build_graph_live(_plan(["g1", "g2"], [("a", "g1"), ("b", "g2")]), "goal", e, root_id="root", assignee="me")
    e.wait_idle()
    T.signal(e, "root", "CANCEL", "me", reason="the goal is gone"); e.wait_idle()
    assert e.graph.get_state(TaskId("root")).name == "CANCELLING"
    before = _graph(e)
    with pytest.raises(ValueError, match="12.7"):
        e.decompose_task(TaskId("root"), [], None, drops=(TaskId("root.a"),))
    assert _graph(e) == before
    e.stop()


# --- one act at every door (critic r10) ------------------------------------------------------------------------------

def test_a_bare_child_assign_is_no_admission_and_nothing_enters_the_split():
    e = make_engine(); e.start()
    T.create_task(e, "root", {"description": "goal", "criteria": [criterion("a", "A"), criterion("b", "B")]}, "me")
    e.wait_idle()
    before = _graph(e)[:2]
    r = e.send_signal_sync(SignalData(signal=Signal.ASSIGN, task_id=TaskId("x"), source=AgentId("me"),
                                      parent_id=TaskId("root"), spec=Spec("x", (Criteria("x_ok", "x", check=pinned("x_ok")),)),
                                      assignee=AgentId("me")))
    e.wait_idle()
    assert r is not None and r.rejected and "admission" in (r.error or "")
    assert _graph(e)[:2] == before
    e.stop()


def test_a_re_issued_child_whose_deadline_lapsed_is_refused_before_anything_is_written():
    e = make_engine(check_interval=10_000); e.start()
    _two_children(e)
    past = datetime.now() - timedelta(hours=1)
    for tid in ("root", "ka", "kb"):            # the goal and its plan outlived their deadlines
        t = e.graph.get_task(TaskId(tid)); t.deadline = past; e._graph.save_task(t)
    before = _graph(e)
    with pytest.raises(ValueError, match="types no deadline"):
        T.decompose(e, "root", [dict(_kid("kc", ["b"]), deadline=(datetime.now() + timedelta(hours=2)).isoformat()),
                                _kid("ka", ["a"], ok="v2")], accepted_risks=REGISTER)
    e.wait_idle()
    assert _graph(e) == before
    e.stop()


def test_a_child_named_and_dropped_at_once_is_refused():
    e = make_engine(); e.start()
    _two_children(e)
    before = _graph(e)
    ka = e.graph.get_task(TaskId("ka"))
    with pytest.raises(ValueError, match="both named and dropped"):
        e.decompose_task(TaskId("root"), [(ka.id, ka.spec, ka.assignee)], None, drops=(ka.id,))
    assert _graph(e) == before
    e.stop()


# --- critic r11 ------------------------------------------------------------------------------------------------------

def test_a_re_issued_child_closing_a_cycle_through_another_branch_is_refused_whole():
    e = make_engine(); e.start()
    T.create_task(e, "R", {"description": "goal", "criteria": [criterion("r1", "R1"), criterion("r2", "R2")]}, "me")
    e.wait_idle()
    T.decompose(e, "R", [_who("A", ["r1"], "me"), _who("B", ["r2"], "me")], accepted_risks=REGISTER); e.wait_idle()
    T.decompose(e, "A", [_who("A1", ["A_ok"], "me")], accepted_risks=REGISTER); e.wait_idle()
    e.add_dependency(TaskId("A1"), TaskId("B"), glue="B reads A1"); e.wait_idle()
    before = _graph(e)
    with pytest.raises(ValueError, match="Dep cycle"):
        T.decompose(e, "A", [_who("A2", ["A_ok"], "me"),
                             {"task_id": "A1", "assignee": "me", "covers": ["A_ok"],
                              "spec": {"description": "A1", "criteria": [criterion("A1_ok", "A1"), {
                                  "name": "dep__B", "description": "A1 reads B", "depends_on": "B"}]}}])
    e.wait_idle()
    assert _graph(e) == before
    e.stop()


def test_a_ring_among_the_authored_children_reaches_the_repair_loop():
    e = make_engine(); e.start()
    plan = _plan(["g1", "g2"], [("a", "g1"), ("b", "g2")],
                 [{"from": "a", "to": "b", "glue": "b reads a"}, {"from": "b", "to": "a", "glue": "a reads b"}])
    _, _, problems = build_graph_live(plan, "goal", e, root_id="root", assignee="me")
    e.wait_idle()
    assert any("Dep cycle" in p for p in problems), problems
    assert not e.graph.get_active_children(TaskId("root"))
    e.stop()


def test_a_child_the_revised_contract_orphans_is_dropped_at_the_decompose_door():
    e = make_engine(); e.start()
    _two_children(e)
    T.edit_criteria(e, "root", [criterion("a", "A"), criterion("c", "C")], "me"); e.wait_idle()   # kb orphaned
    T.decompose(e, "root", [_kid("kc", ["c"])], accepted_risks=REGISTER, drops=["kb"])
    e.wait_idle()
    assert {str(k.id) for k in e.graph.get_active_children(TaskId("root"))} == {"ka", "kc"}
    assert not T.list_holes(e, "root")["holes"]
    e.stop()


def test_a_child_replaced_under_the_same_criterion_takes_its_coverage_with_the_drop():
    e = make_engine(); e.start()
    _two_children(e)
    T.decompose(e, "root", [_kid("kc", ["b"])], accepted_risks=REGISTER, drops=["kb"])
    e.wait_idle()
    assert {(m.criterion_name, str(m.child_id)) for m in e.graph.get_task(TaskId("root")).criterion_mappings} == \
        {("a", "ka"), ("b", "kc")}
    assert not T.list_holes(e, "root")["holes"]
    e.stop()
