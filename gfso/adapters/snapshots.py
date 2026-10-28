"""One run's own copy of a node's place, as it stands on disk, for the runs of ONE validation that work side by side.

GB_sql_database_tngtvm580 (2026-10-25): the root's validation ran in 12 batches at once, all in the root's one place,
and its pinned checks begin with `make clean`. One run's clean took `./sql_database` from under another's probes
(rc=127 on a binary present a moment later, clock skew, a vanished main.o); the validators fled to copies in their
scratch, and those copies' paths stood in the filed findings — a false root FAIL over a tree that passes every root
check alone. A checkout of the delivery's commit per run (`git worktree add`) lost the place's symlinks to a
`core.symlinks=false` git on either side and its registrations to a container's `worktree prune` (critics over
wip/kappa d0fc0b5): what a validator judges is the place ON DISK — uncommitted files, build outputs, links — so that
is what each run gets, copied where the work runs (`ExecutionPort.copy_tree`), and nothing registered anywhere: a
crash leaves a directory in the run's scratch, which the scratch's own rotation clears.
"""
from __future__ import annotations

import inspect
import json
import logging
import os
import re
import subprocess
import threading
from contextlib import contextmanager
from pathlib import Path
from typing import Optional

from gfso.adapters import worktrees as W
from gfso.config import subprocess_env
from gfso.core.types import PlaceUnavailable

log = logging.getLogger(__name__)


class _Place:
    """Who may stand in one place: copies read it side by side; a run that works in the place itself has it alone —
    no other such run beside it, and no copy being taken of a tree its `make clean` is tearing."""

    def __init__(self):
        self._c, self._copying, self._held = threading.Condition(), 0, False

    @contextmanager
    def enter(self, alone: bool):
        """Stand in the place — `alone`, to work in it; else to copy it, beside other copies — once it is free so."""
        with self._c:
            self._c.wait_for(lambda: not self._held and not (alone and self._copying))
            if alone:
                self._held = True
            else:
                self._copying += 1
        try:
            yield
        finally:
            with self._c:
                if alone:
                    self._held = False
                else:
                    self._copying -= 1
                self._c.notify_all()


class NotTheDelivery(Exception):
    """The copy made to judge is not what was delivered: the place changed after DELIVER (§11.3)."""


_PLACES: dict[str, _Place] = {}
_GUARD = threading.Lock()


def _place(path: Path) -> _Place:
    with _GUARD:
        return _PLACES.setdefault(os.path.normcase(os.path.abspath(path)), _Place())


@contextmanager
def snapshot(place, at, execution, edits: Optional[list] = None, delivered: Optional[tuple] = None):
    """`place` copied to `at` for one run, yielded as a path. Where the copy cannot be made (a host that may not make
    symlinks, WinError 1314; a `cp -a` that failed or outran its time) the run is yielded None and works in the place
    itself — ALONE among the runs that fell back so: side by side there is the race this module exists to end. An
    engine error instead would void the batches already paid for, and a cause that does not pass (the host's
    privilege) would refuse the node's every validation. On leaving, the tracked files the run changed in the copy go
    into `edits` (paths relative to the place) and the copy is removed.

    `delivered`: the (tree, commit) DELIVER recorded. A copy whose tracked files are not that tree is no copy of the
    delivery — a process its executor left running changed the place after DELIVER — and raises `NotTheDelivery`
    before anything runs in it: a verdict is about the result as it stood at DELIVER (§11.3). What git does not track
    (a build) is judged as it stands. A delivery with no recorded commit — no git base, a record from before the
    commit was kept — is judged as it stands, as before."""
    place, at = Path(place), Path(at)
    try:
        if at.resolve().is_relative_to(place.resolve()):   # a scratch inside the place (no git base): no copy of a tree into itself
            raise OSError(f"{at} lies inside {place}")
        with _place(place).enter(alone=False):
            execution.copy_tree(str(place), str(at))
            _own_git(place, at, execution)
    except PlaceUnavailable:
        raise                    # …the place down is its project's stop, not a copy to do without (`PlaceUnavailable`)
    except (OSError, subprocess.TimeoutExpired) as e:
        log.warning(f"no snapshot of {place} at {at} ({e}) — this run validates the place itself, alone")
        try:
            execution.remove_tree(str(at))
        except (OSError, subprocess.TimeoutExpired) as e2:
            log.warning(f"the partial copy {at} stays for the scratch's rotation ({e2})")
        with _place(place).enter(alone=True):
            yield None
        return
    try:
        if delivered and delivered[1] and (why := _not_delivered(place, at, *delivered, execution)):
            raise NotTheDelivery(why)
        yield str(at)
        if edits is not None:      # …after a run that ended, not one that raised: its copy is no record
            edits.extend(_changed_or_unknown(place, at, execution))
    finally:
        execution.remove_tree(str(at))


