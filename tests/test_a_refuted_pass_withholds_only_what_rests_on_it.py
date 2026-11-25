"""A refuted pass withholds what rests on it, and only while its reopen is open (§12.8, §12.14, §15.4 q_V's later fail).

A node standing at PASS whose own current record is a later FAIL answered the WHOLE graph with no step: one such
record in an unrelated branch took every holder's work out of `next_steps`, and the stop hook, which holds a console
while it owes moves, let each one go (dev graph, 2026-11-23). The record stays on the log for good, so it cannot be a
state that ends either: held on it past consumption, a console would be held with no exit. The rule: while the part
can be reopened, the steps that would consume it wait (its parent's DELIVER, a Dep consumer's start) and a PASS over it
becomes the FAIL that signs over nothing, its reopen ONE step of the party who makes it; past its reopen nothing waits
on it — the re-decomposition is a move its issuer may make, named as data; COMPLETE is never answered over one the split
has not covered around. Every other step stays. The hold is read on each answer: it holds a console on a move it can
make now and lets it go once the move is made.
"""
from __future__ import annotations

import pytest

from gfso import tools as T
from gfso.core.types import AgentId, State, TaskId
from gfso.driver import _frontier_line
from gfso.hold import own_moves
from tests.support import criterion, make_engine, REGISTER, reviewer_passes
from gfso.engine.closures import refuted_passes


@pytest.fixture(autouse=True)
def _no_plan_gate(monkeypatch):
    monkeypatch.setenv("GFSO_L2_GATE", "0")


@pytest.fixture
def e():
    e = make_engine()
    e.start()
    yield e
    e.stop()


def _child(tid, c, by="w"):
    return {"task_id": tid, "spec": {"description": tid, "criteria": [criterion(c, c.upper())]},
            "assignee": by, "covers": [c]}


def _a_root(e, crits, kids, by=None):
    """`root` held by boss, split into `kids` ({id: criterion}), each held by `by[id]` or w."""
    T.create_task(e, "root", {"description": "goal", "criteria": [criterion(c, c.upper()) for c in crits],
                              "accepted_risks": REGISTER}, assignee="boss")
    e.wait_idle()
    T.signal(e, "root", "ACCEPT", "boss")
    T.decompose(e, "root", [_child(k, c, (by or {}).get(k, "w")) for k, c in kids.items()], accepted_risks=REGISTER)
    e.wait_idle()


def _passed(e, tid, issuer, by="w"):
    if e.graph.get_state(TaskId(tid)) == State.OFFERED:
        T.signal(e, tid, "ACCEPT", by)
    T.signal(e, tid, "DELIVER", by, result="built it")
    reviewer_passes(e, TaskId(tid), reviewer="validator")
    T.signal(e, tid, "PASS", issuer)
    e.wait_idle()
    assert e.graph.get_state(TaskId(tid)) == State.DONE


def _refuted(e, tid):
    """The instrument's FAIL landing after the signature: q_V's discovery carrier, the node DONE and its V standing."""
    c = e.graph.get_task(TaskId(tid)).spec.criteria[0].name
    e.record_exec_verdict(TaskId(tid), "FAIL", [c], "instrument",
                          per_criterion=[{"criterion": c, "verdict": "fail", "evidence": f"ran `check {c}`: it failed",
                                          "behaviours": [f"{c} holds"]}])
    e.wait_idle()
    assert tid in refuted_passes(e)


def _on(out, tid, *actions):
    return [s for s in out["steps"] if s["task_id"] == tid and (not actions or s["action"] in actions)]


def _held_on(e, who):
    """The steps the stop hook holds `who`'s console on."""
    return own_moves(T.next_steps(e, actor=who))


def test_unconsumed_the_parent_does_not_aggregate_over_it_and_its_reopen_is_one_step_of_its_issuer(e):
    _a_root(e, ["a", "b"], {"root.c0": "a", "root.c1": "b"})
    _passed(e, "root.c0", "boss")
    _passed(e, "root.c1", "boss")
    _refuted(e, "root.c1")

    out = e.next_steps()
    assert out["complete"] is False and out["refuted_passes"] == ["root.c1"]
    assert not _on(out, "root", "deliver", "validate"), (
        "the parent's aggregate stood on the frontier over a part its own record refutes — its DELIVER consumes it")
    recovery = _on(out, "root", "revise")
    assert len(recovery) == 1 and "reopen('root.c1')" in recovery[0]["directive"]
    assert recovery[0]["signed_by"] == "boss", "the recovery is the refuted part's issuer's, Del(parent)"
    assert "reopen('root.c1')" in out["refuted_passes_note"]
    scoped = e.next_steps(TaskId("root"))
    assert scoped["refuted_passes"] == ["root.c1"] and not _on(scoped, "root", "deliver", "validate")
    assert [s["task_id"] for s in _held_on(e, "boss")] == ["root"], "the hold let its console go with the reopen owed"

    e.reopen(TaskId("root.c1"), AgentId("boss"))
    e.wait_idle()
    assert e.graph.get_state(TaskId("root.c1")) == State.OFFERED
    assert not e.next_steps().get("refuted_passes")
    assert not [s for s in _held_on(e, "boss") if s["directive"].startswith("RECOVER")], (
        "the hold looped on a reopen already made")


