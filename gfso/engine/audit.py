"""Audit trail — signal log for Thm 11 (structural transparency)."""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Optional

from gfso.core.types import State, Signal, TaskId, AgentId, state_named


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
    # SignalData payload — who decided and why (Thm 11, §11.6 structural transparency)
    source: Optional[AgentId] = None
    reason: Optional[str] = None
    justification: Optional[str] = None
    result: Optional[str] = None
    failed_criteria: tuple[str, ...] = ()
    action: Optional[str] = None
    in_flight: Optional[str] = None  # CONFIRM_CANCEL: executor's in-flight state at cancellation (Thm 11, §11.6)
    # THE CONTRACT THIS SIGNAL SET (ASSIGN only) — Inv-1/Inv-7: "every re-ASSIGN appends a VERSION
    # to the append-only log … past versions live in the log". They did not: the row carried the
    # revision EVENT and no spec, and `tasks.revisions` is a counter, so a contract overwritten by a
    # revision was gone. Measured 2026-08-20: one session's `create_task` replaced another's live
    # root, and nothing anywhere could say what the original had been.
    spec: Optional[str] = None       # JSON of the spec this ASSIGN installed
    # …AND WHY IT WAS REVISED. A re-ASSIGN's reason is signal data logged with it, not a packet field (§11.3); its
    # typed cause (§15.4) landed only on the node's metric flags, so the log — Thm 11's record — never said it.
    revision_reason: Optional[str] = None
    # …AND THE RULING AN ACCEPT_CHALLENGE MAKES: the findings it retires, on the row of the act that retires them
    retire_findings: tuple[str, ...] = ()


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
        """Append one entry — the only way this log grows. History is never rewritten (Inv-7); a
        correction is a new entry, which is what makes `state = fold(log)` checkable."""
        self._entries.append(entry)
        if self._storage is not None:
            self._storage.append_audit(self._to_row(entry))

    def get_entries(self, task_id: TaskId | None = None) -> list[AuditEntry]:
        """The log, whole or for one node, oldest first."""
        if task_id is None:
            return list(self._entries)
        return [e for e in self._entries if e.task_id == task_id]

    def last_at(self, task_id: TaskId, *, signal: Signal | None = None,
                new_state: State | None = None) -> int:
        """Where in the log the last accepted entry on `task_id` matching stands, or -1.

        "Did this happen after that" is a question about the LOG's order, which is the protocol's
        (Inv-7) — never about the clock: two stamps inside one coarse Windows tick tie, and the rework
        gate called a child that PASSED after its parent's FAIL "untouched since the FAIL"."""
        for i in range(len(self._entries) - 1, -1, -1):
            e = self._entries[i]
            if (e.task_id == task_id and not e.rejected and (signal is None or e.signal == signal)
                    and (new_state is None or e.new_state == new_state)):
                return i
        return -1

    def occupied_since(self, task_id: TaskId, at: int) -> set:
        """The states `task_id` stood in from log position `at` on: the one it was in at `at`, and every one it entered
        after — "a consumer in work after the result's PASS" (§12.14) asked of the log, not of the standing state."""
        out, before = set(), None
        for i, e in enumerate(self._entries):
            if e.task_id != task_id or e.rejected or e.new_state is None:
                continue
            if i <= at:
                before = e.new_state
            else:
                out.add(e.new_state)
        return out | ({before} if before is not None else set())

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
            "in_flight": e.in_flight, "spec": e.spec, "revision_reason": e.revision_reason,
            "retire_findings": list(e.retire_findings),
        }

    @staticmethod
    def _from_row(r: dict) -> AuditEntry:
        return AuditEntry(
            timestamp=datetime.fromisoformat(r["ts"]), task_id=TaskId(r["task_id"]),
            signal=Signal[r["signal"]],
            old_state=state_named(r["old_state"]) if r.get("old_state") else None,
            new_state=state_named(r["new_state"]) if r.get("new_state") else None,
            effects=tuple(r.get("effects") or ()), rejected=bool(r.get("rejected")),
            error=r.get("error"),
            source=AgentId(r["source"]) if r.get("source") else None,
            reason=r.get("reason"), justification=r.get("justification"), result=r.get("result"),
            failed_criteria=tuple(r.get("failed_criteria") or ()), action=r.get("action"),
            in_flight=r.get("in_flight"), spec=r.get("spec"), revision_reason=r.get("revision_reason"),
            retire_findings=tuple(r.get("retire_findings") or ()),
        )


#: The accepted signals that install a packet version: the first ASSIGN, a re-ASSIGN (a revision),
#: a REOPEN (a re-ASSIGN out of a terminal), and ACCEPT_CHALLENGE. Entering OFFERED is NOT the
#: mark: a pre-consent REJECT_CHALLENGE returns the node there and installs nothing.
VERSION_INSTALLING = frozenset({Signal.ASSIGN, Signal.ACCEPT_CHALLENGE})


def _on_current_version(entries: list[AuditEntry], signal: Signal) -> bool:
    """Is `signal` logged (accepted) after the latest version-installing event? Oldest first."""
    for e in reversed(entries):
        if e.rejected:
            continue
        if e.signal == signal:
            return True
        if e.signal in VERSION_INSTALLING:
            return False
    return False


def consented_on_current_version(entries: list[AuditEntry]) -> bool:
    """Has the executor ACCEPTed the packet version that stands? Read from the log, where consent
    is recorded (Inv-7); the node carries no attribute for it that could drift from the record."""
    return _on_current_version(entries, Signal.ACCEPT)


def failed_on_current_version(entries: list[AuditEntry]) -> bool:
    """Has a FAIL been handed down on the packet version that stands — is its holder reworking,
    whatever the state is called? A rejected challenge or a resolved block returns a reworking node
    to EXECUTING, and the refusal it is working against has not gone anywhere."""
    return _on_current_version(entries, Signal.FAIL)


def resolved_on_current_version(entries: list[AuditEntry]) -> bool:
    """Has a block of this node already been resolved under the packet version that stands?"""
    return _on_current_version(entries, Signal.RESOLVE_BLOCK)
