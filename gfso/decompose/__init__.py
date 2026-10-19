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

import time
from dataclasses import dataclass, field

from gfso.adapters.agents.human import HumanAgent
from gfso.adapters.storage.memory import MemoryStorage
from gfso.core.types import Criteria, Probe, Signal, Stage, TaskId
from gfso.engine import Engine
from gfso.core.graph.model import root_of
from gfso.core.protocol.procedure import admission_defects, criterionless
from gfso.adapters.llm.stats import calls_of
from gfso.llm import llm_factory

from .loop import (decompose_spec, _audit_fix, _audit_fold, _fold_merge, _search,
                   _progress, _stat_line, _hint, tag_stage, _COVERED, AUDIT_SCHEMA, shape)
from .build import build_graph_live, held_contract
from .extract import extract_spec
from gfso.config import ROOT_ID, MODEL_DEFAULT, sufficiency_at_authoring
from gfso.critic.runner import _undecided_obligations

REPAIR_ROUNDS = 2


class NoPlan(ValueError):
    """The authoring left the goal with no criterion, so no root is built (§2.2) — carrying what it spent."""

    def __init__(self, msg: str, stats: list):
        super().__init__(msg)
        self.stats = stats


@dataclass
class DecomposeResult:
    engine: Engine
    root_id: TaskId
    d_md: str          # the built root's PROJECTION markdown (Engine.project — the one canonical read)
    spec: dict         # the structured graph spec (root_criteria/subtasks/mappings/deps/accepted_risks)
    holes: list = field(default_factory=list)   # [] ⟺ structurally valid; else the honest residue
    stats: list = field(default_factory=list)   # per-call: {stage, duration_ms, input/output/cache tokens}
    note: str | None = None                     # caller-facing caveat (e.g. `request` ignored on refine)
    #: obligations of the ROOT's own goal that none of its own criteria decides, after the one
    #: repair round. As DATA beside the prose, because a caller reading `holes: []` — the field
    #: named after the concept — concluded the plan was clean while the note in the same reply said
    #: eight obligations were undecided (HTTP door, wave 27, 2026-09-06).
    undecided_obligations: tuple = ()


def _default_llm(model: str):
    """The system-wide provider/billing switch (runtime.llm_factory) — never a hardcoded adapter here."""
    return llm_factory(model)


def default_llm(model: str):
    """The plan's transport, for a caller that must hold the client to account for what it spent."""
    return _default_llm(model)


def _dep_contradictions(engine: Engine, strip: str = "") -> list[str]:
    """Declared seams REFUTED by contact — a deterministic read of recorded state, not a guess:
    a BLOCK-discovered edge (§14.2 ground truth: `to` really consumes `from`) running OPPOSITE to a
    declared seam. The pair is a cycle CHECK-2 names, but the cycle line alone does not say which
    direction is true — this does (observed live: the repairer, seeing only declared seams + the
    cycle, patched mappings twice and left the deadlock standing)."""
    edges = engine.get_dependencies()
    declared = {(str(e.from_id), str(e.to_id)) for e in edges if not e.discovered}
    out = []
    for e in edges:
        f, t = str(e.from_id).removeprefix(strip), str(e.to_id).removeprefix(strip)
        if e.discovered and (str(e.to_id), str(e.from_id)) in declared:
            out.append(f"contact recorded `{t}` depends on `{f}` (discovered edge — the world's "
                       f"verdict), but the plan declares the OPPOSITE seam (`{f}` depends on `{t}`): "
                       f"the declared seam is refuted — re-emit `{t}` with a seam consuming `{f}` "
                       f"and drop the refuted seam from `{f}`")
    return out


def _problems(engine: Engine, root_id: TaskId, dropped: list[str]) -> list[str]:
    """Everything structurally wrong right now: unplaced spec items + every unmet check in the subtree
    + declared seams refuted by contact (the actionable direction behind a CHECK-2 cycle).
    Node ids are de-namespaced back to spec ids — the repair audit speaks the spec's language."""
    p = f"{root_id}."
    return dropped + [f"{str(h['task_id']).removeprefix(p)} / {h['check']}: {h['details']}"
                      for h in engine.graph_holes(root_id)] \
        + _dep_contradictions(engine, strip=p)


