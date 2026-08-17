"""Signal validation: who can send what. From paper §14.2."""
from __future__ import annotations

from enum import Enum, auto

from gfso.core.types import Signal


class Role(Enum):
    ISSUER = auto()
    EXECUTOR = auto()
    SYSTEM = auto()


# Paper §14.2: two tables define sender roles
SIGNAL_ROLES: dict[Signal, Role] = {
    # Executor → Issuer
    Signal.ACCEPT: Role.EXECUTOR,
    Signal.CHALLENGE: Role.EXECUTOR,
    Signal.BLOCK: Role.EXECUTOR,
    Signal.DELIVER: Role.EXECUTOR,
    Signal.CONFIRM_CANCEL: Role.EXECUTOR,
    # Issuer → Executor
    Signal.ASSIGN: Role.ISSUER,
    Signal.ACCEPT_CHALLENGE: Role.ISSUER,
    Signal.REJECT_CHALLENGE: Role.ISSUER,
    Signal.PASS: Role.ISSUER,
    Signal.FAIL: Role.ISSUER,
    Signal.CANCEL: Role.ISSUER,
    Signal.RESOLVE_BLOCK: Role.ISSUER,
    # System (finiteness invariant)
    Signal.TIMEOUT: Role.SYSTEM,
}


# The P2P alphabet, DERIVED from the table above rather than typed a second time (a second list is a
# second truth that drifts): §14.2 counts twelve P2P signals, and the one non-P2P member is TIMEOUT —
# "not a P2P signal (no agent sends it) but a system mechanism enforcing finiteness" (Inv-5). Doors
# that take a signal NAME from an agent (MCP / HTTP / CLI — all bind gfso.tools) close on this set.
P2P_SIGNALS: tuple[Signal, ...] = tuple(s for s, r in SIGNAL_ROLES.items() if r is not Role.SYSTEM)


def required_role(signal: Signal) -> Role:
    """Which role is allowed to send this signal."""
    return SIGNAL_ROLES[signal]
