"""Pydantic request/response models for GFSO API."""
from __future__ import annotations

from typing import Optional

from pydantic import BaseModel

from gfso.engine.audit import AuditEntry


# === Request models ===
# The authoring/mutation surface is the generic `POST /api/run/<tool>` (body = the tool's kwargs) — the same
# `gfso.tools.TOOLS` that MCP + CLI bind — so there are NO per-verb request models here; only reads are typed.

class ProbeIn(BaseModel):
    behaviour: str = ""
    command: str = ""
    expect: str = ""
    # The files the command reads, pinned with it (`{path: content}`). Served because a read that
    # drops them unpins the corpus on the next write-back: the agent door and storage carry the
    # field, and a door that rebuilds a probe field by field is exactly where it goes missing.
    inputs: dict[str, str] = {}


class CriteriaIn(BaseModel):
    name: str
    description: str
    # The pinned decision procedure, served with the criterion. A page that shows a criterion and
    # not what will be run to decide it shows an intention and calls it a contract.
    check: list[ProbeIn] = []
    # …and the composition function CHECK-7 checks the children against (§9.6). Served because the
    # check's own answer now names it: a reader shown "checked under an ASSUMED sum" needs to be able
    # to see, on the criterion, that nothing was declared.
    composition: str = ""


# === Response models ===

class CheckResultOut(BaseModel):
    """One structural check as a reader sees it.

    A SKIPPED CHECK IS NOT A PASSED ONE. `passed` was a bare bool beside `skipped`, so a check the
    battery could not run shipped as `passed=True, skipped=True` — fail-open, and the UI reads
    `passed`. The tool door had already been fixed to send `None` there (`gfso/tools.py`) and this
    door had not, so the same check answered differently depending on which one you came in by.
    `verdict` is the word both doors now say: met · unmet · skipped."""

    check_name: str
    passed: Optional[bool]              # None ⟺ skipped: the check did not run, so it says nothing
    details: str
    skipped: bool
    verdict: str = "met_vacuously"      # met · met_vacuously · unmet · skipped — one word, no bool arithmetic
    #: the check held over an EMPTY subject (no Dep edges, no risk components, no child deadlines):
    #: true, and true of nothing. Carried separately so a surface can say which green is which.
    vacuous: bool = False

    @classmethod
    def of(cls, c) -> "CheckResultOut":
        """From the engine's own `CheckResult` — one place builds this row."""
        _vac = bool(c.vacuous) and not c.skipped and bool(c.passed)
        return cls(check_name=c.check_name, details=c.details, skipped=c.skipped,
                   passed=None if c.skipped else c.passed, vacuous=_vac,
                   verdict=("skipped" if c.skipped else
                            "met_vacuously" if _vac else "met" if c.passed else "unmet"))

class AuditEntryOut(BaseModel):
    timestamp: str
    task_id: str
    signal: str
    old_state: str | None
    new_state: str | None
    effects: list[str]
    rejected: bool
    error: str | None
    source: str | None = None
    reason: str | None = None
    justification: str | None = None
    result: str | None = None
    failed_criteria: list[str] = []
    action: str | None = None
    in_flight: str | None = None  # CONFIRM_CANCEL: executor's in-flight state at cancellation (Thm 11)
    # The contract THIS ASSIGN installed (Inv-1/Inv-7: past versions live in the log). The entry has
    # carried it since a `create_task` replaced another session's live root with nothing able to say
    # what the original had been — but this row did not list it, so the one reader the log exists for
    # could not see the one thing a revision changes.
    spec: str | None = None

class SuggestCriteriaRequest(BaseModel):
    description: str

class SuggestCriteriaResponse(BaseModel):
    criteria: list[CriteriaIn]

class SolverItem(BaseModel):
    kind: str
    check: str | None = None
    text: str
    severity: str

class SolverOut(BaseModel):
    recommendations: list[SolverItem]

class ProjectionOut(BaseModel):
    node_id: str
    projection: str  # readable markdown — the critic's input contract


# === Converters (read-side: domain → typed response) ===

def audit_to_out(e: AuditEntry) -> AuditEntryOut:
    """One log entry as the door serves it, `ts` renamed to `timestamp`: the storage spelling and
    the wire spelling are different vocabularies, and a reader looking for `ts` here found nothing
    and reported the time as missing (HTTP door, 2026-09-02)."""
    return AuditEntryOut(
        timestamp=e.timestamp.isoformat(), task_id=e.task_id,
        signal=e.signal.name,
        old_state=e.old_state.name if e.old_state else None,
        new_state=e.new_state.name if e.new_state else None,
        effects=list(e.effects), rejected=e.rejected, error=e.error,
        source=e.source, reason=e.reason, justification=e.justification,
        result=e.result, failed_criteria=list(e.failed_criteria), action=e.action,
        in_flight=e.in_flight, spec=e.spec,
    )