def _refused_probes(spec: dict, contract_fixed: bool = False) -> list[str]:
    """Contract defects the admission refuses (`admission_defects`) — repaired BEFORE the build, where the refusal
    would end a paid authoring (measured: a coreutils authoring of 347 s ended on a shared `/tmp` path). A contract
    held as issued (`held_contract`) is not this round's to repair, so its criteria are not read here (critic r7: read,
    they were "pinned no check" — a phantom both repair calls were spent on)."""
    nodes = ([] if contract_fixed else [(ROOT_ID, spec.get("root_criteria") or [])]) + [
        (str(k.get("id")), k.get("criteria") or []) for k in spec.get("subtasks") or []]
    return [f"{node} / {'criterion ' if crits else ''}{line}" for node, crits in nodes
            for line in admission_defects([Criteria(str(c.get("name", "")), check=tuple(
                Probe.of(p) for p in c.get("check") or ())) for c in crits])]


def _build_verified(spec: dict, request: str, engine: Engine, root_id: str, assignee: str,
                    llm, progress=None, max_iterations: int | None = None,
                    child_assignee: str | None = None, executor: str = "",
                    contract_fixed: bool = False) -> tuple[TaskId, dict, list[str]]:
    """Build wholesale, then repair-loop: problems → one corrective audit call → wholesale re-build
    (revision semantics). Bounded by REPAIR_ROUNDS; returns the final (root_id, spec, residual problems).
    The dispatcher is QUIESCED for the WHOLE verified cycle (build + repairs): the graph's contract is
    "only verified states" — an intermediate build with known problems must not be dispatched
    (observed live: executors spawned on a 2-problem intermediate graph a repair was about to revise).
    `contract_fixed`: the node's contract stands as issued (`held_contract`) — every patch is read against it."""
    hold = (lambda d: held_contract(d, engine.graph.get_task(TaskId(root_id)))) if contract_fixed else (lambda d: d)
    spec = hold(spec)
    for r in range(REPAIR_ROUNDS):
        if not (refused := _refused_probes(spec, contract_fixed)):
            break
        _progress(f"{r + 1}/{REPAIR_ROUNDS} repairer: {len(refused)} probe(s) the admission refuses, before the "
                  f"build…", progress)
        fixed = _audit_fix(llm, request, spec, refused, executor) or {}
        spec = {**spec, **{k: fixed[k] for k in fixed if k in AUDIT_SCHEMA["properties"]}}
    spec = hold(spec)
    _no_plan(spec, engine, root_id, llm, contract_fixed)
    engine._dispatch_quiesce = getattr(engine, "_dispatch_quiesce", 0) + 1
    try:
        _progress("builder: wholesale build through the FSM…", progress)
        eng, rid, dropped = build_graph_live(spec, request, engine, root_id=root_id, assignee=assignee,
                                                 max_iterations=max_iterations,
                                                 child_assignee=child_assignee, contract_fixed=contract_fixed)
        problems = _problems(engine, rid, dropped)
        _progress(f"builder: {len(engine.graph.get_active_children(rid))} nodes · {len(dropped)} dropped · "
                  f"{len(problems)} problem(s)", progress)
        for r in range(REPAIR_ROUNDS):
            if not problems:
                break
            _progress(f"{r + 1}/{REPAIR_ROUNDS} repairer: {len(problems)} problem(s) → corrective auditor (patch)…",
                      progress)
            _hint(llm, f"{r + 1}/{REPAIR_ROUNDS} repairer")
            fixed = _audit_fix(llm, request, spec, problems, executor)
            tag_stage(llm, f"{Stage.AUDIT_FIX}-{r + 1}")
            if not fixed:
                break  # repair call failed — return the honest residue
            # PATCH semantics: a re-emitted top-level field replaces the old one wholesale; omitted fields kept.
            patched = [k for k in fixed if k in AUDIT_SCHEMA["properties"]]
            spec = hold({**spec, **{k: fixed[k] for k in patched}})
            _progress(f"{r + 1}/{REPAIR_ROUNDS} repairer {_stat_line(llm)} · patched: {', '.join(patched)}", progress)
            eng, rid, dropped = build_graph_live(spec, request, engine, root_id=root_id, assignee=assignee,
                                                 max_iterations=max_iterations,
                                                 child_assignee=child_assignee, contract_fixed=contract_fixed)
            problems = _problems(engine, rid, dropped)
        # "No problems" over an EMPTY build is vacuous, not clean — the checks had nothing to fail
        # on. Said as "verified clean", it read as a good decomposition to anyone watching the
        # progress line, in exactly the case that matters most: the provider was unreachable or
        # unauthenticated, so nothing was ever proposed.
        built = len(engine.graph.get_active_children(rid))
        # …AND "CLEAN" NAMES WHAT WAS CHECKED. The word answers the STRUCTURAL checks and nothing
        # else, and it was read as a verdict on the plan: an ordinary user's first call came back
        # `holes: []` and `builder: verified clean` in the same payload as "NOTE: 7 obligation(s) of
        # this goal are still decided by no criterion", and wrote it down as the first surprise of
        # the session — two readings of one plan disagreeing about whether it was clean (wave 25,
        # 2026-09-05). Both were true; only one of them was qualified.
        _progress(("builder: nothing was built — the admission refused the split it proposed (the residue says why)"
                   if any(str(p).startswith("the admission refused") for p in problems) else
                   "builder: nothing was built — no verdict to give (the model proposed no subtasks)")
                  if not built else
                  "builder: structurally clean (L0/L1) — whether the criteria DECIDE the goal is a "
                  "different question, answered below and by the Level-2 review" if not problems else
                  f"builder: honest residue — {len(problems)} problem(s)", progress)
        return rid, spec, problems
    finally:
        engine._dispatch_quiesce = max(0, getattr(engine, "_dispatch_quiesce", 1) - 1)
        if not engine._dispatch_quiesce:
            getattr(engine, "_dispatch_wake", lambda: None)()


