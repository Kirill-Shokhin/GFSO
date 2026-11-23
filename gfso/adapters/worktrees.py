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

import contextlib
import functools
import inspect
import os
import posixpath
import re
import shutil
import subprocess
import tempfile
import threading
import uuid
from datetime import datetime, timezone
from pathlib import Path

from gfso.adapters import children, lfs
from gfso.config import subprocess_env
from gfso.adapters.execution import (NODES, READ_REF, ContainerExecution, LocalExecution, fetched_on_host,
                                     stored_on_host)
from gfso.core.types import base_of_nodes

#: the largest bundle `carry` moves through the server's memory
BUNDLE_CAP = 512 * 2 ** 20


def base_of(place: str | None) -> str | None:
    """The base a node's place is a checkout of — `_place_of` read backwards; None for a place that is no node's."""
    p = Path(place) if place else None
    if p is None or len(p.parents) < 3 or not p.parent.parent.name.startswith(NODES):
        return None
    return str(base_of_nodes(p.parent.parent))


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
#: not the bound — a repository's config still names filters, drivers, commands, and a denylist leaks by class. Long
#: paths taken where the platform bounds them (Git for Windows): a judge's copy deep in a project's places wrote no pack
#: ("Filename too long") and read as the delivery's own fault
APART = ("-c", "safe.directory=*", "-c", "core.hooksPath=/dev/null", "-c", "core.fsmonitor=false", "-c", "core.longpaths=true")
NO_CONFIG = {"GIT_CONFIG_NOSYSTEM": "1", "GIT_CONFIG_GLOBAL": "/dev/null"}


def apart(execution) -> tuple:
    """`APART` where `execution` runs — in a container, with the system's own LFS filter (`lfs`): a checkout there
    writes an LFS file's content, a staging its pointer. This host's places are the user's repository's worktrees."""
    return APART + (lfs.filter_args(execution.python) if _lfs_in(execution) else ())


def _lfs_in(execution) -> bool:
    """Does the system run the LFS filter where `execution` runs (a container: not the user's own repository)?"""
    return isinstance(execution, ContainerExecution)


def _env(who: str = "gfso", env: dict | None = None) -> dict:
    mail = f"{who}@gfso.local"
    return subprocess_env(extra={"GIT_AUTHOR_NAME": who, "GIT_AUTHOR_EMAIL": mail, "GIT_COMMITTER_NAME": who,
                                 "GIT_COMMITTER_EMAIL": mail, "GIT_TERMINAL_PROMPT": "0", **(env or {}), **NO_CONFIG})


def git(cwd, *args, who: str = "gfso", execution=None, env: dict | None = None):
    """One git call in `cwd`, as `who` — a delivery is its executor's commit, and no identity needs configuring —
    where `execution` runs the project's work (this host when None): IN THE CONTAINER OF THE PLACE THE REPOSITORY
    STANDS IN (`session`, by the system's own name of the path — `_writable_root` —, never by what stands there) — a
    node's clone in its own, a judge's copy in its round's, the base in the root's. A repository's config is its agent's
    to write (`core.fsmonitor`, a filter `.gitattributes` names, a merge driver, …), and run there it gives that agent
    nothing it does not hold already; in the project's container, which mounts every place, it read and wrote the
    others' and forged a clone (critics, three times). Asking the config before use was a race."""
    repo = (env or {}).get("GIT_DIR") or (args[1] if args[:1] == ("-C",) else cwd)
    env = _env(who, env)
    if execution is not None:
        return execution.session(str(repo)).run(["git", *apart(execution), *args], cwd=str(cwd), timeout=_SLOW,
                                                env=env)
    return children.run(["git", *APART, *args], timeout=_SLOW, cwd=str(cwd), text=True, encoding="utf-8",
                        errors="replace", env=env)


def _fs(execution):
    """Where a place's files are reached: its execution, this host where none is named."""
    return execution if execution is not None else LocalExecution()


def _held(execution, path):
    """The system writing under `path`, as its execution marks it (`ExecutionPort.system_writes`)."""
    return _fs(execution).system_writes(str(path))


def one_at_a_time(base):
    """The base's lock, for a caller whose reading must not cross a join."""
    return _lock(base)


def _writes_into(arg: str):
    """The system's own writes into the directory the call's `arg` names — a commit, a carry, a join, a clone —: no
    node's growth against its disk bound (`ExecutionPort.system_writes`; the root was charged with every child's
    carried commit, a parent with its children's joins, and a neighbour's delivery FAILed the root's judge: critic)."""
    def _wrap(f):
        sig = inspect.signature(f)

        @functools.wraps(f)
        def _call(*a, **k):
            got = sig.bind(*a, **k).arguments
            with _held(got.get("execution"), got[arg]):
                return f(*a, **k)
        return _call
    return _wrap


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
    """A clone borrows the base's objects by a path relative to its own `objects/`, as the side that reads it lays them
    out: in a container both stand under one root while on the host the places stand in the installation's own state,
    away from the base — a path relative on the host led nowhere inside (an absolute path is one side's only)."""
    ex = _fs(execution)
    if isinstance(ex, ContainerExecution):
        rel = posixpath.relpath(ex.to_inside(str(base_objects)), ex.to_inside(str(objects)))
    else:       # …the host alone reads it; a base on another drive than the places has no relative path (critic)
        try:
            rel = Path(os.path.relpath(base_objects, objects)).as_posix()
        except ValueError:
            rel = Path(os.path.abspath(base_objects)).as_posix()
    ex.files.write_bytes(str(objects / "info" / "alternates"), (rel + "\n").encode())   # …LF alone: a CR is read as the path's


