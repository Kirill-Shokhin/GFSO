"""GFSO single-level decomposition — the E2 search↔audit loop as ONE operation over graph state.

`decompose(request, depth=N)` ≡ init (search + fold over the empty state → spec) + build THROUGH the
FSM + (N−1) × `refine` — where `refine` applies the SAME operation to the BUILT GRAPH as the state:
search over the real projection → audit fold-patch → deterministic merge → wholesale rebuild as a
REVISION (same ids, subtree retained, Del of existing children preserved). `refine(engine, root_id)`
is also public: "+1 iteration" applies to whatever decomposition already exists. The graph only ever
holds VERIFIED states (each round closes on dropped-item + `list_holes` with a bounded repair cycle).
The transport comes from `runtime.llm_factory()` — headless `claude -p` one-shots for Anthropic
(billing per GFSO_BILLING) or GenericLLM for a foreign provider (GFSO_PROVIDER=generic).

Termination & validity guarantees (all bounds hard):
  ≤ depth search calls + ≤ depth fold calls (ALREADY-COVERED / empty-fold exits can only shorten)
  + ≤ REPAIR_ROUNDS repair cycles per build (one corrective audit call + one wholesale re-build each).
  The result NEVER claims more than the graph shows: `holes` carries the final `list_holes` output and
  every unplaced spec item — empty `holes` ⟺ the graph passed its own structural checks (CHECK-1..6 per
  node). Non-empty `holes` is an honest partial result, not a silent success.

Single-level by definition (one node → its children); recurse by calling it again on a child.
"""
from __future__ import annotations

from dataclasses import dataclass, field

from gfso.core.types import TaskId
from gfso.engine import Engine

from .loop import (decompose_spec, _audit_fix, _audit_fold, _fold_merge, _search,
                   _progress, _stat_line, _hint, _tag, _COVERED, AUDIT_SCHEMA, shape)
from .build import build_graph_live
from .extract import extract_spec

REPAIR_ROUNDS = 2


@dataclass
class DecomposeResult:
    engine: Engine
    root_id: TaskId
    d_md: str          # the built root's PROJECTION markdown (Engine.project — the one canonical read)
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


def _build_verified(spec: dict, request: str, engine: Engine, root_id: str, assignee: str,
                    llm, progress=None) -> tuple[TaskId, dict, list[str]]:
    """Build wholesale, then repair-loop: problems → one corrective audit call → wholesale re-build
    (revision semantics). Bounded by REPAIR_ROUNDS; returns the final (root_id, spec, residual problems)."""
    _progress("builder: wholesale build through the FSM…", progress)
    eng, rid, dropped = build_graph_live(spec, request, engine, root_id=root_id, assignee=assignee)
    problems = _problems(engine, rid, dropped)
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
        problems = _problems(engine, rid, dropped)
    _progress("builder: verified clean" if not problems
              else f"builder: honest residue — {len(problems)} problem(s)", progress)
    return rid, spec, problems


def _dens_patch(patch: dict, root_id: str) -> dict:
    """The fold reads the graph's projection, whose node ids are namespaced (`root.walker`) — normalize
    any echoed prefix back to spec ids so the merge matches the extracted state."""
    p = f"{root_id}."

    def dn(x) -> str:
        return str(x).removeprefix(p)

    out = dict(patch)
    for key in ("add_subtasks", "update_subtasks"):
        if key in out:
            out[key] = [{**c, "id": dn(c.get("id", ""))} for c in out[key]]
    if "remove_subtask_ids" in out:
        out["remove_subtask_ids"] = [dn(x) for x in out["remove_subtask_ids"]]
    for key in ("add_mappings", "remove_mappings"):
        if key in out:
            out[key] = [{**m, "child_id": dn(m.get("child_id", ""))} for m in out[key]]
    for key in ("add_deps", "remove_deps"):
        if key in out:
            out[key] = [{**d, "from": dn(d.get("from", "")), "to": dn(d.get("to", ""))} for d in out[key]]
    return out


