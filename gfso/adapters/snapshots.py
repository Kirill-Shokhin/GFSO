"""One run's own copy of a node's delivery, for the runs of ONE validation that work side by side.

GB_sql_database_tngtvm580 (2026-10-25): the root's validation ran in 12 batches at once, all in the root's one place,
and its pinned checks begin with `make clean`. One run's clean took `./sql_database` from under another's probes
(rc=127 on a binary present a moment later, clock skew, a vanished main.o); the validators fled to copies in their
scratch, and those copies' paths stood in the filed findings — a false root FAIL over a tree that passes every root
check alone. So each run gets a copy of its own, made where the work runs, and nothing registered anywhere: a crash
leaves a directory in the run's scratch, which the scratch's own rotation clears.

THE COPY OF A DELIVERY IS THE TREE DELIVER RECORDED, and nothing else (JOINT judge-on-the-delivered-tree): a copy of the
place as it stood carried whatever the executor's `.gitignore` hid — a hidden `impl.py` that `main.py` imports, a stale
binary c_compiler's 46 probes ran — an input nobody delivered, inside the judge's instrument. A checkout of the recorded
commit in a repository of the copy's own (`git init` where the copy runs: its links links, no registration a `worktree
prune` loses — what a `git worktree add` checkout lost, critics over wip/kappa d0fc0b5), then what the result needs built
is built there, by the system, from that tree alone (`_build`). Read BY ITS ID from the project's store
(`store.held`), never from a live place: a delivery is the system's from DELIVER on, whatever becomes of its place.
"""
from __future__ import annotations

import json
import logging
import re
import subprocess
from contextlib import contextmanager
from pathlib import Path
from typing import NamedTuple, Optional

from gfso.adapters import git as G, worktrees as W
from gfso.adapters.execution import ended_by_watch, past_disk
from gfso.config import subprocess_env
from gfso.core.types import IN_THE_WORKS_PATH, LAID, PlaceUnavailable

log = logging.getLogger(__name__)


#: a judge's copy or build the machine's memory watch ended near the shared ceiling: a neighbour's pressure, no verdict
#: on the delivery — asked again (`execution.ended_by_watch`)
WATCHED = "the validation's copy was ended by the machine's memory watch near the shared ceiling, not by the delivery"


class NotTheDelivery(Exception):
    """No copy of what was delivered can be made, and the DELIVERY is the cause: the tree DELIVER recorded cannot be
    read back whole as recorded — an object missing or rewritten, a commit not carrying that tree — or holds nested
    repositories whose files are no part of it (§11.3). The delivery's FAIL."""


class Uncopied(Exception):
    """No copy of what was delivered could be made for a cause NOT the delivery's — a Docker error, a pack outrunning
    its time, a full disk, the place's objects pruned: no verdict on it, the judge asked again (a FAIL is a verdict on
    the delivery, JOINT judge-on-the-delivered-tree)."""


class BuildFailed(Exception):
    """The judge's build of the delivered tree failed (`_build`): the delivery's FAIL, its text the cause, `command`
    what ran."""

    def __init__(self, cause: str, command: str):
        super().__init__(cause)
        self.command = command


#: how long the judge's build may run. c_compiler's `make -j4` takes seconds and a dependency install a few minutes; a
#: build still running at 10 minutes is read as hung — it has taken a sixth of a validation's visit (an hour,
#: `state_bound("VALIDATING")`) before any check, and every batch pays it again
BUILD_S = 600
#: the files GNU make reads by default, in its order: a delivered tree with one at its root is built by `make`
MAKEFILES = ("GNUmakefile", "makefile", "Makefile")


class Source(NamedTuple):
    """Where a judge's copy of a commit is read from, and what its guards hold it to: the git holding it whole
    (`repo`), what the place it was made in held on disk at DELIVER (`du_kib`, None unread: not refused), the gitlinks
    allowed in its tree (`links`, "<commit> <path>"), the commit credited against the tree bomb (`credit`: (where git
    runs, repository, revision) or None), and the base whose LFS store backs `repo`'s (`base`)."""
    repo: str
    du_kib: Optional[int]
    links: tuple
    credit: Optional[tuple]
    base: str


def live(place, execution) -> Source:
    """A place's own git read where it stands — the observation before a session, a test's place —, its comparators
    read off the place now: what it holds, its base's gitlinks and HEAD."""
    root = W.base_of(str(place)) or str(place)
    try:
        links = tuple(W.users_links(place, execution))
    except OSError:                       # …its base gone: no gitlink of it allowed
        links = ()
    return Source(str(place), W.du_kib(execution.session(str(place)), place), links, (execution.session(root), root, "HEAD"),
                  root)


