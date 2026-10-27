"""A verdict is about the result as it stood at DELIVER (§11.3), and a branch is the agents' to write: what joins the
whole is the commit the PASS accepted, not whatever the branch holds by then; and a place removed by hand does not take
its work out of the whole (security, 2026-10-27).

CONTROLS: let `_accepted_ref` return the branch name and the first test goes red; let `_has_branch` read the directory
and the third does; let `accepted_artifact` keep the last delivery instead of the accepted one and the fourth does."""
from __future__ import annotations

import shutil
from pathlib import Path

import gfso.delegate as D
from gfso import workspaces as WS
from gfso.adapters import worktrees as W
from gfso.adapters.execution import LocalExecution
from gfso.adapters.snapshots import snapshot
from gfso.engine.joins import NOT_ON_ITS_BRANCH
from gfso.core.types import Signal, State, TaskId
from tests.test_a_node_works_in_its_own_place import _Executor, _git, _in, _plan, _repo, _run
from tests.test_an_unchanged_redelivery_is_no_new_round import _fail_over
from tests.test_equal_fails_do_not_measure_kappa import _leaves
from tests.test_one_session_carries_a_scope import _entry, _free_claim


class _Engine:
    """What `_accepted_ref` asks of the engine: the tree a PASS accepted, and where to say a moved branch."""

    def __init__(self, tree, commit=None):
        self.tree, self.commit, self.said = tree, commit, []

    def accepted_delivery(self, _):
        return self.tree, self.commit

    def say_once(self, _):
        return True

    def emit_info(self, _, text):
        self.said.append(text)


class _Node:
    id = "root.a"


def _delivered(tmp_path):
    base, place = _repo(tmp_path / "ws"), tmp_path / "place"
    W.ensure(base, place, "gfso/p/a", base)
    (place / "a.txt").write_text("accepted\n")
    tree = W.commit_all(base, place, "gfso: root.a delivery", "exec-1")
    return base, place, tree, (base, place, "gfso/p/a")


def test_a_branch_moved_after_its_pass_joins_the_accepted_commit(tmp_path):
    base, place, tree, w = _delivered(tmp_path)
    (place / "a.txt").write_text("written after the verdict\n")
    W.commit_all(base, place, "later", "someone")
    e = _Engine(tree)
    ref, why = WS._accepted_ref(e, _Node(), w, LocalExecution())
    assert why is None and _git(base, "rev-parse", f"{ref}^{{tree}}").strip() == tree
    assert W.merge(base, base, ref, "join") is None
    assert (base / "a.txt").read_text() == "accepted\n" and "moved after its PASS" in e.said[0]


def test_a_branch_that_no_longer_carries_the_accepted_tree_does_not_join(tmp_path):
    base, place, tree, w = _delivered(tmp_path)
    _git(place, "reset", "-q", "--hard", "HEAD~1")
    (place / "a.txt").write_text("another history\n")
    W.commit_all(base, place, "rewritten", "someone")
    ref, why = WS._accepted_ref(_Engine(tree), _Node(), w, LocalExecution())
    assert ref is None and "no longer carries the tree its PASS accepted" in why


def test_a_place_removed_by_hand_still_has_its_work_to_join(tmp_path):
    base, place, tree, w = _delivered(tmp_path)
    shutil.rmtree(place)
    assert WS._has_branch(w, LocalExecution())
    assert not WS._has_branch((base, place, "gfso/p/nothing"), LocalExecution())


def _pass_over(e, tid, crit, tree, commit=None):
    t = e.graph.get_task(TaskId(tid))
    ex = str(t.assignee)
    assert D._signal(e, t.id, Signal.ACCEPT, ex) or t.state != State.OFFERED
    assert D._signal(e, t.id, Signal.DELIVER, ex, result="r", self_validation="PASS", artifact=tree,
                     commit=commit)
    e.wait_idle()
    key = _free_claim(e, tid)
    e.record_exec_verdict(t.id, "PASS", [], "val-1", per_criterion=[_entry(tid, crit, "pass")],
                          require_probe=True, log_at=key.log_at if key else None)
    if key:
        e.claims.end_validation(key)
    iss = str(e.graph.issuer_of(t.id))
    assert D._signal(e, t.id, Signal.PASS, "val-1") or D._signal(e, t.id, Signal.PASS, iss)
    e.wait_idle()


def test_the_accepted_artifact_is_the_delivery_the_pass_judged(tmp_path, monkeypatch):
    e, _, _ = _leaves(tmp_path, monkeypatch)
    assert e.accepted_artifact(TaskId("root.a")) is None
    _fail_over(e, "root.a", "a_ok", "tree-1")
    assert e.accepted_artifact(TaskId("root.a")) is None
    _pass_over(e, "root.a", "a_ok", "tree-2", "commit-2")
    assert e.accepted_delivery(TaskId("root.a")) == ("tree-2", "commit-2")
    e.stop()


