"""The role sessions the system spawns: an executor's round on one node (`run_executor`), its consent to an offer
(`run_consent`), one session carrying a whole scope (`run_scope_executor`) — each a headless run with its prompt,
schema and work tools, its session bounded (`_session_cap`), its report handed to `reports`."""
from __future__ import annotations

from datetime import datetime
from pathlib import Path
from gfso.config import MODEL_DEFAULT
from gfso.inflight import _inflight
from gfso.llm import session_calls
from gfso.adapters.llm.stats import _stat_line, calls_of, refused_by_limit, the_call_was_cut
from gfso.adapters.llm.structured import schema_instruction, parse_structured
from gfso.core.graph.model import generation_of_task, project_now
from gfso.core.types import THIS_HOST, PlaceUnavailable, TaskId, Signal, Stage, State, Verdict
from gfso.engine.events import emit_cb
from gfso.issuer import signal_ok as _signal
from gfso.roster import AgentRegistry, _resolution_note, missing_workdir
from gfso.workspaces import _enter_workspace, conversation_of, execution_of, performer, project_llm
from gfso.observe import observe_place
from gfso.adapters import worktrees as W
from gfso.adapters.execution import ended_past_disk, place_past_disk
from gfso.packets import (TECH_REPORT, _EXECUTOR_STATES, _executor_packet, observed_lines, _scope_order, _scope_packet,
                          file_tech_reports)
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
        # …and how the result is built: its judge checks a checkout of what DELIVER commits — nothing ignored or
        # untracked — and runs this there before any check (`adapters.snapshots._build`)
        "build": {"type": "string",
                  "description": "with `delivered`: the shell command that builds your result from its committed files "
                                 "alone (e.g. `make`, `pip install -e .`); \"\" when nothing needs building. Left out: "
                                 "`make` where the tree has a Makefile at its root, else nothing"},
        "reason": {"type": "string"},
        "blocker_task_id": {"type": "string"},
        "blocker_task_ids": {"type": "array", "items": {"type": "string"}},
        "tech_report": TECH_REPORT,
    },
    "required": ["status", "summary"],
}


def _session_cap(engine, tasks) -> int | None:
    """The process cap of an executor session: the earliest deadline among the nodes it holds, else the
    adapter's default. No second clock (§12.2): on expiry the process is killed, NO signal forged, and the FSM
    timeout monitor escalates — and a session holding several nodes cannot run past the contract of any of
    them, so none lapses while the session that would deliver it is still working."""
    deadlines = [t.deadline for t in tasks if t.deadline]
    return int((min(deadlines) - project_now(engine.graph)).total_seconds()) if deadlines else None


#: The shortest session worth spawning: one with less left before its deadline is killed before it can report — floored
#: at a minute, sessions started past their deadline and died unparsed until the clock escalated (GB_coreutils_tn5lhw152)
MIN_SESSION_S = 60


def _too_late(engine, node_id, cap) -> dict | None:
    """A session that cannot report before its deadline is not spawned: the clock hands the node to its issuer."""
    if cap is None or cap >= MIN_SESSION_S:
        return None
    engine.emit_info("delegate", f"{node_id}: no session spawned — {max(cap, 0)} s left before its deadline; the clock "
                                 f"hands it to its issuer (§12.2)")
    return {"task_id": str(node_id), "status": "too_late"}


def _observed(engine, node_id, tasks, cwd, cap, _cb) -> tuple[dict, int | None]:
    """What the nodes' pinned checks print on the place before the session (`observe_place`), said in one line — in
    flight while it runs (a server read as idle was restarted under a spawn, see `run_executor`) — and the session's
    cap less the time it took: the session must still end inside its deadline (`_session_cap`)."""
    t0 = datetime.now()
    with _inflight("observation", engine, node_id):
        seen = observe_place(engine, tasks, cwd, cap)
    if rows := [r for rs in seen.values() for r in rs]:
        _cb(f"{node_id}: observed its place before the session — {sum(bool(r.get('matched')) for r in rows)} of "
            f"{len(rows)} pinned check(s) print exactly what they must")
    return seen, None if cap is None else cap - int((datetime.now() - t0).total_seconds())