@contextmanager
def snapshot(source, at, execution, edits: Optional[list] = None, delivered: Optional[tuple] = None,
             built: Optional[list] = None, unbuilt_ok: bool = False, build: bool = True):
    """A checkout at `at` of the commit `delivered` names — the (tree, commit, build) DELIVER recorded —, for one run,
    yielded as a path, read from `source`: the project's store by the delivery's id (`store.held`, a `Source`, or the
    call that reads it), or a git that holds it (`live`).
 What any place holds besides, ignored or changed since, is no part of it: a verdict is
    about the result as it stood at DELIVER (§11.3). Built (`_build`) before the run is handed it, what ran appended to
    `built`. On leaving, the tracked files the run changed in the copy go into `edits` and the copy is removed.

    A checkout the delivery makes impossible raises `NotTheDelivery`, one that fails for any other cause `Uncopied` —
    so does a delivery with no recorded commit: no live place is ever judged in its stead —, a failed build
    `BuildFailed`, all before anything runs in it; `unbuilt_ok`: a failed build is said in `built` and the copy yielded
    unbuilt (an issuer ruling on a FAIL that build made). Whatever the build left running ends with it, and a tracked
    file it changed is put back as delivered (`_after_build`). Not `build`: the checkout as recorded, nothing built nor
    put back — a reader that builds what it runs itself, inside its own bound (the contact reading, `validate._contact`):
    no build of the system's stands on the record's path for it, and none can fail there."""
    if not (commit := delivered[1] if delivered and delivered[1] else None):
        raise Uncopied("no commit was recorded for the delivery: no copy of it is made, and no place is judged as it "
                       "stands — deliver it again")
    # …read where the copy is taken, not before: a reader by id keeps what is absent first (`store.held`)
    at = Path(at)
    try:
        source = source() if callable(source) else source
        src = source if isinstance(source, Source) else live(source, execution)
        if at.resolve().is_relative_to(Path(src.repo).resolve()):
            raise OSError(f"{at} lies inside {src.repo}")
        # …the copy the system's own writing, no judge's growth against its disk bound (`ExecutionPort.system_writes`)
        with execution.system_writes(str(at)):
            execution.files.mkdir(str(at.parent))
            smudged = _checkout(src, at, *delivered[:2], execution)
    except PlaceUnavailable:
        raise                    # …the place down is its project's stop, not a copy to do without (`PlaceUnavailable`)
    except (OSError, subprocess.TimeoutExpired, NotTheDelivery, Uncopied) as e:
        try:
            execution.remove_tree(str(at))
        except (OSError, subprocess.TimeoutExpired) as e2:
            log.warning(f"the partial copy {at} stays for the scratch's rotation ({e2})")
        if isinstance(e, (NotTheDelivery, Uncopied)):
            raise
        raise Uncopied(f"no checkout of the delivery {commit[:12]} could be made: {e}") from e
    try:
        ran = "" if build else "nothing: this copy is not built — its reader builds what it runs"
        for step in (lambda: _build(at, delivered[2], execution),   # …where no client's state is (`client`)
                     lambda: _put_back(at, delivered[0], commit, execution, smudged)) if build else ():
            try:
                ran += step()
            except BuildFailed as e:
                if not unbuilt_ok:
                    raise
                ran += f"{'; ' if ran else ''}{e}"
            finally:
                execution.release(str(at))  # …every process the build left: the run starts in a fresh container
        if built is not None:
            built.append(ran)
        yield str(at)
        if edits is not None:      # …after a run that ended, not one that raised: its copy is no record
            edits.extend(changed_or_unknown(src.repo, at, execution, commit))
    finally:
        execution.remove_tree(str(at))


def judged_at(copy: str, place, execution) -> str:
    """Where a judge stands in `copy`, a checkout of the whole work tree `place` stands in: `place`'s own directory of
    it. A judge registered in `repo/pkg` read the commit of `repo` with `pkg` mapped onto the checkout's top, found none
    of its files and FAILed true work (critic over 4ac5e3a). The copy's top where `place` is a top or unread."""
    try:
        prefix = W.git(place, "rev-parse", "--show-prefix", execution=execution).stdout.strip() if place else ""
    except OSError:                       # …the place gone: the delivery is read by its id, from the top
        prefix = ""
    here = Path(copy) / prefix if prefix else Path(copy)
    return str(here) if prefix and execution.files.is_dir(str(here)) else str(copy)