def _no_plan(spec: dict, engine: Engine, root_id: str, llm, contract_fixed: bool) -> None:
    """Refuse to build a plan any node of which has no criterion it decides — before anything is built or issued.

    Measured (spreadsheet_engine, 2026-10-11): the fold's structured call failed to parse, its retry
    answered `{}` — an honest "nothing to change" for a patch, and on the first round "no plan" — and the
    build ASSIGNed a root with `criteria: []`, which a system executor then took. A subtask with none is the
    same defect one level down: the admission refuses it, after the root was issued. The repair rounds above
    are the retry budget (each such node is a contract defect the admission refuses); what they leave without
    a criterion is reported, not built, so the caller can ask again over an unchanged plan. A subtask's seams
    are not in its spec's `criteria` (they ride `deps`), so the spec reads only what the node decides."""
    new_root = not contract_fixed and engine.graph.get_task(TaskId(root_id)) is None

    def settled(sid) -> bool:
        """A child already terminal: its contract is frozen (§12.14), so no round can write it — old data from
        before the rule (a seams-only DONE child) would otherwise refuse every refine of its parent for good."""
        t = engine.graph.get_task(TaskId(f"{root_id}.{sid}"))
        return t is not None and t.state.name in ("DONE", "ABANDONED")
    empty = ([root_id] if new_root and criterionless(_criteria_of(spec.get("root_criteria"))) else []) + [
        str(k.get("id")) for k in spec.get("subtasks") or []
        if criterionless(_criteria_of(k.get("criteria"))) and not settled(k.get("id"))]
    if not empty:
        return
    calls = [c for c in calls_of(llm) if isinstance(c, dict)]
    failed = sum(1 for c in calls if c.get("parse_failed"))
    raise NoPlan(f"auto_decompose: the authoring left {', '.join(empty)} with no criterion it decides — a task's "
                 f"criteria are a finite NONEMPTY set (§2.2) — so this plan was not built and nothing of it was "
                 f"issued. "
                 + (f"{failed} of {len(calls)} model call(s) returned no parseable plan, and the "
                    f"{REPAIR_ROUNDS} repair round(s) did not write the criteria. " if calls else
                    "The model completed no call — the LLM provider answered nothing (unreachable, or not "
                    "authenticated; see the server log). ")
                 + ("The project is unchanged: call auto_decompose again with the same request." if new_root else
                    f"What stands on '{root_id}' is unchanged: call auto_decompose again."), list(calls))


