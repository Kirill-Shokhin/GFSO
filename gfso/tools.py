"""MCP tool layer — the agent's surface over the CORE upper API.

Pure functions `(engine, *args) -> JSON-able dict` so the logic is testable without the MCP transport.
Every AUTHORING tool desugars to the canonical 12-signal FSM (the lower layer is closed: no mutation
bypasses the audited protocol). The tool DOCSTRINGS are the agent's contract — they state, per tool,
which signals it desugars to, so a model never mistakes an authoring op for a new protocol primitive.
"""
from __future__ import annotations

from dataclasses import asdict
from typing import Optional

from gfso.core.types import (
    TaskId, AgentId, Spec, Criteria, NeglectedItem, CriterionMapping,
    SignalData, Signal, Predictability,
)
from gfso.engine import Engine


# ── serialization helpers ────────────────────────────────────────────────────

def _neglected_from(items: list) -> tuple[NeglectedItem, ...]:
    # predictability verdict (ORDINARY/STATISTICAL/EXTRAORDINARY) is MANDATORY per factor on a decomposed
    # node (CHECK-4 record form, §5.1) — plumbed here so agents can classify; a plain string stays unclassified.
    return tuple(
        NeglectedItem(n) if isinstance(n, str)
        else NeglectedItem(n["item"],
                           Predictability[n["predictability"].upper()] if n.get("predictability") else None,
                           n.get("justification", ""), n.get("invalidation_condition", ""))
        for n in items)


def _spec_from(d: dict) -> Spec:
    crits = tuple(Criteria(c["name"], c.get("description", ""),
                           depends_on=TaskId(c["depends_on"]) if c.get("depends_on") else None)
                  for c in d.get("criteria", []))
    return Spec(d.get("description", ""), crits, _neglected_from(d.get("neglected", [])),
                name=d.get("name", ""))


def _task_out(t) -> Optional[dict]:
    if t is None:
        return None
    return {
        "id": t.id, "name": t.spec.name, "description": t.spec.description, "state": t.state.name,
        "assignee": t.assignee, "parent_id": t.parent_id,
        "criteria": [{"name": c.name, "description": c.description,
                      "depends_on": c.depends_on} for c in t.spec.criteria],
        "neglected": [n.item for n in t.spec.neglected],
        "done_reason": t.done_reason.name if t.done_reason else None,
        "verified": t.verified,
    }


# ── READS ────────────────────────────────────────────────────────────────────

def get_task(engine: Engine, task_id: str) -> Optional[dict]:
    """Read a task node (spec, state, assignee, criteria, NEGLECTED)."""
    return _task_out(engine.get_task(TaskId(task_id)))


def project(engine: Engine, task_id: str) -> str:
    """The read-only projection you REASON over before authoring/validating: goal + subtasks + criteria
    + coverage + seams (Dep) + NEGLECTED + already-run structural checks. Returns markdown."""
    return engine.project(TaskId(task_id))


def get_checks(engine: Engine, task_id: str) -> list[dict]:
    """The L0/L1 structural checks (compiler-style: coverage / DAG / anti-mock / sufficiency …)."""
    return [{"check": c.check_name, "passed": c.passed, "details": c.details, "skipped": c.skipped}
            for c in engine.get_checks(TaskId(task_id))]


def available_actions(engine: Engine, task_id: str, agent: Optional[str] = None) -> list[str]:
    """The protocol signals valid in this node's state for this agent's role (the affordances)."""
    return [s.name for s in engine.available_actions(TaskId(task_id), AgentId(agent) if agent else None)]


def get_graph(engine: Engine) -> dict:
    """The whole graph: nodes (id, name, state, parent) + edges (parent-child and dependency). The bird's-eye
    view — use it to see overall progress / where the frontier is."""
    tasks = engine.all_tasks()
    nodes = [{"id": str(t.id), "name": t.spec.name or t.spec.description[:40], "state": t.state.name,
              "done_reason": t.done_reason.name if t.done_reason else None,  # CANCELLED = a tombstone (grey it)
              "parent_id": str(t.parent_id) if t.parent_id else None} for t in tasks]
    edges = [{"source": str(t.parent_id), "target": str(t.id), "type": "parent-child"}
             for t in tasks if t.parent_id]
    edges += [{"source": str(d.from_id), "target": str(d.to_id), "type": "dependency"}
              for d in engine.graph.dep_edges()]
    return {"nodes": nodes, "edges": edges}


