from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from typing import NewType, Optional

from .enums import State, Signal, DoneReason, Verdict, AutonomyLevel


TaskId = NewType("TaskId", str)
AgentId = NewType("AgentId", str)


@dataclass(frozen=True)
class Criteria:
    name: str
    description: str


@dataclass(frozen=True)
class Spec:
    description: str
    criteria: tuple[Criteria, ...]
    neglected: tuple[str, ...] = ()
    risk_components: tuple[str, ...] = ()  # STD-3: grouped correlated risk factors


@dataclass(frozen=True)
class CriterionMapping:
    """Explicit mapping: which child is responsible for which parent criterion."""
    criterion_name: str
    child_id: TaskId


@dataclass(frozen=True)
class DepEdge:
    """Dependency edge. discovered=True if found via BLOCK, not declared upfront."""
    from_id: TaskId
    to_id: TaskId
    discovered: bool = False


@dataclass
class Task:
    id: TaskId
    spec: Spec
    state: State = State.IDLE
    parent_id: Optional[TaskId] = None
    assignee: Optional[AgentId] = None
    iteration: int = 0
    max_iterations: int = 3
    deadline: Optional[datetime] = None
    created_at: datetime = field(default_factory=datetime.now)
    done_reason: Optional[DoneReason] = None
    autonomy: AutonomyLevel = AutonomyLevel.MANUAL
    was_challenged: bool = False
    was_reassigned: bool = False
    false_positive: bool = False  # V=pass but later found wrong (q_V)
    criterion_mappings: tuple[CriterionMapping, ...] = ()


@dataclass(frozen=True)
class GuardContext:
    iteration: int
    max_iterations: int


@dataclass(frozen=True)
class CheckResult:
    check_name: str
    passed: bool
    details: str = ""
    skipped: bool = False


@dataclass(frozen=True)
class Recommendation:
    suggestions: tuple[str, ...] = ()


@dataclass(frozen=True)
class GraphContext:
    task: Task
    children: tuple[Task, ...] = ()
    parent: Optional[Task] = None
    check_results: tuple[CheckResult, ...] = ()
    recommendation: Optional[Recommendation] = None


@dataclass(frozen=True)
class SignalData:
    """Data carried by a signal through the queue."""
    signal: Signal
    task_id: TaskId
    source: Optional[AgentId] = None
    # Signal-specific payloads
    spec: Optional[Spec] = None                    # ASSIGN
    reason: Optional[str] = None                   # CHALLENGE, BLOCK, CANCEL
    result: Optional[str] = None                   # DELIVER
    self_validation: Optional[Verdict] = None      # DELIVER
    new_spec: Optional[Spec] = None                # ACCEPT_CHALLENGE
    justification: Optional[str] = None            # REJECT_CHALLENGE
    failed_criteria: tuple[str, ...] = ()          # FAIL
    action: Optional[str] = None                   # RESOLVE_BLOCK


@dataclass(frozen=True)
class DispatchPayload:
    signal: Signal
    task: Task
    check_results: tuple[CheckResult, ...] = ()
    recommendation: Optional[Recommendation] = None
