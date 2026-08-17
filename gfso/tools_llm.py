"""The LLM half of the action surface — the verbs that SPAWN model runs.

Split from `gfso.tools` (the structural half, L1: core+engine only) so the structural surface
carries zero LLM/adapter dependencies — this module is L2 and pulls decompose/critic/runtime
freely. Same contract as tools.py: pure functions `(engine, *args) -> JSON-able dict`.

`TOOLS` here is the COMPLETE transport registry (structural ∪ LLM) — the binding layers
(MCP / CLI / HTTP) generate their surfaces from THIS dict; `gfso.tools.TOOLS` stays the
structural subset.
"""
from __future__ import annotations

import time
from dataclasses import asdict
from typing import Optional

from gfso.core.types import TaskId, Signal
from gfso.engine import Engine
from gfso import tools as _tools
from gfso.tools import _agent_id


# WHAT THIS PROCESS IS DOING RIGHT NOW, by verb name. Read by `/api/runtime`, so that a reconcile
# arriving from another session can see there is work in flight and decline to restart the server
# out from under it — a killed server does not take its `claude` children with it.
# A COUNTER, not a set. As a set, the first of two concurrent `validate_result` calls to finish
# cleared the flag while the second was still running — and every tool now runs in its own thread,
# so concurrent calls of one verb are ordinary rather than impossible.
INFLIGHT: "collections.Counter[str]" = __import__("collections").Counter()


def _inflight(name: str):
    import contextlib
    lock = _INFLIGHT_LOCK

    @contextlib.contextmanager
    def _track():
        with lock:
            INFLIGHT[name] += 1
        try:
            yield
        finally:
            with lock:
                INFLIGHT[name] -= 1
                if INFLIGHT[name] <= 0:
                    del INFLIGHT[name]
    return _track()


_INFLIGHT_LOCK = __import__("threading").Lock()


