"""Delegation — the registry-driven autostart machinery (designs §3.1-7 + §7, author-confirmed).

The issuer's ONLY act is setting Del: a node whose assignee is a REGISTERED llm-executor is picked up
from the frontier by the DISPATCHER, which spawns a headless executor (work tools, scoped cwd), wraps
its single structured report into the canonical FSM signals (ACCEPT/DELIVER/BLOCK/CHALLENGE,
source = the executor's id — the executor itself never touches the graph), then AUTO-VALIDATES on
DELIVER→VALIDATING with the registered llm-validator instrument and AUTO-SIGNALS the verdict
(PASS → DONE; FAIL(failed_criteria) → the FSM's own REWORK loop, bounded by max_iterations).
An unparsed validator report NEVER auto-signals — it escalates to the issuer (the one manual point).
Unregistered ids = human = the system stays passive (the safe default); registered NON-executor kinds
never spawn (kind-guard). Identity/authority stays canon-exact: Del binds at delegation, the
executor's own report IS its Inv-1 consent, no second timeout clock (the FSM monitor owns time)."""
from __future__ import annotations

import json
import logging
import os
import threading
import time
from pathlib import Path

from gfso.core.types import TaskId, AgentId, Signal, SignalData

log = logging.getLogger(__name__)

_PROMPTS = Path(__file__).parent / "mcp" / "prompts"
EXECUTOR_TOOLS = ("Read", "Write", "Edit", "Bash", "Glob", "Grep")

EXECUTOR_SCHEMA = {
    "type": "object",
    "properties": {
        "status": {"type": "string", "enum": ["delivered", "blocked", "challenge"]},
        "summary": {"type": "string"},
        "self_validation": {"type": "string"},
        "reason": {"type": "string"},
        "blocker_task_id": {"type": "string"},
        "blocker_task_ids": {"type": "array", "items": {"type": "string"}},
    },
    "required": ["status", "summary"],
}


class AgentRegistry:
    """{agent_id → {kind, model?, workdir?}} — the server-wide roster of NON-human participants.
    kind ∈ llm-executor | llm-validator | external. Persisted as one json file (GFSO_AGENTS_PATH,
    default data/agents.json): survives restarts, editable by hand, no schema migration."""

    def __init__(self, path: str | None = None):
        self._path = Path(path or os.environ.get("GFSO_AGENTS_PATH", "data/agents.json"))
        self._agents: dict[str, dict] = {}
        self._lock = threading.Lock()
        try:
            self._agents = json.loads(self._path.read_text(encoding="utf-8"))
        except Exception:
            pass

    def register(self, agent_id: str, kind: str, model: str = "sonnet",
                 workdir: str | None = None, validator: str | None = None) -> dict:
        if kind not in ("llm-executor", "llm-validator", "unittest-checker", "external"):
            raise ValueError(f"unknown kind {kind!r} (llm-executor | llm-validator | unittest-checker "
                             f"| external; a human needs no registration — unregistered = human)")
        with self._lock:
            self._agents[agent_id] = {"kind": kind, "model": model, "workdir": workdir,
                                      "validator": validator}
            self._path.parent.mkdir(parents=True, exist_ok=True)
            self._path.write_text(json.dumps(self._agents, ensure_ascii=False, indent=1),
                                  encoding="utf-8")
        return {"registered": agent_id, **self._agents[agent_id]}

    def validator_for(self, executor_id: str | None) -> str | None:
        """The validation instrument for work done by `executor_id`: the executor's own configured
        `validator` override, else the FIRST registered llm-validator (the default instrument)."""
        cfg = self.get(executor_id or "") or {}
        return cfg.get("validator") or self.default_validator()

    def get(self, agent_id: str) -> dict | None:
        return self._agents.get(str(agent_id))

    def list(self) -> dict:
        return dict(self._agents)

    def default_validator(self) -> str | None:
        """The auto-validation instrument: the FIRST registered validator — an `llm-validator` (a fresh
        read-only agent) or a `unittest-checker` (a deterministic hidden-test runner, the issuer's
        oracle). With none registered, validation stays the issuer's manual act."""
        for aid, a in self._agents.items():
            if a.get("kind") in ("llm-validator", "unittest-checker"):
                return aid
        return None


