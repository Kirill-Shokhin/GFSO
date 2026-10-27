"""A node's repository is written by the agents working in it, so the system's own git calls on it run where the
project's work runs — inside its container when it has one — not on the host (save `lock` and a forced `remove`
of a place the host registered); and one session's housekeeping
command cannot take every node's place away (security, 2026-10-27)."""
import shutil
import subprocess
from pathlib import Path

from gfso import reports as R
from gfso import workspaces as WS
from gfso.adapters import worktrees as W
from gfso.adapters.execution import LocalExecution
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


def test_every_system_git_call_on_a_place_goes_through_the_projects_execution(tmp_path, monkeypatch):
    base, place, ex = _repo(tmp_path / "ws"), tmp_path / "place", _Recording()
    host = []
    real = W.children.run
    monkeypatch.setattr(W.children, "run", lambda args, **k: host.append(args) or real(args, **k))
    W.ensure(base, place, "gfso/p/a", base, execution=ex)
    W.ensure(base, place, "gfso/p/a", base, execution=ex)          # reused: repaired and locked where the work runs
    W.commit_all(base, place, "gfso: a delivery", "exec-1", execution=ex)
    W.merging(base, place, execution=ex)
    W.contains(base, base, "gfso/p/a", execution=ex)
    W.remove(base, place, "gfso/p/a", execution=ex)
    assert {c[1] for c in ex.calls} >= {"worktree", "rev-parse", "merge-base", "branch", "ls-files"}
    assert not [a for a in host if a[:1] == ["git"]]


def test_a_place_survives_a_prune_run_by_any_session(tmp_path):
    base = _repo(tmp_path / "ws")
    a, b = tmp_path / "a", tmp_path / "b"
    W.ensure(base, a, "gfso/p/a", base)
    W.ensure(base, b, "gfso/p/b", base)
    # a registration whose path the pruning side cannot see — as a container sees the host's, or the host a container's
    (base / ".git" / "worktrees" / "a" / "gitdir").write_text("/nowhere/a/.git\n")
    _git(b, "worktree", "prune")
    assert (base / ".git" / "worktrees" / "a").is_dir()


def test_a_place_deleted_by_hand_is_made_again_without_pruning_the_others(tmp_path):
    base = _repo(tmp_path / "ws")
    a, b = tmp_path / "a", tmp_path / "b"
    W.ensure(base, a, "gfso/p/a", base)
    W.ensure(base, b, "gfso/p/b", base)
    (base / ".git" / "worktrees" / "b" / "gitdir").write_text("/nowhere/b/.git\n")
    shutil.rmtree(a)
    assert W.ensure(base, a, "gfso/p/a", base)
    assert (base / ".git" / "worktrees" / "b").is_dir() and (a / "README").exists()


def test_a_place_made_before_places_were_locked_is_locked_when_reused(tmp_path):
    base, place = _repo(tmp_path / "ws"), tmp_path / "place"
    W.ensure(base, place, "gfso/p/a", base)
    _git(base, "worktree", "unlock", str(place))
    assert not (base / ".git" / "worktrees" / "place" / "locked").exists()
    assert W.ensure(base, place, "gfso/p/a", base) is False
    assert (base / ".git" / "worktrees" / "place" / "locked").exists()


def test_a_place_made_again_on_its_branch_is_locked(tmp_path):
    base = _repo(tmp_path / "ws")
    a = tmp_path / "a"
    W.ensure(base, a, "gfso/p/a", base)
    shutil.rmtree(a)
    assert W.ensure(base, a, "gfso/p/a", base)
    assert (base / ".git" / "worktrees" / "a" / "locked").exists()


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
    W.ensure(base, place, "gfso/p/a", base)
    _git(base, "worktree", "unlock", str(place))
    W.ensure(base, place, "gfso/p/a", base, execution=_OtherSide())
    assert (base / ".git" / "worktrees" / "place" / "locked").exists()
    _git(base, "merge", "-q", "gfso/p/a")
    assert W.remove(base, place, "gfso/p/a", execution=_OtherSide()) and not place.exists()