def list_holes(engine: Engine, root_id: Optional[str] = None) -> list[dict]:
    """Every UNMET structural check across the whole graph (or the subtree under root_id) — the full gap list.
    Call this AFTER auto_decompose / before driving execution: a decomposed graph may come back with failing
    checks (coverage/glue/NEGLECTED/…); this shows them ALL at once so you can fix ∨ declare them up front,
    instead of discovering them one PASS-rejection at a time. Returns [{task_id, name, check, details}]."""
    return engine.graph_holes(TaskId(root_id) if root_id else None)


def get_dependencies(engine: Engine) -> list[dict]:
    """All Dep edges (declared = derived from criteria `depends_on`; discovered = BLOCK-surfaced)."""
    return [{"from": e.from_id, "to": e.to_id, "discovered": e.discovered, "glue": e.glue}
            for e in engine.get_dependencies()]


def metrics(engine: Engine) -> dict:
    """Self-measuring quality vector Q = (q_T, q_D, q_V, q_Dep, q_Del)."""
    return engine.metrics()


# ── AUTHORING (each desugars to the 12-signal FSM — logged, no bypass) ────────

def create_task(engine: Engine, task_id: str = "", spec: Optional[dict] = None, assignee: str = "human",
                parent_id: Optional[str] = None, deadline: Optional[str] = None) -> Optional[dict]:
    """Create a node. Desugars to ASSIGN (creation IS the ASSIGN effect, logged). `task_id` auto-generated if
    omitted; `deadline` = an ISO-8601 string (completes T=(spec,criteria,deadline), §2.2). spec =
    {name: short title (≤6 words), description: the full text, criteria: [{name, description}], neglected: [...]}."""
    import uuid
    from datetime import datetime
    tid = TaskId(task_id or uuid.uuid4().hex[:8])
    dl = datetime.fromisoformat(deadline) if deadline else None
    t = engine.assign_task(tid, _spec_from(spec or {}), AgentId(assignee),
                           parent_id=TaskId(parent_id) if parent_id else None, deadline=dl)
    return _task_out(t)


def decompose(engine: Engine, parent_id: str, children: list[dict],
              mappings: Optional[list[dict]] = None) -> list[dict]:
    """Break a node into children. Desugars to one ASSIGN per child; each child's `covers` declares which
    parent criteria it satisfies (mapping = logged effect). children: [{task_id, spec, assignee}]."""
    kids = [(TaskId(c["task_id"]), _spec_from(c["spec"]), AgentId(c["assignee"])) for c in children]
    maps = [CriterionMapping(m["criterion_name"], TaskId(m["child_id"])) for m in (mappings or [])] or None
    return [_task_out(t) for t in engine.decompose_task(TaskId(parent_id), kids, maps)]


def revise(engine: Engine, task_id: str, spec: dict, agent: str) -> Optional[dict]:
    """Revise a node's whole spec. Canon v3.7 Inv-1: a spec change = re-ASSIGN under the SAME id → REVIEW
    (NOT a CANCEL — no cascade, no tombstone; the executor re-ACCEPTs the new contract). The subtree is
    RETAINED (revision ≠ abandonment); if a criteria change strands a child's coverage it shows up as a
    CHECK-1/CHECK-1b failure to resolve. `agent` must be the issuer (ASSIGN is an issuer signal)."""
    return _task_out(engine.revise(TaskId(task_id), _spec_from(spec), AgentId(agent)))


def reneglect(engine: Engine, task_id: str, neglected: list, agent: str) -> Optional[dict]:
    """Replace a node's NEGLECTED (the RISK register: events with a materialization P — a scope boundary
    belongs in the goal's criteria, not here), carry the rest. RMW over revise. Each item:
    {item, predictability: ORDINARY|STATISTICAL|EXTRAORDINARY, justification, invalidation_condition} —
    the predictability verdict is mandatory per factor on a decomposed node (CHECK-4 record form)."""
    return _task_out(engine.reneglect(TaskId(task_id), _neglected_from(neglected), AgentId(agent)))


def edit_criteria(engine: Engine, task_id: str, criteria: list[dict], agent: str) -> Optional[dict]:
    """Replace a node's criteria, carry the rest. RMW over revise. (Dep criteria use `depends_on`.)"""
    crits = tuple(Criteria(c["name"], c.get("description", ""),
                           depends_on=TaskId(c["depends_on"]) if c.get("depends_on") else None)
                  for c in criteria)
    return _task_out(engine.edit_criteria(TaskId(task_id), crits, AgentId(agent)))