def review_decomposition(engine: Engine, task_id: str, model: str = "sonnet") -> dict:
    """Validate a node's decomposition: the STRUCTURAL gate (L0/L1: coverage, DAG, glue, non-redundancy —
    fails ⇒ fix those first) + the L2 CHECKER (canon §13.4 Level 2): one zero-tool call judging, per
    parent criterion, whether the mapped children's criteria — taken as real-world facts — CAUSALLY
    guarantee it (sufficient / insufficient-with-named-gap / uncertain), plus semantic FM-2 conflicts
    the formal CHECK-8 can't see. ADVISORY: never auto-fixes — fix via the FSM verbs or consciously
    declare ACCEPTED_RISKS. The hole-hunt («what's missing from the space») is NOT this verb — that is the
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
    engine.record_llm_usage("l2_review", llm, TaskId(task_id))   # what the check cost, on the record
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
                           "evidence": {"type": "string"},
                           # What the criterion NAMES, enumerated. A criterion is routinely a
                           # conjunction ("N/P/D loops, hold-space accumulation across the whole
                           # input, and multi-line address ranges"), and one probe over one conjunct
                           # passes it while another is broken. Measured: a root closed DONE on
                           # exactly that — the probe was honest and reproduced, it simply covered
                           # one behaviour of three, and the untested one failed against real sed.
                           # Reproducibility is not coverage; the canon leaves this to runtime
                           # (§6.3: prohibition has no form guard, only FM-3 at runtime), so runtime
                           # is where it is demanded.
                           "behaviours": {"type": "array", "items": {"type": "string"},
                                          "description": "each distinct behaviour this criterion "
                                                         "requires — one entry per conjunct, in the "
                                                         "criterion's own words"},
                           # The claim must be RE-RUNNABLE, on the PASS side as much as the FAIL
                           # side: the measurement's load-bearing direction is the false PASS.
                           # ONE PROBE PER BEHAVIOUR, in the same order.
                           "probe": {"type": "array", "items": {"type": "object", "properties": {
                               # Re-runnable BY SOMEONE ELSE, against the artifact as delivered.
                               # Measured: validators copy the delivery into a scratch directory
                               # under a new name and then cite that name (`from md_real import …`)
                               # with an absolute path to their own interpreter — commands that run
                               # for them and for nobody else. A probe only the issuer can execute
                               # is not evidence, it is a claim about a claim.
                               "command": {"type": "string", "description":
                                           "the exact shell command you RAN, re-runnable AS-IS by "
                                           "someone else in the delivered artifact's own directory: "
                                           "name the delivered files as THEY are named (not your "
                                           "scratch copies), and invoke `python`/`pytest` plainly "
                                           "rather than by an absolute path to your interpreter "
                                           "(e.g. `python -c \"import md; "
                                           "print(md.parse_blocks('a\\n\\nb'))\"`)"},
                               "expect": {"type": "string", "description":
                                          "what its output must show for this verdict to hold — a "
                                          "substring of the real output, not a paraphrase"}},
                               "required": ["command", "expect"]}}},
            "required": ["criterion", "verdict", "evidence", "behaviours", "probe"]}},
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


def _validator_packet(engine: Engine, task, deliverable: str, workdir: Optional[str],
                      scratch: Optional[str] = None) -> str:
    """The validator's self-contained input: contract + seams + ACCEPTED_RISKS + the DELIVER report.
    Embedded by the system — the validator has no graph access (read-only instrument, §14.5)."""
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
    negl = "\n".join(f"- {n.item}" for n in task.spec.accepted_risks)
    return (f"# Node under validation: {tid} — {task.spec.name}\n\n{task.spec.description}\n\n"
            f"## Contract — the criteria (the ENTIRE obligation; use these EXACT names in your report)\n"
            f"{crits}\n\n"
            f"## Upstream dependencies (seams — check against the REAL producer output, not a stub)\n"
            f"{chr(10).join(ups) or '- none'}\n\n"
            f"## ACCEPTED_RISKS (declared assumptions of the plan — do NOT fail for these)\n"
            f"{negl or '- none'}\n\n"
            f"## Executor's DELIVER report (where the work lives, how each criterion is claimed met)\n"
            f"{deliverable}\n\n"
            f"Working directory for your tools: {workdir}\n"
            + (f"A private scratch directory, fresh for THIS validation, if you need to copy the "
               f"delivery before importing or rewriting it: {scratch}\n" if scratch else ""))


def validate_result(engine: Engine, task_id: str, deliverable: Optional[str] = None,
                  model: str = "sonnet", workdir: Optional[str] = None,
                  _llm=None, _progress=None) -> dict:
    """Validate EXECUTION (≠ `review_decomposition`, which checks the decomposition PLAN): spawn ONE independent
    read-only validator agent (Read/Bash/Glob/Grep — it RUNS tests; executed evidence outranks judgment)
    against the node's criteria + the executor's DELIVER report, returning per-criterion verdicts and
    `failed_criteria`. Call it while the node is VALIDATING, after every delivery. This tool is the
    EVIDENCE INSTRUMENT — it never signals: YOU (the issuer) read the report and send PASS or
    FAIL(failed_criteria=...) yourself (verifier = issuer, §14.5; the validator is a fresh context, never
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
    # D6 (§14.5): independent validation belongs at the SEAM (a root, or Del(child)≠Del(parent)).
    # An INTERNAL node self-verifies (its DELIVER carries self_validation) and its guarantee is
    # carried by the root's validation (Thm 1) — so spawning a validator here is pure overhead. Enforced
    # in the engine, not the prompt (measured live: a Haiku agent ran a validator on every internal
    # child despite the protocol telling it not to — visibility ≠ enforcement). The GFSO_VALIDATE_INTERNAL
    # dial restores every-node validation for measurement runs.
    import os as _os
    if (_os.environ.get("GFSO_VALIDATE_INTERNAL", "") in ("", "0")
            and not engine._graph.is_public(task)):
        return {"task_id": task_id, "state": task.state.name, "internal": True, "verdict": None,
                "note": "internal node (same Del as its parent) — no independent validation needed "
                        "(D6/§14.5): self-verify by running its check yourself, put the evidence in the "
                        "DELIVER self_validation, and PASS it directly. Independent validation happens "
                        "once, at the root/seam."}
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
    generation = engine.generation_of(TaskId(task_id))   # the delivery THIS run reads (§14.5 gate)
    inflight_key = engine.begin_validation(TaskId(task_id))
    if inflight_key is None:
        return {"task_id": task_id, "state": task.state.name, "inflight": True,
                "note": "a validator run is already in flight for this node generation "
                        "(node, iteration, reopens) — duplicate spawn suppressed"}
    try:
        llm.on_tick = _cb
        llm.stage_hint = f"{task_id} node-validator"
        _cb(f"{task_id}: independent validator (read-only agent) over the deliverable…")
        system = (Path(__file__).parent / "mcp" / "prompts" / "validator.md").read_text(encoding="utf-8")
        # The validator runs WHERE THE WORK IS, and gets a private scratch BESIDE it.
        #
        # Two needs had been collapsed into one. The scratch exists because a validator copies a
        # delivery next to itself before importing it, and a SHARED scratch let one run judge
        # another's leftovers — measured: a verdict citing a module written three days earlier by a
        # different run, PASS on an artifact failing most of its visible tests. The fix made that
        # scratch the working DIRECTORY, and so the validator opened in an empty one: it could not
        # see the delivery at all and failed correct work, stating as its evidence that nothing was
        # there. Measured on a one-criterion delivery that ran correctly: FAIL, "the working
        # directory is empty".
        #
        # A false FAIL at the seam is worse than no validation — it sends good work to REWORKING and
        # escalates a finished root at the iteration limit. So the working directory is the
        # deliverable's own, and the fresh scratch is offered by name, for copies.
        scratch = None
        if workdir:
            # One dotted directory rather than a loose `<task>_<epoch>/` per validation littering
            # the tree being judged.
            root = Path(workdir) / ".gfso-scratch"
            scratch = str(root / f"{task_id}_{int(time.time())}")
            Path(scratch).mkdir(parents=True, exist_ok=True)
            # Keep the recent ones (a verdict's evidence is worth reading after the fact) and drop
            # the rest: one directory per validation, inside the repository being judged, otherwise
            # accumulates for the life of the project — a rework loop alone makes several.
            import shutil as _sh
            for old_dir in sorted(root.iterdir(), key=lambda d: d.name)[:-20]:
                if old_dir.is_dir():
                    _sh.rmtree(old_dir, ignore_errors=True)
        packet = _validator_packet(engine, task, deliverable, workdir, scratch)
        try:
            text = llm.run_agent(system, packet + schema_instruction(_VALIDATOR_SCHEMA),
                                 allowed_tools=("Read", "Bash", "Glob", "Grep"), cwd=workdir)
        except ValueError as ex:
            # The transport refuses to spawn an agent with no working directory (it would run in
            # the state home and judge artifacts it cannot see — a WRONG verdict, not a missing
            # one). Reported as a result rather than raised, because the caller is an agent session.
            return {"task_id": task_id, "state": task.state.name, "verdict": None,
                    "error": f"{ex} — call validate_result(task_id, workdir=…)"}
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
                    "failed_criteria": list(parsed["failed_criteria"]), "seams": parsed.get("seams", ""),
                    "tools_used": dict(getattr(llm, "last_tool_calls", None) or {})})
        # Tell the issuer the ONE signal this verdict calls for — the evidence tool never signals, and a
        # bare verdict left agents guessing (observed live: after a FAIL an agent sent PASS from REWORKING,
        # which the FSM refused, and it hung). The directive rides where the agent looks: this reply.
        if parsed["verdict"] == "PASS":
            out["next"] = (f"Now sign it: signal('{task_id}','PASS'). This recorded verdict is what "
                           f"unlocks your PASS at the seam (verifier ≠ executor, §14.5).")
        else:
            out["next"] = (f"Now sign it: signal('{task_id}','FAIL', failed_criteria={list(parsed['failed_criteria'])}). "
                           f"The node returns to REWORKING; then fix EXACTLY those criteria and DELIVER again "
                           f"(do NOT send PASS from REWORKING — re-deliver, and the next validation decides).")
        # A report that contradicts its own evidence or leaves a criterion unspoken is NOT a verdict
        # (§10: V = ⋀ over ALL criteria; ⊥ is not pass) — the engine refuses to record it, and the
        # tool reports verdict=null, which NEVER auto-signals (delegate escalates to the issuer).
        # Measured live: a PASS returned over a red `test_values` excused as "ACCEPTED_RISKS-declared".
        try:  # the recorded verdict is what unlocks a self-executed node's PASS (verifier ≠ executor gate)
            engine.record_exec_verdict(TaskId(task_id), parsed["verdict"],
                                       list(parsed["failed_criteria"]), "validate_result",
                                       per_criterion=parsed["per_criterion"],
                                       tools_used=getattr(llm, "last_tool_calls", None),
                                       # THIS instrument must be re-runnable; a human reviewer's
                                       # record (record_reviewer_verdict) is not held to it.
                                       require_probe=True,
                                       generation=generation)
        except ValueError as e:
            out.update({"verdict": None, "verdict_defects": str(e), "report_text": text})
            _cb(f"{task_id}: validator report is NOT a verdict — {e} · {_stat_line(llm)}")
            return out
        except Exception:
            pass
        _cb(f"{task_id}: validator verdict {parsed['verdict']}"
            + (f" — failed: {', '.join(parsed['failed_criteria'])}" if parsed["failed_criteria"] else "")
            + f" · {_stat_line(llm)}")
        return out
    finally:
        engine.record_llm_usage("validator", llm, TaskId(task_id))   # the judge's own spend, recorded
        engine.end_validation(inflight_key)