def changed_or_unknown(place, at, execution, commit: Optional[str] = None, base: Optional[tuple] = None) -> list[str]:
    """`changed`, or nothing where it could not be read: a fact for the record, never the cause of a finished
    report being lost."""
    try:
        return changed(place, at, execution, commit, base)
    except Exception as e:            # noqa: BLE001 — informational, whatever went wrong
        log.warning(f"what the run changed in {at} could not be read ({e!r}) — no edits recorded")
        return []


def changed(place, at, execution, commit: Optional[str] = None, base: Optional[tuple] = None) -> list[str]:
    """The committed files that differ in the copy — content, kind, link target or presence; a touch is no change —
    from `commit`, the delivery the copy is a checkout of, read in the copy's own repository; else from the place as it
    stands. Each side is written as a git tree where the work runs: on the host, a link a container made is no file
    to read (WinError 1920) — EACH IN ITS OWN REPOSITORY AND CONTAINER (`W.git`): the place's in its executor's, the
    copy's in its round's, which already runs what the executor delivered (its checks); one container holding both ran
    the copy's config over the place's neighbours. The two compared entry by entry: a blob's id is its content's,
    whichever repository wrote it. Empty where either side could not be read: unknown is not "changed". `base`: the
    place's side, read once for many copies of it (`on_disk`)."""
    if commit:
        r = W.git(at, "ls-tree", "-r", "-z", "--full-tree", commit, execution=execution)
        head, a = commit, None if r.returncode else _entries(r.stdout)
    else:
        head, a = base or on_disk(place, execution) or (None, None)
    if not head:
        return []
    b = _tree(at, head, Path(at) / ".git" / "gfso-index-copy", execution)              # …gone with the copy
    return [] if a is None or b is None else sorted(p for p in a.keys() | b.keys() if a.get(p) != b.get(p))


def on_disk(place, execution) -> Optional[tuple]:
    """(HEAD, {path: mode and id} of its files as they stand in `place`) — the place's side of `changed`; None where
    it has no commit or could not be read."""
    if not (head := W.git(place, "rev-parse", "HEAD", execution=execution).stdout.strip()):
        return None
    with execution.scratch("gfso-index-", dir=execution.temp_of(str(place))) as d:   # …the place's own temp
        return head, _tree(place, head, Path(d) / "index", execution)


def _entries(listing: str) -> dict:
    """{path: mode and id} of an `ls-tree -r -z` listing."""
    return {p: meta for meta, _, p in (e.partition("\t") for e in listing.split("\0") if e)}


#: `_checkout`'s source, run in the place's own container (where its agent already works) over (commit, git's own
#: arguments): the recorded commit and the objects of its tree — the history not — packed to its output. Replace refs
#: off: one would hand a commit of the agent's choosing under the recorded id
_PACK = 'set -o pipefail; c=$1; shift; git "$@" rev-list --objects --no-walk "$c" | cut -d" " -f1 | ' \
        'git "$@" pack-objects -q --stdout'