def _criteria_of(items) -> list:
    """A spec's criteria as the admission reads them (a seam by its `depends_on`)."""
    return [Criteria(str(c.get("name", "")), depends_on=c.get("depends_on")) for c in items or []]


def _dens_patch(patch: dict, root_id: str) -> dict:
    """The fold reads the graph's projection, whose node ids are namespaced (`root.walker`) — normalize
    any echoed prefix back to spec ids so the merge matches the extracted state."""
    p = f"{root_id}."

    def dn(x) -> str:
        """The node id without the root prefix — what a reader of the plan calls it."""
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


#: What the authoring reads when its author is not the node's issuer (`held_contract`): the split maps onto a contract
#: it does not write.
_HELD = ("\n\n# THE NODE'S CRITERIA ARE FIXED — they are its issuer's contract, not yours (Inv-1). Map every subtask "
         "onto them by their exact names; do not add, rename or remove any. A defect you see in them is reported to "
         "the issuer, not written into the plan.")


def _refine_round(engine: Engine, request: str, root_id: str, assignee: str, llm,
                  progress=None, label: str = "1/1", executor: str = "",
                  contract_fixed: bool = False, findings: str = "") -> tuple[bool, dict, list[str]]:
    """ONE refinement application over the BUILT GRAPH as the state: BOTH roles read the graph's real
    projection (+ any current structural holes) — the one canonical textual read, no separate
    renderer; the auditor folds the findings in as a patch (ids normalized from the projection's
    namespace back to spec ids); the merge rebuilds THROUGH the FSM as a wholesale revision (same
    ids, subtree retained, Del of existing children preserved). Returns (changed, spec, problems);
    changed=False ⟺ converged (ALREADY-COVERED or an empty fold). NB a fold REMOVAL leaves the
    removed node live-but-unmapped (the non-redundancy hole surfaces it) — abandoning work is the
    issuer's explicit CANCEL, never an implicit side effect of refinement."""
    proj = engine.project(TaskId(root_id))
    cur_holes = engine.graph_holes(TaskId(root_id))
    kids = engine.graph.get_active_children(TaskId(root_id))
    # FROZEN = settled. An ESCALATED child is not settled — it is waiting for its issuer and takes a
    # revision like any live node (§12.5), so a refine round may still restructure around it.
    frozen = [c for c in kids if c.state.name in ("DONE", "ABANDONED")]
    # RUNTIME contact feeds the replan: a BLOCKED child is the world's verdict on the plan's seams
    # (observed live: an inverted Dep direction deadlocked the graph, and the fold — reading only the
    # static projection — could not see WHY, so it re-derived the same structure). Surface each
    # blocked child with its recorded BLOCK reason so the auditor can restructure against it.
    blocked = [(c, next((a.reason for a in reversed(engine.audit_log(c.id))
                         if a.signal == Signal.BLOCK and not a.rejected and a.reason), ""))
               for c in kids if c.state.name == "BLOCKED"]
    contradictions = _dep_contradictions(engine)
    # …AND WHAT THE LEVEL-2 CHECK SAID, which the fold never saw. A refine run straight after a
    # review that left eleven findings open returned a projection byte-identical to the one
    # before it, `holes: []`, and charged for the round — the findings are the plan's known
    # defects, in the caller's hand at that exact moment, and the one verb whose job is to
    # repair the plan was the only reader that did not get them (agent door, 2026-08-22).
    l2_open = engine.open_l2_findings(TaskId(root_id)) or []
    state_view = proj + (_HELD if contract_fixed else "") + (("\n\n# CURRENT STRUCTURAL HOLES (unmet checks)\n"
                          + "\n".join(f"- {h['task_id']} / {h['check']}: {h['details']}" for h in cur_holes))
                         if cur_holes else "") \
        + (("\n\n# OPEN LEVEL-2 FINDINGS on this plan (the causal check — the Pragmatic level, §9.1)\n"
            "Each is a criterion the children's criteria do not entail, a conflict between "
            "them, or an obligation of THIS node's goal that none of its own criteria decides. "
            "They are the plan's known defects: fold them in, or leave them for the issuer to "
            "dispute in writing — but do not return an unchanged plan while they stand." "\n"
            + "\n".join(f"- {f}" for f in l2_open)) if l2_open else "") \
        + (("\n\n# COMPLETED SUBTASKS — contracts FROZEN\n"
            "These subtasks are terminal; their contracts cannot change (no update/remove — a terminal node "
            "admits no revision; which of this node's criteria one covers is the split's mapping, not its "
            "contract). Route any NEW obligation to a NEW subtask.\n"
            + "\n".join(f"- {c.id} ({c.state.name})" for c in frozen)) if frozen else "") \
        + (("\n\n# BLOCKED SUBTASKS — runtime contact (the world rejected the current seams)\n"
            "Each blocked executor reported WHY it cannot proceed. If a reason reveals a wrong or "
            "missing dependency (e.g. the declared Dep direction contradicts what the work really "
            "consumes), FIX the structure: re-emit the affected subtasks with corrected dep seams.\n"
            + "\n".join(f"- {c.id}: {r[:300]}" for c, r in blocked)) if blocked else "") \
        + (("\n\n# DECLARED SEAMS REFUTED BY CONTACT — the fix direction is NOT a guess\n"
            "BLOCK recorded discovered dependency edges (runtime ground truth). Each line below "
            "contradicts a declared seam running the opposite way. Re-emit the affected subtasks "
            "with the seam in the DISCOVERED direction and drop the refuted declared seam.\n"
            + "\n".join(f"- {c}" for c in contradictions)) if contradictions else "")
    # FINDINGS ALREADY IN HAND ARE NOT SEARCHED FOR AGAIN: the search is the open enumeration of what the plan
    # misses, and a caller holding the list (the goal's undecided obligations) paid ~140 s for it to be re-derived
    # beside the list (haiku coreutils, 2026-10-12) — the fold reads the list itself
    if findings:
        holes = findings
    else:
        _progress(f"{label} searcher (over the graph projection)…", progress)
        _hint(llm, f"{label} searcher")
        holes = _search(llm, request, state_view)
        tag_stage(llm, Stage.SEARCH_REFINE)
        _progress(f"{label} searcher {_stat_line(llm)} · +{len(holes) / 1000:.1f}k chars findings", progress)
    if holes.lstrip().upper().startswith(_COVERED):
        _progress(f"{label} searcher: ALREADY-COVERED — converged", progress)
        return False, extract_spec(engine, root_id), []
    spec = extract_spec(engine, root_id)
    _progress(f"{label} auditor (fold into the graph state)…", progress)
    _hint(llm, f"{label} auditor")
    patch = _dens_patch(_audit_fold(llm, request, state_view, holes, executor=executor) or {}, root_id)
    tag_stage(llm, Stage.AUDIT_FOLD_REFINE)
    new_spec, ops = _fold_merge(spec, patch)
    new_spec = held_contract(new_spec, engine.graph.get_task(TaskId(root_id))) if contract_fixed else new_spec
    if not ops:
        _progress(f"{label} auditor {_stat_line(llm)} · empty fold — converged", progress)
        return False, spec, []
    d0, dep0, v0 = shape(spec)
    d, dep, v = shape(new_spec)
    _progress(f"{label} auditor {_stat_line(llm)} · |D| {d0}→{d} · |Dep| {dep0}→{dep} · "
              f"|V| {v0}→{v} · ops: {'; '.join(ops)}", progress)
    try:
        rid, new_spec, problems = _build_verified(new_spec, request, engine, root_id, assignee, llm,
                                                  progress=progress, executor=executor, contract_fixed=contract_fixed)
    except NoPlan as no:          # a round over a standing plan that authored no contract leaves that plan, said
        _progress(f"{label} {no}", progress)
        return False, spec, [str(no)]
    return True, new_spec, problems


