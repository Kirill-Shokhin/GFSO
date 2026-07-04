from enum import Enum, auto


class State(Enum):
    IDLE = auto()
    REVIEW = auto()
    CHALLENGED = auto()
    EXECUTING = auto()
    BLOCKED = auto()
    VALIDATING = auto()
    REWORK = auto()
    CANCELLING = auto()   # cancellation handshake in flight (§6.3): CANCEL received, CANCEL_ACK pending
    DONE = auto()
    CANCELLED = auto()    # terminal, V=⊥ — task abandoned (§6.3), distinct from DONE(pass/fail)
    TIMEOUT = auto()
    ESCALATED = auto()


TERMINAL_STATES = frozenset({State.DONE, State.ESCALATED, State.CANCELLED})
NON_TERMINAL_STATES = frozenset(s for s in State if s not in TERMINAL_STATES)

# States a live node can be re-ASSIGNed (revised) from — §6.4 Inv-1: revision = re-ASSIGN same id → REVIEW.
# TIMEOUT accepts no progress signals (§6.3); CANCELLING's sole staffed exit is CANCEL_ACK (§6.3).
REASSIGNABLE_STATES = frozenset({
    State.REVIEW, State.CHALLENGED, State.EXECUTING,
    State.BLOCKED, State.VALIDATING, State.REWORK,
})


class Signal(Enum):
    # Executor → Issuer
    ACCEPT = auto()
    CHALLENGE = auto()
    BLOCK = auto()
    DELIVER = auto()
    CANCEL_ACK = auto()
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
    AUTO = auto()
    CANCELLED = auto()  # legacy only (pre-v3.7 DBs stored cancellation as DONE(cancelled)); new cancellations end in State.CANCELLED


class Verdict(Enum):
    PASS = auto()
    FAIL = auto()


class FM(Enum):
    CORRESPONDENCE = auto()
    CONSISTENCY = auto()
    VERIFIABILITY = auto()
    PROPAGATION = auto()
    CURRENCY = auto()
    FEASIBILITY = auto()
    FEEDBACK = auto()


class AutonomyLevel(Enum):
    MANUAL = auto()
    ASSISTED = auto()
    AUTONOMOUS = auto()


class Predictability(Enum):
    """STD-2 (§5.2): predictability class of a neglected factor.

    ORDINARY      — regular in domain, P estimable → MUST be in decomposition (not neglectable).
    STATISTICAL   — P estimable but rare → neglectable only WITH justification.
    EXTRAORDINARY — no precedent AND not derivable from known models → neglectable.
    """
    ORDINARY = auto()
    STATISTICAL = auto()
    EXTRAORDINARY = auto()


class MutationType(Enum):
    CREATE_TASK = auto()
    SET_STATE = auto()
    APPLY_SPEC = auto()       # sanctioned spec revision via ACCEPT_CHALLENGE (§6.2/§6.6) — may change criteria
    INCREMENT_ITERATION = auto()
    STORE_CHECK_RESULTS = auto()
    STORE_RECOMMENDATION = auto()
    RECORD_DEP = auto()       # BLOCK named a prerequisite node → provisional discovered-Dep edge (§6.2/§7.2)
    ADJUDICATE_DEP = auto()   # RESOLVE_BLOCK adjudicates the provisional: confirm / re-attribute / retract (§6.2)
