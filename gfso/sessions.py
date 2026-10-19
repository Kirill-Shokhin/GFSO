"""The role sessions the system spawns: an executor's round on one node (`run_executor`), its consent to an offer
(`run_consent`), one session carrying a whole scope (`run_scope_executor`) — each a headless run with its prompt,
schema and work tools, its session bounded (`_session_cap`), its report handed to `reports`."""
from __future__ import annotations

from datetime import datetime
from pathlib import Path
from gfso.config import MODEL_DEFAULT
from gfso.inflight import _inflight
from gfso.llm import llm_factory, session_calls
from gfso.adapters.llm.stats import _stat_line
from gfso.adapters.llm.structured import schema_instruction, parse_structured
from gfso.core.graph.model import generation_of_task
from gfso.core.types import TaskId, Signal, Stage, State, Verdict
from gfso.engine.events import emit_cb
from gfso.issuer import signal_ok as _signal
from gfso.roster import AgentRegistry, _resolution_note, missing_workdir
from gfso.workspaces import _enter_workspace, node_workspace, performer
from gfso.packets import _EXECUTOR_STATES, _executor_packet, _scope_order, _scope_packet
from gfso.reports import _decided_status, _report_into_signals, _scope_report_into_signals


_PROMPTS = Path(__file__).parent / "mcp" / "prompts"


EXECUTOR_TOOLS = ("Read", "Write", "Edit", "Bash", "Glob", "Grep")


EXECUTOR_SCHEMA = {
    "type": "object",
    "properties": {
        "status": {"type": "string", "enum": ["delivered", "blocked", "challenge"]},
        "summary": {"type": "string"},
        # THE WORD, not a report. §11.2 puts the executor's OWN verdict in this field, and the
        # human door has always refused anything else (`_self_check_verdict`). Here it was a
        # free string, and §10.3 rests an internal node's completion on it — so the two
        # doors held one field to two contracts, which is this codebase's most expensive class.
        "self_validation": {"type": "string", "enum": [Verdict.PASS, Verdict.FAIL],
                            "description": "your OWN verdict on this delivery (§11.2). The evidence goes in `summary`; this is what you conclude from it."},
        "reason": {"type": "string"},
        "blocker_task_id": {"type": "string"},
        "blocker_task_ids": {"type": "array", "items": {"type": "string"}},
    },
    "required": ["status", "summary"],
}


def _session_cap(tasks) -> int | None:
    """The process cap of an executor session: the earliest deadline among the nodes it holds, else the
    adapter's default. No second clock (§12.2): on expiry the process is killed, NO signal forged, and the FSM
    timeout monitor escalates — and a session holding several nodes cannot run past the contract of any of
    them, so none lapses while the session that would deliver it is still working."""
    deadlines = [t.deadline for t in tasks if t.deadline]
    return max(60, int((min(deadlines) - datetime.now()).total_seconds())) if deadlines else None


def _run_session(llm, system: str, user: str, cfg: dict, cap, cwd: str | None) -> str:
    """One headless executor session with the work tools, in its node's place, under the role's caps."""
    try:
        return llm.run_agent(system, user, allowed_tools=EXECUTOR_TOOLS, cwd=cwd, timeout=cap,
                             max_turns=cfg.get("max_turns"))
    except TypeError:  # a runner without the timeout/turn-cap params (fakes)
        return llm.run_agent(system, user, allowed_tools=EXECUTOR_TOOLS, cwd=cwd)


def _spawn(engine, node_id, executor_id: str, cfg: dict, _llm, role: str, prompt: str, packet: str, schema: dict,
           verb: str, cwd, cap=None, work: bool = True):
    """THE ONE FRAME every role session runs in — spawn · parse: the role's model, its prompt and packet with the
    report schema, under the in-flight registry (`busy`), its spend booked to the node; `work` = the work tools
    under the session cap, else read-only (a consent reads, it does not build). Returns (report or None, text,
    stats, llm, the observation callback) — what the report MEANS is the caller's, never the frame's."""
    _cb = emit_cb(engine, "delegate")
    llm = _llm or llm_factory(cfg.get("model", MODEL_DEFAULT))
    if work:
        llm.on_tick = _cb
    llm.stage_hint = f"{node_id} {role}({executor_id})"
    system, user = (_PROMPTS / prompt).read_text(encoding="utf-8"), packet + schema_instruction(schema)
    with _inflight(verb, engine, node_id):
        text = (_run_session(llm, system, user, cfg, cap, cwd) if work else
                llm.run_agent(system, user, allowed_tools=("Read", "Glob", "Grep"), cwd=cwd))
    stats = session_calls(llm, Stage.EXECUTOR)
    engine.record_llm_usage(Stage.EXECUTOR, llm, node_id)      # the session's spend, booked once to its node
    return parse_structured(text, schema), text, stats, llm, _cb


