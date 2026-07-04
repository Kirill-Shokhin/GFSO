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
    """(Per-node detail — `list_holes` covers the whole graph at once.) The L0/L1 structural checks (compiler-style: coverage / DAG / anti-mock / sufficiency …)."""
    return [{"check": c.check_name, "passed": c.passed, "details": c.details, "skipped": c.skipped}
            for c in engine.get_checks(TaskId(task_id))]


def available_actions(engine: Engine, task_id: str, agent: Optional[str] = None) -> list[str]:
    """(Rarely needed — next_steps' directive already names the required action.) The protocol signals valid in this node's state for this agent's role."""
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

def _agent_id() -> str:
    """The calling agent's standing identity. Identity is TRANSPORT-derived, not configured: this tool
    surface (MCP/CLI) is the AGENT's single entry point — the UI is the human's door and always passes an
    explicit name — so an omitted `assignee` can only mean "the agent itself". Works out of the box as
    `agent`; GFSO_AGENT_ID merely RENAMES it (multi-agent future), it is never required."""
    import os
    return os.environ.get("GFSO_AGENT_ID") or "agent"


def create_task(engine: Engine, task_id: str = "", spec: Optional[dict] = None,
                assignee: Optional[str] = None,
                parent_id: Optional[str] = None, deadline: Optional[str] = None) -> Optional[dict]:
    """Create a node. Desugars to ASSIGN (creation IS the ASSIGN effect, logged). `task_id` auto-generated if
    omitted; `deadline` = an ISO-8601 string (completes T=(spec,criteria,deadline), §2.2). spec =
    {name: short title (≤6 words), description: the full text, criteria: [{name, description}], neglected: [...]}.
    `assignee` (Del) defaults to `agent` = YOU (this tool surface is the agent's door; the UI is the
    human's and always names its user) — omit it when you will execute the node yourself; name someone
    else ONLY when delegating for real (the FSM then rejects your executor signals on that node)."""
    import uuid
    from datetime import datetime
    tid = TaskId(task_id or uuid.uuid4().hex[:8])
    dl = datetime.fromisoformat(deadline) if deadline else None
    t = engine.assign_task(tid, _spec_from(spec or {}), AgentId(assignee or _agent_id()),
                           parent_id=TaskId(parent_id) if parent_id else None, deadline=dl)
    return _task_out(t)


def decompose(engine: Engine, parent_id: str, children: list[dict],
              mappings: Optional[list[dict]] = None) -> list[dict]:
    """(Manual path — `auto_decompose` is the normal way to structure.) Break a node into children. Desugars to one ASSIGN per child; each child's `covers` declares which
    parent criteria it satisfies (mapping = logged effect). children: [{task_id, spec, assignee}];
    an omitted assignee = `agent` (you execute it yourself; name someone only to really delegate)."""
    kids = [(TaskId(c["task_id"]), _spec_from(c["spec"]),
             AgentId(c.get("assignee") or _agent_id())) for c in children]
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


def signal(engine: Engine, task_id: str, signal: str, source: str,
           reason: Optional[str] = None, result: Optional[str] = None,
           justification: Optional[str] = None, action: Optional[str] = None,
           in_flight: Optional[str] = None, blocker_task_id: Optional[str] = None,
           external: bool = False, failed_criteria: Optional[list] = None) -> dict:
    """Send a raw protocol signal (the lifecycle transaction): ACCEPT / DELIVER / PASS / FAIL / BLOCK /
    RESOLVE_BLOCK / CHALLENGE / ACCEPT_CHALLENGE / REJECT_CHALLENGE / CANCEL / CANCEL_ACK. The lower-layer
    primitive. Signals are SIGNED AS YOU automatically (`agent` — the MCP door pins the source;
    impersonation is impossible), and the FSM validates the ROLE: executor signals require the node's
    Del == you, issuer signals require the parent's Del == you — a node delegated to someone else only
    moves on THEIR signals. DELIVER carries `result` (paths + how each criterion is met — the
    validator's input).
    FAIL requires `failed_criteria` (Inv-3). CANCEL opens the two-step abandon handshake (→ CANCELLING);
    the executor settles it with CANCEL_ACK (pass `in_flight` = the state of work at cancellation) →
    CANCELLED. BLOCK on an undeclared prerequisite that is an EXISTING node: pass `blocker_task_id` — it
    records a provisional discovered-Dep edge (feeds q_Dep); RESOLVE_BLOCK then confirms it (default),
    re-attributes (`blocker_task_id`), or retracts it (`external=true` — no producer node)."""
    entry = engine.send_signal_sync(SignalData(
        signal=Signal[signal], task_id=TaskId(task_id), source=AgentId(source),
        reason=reason, result=result,
        justification=justification, action=action,
        in_flight=in_flight,
        blocker_task_id=TaskId(blocker_task_id) if blocker_task_id else None,
        external=bool(external),
        failed_criteria=tuple(failed_criteria or ())))
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