def test_the_commit_recorded_at_deliver_joins_even_beside_another_carrying_its_tree(tmp_path):
    base, place, tree, w = _delivered(tmp_path)
    delivered = W.head(place)
    (place / "b.txt").write_text("later\n")
    W.commit_all(base, place, "later", "someone")
    (place / "b.txt").unlink()
    W.commit_all(base, place, "back to the same files", "someone")     # a newer commit carrying the accepted tree
    assert W.accepted_commit(base, "gfso/p/a", tree) != delivered
    ref, why = WS._accepted_ref(_Engine(tree, delivered), _Node(), w, LocalExecution())
    assert (ref, why) == (delivered, None)


def test_a_recorded_commit_that_does_not_carry_the_accepted_tree_joins_nothing(tmp_path):
    base, place, tree, w = _delivered(tmp_path)
    (place / "a.txt").write_text("other\n")
    W.commit_all(base, place, "other", "someone")
    ref, why = WS._accepted_ref(_Engine(tree, W.head(place)), _Node(), w, LocalExecution())
    assert ref is None and why


def test_a_part_whose_branch_moved_after_its_pass_reaches_its_whole_as_accepted(tmp_path, monkeypatch):
    """Through the joins themselves, not their helper: commits written to a PASSed part's branch before it joins do
    not reach the whole's tree; the accepted delivery does."""
    e, agents, _ = _plan(tmp_path, whole="exec-1")
    real, moved = WS._accepted_ref, []

    def _moved_first(engine, node, w, execution):
        if not moved:
            moved.append(node.id)
            (Path(w[1]) / "tampered.c").write_text("not accepted\n")
            W.commit_all(w[0], w[1], "after the verdict", "someone")
        return real(engine, node, w, execution)
    monkeypatch.setattr(WS, "_accepted_ref", _moved_first)
    sessions = {"a": _Executor("a", {"a.c": "A\n"}), "b": _Executor("b", {"b.c": "B\n"}), "par": _Executor("par", {})}
    _run(e, agents, sessions, _in(e, "par", states=(State.VALIDATING, State.DONE)))
    assert moved and {"a.c", "b.c"} <= sessions["par"].saw and "tampered.c" not in sessions["par"].saw
    e.stop()


class _Unrecorded:
    """The engine of a delivery recorded before its commit was: the accepted tree only."""

    def __init__(self, engine):
        self._e = engine

    def accepted_delivery(self, tid):
        return self._e.accepted_delivery(tid)[0], None

    def __getattr__(self, name):
        return getattr(self._e, name)


def test_a_part_whose_accepted_work_is_gone_from_its_branch_is_merged_by_nobody(tmp_path, monkeypatch):
    """Through the joins: a branch rewritten after its PASS so that it no longer carries the accepted tree — a delivery
    recorded before its commit was, so only the tree can find it — is merged neither by the join nor at the whole's
    session start, and no reader is told to merge it."""
    e, agents, _ = _plan(tmp_path, whole="exec-1")
    real, rewritten, merged = WS._accepted_ref, [], []

    def _rewritten_first(engine, node, w, execution):
        if not rewritten and str(node.id) == "a":
            rewritten.append(node.id)
            _git(w[1], "reset", "-q", "--hard", "HEAD~1")
            (Path(w[1]) / "tampered.c").write_text("not accepted\n")
            W.commit_all(w[0], w[1], "another history", "someone")
        return real(_Unrecorded(engine) if str(node.id) == "a" else engine, node, w, execution)
    real_merge = W.merge
    monkeypatch.setattr(WS, "_accepted_ref", _rewritten_first)
    monkeypatch.setattr(W, "merge", lambda base, into, ref, *a, **k: merged.append(ref) or real_merge(base, into, ref, *a, **k))
    sessions = {"a": _Executor("a", {"a.c": "A\n"}), "b": _Executor("b", {"b.c": "B\n"}), "par": _Executor("par", {})}
    _run(e, agents, sessions, _in(e, "par", states=(State.VALIDATING, State.DONE)))
    assert rewritten and "gfso/p/a" not in merged and "tampered.c" not in sessions["par"].saw
    assert all(NOT_ON_ITS_BRANCH not in why or "merge each" not in why for _, why in e.joins.unjoined_parts(
        e.graph.get_task(TaskId("par"))))
    e.stop()


def test_a_scratch_inside_the_place_is_no_copy_of_it(tmp_path):
    place = tmp_path / "work"
    place.mkdir()
    (place / "f").write_text("x\n")
    with snapshot(place, place / ".scratch" / "delivery", LocalExecution()) as copy:
        assert copy is None
    assert not (place / ".scratch" / "delivery").exists()