#: `_checkout`'s end in the copy, run IN THE COPY'S OWN CONTAINER: "take" (the new copy, commit, tree) — the pack on
#: its input taken into a repository the system makes (`git init`, no template, no alternates): no config, hook, filter
#: driver or excludes of the executor's, nor of the base's, run under it, and the copy's own platform decides its links
#: and modes. Then EVERY object the commit needs is hashed again against its id — git does not, and an object rewritten
#: in the executor's store would check out as a delivery nobody made —, history cut at the commit (`shallow`). Exit 3:
#: nested repositories (their paths printed); exit 4: the tree cannot be read back as recorded; exit 7: an object of
#: it was not there to read, or the copy could not take them (the store's or the disk's, no verdict). "checkout" (the copy,
#: commit): the commit checked out from those objects alone, under the system's LFS filter where it runs one (`W.apart`),
#: over the LFS objects carried into the copy's own store before it (`W.lfs_into_copy`). Run `-I`, as every program the
#: system runs in an agent's tree: `python -c` imports from its cwd first, and a delivered `json.py` exiting 0 passed a
#: changed copy as the delivery (critic over 4817a32, run)
_CHECKOUT = r'''
import hashlib, json, os, subprocess, sys, threading
from pathlib import Path
how, at, commit, apart = sys.argv[1], Path(sys.argv[2]), sys.argv[3], sys.argv[5:]
# …the paths its checkout wrote as their Git LFS content ("smudged"), read before any build ran (`_checkout`) and laid
# beside the copy where its judge's container reads only (`LAID`)
_listed = at.parent.with_name(at.parent.name + ".laid") / "smudged"
SMUDGED = {bytes.fromhex(h) for h in _listed.read_text().split()} if how == "kept" and _listed.is_file() else set()
algo = "sha256" if len(commit) == 64 else "sha1"
env = None              # …the system's git environment (`G.env`), as every caller runs this under
BAD = 6 if how == "kept" else 4
# …an object not there to read when the copy is taken: the store's loss, no verdict (exit 7); in the copy after its build,
# the build's doing (6)
MISSING = BAD if how == "kept" else 7
# …nothing else runs in the copy's container while it is made: a reader ended past its memory's bound was ended by what
# the delivery holds, every time it is asked — its FAIL, the cause said, never a copy to wait for again
BOUND = "ended past the copy's memory bound (GFSO_CONTAINER_MEMORY)"


def bad(code, why):
    print(why)
    sys.exit(code)


def git(*args, **kw):
    r = subprocess.run(["git", *apart, *args], cwd=at, capture_output=True, env=env, **kw)
    if r.returncode == -9:
        bad(BAD, f"git {args[0]} reading it was {BOUND}")
    return r


def lost(p, why, code=None):
    try:
        if p.wait(timeout=5) == -9:
            why, code = why + f" (git cat-file reading it was {BOUND})", None
    except subprocess.TimeoutExpired:
        pass
    bad(code or BAD, why)


def verify(ids):
    """Each object of `ids` read and hashed again; the first object's content back."""
    p = subprocess.Popen(["git", *apart, "cat-file", "--batch"], cwd=at, stdin=subprocess.PIPE,
                         stdout=subprocess.PIPE, env=env)
    threading.Thread(target=lambda: (p.stdin.write(b"".join(i + b"\n" for i in ids)), p.stdin.close()),
                     daemon=True).start()
    first = None
    for i in ids:
        head = p.stdout.readline().split()
        if len(head) != 3 or head[0] != i:
            lost(p, f"its object {i.decode()} is missing", MISSING)
        h, left, content = hashlib.new(algo, head[1] + b" " + head[2] + b"\0"), int(head[2]), b""
        while left:
            chunk = p.stdout.read(min(left, 1 << 20)) or lost(p, f"its object {i.decode()} is cut short")
            h.update(chunk)
            left -= len(chunk)
            content = content or chunk
        p.stdout.read(1)
        if h.hexdigest().encode() != i:
            bad(BAD, f"its object {i.decode()} does not hold what its id names: rewritten after DELIVER")
        first = content if first is None else first
    p.wait()
    return first


def blob_id(data):
    return hashlib.new(algo, b"blob %d\0" % len(data) + data).hexdigest().encode()


def hashed(path, h):
    """`h` over the file `path`, read in chunks: a delivered file near the copy's memory bound is no FAIL of its own."""
    with open(path, "rb") as f:
        while chunk := f.read(1 << 20):
            h.update(chunk)
    return h.hexdigest()


def file_blob_id(path):
    return hashed(path, hashlib.new(algo, b"blob %d\0" % path.stat().st_size)).encode()


def pointed_oid(data):
    """The oid an LFS pointer `data` names, '' for none."""
    head = b"version https://git-lfs.github.com/spec/v1\n"
    keys = dict(ln.split(b" ", 1) for ln in data[len(head):].splitlines() if b" " in ln) if data.startswith(head) else {}
    oid = keys.get(b"oid", b"").removeprefix(b"sha256:").decode("ascii", "replace")
    return oid if len(oid) == 64 else ""


def lfs_object(data):
    """The copy's own store's file of the LFS object a pointer `data` names, only where its sha256 is the pointer's."""
    o = at / ".git" / "lfs" / "objects" / (oid := pointed_oid(data))[:2] / oid[2:4] / oid
    return o if oid and o.is_file() and hashed(o, hashlib.sha256()) == oid else None


def written(path, source, h, want):
    """`source` (a binary stream) into `path` a chunk at a time, hashed as it is written: what lands is what was
    checked, whatever a process the build left running does to the store meanwhile; False where it is not `want`."""
    with open(path, "wb") as f:
        while chunk := source.read(1 << 20):
            h.update(chunk)
            f.write(chunk)
    return h.hexdigest() == want


def put(path, mode, write):
    """`path` made by `write` as delivered, every directory above it a directory of the copy, not a link a build left."""
    d = at
    for part in path.relative_to(at).parts[:-1]:
        d = d / part
        if d.is_symlink() or (d.exists() and not d.is_dir()):
            d.unlink()
        d.mkdir(exist_ok=True)
    if path.is_symlink() or (path.exists() and not path.is_dir()):
        path.unlink()                       # …a fifo or a socket the build left too: opened, a fifo blocks the put
    elif path.is_dir():
        subprocess.run(["rm", "-rf", "--", str(path)])
    write(path)
    if mode != b"120000":
        os.chmod(path, 0o755 if mode == b"100755" else 0o644)


if how == "checkout":
    if (r := git("checkout", "-q", "-f", "--detach", commit)).returncode:
        sys.exit(r.stderr.decode(errors="replace")[-300:])
    sys.exit(0)
tree = sys.argv[4]
if how == "smudged":                # …right after the checkout, before any build: each path written as its LFS content
    # its sizes in one listing and its small blobs in one read — a call per file outran the copy's time on large trees —
    # and each path in hex, which no text decoding on the way out changes (critic over the LFS check)
    ls = git("ls-tree", "-r", "-l", "-z", "--full-tree", tree)
    small = [(rel, meta.split()[2]) for meta, _, rel in (e.partition(b"\t") for e in ls.stdout.split(b"\0") if e)
             if meta.split()[0] != b"120000" and meta.split()[3].isdigit() and int(meta.split()[3]) <= 1024]
    batch = git("cat-file", "--batch", input=b"".join(oid + b"\n" for _, oid in small))
    if ls.returncode or batch.returncode:   # …an empty list would put pointers back unflagged: fail closed
        sys.exit("its tree or its small blobs could not be read")
    got = batch.stdout
    for rel, oid in small:
        head, _, got = got.partition(b"\n")
        if len(head.split()) != 3:            # …"<oid> missing": no body follows
            continue
        data, got = got[:int(head.split()[2])], got[int(head.split()[2]) + 1:]
        path = at / rel.decode("utf-8", "surrogateescape")
        if (named := pointed_oid(data)) and path.is_file() and not path.is_symlink() and \
                hashed(path, hashlib.sha256()) == named:
            print(rel.hex())
    sys.exit(0)
if how == "kept":
    ls = git("ls-tree", "-r", "-z", "--full-tree", tree)
    if ls.returncode:
        bad(6, f"its tree cannot be read: {ls.stderr.decode(errors='replace')[-300:]}")
    items = [(meta.split(), p) for meta, _, p in (e.partition(b"\t") for e in ls.stdout.split(b"\0") if e)]
    items = [i for i in items if i[0][1] != b"commit"]      # …a submodule the user's commit records holds no object here, only "take" reads it
    verify(list(dict.fromkeys([tree.encode(), *(meta[2] for meta, _ in items)])))
    for (mode, _, oid), rel in items:
        path = at / rel.decode("utf-8", "surrogateescape")
        if mode == b"120000":
            if path.is_symlink() and blob_id(os.fsencode(os.readlink(path))) == oid:
                continue
        elif path.is_file() and not path.is_symlink() and (mode == b"100755") == bool(path.stat().st_mode & 0o100):
            # …save the pointer of a file its checkout wrote as content: the build wrote the pointer back, and the
            # checks would read it (critic over the LFS check)
            if file_blob_id(path) == oid and rel not in SMUDGED:
                continue
        o, wrong = oid.decode(), f"its object {oid.decode()} does not hold what its id names"
        size = int(git("cat-file", "-s", o).stdout or b"-1")
        # …read whole only where small: a link's target, an LFS pointer
        data = git("cat-file", "blob", o).stdout if mode == b"120000" or 0 <= size <= 1024 else None  # …`lfs.LONGEST`
        if data is not None and blob_id(data) != oid:
            bad(6, wrong)
        obj = lfs_object(data) if data is not None and mode != b"120000" else None
        if obj is None and rel in SMUDGED:
            # …its checkout wrote its content: as it stands, it is kept; else the build took the object it is put back
            # from — the delivery broke its judge's copy, and put back as its pointer every check read the pointer
            # (critic over the bounds)
            if path.is_file() and not path.is_symlink() and (mode == b"100755") == bool(path.stat().st_mode & 0o100) \
                    and hashed(path, hashlib.sha256()) == pointed_oid(data):
                continue
            bad(6, f"the build removed the Git LFS object of {rel.decode('utf-8', 'replace')} from the copy")
        if mode == b"120000":
            put(path, mode, lambda p: os.symlink(os.fsdecode(data), p))
        elif obj is not None:
            if path.is_file() and not path.is_symlink() and path.stat().st_size == obj.stat().st_size and (
                    mode == b"100755") == bool(path.stat().st_mode & 0o100) and hashed(path, hashlib.sha256()) == obj.name:
                continue
            with open(obj, "rb") as src:
                put(path, mode, lambda p: written(p, src, hashlib.sha256(), obj.name) or bad(6, wrong))
        else:
            cat = subprocess.Popen(["git", *apart, "cat-file", "blob", o], cwd=at, stdout=subprocess.PIPE, env=env)
            head = hashlib.new(algo, b"blob %d\0" % size)
            put(path, mode, lambda p: written(p, cat.stdout, head, o) or lost(cat, wrong))
            cat.wait()
        print(rel.decode("utf-8", "replace"))
    sys.exit(0)
r = subprocess.run(["git", *apart, "init", "-q", "--template=", f"--object-format={algo}", str(at)],
                   capture_output=True, env=env, text=True)
if r.returncode:
    sys.exit(r.stderr[-300:])
if (r := git("index-pack", "--stdin", stdin=sys.stdin.buffer)).returncode:     # …the copy's own disk or the stream
    bad(MISSING, f"its objects could not be taken into the copy: {r.stderr.decode(errors='replace')[-300:]}")
if not (verify([commit.encode()]) or b"").startswith(f"tree {tree}\n".encode()):
    bad(4, f"its commit {commit} does not carry the tree {tree}")
ls = git("ls-tree", "-r", "-t", "-z", "--full-tree", tree)
if ls.returncode:
    bad(4, f"its tree cannot be read: {ls.stderr.decode(errors='replace')[-300:]}")
items = [(meta.split(), p) for meta, _, p in (e.partition(b"\t") for e in ls.stdout.split(b"\0") if e)]
KEPT = set(json.loads(os.environ.get("GFSO_USERS_LINKS") or "[]"))
if nested := [p.decode(errors="replace") for meta, p in items if meta[1] == b"commit" and f"{meta[2].decode()} {p.decode(errors='replace')}" not in KEPT]:
    bad(3, "\n".join(nested))
items = [i for i in items if i[0][1] != b"commit"]
verify(list(dict.fromkeys([tree.encode(), *(meta[2] for meta, _ in items)])))
(at / ".git" / "shallow").write_bytes(commit.encode() + b"\n")
'''


