"""CHECK-7 and CHECK-8. Optional Z3/SMT. Graceful without it."""
from __future__ import annotations

from gfso.core.types import Task, CheckResult

try:
    import z3
    _HAS_Z3 = True
except ImportError:
    _HAS_Z3 = False


def check_sufficiency(task: Task, children: list[Task]) -> CheckResult:
    """CHECK-7: conjunction of children's criteria formally implies parent's criteria."""
    if not _HAS_Z3:
        return CheckResult("CHECK-7:sufficiency", True, skipped=True)

    # TODO: implement when Z3 available and criteria support formal expressions
    return CheckResult("CHECK-7:sufficiency", True, skipped=True)


def check_consistency(children: list[Task]) -> CheckResult:
    """CHECK-8: children's criteria are mutually consistent (no contradiction)."""
    if not _HAS_Z3:
        return CheckResult("CHECK-8:consistency", True, skipped=True)

    # TODO: implement when Z3 available
    return CheckResult("CHECK-8:consistency", True, skipped=True)


def run_constraints(task: Task, children: list[Task]) -> list[CheckResult]:
    """Run constraint checks (CHECK-7, CHECK-8)."""
    return [
        check_sufficiency(task, children),
        check_consistency(children),
    ]
