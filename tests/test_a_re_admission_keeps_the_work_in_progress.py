"""What a re-admission changes and what it leaves alone (critic r13 over the admission-as-one-act stack).

- A child a re-admission drops leaves the plan at the drop, and that admission stales the Level-2 verdict; when its
  cancellation settles later, the plan does not change again, so a review made after the drop stands.
- A split that only sheds a child its revised contract no longer needs re-admits with no new child —
  `decompose(parent, [], drops=[…])` — and the children at work are not re-offered.
- The machine issuer's `reshape` keeps a child, as its `drop_child` does: dropping every child with none in their
  place would turn the node into a leaf with its split gone.
- A re-admission that names a standing child exactly as it stands does not re-issue it: re-listing the split whole, as
  the repair texts advise, re-offered work in progress, dropped deliveries and reopened a passed child (critic r14).
- While a Level-0 hole stands no Level-2 review runs, so the plan gate's hold names the holes, not the review.
- Coverage is the split's (§2.4), not a field of a child's packet (Inv-1, §12.3): a remap re-admits the split and
  revises no child; a re-listed child keeps the `spec` fields left out; a passed child named as it stands is not
  re-checked as if it were given out; a re-admission that changes nothing leaves the review standing; and a project
  written by an older build has its cached checks recomputed on start (critic r15).
"""
from __future__ import annotations

import json

import gfso.tools as T
from gfso.core.types import AgentId, CriterionMapping, State, TaskId
from gfso.decompose.build import _children_that_changed
from gfso.engine.validation import _l2_undischarged
from gfso.issuer import _reshape, _revise_child
from datetime import datetime, timedelta

from gfso.adapters.storage.memory import MemoryStorage
from gfso.core.types import CheckResult
from tests.support import REGISTER, criterion, make_engine, reviewer_passes


def _kid(k, covers, who="agent"):
    return {"task_id": k, "spec": {"description": f"part {k}", "criteria": [criterion(f"{k}_ok", k)]},
            "assignee": who, "covers": covers}


def _split(who="agent", kid_who=("agent", "bob")):
    e = make_engine()
    e.start()
    T.create_task(e, "root", {"description": "goal", "criteria": [criterion("a", "A"), criterion("b", "B")]}, who)
    e.wait_idle()
    T.signal(e, "root", "ACCEPT", who)
    e.wait_idle()
    T.decompose(e, "root", [_kid("k1", ["a"], kid_who[0]), _kid("k2", ["b"], kid_who[1])], accepted_risks=REGISTER)
    e.wait_idle()
    return e


def test_a_dropped_childs_settlement_does_not_stale_a_review_made_after_the_drop(monkeypatch):
    monkeypatch.setenv("GFSO_L2_GATE", "1")
    e = _split()
    T.signal(e, "k2", "ACCEPT", "bob")
    e.wait_idle()
    T.decompose(e, "root", [_kid("k3", ["b"])], drops=["k2"])
    e.wait_idle()
    root = e.graph.get_task(TaskId("root"))
    assert _l2_undischarged(e.graph, root) is None                      # the drop's admission staled it
    e._storage.store_critique(TaskId("root"), json.dumps({"semantic_covered": True}))
    root.verified = True
    e.graph.save_task(root)
    T.signal(e, "k2", "CONFIRM_CANCEL", "bob", in_flight="none")
    e.wait_idle()
    assert e.graph.get_state(TaskId("k2")) == State.ABANDONED
    assert _l2_undischarged(e.graph, e.graph.get_task(TaskId("root"))) == []   # the plan it read still stands
    assert e.execution_blocked_by(TaskId("k1")) is None
    e.stop()


