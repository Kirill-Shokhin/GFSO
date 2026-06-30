"""CHECK-1 through CHECK-6. Pure functions on types. O(n)."""
from __future__ import annotations

from gfso.core.types import Task, CheckResult, Predictability, DepEdge


def check_anti_mock(children: list[Task], dep_edges: list[DepEdge]) -> CheckResult:
    """CHECK-1c (anti-mock): every sibling seam carries a glue truth-maker (§2.2/§18.10) → FM-1.

    A declared Dep edge with empty glue is the forgotten-glue hole: the edge says two
    parts couple but nothing states what must match / what breaks. (Glue *quality* —
    whether it is mockable — is L2's job; this only checks glue is present.)
    """
    child_ids = {c.id for c in children}
    seams = [e for e in dep_edges if e.from_id in child_ids and e.to_id in child_ids]
    if not seams:
        return CheckResult("CHECK-1c:anti_mock", True, "no sibling seams", skipped=True)
    glueless = [f"{e.from_id}->{e.to_id}" for e in seams if not e.glue.strip()]
    if glueless:
        return CheckResult(
            "CHECK-1c:anti_mock", False,
            f"seams with no glue truth-maker: {', '.join(glueless)}",
        )
    return CheckResult("CHECK-1c:anti_mock", True)


def check_coverage(task: Task, children: list[Task]) -> CheckResult:
    """CHECK-1: every criterion of parent is addressed by at least one child.

    Uses explicit CriterionMapping from task.criterion_mappings.
    Each mapping declares: criterion X is addressed by child Y.
    CHECK-1 verifies: (a) every criterion has a mapping, (b) mapped child exists.
    """
    if not task.spec.criteria:
        return CheckResult("CHECK-1:coverage", True, "no criteria defined")

    if not children:
        return CheckResult("CHECK-1:coverage", True, "leaf task", skipped=True)

    if not task.criterion_mappings:
        return CheckResult("CHECK-1:coverage", False, "no criterion mappings declared")

    child_ids = {c.id for c in children}
    crit_names = {c.name for c in task.spec.criteria}
    mapped_criteria = set()
    invalid_mappings = []

    for m in task.criterion_mappings:
        if m.child_id not in child_ids:
            invalid_mappings.append(f"{m.criterion_name} -> {m.child_id} (child not found)")
        elif m.criterion_name not in crit_names:
            # dangling after a criteria re-author: the mapped parent criterion no longer exists (surface-don't-
            # destroy — a revise that removed a covered criterion strands this mapping; the agent must re-map)
            invalid_mappings.append(f"{m.criterion_name} -> {m.child_id} (no such parent criterion)")
        else:
            mapped_criteria.add(m.criterion_name)

    if invalid_mappings:
        return CheckResult(
            "CHECK-1:coverage", False,
            f"invalid mappings: {'; '.join(invalid_mappings)}",
        )

    uncovered = [c.name for c in task.spec.criteria if c.name not in mapped_criteria]
    if uncovered:
        return CheckResult(
            "CHECK-1:coverage", False,
            f"uncovered criteria: {', '.join(uncovered)}",
        )
    return CheckResult("CHECK-1:coverage", True)


def check_non_redundancy(task: Task, children: list[Task]) -> CheckResult:
    """CHECK-1b: non-redundancy — the second side of FM-1 (§4.1 C1, §2.2.2).

    Every child must address at least one parent criterion (via criterion_mappings).
    A child mapped to nothing is superfluous: it inflates the decomposition and
    breaks the non-redundancy half of correctness (Theorem 1 needs both sides).
    """
    if not children:
        return CheckResult("CHECK-1b:non_redundancy", True, "leaf task", skipped=True)
    if not task.criterion_mappings:
        return CheckResult("CHECK-1b:non_redundancy", True, "no mappings declared", skipped=True)

    mapped_children = {m.child_id for m in task.criterion_mappings}
    redundant = [c.id for c in children if c.id not in mapped_children]
    if redundant:
        return CheckResult(
            "CHECK-1b:non_redundancy", False,
            f"children addressing no parent criterion: {', '.join(redundant)}",
        )
    return CheckResult("CHECK-1b:non_redundancy", True)


def check_predictability(task: Task) -> CheckResult:
    """CHECK-STD2: predictability admissibility of NEGLECTED items (§5.2) → FM-1.b.

    Enforced only on classified items (predictability set). Burden of proof:
    - ORDINARY      → may NOT be neglected (must be in the decomposition).
    - STATISTICAL   → neglectable only WITH a justification.
    - EXTRAORDINARY → admissibly neglected.
    Unclassified items (predictability=None) leave STD-2 silent.
    """
    classified = [n for n in task.spec.neglected if n.predictability is not None]
    if not classified:
        return CheckResult("CHECK-STD2:predictability", True, "no classified NEGLECTED items", skipped=True)

    violations = []
    for n in classified:
        if n.predictability == Predictability.ORDINARY:
            violations.append(f"'{n.item}' is ORDINARY — must be in the decomposition, not neglected")
        elif n.predictability == Predictability.STATISTICAL and not n.justification.strip():
            violations.append(f"'{n.item}' is STATISTICAL — neglect requires a justification")

    if violations:
        return CheckResult("CHECK-STD2:predictability", False, "; ".join(violations))
    return CheckResult("CHECK-STD2:predictability", True)


