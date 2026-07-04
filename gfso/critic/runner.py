"""L2 critic — the STRUCTURAL GATE + the semantic hole-hunt (SEARCH in diff mode).

The semantic L2 (find what a decomposition is MISSING) is, by the resolved design, the SAME SEARCH
machinery as `gfso.decompose` run in DIFF mode over the node's projection — NOT the analyst⊥judge
critic that used to live here. E2's regime screen showed the monolithic FM/methodology critic is
strictly dominated (it polices FORM, cannot move CONTENT) and over-confirmed (the A2 precision
problem); its crooked prompts + two-LLM flow were REMOVED. Staged: L0/L1 gate BLOCKS the semantic
pass (L2 presupposes a structurally-complete graph); the semantic verdict is ADVISORY (asserts, does
not auto-fix — the agent fixes via FSM verbs or consciously declares NEGLECTED).
"""
from __future__ import annotations

from gfso.core.types import TaskId
from .types import NodeCritique


def critique_node(engine, node_id: TaskId, llm=None) -> NodeCritique:
    """The L0/L1 STRUCTURAL gate (cached, O(1)) + optional semantic hole-hunt. A leaf or any structural
    failure ⇒ gate_passed=False with the failures (semantic pass gated out). A structurally-clean
    non-leaf with an `llm` ⇒ one SEARCH call in diff mode: the node's goal + its projection as the
    CURRENT DECOMPOSITION → ALREADY-COVERED (semantic_covered=True) or the findings (advisory).
    A failed/absent call ⇒ semantic_covered=None — never read as clean."""
    nid = str(node_id)
    children = engine.get_active_children(node_id)  # cancelled tombstones are not part of the decomposition
    if not children:
        return NodeCritique(nid, gate_passed=False, l0l1_failures=("leaf — no decomposition",))
    checks = engine.get_checks(node_id)  # CACHED, O(1) — eager-fresh, not recomputed here
    failed = [c for c in checks if not c.passed and not c.skipped]
    if failed:
        failures = tuple(f"{c.check_name} — {c.details}" if c.details else c.check_name for c in failed)
        return NodeCritique(nid, gate_passed=False, l0l1_failures=failures)

    task = engine.get_task(node_id)
    findings = ""
    if llm is not None and task is not None:
        from gfso.decompose.loop import _search, _tag, _COVERED
        findings = _search(llm, task.spec.description, engine.project(node_id)) or ""
        _tag(llm, "validate-search")
        if findings:
            covered = findings.lstrip().upper().startswith(_COVERED)
            return NodeCritique(nid, gate_passed=True, semantic_covered=covered,
                                semantic_findings="" if covered else findings)
    return NodeCritique(nid, gate_passed=True)  # structurally clean; semantic pass not run
