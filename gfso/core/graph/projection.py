"""Read-only projection of a node's decomposition — the critic's input contract.

Renders the unit a semantic critic (analyst + validator) reasons over: a node's goal,
its proposed breakdown (subtasks, their criteria, criterion-coverage, seams,
ACCEPTED_RISKS) and the already-run structural (Solver / L0–L1) checks.

Two layers, no strings-as-transport:
  * `NodeProjection` (frozen) — the DATA of the projection, typed end-to-end.
  * `render(projection)` — pure DATA → markdown, the LLM-prompt boundary where
    strings legitimately appear.
`build(...)` extracts the projection from the graph types; `render_node_projection`
is the thin build→render convenience kept for call-sites that want the markdown.
"""
from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from typing import Optional

from gfso.core.types import AcceptedRiskItem, Task, CheckResult, DepEdge, Verdict, register_of, set_aside_of


# === Sentinel markers — typed values, not bare string literals at use-sites ===

class CoverageMarker(Enum):
    """A criterion-coverage entry with no owning child (typed UNMAPPED sentinel)."""
    UNMAPPED = "⚠ UNMAPPED"


class GlueMarker(Enum):
    """A declared seam carrying no glue (typed NONE-DECLARED sentinel)."""
    NONE_DECLARED = "⚠ NONE DECLARED"


# === Projection DATA (frozen, typed) ===

@dataclass(frozen=True)
class CriterionView:
    name: str
    description: str
    # WHAT WILL BE RUN TO DECIDE IT. A projection that shows the criterion and not its procedure
    # shows an intention; the validator then writes its own, at validation time, which is the defect the
    # pinned `check` exists against (A1/§2, Inv-1 §12.3).
    # (behaviour, command, expect, [the paths the probe pins]) — the NAMES, not the bodies: a
    # projection is what a model reads to repair a plan, and a corpus of eighty programs inlined
    # into it would crowd out the plan itself. What it must not do is hide that `{inputs}` HAS a
    # referent — a reader who cannot see the files writes the next version of the command without
    # them.
    check: tuple[tuple, ...] = ()


@dataclass(frozen=True)
class SubtaskView:
    id: str
    description: str
    assignee: Optional[str]
    criteria: tuple[CriterionView, ...]
    accepted_risks: tuple[str, ...]  # item text of each child-local exclusion
    name: str = ""              # short node label (UI title); part of the child's contract framing


@dataclass(frozen=True)
class CoverageView:
    """One acceptance criterion and the child ids that own it (or UNMAPPED)."""
    criterion_name: str
    owners: tuple[str, ...] | CoverageMarker


@dataclass(frozen=True)
class SeamView:
    from_id: str
    to_id: str
    discovered: bool
    glue: str | GlueMarker
    provisional: bool = False


@dataclass(frozen=True)
class CheckView:
    check_name: str
    passed: bool
    skipped: bool
    details: str


@dataclass(frozen=True)
class NodeProjection:
    """Typed DATA of one node's decomposition projection (no markdown here).

    `is_leaf=True` ⇒ no decomposition to review; coverage/seams/accepted_risks/checks
    are not rendered (matches the leaf short-circuit).
    `criteria_declared=False` distinguishes "no criterion mappings declared" from
    "mappings declared but a criterion is unmapped".
    """
    node_id: str
    goal: str
    criteria: tuple[CriterionView, ...]
    is_leaf: bool
    subtasks: tuple[SubtaskView, ...] = ()
    mappings_declared: bool = False
    coverage: tuple[CoverageView, ...] = ()
    seams: tuple[SeamView, ...] = ()
    accepted_risks: tuple[AcceptedRiskItem, ...] = ()
    scope: tuple[str, ...] = ()  # §9.2 declared scope-boundary exclusions on the goal
    checks: tuple[CheckView, ...] = ()


# === Build: graph types → NodeProjection (pure data extraction) ===