def _checkout(src: Source, at: Path, tree: str, commit: str, execution) -> set[str]:
    """`at` made the checkout of `commit` (`_CHECKOUT`), its objects STREAMED from where `src`'s git runs — the
    project's store in its own container, a live place in its —, where `_PACK` packs them, into the copy's, which takes
    them in — one pipe between the two (`ExecutionPort.pipe`): nothing of the pack is held by the server or laid where
    the executor's agent writes, and no cap but the disk bounds a delivery (a pack read into the server's memory, capped
    at 512 MiB, left a larger delivery never judged). The LFS objects its pointers name are carried into the copy's own
    store the same way, each only where it is its pointer's (`W.lfs_into_copy`), before the checkout writes their
    content. A judge mounts nothing of the place, the base, the store or the node's temp (`PlaceContainer._mounts`).
    `NotTheDelivery` where its tree holds nested repositories but those `src` allows — their files are no part of the
    tree DELIVER recorded: it records their commit, whose objects are their agent's to forge —, cannot be read back as
    recorded, or lays past what its place held at DELIVER (`W.tree_past_place`); `Uncopied` where an object of it is
    missing — the system's loss, never the delivery's FAIL —; `OSError` where the copy could not be made."""
    ex, end = execution.session(str(at)), [execution.python, "-I", "-c", _CHECKOUT]
    there, env = execution.session(src.repo), G.env()
    rc, err, r = there.pipe([there.shell() or "bash", "-c", _PACK, "sh", commit, *G.APART], cwd=src.repo, env=env, into=ex,
                            into_args=[*end, "take", str(at), commit, tree, *G.APART], into_cwd=str(at.parent),
                            into_env={**env, "GFSO_USERS_LINKS": json.dumps(list(src.links))}, timeout=1800)
    said = (r.stdout or "").split()
    if r.returncode == 3:
        raise NotTheDelivery(f"the delivery holds nested repositories ({', '.join(said[:5])}): their files are no part "
                             f"of the tree DELIVER recorded ({commit[:12]}), so no copy can be made of it — commit their "
                             f"files into the node's own repository instead")
    if r.returncode == 7 or rc and re.search(r"missing \w+ object|bad object|corrupt|invalid object|unable to read",
                                             err or "", re.I):
        raise Uncopied(f"an object of the delivery {commit[:12]} is missing where it is read from ({src.repo}): "
                       f"{(err or r.stdout or '').strip()[-300:]}")
    if rc:
        raise OSError(f"{src.repo} could not pack {commit[:12]}: {err.strip()[-300:]}")
    if r.returncode == 4 and ended_by_watch(ex):
        raise Uncopied(WATCHED)
    if r.returncode == 4:
        raise NotTheDelivery(f"the tree DELIVER recorded ({commit[:12]}) cannot be read back as recorded: "
                             f"{(r.stdout or '').strip()[-300:]}")
    if r.returncode:
        raise OSError(f"the copy {at} could not take its delivery {commit[:12]}: {(r.stderr or '').strip()[-300:]}")
    W.lfs_into_copy(src.base, src.repo, at, commit, execution)
    if past := W.tree_past_place(ex, at, commit, src.du_kib, src.credit, (at / ".git" / "lfs" / "objects",)):
        raise NotTheDelivery(past)
    r = ex.run([*end, "checkout", str(at), commit, tree, *W.apart(execution)], cwd=str(at.parent), timeout=1800,
               env=env)
    # …ended past the copy's memory bound, the same each time it is asked: a FAIL that says so (§8.4), not a copy waited
    # for forever. NOT HELD: git reads a Git LFS file whole through its filter here, so one about the bound's size
    # fails an honest delivery — the cause names the dial that lifts it
    if r.returncode == 4 and ended_by_watch(ex):
        raise Uncopied(WATCHED)
    if r.returncode == 4:
        raise NotTheDelivery(f"the tree DELIVER recorded ({commit[:12]}) cannot be checked out within its judge's memory "
                             f"bound — a Git LFS file is read whole here; GFSO_CONTAINER_MEMORY lifts it: "
                             f"{(r.stdout or '').strip()[-300:]}")
    if r.returncode:
        raise OSError(f"the copy {at} could not check out its delivery {commit[:12]}: {(r.stderr or '').strip()[-300:]}")
    # …the paths it wrote as their LFS content, read now, before any build: by the attributes it checked out under,
    # not by what a blob looks like — a pointer-shaped file outside the filter stays its text (critic over the LFS check)
    r = ex.run([*end, "smudged", str(at), commit, tree, *G.APART], cwd=str(at.parent), timeout=1800, env=env)
    if r.returncode:
        raise OSError(f"the copy {at} could not say which of its files hold LFS content: {r.stderr.strip()[-300:]}")
    return set(r.stdout.split())


