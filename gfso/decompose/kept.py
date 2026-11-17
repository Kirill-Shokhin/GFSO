"""The plans asked for: the one each project waits on, and every written answer by its handle.

A plan is written for minutes and its asker may come back hours later or after a restart (a chat hands the turn back),
so both live on disk: `projects/<name>.json` — the project's latest plan, {handle, state, told, read, error} —
`answers/<handle>.json` — a written answer, readable by its handle until KEPT_S after it is read or superseded — and
`written/<name>.json` — the file last written for the project, {path, at}, what its page shows before the go."""
from __future__ import annotations

import contextlib
import hashlib
import json
import time
from pathlib import Path

from gfso.config import DEFAULT_PROJECT, data_dir, write_atomic

#: how long an answer is kept once read or superseded
KEPT_S = 3600


def _dir(kind: str) -> Path:
    return data_dir() / "plans" / "kept" / kind


def _read(p: Path) -> dict | None:
    with contextlib.suppress(OSError, ValueError):
        return json.loads(p.read_text(encoding="utf-8"))
    return None


def _write(p: Path, rec: dict) -> None:
    write_atomic(p, json.dumps(rec, ensure_ascii=False))


def answer(handle: str) -> dict | None:
    """The written answer kept under `handle`, or None."""
    rec = _read(_dir("answers") / f"{handle}.json")
    return rec["answer"] if rec else None


def keep_answer(project: str, handle: str, out: dict) -> None:
    """Keep the written answer `out` under `handle`, let go at once if `project` waits on another plan now: written
    first and let go after, a sweep between the two kept a superseded answer for good."""
    rec = record(project)
    _write(_dir("answers") / f"{handle}.json",
           {"answer": out, "at": time.time(), **({"let_go": True} if not rec or rec.get("handle") != handle else {})})


def record(project: str) -> dict | None:
    """The plan `project` waits on — its latest asked — or None."""
    return _read(_dir("projects") / f"{project or DEFAULT_PROJECT}.json")


def set_record(project: str, rec: dict) -> None:
    """Make `rec` the plan `project` waits on; the one it replaces stays readable by its handle until swept."""
    if (was := record(project)) and was.get("handle") != rec.get("handle"):
        let_go(was["handle"])
    _write(_dir("projects") / f"{project or DEFAULT_PROJECT}.json", {**rec, "at": time.time()})


def mark(project: str, handle: str, **flags) -> None:
    """Set `flags` on the project's record, if it is still about `handle`; a read answer starts its KEPT_S."""
    if (rec := record(project)) and rec.get("handle") == handle:
        _write(_dir("projects") / f"{project or DEFAULT_PROJECT}.json", {**rec, **flags})
    if flags.get("read") or not rec or rec.get("handle") != handle:
        let_go(handle)          # …read, or no longer the one its project waits on


def let_go(handle: str) -> None:
    """Start the KEPT_S of the answer under `handle`: read, superseded, or its project gone."""
    p = _dir("answers") / f"{handle}.json"
    if (rec := _read(p)) is not None:
        _write(p, {**rec, "at": time.time(), "let_go": True})


def wrote(project: str, path: str) -> None:
    """`path` is the plan file last written for `project`."""
    _write(_dir("written") / f"{project or DEFAULT_PROJECT}.json", {"path": str(path), "at": time.time()})


def written(project: str) -> dict | None:
    """{path, at, text} of the plan file last written for `project`, or None: none written, or its file gone."""
    rec = _read(_dir("written") / f"{project or DEFAULT_PROJECT}.json")
    with contextlib.suppress(OSError):
        return rec and {**rec, "text": Path(rec["path"]).read_text(encoding="utf-8")}
    return None


def _goal_key(goal: str) -> str:
    return hashlib.sha256(goal.encode()).hexdigest()[:16]


def keep_documents(goal: str, docs: list) -> None:
    """The documents ({path, text}) written under `goal` — every plan of that goal, refined or not, carries them."""
    if docs:
        _write(_dir("documents") / f"{_goal_key(goal)}.json", {"documents": docs})


def documents(goal: str) -> list:
    """The documents written under `goal`, as they were composed into it; [] for none."""
    return (_read(_dir("documents") / f"{_goal_key(goal)}.json") or {}).get("documents") or []


def forget_project(project: str) -> None:
    """A deleted project waits on no plan, and shows none: a new one of its name inherits neither."""
    if rec := record(project):
        let_go(rec["handle"])
    for kind in ("projects", "written"):
        (_dir(kind) / f"{project or DEFAULT_PROJECT}.json").unlink(missing_ok=True)


def sweep() -> None:
    """Let go of answers read or superseded more than KEPT_S ago; one a project still waits on unread stays."""
    d = _dir("answers")
    for p in (d.glob("*.json") if d.is_dir() else ()):
        if (rec := _read(p)) and rec.get("let_go") and time.time() - float(rec.get("at") or 0) >= KEPT_S:
            p.unlink(missing_ok=True)
