"""A node's own place in a git repository: a worktree per node, a delivery as a commit, a join as a merge.

Executors of one plan registered on one directory used to share its live tree while the dispatcher ran them in
parallel, so a validator's `make all` read a sibling's half-edited file — a torn read (§8.6): a false FAIL, or a
PASS over a tree that is not this node's delivery. A copy per validation costs the whole tree each time (77k files
measured) and still fails the build over the sibling's half-edit; a lock serializes the parallelism AUTO exists
for. A worktree shares the repository's objects, holds one node's work alone, and a commit fixes the result as it
stands at DELIVER (§11.3). Only the mechanics are here; which node works where is the graph's question
(`gfso.workspaces.node_workspace`).

Every call on one repository runs under that repository's lock: `worktree add`, a commit and a merge each take
git's own locks, and two of them racing fail on `index.lock` rather than wait. The lock orders git bookkeeping
only — sessions and validations run in their own trees in parallel.
"""
from __future__ import annotations

import os
import shutil
import threading
from pathlib import Path

from gfso.adapters import children
from gfso.config import subprocess_env

_LOCKS: dict[str, threading.RLock] = {}
_GUARD = threading.Lock()
_TOPS: dict[str, bool] = {}
_SLOW = 600          # a checkout of a large tree takes minutes; a wait past this is a hung git, not a slow one


def _key(path) -> str:
    return os.path.normcase(os.path.abspath(str(path)))


def _lock(base) -> threading.RLock:
    with _GUARD:
        return _LOCKS.setdefault(_key(base), threading.RLock())


def _git(cwd, *args, who: str = "gfso"):
    """One git call in `cwd`, as `who` — a delivery is its executor's commit, and no identity needs configuring."""
    mail = f"{who}@gfso.local"
    env = {"GIT_AUTHOR_NAME": who, "GIT_AUTHOR_EMAIL": mail, "GIT_COMMITTER_NAME": who,
           "GIT_COMMITTER_EMAIL": mail, "GIT_TERMINAL_PROMPT": "0"}
    return children.run(["git", *args], timeout=_SLOW, cwd=str(cwd), text=True, encoding="utf-8",
                        errors="replace", env=subprocess_env(keep_key=False, extra=env))


def is_repo_top(base) -> bool:
    """Is `base` the top of a git work tree with a commit to branch from? Asked once per directory per process."""
    k = _key(base)
    if k not in _TOPS:
        ok = False
        if shutil.which("git") and Path(base).is_dir():
            r = _git(base, "rev-parse", "--show-toplevel", "--verify", "HEAD")
            top = r.stdout.splitlines()[0] if r.returncode == 0 and r.stdout else ""
            ok = bool(top) and _key(top) == k
        _TOPS[k] = ok
    return _TOPS[k]


def ensure(base, place, branch: str, start_from) -> bool:
    """The worktree at `place` on `branch`, created from the HEAD of `start_from` when it is not there yet. True
    when it was created now; a place that exists is reused as it stands (a rework round continues its own tree)."""
    place = Path(place)
    with _lock(base):
        if (place / ".git").exists():
            return False
        _git(base, "worktree", "prune")          # a place deleted by hand leaves a registration behind
        if _git(base, "rev-parse", "--verify", "--quiet", f"refs/heads/{branch}").returncode == 0:
            args = ["worktree", "add", str(place), branch]
        else:
            start = _git(start_from, "rev-parse", "HEAD").stdout.strip()
            args = ["worktree", "add", "-b", branch, str(place), start]
        r = _git(base, *args)
        if r.returncode != 0:
            raise OSError(f"git worktree add {place} failed: {r.stderr.strip()}")
        return True


#: What a session leaves behind that is no one's delivery: interpreter and compiler caches. Committed, two siblings'
#: caches of one shared module collide at the join, and one left untracked in the base aborts it (critic r2,
#: 2026-10-04). The repository's own `.gitignore` decides everything else.
CACHES = ("__pycache__", "*.pyc", "*.pyo", ".pytest_cache", "*.o", "*.obj")


def commit_all(base, place, message: str, who: str) -> str:
    """Everything in the place but caches as one commit — empty or not, so every delivery has a name. Its sha."""
    with _lock(base):
        _git(place, "add", "-A", "--", ".", *(f":(exclude,glob)**/{c}" for c in CACHES),
             *(f":(exclude,glob)**/{c}/**" for c in CACHES if "*" not in c))
        r = _git(place, "commit", "--allow-empty", "--no-verify", "-q", "-m", message, who=who)
        if r.returncode != 0:
            raise OSError(f"the delivery could not be committed in {place}: {r.stderr.strip()}")
        return _git(place, "rev-parse", "HEAD").stdout.strip()


def merge(base, into, branch: str, message: str) -> str | None:
    """Join `branch` into the tree at `into`. None when joined (or already in); else why not, with the tree
    returned to where it stood — a half-merged tree would be the torn read this module exists against."""
    with _lock(base):
        r = _git(into, "merge", "--no-ff", "--no-edit", "--no-verify", "-m", message, branch)
        if r.returncode == 0:
            return None
        _git(into, "merge", "--abort")           # refused before it started (a dirty tree): nothing to abort
        return " ".join((r.stdout + " " + r.stderr).split())[:400] or f"git merge exited {r.returncode}"


def contains(base, into, branch: str) -> bool:
    """Is every commit of `branch` already in the tree at `into`?"""
    with _lock(base):
        return _git(into, "merge-base", "--is-ancestor", branch, "HEAD").returncode == 0


def remove(base, place, branch: str) -> bool:
    """Take a joined node's worktree and branch away. False when git refused (a file held open, a branch not
    joined — `branch -d` refuses to lose commits)."""
    with _lock(base):
        ok = _git(base, "worktree", "remove", "--force", str(place)).returncode == 0
        return _git(base, "branch", "-d", branch).returncode == 0 and ok
