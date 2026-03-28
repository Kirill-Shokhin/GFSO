"""Protocol invariants. Pure validation functions."""
from __future__ import annotations

from gfso.core.types import Task, SignalData, Signal


def validate_criteria_immutable(old_task: Task, new_task: Task) -> bool:
    """Invariant 1: criteria cannot change after ASSIGN."""
    return old_task.spec.criteria == new_task.spec.criteria


def validate_fail_has_criteria(signal_data: SignalData) -> bool:
    """Invariant 3: FAIL must specify failed criteria."""
    if signal_data.signal != Signal.FAIL:
        return True
    return len(signal_data.failed_criteria) > 0