def refine(engine: Engine, root_id: str = ROOT_ID, rounds: int = 1, model: str = MODEL_DEFAULT,
           llm=None, progress=None) -> DecomposeResult:
    """Apply `rounds` refinement operations to an EXISTING decomposition — the graph is the state
    ("+1 итерация над тем, что есть"): each round = search over the real projection → fold-patch →
    rebuild as a wholesale revision (verified; holes repaired or returned honestly). Stops early on
    convergence (ALREADY-COVERED / empty fold). `decompose(depth=N)` is exactly init + (N−1) of these."""
    root = engine.graph.get_task(TaskId(root_id))
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
                           stats=list(calls_of(llm)))


def decompose(request: str, depth: int = 1, model: str = MODEL_DEFAULT,
              engine: Engine | None = None, root_id: str = ROOT_ID,
              llm=None, fast: bool = False) -> DecomposeResult:
    """request -> (init search↔fold -> CORE graph -> verified/repaired [-> refine × (depth−1)]).
    Sonnet, depth 1. Builds THROUGH the FSM (the single build path); if no engine is given, spins a
    fresh started in-memory one. depth>1 = further refine operations over the BUILT graph state."""
    if engine is None:
        engine = Engine(MemoryStorage(), HumanAgent(), llm=None, validate_signals=True)
        engine.start()
    return decompose_into(engine, request, root_id=root_id, depth=depth, model=model,
                          llm=llm, fast=fast)


