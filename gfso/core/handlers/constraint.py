"""CHECK-7 and CHECK-8 — the NUMERIC-BOUND arithmetic tier of the L1 formal checks.

Capability honesty (the embedder's contract): what this tier cannot machine-check is reported
`skipped` with the missing capability NAMED — never silently green. Checked here: parseable
numeric bounds (`metric < 200`-style; sums vs the parent bound, upper/lower contradictions).
Beyond this tier: arbitrary-formula entailment/consistency is a DECLARED extension point
(SMT — the `gfso-core[solver]` extra); its absence degrades to a visible skip, and the
semantic (causal) half of sufficiency is L2 by design (§9.1), never this check's claim.
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


#: THE COMPOSITION FUNCTIONS THIS TIER CAN EVALUATE — §9.6's fᵢ, as far as arithmetic reaches.
#: Anything else the issuer declares (a set union, a boolean substitution, prose) is a real
#: declaration this tier cannot check, and it is reported beyond-tier by NAME rather than
#: quietly summed.
_COMPOSITIONS = {"sum": sum, "max": max, "min": min}

#: What the criterion is checked under when its `composition` is blank. §9.9 puts the Semantic
#: level *where a composition function is declared*, and the engine has always checked everywhere —
#: with summation wired in as if it were the only one. It stays the fallback, because a tier that
#: went silent on every undeclared criterion would be a tier that never fires (nothing declares one
#: yet), but it is now SAID: a breach found under an assumed composition names the assumption, so a
#: parallel fan-out's author can see that the arithmetic, not their plan, is what disagrees.
_ASSUMED = "sum"


def _compose(fn: str, bounds: list[tuple[str, float]], upper: bool) -> tuple[float, bool]:
    """The children's bounds under fᵢ: the composed bound, and whether it is STRICT.

    Strictness is not decoration (§9.6 states the example with "both child bounds STRICT"), and
    which children decide it depends on the function. Under `sum` every child contributes, so ONE
    strict term makes Σ strict. Under an extremum only the children AT the extremum decide, and the
    direction settles whether one of them is enough: for `max` under an upper bound the composed
    value is attained by any of them, so every one must be strict; for `max` under a lower bound one
    strict child already carries the maximum past it. `min` is the same argument mirrored.
    """
    values = [v for _, v in bounds]
    strict = [("=" not in op) for op, _ in bounds]
    if fn == "sum":
        return sum(values), any(strict)
    composed = _COMPOSITIONS[fn](values)
    at = [s for s, (_, v) in zip(strict, bounds) if v == composed]
    return composed, (all(at) if (fn == "max") == upper else any(at))


def _child_bounds(task, child_by_id, criterion_name: str, metric: str) -> list | None:
    """Each mapped child's own bound on `metric` — or None where this tier cannot read them all.

    None covers two different absences and both are beyond-tier, never a green and never a zero:
    a child that states no bound on the metric at all, and NO mapped child to read. Nothing to
    compose is not a composition over nothing: with no child mapped to the criterion the total
    came out 0.0 and `0.0 < 2.0` was reported as "children sum 0.0 < parent bound 2.0" — an
    arithmetic false positive on a criterion nobody had covered yet, which is CHECK-1's finding and
    stated correctly there. An ordinary user met it on their first plan ("output contains only
    content-equivalence classes of size >= 2") and reworded a perfectly good criterion to get around
    it (wave 25, 2026-09-05). ⊥ is not zero — the rule this codebase applies to every metric it
    publishes, applied to the check that publishes one.

    THE CHILDREN'S OPERATORS TRAVEL WITH THEIR NUMBERS: strictness is part of what they entail
    (§9.6's own example turns on it), and the tier used to read the value and drop the operator.
    """
    bounds: list[tuple[str, float]] = []
    for m in [m for m in task.criterion_mappings if m.criterion_name == criterion_name]:
        child = child_by_id.get(m.child_id)
        if not child:
            continue
        for cc in child.spec.criteria:
            cb = _parse_numeric_bound(cc.description)
            if cb and cb[0].strip() == metric:
                bounds.append((cb[1], cb[2]))
                break
        else:
            return None
    return bounds or None


def _weigh_the_numeric_bounds(task, child_by_id) -> tuple[list, int, int, list]:
    """The numeric tier of CHECK-7: the mapped children's bounds, composed under fᵢ, against the parent's.

    Returns (violations, how many were actually verified, how many this tier cannot reach, which
    criteria were checked under an ASSUMED composition). The counts are returned rather than
    accumulated in the caller because "beyond this tier" is a capability statement about the CHECK,
    and it is what keeps a skipped criterion from reading as a green one.
    """
    violations: list = []
    checked = 0
    beyond_tier = 0
    assumed: list = []
    for parent_crit in task.spec.criteria:
        parent_bound = _parse_numeric_bound(parent_crit.description)
        if not parent_bound:
            beyond_tier += 1
            continue

        p_metric, p_op, p_val = parent_bound

        # WHICH FUNCTION SECURES THIS CRITERION — the issuer's declaration (§10.1), not the tier's
        # habit. A declared composition this tier cannot evaluate is a fact about the CHECK's reach
        # and is reported as one; it is never downgraded to summation, which would be the check
        # answering a question nobody asked it.
        fn = (parent_crit.composition or "").strip().lower()
        if fn and fn not in _COMPOSITIONS:
            beyond_tier += 1
            continue
        if not fn:
            fn = _ASSUMED

        child_bounds = _child_bounds(task, child_by_id, parent_crit.name, p_metric.strip())
        if child_bounds is None:
            beyond_tier += 1
            continue

        checked += 1
        upper = "<" in p_op
        composed, strict = _compose(fn, child_bounds, upper)
        if not parent_crit.composition.strip():
            assumed.append(parent_crit.name)
        # Reached: `m < f(c)` when the children's operators make it strict, `m ≤ f(c)` otherwise. At
        # f(c) = P that entails a strict parent bound only in the first case; below P, and for a
        # non-strict parent, either case does.
        beyond = composed > p_val if upper else composed < p_val
        at_the_bound = composed == p_val and not (strict or "=" in p_op)
        if beyond or at_the_bound:
            violations.append(
                f"{p_metric}: children {fn} {composed} does not entail {p_op} {p_val}"
                + ("" if beyond else " (no child bound is strict)")
                + ("" if parent_crit.composition.strip() else
                   f" — checked under an ASSUMED {_ASSUMED}: this criterion declares no composition "
                   f"function (§2.4), so if the children secure it some other way (max for a "
                   f"parallel fan-out, min, …) say so with `composition` and the check will use it"))
    return violations, checked, beyond_tier, assumed


def check_sufficiency(task: Task, children: list[Task]) -> CheckResult:
    """CHECK-7: ⋀{criteria(tⱼ) mapped to cᵢ} ⊨ cᵢ, under the composition function cᵢ declares (§9.6).

    For numeric bounds (e.g. response_time < 200ms): composes the child bounds under fᵢ — `sum`,
    `max`, `min` — and checks the result against the parent's. A declared function outside that set
    is beyond this tier; an UNDECLARED one is checked under an assumed sum and the assumption is
    named in the answer. For non-numeric: skipped.
    """
    if not children or not task.spec.criteria:
        return CheckResult("CHECK-7:sufficiency", True, "leaf task", skipped=True)

    if not task.criterion_mappings:
        return CheckResult("CHECK-7:sufficiency", True, "no mappings", skipped=True)

    child_by_id = {c.id: c for c in children}
    violations, checked, beyond_tier, assumed = _weigh_the_numeric_bounds(task, child_by_id)

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
    # A GREEN THAT RESTS ON AN ASSUMPTION SAYS SO. The pass is only as good as the composition it
    # was computed under, and the tier's own choice of one is not the issuer's declaration (§10.1).
    if assumed:
        detail += (f"; {', '.join(assumed)} checked under an ASSUMED {_ASSUMED} (no composition "
                   f"function declared — `composition` on the criterion says which fᵢ secures it)")
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