@_writes_into("place")
def ensure(base, place, branch: str, start_from, execution=None, ground=lambda: None) -> bool:
    """The node's own repository at `place` on `branch`, started from the commit `ground()`, asked under the base's lock,
    of `start_from` — its HEAD where it names none or that repository no longer holds it — when it is not there yet. True when it was made now; a place that exists is reused as it stands (a rework round continues its own tree).

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
        # …the base's own settings, as a worktree had them: line endings, links, attributes (a clone reads only its own);
        # and the system's LFS filter, so the agent's own git there agrees with the system's — its config to change
        # from then on: the system's own calls name the filter by `-c` (`apart`)
        own = {**inherited(base, execution), **dict(lfs.settings(execution.python) if _lfs_in(execution) else ())}
        _fs(execution).files.mkdir(str(place))           # …a session's container mounts only a place that stands
        try:
            for args in (("init", "-q"), *(("config", k, v) for k, v in own.items())):
                if (r := git(place, *args, execution=execution)).returncode:
                    raise OSError(f"git {args[0]} in {place} failed: {r.stderr.strip()}")
            _start(base, place, branch, start_from, execution, ground() or "HEAD")
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


#: what a tree would lay on disk by what it records, in KiB, stopping past `limit`: a name's cost beside its bytes, and an LFS file at the
#: size its pointer says where a store here holds its object (without one it stays a pointer). Streamed: a reading that held the listing
#: died first on the trees it is for (critic). Read where the tree's objects are the system's
_LAID = r"""
import os, re, subprocess, sys
limit, stores, commit, *apart = sys.argv[1:]
limit, stores, git = int(limit) * 1024, [s for s in stores.split("\n") if s], ["git", *apart]
listing = subprocess.Popen([*git, "ls-tree", "-r", "-l", "-z", commit], stdout=subprocess.PIPE)
batch = subprocess.Popen([*git, "cat-file", "--batch"], stdin=subprocess.PIPE, stdout=subprocess.PIPE)
size, rest = 0, b""
while size <= limit and (chunk := listing.stdout.read(2 ** 16)):
    *entries, rest = (rest + chunk).split(b"\0")
    for entry in entries:
        meta = entry.split(b"\t")[0].split()
        n = int(meta[3]) if len(meta) > 3 and meta[3].isdigit() else 0
        if 0 < n <= 1024:              # …as far as LFS reads a pointer: padded past a shorter reading, twelve names of one object passed (critic, ran)
            batch.stdin.write(meta[2] + b"\n")
            batch.stdin.flush()
            batch.stdout.readline()
            text = batch.stdout.read(n + 1)
            if text.startswith(b"version https://git-lfs.github.com/spec/v1\n"):      # …as `lfs.parse` reads one: the last of a key twice (critic, ran)
                keys = dict(line.split(b" ", 1) for line in text.splitlines() if b" " in line)
                o, said = keys.get(b"oid", b"").removeprefix(b"sha256:").decode("ascii", "replace"), keys.get(b"size", b"")
                if said.isdigit() and any(os.path.exists(os.path.join(s, o[:2], o[2:4], o)) for s in stores):
                    n = int(said)
        size += n + 4096