def _changed_or_unknown(place, at, execution) -> list[str]:
    """`changed`, or nothing where it could not be read: a fact for the record, never the cause of a finished
    report being lost."""
    try:
        return changed(place, at, execution)
    except Exception as e:            # noqa: BLE001 — informational, whatever went wrong
        log.warning(f"what the run changed in {at} could not be read ({e!r}) — no edits recorded")
        return []


#: `_own_git`, run IN THE COPY'S OWN CONTAINER over (place, copy): it reads the copy and what that container mounts — the
#: place itself only as a path, never its files, so a link the place's agent left leads nowhere — and keeps links links
_OWN_GIT = r'''
import os, shutil, subprocess, sys
from pathlib import Path
place, at = sys.argv[1], Path(sys.argv[2])
dot = at / ".git"
if dot.is_dir():
    alt = dot / "objects" / "info" / "alternates"
    if alt.is_file():
        borrowed = os.path.normpath(os.path.join(place, ".git", "objects", alt.read_text(encoding="utf-8").strip()))
        alt.write_bytes((Path(os.path.relpath(borrowed, dot / "objects")).as_posix() + "\n").encode())
elif dot.is_file():
    gitdir = Path(os.path.normpath(os.path.join(place, dot.read_text(encoding="utf-8").split("gitdir:", 1)[1].strip())))
    if (gitdir / "commondir").is_file() and not (gitdir / "commondir").is_symlink():
        common = os.path.normpath(gitdir / (gitdir / "commondir").read_text(encoding="utf-8").strip())
        dot.unlink()
        shutil.copytree(gitdir, dot, symlinks=True, ignore=shutil.ignore_patterns("gitdir", "locked", "*.lock"))
        (dot / "commondir").write_text(Path(os.path.relpath(common, dot)).as_posix() + "\n", encoding="utf-8")
        head = subprocess.run(["git", *sys.argv[3:], "--git-dir", str(dot), "rev-parse", "HEAD"], capture_output=True,
                              text=True)
        (dot / "HEAD").write_text(head.stdout.strip() + "\n", encoding="utf-8")
'''


def _own_git(place: Path, at: Path, execution) -> None:
    """A node's place is a worktree whose `.git` names its gitdir relatively: copied, it names nothing — and pointed
    back, every run would share one index (its lock: concurrent `git status` fail) and HEAD (a run's commit would move
    the delivery's branch). The copy gets a gitdir of its own: the worktree's files, HEAD detached at the place's
    commit, the repository's objects shared through a relative `commondir` that reads the same in a container. A node's
    own repository's copy is one too: only where it borrows from moves (relative alternates). Done by one call in the
    copy's own container (`_OWN_GIT`)."""
    ex = execution.session(str(at))
    r = ex.run([ex.python, "-c", _OWN_GIT, str(place), str(at), *W.APART], cwd=str(at), timeout=600,
               env=subprocess_env(extra=W.NO_CONFIG))
    if r.returncode != 0:
        raise OSError(f"the copy {at} could not get a git of its own: {(r.stderr or '').strip()[-300:]}")


