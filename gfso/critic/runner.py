"""L2 critic — the STRUCTURAL GATE + the causal-correctness CHECKER (canon §13.4 Level 2).

Level 2's question is a CHECK, not a hunt: per parent criterion — do the mapped children's
criteria, taken as real-world facts, causally guarantee it? (Plus the semantic FM-2 residue the
formal CHECK-8 cannot see.) EPISTEMIC STATUS (§13.5/§8): the Level-2 AXIS is checkable
only by EXECUTION — no pre-contact instrument can verify it (any verdict is itself a Level-2
claim); this checker is the canon's named LLM-OFFERED approximation — an a-priori estimate over
the faithfulness axis — and the real Level-2 verdict stays with contact (q_D). Hence ADVISORY by
construction, never an acceptance blocker.

Two prior designs are deliberately dead: the analyst⊥judge monolithic critic (E2-refuted:
polices form, cannot move content) and the SEARCH-in-diff-mode hole-hunt (the opposite extreme —
"what is missing" is the DECOMPOSER's question and lives in refine, not here). Staged: the L0/L1
gate BLOCKS the checker (L2 presupposes a structurally-complete graph); the verdict never
auto-fixes — the agent fixes via FSM verbs or consciously declares ACCEPTED_RISKS.
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

# The ATOMICITY report contract (the same check over the degenerate plan D(t)=∅): is the goal one
# unit of work, or does it hold separable, independently-deliverable parts? Incomplete ⇒ no verdict.
ATOMICITY_SCHEMA = {
    "type": "object",
    "properties": {
        "verdict": {"type": "string", "enum": ["atomic", "separable"]},
        "why": {"type": "string"},
        "concerns": {"type": "array", "items": {
            "type": "object",
            "properties": {"name": {"type": "string"},
                           "criteria": {"type": "array", "items": {"type": "string"}}},
            "required": ["name", "criteria"]}},
    },
    "required": ["verdict", "why"],
}


def review_decomposition(engine, node_id: TaskId, llm=None) -> NodeCritique:
    """L2 validate — the STRUCTURAL gate (cached L0/L1, eager-fresh) + the causal-correctness
    CHECKER. Stores the critique as the validation record + sets verified=True.
    Lives HERE, not on Engine: the critic pulls decompose/adapters, and the engine imports core
    only (the mechanical layer gate) — the engine is an argument, not a host."""
    import json
    from dataclasses import asdict
    from datetime import datetime
    used = llm or engine._llm
    critique = critique_node(engine, node_id, used)
    rec = {**asdict(critique),   # + review provenance: re-validation UX needs "who judged, when"
           # `_model` is the port's attribute; the public-looking `model` never existed, so every
           # record until now stored an empty string — and provenance you cannot read is no provenance
           # (it hid WHICH model produced a verdict while two runs disagreed about the same plan).
           "model": str(getattr(used, "_model", None) or getattr(used, "model", "") or ""),
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


def _critique_leaf(engine, node_id: TaskId, llm=None) -> NodeCritique:
    """The same Level-2 question over the DEGENERATE plan: D(t)=∅ — "this goal is one unit of work".

    That is a claim like any other in the plan, and until it is checked it is the cheapest way to
    route around the method entirely: declare the goal atomic and no decomposition exists to review
    (observed live — a fresh agent took an issued 6-criteria goal straight to code). So a leaf is
    reviewed too, by its own question: do these acceptance criteria describe separable,
    independently-deliverable parts? A `separable` verdict names them as a partition of the criteria;
    an `atomic` verdict closes the check and the node executes as a leaf, which is a perfectly good
    answer — this is not a push to decompose (§10: inventing a pass-through child makes the plan
    WORSE). Advisory exactly like the decomposition checker: the agent fixes or disputes, contact
    decides (§13.5)."""
    nid = str(node_id)
    task = engine.get_task(node_id)
    if llm is None or task is None:
        return NodeCritique(nid, gate_passed=True)   # no instrument — no verdict, never read as clean

    from gfso.adapters.llm.structured import schema_instruction, parse_structured
    from gfso.decompose.loop import _tag

    system = (Path(__file__).parent / "prompts" / "atomicity.md").read_text(encoding="utf-8")
    crits = "\n".join(f"- {c.name}: {c.description}" for c in task.spec.criteria)
    user = (f"# GOAL DECLARED ATOMIC (no decomposition)\n"
            f"**{task.spec.name or nid}**\n\n{task.spec.description}\n\n"
            f"## Acceptance criteria\n{crits}\n\n"
            f"Judge: one unit of work, or separable parts?")
    text = llm.complete(prompt=user + schema_instruction(ATOMICITY_SCHEMA), context=system)
    _tag(llm, "l2-atomicity")

    parsed = parse_structured(text or "", ATOMICITY_SCHEMA)
    if parsed is None:
        return NodeCritique(nid, gate_passed=True)   # no verdict — never read as clean
    if parsed["verdict"] == "atomic":
        return NodeCritique(nid, gate_passed=True, semantic_covered=True,
                            criteria_verdicts=({"criterion": "atomicity", "verdict": "sufficient",
                                                "why": parsed.get("why", "")},))
    concerns = parsed.get("concerns") or ()
    named = "; ".join(f"{c.get('name')} [{', '.join(c.get('criteria') or ())}]" for c in concerns)
    return NodeCritique(
        nid, gate_passed=True, semantic_covered=False,
        semantic_findings=f"[separable] {parsed.get('why', '')}" + (f" — concerns: {named}" if named else ""),
        criteria_verdicts=({"criterion": "atomicity", "verdict": "insufficient",
                            "why": f"{parsed.get('why', '')}" + (f" Concerns: {named}" if named else "")},))


def critique_node(engine, node_id: TaskId, llm=None) -> NodeCritique:
    """The L0/L1 STRUCTURAL gate (cached, O(1)) + the L2 CHECKER. A leaf or a structural CORRECTNESS
    failure ⇒ gate_passed=False (checker gated out — L2 presupposes structure). A structurally-clean
    non-leaf with an `llm` ⇒ ONE zero-tool call over the node's projection (the one canonical
    read): per parent criterion sufficient/insufficient/uncertain + FM-2 conflicts. A failed,
    absent or INCOMPLETE verdict ⇒ semantic_covered=None — never read as clean.

    "Structurally clean" means the SAME checks that admit a plan to execution: the whole Syntactic
    level (CHECK-1, 1b, 2, 3, 4, 5, 6 — §13.4), read from `_EXEC_GATING_CHECKS` so the two gates
    cannot drift apart. The register and risk-node rows are on that level too (§13.1: "a decomposition
    without the register is incomplete by definition"), so a plan with an empty ACCEPTED_RISKS gets no
    Level-2 verdict and no execution — the hole is repaired, not routed around. What that costs is
    real and was measured (gating the register bought fabricated entries and churn), and it is a q_T
    defect with a name and an owner — an argument about incentives, not about whose rule this is.
    One definition of an admissible plan, used by both gates."""
    from gfso.engine.validation import _EXEC_GATING_CHECKS
    nid = str(node_id)
    children = engine.get_active_children(node_id)  # cancelled tombstones are not part of the decomposition
    if not children:
        return _critique_leaf(engine, node_id, llm)
    checks = engine.get_checks(node_id)  # CACHED, O(1) — eager-fresh, not recomputed here
    failed = [c for c in checks if not c.passed and not c.skipped
              and c.check_name.startswith(_EXEC_GATING_CHECKS)]
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
