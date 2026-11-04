"""What the system's own records have in common: a file on this installation's data, which no session mounts, turning over,
and how a reading of many changed paths is said in a bounded line whatever a session chose to change."""
from __future__ import annotations

import collections
import contextlib
import json
import logging
import os
import time
from pathlib import Path

try:
    import fcntl
    msvcrt = None
except ImportError:
    fcntl = None
    import msvcrt

log = logging.getLogger(__name__)
#: a record turns over at this size, its last turn kept: what a session asks for fills no disk, and what it turns out is said
CAP = 16 * 2 ** 20
#: of one reading: the paths named, each at most this long, and the directories counted where not all could be named
NAMES, NAME_CUT, COUNTED = 200, 300, 50


def append(path: Path, row: dict, cap: "int | None" = None) -> None:
    """`row` on the record at `path`, turned over past `cap` with its last turn kept; a file a reader holds open just now
    goes on growing: a row is worth more than the size."""
    path.parent.mkdir(parents=True, exist_ok=True)
    with one_at_a_time(path.with_suffix(".lock")):
        turned = False
        if path.exists() and path.stat().st_size >= (CAP if cap is None else cap):
            try:
                os.replace(path, path.with_suffix(".jsonl.1"))
                turned = True
            except OSError as e:
                log.warning(f"the record {path.name} did not turn over now ({e}): it goes on growing")
        with path.open("a", encoding="utf-8") as f:
            f.write((json.dumps({"at": row["at"], "turned": "what came before the last turn is gone"}) + "\n" if turned else "") + json.dumps(row) + "\n")


def rows_of(path: Path) -> tuple:
    """(the rows of the record at `path`, how many of its lines could not be read): one torn line stops no reader."""
    rows, bad = [], 0
    for line in path.read_text(encoding="utf-8", errors="replace").splitlines() if path.exists() else ():
        try:
            rows.append(json.loads(line))
        except ValueError:
            bad += 1
    return rows, bad


def _lock(f) -> None:
    """Back once this holds `f`'s lock, across processes and across two opens in one."""
    if fcntl:
        fcntl.flock(f.fileno(), fcntl.LOCK_EX)
        return
    while True:
        try:
            f.seek(0)
            msvcrt.locking(f.fileno(), msvcrt.LK_NBLCK, 1)
            return
        except OSError:
            time.sleep(0.02)


@contextlib.contextmanager
def one_at_a_time(path: Path):
    """No other process or thread holds `path` while this runs: two writers on Windows tore rows and lost them (critic, ran)."""
    with open(path, "a+b") as f:
        _lock(f)
        yield


def said_of(entries: list) -> dict:
    """`entries` (`<type> <path>`) as one bounded line: the quietest directories named first, so what a session stamps over
    and over in one place displaces nothing elsewhere (critic, ran: 3000 files a second hid every other write), and where
    not all could be named, how many under each of the busiest."""
    by_dir = collections.defaultdict(list)
    for e in entries:
        by_dir[e.rpartition("/")[0]].append(e)
    named = [e[:NAME_CUT] for _, group in sorted(by_dir.items(), key=lambda kv: len(kv[1])) for e in group][:NAMES]
    busiest = sorted(by_dir.items(), key=lambda kv: -len(kv[1]))[:COUNTED]
    return {"changed": named, "changed_n": len(entries),
            **({"under": {d[:NAME_CUT]: len(g) for d, g in busiest}} if len(named) < len(entries) else {})}
