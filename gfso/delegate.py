"""Delegation — the registry-driven autostart machinery (designs doc §3.1-7 + §7, author-confirmed).

The issuer's ONLY act is setting Del: a node whose assignee is a REGISTERED llm-executor is picked up
from the frontier by the DISPATCHER, which spawns a headless executor (work tools, scoped cwd), wraps
its single structured report into the canonical FSM signals (ACCEPT/DELIVER/BLOCK/CHALLENGE,
source = the executor's id — the executor itself never touches the graph), then AUTO_PASS-VALIDATES on
DELIVER→VALIDATING with the registered llm-validator instrument and AUTO_PASS-SIGNALS the verdict
(PASS → DONE; FAIL(failed_criteria) → the FSM's own REWORKING loop, bounded by max_iterations).
An unparsed validator report NEVER auto-signals — it escalates to the issuer (the one manual point).
Unregistered ids = human = the system stays passive (the safe default); registered NON-executor kinds
never spawn (kind-guard). Identity/authority stays canon-exact: Del binds at delegation, the
executor's own report IS its Inv-1 consent, no second timeout clock (the FSM monitor owns time)."""
from __future__ import annotations

import contextlib
import json
import logging
import subprocess
import threading
import time
from pathlib import Path
from typing import Optional

from gfso import tools_llm as T
from gfso.engine.joins import NOT_ON_ITS_BRANCH
from gfso.engine.validation import whole_waits_for_its_parts
from gfso.config import DEFAULT_PROJECT, MODEL_DEFAULT, agents_path, max_sessions, provider, validator_retry_model
from gfso.llm import llm_factory
from gfso.places import cheap_to_ask
from gfso.tools import _agent_id
from gfso.inflight import _inflight, being_rewritten, in_flight
from gfso.adapters.verifiers import evaluate_unittest
from gfso.core.graph.model import generation_of_task
from gfso.core.protocol.procedure import BOUND_SPENT, criterionless, probes_from as _checks_of
from gfso.core.types import (HOST, TaskId, AgentId, Criteria, Signal, SignalData, Spec, State,
                             Verdict, Action, Mode, PlaceUnavailable,
                             SPAWNABLE_ACTIONS, files_at, passed, register_of, system_decides)
from gfso.issuer import (LIMIT_RETRY_S, Verbs, answer_open_questions, signal_ok as _signal, system_mover,
                          split_has_a_mover)
from gfso.adapters.llm.chat import answers, is_address
from gfso.adapters.llm.stats import is_limit, refused_by_limit, torn_among, what_stopped
from gfso.roster import AgentRegistry, _resolution_note, missing_workdir
from gfso.adapters.execution import release_rounds
from gfso.workspaces import (performer, _place_of, _where_it_joins, _workspace, clear_workspaces, execution_of,
                             join_whole, land_accepted, made, node_workspace, root_created, session_scope,
                             stands)
from gfso.packets import _EXECUTOR_STATES, _scope_order
from gfso.sessions import unattended_here, run_consent, run_executor, run_scope_executor

log = logging.getLogger(__name__)

#: How many times a call that was CUT before it answered — a validation, an executor's or a scope's session — is
#: redialled before the node falls through to the ordinary path (one retry, then parked). Finite: the point of the
#: budget is that it ends (Inv-5). SPACED (TORN_DELAY_S, doubling): redialled at once, a session cut by
#: "API Error: 403" was cut again four seconds later, parked, and its issuer's reassign 15 min on broke the scope
#: and re-armed the plan's gate — 82 min of re-planning (AUTO haiku coreutils, GB_coreutils_tn5q9r220); the
#: outage had passed by then. Four spaced redials wait out 7.5 min of it.
TORN_REDIALS = 4
TORN_DELAY_S = 30


#: The ISSUER's answer to a dispute (§12.4's two exits of CHALLENGED). `accept` carries the
#: corrected criteria — a new packet version, re-consented — and `reject` carries the justification
#: the canon requires of it (§16.12: the negative closure is what makes a challenge answerable).
#: The model layer the issuer function runs on — handed to it, so it sits below this layer (`Verbs`).
#: Seconds between re-asks of the validator on a node whose issuer is the system and whose last two
#: validations left no verdict, until VALIDATING's own bound (T_validate) ends the wait. Short: what comes back
#: without a verdict here is a model's report that ran and fell short of its coverage (a torn or never-started call
#: has its own redial), and waiting makes the next one no fuller — at 600 s correct deliveries sat 19–75 min in
#: VALIDATING (GB_coreutils_tmiy4m001). Each re-ask is a whole validation of minutes, so nothing spins. Where no model
#: started at all the instant answer is the same refusal again, so that one waits as before (`REVALIDATE_IDLE_S`).
REVALIDATE_S, REVALIDATE_IDLE_S = 30, 600


def _reask_wait(ret) -> float:
    """How long a node waits before its validator is asked again after two runs with no verdict — one rule for the
    node's and the scope's doors."""
    return REVALIDATE_IDLE_S if ret in (None, "no-verdict:never-ran") else REVALIDATE_S
#: A refused root join is tried again after this many seconds, doubling per refusal up to the cap: the refusal
#: (a dirty base, a conflict) waits on a person, and each try is a merge and an abort on the user's own tree.
JOIN_RETRY_S, JOIN_RETRY_MAX_S = 5, 300


def _the_place_is_down(engine, e: Exception) -> bool:
    """Did a round meet its execution place down outside a model call (a git or a copy in the container)? Then it is
    the stop a booked call makes (`Engine.stop_for_the_place`), and the round answered nothing."""
    if isinstance(e, PlaceUnavailable):
        engine.stop_for_the_place(e.place, str(e))
    return isinstance(e, PlaceUnavailable)


def _system_issues(engine, agents, task_id) -> bool:
    """Does the SYSTEM make this node's issuer moves (a machine issuer, or the AUTO root's customer)?"""
    return system_mover(engine, agents, TaskId(task_id), "escalation") is not None


def _contact_place(engine, agents, node) -> "str | None":
    """Where an issuer's question is answered from contact — the node's validator's place — or None where no contact
    can run: a directory that is not there (the run returned nothing and the question waited forever), or a
    transport without tool-using agent runs (`GFSO_PROVIDER=generic`). None asks as before contact existed."""
    where = validator_workdir(engine, agents, node)
    return (where if where and provider() != "generic" and cheap_to_ask(where) and stands(engine, agents, where)
            else None)


def _in_flight_as(name: str, fn):
    """`fn(engine, node, …)` in flight for every reader while it runs (`gfso.inflight`), as each session the system
    starts is — the plan review an issuer's turn runs was not, and a stop read `stopped` over it (critic over f622997)."""
    def run(engine, node, *a, **kw):
        """`fn` on `node`, registered while it runs."""
        with _inflight(name, engine, node):
            return fn(engine, node, *a, **kw)
    return run


ISSUER_VERBS = Verbs(llm=llm_factory, busy=_inflight, review=_in_flight_as("review_decomposition", T.review_decomposition),
                     # the split is its node's EXECUTOR's move: authored by him, it re-authors no contract (Inv-1)
                     refine=lambda engine, node: T.SYSTEM_TOOLS["auto_decompose"](
                         engine, root_id=node, depth=1, author=str(engine.graph.get_task(node).assignee)),
                     place=lambda engine, agents, node: _contact_place(engine, agents, node),
                     execution=lambda engine: execution_of(engine, default_agents()))


def publish_the_workforce(engine, roster: dict) -> None:
    """Hand the engine the roster's executors and whose each is — what a mode issues nodes to — and what KIND every
    registered id is. Called by every round of the dispatcher and by the verbs that change the roster or read the pool
    before a round has run (registering, setting a mode): published only by the round, a root created right after its
    executor was registered kept or lost its creator as issuer by which thread ran first."""
    kinds = {aid: cfg.get("kind") for aid, cfg in roster.items()}
    if engine.workforce.publish_roster(kinds):
        # …a role on or off the roster is news to an open page (its goal form's mode readiness), told where every roster
        # change is published — the roster lives in its own file, beside the store the plan's watch sees (`PlanWatch`)
        engine.emit_info("graph", "the roster changed")
    engine.workforce.publish_executor_pool({aid: cfg.get("project") for aid, cfg in roster.items()
                                  if cfg.get("kind") == "llm-executor"},
                                 {aid: (cfg.get("model") or MODEL_DEFAULT)
                                       + (f", up to {cfg['max_turns']} turns" if cfg.get("max_turns") else "")
                                       + (f", context budget {cfg['context_budget']} tokens"
                                          if cfg.get("context_budget") else "")
                                  for aid, cfg in roster.items() if cfg.get("kind") == "llm-executor"})


def confirm_system_cancellations(engine, agents: "AgentRegistry", in_flight=lambda t: False) -> None:
    """A system executor's acknowledgment of a cancellation (CONFIRM_CANCEL, §12.6): the one move of
    CANCELLING, and its executor's — which nobody made, so a cancelled subtree waited out CANCELLING's
    bound. The in-flight state is the workspace as the executor left it: the system holds no other."""
    for t in engine.tasks_by_state(State.CANCELLING):
        cfg = agents.get(str(t.assignee or "")) or {}
        if cfg.get("kind") == "llm-executor" and not in_flight(t):
            _signal(engine, t.id, Signal.CONFIRM_CANCEL, str(t.assignee),
                    in_flight="cancelled by its issuer; the workspace stands as the last round left it")


def _standing_instrument_verdict(engine, task_id: TaskId) -> Optional[dict]:
    """An instrument's verdict that stands on THIS delivery — {verdict, failed_criteria}, reused rather than paid for
    twice — or None. Current: on this delivery, with nothing it is built from delivered again or FAILed since (the
    engine's own currency rule, `record_stands`, through `current_exec_verdict` — the one question a signature asks
    too; read off the generation alone, a PASS over parts delivered again was replayed into a gate that refused it,
    three times, critic 2026-09-28). An instrument's: a self-report and a verdict asserted by hand are the
    executor's and the issuer's own words, and replaying either under the registered validator's name put verdicts
    an instrument never gave into the log as its PASS (both stranger doors, 2026-09-02)."""
    rec = engine.current_exec_verdict(task_id)
    if (rec is None or engine.verdict_provenance(task_id) != "instrument"
            or rec.get("verdict") not in (Verdict.PASS, Verdict.FAIL)):
        return None
    return {"verdict": rec["verdict"], "failed_criteria": list(rec.get("failed_criteria") or ())}


def _standing_verdicts(engine, top_id: TaskId) -> dict:
    """The instrument's verdicts standing on the deliveries of the scope that wait, per node — but only where nothing
    below the node is validated again: a whole's result is its subtree's artifact, so a part re-delivered under it
    makes its record a verdict on a result that no longer stands (critic: a SEMI holder signed a whole's PASS read off
    such a record, over a part's rework that broke it). A sibling's ⊥ no longer re-buys a whole scope's validation."""
    return {str(t.id): v for t in engine.scope_members(top_id)
            if t.state.name == "VALIDATING" and (v := _standing_instrument_verdict(engine, t.id))}


def _sign_scope(engine, top, verdicts: dict, validator_id: str, sign: bool) -> str:
    """Sign a scope's recorded verdicts in build order, parts first, each by its issuer: a node inside the scope
    by the scope's executor, the top by the instrument where its issuer's signature is automated.

    A node's verdict is signed only over a footing that stands — its parts and its producers DONE. Where it does
    not, the delivery is answered at once rather than left to wait in VALIDATING across someone else's rework,
    which outlasted T_validate and escalated good deliveries (critic, 2026-09-28): a whole over a part that fails
    FAILs, on the criteria of the whole mapped to that part (Thm 1 makes that verdict true; Inv-3); any other node
    whose footing is being redone — a consumer beside a failing producer, a node over a part reworked, disputed or
    re-presented — has no true verdict yet, so its issuer re-presents it (Inv-1: a re-ASSIGN keeping the criteria
    answers nothing), and it is re-delivered over the fix. A footing still awaiting its own verdict is waited for.
    The whole is re-delivered with its parts' rework, in the same session (`_scope_report_into_signals`)."""
    failing, undecided, again = set(), set(), set()
    for t in [t for t in _scope_order(engine, engine.scope_members(top.id)) if str(t.id) in verdicts]:
        tid, own = str(t.id), verdicts[str(t.id)]
        kids = {str(k.id) for k in engine.graph.get_active_children(t.id)}
        producers = {str(e.from_id) for e in engine.adopted_dependencies() if str(e.to_id) == tid}
        fails = list(own.get("failed_criteria") or ()) if own.get("verdict") == Verdict.FAIL else []
        through: dict = {}
        for m in t.criterion_mappings:
            if str(m.child_id) in failing and m.criterion_name not in fails:
                through.setdefault(m.criterion_name, []).append(str(m.child_id))
        fails += [c for c in through if c not in fails]
        states = {x: (engine.graph.get_state(TaskId(x)) or State.IDLE).name for x in kids | producers}
        waiting = {x for x, st in states.items() if x in undecided or (st == "VALIDATING" and x not in failing | again)}
        if not fails and (own.get("verdict") is None or waiting):
            undecided.add(tid)
            continue
        redone = {x for x, st in states.items() if st != "DONE"} - waiting
        if tid == str(top.id) and not sign:
            continue                                   # the record stands; the signature is its issuer's
        issuer = validator_id if tid == str(top.id) else str(engine.graph.issuer_of(t.id))
        if not fails and redone:
            # inside the scope its issuer is the scope's executor, whose moves the system makes; the top's issuer
            # is across a seam, and his decision stays his (a lapse hands it to him, §12.5)
            if tid != str(top.id) and _represent(engine, t, str(engine.graph.issuer_of(t.id)), redone):
                again.add(tid)
            else:
                undecided.add(tid)
            continue
        failing.update({tid} if fails else set())
        if (_signal(engine, t.id, Signal.FAIL if fails else Signal.PASS, issuer,
                **({"failed_criteria": tuple(fails),
                    "reason": "failed in its scope's validation"
                              + (f" — its part(s) {', '.join(sorted(kids & failing))} failed, and a whole is not "
                                 f"attained while a part fails (Thm 1)" if kids & failing else "")} if fails else {}))
                and fails and through):
            engine.note_failed_through_parts(t.id, through)
    state = engine.graph.get_state(top.id)
    return ("pass" if state == State.DONE else "fail" if failing else
            "recorded" if not sign and str(top.id) not in undecided else
            # …every undecided node ⊥ by checks that ran their whole bound on the tree it delivered: asked again, the same
            # tree times out again (`BOUND_SPENT`)
            "no-verdict:bound" if undecided and not again and all(
                BOUND_SPENT in str((verdicts.get(x) or {}).get("error") or "") for x in undecided) else
            "no-verdict" if undecided and not again else "rejected")


