"""Audit trail — signal log for Th.11 (structural transparency)."""
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
    # SignalData payload — who decided and why (Th.11, §11 structural transparency)
    source: Optional[AgentId] = None
    reason: Optional[str] = None
    justification: Optional[str] = None
    result: Optional[str] = None
    failed_criteria: tuple[str, ...] = ()
    action: Optional[str] = None


class AuditLog:
    def __init__(self):
        self._entries: list[AuditEntry] = []

    def record(self, entry: AuditEntry) -> None:
        self._entries.append(entry)

    def get_entries(self, task_id: TaskId | None = None) -> list[AuditEntry]:
        if task_id is None:
            return list(self._entries)
        return [e for e in self._entries if e.task_id == task_id]

    def __len__(self) -> int:
        return len(self._entries)