def test_a_split_sheds_a_child_with_no_new_one_and_the_work_in_progress_keeps_working():
    e = _split(kid_who=("agent", "agent"))
    T.signal(e, "k1", "ACCEPT", "agent")
    e.wait_idle()
    T.edit_criteria(e, "root", [criterion("a", "A")])                  # k2 now addresses no criterion
    e.wait_idle()
    assert [h["check"] for h in T.list_holes(e)["holes"]] == ["CHECK-1b:no_orphan"]
    out = T.decompose(e, "root", [], drops=["k2"])
    e.wait_idle()
    assert out == [] and T.list_holes(e)["holes"] == []
    assert [str(k.id) for k in e.graph.get_active_children(TaskId("root"))] == ["k1"]
    k1 = e.graph.get_task(TaskId("k1"))
    assert k1.state == State.EXECUTING and k1.revisions == 0
    e.stop()


def test_an_empty_decompose_that_names_nothing_is_still_refused():
    e = _split()
    out = T.decompose(e, "root", [])
    assert out.get("refused") and "mappings=" in out["error"] and "drops=" in out["error"]
    e.stop()


def test_the_machine_issuers_reshape_does_not_dissolve_a_split():
    e = _split(who="exec1", kid_who=("exec2", "exec2"))
    ok, why = _reshape(e, e.graph.get_task(TaskId("root")), "exec1", {"drop": ["k1", "k2"]}, "no longer needed", None)
    e.wait_idle()
    assert ok is False and "replace" in why
    assert [str(k.id) for k in e.graph.get_active_children(TaskId("root"))] == ["k1", "k2"]
    e.stop()


def test_a_re_admission_leaves_a_standing_child_it_names_unchanged():
    e = _split(kid_who=("agent", "bob"))
    T.signal(e, "k1", "ACCEPT", "agent")
    T.signal(e, "k2", "ACCEPT", "bob")
    e.wait_idle()
    T.signal(e, "k2", "DELIVER", "bob", result="done", self_validation="PASS")
    e.wait_idle()
    reviewer_passes(e, "k2")
    T.signal(e, "k2", "PASS", "agent")
    e.wait_idle()
    T.edit_criteria(e, "root", [criterion("a", "A"), criterion("b", "B"), criterion("c", "C")])
    e.wait_idle()
    # the whole split re-listed: k1 now covers c too — coverage is the split's (§2.4), no field of its packet — and
    # k2 exactly as it stands
    T.decompose(e, "root", [_kid("k1", ["a", "c"]), _kid("k2", ["b"], "bob")], accepted_risks=REGISTER)
    e.wait_idle()
    k1, k2 = e.graph.get_task(TaskId("k1")), e.graph.get_task(TaskId("k2"))
    assert (k1.state, k1.revisions) == (State.EXECUTING, 0)           # a remap revises no child
    assert (k2.state, k2.revisions, k2.reopens) == (State.DONE, 0, 0)  # a passed child named unchanged stays passed
    assert T.list_holes(e)["holes"] == []
    # …and changing its CONTRACT is a revision of it: offered again
    T.decompose(e, "root", [{**_kid("k1", ["a", "c"]), "spec": {"description": "part k1, now also c",
                                                                "criteria": [criterion("k1_ok", "k1")]}}])
    e.wait_idle()
    k1 = e.graph.get_task(TaskId("k1"))
    assert (k1.state, k1.revisions) == (State.OFFERED, 1)
    e.stop()


def test_a_remap_onto_a_delivered_or_passed_child_keeps_its_work():
    e = _split(kid_who=("agent", "bob"))
    T.signal(e, "k1", "ACCEPT", "agent")
    T.signal(e, "k2", "ACCEPT", "bob")
    e.wait_idle()
    T.signal(e, "k1", "DELIVER", "agent", result="done", self_validation="PASS")
    T.signal(e, "k2", "DELIVER", "bob", result="done", self_validation="PASS")
    e.wait_idle()
    reviewer_passes(e, "k2")
    T.signal(e, "k2", "PASS", "agent")
    T.edit_criteria(e, "root", [criterion("a", "A"), criterion("b", "B"), criterion("c", "C"), criterion("d", "D")])
    e.wait_idle()
    one = T.map_criterion(e, "root", "k1", "c")               # d still uncovered: the re-admission is refused whole
    assert one.get("refused") and "mappings=" in one["error"]
    out = T.decompose(e, "root", [], mappings=[{"criterion_name": "c", "child_id": "k1"},
                                               {"criterion_name": "d", "child_id": "k2"}])
    e.wait_idle()
    assert out == [] and T.list_holes(e)["holes"] == []
    assert [(t, e.graph.get_task(TaskId(t)).state, e.graph.get_task(TaskId(t)).revisions) for t in ("k1", "k2")] == [
        ("k1", State.VALIDATING, 0), ("k2", State.DONE, 0)]
    e.stop()