def _close_the_goals_obligations(engine, request, rid, assignee, llm, spec, holes, progress, executor=""):
    """Ask the sufficiency question about the ROOT, fold what it names once, and MEASURE the residue.

    Returns (spec, holes, residue) — the obligations still undecided after the repair round, or `()`.
    A bottom from the check names nothing and changes nothing: "the check could not run" is not "the
    goal is covered" (§11.2).

    The first version announced "closing them before the plan is handed over" and then handed over a
    plan with the same seven open, because it never asked again (CLI door, 2026-09-02). A claim about
    a result, made before the result exists, is the thing this whole product refuses; the round is
    worth one extra call precisely so the answer can be a measurement instead.
    """
    task = engine.graph.get_task(rid)
    if task is None:
        return spec, holes, ()
    gaps = _undecided_obligations(engine, task, llm, stage=Stage.AUTHORING_OBLIGATIONS)
    if not gaps:
        return spec, holes, ()
    _progress(f"{rid}: the goal has {len(gaps)} obligation(s) no criterion decides — one repair "
              f"round over them", progress)
    listed = "\n".join(f"- {g.get('obligation', '')}" for g in gaps)
    changed, spec2, holes2 = _refine_round(
        engine, request, str(rid), assignee, llm, progress=progress, label="sufficiency", executor=executor,
        findings=f"# OBLIGATIONS OF THIS GOAL THAT NO CRITERION OF THE ROOT DECIDES\n"
                 f"Each line is something the goal text requires and the plan does not yet make checkable. "
                 f"Add or sharpen the ROOT's criteria so each becomes decidable — most belong in the criterion "
                 f"of the component they name — and give the children the criteria that entail them. Do not "
                 f"restate an obligation as a criterion — write the observable that settles it.\n{listed}")
    if not changed:
        return spec, holes, tuple(g.get("obligation", "") for g in gaps)
    # …AND ASK AGAIN, because the repair is a model's answer and not a fact until it is checked.
    _after = _undecided_obligations(engine, engine.graph.get_task(rid), llm)
    if _after is None:   # ⊥: the goal could not be re-read, so nothing is measured closed — all stand
        _progress(f"{rid}: the goal could not be re-read after the repair — its {len(gaps)} obligation(s) "
                  f"stand as named", progress)
        return spec2, holes2, tuple(g.get("obligation", "") for g in gaps)
    residue = tuple(g.get("obligation", "") for g in _after)
    _progress(f"{rid}: {len(gaps) - len(residue)} of {len(gaps)} closed"
              + (f"; still open: {'; '.join(residue)}" if residue else ""), progress)
    return spec2, holes2, residue



def _the_request(existing, request: str, contract_fixed: bool = False) -> str:
    """What an undecomposed node is split by: the request — or, for a node already ISSUED, its own contract
    (description + criteria) with the request as guidance. The split SEMI asks of a held node reached the
    decomposer with only what the holder typed ("split it please"), and the node's contract was re-authored
    from that (critic rounds 11, 12)."""
    if existing is None:
        return request
    crits = "\n".join(f"- {c.name}: {c.description}" for c in existing.spec.criteria)
    own = (existing.spec.description or existing.spec.name or "") + (f"\n\nCriteria:\n{crits}" if crits else "")
    guide = (request or "").strip()
    return own + (f"\n\n# How to split it (the caller)\n{guide}" if guide and guide not in own else "") + (
        _HELD if contract_fixed else "")



