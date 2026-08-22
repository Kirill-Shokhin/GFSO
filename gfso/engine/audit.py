"""Audit trail — signal log for Thm 11 (structural transparency)."""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Optional

from gfso.core.types import State, Signal, TaskId, AgentId


@dataclass(frozen=True)
class AuditEntry:
    timestamp: datetime
    task_id: TaskId
    signal: Signal
    old_state: Optional[State]
    new_state: Optional[State]
    effects: tuple[str, ...]  # effect type names
    rejected: bool = False
    error: Optional[str] = None
    # SignalData payload — who decided and why (Thm 11, §22 structural transparency)
    source: Optional[AgentId] = None
    reason: Optional[str] = None
    justification: Optional[str] = None
    result: Optional[str] = None
    failed_criteria: tuple[str, ...] = ()
    action: Optional[str] = None
    in_flight: Optional[str] = None  # CONFIRM_CANCEL: executor's in-flight state at cancellation (Thm 11, §14.3)
    # THE CONTRACT THIS SIGNAL SET (ASSIGN only) — Inv-1/Inv-7: "every re-ASSIGN appends a VERSION
    # to the append-only log … past versions live in the log". They did not: the row carried the
    # revision EVENT and no spec, and `tasks.revisions` is a counter, so a contract overwritten by a
    # revision was gone. Measured 2026-08-20: one session's `create_task` replaced another's live
    # root, and nothing anywhere could say what the original had been.
    spec: Optional[str] = None       # JSON of the spec this ASSIGN installed


class AuditLog:
    """The append-only signal log (Thm 11/Inv-7). With a storage that implements the audit methods
    (SqliteStorage), every entry is PERSISTED on record and the log HYDRATES on construction —
    the trail survives a restart (state = fold(log) needs the log to outlive the process; it was
    in-memory only, and a restarted server had no history at all). A storage without the methods
    (MemoryStorage) keeps the old in-memory behavior — consistent with its own ephemerality."""

    def __init__(self, storage=None):
        self._entries: list[AuditEntry] = []
        self._storage = storage if (storage is not None and hasattr(storage, "append_audit")) else None
        if self._storage is not None:
            self._entries = [self._from_row(r) for r in self._storage.load_audit()]

    def record(self, entry: AuditEntry) -> None:
        self._entries.append(entry)
        if self._storage is not None:
            self._storage.append_audit(self._to_row(entry))

    def get_entries(self, task_id: TaskId | None = None) -> list[AuditEntry]:
        if task_id is None:
            return list(self._entries)
        return [e for e in self._entries if e.task_id == task_id]

    def __len__(self) -> int:
        return len(self._entries)

    @staticmethod
    def _to_row(e: AuditEntry) -> dict:
        return {
            "ts": e.timestamp.isoformat(), "task_id": str(e.task_id), "signal": e.signal.name,
            "old_state": e.old_state.name if e.old_state else None,
            "new_state": e.new_state.name if e.new_state else None,
            "effects": list(e.effects), "rejected": e.rejected, "error": e.error,
            "source": str(e.source) if e.source else None, "reason": e.reason,
            "justification": e.justification, "result": e.result,
            "failed_criteria": list(e.failed_criteria), "action": e.action,
            "in_flight": e.in_flight, "spec": e.spec,
        }

    @staticmethod
    def _from_row(r: dict) -> AuditEntry:
        return AuditEntry(
            timestamp=datetime.fromisoformat(r["ts"]), task_id=TaskId(r["task_id"]),
            signal=Signal[r["signal"]],
            old_state=State[r["old_state"]] if r.get("old_state") else None,
            new_state=State[r["new_state"]] if r.get("new_state") else None,
            effects=tuple(r.get("effects") or ()), rejected=bool(r.get("rejected")),
            error=r.get("error"),
            source=AgentId(r["source"]) if r.get("source") else None,
            reason=r.get("reason"), justification=r.get("justification"), result=r.get("result"),
            failed_criteria=tuple(r.get("failed_criteria") or ()), action=r.get("action"),
            in_flight=r.get("in_flight"), spec=r.get("spec"),
        )
