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
from gfso.adapters.execution import LocalExecution
from gfso.core.types import HOST

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
    env = subprocess_env(extra={"GIT_AUTHOR_NAME": who, "GIT_AUTHOR_EMAIL": mail,
                                                "GIT_COMMITTER_NAME": who, "GIT_COMMITTER_EMAIL": mail,
                                                "GIT_TERMINAL_PROMPT": "0", **(env or {})})
    if execution is not None:
        return execution.run(["git", *args], cwd=str(cwd), timeout=_SLOW, env=env)
    return children.run(["git", *args], timeout=_SLOW, cwd=str(cwd), text=True, encoding="utf-8",
                        errors="replace", env=env)


def _fs(execution):
    """Where a place's files are reached: its execution, this host where none is named."""
    return execution if execution is not None else LocalExecution()


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


def is_clone(place, execution=None) -> bool:
    """Is `place` a node's repository of its own (a clone of the base), not a worktree of the base's?"""
    return _fs(execution).files.is_dir(str(Path(place) / ".git"))


def relative_alternates(objects: Path, base_objects: Path, execution=None) -> None:
    """A clone borrows the base's objects by a path relative to its own `objects/`: the same files read the same from
    the host and from a container that mounts them elsewhere (an absolute path is one side's only)."""
    _fs(execution).files.write_bytes(str(objects / "info" / "alternates"),   # …LF alone: a CR is read as part of the path
                                     (Path(os.path.relpath(base_objects, objects)).as_posix() + "\n").encode())


def ensure(base, place, branch: str, start_from, execution=None) -> bool:
    """The node's own repository at `place` on `branch`, started from the HEAD of `start_from` when it is not there
    yet. True when it was made now; a place that exists is reused as it stands (a rework round continues its own tree).

    A REPOSITORY OF ITS OWN, not a worktree of the base's: a worktree writes the base's refs, objects and
    registrations, so a session in one place could move or break every other node's (NODE_ISOLATION_RESEARCH §6, G).
    The clone reads the base's objects (`--shared`, relative alternates) and holds its own refs and index; the system
    brings in what it needs (`bring`) and takes the node's branch back at DELIVER (`commit_all`). Run where the
    project's work runs. A place made as a worktree before this keeps working as one, locked."""
    place = Path(place)
    with _lock(base):
        if is_clone(place, execution):
            return False
        if _fs(execution).files.exists(str(place / ".git")):
            _by_registration(base, ["worktree", "lock", str(place)], execution)
            return False
        # …the base's own settings, as a worktree had them: line endings, links, attributes (a clone reads only its own)
        own = [a for k in INHERITED for v in [git(base, "config", "--local", "--get", k, execution=execution)
                                                .stdout.strip()] if v for a in ("-c", f"{k}={v}")]
        r = git(base, "clone", "--shared", "--no-checkout", "-q", *own, str(base), str(place), execution=execution)
        if r.returncode != 0:
            raise OSError(f"git clone {place} failed: {r.stderr.strip()}")
        try:
            _start(base, place, branch, start_from, execution)
        except Exception:   # …a half-made place would be reused as it stands, empty, and its emptiness delivered
            _fs(execution).remove_tree(str(place))
            raise
        return True


#: the base's local settings a node's own repository takes on: what a worktree of the base read from it
INHERITED = ("core.autocrlf", "core.eol", "core.symlinks", "core.filemode", "core.ignorecase")


def _start(base, place: Path, branch: str, start_from, execution) -> None:
    relative_alternates(place / ".git" / "objects", Path(base) / ".git" / "objects", execution)
    for name in ("exclude", "attributes"):        # what the base keeps out of its commits stays out of the node's
        if (kept := HOST.read_bytes(str(Path(base) / ".git" / "info" / name))) is not None:    # the base: the host's
            _fs(execution).files.write_bytes(str(place / ".git" / "info" / name), kept)
    git(place, "remote", "remove", "origin", execution=execution)        # nothing in the place names the base to push to
    if git(base, "rev-parse", "--verify", "--quiet", f"refs/heads/{branch}", execution=execution).returncode == 0:
        start = git(base, "rev-parse", f"refs/heads/{branch}", execution=execution).stdout.strip()
    else:
        got = git(place, "fetch", "-q", str(start_from), "HEAD", execution=execution)
        if got.returncode != 0:
            raise OSError(f"{place} could not fetch its start from {start_from}: {got.stderr.strip()}")
        start = "FETCH_HEAD"
    r = git(place, "checkout", "-q", "-B", branch, start, execution=execution)
    if r.returncode != 0:
        raise OSError(f"{place} could not start {branch}: {r.stderr.strip()}")


