"""Pydantic request/response models for GFSO API."""
from __future__ import annotations

from typing import Optional

from pydantic import BaseModel

from gfso.core.types import Task
from gfso.engine.audit import AuditEntry


# === Request models ===
# The authoring/mutation surface is the generic `POST /api/run/<tool>` (body = the tool's kwargs) — the same
# `gfso.tools.TOOLS` that MCP + CLI bind — so there are NO per-verb request models here; only reads are typed.

class CriteriaIn(BaseModel):
    name: str
    description: str


# === Response models ===

class TaskOut(BaseModel):
    id: str
    name: str = ""
    description: str
    state: str
    parent_id: str | None
    assignee: str | None
    iteration: int
    max_iterations: int
    done_reason: str | None
    criteria: list[CriteriaIn]
    accepted_risks: list[str]  # item texts (back-compat)
    # ONE NAME FOR ONE FACT, and the whole record under it. This door called it
    # `accepted_risks_detail` and dropped `invalidation_condition`, while the tool surface answers
    # `accepted_risks_recorded` and carries all four fields — two spellings of one thing, and the
    # HTTP one missing the field §13.1 makes the point of the register (what would revoke the
    # acceptance). Three doors reported "I cannot tell whether the rest of it was stored" in three
    # waves (2026-09-03/04). `accepted_risks_detail` stays as an alias for one release so an
    # integrator reading it does not lose it overnight.
    accepted_risks_recorded: list[dict] = []
    accepted_risks_detail: list[dict] = []   # DEPRECATED alias of the above
    risk_components: list[str]
    scope: list[str] = []  # §13.1 declared scope-boundary exclusions (objectified on the goal)
    created_at: str
    deadline: str | None
    was_challenged: bool
    criterion_mappings: list[dict] = []  # [{criterion_name, child_id}]
    reopens: int = 0
    # When the CURRENT state was entered. Two engine decisions key on it — the Inv-5 per-state clock
    # and the contact-refuted-coverage gate ("was a covering child touched since that FAIL?") — and
    # neither was observable from outside: a live run where the gate did not refuse could not be
    # diagnosed, because the field is in memory only and a restart re-arms it to load time.
    state_entered_at: str | None = None

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

class RecommendationOut(BaseModel):
    suggestions: list[str]

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

class TaskDetailOut(TaskOut):
    # HOW THIS NODE CLOSED, beside the node itself. `null` while it has not settled positive —
    # there is nothing to weigh yet, and an empty object would read as "closed, nothing to weigh".
    # Absent entirely until 2026-09-06: the page fetched a second endpoint for `by_hand` and had no
    # way at all to learn that a hand verdict had DISPLACED an instrument's opposite one, so every
    # DONE node was drawn identically — the earned one and the asserted one (wave 26).
    closure: dict | None = None
    checks: list[CheckResultOut]
    recommendation: RecommendationOut | None
    audit: list[AuditEntryOut]
    children: list[TaskOut]

class GraphNode(BaseModel):
    id: str
    label: str
    state: str
    assignee: str | None
    parent_id: str | None
    has_children: bool
    done_reason: str | None = None   # ABANDONED = a tombstone (UI greys it, not an active node)
    # The same closure facts, on the object the PICTURE is built from: a drawing that cannot tell an
    # instrument's PASS from a self-named party's is a drawing of the one thing this product refuses.
    closure: dict | None = None

class GraphEdge(BaseModel):
    source: str
    target: str
    type: str
    discovered: bool = False

class GraphOut(BaseModel):
    nodes: list[GraphNode]
    edges: list[GraphEdge]

class MetricsOut(BaseModel):
    # None = ⊥: empty population (canon §21) — no observations is not "100%"; the UI renders a dash
    q_T: float | None = None
    q_D: float | None = None
    q_V: float | None = None
    q_Dep: float | None = None
    q_Del: float | None = None
    # NOT part of Q (§24.5) and served anyway: the canon says to read a low q_D TOGETHER with this
    # share, because an over-strict validator's false FAILs inflate q_D's numerator. The endpoint's
    # own docstring promised it while this model silently dropped it — pydantic ignores what it does
    # not declare, so the door documented a field it did not serve (measured 2026-09-02, looking at
    # a page that showed q_D at 0% in red with no way to ask whether the validator was the cause).
    false_fail_share: float | None = None
    # What each number is ABOUT, from the module that computes it. Served because a true number read
    # as a defect is a defect OF THE SURFACE, and the page cannot be trusted to keep its own copy true.
    means: dict[str, str] = {}

class SuggestCriteriaRequest(BaseModel):
    description: str

class SuggestCriteriaResponse(BaseModel):
    criteria: list[CriteriaIn]

class ActionOut(BaseModel):
    signal: str
    role: str

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

def task_to_out(t: Task) -> TaskOut:
    """A node as the door serves it — the wire shape, kept apart from the graph's own so a
    rename on one side cannot silently reshape the other."""
    return TaskOut(
        id=t.id, name=t.spec.name, description=t.spec.description, state=t.state.name,
        parent_id=t.parent_id, assignee=t.assignee,
        iteration=t.iteration, max_iterations=t.max_iterations,
        done_reason=t.done_reason.name if t.done_reason else None,
        criteria=[CriteriaIn(name=c.name, description=c.description) for c in t.spec.criteria],
        accepted_risks=[n.item for n in t.spec.accepted_risks],
        accepted_risks_recorded=(_risks := [{
            "item": n.item,
            "predictability": n.predictability.name if n.predictability else None,
            "justification": n.justification,
            "invalidation_condition": n.invalidation_condition,
        } for n in t.spec.accepted_risks]),
        accepted_risks_detail=_risks,
        risk_components=list(t.spec.risk_components),
        scope=list(t.spec.scope),
        created_at=t.created_at.isoformat(),
        deadline=t.deadline.isoformat() if t.deadline else None,
        was_challenged=t.was_challenged,
        criterion_mappings=[{"criterion_name": m.criterion_name, "child_id": m.child_id} for m in t.criterion_mappings],
        reopens=t.reopens,
        state_entered_at=(t.state_entered_at.isoformat() if t.state_entered_at else None),
    )

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
