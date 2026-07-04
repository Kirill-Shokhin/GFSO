"""GFSO single-level decomposition function — the E2 search↔audit loop as one button, end to end.

`decompose(request, depth=1)` runs SEARCH↔AUDIT (`depth` = the calibration dial: iterations of the
refinement loop; trivial task → 1) and builds the CORE graph WHOLESALE from the final spec, then closes
the loop on structural validity: dropped-item + `list_holes` verification with a bounded repair cycle.
The transport comes from `runtime.llm_factory()` — headless `claude -p` one-shots for Anthropic (billing
per GFSO_BILLING) or GenericLLM for a foreign provider (GFSO_PROVIDER=generic).

Termination & validity guarantees (all bounds hard):
  ≤ depth search calls + ≤ depth audit calls (early ALREADY-COVERED exit can only shorten)
  + ≤ REPAIR_ROUNDS repair cycles (one corrective audit call + one wholesale re-build each; a re-build is
    a wholesale REVISION — same ids, subtree retained, v3.7).
  The result NEVER claims more than the graph shows: `holes` carries the final `list_holes` output and
  every unplaced spec item — empty `holes` ⟺ the graph passed its own structural checks (CHECK-1..6 per
  node). Non-empty `holes` is an honest partial result, not a silent success.

Single-level by definition (one node → its children); recurse by calling it again on a child.
"""
from __future__ import annotations

from dataclasses import dataclass, field

from gfso.core.types import TaskId
from gfso.engine import Engine

from .loop import (decompose_text, decompose_spec, _audit_fix, _progress, _stat_line, _hint,
                   AUDIT_SCHEMA)
from .build import build_graph_live

REPAIR_ROUNDS = 2


@dataclass
class DecomposeResult:
    engine: Engine
    root_id: TaskId
    d_md: str          # the durable markdown basis (basis_markdown)
    spec: dict         # the structured graph spec (root_criteria/subtasks/mappings/deps/neglected)
    holes: list = field(default_factory=list)   # [] ⟺ structurally valid; else the honest residue
    stats: list = field(default_factory=list)   # per-call: {stage, duration_ms, input/output/cache tokens}


def _default_llm(model: str):
    """The system-wide provider/billing switch (runtime.llm_factory) — never a hardcoded adapter here."""
    from gfso.runtime import llm_factory
    return llm_factory(model)


def _problems(engine: Engine, root_id: TaskId, dropped: list[str]) -> list[str]:
    """Everything structurally wrong right now: unplaced spec items + every unmet check in the subtree.
    Node ids are de-namespaced back to spec ids — the repair audit speaks the spec's language."""
    p = f"{root_id}."
    return dropped + [f"{str(h['task_id']).removeprefix(p)} / {h['check']}: {h['details']}"
                      for h in engine.graph_holes(root_id)]


def _count_problems(spec: dict) -> list[str]:
    """The prose→spec COUNT-CHECK: the carried basis is the richer artifact — if its D/Dep sections
    enumerate clearly MORE items than the structured spec carries, transcription lost content (measured
    live: −2 Dep / −1 V on a depth-2 T01). Deliberately CONSERVATIVE (the basis is free prose — a
    misfire would trigger repairs on clean runs): only counts numbered items under an explicit D
    section header / bullets under a Dep header, and only flags a deficit ≥ 2. V criteria are not
    counted (spread across nodes; no reliable prose anchor)."""
    import re
    md = spec.get("basis_markdown") or ""
    if not md:
        return []

    def _section_items(header_re: str, item_re: str) -> int | None:
        m = re.search(header_re, md, re.MULTILINE)
        if not m:
            return None
        tail = md[m.end():]
        nxt = re.search(r"^#{1,3}\s", tail, re.MULTILINE)
        body = tail[:nxt.start()] if nxt else tail
        return len(re.findall(item_re, body, re.MULTILINE))

    out = []
    nd = _section_items(r"^#{1,3}\s*D\b[^\n]*$", r"^\s*\d+[.)]\s")
    if nd is not None and nd >= len(spec.get("subtasks", ())) + 2:
        out.append(f"the basis D section enumerates {nd} components but the spec carries only "
                   f"{len(spec.get('subtasks', ()))} subtasks — restore the lost components")
    ndep = _section_items(r"^#{1,3}\s*Dep\b[^\n]*$", r"^\s*(?:[-*]|\d+[.)])\s")
    if ndep is not None and ndep >= len(spec.get("deps", ())) + 2:
        out.append(f"the basis Dep section lists {ndep} seams but the spec carries only "
                   f"{len(spec.get('deps', ()))} deps — restore the lost seams")
    return out


