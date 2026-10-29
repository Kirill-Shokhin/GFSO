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
import re
import shutil
import threading
import uuid
from pathlib import Path

from gfso.adapters import children
from gfso.config import subprocess_env
from gfso.adapters.execution import NODES, LocalExecution, fetched_on_host

#: the largest bundle `_carry` moves through the server's memory
BUNDLE_CAP = 512 * 2 ** 20


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


#: every system git call's own settings, after the caller's: no config but the repository's (the system's and the
#: user's are not the agent's to read, and an image's `safe.directory` goes with them), no hook, no fsmonitor. Depth,
#: not the bound — a repository's config still names filters, drivers, commands, and a denylist leaks by class
APART = ("-c", "safe.directory=*", "-c", "core.hooksPath=/dev/null", "-c", "core.fsmonitor=false")
NO_CONFIG = {"GIT_CONFIG_NOSYSTEM": "1", "GIT_CONFIG_GLOBAL": "/dev/null"}


def git(cwd, *args, who: str = "gfso", execution=None, env: dict | None = None):
    """One git call in `cwd`, as `who` — a delivery is its executor's commit, and no identity needs configuring —
    where `execution` runs the project's work (this host when None): IN THE CONTAINER OF THE PLACE THE REPOSITORY
    STANDS IN (`session`, by the system's own name of the path — `_writable_root` —, never by what stands there) — a
    node's clone in its own, a judge's copy in its round's, the base in the root's. A repository's config is its agent's
    to write (`core.fsmonitor`, a filter `.gitattributes` names, a merge driver, …), and run there it gives that agent
    nothing it does not hold already; in the project's container, which mounts every place, it read and wrote the
    others' and forged a clone (critics, three times). Asking the config before use was a race."""
    repo = (env or {}).get("GIT_DIR") or (args[1] if args[:1] == ("-C",) else cwd)
    mail = f"{who}@gfso.local"
    env = subprocess_env(extra={"GIT_AUTHOR_NAME": who, "GIT_AUTHOR_EMAIL": mail,
                                                "GIT_COMMITTER_NAME": who, "GIT_COMMITTER_EMAIL": mail,
                                                "GIT_TERMINAL_PROMPT": "0", **(env or {}), **NO_CONFIG})
    if execution is not None:
        return execution.session(str(repo)).run(["git", *APART, *args], cwd=str(cwd), timeout=_SLOW, env=env)
    return children.run(["git", *APART, *args], timeout=_SLOW, cwd=str(cwd), text=True, encoding="utf-8",
                        errors="replace", env=env)


def _fs(execution):
    """Where a place's files are reached: its execution, this host where none is named."""
    return execution if execution is not None else LocalExecution()


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
    The clone reads the base's objects (relative alternates) and holds its own refs and index; the system brings in
    what it needs (`bring`) and takes the node's branch back at DELIVER (`commit_all`). Made in its own container by
    `init`, never by a transport from the base — whose `upload-pack` would run beside the place, under the root's
    config. A place made as a worktree before this keeps working as one, locked."""
    place = Path(place)
    with _lock(base):
        if is_clone(place, execution):
            return False
        if _fs(execution).files.exists(str(place / ".git")):
            _by_registration(base, ["worktree", "lock", str(place)], execution)
            return False
        # …the base's own settings, as a worktree had them: line endings, links, attributes (a clone reads only its own)
        own = inherited(base, execution)
        _fs(execution).files.mkdir(str(place))           # …a session's container mounts only a place that stands
        try:
            for args in (("init", "-q"), *(("config", k, v) for k, v in own.items())):
                if (r := git(place, *args, execution=execution)).returncode:
                    raise OSError(f"git {args[0]} in {place} failed: {r.stderr.strip()}")
            _start(base, place, branch, start_from, execution)
        except Exception:   # …a half-made place would be reused as it stands, empty, and its emptiness delivered
            _fs(execution).remove_tree(str(place))
            raise
        return True


#: the base's local settings a node's own repository takes on: what a worktree of the base read from it
INHERITED = ("core.autocrlf", "core.eol", "core.symlinks", "core.filemode", "core.ignorecase")


def inherited(base, execution) -> dict:
    """{key: value} of the base's `INHERITED` settings it sets — what every node's own repository is made with."""
    return {k: v for k in INHERITED if (v := git(base, "config", "--local", "--get", k, execution=execution).stdout.strip())}


def kept_out(base, execution=None) -> dict:
    """{name: bytes} of the base's `info/exclude` and `info/attributes`, read where it stands — what every node's own
    repository is made with: what the base keeps out of its commits stays out of the node's."""
    return {n: b for n in ("exclude", "attributes")
            if (b := _fs(execution).files.read_bytes(str(Path(base) / ".git" / "info" / n))) is not None}


