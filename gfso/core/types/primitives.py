"""The nouns of the protocol: task, spec, criterion, signal, verdict record, the typed answers a
transition gives back.

Frozen dataclasses, so a value that crossed a boundary cannot be edited behind the boundary's
back — the log is the record of change, and a mutable primitive would make it a partial one.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from typing import Mapping, NewType, Optional

from gfso.config import LABEL_CHARS

from .enums import State, Signal, DoneReason, Verdict, AutonomyLevel, Predictability, RevisionReason


TaskId = NewType("TaskId", str)
AgentId = NewType("AgentId", str)

# THE REWORKING BOUND, in ONE place. It was spelled three times — here, in the effect that carries a
# revision, and in the storage DDL — and two of them still said 3 after the value moved to 12, so the
# product shipped a rule whose number depended on which door wrote the row. The reasoning behind the
# magnitude is on `Task.max_iterations` below; what this constant carries is that there is exactly one.
DEFAULT_MAX_ITERATIONS = 12


@dataclass(frozen=True)
class Probe:
    """One observation of one conjunct of a criterion — the criterion's own decision procedure, pinned.

    §2 types a criterion as a DECIDABLE predicate, and "for any accepted program the output matches
    gcc" is not one: the domain is infinite, so nothing returns pass/fail in finite time. What made
    such a text pass for a criterion is that the procedure was supplied later, by whoever validated,
    out of their own head — differently each round. A pinned probe set P is what turns the intention
    into the predicate the type demands ("matches gcc on P"), fixed BEFORE execution (Inv-1, §12.3),
    and it names its own residue: behaviour outside P is unchecked, which is the FM-3 boundary stated
    rather than closed (Ch. 20).
    """
    behaviour: str          # the conjunct of the criterion this observes
    command: str = ""       # how to observe it — runnable as written by someone who was not the executor
    expect: str = ""        # what the observation must show for this conjunct to count as passed
    # The files the command reads, as ((relative path, content), …), materialized by the SYSTEM at
    # validation into a directory the validator owns; the command names that directory `{inputs}`.
    # A probe over a corpus the executor writes is a fixed command whose object moves under it:
    # measured on `c_compiler` (2026-09-20/21), `torture_corpus/*.c` grew from 60 files to 79 under a
    # node that closed with `procedure_moved_since_authoring: false`. Carried here, the corpus is
    # part of the pinned procedure — its digest moves when it does, and nobody but the issuer moves it.
    inputs: tuple[tuple[str, str], ...] = ()

    def __post_init__(self):
        raw = self.inputs
        if isinstance(raw, Mapping):
            raw = raw.items()
        # a structured-output door hands them over as [{path, content}]; every reader gets pairs
        object.__setattr__(self, "inputs", tuple(sorted(
            (str(x.get("path", "")), str(x.get("content", ""))) if isinstance(x, Mapping)
            else (str(x[0]), str(x[1])) for x in (raw or ()))))

    @classmethod
    def of(cls, p: "Probe | Mapping") -> "Probe":
        """One reader for a probe however a door hands it over."""
        if isinstance(p, Probe):
            return p
        return cls(str(p.get("behaviour", "") or ""), str(p.get("command", "") or ""),
                   str(p.get("expect", "") or ""), p.get("inputs") or ())

    def to_dict(self) -> dict:
        """The probe as a door serializes it — one writer, so a field cannot travel through one
        door and be dropped by the next (the `check` field itself was lost that way once)."""
        d = {"behaviour": self.behaviour, "command": self.command, "expect": self.expect}
        if self.inputs:
            d["inputs"] = dict(self.inputs)
        return d


@dataclass(frozen=True)
class Criteria:
    name: str
    description: str = ""
    input: Optional[str] = None
    expected: Optional[str] = None
    n: Optional[int] = None
    timeout: Optional[int] = None
    depends_on: Optional[TaskId] = None  # §2: this criterion references a sibling's output (the glue)
                                         # → induces a Dep edge (from=depends_on, to=this task)
    check: tuple[Probe, ...] = ()        # the pinned decision procedure (§2/A1): what will be run to
                                         # decide this criterion, authored with the criterion by the
                                         # ISSUER side and before execution — never invented at
                                         # validation time by whoever happens to validate
    # HOW THE CHILDREN'S CRITERIA SECURE THIS ONE — fᵢ, §2.4: "for each cᵢ the Issuer declares HOW
    # the children's criteria secure cᵢ — a composition function fᵢ", and CHECK-7 is ⋀criteria(tⱼ)
    # ⊨ cᵢ under it. Unwritten, the arithmetic tier had exactly one composition in it: summation.
    # A parent bound met by a parallel fan-out (the slowest child decides — max) was reported as a
    # breach because two children of 100 "sum" to 200, and a real budget split was passed wherever
    # the children happened to add up. The function belongs to the criterion, not to a mapping: it
    # is one statement about cᵢ however many children carry it, and it is the issuer's to write.
    composition: str = ""

    def __post_init__(self):
        if self.check and any(isinstance(p, Mapping) for p in self.check):
            object.__setattr__(self, "check", tuple(Probe.of(p) for p in self.check))


@dataclass(frozen=True)
class AcceptedRiskItem:
    """One entry of a split's ACCEPTED_RISKS register (§9.2): an uncertain EVENT the split accepts — never a scope
    boundary (that is the goal's `scope`) and never a fact already known. STD-1's four fields — the factor (`item`),
    its estimate (`p`, the materialization probability, and `impact`), `justification`, `invalidation_condition` —
    with STD-2's predictability verdict, and STD-3's `component` where the entry is a correlated component's
    grouped acceptance (CHECK-5 is met by it). A field left empty is a record CHECK-4 refuses on a decomposed node.

    `denial` marks the one entry every split carries for its own denial by S (§9.5, CHECK-4's "nonempty"): the
    composition claim the split pre-registers, refuted at contact. Its P is the recorded refutation rate of
    comparable splits where one exists, else the decomposer's stated estimate; it is grouped with no component and
    stands beside the roll-up, and it is not admitted (§9.2): it bounds nothing, it states the hypothesis's odds.
    """
    item: str
    predictability: Optional[Predictability] = None
    justification: str = ""
    invalidation_condition: str = ""  # STD-1: when to revisit the acceptance
    p: Optional[float] = None         # STD-1 estimate: the probability the event materializes, in (0, 1]
    impact: str = ""                  # STD-1 estimate: what it costs the goal when it does
    component: str = ""               # STD-3: the risk component this entry accepts as a group
    denial: bool = False              # §9.5: the split's own denial by S, not a risk event it accepts

    #: The denial's fixed text — what is denied and when it is revisited are the same for every split (§9.5).
    DENIAL_ITEM = "this split's composition claim, denied at contact (the parent fails while every child passes)"
    DENIAL_IMPACT = "the parent's criteria fail over passing children; the split is revised or re-decomposed"
    DENIAL_REVISIT = "contact refutes the split (its node FAILs while its active children pass)"

    @classmethod
    def denial_of(cls, p, justification: str) -> "AcceptedRiskItem":
        """The split's denial entry with the decomposer's P and its justification."""
        return cls(cls.DENIAL_ITEM, None, str(justification or ""), cls.DENIAL_REVISIT,
                   float(p) if isinstance(p, (int, float)) and not isinstance(p, bool) else None,
                   cls.DENIAL_IMPACT, "", True)

    def to_dict(self) -> dict:
        """The one written form of an entry — storage, the plan export and the log all write this."""
        return {"item": self.item, "predictability": self.predictability.name if self.predictability else None,
                "justification": self.justification, "invalidation_condition": self.invalidation_condition,
                "p": self.p, "impact": self.impact, "component": self.component, "denial": self.denial}

    @classmethod
    def of(cls, raw, predictability=None) -> "AcceptedRiskItem":
        """The one reader: a bare string (the factor alone), or the written form — `invalidation` accepted as the
        plan schema's name for the condition. `predictability` turns the written verdict into the enum (each door
        names a wrong word its own way)."""
        if isinstance(raw, AcceptedRiskItem):
            return raw
        if isinstance(raw, str):
            return cls(raw)
        if raw.get("denial") is True:          # its item, impact and revisit are fixed (§9.5); the decomposer gives P
            return cls.denial_of(raw.get("p"), str(raw.get("justification") or ""))
        named = predictability or (lambda s: Predictability.__members__.get(s))
        verdict, p = raw.get("predictability"), raw.get("p")
        return cls(str(raw.get("item", "")), named(verdict) if verdict else None, str(raw.get("justification") or ""),
                   str(raw.get("invalidation_condition") or raw.get("invalidation") or ""),
                   float(p) if isinstance(p, (int, float)) and not isinstance(p, bool) else None,
                   str(raw.get("impact") or ""), str(raw.get("component") or ""), raw.get("denial") is True)


@dataclass(frozen=True)
class Spec:
    description: str
    criteria: tuple[Criteria, ...]
    accepted_risks: tuple[AcceptedRiskItem, ...] = ()
    risk_components: tuple[str, ...] = ()  # STD-3: grouped correlated risk factors
    scope: tuple[str, ...] = ()            # §9.2: declared scope-BOUNDARY exclusions — a capability the goal
                                           # deliberately does NOT include (no materialization P). Objectified ON
                                           # the goal so the exclusion is VISIBLE in the graph, not an implicit
                                           # absence; distinct from ACCEPTED_RISKS (risk EVENTS with a P).
    name: str = ""                         # short node label (UI title); description = the full text
    # WHICH OF THE PARENT'S RISK COMPONENTS (STD-3, §9.4) THIS NODE IS THE MITIGATION FOR. CHECK-5
    # asks whether every component has a child addressing it, and it used to answer by looking for
    # the component's NAME inside a child's description: `component.lower() in desc`. A node called
    # "drought-resistant seed trial" covered `drought`; one called "irrigation" covered nothing,
    # and a node that merely MENTIONED the word covered it. Coverage is a claim the split's author
    # makes, so it is recorded here like `covers` records a criterion's — a check reads a record,
    # never prose.
    covers_risks: tuple[str, ...] = ()

    def __post_init__(self):
        # Coerce bare strings → AcceptedRiskItem so existing call-sites keep working.
        if self.accepted_risks and any(isinstance(n, str) for n in self.accepted_risks):
            object.__setattr__(self, "accepted_risks", tuple(
                AcceptedRiskItem(n) if isinstance(n, str) else n for n in self.accepted_risks
            ))

    @property
    def set_aside(self) -> tuple[AcceptedRiskItem, ...]:
        """The risk events the register accepts — what a reader told "the plan set these aside" may read. The split's
        own denial by S is not one: not admitted, it licenses nothing (§9.2), and read as set aside it would excuse
        exactly the composition failure it states."""
        return tuple(n for n in self.accepted_risks if not n.denial)


@dataclass(frozen=True)
class Register:
    """A split's ACCEPTED_RISKS register (§9.2) with the STD-3 components it groups them by (§9.4): its decomposer
    Del(t)'s statement about his own split, authored and changed only with it — at its admission (§11.5). Not the
    packet's pre-filled ACCEPTED_RISKS (`Spec.accepted_risks`), which is task data its issuer writes (§10.1): one
    field carried both, so the decomposer could change his own register only through a revision his issuer made,
    re-offering the node (sync audit, A-F6)."""
    items: tuple[AcceptedRiskItem, ...] = ()
    components: tuple[str, ...] = ()

    def __post_init__(self):
        # a bare string is an unclassified entry, as `Spec` reads one
        object.__setattr__(self, "items", tuple(AcceptedRiskItem(n) if isinstance(n, str) else n for n in self.items))

    @property
    def set_aside(self) -> tuple[AcceptedRiskItem, ...]:
        """The risk events it accepts — its own denial by S is not one (`Spec.set_aside`)."""
        return tuple(n for n in self.items if not n.denial)


@dataclass(frozen=True)
class CriterionMapping:
    """Explicit mapping: which child is responsible for which parent criterion."""
    criterion_name: str
    child_id: TaskId


@dataclass(frozen=True)
class DepEdge:
    """Dependency edge (a cross-subtask seam).

    Direction: `from_id` = PRODUCER, `to_id` = CONSUMER (to_id depends on from_id's
    output — the consumer carries the `depends_on=from_id` criterion, §2).
    glue = the anti-mock truth-maker (canon §2 / §3): what of `from_id`'s output
    `to_id`'s criterion references, and what breaks if the edge is mishandled. A seam
    without glue is the FM-1 forgotten-glue hole — so glue is first-class on the edge,
    not folded into a node-local criterion (which would be mock-satisfiable).
    discovered=True if found via BLOCK, not declared upfront.
    provisional=True while the two-phase record (§11.3/§15.5) awaits adjudication: BLOCK
    registers provisional, RESOLVE_BLOCK confirms/re-attributes/retracts; an escalated-
    unresolved provisional still counts toward q_Dep (the hole was real).
    closed=True once the BLOCK that made it no longer stands and nobody answered it (its node left BLOCKED by a
    re-ASSIGN, a CANCEL or its bound): counted in q_Dep, never an edge of E_Dep, asking nothing (§15.5).
    declared_first=True when, at the record's FIRST BLOCK, a packet version already installed had declared the pair:
    the BLOCK met a dependency the plan knew, so q_Dep counts it declared (§15.5 "declared before any BLOCK named
    them") — the record still carries the wait. A record is a record (the wait, admission and CHECK-2 read it so);
    whether it is a DISCOVERY is `discovered and not declared_first`, read by q_Dep alone.
    refuted=True once the issuer's adjudication refutes it: kept, not deleted, so the order of "named by a BLOCK"
    and "declared" stays readable; it asks nothing, is no edge of E_Dep and leaves q_Dep's population (§15.5).
    A later BLOCK naming it reopens it.
    """
    from_id: TaskId
    to_id: TaskId
    discovered: bool = False
    glue: str = ""
    provisional: bool = False
    closed: bool = False
    declared_first: bool = False
    refuted: bool = False


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
    # 2026-09-20 on a `c_compiler` run: the validator refused the aggregate three times on real
    # defects, the root escalated, the agent built a second root, and it began again.
    # Finiteness is carried by what really bounds a run — the deadline (timeout → ESCALATED)
    # and the money — not by an attempt count that means nothing at machine speed.
    # A human issuer who means "few attempts" sets it on the node — it is a packet field, and
    # since §12.5 exhausting it is a question FOR the issuer rather than a dead end, the
    # number is his forecast of his own cost and nothing else depends on it.
    max_iterations: int = DEFAULT_MAX_ITERATIONS
    deadline: Optional[datetime] = None
    created_at: datetime = field(default_factory=datetime.now)
    # Inv-5 clock: when the CURRENT state was entered (stamped at every state change). Deliberately
    # not persisted — a restart re-arms the clock from load time; finiteness still holds.
    state_entered_at: datetime = field(default_factory=datetime.now)
    # THE DEADLINE WAS THE ENGINE'S, NOT THE ISSUER'S. §2.5 lets an implementation write a default
    # into a packet the issuer left without one — "logged as supplied" — and that is what the flag
    # is for: a default is a bound, not a CLAIM about ordering, so CHECK-3 has nothing the issuer
    # stated to compare when one side carries one (two siblings created a moment apart would
    # otherwise be reported as a Dep violation manufactured by the clock).
    deadline_supplied: bool = False
    # THE CLAIM AS IT WAS AUTHORED, kept beside the claim as it stands. Set once, at the first
    # ASSIGN, and never touched by a revision — so "what did this node promise before anyone
    # worked on it" is a fact on the node rather than an archaeology exercise over the log. The
    # author asked for exactly this and it was not built: a claim narrows most cheaply through its
    # risk register, and with nothing to compare against, the narrowing is invisible until someone
    # reads the whole trace by hand (measured on `c_compiler`, 2026-09-20/21 — the register grew
    # from seven entries to nine after the work began and every surface said the claim stood).
    authored: Optional[Spec] = None
    # THE SPLIT'S REGISTER, its decomposer's (§9.2) — None until a split is admitted with one (`register_of`).
    register: Optional[Register] = None
    done_reason: Optional[DoneReason] = None
    autonomy: AutonomyLevel = AutonomyLevel.MANUAL
    was_challenged: bool = False
    was_reassigned: bool = False
    false_positive: bool = False  # V=pass but later found wrong (q_V)
    # R′ (§12.14): ONE sign-agnostic per-node counter next to max_iterations — counts EVERY
    # quasi-terminal exit (DONE→OFFERED and ABANDONED→OFFERED alike); exhaustion = finality (Inv-5).
    reopens: int = 0
    max_reopens: int = 1
    # Set when a DONE(pass/auto) node is reopened under the SAME criteria: if the fresh run then
    # FAILs, the old pass is refuted — exactly q_V's pass→later-fail member (§12.14/§15.4), no new machinery.
    reopened_from_pass: bool = False
    # Contract generation: bumped by every revision (re-ASSIGN under the same id, Inv-1). Neither
    # `iteration` (the rework loop) nor `reopens` (R′) moves on a revision, so this is what tells a
    # verdict about the delivery that stood BEFORE the contract changed from one about the current
    # contract — §12.4 admits a re-ASSIGN from VALIDATING, and §12.10 voids the pending delivery with it.
    revisions: int = 0
    # §15.4 causal typing of revisions. spec_defect_criteria_change = the q_T member («criteria
    # изменены по дефекту спеки»); reassign_* refine q_Del: when a Del change carried a typed
    # reason, only CAPABILITY_MISMATCH counts (untyped keeps the documented over-approximation).
    spec_defect_criteria_change: bool = False
    reassign_reason_typed: bool = False
    reassign_capability_mismatch: bool = False
    criterion_mappings: tuple[CriterionMapping, ...] = ()
    verified: bool = False  # L2 dirty flag: stored critique is fresh for current decomposition

    def label(self, chars: int = LABEL_CHARS) -> str:
        """The node as a reader names it: its name, else the head of its description."""
        return self.spec.name or self.spec.description[:chars]


@dataclass(frozen=True)
class GuardContext:
    iteration: int
    max_iterations: int
    # R′ finality-gate inputs (§12.14), computed by the graph at the chokepoint and read by the pure
    # FSM guard. `consumed` defaults True = FAIL-CLOSED: no reopen unless the graph explicitly
    # established the terminal is locally reversible (не потреблён). Meaningful only on DONE/ABANDONED.
    reopens: int = 0
    max_reopens: int = 1
    consumed: bool = True
    # Has the executor ACCEPTed the CURRENT packet version? Read off the log, where consent is
    # recorded (`consented_on_current_version`); decides where REJECT_CHALLENGE returns the node.
    # False by default = nothing inferred that the log does not carry.
    consented: bool = False


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
    deadline_supplied: bool = False                # ASSIGN at creation: the deadline is the implementation's default (§2.5)
    # ASSIGN: the rework bound. On the FIRST assign it is the node's budget; on a REVISION
    # `None` means keep the one the node has, like `deadline` and `assignee` beside it.
    # None = the signal names no budget: a first ASSIGN takes the default, a re-install KEEPS the one in force (§12.3 —
    # a packet field only the issuer's act changes; defaulted, every ACCEPT_CHALLENGE reset it to 12, A-F5)
    max_iterations: Optional[int] = None
    covers: tuple[str, ...] = ()                   # ASSIGN: parent criteria this child is mapped to (§2)
    reason: Optional[str] = None                   # CHALLENGE, BLOCK, CANCEL
    in_flight: Optional[str] = None                # CONFIRM_CANCEL: executor's in-flight state at cancellation (Thm 11, §12.6)
    blocker_task_id: Optional[TaskId] = None       # BLOCK: the undeclared prerequisite NODE (→ provisional discovered-Dep,
                                                   # §11.3); RESOLVE_BLOCK: the corrected source on mis-attribution
    blocker_task_ids: tuple[TaskId, ...] = ()      # BLOCK: ALL undeclared prerequisite nodes — one BLOCK may surface
                                                   # several (§11.3: an edge per surfaced prerequisite); RESOLVE_BLOCK:
                                                   # the corrected FULL set (SET semantics — unlisted provisionals retract)
    external: bool = False                         # RESOLVE_BLOCK: blocker was non-producible (no producer node) →
                                                   # retract the provisional edge; the FM-5 currency line, not a Dep (§11.3)
    result: Optional[str] = None                   # DELIVER
    self_validation: Optional[Verdict] = None      # DELIVER
    new_spec: Optional[Spec] = None                # ACCEPT_CHALLENGE
    # ACCEPT_CHALLENGE: the issuer's ruling — ids of the validator's findings the executor's CHALLENGE named that this
    # acceptance holds outside their criterion as written (`engine.findings`); part of the act, never a second step
    retire_findings: tuple[str, ...] = ()
    justification: Optional[str] = None            # REJECT_CHALLENGE
    failed_criteria: tuple[str, ...] = ()          # FAIL
    action: Optional[str] = None                   # RESOLVE_BLOCK
    revision_reason: Optional[RevisionReason] = None  # re-ASSIGN: causal type of the revision (§15.4)
    # WHICH VISIT OF WHICH STATE a TIMEOUT bounds — (state, entered_at), set by the monitor.
    # "A timeout bounds one visit of one state" (§12.2): between the tick that measured the wait and
    # the step that runs the trigger the node can leave and re-enter, and the trigger must not act on
    # a visit it never measured — in particular not on a fresh OFFERED entered by a new packet
    # version, whose deadline is its own (§12.3).
    visit: Optional[tuple] = None

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
    §15.6 records the timeout close apart from a pass precisely because it is not one — so that is the
    other predicate, below, and a caller picks which question it is asking.
    """
    return task is not None and task.state is State.DONE and task.done_reason is DoneReason.PASS


def settled_positive(task: "Task | None") -> bool:
    """DONE and not refused — an earned PASS *or* the timeout's auto_pass (§15.6, Ch. 16).

    For populations where the canon counts a node that completed without a refusal, however it got
    there. Anything that must not accept a verdict nobody gave uses `passed` instead.
    """
    return (task is not None and task.state is State.DONE
            and task.done_reason in (DoneReason.PASS, DoneReason.AUTO_PASS))


def register_of(task: Task) -> Register:
    """The register of `task`'s split — its decomposer's, admitted with it (§9.2, §11.5); empty until he admits one. The
    packet's pre-filled ACCEPTED_RISKS is never read as it: "a register carried in the task's own fields, a pre-filled
    one, is task data, not the split's register" (critic r4 over A-F6: the fallback let the issuer write, and change,
    the battery's verdict on the decomposer's split)."""
    return task.register if task.register is not None else Register()


def set_aside_of(task: Task) -> tuple[AcceptedRiskItem, ...]:
    """What a reader of `task`'s claim is told was set aside: its packet's pre-fill — its issuer's word, a field of the
    packet the executor receives (§10.1) — and its split's register, its decomposer's (§9.2); neither one's denial by S.
    CHECK-4/5 read the register alone (`register_of`); a packet a party works or validates by carries both (critic r5:
    read off the register only, an issuer's pre-fill on a leaf reached no executor and no validator)."""
    seen, out = set(), []
    for n in task.spec.set_aside + register_of(task).set_aside:
        if n.item not in seen:
            seen.add(n.item)
            out.append(n)
    return tuple(out)