# The validator's report contract (parsed, never trusted): verdict PASS ⟺ every criterion passes;
# failed_criteria = exactly what the issuer passes to FAIL. Inv-3: a FAIL is never criteria-less.
_VALIDATOR_SCHEMA = {
    "type": "object",
    "properties": {
        "verdict": {"type": "string", "enum": ["PASS", "FAIL"]},
        "per_criterion": {"type": "array", "items": {
            "type": "object",
            "properties": {"criterion": {"type": "string"},
                           "verdict": {"type": "string", "enum": ["pass", "fail", "undecidable"]},
                           "evidence": {"type": "string"}},
            "required": ["criterion", "verdict", "evidence"]}},
        "seams": {"type": "string"},
        "failed_criteria": {"type": "array", "items": {"type": "string"}},
    },
    "required": ["verdict", "per_criterion", "failed_criteria"],
}


def _last_deliver_result(engine: Engine, task_id: TaskId) -> Optional[str]:
    stored = engine._graph._storage.get_deliver_result(task_id)   # persisted on DELIVER — survives restarts
    if stored:
        return stored
    for e in reversed(engine.audit_log(task_id)):                 # in-memory fallback (older DBs)
        if e.signal == Signal.DELIVER and not e.rejected and e.result:
            return e.result
    return None


def _validator_packet(engine: Engine, task, deliverable: str, workdir: Optional[str]) -> str:
    """The validator's self-contained input: contract + seams + NEGLECTED + the DELIVER report.
    Embedded by the system — the validator has no graph access (read-only instrument, §6.5)."""
    import os
    tid = str(task.id)
    crits = "\n".join(f"- **{c.name}**: {c.description}" for c in task.spec.criteria) or "- (none)"
    ups = []
    for e in engine.get_dependencies():
        if str(e.to_id) == tid:
            prod = engine.get_task(TaskId(e.from_id))
            name = prod.spec.name or prod.spec.description[:40] if prod else "?"
            state = prod.state.name if prod else "?"
            ups.append(f"- consumes `{e.from_id}` ({name}, state {state})"
                       + (f" — glue: {e.glue}" if e.glue else ""))
    negl = "\n".join(f"- {n.item}" for n in task.spec.neglected)
    return (f"# Node under validation: {tid} — {task.spec.name}\n\n{task.spec.description}\n\n"
            f"## Contract — the criteria (the ENTIRE obligation; use these EXACT names in your report)\n"
            f"{crits}\n\n"
            f"## Upstream dependencies (seams — check against the REAL producer output, not a stub)\n"
            f"{chr(10).join(ups) or '- none'}\n\n"
            f"## NEGLECTED (declared assumptions of the plan — do NOT fail for these)\n"
            f"{negl or '- none'}\n\n"
            f"## Executor's DELIVER report (where the work lives, how each criterion is claimed met)\n"
            f"{deliverable}\n\n"
            f"Working directory for your tools: {workdir or os.getcwd()}\n")


