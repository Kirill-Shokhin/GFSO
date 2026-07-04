from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from typing import NewType, Optional

from .enums import State, Signal, DoneReason, Verdict, AutonomyLevel, Predictability


TaskId = NewType("TaskId", str)
AgentId = NewType("AgentId", str)


@dataclass(frozen=True)
class Criteria:
    name: str
    description: str = ""
    input: Optional[str] = None
    expected: Optional[str] = None
    n: Optional[int] = None
    timeout: Optional[int] = None
    depends_on: Optional[TaskId] = None  # §2.2: this criterion references a sibling's output (the glue)
                                         # → induces a Dep edge (from=depends_on, to=this task)


@dataclass(frozen=True)
class NeglectedItem:
    """A declared scope-exclusion (STD-1) with its STD-2 predictability verdict.

    predictability=None → unclassified (legacy/plain text); on a decomposed node CHECK-4 flags the
    record as incomplete (the verdict is mandatory per factor, §5.1/Ст. I.10).
    """
    item: str
    predictability: Optional[Predictability] = None
    justification: str = ""
    invalidation_condition: str = ""  # STD-1: when this exclusion flips back in-scope


@dataclass(frozen=True)
class Spec:
    description: str
    criteria: tuple[Criteria, ...]
    neglected: tuple[NeglectedItem, ...] = ()
    risk_components: tuple[str, ...] = ()  # STD-3: grouped correlated risk factors
    name: str = ""                         # short node label (UI title); description = the full text

    def __post_init__(self):
        # Coerce bare strings → NeglectedItem so existing call-sites keep working.
        if self.neglected and any(isinstance(n, str) for n in self.neglected):
            object.__setattr__(self, "neglected", tuple(
                NeglectedItem(n) if isinstance(n, str) else n for n in self.neglected
            ))


@dataclass(frozen=True)
class CriterionMapping:
    """Explicit mapping: which child is responsible for which parent criterion."""
    criterion_name: str
    child_id: TaskId


@dataclass(frozen=True)
class DepEdge:
    """Dependency edge (a cross-subtask seam).

    Direction: `from_id` = PRODUCER, `to_id` = CONSUMER (to_id depends on from_id's
    output — the consumer carries the `depends_on=from_id` criterion, §2.2).
    glue = the anti-mock truth-maker (canon §2.2 / §18.10): what of `from_id`'s output
    `to_id`'s criterion references, and what breaks if the edge is mishandled. A seam
    without glue is the FM-1 forgotten-glue hole — so glue is first-class on the edge,
    not folded into a node-local criterion (which would be mock-satisfiable).
    discovered=True if found via BLOCK, not declared upfront.
    provisional=True while the two-phase record (§6.2/§7.2) awaits adjudication: BLOCK
    registers provisional, RESOLVE_BLOCK confirms/re-attributes/retracts; an escalated-
    unresolved provisional still counts toward q_Dep (the hole was real).
    """
    from_id: TaskId
    to_id: TaskId
    discovered: bool = False
    glue: str = ""
    provisional: bool = False


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
    verified: bool = False  # L2 dirty flag: stored critique is fresh for current decomposition


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
    spec: Optional[Spec] = None                    # ASSIGN (the packet)
    assignee: Optional[AgentId] = None             # ASSIGN: who executes (Del)
    parent_id: Optional[TaskId] = None             # ASSIGN: parent for a child node
    deadline: Optional[datetime] = None            # ASSIGN: T=(spec,criteria,deadline)
    max_iterations: int = 3                        # ASSIGN: rework bound
    covers: tuple[str, ...] = ()                   # ASSIGN: parent criteria this child is mapped to (§2.2)
    reason: Optional[str] = None                   # CHALLENGE, BLOCK, CANCEL
    in_flight: Optional[str] = None                # CANCEL_ACK: executor's in-flight state at cancellation (T11, §6.3)
    blocker_task_id: Optional[TaskId] = None       # BLOCK: the undeclared prerequisite NODE (→ provisional discovered-Dep,
                                                   # §6.2); RESOLVE_BLOCK: the corrected source on mis-attribution
    external: bool = False                         # RESOLVE_BLOCK: blocker was non-producible (no producer node) →
                                                   # retract the provisional edge; the FM-5 currency line, not a Dep (§6.2)
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