def auto_decompose(engine: Engine, request: str = "", root_id: str = "root",
                   assignee: Optional[str] = None,
                   depth: int = 1, model: str = "sonnet", fast: bool = False,
                   max_iterations: Optional[int] = None, _progress=None) -> dict:
    """THE one decomposition verb — dispatched by the target's state (one operation over graph state):
    (a) empty project / undecomposed node → authors a real GFSO subtree from `request` (the root node
    itself is created from the request — no hand create_task needed), builds INTO the live CORE through
    the FSM, VERIFIES (list_holes + bounded repair — honest `holes` residue, never a silent partial),
    then applies depth−1 refine rounds; (b) an ALREADY-decomposed node → `depth` REFINE rounds over what
    exists ("+1 iteration": search over the graph's real projection → fold genuinely new findings →
    rebuild as a verified revision; existing children keep their Del and their own ACCEPTED_RISKS/scope;
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
                         depth=depth, model=model, fast=fast, progress=_cb,
                         # A term of the CONTRACT, chosen per decomposition: how many
                         # rework rounds a node gets before the loop settles (§14.3).
                         max_iterations=max_iterations)
    engine.record_llm_usage("decomposer", res.stats, res.root_id)   # what the plan cost, on the record
    kids = engine.get_active_children(res.root_id)
    out = {"root_id": str(res.root_id),
           "subtasks": [{"id": str(c.id), "description": c.spec.description} for c in kids],
           "holes": res.holes,
           "stats": res.stats,
           "projection": res.d_md}  # the built root's projection markdown — the one canonical read
    if res.note:
        out["note"] = res.note     # e.g. refine over a decomposed node IGNORED the request text
    # No children AND not one completed model call: the provider never answered — unreachable, or
    # unauthenticated. The LLM ports return "" / {} on transport failure by contract, so this arrived
    # as a clean, confident, "verified" empty decomposition — which reads as a statement about the
    # GOAL ("nothing to split") rather than about the installation. It is what a fresh install
    # without credentials hits, on the one verb it is told to start with.
    if not out["subtasks"] and not res.stats:
        out["error"] = ("no subtasks were produced and the model completed no call — the LLM "
                        "provider answered nothing (unreachable, or not authenticated; see the "
                        "server log). A fact about the provider, not about the goal.")
    return out


# The COMPLETE transport registry: structural surface + the LLM verbs. Binding layers use THIS.
def _tracked(name, fn):
    """The three verbs that spawn a model and run for minutes announce themselves in INFLIGHT, so a
    reconcile from another session can see the server is busy and decline to restart it."""
    import functools

    @functools.wraps(fn)
    def wrapper(*a, **kw):
        with _inflight(name):
            return fn(*a, **kw)
    return wrapper


TOOLS = {
    **_tools.TOOLS,
    "auto_decompose": _tracked("auto_decompose", auto_decompose),
    "review_decomposition": _tracked("review_decomposition", review_decomposition),   # L2, §13.4
    "validate_result": _tracked("validate_result", validate_result),                  # §14.1
}
