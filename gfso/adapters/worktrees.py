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

#: a base's node places stand beside it, under this prefix and the base's name
NODES = ".gfso-nodes-"


def base_of(place: str | None) -> str | None:
    """The base a node's place is a checkout of — `_place_of` read backwards; None for a place that is no node's."""
    p = Path(place) if place else None
    if p is None or len(p.parents) < 3 or not p.parent.parent.name.startswith(NODES):
        return None
    return str(p.parent.parent.parent / p.parent.parent.name[len(NODES):])


_LOCKS: dict[str, threading.RLock] = {}
_GUARD = threading.Lock()
_TOPS: dict[str, bool] = {}
_SLOW = 600          # a checkout of a large tree takes minutes; a wait past this is a hung git, not a slow one


def _key(path) -> str:
    return os.path.normcase(os.path.abspath(str(path)))


def _lock(base) -> threading.RLock:
    with _GUARD:
        return _LOCKS.setdefault(_key(base), threading.RLock())


def git(cwd, *args, who: str = "gfso", execution=None, env: dict | None = None):
    """One git call in `cwd`, as `who` — a delivery is its executor's commit, and no identity needs configuring —
    where `execution` runs the project's work (this host when None)."""
    mail = f"{who}@gfso.local"
    env = subprocess_env(keep_key=False, extra={"GIT_AUTHOR_NAME": who, "GIT_AUTHOR_EMAIL": mail,
                                                "GIT_COMMITTER_NAME": who, "GIT_COMMITTER_EMAIL": mail,
                                                "GIT_TERMINAL_PROMPT": "0", **(env or {})})
    if execution is not None:
        return execution.run(["git", *args], cwd=str(cwd), timeout=_SLOW, env=env)
    return children.run(["git", *args], timeout=_SLOW, cwd=str(cwd), text=True, encoding="utf-8",
                        errors="replace", env=env)


def _relative_gitfile(place: Path, execution=None) -> None:
    """A worktree's `.git` names its gitdir by a path relative to the place: written absolute (`C:/…`), the same tree
    is no repository inside a container that mounts it elsewhere (probe P2). Hidden on Windows, so rewritten in place."""
    with open(place / ".git", "r+", encoding="utf-8") as f:
        gitdir = f.read().split("gitdir:", 1)[1].strip()
        gitdir = execution.to_outside(gitdir) if execution is not None else gitdir
        f.seek(0)
        f.write("gitdir: " + Path(os.path.relpath(gitdir, place)).as_posix() + "\n")
        f.truncate()


def checks_out_crlf(base) -> bool:
    """Does the repository at `base` check its files out with CRLF (`core.autocrlf=true`, any level that applies)?"""
    return is_repo_top(base) and git(base, "config", "--get", "core.autocrlf").stdout.strip().lower() == "true"


def is_repo_top(base) -> bool:
    """Is `base` the top of a git work tree with a commit to branch from? Asked once per directory per process."""
    k = _key(base)
    if k not in _TOPS:
        ok = False
        if shutil.which("git") and Path(base).is_dir():
            r = git(base, "rev-parse", "--show-toplevel", "--verify", "HEAD")
            top = r.stdout.splitlines()[0] if r.returncode == 0 and r.stdout else ""
            ok = bool(top) and _key(top) == k
        _TOPS[k] = ok
    return _TOPS[k]


def ensure(base, place, branch: str, start_from, execution=None) -> bool:
    """The worktree at `place` on `branch`, created from the HEAD of `start_from` when it is not there yet. True
    when it was created now; a place that exists is reused as it stands (a rework round continues its own tree).

    Run where the project's work runs: the repository is the agents' to write, so the host does not act on it. LOCKED,
    so no session's `worktree prune` takes every node's registration away, and with no prune of its own: `--force`
    re-adds over the registration a place deleted by hand left behind, touching no other node's."""
    place = Path(place)
    with _lock(base):
        if (place / ".git").exists():
            # …made before places were locked: locked now
            _by_registration(base, ["worktree", "lock", str(place)], execution)
            return False
        if git(base, "rev-parse", "--verify", "--quiet", f"refs/heads/{branch}", execution=execution).returncode == 0:
            args = ["worktree", "add", "--lock", "--force", "--force", str(place), branch]
        else:
            start = git(start_from, "rev-parse", "HEAD", execution=execution).stdout.strip()
            args = ["worktree", "add", "--lock", "--force", "--force", "-b", branch, str(place), start]
        r = git(base, *args, execution=execution)
        if r.returncode != 0:
            raise OSError(f"git worktree add {place} failed: {r.stderr.strip()}")
        _relative_gitfile(place, execution)
        return True


