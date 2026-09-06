"""CHECK-1 through CHECK-6. Pure functions on types. O(n)."""
from __future__ import annotations

import re

from gfso.core.types import Task, CheckResult, Predictability, DepEdge


# The canon's own CHECK → failure-mode routing (§13.4's battery, corroborated by §13.6's table).
# ONE table, in the product, read by everything that displays it — the UI used to carry its own copy
# in JavaScript, which drifted: it credited CHECK-6 to FM-1 where §13.4 routes leaf delegation to
# FM-7, and knew nothing of CHECK-1b/7/8. `tests/test_canon_check_map.py` parses the battery out of
# the canon and compares both directions, the same way the FSM table is guarded.
# CHECK-1c (anti-mock) is deliberately absent: it is an engineering addition with no canon row.
CHECK_TO_FM: dict[str, str] = {
    "CHECK-1:coverage":       "FM-1.a",
    "CHECK-1b:no_orphan":     "FM-1.e",
    "CHECK-2:dag":            "FM-4",
    "CHECK-3:deadlines":      "FM-5",
    "CHECK-4:accepted_risks": "FM-1",
    "CHECK-5:risk_nodes":     "FM-1",
    "CHECK-6:delegation":     "FM-7",
    "CHECK-7:sufficiency":    "FM-1",
    "CHECK-8:consistency":    "FM-2",
}

FM_LABEL: dict[str, str] = {
    "FM-1": "Correspondence", "FM-2": "Consistency", "FM-3": "Veracity", "FM-4": "Propagation",
    "FM-5": "Freshness", "FM-6": "Feasibility", "FM-7": "Feedback",
}


def _mentions(text: str, name: str) -> bool:
    """Does `text` name the criterion `name` as a token? Word-boundary exact match — a substring
    test would fire on any criterion whose name is a common word fragment."""
    if not text or not name.strip():
        return False
    return re.search(rf"(?<!\w){re.escape(name.strip())}(?!\w)", text) is not None


