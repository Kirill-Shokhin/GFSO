"""A reference embedding host — the suite's default subject, so the embeddability claim is CHECKED
on every run instead of skipped.

What this is, and what it is not: it is a CLIENT of the public port surface, not a mirror of
anything. A mirror is a copy of content and rots silently; a client breaks LOUDLY, and exactly when
the embedding contract breaks — which is the one moment we want to hear about it. Nothing here
duplicates engine logic: the protocol step is `gfso.engine.loop.process_signal`, called from this
host's own pump.

Deliberately mismatching every stdlib default, per docs/embeddability_acceptance.md:
  * storage  — a JSON-lines file store (not sqlite, not the in-memory adapter), including the
               MANDATORY append-only signal log and the exec-verdict extension the seam gate needs;
  * clock    — virtual time under the test's control;
  * runtime  — no Engine, no engine threads: a plain list used as the follow-up sink, drained here.

The generic dataclass codec below is deliberate: the acceptance doc's own instruction is to POINT AT
the schema rather than transcribe it, and a hand-copied field list is the mirror we are avoiding.
"""
from __future__ import annotations

import dataclasses
import gfso.core.types.primitives as P
import json
import time
import typing
from datetime import datetime
from enum import Enum
from pathlib import Path
from typing import Any, Optional

from gfso.core.graph import Graph
from gfso.core.types.ports import AgentPort, ClockPort, StoragePort
from gfso.core.types.primitives import (
    AgentId, CheckResult, DepEdge, DispatchPayload, Recommendation, SignalData, Task, TaskId,
)
from gfso.engine.audit import AuditLog
from gfso.engine.events import EventBus
from gfso.engine.loop import process_signal
from gfso.core.types.enums import TERMINAL_STATES
from gfso.core.types.primitives import Signal


# ----------------------------------------------------------------- generic dataclass codec

def _encode(o: Any) -> Any:
    if dataclasses.is_dataclass(o) and not isinstance(o, type):
        return {f.name: _encode(getattr(o, f.name)) for f in dataclasses.fields(o)}
    if isinstance(o, Enum):
        return {"__enum__": type(o).__name__, "name": o.name}
    if isinstance(o, datetime):
        return {"__dt__": o.isoformat()}
    if isinstance(o, tuple):
        return {"__tuple__": [_encode(x) for x in o]}
    if isinstance(o, list):
        return [_encode(x) for x in o]
    if isinstance(o, dict):
        return {k: _encode(v) for k, v in o.items()}
    return o


def _strip_optional(tp: Any) -> Any:
    if typing.get_origin(tp) is typing.Union:
        args = [a for a in typing.get_args(tp) if a is not type(None)]
        return args[0] if len(args) == 1 else tp
    return tp


def _decode(raw: Any, tp: Any = None) -> Any:
    if isinstance(raw, dict) and "__enum__" in raw:
        return getattr(P, raw["__enum__"])[raw["name"]]
    if isinstance(raw, dict) and "__dt__" in raw:
        return datetime.fromisoformat(raw["__dt__"])
    tp = _strip_optional(tp) if tp is not None else None
    if isinstance(raw, dict) and "__tuple__" in raw:
        inner = typing.get_args(tp)[0] if tp is not None and typing.get_args(tp) else None
        return tuple(_decode(x, inner) for x in raw["__tuple__"])
    if isinstance(raw, list):
        inner = typing.get_args(tp)[0] if tp is not None and typing.get_args(tp) else None
        return [_decode(x, inner) for x in raw]
    if isinstance(raw, dict) and tp is not None and dataclasses.is_dataclass(tp):
        hints = typing.get_type_hints(tp)
        init = {f.name: _decode(raw.get(f.name), hints.get(f.name))
                for f in dataclasses.fields(tp) if f.init}
        obj = tp(**init)
        for f in dataclasses.fields(tp):          # non-init attributes carry protocol state
            if not f.init and f.name in raw:
                setattr(obj, f.name, _decode(raw[f.name], hints.get(f.name)))
        return obj
    return raw


# ----------------------------------------------------------------- the ports

