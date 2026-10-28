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


_PLACES: dict[str, _Place] = {}
_GUARD = threading.Lock()


def _place(path: Path) -> _Place:
    with _GUARD:
        return _PLACES.setdefault(os.path.normcase(os.path.abspath(path)), _Place())


@contextmanager
def snapshot(place, at, execution, edits: Optional[list] = None):
    """`place` copied to `at` for one run, yielded as a path. Where the copy cannot be made (a host that may not make
    symlinks, WinError 1314; a `cp -a` that failed or outran its time) the run is yielded None and works in the place
    itself — ALONE among the runs that fell back so: side by side there is the race this module exists to end. An
    engine error instead would void the batches already paid for, and a cause that does not pass (the host's
    privilege) would refuse the node's every validation. On leaving, the tracked files the run changed in the copy go
    into `edits` (paths relative to the place) and the copy is removed."""
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
