"""CHECK-1 through CHECK-6. Pure functions on types. O(n)."""
from __future__ import annotations

import re

from gfso.core.types import Task, CheckResult, Predictability, DepEdge, State, register_of
from gfso.core.protocol.procedure import (admission_defects, criterionless, degenerate_procedures, reads_an_unpinned_set,
                                          unread_inputs)


# The canon's own CHECK → failure-mode routing (§9.5's battery, corroborated by §9.10's table).
# ONE table, in the product, read by everything that displays it — the UI used to carry its own copy
# in JavaScript, which drifted: it credited CHECK-6 to FM-1, and knew nothing of CHECK-1b/7/8. `tests/test_canon_check_map.py` parses the battery out of
# the canon and compares both directions, the same way the FSM table is guarded.
# CHECK-1c (anti-mock) is deliberately absent, and v4.1 is why it stays that way rather than being
# a gap: §9.5 now names this exact guard — "an implementation may add guards that operationalize a
# form item the battery does not check (§20.10); they are not battery rows" — and gives the
# reason the canon cannot carry it as a tenth row (§2.7 states Dep in one direction only, §4.5 does
# not fix where the integration criterion lives, and a discovered edge arrives mid-execution with
# no criterion, where a failing Syntactic CHECK would read as "not admitted"). So it is an
# engineering guard WITH a canon warrant, not one without a row.
#: ONE check may guard several modes, so the value is the LIST §9.5 states, and the list may be EMPTY.
#: CHECK-2 guards one mode by one of its three clauses — Dep acyclic → FM-5; its two D clauses (acyclic, one
#: parent) guard no mode: they operationalize §15.3's forest, and FM-4 is met by the parent's own check under
#: a correct D (Thm 1), which no structural CHECK compares. CHECK-6 guards none either: it runs at the split's
#: admission, Del being total (Ch. 2), so every admitted leaf carries a drafted Del its first ASSIGN fixes —
#: the owner Inv-8's CANCELLING row names when a cascade reaches it unissued; what it checks is Del's own
#: definition on a split's leaves.
CHECK_TO_FM: dict[str, tuple[str, ...]] = {
    "CHECK-1:coverage":       ("FM-1.a",),
    "CHECK-1b:no_orphan":     ("FM-1.e",),
    "CHECK-2:dag":            ("FM-5",),
    "CHECK-3:deadlines":      ("FM-5",),
    "CHECK-4:accepted_risks": ("FM-1",),
    "CHECK-5:risk_nodes":     ("FM-1",),
    "CHECK-6:delegation":     (),
    "CHECK-7:sufficiency":    ("FM-1",),
    "CHECK-8:consistency":    ("FM-2",),
}

FM_LABEL: dict[str, str] = {
    "FM-1": "Correspondence", "FM-2": "Consistency", "FM-3": "Veracity", "FM-4": "Propagation",
    "FM-5": "Freshness", "FM-6": "Feasibility",
}


def _mentions(text: str, name: str) -> bool:
    """Does `text` name the criterion `name` as a token? Word-boundary exact match — a substring
    test would fire on any criterion whose name is a common word fragment."""
    if not text or not name.strip():
        return False
    return re.search(rf"(?<!\w){re.escape(name.strip())}(?!\w)", text) is not None


def risks_naming_own_criteria(task: Task) -> list[str]:
    """The ACCEPTED_RISKS items of `task` that name one of its own criteria — CHECK-4's first refusal, as data:
    such an entry is a unilateral amendment of the contract, not a risk (§9.2)."""
    return [n.item for n in register_of(task).items
            if any(_mentions(n.item, c.name) or _mentions(n.justification, c.name) for c in task.spec.criteria)]


