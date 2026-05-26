"""Pydantic request/response models for GFSO API."""
from __future__ import annotations

from typing import Optional
from pydantic import BaseModel

from gfso.core.types import (
    Task, State, Signal, Spec, Criteria, CriterionMapping,
    CheckResult, Recommendation, SignalData, Verdict,
    TaskId, AgentId,
)
from gfso.engine.audit import AuditEntry


# === Request models ===

class CriteriaIn(BaseModel):
    name: str
    description: str

class SpecIn(BaseModel):
    description: str
    criteria: list[CriteriaIn] = []
    neglected: list[str] = []
    risk_components: list[str] = []

class CreateTaskRequest(BaseModel):
    task_id: str = ""
    spec: SpecIn
    assignee: str
    parent_id: str | None = None
    max_iterations: int = 3
    deadline: str | None = None  # ISO 8601; UI ready, engine.assign_task ignores until extended

class SendSignalRequest(BaseModel):
    signal: str
    source: str = ""
    reason: str | None = None
    result: str | None = None
    self_validation: str | None = None
    new_spec: SpecIn | None = None
    justification: str | None = None
    failed_criteria: list[str] = []
    action: str | None = None

class CriterionMappingIn(BaseModel):
    criterion_name: str
    child_id: str

class DecomposeRequest(BaseModel):
    children: list[CreateTaskRequest]
    criterion_mappings: list[CriterionMappingIn] = []


# === Response models ===

class TaskOut(BaseModel):
    id: str
    description: str
    state: str
    parent_id: str | None
    assignee: str | None
    iteration: int
    max_iterations: int
    done_reason: str | None
    criteria: list[CriteriaIn]
    neglected: list[str]
    risk_components: list[str]
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

class GraphEdge(BaseModel):
    source: str
    target: str
    type: str
    discovered: bool = False

class GraphOut(BaseModel):
    nodes: list[GraphNode]
    edges: list[GraphEdge]

class MetricsOut(BaseModel):
    q_T: float
    q_D: float
    q_V: float
    q_Dep: float
    q_Del: float

class SuggestCriteriaRequest(BaseModel):
    description: str

class SuggestCriteriaResponse(BaseModel):
    criteria: list[CriteriaIn]


# === Converters ===

def spec_in_to_spec(s: SpecIn) -> Spec:
    return Spec(
        description=s.description,
        criteria=tuple(Criteria(c.name, c.description) for c in s.criteria),
        neglected=tuple(s.neglected),
        risk_components=tuple(s.risk_components),
    )

def task_to_out(t: Task) -> TaskOut:
    return TaskOut(
        id=t.id, description=t.spec.description, state=t.state.name,
        parent_id=t.parent_id, assignee=t.assignee,
        iteration=t.iteration, max_iterations=t.max_iterations,
        done_reason=t.done_reason.name if t.done_reason else None,
        criteria=[CriteriaIn(name=c.name, description=c.description) for c in t.spec.criteria],
        neglected=list(t.spec.neglected),
        risk_components=list(t.spec.risk_components),
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
    )

def signal_request_to_data(task_id: str, req: SendSignalRequest) -> SignalData:
    sv = None
    if req.self_validation:
        sv = Verdict[req.self_validation]
    new_spec = None
    if req.new_spec:
        new_spec = spec_in_to_spec(req.new_spec)
    return SignalData(
        signal=Signal[req.signal],
        task_id=TaskId(task_id),
        source=AgentId(req.source) if req.source else None,
        reason=req.reason, result=req.result,
        self_validation=sv, new_spec=new_spec,
        justification=req.justification,
        failed_criteria=tuple(req.failed_criteria),
        action=req.action,
    )
