"""CHECK-7 and CHECK-8 — the NUMERIC-BOUND arithmetic tier of the L1 formal checks.

Capability honesty (the embedder's contract): what this tier cannot machine-check is reported
`skipped` with the missing capability NAMED — never silently green. Checked here: parseable
numeric bounds (`metric < 200`-style; sums vs the parent bound, upper/lower contradictions).
Beyond this tier: arbitrary-formula entailment/consistency is a DECLARED extension point
(SMT — the `gfso-core[solver]` extra); its absence degrades to a visible skip, and the
semantic (causal) half of sufficiency is L2 by design (§13.4), never this check's claim.
(A vestigial `import z3` flag that no code read was removed — the module never called Z3;
claiming otherwise in the header was exactly the silent-degradation this contract forbids.)
"""
from __future__ import annotations

import re
from gfso.core.types import Task, CheckResult


def _parse_numeric_bound(desc: str) -> tuple[str, str, float] | None:
    """Try to parse 'metric < 200ms' or 'metric > 80%' style criteria.

    The number must actually BE a number. `[\\d.]+` also matches a run of dots, and a criterion
    describing markdown ("`> ...` renders as a blockquote") then reached `float('...')` and threw —
    taking the whole decomposition down with a 422 instead of degrading to a skip. A tier that
    cannot machine-check something reports it, never crashes on it (this module's own contract).
    """
    m = re.match(r'(.+?)\s*([<>]=?)\s*(\d+(?:\.\d+)?)', desc.strip())
    if m:
        return m.group(1).strip(), m.group(2), float(m.group(3))
    return None


def _weigh_the_numeric_bounds(task, child_by_id) -> tuple[list, int, int]:
    """The numeric tier of CHECK-7: sum the mapped children's bounds against the parent's.

    Returns (violations, how many were actually verified, how many this tier cannot reach).
    The counts are returned rather than accumulated in the caller because "beyond this tier"
    is a capability statement about the CHECK, and it is what keeps a skipped criterion from
    reading as a green one.
    """
    violations: list = []
    checked = 0
    beyond_tier = 0
    for parent_crit in task.spec.criteria:
        parent_bound = _parse_numeric_bound(parent_crit.description)
        if not parent_bound:
            beyond_tier += 1
            continue

        p_metric, p_op, p_val = parent_bound

        mapped_children = [
            m.child_id for m in task.criterion_mappings
            if m.criterion_name == parent_crit.name
        ]

        # NOTHING TO SUM IS NOT A SUM OF ZERO. With no child mapped to this criterion the loop below
        # adds nothing, and `0.0 < 2.0` was then reported as "children sum 0.0 < parent bound 2.0" —
        # an arithmetic false positive on a criterion nobody had covered yet, which is CHECK-1's
        # finding and stated correctly there. An ordinary user met it on their first plan ("output
        # contains only content-equivalence classes of size >= 2") and reworded a perfectly good
        # criterion to get around it (wave 25, 2026-09-05). ⊥ is not zero — the same rule this
        # codebase applies to every metric it publishes, applied to the check that publishes one.
        if not mapped_children:
            beyond_tier += 1
            continue

        child_sum = 0.0
        # THE CHILDREN'S STRICTNESS IS PART OF WHAT THEY ENTAIL, not decoration on the number.
        # `m < c` for at least one child makes the sum STRICTLY below Σc; all-non-strict children
        # only give `m ≤ Σc`. §13.4 annotates its own worked example with exactly this — "the bound
        # 100 + 100 ≤ 200 with both child bounds STRICT; the non-strict test alone would not entail
        # the strict parent criterion" — and the tier used to read the value and drop the operator,
        # so `<= 100` twice under a parent `< 200` was reported as a verified bound. A false green
        # on the Semantic level is the one thing this tier exists to prevent.
        strict_sum = False
        parseable = True
        for cid in mapped_children:
            child = child_by_id.get(cid)
            if not child:
                continue
            for cc in child.spec.criteria:
                cb = _parse_numeric_bound(cc.description)
                if cb and cb[0].strip() == p_metric.strip():
                    child_sum += cb[2]
                    strict_sum = strict_sum or "=" not in cb[1]
                    break
            else:
                parseable = False

        if not parseable:
            beyond_tier += 1
            continue

        checked += 1
        # Reached: `m < Σc` when some child is strict, `m ≤ Σc` otherwise. At Σc = P that entails a
        # strict parent bound only in the first case; below P, and for a non-strict parent, either
        # case does.
        beyond = child_sum > p_val if "<" in p_op else child_sum < p_val
        at_the_bound = child_sum == p_val and not (strict_sum or "=" in p_op)
        if beyond or at_the_bound:
            violations.append(f"{p_metric}: children sum {child_sum} does not entail {p_op} {p_val}"
                              + ("" if beyond else " (no child bound is strict)"))
    return violations, checked, beyond_tier


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
    violations, checked, beyond_tier = _weigh_the_numeric_bounds(task, child_by_id)

    if violations:
        return CheckResult("CHECK-7:sufficiency", False, "; ".join(violations))
    if checked == 0:
        return CheckResult("CHECK-7:sufficiency", True,
                           f"skipped: no criteria machine-checkable at the numeric-bound tier "
                           f"({beyond_tier} beyond it — formula entailment needs the solver "
                           f"capability; causal sufficiency is L2)", skipped=True)
    detail = f"verified {checked} numeric bound(s)"
    if beyond_tier:
        detail += f"; {beyond_tier} criteria beyond this tier (formula/causal — solver capability / L2)"
    return CheckResult("CHECK-7:sufficiency", True, detail)


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
        uppers = [(v, op, cid) for op, v, cid in entries if "<" in op]
        lowers = [(v, op, cid) for op, v, cid in entries if ">" in op]
        for uv, uop, uid in uppers:
            for lv, lop, lid in lowers:
                # AT EQUAL BOUNDS THE OPERATORS DECIDE, and dropping them invented a conflict:
                # `x <= 5` and `x >= 5` are jointly satisfied by x = 5, and CHECK-8 reported them
                # as an FM-2 contradiction — the check whose whole purpose is to find real ones.
                # Unsatisfiable iff the window is empty: the upper below the lower, or the two
                # meeting at a point that at least one of them excludes.
                if uv < lv or (uv == lv and ("=" not in uop or "=" not in lop)):
                    contradictions.append(
                        f"{metric}: {uid} requires {uop}{uv} but {lid} requires {lop}{lv}")

    if contradictions:
        return CheckResult("CHECK-8:consistency", False, "; ".join(contradictions))
    if not bounds:
        return CheckResult("CHECK-8:consistency", True,
                           "skipped: no numeric bounds to cross-check (formula-level consistency "
                           "needs the solver capability)", skipped=True)
    return CheckResult("CHECK-8:consistency", True,
                       f"cross-checked numeric bounds on {len(bounds)} metric(s)")


def run_constraints(task: Task, children: list[Task]) -> list[CheckResult]:
    """The Semantic tier (CHECK-7/8) over one node: formal sufficiency and mutual satisfiability."""
    return [
        check_sufficiency(task, children),
        check_consistency(children),
    ]