def check_anti_mock(children: list[Task], dep_edges: list[DepEdge]) -> CheckResult:
    """CHECK-1c (anti-mock): every sibling seam carries a glue truth-maker (§10/§2) → FM-1.

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
        # A DECOMPOSED node with no criteria of its own is not "covered", it is UNJUDGEABLE. By A1 a
        # task is a goal plus a decidable predicate, so an empty criteria set makes V(node) true
        # vacuously — the §26.3 shape of a check that passes because its population is empty.
        # Measured: a two-hour run built five well-specified children under a root carrying ZERO
        # criteria; coverage reported no holes (nothing to cover), the Level-2 gate reported
        # `semantic_covered: true` over `criteria_judged: 0`, every child passed, and the only thing
        # that caught it was the validator refusing to invent a criterion to judge the root by.
        if children:
            return CheckResult("CHECK-1:coverage", False,
                               "the node has children but no criteria of its own — nothing to "
                               "cover and nothing to validate it against (A1: a task is a goal "
                               "plus a decidable predicate)")
        return CheckResult("CHECK-1:coverage", True, "no criteria defined")

    if not children:
        return CheckResult("CHECK-1:coverage", True, "leaf task", skipped=True)

    if not task.criterion_mappings:
        return CheckResult("CHECK-1:coverage", False, "no criterion mappings declared")

    child_ids = {c.id for c in children}
    # …AND WHAT EACH OF THEM PROMISES. A mapping used to be checked on two things: the
    # criterion exists on the parent, the child exists. It never asked whether the covering
    # child DECIDES anything. A child with `criteria: []` therefore satisfied CHECK-1 for a
    # parent criterion, and — being a leaf — passed its own CHECK-1 as "no criteria defined",
    # so the whole plan read L0-clean while one conjunct of Thm 1's AND forbade nothing.
    # Probed end to end 2026-09-05 after an outside audit inferred the path: the child closed
    # DONE on its own self-report and satisfied its parent's AND. By A1 a task is a goal plus a
    # decidable predicate; a child that carries none secures nothing for anybody.
    _empty = {c.id for c in children if not c.spec.criteria}
    crit_names = {c.name for c in task.spec.criteria}
    mapped_criteria = set()
    invalid_mappings = []

    for m in task.criterion_mappings:
        if m.child_id not in child_ids:
            invalid_mappings.append(f"{m.criterion_name} -> {m.child_id} (child not found)")
        elif m.child_id in _empty:
            invalid_mappings.append(
                f"{m.criterion_name} -> {m.child_id} (that child has NO criteria of its own, so"
                f" it decides nothing: its pass would be vacuous and could not secure this"
                f" criterion — §10, A1. Give it criteria, or map this criterion elsewhere)")
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
    """CHECK-1b: non-redundancy — the second side of FM-1 (§12.1 C1, §10).

    Every child must address at least one parent criterion (via criterion_mappings).
    A child mapped to nothing is superfluous: it inflates the decomposition and
    breaks the non-redundancy half of correctness (Theorem 1 needs both sides).
    """
    if not children:
        return CheckResult("CHECK-1b:no_orphan", True, "leaf task", skipped=True)
    if not task.criterion_mappings:
        return CheckResult("CHECK-1b:no_orphan", True, "no mappings declared", skipped=True)

    mapped_children = {m.child_id for m in task.criterion_mappings}
    redundant = [c.id for c in children if c.id not in mapped_children]
    if redundant:
        return CheckResult(
            "CHECK-1b:no_orphan", False,
            f"children addressing no parent criterion: {', '.join(redundant)}",
        )
    return CheckResult("CHECK-1b:no_orphan", True)


def check_dag(children: list[Task], dep_edges: list[tuple[str, str]],
              task: Task | None = None) -> CheckResult:
    """CHECK-2: the graph of D is a DAG (§13.4 → FM-4), and Dep is acyclic (§10, which defines Dep as
    an acyclic relation and has no CHECK row of its own).

    The D clause is the canon's own row and used to be missing entirely: this check walked the *Dep*
    edges and reported "CHECK-2:dag" over them, so "a cycle → infinite recursion → an A1 violation"
    (§10) was verified nowhere. What is decidable from ONE split is a node that is its own child
    (a self-parent — reachable through the authoring door, measured) and a repeated child; a longer
    D cycle is not visible from a single node's split and is refused where the whole graph is —
    `Engine._assert_no_d_cycle`, at the ASSIGN that would close it.
    """
    if task is not None:
        seen: set[str] = set()
        for c in children:
            if str(c.id) == str(task.id):
                return CheckResult("CHECK-2:dag", False,
                                   f"cycle in the decomposition graph: {task.id} is its own child "
                                   f"(D must be a DAG — a cycle is infinite recursion, §10/§13.4)")
            if str(c.id) in seen:
                return CheckResult("CHECK-2:dag", False,
                                   f"cycle in the decomposition graph: {c.id} appears twice among "
                                   f"the children of {task.id}")
            seen.add(str(c.id))

    if not dep_edges:
        return CheckResult("CHECK-2:dag", True, "D acyclic; no dependency edges", vacuous=True)

    # Build adjacency and detect cycle via DFS
    adj: dict[str, list[str]] = {}
    for a, b in dep_edges:
        adj.setdefault(a, []).append(b)

    UNVISITED, IN_PROGRESS, DONE = 0, 1, 2
    status: dict[str, int] = {t.id: UNVISITED for t in children}
    stack: list[str] = []

    def find_cycle(node: str) -> list[str] | None:
        """One cycle in the dependency edges, as the path that closes it — or `None`.

    The PATH, not a boolean: CHECK-2 names which nodes make the loop, because "there is a cycle" is
    not something a caller can act on."""
        if node not in status:
            return None
        if status[node] == IN_PROGRESS:
            return stack[stack.index(node):] + [node]
        if status[node] == DONE:
            return None
        status[node] = IN_PROGRESS
        stack.append(node)
        for neighbor in adj.get(node, []):
            cycle = find_cycle(neighbor)
            if cycle is not None:
                return cycle
        stack.pop()
        status[node] = DONE
        return None

    for task in children:
        if status.get(task.id, DONE) == UNVISITED:
            cycle = find_cycle(task.id)
            if cycle is not None:
                # Name the cycle — an anonymous "cycle detected" leaves the repair (refine reads this
                # as a structural hole) without a locus; the named path IS the contradiction to fix
                # (e.g. a declared seam vs a BLOCK-discovered edge running the opposite way).
                return CheckResult("CHECK-2:dag", False,
                                   "cycle in dependency graph: " + " -> ".join(cycle))

    return CheckResult("CHECK-2:dag", True)


def check_deadlines(task: Task, children: list[Task], dep_edges: list[tuple[str, str]]) -> CheckResult:
    """CHECK-3: deadline coherence along Dep — the HORIZONTAL rule, which is the whole of the row.

    §10: for every dependency (a, b), deadline(a) < deadline(b).

    THE VERTICAL RULE IS NOT THIS CHECK, and used to be reported as though it were. §3.4 item (6)
    (every child's deadline < its parent's) is stated by the canon and given no CHECK of its own —
    `formal/README.md` #6 says so in as many words, and adds that "any prose that credits it to
    CHECK-3 is wrong about the canon". It rode inside this result anyway, tagged only in the details,
    and `_EXEC_GATING_CHECKS` matches on the NAME — so it acquired authority to refuse execution
    under a canon check's name, in the gate whose own comment keeps CHECK-1c out on the ground that
    "the gate is exactly the canon's level, in both directions" (audited 2026-09-05, F4).
    Now `check_vertical_deadlines` owns it, under its own name, outside the gate: the violation is
    SURFACED where the plan's checks are read, and refuses nothing — the same treatment CHECK-1c
    gets, for the same reason.
    """
    deadlines = {t.id: t.deadline for t in children}
    deadlines[task.id] = task.deadline

    violations = []
    for a, b in dep_edges:
        dl_a = deadlines.get(a)
        dl_b = deadlines.get(b)
        if dl_a is None or dl_b is None:
            continue
        if dl_a >= dl_b:
            violations.append(f"Dep {a}(deadline={dl_a}) >= {b}(deadline={dl_b})")

    if violations:
        return CheckResult("CHECK-3:deadlines", False, "; ".join(violations))
    if not dep_edges:
        return CheckResult("CHECK-3:deadlines", True, "no dependency edges", vacuous=True)
    return CheckResult("CHECK-3:deadlines", True)


def check_vertical_deadlines(task: Task, children: list[Task]) -> CheckResult:
    """§3.4(6): every child's deadline < its parent's — SURFACED, not gating.

    A child that may finish after its parent's own deadline cannot compose into it, so the plan
    promises what passage of time denies. The canon states the rule and gives it no CHECK
    (§26.5-bis, the un-operationalized form items), which is exactly why it is reported under its own
    name and is absent from `_EXEC_GATING_CHECKS`: a rule with no canon row does not acquire the
    authority to refuse execution by being written inside a result that has one.

    Its silence at zero is real silence. A deadline is a design decision and not a mandatory field
    (`formal/README.md` #6: absence stays silent), so a plan that declares none says nothing here.
    """
    violations = [f"child {c.id}(deadline={c.deadline}) >= parent {task.id}(deadline={task.deadline})"
                  for c in children
                  if c.deadline is not None and task.deadline is not None
                  and c.deadline >= task.deadline]
    if violations:
        return CheckResult("§3.4(6):vertical_deadlines", False, "; ".join(violations))
    if not any(c.deadline for c in children) or task.deadline is None:
        return CheckResult("§3.4(6):vertical_deadlines", True, "no child deadlines to place", vacuous=True)
    return CheckResult("§3.4(6):vertical_deadlines", True)


def check_accepted_risks(task: Task, children: list[Task]) -> CheckResult:
    """CHECK-4: for a DECOMPOSED node (D≠∅), the ACCEPTED_RISKS section exists, is non-empty, and its records
    are well-formed (record schema §13.1, predictability per factor §13.2).

    ACCEPTED_RISKS is authored per-decomposition by the node's own decomposer — a leaf (D=∅) has no
    decomposition, so its ACCEPTED_RISKS is vacuous and CHECK-4 does not gate it (nor a freshly created child;
    it is authored lazily when/if the child decomposes).

    Record FORM is what L0 can check mechanically (an incomplete record is not an ACCEPTED_RISKS record, §13.1):
    - a predictability verdict is present per factor (it doubles as the risk-vs-scope discriminator, §13.1:
      an entry with no estimable materialization P is a goal SCOPE boundary → goal criteria/CHECK-1);
    - a self-declared ORDINARY factor cannot sit in ACCEPTED_RISKS (internal contradiction of the record, §13.2);
    - a STATISTICAL factor carries its justification (§13.2).
    Whether the factor is REALLY that predictability class in the domain (S-regularity, FM-1.b vs §9)
    is a domain question — L2/validator territory, not decidable here."""
    if not children:
        return CheckResult("CHECK-4:accepted_risks", True,
                           "leaf (D=∅): ACCEPTED_RISKS is per-decomposition (§13.1)", skipped=True)
    if not task.spec.accepted_risks:
        return CheckResult("CHECK-4:accepted_risks", False, "ACCEPTED_RISKS section is empty")

    malformed = []
    for n in task.spec.accepted_risks:
        # A ACCEPTED_RISKS entry that names a criterion of THIS node is not a risk record — it is a
        # unilateral contract amendment (§13.1: the register holds risk FACTORS of the decomposition,
        # each with an estimable P; §10: the criteria ARE the obligation). Observed live (BCB/93):
        # "test_values criterion cannot pass — canonical test has design flaw" was authored as
        # EXTRAORDINARY, and the validator then excused the red criterion by it → false PASS. The
        # canon path for a criterion believed defective is CHALLENGE (spec defect, q_T) or the
        # issuer's revision — both logged, neither silent.
        named = [c.name for c in task.spec.criteria
                 if _mentions(n.item, c.name) or _mentions(n.justification, c.name)]
        if named:
            malformed.append(
                f"'{n.item}' names this node's own criterion ({', '.join(named)}) — a criterion is "
                f"the obligation, not an acceptable risk (§2.2/§5.1). If it is defective: CHALLENGE "
                f"it (spec defect) or have the issuer revise it; accepting it as a risk cannot retire it")
        elif n.predictability is None:
            malformed.append(
                # …and HOW to give it one. This said the record was incomplete and never named the
                # field: a person wrote "Predictable: yes", "unpredictable", "predictability:
                # predictable" into the item text and stayed red through all of them, because
                # `accepted_risks` also accepts bare strings and keeps them in a permanently failing
                # state (measured 2026-08-21, fifteen minutes of blind guessing). The excellent
                # explanation of the three categories lived on the other side of a key they had to
                # guess first.
                f"'{n.item}' has no predictability verdict (record incomplete, §13.1). Write the "
                f"entry as an OBJECT with the `predictability` key — {{'item': …, "
                f"'predictability': 'STATISTICAL'|'EXTRAORDINARY', 'justification': …}} — not as a "
                f"bare string: ORDINARY = occurs regularly in the domain, so it belongs in the "
                f"DECOMPOSITION and not here · STATISTICAL = P is estimable and the event "
                f"infrequent, admissible WITH a justification · EXTRAORDINARY = no precedent and "
                f"not derivable from known models. It is a burden-of-proof scale, not high/medium/"
                f"low. A capability the goal deliberately EXCLUDES has no P at all — that is "
                f"`scope`, not a risk")
        elif n.predictability == Predictability.ORDINARY:
            malformed.append(f"'{n.item}' is declared ORDINARY — must be in the decomposition, not accepted_risks")
        elif n.predictability == Predictability.STATISTICAL and not n.justification.strip():
            malformed.append(f"'{n.item}' is STATISTICAL — accepting it as a risk requires a justification")
    if malformed:
        return CheckResult("CHECK-4:accepted_risks", False, "; ".join(malformed))
    return CheckResult("CHECK-4:accepted_risks", True)


def check_risk_nodes(task: Task, children: list[Task]) -> CheckResult:
    """CHECK-5: for each risk component (STD-3), a risk-node exists in children.

    Paper §13.3: risk components group correlated factors with a common root cause.
    Each component must have a corresponding child task addressing it.
    """
    if not task.spec.risk_components:
        return CheckResult("CHECK-5:risk_nodes", True, "no risk components defined", vacuous=True)

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


def check_delegation(children: list[Task], task: Task | None = None,
                     non_leaf_ids: set[str] | None = None) -> CheckResult:
    """CHECK-6: "∀ leaf t: Del(t) ≠ ∅" (§13.4 → FM-7).

    The quantifier is over LEAVES, and it used to be read over every child: a decomposed child was
    demanded an executor it does not need (its work is its own children's — §10 Del is per node, and
    a node that delegates further is accountable through them), while the node the canon does name
    went unchecked when it was a leaf with no parent to run the check for it. Both directions are
    fixed: leaves among the children (`non_leaf_ids` tells which children decompose further; without
    it the caller cannot distinguish, so every child is treated as a leaf — the conservative read),
    and the node ITSELF when it has no split at all, which is the case §13.4 states literally."""
    non_leaf = non_leaf_ids or set()
    if not children:
        if task is not None and task.assignee is None:
            return CheckResult("CHECK-6:delegation", False,
                               f"leaf without an executor: {task.id} (FM-7 — no one to report to)")
        return CheckResult("CHECK-6:delegation", True)
    unassigned = [t.id for t in children if t.assignee is None and str(t.id) not in non_leaf]
    if unassigned:
        return CheckResult(
            "CHECK-6:delegation", False,
            f"unassigned leaves: {', '.join(unassigned)}",
        )
    return CheckResult("CHECK-6:delegation", True)


def run_structural(task: Task, children: list[Task], dep_edges: list[tuple[str, str]] | None = None,
                   non_leaf_ids: set[str] | None = None) -> list[CheckResult]:
    """Run all structural checks (CHECK-1 through CHECK-6)."""
    edges = dep_edges or []
    return [
        check_coverage(task, children),
        check_non_redundancy(task, children),
        check_dag(children, edges, task),
        check_deadlines(task, children, edges),
        check_vertical_deadlines(task, children),
        check_accepted_risks(task, children),
        check_risk_nodes(task, children),
        check_delegation(children, task, non_leaf_ids),
    ]