def test_the_plan_gates_hold_names_the_level_0_holes_while_they_stand(monkeypatch):
    monkeypatch.setenv("GFSO_L2_GATE", "1")
    e = _split(kid_who=("agent", "agent"))
    T.edit_criteria(e, "root", [criterion("a", "A"), criterion("b", "B"), criterion("c", "C")])
    e.wait_idle()
    held = e.execution_blocked_by(TaskId("k1"))
    assert "CHECK-1" in held["why"] and "decompose" in held["opens_with"]
    out = T.signal(e, "k1", "ACCEPT", "agent")
    assert out.get("accepted") is False and "Level-0 holes" in str(out.get("error"))
    e.stop()


def test_a_relisted_child_keeps_the_spec_fields_left_out():
    e = _split(kid_who=("agent", "agent"))
    T.decompose(e, "root", [{**_kid("k3", ["b"]), "spec": {"description": "part k3", "criteria": [criterion("k3_ok", "k3")],
                                                           "accepted_risks": REGISTER}}])
    e.wait_idle()
    T.signal(e, "k3", "ACCEPT", "agent")
    e.wait_idle()
    T.decompose(e, "root", [{"task_id": "k3", "spec": {"description": "part k3", "criteria": [criterion("k3_ok", "k3")]},
                             "assignee": "agent", "covers": ["b"]}])          # no `accepted_risks`: its pre-fill stands
    e.wait_idle()
    k3 = e.graph.get_task(TaskId("k3"))
    assert (k3.state, k3.revisions, len(k3.spec.accepted_risks)) == (State.EXECUTING, 0, len(REGISTER))
    e.stop()


def test_a_passed_child_named_with_its_spent_deadline_does_not_refuse_the_act():
    e = _split(kid_who=("agent", "bob"))
    T.signal(e, "k2", "ACCEPT", "bob")
    e.wait_idle()
    T.signal(e, "k2", "DELIVER", "bob", result="done", self_validation="PASS")
    e.wait_idle()
    reviewer_passes(e, "k2")
    T.signal(e, "k2", "PASS", "agent")
    e.wait_idle()
    k2 = e.graph.get_task(TaskId("k2"))
    k2.deadline = datetime.now() - timedelta(minutes=5)                     # its deadline has gone by since it passed
    e.graph.save_task(k2)
    T.edit_criteria(e, "root", [criterion("a", "A"), criterion("b", "B"), criterion("c", "C")])
    e.wait_idle()
    out = T.decompose(e, "root", [{**_kid("k2", ["b", "c"], "bob"), "deadline": k2.deadline.isoformat()}],
                      accepted_risks=REGISTER)
    e.wait_idle()
    assert isinstance(out, list) and T.list_holes(e)["holes"] == []
    assert e.graph.get_state(TaskId("k2")) == State.DONE
    e.stop()


def test_a_re_admission_that_changes_nothing_leaves_the_review_standing(monkeypatch):
    monkeypatch.setenv("GFSO_L2_GATE", "1")
    e = _split(kid_who=("agent", "agent"))
    root = e.graph.get_task(TaskId("root"))
    e._storage.store_critique(TaskId("root"), json.dumps({"semantic_covered": True}))
    root.verified = True
    e.graph.save_task(root)
    T.decompose(e, "root", [_kid("k1", ["a"]), _kid("k2", ["b"])], accepted_risks=REGISTER)
    e.wait_idle()
    assert _l2_undischarged(e.graph, e.graph.get_task(TaskId("root"))) == []
    e.stop()


