"""Signal validation: who can send what. From paper §6.2."""
from __future__ import annotations

from enum import Enum, auto

from gfso.core.types import Signal


class Role(Enum):
    ISSUER = auto()
    EXECUTOR = auto()
    SYSTEM = auto()


# Paper §6.2: two tables define sender roles
SIGNAL_ROLES: dict[Signal, Role] = {
    # Executor → Issuer
    Signal.ACCEPT: Role.EXECUTOR,
    Signal.CHALLENGE: Role.EXECUTOR,
    Signal.BLOCK: Role.EXECUTOR,
    Signal.DELIVER: Role.EXECUTOR,
    Signal.CANCEL_ACK: Role.EXECUTOR,
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


def required_role(signal: Signal) -> Role:
    """Which role is allowed to send this signal."""
    return SIGNAL_ROLES[signal]