@system_decides()
def _represent(engine, t, issuer: str, redone: set) -> bool:
    """Its issuer re-presents a delivery whose footing is being redone: a re-ASSIGN under the same packet (Inv-1),
    which answers nothing — the node is re-delivered over the fix and validated then."""
    try:
        engine.revise(t.id, t.spec, AgentId(issuer))
    except ValueError as e:
        engine.emit_info("delegate", f"{t.id}: not re-presented ({e}) — it waits in VALIDATING for its issuer")
        return False
    engine.emit_info("delegate", f"{t.id}: re-presented by its issuer — what it is built from "
                                 f"({', '.join(sorted(redone))}) is being redone, so its delivery has no verdict "
                                 f"yet; it is re-delivered over the fix (Inv-1)")
    return True


def _auto_validate_scope(engine, top_id: TaskId, agents: AgentRegistry, _llm=None, sign: bool = True) -> str:
    """The scope's ONE validation, and its signatures: the instrument bound to the scope's executor validates
    every delivery the scope holds in one run, each node's own verdict is recorded, and `_sign_scope` signs
    them. 'pass' / 'fail' / 'recorded' / 'rejected' / 'no-verdict' / 'no-instrument', as `_auto_validate`."""
    top = engine.graph.get_task(top_id)
    validator_id = _which_instrument_validates(engine, top, top_id, agents, engine.project_name)
    if validator_id is None:
        engine.emit_info("delegate", f"{top_id}: no llm-validator registered — the scope's validation stays manual")
        return "no-instrument"
    verdicts, out = _standing_verdicts(engine, top_id), {}
    if (missing := {str(t.id) for t in engine.scope_members(top_id) if t.state.name == "VALIDATING"} - set(verdicts)):
        vcfg = agents.get(validator_id) or {}
        # …in flight for every reader while it runs, as each session the system starts is: a stop read `stopped` over it
        with _inflight("validate_scope", engine, top_id):
            out = T.validate_scope(engine, str(top_id),
                                   validator_workdir(engine, agents, top_id, named_validator=str(validator_id), vcfg=vcfg),
                                   validator=str(validator_id), model=vcfg.get("model", MODEL_DEFAULT), _llm=_llm,
                                   only=missing)
        if out.get("inflight"):
            return "rejected"
        verdicts = {**verdicts, **(out.get("verdicts") or {})}
    if verdicts:
        return _sign_scope(engine, top, verdicts, str(validator_id), sign)
    if refused_by_limit(out.get("stats")):
        return "no-verdict:limit"
    if any(isinstance(c, dict) and c.get("ended") == "uncopied" for c in out.get("stats") or ()):
        return "no-verdict:never-ran"                    # …a delivery not copied to be judged: no validator started
    return "no-verdict:torn" if torn_among(out.get("stats") or ()) else "no-verdict"   # as a node's (`_classify_no_verdict`)


def _oracle_workdir(engine, vcfg: dict):
    """The workspace for this project from the issuer-side oracle map (same map the unittest-checker
    uses), so a criteria validator runs the code where the executor delivered it. None if absent."""
    project = getattr(engine, "_project_name", None) or "default"
    try:
        entry = json.loads(Path(vcfg["oracle_map"]).read_text(encoding="utf-8")).get(project)
        return entry.get("workdir") if entry else None
    except Exception:
        return None


def _checker_validate(engine, task_id: TaskId, vcfg: dict, workdir: str | None = None, execution=None) -> dict:
    """Deterministic HIDDEN-TEST validation (the issuer's oracle — the executor never sees the tests).
    Runs the project's hidden unittest suite against the delivered solution.py, maps each test method
    to the criterion of the same name, returns {verdict, per_criterion, failed_criteria}. No LLM, no
    false-PASS. The oracle map (config: `oracle_map`) is issuer-side; the agent has no path to it.
    It has NO default: a shipped default pointed every install at one experiment's map file, which
    on any other machine simply did not exist — a registration that names no map now says so."""
    # …IN THIS PROCESS, ON THE SERVER'S MACHINE: it imports what the delivery wrote, so no project whose work the system
    # holds in a container may name it (a delivery's code ran on the host under a container execution, critic, live)
    if execution is not None and execution.files is not HOST:
        return {"verdict": None, "note": "a unittest-checker runs a delivery on this machine, and this project's work runs "
                                         "in a container: refused — register an llm-validator with pinned checks"}
    project = getattr(engine, "_project_name", None) or "default"
    try:
        entry = json.loads(Path(vcfg["oracle_map"]).read_text(encoding="utf-8")).get(project)
    except Exception:
        entry = None
    if not entry:
        return {"verdict": None, "note": f"no hidden-test oracle registered for project {project}"}
    crits = entry["criteria"]
    sol = str(Path(workdir or entry["workdir"]) / "solution.py")      # the node's own delivery, where it has a place
    if (delivered := files_at(sol).read_text(sol)) is None:
        return {"verdict": Verdict.FAIL, "failed_criteria": list(crits),
                "per_criterion": [{"criterion": c, "verdict": "fail",
                                   "evidence": "no solution.py delivered"} for c in crits]}
    results = evaluate_unittest(delivered, Path(entry["canonical"]).read_text(encoding="utf-8"))
    by = {r.check_name: r for r in results}
    per, failed = [], []
    for c in crits:
        r = by.get(c)
        ok = bool(r and r.passed)
        per.append({"criterion": c, "verdict": "pass" if ok else "fail",
                    "evidence": ("passed" if ok else (r.details[:400] if r else "test not found in suite"))})
        if not ok:
            failed.append(c)
    return {"verdict": Verdict.PASS if not failed else Verdict.FAIL, "per_criterion": per, "failed_criteria": failed}


def _children_workdir(engine, agents: AgentRegistry, task_id: TaskId) -> str | None:
    """Where this node's work actually lives: the workdir of a registered child executor.

    A parent whose own Del is the unregistered user-agent has no directory of its own, but its
    children do — and their directory is the one holding the artifact the parent aggregates."""
    for kid in engine._graph.get_active_children(task_id):
        if (wd := (agents.get(kid.assignee or "") or {}).get("workdir")):
            return wd
    return None


def validator_workdir(engine, agents: AgentRegistry, task_id: TaskId,
                    named_validator: str | None = None, vcfg: dict | None = None) -> str | None:
    """WHERE THE VALIDATOR OF THIS NODE STANDS — one answer, whichever door asked.

    There were two, and they disagreed. Probed 2026-09-07 with an executor registered against
    `WORK` and a validator against `SCRATCH`: the dispatcher sent the validator to `WORK`, a manual
    `validate_result(node, validator="val-1")` sent it to `SCRATCH`, and on a node held by an
    unregistered person the manual door sent it to `SCRATCH` even with no validator named. Three
    orders of priority for one question.

    The order below is the dispatcher's, and it is the one a run already paid for: **the graph
    before the roster**. The validator's registered directory is a roster fact; where the work IS is
    a graph fact, and only the second is true by construction (measured 2026-08-21 — a stale `val-1`
    from an older experiment pointed at a scratch directory, the root was validated there, the report
    said "no implementation exists", and a false FAIL over seventeen criteria drove the run into the
    rework loop that ended it).

    The roster is still asked, and that is the OTHER fix this keeps: a root is normally held by the
    caller themselves, an id the roster does not know, so the graph answers nothing and the named
    validator's own directory is what saves the call (measured on the HTTP door 2026-09-02, where
    the refusal "agent has no registered workdir" stood while a validator with the right directory sat
    in the same roster). It answers second, not first.
    """
    task = engine.graph.get_task(task_id)
    executor = task.assignee if task is not None else None
    roster_side = (named_validator, executor,
                   agents.validator_for(executor, project=engine.project_name))
    # …and before the roster's directory, the node's OWN place when it has one: the roster names the base every
    # executor branches from, where a sibling may be mid-edit — the torn read a node workspace exists against
    return (node_workspace(engine, agents, task_id)
            or (agents.get(executor or "") or {}).get("workdir")
            or _children_workdir(engine, agents, task_id)
            or next((wd for who in roster_side
                     if who and (wd := (agents.get(str(who)) or {}).get("workdir"))), None)
            or _oracle_workdir(engine, vcfg or {}))


def _validate_with(engine, agents, task_id, task, validator_id, vcfg, sign, T,
                model_override, _llm) -> dict:
    """Run whichever instrument this node is bound to, and hand back its report.

    Two instruments under one contract (`{verdict, per_criterion, failed_criteria}`) and very
    different economics: the deterministic oracle runs a hidden suite in seconds, the
    read-only validator spends a model run. Which is bound is the roster's business; the
    caller only needs the report."""
    if vcfg.get("kind") == "unittest-checker":
        # deterministic hidden-test oracle — runs the suite the executor never sees, records the
        # per-criterion verdict (the integrity gate applies), then auto-signals below.
        generation = engine.graph.generation_of(task_id)     # the delivery THIS check reads (§10.3 gate)
        read_at = len(engine.audit_log())               # …and where the log stood when it read it
        out = _checker_validate(engine, task_id, vcfg, node_workspace(engine, agents, task_id), execution_of(engine, agents))
        if out.get("verdict") in (Verdict.PASS, Verdict.FAIL):
            try:
                engine.record_exec_verdict(task_id, out["verdict"], out.get("failed_criteria") or [],
                                           validator_id, per_criterion=out.get("per_criterion"),
                                           generation=generation, log_at=read_at)
            except Exception as e:  # a malformed report is ⊥, not a verdict (§2) — never auto-signal it
                engine.emit_info("delegate", f"{task_id}: checker verdict refused ({e})")
                out = {"verdict": None}
        f = out.get("failed_criteria") or []
        engine.emit_info("delegate", f"{task_id}: unittest-checker → {out.get('verdict')} {out.get('note') or ''}"
                         + (f" (failed: {', '.join(f)})" if f else ""))
    else:
        ecfg = agents.get(task.assignee) if task else None   # validate WHERE the executor worked
        # The criteria validator must run the code IN the workspace. When neither the executor nor
        # the validator config pins a workdir (self-execution: the executor is the unregistered user-agent),
        # fall back to the issuer-side oracle map, where setup records this project's workspace.
        # …and when the executor has none, the CHILDREN's workdir before the validator's own. The
        # validator's registered directory is a roster fact; where the work IS is a graph fact, and
        # only the second one is true by construction. Measured 2026-08-21: a stale `val-1` entry
        # from an older experiment pointed at a scratch directory, the root was validated there, the
        # report said "no implementation exists" — and a FALSE FAIL over seventeen criteria drove
        # the run into the rework loop that ended it. The snapshot taken at that same delivery holds
        # every file the validator could not find.
        _wd = validator_workdir(engine, agents, task_id,
                              named_validator=str(validator_id), vcfg=vcfg)
        out = T.SYSTEM_TOOLS["validate_result"](engine, str(task_id),
                              model=model_override or vcfg.get("model", MODEL_DEFAULT),
                              workdir=_wd, validator=str(validator_id), _llm=_llm)


    return out


def _which_instrument_validates(engine, task, task_id: TaskId, agents: AgentRegistry,
                             project: str | None) -> str | None:
    """Which registered validator validates this node — and a sentence when it is nobody's.

    Two corrections live here, both bought on live runs, and they are one question: the
    roster is shared by every project on the server, so "the first registered role" is
    somebody else's instrument standing in somebody else's directory.
    """
    validator_id = agents.validator_for(task.assignee if task else None, project=project)
    # A node whose executor is the UNREGISTERED user-agent (the root, and every node the agent keeps
    # for itself) has no workdir of its own, so the workspace-matching rule above has nothing to
    # match on and falls back to "first registered" — which is another run's validator. Measured
    # 2026-08-20: a root was validated by `val-1` from an experiment, whose workdir pointed at that
    # experiment's scratch directory. The graph knows what the right answer is: this project's
    # CHILDREN are delegated to registered executors, and their workdir is where the work lives.
    if task is not None and not (agents.get(task.assignee or "") or {}).get("workdir"):
        for kid in engine._graph.get_active_children(task_id):
            if (agents.get(kid.assignee or "") or {}).get("workdir"):
                if (near := agents.validator_for(kid.assignee, project=project)):
                    validator_id = near
                break
    # …AND WHOSE INSTRUMENT IT IS, when it is nobody's in particular. The roster is one shared file,
    # so a project that registered nothing gets whichever unscoped role came first — on the CLI door
    # 2026-09-02 that was `val-1`, a leftover of a measurement run whose registered workdir points
    # into that run's scratch directory, and it signed every node of a stranger's graph. The choice
    # is deliberate (the arm's library roles carry no project either), so what is owed is not a
    # refusal but a sentence: said ONCE per node, where the person driving the graph reads it.
    if validator_id is not None:
        _vcfg = agents.get(validator_id) or {}
        if not _vcfg.get("project") and project:
            if engine.say_once(f"unscoped:{task_id}:{validator_id}"):
                engine.emit_info(
                    "delegate",
                    f"{task_id}: validated by '{validator_id}', which belongs to NO project — the roster "
                    f"is shared by every project of this server, and this role"
                    + (f" works in {_vcfg['workdir']}" if _vcfg.get("workdir") else " has no workdir")
                    + f". Register your own (`register_agent('<id>', 'llm-validator', workdir=…)`) to "
                      f"be validated by an instrument standing in YOUR work.")
    return validator_id


def _pass_held_by_open_parts(engine, agents, task_id: TaskId) -> bool:
    """Do parts of this whole stand open at the moment a machine would sign its PASS (a child attached while its validator
    ran)? Then it is not signed: at a seam the gate admits the PASS (§12.8), and a machine signing it closed the whole over
    work nobody had done (Thm 1). What a verdict accepts is the commit DELIVER recorded (§11.3), which holds no such part,
    so waiting for the part and validating that commit again would land the result without it: where the system issues,
    the delivery is re-presented at once, as `_sign_scope` does a footing being redone, and comes again over the part.
    Elsewhere the node waits in VALIDATING: its issuer's to move, and its bound hands it to him (§16.14)."""
    t = engine.graph.get_task(task_id)
    # …where the gate refuses it anyway, the refusal is the answer, with its reason
    if whole_waits_for_its_parts(engine.graph, t) or not (parts := engine.joins.open_parts(task_id)):
        return False
    named = {str(k.id) for k in parts}
    if not (_system_issues(engine, agents, task_id) and _represent(engine, t, str(engine.graph.issuer_of(t.id)), named)):
        engine.emit_info("delegate", f"{task_id}: its validator's PASS stands on the record, not signed: "
                                     f"{', '.join(sorted(named))} stand(s) open under it (Thm 1)")
    return True


def _replay_a_standing_verdict(engine, agents, task_id: TaskId, rec: Optional[dict], validator_id, sign: bool):
    """Reuse a validator's ruling on THIS delivery (`_standing_instrument_verdict`) instead of paying for a second one.

    Returns the outcome string, or None meaning "nothing to reuse — run the instrument"."""
    if rec is not None:
        if not sign:
            # A verdict for THIS delivery already stands and the signature is not ours to give, so
            # there is nothing left to do — and certainly not another paid run over the same
            # delivery, which is what happened while this path went on to signal (measured on the
            # human door 2026-08-22).
            engine.emit_info("delegate", f"{task_id}: already validated for this delivery — verdict "
                                         f"{rec['verdict']} stands on the record; signing is yours.")
            return "recorded"
        engine.emit_info("delegate", f"{task_id}: fresh recorded verdict {rec['verdict']} reused — "
                                     f"no duplicate validator run")
        sig = Signal.PASS if rec["verdict"] == Verdict.PASS else Signal.FAIL
        if sig == Signal.PASS and _pass_held_by_open_parts(engine, agents, task_id):
            return "rejected"
        if _signal(engine, task_id, sig, validator_id,
                   **({"failed_criteria": tuple(rec.get("failed_criteria") or ())}
                      if sig == Signal.FAIL else {})):
            return "pass" if sig == Signal.PASS else "fail"
        engine.emit_info("delegate", f"{task_id}: reused verdict {rec['verdict']} REJECTED by the "
                                     f"FSM — the node revalidates on the graph's next change")
        return "rejected"
    return None


