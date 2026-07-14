"""The LLM half of the action surface — the verbs that SPAWN model runs.

Split from `gfso.tools` (the structural half, L1: core+engine only) so the structural surface
carries zero LLM/adapter dependencies — this module is L2 and pulls decompose/critic/runtime
freely. Same contract as tools.py: pure functions `(engine, *args) -> JSON-able dict`.

`TOOLS` here is the COMPLETE transport registry (structural ∪ LLM) — the binding layers
(MCP / CLI / HTTP) generate their surfaces from THIS dict; `gfso.tools.TOOLS` stays the
structural subset.
"""
from __future__ import annotations

from dataclasses import asdict
from typing import Optional

from gfso.core.types import TaskId, Signal
from gfso.engine import Engine
from gfso import tools as _tools
from gfso.tools import _agent_id


def review_decomposition(engine: Engine, task_id: str, model: str = "sonnet") -> dict:
    """Validate a node's decomposition: the STRUCTURAL gate (L0/L1: coverage, DAG, glue, non-redundancy —
    fails ⇒ fix those first) + the L2 CHECKER (canon §5.4 Level 2): one zero-tool call judging, per
    parent criterion, whether the mapped children's criteria — taken as real-world facts — CAUSALLY
    guarantee it (sufficient / insufficient-with-named-gap / uncertain), plus semantic FM-2 conflicts
    the formal CHECK-8 can't see. ADVISORY: never auto-fixes — fix via the FSM verbs or consciously
    declare NEGLECTED. The hole-hunt («what's missing from the space») is NOT this verb — that is the
    DECOMPOSER's question: run auto_decompose (refine). Use this on externally-authored or hand-edited
    graphs; the UI's «AI review» button is this verb."""
    from gfso.runtime import llm_factory
    from gfso.decompose.loop import _stat_line
    from gfso.critic.runner import review_decomposition
    from gfso.engine.events import emit_cb

    _cb = emit_cb(engine, "review")
    llm = llm_factory(model)
    llm.on_tick = _cb
    llm.stage_hint = f"{task_id} L2-checker"
    _cb(f"{task_id}: L2 checker (causal entailment per parent criterion)…")
    out = asdict(review_decomposition(engine, TaskId(task_id), llm=llm))
    out["stats"] = list(llm.calls)
    verdict = ("gate FAILED — fix L0/L1 first" if not out.get("gate_passed")
               else "no gaps found (advisory)" if out.get("semantic_covered")
               else "gaps/conflicts returned (advisory)" if out.get("semantic_covered") is False
               else "no checker verdict")
    _cb(f"{task_id}: {verdict} · checker {_stat_line(llm)}")
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


def validate_result(engine: Engine, task_id: str, deliverable: Optional[str] = None,
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

    from gfso.engine.events import emit_cb
    _cb = emit_cb(engine, "validate_result", _progress)
    llm = _llm or llm_factory(model)
    if not hasattr(llm, "run_agent"):
        return {"error": "validate_result needs the headless agent-runner (Anthropic transport); "
                         "GFSO_PROVIDER=generic covers zero-tool one-shots only"}
    llm.on_tick = _cb
    llm.stage_hint = f"{task_id} node-validator"
    _cb(f"{task_id}: independent validator (read-only agent) over the deliverable…")
    system = (Path(__file__).parent / "mcp" / "prompts" / "validator.md").read_text(encoding="utf-8")
    packet = _validator_packet(engine, task, deliverable, workdir)
    text = llm.run_agent(system, packet + schema_instruction(_VALIDATOR_SCHEMA),
                         allowed_tools=("Read", "Bash", "Glob", "Grep"), cwd=workdir)
    if hasattr(llm, "tag_last"):
        llm.tag_last("validate_result")
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
                                   list(parsed["failed_criteria"]), "validate_result")
    except Exception:
        pass
    _cb(f"{task_id}: validator verdict {parsed['verdict']}"
        + (f" — failed: {', '.join(parsed['failed_criteria'])}" if parsed["failed_criteria"] else "")
        + f" · {_stat_line(llm)}")
    return out


def auto_decompose(engine: Engine, request: str = "", root_id: str = "root",
                   assignee: Optional[str] = None,
                   depth: int = 1, model: str = "sonnet", fast: bool = False, _progress=None) -> dict:
    """THE one decomposition verb — dispatched by the target's state (one operation over graph state):
    (a) empty project / undecomposed node → authors a real GFSO subtree from `request` (the root node
    itself is created from the request — no hand create_task needed), builds INTO the live CORE through
    the FSM, VERIFIES (list_holes + bounded repair — honest `holes` residue, never a silent partial),
    then applies depth−1 refine rounds; (b) an ALREADY-decomposed node → `depth` REFINE rounds over what
    exists ("+1 iteration": search over the graph's real projection → fold genuinely new findings →
    rebuild as a verified revision; existing children keep their Del and their own NEGLECTED/scope;
    `request` may be omitted — the node's own contract is the request). Recursion = the same verb on a
    child (root_id=<child>). The decomposer OWNS the target node's criteria (re-authored to the derived
    V-set; name/description preserved). Runs on headless subscription-billed Sonnet one-shots.
    `fast=true` on SIMPLE tasks: measured pace-suffixes, ~1.5× faster / ~40% fewer tokens with the same
    structural shape. Prefer this over reasoning the graph node-by-node — that under-covers and burns
    tokens."""
    from gfso.decompose import decompose_into
    from gfso.engine.events import emit_cb

    _cb = emit_cb(engine, "decompose", _progress)
    res = decompose_into(engine, request, root_id=root_id, assignee=assignee or _agent_id(),
                         depth=depth, model=model, fast=fast, progress=_cb)
    kids = engine.get_active_children(res.root_id)
    out = {"root_id": str(res.root_id),
           "subtasks": [{"id": str(c.id), "description": c.spec.description} for c in kids],
           "holes": res.holes,
           "stats": res.stats,
           "projection": res.d_md}  # the built root's projection markdown — the one canonical read
    if res.note:
        out["note"] = res.note     # e.g. refine over a decomposed node IGNORED the request text
    return out


# The COMPLETE transport registry: structural surface + the LLM verbs. Binding layers use THIS.
TOOLS = {
    **_tools.TOOLS,
    "auto_decompose": auto_decompose,
    "review_decomposition": review_decomposition,   # pre-contact L2 review of the PLAN (§5.4)
    "validate_result": validate_result,             # post-contact validation of the RESULT (§6.1)
}