def _unread(llm, unparsed: str) -> str:
    """The headline of a session that left no report: `unparsed` — unless what stops the project (the account's limit,
    the execution place down) refused its call: then nothing came to be read and no issuer's attention is owed."""
    return ("no report — the call was refused by what stops the project, nothing was answered"
            if refused_by_limit(calls_of(llm)) else unparsed)


def _fresh_disk(engine, agents, cwd) -> None:
    """A session starts: an end of the disk's watch nobody read for its place — its idle container ended between
    sessions — is not this session's (critic: it named a later ordinary cut)."""
    if cwd:
        ended_past_disk(execution_of(engine, agents).session(cwd))


def _past_disk(engine, agents, cwd) -> tuple:
    """(past, ended) of a session that left no report: `past`, its place's directories past its node's bound now
    (`place_past_disk`) — which no redial or retry lifts, every session there ended again; `ended`, why the disk's watch
    ended this one, if it did (`ended_past_disk`) — said, and lifted by the next session where its layer alone held it."""
    ex = execution_of(engine, agents).session(cwd) if cwd else None
    return (place_past_disk(ex), ended_past_disk(ex)) if ex is not None else (None, None)


def _run_session(llm, system: str, user: str, cfg: dict, cap, cwd: str | None, session: str | None = None) -> str:
    """One headless executor session with the work tools, in its node's place, under the role's caps — continuing
    the node's conversation with this executor where one is named (`session_key`)."""
    try:
        return llm.run_agent(system, user, allowed_tools=EXECUTOR_TOOLS, cwd=cwd, timeout=cap,
                             max_turns=cfg.get("max_turns"), session=session)
    except TypeError:  # a runner without the timeout/turn-cap/session params (fakes)
        return llm.run_agent(system, user, allowed_tools=EXECUTOR_TOOLS, cwd=cwd)


#: Lines of `git status` a reopen is shown (`_machine_state`).
SHOWN_STATUS = 40


def _machine_state(engine, tasks, cwd) -> str:
    """The place as the system reads it for a session reopened on a handover (`budget.run`): what the nodes' checks
    print on it now and what the work changed in it — the state itself, where the note is only the closing session's
    word about it."""
    rows = [r for rs in observe_place(engine, tasks, cwd).values() for r in rs]
    st = W.git(cwd, "status", "--short", execution=execution_of(engine)).stdout.splitlines() if cwd else []
    diff = W.git(cwd, "diff", "--stat", "HEAD", execution=execution_of(engine)).stdout.strip() if cwd else ""
    return ((observed_lines(rows) if rows else "")
            + (f"\n`git status --short` ({len(st)} path(s)):\n" + "\n".join(st[:SHOWN_STATUS])
               + (f"\n… and {len(st) - SHOWN_STATUS} more" if len(st) > SHOWN_STATUS else "") if st else "")
            + (f"\n\n`git diff --stat HEAD`:\n{diff}" if diff else ""))