def changed(place, at, execution) -> list[str]:
    """The place's committed files that differ in the copy — content, kind, link target or presence; a touch is no
    change. Each side is written as a git tree where the work runs: on the host, a link a container made is no file
    to read (WinError 1920) — EACH IN ITS OWN REPOSITORY AND CONTAINER (`W.git`): the place's in its executor's, the
    copy's in its round's, which already runs what the executor delivered (its checks); one container holding both ran
    the copy's config over the place's neighbours. The two compared entry by entry: a blob's id is its content's,
    whichever repository wrote it. Empty where either side could not be read: unknown is not "changed"."""
    head = W.git(place, "rev-parse", "HEAD", execution=execution).stdout.strip()
    if not head:
        return []
    with execution.scratch("gfso-index-", dir=execution.temp_of(str(place))) as d:   # …the place's own temp
        a = _tree(place, head, Path(d) / "index", execution)
    b = _tree(at, head, Path(at) / ".git" / "gfso-index-copy", execution)              # …gone with the copy
    return [] if a is None or b is None else sorted(p for p in a.keys() | b.keys() if a.get(p) != b.get(p))


#: `_judges_git`, run in the copy's own container. The copy's `.git` is neutralised where it stands — the system's
#: config (the base's settings a node's repository is made with, `W.INHERITED`, and the object format), the base's
#: `info/*` (`W.kept_out`), no hooks, no `commondir` (its objects borrowed instead), a gitfile or a link replaced by a
#: git of its own — so `.git/modules` stays and nothing of the executor's runs under a judge's git. The tree is
#: written in a git dir the system makes beside the copy (GIT_DIR, the copy its work tree, its objects borrowed),
#: staged by the one rule DELIVER staged by (`W.stage`, whose source is handed in). Exit 3: nested repositories.
_JUDGES_GIT = r'''
import json, os, shutil, subprocess, sys
from pathlib import Path
at, commit, delivered, base = Path(sys.argv[1]), sys.argv[2], sys.argv[3], Path(sys.argv[4])
given, apart = json.loads(sys.argv[5]), sys.argv[6:]
DELIVERED = tuple(given["spec"])
exec(given["stage"])


def put(path, text):                                     # …LF on any host: a CR ends no path git reads
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(text.encode() if isinstance(text, str) else text)


def objects_of(gitdir):
    """The object stores a git dir reads: its own, and its `commondir`'s."""
    out, common = [gitdir / "objects"], gitdir / "commondir"
    if common.is_file() and not common.is_symlink():
        out.append(Path(os.path.normpath(gitdir / common.read_text(encoding="utf-8", errors="replace").strip())) / "objects")
    return out


def borrow(gitdir, stores):
    put(gitdir / "objects/info/alternates",
        "".join(Path(os.path.relpath(s, gitdir / "objects")).as_posix() + "\n" for s in stores))


def run(*args, **env):
    return subprocess.run(["git", *apart, *args], cwd=at, capture_output=True, text=True, encoding="utf-8",
                          errors="replace", env={**os.environ, **env})


dot = at / ".git"
fmt = ""
if dot.is_dir() and not dot.is_symlink():
    fmt = subprocess.run(["git", "config", "-f", str(dot / "config"), "--get", "extensions.objectFormat"],
                         capture_output=True, text=True).stdout.strip()
    stores = objects_of(dot)
    if len(stores) > 1:
        old = (dot / "objects/info/alternates").read_text(encoding="utf-8", errors="replace") \
            if (dot / "objects/info/alternates").is_file() else ""
        put(dot / "objects/info/alternates", old + Path(os.path.relpath(stores[1], dot / "objects")).as_posix() + "\n")
        (dot / "commondir").unlink()
    for gone in ("hooks", "info", "config.worktree"):
        p = dot / gone
        shutil.rmtree(p) if p.is_dir() and not p.is_symlink() else p.unlink() if os.path.lexists(p) else None
else:
    stores = []
    if dot.is_file() and not dot.is_symlink():
        stores = objects_of(Path(os.path.normpath(
            at / dot.read_text(encoding="utf-8", errors="replace").split("gitdir:", 1)[-1].strip())))
    if os.path.lexists(dot):
        dot.unlink()
    for d in ("objects", "refs/heads"):
        (dot / d).mkdir(parents=True)
    borrow(dot, stores)
    put(dot / "HEAD", commit + "\n")
config = f"[core]\n\trepositoryformatversion = {1 if fmt else 0}\n\tbare = false\n"
config += f"[extensions]\n\tobjectFormat = {fmt}\n" if fmt else ""
for k in given["inherited"]:
    v = subprocess.run(["git", "config", "-f", str(base / ".git" / "config"), "--get", k], capture_output=True, text=True)
    if v.returncode == 0 and v.stdout.strip():
        config += f"[{k.split('.')[0]}]\n\t{k.split('.')[1]} = {v.stdout.strip()}\n"
own = at.parent / ("gfso-judge-" + os.urandom(4).hex())
for gitdir in (dot, own):
    put(gitdir / "config", config)
    for name, text in given["kept_out"].items():
        put(gitdir / "info" / name, text.encode("latin-1"))
for d in ("objects", "refs/heads"):
    (own / d).mkdir(parents=True, exist_ok=True)
borrow(own, [dot / "objects"])
put(own / "HEAD", commit + "\n")
git = lambda *a: run(*a, GIT_DIR=str(own), GIT_WORK_TREE=str(at))
if (r := git("read-tree", commit)).returncode or (r := stage(git)).returncode:
    sys.exit(r.stderr[-300:])
tree = git("write-tree").stdout.strip()
nested = [line.split("\t", 1)[1] for line in git("ls-tree", "-r", tree).stdout.splitlines() if line.startswith("160000")]
if nested:
    print("\n".join(nested))
    sys.exit(3)
if tree != delivered:
    print("\n".join(git("diff-tree", "-r", "--name-only", delivered, tree).stdout.splitlines()) or tree)
    sys.exit(4)
'''