def test_a_refuted_part_in_one_branch_leaves_the_other_branchs_moves_in_place(e):
    _a_root(e, ["a", "b"], {"root.x": "a", "root.y": "b"}, by={"root.x": "boss"})
    T.signal(e, "root.x", "ACCEPT", "boss")
    T.decompose(e, "root.x", [_child("root.x.0", "a"), _child("root.x.1", "a")], accepted_risks=REGISTER)
    e.wait_idle()
    _passed(e, "root.x.0", "boss")
    _refuted(e, "root.x.0")
    T.signal(e, "root.y", "ACCEPT", "w")
    e.wait_idle()

    out = T.next_steps(e, actor="w")
    assert out["complete"] is False and out["refuted_passes"] == ["root.x.0"]
    assert "root.y" in [s["task_id"] for s in own_moves(out)], (
        "a refuted record in another branch took this holder's work off the frontier, and his console stops")
    assert _on(out, "root.x.1"), "a sibling of the refuted part keeps its step"


def test_unconsumed_a_dep_consumer_waits_on_its_recovery(e):
    """§12.14's Dep leg: a consumer in work after the pass consumes it, so its start is what rests on it."""
    _a_root(e, ["a", "b"], {"root.c0": "a", "root.c1": "b"})
    T.add_dependency(e, "root.c0", "root.c1", glue="c1 reads what c0 built", agent="boss")
    e.wait_idle()
    _passed(e, "root.c0", "boss")
    _refuted(e, "root.c0")

    out = e.next_steps()
    assert not _on(out, "root.c1"), (
        "the consumer of a refuted pass was offered its start — its ACCEPT consumes the pass, and the reopen is refused")
    wait = [w for w in out.get("waiting", ()) if w["task_id"] == "root.c1"]
    assert wait and list(wait[0]["waits_on"]) == ["root.c0"], "a consumer held back is said as a wait, never silence"
    assert "reopen('root.c0')" in wait[0]["opens_with"]
    assert "reopen('root.c0')" in _on(out, "root", "revise")[0]["directive"]
    assert not _held_on(e, "w"), "the consumer's holder was held on a start the frontier withholds"
    assert [s["task_id"] for s in _held_on(e, "boss")] == ["root"]

    e.reopen(TaskId("root.c0"), AgentId("boss"))
    e.wait_idle()
    assert e.graph.get_state(TaskId("root.c0")) == State.OFFERED
    assert not [s for s in _held_on(e, "boss") if s["directive"].startswith("RECOVER")]


def test_consumed_by_a_dep_consumer_nothing_waits_and_the_parents_deliver_is_offered(e):
    """Past its reopen the record withholds nothing: held on it, a console would be held with no exit (the record stays
    for good); the re-decomposition is named as data, a move its issuer may make."""
    _a_root(e, ["a", "b"], {"root.c0": "a", "root.c1": "b"})
    T.add_dependency(e, "root.c0", "root.c1", glue="c1 reads what c0 built", agent="boss")
    e.wait_idle()
    _passed(e, "root.c0", "boss")
    T.signal(e, "root.c1", "ACCEPT", "w")
    e.wait_idle()
    _refuted(e, "root.c0")

    out = e.next_steps()
    assert _on(out, "root.c1", "execute"), "a consumer already building on the pass lost its step"
    assert not _on(out, "root", "revise"), "a reopen the gate refuses stood as a step"
    assert "re-decomposition of 'root' around 'root.c0'" in out["refuted_passes_note"]
    assert [s["task_id"] for s in _held_on(e, "w")] == ["root.c1"] and not _held_on(e, "boss"), (
        "a console was held on the refuted record past its reopen")

    _passed(e, "root.c1", "boss")
    agg = _on(e.next_steps(), "root", "deliver")
    assert agg and "root.c0" in agg[0]["directive"], "the parent's DELIVER is offered, the record said beside it"


def test_consumed_by_its_parents_deliver_the_parents_verdict_is_offered_both_ways(e):
    _a_root(e, ["a", "b"], {"root.c0": "a", "root.c1": "b"})
    _passed(e, "root.c0", "boss")
    _passed(e, "root.c1", "boss")
    T.signal(e, "root", "DELIVER", "boss", result="integrated")
    e.wait_idle()
    _refuted(e, "root.c1")

    out = e.next_steps()
    on_root = _on(out, "root", "validate")
    assert on_root and "SIGN NO PASS" not in on_root[0]["directive"], (
        "past consumption the parent's check reads its delivered result (§12.8): its PASS is not withheld")
    assert "root.c1" in on_root[0]["directive"] and not _on(out, "root", "revise")