def _say_it_is_hand_asserted(engine, task_id: TaskId, rec: dict) -> None:
    """Why a standing verdict is not being replayed: a person asserted it, and that is theirs to sign.

    Said where the reuse would have happened, because from outside the two are indistinguishable —
    the node simply sits there while an instrument runs that "already had a verdict".
    """
    engine.emit_info("delegate",
                     f"{task_id}: a verdict is on the record for this delivery but it was ASSERTED "
                     f"BY HAND ({rec.get('validator')}) — that is the issuer's own word, not a "
                     f"verdict this dispatcher may replay under an instrument's name. Sign it "
                     f"yourself, or let the instrument run.")


def _classify_no_verdict(engine, task_id: TaskId, out: dict) -> str:
    """A validation that returned no verdict, said where the issuer reads and classified by what ended it: the
    account's limit, a cut call, a model that answered badly, or one that never ran."""
    # The report is kept on disk, not merely "in the tool's output": under delegation the tool's
    # caller is this dispatcher, which reads a verdict and nothing else, so the old wording named
    # a place no one could look — and the evidence for why a validator could not state a verdict
    # was gone by the time anyone asked.
    # …AND WHETHER IT COST ANYTHING, because otherwise the reader has to infer it and two of
    # them inferred it wrong. A validator that never made a model call — refused at the preflight
    # because its registered directory holds none of this delivery, which is what a foreign
    # unscoped role does — and a validator that spent a paid run and came back unreadable are the
    # same line here, and they are opposite facts about the money. Two doors reported "failed
    # validator runs are billed and appear in no stage" from exactly this ambiguity (wave 25,
    # 2026-09-05); probed afterwards, the spend of a real unreadable run IS recorded, so what
    # was actually missing is this sentence.
    # WHAT THE TOOL OBSERVED, BEFORE ANYTHING THIS LAYER INFERS. `validate_result` returns an
    # `error` when the validation never got as far as a model — an observation, with the reason in
    # it — and this line threw it away and reconstructed a cause from a cost of zero instead
    # ("it was refused before it started"). On 2026-09-05 that sentence stood over three dead
    # runs, and the arm reading the log then wrote a THIRD invented cause on top of it. Zero
    # spend is a fact about the money and about nothing else.
    _spent = sum(float(c.get("cost_usd") or 0) for c in (out.get("stats") or ()))
    _why = str(out.get("error") or "").strip()
    engine.emit_info("delegate",
                     f"{task_id}: validator verdict UNPARSED/error — "
                     + (f"its call was refused: {_stopped}" if (_stopped := what_stopped(out.get("stats"))) else "issuer must decide")
                     + (f" · {_why}" if _why else "")
                     + (f" · this run cost ${_spent:.4f} (recorded in `usage`)" if _spent
                        else " · no model call is recorded for it, so `usage` will not show it")
                     + (f" (report: {out['report_kept_at']})" if out.get("report_kept_at")
                        else " (report not kept)"))
    # THREE OUTCOMES, NOT TWO. A validator that was never started, a validator that answered badly, and
    # a validator whose call was CUT are three different facts, and only the last one was being
    # read as one of the other two. The provider marks it where it is visible (the CLI's stream
    # ended with no result event — `transport_torn`); here it only has to be believed rather
    # than re-derived from a cost of zero, which is the inference that misdiagnosed it.
    _stats = out.get("stats") or ()
    if BOUND_SPENT in f"{_why} {out.get('verdict_defects') or ''}":     # …a refused report's reason rides here
        return "no-verdict:bound"
    if refused_by_limit(_stats) or is_limit(_why):
        return "no-verdict:limit"
    if torn_among(_stats):
        return "no-verdict:torn"
    return "no-verdict" if (_stats or _spent) else "no-verdict:never-ran"


def _auto_validate(engine, task_id: TaskId, agents: AgentRegistry, _llm=None,
                   model_override: str | None = None, sign: bool = True) -> str | None:
    """DELIVER→VALIDATING auto-fires the registered validator instrument; the verdict AUTO_PASS-SIGNALS
    (PASS → DONE; FAIL(failed_criteria) → REWORKING — the rework loop lives in the FSM, max_iterations
    bounds it). verdict:null NEVER auto-signals — the one escalation to the issuer. Returns the
    outcome for the dispatcher: 'pass'/'fail' (signed), 'rejected' (the FSM refused the verdict —
    ≠ no-verdict: the graph wasn't ready, revalidate on its next change), 'no-verdict'."""
    task = engine.graph.get_task(task_id)
    _proj = engine.project_name
    validator_id = _which_instrument_validates(engine, task, task_id, agents, _proj)
    if validator_id is None:
        engine.emit_info("delegate", f"{task_id}: no llm-validator registered — validation stays manual")
        # …AND SAID AS ITSELF, not as a failure. This returned a bare None, which the caller reads as
        # "the run died", so a graph that simply never had an instrument was given a retry (one paid
        # model run) and then PARKED for its issuer as "validator produced no verdict twice". An
        # absence of an instrument and an instrument that failed are opposite facts.
        return "no-instrument"
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
    # …WHAT IS REUSED IS AN INSTRUMENT'S VERDICT ON THIS DELIVERY, read by the one rule the scope's validation reads
    # too (`_standing_instrument_verdict`); a verdict a person asserted is said to be theirs, not replayed.
    if engine.current_exec_verdict(task_id) is not None and engine.verdict_provenance(task_id) == "by_hand":
        _say_it_is_hand_asserted(engine, task_id, engine.current_exec_verdict(task_id))
    if (out := _replay_a_standing_verdict(
            engine, agents, task_id, _standing_instrument_verdict(engine, task_id) if _vkind != "unittest-checker" else None,
            validator_id, sign)) is not None:
        return out
    vcfg = agents.get(validator_id) or {}
    out = _validate_with(engine, agents, task_id, task, validator_id, vcfg, sign, T,
                      model_override, _llm)
    if out.get("inflight") or out.get("waiting_on"):
        # Neither of these is a failed validation, so neither may cost the node its one
        # no-verdict retry: `inflight` = another validator run (e.g. a manual `validate_result`)
        # already holds this generation; `waiting_on` = the node aggregates children that have
        # not settled, so there is nothing to validate yet (Thm 1). Both behave like a rejected
        # verdict — free the dedup key and revalidate on the graph's next change.
        engine.emit_info(
        "delegate",
        f"{task_id}: validator already in flight — duplicate spawn suppressed"
        if out.get("inflight") else
        f"{task_id}: not validated yet — waiting on {', '.join(out['waiting_on'])}")
        return "rejected"
    verdict = out.get("verdict")
    if not sign:
        # THE INSTRUMENT RAN; THE SIGNATURE IS NOT THE INSTRUMENT'S TO GIVE. A human issuer who
        # registers a validator has asked for the validation, not for the decision — §10.2 keeps the
        # verdict the issuer's act, and what the instrument owes them is the record. Measured on two
        # doors 2026-08-21: both testers registered an `llm-validator`, kept the root for themselves,
        # and watched nothing happen at all, because the path was skipped whole rather than split at
        # the signature. `register_agent` had promised it fires "on EVERY delivery".
        if verdict:
            engine.emit_info(
                "delegate",
                f"{task_id}: validated for you — the verdict is {verdict}, on the record "
                f"(`get_verdict {task_id}`). Signing is yours: `signal {task_id} {verdict} <you>` "
                f"when you agree with it.")
        return "recorded" if verdict else _classify_no_verdict(engine, task_id, out)
    _why: list = []
    if verdict == Verdict.PASS:
        if _pass_held_by_open_parts(engine, agents, task_id):
            return "rejected"
        if _signal(engine, task_id, Signal.PASS, validator_id, _why=_why):
            return "pass"
    elif verdict == Verdict.FAIL:
        if _signal(engine, task_id, Signal.FAIL, validator_id, _why=_why,
                   failed_criteria=tuple(out.get("failed_criteria") or ())):
            return "fail"
    else:  # null/error — never auto-signal an unparsed verdict
        return _classify_no_verdict(engine, task_id, out)
    # WITH THE FSM'S OWN REASON. "The node revalidates on the graph's next change" is true and
    # useless on its own: some refusals are transient (children not settled yet — the graph WILL
    # change) and some are standing (the node's plan no longer passes the Syntactic level — nothing
    # will change it but a person). Told apart only by the reason, which existed and went to the log
    # alone, so an unattended run waited out its whole ceiling on a refusal nobody could read.
    engine.emit_info("delegate", f"{task_id}: validator verdict {verdict} REJECTED by the FSM"
                     + (f" — {_why[0]}" if _why else "")
                     + ". The node revalidates on the graph's next change; if that refusal is about "
                       "the node's own plan rather than about its children, nothing will change it "
                       "on its own — `list_holes` names what to repair.")
    return "rejected"


class Slots:
    """The dispatcher's ONE concurrency cap — every model session it starts holds a slot, so the user's
    machine and the account never carry more than `n` at once — with ONE admission rule: when a slot
    frees, work that CLOSES what is already delivered or asked (a validation, the issuer's answer) is
    admitted before work that OPENS new execution (an executor, a consent, a scope session). Closing work
    lies on the critical path of a result that already exists; a plain FIFO semaphore handed the slot
    to whichever thread the OS woke, and measured that way a delivered node's validator waited five
    minutes behind the executor that started the same second, and an 18-second issuer answer waited
    seven (two AUTO runs, 2026-10). It cannot starve executors: closing work exists only for a delivery
    or a question that opening work produced, and its retries are bounded and backed off, so the
    closing queue empties and an opener runs whenever none waits. Waiting is the only thing the rule
    reorders — the count admitted at once is `n`, as before."""

    class _Lane:
        def __init__(self, slots: "Slots", closing: bool):
            self._slots, self._closing = slots, closing

        def acquire(self) -> None:
            """Block until this lane may take a slot (`Slots.acquire`)."""
            self._slots.acquire(self._closing)

        def release(self) -> None:
            """Give the slot back."""
            self._slots.release()

        def __enter__(self):
            self.acquire()

        def __exit__(self, *exc) -> None:
            self.release()

    def __init__(self, n: int):
        self._free, self._closers, self._cv = n, 0, threading.Condition()
        self.closing, self.opening = self._Lane(self, True), self._Lane(self, False)

    def acquire(self, closing: bool) -> None:
        """Take a slot; an opener also waits while any closer waits."""
        with self._cv:
            self._closers += closing
            self._cv.wait_for(lambda: self._free > 0 and (closing or not self._closers))
            self._free -= 1
            self._closers -= closing
            self._cv.notify_all()   # the last closer admitted may leave a free slot an opener waits on

    def release(self) -> None:
        """Free a slot and let every waiter re-check its turn."""
        with self._cv:
            self._free += 1
            self._cv.notify_all()


