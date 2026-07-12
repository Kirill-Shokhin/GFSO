"""Protocol invariants. Pure validation functions.

NB Invariant 1 (criteria immutability) has NO named function here BY DESIGN: it is enforced
structurally — every in-place criteria change on a SET_STATE raises InvariantViolation at the
mutation chokepoint (core/graph/mutations.py::_set_state), and the only sanctioned change paths
are revision (re-ASSIGN, §6.4 Inv-1) and the pre-acceptance CHALLENGE channel (APPLY_SPEC).
A `validate_criteria_immutable` helper used to live here, defined but never called — dead code
that read as protection; removed (visibility ≠ enforcement)."""
from __future__ import annotations

from gfso.core.types import SignalData, Signal


def validate_fail_has_criteria(signal_data: SignalData) -> bool:
    """Invariant 3: FAIL must specify failed criteria."""
    if signal_data.signal != Signal.FAIL:
        return True
    return len(signal_data.failed_criteria) > 0