def _executor_packet(engine, task, workdir: str | None) -> str:
    """The executor's self-contained contract (it has no graph access): spec + criteria + upstream
    inputs (the REAL delivered outputs it consumes) + NEGLECTED + rework feedback if any."""
    from gfso.tools_llm import _last_deliver_result
    tid = str(task.id)
    crits = "\n".join(f"- **{c.name}**: {c.description}" for c in task.spec.criteria) or "- (none)"
    ups = []
    for e in engine.get_dependencies():
        if str(e.to_id) == tid:
            prod = engine.get_task(TaskId(e.from_id))
            delivered = _last_deliver_result(engine, TaskId(e.from_id)) or "(not delivered yet)"
            name = (prod.spec.name or prod.spec.description[:40]) if prod else "?"
            ups.append(f"- input from `{e.from_id}` ({name})"
                       + (f" — glue: {e.glue}" if e.glue else "") + f"\n  its DELIVER: {delivered}")
    negl = "\n".join(f"- {n.item}" for n in task.spec.neglected)
    rework = ""
    if task.state.name == "REWORK":
        failed = next((list(a.failed_criteria) for a in reversed(engine.audit_log(task.id))
                       if a.signal == Signal.FAIL and not a.rejected and a.failed_criteria), [])
        rework = (f"\n## REWORK (iteration {task.iteration}) — the validator FAILED these criteria; "
                  f"fix exactly them:\n" + "\n".join(f"- {f}" for f in failed) + "\n")
    return (f"# Your node: {tid} — {task.spec.name}\n\n{task.spec.description}\n\n"
            f"## Criteria (your ENTIRE obligation; each must really hold)\n{crits}\n\n"
            f"## Inputs (upstream deliveries you consume — use the REAL outputs, no stubs)\n"
            f"{chr(10).join(ups) or '- none'}\n\n"
            f"## NEGLECTED (declared plan assumptions — do not gold-plate against these)\n"
            f"{negl or '- none'}\n{rework}\n"
            f"Working directory: {workdir or os.getcwd()}\n")


def _signal(engine, task_id: TaskId, sig: Signal, source: str, **kw) -> bool:
    entry = engine.send_signal_sync(SignalData(signal=sig, task_id=task_id,
                                               source=AgentId(source), **kw))
    ok = bool(entry and not entry.rejected)
    if not ok:
        log.warning(f"delegate: {sig.name} on {task_id} rejected: {entry.error if entry else '?'}")
    return ok


