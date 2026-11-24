"""The plans asked for: the one each project waits on, and every written answer by its handle.

A plan is written for minutes and its asker may come back hours later or after a restart (a chat hands the turn back),
so both live on disk: `projects/<name>.json` — the writings the project waits on, by handle (`records`) —
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
    write_atomic(p, json.dumps(rec, ensure_ascii=False, default=str))


def answer(handle: str) -> dict | None:
    """The written answer kept under `handle`, or None."""
    rec = _read(_dir("answers") / f"{handle}.json")
    return rec["answer"] if rec else None


def keep_answer(project: str, handle: str, out: dict) -> None:
    """Keep the written answer `out` under `handle`, let go at once if `project` no longer waits on it: written first
    and let go after, a sweep between the two kept a superseded answer for good."""
    _write(_dir("answers") / f"{handle}.json",
           {"answer": out, "at": time.time(), **({} if record(project, handle) else {"let_go": True})})


def _path(project: str) -> Path:
    return _dir("projects") / f"{project or DEFAULT_PROJECT}.json"


def records(project: str) -> dict:
    """{handle: {state, told, read, error, slot}} — every writing `project` waits on, each until read or superseded in
    its slot; one project held two at once (two authorings on sibling nodes, an authoring beside a plan), and one record
    lost the other's end. A record of the one-plan form before is read as its one writing."""
    got = _read(_path(project)) or {}
    return {got["handle"]: got} if "handle" in got else got


def record(project: str, handle: str) -> dict | None:
    """The writing `handle` names among those `project` waits on, or None."""
    return records(project).get(handle)


def open_writing(project: str, handle: str, slot: str) -> None:
    """`project` waits on the writing `handle` anew; it supersedes the one of its `slot` before (a plan asked anew), and
    those read are let go."""
    recs = records(project)
    for h in [h for h, r in recs.items() if h != handle and (r.get("slot") == slot or r.get("read"))]:
        let_go(h)
        del recs[h]
    _write(_path(project), {**recs, handle: {"state": "writing", "told": False, "read": False, "slot": slot,
                                             "at": time.time()}})


def mark(project: str, handle: str, **flags) -> None:
    """Set `flags` on the writing `handle`, if `project` still waits on it; a read answer starts its KEPT_S."""
    recs = records(project)
    if handle in recs:
        _write(_path(project), {**recs, handle: {**recs[handle], **flags}})
    if flags.get("read") or handle not in recs:
        let_go(handle)          # …read, or no longer one its project waits on


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
    for h in records(project):
        let_go(h)
    for kind in ("projects", "written"):
        (_dir(kind) / f"{project or DEFAULT_PROJECT}.json").unlink(missing_ok=True)


def sweep() -> None:
    """Let go of answers read or superseded more than KEPT_S ago; one a project still waits on unread stays."""
    d = _dir("answers")
    for p in (d.glob("*.json") if d.is_dir() else ()):
        if (rec := _read(p)) and rec.get("let_go") and time.time() - float(rec.get("at") or 0) >= KEPT_S:
            p.unlink(missing_ok=True)