def run_executor(engine, task_id: TaskId, executor_id: str, agents: AgentRegistry,
                 _llm=None) -> dict:
    """ONE delegated execution round: spawn the headless executor with the packet, translate its report
    into FSM signals (its consent = its own report, Inv-1), then auto-validate + auto-verdict if a
    validator instrument is registered. Returns a summary dict (also emitted to the observation field). The session
    is the PERFORMER's (`performer`: the executor itself, or the hands of a holder that dispatches); every signal is
    `executor_id`'s, the node's Del."""
    hands, cfg = performer(engine, agents, executor_id)
    cfg = cfg or {}
    task = engine.graph.get_task(task_id)
    if task is None:
        return {"error": f"unknown task {task_id}"}
    # THE VERSION THIS SESSION ANSWERS, read once, with the consent it stands on: a holder's node not yet consented
    # to is not worked by its hands — the system never consents in its place (Inv-1) — and a revision landing from
    # here on is a version the report does not answer (`started_on`)
    started_on = generation_of_task(task)
    if task.state.name == "OFFERED" and agents.get(executor_id) is None:
        return {"task_id": str(task_id), "status": "not_consented"}

    _cb = emit_cb(engine, "delegate")
    # THE PLACE, ASKED BEFORE ANYTHING IS SPENT — the same question `missing_workdir` answers for
    # the dispatcher, through the same function rather than a second spelling of the rule. This arm
    # is for whoever calls this verb DIRECTLY; under the dispatcher the question was already asked
    # one step earlier, before ACCEPT, because by here the obligation has been fixed.
    # ASCII, deliberately: this sentence reaches the observation strip and consoles that are cp1251.
    _wd = missing_workdir(cfg)
    if _wd:
        _cb(f"{task_id}: executor {executor_id} NOT spawned - its registered workdir '{_wd}' is not "
            f"a directory{_resolution_note(_wd)}. No signal sent; re-register the role against the "
            f"directory the work is really in.")
        engine.emit_info("delegate", f"{task_id}: executor {executor_id} has no working directory "
                                     f"('{_wd}') - not spawned")
        return {"task_id": str(task_id), "status": "no_workdir", "workdir": _wd,
                "error": f"the registered workdir of {executor_id!r} is not an existing directory"}
    cap = _session_cap([task])
    cwd, unjoined, ws = _enter_workspace(engine, agents, task, [task])
    _cb(f"{task_id}: executor {executor_id} spawned (workdir={cwd or 'cwd'}"
        + (f", cap {cap}s" if cap else "") + ")…")
    # The dispatcher's own spawn is the LONGEST thing this server does — up to a fifteen-minute
    # `claude -p` — and it was the one path that never appeared in `busy`, so a reconcile arriving
    # from another session read the server as idle and restarted it mid-run.
    report, text, stats, llm, _cb = _spawn(engine, task_id, executor_id, cfg, _llm, "executor", "executor.md",
                                           _executor_packet(engine, task, cwd, unjoined), EXECUTOR_SCHEMA,
                                           "delegated_execution", cwd, cap)
    if report is None:
        # No signal is forged on a broken report: the node stays where it is; the FSM's own timeout
        # monitor escalates a stuck node (no second clock). Visible in the observation field.
        _cb(f"{task_id}: executor report DID NOT PARSE — no signals sent; issuer attention needed "
            f"· executor {_stat_line(llm)}")
        return {"task_id": str(task_id), "status": "unparsed", "report_text": text, "stats": stats}

    # `_decided_status` is the owner of "which of the three was this"; the dispatch enforces it and
    # this line only reports what the round amounted to. An unrecognised word is `undecided`, and
    # the caller can tell that from a delivery.
    status = _decided_status(report.get("status"))
    _report_into_signals(engine, task_id, executor_id, task, report,
                         status or str(report.get("status")), llm, _cb,
                         observed=engine.observed_here(task_id)
                         and agents.validator_for(hands or executor_id, project=engine.project_name) is not None,
                         workspace=ws, started_on=started_on)
    return {"task_id": str(task_id), "status": status or "undecided",
            "reported_status": None if status else report.get("status"), "stats": stats}


CONSENT_SCHEMA = {
    "type": "object",
    "properties": {"decision": {"type": "string", "enum": ["accept", "challenge"]},
                   "reason": {"type": "string", "description": "on a challenge: which criteria are "
                              "defective and why; on an accept: one line on why the contract holds"}},
    "required": ["decision", "reason"],
}


