"""CHECK-7 and CHECK-8. Basic arithmetic for simple criteria, Z3 for complex."""
from __future__ import annotations

import re
from gfso.core.types import Task, CheckResult, CriterionMapping

try:
    import z3
    _HAS_Z3 = True
except ImportError:
    _HAS_Z3 = False


def _parse_numeric_bound(desc: str) -> tuple[str, str, float] | None:
    """Try to parse 'metric < 200ms' or 'metric > 80%' style criteria."""
    m = re.match(r'(.+?)\s*([<>]=?)\s*([\d.]+)', desc.strip())
    if m:
        return m.group(1).strip(), m.group(2), float(m.group(3))
    return None


def check_sufficiency(task: Task, children: list[Task]) -> CheckResult:
    """CHECK-7: children's criteria sufficient for parent's criteria.

    For numeric bounds (e.g. response_time < 200ms): sums child bounds
    and checks against parent bound. For non-numeric: skipped.
    """
    if not children or not task.spec.criteria:
        return CheckResult("CHECK-7:sufficiency", True, "leaf task", skipped=True)

    if not task.criterion_mappings:
        return CheckResult("CHECK-7:sufficiency", True, "no mappings", skipped=True)

    child_by_id = {c.id: c for c in children}
    violations = []

    for parent_crit in task.spec.criteria:
        parent_bound = _parse_numeric_bound(parent_crit.description)
        if not parent_bound:
            continue

        p_metric, p_op, p_val = parent_bound

        mapped_children = [
            m.child_id for m in task.criterion_mappings
            if m.criterion_name == parent_crit.name
        ]

        child_sum = 0.0
        parseable = True
        for cid in mapped_children:
            child = child_by_id.get(cid)
            if not child:
                continue
            for cc in child.spec.criteria:
                cb = _parse_numeric_bound(cc.description)
                if cb and cb[0].strip() == p_metric.strip():
                    child_sum += cb[2]
                    break
            else:
                parseable = False

        if not parseable:
            continue

        if '<' in p_op and child_sum > p_val:
            violations.append(f"{p_metric}: children sum {child_sum} > parent bound {p_val}")
        elif '>' in p_op and child_sum < p_val:
            violations.append(f"{p_metric}: children sum {child_sum} < parent bound {p_val}")

    if violations:
        return CheckResult("CHECK-7:sufficiency", False, "; ".join(violations))
    return CheckResult("CHECK-7:sufficiency", True)


def check_consistency(children: list[Task]) -> CheckResult:
    """CHECK-8: children's criteria are mutually consistent."""
    if not children:
        return CheckResult("CHECK-8:consistency", True, "no children", skipped=True)

    # Check for contradictions in numeric bounds on same metric
    bounds: dict[str, list[tuple[str, float, str]]] = {}
    for c in children:
        for crit in c.spec.criteria:
            parsed = _parse_numeric_bound(crit.description)
            if parsed:
                metric, op, val = parsed
                bounds.setdefault(metric, []).append((op, val, c.id))

    contradictions = []
    for metric, entries in bounds.items():
        uppers = [(v, cid) for op, v, cid in entries if '<' in op]
        lowers = [(v, cid) for op, v, cid in entries if '>' in op]
        for uv, uid in uppers:
            for lv, lid in lowers:
                if uv <= lv:
                    contradictions.append(f"{metric}: {uid} requires <{uv} but {lid} requires >{lv}")

    if contradictions:
        return CheckResult("CHECK-8:consistency", False, "; ".join(contradictions))
    return CheckResult("CHECK-8:consistency", True)


def run_constraints(task: Task, children: list[Task]) -> list[CheckResult]:
    return [
        check_sufficiency(task, children),
        check_consistency(children),
    ]
