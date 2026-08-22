from enum import Enum, StrEnum, auto


class State(Enum):
    IDLE = auto()
    OFFERED = auto()
    CHALLENGED = auto()
    EXECUTING = auto()
    BLOCKED = auto()
    VALIDATING = auto()
    REWORKING = auto()
    CANCELLING = auto()   # cancellation handshake in flight (§14.3): CANCEL received, CONFIRM_CANCEL pending
    DONE = auto()
    ABANDONED = auto()    # terminal, V=⊥ — task abandoned (§14.3), distinct from DONE(pass/fail)
    OVERDUE = auto()
    ESCALATED = auto()


TERMINAL_STATES = frozenset({State.DONE, State.ESCALATED, State.ABANDONED})
NON_TERMINAL_STATES = frozenset(s for s in State if s not in TERMINAL_STATES)

# R′ (§14.3 "Финальность"): DONE and ABANDONED are QUASI-terminal — a named extension of the
# admissible set (Inv-6): re-ASSIGN (REOPEN) is admitted under a double gate (finality-gate of
# consumption + max_reopens). ESCALATED stays fully terminal (its resolution is outside the FSM).
QUASI_TERMINAL_STATES = frozenset({State.DONE, State.ABANDONED})

# States a live node can be re-ASSIGNed (revised) from — §14.4 Inv-1: revision = re-ASSIGN same id → OFFERED.
# OVERDUE accepts no progress signals (§14.3); CANCELLING's sole staffed exit is CONFIRM_CANCEL (§14.3).
REASSIGNABLE_STATES = frozenset({
    State.OFFERED, State.CHALLENGED, State.EXECUTING,
    State.BLOCKED, State.VALIDATING, State.REWORKING,
})


class Action(StrEnum):
    """What the frontier asks of whoever holds a node — the nine directives it can issue.

    A vocabulary, not a protocol alphabet: `Signal` is what the FSM accepts, this is what a step
    TELLS someone to do, and the two are different sizes on purpose (`review` and `revise` move no
    signal of their own; `execute` is work, not a transition). It lived as bare strings in three
    places that had to agree and did not: the frontier authored them, the dispatcher compared
    against four of them, and a third list in the tool surface named five.

    A `StrEnum`, so the wire form is unchanged down to the byte — the measurement arm dispatches on
    these exact strings and a new spelling would end its runs silently. Two members are therefore
    named for what the directive DOES rather than after their own value: `FIX` ("rework") and
    `CHECK_PLAN` ("review"). Those two words are retired STATE names in v4 (v3.9 spelled OFFERED and
    REWORKING that way), and an identifier carrying them re-creates the verb-against-state collision
    the naming guard exists to catch — it caught this one."""
    ACCEPT = "accept"
    EXECUTE = "execute"
    DELIVER = "deliver"
    FIX = "rework"
    REVISE = "revise"
    VALIDATE = "validate"
    CHECK_PLAN = "review"
    RESOLVE = "resolve"
    CONFIRM_CANCEL = "confirm_cancel"


# The three SUBSETS, named where the vocabulary is — and deliberately NOT collapsed into one. They
# answer different questions and the arm's own dispatch depends on the difference (run sheet, hard
# constraint on the action vocabulary): what an EXECUTOR is asked to do, what the dispatcher can
# spawn work for, and what a step means when it belongs to someone else.
EXECUTOR_ACTIONS = frozenset({Action.ACCEPT, Action.EXECUTE, Action.DELIVER, Action.FIX,
                              Action.CONFIRM_CANCEL})
SPAWNABLE_ACTIONS = frozenset({Action.ACCEPT, Action.EXECUTE, Action.FIX, Action.DELIVER})


class Signal(Enum):
    # Executor → Issuer
    ACCEPT = auto()
    CHALLENGE = auto()
    BLOCK = auto()
    DELIVER = auto()
    CONFIRM_CANCEL = auto()
    # Issuer → Executor
    ASSIGN = auto()
    ACCEPT_CHALLENGE = auto()
    REJECT_CHALLENGE = auto()
    PASS = auto()
    FAIL = auto()
    CANCEL = auto()
    RESOLVE_BLOCK = auto()
    # System (finiteness invariant)
    TIMEOUT = auto()


class DoneReason(Enum):
    PASS = auto()
    FAIL = auto()
    AUTO_PASS = auto()
    CANCELLED = auto()  # legacy only (pre-v3.7 DBs stored cancellation as DONE(cancelled)); new cancellations end in State.ABANDONED


class Verdict(StrEnum):
    """V's two values, §11.2 — the WORD, owned once.

    A `StrEnum`: the wire form is the same byte string every record, report and signal already
    carries ("PASS" / "FAIL"), so nothing serialized changes and a comparison against a stored
    verdict works unchanged. It was an `auto()` Enum, which is why eleven modules spelled the word
    themselves instead — and an `== Verdict.FAIL` against a stored record silently meant `== 2`."""

    PASS = "PASS"
    FAIL = "FAIL"