def _spawn(engine, node_id, executor_id: str, cfg: dict, _llm, role: str, prompt: str, packet: str, schema: dict,
           verb: str, cwd, cap=None, work: bool = True, tasks: tuple = ()):
    """THE ONE FRAME every role session runs in — spawn · parse: the role's model, its prompt and packet with the
    report schema, under the in-flight registry (`busy`), its spend booked to the node; `work` = the work tools
    under the session cap, its context handed over at its ceiling and the role's budget (`budget.run`) with `tasks`'
    machine state, else read-only (a consent reads, it does not build). Returns (report or None, text, stats, llm, the
    observation callback) — what the report MEANS is the caller's, never the frame's."""
    _cb = emit_cb(engine, "delegate")
    llm = _llm or project_llm(engine, cfg.get("model", MODEL_DEFAULT))
    if work:
        llm.on_tick = _cb
        llm.budgeted, llm.context_budget = True, cfg.get("context_budget")   # the resource's, declared with its role
        llm.machine_state = lambda: _machine_state(engine, tasks, cwd)
        llm.reads_as_report = lambda text: parse_structured(text, schema) is not None
    llm.stage_hint = f"{node_id} {role}({executor_id})"
    system, user = (_PROMPTS / prompt).read_text(encoding="utf-8"), packet + schema_instruction(schema)
    stage = Stage.CONSENT if role == "consent" else Stage.EXECUTOR      # a consent reads; it is not the work
    with _inflight(verb, engine, node_id):
        try:
            text = (_run_session(llm, system, user, cfg, cap, cwd, conversation_of(engine, node_id, executor_id, role))
                    if work else
                    llm.run_agent(system, user, allowed_tools=("Read", "Glob", "Grep"), cwd=cwd))
        finally:
            # …booked once to its node, whatever the run raised after its sessions: a raise between two sessions of a
            # handover chain left eight paid sessions off the ledger (GB_c_compiler_ctx3b1285_10301332)
            stats = session_calls(llm, stage)
            engine.record_llm_usage(stage, llm, node_id)
    file_tech_reports(engine, report := parse_structured(text, schema), role, executor_id, node_id)
    return report, text, stats, llm, _cb


def unattended_here(engine, agents) -> None:
    """THE WORK THE SYSTEM DISPATCHES IS DONE WITH NOBODY WATCHING — so it runs where its place allows it
    (`ExecutionPort.agents_refused`): refused before anything of it runs, the plan's checks of its place included; the
    refusal is its project's stop (`delegate._the_place_is_down`)."""
    if why := execution_of(engine, agents).agents_refused():
        raise PlaceUnavailable(THIS_HOST, why)


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
    unattended_here(engine, agents)
    cap = _session_cap(engine, [task])
    if late := _too_late(engine, task_id, cap):
        return late
    cwd, unjoined, ws = _enter_workspace(engine, agents, task, [task])
    seen, cap = _observed(engine, task_id, [task], cwd, cap, _cb)
    if late := _too_late(engine, task_id, cap):
        return late
    _fresh_disk(engine, agents, cwd)
    _cb(f"{task_id}: executor {executor_id} spawned (workdir={cwd or 'cwd'}"
        + (f", cap {cap}s" if cap else "") + ")…")
    # The dispatcher's own spawn is the LONGEST thing this server does — up to a fifteen-minute
    # `claude -p` — and it was the one path that never appeared in `busy`, so a reconcile arriving
    # from another session read the server as idle and restarted it mid-run.
    report, text, stats, llm, _cb = _spawn(engine, task_id, executor_id, cfg, _llm, "executor", "executor.md",
                                           _executor_packet(engine, task, cwd, unjoined, seen), EXECUTOR_SCHEMA,
                                           "delegated_execution", cwd, cap, tasks=(task,))
    if report is None:
        # No signal is forged on a broken report: the node stays where it is; the FSM's own timeout
        # monitor escalates a stuck node (no second clock). Visible in the observation field.
        past, ended = _past_disk(engine, agents, cwd)
        _cb(f"{task_id}: {_unread(llm, 'executor report DID NOT PARSE — no signals sent; issuer attention needed')} "
            f"· executor {_stat_line(llm)}" + (f" · ended by the disk's watch: {ended}" if ended else ""))
        return {"task_id": str(task_id), "status": "unparsed", "report_text": text, "stats": stats,
                "cut": the_call_was_cut(llm, text or ""), "limit": refused_by_limit(calls_of(llm)), "past_disk": past,
                "disk_ended": ended}

    # `_decided_status` is the owner of "which of the three was this"; the dispatch enforces it and
    # this line only reports what the round amounted to. An unrecognised word is `undecided`, and
    # the caller can tell that from a delivery.
    status = _decided_status(report.get("status"))
    _report_into_signals(engine, task_id, executor_id, task, report,
                         status or str(report.get("status")), llm, _cb,
                         observed=engine.observed_here(task_id)
                         and agents.validator_for(hands or executor_id, project=engine.project_name) is not None,
                         workspace=ws, started_on=started_on, unjoined=unjoined)
    return {"task_id": str(task_id), "status": status or "undecided",
            "reported_status": None if status else report.get("status"), "stats": stats}