listing.kill()
print(size // 1024)
"""


#: what a tree may lay past what its place holds on disk: its files are charged there, a name costs a little more than the place shows
LAY_MARGIN_KIB = 2 ** 20


def _laid_kib(ex, at, commit: str, limit: int, stores) -> int | None:
    """What `commit`'s tree lays by `_LAID`, up to `limit` and a little past it; None unread."""
    try:
        r = ex.run([ex.python, "-I", "-c", _LAID, str(limit), "\n".join(map(str, stores)), commit, *APART], cwd=str(at), timeout=600, env=_env())
    except OSError:
        return None
    laid = (r.stdout or "").strip()
    return int(laid) if not r.returncode and laid.isdigit() else None


#: what the working directory holds on disk, in KiB, as `du -sk .` reads it: allocated blocks, a file of many links once, one
#: vanishing mid-walk no stop; where no blocks are told (Windows), its size by the cluster. A linked directory — a symlink, a
#: junction — is its entry, never walked into: walked, one to the place itself never ended, one to elsewhere read ×360 (critic, ran)
_HELD = r"""
import os, stat
seen, size = set(), 0
def held(p):
    global size
    try:
        s = os.lstat(p)
    except OSError:
        return False
    if s.st_nlink > 1 and not stat.S_ISDIR(s.st_mode):
        if (s.st_dev, s.st_ino) in seen:
            return False
        seen.add((s.st_dev, s.st_ino))
    b = getattr(s, "st_blocks", None)
    size += b * 512 if b is not None else -(-s.st_size // 4096) * 4096
    return stat.S_ISDIR(s.st_mode) and not getattr(s, "st_file_attributes", 0) & 0x400
for d, dirs, names in os.walk(".", onerror=lambda e: None):
    for n in names:
        held(os.path.join(d, n))
    dirs[:] = [n for n in dirs if held(os.path.join(d, n))]
held(".")
print(size // 1024)
"""


def du_kib(holder, place) -> int | None:
    """What `place` holds on disk in KiB, read by `_HELD` in the interpreter `holder` runs; None unread. Not by `du`: on a
    Windows host it is an MSYS program on Git Bash's path alone, and a server started anywhere else recorded no measure
    at every keep — the tree-bomb guard holding nothing."""
    try:
        r = holder.run([holder.python, "-I", "-c", _HELD], cwd=str(place), timeout=600, env=_env())
    except (OSError, subprocess.TimeoutExpired):
        return None
    kib = (r.stdout or "").strip()
    return int(kib) if not r.returncode and kib.isdigit() else None


def tree_past_place(ex, at, commit: str, held: int | None, base: tuple | None = None, stores: tuple = ()) -> str | None:
    """Why a commit's tree may not be laid at `at`: it records more than its place held on disk (`held` KiB — for a
    delivery, what its keep recorded at DELIVER, so the guard outlives the place).
    One blob under many names, kept from the place's disk by the index, took 2.0 GiB of copy from a 509 KB pack, a system's write and no
    one's charge, bounded by nothing but Docker's disk, every project's (critic, ran). Against the place, not a node's bound: that bound
    is what a node adds, and a whole of accepted parts, or a large repository, lay past it honestly (critic, ran); a tree as large as its
    place costs what the place already did, and what the user's own imported commit `base` records — (where git runs, the repository,
    the revision) — is credited, no agent writing it: a file git lays with holes reads little on disk, and a part may have removed from
    the whole what a sibling's ground still holds (critic, ran). NOT HELD: a large file a part made and a sibling then removed parks that
    sibling. Unread is not refused: the checkout says."""
    if held is None:
        return None
    limit = held + LAY_MARGIN_KIB
    laid = _laid_kib(ex, at, commit, limit, stores)
    if laid is None or laid <= limit:
        return None
    if base and (credit := _laid_kib(base[0], base[1], base[2], 2 ** 50, ())):
        limit += credit
        laid = _laid_kib(ex, at, commit, limit, stores)
        if laid is None or laid <= limit:
            return None
    return (f"the tree of {commit[:12]} would lay over {limit} KiB, past what its place held on disk ({held} KiB): "
            f"it names content its files do not hold, or files git lays with holes that a part delivered, and no copy of it is made")


def _start(base, place: Path, branch: str, start_from, execution, rev: str = "HEAD") -> None:
    """The new clone on `branch`: the base's commit of that name where it has one, else `rev` of `start_from` — a
    parent's place, whose commit comes over by bundle (`carry`): no container holds both places."""
    relative_alternates(place / ".git" / "objects", Path(base) / ".git" / "objects", execution)
    for name, kept in kept_out(base, execution).items():
        _fs(execution).files.write_bytes(str(place / ".git" / "info" / name), kept)
    if git(base, "rev-parse", "--verify", "--quiet", f"refs/heads/{branch}", execution=execution).returncode == 0:
        start = carry(base, base, place, f"refs/heads/{branch}", execution)
    else:
        held = git(start_from, "cat-file", "-e", f"{rev}^{{commit}}", execution=execution).returncode == 0
        start = carry(base, start_from, place, rev if held else "HEAD", execution)
    # …a parent's commit laid here is this place's baseline, charged to no one: the same tree a delivery's copy refuses
    if past := tree_past_place(_fs(execution).session(str(place)), place, start,
                               du_kib(_fs(execution).session(str(start_from)), start_from),
                               (_fs(execution).session(str(base)), base, "HEAD"), _stores(base, place) if _lfs_in(execution) else ()):
        raise OSError(f"{place} could not start {branch}: {past}")
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
    hides itself is still part of what was handed in. What `commit_all` commits at DELIVER, and so what its judge
    checks out (`snapshots._checkout`). The last git call's result."""
    r = git("add", "-A", "--", *DELIVERED)
    if r.returncode:
        return r
    hidden = [p for p in git("ls-files", "-z", "-o", "-i", "--exclude-standard", "--", ":(glob)**/.gitignore",
                             ":(glob)**/.gitattributes", *DELIVERED[1:]).stdout.split("\0") if p]
    return git("add", "-f", "--", *hidden) if hidden else r


@_writes_into("place")
def commit_all(base, place, message: str, who: str, execution=None, branch: str | None = None) -> str:
    """Everything in the place but caches as one commit — empty or not, so every delivery has a name. Its TREE: the
    same files are the same id whatever commit carries them, so a re-delivery of an unchanged result reads as one
    (four FAILs over one tree read as four attempts and split a leaf, GB_sql_database_tngo2o700 root.joins). Taken
    where the work was made: host git cannot index a symlink made inside a container (probe P5) — in the place's own
    container, whose agent's filters and fsmonitor ran over every place from the project's; and taken back into the
    base by bundle (`carry`), the base's side in the root's container."""
    with _lock(base):
        if (r := stage(lambda *a: git(place, *a, execution=execution))).returncode:
            raise NotStaged(unstaged_cause(r.stderr or ""))
        r = git(place, "commit", "--allow-empty", "--no-verify", "-q", "-m", message, who=who, execution=execution)
        if r.returncode != 0:
            raise OSError(f"the delivery could not be committed in {place}: {r.stderr.strip()}")
        # …taken back into the base under the node's own name, never the place's word
        if branch and is_clone(place, execution):
            try:
                _name(base, branch, carry(base, place, base, "HEAD", execution), execution)
            except OSError as e:
                raise NotCarried(f"the delivery could not be taken back into the project: {e}") from e
        return git(place, "rev-parse", "HEAD^{tree}", execution=execution).stdout.strip()


def read_head(place, rev: str = "HEAD") -> tuple[str, str, list]:
    """(tree, commit, left out) of the user's repository at `place` as their chat committed it — its `rev`, HEAD where
    none is named —; left out: what `git status` names that the commit does not hold, no part of the delivery. Read
    only: a DELIVER refused after it writes nothing (a ref written first stood for a delivery never admitted).
    Only what is committed is delivered, as only what is committed enters a project (`_carried_in`): a tree staged whole
    took their uncommitted notes and local files into the volume every later session reads (critic)."""
    commit = git(place, "rev-parse", "--verify", "-q", f"{rev}^{{commit}}").stdout.strip()
    if not commit:
        raise OSError(f"{place} has no commit to deliver")
    # …read by their own git: under the system's flags (`APART`) their CRLF checkout read as changed (README, live)
    seen = children.run(["git", "-C", str(place), "status", "--porcelain", "-z"], timeout=_SLOW, text=True,
                        encoding="utf-8", errors="replace").stdout
    left = [line[3:] for line in seen.split("\0") if line[3:]]
    return git(place, "rev-parse", f"{commit}^{{tree}}").stdout.strip(), commit, left


class NotCarried(OSError):
    """A delivery its executor can lift the cause of, a size past what a carry holds: told it, as what `NotStaged` says."""


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
    are no part of the tree, so no copy of it can be checked out whole (`snapshots._checkout`) —, but those the user's own
    imported commit records at that commit: empty in every copy alike, they carry nothing of a node's, and a repository holding a
    submodule could deliver nothing, with no move of its executor's to lift it (critic, ran)."""
    kept = set(users_links(place, execution))
    return [link.split(" ", 1)[1] for link in links_of(place, rev, execution) if link not in kept]


def links_of(repo, rev: str, execution) -> list[str]:
    """Each gitlink of `rev`'s tree in `repo`, as "<commit> <path>"."""
    r = git(repo, "ls-tree", "-r", "-z", rev, execution=execution)
    return [" ".join((e.split(" ", 2)[2].split("\t", 1))) for e in r.stdout.split("\0") if e.startswith("160000 ")] if r.returncode == 0 else []


def declared_links(repo, rev: str, execution=None) -> list[str]:
    """The gitlinks of `rev` in `repo` its own `.gitmodules` declares as submodules: a repository a chat committed as a
    bare gitlink is its stray, which no checkout holds (critic)."""
    said = git(repo, "config", "--blob", f"{rev}:.gitmodules", "--get-regexp", r"\.path$", execution=execution).stdout.split("\n")
    declared = {line.split(" ", 1)[1] for line in said if " " in line}
    return [link for link in links_of(repo, rev, execution) if link.split(" ", 1)[1] in declared]


def users_links(place, execution) -> list[str]:
    """What the user's imported commit records of gitlinks, for the node's `place` — or, for a place that is no node's on
    this host, the user's own repository where their chat works, the submodules its HEAD declares (`declared_links`)."""
    if root := base_of(str(place)):
        return links_of(root, "HEAD", execution)
    if execution is not None and not isinstance(execution, LocalExecution):
        return []
    return declared_links(place, "HEAD")


def nested_cause(paths: list) -> str:
    """Why a delivery over `paths` (`nested`) is refused, and the executor's own move that lifts it."""
    return (f"its tree holds nested git repositories or submodules ({', '.join(paths[:10])}"
            f"{', …' if len(paths) > 10 else ''}): the delivery records only their commit, not their files, so they "
            f"cannot be checked against it. Commit their files into this node's own repository: for each path, delete "
            f"its inner `.git` (a directory, or a submodule's file) and run `git rm --cached <path>` (a submodule: "
            f"drop its entry from `.gitmodules` too), so its files are plain files of your tree; then deliver again")


@_writes_into("place")
def bring(base, place, branch: str, execution=None) -> None:
    """`branch` of the base brought into a node's own repository under its name — what its packet tells it to merge."""
    if is_clone(place, execution):
        with _lock(base):
            _name(place, branch, carry(base, base, place, f"refs/heads/{branch}", execution), execution)


@_writes_into("repo")
def _name(repo, branch: str, sha: str, execution) -> None:
    """`branch` of the repository at `repo` set to `sha`, whatever it held — checked out by a worktree left from
    before or not: the commit is the system's word, read in its source (`carry`)."""
    r = git(repo, "update-ref", f"refs/heads/{branch}", sha, execution=execution)
    if r.returncode != 0:
        raise OSError(f"{repo} could not name {sha} {branch}: {r.stderr.strip()}")


#: a commit named by its id
_BARE = re.compile(r"[0-9a-f]{40,64}")


def _not_carried(base, dst, execution) -> list:
    """The commits a carry into `dst` leaves out: what every place reads through its alternates — the read copy of the
    base, where the sessions read that one (`execution._READ_COPY`), the base's branches where they read the base —, what
    `dst` stands on, and into the base its branches, which it holds: else every carry up the tree held the whole's
    accumulated work, in the server's memory, up to the cap."""
    def _out(*a):
        return git(*a, execution=execution).stdout.split()
    branches = _out(base, "for-each-ref", "--format=%(objectname)", "refs/heads/")
    seen = _out(base, "rev-parse", "--verify", "--quiet", f"{READ_REF}^{{commit}}")
    into_base = Path(dst) == Path(base)
    held = branches if into_base or not seen else _out(dst, "rev-list", "--no-walk", "--ignore-missing", *branches) if branches else []
    return [*held, *seen]


@_writes_into("dst")
def carry(base, src, dst, rev: str, execution) -> str:
    """The commit `rev` names in the repository at `src`, present in the one at `dst` — its id. TWO REPOSITORIES, AND
    NEITHER'S GIT RUNS WHERE THE OTHER STANDS: a fetch from a path ran the source's `upload-pack` beside the target, in
    one container holding both. Here the source writes a bundle of what the base lacks in its own container (`git`), the
    system moves the file through the port, from the source's temp to the target's (`temp_of`), and the target takes its
    objects in its own: a bundle is objects and refs — no config, no hook — so each side runs only its own agent's
    config, where that agent already works. The id is read in the source's container and the bundle's refs are never
    taken: a bundle swapped on the way brings no other commit under it. What the base holds travels not at all — a
    clone reads its objects. The LFS objects the carried commits' pointers name go with them (`_lfs_carried`)."""
    sha = git(src, "rev-parse", "--verify", "--quiet", f"{rev}^{{commit}}", execution=execution).stdout.strip()
    if not sha:
        raise OSError(f"{src} names no commit {rev} for {dst} to take")
    if git(dst, "cat-file", "-e", f"{sha}^{{commit}}", execution=execution).returncode == 0:
        return sha
    ex, b = _fs(execution), Path(_fs(execution).temp_of(str(dst))) / f"gfso-{uuid.uuid4().hex}.bundle"
    tips = _not_carried(base, dst, execution)
    with _held(execution, b.parent):         # …the bundle in the target's temp: no node's growth
        try:
            ex.files.write_bytes(str(b), _bundled(src, rev, tips, execution))
            got = git(dst, "bundle", "unbundle", str(b), execution=execution)
            if got.returncode or git(dst, "cat-file", "-e", f"{sha}^{{commit}}", execution=execution).returncode:
                raise OSError(f"{dst} could not take {rev} of {src}: {got.stderr.strip()[-300:]}")
        finally:
            ex.files.remove_matching(str(b.parent), [b.name])
    _lfs_carried(base, src, dst, ["--ignore-missing", sha, *(["--not", *tips] if tips else [])], execution)
    return sha


#: the LFS pointers among the blobs the commits "$1" names (`rev-list` arguments) hold short enough to be one: the
#: listing (`<blob> <path>`), a blank line, each blob as `cat-file --batch` prints it — by git under "$@" (`apart`)
_POINTED = r'''r=$1; shift
l=$(git "$@" rev-list --objects --filter=blob:limit=1025 $r) || exit 1
printf '%s\n\n' "$l"
printf '%s\n' "$l" | cut -d' ' -f1 | git "$@" cat-file --batch-check='%(objecttype) %(objectname)' | sed -n 's/^blob //p' | git "$@" cat-file --batch'''
_BLOB = re.compile(rf"^(?P<blob>[0-9a-f]{{40,64}}) blob \d+\n{re.escape(lfs.SPEC.decode())}(?:ext-[^\n]*\n)*"
                   r"oid sha256:(?P<oid>[0-9a-f]{64})\nsize (?P<size>\d+)\n", re.M)
#: of the object paths on stdin (`<store>/`-relative), those none of the stores "$@" holds
_LACKING = 'while read -r p; do for s; do [ -f "$s/$p" ] && continue 2; done; echo "$p"; done'


def pointed(repo, revs: list, execution) -> dict:
    """{oid: (size, path)} of the LFS pointers in the commits `revs` names (`rev-list` arguments) in the repository
    at `repo`, read in its own container as git stores them — no filter runs to read them."""
    r = execution.session(str(repo)).run(["sh", "-c", _POINTED, "sh", " ".join(revs), *apart(execution)],
                                         cwd=str(repo), timeout=_SLOW, env=_env())
    if r.returncode or (len(r.stdout) > children.PRINTED_CAP and children.CUT in r.stdout):
        raise OSError(f"{repo}: its LFS pointers could not be read ({r.stderr.strip()[-300:] or 'past what the server holds'})")
    listing, _, batch = r.stdout.partition("\n\n")
    paths = dict(ln.split(" ", 1) for ln in listing.splitlines() if " " in ln)
    return {m["oid"]: (int(m["size"]), paths.get(m["blob"], m["blob"])) for m in _BLOB.finditer(batch)}


def _stores(base, repo) -> list:
    """The LFS stores the repository at `repo` reads (`lfs.stores_of`): its own, then the base's."""
    return list(dict.fromkeys(str(Path(p) / ".git" / "lfs" / "objects") for p in (repo, base)))


def lfs_object(base, repo, oid: str, size: int, execution) -> bytes | None:
    """The LFS object `oid` from a store the repository at `repo` reads, through the port — read to its pointer's size
    and returned only where it is the object (`lfs.is_object`): the stores are agents' to write. None past
    `BUNDLE_CAP`, as a bundle is (`_bundled`)."""
    if size > BUNDLE_CAP:
        return None
    return next((d for s in _stores(base, repo) if (d := execution.files.read_bytes(lfs.path_in(s, oid), size + 1))
                 is not None and lfs.is_object(d, oid, size)), None)


def _lfs_carried(base, src, dst, revs: list, execution) -> None:
    """The LFS objects the pointers of the commits `revs` names in `src` (`pointed`) name, written into the own store
    of `dst` where none it reads holds them — a parent that joins a part's change then checks out its content, and a
    landing finds it in the base (`land_lfs`). Each object only as `carry_lfs` takes it; one `src` lacks is not
    carried, and its pointer reads as a pointer — said where the result lands."""
    if not _lfs_in(execution) or not (want := pointed(src, revs, execution)):
        return
    rel = {"/".join((o[:2], o[2:4], o)): o for o in want}
    lacking = execution.session(str(dst)).bytes_call(["sh", "-c", _LACKING, "sh", *_stores(base, dst)], cwd=str(dst),
                                                     input="".join(f"{p}\n" for p in rel).encode())
    carry_lfs(base, src, dst, {rel[p]: want[rel[p]] for p in lacking.stdout.decode().split() if p in rel}, execution)


#: one LFS object taken from stdin in the container of the repository it goes to: written into the store "$1" as
#: git-lfs lays it out, only where its size and sha256 are the pointer's ("$2", "$3"); exit 5 where they are not
_TAKE_LFS = r'''
import hashlib, os, sys, tempfile
store, oid, size = sys.argv[1], sys.argv[2], int(sys.argv[3])
at = os.path.join(store, oid[:2], oid[2:4], oid)
os.makedirs(os.path.dirname(at), exist_ok=True)
h, n = hashlib.sha256(), 0
with tempfile.NamedTemporaryFile(dir=os.path.dirname(at), delete=False) as t:
    while n <= size and (c := sys.stdin.buffer.read(1 << 20)):
        n += len(c)
        h.update(c)
        t.write(c)
if n == size and h.hexdigest() == oid:
    os.replace(t.name, at)
else:
    os.unlink(t.name)
    sys.exit(5)
'''


def carry_lfs(base, src, dst, want: dict, execution) -> list[str]:
    """Each LFS object `want` names ({oid: (size, path)}) from a store the repository at `src` reads into the own store
    of the one at `dst`: STREAMED from `src`'s container into `dst`'s (`ExecutionPort.pipe`), nothing of it held by the
    server whatever its size, and kept only where it is the pointer's object (`_TAKE_LFS`) — the stores are agents' to
    write, so a forged one in the first store gives way to the next. [The paths whose object no store held]."""
    into, there = execution.session(str(dst)), execution.session(str(src))
    take = lambda store, oid, size: there.pipe(
        ["cat", "--", lfs.path_in(store, oid)], cwd=str(src), into=into, timeout=_SLOW, into_cwd=str(dst),
        into_args=[into.python, "-I", "-c", _TAKE_LFS, _stores(base, dst)[0], oid, str(size)])[2].returncode == 0
    return [path for oid, (size, path) in want.items() if not any(take(s, oid, size) for s in _stores(base, src))]


def lfs_into_copy(base, src, dst, commit: str, execution) -> list[str]:
    """The LFS objects the pointers of `commit` name — read in the copy at `dst`, from the objects the system checked
    there, not in the place `src` — carried from the stores `src` reads into the copy's own (`carry_lfs`), so its
    checkout writes their content; [the paths whose object no store held]. Nothing where no LFS filter runs."""
    return carry_lfs(base, src, dst, pointed(dst, [commit], execution), execution) if _lfs_in(execution) else []


def land_lfs(base, sha: str, since: str | None, execution) -> list[str]:
    """The LFS objects the pointers of the landed commits (`sha` but `since`, the imported one) name, written into the
    user's LFS store by the host (`execution.stored_on_host`) — only what the base holds verified (`lfs_object`); [the
    paths whose object could not be carried]."""
    if not _lfs_in(execution):
        return []
    want = pointed(base, [sha, *(["--not", since] if since else [])], execution)
    return stored_on_host(Path(base), want, lambda oid, size: lfs_object(base, base, oid, size, execution))


def _bundled(src, rev: str, nots: list, execution) -> bytes:
    """A bundle of `rev` of the repository at `src` but what `nots` hold, made in its own container and read out of its
    temp — to a cap, not whole: the source's agent holds its temp, and a bundle swapped for a huge sparse file filled
    the server's memory, every project's with it (critic over 61bf915) — past the cap, an `OSError`."""
    ex, name = _fs(execution), f"gfso-{uuid.uuid4().hex}.bundle"
    a = Path(ex.temp_of(str(src))) / name
    with _held(execution, a.parent):         # …the bundle in the source's temp: no node's growth
        try:
            # …a bundle names refs, and a bare commit makes an empty one, refused; what `nots` holds that the source does
            # not know, it has none of
            ref = f"refs/gfso-carry/{uuid.uuid4().hex}" if _BARE.fullmatch(rev) else rev
            if ref != rev:
                git(src, "update-ref", ref, rev, execution=execution)
            got = git(src, "bundle", "create", "-q", str(a), ref, "--ignore-missing", *(["--not", *nots] if nots else []),
                      execution=execution)
            if ref != rev:
                git(src, "update-ref", "-d", ref, execution=execution)
            if got.returncode or (data := ex.files.read_bytes(str(a), BUNDLE_CAP + 1)) is None:
                raise OSError(f"{src} could not bundle {rev}: {got.stderr.strip()[-300:]}")
            if len(data) > BUNDLE_CAP:
                raise OSError(f"{src}'s bundle of {rev} passes {BUNDLE_CAP >> 20} MiB: not carried")
            return data
        finally:
            ex.files.remove_matching(str(a.parent), [name])


def to_host(src, ref: str, to, execution) -> str:
    """The commit `ref` names in the repository at `src`, where `execution` runs (a container), taken into the user's
    repository at `to` on this host by their own git (`fetched_on_host`) — a bundle made in `src`'s own container,
    every object checked; git's words where it refused, else ''."""
    return fetched_on_host(Path(to), _bundled(src, ref, [], execution), ref)


def move_result(base, ref: str, sha: str) -> str | None:
    """THE one move of a result branch of the person's repository to `sha` — every landing's (`land`, a chat-performed
    root's `_name_the_delivery`). The result it holds, where `sha` does not contain it, is kept first under
    `<ref>-<UTC time>`, that name returned: a project made again under a deleted one's name, or a root whose earlier result
    was never merged, landed over it and left it only in the reflog — and the result is the person's. The move itself is
    from the value read, so a write between the two is refused, never overwritten unkept; either step failing raises
    OSError, nothing moved."""
    git_ = lambda *a: children.run(["git", "-C", str(base), *a], timeout=_SLOW, text=True, encoding="utf-8",
                                   errors="replace", env=subprocess_env(extra={"GIT_NO_REPLACE_OBJECTS": "1"}))
    old = git_("rev-parse", "--verify", "--quiet", f"{ref}^{{commit}}").stdout.strip()
    kept = None
    if old and old != sha and git_("merge-base", "--is-ancestor", old, sha).returncode:
        kept = f"{ref}-{datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ')}"
        if (got := git_("update-ref", "-m", "gfso: the result a landing would have overwritten", kept, old, "")).returncode:
            raise OSError(f"`{ref}` holds {old[:12]}, which the new result does not contain, and it could not be kept "
                          f"as `{kept}`: {got.stderr.strip()[-300:]}")
    if (got := git_("update-ref", "-m", "gfso: a root's accepted result", ref, sha, old)).returncode:
        raise OSError(f"`{ref}` could not be set to {sha[:12]}: {got.stderr.strip()[-300:]}")
    return kept


def main_worktree(place) -> str:
    """The repository the worktree `place` belongs to, named by its main worktree — which outlives every linked one,
    as a linked worktree is removed when its work is merged; `place` itself where there is none (a bare repository's)."""
    out = git(place, "worktree", "list", "--porcelain").stdout.splitlines()
    top = out[0].removeprefix("worktree ") if out[:1] and out[0].startswith("worktree ") and "bare" not in out[1:2] else ""
    return str(Path(top)) if top and is_repo_top(top) else str(place)


def checked_out(base, ref: str, execution=None) -> bool:
    """Is `ref` checked out in a worktree of the repository at `base` (the user's, where `execution` names none)? The
    system lands only on a branch nobody works on: moved under their working tree, the files stay, and their next commit
    undoes what landed."""
    return f"branch {ref}" in git(base, "worktree", "list", "--porcelain", execution=execution).stdout.splitlines()


def land(base, ref: str, execution, since: str | None, tree: str | None = None, rev: str = "HEAD") -> str:
    """The HEAD of the base in the project's volume (or its `rev`), as `ref` of the user's repository on the host — which the system
    names by the same path —; the commit's id. Bundled in the base's own container of what `since` (the commit the base
    was imported from) lacks — whole where the user's repository lacks that too —, carried out through the port, and
    taken there by the user's own git: `fetch` from the bundle and `update-ref` of `ref` alone — no config nor hook of
    the place, never their working tree nor any branch of theirs; `ref` checked out in any worktree of theirs is
    refused. `ref` standing is moved to the new commit (`move_result`: a result it would no longer contain kept
    first as `<ref>-<UTC time>`)."""
    sha = git(base, "rev-parse", "--verify", "--quiet", f"{rev}^{{commit}}", execution=execution).stdout.strip()
    # …no replace refs: an object they stand in for is not the one a checkout without them reads (critic, run)
    host = lambda *a: children.run(["git", "-C", str(base), *a], timeout=_SLOW, text=True, encoding="utf-8",
                                   errors="replace", env=subprocess_env(extra={"GIT_NO_REPLACE_OBJECTS": "1"}))
    if not sha:
        raise OSError("the base names no commit")
    if checked_out(base, ref):
        raise OSError(f"`{ref}` is checked out there (in a worktree of it), and the system lands only on a branch "
                      f"nobody works on: check out another branch")
    # …WHOLE, not merely there: a fetch that failed leaves the commit and its tree behind without their blobs, and a
    # landing retried on them set the branch to a commit no checkout reads (critic over e59b9d5, run)
    # …and none taken on trust from the system's own refs: the old landing left one naming such a commit (critic, run)
    whole = lambda: host("rev-list", "--objects", "--missing=error", sha, "--not", "--exclude=refs/heads/gfso/*",
                         "--all").returncode == 0
    why = ""
    for nots in ([since] if since and since != sha else [], []):
        if whole():
            break
        if not (why := fetched_on_host(base, _bundled(base, rev, nots, execution))):
            break
    # …a fetch that said an error is no landing, whatever it took in: it went past the bundle (a submodule's remote)
    if why or not whole():
        raise OSError(f"its commit {sha[:12]} could not be fetched: {why or 'not in the bundle'}")
    # …the tree the root's PASS accepted, read on the host: the base's HEAD is read in a container a session's leftover
    # may still run in, and what lands is the issuer's PASS, never what stood there at landing (critic over a99ea34)
    if tree and (got := host("rev-parse", f"{sha}^{{tree}}").stdout.strip()) != tree:
        raise OSError(f"its HEAD {sha[:12]} holds tree {got[:12]}, not the {tree[:12]} its PASS accepted")
    move_result(base, ref, sha)
    return sha


def _commit_in(base, ref: str, execution) -> str:
    """`ref` — a branch of the base or a commit — as the commit it names, read in the base: a node's own repository
    reads the base's objects, not its branches."""
    r = git(base, "rev-parse", "--verify", "--quiet", f"{ref}^{{commit}}", execution=execution)
    return r.stdout.strip() if r.returncode == 0 and r.stdout.strip() else ref


def head(place, execution=None) -> str | None:
    """The commit the tree at `place` stands on, or None."""
    return git(place, "rev-parse", "HEAD", execution=execution).stdout.strip() or None


#: why a join is skipped: the agent's own merge stands unfinished in the place — nothing of it is touched
MERGE_STANDS = "a merge stands unfinished in the tree, begun by its agent: left as it stands, this branch with it"


@_writes_into("into")
def merge(base, into, branch: str, message: str, execution=None) -> str | None:
    """Join `branch` into the tree at `into`. None when joined (or already in); else why not, with the tree
    returned to where it stood — a half-merged tree would be the torn read this module exists against. Written where the
    work runs, so a symlink a part made is checked out as one. Two repositories, one git: the commit is named in the
    base's container, and the merge runs in `into`'s own — a parent's place in its, the base in the root's, whose
    agent writes the base's config — reading the part's objects through the base's: the drivers and filters that run
    are `into`'s config, the attributes the part brought only name them."""
    with _lock(base):
        # …A MERGE ALREADY STANDING THERE IS THE AGENT'S WORK: git refuses to start another, and the abort below then
        # undid its merge — MERGE_HEAD and every resolution gone between two rounds (GB_c_compiler_ctx3b1285)
        if merging(base, into, execution=execution):
            return MERGE_STANDS
        sha = _commit_in(base, branch, execution)
        # …its objects into `into`'s own store: a session reads no delivery through the base (`execution._READ_COPY`)
        try:
            carry(base, base, into, sha, execution)
        except OSError as e:                # …said as any join's refusal, its cause the whole's or its issuer's to read
            return str(e)
        r = git(into, "merge", "--no-ff", "--no-edit", "--no-verify", "-m", message, sha, execution=execution)
        if r.returncode == 0:
            return None
        git(into, "merge", "--abort", execution=execution)   # refused before it started (a dirty tree): nothing to abort
        return " ".join((r.stdout + " " + r.stderr).split())[:400] or f"git merge exited {r.returncode}"


#: one form of every diff read here, whatever the repository's own config says: a prefix, colour or rename detection
#: of its choosing turned a lost line into a silent pass (critic)
_PLAIN = ("--no-ext-diff", "--no-textconv", "--no-color", "--no-renames", "--src-prefix=a/", "--dst-prefix=b/", "-U0")
_HUNK = re.compile(r"^@@ -(\d+)(?:,(\d+))? \+(\d+)(?:,(\d+))? @@")


def change_not_there(place, base: str, sha: str, execution=None) -> list[str]:
    """The files where a line `sha` added over `base` is gone or changed in the COMMITTED tree at `place` (HEAD): a
    line of `base..sha`'s additions that `sha..HEAD` deletes — both read in `sha`'s own line numbers. A line others
    insert beside or inside the part's lines deletes none of them; a file the part created is the case where every
    line is its own. Read-only. Not seen: a line the part REMOVED coming back, a binary file's content."""
    if not (re.fullmatch(r"[0-9a-f]{7,64}", base or "") and re.fullmatch(r"[0-9a-f]{7,64}", sha or "")):
        return []
    q = ("-c", "core.quotePath=true")          # …one quoting, whatever the repository's own config says (critic)
    added = _lines(git(place, *q, "diff", *_PLAIN, base, sha, execution=execution).stdout, new=True)
    if not added:
        return []
    gone = _lines(git(place, *q, "diff", *_PLAIN, sha, "HEAD", execution=execution).stdout, new=False)
    return sorted(p for p, ls in added.items() if ls & gone.get(p, set()))


def _lines(patch: str, new: bool) -> dict:
    """{path: line numbers} a -U0 patch adds (`new`, numbered in its new side) or deletes (numbered in its old side)."""
    out, path, head = {}, None, False
    for ln in patch.splitlines():
        if ln.startswith("diff --git "):
            path, head = None, True             # …a file's headers stand only before its first hunk: a deleted
        elif head and ln.startswith("+++ " if new else "--- "):    # content line "-- …" is no header (critic)
            path = _path_of(ln[4:], "b/" if new else "a/")
        elif path and (m := _HUNK.match(ln)):
            head = False
            at, n = (m.group(3), m.group(4)) if new else (m.group(1), m.group(2))
            out.setdefault(path, set()).update(range(int(at), int(at) + int(1 if n is None else n)))
    return out


def _path_of(said: str, prefix: str) -> str | None:
    """A diff header's path: None for /dev/null, a C-quoted name (tab, newline, quote, backslash, raw bytes) unquoted."""
    said = said.rstrip("\t")                   # …git ends a header naming a path with a space by a TAB
    if said.startswith('"'):
        said = said[1:-1].encode("latin-1", "backslashreplace").decode("unicode_escape").encode("latin-1").decode(
            "utf-8", "replace")
    return said[len(prefix):] if said.startswith(prefix) else None


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


def settled(base, place, branch: str, execution=None, onto: str = "HEAD") -> bool:
    """Is all the place holds already in `onto` of the base — its HEAD, or the branch the root's result landed on? A
    worktree: its branch is joined. A node's own repository: its HEAD — delivered or not — is an ancestor; a commit never
    taken back is in no branch of the base, and a place holding one is kept."""
    sha = head(place, execution=execution) if is_clone(place, execution) else _commit_in(base, branch, execution)
    with _lock(base):
        return bool(sha) and git(base, "merge-base", "--is-ancestor", sha, onto,
                                 execution=execution).returncode == 0


def remove(base, place, branch: str, execution=None, onto: str = "HEAD") -> bool:
    """Take a joined node's worktree and branch away (twice forced: the place is locked). False when git refused (a
    file held open) or the branch is not all in `onto` (`settled`'s: `branch -d` read only the base's HEAD)."""
    with _lock(base):
        if git(base, "rev-parse", "--verify", "--quiet", f"refs/heads/{branch}", execution=execution).returncode == 0 \
                and git(base, "merge-base", "--is-ancestor", f"refs/heads/{branch}", onto, execution=execution).returncode:
            return False
        if is_clone(place, execution):
            _fs(execution).remove_tree(str(place))
            ok = not _fs(execution).files.exists(str(place))
            if git(base, "rev-parse", "--verify", "--quiet", f"refs/heads/{branch}",
                   execution=execution).returncode != 0:
                return ok                        # never delivered: no branch of its own in the base to take away
        else:
            ok = _by_registration(base, ["worktree", "remove", "--force", "--force", str(place)],
                                  execution).returncode == 0
        r = git(base, "branch", "-D", branch, execution=execution)
        if r.returncode and "used by worktree" in (r.stderr or "") and not _fs(execution).files.exists(str(place)):
            # …a worktree registration this path had before it was a repository of its own still claims the branch
            _by_registration(base, ["worktree", "remove", "--force", "--force", str(place)], execution)
            r = git(base, "branch", "-D", branch, execution=execution)
        return r.returncode == 0 and ok