class Dispatcher:
    """The autostart engine: EVENT-DRIVEN — every graph transition (the same bus the UI/WS listens on)
    wakes a frontier re-evaluation, so an executor-actionable step whose Del is a REGISTERED llm-executor
    is picked up within milliseconds (dedup per node×iteration; small concurrency cap). The periodic wait
    is only a safety net for an event missed while a run was in flight — dispatch_once is idempotent, so an
    extra pass is free."""

    def __init__(self, engine, agents: AgentRegistry, poll: float = 15.0, max_concurrent: int | None = None,
                 runner=run_executor, validator_runner=None, consent_runner=None, scope_runner=None,
                 scope_validator=None):
        self._engine, self._agents, self._poll = engine, agents, poll   # poll = safety-net interval
        self._cap = Slots(max_concurrent or max_sessions())
        self._runner = runner
        self._scope_runner = scope_runner or run_scope_executor
        self._scope_validate = scope_validator or _auto_validate_scope
        self._consent = consent_runner or run_consent
        self._running: set[str] = set()   # nodes whose executor round is running right now
        self._issuer_attempts: dict = {}   # (node generation, question) → (unproductive settles, not before)
        self._issuer_owed: dict = {}       # (node, question) → (owed since, versions reported stuck, last move)
        self._validate = validator_runner or _auto_validate
        self._retry_model: dict = {}   # round key → the tier its RETRY should use
        self._seen: set[str] = set()      # "{task}#{iter}" / "v:{task}#{iter}" — one run per round
        self._rested = False              # the stopped project's containers ended (`_rest`) since its stop
        self._lapsed_said: set[str] = set()   # roles whose owner's departure is already on the record
        # …and the claim on a key is ATOMIC. The dedup was a bare check-then-add over a set, and
        # `dispatch_once` runs from two places by design — the poll loop and the transition wake — so
        # two rounds could both read "not seen" before either wrote, and the node was executed TWICE:
        # two paid agent runs on one contract, writing the same files. Measured live (an unrelated
        # timing change in the roster read was enough to open the window every time), which is what a
        # latent race does — it waits for the schedule to shift.
        self._claim_lock = threading.Lock()
        self._retried: set[str] = set()   # validator no-verdict retries (one per node×iteration)
        #: redials after a CUT call, counted apart from the retry above and per the same key:
        #: a transport that never delivered a validation must not consume the budget meant for
        #: a second validation (see the branch in the validate pass).
        self._torn: dict[str, int] = {}
        self._stop = threading.Event()
        self._dirty = threading.Event()   # set by every transition → the loop re-evaluates the frontier
        self._rejoined_once = False       # the start-up sweep of passed roots the base does not hold (`_rejoin`)
        self._retry_at: dict[str, tuple[float, float]] = {}   # a refused root join: (next try, its delay)
        self._to_clear: set[str] = set()  # landed roots whose places wait for a verdict still coming (`_clear_places`)
        # a root that has a place owes a join, and is complete only once it landed (`Joins.root_landed`)
        self._engine.joins.set_join_owed(lambda t: (w := _place_of(self._engine, self._agents, t)) is not None
                                   and made(self._engine, w[1]))
        # …and the place the project runs in, probed while it is down (`Engine.lift_the_system_stop`)
        self._engine.probe_the_place_with(lambda place: (answers(place) if is_address(place)
                                                         else execution_of(self._engine, self._agents).unavailable(
                                                             storage=True)))
        # Subscribed HERE, not in `start()`: the callback no longer only sets a flag — it is what
        # makes a cleared block executable again (see `_on_bus`), and that must not depend on
        # whether this dispatcher's poll loop was ever started.
        self._engine.on_transition(self._on_bus)

    def _refused_here(self) -> bool:
        """Is the work this round would dispatch refused where the project runs (`sessions.unattended_here`)? Asked
        BEFORE its executor's ACCEPT, as the workdir is: then nothing is signalled — no obligation the executor never
        consented to — and the refusal is the project's stop; the round, freed, runs once the stop lifts."""
        try:
            unattended_here(self._engine, self._agents)
        except PlaceUnavailable as e:
            return _the_place_is_down(self._engine, e)
        return False

    def _deps_ready(self, task_id: TaskId, waits: "dict | None" = None) -> bool:
        """An executor spawn is useless before the node's Dep PRODUCERS deliver — it hits a missing
        input and BLOCKs (observed live). Gate accept-step spawns on producer DONE. A producer node
        that does not EXIST yet counts as NOT ready: during a build the consumer's ASSIGN can land
        milliseconds before its producer's (observed live — the consumer slipped the gate and burned
        a doomed run); the producer's own ASSIGN wakes the loop, so no liveness is lost. Those it takes from its whole
        too (`Engine.producers_awaited`)."""
        return all((p := self._engine.graph.get_task(TaskId(f))) is not None and p.state == State.DONE
                   for f in self._engine.producers_awaited(task_id, waits))

    def _resolve_ready_blocks(self) -> None:
        """Auto BLOCK resolution: BLOCKED-on-nodes resolves once every EXISTING producer is DONE.
        Adjudication follows the PROVISIONAL edges this node's BLOCK recorded: all sources real →
        confirm all; some mis-named PHANTOM sources (nonexistent nodes — observed live) → the corrected
        set = the real sources (SET semantics drops only the bogus edges, never the real ones); all
        phantom → external=True. External blocks stay for a human. The unblocked node's spawn-dedup
        key is dropped so a FRESH executor run picks it up."""
        for t in self._engine.tasks_by_state(State.BLOCKED):
            if not self._resolves_blocks_for(t.id):
                continue
            deps_in = [e for e in self._engine.get_dependencies() if str(e.to_id) == str(t.id)]
            if not deps_in:
                continue
            existing = [self._engine.graph.get_task(TaskId(e.from_id)) for e in deps_in
                        if self._engine.graph.get_task(TaskId(e.from_id)) is not None]
            # WHICH BLOCKS CLEAR THEMSELVES is one rule (`Engine.block_clears_itself`), read here and by the
            # issuer's questions: a block that named no node with every producer already DONE, or a repeat one,
            # resumed an executor that blocked again — a paid loop (critic 7 #5; critic, 2026-09-27).
            if all(p.state.name == "DONE" for p in existing) and self._engine.block_clears_itself(t):
                # keyed on the BLOCKED EPISODE, not the iteration: the guard exists to stop a
                # second signal inside one episode, and a node may block twice under the same
                # contract — with `#iteration` the second block found the key spent and was never
                # auto-resolved at all.
                key = f"rb:{t.id}#{t.state_entered_at}"
                if key in self._seen:
                    continue
                self._seen.add(key)
                issuer = str(self._engine.graph.issuer_of(t.id))
                prov = [e.from_id for e in deps_in if e.provisional]
                prov_real = [x for x in prov
                             if self._engine.graph.get_task(TaskId(x)) is not None]
                if len(prov_real) == len(prov):
                    _signal(self._engine, t.id, Signal.RESOLVE_BLOCK, issuer, action="confirm")
                elif prov_real:
                    _signal(self._engine, t.id, Signal.RESOLVE_BLOCK, issuer,
                            blocker_task_ids=tuple(TaskId(x) for x in prov_real))
                else:
                    _signal(self._engine, t.id, Signal.RESOLVE_BLOCK, issuer, external=True)
                self._seen.discard(self._round_key(t))
                self._engine.emit_info("delegate",
                                       f"{t.id}: producers DONE — RESOLVE_BLOCK (auto), executor re-queued")

    def _validate_here(self, task) -> bool:
        """Does the instrument observe this delivery? Every one by default, internal nodes included:
        §10.3 says who SIGNS an internal node (its issuer, inside one scope), not that nobody looks.
        `GFSO_VALIDATE_INTERNAL=0` narrows observation to the PUBLIC nodes (a root, or Del(child) ≠
        Del(parent)); an internal node then completes on its DELIVER self_validation, its guarantee
        carried by the public result's validation (Thm 1)."""
        if task is None:
            return True
        return self._engine.observed_here(task.id)

    def _issuer_is_automated(self, task_id: TaskId) -> bool:
        """Is this node's ISSUER automated — the standing agent id, or a registered participant?

        A person is any OTHER name: their node is validated and recorded and then waits for them to
        signal (§10.2 keeps the verdict the issuer's act). The line falls exactly there and nowhere
        else — which matters, because the default identity on every door is the standing agent, so a
        person who never names themselves IS the standing agent as far as this question goes, and
        their nodes auto-sign. Measured 2026-08-22: a tester driving the CLI as the default identity
        watched six of six nodes signed for them while the roster's own help promised the opposite.
        Naming yourself (`source=<your name>`, and an `assignee` of your own) is what makes you a
        person here."""
        issuer = str(self._engine.graph.issuer_of(task_id))
        return issuer == _agent_id() or self._agents.get(issuer) is not None

    def _resolves_blocks_for(self, task_id: TaskId) -> bool:
        """Is resolving this node's dependency-ready block the SYSTEM's move? It is mechanical (every
        producer DONE), so it follows who holds the issuer's moves: a registered participant, the
        standing agent under AUTO, or — with no mode set, as before modes — the standing agent too."""
        return self._engine.issuer_kind(task_id, self._agents) in ("machine", "legacy")

    def _release_after_answer(self, task_id: TaskId, redispatch: bool = False) -> None:
        """An issuer's answer is in: the node's question may be asked again. Only an ANSWERED dispute
        re-opens the node's own rounds — a rejection returns the executor to the same generation — so
        only then are its round keys freed; freed on any answer they let a second run be claimed while
        the first is in flight. The loop is woken only then too: an answer that moved nothing backs off."""
        self._seen.discard(f"q:{task_id}")
        t = self._engine.graph.get_task(task_id)
        if redispatch and t is not None:
            for key in (self._round_key(t), self._round_key(t, "consent")):
                self._seen.discard(key)
            self._dirty.set()

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
        # …and JOINED: a whole validated in its place before its parts' merges land reads a tree without them
        # (critic r2, 2026-10-04: a SEMI whole's validator ran in a base holding only the starter)
        return not self._engine.joins.open_parts(task_id)

    def _round_key(self, task, prefix: str = "") -> str:
        """The dedup key of a node's CURRENT round: id + the generation that makes it a round.

        It used to be id + iteration only, and a revision moves neither iteration nor reopens — so a
        revised node kept a key that was already spent and was never re-executed. That was patched by
        MARKING revised nodes and dropping their keys on the next pass, and the patch had its own
        defect: the mark fired on EVERY ASSIGN, creation included, so a node's key could be dropped
        moments after its first claim and the node was executed TWICE (two paid runs, one contract —
        measured live). Putting the generation IN the key removes both: a revision is a new round by
        construction, and nothing has to be un-remembered."""
        return f"{prefix}{task.id}#" + "#".join(str(g) for g in generation_of_task(task))

    def _admissible(self, task_id: TaskId) -> bool:
        """Would the node's first execution step be ADMITTED? Asked before paying for it.

        The execution gate lives on the ACCEPT signal, and the dispatcher spawns the executor BEFORE
        that signal exists — the run's report is what produces it. So a leaf under a plan the gate
        refuses had its executor spawned, worked, and reported, and only then was the ACCEPT rejected:
        a paid call thrown away, repeatedly, while the plan sat unfixed. This asks the gate's own
        question first, exactly as `_deps_ready` asks the dependency one."""
        return self._engine.execution_blocked_by(task_id) is None

    def _split_owed_said(self, task) -> bool:
        """Is this childless node's split owed, with someone to make it (`issuer.split_has_a_mover`)? Then no
        executor session is spawned on it: its DELIVER as a leaf is refused, so the run could only be thrown away
        (measured: two paid sessions, then parked, then two more). The split is made by the machine issuer's
        question `split`, or by its issuer, whose step names it (`NodeSteps._step_for`).

        Owed only by its plan's author's judgement, never by a count of rounds: equal FAILs say the work is not there
        yet, not that the node is above its executor's κ (§3.7) — every session of the haiku 4.5 `select` that a count
        stopped had ended by itself, turns to spare (GB_sql_database_tnha1f292). A node that does not converge runs
        its rounds and its clock (§12.15 Φ3)."""
        owed = self._engine.split_owed(task.id) if split_has_a_mover(self._engine, self._agents, task) else None
        if owed is not None:
            self._say_once(f"split:{task.id}", f"{task.id}: no session started — {owed['why']}. The step "
                                                f"that opens it: {owed['opens_with']}.")
        return owed is not None

    def _key_of(self, task_id: TaskId, prefix: str = "") -> str:
        """The round key of the node by its id — none where the node is gone."""
        t = self._engine.graph.get_task(task_id)
        return self._round_key(t, prefix) if t is not None else ""

    @contextlib.contextmanager
    def _slot(self, lane, key: str):
        """`lane`'s slot for the session claimed under `key`, yielding whether it may start: not where the run was
        stopped while it waited — its claim is freed so the start dispatches it again, and the body starts nothing.
        Checked only before the wait, a queued session started and signed after `stopped` was read (critic over
        f622997)."""
        with lane:
            if stopped := self._engine.paused() is not None:
                self._seen.discard(key)
            yield not stopped

    def _claim(self, key: str) -> bool:
        """Claim a round for a node ONCE: True to the first caller, False to everyone after.

        The check and the write have to be one step. `dispatch_once` is called from the poll loop AND
        from the transition wake (that is the point of an event-driven dispatcher), so a bare
        `if key not in seen: seen.add(key)` lets two rounds through — and each spends a real agent
        call on the same contract."""
        with self._claim_lock:
            if key in self._seen:
                return False
            self._seen.add(key)
            return True

    def _say_once(self, key: str, msg: str) -> bool:
        """Put one explanation of a non-event on the record, and only one. True when it was said.

        Every line built through here answers the same question — why did nothing happen to this
        node — and the dispatcher asks it again on every poll round, so the same sentence would
        land in the log for as long as the project sits. The KEY is what the sentence is about (a
        node, a role, a particular open set of children); it changes when the situation does, which
        is what keeps the next round's silence honest instead of lost. Seven sites wrote this rule
        out by hand before it had an owner."""
        if key in self._lapsed_said:
            return False
        self._lapsed_said.add(key)
        self._engine.emit_info("delegate", msg)
        return True

    def _say_it_self_verifies(self, s: dict, task) -> None:
        """Say, once per delivery, that no validator is coming and why (§10.3)."""
        self._say_once(
                f"internal:{self._round_key(task, 'v:')}",
                f"{s['task_id']}: delivered and NOT auto-validated — it is an internal "
                f"node (its Del is its parent's), which §10.3 lets self-verify: its "
                f"guarantee is carried by the validation of the public result above it. "
                f"It waits for its issuer ({self._engine.graph.issuer_of(TaskId(s['task_id']))}) "
                f"to signal PASS/FAIL. Observation of every delivery is the default and this "
                f"installation set GFSO_VALIDATE_INTERNAL=0; to make this node a seam, give it a "
                f"different executor from its parent's.")

    def _say_it_waits_for_its_children(self, s: dict, task) -> None:
        """Say, once per open set, which children a delivered parent is still aggregating."""
        _open = [f"'{k.id}' is {k.state.name}" + (" (its result still joining)" if k.state == State.DONE else "")
                 for k in self._engine.joins.open_parts(TaskId(s["task_id"]))]
        if _open:
            self._say_once(
                f"kids:{s['task_id']}#{','.join(sorted(_open))}",
                f"{s['task_id']}: delivered, but not validated yet — it aggregates "
                f"children that have not settled ({'; '.join(_open)}). A verdict now "
                f"would be refused at the gate, so none is spent. Drive those nodes; "
                f"validation follows by itself.")

    def _dispatch_validation(self, s: dict, task, it: tuple, started: list) -> bool:
        """Act on a delivery that is waiting to be validated. True when this step is done with.

        Three of the four ways out are a SENTENCE and no thread: the issuer keeps the
        signature, the node self-verifies, or it is still the AND over children that have
        not passed. Only the fourth spends money.
        """
        _proj = self._engine.project_name
        _validator = self._agents.validator_for(s.get("assignee"), project=_proj)
        # PUBLISHED FOR THE DOORS, the way the roster already is. The doors announce "an independent
        # validator is bound to this node" and could not say WHICH — the layer gate forbids them the
        # registry, and rightly — so five strangers went to the log to discover that the validator
        # belonged to another project and stood in a directory holding none of their work.
        if _validator:
            _cfg = self._agents.get(str(_validator)) or {}
            self._engine.workforce.publish_bound_validator(
                TaskId(s["task_id"]),
                {"id": str(_validator), "project": _cfg.get("project"),
                 "workdir": node_workspace(self._engine, self._agents, s["task_id"]) or _cfg.get("workdir")})
        if s.get("action") == Action.VALIDATE and _validator is not None:
            # A HUMAN ISSUER KEEPS THEIR VERDICT — and not the validation. Skipping the whole path
            # meant a person who had registered an `llm-validator` and bound it to their executor
            # got nothing at all: the node sat in VALIDATING with the instrument idle, on both
            # doors, while `register_agent` promised it fires "on EVERY delivery" (measured
            # 2026-08-21). Registering an instrument IS asking for the validation; §10.2 keeps only
            # the signature theirs. So it runs and RECORDS, and the person signs.
            _sign = (self._issuer_is_automated(TaskId(s["task_id"]))
                     and not self._engine.holder_signs(TaskId(s["task_id"])))
            # AN APPOINTED OBSERVER'S FAIL ALREADY STANDS on this delivery (Inv-2): the system's issuer
            # signs it, rather than paying for a validation whose PASS the record door would refuse. The
            # replay of standing verdicts skips hand records, so a binding hand FAIL — the issuer's own —
            # left the node in VALIDATING with a validation started every round (critic, 2026-09-27).
            if _sign and ((_ob := self._engine.pass_blocked_by(TaskId(s["task_id"]))) or {}).get(
                    "kind") == "observed_fail":
                if _signal(self._engine, TaskId(s["task_id"]), Signal.FAIL,
                           str(self._engine.graph.issuer_of(TaskId(s["task_id"]))), failed_criteria=tuple(_ob["fails"]),
                           reason=f"an appointed observer recorded this delivery FAIL on {', '.join(_ob['fails'])}"):
                    started.append(f"fail:{s['task_id']}")
                return True
            if not self._validate_here(task):
                # §10.3: an INTERNAL node (its Del is its parent's) self-verifies, and no
                # independent validator is spawned — but nothing then SIGNS it either, so the
                # node sits in VALIDATING until its issuer acts. Measured 2026-08-20 on the
                # shipped autonomous demo, whose whole subtree is delegated to ONE executor:
                # every child is internal by construction, the delivery landed in 57 seconds,
                # and the graph then stood still for half an hour with nothing to read. Said
                # once per delivery; the decision itself stays the issuer's.
                self._say_it_self_verifies(s, task)
                return True
            if not self._children_settled(TaskId(s["task_id"])):
                # …and say which children, once. Skipping is right — the verdict would be
                # rejected at the gate (Thm 1: the parent is the AND over its children) — but in
                # silence a delivered parent looks like a validator that never came. Measured
                # 2026-08-20 on a live run: a root sat in VALIDATING for nineteen minutes after
                # its own repair added a child, with `busy: []` and nothing to read.
                self._say_it_waits_for_its_children(s, task)
                return True
            # …AND NOTHING IS SPENT VALIDATING A CONTRACT THAT IS EMPTY. V is the conjunction over the
            # node's criteria (§2); over the empty set it is vacuously true, which is not a
            # validation — and the engine refuses to RECORD such a verdict, by name, at the register.
            # The refusal sat downstream of the spend: a stranger's criteria-less node burned TWO
            # paid validator dispatches before "AUTOMATIC VALIDATION GAVE UP", while
            # `record_verdict` on the same node answered instantly and correctly (MCP door, wave 24,
            # 2026-09-04). Deciding not to pay is the same question, asked before the money.
            if criterionless(task.spec.criteria):
                self._say_once(
                    f"nocriteria:{self._round_key(task, 'v:')}",
                    f"{s['task_id']}: delivered and NOT validated — it has no criteria, so there is "
                    f"nothing a verdict could be ABOUT (V is the conjunction over a node's "
                    f"criteria, §2, and over an empty set it is vacuously true). No instrument is "
                    f"spent on it. Give it criteria (`edit_criteria`) and it is validated on the next "
                    f"delivery.")
                return True
            if self._claim(self._round_key(task, "v:")):
                started.append(f"validate:{s['task_id']}")
                threading.Thread(target=self._validate_queued,
                                 args=(TaskId(s["task_id"]), it, _sign), daemon=True).start()
            return True
        return False

    def _dispatch_steps(self, out: dict, started: list) -> None:
        """Act on each frontier step: fire the instrument on a delivery, or spawn work.

        `dispatch_once` is one poll ROUND — publish the roster, resolve ready blocks, then
        act — and the acting had grown to a hundred and thirty statements inside it, so the
        round's own shape was invisible. This is the acting; the round is what calls it."""
        waits = self._engine.start_waits()
        for s in out.get("steps", []):
            task = self._engine.graph.get_task(TaskId(s["task_id"]))
            # THE WHOLE GENERATION, not the iteration: it is what `_round_key` keys the round on,
            # and the staleness guard has to ask the same question the dedup key answers.
            it = generation_of_task(task)
            # …and ONE SESSION AT A TIME IN A NODE'S PLACE: a revised node gets a new round while the session of the
            # superseded version is still writing there, and a second one beside it would deliver what both wrote
            if (self._carried_by_a_scope(task) or self._dispatch_validation(s, task, it, started)
                    or s["task_id"] in self._running):
                continue
            if s.get("action") not in SPAWNABLE_ACTIONS or (task is not None and self._split_owed_said(task)):
                continue
            if not self._deps_ready(TaskId(s["task_id"]), waits) or self._being_rewritten(s["task_id"]):
                continue                   # spawning before the producers deliver ⇒ instant BLOCK; mid-rewrite ⇒ waste
                                           # EVERY executor spawn, not the first one only: the gate
                                           # asked its question on `accept` alone, so a node already
                                           # past that step — resumed after a cleared block, re-queued
                                           # out of REWORKING, or given a Dep AFTER it started — was
                                           # spawned against an input that does not exist yet, and
                                           # blocked itself on arrival. A paid run whose only possible
                                           # outcome is the BLOCK it already reported.
            # A PARENT IS NOT A LEAF, AND ITS WORK IS ITS CHILDREN'S. The dispatcher spawned an
            # executor on a node with children that had never run: the run re-did at the parent what
            # the children were about to do, and the node then sat in VALIDATING for 24 minutes while
            # they caught up (HTTP door, 2026-09-02). `next_steps` never offered it — it said
            # `review`, the plan step — so the two rules disagreed about what is actionable, and the
            # frontier was right: a non-leaf aggregates (Thm 1), it does not execute. Delivering the
            # aggregate is still the parent's own act, so DELIVER stays spawnable; what is refused is
            # starting the WORK of a node whose children have not settled.
            if (s.get("action") == Action.ACCEPT and task is not None and task.state == State.OFFERED
                    and self._engine.graph.get_active_children(task.id)
                    and (self._agents.get(s.get("assignee") or "") or {}).get("kind") == "llm-executor"
                    and self._admissible(task.id)):
                # …BUT ITS CONSENT IS ITS OWN, and nobody else can give it (Inv-1): a system-held
                # parent that is offered a version — first issue, an accepted dispute, an extension —
                # is asked for exactly that, with no work spawned.
                if self._claim(self._round_key(task, "consent")):
                    started.append(s["task_id"])
                    threading.Thread(target=self._consent_guarded,
                                     args=(task.id, s["assignee"]), daemon=True).start()
                continue
            if (s.get("action") == Action.FIX and task is not None and any(
                    k.state != State.DONE for k in self._engine.graph.get_active_children(task.id))):
                continue       # a repaired or new child is still on its way: re-aggregating now pays for a
                               # delivery that cannot pass, and spends the parent's rework budget on it
            if (s.get("action") in (Action.ACCEPT, Action.EXECUTE)
                    and (_kids := self._engine.graph.get_active_children(TaskId(s["task_id"])))):
                self._say_once(
                        f"parent:{s['task_id']}",
                        f"{s['task_id']}: not spawned — it has children ({', '.join(str(k.id) for k in _kids)}) "
                        f"and a parent's result is the AND over them (Thm 1). Its executor runs when "
                        f"they have passed and there is an aggregate to deliver.")
                continue
            if s.get("action") == Action.ACCEPT and not self._admissible(TaskId(s["task_id"])):
                # …and SAY SO, once per node. The gate is right (§11.5: a plan that has not passed
                # its checks does not start, and the ACCEPT would be refused with the executor's
                # work), but silence made it indistinguishable from a dead dispatcher. Measured on
                # the shipped `autonomous_org` demo, which drives only this loop and never the
                # frontier's own review step: two children sat in OFFERED for half an hour over an
                # empty workspace, with nothing anywhere saying why.
                _p = self._engine._graph.get_parent(TaskId(s["task_id"]))
                if _p is not None:
                    self._say_once(
                        f"gate:{s['task_id']}",
                        f"{s['task_id']}: not started — its parent's plan ('{_p.id}') is not "
                        f"admitted to execution yet (§11.5). `next_steps` names the step that opens "
                        f"it: review_decomposition('{_p.id}'), or closing the holes it lists. "
                        f"Nothing is lost; dispatch resumes the moment the plan passes.")
                continue
            hands, cfg = performer(self._engine, self._agents, s.get("assignee"))
            if cfg is None:
                # Unregistered Del = a human (or an external system): the dispatcher stays passive,
                # correctly — but said once, because a node that simply never starts looks like a
                # broken dispatcher. The live case that made this matter: a plan repair ADDED a
                # child, which was created with its author's own id rather than a registered
                # executor's, and in a delegated run it landed on nobody at all.
                self._say_once(
                        f"unowned:{s['task_id']}#{s.get('assignee')}",
                        f"{s['task_id']}: not started — Del is '{s.get('assignee')}', which is not a "
                        f"registered executor, so this node waits for THAT party's own signals. "
                        f"If it was meant to be delegated, `reassign` it to a registered role; if "
                        f"it is yours, drive it yourself (`next_steps` carries its directive).")
                continue
            if cfg.get("kind") != "llm-executor":
                self._engine.emit_info("delegate",
                                       f"{s['task_id']}: Del={s['assignee']} is a registered "
                                       f"{cfg.get('kind')} — not an executor kind, nothing to start")
                continue
            if self._waits_for_its_holder(s, task, hands):
                continue
            if self._owner_gone(s, cfg, hands):
                continue
            if not self._claim(self._round_key(task)):
                continue
            started.append(s["task_id"])
            threading.Thread(target=self._run_guarded,
                             args=(TaskId(s["task_id"]), s["assignee"], it), daemon=True).start()

    def _owner_gone(self, s: dict, cfg: dict, hands: str) -> bool:
        """Is the party that registered the performing role gone? Nothing is cancelled and no state moves — the node
        keeps its place and resumes the moment the owner returns; what stops is the spawning of work nobody is waiting
        for. Said ONCE per role, because the alternative is a line per dispatch cycle for as long as the project sits."""
        if self._agents.owner_is_live(hands):
            self._lapsed_said.discard(hands)
            return False
        self._say_once(hands, f"{s['task_id']}: {hands}'s owner ({cfg.get('client')}) is gone — dispatch for that "
                              f"role stops here; nothing is cancelled, and it resumes when the same owner returns")
        return True

    def _waits_for_its_holder(self, s: dict, task, hands) -> bool:
        """A holder's node offered and not yet consented to: THE HOLDER'S CONSENT IS ITS OWN (Inv-1) — its hands start
        after its ACCEPT, never in its place. Said once."""
        if self._agents.get(s.get("assignee") or "") is not None or task is None or task.state != State.OFFERED:
            return False
        self._say_once(f"own-consent:{s['task_id']}",
                       f"{s['task_id']}: waits for its holder's ACCEPT — {hands} performs it in a clean session once "
                       f"{s['assignee']} has consented to the contract")
        return True

    def _session_scope(self, task):
        """`session_scope` over this dispatcher's engine and roster."""
        return session_scope(self._engine, self._agents, task)

    def _carried_by_a_scope(self, task) -> bool:
        """Is this node's work and validation its scope's (`_dispatch_scopes`)? Then nothing of its own is
        spawned, and that is said once."""
        top = self._session_scope(task)
        if top is not None:
            self._say_once(f"scope:{task.id}#{top.id}",
                           f"{task.id}: carried by the session of scope '{top.id}' — one executor session builds "
                           f"every node of it and one validation checks each node's own criteria")
        return top is not None

    def _scope_key(self, members: list, prefix: str = "") -> str:
        """The dedup key of a scope's round: every node's generation and state — a round is one per visit of the
        scope, so a node answered or re-delivered makes the next one."""
        return prefix + ";".join(f"{m.id}#" + "#".join(str(g) for g in generation_of_task(m)) + f"@{m.state.name}"
                                 for m in members)

    def _dispatch_scopes(self, started: list) -> None:
        """Start what each scope carried by one session is ready for: its one validation, once every node of it
        is delivered, done, or a whole waiting for its parts to pass; else its one session, once every open node
        may start."""
        tops = {}
        for t in self._engine.all_tasks():
            if self._engine.graph.get_active_children(t.id) and (top := self._session_scope(t)) is not None:
                tops[str(top.id)] = top
        for top in tops.values():
            members = self._engine.scope_members(top.id)
            if any(str(m.id) in self._running or self._being_rewritten(m.id) for m in members):
                continue
            ready = self._scope_ready(top, members)
            # …and a delivery does not wait for what cannot come now: with no session to start (a sibling's dispute
            # open, a block, a parked scope) the delivered nodes are validated rather than left to their bound —
            # a good delivery lapsed to ESCALATED behind a sibling's hour-long dispute (critic, 2026-09-28)
            if (any(m.state == State.VALIDATING for m in members) and (not ready or all(
                    m.state in (State.VALIDATING, State.DONE) for m in members))):
                sign = self._issuer_is_automated(top.id) and not self._engine.holder_signs(top.id)
                if self._claim(self._scope_key(members, "sv:")):
                    started.append(f"validate-scope:{top.id}")
                    threading.Thread(target=self._validate_scope_guarded,
                                     args=(top.id, self._scope_key(members), sign), daemon=True).start()
            elif ready and self._claim(self._scope_key(members)):
                started.append(f"scope:{top.id}")
                threading.Thread(target=self._scope_guarded,
                                 args=(top.id, str(top.assignee), self._scope_key(members)), daemon=True).start()

    def _scope_ready(self, top, members: list) -> bool:
        """May the scope's session start? Some node is open and none waits on an answer, every open node is
        admitted to execution (§11.5), no split in it is refuted or owed, every producer outside the scope has
        passed, and its executor is here. A refuted split is its executor's repair — a revision, not a
        re-delivery, which the re-delivery gate refuses — and an owed one its executor's split: a session
        before either is a paid run whose every report is refused (measured: two such, then parked)."""
        open_ = [m for m in members if m.state.name in _EXECUTOR_STATES]
        if not open_ or any(m.state.name not in (*_EXECUTOR_STATES, "VALIDATING", "DONE") for m in members):
            return False
        own_consent = self._agents.get(str(top.assignee)) is None   # a holder's hands: it consents, they never do
        if (not self._agents.owner_is_live(performer(self._engine, self._agents, top.assignee)[0])
                or (own_consent and any(m.state == State.OFFERED for m in open_))
                or self._engine.parking.is_execution_parked(top)
                or any(self._engine.parking.contested_reason(m.id) for m in open_)
                or any(self._engine.decomposition_refuted(m.id) or self._engine.dep_order_refuted(m.id)
                       for m in open_ if self._engine.graph.get_active_children(m.id))
                or any(self._split_owed_said(m) for m in open_)):
            return False
        inside, waits = {str(m.id) for m in members}, self._engine.start_waits()
        for f in {f for m in open_ for f in self._engine.producers_awaited(m.id, waits)} - inside:
            if (p := self._engine.graph.get_task(TaskId(f))) is None or p.state != State.DONE:
                return False                    # spawned before its producer delivers, it can only BLOCK
        held = [(m, why) for m in open_ if (why := self._engine.execution_blocked_by(m.id))]
        for m, why in held[:1]:
            self._say_once(f"gate:{m.id}", f"{top.id}: its scope's session not started — '{m.id}' is not "
                                           f"admitted to execution yet (§11.5): {why['why']}. The step that "
                                           f"opens it: {why['opens_with']}.")
        return not held

    def _scope_guarded(self, top_id: TaskId, executor_id: str, key: str) -> None:
        """A scope session under the concurrency cap, every node of the scope in flight while it runs."""
        ids = [str(m.id) for m in self._engine.scope_members(top_id)]
        self._running.update(ids)
        try:
            with self._slot(self._cap.opening, key) as go:
                if go:
                    self._scope_body(top_id, executor_id, key)
        finally:
            self._running.difference_update(ids)

    def _scope_body(self, top_id: TaskId, executor_id: str, key: str) -> None:
        """Accept every open node top-down when the session starts — its executor's consent fixes the start
        of each obligation (Inv-1, §11.2) — run the one session, and give the round back once when nothing
        it reported took effect, then park the scope's top for its issuer."""
        members = self._engine.scope_members(top_id)
        if self._scope_key(members) != key or str(members[0].assignee) != executor_id:
            self._engine.emit_info("delegate", f"{top_id}: queued scope session is stale — slot released")
            return
        if (gone := missing_workdir(performer(self._engine, self._agents, executor_id)[1] or {})):
            self._seen.discard(key)
            self._say_once(f"nowd:{top_id}:{executor_id}", f"{top_id}: scope session not started - the workdir "
                                                          f"registered for '{executor_id}' ('{gone}') is not a directory")
            return
        if self._refused_here():
            self._seen.discard(key)
            return
        self._engine.parking.unpark_execution(top_id)
        for m in members:
            if m.state == State.OFFERED and self._agents.get(executor_id) is not None:
                _signal(self._engine, m.id, Signal.ACCEPT, executor_id)
        before = sum(self._engine.accepted_moves(m.id) for m in members)
        try:
            out = self._scope_runner(self._engine, top_id, executor_id, self._agents)
            if isinstance(out, dict) and out.get("status") in ("not_consented", "too_late"):
                return                    # a member re-offered before the session began: it waits for the holder
            if (sum(self._engine.accepted_moves(m.id) for m in members) == before
                    and not any(self._engine.parking.contested_reason(m.id) for m in members)):
                self._one_retry_then_park(top_id, "u:", f"the scope session reported "
                                          f"{(out or {}).get('status')!r} and no signal took effect", claim=key,
                                          cut=bool((out or {}).get("cut")), limit=bool((out or {}).get("limit")),
                                          ended=(out or {}).get("past_disk"), note=(out or {}).get("disk_ended"))
        except Exception as e:                          # noqa: BLE001 — a failed round is not a signal
            log.warning(f"delegate: scope session of {top_id} failed: {e}")
            self._one_retry_then_park(top_id, "x:", f"scope session failed — {e}", claim=key,
                                      limit=_the_place_is_down(self._engine, e))

    def _validate_scope_guarded(self, top_id: TaskId, key: str, sign: bool = True) -> None:
        """The scope's one validation under the concurrency cap. A run that yields no verdict gets one more;
        after that the scope's top waits for its issuer, as a node's validation does."""
        vkey = "sv:" + key
        queued = [self._engine.claims.queue_validation(m.id) for m in self._engine.scope_members(top_id)
                  if m.state == State.VALIDATING]
        try:
            self._validate_scope_body(top_id, key, vkey, sign)
        finally:
            for q in queued:
                self._engine.claims.dequeue_validation(q)

    def _validate_scope_body(self, top_id: TaskId, key: str, vkey: str, sign: bool) -> None:
        """The scope's validation round under the cap (`_validate_scope_guarded`)."""
        with self._slot(self._cap.closing, vkey) as go:
            if not go:
                return
            if self._scope_key(self._engine.scope_members(top_id)) != key:
                return
            self._engine.parking.unpark_validation(top_id)   # a fresh attempt un-parks it
            try:
                ret = self._scope_validate(self._engine, top_id, self._agents, sign=sign)
            except Exception as e:                      # noqa: BLE001 — a failed run is not a verdict
                log.warning(f"auto-validate of scope {top_id} failed: {e}")
                ret = "no-verdict:limit" if _the_place_is_down(self._engine, e) else None
            if ret == "rejected":
                self._seen.discard(vkey)                # revalidates, on the standing records, when the graph moves
            if ret in ("pass", "fail", "recorded", "no-instrument", "rejected"):
                return
            if ret in ("no-verdict:limit", "no-verdict:bound"):
                return (self._wait_out_limit(top_id, vkey, "the scope's validator") if ret == "no-verdict:limit"
                        else self._wait_for_the_issuer(top_id))
            if ret == "no-verdict:torn" and self._redial(top_id, vkey):   # a cut call is no answer: it spends no retry
                return
            if vkey not in self._retried:
                self._retried.add(vkey)
                self._seen.discard(vkey)
                self._dirty.set()
                self._engine.emit_info("delegate", f"{top_id}: the scope's validation returned no verdict — one retry")
            elif not self._ask_again_where_the_system_issues(top_id, vkey, _reask_wait(ret)):
                self._engine.emit_info("delegate", f"{top_id}: the scope's validation produced no verdict twice — "
                                                   f"its ISSUER must decide (⊥ is not pass, §2.3)")
                self._engine.parking.park_validation(top_id)

    def _publish_the_roster(self) -> None:
        """Who is on the roster, for every reader of the graph: before the stop's return, for a project stands stopped
        after every server start and its finished run read «this name is not on the validator roster» under the very
        validator the page lists (ui stream, 2026-11-03)."""
        # the FSM accepts a registered validator's PASS/FAIL as the issuer's role-V instrument (§10.3) —
        # both the LLM validator (a fresh read-only agent) and the deterministic unittest-checker
        _roster = self._agents.list()
        self._engine._graph.authorized_validators = {
            aid for aid, cfg in _roster.items()
            if cfg.get("kind") in ("llm-validator", "unittest-checker")}
        # …AND WHOSE EACH ONE IS. The set above says an instrument EXISTS on this server; it cannot
        # answer whether one will validate a given node, and the surfaces asked it as though it could:
        # a user whose project had registered nothing was told on every delivery that "an
        # independent validator is bound to this node — wait for it", because twenty-five roles
        # belonging to seventeen other projects were on the shared roster (HTTP door, wave 26,
        # 2026-09-06). They waited for a validator that could never come, and the same sentence warned
        # them off the one action that would have worked. The scope rule already exists in
        # `validator_for` (this project's roles first, then UNSCOPED ones, never another project's);
        # published here so the read surfaces can ask the same question.
        self._engine.workforce.publish_validator_projects({
            aid: cfg.get("project") for aid, cfg in _roster.items()
            if cfg.get("kind") in ("llm-validator", "unittest-checker")})
        # …and WHO ELSE is registered, published downward for the read surfaces. `gfso.tools` is the
        # layer below this one (core+engine only, held by `test_layering`) and must not import the
        # dispatcher to find out that a node's Del is a machine — but it is the difference between
        # "the graph waits for a person" and "the dispatcher has it in hand", and a driving agent
        # reported itself blocked on a human over exactly that (2026-08-20).
        publish_the_workforce(self._engine, _roster)

    def dispatch_once(self) -> list[str]:
        """One poll round (the testable unit): spawn executor runs for executor-ready steps AND the
        auto-validation for EVERY freshly delivered node (delegated or self-executed — one path;
        fires only when an llm-validator is registered AND the node's issuer is automated, else
        validation stays the issuer's act)."""
        if getattr(self._engine, "_dispatch_quiesce", 0):
            return []      # a wholesale build/rebuild is mid-burst — dispatch on the settled graph only
        self._publish_the_roster()
        self._clear_what_waited()
        if self._engine.paused() or self._over():
            self._rest()
            return []      # the user's STOP: nothing new starts; running sessions finish and their signals land
        self._rested = False
        self._rejoin()     # a root's result that did not land is tried again (cheap: roots only)
        self._resolve_ready_blocks()
        answer_open_questions(self._engine, self._agents, self._claim, self._release_after_answer,
                              self._cap.closing, ISSUER_VERBS, self._issuer_attempts, self._issuer_owed)
        if self._engine.mode() is not None:
            confirm_system_cancellations(self._engine, self._agents, lambda t: str(t.id) in self._running)
        started = []
        out = self._engine.next_steps()
        # A NODE THE PLAN GATE HOLDS BACK IS NOT A STEP — it is in `waiting`, because offering an
        # ACCEPT the engine refuses cost whoever obeyed it a call (measured on the MCP door
        # 2026-08-21). It still has to be SAID, once per node: a gate that only refuses is
        # indistinguishable from a dead dispatcher (the `autonomous_org` case, half an hour of
        # silence over an empty workspace).
        for w in out.get("waiting", []):
            # THE KIND, not the shape of a neighbouring field. This skipped an entry that had no
            # `opens_with`, on the assumption that dep-order waits carry none — they do, so a
            # dependency wait was narrated as a plan-gate hold, with a list repr and the wrong
            # canon citation (register 2026-08-22, finding 1).
            if w.get("kind") == "dependency" or not (_opens := w.get("opens_with")):
                continue                       # dep-order waits are read from `waits_on` instead
            self._say_once(
                f"gate:{w['task_id']}",
                f"{w['task_id']}: not started — {', '.join(w['waits_on'])} is not admitted to "
                f"execution yet "
                f"(§11.5): {w['why']}. The step that opens it: {_opens}. Nothing is lost; dispatch "
                f"resumes the moment the plan passes.")
        self._dispatch_scopes(started)
        self._dispatch_steps(out, started)
        return started

    def _being_rewritten(self, task_id) -> bool:
        """`being_rewritten` for this dispatcher's engine."""
        return being_rewritten(self._engine, TaskId(task_id))

    _EXECUTOR_STATES = _EXECUTOR_STATES

    def _fresh(self, task_id: TaskId, expect_gen: tuple, states: tuple,
               executor_id: str | None = None) -> bool:
        """TOCTOU guard: the dispatch decision can be minutes older than the semaphore slot (observed
        live — a queued second-generation run fired on a node that had DELIVERED meanwhile). Re-check
        the node right before spending an LLM run; a stale slot is dropped silently — if the node is
        genuinely actionable again, a later pass re-dispatches it under a fresh key.

        DEL IS PART OF WHAT GOES STALE. The check looked at the state and the iteration only, so a
        node REASSIGNED between the queue and the slot was still run as the old executor — and every
        signal that run made came back "exec-1 is not executor for root.matcher (executor=exec-2)".
        Measured on a live E3 run 2026-08-22: an ACCEPT, a second ACCEPT and a DELIVER all refused,
        the run paid for, and the graph stalled for ten minutes with the frontier repeating a step
        the dispatcher could not take.

        SO IS THE REST OF THE GENERATION. This compared `iteration` alone, while `_round_key` — the
        dedup key of the very same round — uses the whole (iteration, reopens, revisions) triple.
        The two halves of one fact disagreed: a node REVISED while its run sat in the queue got a new
        round key, so the dispatcher spawned a SECOND paid run, and this guard let the first one
        proceed as well — against a contract that no longer exists. Measured: two paid executor runs
        on one node, the node left in VALIDATING carrying the superseded delivery to be validated
        against the new criteria, and the run that did the right work having its DELIVER refused by
        the FSM. Both `revise` and `reopen` land the node in OFFERED, which is an executor state, so
        the state check catches neither."""
        t = self._engine.graph.get_task(task_id)
        if t is None or t.state.name not in states or generation_of_task(t) != tuple(expect_gen):
            self._engine.emit_info("delegate",
                                   f"{task_id}: queued run is stale (state {t.state.name if t else '?'}"
                                   f", generation {generation_of_task(t) if t else '?'} ≠ "
                                   f"{tuple(expect_gen)}) — slot released")
            return False
        if executor_id is not None and str(t.assignee) != str(executor_id):
            # …and the ROUND is freed with it. A reassignment moves no generation counter, so the
            # round key is unchanged and a released slot would otherwise be a claim nobody ever
            # spends: the node would sit forever, which is the same stall by another road.
            self._seen.discard(self._round_key(t))
            self._engine.emit_info(
                "delegate", f"{task_id}: queued run is stale — it was queued for '{executor_id}' and "
                            f"Del is now '{t.assignee}'; slot released, the next pass dispatches it "
                            f"to the executor that holds it")
            return False
        return True

    def _one_retry_then_park(self, task_id: TaskId, tag: str, what: str, claim: str | None = None,
                             cut: bool = False, limit: bool = False, ended: str | None = None,
                             note: str | None = None) -> None:
        """A round that ended with NOTHING SIGNALLED: give it exactly one more, then park it and say so.

        Three things end a round that way — an unreadable report, a status word the contract does not
        define, and an exception anywhere in the spawn — and all three leave a node whose round key is
        already spent, i.e. one the dispatcher will never pick up again while the frontier goes on
        advertising the step. ACCEPT was already sent, so the node sits in EXECUTING, where only its
        deadline moves it — so the park is recorded for the issuer's frontier (`parked_executions`).
        Written ONCE because a rule kept in three places moves in one of them — which is how the
        unreadable-report case came to be handled and the other two did not.
        """
        t = self._engine.graph.get_task(task_id)
        if ended:
            # …its place's directories past its own disk bound: every session there is ended again, so no redial and no
            # retry — the issuer told why, at once (four redials and a retry each died within seconds, said as a cut)
            self._engine.emit_info("delegate", f"{task_id}: {what} — {ended}; the node is PARKED where it stands and "
                                               f"needs its issuer")
            self._engine.parking.park_execution(task_id, ended)
            return
        if limit and t is not None:
            return self._wait_out_limit(task_id, claim or self._round_key(t), "the session's")
        if cut and t is not None and self._redial(task_id, claim or self._round_key(t), "the session's"):
            return
        key = self._round_key(t, tag) if t is not None else None
        if key and key not in self._retried:
            self._retried.add(key)
            self._seen.discard(claim or self._round_key(t))
            self._dirty.set()
            self._engine.emit_info("delegate", f"{task_id}: {what} — one retry")
        else:
            self._engine.emit_info(
                "delegate", f"{task_id}: {what} twice — the node is PARKED where it stands and "
                            f"needs its issuer; nothing was signalled on its behalf")
            # …and said where the ISSUER reads, not only in the log (the frontier's step for the node) — with what the
            # disk's watch said of its last end, where it was that (critic: a place just under its bound lost its cause)
            self._engine.parking.park_execution(task_id, note=note and f"ended by the disk's watch: {note}")

    def _consent_guarded(self, task_id: TaskId, executor_id: str) -> None:
        """A consent round under the concurrency cap; one that signals nothing is retried once and then
        parked for the issuer, like any executor round that leaves the node where it stood."""
        with self._slot(self._cap.opening, self._key_of(task_id, "consent")) as go:
            if not go:
                return
            try:
                out = self._consent(self._engine, task_id, executor_id, self._agents)
            except Exception as e:                      # noqa: BLE001 — a failed round is not a signal
                log.warning(f"delegate: consent of {task_id} failed: {e}")
                # …its place made first now: a place down there waits it out, as an executor's round does
                out = {"status": "error", "limit": _the_place_is_down(self._engine, e)}
            if out.get("status") in ("accepted", "challenged", "not_offered"):
                return
            t = self._engine.graph.get_task(task_id)
            if out.get("limit") and t is not None:
                return self._wait_out_limit(task_id, self._round_key(t, "consent"), f"{executor_id}'s consent")
            if past := out.get("past_disk"):          # …its place past its bound: a retry is ended again (`_one_retry…`)
                self._engine.emit_info("delegate", f"{task_id}: {executor_id}'s consent signalled nothing — {past}; "
                                                   f"PARKED for its issuer")
                return self._engine.parking.park_execution(task_id, past)
            retry = self._round_key(t, "consent-retry") if t is not None else None
            if retry and retry not in self._retried:
                self._retried.add(retry)
                self._seen.discard(self._round_key(t, "consent"))
                self._dirty.set()
                self._engine.emit_info("delegate", f"{task_id}: {executor_id}'s consent signalled nothing — one retry")
            else:
                self._engine.emit_info("delegate", f"{task_id}: {executor_id}'s consent signalled nothing twice — "
                                                   f"PARKED for its issuer")
                self._engine.parking.park_execution(task_id)

    def _run_guarded(self, task_id: TaskId, executor_id: str, expect_gen: tuple = (0, 0, 0)) -> None:
        self._running.add(str(task_id))
        try:
            self._run_guarded_body(task_id, executor_id, expect_gen)
        finally:
            self._running.discard(str(task_id))

    def _run_guarded_body(self, task_id: TaskId, executor_id: str, expect_gen: tuple) -> None:
        with self._slot(self._cap.opening, self._key_of(task_id)) as go:
            if not go or not self._fresh(task_id, expect_gen, self._EXECUTOR_STATES, executor_id):
                return
            # ACCEPT FIXES THE START OF THE OBLIGATION (§11.2) — so it is sent when the work
            # STARTS, not when the report comes back. Wrapping the finished report into
            # ACCEPT+DELIVER put both signals at the END: the node sat in OFFERED for its entire
            # working life and crossed EXECUTING in an instant. Measured 2026-08-20 on three leaves
            # — ACCEPT and DELIVER carried the IDENTICAL timestamp on every first delivery, and
            # files were on disk 25-53 s before the graph admitted the node had started. No view,
            # the UI included, could show work in progress, because no interval held that fact:
            # "trust, but see" (§19.1) has nothing to see. The executor's consent is still its own
            # report — a spawned executor that never reports leaves the node in EXECUTING, where
            # the dispatcher's own `_EXECUTOR_STATES` picks it up again exactly as before.
            # THE PLACE IS ASKED BEFORE THE OBLIGATION IS FIXED. `run_executor` refuses a role whose
            # workdir is gone, but by the time it is called the ACCEPT below has already moved the
            # node OFFERED → EXECUTING and this round's key is spent — so the refusal said "the node
            # stays where it is" while the node had in fact been started and would never be picked
            # up again, even after the directory was restored. Same liveness as the transport crash
            # it replaced, with a better sentence: exactly the shape this repository keeps paying
            # for. Asked here, nothing is signalled, and the ROUND IS FREED, so putting the
            # directory back is enough for the next pass to dispatch the node.
            _gone = missing_workdir(performer(self._engine, self._agents, executor_id)[1] or {})
            if _gone:
                _t0 = self._engine.graph.get_task(task_id)
                if _t0 is not None:
                    self._seen.discard(self._round_key(_t0))
                self._say_once(
                    f"nowd:{task_id}:{executor_id}",
                    f"{task_id}: not started - the workdir registered for '{executor_id}' "
                    f"('{_gone}') is not a directory{_resolution_note(_gone)}. Nothing was "
                    f"signalled and the node is where it was; re-register the role against the "
                    f"directory the work is really in, and the next pass dispatches it.")
                return
            if self._refused_here():
                if (_t0 := self._engine.graph.get_task(task_id)) is not None:
                    self._seen.discard(self._round_key(_t0))
                return
            # …AND THE ONCE IS RELEASED WHEN THE PLACE COMES BACK. Kept forever, "once" means once
            # per server lifetime: a directory that goes away, returns, and goes away again is held
            # back in silence the second time — the same shape as the owner-departure notice, which
            # discards its own key when the owner returns.
            self._lapsed_said.discard(f"nowd:{task_id}:{executor_id}")
            self._engine.parking.unpark_execution(task_id)                     # a fresh run un-parks it
            _t = self._engine.graph.get_task(task_id)
            if _t is not None and _t.state.name == "OFFERED":
                if self._agents.get(executor_id) is None:
                    self._seen.discard(self._round_key(_t))   # a holder's node re-offered while queued: its
                    return                                    # consent, not ours; the round waits for it
                _signal(self._engine, task_id, Signal.ACCEPT, executor_id)
            # WHETHER ANYTHING TOOK EFFECT, by the node's ACCEPTED log entries: a BLOCK and its resolution
            # during the run move no generation, and on this clock can re-enter EXECUTING within the same
            # tick, so neither the generation nor the entry time tells a new visit from the old one. Every
            # accepted transition is an entry (Thm 11); a refused one is not counted.
            _before = self._engine.accepted_moves(task_id)
            try:
                out = self._runner(self._engine, task_id, executor_id, self._agents)
                if isinstance(out, dict) and out.get("status") in ("not_consented", "too_late"):
                    return                # re-offered before its session began: the round waits for the holder
                # DID THE NODE LEAVE THE EXECUTOR'S HANDS? Asked of the GRAPH, not of the report's
                # status word: an unparsed report, an undefined status and a signal the FSM refused
                # (a DELIVER with an empty summary, a BLOCK, the ACCEPT) all end the round with the
                # node where it was and its key spent — the status-word checks caught the first two
                # and returned "delivered" for the third, and the node sat to its deadline while its
                # issuer read "being worked on". One retry, then parked and handed to the issuer.
                _now = self._engine.graph.get_task(task_id)
                if (_now is not None and _now.state.name in self._EXECUTOR_STATES
                        and self._engine.accepted_moves(task_id) == _before
                        and not self._engine.parking.contested_reason(task_id)):
                    _st = out.get("status") if isinstance(out, dict) else None
                    _what = ("unreadable executor report" if _st == "unparsed" else
                             f"executor reported status {out.get('reported_status')!r}, which is none of "
                             f"delivered / blocked / challenge" if _st == "undecided" else
                             f"executor reported {_st!r} but no signal took effect (see the log for the "
                             f"refusal)")
                    self._one_retry_then_park(task_id, "u:", _what,
                                              cut=bool(isinstance(out, dict) and out.get("cut")),
                                              limit=bool(isinstance(out, dict) and out.get("limit")),
                                              ended=out.get("past_disk") if isinstance(out, dict) else None,
                                              note=out.get("disk_ended") if isinstance(out, dict) else None)
            except Exception as e:
                # Into the OBSERVATION FIELD, not only a log record. This handler catches the whole
                # spawn path, and a node whose dispatch raised is never retried — its key stays in
                # `_seen` until a re-ASSIGN. Logged alone, that is a graph which simply stops.
                log.exception(f"delegate run failed on {task_id}: {e}")   # …with where: str(e) alone named no line
                try:
                    # …AND THE ROUND IS GIVEN BACK. This handler catches the whole spawn path — the
                    # transport, the model factory, the usage record, reading the prompt file — and
                    # it used to log the failure and leave the key spent, which the comment here
                    # described in as many words and did not fix: "a graph which simply stops".
                    self._one_retry_then_park(task_id, "x:", f"dispatch failed — {e}",
                                              limit=_the_place_is_down(self._engine, e))
                # the log line above already carries the failure; the observation strip must not be
                # able to mask the dispatch error it is reporting
                except Exception:
                    pass

    def _redial(self, task_id: TaskId, key: str, whose: str = "the validator's") -> bool:
        """Dial a CUT call again, within its own small budget and after its spacing (TORN_DELAY_S, doubling). True =
        handled here.

        The budget is separate from the one retry on purpose: that retry exists to buy a second
        answer — a VALIDATION of a delivery, an executor's report — and a severed transport produced no
        first one; charging it there is how a node reaches its park having never been answered. Finite,
        because an unbounded redial is the loop Inv-5 exists against.
        """
        n = self._torn.get(key, 0)
        if n >= TORN_REDIALS:
            return False
        self._torn[key], delay = n + 1, TORN_DELAY_S * 2 ** n
        self._give_back(key, delay)
        self._engine.emit_info(
            "delegate", f"{task_id}: {whose} call was CUT before it answered (attempt {n + 1} of "
                        f"{TORN_REDIALS}) — redialled in {delay}s on its own tier; nothing was answered, so this "
                        f"does not spend the node's retry")
        return True

    def _give_back(self, key: str, delay: float) -> None:
        """The round given back after `delay` seconds: the dispatcher may claim its key again."""
        def again():
            """The round given back: the dispatcher may claim its key again."""
            self._seen.discard(key)
            self._dirty.set()
        if delay:
            (timer := threading.Timer(delay, again)).daemon = True
            timer.start()
        else:
            again()

    def _wait_out_limit(self, task_id: TaskId, key: str, whose: str) -> None:
        """The account's limit refused the call: nothing was answered, so neither the node's retry nor a redial is
        spent — the round comes back when the limit can have lifted, probed every LIMIT_RETRY_S as the issuer's door
        does, and the node's own clock still bounds it (§12.2). Read as an unreadable report, two limit-ended sessions
        parked a node for the 2.5 h of the window and after it (GB_c_compiler_tncfs1160, 2026-10-23). An execution place
        down is the same stop (`Engine.stop_for_the_place`): read as a cut call and then an unreadable report, a dead
        Docker daemon parked the first leaf in 8 min (GB_sql_database_tnij0m952)."""
        self._give_back(key, wait := self._engine.stop_wait_s() or LIMIT_RETRY_S)
        why = f": {stop['why']}" if (stop := self._engine.paused() or {}).get("place") else " by the account's usage limit"
        self._engine.emit_info("delegate", f"{task_id}: {whose} call was refused{why} — asked again in {wait:.0f}s; "
                                           f"nothing was answered, so this spends none of the node's retries")

    def _validate_queued(self, task_id: TaskId, expect_gen: tuple = (0, 0, 0), sign: bool = True) -> None:
        """A node's validation from the moment the dispatcher takes it on: in flight for every reader while it waits for
        a slot and while it runs (`claims.queue_validation`)."""
        key = self._engine.claims.queue_validation(task_id)
        try:
            self._validate_guarded(task_id, expect_gen, sign)
        finally:
            self._engine.claims.dequeue_validation(key)

    def _validate_guarded(self, task_id: TaskId, expect_gen: tuple = (0, 0, 0),
                          sign: bool = True) -> None:
        with self._slot(self._cap.closing, self._key_of(task_id, "v:")) as go:
            _t0 = self._engine.graph.get_task(task_id)
            if not go or not self._fresh(task_id, expect_gen, ("VALIDATING",)):
                if _t0 is not None:
                    self._seen.discard(self._round_key(_t0, "v:"))
                return
            ret = None
            self._engine.parking.unpark_validation(task_id)   # a fresh attempt un-parks it
            try:
                _t0 = self._engine.graph.get_task(task_id)
                _mo = self._retry_model.get(self._round_key(_t0, "v:")) if _t0 is not None else None
                # …AND WHAT THIS NODE HAS ALREADY COST. A refused report is kept beside the node with
                # a count (§2.3: ⊥ is evidence, not a verdict), and that count survives a restart
                # and a fresh delivery — where the in-process retry key does not. Measured across the
                # recent runs: 44 refused reports against 57 recorded verdicts, one node reaching
                # FIVE refusals. Spending the cheap tier again on a node that has already refused
                # once buys the same refusal; where the installation names a retry tier, a node
                # with a refusal behind it starts there (none by default — see validator_retry_model).
                if _mo is None and (self._engine.rejected_report(task_id) or {}).get("refusals", 0):
                    _mo = validator_retry_model()
                ret = self._validate(self._engine, task_id, self._agents, **({"model_override": _mo} if _mo else {}),
                                     **({"sign": sign} if not sign else {}))
            except Exception as e:
                log.warning(f"auto-validate failed on {task_id}: {e}")
                ret = "no-verdict:limit" if _the_place_is_down(self._engine, e) else ret
            t = self._engine.graph.get_task(task_id)
            if ret == "rejected":
                # the FSM refused the verdict (e.g. children not settled yet) — NOT a validator
                # failure: free the key so the node revalidates when the graph next changes,
                # and never burn the one no-verdict retry on it (observed live: a rejected PASS
                # was misread as no-verdict → the retry was wasted → the node stuck for good).
                if t is not None:
                    self._seen.discard(self._round_key(t, "v:"))
                return
            # NO-INSTRUMENT: nothing was spawned and nothing failed — no registered validator here, so
            # the verdict is the issuer's own act (§10.2) and the node waits for them, which the
            # frontier already says. Neither a retry nor a park belongs here.
            # RECORDED: VALIDATED, AND DELIBERATELY NOT SIGNED — a human issuer's node (§10.2 keeps the
            # signature theirs). The node stays in VALIDATING BY DESIGN, and the branch below
            # reads that state as "the validator died" and queues a retry: measured on the human
            # door 2026-08-22, every recorded verdict was followed by "validator returned no
            # verdict — one retry queued" and a SECOND paid run over the same delivery, minutes
            # after the first had already answered. A settled outcome is settled whoever signs.
            if ret in ("no-instrument", "recorded"):
                return
            # a validator run that died/unparsed leaves VALIDATING with no verdict — ONE retry
            if t is not None and t.state.name == "VALIDATING":
                key = self._round_key(t, "v:")
                # A CUT CALL IS NOT AN ANSWER, so it does not spend the answer's budget. The one
                # retry exists to buy a second VALIDATION of this delivery; a severed transport
                # produced no validation to be second to, and charging it against that budget is how
                # a node reaches its park having never been validated once. It gets a budget of its
                # own instead — small, because an installation that cannot complete a call twice in
                # a row has a problem no third attempt fixes, and finite, because an unbounded
                # redial is the loop Inv-5 exists against.
                if ret in ("no-verdict:limit", "no-verdict:bound"):
                    return (self._wait_out_limit(task_id, key, "the validator's") if ret == "no-verdict:limit"
                            else self._wait_for_the_issuer(task_id))
                if ret == "no-verdict:torn" and self._redial(task_id, key):
                    return
                if key not in self._retried:
                    self._retried.add(key)
                    self._seen.discard(key)
                    # …AND ON A STRONGER MODEL. The usual reason a report carries no verdict is
                    # coverage discipline — the validator names three behaviours and probes two, or
                    # labels one command for two of them — and that is exactly what a bigger model
                    # gets right first time (measured 2026-08-20: opus wrote a probe per label and
                    # passed, sonnet fused labels and was refused twice). Retrying the same tier
                    # mostly reproduces the same gap: a run ended `validator_no_verdict` after three
                    # calls and $4.40 with the artifact scoring 0.86 on the held-out suite. The
                    # retry is the moment to spend more, because it is the last one before the node
                    # parks and a person is needed.
                    # …ONLY WHERE THE INSTALLATION ASKS FOR IT. Off by default since 2026-09-27: it
                    # priced over the refusal instead of removing its cause, and it stuck to the node
                    # (13 of 19 validations of a small automatic run). `GFSO_VALIDATOR_RETRY_MODEL`
                    # names the tier; the tier is named in the log either way.
                    # …AND ONLY WHEN A MODEL ACTUALLY RAN. The escalation answers a report that
                    # came back thin, which is a model-quality problem. When the instrument never
                    # reached a model at all — its registered directory holds none of this delivery,
                    # say — a bigger model changes nothing except the price, and the log's own
                    # sentence ("a fuller report is usually a coverage-discipline gap") is then a
                    # wrong diagnosis printed with confidence. Measured 2026-09-05: three runs died
                    # here, each having spent its two attempts on a validator that never started.
                    # …and a CUT call earns no escalation either, for the same reason a never-started
                    # one does not: the tier answers a report's thinness, and neither of these two
                    # produced a report to be thin. Reaching here means the redials are spent, so
                    # what follows is the ordinary last attempt, on the node's own tier.
                    _tier = (validator_retry_model()
                             if ret not in ("no-verdict:never-ran", "no-verdict:torn") else None)
                    if _tier:
                        self._retry_model[key] = _tier
                    self._engine.emit_info(
                        "delegate", f"{task_id}: validator returned no verdict — one retry queued, "
                                    + (f"on {_tier} (a fuller report is usually a coverage-discipline "
                                       f"gap; the installation named it in GFSO_VALIDATOR_RETRY_MODEL)"
                                       if _tier else
                                       "on its OWN tier — " + (
                                           "no model ran, so a bigger one would only cost more"
                                           if ret == "no-verdict:never-ran" else
                                           "the escalation is off (GFSO_VALIDATOR_RETRY_MODEL)")))
                else:
                    # The retry produced no verdict either, and ⊥ is not pass (§2.3): the node cannot
                    # complete, and until now nothing said so — it simply stayed in VALIDATING. That
                    # is the canon's exhausted-automation case, whose answer is ATTENTION (§19.1's
                    # third mode), not silence and not auto-acceptance: auto-passing a node no one
                    # could validate would manufacture exactly the false close this system exists to
                    # prevent. Measured live (markdown_renderer, 2026-08-12): two unparsed reports,
                    # then a root sat in VALIDATING until the harness's own wall clock ended the run
                    # — and what is NOT done here is sending the system timeout, which in v4.0
                    # routed (VALIDATING, TIMEOUT) to DONE(auto_pass): auto-accepting a node no one
                    # could validate is the false close this measurement exists to detect. Since v4.1
                    # the node does not sit here indefinitely either — VALIDATING's own bound hands
                    # it to its ISSUER in ESCALATED (§16.14), with the delivery still in the log and
                    # no verdict invented. The driver stops validating it; the protocol carries it to
                    # the party who decides.
                    if self._ask_again_where_the_system_issues(task_id, key, _reask_wait(ret)):
                        return
                    self._engine.emit_info("delegate",
                                           f"{task_id}: validator produced no verdict twice — the ISSUER "
                                           f"must decide (⊥ is not pass, §2.3); no automatic verdict "
                                           f"will arrive, and VALIDATING's own bound hands the node to "
                                           f"him (§16.14)")
                    # …and say it where the DRIVER looks, not only in the log: the frontier kept
                    # printing "VALIDATE this" while nothing was ever going to come.
                    self._engine.parking.park_validation(task_id)

    def _wait_for_the_issuer(self, task_id: TaskId) -> None:
        """A delivery whose every unobserved check ran past its whole own bound: not validated again — the same tree
        times out again, and each re-ask was a paid validator run every half minute until T_validate (critic over the
        timeout ⊥). It waits, no verdict invented, for VALIDATING's bound to hand it to its issuer (§12.2, §16.14)."""
        self._engine.emit_info("delegate", f"{task_id}: {BOUND_SPENT}")

    def _ask_again_where_the_system_issues(self, task_id: TaskId, key: str, wait: float) -> bool:
        """After two validations with no verdict: where the SYSTEM is the node's issuer, schedule its
        instrument again rather than park the node for an issuer who would be told to decide.

        Its issuer owes the verdict within T_validate and has no act here but to obtain one, so it keeps
        asking until the bound hands the node to its issuer function (§16.14). Parking told "the ISSUER
        must decide" to an AUTO root's customer, who may not move — measured live, it took the project
        back instead (GB_json_parser_tlvnhk180)."""
        if not _system_issues(self._engine, self._agents, task_id):
            return False
        self._engine.emit_info("delegate", f"{task_id}: validator produced no verdict twice (⊥ is not "
                                           f"pass, §2.3) — asked again in {wait:.0f} s, "
                                           f"until VALIDATING's bound hands it to its issuer (§16.14)")
        timer = threading.Timer(wait, self._seen.discard, (key,))
        timer.daemon = True                      # like every thread here: never holds a process open
        timer.start()
        return True

    def _on_bus(self, tid=None, old=None, new=None, signal=None) -> None:
        """The transition-bus callback — trivial (set a flag), never blocks the signal path nor
        re-enters dispatch (the loop thread runs the real pass).

        It used to also mark ASSIGNed nodes so their dedup keys would be dropped — the way a REVISED
        node became fresh work. The generation now rides in the key itself (`_round_key`), so a
        revision is a new round with nothing to un-remember, and the mark is gone along with the
        double dispatch it caused on a node's FIRST assign.

        RESOLVE_BLOCK is the exception, and it has to be here rather than in the auto-sweep: a
        cleared block makes the node executable again WITHOUT moving its generation (no iteration,
        no reopen, no revision), so its round key stays spent and the dispatcher never looks at it
        again. The sweep dropped the key itself, so the automatic path worked and the HAND-sent
        signal did not — measured live: a node cleared by its issuer sat in EXECUTING for thirteen
        minutes with nothing running inside it. Every RESOLVE_BLOCK passes here, whoever sent it.

        REJECT_CHALLENGE is the same case (§12.4: back to the wait the challenge interrupted, the version unchanged):
        the system issuer's own answer freed the round, a holder's did not — a SOLO-dispatch holder rejected its hands'
        dispute and the node sat in EXECUTING to the run's ceiling with nothing running (GB_json_parser_tmms78001)."""
        if signal in (Signal.RESOLVE_BLOCK, Signal.REJECT_CHALLENGE) and tid is not None:
            t = self._engine.graph.get_task(tid)
            if t is not None:
                self._seen.discard(self._round_key(t))
                self._seen.discard(self._round_key(t, "consent"))
        if signal == Signal.ASSIGN and tid is not None and (t := self._engine.graph.get_task(tid)) is not None \
                and t.parent_id is None:
            # a root made (or handed on): its base's import is its own — off the signal path, docker work
            threading.Thread(target=self._root_made, args=(t,), daemon=True).start()
        if new == State.DONE and tid is not None:
            # git work, so off the signal path; a parent's session merges its DONE parts itself on entry, so the
            # order of this thread and that session decides nothing. A node whose place was made is marked joining
            # HERE, before the thread starts, so no reader sees it DONE with its join neither running nor done — and
            # asked without git (a place exists only in a git base), which the signal path never waits on
            t = self._engine.graph.get_task(tid)
            if (w := _place_of(self._engine, self._agents, t)) is not None and made(self._engine, w[1]):
                self._engine.joins.mark_joining(tid, True)
            threading.Thread(target=self._join, args=(tid,), daemon=True).start()
        if new == State.ABANDONED and tid is not None:
            threading.Thread(target=self._released, args=(tid,), daemon=True).start()
        self._dirty.set()

    def _root_made(self, root) -> None:
        try:
            root_created(self._engine, self._agents, root)
        except Exception as e:                          # noqa: BLE001 — said, never raised into a thread
            self._engine.emit_info("execution", f"{root.id}: its base could not be imported - {e}")

    def _will_join(self, tid) -> bool:
        """Has this passed node a place of its own whose result must still land somewhere — so it is joining now?"""
        t = self._engine.graph.get_task(TaskId(tid))
        w = _workspace(self._engine, self._agents, t) if t is not None else None
        return (w is not None and made(self._engine, w[1])
                and _where_it_joins(self._engine, self._agents, t, w) is not None)

    def _join(self, tid) -> None:
        """A part PASSed: it joins the whole (`join_whole`); at the root's PASS the joined places go."""
        # …IN FLIGHT while it runs: a root's join is what puts the delivered result in the base, and a reader taking
        # the root's DONE for "the base holds it" reads ahead of the merge (`/api/runtime` lists it as busy)
        why = None
        t = self._engine.graph.get_task(TaskId(tid))
        is_root = t is not None and self._engine.graph.get_parent(t.id) is None
        try:
            with _inflight("join_whole", self._engine, tid):
                why = join_whole(self._engine, self._agents, tid)
                if is_root and why is None and t.state == State.DONE:   # …and lands where its user reads it
                    why = land_accepted(self._engine, self._agents, t)
        except Exception as e:                          # noqa: BLE001 — a join that failed is said, not raised
            why = f"{type(e).__name__}: {e}"
            log.warning(f"delegate: {tid} did not join its whole: {e}")
            self._engine.emit_info("delegate", f"{tid}: its delivery did not join its whole - {e}")
        finally:
            # a ROOT whose result did not land stays named, with the branch that holds it, until a later try lands
            # it (`_rejoin`, backing off): the base is what a reader of `complete` reads. A part that did not land is
            # its whole's to integrate (`_enter_workspace`).
            if why and NOT_ON_ITS_BRANCH not in why and (w := _place_of(self._engine, self._agents, t)) is not None:
                why = f"{why} (its result stands on branch `{w[2]}`)"
            if is_root:
                delay = min(max(2 * self._retry_at.get(str(tid), (0, 0))[1], JOIN_RETRY_S), JOIN_RETRY_MAX_S)
                (self._retry_at.__setitem__(str(tid), (time.monotonic() + delay, delay)) if why
                 else self._retry_at.pop(str(tid), None))
            self._engine.joins.mark_joining(tid, False, unjoined=why or None)
            self._dirty.set()
        if is_root and why is None and t.state == State.DONE:
            self._clear_places(t)
        self._released(tid)

    def _clear_places(self, root) -> None:
        """The root landed: its places go, unless a verdict is still coming (a signature can land before it, and it is what
        refutes the signed node) or a node is still open (a child attached after the close works in them) — then a later
        pass asks again (`_clear_what_waited`). The clearing ends every session of the project, rounds included, so any
        node holds it, and work outweighs the disk: every issued node has a clock. A restart keeps nothing of the wait, and
        `_rejoin`'s first pass comes back here over a place still standing."""
        if (self._engine.open_nodes()
                or any(self._engine.claims.validation_in_flight(t.id) for t in self._engine.all_tasks())):
            self._to_clear.add(str(root.id))
            return
        self._to_clear.discard(str(root.id))
        try:                                            # the places go once the root landed; a refusal here is
            with _inflight("clear_workspaces", self._engine, root.id):      # …still its work: no rest under it (`_rest`)
                clear_workspaces(self._engine, self._agents, root)   # tidying, never "did not land" (critic r4, J4)
        except Exception as e:                          # noqa: BLE001
            log.warning(f"delegate: {root.id} landed; its places were not cleared: {e}")

    def _clear_what_waited(self) -> None:
        """Each pass, a stop or a goal's end included: clear what `_clear_places` held, if the root still stands landed. A
        root reopened, or joining again, meanwhile is its next join's to clear (`_join`)."""
        for tid in self._to_clear.copy():
            t = self._engine.graph.get_task(TaskId(tid))
            if t is not None and t.state == State.DONE and self._engine.joins.root_landed(t):
                self._clear_places(t)
            else:
                self._to_clear.discard(tid)

    def _released(self, tid) -> None:
        """A node that ended — passed and joined, or cancelled — holds no container any more: its place's, its client's
        and its commands' end, its directories and CLI state kept, and a node reopened later starts them again on its
        next session. Standing until the project stopped, a done node's processes and memory counted against every
        other's (SECURITY.md)."""
        t = self._engine.graph.get_task(TaskId(tid))
        if t is None or t.state not in (State.DONE, State.ABANDONED) or str(tid) in self._engine.joins.joining_nodes():
            return
        # …a verdict still coming over a node already signed: its round is what refutes it (the goal's end takes them)
        if self._engine.claims.validation_in_flight(t.id):
            return
        # …the place's own node alone: a scope's member works in its top's place, and its PASS ended the containers
        # the scope's rework was running in (critic B8)
        if (session_scope(self._engine, self._agents, t) or t).id != t.id:
            return
        try:
            if (w := _place_of(self._engine, self._agents, t)) is not None and made(self._engine, w[1]):
                (ex := execution_of(self._engine, self._agents)).release(w[1])
                release_rounds(ex, w[1])
        except Exception as e:                          # noqa: BLE001 — tidying, said, never raised into a thread
            log.warning(f"delegate: {tid} ended; its place's containers were not ended: {e}")

    def _over(self) -> bool:
        """Every node settled and the result landed — asked only once a start has read what its last process left
        (`_rejoin`): a parent's acceptance settles none of its children (§11.3), so a root's DONE alone is not this."""
        joins, graph = self._engine.joins, self._engine.graph
        return (self._rejoined_once and not joins.joining_nodes() and not joins.unjoined_roots()
                and bool(tasks := self._engine.all_tasks()) and not self._engine.open_nodes()
                # …a DONE readable before its join is marked: `root_landed` reads that as being joined
                and all(joins.root_landed(t) for t in tasks if t.state == State.DONE and graph.get_parent(t.id) is None))

    def _rest(self) -> None:
        """The containers of a project that nothing of will run ended once, when nothing of it runs any more — stopped
        (`run_state`'s `stopped`) or its goal over (`_over`), else they stood idle on the person's machine for as long as
        it was left: its work stands in its volumes, and its next start makes them again over them (`ExecutionPort.stop`)."""
        # …asked again after what runs now, which may start one (a verb that moves no node), and after a stop that failed
        if any(w.get("project") == (self._engine.project_name or DEFAULT_PROJECT) for w in in_flight()):
            self._rested = False
            return
        if self._rested:
            return
        try:
            execution_of(self._engine).stop()
            self._rested = True
        except (OSError, ValueError, subprocess.SubprocessError) as e:
            log.warning(f"the stopped project's containers could not be ended: {e}")

    def _rejoin(self) -> None:
        """Try again every root whose result did not land, and on start every passed root whose branch the base does
        not hold yet — a process stopped between a root's DONE and its join left nothing in memory to say so."""
        now = time.monotonic()
        roots = {r for r in self._engine.joins.unjoined_roots() if self._retry_at.get(r, (0, 0))[0] <= now}
        if not self._rejoined_once:
            self._rejoined_once = True
            for r in self._engine.all_tasks():
                if r.state == State.DONE and self._engine.graph.get_parent(r.id) is None and self._will_join(r.id):
                    roots.add(str(r.id))
        for r in roots - set(self._engine.joins.joining_nodes()):
            self._engine.joins.mark_joining(r, True)
            threading.Thread(target=self._join, args=(r,), daemon=True).start()

    def start(self) -> None:
        """Begin the dispatch loop for this engine — event-driven off the transition bus, with a
        bounded safety-net poll behind it."""
        # (the transition bus is subscribed in __init__ — the callback is load-bearing, not a wake)
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
        """Stop the loop and wait briefly for it to settle. Idempotent."""
        self._stop.set()
        self._dirty.set()                              # wake the loop so it exits promptly


_DISPATCHERS: dict[int, Dispatcher] = {}
_DEFAULT_AGENTS: AgentRegistry | None = None


def default_agents() -> AgentRegistry:
    """The server-wide roster singleton (one json file, shared by every project engine).

    Keyed by the PATH it was built for, so a process that moves its state home — every test that
    does, and every embedding that runs two homes in one process — gets the roster of the home it is
    in now. As a plain singleton it kept the first path forever: the suite registered its probe roles
    into the REAL roster of this installation, beside live runs' roles (found 2026-08-21)."""
    global _DEFAULT_AGENTS
    path = str(agents_path())
    if _DEFAULT_AGENTS is None or _DEFAULT_AGENTS.path != path:
        _DEFAULT_AGENTS = AgentRegistry(path)
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