class CriticVerdict(StrEnum):
    """What the Level-2 checker says about ONE criterion of a plan (§13.4) — the word, owned once.

    Only `SUFFICIENT` closes a finding; both other values leave it open, and that asymmetry was
    written as `!= "sufficient"` in four modules — the checker, the gate, the frontier and the
    read surface — each of which would have had to be found and changed together. The values are
    the enum of the schema the model answers in, so nothing on the wire moves."""

    SUFFICIENT = "sufficient"
    INSUFFICIENT = "insufficient"
    UNCERTAIN = "uncertain"


class Stage(StrEnum):
    """The ROLE a paid call played, as the spend ledger records it — the word, owned once.

    Two sides of one accounting already disagreed about the same spend (`validate_result` against
    `validator`), and a stage nobody spelled at the recording site never appeared in the ledger at
    all — which is how the sufficiency check looked like it had never run. The values are the exact
    strings already in every database and every measurement script; a `StrEnum` changes no byte.
    Stages that repeat per round carry the round number appended (`audit-fix-1`)."""

    SEARCH = "search-1"
    AUDIT_FOLD = "audit-fold-1"
    AUDIT_FIX = "audit-fix"                # + "-<round>"
    SEARCH_REFINE = "search-refine"
    AUDIT_FOLD_REFINE = "audit-fold-refine"
    DECOMPOSER = "decomposer"
    EXECUTOR = "executor"
    # …named for what it does, like `Action.CHECK_PLAN`: the identifier may not carry a word
    # v4 retired (the naming guard catches it), while the VALUE is the byte string already
    # in every database and measurement script and must not move.
    L2_CHECK_PLAN = "l2_review"
    L2_CHECKER = "l2-checker"
    L2_ATOMICITY = "l2-atomicity"
    UNDECIDED_OBLIGATIONS = "undecided-obligations"
    VALIDATE_RESULT = "validate_result"
    VALIDATOR = "validator"


class RevisionReason(Enum):
    """Causal type of a revision (re-ASSIGN, §14.4 Inv-1) — §24.5: the causally-typed members of
    q_T («criteria изменены по дефекту спеки») and q_Del (re-ASSIGN(capability_mismatch)) require
    the revision reason typed in the packet. Optional: an untyped revision keeps each metric's
    documented bias (q_T under-approximates — counts challenges only; q_Del over-approximates —
    counts every Del change)."""
    SPEC_DEFECT = auto()          # criteria changed because the contract itself was defective → q_T member
    SCOPE_EXPANSION = auto()      # sanctioned goal re-ASSIGN with new criteria (§13.1/§21) — NOT a defect
    CAPABILITY_MISMATCH = auto()  # Del change because the executor could not do the work → q_Del member
    OTHER = auto()                # routine (load, handoff, restructure) — counted by neither metric


class FM(Enum):
    CORRESPONDENCE = auto()
    CONSISTENCY = auto()
    VERACITY = auto()
    PROPAGATION = auto()
    FRESHNESS = auto()
    FEASIBILITY = auto()
    FEEDBACK = auto()


class AutonomyLevel(Enum):
    MANUAL = auto()
    ASSISTED = auto()
    AUTONOMOUS = auto()


class Predictability(Enum):
    """STD-2 (§5.2): predictability class of an accepted-risk factor.

    ORDINARY      — regular in domain, P estimable → MUST be in decomposition (never acceptable as a risk).
    STATISTICAL   — P estimable but rare → acceptable as a risk only WITH justification.
    EXTRAORDINARY — no precedent AND not derivable from known models → acceptable as a risk.
    """
    ORDINARY = auto()
    STATISTICAL = auto()
    EXTRAORDINARY = auto()


class MutationType(Enum):
    CREATE_TASK = auto()
    SET_STATE = auto()
    APPLY_SPEC = auto()       # sanctioned spec revision via ACCEPT_CHALLENGE (§14.2/§14.6) — may change criteria
    INCREMENT_ITERATION = auto()
    STORE_CHECK_RESULTS = auto()
    STORE_RECOMMENDATION = auto()
    RECORD_DEP = auto()       # BLOCK named a prerequisite node → provisional discovered-Dep edge (§14.2/§15.2)
    ADJUDICATE_DEP = auto()   # RESOLVE_BLOCK adjudicates the provisional: confirm / re-attribute / retract (§14.2)
    REOPEN = auto()           # R′ (§14.3): gated re-ASSIGN out of a quasi-terminal — spends a reopen,
                              # drops the stale verdict (V=pass is re-earned in OFFERED, never carried forward)