def run_executor(engine, task_id: TaskId, executor_id: str, agents: AgentRegistry,
                 _llm=None) -> dict:
    """ONE delegated execution round: spawn the headless executor with the packet, translate its report
    into FSM signals (its consent = its own report, Inv-1), then auto-validate + auto-verdict if a
    validator instrument is registered. Returns a summary dict (also emitted to the observation field)."""
    from gfso.runtime import llm_factory
    from gfso.adapters.llm.structured import schema_instruction, parse_structured
    from gfso.decompose.loop import _stat_line

    cfg = agents.get(executor_id) or {}
    task = engine.get_task(task_id)
    if task is None:
        return {"error": f"unknown task {task_id}"}

    from gfso.engine.events import emit_cb
    _cb = emit_cb(engine, "delegate")
    llm = _llm or llm_factory(cfg.get("model", "sonnet"))
    llm.on_tick = _cb
    llm.stage_hint = f"{task_id} executor({executor_id})"
    # Process cap = the node's deadline when set (§3.5: no second clock — on expiry the process is
    # killed, NO signal forged, the FSM timeout monitor escalates), else the adapter default (15 min).
    cap = None
    if getattr(task, "deadline", None):
        from datetime import datetime
        cap = max(60, int((task.deadline - datetime.now()).total_seconds()))
    _cb(f"{task_id}: executor {executor_id} spawned (workdir={cfg.get('workdir') or 'cwd'}"
        + (f", cap {cap}s" if cap else "") + ")…")
    system = (_PROMPTS / "executor.md").read_text(encoding="utf-8")
    packet = _executor_packet(engine, task, cfg.get("workdir"))
    try:
        text = llm.run_agent(system, packet + schema_instruction(EXECUTOR_SCHEMA),
                             allowed_tools=EXECUTOR_TOOLS, cwd=cfg.get("workdir"), timeout=cap)
    except TypeError:  # a runner without the timeout param (fakes)
        text = llm.run_agent(system, packet + schema_instruction(EXECUTOR_SCHEMA),
                             allowed_tools=EXECUTOR_TOOLS, cwd=cfg.get("workdir"))
    if hasattr(llm, "tag_last"):
        llm.tag_last("executor")
    report = parse_structured(text, EXECUTOR_SCHEMA)
    if report is None:
        # No signal is forged on a broken report: the node stays where it is; the FSM's own timeout
        # monitor escalates a stuck node (no second clock). Visible in the observation field.
        _cb(f"{task_id}: executor report DID NOT PARSE — no signals sent; issuer attention needed "
            f"· executor {_stat_line(llm)}")
        return {"task_id": str(task_id), "status": "unparsed", "report_text": text,
                "stats": list(getattr(llm, "calls", []))}

    status = report["status"]
    if status == "challenge":
        _signal(engine, task_id, Signal.CHALLENGE, executor_id, reason=report.get("reason", ""))
        _cb(f"{task_id}: executor CHALLENGED the spec — issuer resolves · {_stat_line(llm)}")
    elif status == "blocked":
        if task.state.name == "REVIEW":  # consent happened (it worked far enough to find the block)
            _signal(engine, task_id, Signal.ACCEPT, executor_id)
        blocker = report.get("blocker_task_id")
        blockers = tuple(TaskId(b) for b in (report.get("blocker_task_ids") or []) if b)
        _signal(engine, task_id, Signal.BLOCK, executor_id, reason=report.get("reason", ""),
                blocker_task_id=TaskId(blocker) if blocker else None,
                blocker_task_ids=blockers)
        _cb(f"{task_id}: executor BLOCKED ({report.get('reason', '')[:80]}) · {_stat_line(llm)}")
    else:  # delivered — the DISPATCHER picks the VALIDATING node up and auto-validates (one path
        # for every delivery, delegated or self-executed; natural node×iteration dedup)
        if task.state.name == "REVIEW":
            _signal(engine, task_id, Signal.ACCEPT, executor_id)
        _signal(engine, task_id, Signal.DELIVER, executor_id, result=report["summary"])
        _cb(f"{task_id}: executor DELIVERED · {_stat_line(llm)}")
    return {"task_id": str(task_id), "status": status,
            "stats": list(getattr(llm, "calls", []))}


def _oracle_workdir(engine, vcfg: dict):
    """The workspace for this project from the issuer-side oracle map (same map the unittest-checker
    uses), so a criteria-judge validator runs the code where the executor delivered it. None if absent."""
    import json as _json
    from pathlib import Path
    project = getattr(engine, "_project_name", None) or "default"
    try:
        entry = _json.loads(Path(vcfg.get("oracle_map", "data/e0_canonical_map.json"))
                            .read_text(encoding="utf-8")).get(project)
        return entry.get("workdir") if entry else None
    except Exception:
        return None