def check_anti_mock(children: list[Task], dep_edges: list[DepEdge]) -> CheckResult:
    """CHECK-1c (anti-mock): every sibling seam carries a glue truth-maker (§9.5) → FM-1.

    A declared Dep edge with empty glue is the forgotten-glue hole: the edge says two
    parts couple but nothing states what must match / what breaks. (Glue *quality* —
    whether it is mockable — is L2's job; this only checks glue is present.)

    NOT a battery row, and §20.10 is the warrant: it operationalizes a form item the canon
    states (§4.5 item 4, "explicit Dep — the couplings written, not hidden") and the §9.5 battery
    does not check. What it does NOT do is close FM-1.f: glue text is not a criterion, so a
    non-empty glue does not write the integration criterion and an empty one does not show it
    missing — that mode stays Pragmatic, with no a-priori CHECK (§9.5, §9.10).
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


def check_procedure(task: Task) -> CheckResult:
    """A1:procedure — every criterion of THIS node pins the procedure that decides it (§2.2, §1.3(i)).

    NOT a member of §9.5's battery, and deliberately not named like one: the numbered level is the
    canon's and the execution gate is that level in both directions (see the gate's own note on
    CHECK-1c). It sits beside what CHECK-1 already enforces from A1 — CHECK-1 refuses a decomposed
    node with NO criteria ("a task is a goal plus a decidable predicate").

    **Graded honestly: this is a DESIGN DECISION that operationalizes A1, not A1 read off the
    canon.** A1 asserts that a correct decidable predicate EXISTS, "not *which one* it is" (§4.1),
    and §11.2's own example of a decidable criterion — "every function ≤ 50 lines" — pins no
    command and would be refused here. What the rule actually demands is that the procedure be
    WRITTEN DOWN, and before the work: that is Inv-1's pre-registration (§12.14) applied to the
    thing A1 leaves open, chosen because the alternative was measured — the procedure invented at
    validation time, differently each round, with a PASS that meant whatever the validator felt like
    checking.

    What made the gap invisible: "for ANY accepted program the output matches gcc" reads like a
    criterion and decides nothing — the domain is infinite. Whoever validated then invented a probe
    set at validation time, a different one each round, so a PASS recorded the validator's appetite rather
    than the promise. Pinning the procedure with the criterion is what returns the object to its
    type, and it says its own limit out loud: what P does not reach is unchecked (FM-3, Ch. 8).
    """
    # …nor over a settled node of seams alone: a contract frozen before the rule is not re-checked (§11.5), and no move
    # could lift the hole it would leave on its parent's plan for good (critic, 2026-10-11)
    settled = task.state.name in ("DONE", "ABANDONED")
    if not task.spec.criteria or (settled and criterionless(task.spec.criteria)):
        return CheckResult("A1:procedure", True, "no criteria defined", skipped=True)
    # the admission's own ladder, read rather than written again (`admission_defects`; ortho audit, D-F7) — a contract
    # this row calls clean is one the doors admit, and the reverse
    # …and a settled contract's hollow procedure is said, not failed: nothing re-admits it (same ground as above)
    if defects := [d for d in admission_defects(task.spec.criteria) if not (settled and "emits a constant" in d)]:
        return CheckResult("A1:procedure", False, "; ".join(defects))
    notes = []
    if loose := reads_an_unpinned_set(task.spec.criteria):
        notes.append("these commands iterate over a set of files the contract does not pin, so "
                     "their object can grow or shrink under a check whose digest does not move "
                     "(measured on `c_compiler`: 60 files at authoring, 79 at the close) — pin the "
                     "data with the probe (`inputs`) and read it through `{inputs}`: "
                     + "; ".join(f"{k}: {', '.join(v)}" for k, v in sorted(loose.items())))
    if unread := unread_inputs(task.spec.criteria):
        notes.append("these commands carry pinned inputs and never name `{inputs}`, so they still "
                     "read whatever the working directory holds when validated: "
                     + "; ".join(f"{k}: {', '.join(v)}" for k, v in sorted(unread.items())))
    if hollow := degenerate_procedures(task.spec.criteria):
        # A procedure ALL of whose probes are constant is refused above (`hollow_procedures`); a constant beside a real
        # probe is only said — whether the real one can SEE a divergence is FM-3, which §9.10 leaves unguarded.
        notes.append("pinned, but these commands emit a constant and cannot come out false — a "
                     "criterion they decide forbids nothing (§1.3): "
                     + "; ".join(f"{k}: {', '.join(v)}" for k, v in sorted(hollow.items())))
    return CheckResult("A1:procedure", True, " · ".join(notes)) if notes else CheckResult("A1:procedure", True)


def check_coverage(task: Task, children: list[Task]) -> CheckResult:
    """CHECK-1: every criterion of parent is addressed by at least one child.

    Uses explicit CriterionMapping from task.criterion_mappings.
    Each mapping declares: criterion X is addressed by child Y.
    CHECK-1 verifies: (a) every criterion has a mapping, (b) mapped child exists.
    """
    if not task.spec.criteria:
        # A DECOMPOSED node with no criteria of its own is not "covered", it is UNVALIDATABLE. By A1 a
        # task is a goal plus a decidable predicate, so an empty criteria set makes V(node) true
        # vacuously, which §2.2 rules out by requiring the set nonempty — a check that passes because
        # its population is empty.
        # Measured: a two-hour run built five well-specified children under a root carrying ZERO
        # criteria; coverage reported no holes (nothing to cover), the Level-2 gate reported
        # `semantic_covered: true` over `criteria_checked: 0`, every child passed, and the only thing
        # that caught it was the validator refusing to invent a criterion to validate the root by.
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
                f" criterion — §2.2, A1. Give it criteria, or map this criterion elsewhere)")
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
    """CHECK-1b: non-redundancy — the second side of FM-1 (§8.3, §2.4).

    Every child must address at least one parent criterion (via criterion_mappings).
    A child mapped to nothing is superfluous: it inflates the decomposition and
    breaks the non-redundancy half of correctness (Theorem 1 needs both sides).
    """
    if not children:
        return CheckResult("CHECK-1b:no_orphan", True, "leaf task", skipped=True)
    if not task.criterion_mappings:
        return CheckResult("CHECK-1b:no_orphan", True, "no mappings declared", skipped=True)

    mapped_children = {m.child_id for m in task.criterion_mappings}
    # …over the children a re-admission can still drop: one whose verdict is settled is not re-checked (§11.5) — no act
    # of the decomposer drops it, so a criterion removed from it left a flag only a false mapping could lift
    redundant = [c.id for c in children if c.id not in mapped_children and c.state != State.DONE]
    if redundant:
        return CheckResult(
            "CHECK-1b:no_orphan", False,
            f"children addressing no parent criterion: {', '.join(redundant)}",
        )
    return CheckResult("CHECK-1b:no_orphan", True)


def _a_split_that_is_not_a_dag(task: Task | None, children: list[Task]) -> CheckResult | None:
    """The D clause of CHECK-2, over ONE split — or None if this split is fine.

    What is decidable from a single node's decomposition is a node that is its own child (a
    self-parent, reachable through the authoring door — measured) and a repeated child. A longer D
    cycle is not visible from one split and is refused where the whole graph is:
    `admission.refuse_a_d_cycle`, at the ASSIGN that would close it.
    """
    if task is None:
        return None
    seen: set[str] = set()
    for c in children:
        if str(c.id) == str(task.id):
            return CheckResult("CHECK-2:dag", False,
                               f"cycle in the decomposition graph: {task.id} is its own child "
                               f"(D must be a DAG — a cycle is infinite recursion, §15.3/§9.5)")
        if str(c.id) in seen:
            return CheckResult("CHECK-2:dag", False,
                               f"cycle in the decomposition graph: {c.id} appears twice among "
                               f"the children of {task.id}")
        seen.add(str(c.id))
    return None


def check_dag(children: list[Task], dep_edges: list[tuple[str, str]],
              task: Task | None = None, population: dict | set | None = None) -> CheckResult:
    """CHECK-2: the graph of D is a DAG (§9.5: §15.3's forest, guarding no mode), and Dep is acyclic
    (§9.5 → FM-5; §2.7 defines Dep as an acyclic relation).

    The D clause is the canon's own row and used to be missing entirely: this check walked the *Dep*
    edges and reported "CHECK-2:dag" over them, so "a cycle → infinite recursion → an A1 violation"
    (§15.3) was verified nowhere. What is decidable from ONE split is a node that is its own child
    (a self-parent — reachable through the authoring door, measured) and a repeated child; a longer
    D cycle is not visible from a single node's split and is refused where the whole graph is —
    `admission.refuse_a_d_cycle`, at the ASSIGN that would close it.
    """
    if (d_cycle := _a_split_that_is_not_a_dag(task, children)) is not None:
        return d_cycle

    # VACUOUS IS ABOUT WHAT WAS EXAMINED — the same rule CHECK-3 keeps below, and this half was
    # left reading the list handed in. An edge whose endpoints are not nodes of the graph (a
    # `depends_on` naming an id nobody has) reaches the walk, contributes no reachable pair, and
    # turned `vacuous` FALSE — a positive claim that the dependencies were acyclic, with empty
    # details, rendered by `api/models.py` as "met" rather than "met_vacuously". The population is
    # the pairs whose BOTH ends this walk can stand on.
    known = set(population or ()) or ({str(t.id) for t in children} |
                                      ({str(task.id)} if task is not None else set()))
    reachable = [(a, b) for a, b in dep_edges if a in known and b in known]
    if not reachable:
        return CheckResult("CHECK-2:dag", True,
                           "D acyclic; no dependency edges" if not dep_edges
                           else "D acyclic; no dependency edge of this decomposition has both ends "
                                "in the graph",
                           vacuous=True)

    # Build adjacency and detect cycle via DFS
    adj: dict[str, list[str]] = {}
    for a, b in dep_edges:
        adj.setdefault(a, []).append(b)

    UNVISITED, IN_PROGRESS, DONE = 0, 1, 2
    # EVERY NODE THE EDGES TOUCH, not only the siblings. Seeded from `children` alone, the walk
    # refused to step onto any endpoint outside the sibling set (the `node not in status` guard
    # below), so a Dep edge between nodes under DIFFERENT parents was silently not examined — and
    # a cycle closed through such an edge read as `passed=True` here while `check_dag` over the
    # whole graph named it verbatim. The caller decides the population (`Graph.dep_scope`); this
    # check must examine all of what it is given.
    status: dict[str, int] = {str(t.id): UNVISITED for t in children}
    for a, b in dep_edges:
        status.setdefault(a, UNVISITED)
        status.setdefault(b, UNVISITED)
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

    for start in list(status):
        if status.get(start, DONE) == UNVISITED:
            cycle = find_cycle(start)
            if cycle is not None:
                # Name the cycle — an anonymous "cycle detected" leaves the repair (refine reads this
                # as a structural hole) without a locus; the named path IS the contradiction to fix
                # (e.g. a declared seam vs a BLOCK-discovered edge running the opposite way).
                return CheckResult("CHECK-2:dag", False,
                                   "cycle in dependency graph: " + " -> ".join(cycle))

    return CheckResult("CHECK-2:dag", True)


def check_deadlines(task: Task, children: list[Task], dep_edges: list[tuple[str, str]],
                    deadlines: dict[str, object] | None = None) -> CheckResult:
    """CHECK-3: deadline coherence along Dep — the HORIZONTAL rule, which is the whole of the row.

    §2.7: for every dependency (a, b), deadline(a) < deadline(b).

    THE VERTICAL RULE IS NOT THIS CHECK, and used to be reported as though it were. §4.5 item (6)
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
    # The deadlines of the WHOLE examined population, supplied by the caller that decided that
    # population (`Graph.dep_scope`). Built from `children` alone, this map had no entry for an
    # endpoint under a different parent, and the pair was `continue`d — so a violation carried by a
    # cross-branch seam, which is the ordinary shape of a seam, was skipped rather than reported.
    known = dict(deadlines or {})
    known.setdefault(str(task.id), task.deadline)
    for c in children:
        known.setdefault(str(c.id), c.deadline)
    # A SUPPLIED DEFAULT IS READ like any deadline (§9.5 quantifies CHECK-3 over every Dep pair; §2.5 lets the
    # implementation write a default, it does not waive §2.7 for it). Every door writes defaults ORDERED along Dep
    # wherever some choice orders it (`mutations.Schedule`), so a crossing here is a real one.

    violations, examined = [], 0
    for a, b in dep_edges:
        dl_a, dl_b = known.get(a), known.get(b)
        if dl_a is None or dl_b is None:
            continue                    # a node without a deadline states no ordering to violate
        examined += 1
        if dl_a >= dl_b:
            violations.append(f"Dep {a}(deadline={dl_a}) >= {b}(deadline={dl_b})")

    if violations:
        return CheckResult("CHECK-3:deadlines", False, "; ".join(violations))
    # VACUOUS IS ABOUT WHAT WAS EXAMINED, not about what was handed in. Read off `dep_edges` alone,
    # this said `passed=True, vacuous=False` — a positive claim that the dependencies were ordered —
    # over a node for which not one comparable pair existed.
    if not examined:
        return CheckResult("CHECK-3:deadlines", True,
                           "no dependency edges" if not dep_edges
                           else "no dependency pair carries deadlines on both ends",
                           vacuous=True)
    return CheckResult("CHECK-3:deadlines", True)


def check_vertical_deadlines(task: Task, children: list[Task]) -> CheckResult:
    """§4.5(6): every child's deadline < its parent's — SURFACED, not gating.

    A child that may finish after its parent's own deadline cannot compose into it, so the plan
    promises what passage of time denies. The canon states the rule and gives it no CHECK
    (§20.10, the un-operationalized form items), which is exactly why it is reported under its own
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
        return CheckResult("§4.5(6):vertical_deadlines", False, "; ".join(violations))
    if not any(c.deadline for c in children) or task.deadline is None:
        return CheckResult("§4.5(6):vertical_deadlines", True, "no child deadlines to place", vacuous=True)
    return CheckResult("§4.5(6):vertical_deadlines", True)


def _std1_missing(n) -> list:
    """The STD-1 fields this register entry leaves empty (§9.2)."""
    return ([] if isinstance(n.p, float) and 0 < n.p <= 1 else ["p"]) + [
        f for f in ("impact", "justification", "invalidation_condition") if not getattr(n, f).strip()]


def check_accepted_risks(task: Task, children: list[Task]) -> CheckResult:
    """CHECK-4: for a DECOMPOSED node (D≠∅), the ACCEPTED_RISKS section exists, is non-empty, and its records
    are well-formed (record schema §9.2, predictability per factor §9.3).

    ACCEPTED_RISKS is authored per-decomposition by the node's own decomposer — a leaf (D=∅) has no
    decomposition, so its ACCEPTED_RISKS is vacuous and CHECK-4 does not gate it (nor a freshly created child;
    it is authored lazily when/if the child decomposes).

    Record FORM is what L0 can check mechanically (an incomplete record is not an ACCEPTED_RISKS record, §9.2):
    - a predictability verdict is present per factor (it doubles as the risk-vs-scope discriminator, §9.2:
      an entry with no estimable materialization P is a goal SCOPE boundary → goal criteria/CHECK-1);
    - a self-declared ORDINARY factor cannot sit in ACCEPTED_RISKS (internal contradiction of the record, §9.3);
    - every entry carries STD-1's four fields, its estimate filled — a P in (0, 1] and an impact — with its
      justification and its invalidation condition (§9.5's CHECK-4 row; the roll-up 1 − ∏(1 − Pᵢ) of §9.4 reads P).
    Whether the factor is REALLY that predictability class in the domain (S-regularity, FM-1.b, §8.3)
    is a domain question — L2/validator territory, not decidable here."""
    if not children:
        return CheckResult("CHECK-4:accepted_risks", True,
                           "leaf (D=∅): ACCEPTED_RISKS is per-decomposition (§9.2)", skipped=True)
    if not register_of(task).items:
        return CheckResult("CHECK-4:accepted_risks", False, "ACCEPTED_RISKS section is empty")

    malformed = []
    # …AND THE SPLIT'S OWN DENIAL. Every split is a pre-registered hypothesis no discipline certifies a priori, so at
    # least one uncertain event stands behind it — its denial by S — and its estimate is what makes "nonempty" a
    # true report rather than a filler entry (§9.5). Lifted by the decomposer's own entry (§12.16 (ii)).
    if not any(n.denial for n in register_of(task).items):
        malformed.append(
            "no entry states this split's own denial by S (§9.5: every split is a pre-registered hypothesis, and "
            "its odds of being refuted at contact are an uncertain event it carries) — add "
            "{'denial': true, 'p': <the recorded refutation rate of comparable splits, else your estimate>, "
            "'justification': <where that P comes from>} (the item, impact and invalidation condition are fixed)")
    elif (k := sum(n.denial for n in register_of(task).items)) > 1:
        malformed.append(f"{k} entries state this split's denial by S — a split is one hypothesis with one denial "
                         f"(§9.5); keep one")
    for n in register_of(task).items:
        if n.denial:
            if n.component:
                malformed.append(f"the split's denial entry names component '{n.component}' — it is grouped with "
                                 f"none and stands beside the roll-up (§9.5)")
            elif (missing := _std1_missing(n)):
                malformed.append(f"the split's denial entry lacks {', '.join(missing)} (§9.5)")
            continue
        # A ACCEPTED_RISKS entry that names a criterion of THIS node is not a risk record — it is a
        # unilateral contract amendment (§9.2: the register holds risk FACTORS of the decomposition,
        # each with an estimable P; §2.2: the criteria ARE the obligation). Observed live (BCB/93):
        # "test_values criterion cannot pass — canonical test has design flaw" was authored as
        # EXTRAORDINARY, and the validator then excused the red criterion by it → false PASS. The
        # canon path for a criterion believed defective is CHALLENGE (spec defect, q_T) or the
        # issuer's revision — both logged, neither silent.
        named = [c.name for c in task.spec.criteria
                 if _mentions(n.item, c.name) or _mentions(n.justification, c.name)]
        if named:
            malformed.append(
                f"'{n.item}' names this node's own criterion ({', '.join(named)}) — a criterion is "
                f"the obligation, not an acceptable risk (§2.2/§9.2). If it is defective: CHALLENGE "
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
                f"'{n.item}' has no predictability verdict (record incomplete, §9.2). Write the "
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
        elif (missing := _std1_missing(n)):
            malformed.append(f"'{n.item}' lacks STD-1's {', '.join(missing)} (§9.2: every entry carries the factor, its "
                             f"estimate — `p`, the probability it materializes in (0, 1], and `impact` — its "
                             f"`justification` and its `invalidation_condition`)")
    if malformed:
        return CheckResult("CHECK-4:accepted_risks", False, "; ".join(malformed))
    return CheckResult("CHECK-4:accepted_risks", True)


def check_risk_nodes(task: Task, children: list[Task]) -> CheckResult:
    """CHECK-5: for each risk component (STD-3), a risk-node exists in children, or the component's grouped
    ACCEPTED_RISKS entry does (§9.4).

    Paper §9.4: risk components group correlated factors with a common root cause. Each component
    must have a corresponding child addressing it — and WHICH child is a claim the split's author
    makes, recorded on that child (`covers_risks`) exactly as `covers` records a criterion's.

    It was a substring search over prose: `component.lower() in child.description.lower()`. A
    component was "covered" iff some child's text happened to contain its name, so a child called
    "drought-resistant seed trial" covered `drought`, a child called "irrigation" covered nothing
    whatever it really mitigated, and a child that merely MENTIONED the word covered it. Both
    directions are wrong and neither is visible to the reader. The check now reads the record, and
    where no record exists it says so instead of guessing from the description — an undecidable
    conjunct is ⊥, and ⊥ is not a pass (§2.3).
    """
    if not register_of(task).components:
        return CheckResult("CHECK-5:risk_nodes", True, "no risk components defined", vacuous=True)

    if not children:
        return CheckResult("CHECK-5:risk_nodes", False,
                           f"no children to cover {len(register_of(task).components)} risk components")

    # …or ACCEPTED as a group: a component the split accepts rather than mitigates has its grouped entry in the
    # register, and that meets CHECK-5 as a risk node does — where STD-2 grades it statistical (§9.4). A component
    # groups historical problems, so it has precedent; graded otherwise, its entry accepts nothing (critic r4)
    accepted = {n.component for n in register_of(task).items
                if n.component and n.predictability == Predictability.STATISTICAL}
    graded_out = sorted({n.component for n in register_of(task).items if n.component} - accepted)
    covered = {r for c in children for r in c.spec.covers_risks} | accepted
    uncovered = [n for n in register_of(task).components if n not in covered]

    if not covered:
        return CheckResult(
            "CHECK-5:risk_nodes", True,
            f"skipped: no child records which risk component it covers and no ACCEPTED_RISKS entry names one, so this cannot be decided "
            f"for any of {', '.join(register_of(task).components)} — declare `covers_risks` on the "
            f"mitigating child (§9.4/STD-3). It is not read off the descriptions: a name occurring "
            f"in a node's text is not a claim that the node covers the risk", skipped=True)
    if uncovered:
        return CheckResult("CHECK-5:risk_nodes", False,
                           f"uncovered risk components: {', '.join(uncovered)} — no child records "
                           f"`covers_risks` for them and no ACCEPTED_RISKS entry accepts them as a group "
                           f"(`component`)"
                           + (f"; the grouped entries for {', '.join(graded_out)} are not graded STATISTICAL, and "
                              f"only a statistical component is accepted by its entry (§9.4) — mitigate it by a "
                              f"child, or grade the entry as STD-2 finds it" if graded_out else ""))
    return CheckResult("CHECK-5:risk_nodes", True)


def check_delegation(children: list[Task], task: Task | None = None,
                     non_leaf_ids: set[str] | None = None) -> CheckResult:
    """CHECK-6: "∀ leaf t: Del(t) ≠ ∅" (§9.5 → no FM: Del's definition, Ch. 2, on the leaves).

    The quantifier is over LEAVES, and it used to be read over every child: a decomposed child was
    demanded an executor it does not need (its work is its own children's — §2.6 Del is per node, and
    a node that delegates further is accountable through them), while the node the canon does name
    went unchecked when it was a leaf with no parent to run the check for it. Both directions are
    fixed: leaves among the children (`non_leaf_ids` tells which children decompose further; without
    it the caller cannot distinguish, so every child is treated as a leaf — the conservative read),
    and the node ITSELF when it has no split at all, which is the case §9.5 states literally."""
    non_leaf = non_leaf_ids or set()
    if not children:
        if task is not None and task.assignee is None:
            return CheckResult("CHECK-6:delegation", False,
                               f"leaf without an executor: {task.id} (no executor: the leaf cannot be issued — Del, Ch. 2)")
        return CheckResult("CHECK-6:delegation", True)
    unassigned = [t.id for t in children if t.assignee is None and str(t.id) not in non_leaf]
    if unassigned:
        return CheckResult(
            "CHECK-6:delegation", False,
            f"unassigned leaves: {', '.join(unassigned)}",
        )
    return CheckResult("CHECK-6:delegation", True)


def run_structural(task: Task, children: list[Task], dep_edges: list[tuple[str, str]] | None = None,
                   non_leaf_ids: set[str] | None = None,
                   deadlines: dict[str, object] | None = None) -> list[CheckResult]:
    """Run all structural checks (CHECK-1 through CHECK-6).

    `dep_edges` and `deadlines` come from ONE owner (`Graph.dep_scope`) so that the cached
    computation and the execution gate quantify over the same population; they used to differ, and
    the same node then carried opposite answers at two doors.
    """
    edges = dep_edges or []
    return [
        check_procedure(task),
        check_coverage(task, children),
        check_non_redundancy(task, children),
        check_dag(children, edges, task, deadlines),
        check_deadlines(task, children, edges, deadlines),
        check_vertical_deadlines(task, children),
        check_accepted_risks(task, children),
        check_risk_nodes(task, children),
        check_delegation(children, task, non_leaf_ids),
    ]