def test_a_project_written_by_an_older_build_has_its_checks_recomputed_on_start():
    storage = MemoryStorage()
    e = make_engine(storage)
    e.start()
    T.create_task(e, "root", {"description": "goal", "criteria": [criterion("a", "A")]}, "agent")
    e.wait_idle()
    T.decompose(e, "root", [_kid("k1", ["a"])], accepted_risks=REGISTER)
    e.wait_idle()
    e.stop()
    root = storage.get_task(TaskId("root"))
    root.criterion_mappings = ()                                             # its coverage, as an older build left it
    storage.save_task(root)
    storage.store_check_results(TaskId("root"), [CheckResult("CHECK-1:coverage", True, "")])   # …and its stale verdict
    e2 = make_engine(storage)
    e2.start()
    assert [h["check"] for h in T.list_holes(e2)["holes"]] == ["CHECK-1:coverage"]
    e2.stop()


def test_the_machine_issuer_maps_a_new_criterion_onto_a_delivered_child_keeping_its_delivery():
    e = _split(who="exec1", kid_who=("exec2", "exec2"))
    for k in ("k1", "k2"):
        T.signal(e, k, "ACCEPT", "exec2")
    e.wait_idle()
    T.signal(e, "k1", "DELIVER", "exec2", result="done", self_validation="PASS")
    T.edit_criteria(e, "root", [criterion("a", "A"), criterion("b", "B"), criterion("c", "C")], agent="exec1")
    e.wait_idle()
    ok, why = _revise_child(e, e.graph.get_task(TaskId("root")), "exec1", {"child_id": "k1", "covers": ["c"]}, "", None)
    e.wait_idle()
    assert ok, why
    k1 = e.graph.get_task(TaskId("k1"))
    assert (k1.state, k1.revisions) == (State.VALIDATING, 0) and T.list_holes(e)["holes"] == []
    e.stop()


def test_a_rebuild_reissues_a_child_for_its_contract_not_for_its_coverage():
    e = _split(kid_who=("agent", "agent"))
    k1 = e.graph.get_task(TaskId("k1"))
    dropped: list = []
    same = [(k1.id, k1.spec, AgentId("agent"))]
    assert _children_that_changed(e, TaskId("root"), same, [CriterionMapping("b", k1.id)], dropped) == []
    e.stop()


def test_a_remap_that_covers_around_a_passed_child_consumes_it():
    e = _split(kid_who=("agent", "bob"))
    T.signal(e, "k2", "ACCEPT", "bob")
    e.wait_idle()
    T.signal(e, "k2", "DELIVER", "bob", result="done", self_validation="PASS")
    e.wait_idle()
    reviewer_passes(e, "k2")
    T.signal(e, "k2", "PASS", "agent")
    e.wait_idle()
    k2 = e.graph.get_task(TaskId("k2"))
    assert not e.graph.is_consumed(k2)
    T.map_criterion(e, "root", "k1", "b")                     # b gets a responsible child it did not have (§12.14)
    e.wait_idle()
    assert e.graph.is_consumed(e.graph.get_task(TaskId("k2")))
    e.stop()


def test_the_machine_issuer_maps_two_holes_onto_two_children_in_one_reshape():
    e = _split(who="exec1", kid_who=("exec2", "exec2"))
    T.edit_criteria(e, "root", [criterion("a", "A"), criterion("b", "B"), criterion("c", "C"), criterion("d", "D")],
                    agent="exec1")
    e.wait_idle()
    root = e.graph.get_task(TaskId("root"))
    ok, why = _revise_child(e, root, "exec1", {"child_id": "k1", "covers": ["c"]}, "", None)
    assert not ok and "reshape" in why and e.graph.get_task(TaskId("k1")).revisions == 0   # refused whole, untouched
    ok, why = _reshape(e, root, "exec1", {"map": {"k1": ["c"], "k2": ["d"]}}, "", None)
    e.wait_idle()
    assert ok, why
    assert T.list_holes(e)["holes"] == [] and [e.graph.get_task(TaskId(k)).revisions for k in ("k1", "k2")] == [0, 0]
    e.stop()
