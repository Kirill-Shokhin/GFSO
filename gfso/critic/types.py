"""Typed result of the L2 validate — the structural gate + the causal-correctness CHECKER verdict.

(Two removed extremes, for provenance: the analyst⊥judge monolithic critic was E2-refuted — polices
form, can't move content; its replacement, the decompose SEARCH prompt in diff mode, was the
OPPOSITE extreme — a hole-hunt is the decomposer's question ("what is missing"), not Level 2's
("does the declared mapping causally entail"). The checker asks canon §13.4's own question.)
"""
from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class NodeCritique:
    """Per-node L2 result. gate_passed=False ⇒ L2 not run (leaf or L0/L1 failed).

    The CHECKER pass is ADVISORY (L2 is not an acceptance blocker): per parent criterion a verdict
    sufficient/insufficient/uncertain with the named causal gap, plus semantic FM-2 conflicts.
    `semantic_covered` is True (every criterion sufficient, no conflicts) / False (gaps or conflicts
    below) / None (no verdict — no LLM, gate failed, call failed, or the verdict was INCOMPLETE:
    a missing per-criterion entry is never read as clean)."""
    node_id: str
    gate_passed: bool
    l0l1_failures: tuple[str, ...] = ()      # check names that gated L2 out
    semantic_covered: bool | None = None
    semantic_findings: str = ""              # rendered gaps/conflicts (advisory, human-readable)
    criteria_verdicts: tuple[dict, ...] = () # [{criterion, verdict, why}] — one per parent criterion
    conflicts: tuple[dict, ...] = ()         # [{between: [child ids], why}] — FM-2 semantic residue