def build(
    node: Task,
    children: list[Task],
    dep_edges: list[DepEdge],
    check_results: list[CheckResult],
) -> NodeProjection:
    """Extract the typed projection from graph types.

    dep_edges may be the full edge set; only sibling seams (both endpoints are
    children of `node`) are captured — this decomposition's internal structure.
    """
    criteria = tuple(
        CriterionView(c.name, c.description,
                      tuple((p.behaviour, p.command, p.expect, [x for x, _ in p.inputs])
                            for p in (c.check or ())))
        for c in node.spec.criteria
    )

    if not children:
        return NodeProjection(
            node_id=str(node.id), goal=node.spec.description, criteria=criteria,
            is_leaf=True,
        )

    subtasks = tuple(
        SubtaskView(
            id=str(c.id),
            description=c.spec.description,
            assignee=c.assignee,
            criteria=tuple(CriterionView(cc.name, cc.description,
                                         tuple((p.behaviour, p.command, p.expect,
                                                [x for x, _ in p.inputs])
                                               for p in (cc.check or ())))
                           for cc in c.spec.criteria),
            accepted_risks=tuple(n.item for n in set_aside_of(c)),
            name=c.spec.name,
        )
        for c in children
    )

    by_crit: dict[str, list[str]] = {}
    for m in node.criterion_mappings:
        by_crit.setdefault(m.criterion_name, []).append(str(m.child_id))
    coverage = tuple(
        CoverageView(
            c.name,
            tuple(by_crit[c.name]) if c.name in by_crit else CoverageMarker.UNMAPPED,
        )
        for c in node.spec.criteria
    )

    child_ids = {c.id for c in children}
    seams = tuple(
        SeamView(
            from_id=str(e.from_id), to_id=str(e.to_id), discovered=e.discovered,
            glue=e.glue if e.glue else GlueMarker.NONE_DECLARED,
            provisional=e.provisional,
        )
        for e in dep_edges
        if e.from_id in child_ids and e.to_id in child_ids
    )

    accepted_risks = tuple(register_of(node).items)

    checks = tuple(
        CheckView(r.check_name, r.passed, r.skipped, r.details) for r in check_results
    )

    return NodeProjection(
        node_id=str(node.id), goal=node.spec.description, criteria=criteria,
        is_leaf=False, subtasks=subtasks,
        mappings_declared=bool(node.criterion_mappings),
        coverage=coverage, seams=seams, accepted_risks=accepted_risks,
        scope=tuple(node.spec.scope), checks=checks,
    )


# === Render: NodeProjection → markdown (the LLM-prompt boundary) ===

def _render_split(p, out: list) -> None:
    """The two sections that describe the SPLIT: the subtasks, and the seams between them.

    `render` is the one place a projection becomes prose, and it read as one long ribbon of
    appends. The split is what the critic is actually asked about, so it is its own
    paragraph — the node's own contract and the checks already run stay with the caller."""
    out.append("## Subtasks (D) — the proposed breakdown")
    for s in p.subtasks:
        who = f" · assignee: {s.assignee}" if s.assignee else ""
        label = f"{s.name}: " if s.name else ""
        out.append(f"### `{s.id}` — {label}{s.description or '(no description)'}{who}")
        if s.criteria:
            for cc in s.criteria:
                out.append(f"  - {cc.name}: {cc.description or '(no description)'}")
        else:
            out.append("  - (no criteria declared)")
        for item in s.accepted_risks:
            out.append(f"  - ACCEPTED_RISKS: {item}")
    out.append("")

    out.append("## Criterion coverage — which subtask owns which acceptance criterion")
    if p.mappings_declared:
        for cov in p.coverage:
            if isinstance(cov.owners, CoverageMarker):
                owners = cov.owners.value
            else:
                owners = ", ".join(cov.owners)
            out.append(f"- **{cov.criterion_name}** → {owners}")
    else:
        out.append("- (no criterion mappings declared)")
    out.append("")

    out.append("## Dependencies (Dep) — declared seams between subtasks")
    if p.seams:
        for e in p.seams:
            # A CONFIRMED discovery is contact's verdict on the plan; a provisional one is an executor's report
            # its issuer has not answered — a claim (§11.3), and a reviewer told "ground truth" reads it as one
            tag = (" (discovered by a BLOCK — reported, not yet answered by its issuer)" if e.discovered and e.provisional
                   else " (discovered by contact — confirmed)" if e.discovered else "")
            out.append(f"- `{e.to_id}` depends on `{e.from_id}`{tag}")
            glue = e.glue.value if isinstance(e.glue, GlueMarker) else e.glue
            out.append(f"  - glue (what must match / what breaks): {glue}")
    else:
        out.append("- (none declared)")