def _build_verified(spec: dict, request: str, engine: Engine, root_id: str, assignee: str,
                    llm, progress=None) -> tuple[TaskId, dict, list[str]]:
    """Build wholesale, then repair-loop: problems → one corrective audit call → wholesale re-build
    (revision semantics). Bounded by REPAIR_ROUNDS; returns the final (root_id, spec, residual problems)."""
    _progress("builder: wholesale build through the FSM…", progress)
    eng, rid, dropped = build_graph_live(spec, request, engine, root_id=root_id, assignee=assignee)
    problems = _count_problems(spec) + _problems(engine, rid, dropped)
    _progress(f"builder: {len(engine.get_active_children(rid))} nodes · {len(dropped)} dropped · "
              f"{len(problems)} problem(s)", progress)
    for r in range(REPAIR_ROUNDS):
        if not problems:
            break
        _progress(f"{r + 1}/{REPAIR_ROUNDS} repairer: {len(problems)} problem(s) → corrective auditor (patch)…",
                  progress)
        _hint(llm, f"{r + 1}/{REPAIR_ROUNDS} repairer")
        fixed = _audit_fix(llm, request, spec, problems)
        if hasattr(llm, "tag_last"):
            llm.tag_last(f"audit-fix-{r + 1}")
        if not fixed:
            break  # repair call failed — return the honest residue
        # PATCH semantics: a re-emitted top-level field replaces the old one wholesale; omitted fields kept.
        patched = [k for k in fixed if k in AUDIT_SCHEMA["properties"]]
        spec = {**spec, **{k: fixed[k] for k in patched}}
        _progress(f"{r + 1}/{REPAIR_ROUNDS} repairer {_stat_line(llm)} · patched: {', '.join(patched)}", progress)
        eng, rid, dropped = build_graph_live(spec, request, engine, root_id=root_id, assignee=assignee)
        problems = _count_problems(spec) + _problems(engine, rid, dropped)
    _progress("builder: verified clean" if not problems
              else f"builder: honest residue — {len(problems)} problem(s)", progress)
    return rid, spec, problems


def decompose(request: str, depth: int = 1, model: str = "sonnet",
              engine: Engine | None = None, root_id: str = "root",
              llm=None, emit_basis: bool | None = None, fast: bool = False) -> DecomposeResult:
    """request -> (search↔audit -> graph spec -> CORE graph -> verified/repaired). Sonnet, depth 1.
    Final-audit emission policy is measured-auto (depth=1 → prose-first full, depth≥2 → lean structure;
    see decompose_spec). Builds THROUGH the FSM (the single build path); if no engine is given, spins a
    fresh started in-memory one."""
    llm = llm or _default_llm(model)
    spec = decompose_spec(request, depth=depth, llm=llm, emit_basis=emit_basis, fast=fast)
    if engine is None:
        from gfso.adapters.storage.memory import MemoryStorage
        from gfso.adapters.agents.human import HumanAgent
        engine = Engine(MemoryStorage(), HumanAgent(), llm=None, validate_signals=True)
        engine.start()
    rid, spec, holes = _build_verified(spec, request, engine, root_id, "human", llm)
    return DecomposeResult(engine, rid, spec.get("basis_markdown", ""), spec, holes,
                           stats=list(getattr(llm, "calls", [])))


def decompose_into(engine: Engine, request: str, root_id: str = "root", assignee: str = "human",
                   depth: int = 1, model: str = "sonnet", llm=None, progress=None,
                   emit_basis: bool | None = None, fast: bool = False) -> DecomposeResult:
    """Agent-facing: run search↔audit on `request` and build the result INTO a LIVE engine THROUGH the FSM
    (signals), under `root_id`, then verify + repair until `list_holes` is clean (or return the residue
    honestly). Every node is authored by a logged ASSIGN; Dep seams are declared as `depends_on` criteria
    at creation. The entry the MCP/API surface calls. Final-audit emission = measured-auto (depth=1 →
    prose-first, depth≥2 → lean; see decompose_spec). `fast` = the measured pace-suffixes (see
    decompose_spec; ~1.5× faster on simple tasks, content quality unjudged). `progress(msg)` mirrors
    pipeline stages to a transport channel (stderr always written)."""
    import time
    t0 = time.time()
    llm = llm or _default_llm(model)
    spec = decompose_spec(request, depth=depth, llm=llm, progress=progress, emit_basis=emit_basis,
                          fast=fast)
    rid, spec, holes = _build_verified(spec, request, engine, root_id, assignee, llm, progress=progress)
    calls = list(getattr(llm, "calls", []))
    total_out = sum((c.get("output_tokens") or 0) for c in calls if isinstance(c, dict))
    _progress(f"total: {time.time() - t0:.0f}s wall · {total_out / 1000:.1f}k tokens · "
              f"{len(calls)} LLM calls", progress)
    return DecomposeResult(engine, rid, spec.get("basis_markdown", ""), spec, holes, stats=calls)


__all__ = ["decompose", "decompose_into", "decompose_text", "decompose_spec",
           "build_graph_live", "DecomposeResult"]