def _refuse_what_cannot_be_built(engine: Engine, root_id: str, existing, request: str, plan) -> None:
    """Every target `decompose_into` cannot build, refused before anything is spent."""
    # A SETTLED goal is FROZEN (no revision on a terminal, §12.14) — refining it would only crash on
    # the root's own re-author. ESCALATED is deliberately NOT in this list: it is not settled, it is
    # waiting for its issuer (§12.5), and "change or narrow the criteria" is the second of his
    # three moves — which is exactly what a refine round IS. This sentence used to read "a completed
    # goal is frozen; start a NEW goal (new root) instead", i.e. the door for the issuer's own move
    # told him by name to do the one thing that breaks the graph. It is the literal instruction the
    # measured `c_compiler` run followed, twice.
    if existing is not None and existing.state.name in ("DONE", "ABANDONED"):
        raise ValueError(f"auto_decompose: {root_id!r} is {existing.state.name} — a settled goal is "
                         f"frozen. `reopen({root_id!r})` puts it back under its standing contract "
                         f"while nothing has been staked on it and reopens remain (§12.14); a goal "
                         f"that is genuinely different belongs in its own project (`use_project`).")
    # …AND A TARGET THAT CANNOT BE BUILT IS REFUSED BEFORE ANYTHING IS SPENT. A missing `root_id` means
    # "author a new root", and a project has exactly one: the engine refuses the second one at its
    # ASSIGN — but only after the paid search had run (measured in the suite: two SEARCH spawns for a
    # node that did not exist). Likewise an empty request with no node to take the contract from.
    if existing is None:
        _root = root_of(engine.all_tasks())
        if _root is not None:
            raise ValueError(f"auto_decompose: {root_id!r} is not a node of this project, and a new root "
                             f"cannot be authored — the project's root is {str(_root.id)!r}, and a project "
                             f"has exactly one. "
                             + (f"It is {_root.state.name}: `reopen({str(_root.id)!r})` puts it back under its "
                                f"contract while reopens remain (§12.14)."
                                if _root.state.name in ("DONE", "ABANDONED") else
                                f"To refine the plan pass root_id={str(_root.id)!r}; to split a child, pass "
                                f"that child's id."))
        if not (request or "").strip():
            raise ValueError(f"auto_decompose: {root_id!r} does not exist and `request` is empty — there "
                             f"is no contract to author it from. Pass the goal as `request`.")
    if plan is not None and existing is not None and engine.graph.get_active_children(TaskId(root_id)):
        raise ValueError(f"auto_decompose: {root_id!r} is already decomposed — a given plan builds only "
                         f"an undecomposed target.")