CONSENT_SCHEMA = {
    "type": "object",
    "properties": {"decision": {"type": "string", "enum": ["accept", "challenge"]},
                   "reason": {"type": "string", "description": "on a challenge: which criteria are "
                              "defective and why; on an accept: one line on why the contract holds"},
                   "tech_report": TECH_REPORT},
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
    unattended_here(engine, agents)
    kids = "\n".join(f"- `{k.id}` ({k.label()}) — {k.state.name}; "
                     f"Del={k.assignee}" for k in engine.graph.get_active_children(task_id)) or "- none"
    # …IN ITS OWN PLACE, made now as its first session would make it (`_enter_workspace`): asked in the base, before
    # its executor made one, it shared the base's model-client state with the root's executor and read its
    # conversations (measured, a stand-in model driving the real CLI). With no git base, the roster's directory
    here = _enter_workspace(engine, agents, task, [task])[0] or cfg.get("workdir")
    packet = (_executor_packet(engine, task, here)
              + f"\n## The split under your node — built by its children, merged into your tree: what your criteria "
                f"catch in it is yours to fix there, not a defect of your contract\n{kids}\n")
    answer, _t, _s, _l, _cb = _spawn(engine, task_id, executor_id, cfg, _llm, "consent", "consent.md", packet,
                                     CONSENT_SCHEMA, "delegated_consent", here, work=False)
    if answer is None:
        _cb(f"{task_id}: " + _unread(_l, f"{executor_id}'s consent DID NOT PARSE — nothing signalled")
            + f" · {_stat_line(_l)}")
        return {"task_id": str(task_id), "status": "unparsed", "limit": refused_by_limit(calls_of(_l))}
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
    unattended_here(engine, agents)
    _cb = emit_cb(engine, "delegate")
    cap = _session_cap(engine, todo)
    if late := _too_late(engine, top_id, cap):
        return late
    top = engine.graph.get_task(top_id)
    cwd, unjoined, ws = _enter_workspace(engine, agents, top, order)
    seen, cap = _observed(engine, top_id, todo, cwd, cap, _cb)
    if late := _too_late(engine, top_id, cap):
        return late
    _fresh_disk(engine, agents, cwd)
    _cb(f"{top_id}: one executor session ({executor_id}) for the scope's open node(s) "
        f"{', '.join(str(t.id) for t in todo)}" + (f", cap {cap}s" if cap else "") + "…")
    report, text, stats, llm, _cb = _spawn(engine, top_id, executor_id, cfg, _llm, "scope-executor",
                                           "executor_scope.md", _scope_packet(engine, top, order, cwd, unjoined, seen),
                                           SCOPE_SCHEMA, "delegated_execution", cwd, cap, tasks=tuple(todo))
    if report is None:
        past, ended = _past_disk(engine, agents, cwd)
        _cb(f"{top_id}: " + _unread(llm, "the scope session's report DID NOT PARSE — no signals sent")
            + f" · {_stat_line(llm)}" + (f" · ended by the disk's watch: {ended}" if ended else ""))
        return {"task_id": str(top_id), "status": "unparsed", "report_text": text, "stats": stats,
                "cut": the_call_was_cut(llm, text or ""), "limit": refused_by_limit(calls_of(llm)), "past_disk": past,
                "disk_ended": ended}
    _scope_report_into_signals(engine, order, executor_id, report, llm, _cb, workspace=ws, started_on=started_on,
                               unjoined=unjoined)
    return {"task_id": str(top_id), "status": "reported", "stats": stats}