def _refine_round(engine: Engine, request: str, root_id: str, assignee: str, llm,
                  progress=None, label: str = "1/1") -> tuple[bool, dict, list[str]]:
    """ONE refinement application over the BUILT GRAPH as the state: BOTH roles read the graph's real
    projection (+ any current structural holes) — the one canonical textual read, no separate
    renderer; the auditor folds the findings in as a patch (ids normalized from the projection's
    namespace back to spec ids); the merge rebuilds THROUGH the FSM as a wholesale revision (same
    ids, subtree retained, Del of existing children preserved). Returns (changed, spec, problems);
    changed=False ⟺ converged (ALREADY-COVERED or an empty fold). NB a fold REMOVAL leaves the
    removed node live-but-unmapped (the non-redundancy hole surfaces it) — abandoning work is the
    issuer's explicit CANCEL, never an implicit side effect of refinement."""
    from gfso.core.types import TaskId
    proj = engine.project(TaskId(root_id))
    cur_holes = engine.graph_holes(TaskId(root_id))
    state_view = proj + (("\n\n# CURRENT STRUCTURAL HOLES (unmet checks)\n"
                          + "\n".join(f"- {h['task_id']} / {h['check']}: {h['details']}" for h in cur_holes))
                         if cur_holes else "")
    _progress(f"{label} searcher (over the graph projection)…", progress)
    _hint(llm, f"{label} searcher")
    holes = _search(llm, request, state_view)
    _tag(llm, "search-refine")
    _progress(f"{label} searcher {_stat_line(llm)} · +{len(holes) / 1000:.1f}k chars findings", progress)
    if holes.lstrip().upper().startswith(_COVERED):
        _progress(f"{label} searcher: ALREADY-COVERED — converged", progress)
        return False, extract_spec(engine, root_id), []
    spec = extract_spec(engine, root_id)
    _progress(f"{label} auditor (fold into the graph state)…", progress)
    _hint(llm, f"{label} auditor")
    patch = _dens_patch(_audit_fold(llm, request, state_view, holes) or {}, root_id)
    _tag(llm, "audit-fold-refine")
    new_spec, ops = _fold_merge(spec, patch)
    if not ops:
        _progress(f"{label} auditor {_stat_line(llm)} · empty fold — converged", progress)
        return False, spec, []
    d0, dep0, v0 = shape(spec)
    d, dep, v = shape(new_spec)
    _progress(f"{label} auditor {_stat_line(llm)} · |D| {d0}→{d} · |Dep| {dep0}→{dep} · "
              f"|V| {v0}→{v} · ops: {'; '.join(ops)}", progress)
    rid, new_spec, problems = _build_verified(new_spec, request, engine, root_id, assignee, llm,
                                              progress=progress)
    return True, new_spec, problems


def refine(engine: Engine, root_id: str = "root", rounds: int = 1, model: str = "sonnet",
           llm=None, progress=None) -> DecomposeResult:
    """Apply `rounds` refinement operations to an EXISTING decomposition — the graph is the state
    ("+1 итерация над тем, что есть"): each round = search over the real projection → fold-patch →
    rebuild as a wholesale revision (verified; holes repaired or returned honestly). Stops early on
    convergence (ALREADY-COVERED / empty fold). `decompose(depth=N)` is exactly init + (N−1) of these."""
    from gfso.core.types import TaskId
    root = engine.get_task(TaskId(root_id))
    if root is None:
        raise ValueError(f"refine: no decomposition at {root_id!r}")
    llm = llm or _default_llm(model)
    request = root.spec.description
    assignee = str(root.assignee) if root.assignee else "human"
    spec, holes = extract_spec(engine, root_id), []
    for i in range(max(1, rounds)):
        changed, spec, holes = _refine_round(engine, request, root_id, assignee, llm,
                                             progress=progress, label=f"{i + 1}/{rounds}")
        if not changed:
            break
    return DecomposeResult(engine, TaskId(root_id), engine.project(TaskId(root_id)), spec, holes,
                           stats=list(getattr(llm, "calls", [])))


