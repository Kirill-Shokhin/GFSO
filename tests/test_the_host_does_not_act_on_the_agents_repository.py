"""A node's repository is written by the agents working in it, so the system's own git calls on it run where the
project's work runs — inside its container when it has one — not on the host (save `lock` and a forced `remove`
of a place the host registered); and one session's housekeeping
command cannot take every node's place away (security, 2026-10-27)."""
import shutil
import subprocess

import pytest
from pathlib import Path

from gfso import reports as R
from gfso import workspaces as WS
from gfso.adapters import worktrees as W
from gfso.adapters.execution import LocalExecution
from gfso.adapters.snapshots import snapshot
from gfso.core.types import State
from tests.test_a_node_works_in_its_own_place import _Executor, _in, _plan, _run


def _git(cwd, *args) -> str:
    return subprocess.run(["git", *args], cwd=cwd, capture_output=True, text=True, check=True).stdout


def _repo(path: Path) -> Path:
    path.mkdir(parents=True)
    _git(path, "init", "-q")
    (path / "README").write_text("x\n")
    _git(path, "add", "-A")
    _git(path, "-c", "user.name=t", "-c", "user.email=t@t", "commit", "-q", "-m", "starter")
    return path


class _Recording(LocalExecution):
    """This host, but every call counted — the stand-in for a container."""

    def __init__(self):
        self.calls = []

    def run(self, args, *, cwd, timeout, env=None):
        self.calls.append(list(args))
        return super().run(args, cwd=cwd, timeout=timeout, env=env)


def _legacy(base, place, branch):
    """A place made as a worktree of the base, as every place was before each node had a repository of its own."""
    _git(base, "worktree", "add", "-q", "-b", branch, str(place))


def test_every_system_git_call_on_a_place_goes_through_the_projects_execution(tmp_path, monkeypatch):
    base, place, ex = _repo(tmp_path / "ws"), tmp_path / "place", _Recording()
    host = []
    real = W.children.run
    monkeypatch.setattr(W.children, "run", lambda args, **k: host.append(args) or real(args, **k))
    W.ensure(base, place, "gfso/p/a", base, execution=ex)
    W.ensure(base, place, "gfso/p/a", base, execution=ex)          # reused as it stands
    W.commit_all(base, place, "gfso: a delivery", "exec-1", execution=ex, branch="gfso/p/a")
    W.merging(base, place, execution=ex)
    W.contains(base, base, "gfso/p/a", execution=ex)
    W.remove(base, place, "gfso/p/a", execution=ex)
    gits = [c for c in ex.calls if "git" in str(c[0]) and "python" not in str(c[0])]
    assert gits and all(c[1:1 + len(W.APART)] == list(W.APART) for c in gits), "no hook, no fsmonitor, the repo's config alone"
    assert {c[1 + len(W.APART)] for c in gits} >= {"init", "checkout", "bundle", "update-ref", "rev-parse",
                                                      "merge-base", "branch", "ls-files"}
    assert not [a for a in host if a[:1] == ["git"]]


def test_a_place_is_a_repository_of_its_own_whose_refs_no_other_place_writes(tmp_path):
    """A worktree wrote the base's refs and registrations, so one session's `git worktree prune` or a commit to a
    neighbour's branch reached every node; a clone holds its own refs and borrows only the base's objects."""
    base = _repo(tmp_path / "ws")
    a, b = tmp_path / "a", tmp_path / "b"
    W.ensure(base, a, "gfso/p/a", base)
    W.ensure(base, b, "gfso/p/b", base)
    assert W.is_clone(a) and _git(base, "worktree", "list", "--porcelain").count("worktree ") == 1
    _git(b, "worktree", "prune")
    _git(b, "branch", "-f", "gfso/p/a", "HEAD")                    # b's own ref of that name, not the base's
    (a / "x.c").write_text("x\n")
    W.commit_all(base, a, "gfso: a delivery", "exec-1", branch="gfso/p/a")
    assert _git(base, "log", "-1", "--format=%s", "gfso/p/a").strip() == "gfso: a delivery"
    assert "origin" not in _git(a, "remote")                      # nothing in the place names the base to push to


def test_a_place_deleted_by_hand_is_made_again_from_its_branch(tmp_path):
    base = _repo(tmp_path / "ws")
    a, b = tmp_path / "a", tmp_path / "b"
    W.ensure(base, a, "gfso/p/a", base)
    W.ensure(base, b, "gfso/p/b", base)
    (a / "a.c").write_text("A\n")
    W.commit_all(base, a, "gfso: a delivery", "exec-1", branch="gfso/p/a")
    LocalExecution().remove_tree(a)
    assert W.ensure(base, a, "gfso/p/a", base)
    assert (a / "a.c").read_text() == "A\n" and W.is_clone(b)


def test_a_place_made_as_a_worktree_before_is_locked_when_reused(tmp_path):
    base, place = _repo(tmp_path / "ws"), tmp_path / "place"
    _legacy(base, place, "gfso/p/a")
    assert not (base / ".git" / "worktrees" / "place" / "locked").exists()
    assert W.ensure(base, place, "gfso/p/a", base) is False
    assert (base / ".git" / "worktrees" / "place" / "locked").exists()


