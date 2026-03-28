"""CHECK-1 through CHECK-6. Pure functions on types. O(n)."""
from __future__ import annotations

from gfso.core.types import Task, CheckResult, CriterionMapping


def check_coverage(task: Task, children: list[Task]) -> CheckResult:
    """CHECK-1: every criterion of parent is addressed by at least one child.

    Uses explicit CriterionMapping from task.criterion_mappings.
    Each mapping declares: criterion X is addressed by child Y.
    CHECK-1 verifies: (a) every criterion has a mapping, (b) mapped child exists.
    """
    if not task.spec.criteria:
        return CheckResult("CHECK-1:coverage", True, "no criteria defined")

    if not children:
        return CheckResult("CHECK-1:coverage", False, "no children to cover criteria")

    if not task.criterion_mappings:
        return CheckResult("CHECK-1:coverage", False, "no criterion mappings declared")

    child_ids = {c.id for c in children}
    mapped_criteria = set()
    invalid_mappings = []

    for m in task.criterion_mappings:
        if m.child_id not in child_ids:
            invalid_mappings.append(f"{m.criterion_name} -> {m.child_id} (child not found)")
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
        check_dag(children, edges),
        check_deadlines(task, children, edges),
        check_neglected(task),
        check_risk_nodes(task, children),
        check_delegation(children),
    ]