def _checker_validate(engine, task_id: TaskId, vcfg: dict) -> dict:
    """Deterministic HIDDEN-TEST validation (the issuer's oracle — the executor never sees the tests).
    Runs the project's hidden unittest suite against the delivered solution.py, maps each test method
    to the criterion of the same name, returns {verdict, per_criterion, failed_criteria}. No LLM, no
    false-PASS. The oracle map (config: `oracle_map`) is issuer-side; the agent has no path to it."""
    import json as _json
    from pathlib import Path
    from gfso.adapters.verifiers import evaluate_unittest
    project = getattr(engine, "_project_name", None) or "default"
    try:
        entry = _json.loads(Path(vcfg.get("oracle_map", "data/e0_canonical_map.json"))
                            .read_text(encoding="utf-8")).get(project)
    except Exception:
        entry = None
    if not entry:
        return {"verdict": None, "note": f"no hidden-test oracle registered for project {project}"}
    crits = entry["criteria"]
    sol = Path(entry["workdir"]) / "solution.py"
    if not sol.exists():
        return {"verdict": "FAIL", "failed_criteria": list(crits),
                "per_criterion": [{"criterion": c, "verdict": "fail",
                                   "evidence": "no solution.py delivered"} for c in crits]}
    results = evaluate_unittest(sol.read_text(encoding="utf-8"),
                               Path(entry["canonical"]).read_text(encoding="utf-8"))
    by = {r.check_name: r for r in results}
    per, failed = [], []
    for c in crits:
        r = by.get(c)
        ok = bool(r and r.passed)
        per.append({"criterion": c, "verdict": "pass" if ok else "fail",
                    "evidence": ("passed" if ok else (r.details[:400] if r else "test not found in suite"))})
        if not ok:
            failed.append(c)
    return {"verdict": "PASS" if not failed else "FAIL", "per_criterion": per, "failed_criteria": failed}


def _auto_validate(engine, task_id: TaskId, agents: AgentRegistry, _llm=None) -> str | None:
    """DELIVER→VALIDATING auto-fires the registered validator instrument; the verdict AUTO-SIGNALS
    (PASS → DONE; FAIL(failed_criteria) → REWORK — the rework loop lives in the FSM, max_iterations
    bounds it). verdict:null NEVER auto-signals — the one escalation to the issuer. Returns the
    outcome for the dispatcher: 'pass'/'fail' (signed), 'rejected' (the FSM refused the verdict —
    ≠ no-verdict: the graph wasn't ready, revalidate on its next change), 'no-verdict'."""
    from gfso import tools_llm as T

    task = engine.get_task(task_id)
    validator_id = agents.validator_for(task.assignee if task else None)
    if validator_id is None:
        engine.emit_info("delegate", f"{task_id}: no llm-validator registered — validation stays manual")
        return None
    # A FRESH recorded verdict for the CURRENT generation (e.g. the agent already ran a manual
    # validate_result) is signed directly — spawning another validator run would duplicate minutes
    # of agent work for the same evidence (observed live: one duplicate per rework cycle).
    # BUT a deterministic hidden-test oracle (unittest-checker) is CHEAP (runs the suite in seconds)
    # and AUTHORITATIVE (the issuer's ground truth) — it must NOT be pre-empted by a recorded LLM
    # verdict. Observed live (floor_17): the checker returned FAIL, the agent then ran validate_result
    # which returned a shallow PASS over its own incomplete mock, and reuse signed that PASS — a false
    # close. So reuse applies only when the assigned validator is the expensive LLM kind; for a
    # unittest-checker the oracle always runs, and only ITS OWN verdict is ever reused.
    _vkind = (agents.get(validator_id) or {}).get("kind")
    rec = engine._graph.exec_verdict_record(task_id)
    if (_vkind != "unittest-checker"
            and rec and task is not None
            and rec.get("iteration") == getattr(task, "iteration", 0)
            and rec.get("reopens", 0) == getattr(task, "reopens", 0)
            and rec.get("verdict") in ("PASS", "FAIL")):
        engine.emit_info("delegate", f"{task_id}: fresh recorded verdict {rec['verdict']} reused — "
                                     f"no duplicate validator run")
        sig = Signal.PASS if rec["verdict"] == "PASS" else Signal.FAIL
        if _signal(engine, task_id, sig, validator_id,
                   **({"failed_criteria": tuple(rec.get("failed_criteria") or ())}
                      if sig == Signal.FAIL else {})):
            return "pass" if sig == Signal.PASS else "fail"
        engine.emit_info("delegate", f"{task_id}: reused verdict {rec['verdict']} REJECTED by the "
                                     f"FSM — the node revalidates on the graph's next change")
        return "rejected"
    vcfg = agents.get(validator_id) or {}
    if vcfg.get("kind") == "unittest-checker":
        # deterministic hidden-test oracle — runs the suite the executor never sees, records the
        # per-criterion verdict (the integrity gate applies), then auto-signals below.
        out = _checker_validate(engine, task_id, vcfg)
        if out.get("verdict") in ("PASS", "FAIL"):
            try:
                engine.record_exec_verdict(task_id, out["verdict"], out.get("failed_criteria") or [],
                                           validator_id, per_criterion=out.get("per_criterion"))
            except Exception as e:  # a malformed report is ⊥, not a verdict (§2.2) — never auto-signal it
                engine.emit_info("delegate", f"{task_id}: checker verdict refused ({e})")
                out = {"verdict": None}
        f = out.get("failed_criteria") or []
        engine.emit_info("delegate", f"{task_id}: unittest-checker → {out.get('verdict')}"
                         + (f" (failed: {', '.join(f)})" if f else ""))
    else:
        ecfg = agents.get(task.assignee) if task else None   # validate WHERE the executor worked
        # The criteria-judge validator must run the code IN the workspace. When neither the executor nor
        # the validator config pins a workdir (self-execution: the executor is the unregistered user-agent),
        # fall back to the issuer-side oracle map, where setup records this project's workspace.
        _wd = (ecfg or {}).get("workdir") or vcfg.get("workdir") or _oracle_workdir(engine, vcfg)
        out = T.validate_result(engine, str(task_id), model=vcfg.get("model", "sonnet"),
                              workdir=_wd, _llm=_llm)
        if out.get("inflight"):
            # another validator run (e.g. a manual validate_result) already holds this node
            # generation — treat like a rejected verdict: free the dedup key, revalidate on the
            # graph's next change, never burn the one no-verdict retry on a suppressed duplicate
            engine.emit_info("delegate", f"{task_id}: validator already in flight — duplicate spawn suppressed")
            return "rejected"
    verdict = out.get("verdict")
    if verdict == "PASS":
        if _signal(engine, task_id, Signal.PASS, validator_id):
            return "pass"
    elif verdict == "FAIL":
        if _signal(engine, task_id, Signal.FAIL, validator_id,
                   failed_criteria=tuple(out.get("failed_criteria") or ())):
            return "fail"
    else:  # null/error — never auto-signal an unparsed verdict
        engine.emit_info("delegate",
                         f"{task_id}: validator verdict UNPARSED/error — issuer must decide "
                         f"(report kept in the validate_result output)")
        return "no-verdict"
    engine.emit_info("delegate", f"{task_id}: validator verdict {verdict} REJECTED by the FSM — "
                     f"the node revalidates on the graph's next change")
    return "rejected"