def validate_node(engine: Engine, task_id: str, deliverable: Optional[str] = None,
                  model: str = "sonnet", workdir: Optional[str] = None,
                  _llm=None, _progress=None) -> dict:
    """Validate EXECUTION (≠ `validate`, which checks the decomposition PLAN): spawn ONE independent
    read-only validator agent (Read/Bash/Glob/Grep — it RUNS tests; executed evidence outranks judgment)
    against the node's criteria + the executor's DELIVER report, returning per-criterion verdicts and
    `failed_criteria`. Call it while the node is VALIDATING, after every delivery. This tool is the
    EVIDENCE INSTRUMENT — it never signals: YOU (the issuer) read the report and send PASS or
    FAIL(failed_criteria=...) yourself (verifier = issuer, §6.5; the validator is a fresh context, never
    the work's executor). `deliverable` defaults to the node's last DELIVER result from the audit log —
    pass it explicitly if the server restarted since delivery. `verdict: null` = the validator's report
    did not parse; NEVER read that as pass — the raw report_text is attached for your own judgment."""
    from gfso.runtime import llm_factory
    from gfso.decompose.loop import _stat_line
    from gfso.adapters.llm.structured import schema_instruction, parse_structured
    from pathlib import Path

    task = engine.get_task(TaskId(task_id))
    if task is None:
        return {"error": f"unknown task {task_id}"}
    deliverable = deliverable or _last_deliver_result(engine, TaskId(task_id))
    if not deliverable:
        return {"error": f"nothing to validate: {task_id} has no recorded DELIVER result — "
                         f"pass `deliverable` explicitly (state {task.state.name})"}

    def _cb(msg: str) -> None:  # same observation field as decompose/validate (UI pipeline log)
        try:
            engine.emit_info("validate_node", msg)
        except Exception:
            pass
        if _progress is not None:
            _progress(msg)

    llm = _llm or llm_factory(model)
    if not hasattr(llm, "run_agent"):
        return {"error": "validate_node needs the headless agent-runner (Anthropic transport); "
                         "GFSO_PROVIDER=generic covers zero-tool one-shots only"}
    llm.on_tick = _cb
    llm.stage_hint = f"{task_id} node-validator"
    _cb(f"{task_id}: independent validator (read-only agent) over the deliverable…")
    system = (Path(__file__).parent / "mcp" / "prompts" / "validator.md").read_text(encoding="utf-8")
    packet = _validator_packet(engine, task, deliverable, workdir)
    text = llm.run_agent(system, packet + schema_instruction(_VALIDATOR_SCHEMA),
                         allowed_tools=("Read", "Bash", "Glob", "Grep"), cwd=workdir)
    if hasattr(llm, "tag_last"):
        llm.tag_last("validate_node")
    out: dict = {"task_id": task_id, "state": task.state.name, "stats": list(getattr(llm, "calls", []))}
    parsed = parse_structured(text, _VALIDATOR_SCHEMA)
    if parsed is None:
        # No retry: an agent run is minutes-long; the raw report is still evidence for the issuer.
        if getattr(llm, "calls", None):
            llm.calls[-1]["parse_failed"] = True
        out.update({"verdict": None, "report_text": text})
        _cb(f"{task_id}: validator report did not parse (verdict=null) · {_stat_line(llm)}")
        return out
    out.update({"verdict": parsed["verdict"], "per_criterion": parsed["per_criterion"],
                "failed_criteria": list(parsed["failed_criteria"]), "seams": parsed.get("seams", "")})
    try:  # the recorded verdict is what unlocks a self-executed node's PASS (verifier ≠ executor gate)
        engine.record_exec_verdict(TaskId(task_id), parsed["verdict"],
                                   list(parsed["failed_criteria"]), "validate_node")
    except Exception:
        pass
    _cb(f"{task_id}: validator verdict {parsed['verdict']}"
        + (f" — failed: {', '.join(parsed['failed_criteria'])}" if parsed["failed_criteria"] else "")
        + f" · {_stat_line(llm)}")
    return out


_EXECUTOR_ACTIONS = ("accept", "execute", "deliver", "rework", "cancel_ack")