def _start(base, place: Path, branch: str, start_from, execution) -> None:
    """The new clone on `branch`: the base's commit of that name where it has one, else the HEAD of `start_from` — a
    parent's place, whose commit comes over by bundle (`_carry`): no container holds both places."""
    relative_alternates(place / ".git" / "objects", Path(base) / ".git" / "objects", execution)
    for name, kept in kept_out(base, execution).items():
        _fs(execution).files.write_bytes(str(place / ".git" / "info" / name), kept)
    if git(base, "rev-parse", "--verify", "--quiet", f"refs/heads/{branch}", execution=execution).returncode == 0:
        start = git(base, "rev-parse", f"refs/heads/{branch}", execution=execution).stdout.strip()
    else:
        start = _carry(base, start_from, place, "HEAD", execution)
    r = git(place, "checkout", "-q", "-B", branch, start, execution=execution)
    if r.returncode != 0:
        raise OSError(f"{place} could not start {branch}: {r.stderr.strip()}")


#: What a session leaves behind that is no one's delivery: interpreter and compiler caches. Committed, two siblings'
#: caches of one shared module collide at the join, and one left untracked in the base aborts it (critic r2,
#: 2026-10-04). The repository's own `.gitignore` decides everything else.
#: …and the tools' own caches and environments, which mark themselves ignored with a `.gitignore` of their own
CACHES = ("__pycache__", "*.pyc", "*.pyo", ".pytest_cache", "*.o", "*.obj", ".mypy_cache", ".ruff_cache", ".tox",
          ".nox", ".venv", "venv")
#: the pathspec of what a delivery commits: everything in the place but its caches
DELIVERED = (".", *(f":(exclude,glob)**/{c}" for c in CACHES),
             *(f":(exclude,glob)**/{c}/**" for c in CACHES if "*" not in c))


def stage(git):
    """THE DELIVERED TREE, staged by `git(*args)` (a CompletedProcess, text out): everything `DELIVERED` names that
    the ignore rules let in, and every `.gitignore` or `.gitattributes` there that ignore rules hide — a rule that
    hides itself is still part of what was handed in, and one added after DELIVER to hide a file is seen. The one rule
    of both sides: `commit_all` at DELIVER, and a judge holding its copy to that tree (`snapshots._JUDGES_GIT`, which
    runs this function's own source). The last git call's result."""
    r = git("add", "-A", "--", *DELIVERED)
    if r.returncode:
        return r
    hidden = [p for p in git("ls-files", "-z", "-o", "-i", "--exclude-standard", "--", ":(glob)**/.gitignore",
                             ":(glob)**/.gitattributes", *DELIVERED[1:]).stdout.split("\0") if p]
    return git("add", "-f", "--", *hidden) if hidden else r


def commit_all(base, place, message: str, who: str, execution=None, branch: str | None = None) -> str:
    """Everything in the place but caches as one commit — empty or not, so every delivery has a name. Its TREE: the
    same files are the same id whatever commit carries them, so a re-delivery of an unchanged result reads as one
    (four FAILs over one tree read as four attempts and split a leaf, GB_sql_database_tngo2o700 root.joins). Taken
    where the work was made: host git cannot index a symlink made inside a container (probe P5) — in the place's own
    container, whose agent's filters and fsmonitor ran over every place from the project's; and taken back into the
    base by bundle (`_carry`), the base's side in the root's container."""
    with _lock(base):
        if (r := stage(lambda *a: git(place, *a, execution=execution))).returncode:
            raise NotStaged(unstaged_cause(r.stderr or ""))
        r = git(place, "commit", "--allow-empty", "--no-verify", "-q", "-m", message, who=who, execution=execution)
        if r.returncode != 0:
            raise OSError(f"the delivery could not be committed in {place}: {r.stderr.strip()}")
        # …taken back into the base under the node's own name, never the place's word
        if branch and is_clone(place, execution):
            _name(base, branch, _carry(base, place, base, "HEAD", execution), execution)
        return git(place, "rev-parse", "HEAD^{tree}", execution=execution).stdout.strip()