def decompose_into(engine: Engine, request: str, root_id: str = ROOT_ID, assignee: str = "human",
                   depth: int = 1, model: str = MODEL_DEFAULT, llm=None, progress=None,
                   fast: bool = False, max_iterations: int | None = None,
                   child_assignee: str | None = None, spec: dict | None = None,
                   executor: str = "", author: str | None = None) -> DecomposeResult:
    """Agent-facing: run the init search↔fold on `request`, build the result INTO a LIVE engine THROUGH
    the FSM (signals) under `root_id`, verify + repair until `list_holes` is clean (or return the
    residue honestly) — then apply `depth−1` refine operations over the BUILT graph (each verified;
    the graph only ever holds verified states). Every node is authored by a logged ASSIGN; Dep seams
    are declared as `depends_on` criteria at creation. The entry the MCP/API surface calls. `fast` =
    the measured pace-suffixes (init round only; ~1.5× faster on simple tasks, content quality
    unvalidated). `progress(msg)` mirrors pipeline stages to a transport channel (stderr always written).
    `spec` — a plan already authored (`extract_spec` of another graph) is built as it stands, with no
    search and no authoring call: two executions of ONE plan are then comparable, the plan's own
    price left out of both. `author` — the party authoring the split: a node's contract is re-authored only by its
    issuer, so where the author is not the issuer the split maps onto the contract as issued (`held_contract`)."""
    t0 = time.time()
    llm = llm or _default_llm(model)
    depth = max(1, depth)
    # ONE verb, dispatched by the state (the monada): an undecomposed target → init round + build
    # + (depth−1) refines; an ALREADY-decomposed target → depth refine rounds over what exists (its
    # own contract is the request — re-authoring the goal itself is the revise verb, not decompose).
    existing = engine.graph.get_task(TaskId(root_id))
    note = None
    _refuse_what_cannot_be_built(engine, root_id, existing, request, spec)
    held = existing is not None and author is not None and str(author) != str(engine.graph.issuer_of(existing.id))
    given = spec
    if existing is not None and engine.graph.get_active_children(TaskId(root_id)):
        _progress(f"{root_id} is already decomposed → {depth} refine round(s) over the existing graph",
                  progress)
        req = existing.spec.description or request
        if request and request.strip() and request.strip() != (existing.spec.description or "").strip():
            # NEVER swallow caller intent silently: refine works over the node's OWN contract; a new
            # goal/requirement is the REVISE verb (re-ASSIGN with the new contract), then refine.
            note = (f"NOTE: `{root_id}` is already decomposed — refine ran over the node's OWN contract; "
                    f"your `request` text was NOT applied. To change the goal itself: revise the node "
                    f"(new description/criteria), then auto_decompose again.")
            _progress(note, progress)
        spec, holes, rid = extract_spec(engine, root_id), [], TaskId(root_id)
        for i in range(depth):
            changed, spec, holes = _refine_round(engine, req, root_id, assignee, llm, progress=progress,
                                                 label=f"{i + 1}/{depth}", executor=executor, contract_fixed=held)
            if not changed:
                break
    else:
        # the combined text is what the DECOMPOSER reads; the goal text a build keeps is the caller's (critic round 13)
        spec = given if given is not None else decompose_spec(
            _the_request(existing, request, held), llm=llm, progress=progress, fast=fast, label=f"1/{depth}",
            executor=executor)
        rid, spec, holes = _build_verified(spec, request, engine, root_id, assignee, llm,
                                           progress=progress, max_iterations=max_iterations,
                                           child_assignee=child_assignee, executor=executor, contract_fixed=held)
        for i in range(1, depth if given is None else 1):
            changed, spec, holes = _refine_round(engine, request, root_id, assignee, llm, progress=progress,
                                                 label=f"{i + 1}/{depth}", executor=executor, contract_fixed=held)
            if not changed:
                break
    # THE QUESTION THE GATE WILL ASK, ASKED BY WHOEVER WRITES THE ANSWER. The sufficiency check —
    # "what does this goal require that no criterion of this node decides" (FM-1.f) — ran only at
    # review time, so the verb that AUTHORS the criteria never heard it: two testers watched
    # `auto_decompose` produce a root whose own gate then named five to twelve undecided obligations
    # a minute later, and paid two full review rounds to repair what the previous call had just
    # written (2026-09-02, both agent doors). It is the same question either way; asking it here
    # costs one call and the repair rides on the fold that already exists. ONCE, never in a loop —
    # the loop is what cost twenty-six rounds and $19.44 on the E3 arm before it was bounded.
    _residue: tuple = ()
    if sufficiency_at_authoring() and given is None and not held:
        spec, holes, _residue = _close_the_goals_obligations(engine, request, rid, assignee, llm,
                                                             spec, holes, progress, executor)
        if _residue:
            # …AND THE CALLER LEARNS IT HERE, not one paid review round later. The gate will name
            # these again; what it must not do is name them for the first time.
            note = ((note + " ") if note else "") + (
                f"NOTE: {len(_residue)} obligation(s) of this goal are still decided by no criterion "
                f"after the repair round — the Level-2 review will name them again: "
                + "; ".join(_residue))
    calls = list(calls_of(llm))
    total_out = sum((c.get("output_tokens") or 0) for c in calls if isinstance(c, dict))
    _progress(f"total: {time.time() - t0:.0f}s wall · {total_out / 1000:.1f}k tokens · "
              f"{len(calls)} LLM calls", progress)
    return DecomposeResult(engine, rid, engine.project(rid), spec, holes, stats=calls, note=note,
                           undecided_obligations=tuple(_residue))


__all__ = ["decompose", "decompose_into", "decompose_spec", "refine",
           "extract_spec", "build_graph_live", "DecomposeResult"]
