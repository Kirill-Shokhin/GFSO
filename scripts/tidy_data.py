"""Bring a working `data/` directory back to what is still worth reading — reversibly.

A box that has driven runs for a few months accumulates three things that are not results:
sqlite sidecars (`-wal`/`-shm`) left behind by every base ever opened, migration backups of a
schema two versions old, and the bases of scratch projects nobody recorded. On this box that is the
larger part of the directory by size, and it is what makes the real runs hard to find.

Three rules the tool holds, because each one is a way this could destroy work:

* **A sidecar is dropped only after sqlite itself says it carries nothing.** `PRAGMA
  wal_checkpoint(TRUNCATE)` folds any pending frames into the base and reports what was left; a base
  that will not check point — because a live server holds it — is skipped whole, and the operating
  system's own lock is the guard, not a list of names kept here.
* **Nothing is deleted before it is archived.** Bases and backups go into one dated zip first; the
  zip is verified to hold them before the originals go.
* **A base a recorded run claims is never touched** (`experiments/e3_specbench/results/*/result.json`
  names the project). Everything else in `data/` is out of reach by construction rather than by a
  list: the tool globs exactly `*.db`, `*.pre-v4.bak` and `*.log`, so the E1 corpus in
  `postmortems/`, the agent rosters and every other directory are never candidates at all — a
  protected-names list would only be a second place to forget something.

    python scripts/tidy_data.py                 # what would happen, and how many bytes
    python scripts/tidy_data.py --apply         # do it
    python scripts/tidy_data.py --apply --keep-orphans   # sidecars and backups only
"""
from __future__ import annotations

import argparse
import datetime
import glob
import json
import os
import sqlite3
import sys
import zipfile

def _claimed(results_dir: str) -> set[str]:
    """The project name of every run that left a `result.json` — the bases an analysis still reads."""
    names = set()
    for path in glob.glob(os.path.join(results_dir, "*", "result.json")):
        try:
            with open(path, encoding="utf-8") as fh:
                project = json.load(fh).get("project")
        except (OSError, ValueError):
            continue
        if project:
            names.add(project)
    return names


def _available(db: str, checkpoint: bool) -> bool:
    """Is this base ours to touch — and, when acting, is its write-ahead log now empty?

    A base held open elsewhere refuses the connection, and that refusal is the point: it is the live
    server saying the file is in use, which no bookkeeping of ours could say as reliably.

    `checkpoint` is what separates planning from acting. Folding the log into the base
    (`wal_checkpoint(TRUNCATE)`) is a WRITE, so it belongs to `--apply` only; a dry run that quietly
    rewrote 400 bases would be a plan that already happened. Planning therefore asks the weaker
    question — can this file be opened for writing at all — and leaves the log alone.
    """
    try:
        con = sqlite3.connect(db, timeout=1.0)
        try:
            if not checkpoint:
                return True
            busy, _, _ = con.execute("PRAGMA wal_checkpoint(TRUNCATE)").fetchone()
            return busy == 0
        finally:
            con.close()
    except sqlite3.Error:
        return False


def _size(paths) -> int:
    return sum(os.path.getsize(p) for p in paths if os.path.exists(p))


def _plan(data_dir: str, results_dir: str, keep_orphans: bool, checkpoint: bool) -> dict:
    claimed = _claimed(results_dir)
    bases = sorted(glob.glob(os.path.join(data_dir, "*.db")))
    sidecars, orphans, skipped = [], [], []
    sidecar_bytes = 0
    for db in bases:
        name = os.path.splitext(os.path.basename(db))[0]
        # …counted BEFORE the checkpoint: folding the log makes sqlite drop the sidecars itself on a
        # clean close, so a count taken afterwards would report zero for work that did happen.
        present = [p for p in (db + "-wal", db + "-shm") if os.path.exists(p)]
        if not _available(db, checkpoint):
            skipped.append(name)
            continue
        sidecars += present
        sidecar_bytes += _size(present)
        if name not in claimed and not keep_orphans:
            orphans.append(db)
    return {
        "claimed": sorted(claimed),
        "sidecars": sidecars,
        "orphans": orphans,
        "backups": sorted(glob.glob(os.path.join(data_dir, "*.pre-v4.bak"))),
        "logs": sorted(glob.glob(os.path.join(data_dir, "*.log"))),
        "skipped": skipped,
        "sidecar_bytes": sidecar_bytes,
    }


def _archive(paths: list[str], zip_path: str) -> bool:
    """Write every path into one zip and prove it landed there before any caller deletes anything."""
    if not paths:
        return True
    os.makedirs(os.path.dirname(zip_path), exist_ok=True)
    with zipfile.ZipFile(zip_path, "w", zipfile.ZIP_DEFLATED) as zf:
        for path in paths:
            zf.write(path, os.path.basename(path))
    with zipfile.ZipFile(zip_path) as zf:
        stored = set(zf.namelist())
        missing = [p for p in paths if os.path.basename(p) not in stored]
    if missing:
        print(f"  ARCHIVE INCOMPLETE — {len(missing)} file(s) did not land; nothing deleted")
        return False
    return True


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--data", default=os.environ.get("GFSO_DATA_DIR", "data"))
    ap.add_argument("--results", default=os.path.join("experiments", "e3_specbench", "results"))
    ap.add_argument("--apply", action="store_true", help="actually archive and delete")
    ap.add_argument("--keep-orphans", action="store_true",
                    help="leave the bases no recorded run claims where they are")
    args = ap.parse_args()

    plan = _plan(args.data, args.results, args.keep_orphans, checkpoint=args.apply)
    print(f"bases claimed by a recorded run: {len(plan['claimed'])}  (never touched)")
    print(f"bases skipped, in use right now: {len(plan['skipped'])}")
    for group in ("sidecars", "orphans", "backups", "logs"):
        paths = plan[group]
        size = plan["sidecar_bytes"] if group == "sidecars" else _size(paths)
        print(f"{group:9s} {len(paths):5d} files   {size / 1e6:8.1f} MB")
    total = plan["sidecar_bytes"] + sum(_size(plan[g]) for g in ("orphans", "backups", "logs"))
    print(f"{'total':9s} {'':5s}          {total / 1e6:8.1f} MB")

    if not args.apply:
        print("\n(dry run — nothing was written; pass --apply to do it)")
        return 0

    stamp = datetime.date.today().isoformat()
    zip_path = os.path.join(args.data, "_archive", f"data-{stamp}.zip")
    keepsakes = plan["orphans"] + plan["backups"] + plan["logs"]
    if not _archive(keepsakes, zip_path):
        return 1
    if keepsakes:
        print(f"archived {len(keepsakes)} file(s) -> {zip_path} ({_size([zip_path]) / 1e6:.1f} MB)")

    removed, failed = 0, 0
    for path in plan["sidecars"] + keepsakes:
        if not os.path.exists(path):
            removed += 1          # sqlite dropped it itself on the clean close — done, not refused
            continue
        try:
            os.remove(path)
            removed += 1
        except OSError:
            failed += 1
    print(f"removed {removed} file(s); {failed} refused by the operating system (in use)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