class NotStaged(OSError):
    """The place's files could not be staged as a delivery (`stage`): nothing was committed. Its text is the cause."""


def unstaged_cause(stderr: str) -> str:
    """Why staging failed, in git's own words — and, where a nested repository without a commit stopped it, what
    lifts that (`nested_cause`)."""
    said = " ".join(stderr.split())[-400:] or "git add failed"
    inner = re.findall(r"'([^']+?)/?' does not have a commit checked out", stderr)
    return f"its files could not be staged ({said})" + (f"; {nested_cause(inner)}" if inner else "")


def nested(place, rev: str = "HEAD", execution=None) -> list[str]:
    """The paths `rev`'s tree in `place` records only as a gitlink — a nested repository or a submodule, whose files
    are no part of the tree, so no copy of the place can be held to it (`snapshots._not_delivered`)."""
    r = git(place, "ls-tree", "-r", "-z", rev, execution=execution)
    return [e.split("\t", 1)[1] for e in r.stdout.split("\0") if e.startswith("160000 ")] if r.returncode == 0 else []


def nested_cause(paths: list) -> str:
    """Why a delivery over `paths` (`nested`) is refused, and the executor's own move that lifts it."""
    return (f"its tree holds nested git repositories or submodules ({', '.join(paths[:10])}"
            f"{', …' if len(paths) > 10 else ''}): the delivery records only their commit, not their files, so they "
            f"cannot be checked against it. Commit their files into this node's own repository: for each path, delete "
            f"its inner `.git` (a directory, or a submodule's file) and run `git rm --cached <path>` (a submodule: "
            f"drop its entry from `.gitmodules` too), so its files are plain files of your tree; then deliver again")


def bring(base, place, branch: str, execution=None) -> None:
    """`branch` of the base brought into a node's own repository under its name — what its packet tells it to merge."""
    if is_clone(place, execution):
        with _lock(base):
            _name(place, branch, _carry(base, base, place, f"refs/heads/{branch}", execution), execution)


def _name(repo, branch: str, sha: str, execution) -> None:
    """`branch` of the repository at `repo` set to `sha`, whatever it held — checked out by a worktree left from
    before or not: the commit is the system's word, read in its source (`_carry`)."""
    r = git(repo, "update-ref", f"refs/heads/{branch}", sha, execution=execution)
    if r.returncode != 0:
        raise OSError(f"{repo} could not name {sha} {branch}: {r.stderr.strip()}")


def _carry(base, src, dst, rev: str, execution) -> str:
    """The commit `rev` names in the repository at `src`, present in the one at `dst` — its id. TWO REPOSITORIES, AND
    NEITHER'S GIT RUNS WHERE THE OTHER STANDS: a fetch from a path ran the source's `upload-pack` beside the target, in
    one container holding both. Here the source writes a bundle of what the base lacks in its own container (`git`), the
    system moves the file through the port, from the source's temp to the target's (`temp_of`), and the target takes its
    objects in its own: a bundle is objects and refs — no config, no hook — so each side runs only its own agent's
    config, where that agent already works. The id is read in the source's container and the bundle's refs are never
    taken: a bundle swapped on the way brings no other commit under it. What the base holds travels not at all — a
    clone reads its objects."""
    sha = git(src, "rev-parse", "--verify", "--quiet", f"{rev}^{{commit}}", execution=execution).stdout.strip()
    if not sha:
        raise OSError(f"{src} names no commit {rev} for {dst} to take")
    if git(dst, "cat-file", "-e", f"{sha}^{{commit}}", execution=execution).returncode == 0:
        return sha
    ex, b = _fs(execution), Path(_fs(execution).temp_of(str(dst))) / f"gfso-{uuid.uuid4().hex}.bundle"
    tips = git(base, "for-each-ref", "--format=%(objectname)", "refs/heads/", execution=execution).stdout.split()
    try:
        ex.files.write_bytes(str(b), _bundled(src, rev, tips, execution))
        got = git(dst, "bundle", "unbundle", str(b), execution=execution)
        if got.returncode or git(dst, "cat-file", "-e", f"{sha}^{{commit}}", execution=execution).returncode:
            raise OSError(f"{dst} could not take {rev} of {src}: {got.stderr.strip()[-300:]}")
    finally:
        ex.files.remove_matching(str(b.parent), [b.name])
    return sha