def run_consent(engine, task_id: TaskId, executor_id: str, agents: "AgentRegistry",
                _llm=None) -> dict:
    """A system executor's consent to the contract of a node WITH children (Inv-1: a version binds
    its executor only by his ACCEPT of it).

    Its work is its children's and its own act comes after them, so the ordinary execution round is
    never spawned on it — and nothing else gave it a way to consent. A root handed to a system
    executor, and every revision of a system-held parent (a dispute accepted, a contract extended),
    then sat in OFFERED until its bound: nobody could move it but a party nobody asked."""
    cfg = agents.get(executor_id) or {}
    task = engine.graph.get_task(task_id)
    if task is None or task.state != State.OFFERED:
        return {"task_id": str(task_id), "status": "not_offered"}
    kids = "\n".join(f"- `{k.id}` ({k.label()}) — {k.state.name}; "
                     f"Del={k.assignee}" for k in engine.graph.get_active_children(task_id)) or "- none"
    # …where its work stands: its own place once a session made it (a revised node), else the roster's directory
    here = node_workspace(engine, agents, task_id) or cfg.get("workdir")
    packet = (_executor_packet(engine, task, here)
              + f"\n## The split under your node — the children's work, not yours\n{kids}\n")
    answer, _t, _s, _l, _cb = _spawn(engine, task_id, executor_id, cfg, _llm, "consent", "consent.md", packet,
                                     CONSENT_SCHEMA, "delegated_consent", here, work=False)
    if answer is None:
        _cb(f"{task_id}: {executor_id}'s consent DID NOT PARSE — nothing signalled")
        return {"task_id": str(task_id), "status": "unparsed"}
    decision = str(answer.get("decision", "")).strip().lower()
    if decision not in ("accept", "challenge"):
        _cb(f"{task_id}: {executor_id}'s consent named no decision it may make ({decision!r}) — nothing signalled")
        return {"task_id": str(task_id), "status": "unparsed"}
    if decision == "challenge":
        ok = _signal(engine, task_id, Signal.CHALLENGE, executor_id,
                     reason=str(answer.get("reason") or "the contract is defective"))
        _cb(f"{task_id}: {executor_id} CHALLENGED its contract" if ok else f"{task_id}: CHALLENGE refused")
        return {"task_id": str(task_id), "status": "challenged" if ok else "refused"}
    ok = _signal(engine, task_id, Signal.ACCEPT, executor_id)
    _cb(f"{task_id}: {executor_id} ACCEPTED its contract" if ok else f"{task_id}: ACCEPT refused")
    return {"task_id": str(task_id), "status": "accepted" if ok else "refused"}


#: What a scope session reports: the executor's own report, once per node it was handed, naming the node.
SCOPE_SCHEMA = {
    "type": "object",
    "properties": {"nodes": {"type": "array", "items": {
        "type": "object",
        "properties": {"task_id": {"type": "string",
                                   "description": "the node this entry reports on, exactly as its heading names it"},
                       **EXECUTOR_SCHEMA["properties"]},
        "required": ["task_id", *EXECUTOR_SCHEMA["required"]]}}},
    "required": ["nodes"],
}


def run_scope_executor(engine, top_id: TaskId, executor_id: str, agents: AgentRegistry, _llm=None) -> dict:
    """ONE executor session for a whole scope: the nodes one session of the executor builds and checks (κ,
    §3.7) are handed over together, in build order, and its one report is wrapped into each node's signals.
    The scope's top presents one result outward; the nodes inside are its own detail (§10.3)."""
    cfg = performer(engine, agents, executor_id)[1] or {}
    order = _scope_order(engine, engine.scope_members(top_id))
    started_on = {str(t.id): generation_of_task(t) for t in order}   # before the place is entered (see run_executor)
    todo = [t for t in order if t.state.name in _EXECUTOR_STATES]
    if not todo:
        return {"task_id": str(top_id), "status": "nothing_open"}
    if agents.get(executor_id) is None and any(t.state.name == "OFFERED" for t in todo):
        return {"task_id": str(top_id), "status": "not_consented"}
    _cb = emit_cb(engine, "delegate")
    cap = _session_cap(todo)
    top = engine.graph.get_task(top_id)
    cwd, unjoined, ws = _enter_workspace(engine, agents, top, order)
    _cb(f"{top_id}: one executor session ({executor_id}) for the scope's open node(s) "
        f"{', '.join(str(t.id) for t in todo)}" + (f", cap {cap}s" if cap else "") + "…")
    report, text, stats, llm, _cb = _spawn(engine, top_id, executor_id, cfg, _llm, "scope-executor",
                                           "executor_scope.md", _scope_packet(engine, top, order, cwd, unjoined),
                                           SCOPE_SCHEMA, "delegated_execution", cwd, cap)
    if report is None:
        _cb(f"{top_id}: the scope session's report DID NOT PARSE — no signals sent · {_stat_line(llm)}")
        return {"task_id": str(top_id), "status": "unparsed", "report_text": text, "stats": stats}
    _scope_report_into_signals(engine, order, executor_id, report, llm, _cb, workspace=ws, started_on=started_on)
    return {"task_id": str(top_id), "status": "reported", "stats": stats}