def _after_build(at: Path, tree: str, commit: str, execution, smudged: set = frozenset()) -> str:
    """The copy's tracked files as DELIVER recorded them once the build has run (`_CHECKOUT` "kept"), each it changed
    put back from the copy's own objects, hashed again — what is said of it appended to what ran. A build writes its
    outputs, never the delivered sources: a process it started rewrote `main.c` after it "succeeded", and every check
    after read a tree never delivered (critic over 909e417). Put back rather than failed: an honest build may regenerate
    a tracked file (a parser's generated source, a lock file stamped with a time), and its checks then run over the
    delivered one. Objects of the copy's own repository the build rewrote leave nothing to put back from: `BuildFailed`
    — the delivered code broke its judge's copy."""
    # …which the checkout smudged, laid where the copy's container reads only: no build reaches it, and a list on the
    # command line passed Windows' 32K at some 500 files (critic over the LFS check)
    try:
        execution.files.mkdir(laid := str(at.parent) + LAID)
        execution.files.write_files(laid, {"smudged": "\n".join(sorted(smudged)).encode()})
    except OSError as e:          # …where it lies in the build's own root (a system check's copy), the build broke it
        raise BuildFailed(f"the build broke the directory the system lays beside its copy: {e}",
                          "the judge's check of the delivered files") from e
    finally:
        execution.release(laid)
    ex = execution.session(str(at))
    r = ex.run([execution.python, "-I", "-c", _CHECKOUT, "kept", str(at), commit, tree, *G.APART], cwd=str(at.parent),
               timeout=BUILD_S, env=G.env())
    if r.returncode == 137 and ended_by_watch(ex):
        raise Uncopied(WATCHED)
    if r.returncode == 137 and (past := past_disk(ex)):
        raise BuildFailed(f"the build was ended: {past}", "the judge's check of the delivered files")
    if r.returncode:
        why = ("putting them back was ended past the copy's memory bound (GFSO_CONTAINER_MEMORY)" if r.returncode == 137
               else (r.stdout or r.stderr or "").strip()[-300:])
        raise BuildFailed(f"the build changed the copy's own repository, so its delivered files cannot be put back: "
                          f"{why}", "the judge's check of the delivered files")
    put = (r.stdout or "").splitlines()
    return (f"; it changed {len(put)} delivered file(s), put back as delivered before any check: "
            f"{', '.join(put[:10])}" if put else "")