def reassign(engine: Engine, task_id: str, assignee: str) -> Optional[dict]:
    """Change a node's executor (Del). Canon Inv-1 fixes Del at ASSIGN → a change = revision: re-ASSIGN
    (same id) carrying the new executor (the issuer acts; the subtree is retained — no cascade)."""
    return _task_out(engine.reassign(TaskId(task_id), AgentId(assignee)))


def add_dependency(engine: Engine, from_id: str, to_id: str, glue: str = "") -> dict:
    """Declare `to_id depends on from_id`'s output. Dep is criteria-content (§2.2): desugars to a
    re-author of the CONSUMER adding the glue criterion; the edge is derived. Cycle → rejected."""
    engine.add_dependency(TaskId(from_id), TaskId(to_id), glue=glue)
    return {"ok": True, "from": from_id, "to": to_id}


def remove_dependency(engine: Engine, from_id: str, to_id: str) -> dict:
    """Drop a dependency (re-authors the consumer to remove the glue criterion)."""
    engine.remove_dependency(TaskId(from_id), TaskId(to_id))
    return {"ok": True}


def map_criterion(engine: Engine, parent_id: str, child_id: str, criterion_name: str) -> Optional[dict]:
    """Bind an EXISTING child to a parent criterion (add/repair the coverage mapping). Use this when a child
    covers a parent criterion but wasn't mapped at decompose time, or when a re-authored parent criterion left
    a child's mapping dangling (CHECK-1). `decompose` maps only NEW children — this is the post-hoc verb."""
    return _task_out(engine.map_criterion(TaskId(parent_id), TaskId(child_id), criterion_name))


def signal(engine: Engine, task_id: str, signal: str, source: str, **payload) -> dict:
    """Send a raw protocol signal (the lifecycle transaction): ACCEPT / DELIVER / PASS / FAIL / BLOCK /
    RESOLVE_BLOCK / CHALLENGE / ACCEPT_CHALLENGE / REJECT_CHALLENGE / CANCEL / CANCEL_ACK. The lower-layer
    primitive. CANCEL opens the two-step abandon handshake (→ CANCELLING); the executor settles it with
    CANCEL_ACK (pass `in_flight` = the state of work at cancellation) → CANCELLED. BLOCK on an undeclared
    prerequisite that is an EXISTING node: pass `blocker_task_id` — it records a provisional discovered-Dep
    edge (feeds q_Dep); RESOLVE_BLOCK then confirms it (default), re-attributes (`blocker_task_id`), or
    retracts it (`external=true` — the blocker had no producer node)."""
    entry = engine.send_signal_sync(SignalData(
        signal=Signal[signal], task_id=TaskId(task_id), source=AgentId(source),
        reason=payload.get("reason"), result=payload.get("result"),
        justification=payload.get("justification"), action=payload.get("action"),
        in_flight=payload.get("in_flight"),
        blocker_task_id=TaskId(payload["blocker_task_id"]) if payload.get("blocker_task_id") else None,
        external=bool(payload.get("external", False)),
        failed_criteria=tuple(payload.get("failed_criteria", ()))))
    st = engine.get_state(TaskId(task_id))
    ok = bool(entry and not entry.rejected)
    out = {"accepted": ok, "state": st.name if st else None}
    if not ok:
        # Feedback, not a silent false: WHY it was rejected + the structural gate the executor can't see.
        reason = (entry.error if entry and entry.error else
                  f"{signal} is not valid in state {st.name if st else '?'} — "
                  f"valid here: {[s.name for s in engine.available_actions(TaskId(task_id))]}")
        fails = [f"{c.check_name}: {c.details}" for c in engine.get_checks(TaskId(task_id))
                 if not c.passed and not c.skipped]
        out["error"] = reason
        if fails:
            out["failing_checks"] = fails
    return out