class JsonlStorage(StoragePort):
    """One directory, one file per record kind, JSON lines. Append-only where the contract demands
    it (the audit log), last-wins on load elsewhere."""

    def __init__(self, workdir: str | Path):
        self.dir = Path(workdir)
        self.dir.mkdir(parents=True, exist_ok=True)
        self._tasks: dict[str, Task] = {}
        self._deps: list[DepEdge] = []
        self._checks: dict[str, list[CheckResult]] = {}
        self._recs: dict[str, Recommendation] = {}
        self._blobs: dict[str, dict[str, str]] = {"critique": {}, "deliver": {}, "verdict": {}}
        self._load()

    # --- files
    def _f(self, name: str) -> Path:
        return self.dir / f"{name}.jsonl"

    def _append(self, name: str, row: dict) -> None:
        with self._f(name).open("a", encoding="utf-8") as fh:
            fh.write(json.dumps(row, ensure_ascii=False) + "\n")

    def _rows(self, name: str) -> list[dict]:
        p = self._f(name)
        if not p.exists():
            return []
        return [json.loads(l) for l in p.read_text(encoding="utf-8").splitlines() if l.strip()]

    def _load(self) -> None:
        for row in self._rows("tasks"):                       # last write wins
            self._tasks[row["id"]] = _decode(row["task"], Task)
        self._deps = [_decode(r, DepEdge) for r in self._rows("deps")]
        for r in self._rows("checks"):
            self._checks[r["task_id"]] = [_decode(c, CheckResult) for c in r["results"]]
        for r in self._rows("recs"):
            self._recs[r["task_id"]] = _decode(r["rec"], Recommendation)
        for r in self._rows("blobs"):
            self._blobs[r["kind"]][r["task_id"]] = r["value"]

    # --- MANDATORY core
    def get_task(self, task_id: TaskId) -> Optional[Task]:
        return self._tasks.get(str(task_id))

    def save_task(self, task: Task) -> None:
        self._tasks[str(task.id)] = task
        self._append("tasks", {"id": str(task.id), "task": _encode(task)})

    def get_all_tasks(self) -> list[Task]:
        return list(self._tasks.values())

    def get_children(self, task_id: TaskId) -> list[Task]:
        return [t for t in self._tasks.values() if t.parent_id and str(t.parent_id) == str(task_id)]

    def get_parent(self, task_id: TaskId) -> Optional[Task]:
        t = self.get_task(task_id)
        return self.get_task(t.parent_id) if t and t.parent_id else None

    def get_active_tasks(self) -> list[Task]:
        return [t for t in self._tasks.values() if t.state not in TERMINAL_STATES]

    def get_check_results(self, task_id: TaskId) -> list[CheckResult]:
        return list(self._checks.get(str(task_id), []))

    def store_check_results(self, task_id: TaskId, results: list[CheckResult]) -> None:
        self._checks[str(task_id)] = list(results)
        self._append("checks", {"task_id": str(task_id), "results": [_encode(r) for r in results]})

    def get_recommendation(self, task_id: TaskId) -> Optional[Recommendation]:
        return self._recs.get(str(task_id))

    def store_recommendation(self, task_id: TaskId, rec: Recommendation) -> None:
        self._recs[str(task_id)] = rec
        self._append("recs", {"task_id": str(task_id), "rec": _encode(rec)})

    def add_dep_edge(self, edge: DepEdge) -> None:
        self._deps.append(edge)
        self._append("deps", _encode(edge))

    def remove_dep_edge(self, from_id: TaskId, to_id: TaskId) -> None:
        self._deps = [e for e in self._deps
                      if not (str(e.from_id) == str(from_id) and str(e.to_id) == str(to_id))]
        self._f("deps").write_text(
            "".join(json.dumps(_encode(e), ensure_ascii=False) + "\n" for e in self._deps),
            encoding="utf-8")

    def get_dep_edges(self) -> list[DepEdge]:
        return list(self._deps)

    def append_audit(self, row: dict) -> None:
        self._append("audit", _encode(row))

    def load_audit(self) -> list[dict]:
        return self._rows("audit")

    # --- extensions the seam gate and the validator need
    def _blob(self, kind: str, task_id: TaskId, value: str) -> None:
        self._blobs[kind][str(task_id)] = value
        self._append("blobs", {"kind": kind, "task_id": str(task_id), "value": value})

    def store_critique(self, task_id: TaskId, critique_json: str) -> None:
        self._blob("critique", task_id, critique_json)

    def get_critique(self, task_id: TaskId) -> Optional[str]:
        return self._blobs["critique"].get(str(task_id))

    def store_deliver_result(self, task_id: TaskId, result: str) -> None:
        self._blob("deliver", task_id, result)

    def get_deliver_result(self, task_id: TaskId) -> Optional[str]:
        return self._blobs["deliver"].get(str(task_id))

    def store_exec_verdict(self, task_id: TaskId, verdict_json: str) -> None:
        self._blob("verdict", task_id, verdict_json)

    def get_exec_verdict(self, task_id: TaskId) -> Optional[str]:
        return self._blobs["verdict"].get(str(task_id))