def _put_back(at: Path, tree: str, commit: str, execution, smudged: set) -> str:
    """`_after_build`, the system's own write: no judge's growth against its disk bound."""
    with execution.system_writes(str(at)):
        return _after_build(at, tree, commit, execution, smudged)


def _build(at: Path, declared: Optional[str], execution) -> str:
    """The delivered tree built in its copy `at` where the copy's judge runs — its container, under its way out —
    before any check: DELIVER's `build` where it gave one (an empty one: nothing to build); else, where the tree has a
    makefile at its root, its default target (`make`); else nothing. Said back as the executor's next packet says it;
    a build that fails or outruns `BUILD_S` raises `BuildFailed`, the tail of its output the cause. What it makes stays
    in this copy."""
    if declared is None and any(execution.files.exists(str(at / m)) for m in MAKEFILES):
        declared, which = "make", "the delivered Makefile's default target (`make`: no `build` was declared at DELIVER)"
    # …a build of quotes alone is how a client writes "none" (`""` from a live in_chat run): run, it is 127, not a build
    elif (declared or "").strip(" \t\r\n\"'`"):
        which = f"the build declared at DELIVER (`{declared}`)"
    else:
        return ("nothing: DELIVER declared nothing to build (`build: \"\"`)" if declared is not None else
                "nothing: no `build` was declared at DELIVER and the delivered tree has no Makefile at its root")
    ex = execution.session(str(at))
    try:
        r = ex.run([ex.shell() or "sh", "-c", "exec 2>&1\n" + IN_THE_WORKS_PATH + declared], cwd=str(at), timeout=BUILD_S,
                   env=subprocess_env())
    except subprocess.TimeoutExpired:
        raise BuildFailed(f"the judge built with {which}, and it was still running at {BUILD_S} s: ended, and no check "
                          f"was run", declared) from None
    if r.returncode == 137 and ended_by_watch(ex):
        raise Uncopied(WATCHED)
    if r.returncode == 137 and (past := past_disk(ex)):
        raise BuildFailed(f"the judge built with {which}, and it was ended: {past}; no check was run", declared)
    if r.returncode:
        out = f"{r.stdout or ''}{r.stderr or ''}".strip()
        raise BuildFailed(f"the judge built with {which}, and it exited {r.returncode}, so no check was run — its "
                          f"output's end: {out[-1500:] or '(nothing)'}", declared)
    return f"{which}, which succeeded"