def validate(engine: Engine, task_id: str, model: str = "sonnet") -> dict:
    """Validate a node's decomposition: the STRUCTURAL gate (L0/L1: coverage, DAG, glue, non-redundancy —
    fails ⇒ fix those first) + the SEMANTIC hole-hunt: one headless subagent SEARCH in diff mode over the
    node's projection → `semantic_covered` (the space is covered) or `semantic_findings` (what's missing —
    ADVISORY: fix via the FSM verbs or consciously declare NEGLECTED; it never auto-fixes). Use on
    externally-authored or hand-edited graphs; fresh auto_decompose graphs had this hunt at build time."""
    from gfso.runtime import llm_factory
    from gfso.decompose.loop import _stat_line

    def _cb(msg: str) -> None:  # same observation field as decompose (UI pipeline log)
        try:
            engine.emit_info("validate", msg)
        except Exception:
            pass

    llm = llm_factory(model)
    llm.on_tick = _cb
    llm.stage_hint = f"{task_id} validator"
    _cb(f"{task_id}: semantic hole-hunt (search-diff over the projection)…")
    out = asdict(engine.validate_decomposition(TaskId(task_id), llm=llm))
    out["stats"] = list(llm.calls)
    verdict = ("gate FAILED — fix L0/L1 first" if not out.get("gate_passed")
               else "ALREADY-COVERED" if out.get("semantic_covered")
               else "advisory findings returned" if out.get("semantic_covered") is False
               else "no semantic verdict")
    _cb(f"{task_id}: {verdict} · validator {_stat_line(llm)}")
    return out


def next_step(engine: Engine, root_id: Optional[str] = None) -> dict:
    """The EXECUTION forcing-point — call this in a LOOP and do EXACTLY what `directive` says, until it
    returns complete=True. It hands you the single next required action for the current frontier node
    (children before parents): accept / execute / deliver / validate / rework / cancel_ack. You CANNOT stop
    until the root is DONE/PASS — the graph drives, you execute. Returns {complete, task_id, name, state,
    action, criteria, directive}. For PARALLEL delegation to executor subagents use next_steps instead."""
    return engine.next_step(TaskId(root_id) if root_id else None)


def next_steps(engine: Engine, root_id: Optional[str] = None) -> dict:
    """The PARALLEL frontier: EVERY currently actionable node at once, priority-ordered. Steps with
    parallel_ok=true are independent execute-leaves (their Dep producers PASSED) — delegate each to its own
    executor subagent CONCURRENTLY. Do the non-parallel steps (accept/validate/rework/resolve/deliver)
    yourself in the returned order. Loop until complete=True (root DONE/PASS). Returns {complete, steps}."""
    return engine.next_steps(TaskId(root_id) if root_id else None)


def auto_decompose(engine: Engine, request: str, root_id: str = "root", assignee: str = "human",
                   depth: int = 1, model: str = "sonnet", _progress=None) -> dict:
    """Author a real GFSO subtree from `request` in ONE call: runs the search↔audit refinement (`depth` =
    iterations, the quality dial — 1 for a simple task), builds the result INTO the live CORE through the
    FSM wholesale, then VERIFIES: list_holes + unplaced-item check with a bounded repair loop, so the
    returned graph is structurally valid — or `holes` reports the honest residue (never a silent partial).
    The decomposer OWNS the root's criteria: an existing root's hand-written criteria are re-authored to
    the derived V-set (name/description preserved). Runs on headless subscription-billed Sonnet one-shots.
    Prefer this over reasoning the graph node-by-node — that under-covers and burns tokens."""
    from gfso.decompose import decompose_into

    def _cb(msg: str) -> None:  # fan out: transport channel (MCP notifications) + the live UI strip
        try:
            engine.emit_info("decompose", msg)
        except Exception:
            pass
        if _progress is not None:
            _progress(msg)

    res = decompose_into(engine, request, root_id=root_id, assignee=assignee, depth=depth, model=model,
                         progress=_cb)
    kids = engine.get_active_children(res.root_id)
    return {"root_id": str(res.root_id),
            "subtasks": [{"id": str(c.id), "description": c.spec.description} for c in kids],
            "holes": res.holes,
            "stats": res.stats,
            "basis_markdown": res.d_md}


# Registry: name -> function. The server registers these; tests call them directly.
TOOLS = {
    "get_task": get_task, "project": project, "get_checks": get_checks, "get_graph": get_graph,
    "list_holes": list_holes,
    "available_actions": available_actions, "get_dependencies": get_dependencies, "metrics": metrics,
    "create_task": create_task, "decompose": decompose, "auto_decompose": auto_decompose,
    "revise": revise, "reneglect": reneglect, "edit_criteria": edit_criteria, "reassign": reassign,
    "add_dependency": add_dependency, "remove_dependency": remove_dependency, "map_criterion": map_criterion,
    "signal": signal, "validate": validate, "next_step": next_step, "next_steps": next_steps,
}