def _not_delivered(place, at, tree: str, commit: str, execution) -> Optional[str]:
    """Why the copy at `at` is not the delivery — its files staged as DELIVER staged them (`W.stage`) over a git the
    system made (`_JUDGES_GIT`), written as a tree and held against the `tree` the system recorded — or None where it
    is. NOTHING OF THE COPY'S `.git` IS READ FOR BEHAVIOUR: its config, hooks, attributes and excludes are its
    executor's, and a filter they name, run in the copy's container before its judge, could change the copy after this
    look, or hash a changed file as delivered (critics over cba729f: a `commondir` led to a config of its own). Its
    objects are borrowed — a forged one can only make the tree differ. The copy keeps its neutralised git: a judge's git
    runs no filter of the executor's. A nested repository's files are no part of the recorded tree — DELIVER records its
    commit, whose objects are its agent's to forge — so a delivery holding one is not judged, and that is named. A
    repository whose executor ran a clean filter of its own at DELIVER is not reproduced and reads as changed."""
    base = W.base_of(str(place)) or str(place)
    given = {"inherited": W.INHERITED, "spec": W.DELIVERED, "stage": inspect.getsource(W.stage),
             "kept_out": {k: v.decode("latin-1") for k, v in W.kept_out(base).items()}}
    ex = execution.session(str(at))
    r = ex.run([ex.python, "-c", _JUDGES_GIT, str(at), commit, tree, str(base), json.dumps(given), *W.APART],
               cwd=str(at), timeout=1800, env=subprocess_env(extra=W.NO_CONFIG))
    said = (r.stdout or "").split()
    if r.returncode == 0:
        return None
    if r.returncode == 3:
        return (f"the delivery holds nested repositories ({', '.join(said[:5])}): their files are no part of the tree "
                f"DELIVER recorded ({commit[:12]}), so no copy can be held to it — commit their files into the node's "
                f"own repository instead")
    if r.returncode == 4:
        return (f"the place changed after DELIVER ({commit[:12]}): {len(said)} tracked file(s) differ — "
                f"{', '.join(said[:5])}")
    return f"the copy could not be held to its delivery {commit[:12]}: {(r.stderr or '').strip()[-300:]}"


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
    return None if r.returncode else {p: meta for meta, _, p in (e.partition("\t") for e in r.stdout.split("\0") if e)}


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
