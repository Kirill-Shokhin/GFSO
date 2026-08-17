from enum import Enum, auto


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


class Verdict(Enum):
    PASS = auto()
    FAIL = auto()


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
