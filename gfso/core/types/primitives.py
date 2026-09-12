"""The nouns of the protocol: task, spec, criterion, signal, verdict record, the typed answers a
transition gives back.

Frozen dataclasses, so a value that crossed a boundary cannot be edited behind the boundary's
back — the log is the record of change, and a mutable primitive would make it a partial one.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from typing import Mapping, NewType, Optional

from .enums import State, Signal, DoneReason, Verdict, AutonomyLevel, Predictability, RevisionReason


TaskId = NewType("TaskId", str)
AgentId = NewType("AgentId", str)


@dataclass(frozen=True)
class Probe:
    """One observation of one conjunct of a criterion — the criterion's own decision procedure, pinned.

    §10 types a criterion as a DECIDABLE predicate, and "for any accepted program the output matches
    gcc" is not one: the domain is infinite, so nothing returns pass/fail in finite time. What made
    such a text pass for a criterion is that the procedure was supplied later, by whoever validated,
    out of their own head — differently each round. A pinned probe set P is what turns the intention
    into the predicate the type demands ("matches gcc on P"), fixed BEFORE execution (Inv-1, §14.4),
    and it names its own residue: behaviour outside P is unchecked, which is the FM-3 boundary stated
    rather than closed (Ch. 8).
    """
    behaviour: str          # the conjunct of the criterion this observes
    command: str = ""       # how to observe it — runnable as written by someone who was not the executor
    expect: str = ""        # what the observation must show for this conjunct to count as passed


@dataclass(frozen=True)
class Criteria:
    name: str
    description: str = ""
    input: Optional[str] = None
    expected: Optional[str] = None
    n: Optional[int] = None
    timeout: Optional[int] = None
    depends_on: Optional[TaskId] = None  # §10: this criterion references a sibling's output (the glue)
                                         # → induces a Dep edge (from=depends_on, to=this task)
    check: tuple[Probe, ...] = ()        # the pinned decision procedure (§10/A1): what will be run to
                                         # decide this criterion, authored with the criterion by the
                                         # ISSUER side and before execution — never invented at
                                         # validation time by whoever happens to judge

    def __post_init__(self):
        if self.check and any(isinstance(p, Mapping) for p in self.check):
            object.__setattr__(self, "check", tuple(
                Probe(str(p.get("behaviour", "")), str(p.get("command", "")), str(p.get("expect", "")))
                if isinstance(p, Mapping) else p for p in self.check))


@dataclass(frozen=True)
class AcceptedRiskItem:
    """A declared scope-exclusion (STD-1) with its STD-2 predictability verdict.

    predictability=None → unclassified (legacy/plain text); on a decomposed node CHECK-4 flags the
    record as incomplete (the verdict is mandatory per factor, §13.1/§13.2).
    """
    item: str
    predictability: Optional[Predictability] = None
    justification: str = ""
    invalidation_condition: str = ""  # STD-1: when this exclusion flips back in-scope


@dataclass(frozen=True)
class Spec:
    description: str
    criteria: tuple[Criteria, ...]
    accepted_risks: tuple[AcceptedRiskItem, ...] = ()
    risk_components: tuple[str, ...] = ()  # STD-3: grouped correlated risk factors
    scope: tuple[str, ...] = ()            # §13.1: declared scope-BOUNDARY exclusions — a capability the goal
                                           # deliberately does NOT include (no materialization P). Objectified ON
                                           # the goal so the exclusion is VISIBLE in the graph, not an implicit
                                           # absence; distinct from ACCEPTED_RISKS (risk EVENTS with a P).
    name: str = ""                         # short node label (UI title); description = the full text

    def __post_init__(self):
        # Coerce bare strings → AcceptedRiskItem so existing call-sites keep working.
        if self.accepted_risks and any(isinstance(n, str) for n in self.accepted_risks):
            object.__setattr__(self, "accepted_risks", tuple(
                AcceptedRiskItem(n) if isinstance(n, str) else n for n in self.accepted_risks
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
    output — the consumer carries the `depends_on=from_id` criterion, §10).
    glue = the anti-mock truth-maker (canon §10 / §2): what of `from_id`'s output
    `to_id`'s criterion references, and what breaks if the edge is mishandled. A seam
    without glue is the FM-1 forgotten-glue hole — so glue is first-class on the edge,
    not folded into a node-local criterion (which would be mock-satisfiable).
    discovered=True if found via BLOCK, not declared upfront.
    provisional=True while the two-phase record (§14.2/§15.2) awaits adjudication: BLOCK
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
    # THE REWORKING BOUND, SET FOR THE USER THIS PRODUCT ACTUALLY HAS. Inv-5 demands that the
    # DELIVER→FAIL loop be FINITE; the canon's "default 3" is a default, not a magnitude it
    # derives. Three is the right number when the bound protects a HUMAN issuer's attention and
    # budget — it says "we talk before a fourth attempt". In agent work the issuer and the
    # executor are the same agent, so the cap protects nobody and buys the opposite: the node
    # goes ESCALATED (terminal, no way back), and at a ROOT — which has no parent to re-split —
    # the only sanctioned recovery, "re-decompose around it", degenerates into building another
    # root with no memory of the refusals, the regression set or the claim drift. Measured
    # 2026-09-20 on a `c_compiler` run: the judge refused the aggregate three times on real
    # defects, the root escalated, the agent built a second root, and it began again.
    # Finiteness is carried by what really bounds a run — the deadline (timeout → OVERDUE →
    # ESCALATED) and the money — not by an attempt count that means nothing at machine speed.
    # A human issuer who means "few attempts" sets it; 3 remains one line of configuration.
    max_iterations: int = 12
    deadline: Optional[datetime] = None
    created_at: datetime = field(default_factory=datetime.now)
    # Inv-5 clock: when the CURRENT state was entered (stamped at every state change). Deliberately
    # not persisted — a restart re-arms the clock from load time; finiteness still holds.
    state_entered_at: datetime = field(default_factory=datetime.now)
    # THE CLAIM AS IT WAS AUTHORED, kept beside the claim as it stands. Set once, at the first
    # ASSIGN, and never touched by a revision — so "what did this node promise before anyone
    # worked on it" is a fact on the node rather than an archaeology exercise over the log. The
    # author asked for exactly this and it was not built: a claim narrows most cheaply through its
    # risk register, and with nothing to compare against, the narrowing is invisible until someone
    # reads the whole trace by hand (measured on `c_compiler`, 2026-09-20/21 — the register grew
    # from seven entries to nine after the work began and every surface said the claim stood).
    authored: Optional[Spec] = None
    done_reason: Optional[DoneReason] = None
    autonomy: AutonomyLevel = AutonomyLevel.MANUAL
    was_challenged: bool = False
    was_reassigned: bool = False
    false_positive: bool = False  # V=pass but later found wrong (q_V)
    # R′ (§14.3): ONE sign-agnostic per-node counter next to max_iterations — counts EVERY
    # quasi-terminal exit (DONE→OFFERED and ABANDONED→OFFERED alike); exhaustion = finality (Inv-5).
    reopens: int = 0
    max_reopens: int = 1
    # Set when a DONE(pass/auto) node is reopened under the SAME criteria: if the fresh run then
    # FAILs, the old pass is refuted — exactly q_V's pass→later-fail member (§14.3/§15.2), no new machinery.
    reopened_from_pass: bool = False
    # Contract generation: bumped by every revision (re-ASSIGN under the same id, Inv-1). Neither
    # `iteration` (the rework loop) nor `reopens` (R′) moves on a revision, so this is what tells a
    # verdict about the delivery that stood BEFORE the contract changed from one about the current
    # contract — §14.3 admits a re-ASSIGN from VALIDATING, and §6.3 voids the pending delivery with it.
    revisions: int = 0
    # §24.5 causal typing of revisions. spec_defect_criteria_change = the q_T member («criteria
    # изменены по дефекту спеки»); reassign_* refine q_Del: when a Del change carried a typed
    # reason, only CAPABILITY_MISMATCH counts (untyped keeps the documented over-approximation).
    spec_defect_criteria_change: bool = False
    reassign_reason_typed: bool = False
    reassign_capability_mismatch: bool = False
    criterion_mappings: tuple[CriterionMapping, ...] = ()
    verified: bool = False  # L2 dirty flag: stored critique is fresh for current decomposition


@dataclass(frozen=True)
class GuardContext:
    iteration: int
    max_iterations: int
    # R′ finality-gate inputs (§14.3), computed by the graph at the chokepoint and read by the pure
    # FSM guard. `consumed` defaults True = FAIL-CLOSED: no reopen unless the graph explicitly
    # established the terminal is locally reversible (не потреблён). Meaningful only on DONE/ABANDONED.
    reopens: int = 0
    max_reopens: int = 1
    consumed: bool = True


@dataclass(frozen=True)
class CheckResult:
    check_name: str
    passed: bool
    details: str = ""
    skipped: bool = False
    #: TRUE OVER NOTHING. A check whose subject set is empty — no Dep edges to order, no risk
    #: components to carry, no child deadlines to place — is a conjunction over ∅ and passes
    #: VACUOUSLY. That is not the same fact as "this was checked and held", and a reader looking at
    #: a row of green ticks cannot tell them apart: the class this project keeps finding in itself
    #: is a rule that is vacuously true at zero X (a node closed in four seconds through
    #: `criteria: []`, 2026-09-02). `skipped` is the third case — the check did not run at all.
    vacuous: bool = False


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
    # ASSIGN: the rework bound. On the FIRST assign it is the node's budget; on a REVISION
    # `None` means keep the one the node has, like `deadline` and `assignee` beside it.
    max_iterations: Optional[int] = 12
    covers: tuple[str, ...] = ()                   # ASSIGN: parent criteria this child is mapped to (§10)
    reason: Optional[str] = None                   # CHALLENGE, BLOCK, CANCEL
    in_flight: Optional[str] = None                # CONFIRM_CANCEL: executor's in-flight state at cancellation (Thm 11, §14.3)
    blocker_task_id: Optional[TaskId] = None       # BLOCK: the undeclared prerequisite NODE (→ provisional discovered-Dep,
                                                   # §14.2); RESOLVE_BLOCK: the corrected source on mis-attribution
    blocker_task_ids: tuple[TaskId, ...] = ()      # BLOCK: ALL undeclared prerequisite nodes — one BLOCK may surface
                                                   # several (§14.2: an edge per surfaced prerequisite); RESOLVE_BLOCK:
                                                   # the corrected FULL set (SET semantics — unlisted provisionals retract)
    external: bool = False                         # RESOLVE_BLOCK: blocker was non-producible (no producer node) →
                                                   # retract the provisional edge; the FM-5 currency line, not a Dep (§14.2)
    result: Optional[str] = None                   # DELIVER
    self_validation: Optional[Verdict] = None      # DELIVER
    new_spec: Optional[Spec] = None                # ACCEPT_CHALLENGE
    justification: Optional[str] = None            # REJECT_CHALLENGE
    failed_criteria: tuple[str, ...] = ()          # FAIL
    action: Optional[str] = None                   # RESOLVE_BLOCK
    revision_reason: Optional[RevisionReason] = None  # re-ASSIGN: causal type of the revision (§24.5)

    @property
    def blockers(self) -> tuple[TaskId, ...]:
        """The ONE normalization point for the blocker payload: singular ∪ plural, deduped,
        order preserved (singular kept for back-compat — a single id ≡ a set of one)."""
        ids = (self.blocker_task_id,) + tuple(self.blocker_task_ids) if self.blocker_task_id \
            else tuple(self.blocker_task_ids)
        seen: set = set()
        return tuple(b for b in ids if b and not (b in seen or seen.add(b)))


@dataclass(frozen=True)
class Wait:
    """WHY a node is not on the frontier, and what would put it there — one shape, six authors.

    The answer was built in six places: a parent held by Thm 1, a validator already running, the
    plan gate, the dependency order, a stranded terminal, and `get_task`'s own `blocked_by`. Three
    of them made `waits_on` a comma-joined STRING and one a LIST, and both kinds were merged into
    the same `waiting` array; the stranded entry dropped `assignee` and `waits_on` altogether, and
    the sixth renamed the fields (`what_now` for `opens_with`, `reason` for `why`). It was already
    live: the dispatcher tells `opens_with` apart to decide whether a wait is dep-order, so a
    dependency wait was narrated with a list repr and the wrong canon citation.

    `waits_on` is ALWAYS a tuple of ids or plain phrases — never a pre-joined sentence."""

    task_id: str
    state: str
    waits_on: tuple[str, ...]
    why: str
    opens_with: str
    assignee: Optional[str] = None
    kind: str = "dependency"      # dependency | children | validator | plan | stranded | blocker

    def as_dict(self) -> dict:
        """The wire form the frontier already speaks — `waits_on` always a list, `kind` always present."""
        return {"task_id": self.task_id, "state": self.state, "assignee": self.assignee,
                "waits_on": list(self.waits_on), "why": self.why,
                "opens_with": self.opens_with, "kind": self.kind}


@dataclass(frozen=True)
class Refusal:
    """WHY a signal moved nothing, in fields rather than in prose.

    Four independent places used to answer that question and each answered differently: the FSM
    returned a bare `None` (no reason at all — a refusal the log recorded as a fact with no
    content), the validation layer raised free-form text, the loop wrote whatever it was handed, and
    the tool layer assembled a dict per branch. So the same act — pressing a transition — could come
    back as a sentence, as a silence, or as a different sentence depending on which door refused it.

    `kind` says WHICH refusal it is (the reader's first question and the one the old single sentence
    conflated); `why` is the fact; `route` is where the caller's intent actually goes, when there is
    somewhere; `opens_with` is the act that would make the same signal land."""

    kind: str                      # "state" | "guard" | "rule" | "payload" | "role"
    why: str
    route: Optional[str] = None
    opens_with: Optional[str] = None


@dataclass(frozen=True)
class SignalOutcome:
    """What the system answers when a transition is attempted — ONE shape, every door.

    The fields are always present: a caller never has to know which branch produced the reply to
    know where to look. `accepted` with `to_state` is the whole of the happy answer; a refusal
    carries `refusal` and leaves `to_state` at None (nothing moved)."""

    task_id: TaskId
    signal: Signal
    accepted: bool
    from_state: Optional[State] = None
    to_state: Optional[State] = None
    refusal: Optional[Refusal] = None

    def as_dict(self) -> dict:
        """The wire form the doors already speak — `accepted` / `state` / `error`, unchanged, plus
        the refusal's own fields for a reader that wants them apart."""
        out: dict = {"accepted": self.accepted,
                     "state": (self.to_state or self.from_state).name
                     if (self.to_state or self.from_state) else None}
        if self.refusal is not None:
            out["error"] = " ".join(x for x in (self.refusal.why, self.refusal.route) if x)
            out["refused_by"] = self.refusal.kind
            if self.refusal.opens_with:
                out["opens_with"] = self.refusal.opens_with
        return out


@dataclass(frozen=True)
class DispatchPayload:
    signal: Signal
    task: Task
    check_results: tuple[CheckResult, ...] = ()
    recommendation: Optional[Recommendation] = None


def passed(task: "Task | None") -> bool:
    """Did this node EARN a pass — DONE with a verdict someone gave it?

    The question was written in nine places and three spellings (an enum compare, a `.name` string
    compare, a `getattr(…, "name", "")` compare), and they were not equivalent: some counted
    AUTO_PASS and some did not, which is a difference in MEANING carried by an accident of style.
    §21 records the timeout close apart from a pass precisely because it is not one — so that is the
    other predicate, below, and a caller picks which question it is asking.
    """
    return task is not None and task.state is State.DONE and task.done_reason is DoneReason.PASS


def settled_positive(task: "Task | None") -> bool:
    """DONE and not refused — an earned PASS *or* the timeout's auto_pass (§21, Ch. 24).

    For populations where the canon counts a node that completed without a refusal, however it got
    there. Anything that must not accept a verdict nobody gave uses `passed` instead.
    """
    return (task is not None and task.state is State.DONE
            and task.done_reason in (DoneReason.PASS, DoneReason.AUTO_PASS))