def _render_declared(p, out: list) -> None:
    """The three DECLARED sections: what was consciously excluded, the scope boundary, and
    the structural checks already run. Split from the head — goal, criteria, split — because
    the reader of a projection is asking two different questions and the second half is the
    one that is about what the plan says it does NOT do."""
    out.append("## ACCEPTED_RISKS — the split's register: the uncertain events it accepts")
    events = [n for n in p.accepted_risks if not n.denial]
    if events:
        for n in events:
            pr = f"predictability: {n.predictability.name if n.predictability else 'unclassified'}"
            est = f"; P {n.p}" if n.p is not None else ""
            imp = f"; impact: {n.impact}" if n.impact else ""
            grp = f"; component: {n.component}" if n.component else ""
            j = f"; justification: {n.justification}" if n.justification else ""
            inv = f"; invalidation: {n.invalidation_condition}" if n.invalidation_condition else ""
            out.append(f"- {n.item}  [{pr}{est}{imp}{grp}{j}{inv}]")
    else:
        out.append("- (none declared)")
    out.append("")
    # …and BESIDE it, the split's own denial: its odds of being refuted, not an event it accepts — it covers no gap
    # (§9.2: not admitted, it licenses nothing; critic r4 — under the register it read as covering every gap)
    for n in (n for n in p.accepted_risks if n.denial):
        out.append(f"## The split's denial by S — its stated odds of refutation at contact (P {n.p}), NOT an accepted "
                   f"risk: it covers no gap and excuses no criterion (§9.2, §9.5)")
        out.append("")

    # SCOPE is an OPTIONAL goal-level mark (canon §9.2: помечается «когда исключение неочевидно»),
    # unlike ACCEPTED_RISKS (mandatory for a decomposed node, CHECK-4) — render only when declared: an
    # empty section on a child would misread a goal-level object as that child's missing register.
    if p.scope:
        out.append("## SCOPE — declared boundary exclusions (capabilities deliberately not included)")
        for s in p.scope:
            out.append(f"- {s}")
        out.append("")

    out.append("## Structural checks already run (Solver, L0–L1) — verified, do not re-derive")
    if p.checks:
        for r in p.checks:
            status = "SKIPPED" if r.skipped else (Verdict.PASS if r.passed else Verdict.FAIL)
            detail = f" — {r.details}" if r.details else ""
            out.append(f"- {r.check_name}: {status}{detail}")
    else:
        out.append("- (no checks recorded)")



def render(projection: NodeProjection) -> str:
    """Pure DATA → markdown for the critic. The one place strings are built."""
    p = projection
    out: list[str] = []
    out.append(f"# Decomposition under review — node `{p.node_id}`")
    out.append("")
    out.append("## Goal — what this node must achieve")
    out.append(p.goal or "(no description)")
    out.append("")
    out.append('## Acceptance criteria (V) — what "done" means for this node')
    if p.criteria:
        for c in p.criteria:
            out.append(f"- **{c.name}**: {c.description or '(no description)'}")
            for beh, cmd, exp, *rest in (c.check or ()):
                files = rest[0] if rest else []
                out.append(f"    - pinned check — {beh}: `{cmd}` → expect: {exp}"
                           + (f" (`{{inputs}}` = {len(files)} file(s) pinned with this probe: "
                              f"{', '.join(files)})" if files else ""))
    else:
        out.append("- (none declared)")
    out.append("")

    if p.is_leaf:
        out.append("## Subtasks (D)")
        out.append("- (leaf node — no decomposition to review)")
        return "\n".join(out)

    _render_split(p, out)
    out.append("")

    _render_declared(p, out)
    return "\n".join(out)


def render_node_projection(
    node: Task,
    children: list[Task],
    dep_edges: list[DepEdge],
    check_results: list[CheckResult],
) -> str:
    """Build the typed projection then render it to markdown (convenience wrapper)."""
    return render(build(node, children, dep_edges, check_results))