def test_under_settled_parents_the_reopen_is_the_nearest_live_holders(e):
    """A part under a DONE whole is not reopened (§12.7) and a DONE whole is not re-split: the one move is the whole's
    own reopen, by its issuer — and the whole reopened does not read its refuted part as passed."""
    _a_root(e, ["a", "b"], {"root.x": "a", "root.y": "b"}, by={"root.x": "mid"})
    T.signal(e, "root.x", "ACCEPT", "mid")
    T.decompose(e, "root.x", [_child("root.x.0", "a"), _child("root.x.1", "a")], accepted_risks=REGISTER)
    e.wait_idle()
    _passed(e, "root.x.0", "mid")
    _passed(e, "root.x.1", "mid")
    _passed(e, "root.x", "boss", by="mid")
    _refuted(e, "root.x.0")

    out = e.next_steps()
    assert not _on(out, "root.x"), "the recovery stood on a settled whole, offering its holder moves the doors refuse"
    on_root = _on(out, "root", "revise")
    assert on_root and "reopen('root.x')" in on_root[0]["directive"] and on_root[0]["signed_by"] == "boss"
    assert not _held_on(e, "mid") and [s["task_id"] for s in _held_on(e, "boss")] == ["root"]

    e.reopen(TaskId("root.x"), AgentId("boss"))
    e.wait_idle()
    take = _on(e.next_steps(), "root.x", "accept")
    assert take and "every part passed" not in take[0]["directive"], "a refuted part read as passed to its whole"
    assert "root.x.0" in take[0]["directive"]


def test_a_whole_validating_over_a_refuted_part_is_offered_its_fail_not_its_pass(e):
    """The whole delivered before the part settled, so the part is not consumed: a PASS over it would settle the whole
    it is reopened under; its FAIL signs over nothing (§8.4) and stays — never the verdict step withheld wholesale."""
    _a_root(e, ["a", "b"], {"root.c0": "a", "root.c1": "b"})
    _passed(e, "root.c0", "boss")
    T.signal(e, "root.c1", "ACCEPT", "w")
    T.signal(e, "root", "DELIVER", "boss", result="integrated early")
    e.wait_idle()
    _passed(e, "root.c1", "boss")
    _refuted(e, "root.c1")
    assert e.graph.get_state(TaskId("root")) == State.VALIDATING

    out = e.next_steps()
    verdict = _on(out, "root", "validate")
    assert len(verdict) == 1 and verdict[0]["directive"].startswith("SIGN NO PASS")
    assert "'FAIL', failed_criteria=['b']" in verdict[0]["directive"]
    assert "reopen('root.c1')" in _on(out, "root", "revise")[0]["directive"]

    T.signal(e, "root", "FAIL", e.graph.issuer_of(TaskId("root")), failed_criteria=["b"])
    e.wait_idle()
    assert e.graph.get_state(TaskId("root")) == State.REWORKING
    assert "reopen('root.c1')" in _on(e.next_steps(), "root", "revise")[0]["directive"], "its FAIL shut the reopen"


def test_status_reads_a_refuted_pass_below_an_open_root_and_over_a_settled_one(e):
    _a_root(e, ["a", "b"], {"root.c0": "a", "root.c1": "b"})
    _passed(e, "root.c0", "boss")
    _passed(e, "root.c1", "boss")
    _refuted(e, "root.c1")
    line = _frontier_line(e.next_steps())
    assert "step(s) for you" in line and "root.c1" in line


def test_complete_is_never_answered_over_an_uncovered_refuted_pass_and_is_over_one_covered_around(e):
    _a_root(e, ["a", "b"], {"root.c0": "a", "root.c1": "b"})
    _passed(e, "root.c0", "boss")
    _passed(e, "root.c1", "boss")
    T.signal(e, "root", "DELIVER", "boss", result="integrated")
    e.wait_idle()
    reviewer_passes(e, TaskId("root"), reviewer="validator")
    T.signal(e, "root", "PASS", e.graph.issuer_of(TaskId("root")))
    e.wait_idle()
    assert e.next_steps()["complete"] is True
    _refuted(e, "root.c1")

    for out in (e.next_steps(), e.next_steps(TaskId("root"))):
        assert out["complete"] is False and out["refuted_passes"] == ["root.c1"] and not out["steps"]
        assert "reopen('root')" in out["directive"], "the settled goal's own reopen is the recovery"
    assert _frontier_line(e.next_steps()).startswith("frontier: NOT COMPLETE")

    e.reopen(TaskId("root"), AgentId(str(e.graph.issuer_of(TaskId("root")))))
    e.wait_idle()
    T.signal(e, "root", "ACCEPT", "boss")
    T.decompose(e, "root", [_child("root.c0", "a"), _child("root.c1", "b"), _child("root.c2", "b")],
                accepted_risks=REGISTER)
    e.wait_idle()
    assert refuted_passes(e) == ["root.c1"], "the record stays on the log"
    _passed(e, "root.c2", "boss")
    T.signal(e, "root", "DELIVER", "boss", result="integrated around root.c1")
    e.wait_idle()
    reviewer_passes(e, TaskId("root"), reviewer="validator")
    T.signal(e, "root", "PASS", e.graph.issuer_of(TaskId("root")))
    e.wait_idle()
    assert e.next_steps()["complete"] is True, "a refuted pass the split covered around held COMPLETE back for good"
