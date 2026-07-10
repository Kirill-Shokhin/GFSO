"""Pydantic request/response models for GFSO API."""
from __future__ import annotations

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
    neglected: list[str]  # item texts (back-compat)
    neglected_detail: list[dict] = []  # [{item, predictability, justification}]
    risk_components: list[str]
    scope: list[str] = []  # Ст. II.6 declared scope-boundary exclusions (objectified on the goal)
    created_at: str
    deadline: str | None
    was_challenged: bool
    criterion_mappings: list[dict] = []  # [{criterion_name, child_id}]

class CheckResultOut(BaseModel):
    check_name: str
    passed: bool
    details: str
    skipped: bool

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
    in_flight: str | None = None  # CANCEL_ACK: executor's in-flight state at cancellation (T11)

class TaskDetailOut(TaskOut):
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
    done_reason: str | None = None   # CANCELLED = a tombstone (UI greys it, not an active node)

class GraphEdge(BaseModel):
    source: str
    target: str
    type: str
    discovered: bool = False

class GraphOut(BaseModel):
    nodes: list[GraphNode]
    edges: list[GraphEdge]

class MetricsOut(BaseModel):
    # None = ⊥: empty population (canon §13) — no observations is not "100%"; the UI renders a dash
    q_T: float | None = None
    q_D: float | None = None
    q_V: float | None = None
    q_Dep: float | None = None
    q_Del: float | None = None

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
    return TaskOut(
        id=t.id, name=t.spec.name, description=t.spec.description, state=t.state.name,
        parent_id=t.parent_id, assignee=t.assignee,
        iteration=t.iteration, max_iterations=t.max_iterations,
        done_reason=t.done_reason.name if t.done_reason else None,
        criteria=[CriteriaIn(name=c.name, description=c.description) for c in t.spec.criteria],
        neglected=[n.item for n in t.spec.neglected],
        neglected_detail=[{
            "item": n.item,
            "predictability": n.predictability.name if n.predictability else None,
            "justification": n.justification,
        } for n in t.spec.neglected],
        risk_components=list(t.spec.risk_components),
        scope=list(t.spec.scope),
        created_at=t.created_at.isoformat(),
        deadline=t.deadline.isoformat() if t.deadline else None,
        was_challenged=t.was_challenged,
        criterion_mappings=[{"criterion_name": m.criterion_name, "child_id": m.child_id} for m in t.criterion_mappings],
    )

def audit_to_out(e: AuditEntry) -> AuditEntryOut:
    return AuditEntryOut(
        timestamp=e.timestamp.isoformat(), task_id=e.task_id,
        signal=e.signal.name,
        old_state=e.old_state.name if e.old_state else None,
        new_state=e.new_state.name if e.new_state else None,
        effects=list(e.effects), rejected=e.rejected, error=e.error,
        source=e.source, reason=e.reason, justification=e.justification,
        result=e.result, failed_criteria=list(e.failed_criteria), action=e.action,
        in_flight=e.in_flight,
    )