def _mark_mine(out: dict) -> dict:
    """Del is LOAD-BEARING on the frontier, not a label: every step carries `mine` (the calling agent is
    the node's executor), and a FOREIGN executor-step's directive is rewritten to hands-off — the FSM
    would reject your executor signals on it anyway (source ≠ Del is a validation error). Foreign steps
    stay VISIBLE (that is the point: you see what the graph waits on)."""
    me = _agent_id()
    for s in (out.get("steps") or ([out] if out.get("task_id") else [])):
        a = s.get("assignee")
        s["mine"] = (a == me) or not a
        if not s["mine"] and s.get("action") in _EXECUTOR_ACTIONS:
            s["directive"] = (f"NOT YOURS (Del={a}) — do NOT execute or signal for it; the graph WAITS "
                              f"for that executor (a human via the UI, an external system by its own "
                              f"signals). Work your `mine` steps; surface this one to the user if the "
                              f"wait blocks you. | contract was: " + s.get("directive", ""))
    return out


def next_step(engine: Engine, root_id: Optional[str] = None) -> dict:
    """(Single-step view — `next_steps` is the PRIMARY driver; prefer it.) The EXECUTION forcing-point — call this in a LOOP and do EXACTLY what `directive` says, until it
    returns complete=True. It hands you the single next required action for the current frontier node
    (children before parents): accept / execute / deliver / validate / rework / cancel_ack. You CANNOT stop
    until the root is DONE/PASS — the graph drives, you execute. Returns {complete, task_id, name, state,
    action, assignee, mine, criteria, directive}; `mine=false` = the node belongs to ANOTHER executor
    (human/external) — hands off, it waits for them. For PARALLEL delegation use next_steps."""
    return _mark_mine(engine.next_step(TaskId(root_id) if root_id else None))


def next_steps(engine: Engine, root_id: Optional[str] = None) -> dict:
    """The PARALLEL frontier: EVERY currently actionable node at once, priority-ordered. Steps with
    parallel_ok=true are independent execute-leaves (their Dep producers PASSED) — delegate each to its own
    executor subagent CONCURRENTLY. Do the non-parallel steps (accept/validate/rework/resolve/deliver)
    yourself in the returned order; `mine=false` steps belong to OTHER executors (human/external) — visible
    but hands-off. Loop until complete=True (root DONE/PASS). Returns {complete, steps}."""
    return _mark_mine(engine.next_steps(TaskId(root_id) if root_id else None))


def auto_decompose(engine: Engine, request: str, root_id: str = "root",
                   assignee: Optional[str] = None,
                   depth: int = 1, model: str = "sonnet", fast: bool = False, _progress=None) -> dict:
    """Author a real GFSO subtree from `request` in ONE call: runs the search↔audit refinement (`depth` =
    iterations, the quality dial — 1 for a simple task), builds the result INTO the live CORE through the
    FSM wholesale, then VERIFIES: list_holes + unplaced-item check with a bounded repair loop, so the
    returned graph is structurally valid — or `holes` reports the honest residue (never a silent partial).
    The decomposer OWNS the root's criteria: an existing root's hand-written criteria are re-authored to
    the derived V-set (name/description preserved). Runs on headless subscription-billed Sonnet one-shots.
    `fast=true` on SIMPLE tasks: measured pace-suffixes, ~1.5× faster / ~40% fewer tokens with the same
    structural shape (frozen prompt cores untouched). Prefer this over reasoning the graph node-by-node —
    that under-covers and burns tokens."""
    from gfso.decompose import decompose_into

    def _cb(msg: str) -> None:  # fan out: transport channel (MCP notifications) + the live UI strip
        try:
            engine.emit_info("decompose", msg)
        except Exception:
            pass
        if _progress is not None:
            _progress(msg)

    res = decompose_into(engine, request, root_id=root_id, assignee=assignee or _agent_id(),
                         depth=depth, model=model, fast=fast, progress=_cb)
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
    "signal": signal, "validate": validate, "validate_node": validate_node,
    "next_step": next_step, "next_steps": next_steps,
}