#: What a session leaves behind that is no one's delivery: interpreter and compiler caches. Committed, two siblings'
#: caches of one shared module collide at the join, and one left untracked in the base aborts it (critic r2,
#: 2026-10-04). The repository's own `.gitignore` decides everything else.
CACHES = ("__pycache__", "*.pyc", "*.pyo", ".pytest_cache", "*.o", "*.obj")


def commit_all(base, place, message: str, who: str, execution=None) -> str:
    """Everything in the place but caches as one commit — empty or not, so every delivery has a name. Its TREE: the
    same files are the same id whatever commit carries them, so a re-delivery of an unchanged result reads as one
    (four FAILs over one tree read as four attempts and split a leaf, GB_sql_database_tngo2o700 root.joins). Taken
    where the work was made: host git cannot index a symlink made inside a container (probe P5)."""
    with _lock(base):
        git(place, "add", "-A", "--", ".", *(f":(exclude,glob)**/{c}" for c in CACHES),
             *(f":(exclude,glob)**/{c}/**" for c in CACHES if "*" not in c), execution=execution)
        r = git(place, "commit", "--allow-empty", "--no-verify", "-q", "-m", message, who=who, execution=execution)
        if r.returncode != 0:
            raise OSError(f"the delivery could not be committed in {place}: {r.stderr.strip()}")
        return git(place, "rev-parse", "HEAD^{tree}", execution=execution).stdout.strip()


def head(place, execution=None) -> str | None:
    """The commit the tree at `place` stands on, or None."""
    return git(place, "rev-parse", "HEAD", execution=execution).stdout.strip() or None


def merge(base, into, branch: str, message: str, execution=None) -> str | None:
    """Join `branch` into the tree at `into`. None when joined (or already in); else why not, with the tree
    returned to where it stood — a half-merged tree would be the torn read this module exists against. Written where the
    work runs, so a symlink a part made is checked out as one."""
    with _lock(base):
        r = git(into, "merge", "--no-ff", "--no-edit", "--no-verify", "-m", message, branch, execution=execution)
        if r.returncode == 0:
            return None
        git(into, "merge", "--abort", execution=execution)   # refused before it started (a dirty tree): nothing to abort
        return " ".join((r.stdout + " " + r.stderr).split())[:400] or f"git merge exited {r.returncode}"


def accepted_commit(base, branch: str, tree: str, execution=None) -> str | None:
    """The newest commit of `branch` whose tree is `tree` — the delivery a verdict accepted, wherever the branch has
    moved since — or None when the branch carries no such commit."""
    with _lock(base):
        r = git(base, "log", "--format=%H %T", branch, "--", execution=execution)
    return next((c for c, t in (ln.split() for ln in r.stdout.splitlines() if ln.count(" ") == 1) if t == tree), None)


def merging(base, place, execution=None) -> bool:
    """Is a merge left unfinished in the tree at `place` — begun and not concluded, or with paths still unmerged?"""
    with _lock(base):
        return (git(place, "rev-parse", "-q", "--verify", "MERGE_HEAD", execution=execution).returncode == 0
                or bool(git(place, "ls-files", "-u", execution=execution).stdout.strip()))


def contains(base, into, branch: str, execution=None) -> bool:
    """Is every commit of `branch` already in the tree at `into`?"""
    with _lock(base):
        return git(into, "merge-base", "--is-ancestor", branch, "HEAD", execution=execution).returncode == 0


def _by_registration(base, args: list, execution):
    """A worktree command that finds the place by the path it was registered under: where the work runs, else — for
    a place registered on the host before system git moved into the execution, which the execution cannot match
    ("is not a working tree") — on the host, for these two commands only (`lock`, a forced `remove`), which
    read no index and run nothing the agents wrote."""
    r = git(base, *args, execution=execution)
    if r.returncode and execution is not None and "is not a working tree" in (r.stderr or ""):
        r = git(base, *args)
    return r


def remove(base, place, branch: str, execution=None) -> bool:
    """Take a joined node's worktree and branch away (twice forced: the place is locked). False when git refused (a
    file held open, a branch not joined — `branch -d` refuses to lose commits)."""
    with _lock(base):
        ok = _by_registration(base, ["worktree", "remove", "--force", "--force", str(place)], execution).returncode == 0
        return git(base, "branch", "-d", branch, execution=execution).returncode == 0 and ok
