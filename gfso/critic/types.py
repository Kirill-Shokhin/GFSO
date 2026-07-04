"""Typed result of the L2 validate — the structural gate + the semantic diff-search verdict.

(The old analyst⊥judge types — Hole / Verdict / per-finding rulings — were part of the REMOVED
monolithic critic (E2-refuted: polices form, can't move content) and are gone with it; the
semantic pass is the decompose SEARCH prompt in diff mode, whose findings are prose, advisory.)
"""
from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class NodeCritique:
    """Per-node L2 result. gate_passed=False ⇒ L2 not run (leaf or L0/L1 failed).

    The semantic pass (search-in-diff-mode over the node's projection — the node + ALL its
    children, one whole decomposition level, the same unit decompose builds) is ADVISORY (L2 is
    not an acceptance blocker): `semantic_covered` is True (searcher reported ALREADY-COVERED) /
    False (findings below) / None (semantic pass not run — no LLM, gate failed, or the call
    failed — which is NEVER read as clean)."""
    node_id: str
    gate_passed: bool
    l0l1_failures: tuple[str, ...] = ()   # check names that gated L2 out
    semantic_covered: bool | None = None
    semantic_findings: str = ""           # the searcher's hole-hunt output (prose, advisory)