def _bundled(src, rev: str, nots: list, execution) -> bytes:
    """A bundle of `rev` of the repository at `src` but what `nots` hold, made in its own container and read out of its
    temp — to a cap, not whole: the source's agent holds its temp, and a bundle swapped for a huge sparse file filled
    the server's memory, every project's with it (critic over 61bf915) — past the cap, an `OSError`."""
    ex, name = _fs(execution), f"gfso-{uuid.uuid4().hex}.bundle"
    a = Path(ex.temp_of(str(src))) / name
    try:
        got = git(src, "bundle", "create", "-q", str(a), rev, *(["--not", *nots] if nots else []), execution=execution)
        if got.returncode or (data := ex.files.read_bytes(str(a), BUNDLE_CAP + 1)) is None:
            raise OSError(f"{src} could not bundle {rev}: {got.stderr.strip()[-300:]}")
        if len(data) > BUNDLE_CAP:
            raise OSError(f"{src}'s bundle of {rev} passes {BUNDLE_CAP >> 20} MiB: not carried")
        return data
    finally:
        ex.files.remove_matching(str(a.parent), [name])


def land(base, ref: str, execution, since: str | None, tree: str | None = None) -> str:
    """The HEAD of the base in the project's volume, as `ref` of the user's repository on the host — which the system
    names by the same path —; the commit's id. Bundled in the base's own container of what `since` (the commit the base
    was imported from) lacks — whole where the user's repository lacks that too —, carried out through the port, and
    taken there by the user's own git: `fetch` from the bundle and `update-ref` of `ref` alone — no config nor hook of
    the place, never their working tree nor any branch of theirs; `ref` checked out in any worktree of theirs is
    refused. `ref` standing is moved to the new commit (its reflog keeps where it stood)."""
    sha = git(base, "rev-parse", "--verify", "--quiet", "HEAD^{commit}", execution=execution).stdout.strip()
    host = lambda *a: children.run(["git", "-C", str(base), *a], timeout=_SLOW, text=True, encoding="utf-8",
                                   errors="replace")
    if not sha:
        raise OSError("the base names no commit")
    if f"branch {ref}" in host("worktree", "list", "--porcelain").stdout.splitlines():
        raise OSError(f"`{ref}` is checked out there (in a worktree of it), and the system lands only on a branch "
                      f"nobody works on: check out another branch")
    why = ""
    for nots in ([since] if since and since != sha else [], []):
        if host("cat-file", "-e", f"{sha}^{{commit}}").returncode == 0:
            break
        if not (why := fetched_on_host(base, _bundled(base, "HEAD", nots, execution))):
            break
    # …a fetch that said an error is no landing, whatever it took in: it went past the bundle (a submodule's remote)
    if why or host("cat-file", "-e", f"{sha}^{{commit}}").returncode:
        raise OSError(f"its commit {sha[:12]} could not be fetched: {why or 'not in the bundle'}")
    # …the tree the root's PASS accepted, read on the host: the base's HEAD is read in a container a session's leftover
    # may still run in, and what lands is the issuer's PASS, never what stood there at landing (critic over a99ea34)
    if tree and (got := host("rev-parse", f"{sha}^{{tree}}").stdout.strip()) != tree:
        raise OSError(f"its HEAD {sha[:12]} holds tree {got[:12]}, not the {tree[:12]} its PASS accepted")
    if (got := host("update-ref", "-m", "gfso: a root's accepted result", ref, sha)).returncode:
        raise OSError(f"`{ref}` could not be set to {sha[:12]}: {got.stderr.strip()[-300:]}")
    return sha


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
    work runs, so a symlink a part made is checked out as one. Two repositories, one git: the commit is named in the
    base's container, and the merge runs in `into`'s own — a parent's place in its, the base in the root's, whose
    agent writes the base's config — reading the part's objects through the base's: the drivers and filters that run
    are `into`'s config, the attributes the part brought only name them."""
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