#: What a session leaves behind that is no one's delivery: interpreter and compiler caches. Committed, two siblings'
#: caches of one shared module collide at the join, and one left untracked in the base aborts it (critic r2,
#: 2026-10-04). The repository's own `.gitignore` decides everything else.
CACHES = ("__pycache__", "*.pyc", "*.pyo", ".pytest_cache", "*.o", "*.obj")


def commit_all(base, place, message: str, who: str, execution=None, branch: str | None = None) -> str:
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
        # …taken back into the base under the node's own name, never the place's word
        if branch and is_clone(place, execution):
            got = git(base, "fetch", "-q", "--update-head-ok", str(place), f"+HEAD:refs/heads/{branch}",
                      execution=execution)     # …a worktree registration left from before may still claim the branch
            if got.returncode != 0:
                raise OSError(f"the delivery could not be taken back from {place}: {got.stderr.strip()}")
        return git(place, "rev-parse", "HEAD^{tree}", execution=execution).stdout.strip()


def bring(base, place, branch: str, execution=None) -> None:
    """`branch` of the base brought into a node's own repository under its name — what its packet tells it to merge."""
    if is_clone(place, execution):
        with _lock(base):
            git(place, "fetch", "-q", str(base), f"+refs/heads/{branch}:refs/heads/{branch}", execution=execution)


def _commit_in(base, ref: str, execution) -> str:
    """`ref` — a branch of the base or a commit — as the commit it names, read in the base: a node's own repository
    reads the base's objects, not its branches."""
    r = git(base, "rev-parse", "--verify", "--quiet", f"{ref}^{{commit}}", execution=execution)
    return r.stdout.strip() if r.returncode == 0 and r.stdout.strip() else ref


def head(place, execution=None) -> str | None:
    """The commit the tree at `place` stands on, or None."""
    return git(place, "rev-parse", "HEAD", execution=execution).stdout.strip() or None


def merge(base, into, branch: str, message: str, execution=None) -> str | None:
    """Join `branch` into the tree at `into`. None when joined (or already in); else why not, with the tree
    returned to where it stood — a half-merged tree would be the torn read this module exists against. Written where the
    work runs, so a symlink a part made is checked out as one."""
    with _lock(base):
        r = git(into, "merge", "--no-ff", "--no-edit", "--no-verify", "-m", message, _commit_in(base, branch, execution),
                execution=execution)
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
        return git(into, "merge-base", "--is-ancestor", _commit_in(base, branch, execution), "HEAD",
                   execution=execution).returncode == 0


def _by_registration(base, args: list, execution):
    """A worktree command that finds the place by the path it was registered under: where the work runs, else — for
    a place registered on the host before system git moved into the execution, which the execution cannot match
    ("is not a working tree") — on the host, for these two commands only (`lock`, a forced `remove`), which
    read no index and run nothing the agents wrote."""
    r = git(base, *args, execution=execution)
    if r.returncode and execution is not None and "is not a working tree" in (r.stderr or ""):
        r = git(base, *args)
    return r


def settled(base, place, branch: str, execution=None) -> bool:
    """Is all the place holds already in the base's tree? A worktree: its branch is joined. A node's own repository:
    its HEAD — delivered or not — is an ancestor of the base's HEAD; a commit never taken back is in no branch of the
    base, and a place holding one is kept."""
    if not is_clone(place, execution):
        return contains(base, base, branch, execution=execution)
    sha = head(place, execution=execution)
    with _lock(base):
        return bool(sha) and git(base, "merge-base", "--is-ancestor", sha, "HEAD",
                                 execution=execution).returncode == 0


def remove(base, place, branch: str, execution=None) -> bool:
    """Take a joined node's worktree and branch away (twice forced: the place is locked). False when git refused (a
    file held open, a branch not joined — `branch -d` refuses to lose commits)."""
    with _lock(base):
        if is_clone(place, execution):
            _fs(execution).remove_tree(str(place))
            ok = not _fs(execution).files.exists(str(place))
            if git(base, "rev-parse", "--verify", "--quiet", f"refs/heads/{branch}",
                   execution=execution).returncode != 0:
                return ok                        # never delivered: no branch of its own in the base to take away
        else:
            ok = _by_registration(base, ["worktree", "remove", "--force", "--force", str(place)],
                                  execution).returncode == 0
        r = git(base, "branch", "-d", branch, execution=execution)
        if r.returncode and "used by worktree" in (r.stderr or "") and not _fs(execution).files.exists(str(place)):
            # …a worktree registration this path had before it was a repository of its own still claims the branch
            _by_registration(base, ["worktree", "remove", "--force", "--force", str(place)], execution)
            r = git(base, "branch", "-d", branch, execution=execution)
        return r.returncode == 0 and ok