def check_dag(children: list[Task], dep_edges: list[tuple[str, str]]) -> CheckResult:
    """CHECK-2: decomposition graph is a DAG (no cycles)."""
    if not dep_edges:
        return CheckResult("CHECK-2:dag", True, "no dependency edges")

    # Build adjacency and detect cycle via DFS
    adj: dict[str, list[str]] = {}
    for a, b in dep_edges:
        adj.setdefault(a, []).append(b)

    UNVISITED, IN_PROGRESS, DONE = 0, 1, 2
    status: dict[str, int] = {t.id: UNVISITED for t in children}

    def has_cycle(node: str) -> bool:
        if node not in status:
            return False
        if status[node] == IN_PROGRESS:
            return True
        if status[node] == DONE:
            return False
        status[node] = IN_PROGRESS
        for neighbor in adj.get(node, []):
            if has_cycle(neighbor):
                return True
        status[node] = DONE
        return False

    for task in children:
        if status.get(task.id, DONE) == UNVISITED:
            if has_cycle(task.id):
                return CheckResult("CHECK-2:dag", False, "cycle detected in dependency graph")

    return CheckResult("CHECK-2:dag", True)


def check_deadlines(task: Task, children: list[Task], dep_edges: list[tuple[str, str]]) -> CheckResult:
    """CHECK-3: for every dependency (a, b), deadline(a) < deadline(b)."""
    if not dep_edges:
        return CheckResult("CHECK-3:deadlines", True, "no dependency edges")

    deadlines = {t.id: t.deadline for t in children}
    deadlines[task.id] = task.deadline

    violations = []
    for a, b in dep_edges:
        dl_a = deadlines.get(a)
        dl_b = deadlines.get(b)
        if dl_a is None or dl_b is None:
            continue
        if dl_a >= dl_b:
            violations.append(f"{a}(deadline={dl_a}) >= {b}(deadline={dl_b})")

    if violations:
        return CheckResult("CHECK-3:deadlines", False, "; ".join(violations))
    return CheckResult("CHECK-3:deadlines", True)


def check_neglected(task: Task) -> CheckResult:
    """CHECK-4: NEGLECTED section exists and is non-empty."""
    if not task.spec.neglected:
        return CheckResult("CHECK-4:neglected", False, "NEGLECTED section is empty")
    return CheckResult("CHECK-4:neglected", True)


def check_risk_nodes(task: Task, children: list[Task]) -> CheckResult:
    """CHECK-5: for each risk component (STD-3), a risk-node exists in children.

    Paper §5.3: risk components group correlated factors with a common root cause.
    Each component must have a corresponding child task addressing it.
    """
    if not task.spec.risk_components:
        return CheckResult("CHECK-5:risk_nodes", True, "no risk components defined")

    if not children:
        return CheckResult("CHECK-5:risk_nodes", False,
                           f"no children to cover {len(task.spec.risk_components)} risk components")

    child_descs = {c.id: c.spec.description.lower() for c in children}
    uncovered = []
    for component in task.spec.risk_components:
        covered = any(component.lower() in desc for desc in child_descs.values())
        if not covered:
            uncovered.append(component)

    if uncovered:
        return CheckResult("CHECK-5:risk_nodes", False,
                           f"uncovered risk components: {', '.join(uncovered)}")
    return CheckResult("CHECK-5:risk_nodes", True)


def check_delegation(children: list[Task]) -> CheckResult:
    """CHECK-6: every leaf task has an assignee."""
    unassigned = [t.id for t in children if t.assignee is None]
    if unassigned:
        return CheckResult(
            "CHECK-6:delegation", False,
            f"unassigned tasks: {', '.join(unassigned)}",
        )
    return CheckResult("CHECK-6:delegation", True)


def run_structural(task: Task, children: list[Task], dep_edges: list[tuple[str, str]] | None = None) -> list[CheckResult]:
    """Run all structural checks (CHECK-1 through CHECK-6)."""
    edges = dep_edges or []
    return [
        check_coverage(task, children),
        check_non_redundancy(task, children),
        check_dag(children, edges),
        check_deadlines(task, children, edges),
        check_neglected(task),
        check_predictability(task),
        check_risk_nodes(task, children),
        check_delegation(children),
    ]