def decompose(request: str, depth: int = 1, model: str = "sonnet",
              engine: Engine | None = None, root_id: str = "root",
              llm=None, fast: bool = False) -> DecomposeResult:
    """request -> (init search↔fold -> CORE graph -> verified/repaired [-> refine × (depth−1)]).
    Sonnet, depth 1. Builds THROUGH the FSM (the single build path); if no engine is given, spins a
    fresh started in-memory one. depth>1 = further refine operations over the BUILT graph state."""
    if engine is None:
        from gfso.adapters.storage.memory import MemoryStorage
        from gfso.adapters.agents.human import HumanAgent
        engine = Engine(MemoryStorage(), HumanAgent(), llm=None, validate_signals=True)
        engine.start()
    return decompose_into(engine, request, root_id=root_id, depth=depth, model=model,
                          llm=llm, fast=fast)


def decompose_into(engine: Engine, request: str, root_id: str = "root", assignee: str = "human",
                   depth: int = 1, model: str = "sonnet", llm=None, progress=None,
                   fast: bool = False) -> DecomposeResult:
    """Agent-facing: run the init search↔fold on `request`, build the result INTO a LIVE engine THROUGH
    the FSM (signals) under `root_id`, verify + repair until `list_holes` is clean (or return the
    residue honestly) — then apply `depth−1` refine operations over the BUILT graph (each verified;
    the graph only ever holds verified states). Every node is authored by a logged ASSIGN; Dep seams
    are declared as `depends_on` criteria at creation. The entry the MCP/API surface calls. `fast` =
    the measured pace-suffixes (init round only; ~1.5× faster on simple tasks, content quality
    unjudged). `progress(msg)` mirrors pipeline stages to a transport channel (stderr always written)."""
    import time
    from gfso.core.types import TaskId
    t0 = time.time()
    llm = llm or _default_llm(model)
    depth = max(1, depth)
    # ONE verb, dispatched by the state (the monada): an undecomposed target → init round + build
    # + (depth−1) refines; an ALREADY-decomposed target → depth refine rounds over what exists (its
    # own contract is the request — re-authoring the goal itself is the revise verb, not decompose).
    existing = engine.get_task(TaskId(root_id))
    if existing is not None and engine.get_active_children(TaskId(root_id)):
        _progress(f"{root_id} is already decomposed → {depth} refine round(s) over the existing graph",
                  progress)
        req = existing.spec.description or request
        spec, holes, rid = extract_spec(engine, root_id), [], TaskId(root_id)
        for i in range(depth):
            changed, spec, holes = _refine_round(engine, req, root_id, assignee, llm,
                                                 progress=progress, label=f"{i + 1}/{depth}")
            if not changed:
                break
    else:
        spec = decompose_spec(request, llm=llm, progress=progress, fast=fast, label=f"1/{depth}")
        rid, spec, holes = _build_verified(spec, request, engine, root_id, assignee, llm,
                                           progress=progress)
        for i in range(1, depth):
            changed, spec, holes = _refine_round(engine, request, root_id, assignee, llm,
                                                 progress=progress, label=f"{i + 1}/{depth}")
            if not changed:
                break
    calls = list(getattr(llm, "calls", []))
    total_out = sum((c.get("output_tokens") or 0) for c in calls if isinstance(c, dict))
    _progress(f"total: {time.time() - t0:.0f}s wall · {total_out / 1000:.1f}k tokens · "
              f"{len(calls)} LLM calls", progress)
    return DecomposeResult(engine, rid, engine.project(rid), spec, holes, stats=calls)


__all__ = ["decompose", "decompose_into", "decompose_spec", "refine",
           "extract_spec", "build_graph_live", "DecomposeResult"]