class VirtualClock(ClockPort):
    """Time the test moves by hand — Inv-5 must be checkable without waiting for it."""

    def __init__(self, start: float | None = None):
        # Anchored on the wall clock at construction: the engine stamps created_at /
        # state_entered_at with real datetimes, so virtual time must start beside them or every
        # age comparison is off by years.
        self._t = time.time() if start is None else start

    def now(self) -> float:
        return self._t

    def wait(self, seconds: float) -> None:
        return None                      # virtual time never blocks; the host advances it

    def advance(self, seconds: float) -> None:
        self._t += seconds


class NoAgents(AgentPort):
    """This host delegates to nobody: every participant is external and sends its own signals."""

    def dispatch(self, agent_id: AgentId, payload: DispatchPayload) -> Optional[SignalData]:
        return None


# ----------------------------------------------------------------- the host

class Host:
    def __init__(self, workdir: str | Path):
        self.workdir = Path(workdir)
        self.storage = JsonlStorage(self.workdir)
        self.clock = VirtualClock()
        self.graph = Graph(self.storage)
        self.audit = AuditLog(self.storage)
        self.events = EventBus()
        self.agents = NoAgents()

    # --- the pump: one queue, drained to quiescence, no threads
    def send(self, signal_data: SignalData) -> None:
        pending: list[SignalData] = [signal_data]
        seen = 0
        while pending:
            sd = pending.pop(0)
            sink = _ListSink(pending)
            process_signal(sd, self.graph, self.agents, None, sink, self.audit, self.events,
                           validate=True)
            seen += 1
            if seen > 500:                       # a host must not spin forever on follow-ups
                raise RuntimeError("signal pump did not reach quiescence")

    # --- observations the suite asks for
    def state(self, task_id: str) -> Optional[str]:
        st = self.graph.get_state(TaskId(task_id))
        return st.name if st is not None else None

    def graph_holes(self) -> list[dict]:
        out = []
        for t in self.storage.get_all_tasks():
            for c in self.storage.get_check_results(t.id):
                if not c.passed and not getattr(c, "skipped", False):
                    out.append({"task_id": str(t.id), "name": t.spec.name or str(t.id),
                                "check": c.check_name, "details": c.details})
        return out

    def record_verdict(self, task_id: str, verdict: str, failed: list, reviewer: str) -> None:
        """An independent reviewer's verdict on the current delivery — what the self-PASS gate reads.
        The independence rule is the engine's (§14.5); a host records, it does not adjudicate."""
        task = self.storage.get_task(TaskId(task_id))
        if task is not None and task.assignee and str(reviewer) == str(task.assignee):
            raise ValueError(f"reviewer {reviewer!r} is the node's executor (verifier ≠ executor)")
        self.storage.store_exec_verdict(TaskId(task_id), json.dumps({
            "verdict": verdict, "failed_criteria": list(failed or ()), "validator": str(reviewer),
            "iteration": getattr(task, "iteration", 0), "reopens": getattr(task, "reopens", 0),
            "per_criterion": [], "ts": datetime.now().isoformat(sep=" ", timespec="seconds")}))

    def advance_clock(self, seconds: float) -> None:
        """Move virtual time and let the timeout machinery run exactly one pass."""
        self.clock.advance(seconds)
        now = self.clock.now()
        for task in list(self.storage.get_active_tasks()):
            if task.state in TERMINAL_STATES:
                continue
            entered = getattr(task, "state_entered_at", task.created_at)
            overdue = task.deadline is not None and now > task.deadline.timestamp()
            stale = (now - entered.timestamp()) > self._state_timeout
            if overdue or stale:
                self.send(SignalData(signal=Signal.TIMEOUT, task_id=task.id))

    _state_timeout = 3600.0

    def audit_rows(self) -> list[dict]:
        return self.storage.load_audit()

    def restart(self) -> "Host":
        """A NEW process over the SAME store: nothing in memory survives, the log hydrates."""
        return Host(self.workdir)


class _ListSink:
    """`.put(SignalData)` over a plain list — the whole runtime this host needs."""

    def __init__(self, backing: list):
        self._backing = backing

    def put(self, item) -> None:
        self._backing.append(item)


def make_host(workdir: str) -> Host:
    return Host(workdir)
