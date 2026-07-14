"""L2 critic — the STRUCTURAL GATE + the causal-correctness CHECKER (canon §5.4 Level 2).

Level 2's question is a CHECK, not a hunt: per parent criterion — do the mapped children's
criteria, taken as real-world facts, causally guarantee it? (Plus the semantic FM-2 residue the
formal CHECK-8 cannot see.) EPISTEMIC STATUS (§5.4-bis/§18.1): the Level-2 AXIS is checkable
only by EXECUTION — no pre-contact instrument can verify it (any verdict is itself a Level-2
claim); this checker is the canon's named LLM-REVIEW approximation — an a-priori estimate over
the faithfulness axis — and the real Level-2 verdict stays with contact (q_D). Hence ADVISORY by
construction, never an acceptance blocker.

Two prior designs are deliberately dead: the analyst⊥judge monolithic critic (E2-refuted:
polices form, cannot move content) and the SEARCH-in-diff-mode hole-hunt (the opposite extreme —
"what is missing" is the DECOMPOSER's question and lives in refine, not here). Staged: the L0/L1
gate BLOCKS the checker (L2 presupposes a structurally-complete graph); the verdict never
auto-fixes — the agent fixes via FSM verbs or consciously declares NEGLECTED.
"""
from __future__ import annotations

from pathlib import Path

from gfso.core.types import TaskId
from .types import NodeCritique

# The checker's report contract (parsed, never trusted): one entry per parent criterion; an
# incomplete verdict is treated as NO verdict (semantic_covered=None — never read as clean).
CHECKER_SCHEMA = {
    "type": "object",
    "properties": {
        "criteria": {"type": "array", "items": {
            "type": "object",
            "properties": {"criterion": {"type": "string"},
                           "verdict": {"type": "string",
                                       "enum": ["sufficient", "insufficient", "uncertain"]},
                           "why": {"type": "string"}},
            "required": ["criterion", "verdict", "why"]}},
        "conflicts": {"type": "array", "items": {
            "type": "object",
            "properties": {"between": {"type": "array", "items": {"type": "string"}},
                           "why": {"type": "string"}},
            "required": ["between", "why"]}},
    },
    "required": ["criteria"],
}


def review_decomposition(engine, node_id: TaskId, llm=None) -> NodeCritique:
    """L2 validate — the STRUCTURAL gate (cached L0/L1, eager-fresh) + the causal-correctness
    CHECKER. Stores the critique as the validation record + sets verified=True (advisory).
    Lives HERE, not on Engine: the critic pulls decompose/adapters, and the engine imports core
    only (the mechanical layer gate) — the engine is an argument, not a host."""
    import json
    from dataclasses import asdict
    from datetime import datetime
    used = llm or engine._llm
    critique = critique_node(engine, node_id, used)
    rec = {**asdict(critique),   # + review provenance: re-validation UX needs "who judged, when"
           "model": str(getattr(used, "model", "") or ""),
           "ts": datetime.now().isoformat(sep=" ", timespec="seconds")}
    engine._graph._storage.store_critique(node_id, json.dumps(rec))
    node = engine.get_task(node_id)
    if node is not None:
        node.verified = True  # critique is now current for this decomposition
        engine._graph.save_task(node)
    _log_critique(engine, critique)
    return critique


def _log_critique(engine, critique: NodeCritique) -> None:
    """Append a JSONL line per validation — the raw material for coverage curves."""
    path = getattr(engine, "_critique_log_path", None)
    if not path:
        return
    import json
    from datetime import datetime
    rec = {
        "ts": datetime.now().isoformat(),
        "node": critique.node_id,
        "gate_passed": critique.gate_passed,
        "l0l1_failures": list(critique.l0l1_failures),
        "semantic_covered": critique.semantic_covered,
        "insufficient": sum(1 for c in critique.criteria_verdicts
                            if c.get("verdict") == "insufficient"),
        "conflicts": len(critique.conflicts),
    }
    with open(path, "a", encoding="utf-8") as f:
        f.write(json.dumps(rec) + "\n")


def critique_node(engine, node_id: TaskId, llm=None) -> NodeCritique:
    """The L0/L1 STRUCTURAL gate (cached, O(1)) + the L2 CHECKER. A leaf or any structural failure
    ⇒ gate_passed=False (checker gated out — L2 presupposes structure). A structurally-clean
    non-leaf with an `llm` ⇒ ONE zero-tool call over the node's projection (the one canonical
    read): per parent criterion sufficient/insufficient/uncertain + FM-2 conflicts. A failed,
    absent or INCOMPLETE verdict ⇒ semantic_covered=None — never read as clean."""
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
    if llm is None or task is None:
        return NodeCritique(nid, gate_passed=True)  # structurally clean; checker not run

    from gfso.adapters.llm.structured import schema_instruction, parse_structured
    from gfso.decompose.loop import _tag

    system = (Path(__file__).parent / "prompts" / "checker.md").read_text(encoding="utf-8")
    user = (f"# DECOMPOSITION LEVEL UNDER CHECK\n{engine.project(node_id)}\n\n"
            f"Judge EVERY parent criterion listed above — one entry each.")
    text = llm.complete(prompt=user + schema_instruction(CHECKER_SCHEMA), context=system)
    _tag(llm, "l2-checker")

    parsed = parse_structured(text or "", CHECKER_SCHEMA)
    if parsed is None:
        return NodeCritique(nid, gate_passed=True)  # no verdict — never read as clean

    verdicts = tuple(parsed["criteria"])
    conflicts = tuple(parsed.get("conflicts") or ())
    missing = ({c.name for c in task.spec.criteria}
               - {v.get("criterion", "") for v in verdicts})
    if missing:  # incomplete per-criterion coverage of the verdict itself
        return NodeCritique(nid, gate_passed=True, criteria_verdicts=verdicts, conflicts=conflicts,
                            semantic_findings=f"checker verdict INCOMPLETE — unjudged criteria: "
                                              f"{', '.join(sorted(missing))}")

    gaps = [v for v in verdicts if v.get("verdict") != "sufficient"]
    covered = not gaps and not conflicts
    findings = "" if covered else "\n".join(
        [f"[{v.get('verdict')}] {v.get('criterion')} — {v.get('why')}" for v in gaps]
        + [f"[conflict] {', '.join(c.get('between', ()))} — {c.get('why')}" for c in conflicts])
    return NodeCritique(nid, gate_passed=True, semantic_covered=covered,
                        semantic_findings=findings, criteria_verdicts=verdicts, conflicts=conflicts)