class Dispatcher:
    """The autostart engine: EVENT-DRIVEN — every graph transition (the same bus the UI/WS listens on)
    wakes a frontier re-evaluation, so an executor-actionable step whose Del is a REGISTERED llm-executor
    is picked up within milliseconds (dedup per node×iteration; small concurrency cap). The periodic wait
    is only a safety net for an event missed while a run was in flight — dispatch_once is idempotent, so an
    extra pass is free."""

    def __init__(self, engine, agents: AgentRegistry, poll: float = 15.0, max_concurrent: int = 4,
                 runner=run_executor, validator_runner=None):
        self._engine, self._agents, self._poll = engine, agents, poll   # poll = safety-net interval
        self._cap = threading.Semaphore(max_concurrent)
        self._runner = runner
        self._validate = validator_runner or _auto_validate
        self._seen: set[str] = set()      # "{task}#{iter}" / "v:{task}#{iter}" — one run per round
        self._retried: set[str] = set()   # validator no-verdict retries (one per node×iteration)
        self._stale: set[str] = set()     # re-ASSIGNed (revised) nodes → their dedup keys no longer bind
        self._stop = threading.Event()
        self._dirty = threading.Event()   # set by every transition → the loop re-evaluates the frontier

    def _deps_ready(self, task_id: TaskId) -> bool:
        """An executor spawn is useless before the node's Dep PRODUCERS deliver — it hits a missing
        input and BLOCKs (observed live). Gate accept-step spawns on producer DONE. A producer node
        that does not EXIST yet counts as NOT ready: during a build the consumer's ASSIGN can land
        milliseconds before its producer's (observed live — the consumer slipped the gate and burned
        a doomed run); the producer's own ASSIGN wakes the loop, so no liveness is lost."""
        tid = str(task_id)
        for e in self._engine.get_dependencies():
            if str(e.to_id) == tid:
                prod = self._engine.get_task(TaskId(e.from_id))
                if prod is None or prod.state.name != "DONE":
                    return False
        return True

    def _resolve_ready_blocks(self) -> None:
        """Auto BLOCK resolution: BLOCKED-on-nodes resolves once every EXISTING producer is DONE.
        Adjudication follows the PROVISIONAL edges this node's BLOCK recorded: all sources real →
        confirm all; some mis-named PHANTOM sources (nonexistent nodes — observed live) → the corrected
        set = the real sources (SET semantics drops only the bogus edges, never the real ones); all
        phantom → external=True. External blocks stay for a human. The unblocked node's spawn-dedup
        key is dropped so a FRESH executor run picks it up."""
        from gfso.core.types import State
        for t in self._engine.tasks_by_state(State.BLOCKED):
            if not self._issuer_is_automated(t.id):
                continue
            deps_in = [e for e in self._engine.get_dependencies() if str(e.to_id) == str(t.id)]
            if not deps_in:
                continue
            existing = [e.from_id for e in deps_in
                        if self._engine.get_task(TaskId(e.from_id)) is not None]
            if all(self._engine.get_task(TaskId(x)).state.name == "DONE" for x in existing):
                key = f"rb:{t.id}#{getattr(t, 'iteration', 0)}"
                if key in self._seen:
                    continue
                self._seen.add(key)
                issuer = str(self._engine._issuer_of(t.id))
                prov = [e.from_id for e in deps_in if getattr(e, "provisional", False)]
                prov_real = [x for x in prov
                             if self._engine.get_task(TaskId(x)) is not None]
                if len(prov_real) == len(prov):
                    _signal(self._engine, t.id, Signal.RESOLVE_BLOCK, issuer, action="confirm")
                elif prov_real:
                    _signal(self._engine, t.id, Signal.RESOLVE_BLOCK, issuer,
                            blocker_task_ids=tuple(TaskId(x) for x in prov_real))
                else:
                    _signal(self._engine, t.id, Signal.RESOLVE_BLOCK, issuer, external=True)
                self._seen.discard(f"{t.id}#{getattr(t, 'iteration', 0)}")
                self._engine.emit_info("delegate",
                                       f"{t.id}: producers DONE — RESOLVE_BLOCK (auto), executor re-queued")

    def _validate_here(self, task) -> bool:
        """D6 (§6.5) — validation-at-the-seam: the independent validator instrument auto-fires on
        PUBLIC nodes (a root, or Del(child) ≠ Del(parent)); an INTERNAL node (the executor's own
        private decomposition) self-verifies via its DELIVER self_validation, and its guarantee is
        carried by the public result's validation (T1). NOT validate-every-node — per-node
        instrumenting stays available as an OPT-IN dial: GFSO_VALIDATE_INTERNAL=1 restores the
        every-delivery behavior (useful for measurement runs, harmless for correctness)."""
        import os
        if task is None:
            return True
        if os.environ.get("GFSO_VALIDATE_INTERNAL", "") not in ("", "0"):
            return True
        return self._engine._graph.is_public(task)

    def _issuer_is_automated(self, task_id: TaskId) -> bool:
        """Auto-validation fires ONLY for nodes whose ISSUER is automated — the standing agent or a
        registered participant. A HUMAN issuer (any unregistered name) validates their node THEMSELVES:
        the system never takes a human's verdict away (the author's per-node discrimination rule)."""
        from gfso.tools import _agent_id
        issuer = str(self._engine._issuer_of(task_id))
        return issuer == _agent_id() or self._agents.get(issuer) is not None

    def _drop_keys(self, tid: str) -> None:
        """Forget every dedup key of a node — targeted discards (a concurrent worker may be
        discarding its own key at the same moment; never rebuild the sets wholesale)."""
        heads = (tid, f"v:{tid}", f"rb:{tid}")
        for bag in (self._seen, self._retried):
            for k in [k for k in bag if k.rsplit("#", 1)[0] in heads]:
                bag.discard(k)

    def _children_settled(self, task_id: TaskId) -> bool:
        """A parent's verdict is structurally rejected until ALL its children PASS (Theorem-1 gate) —
        a validator run before that is a guaranteed-wasted spawn (observed live: two doomed PASSes)."""
        kids = self._engine.get_active_children(task_id)
        return all(k.state.name == "DONE" and getattr(k.done_reason, "name", "") == "PASS"
                   for k in kids)

    def dispatch_once(self) -> list[str]:
        """One poll round (the testable unit): spawn executor runs for executor-ready steps AND the
        auto-validation for EVERY freshly delivered node (delegated or self-executed — one path;
        fires only when an llm-validator is registered AND the node's issuer is automated, else
        validation stays the issuer's act)."""
        if getattr(self._engine, "_dispatch_quiesce", 0):
            return []      # a wholesale build/rebuild is mid-burst — dispatch on the settled graph only
        # a re-ASSIGNed (revised) node is fresh work: its old spawn/validate keys no longer bind
        for tid in list(self._stale):
            self._stale.discard(tid)
            self._drop_keys(tid)
        # the FSM accepts a registered validator's PASS/FAIL as the issuer's role-V instrument (§6.5) —
        # both the LLM validator (a fresh read-only agent) and the deterministic unittest-checker
        self._engine._graph._authorized_validators = {
            aid for aid, cfg in self._agents.list().items()
            if cfg.get("kind") in ("llm-validator", "unittest-checker")}
        self._resolve_ready_blocks()
        started = []
        out = self._engine.next_steps()
        for s in out.get("steps", []):
            task = self._engine.get_task(TaskId(s["task_id"]))
            it = getattr(task, "iteration", 0)
            if s.get("action") == "validate" and self._agents.validator_for(s.get("assignee")) is not None:
                if not self._issuer_is_automated(TaskId(s["task_id"])):
                    continue                              # a human issuer keeps their verdict
                if not self._validate_here(task):
                    continue                              # D6: internal (same-Del) node — self-validation
                if not self._children_settled(TaskId(s["task_id"])):
                    continue                              # verdict would be gate-rejected — wait for the children
                key = f"v:{s['task_id']}#{it}"
                if key not in self._seen:
                    self._seen.add(key)
                    started.append(f"validate:{s['task_id']}")
                    threading.Thread(target=self._validate_guarded,
                                     args=(TaskId(s["task_id"]), it), daemon=True).start()
                continue
            if s.get("action") not in ("accept", "execute", "rework", "deliver"):
                continue
            if s.get("action") == "accept" and not self._deps_ready(TaskId(s["task_id"])):
                continue                   # spawning before the producers deliver ⇒ instant BLOCK
            cfg = self._agents.get(s.get("assignee") or "")
            if cfg is None:
                continue                   # unregistered = human = passive
            if cfg.get("kind") != "llm-executor":
                self._engine.emit_info("delegate",
                                       f"{s['task_id']}: Del={s['assignee']} is a registered "
                                       f"{cfg.get('kind')} — not an executor kind, nothing to start")
                continue
            key = f"{s['task_id']}#{it}"
            if key in self._seen:
                continue
            self._seen.add(key)
            started.append(s["task_id"])
            threading.Thread(target=self._run_guarded,
                             args=(TaskId(s["task_id"]), s["assignee"], it), daemon=True).start()
        return started

    _EXECUTOR_STATES = ("REVIEW", "EXECUTING", "REWORK")

    def _fresh(self, task_id: TaskId, expect_iter: int, states: tuple) -> bool:
        """TOCTOU guard: the dispatch decision can be minutes older than the semaphore slot (observed
        live — a queued second-generation run fired on a node that had DELIVERED meanwhile). Re-check
        the node right before spending an LLM run; a stale slot is dropped silently — if the node is
        genuinely actionable again, a later pass re-dispatches it under a fresh key."""
        t = self._engine.get_task(task_id)
        if t is None or t.state.name not in states or getattr(t, "iteration", 0) != expect_iter:
            self._engine.emit_info("delegate",
                                   f"{task_id}: queued run is stale (state {t.state.name if t else '?'}"
                                   f") — slot released")
            return False
        return True

    def _run_guarded(self, task_id: TaskId, executor_id: str, expect_iter: int = 0) -> None:
        with self._cap:
            if not self._fresh(task_id, expect_iter, self._EXECUTOR_STATES):
                return
            try:
                self._runner(self._engine, task_id, executor_id, self._agents)
            except Exception as e:
                log.warning(f"delegate run failed on {task_id}: {e}")

    def _validate_guarded(self, task_id: TaskId, expect_iter: int = 0) -> None:
        with self._cap:
            if not self._fresh(task_id, expect_iter, ("VALIDATING",)):
                self._seen.discard(f"v:{task_id}#{expect_iter}")
                return
            ret = None
            try:
                ret = self._validate(self._engine, task_id, self._agents)
            except Exception as e:
                log.warning(f"auto-validate failed on {task_id}: {e}")
            t = self._engine.get_task(task_id)
            if ret == "rejected":
                # the FSM refused the verdict (e.g. children not settled yet) — NOT a validator
                # failure: free the key so the node revalidates when the graph next changes,
                # and never burn the one no-verdict retry on it (observed live: a rejected PASS
                # was misread as no-verdict → the retry was wasted → the node stuck for good).
                if t is not None:
                    self._seen.discard(f"v:{task_id}#{getattr(t, 'iteration', 0)}")
                return
            # a validator run that died/unparsed leaves VALIDATING with no verdict — ONE retry
            if t is not None and t.state.name == "VALIDATING":
                key = f"v:{task_id}#{getattr(t, 'iteration', 0)}"
                if key not in self._retried:
                    self._retried.add(key)
                    self._seen.discard(key)
                    self._engine.emit_info("delegate",
                                           f"{task_id}: validator returned no verdict — one retry queued")

    def _on_bus(self, tid=None, old=None, new=None, signal=None) -> None:
        """The transition-bus callback — trivial (set a flag + note revisions), never blocks the signal
        path nor re-enters dispatch (the loop thread runs the real pass). An ASSIGN on the bus = a
        (re)authored node: mark its dedup keys stale so a REVISED node is fresh work (observed live:
        a revised root kept its consumed spawn key and was never re-executed). An initial ASSIGN has
        no keys — the mark is a free no-op."""
        if getattr(signal, "name", "") == "ASSIGN" and tid is not None:
            self._stale.add(str(tid))
        self._dirty.set()

    def start(self) -> None:
        # Wake the loop on every graph transition (same event bus as the UI/WS).
        self._engine.on_transition(self._on_bus)
        # the quiesce-end poke: a wholesale build clears engine._dispatch_quiesce and calls this
        self._engine._dispatch_wake = self._dirty.set

        def _loop():
            while not self._stop.is_set():
                self._dirty.clear()                    # clear BEFORE the pass: a transition during it re-arms
                try:
                    self.dispatch_once()
                except Exception as e:
                    log.warning(f"dispatcher run failed: {e}")
                self._dirty.wait(self._poll)           # woken instantly by a transition, else safety-net poll
        threading.Thread(target=_loop, daemon=True).start()

    def stop(self) -> None:
        self._stop.set()
        self._dirty.set()                              # wake the loop so it exits promptly


_DISPATCHERS: dict[int, Dispatcher] = {}
_DEFAULT_AGENTS: AgentRegistry | None = None


def default_agents() -> AgentRegistry:
    """The server-wide roster singleton (one json file, shared by every project engine)."""
    global _DEFAULT_AGENTS
    if _DEFAULT_AGENTS is None:
        _DEFAULT_AGENTS = AgentRegistry()
    return _DEFAULT_AGENTS


def ensure_dispatcher(engine, agents: AgentRegistry | None = None) -> Dispatcher:
    """One dispatcher per engine (lazy, idempotent). Attached at ENGINE creation (runtime), so
    delegation works identically under every entry point (stdio MCP, unified serve, tests)."""
    key = id(engine)
    if key not in _DISPATCHERS:
        d = Dispatcher(engine, agents or default_agents())
        d.start()
        _DISPATCHERS[key] = d
    return _DISPATCHERS[key]