def test_a_whole_run_calls_no_git_on_the_host_inside_a_place(tmp_path, monkeypatch):
    """Where the calls are wired, not only the adapter: a project's places see git only through its execution."""
    e, agents, base = _plan(tmp_path, whole="exec-1")
    ex, host = _Recording(), []
    for mod in (WS, R):
        monkeypatch.setattr(mod, "execution_of", lambda *a, **k: ex)
    real = W.children.run
    monkeypatch.setattr(W.children, "run", lambda args, **k: host.append((args, k.get("cwd"))) or real(args, **k))
    sessions = {"a": _Executor("a", {"a.c": "A\n"}), "b": _Executor("b", {"b.c": "B\n"}), "par": _Executor("par", {})}
    _run(e, agents, sessions, _in(e, "par", states=(State.VALIDATING, State.DONE)))
    assert ex.calls and not [a for a, cwd in host if a[:1] == ["git"] and ".gfso-nodes-" in str(cwd)]
    e.stop()


class _OtherSide(_Recording):
    """A container: it cannot match a place the host registered under the host's path."""

    def run(self, args, *, cwd, timeout, env=None):
        if args[1:3] in (["worktree", "lock"], ["worktree", "remove"]):
            self.calls.append(list(args))
            return subprocess.CompletedProcess(args, 128, "", "fatal: '/x' is not a working tree")
        return super().run(args, cwd=cwd, timeout=timeout, env=env)


def test_a_place_the_host_registered_is_still_locked_and_removed(tmp_path):
    """Places made before system git moved into the execution: their registration names the host's path, so the two
    commands that find a place by it fall back to the host — the cleanup at the root's PASS works as it did."""
    base, place = _repo(tmp_path / "ws"), tmp_path / "place"
    _legacy(base, place, "gfso/p/a")
    W.ensure(base, place, "gfso/p/a", base, execution=_OtherSide())
    assert (base / ".git" / "worktrees" / "place" / "locked").exists()
    _git(base, "merge", "-q", "gfso/p/a")
    assert W.remove(base, place, "gfso/p/a", execution=_OtherSide()) and not place.exists()


def test_a_worktree_place_deleted_by_hand_is_made_again_and_delivers(tmp_path):
    """Its registration, locked, still claims the branch as checked out; the clone made in its place delivers anyway."""
    base, place = _repo(tmp_path / "ws"), tmp_path / "a"
    _legacy(base, place, "gfso/p/a")
    _git(base, "worktree", "lock", str(place))
    LocalExecution().remove_tree(place)
    assert W.ensure(base, place, "gfso/p/a", base) and W.is_clone(place)
    (place / "a.c").write_text("A\n")
    W.commit_all(base, place, "gfso: a delivery", "exec-1", branch="gfso/p/a")
    assert _git(base, "log", "-1", "--format=%s", "gfso/p/a").strip() == "gfso: a delivery"
    _git(base, "merge", "-q", "gfso/p/a")
    assert W.remove(base, place, "gfso/p/a") and "gfso/p/a" not in _git(base, "branch")   # the old claim goes too


def test_a_start_that_fails_leaves_no_place_to_reuse(tmp_path):
    base, place = _repo(tmp_path / "ws"), tmp_path / "a"
    with pytest.raises(OSError):
        W.ensure(base, place, "gfso/p/a", tmp_path / "no-such-parent")
    assert not place.exists()


def test_a_place_goes_at_the_end_only_when_all_it_holds_is_in_the_base(tmp_path):
    base = _repo(tmp_path / "ws")
    a, b = tmp_path / "a", tmp_path / "b"
    W.ensure(base, a, "gfso/p/a", base)
    W.ensure(base, b, "gfso/p/b", base)
    (a / "late.c").write_text("after its delivery\n")
    _git(a, "add", "-A")
    _git(a, "-c", "user.name=t", "-c", "user.email=t@t", "commit", "-q", "-m", "never taken back")
    assert not W.settled(base, a, "gfso/p/a")                        # a commit the base never took: kept, named
    assert W.settled(base, b, "gfso/p/b") and W.remove(base, b, "gfso/p/b") and not b.exists()   # nothing new: goes


def test_a_place_keeps_out_what_the_base_keeps_out_and_reads_its_line_endings(tmp_path):
    base = _repo(tmp_path / "ws")
    _git(base, "config", "core.autocrlf", "false")
    (base / ".git" / "info").mkdir(exist_ok=True)
    (base / ".git" / "info" / "exclude").write_text("secret.env\n")
    place = tmp_path / "a"
    W.ensure(base, place, "gfso/p/a", base)
    (place / "secret.env").write_text("x\n")
    (place / "a.c").write_text("A\n")
    W.commit_all(base, place, "gfso: a delivery", "exec-1", branch="gfso/p/a")
    assert _git(base, "ls-tree", "-r", "--name-only", "gfso/p/a").split() == ["README", "a.c"]
    assert _git(place, "config", "--get", "core.autocrlf").strip() == "false"


def test_a_copy_of_a_place_at_its_real_depth_still_borrows_the_base_objects(tmp_path):
    """A validator's copy stands deeper than the place; borrowed by the place's relative path, its objects were gone."""
    base = _repo(tmp_path / "ws")
    (base / "src").mkdir()
    (base / "src" / "lib.c").write_text("int a;\n")                  # a subtree only the base's objects hold
    _git(base, "add", "-A")
    _git(base, "-c", "user.name=t", "-c", "user.email=t@t", "commit", "-q", "-m", "nested")
    nodes = tmp_path / ".gfso-nodes-ws" / "p"
    place = nodes / "a"
    W.ensure(base, place, "gfso/p/a", base)
    at = nodes / ".gfso-scratch-a" / "r" / "batch1" / "delivery"
    edits: list = []
    with snapshot(place, at, LocalExecution(), edits) as copy:
        (Path(copy) / "src" / "lib.c").write_text("int b;\n")
    assert edits == ["src/lib.c"]