def _tree(where, head: str, index: Path, execution) -> Optional[dict]:
    """{path: mode and id} of `head`'s files as they stand on disk in `where`, built in an index of its own (`index`):
    the place's commit on both sides, whatever a run committed in its copy."""
    env = {"GIT_INDEX_FILE": str(index)}
    for args in (("read-tree", head), ("add", "-u")):
        if W.git(where, *args, execution=execution, env=env).returncode != 0:
            return None
    if not (t := W.git(where, "write-tree", execution=execution, env=env).stdout.strip()):
        return None
    r = W.git(where, "ls-tree", "-r", "-z", "--full-tree", t, execution=execution)
    return None if r.returncode else _entries(r.stdout)


def swap(text: str, frm, to) -> str:
    """`text` with the directory `frm` named as `to`, in every spelling a path arrives in — either separator, doubled
    inside JSON, msys's `/c/` (and `/mnt/c/`, `/cygdrive/c/`), either drive case — each written back in the spelling
    it came in: a PATH entry `/c/…` rewritten `C:/…` is no entry at all. A whole path: not the tail of another
    (`/mnt/c/x` is no `/c/x`), not the prefix of a sibling (`…/root` is not `…/root.select`). `to` stands on the same
    drive as `frm` — a run's copy is made beside the place."""
    src, dst = Path(frm), Path(to)
    sep = r"[\\/]{1,4}"
    d = re.escape(src.drive[:1])
    head = rf"(?<![\w.-])(?P<head>{d}:|(?:/mnt|/cygdrive)?/{d}(?=[\\/]))" if d else r"(?<![\w.-])(?P<head>)"
    rx = re.compile(head + sep + sep.join(re.escape(p) for p in src.parts[1:]) + r"(?![\w.-])",
                    re.IGNORECASE if d else 0)

    def _as(m) -> str:
        b = re.search(r"[\\/]+", m.group(0)[len(m["head"]):]).group(0)
        return m["head"] + b + b.join(dst.parts[1:])
    return rx.sub(_as, text)
