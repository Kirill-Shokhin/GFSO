"""L2 critic — STRUCTURAL GATE only (a rough shell; the semantic pass is deferred).

The semantic L2 (find what a decomposition is MISSING) is, by the resolved design, the SAME
search↔audit machinery as `gfso.decompose` run in DIFF mode — NOT the analyst⊥judge critic that used
to live here. E2's regime screen showed the monolithic FM/methodology critic is strictly dominated
(it polices FORM, cannot move CONTENT), and that critic over-confirmed (the A2 precision problem). Its
crooked prompts + the two-LLM flow were REMOVED so they are never pushed. This returns ONLY the sound
L0/L1 gate; wire the search(diff)⊕audit pass here when L2 is actually exercised (mode-A manual graphs /
post-edit validation) — see the project-memory backlog.
"""
from __future__ import annotations

from gfso.core.types import TaskId
from .types import NodeCritique


def critique_node(engine, node_id: TaskId, llm=None) -> NodeCritique:
    """The L0/L1 STRUCTURAL gate for one decomposition unit (cached, O(1)). A leaf or any structural
    failure ⇒ gate_passed=False with the failures. A structurally-clean non-leaf ⇒ gate_passed=True,
    holes=() — the semantic hole-hunt (search(diff)⊕audit) is NOT wired yet (deferred). `llm` is accepted
    for call-site compatibility but unused."""
    nid = str(node_id)
    children = engine.get_active_children(node_id)  # cancelled tombstones are not part of the decomposition
    if not children:
        return NodeCritique(nid, gate_passed=False, l0l1_failures=("leaf — no decomposition",))
    checks = engine.get_checks(node_id)  # CACHED, O(1) — eager-fresh, not recomputed here
    failed = [c for c in checks if not c.passed and not c.skipped]
    if failed:
        failures = tuple(f"{c.check_name} — {c.details}" if c.details else c.check_name for c in failed)
        return NodeCritique(nid, gate_passed=False, l0l1_failures=failures)
    return NodeCritique(nid, gate_passed=True)  # structurally clean; semantic L2 deferred
