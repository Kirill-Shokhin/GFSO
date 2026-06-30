from enum import Enum, auto


class State(Enum):
    IDLE = auto()
    REVIEW = auto()
    CHALLENGED = auto()
    EXECUTING = auto()
    BLOCKED = auto()
    VALIDATING = auto()
    REWORK = auto()
    DONE = auto()
    TIMEOUT = auto()
    ESCALATED = auto()


TERMINAL_STATES = frozenset({State.DONE, State.ESCALATED})
NON_TERMINAL_STATES = frozenset(s for s in State if s not in TERMINAL_STATES)


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
    CANCELLED = auto()


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
