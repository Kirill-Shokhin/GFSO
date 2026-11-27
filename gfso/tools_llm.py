"""The LLM half of the action surface — the verbs that SPAWN model runs.

Split from `gfso.tools` (the structural half, L1: core+engine only) so the structural surface
carries zero LLM/adapter dependencies — this module is L2 and pulls decompose/critic/runtime
freely. Same contract as tools.py: pure functions `(engine, *args) -> JSON-able dict`.

`TOOLS` here is the COMPLETE transport registry (structural ∪ LLM) — the binding layers
(MCP / CLI / HTTP) generate their surfaces from THIS dict; `gfso.tools.TOOLS` stays the
structural subset.
"""
from __future__ import annotations

import functools
import hashlib
import inspect
import json
import logging
import os
import re
import threading
import time
import contextvars
from concurrent.futures import Future, wait as _settled_within
from contextlib import nullcontext
from pathlib import Path
from dataclasses import asdict
from typing import Optional, Union

from gfso import canon as _canon, past
from gfso.llm import llm_factory
from gfso.executions import declaring_role, execution_of, where_it_runs
from gfso.workspaces import no_repository, unjudged, record_repository, validator_workdir
from gfso.roster import default_agents, publish_the_workforce, staffed
from gfso.adapters import worktrees as W
from gfso.adapters.execution import IMPORTED, ContainerExecution
from gfso.adapters.hostrepo import committed, left_out
from gfso.core.types import (HOST, TERMINAL_STATES, VOLUME, AgentId, Mode, Signal, State, TaskId, Stage,
                             Verdict, passed)
from gfso.core.protocol.invariants import INTENT
from gfso.places import cheap_to_ask
from gfso.critic import runner as _critic_runner
import gfso.decompose as _decompose
from gfso.adapters.execution import network_of, node_key
from gfso.decompose import NoPlan, decompose_into, artifact as _artifact, planning as _planning, kept as _kept
from gfso.engine.events import emit_cb
from gfso.engine.moves import DOOR_KEYS, READS, SIGNERS, door_holder, door_role, role_holder, signer_arg, signer_due
from gfso.engine.validation import (a_human, depth_of, hands_of, heard_on, his_seam,
                                   holder_boundary, in_chat_names, mode_kind)
from gfso.core.graph.metrics import DIAGNOSTIC_MEANS
from gfso.core.graph.model import (MAX_ITERATIONS_CEILING, bounds_refusal, project_deadline_s, project_now,
                                   witnessed_count)
from gfso.adapters.llm.stats import stat_line, refused_by_limit, what_stopped
from gfso.engine import PERSONS_WORDS, Engine
from gfso import signin, tools as _tools
from gfso.serverctl import open_the_page
from gfso.config import CALLER, agent_id as _config_agent_id, caller_id, client_kind, how_it_is_waited, refuse_unsigned, reserved_refusal
from gfso.config import WRITTEN_IN_THE_CALL as _config_written_in_the_call, FOR_THE_PERSON, PERSONS_NAMES
from gfso.engine.frontier import OBSERVE
from gfso.adapters.llm.structured import parse_structured, schema_instruction
from gfso import config as _config_module
from gfso.config import (DEFAULT_EXECUTION, DEFAULT_PROJECT, ROOT_ID, MODEL_DEFAULT, executions,
                         WAIT_MAX_SECONDS, WAIT_POLL_SECONDS,
                         ANSWER_WITHIN_SECONDS)
from gfso.inflight import flight, in_flight
from gfso.validate import validate_result
from gfso.tools import answering
from gfso.in_chat import (a_chats_delivery, back_to_their_branch, chat_place, not_its_repository, on_their_branch,
                          switches_branches, work_branch)

log = logging.getLogger(__name__)


def _how_many_are_open(gate_passed: bool, open_findings, a_model_ran: bool) -> dict:
    """ONE NUMBER FOR "HOW MANY ARE OPEN", and ⊥ wherever it was not measured.

    The findings live in three fields — per-criterion verdicts, conflicts, undecided obligations —
    and a round could read `undecided: 0` while the gate was still shut on the other two, so a
    caller's own summary genuinely missed them (agent door, 2026-08-21). The gate's own list is the
    count. Both ways it can be UNMEASURED carry a reason instead of a zero, because a number that
    cannot tell "none" from "not measured" must not be a number: the Syntactic level gating the
    checker out, and the checker being admitted and answering nothing.
    """
    if not gate_passed:
        return {"open_count": None,
                "open_count_note": ("not measured: the Level-2 checker did not run, because the "
                                    "Syntactic level (§9.5) is not clean — `list_holes` names "
                                    "those, and they are what to fix first.")}
    if open_findings is None:
        return {"open_count": None, "open_count_note": _nothing_was_validated(a_model_ran)}
    return {"open_count": len(open_findings)}


def _nothing_was_validated(a_model_ran: bool) -> str:
    """Why the open-finding count is ⊥ when the checker was ADMITTED and still said nothing.

    The branch beside this one already knows the lesson — a number that cannot tell "none" from "not
    measured" must not be a number — and it covers only the case where the Syntactic level gated the
    checker out. The other case is the one a fresh install lives in: the structure is clean, the
    checker runs, and no readable verdict comes back because no model is available at all. Probed
    2026-09-05 with the Claude CLI off the PATH: `gate_passed: true`, `open_count: 0`,
    `execution_admitted: false`, and the engine's own refusal then said "run review_decomposition
    first" — the verb that had just answered. Zero findings, execution refused, and the cure is the
    thing you did: a loop with no exit named, for everyone without the CLI.
    """
    return ("not measured: the checker was admitted and returned no readable verdict"
            + (" — it made NO model call, so most likely no provider is available (the Claude CLI on PATH, "
               "a credential set by `gfso credential claude`)" if not a_model_ran else "")
            + ". No verdict is never read as clean (§9.5 fail-closed), so execution stays shut. Run this "
              "again — a reply that could not be read may not recur. If every run comes back like this, two "
              "supported ways on: make a checker available and run this again, or take the canon's "
              "EXPLORE branch — `set_mode(..., l2_gate=False)` for this project (`GFSO_L2_GATE=0` for the "
              "server), where the plan's causal check is "
              "bought with contact instead of with the checker (§9.9). The second is a deployment "
              "decision, not a workaround: it is what a system with no checker honestly is.")


def _delta_since_the_last_review(out: dict, prev_open, prev_ts) -> None:
    """What changed since the last check of the SAME plan — and the SAME KEYS every time.

    The checker is an approximation (§9.9) and may legitimately differ between runs: on a plan whose
    criteria were byte-identical, one finding vanished and another appeared. A reader who sees which
    findings are NEW can tell a plan that is converging from one that is being re-read.

    Its own owner because the answer's shape is its own contract: `delta_note` was present on a
    node's first review and ABSENT on the second, replaced by `compared_with`, and a client reading
    it raised KeyError on its second call (HTTP door, wave 27, 2026-09-06). Every branch below sets
    all four keys.
    """
    # …compared only when THIS round measured: a round that reached no verdict reported every earlier
    # finding "closed" beside `execution_admitted: false` (critic round 12)
    if prev_open is not None and out.get("open_count") is not None:
        out["new_since_last_review"] = [f for f in out["open_findings"] if f not in prev_open]
        out["closed_since_last_review"] = [f for f in prev_open if f not in out["open_findings"]]
        # …AND WHICH CHECK IT IS COMPARED WITH. A round that fails Level-0 records no findings, so a
        # later round measured its closures against a round that had measured nothing — eight
        # genuinely closed findings reported as zero closed (measured on the human door 2026-08-22).
        out["compared_with"] = prev_ts or "the previous review"
        out["delta_note"] = (f"compared with the review of {out['compared_with']}: "
                             f"{len(out['new_since_last_review'])} new, "
                             f"{len(out['closed_since_last_review'])} closed.")
        return
    out["new_since_last_review"] = None
    out["closed_since_last_review"] = None
    out["compared_with"] = None
    out["delta_note"] = ("no earlier review to compare with — this is the first on this node."
                         if prev_open is None else
                         "not compared: the checker did not run this round (see `open_count_note`), "
                         "so nothing here is new or closed.")


def review_decomposition(engine: Engine, task_id: str, model: Optional[str] = None) -> dict:
    """Validate a node's decomposition: the STRUCTURAL gate (L0/L1: coverage, DAG, glue, non-redundancy —
    fails ⇒ fix those first) + the L2 CHECKER (canon §9.1 Level 2): one zero-tool call checking, per
    parent criterion, whether the mapped children's criteria — taken as real-world facts — CAUSALLY
    guarantee it (sufficient / insufficient-with-named-gap / uncertain), plus semantic FM-2 conflicts
    the formal CHECK-8 can't see. ADVISORY: never auto-fixes — fix via the FSM verbs or consciously
    declare ACCEPTED_RISKS. The hole-hunt («what's missing from the space») is NOT this verb — that is the
    DECOMPOSER's question: run auto_decompose (refine). Use this on externally-authored or hand-edited
    graphs; the UI's «AI review» button is this verb. Answers at once: a check running past a few seconds goes on in
    the server, its verdict read by `get_review(task_id)` once it lands."""
    _cb = emit_cb(engine, "review")
    # ONE CHECK PER VERSION OF THE PLAN. The verb spends a model run, and nothing stopped a second
    # caller (or the frontier's own directive) from starting another over the same unchanged plan —
    # which `validate_result` has refused to do for a while (measured on the human door 2026-08-22).
    _slot = engine.claims.begin_review(TaskId(task_id))
    if _slot is None:
        return {"task_id": task_id, "inflight": True, "verdict": None,
                "note": "a Level-2 check is already running over this version of the plan — "
                        "duplicate spawn suppressed; its verdict lands by itself (`get_review` "
                        "reads it when it does). If nothing lands, the plan has changed under it "
                        "or its runner died: `revise` moves the node to a new version and the "
                        "check can be asked again."}
    llm = None
    try:
        llm = llm_factory(model or engine.system_model(), execution=execution_of(engine))
        llm.on_tick = _cb
        llm.stage_hint = f"{task_id} L2-checker"
        _cb(f"{task_id}: L2 checker (causal entailment per parent criterion)…")
        # What stood open BEFORE this run, so the reply can say which findings are new (see below).
        # From the STORED review, not the gate's current view: the gate answers None the moment an
        # edit stales the verdict — which is exactly the situation in which someone re-runs the
        # check — so the delta went blank in the rounds that changed something. Measured on the
        # human door 2026-08-22, on the round where the checker CONTRADICTED two earlier ones:
        # "the round that actually regressed is the round where the delta reporting switched off".
        _prev_open = engine.stored_review_findings(TaskId(task_id))
        _prev_ts = (engine.get_critique(TaskId(task_id)) or {}).get("ts")
        out = asdict(_critic_runner.review_decomposition(engine, TaskId(task_id), llm=llm))
    finally:
        # EVERYTHING AFTER THE CLAIM, not only the model call. Four statements used to sit between
        # `begin_review` and this `try` — building the provider, arming the tick callback, and two
        # storage reads. `llm_factory` raises on an ordinary misconfiguration, and the claim then
        # leaked with no model ever having run: no kill, no hang, no thread teardown needed.
        engine.claims.end_review(_slot)
        if llm is not None:   # what the check cost, on the record — a raise after the model ran loses none of it
            engine.record_llm_usage(Stage.L2_CHECK_PLAN, llm, TaskId(task_id))
    out["stats"] = list(llm.calls)
    # …AND HOW TO READ IT AGAIN FOR FREE. This verb SPENDS a model run every call, and it is also
    # the only place the review is rendered — so a reader whose first answer scrolled past re-ran it
    # to see the tail, at $0.16 and 65 seconds for a record that had not changed (measured on the
    # agent door 2026-08-22). `get_review` reads the stored one and costs nothing; it was never
    # mentioned where the money is spent.
    out["reread_free"] = (f"this ran the checker ({len(llm.calls)} model call(s)) — `get_review("
                          f"'{task_id}')` reads the SAME record again for free; re-run this verb "
                          f"only after the plan changed.")
    # WHAT IT MEANS FOR EXECUTION, said in the reply. `gate_passed` is about Level 0/1 only, and a
    # reader took `gate_passed: true` for "the plan is good" while the checker was saying a criterion
    # is not carried (measured 2026-08-20). The question anyone actually has is whether the children
    # may start, so the answer carries it.
    _open = engine.open_l2_findings(TaskId(task_id))
    out["execution_admitted"] = engine.execution_admitted(TaskId(task_id))
    # ... and what the OTHER flag is about, beside it. `gate_passed: true` next to
    # `execution_admitted: false` reads as a contradiction unless you already know the first names a
    # PRE-condition (the structure was clean enough to run the checker) rather than a verdict on the
    # plan (measured on the human door 2026-08-21 — only `what_this_means` saved the reading).
    out["gate_passed_means"] = (
        "Level 0/1 only: the structure was clean enough for the Level-2 checker to run. It is not a "
        "verdict on the plan — that is `execution_admitted`, and the two disagree whenever the "
        "checker ran and returned findings.")
    # ONE NUMBER FOR "HOW MANY ARE OPEN". The findings live in three fields — per-criterion verdicts,
    # conflicts, undecided obligations — and a round could read `undecided: 0` while the gate was
    # still shut on the other two, so a caller's own summary genuinely missed them (measured on the
    # agent door 2026-08-21). The gate's own list is the count.
    out["open_findings"] = _open if _open is not None else []
    # …AND "NOT MEASURED" IS NOT "NOTHING OPEN". When the Syntactic level fails, the Level-2 checker
    # is gated out and names nothing — and the count then read `open_count: 0` beside six hard L0
    # failures, which a reader glancing at it takes for a clean plan (measured on the human door
    # 2026-08-22). A number that cannot distinguish "none" from "unmeasured" must not be a number.
    out.update(_how_many_are_open(bool(out.get("gate_passed")), _open, bool(llm.calls)))
    _delta_since_the_last_review(out, _prev_open, _prev_ts)
    out["what_this_means"] = (
        "the children may start" if out["execution_admitted"] else
        "the children may NOT start yet: Level-0 checks are open (`list_holes`), so the Level-2 review could not run "
        "— repair the plan, then review it" if engine.split_holes(TaskId(task_id)) else
        "the children may NOT start yet: no CURRENT Level-2 verdict covers this decomposition"
        if _open is None else
        "the children may NOT start yet: the Level-2 review left findings open — "
        + ", ".join(_open) + " (fix the plan AND re-run this review — a fix retires the verdict "
                              "rather than discharging it — or `dispute_finding` in writing)")
    # …AND HAND BACK THE KEYS IT JUST TOLD THEM TO COPY. `dispute_finding`'s own help says the review
    # returns the exact open strings under `dispute_keys`, and this verb answered `null` for it while
    # naming those same strings in the sentence above (MCP door, 2026-09-02). The reader was told to
    # copy one from a field that was empty, with the values sitting in prose a line away.
    if _open:
        out["dispute_keys"] = list(_open)
    # WHAT THE LINE SAYS MUST MATCH WHAT THE GATE DID. "advisory" was written when the checker only
    # advised; it now GATES, and a reader took "gaps/conflicts returned (advisory)" for something
    # they could ignore while the same call was answering `execution_admitted: false` (measured on
    # the human door 2026-08-22: "I nearly stopped re-running the review"). And the stats belong to
    # the whole check — the sub-call's line under-reported one review by thirty times.
    verdict = ("gate FAILED — fix L0/L1 first" if not out.get("gate_passed")
               else "no gaps found — execution ADMITTED" if out.get("execution_admitted")
               else f"{out.get('open_count', 0)} finding(s) OPEN — children may NOT start"
               if out.get("semantic_covered") is not None
               else "no checker verdict")
    # …and do not announce a checker that did not run: "gate FAILED — fix L0/L1 first · checker
    # done" was printed for a round in which the checker never spoke (measured 2026-08-22).
    _cb(f"{task_id}: {verdict}" + (f" · checker {stat_line(llm)}" if out.get("gate_passed")
                                   else " · the Level-2 checker did not run"))
    return out


_DOC_MAX = 256_000   # bytes of one named document carried into the goal's contract


def _named_documents(engine: Engine, request: str) -> str:
    """The documents `request` names, written out under it (`_documents_named`, `_under_the_goal`)."""
    return _under_the_goal(_documents_named(engine, request))


def _under_the_goal(docs: list) -> str:
    """`docs` ({path, text}) as the goal's contract carries them, under the request."""
    return ("\n\n# THE DOCUMENTS THIS REQUEST NAMES, as they stood in the work's place when the goal was set\n\n"
            + "\n\n".join(f"## {d['path']}\n\n{d['text']}" for d in docs)) if docs else ""


def _documents_named(engine: Engine, request: str) -> list:
    """The files a new goal's request names that stand in the place its work will be done — the workdirs of
    this project's registered roles — written out under the request, so the goal's contract carries them.

    The plan author, its auditors and the root's reviewer are zero-tool completions: a request saying
    "implement what prompt.md specifies" reached them as its one-paragraph summary, and the plan's criteria
    contradicted the 12 KB statement the root's executor then read in its workdir (spreadsheet_engine, AUTO
    haiku, 2026-10-10 — EVIDENCE_LOG §13.38). Whoever reads the contract now reads what the executor reads: in the
    user's chat the tree as it stands; elsewhere what the new root imports, the user's committed HEAD (`committed`) — read
    from the live tree, a project in a container carried an uncommitted edit and an untracked `.env` to the provider (critic,
    ran); read from its volume, a second goal's contract quoted what the earlier root's executors left there (critic)."""
    ex = execution_of(engine)
    bases, files = _work_places(engine, ex), ex.files
    read = ((lambda b, p: files.read_bytes(str(p), _DOC_MAX + 1) if files.exists(str(p)) and not files.is_dir(str(p)) else None)
            if files is HOST else (lambda b, p: committed(b, p.relative_to(b).as_posix())))
    seen, parts = set(), []
    for tok in re.findall(r"[^\s`'\"(),;<>\[\]]+", request or ""):
        tok = tok.rstrip(".:")
        # a word of prose is no file name; a path to a file that stands is one, `Makefile` included
        # …a share named here, by the request or by the reader's answer, is asked about from this host: not asked
        if "://" in tok or not cheap_to_ask(tok) or not (Path(tok).suffix or Path(tok).is_absolute()):
            continue
        # the first base the name stands in is the one it names; a name met again is the same document
        for b in bases:
            p = Path(os.path.normpath(Path(tok) if Path(tok).is_absolute() else b / tok))
            if not p.is_relative_to(b) or (raw := read(b, p)) is None:
                continue
            if p not in seen and len(raw) <= _DOC_MAX and b"\0" not in raw:
                parts.append({"path": p.relative_to(b).as_posix(), "text": raw.decode("utf-8", errors="replace")})
            seen.add(p)
            break
    return parts


def _work_places(engine: Engine, ex) -> list:
    """The directories this project's registered roles work in — this project's own only: an unscoped or another
    project's role stands in someone else's place. Where the work runs apart, its one base (`ex.base`), the one imported:
    another role's workdir, a typo or a role left from a name reused, gave the contract a repository never imported (critic, ran)."""
    if ex.files is not HOST:
        return [Path(os.path.normpath(ex.base))]
    return sorted({Path(os.path.normpath(w)) for c in staffed().list().values()
                   if (c or {}).get("kind") in ("llm-executor", "llm-validator")
                   and c.get("project") and c.get("project") == engine.project_name
                   and (w := c.get("workdir")) and cheap_to_ask(w) and Path(w).is_dir()})


_PLACE_SCHEMA = {"type": "object", "required": ["files"],
                 "properties": {"files": {"type": "array", "items": {"type": "string"}}}}
_PLACE_SYSTEM = ("You read the place where a goal's work will be done, before its plan is written. Name the files whose "
                 "text defines the work the request asks for: its statement or specification, the interface the "
                 "delivery must meet (how it is built and invoked, what it reads and what it prints), the stubs and "
                 "build files it starts from. Read them to judge; write nothing. Return their paths relative to "
                 "the place named in the request.")


def _work_place_documents(engine: Engine, request: str, model: str) -> str:
    """The files of the work's place that define the work, as a read-only run in each place names them — their names
    only; `_named_documents` carries their text verbatim. The plan's author is a zero-tool completion: given a
    customer's summary that named no file, it never saw the binary, its input or its output, wrote probes against an
    interface that does not exist and, out of budget, `echo` in their place (AUTO haiku 4.5 sql_database,
    GB_sql_database_tmu9cb784, 0.09 held-out). Criteria take their content from contact with the work (d6, §4.1)."""
    named: list = []
    ex = execution_of(engine)
    # …not over a base no session of its project may run in: a volume of a base with no git, from before such bases
    # were refused, gave the reader its `.env` and ignored files, and the reader gave them to the provider (critic)
    if ex.files is not HOST and (why := ex.agents_refused()):
        engine.emit_info("plan", f"the work's place is not read for the plan: {why}")
        return ""
    for base in _work_places(engine, ex):
        llm = llm_factory(model, execution=ex)
        llm.stage_hint = f"root place-reader({engine.project_name})"   # named like every role's trace, so it is read
        try:
            # …from a temp of its own where the places stand apart, reading the base read-only: in the base it shared the
            # model client's state of the root's executor, and read the conversations that state holds
            if ex.files.holds(str(base)):
                ex.files.mkdir(here := os.path.join(ex.temp_root(), "plan-reader"))
            else:
                here = str(base)
            text = llm.run_agent(_PLACE_SYSTEM, f"The work's place: {base.as_posix()}\n\n" + (request or "")
                                 + schema_instruction(_PLACE_SCHEMA),
                                 allowed_tools=("Read", "Glob", "Grep"), cwd=here, timeout=600, max_turns=30)
        except Exception:                                   # noqa: BLE001 — the goal is set from the request alone
            log.warning("reading the work's place failed", exc_info=True)
            continue
        finally:
            engine.record_llm_usage(Stage.DECOMPOSER, llm, TaskId(ROOT_ID))
        named += [(base / f).as_posix() for f in (parse_structured(text or "", _PLACE_SCHEMA) or {}).get("files") or ()]
    return " ".join(named)


def _what_the_gate_does(engine: Engine, root_id, kids: list, n: int) -> str:
    """The sentence about undecided obligations, said from what the gate answers NOW — never promised.

    "The gate will refuse execution" was printed over a root with no split (spreadsheet_engine, 2026-10-11),
    and a system executor took it: the plan gate holds a split's children (§11.5, `execution_blocked_by`),
    and an atomic root has none — its unwritten criterion is a defect of the goal's setting, read only at
    contact (§8.3). Nor does it hold where `GFSO_L2_GATE=0` or another party takes the child (EXPLORE, §9.9)."""
    said = f"{n} obligation(s) of the goal are decided by no criterion (`undecided_obligations`)"
    if any(k.state == State.OFFERED and engine.execution_blocked_by(k.id) for k in kids):
        return (f"{said}, so the gate refuses execution of its children — fix the criteria they name and run "
                f"`review_decomposition('{root_id}')`.")
    if not kids:
        return (f"{said}, and '{root_id}' has no split, so no plan gate stands before its execution: an "
                f"obligation its own criteria do not write is a defect of the goal's setting, read only at "
                f"contact (§8.3) — its issuer lifts it by revising the criteria (`edit_criteria('{root_id}')`).")
    return (f"{said}; the gate does not hold these children here (the Level-2 gate is off, or another party "
            f"takes them — EXPLORE, §9.9) — fix the criteria they name and run `review_decomposition('{root_id}')`.")


def _no_plan(no, verb: str = "auto_decompose") -> str:
    """Why no plan was built — and where a system stop refused its calls, that none was written, not that it was
    unreadable (critic over b5f7350) — in the words of `verb`, the one to call again."""
    stopped = what_stopped(no.stats)
    return (f"{stopped}: no plan was authored — the project is stopped until it lifts; then call {verb} again"
            if stopped else str(no).replace("auto_decompose", verb))


def _no_deferral_nobody_makes(spec: Optional[dict], splittable: bool) -> Optional[dict]:
    """`spec` as handed in — refused where it becomes the user's plan (handed in whole under AUTO, not `splittable`) with
    a deferred split: such a plan is never re-split by the system (`users_plan`), so the split would wait for a round
    that never comes, and the run would stop on "refuted" when its producer passed (critic). Under SOLO or SEMI the
    system or the holder still splits it. The lift is the user's own: split those parts in the plan, or hand it in open."""
    if spec is None or splittable:
        return spec
    if later := [str(s.get("id")) for s in spec.get("subtasks") or () if s.get("split_after")]:
        raise ValueError(f"the plan handed in defers the split of {', '.join(later)} (`split_after`), and a plan handed in "
                         f"whole is never split by the system: split them in the plan, or hand it in open "
                         f"(`open_plan=true`) for the system to split them once their producers deliver")
    return spec


def _childrens_executor(engine: Engine, root_id: str, assignee: str, executor: Optional[str], kid) -> str:
    """Who the mode hands `root_id`'s children to (`kid`), or the `executor` the caller named where the mode lets it —
    one rule for the plan and the go, so a plan is never placed for a session its parts will not run in."""
    if executor and str(executor) != str(kid) and not (
            str(kid) != caller_id() and str(executor) in map(str, engine.seam_keepers(AgentId(assignee)))):
        # the lift is the caller's own call without the name (§12.16 (ii)); naming `set_mode` as the way
        # out handed it the user's choice — measured, a semi holder read it, asked to switch, and stopped
        raise ValueError(
            f"this project runs in {(engine.mode_at(root_id) or {}).get('mode')}: the children of '{root_id}' are held "
            f"by {'the system' if str(kid) != caller_id() else 'you'}, so they cannot go to "
            f"{executor}. Call it again without `executor` — the mode assigns them.")
    return executor or str(kid)


def _refused_while_written(engine: Engine, node: str, other: tuple) -> dict:
    """The refusal of a move on `node` while the authoring `other` ((node, handle), `Engine.authorings.over`) writes over
    it: it names what it waits on and lifts when that ends (§12.16(ii))."""
    n, h = other
    where = "that node" if n == node else "in its subtree" if n in engine.authorings.lineage(node) else "above it"
    return {"refused": True, "task_id": node, "being_rewritten": h or n,
            "error": f"being_rewritten: an authoring is writing {n} now, and {node} is {where}: one split has one writer, "
                     f"and nothing moves in it while it is written — this call started nothing; it may be made once the "
                     f"authoring has ended, " + (f"`auto_decompose(writing=\"{h}\")` answering it then and `gfso wait` "
                                                 f"waking on it" if h else "`next_steps` naming it in flight meanwhile")}


def _alone_on_its_subtree(fn):
    """ONE AUTHORING PER SUBTREE, at the authoring's own entry, so every path to it is held: a request, a refine, a plan
    file's go, the page, the system's own split. While one writes a node, another on it, above it or below it is refused
    — two writers on one split killed the authoring (gb-coreutils-tnq7tv040, 2026-10-30). A read by handle writes
    nothing; a writing its door's call claimed for it keeps that claim (`Authorings.writing`)."""
    sig = inspect.signature(fn)

    @functools.wraps(fn)
    def _call(*a, **kw):
        at = sig.bind_partial(*a, **kw).arguments
        engine, node = at["engine"], str(at.get("root_id") or ROOT_ID)
        if at.get("writing") or engine.authorings.mine(node):
            return fn(*a, **kw)
        if (other := engine.authorings.take(node)) is not None:
            return _refused_while_written(engine, node, other)
        with engine.authorings.writing(node):
            return fn(*a, **kw)
    return _call


@_alone_on_its_subtree
def auto_decompose(engine: Engine, request: str = "", root_id: str = ROOT_ID,
                   assignee: Optional[str] = None, executor: Optional[str] = None,
                   depth: int = 1, model: Optional[str] = None, fast: bool = False,
                   max_iterations: Optional[int] = None, spec: Optional[dict] = None,
                   _progress=None, author: Optional[str] = None, open_plan: bool = False,
                   plan: Optional[str] = None, _contact: str = "", user_said: str = "",
                   writing: Optional[str] = None) -> dict:
    """THE one decomposition verb — dispatched by the target's state (one operation over graph state):
    (a) empty project / undecomposed node → authors a real GFSO subtree from `request` (the root node
    itself is created from the request — no hand create_task needed), builds INTO the live CORE through
    the FSM, VERIFIES (list_holes + bounded repair — honest `holes` residue, never a silent partial),
    then applies depth−1 refine rounds; (b) an ALREADY-decomposed node → `depth` REFINE rounds over what
    exists ("+1 iteration": search over the graph's real projection → fold genuinely new findings →
    rebuild as a verified revision; existing children keep their Del and their own ACCEPTED_RISKS/scope;
    `request` may be omitted — the node's own contract is the request). Recursion = the same verb on a
    child (root_id=<child>). The target node's criteria are re-authored to the derived V-set (name/description
    preserved) unless `author` — pinned to you on the MCP door, the node's Del when the system splits as its
    executor — is not its issuer; then the split maps onto them as issued (Inv-1). No author named: re-authored.
    `fast=true` on SIMPLE tasks: measured pace-suffixes, ~1.5× faster / ~40% fewer tokens with the same
    structural shape. Prefer this over reasoning the graph node-by-node — that under-covers and burns
    tokens.

    **`assignee` names the Del of the ROOT, and therefore the ISSUER of every child** (the issuer of
    a node is its parent's Del, §10.1). Passing an executor's id here hands them the whole graph:
    your own `edit_criteria`, `map_criterion` and PASS/FAIL on the children are then refused,
    because you are not their issuer. Measured 2026-08-21 — a caller delegated by passing the
    executor here and spent fifteen minutes locked out of their own plan before `reassign`ing the
    root back. To build a graph someone else owns end to end, this is the parameter for it.

    **`executor` is the other thing you probably meant: the Del of the CHILDREN.** The root stays
    with you — you keep your issuer rights over the whole plan — and the work goes to them, which is
    what "delegate it to X" means everywhere else. Both may be passed; they answer different
    questions (whose the goal is, whose the work is).

    `spec` builds a plan already authored — the shape `extract_spec` reads off a graph — as it
    stands, with no search: the way to execute ONE plan twice and compare the executions. A plan handed in is the
    user's (append-only, never re-split; refuted at contact, the run stops for the user); `open_plan=true` hands it in
    as a DRAFT the system may repair and re-split like its own — the run that polishes a plan, whose final graph
    `export_plan` then reads back as the plan to hand in closed.

    `plan` is THE GO on a plan file (`plan` / `refine_plan`, a path or the text): the project is built from the goal
    and the plan the file holds, exactly or refused; from then on contact may repair it, for the system wrote it. Under
    `solo` and `semi` the go is the person's: `user_said`, their own words agreeing to the plan they were shown.
    One authoring per subtree: while one writes a node, one on it, above it or below it is refused, and every move in
    the subtree it writes waits for it to end (`being_rewritten`).

    At a door an authoring from a request, or a refine, is written in a thread of the server's as a plan is (`_once`):
    the call answers within a few seconds — a refusal or a short run as itself, past that `{writing: <handle>}` —, the
    graph it builds is read by `get_graph` as it stands, and its whole answer by `auto_decompose(writing=<handle>)` once
    it ends; `gfso wait` wakes on it. The go on a plan file runs no model and answers in its call."""
    if writing:
        return _by_handle(writing, engine.project_name)
    if (yours := _a_new_roots_go(engine, root_id, request, plan, spec, model, user_said)) is not None:
        return yours
    if (unjudged := _no_place_at_the_go(engine)) is not None:
        return unjudged
    request, spec = (_the_go(engine, plan, request, spec, root_id) if plan is not None
                     else (request, _no_deferral_nobody_makes(spec, open_plan or mode_kind(engine.graph) != Mode.AUTO)))
    given, model = request, model or engine.planner_model()
    _cb = emit_cb(engine, "decompose", _progress)
    # …and SAY it, once, at the moment it happens: naming someone else here makes them the issuer of
    # every child, which is the opposite of what "delegate the work" usually means to the caller.
    if assignee and assignee != caller_id() and not executor:
        # …and ONLY when they have not already done the other thing. The remedy also interpolated
        # the CALLER's own id ("pass executor=<you>"), which is not the delegation anyone means, and
        # it printed one line before the message saying the children HAD been delegated (measured on
        # the human door 2026-08-22: "the remedy interpolates the wrong variable, and it contradicts
        # the very next line").
        _cb(f"{root_id}: Del={assignee} — that makes {assignee} the ISSUER of every child (§10.1: "
            f"the issuer is the parent's Del), so `edit_criteria` / `map_criterion` / PASS on them "
            f"belong to {assignee} and not to you. To delegate the WORK instead, leave the root with "
            f"you and pass `executor=<the executor's id>`: the children go to them, and the root — "
            f"with the issuer rights over the plan — stays yours.")
    if executor:
        _cb(f"{root_id}: the children are delegated to {executor}; the root stays with "
            f"{assignee or caller_id()}, who issues them.")
    assignee, executor, author = _held_as_the_mode_says(engine, root_id, assignee, executor, author)
    if fresh := engine.graph.get_task(TaskId(root_id)) is None:
        # the place is read for the plan's author; a plan handed in (`spec`) has none
        found = "" if spec is not None else _work_place_documents(engine, request, model)
        # …a plan file's goal already carries the documents it names (`plan`)
        request = (request or "") + ("" if plan is not None else _named_documents(engine, f"{request} {found}"))
    planner = _decompose.default_llm(model, execution=execution_of(engine))   # the one door to the plan's transport
    try:
        res = decompose_into(engine, request, root_id=root_id, assignee=assignee or caller_id(),
                             child_assignee=executor, llm=planner,
                             depth=depth, model=model, fast=fast, progress=_cb,
                             # A term of the CONTRACT, chosen per decomposition: how many
                             # rework rounds a node gets before the loop settles (§12.15).
                             max_iterations=max_iterations, spec=spec, author=author,
                             closed=spec is not None and not open_plan, contact=_contact,
                             # WHICH EXECUTOR ONE SESSION IS: the fact the decomposer judges each piece's fit
                             # against, so the seams move with the model rather than with a number we set
                             # …the session that DOES the parts: the user-agent's hands where it dispatches (critic:
                             # under solo/semi-dispatch both doors judged against nobody)
                             executor=engine.workforce.executor_session(hands_of(engine.graph, executor or assignee)
                                                                        or executor or assignee),
                             # …a root's, on every route of its go — a plan file, a spec, a request — and every go again
                             system_root=lambda s: with_the_intent(engine, s, root_id))
    except NoPlan as no:            # no root built: what was spent is still on the record
        return {"root_id": None, "subtasks": [], "holes": [], "stats": no.stats, "error": _no_plan(no)}
    finally:
        # …on every path: a build that raised took its calls with it, and a row's ledger showed no plan at all
        # while the plan's author and auditors had spent $0.56 (GB_sql_database_tmu9cb784)
        engine.record_llm_usage(Stage.DECOMPOSER, planner, TaskId(root_id))
    kids = engine.graph.get_active_children(res.root_id)
    # …A PLAN BEING POLISHED IS NOT YET THE USER'S: `open_plan` hands the spec in as a draft the system may repair and
    # re-split on contact, so its final graph (export_plan) shows what the plan needed — the author, 2026-10-25: «пока
    # план полируется оставлять открытым возможность менять, потом смотреть что менялось и фиксировать итог»
    if spec is not None and not open_plan and plan is None:
        engine.give_users_plan(res.root_id)
    out = {"root_id": str(res.root_id),
           "subtasks": [{"id": str(c.id), "description": c.spec.description} for c in kids],
           "holes": res.holes,
           "stats": res.stats,
           "projection": res.d_md}  # the built root's projection markdown — the one canonical read
    # WHAT AN EMPTY `holes` DOES NOT MEAN. It answers the STRUCTURAL checks and nothing else, and a
    # caller who read it as "the plan is clean" walked into a twelve-finding gate with eight
    # obligations this same reply had already named in prose (HTTP door, wave 27, 2026-09-06: "two
    # fields of the same reply disagree about whether the plan is ready"). The obligations ride as
    # DATA now, and the note is attached whether or not the structural list is empty.
    if res.undecided_obligations:
        out["undecided_obligations"] = list(res.undecided_obligations)
    if res.holes:
        # TWO SURFACES, ONE WORD, DIFFERENT SETS. This residue is everything structurally wrong —
        # unplaced spec items and refuted seams as well as unmet checks — while `list_holes` returns
        # the unmet CHECKS alone. A reader who called it next was told the graph was clean about the
        # very residue printed a moment earlier, and read one of the two as broken (measured on the
        # human door 2026-08-22). Which set is which, said where the difference shows.
        _checks = {f"{h['task_id']} / {h['check']}" for h in engine.graph_holes(res.root_id)}
        out["holes_note"] = (
            f"{len(res.holes)} residual problem(s): unmet structural checks AND spec items no node "
            f"carries AND seams contact refuted. `list_holes` shows the {len(_checks)} unmet CHECK(s) "
            f"only — an empty `list_holes` does NOT mean this list is empty.")
    else:
        out["holes_note"] = (
            f"no residual STRUCTURAL problem (L0/L1). That is not a verdict on the plan: "
            + (_what_the_gate_does(engine, res.root_id, kids, len(res.undecided_obligations))
               if res.undecided_obligations else
               f"whether the criteria DECIDE the goal is the Level-2 question, and "
               f"`review_decomposition('{res.root_id}')` is what answers it."))
    if res.note:
        out["note"] = res.note     # e.g. refine over a decomposed node IGNORED the request text
    # No children AND not one completed model call: the provider never answered — unreachable, or
    # unauthenticated. The LLM ports return "" / {} on transport failure by contract, so this arrived
    # as a clean, confident, "verified" empty decomposition — which reads as a statement about the
    # GOAL ("nothing to split") rather than about the installation. It is what a fresh install
    # without credentials hits, on the one verb it is told to start with.
    out.update(_no_provider_answer(out["subtasks"], res.stats, spec))
    out.update(_built_from_a_file(engine, plan, spec, res.root_id, user_said))
    return {**out, **_heard_at_the_go(engine, given, user_said, res.root_id, fresh)}


def _held_as_the_mode_says(engine: Engine, root_id: str, assignee: Optional[str], executor: Optional[str],
                           author: Optional[str]) -> tuple:
    """(the root's Del, its children's, the split's author) as the mode over `root_id` decides them — as given with none.

    UNDER A MODE the mode decides both answers, and a name that contradicts it is refused (`del_by_mode`): the knob is
    the user's choice of who holds what, not a default a habitual argument re-decides. The root keeps its creator as the
    goal's issuer (`Graph.issuer_of`). In a mode scope the node stands, its children are the scope's holder's, and every
    go there is the holder's own split: at the scope's top it maps onto the contract its issuer formed and re-authors
    none (`held_contract`) — that contract is the person's, and moves only by his revision (§10.1)."""
    if (scope := engine.scope_at(root_id)) is not None:
        assignee = str(engine.graph.get_task(TaskId(root_id)).assignee)
        return (assignee, _childrens_executor(engine, root_id, assignee, executor, scope["holder"]),
                author or scope["holder"])
    if engine.mode() is None:
        return assignee, executor, author
    _root = engine.graph.get_task(TaskId(root_id))
    if _root is None:
        _want = engine.del_at(0, None)
        assignee = str(_tools.del_by_mode(engine, None, assignee)) if assignee else str(_want)
        engine.record_root_issuer(TaskId(root_id), AgentId(caller_id()))
    else:
        assignee = str(_root.assignee)
    return assignee, _childrens_executor(engine, root_id, assignee, executor,
                                         engine.del_at(depth_of(engine.graph, TaskId(root_id)) + 1 if _root else 1,
                                                       AgentId(assignee))), author


def _built_from_a_file(engine: Engine, plan: Optional[str], spec: dict, root_id, user_said: str) -> dict:
    """What the go on a plan file adds once built: the gate off under it where the system's own review ran over it
    (never for the project's other goals: one go turned it off for every goal of a shared graph); the person's words,
    recorded on the feed; its checks run once over the base, each that cannot run or already holds there said, never a
    gate (`PinsOnTheBase`), or that none ran; and, to a chat performing the work itself, where it goes on."""
    if plan is None:
        return {}
    out, said = ({"open_at_the_go": left} if (left := open_at_the_go(plan)) else {}), str(user_said).strip()
    if reviewed(plan):
        engine.reviewed_in_its_file(root_id)
    if spec:
        pins = _decompose.PinsOnTheBase(execution_of(engine)).review(spec)
        # …on this host bash only read them (`PinsOnTheBase.here`): what it refused stands, none ran
        if "run" not in pins:
            pins = {**pins, "not_run": [*(pins["not_run"] if "parsed" in pins else ()),
                                        "the checks were not run over the base: this project's work runs on this host, "
                                        "where the system runs no check before the work — read each yourself: one that "
                                        "already holds on the base decides nothing"]}
        out[_planning.PINS] = pins
    if said:
        engine.emit_info("go", f"the go on the plan file, by the person: «{said[:300]}»")
        out["user_said"] = said
    # …the plan agreed, kept with the goal for its reading against the person's words — its template's comments are
    # the system's instructions to the agent, not the agreement
    engine.hear(root_id, "plan", "\n".join(x for x in _planning.text_of(plan).splitlines()
                                           if not x.lstrip().startswith("#")))
    if holds_its_work(engine, root_id):
        # …THE PERSON'S READING IS THIS PLAN'S OWN READING: its decomposer is their own agent, they read it and gave the go in
        # their words; the Level-2 gate stands for the system's own plans, and held the parts on an unannounced review
        # by the system's model (critic over 354554c)
        engine.reviewed_in_its_file(root_id)
        engine.emit_info("go", f"{root_id}: the plan's review is the person's own, given with the go")
        place = validator_workdir(engine, default_agents(), TaskId(str(root_id)))
        theirs = on_their_branch(engine, place) if place and switches_branches(engine, root_id) else ""
        if place and W.is_repo_top(place):
            engine.graph.store_setting(f"{past.CHAT_START}{root_id}", json.dumps({
                "branch": W.git(place, "symbolic-ref", "-q", "--short", "HEAD").stdout.strip(),
                "head": W.git(place, "rev-parse", "--verify", "-q", "HEAD^{commit}").stdout.strip()}))
        parts = [str(c.id) for c in engine.graph.get_active_children(TaskId(str(root_id)))]
        out["say"] = (theirs + ". " if theirs else "") + (
            (f"The split maps onto {root_id}'s contract as its issuer, the person, set it — none of it re-authored; "
             f"it changes only by his revision from his page. Do the work " if maps_onto_its_contract(engine, root_id)
             else "The checks the person agreed are the contract now, fixed in the graph before the work. Do the work ")
            + (f"yourself on the branch `{work_branch(engine)}` and commit; " if switches_branches(engine, root_id) else
               "yourself where you work, and commit there — the checkout is shared, so no branch is switched; ")
            + (f"take each part ({', '.join(parts)}) in turn — ACCEPT it, do it, DELIVER it with your self-check, and "
               f"PASS it yourself: below the root it is yours (`validate_result` has it checked when you want, "
               f"`set_checker` gives it to the validator on the person's words, you signing either way) — and DELIVER `{root_id}` once every part "
               f"has passed" if parts else f"DELIVER `{root_id}`")
            + f" (`signal`, your self-check in `result`)"
            + (f"; a validator other than you observes `{root_id}` against its checks and the parts' own, by itself."
               if engine.observes_by_itself(TaskId(str(root_id))) else
               f"; `{root_id}` is yours to PASS too, the validator observing the scope's top above it."))
        # …and the move itself, as every move's reply carries it: the go's alone had none, and a fresh client asked
        # `next_step` before its DELIVER to learn it (s23g4)
        out.update(_tools.next_for(engine, caller_id()))
    return out


def _no_place_at_the_go(engine: Engine) -> Optional[dict]:
    """The go refused where a role of the project works in a directory no delivery from it could be judged by
    (`unjudged`): never sessions paid for with no verdict possible. None: the go goes on."""
    if got := unjudged(engine, default_agents()):
        return {"refused": True, "error": "the go is refused: " + "; ".join(
            f"{aid} works in a directory no delivery is judged in — {why}" for aid, why in got)}
    return None


def _a_new_roots_go(engine: Engine, root_id: str, request: str, plan, spec, model, user_said: str) -> Optional[dict]:
    """The one gate every new root's go passes, by any route (a plan file, a spec, a request): where the person's own
    agent holds the work in its chat (`holds_its_work`), a request with no model named is answered with the plan file to
    fill and no model called (`yours_to_write`); under `solo` and `semi` the go is refused without the person's words —
    told "write to the person now, before any other call", a fresh client summarized the plan in the same turn as its
    go, and the person never saw it before the work (s20g1). Their words are recorded on the feed, for the person to see;
    whether they are theirs, nothing here can tell. None: the go goes on."""
    if engine.graph.get_task(TaskId(root_id)) is not None:
        return None
    if plan is None and spec is None and model is None and holds_its_work(engine, root_id) and str(request or "").strip():
        engine.hear(root_id, "request", request)
        return yours_to_write(engine, request)
    if mode_kind(engine.graph) in (Mode.SOLO, Mode.SEMI) and not str(user_said).strip():
        raise ValueError("auto_decompose: under solo and semi the go is the person's — show them the plan's criteria "
                         "and checks, end your turn, and give the go with their own words agreeing to it as "
                         "`user_said`, recorded on the project's feed")
    return None


REASSIGN, persons_move = _tools.REASSIGN, _tools.persons_move


def _the_persons_move(engine: Engine, tid, sig: str) -> Optional[dict]:
    """An issuer's move on a node whose issuer is the person (`Engine.issued_by_the_person`) is theirs (§10.2), so from
    an agent's connection it carries their words, recorded on the feed; refused without them, nothing written (§12.16
    (ii)). A client signing the root itself was stopped as self-approval (s21); one that put "which line ending?" to
    them by a CHALLENGE answered it with REJECT_CHALLENGE in their name (critic, in-process). A re-ASSIGN is theirs once
    the root is ESCALATED, their decision (§12.5); elsewhere its packet is asked by the engine (`_the_persons_packet`).
    A reassign is theirs in every state: it re-issues the root with its packet unchanged, which that gate never sees.
    None: the move goes on."""
    if not persons_move(engine, tid, sig):
        return None
    if (p := CALLER.get()) is not None and p.a_page:
        return None                     # …the person's own page making it: the move itself is their word
    verdict = sig in (Verdict.PASS.value, Verdict.FAIL.value)
    if not (said := PERSONS_WORDS.get().strip()):
        return {"accepted": False, "refused": True,
                "error": f"{tid}'s {sig} is the person's: show them the validator's verdict on each criterion "
                         f"(`get_verdict('{tid}')`), ask them, and sign with their own words as `user_said`" if verdict
                         else f"{tid}'s {sig} is the person's — its issuer is them (§10.1), and you would be answering "
                              f"for them: show them the question, ask them, and send their own words as `user_said`, "
                              f"or they make it on their page. Nothing was written"}
    act = "verdict" if verdict else "answer"
    engine.emit_info(act, f"{tid}: {sig} on the person's words: «{said[:300]}»")
    engine.hear(tid, act, said)
    return None


def _heard_at_the_go(engine: Engine, goal: str, user_said: str, root_id, fresh: bool) -> dict:
    """Every go's words kept over its root (`Engine.hear`) — a second go's too (critic over 677b376) — and, at a new
    root's go, what the person must hear (`recorded_at_the_go`). None in a mode scope: a go there is its holder's own
    split, and words heard with it would be quoted as the person's (`persons_words`)."""
    if engine.scope_at(root_id) is None:
        engine.hear(root_id, "go", user_said)
    return recorded_at_the_go(engine, goal, user_said, root_id) if fresh else {}


def recorded_at_the_go(engine: Engine, goal: str, user_said: str = "", root_id=ROOT_ID) -> dict:
    """What the person must hear at the go, as the graph read says it too: what of their repository the agents' copy lacks
    and the goal as given, verbatim, derived once and recorded with the project (`tools.at_the_go`); whether its work runs
    on this machine, by the one reading of the roster as published (`Workforce.runs_on_host`)."""
    said = {"not_imported": [], **_not_imported(engine), "goal_as_given": goal,
            **({"user_said": str(user_said).strip()} if str(user_said).strip() else {})}
    _tools.record_at_the_go(engine, root_id, said)
    return {"runs_on_host": engine.workforce.runs_on_host(), **said}


#: {the call's arguments: its writing} — a plan in flight, written for minutes in a thread of the server's while its call
#: answers at once: a call held that long held its client's turn, and the person with it. What it came to is kept on
#: disk (`decompose.kept`): the plan each project waits on, and every written answer by its handle.
_PLANNING: dict = {}
_PLANNING_LOCK = threading.Lock()


def _handle_of(key: tuple) -> str:
    return f"{key[0]}-{hashlib.sha1(repr(key).encode()).hexdigest()[:10]}"


class _Writing:
    """One plan being written: its handle and its answer to come."""

    def __init__(self, key: tuple):
        self.handle, self.answer = _handle_of(key), Future()


def _once(key: tuple, write, engine=None) -> dict:
    """One writing of `write()` per `key` (`key[0]` the verb, `key[1]` the project), in a thread of the server's: a call
    while it runs answers `{writing: <handle>}`, one after it — or the verb with `writing=<handle>` — the written answer.
    A new plan asked for is the one its project waits on. An error is answered once and written again when asked again.
    On the CLI's direct path the writing is done in the call: no thread would outlive its process."""
    if _config_written_in_the_call.get():
        return answering(write)()
    handle, project = _handle_of(key), key[1]
    with _PLANNING_LOCK:
        _kept.sweep()
        if key not in _PLANNING and (out := _kept.answer(handle)) is not None:
            _kept.mark(project, handle, read=True)
            return dict(out)
        # …and a writing started anew is the record's anew, same handle or not: a re-ask after its failure or restart was
        # read kept `read` and the old error, and the plan written again was listed to no one (critic)
        if _kept.record(project, handle) is None or key not in _PLANNING:
            _kept.open_writing(project, handle, _slot(key))
        if started := key not in _PLANNING:
            w = _PLANNING[key] = _Writing(key)
            threading.Thread(target=contextvars.copy_context().run, args=(_written_in_its_thread, key, w, write, engine),
                             daemon=True, name=f"gfso-{key[0]}").start()
        return _answer_of(key, started)


def _slot(key: tuple) -> str:
    """What a writing supersedes when asked anew: the project's plan (`plan`, `refine_plan`), an authoring its node's."""
    return f"{key[0]}:{key[2]}" if key[0] == "auto_decompose" else "plan"


def _ends(project, handles) -> dict:
    """{handle: its state} of each writing of `handles` `project` waits on, a writing the server lost read `failed`."""
    with _PLANNING_LOCK:
        live, recs = {w.handle for w in _PLANNING.values()}, _kept.records(project)
    return {h: "failed" if r.get("state") == "writing" and h not in live else r.get("state")
            for h in handles if (r := recs.get(h))}


def _answer_of(key: tuple, started: bool = False) -> dict:
    """What a writing in memory answers now (called under `_PLANNING_LOCK`): `{writing}` while it runs, else its error,
    answered once."""
    w = _PLANNING[key]
    if not w.answer.done():
        return _being_written(w.handle, key[1], started)
    del _PLANNING[key]
    _kept.mark(key[1], w.handle, read=True)
    return dict(w.answer.result())


def _by_handle(handle: str, project, read: bool = True) -> dict:
    """The writing `handle` names, answered as its own call again would be: no second writing, whatever drifted. Not
    `read`: as it stands, marked as read by no one (a wait carrying it)."""
    with _PLANNING_LOCK:
        if (key := next((k for k, w in _PLANNING.items() if w.handle == handle), None)) is not None:
            w = _PLANNING[key]
            return _answer_of(key) if read or not w.answer.done() else dict(w.answer.result())
        if (out := _kept.answer(handle)) is not None:
            if read:
                _kept.mark(project, handle, read=True)
            return dict(out)
        rec = _kept.record(project, handle)
        if rec and rec.get("state") in ("failed", "writing"):
            if read:
                _kept.mark(project, handle, read=True)
            return {"refused": True, "error": rec.get("error") or "its writing was lost when the server restarted: "
                                                                   "ask for it anew"}
        return {"refused": True, "error": f"no plan is being written or kept as {handle!r}: one is kept until read, "
                                          f"and {_kept.KEPT_S // 60} minutes after; ask for it anew"}


def said_a_plan(project, out: dict) -> None:
    """A reply carried `out` (`next_steps`) to the one who asked: the plan written or failed in it is said."""
    plans = out.get("plans") or {}
    for h in (plans.get("written") or []) + (plans.get("failed") or []):
        told(project, h)


def told(project, handle) -> None:
    """The plan `project` waits on has been said — a wait ended on it, or a chat's reply carried it: it ends no later
    wait and stays listed until read."""
    with _PLANNING_LOCK:
        _kept.mark(project, handle, told=True)


def _written_in_its_thread(key: tuple, w: _Writing, write, engine) -> None:
    """Write one plan, marked in flight under its project (`engine`; none: `write` marks itself), so a reconcile from
    another session does not restart under it; what it came to is kept: the answer by its handle, and the state of the
    plan its project waits on."""
    with flight(key[0], engine, ROOT_ID) if engine is not None else nullcontext():
        out = answering(write)()
    with _PLANNING_LOCK:
        if "error" in out:
            _kept.mark(key[1], w.handle, state="failed", error=str(out["error"])[:2000])
        else:
            _kept.keep_answer(key[1], w.handle, out)
            _kept.mark(key[1], w.handle, state="written")     # …or let go, its project waiting on another now
            _PLANNING.pop(key, None)
    w.answer.set_result(out)


#: how long a writing takes, by its verb, as its answer says it
_HOW_LONG = {"plan": "about 3–8 minutes on a small task", "refine_plan": "2–3 minutes",
             "auto_decompose": "minutes; its subtree is held meanwhile"}


def _being_written(handle: str, project, started: bool) -> dict:
    """The answer while a plan is written: the facts of its writing, and how its agent learns it is written."""
    verb = handle.rsplit("-", 1)[0]
    return {"writing": handle, "started": started,
            "say": (f"The plan is being written ({_HOW_LONG.get(verb, 'minutes')}"
                    f"): `{verb}(writing=\"{handle}\")` answers it once written, and `next_steps` names it under "
                    f"`plans`. " + how_it_is_waited(project, "it is written"))}


def plans_of(project) -> dict:
    """The writings `project` waits on, as `next_steps` names them: `writing`; `written` or `failed`, not yet said (either
    ends a wait); `unread`, said and not read. A writing the server lost at a restart is `failed`."""
    out: dict = {}
    with _PLANNING_LOCK:
        live = {w.handle for w in _PLANNING.values()}
        for h, rec in _kept.records(project).items():
            if rec.get("read") or rec.get("state") == _kept.SUPERSEDED:
                continue
            state = rec.get("state") if rec.get("state") != "writing" or h in live else "failed"
            out.setdefault("writing" if state == "writing" else "unread" if rec.get("told") else state, []).append(h)
    return {"plans": out} if out else {}


def plan(engine: Engine, request: str = "", model: Optional[str] = None, executor: Optional[str] = None,
         depth: int = 1, review_model: Optional[str] = None, writing: Optional[str] = None,
         plan: Optional[str] = None, root_id: str = ROOT_ID) -> dict:
    """Author a plan for `request` WITHOUT a project: the plan file (`.gfso`) — the goal, the split with its criteria,
    pinned checks, mappings, dependencies and register, the Level-2 review over it — for the customer to read whole.
    Nothing executes and no project is made. Answers at once: `{writing}` while it is written (about 3–8 minutes on a small
    task), and `plan(writing=<handle>)` (or the same call again), once written, holds the file's whole `text` beside its
    `path`, unless it is longer than PLAN_TEXT_MAX characters. Send a note with `refine_plan`; give the go with
    `auto_decompose(plan=<path>)`, which builds the project from the file as it stands. `executor` names the registered
    executor whose session the fit of each part is judged against. `plan` hands in a file written elsewhere — the one a
    chat holding its own work filled with the person — to be shown before the go, as a file the system writes is:
    no model is called. `root_id`: the node the go will build under — in a mode scope, the node the person asks on."""
    if writing:
        return _by_handle(writing, engine.project_name)
    if plan is not None:
        return handed_in(engine, plan, root_id)
    if not str(request or "").strip():
        return {"refused": True, "error": "plan needs the request, or `writing=<handle>` to read one being written"}
    # …the person's request as they asked it, quotable whatever the plan's `goal` comes to say: the file is the agent's —
    # never in a mode scope, where the request is its holder's, not the person's
    if engine.scope_at(root_id) is None:
        engine.hear(root_id, "request", request)
    if model is None and holds_its_work(engine, root_id):
        return yours_to_write(engine, request, root_id)
    model = model or engine.planner_model()
    # …the fit judged against WHO WILL DO the parts (§3.7: a leaf is within its holder's κ) — under a mode, the executor
    # the go hands the root's children to, as `auto_decompose` defaults it. Unnamed, the planner judged against an
    # unknown agent, and the user's path (`plan(request)`) got a plan placed for a session it would not run in (critic)
    if (scope := engine.scope_at(root_id)) is not None:
        executor = _childrens_executor(engine, root_id, scope["holder"], executor, scope["holder"])
    elif engine.mode() is not None:
        try:
            root = engine.del_at(0, None)
            kid = engine.del_at(1, root)
        except ValueError:          # no executor the mode could hand the parts to: the go refuses that, not the plan
            root = kid = None
        if kid is not None:
            # …ONE RULE WITH THE GO: a name the go would refuse is refused here, or the plan is placed for one session
            # and its parts run in another (critic)
            executor = _childrens_executor(engine, ROOT_ID, str(root), executor, kid)
    if executor:
        # …held by the user-agent, its parts run in its hands' session where it dispatches, as the go judges
        executor = hands_of(engine.graph, executor) or (None if str(executor) == caller_id() else executor)
    # …the goal as the project's root will hold it — with the documents it names written under it, as the go would add
    # them — so the plan and its review are written against the contract the work will run on (critic)
    docs = _documents_named(engine, request or "")
    request = (request or "") + _under_the_goal(docs)
    # …kept apart by the goal they were written under: a document's own `## ` heading reads as a boundary in the text
    _kept.keep_documents(request, docs)

    def write() -> dict:
        """The file written and kept, or why not."""
        try:
            text = _planning.author(request, model, engine.workforce.executor_session(executor) if executor else "",
                                    depth, review_model or engine.system_model(), emit_cb(engine, "plan"),
                                    execution=execution_of(engine), ledger=engine.record_llm_usage)
        except NoPlan as no:
            return {"error": _no_plan(no, "plan")}
        return _shown(engine, _plan_written(text), _artifact.parse(text)["spec"], root_id)
    return _once(("plan", engine.project_name, request, model, executor, depth, review_model or engine.system_model()),
                 write, engine)


def handed_in(engine: Engine, plan: str, root_id: str = ROOT_ID) -> dict:
    """A plan file handed in before the go (`plan(plan=)`): kept as the project's written plan, so its page shows it as it
    shows one the system wrote (`written_plan`: its parts, what the go would refuse), and told on its feed — the file a
    solo chat filled reached the system only at its go, and the person's page showed nothing before (ui). No model."""
    text = _planning.text_of(plan)
    try:
        p = _artifact.parse(text)
    except ValueError as e:
        return {"refused": True, "error": f"the plan file does not read: {e}"}
    refused = [*((off,) if (off := off_its_contract(engine, p["spec"], root_id)) else ()),
               *_decompose.go_refusals(with_the_intent(engine, p["spec"], root_id), p["goal"])]
    out = {"path": str(_planning.kept(text)), "chars": len(text), "parts": [s["id"] for s in p["spec"].get("subtasks") or ()],
           "refused_by_the_go": refused,
           "say": ("The go refuses this file as it stands: repair the points of refused_by_the_go in it and hand it in "
                   "again." if refused else
                   "It is on the person's page now. Show them its criteria and checks too; their own words agreeing "
                   "give the go: `auto_decompose(plan=path, user_said=<their words>)`.")}
    return _shown(engine, out, p["spec"], root_id)


def holds_its_work(engine: Engine, node=None) -> bool:
    """Does the person's own agent hold and perform this project's work in its chat — `solo`, `in_chat`? Then the plan's
    content is its own, written with the person (§4.5: a split's content is its author's; §11.5: its executor may author
    it in performing it), and the system's planner is not asked: on a fresh solo run it wrote for 10 of 18 minutes,
    turning 3 asked requirements into 9 criteria and a suite nobody asked for (s20g1). On `node`, the mode it lies under
    (`mode_at`): a stream holding its scope solo in_chat holds its work so."""
    rec = engine.mode_at(node) or {}
    return rec.get("mode") == Mode.SOLO and rec.get("perform") == "in_chat"


#: The root criterion the system adds at the go (`with_the_intent`) — its text the system's, never the plan template's,
#: where the agent writing the plan could rewrite it; the person's own clarifications go into it by `edit_criteria`.
INTENT_CRITERION = {
    "name": INTENT,
    "description": "The result answers what the person asked, as their recorded words state it — the goal as given, "
                   "their words at the go and on later acts, the agreed plan — including what the written criteria do "
                   "not carry. A miss of their words is this criterion's fail, quoting them.",
    "check": [{"behaviour": "the delivered work, read against the person's recorded words",
               "command": "git log --stat -n 20 --format='%h %s'",
               "expect": "work that answers each thing the person's recorded words ask, nothing of theirs left out",
               "exact": False}]}


def intent_check(engine: Engine) -> bool:
    """Does the go of a plan add `answers_the_persons_words`? The engine's one reading (`Engine.intent_check`)."""
    return engine.intent_check()


def with_the_intent(engine: Engine, spec: dict, root_id: str = ROOT_ID) -> dict:
    """`spec` as a go on `root_id` writes it: where `intent_check` holds and `root_id` is a goal's root, with the root
    criterion `answers_the_persons_words` mapped to every part — the aggregate's joint responsibility, read at the root's
    own contact (§3.5); the parts get no copy. A criterion of the plan under that name is replaced: written by the agent
    the criterion reads, it was admitted as "always holds" over `git log -1` (critic over de23af3). Its text is the
    system's, or — on a root that stands — the root's own where a revision on the person's words installed it (`hear`'s
    `intent`): a second go dropped it, or would reset what they said they meant (critic over deb1158); a text the plan's
    agent wrote while the switch was off does not stand (critic over 677b376). The one reading every root door builds
    by and the plan's answer says (`added_at_the_go`). A mode scope's top stands for the root (`goal_top`); below it every
    node is the holder's own."""
    root = engine.graph.get_task(TaskId(str(root_id)))
    if not engine.intent_check(node=root_id) or not engine.goal_top(root_id):
        return spec
    theirs = {_decompose.criterion_key(h["intent"]) for h in heard_on(engine.graph, root_id) if h.get("intent")}
    mine = next(({"name": c.name, "description": c.description, "check": [p.to_dict() for p in c.check]}
                 for c in (root.spec.criteria if root else ())
                 if c.name == INTENT and _decompose.criterion_key(c) in theirs), INTENT_CRITERION)
    kids = [str(k["id"]) for k in spec.get("subtasks") or ()]
    return {**spec, "root_criteria": [*(c for c in spec.get("root_criteria") or () if c.get("name") != INTENT),
                                      json.loads(json.dumps(mine))],
            **({"mappings": [*(m for m in spec.get("mappings") or () if m.get("criterion") != INTENT),
                             *({"criterion": INTENT, "child_id": k} for k in kids)]} if kids else {})}


def added_at_the_go(engine: Engine, spec: dict, root_id: str = ROOT_ID) -> list[dict]:
    """The root criteria the go on `root_id` writes that the plan `spec` does not carry as they are (`with_the_intent`);
    none at a contract given, which the go maps onto as issued (`maps_onto_its_contract`)."""
    if maps_onto_its_contract(engine, root_id):
        return []
    return [c for c in with_the_intent(engine, spec, root_id).get("root_criteria") or ()
            if c not in (spec.get("root_criteria") or ())]


#: the plan file a scope's holder fills at its top (`yours_to_write`): the contract its issuer set, and the parts to add
YOURS_ONTO = """format = "gfso-plan/1"
goal = {goal}

[plan]
name = ""

# {node}'s contract as its issuer, the person, set it: the split maps onto these criteria and re-authors none — keep
# them as they stand; they change only by his revision from his page.
{criteria}
# Parts ([[plan.subtasks]], with [[plan.mappings]] onto the criteria above and accepted_risks):
# https://github.com/Kirill-Shokhin/GFSO/blob/main/docs/PLAN_FORMAT.md
"""

#: the plan file a solo in_chat agent fills with the person: every field left empty is refused by the go's reading (`form`)
YOURS = """format = "gfso-plan/1"
goal = {goal}

[plan]
name = ""

# One criterion per thing the person asked for, in their words; nothing they did not ask. Each carries a check fixed
# now: a command someone else can run on the result and what it must print. exact = true: `expect` IS that output, its
# very text (spacing loose), compared by running it — never a description of it; false: described in words, judged by
# a reader. Where no command decides it, write `procedure = "…"` instead of command/expect/exact: the checker performs
# those words, the system never runs them. Copy the block for the next criterion.
[[plan.root_criteria]]
name = ""
description = ""

[[plan.root_criteria.check]]
behaviour = ""
command = ""
expect = ""
exact = true

# Parts ([[plan.subtasks]], with [[plan.mappings]] and accepted_risks) only where one session cannot carry the whole:
# https://github.com/Kirill-Shokhin/GFSO/blob/main/docs/PLAN_FORMAT.md
"""


def maps_onto_its_contract(engine: Engine, node) -> bool:
    """Does a go on `node` map onto a contract it was given — a mode scope's top, whose packet its issuer, the person,
    formed (§10.1)? Its holder's split there re-authors none of it (`held_contract`); it moves by his revision alone."""
    return engine.scope_at(node) is not None and engine.goal_top(node)


def its_contract(engine: Engine, node) -> list[dict]:
    """The root criteria a plan at `node` stands on where a go maps onto its contract — that contract as issued, checks
    and all, as `held_contract` builds on it; [] elsewhere."""
    t = engine.graph.get_task(TaskId(str(node))) if maps_onto_its_contract(engine, node) else None
    return [] if t is None else its_criteria(t)


def off_its_contract(engine: Engine, spec: dict, node) -> Optional[str]:
    """Why a plan at `node` cannot go as it stands where a go maps onto its contract — its root criteria other than that
    contract, which the go would map onto in their place: checked against one contract and gone on another — or None."""
    if not maps_onto_its_contract(engine, node):
        return None
    key = lambda cs: sorted((str(c.get("name")), _decompose.criterion_key(c)) for c in cs)
    if key(spec.get("root_criteria") or ()) == key(its_contract(engine, node)):
        return None
    return (f"{node}'s criteria are its issuer's contract — the person's — and a split at it maps onto them as issued: "
            f"the file's root criteria must be exactly them (`plan(request, root_id='{node}')` hands them); they change "
            f"only by the person's revision from his page")


def _criteria_text(crits: list[dict]) -> str:
    """Root criteria as a plan file writes them."""
    q = lambda v: json.dumps(str(v or ""), ensure_ascii=False)
    return "\n".join(f"[[plan.root_criteria]]\nname = {q(c['name'])}\ndescription = {q(c['description'])}\n"
                     + "".join(f"\n[[plan.root_criteria.check]]\nbehaviour = {q(p.get('behaviour'))}\ncommand = "
                               f"{q(p.get('command'))}\nexpect = {q(p.get('expect'))}\nexact = "
                               f"{'true' if p.get('exact') else 'false'}\n"
                               + (f"bound_s = {json.dumps(p['bound_s'])}\n" if p.get("bound_s") is not None else "")
                               + (f"procedure = {q(p['procedure'])}\n" if p.get("procedure") else "")
                               for p in c.get("check") or ())
                     for c in crits)


def yours_to_write(engine: Engine, request: str, node=ROOT_ID) -> dict:
    """The answer of `plan` where the person's own agent holds the work (`holds_its_work`): no model is called — the file
    to fill with the person, the goal in their words, and how its go goes. At a contract given (`maps_onto_its_contract`)
    the file's root criteria ARE that contract, and its holder adds the parts mapped onto them."""
    goal = json.dumps(str(request).strip(), ensure_ascii=False)
    if crits := its_contract(engine, node):
        return {"yours": True, "text": YOURS_ONTO.format(goal=goal, node=node, criteria=_criteria_text(crits)),
                "say": f"No model writes this plan, and its root criteria are {node}'s contract as its issuer, the "
                       f"person, set it: keep them as they stand, and add the parts that carry them, each mapped onto "
                       f"them. Hand it in, `plan(plan=<the text>, root_id='{node}')`, and give the go, "
                       f"`auto_decompose(plan=<its path>, root_id='{node}')`: the split is yours, no words of theirs "
                       f"owed. A change of those criteria is the person's revision, from his page."}
    return {"yours": True, "text": YOURS.format(goal=goal),
            "say": "No model writes this plan: you hold the work, so its criteria are yours, written with the person. "
                   "Fill `text`: each thing they asked for as a criterion with its check, nothing they did not ask; a "
                   "piece one session carries has no parts. Hand it in, `plan(plan=<the filled text>)`: it goes on "
                   "the person's page and says what the go would refuse. Show them the criteria and checks; their own "
                   "words agreeing give the go: `auto_decompose(plan=<its path>, user_said=<their words>)`. "
                   "The system then fixes those checks in the graph before any work, and a validator other than you "
                   "signs the root against them. `plan(request, model=...)` has the system write it instead."}


def refine_plan(engine: Engine, plan: str = "", note: str = "", model: Optional[str] = None,
                review_model: Optional[str] = None, writing: Optional[str] = None) -> dict:
    """The customer's note on a plan file (a path or the text), 2–3 minutes, on something about the person's result: one
    refine round with the note as its finding, by
    `model` (an older one may be named), and the review run again. The new file carries the note with its answer —
    what the round changed in the plan, read off the plan itself, and the answer holds it as `plan`'s does. The old file
    stays as it was; the call answers at once, as `plan`'s does, and `refine_plan(writing=<handle>)` reads it. A round
    its answer marks NOT ANSWERED — the review still finds open the root criterion the note named, or one the round
    added — spent no note: refine again with it."""
    if writing:
        return _by_handle(writing, engine.project_name)
    if not plan or not note:
        return {"refused": True, "error": "refine_plan needs the plan and the note, or `writing=<handle>` to read one"}
    if no := _answered(plan):
        return no
    model = model or engine.planner_model()

    def write() -> dict:
        """The refined file written and kept, or why not."""
        try:
            # …the review is the system's, on its model: a planner named stronger authors, it does not also review (critic)
            text = _planning.refine(_planning.text_of(plan), note, model, review_model or engine.system_model(),
                                    emit_cb(engine, "plan"),
                                    execution=execution_of(engine), ledger=engine.record_llm_usage)
        except NoPlan as no:
            return {"error": _no_plan(no, "refine_plan")}
        except (ValueError, OSError) as e:
            return {"error": str(e)}
        return _shown(engine, _plan_written(text), _artifact.parse(text)["spec"])
    return _once(("refine_plan", engine.project_name, plan, note, model, review_model or engine.system_model()), write,
                 engine)


def _answered(plan: str) -> Optional[dict]:
    """The refusal of a round over a file whose note is answered and whose go is not refused: three rounds of notes on a
    plan with nothing undecided took 8:28 of a 17-minute run and left it worse, undecided 0→1→8→3 (fresh client,
    2026-11-09). A round its answer marks NOT ANSWERED, or a file the go refuses, is still the round's to repair."""
    try:
        p = _artifact.parse(_planning.text_of(plan))
    except (ValueError, OSError):
        return None                     # …the round's own reading says why it cannot read the file
    if not any("NOT ANSWERED" not in str(n.get("answer", "")) for n in p["notes"]) or \
            _decompose.go_refusals(p["spec"], p["goal"]):
        return None
    return {"refused": True, "error": "this plan already carries an answered note, and the go takes it as it stands: "
                                      "give the go (`auto_decompose(plan=path)`) and tell the person in one line what "
                                      "stays open; a point of their own goes into a new plan, `plan(request)` with "
                                      "their words"}


def _no_provider_answer(subtasks, stats, spec) -> dict:
    """The `error` of a decomposition that built nothing while no model answered — the provider's, not the goal's; a
    plan handed in calls no model by design."""
    return ({"error": "no subtasks were produced and the model completed no call — the LLM provider answered nothing "
                      "(unreachable, or not authenticated; see the server log). A fact about the provider, not about "
                      "the goal."} if not subtasks and not stats and spec is None else {})


def open_at_the_go(plan: str) -> list[str]:
    """What the plan's own review left open when the go was given: each criterion its children were judged not to
    secure (`insufficient`), or were not judged on (`uncertain`). The go runs the plan as it stands (the gate off
    under it, its review in the file), so each goes in carrying its FM-1.d (§11.5): the root's checks still decide the
    result, but a failure there names no part. Said, never silent — a tester's run started on two such criteria with
    nothing said, and its failures pointed nowhere."""
    review = _artifact.parse(_planning.text_of(plan)).get("review") or {}
    lines = [x.strip() for x in str(review.get("semantic_findings") or "").splitlines()]
    return [x[:300] for x in lines if x.startswith(("[insufficient]", "[uncertain]"))]


def reviewed(plan: str) -> bool:
    """Was the system's own Level-2 review run over exactly this file (`planning.mark_reviewed`, at its writing)? A
    `[review]` line is no such record; a file its customer wrote is reviewed in the project as any other split."""
    return _planning.was_reviewed(_planning.text_of(plan))


def _the_go(engine: Engine, plan: str, request: str, spec, root_id=ROOT_ID) -> tuple[str, dict]:
    """The goal and the plan a plan file holds, for the go on `root_id` — refused beside a second plan or another goal,
    and at a contract given, off it (`off_its_contract`)."""
    if spec is not None:
        raise ValueError("auto_decompose: pass the plan file (`plan`) or a spec (`spec`), not both")
    p = _artifact.parse(text := _planning.text_of(plan))
    if off := off_its_contract(engine, p["spec"], root_id):
        raise ValueError(f"auto_decompose: {off}")
    if ((at := _kept.written(engine.project_name)) or {}).get("text") != text:
        _shown(engine, {"path": str(_planning.kept(text))})     # …a go on a text not shown is shown, as it is built
    if (request or "").strip() and request.strip() != p["goal"].strip():
        raise ValueError("auto_decompose: `request` differs from the goal the plan file answers — the go builds "
                         "the plan for its own goal; leave `request` out, or plan the new goal anew")
    # …its review ran where it was written and its customer read it: a second one, over the same file, was minutes and
    # one more round of findings before any work (critic: no row ever ran this; every row of a plan handed in had the
    # gate off, as `set_mode` says of a plan verified where it was authored). And not closed after its build, for the
    # system wrote it (`auto_decompose`): a check of its own that contact refutes is repaired, where a closed plan spun on
    # a true CHALLENGE, its issuer's right answer thrown away 29 times, 27 min (tracker, 2026-11-03; the author:
    # «подчинять систему безоговорочно этому плану нельзя, он может быть сильным но не идеальным»). `spec` stays closed.
    return p["goal"], p["spec"]


#: The longest plan text an answer holds: a read of the file lies outside the person's folder, and a fresh client's auto
#: mode stopped there on a prompt, with no one present before the go (measured). Past this, `path` stands alone. The room
#: the MCP door declares (`ANSWER_ROOM`) replaces the client's token cap for the text, so the bound is that room, its JSON
#: escaping spared: at 80,000 a coreutils plan (88–105k) and a compiler's (to 279k) went by path (2026-11-05, 11-11).
PLAN_TEXT_MAX = 400_000


def _plan_written(text: str) -> dict:
    """The plan file kept under the state directory by its content, with what the customer reads first and, last in the
    answer, the file's text to read it by. The text only reads: the note and the go take the file."""
    path = _planning.kept(text)
    _planning.mark_reviewed(text)
    p = _artifact.parse(text)
    r = p["review"]
    undecided = len(r.get("undecided_obligations") or ())
    deferred = [s["id"] for s in p["spec"].get("subtasks") or () if s.get("split_after")]
    # …WHAT THE GO WILL REFUSE, said now: the authoring's repair rounds can end with the file still refused, and the
    # customer read 40 minutes of plan, gave the go and met the refusal (c_compiler, 2026-11-11)
    refused = _decompose.go_refusals(p["spec"], p["goal"])
    if refused:
        # …a refined file still refused goes to the person, never into a loop
        return {"path": str(path), "chars": len(text), "refused_by_the_go": refused,
                "say": (f"Do not give the go on this file: it refuses it as it stands ({len(refused)} point(s)), after "
                        "a round of notes. Write to the person in one line that this round left the plan "
                        "unrunnable, naming the first points of refused_by_the_go; a file of this plan the go took "
                        "before the note still stands, and its go is theirs to give." if p["notes"] else
                        "Do not give the go yet, and write to the person in one line that the plan needs one more round: "
                        f"the go refuses it as it stands ({len(refused)} point(s)). Send them as the note: "
                        "`refine_plan(plan=path, note=<the points of refused_by_the_go>)`, then read the new file."),
                **({"text": text} if len(text) <= PLAN_TEXT_MAX else {})}
    pins = r.get(_planning.PINS) or {}
    # …what the pins did over the base, said where the customer reads first: a pin no work can run is a note, and pins
    # never run pass no one silently
    nr, cannot = pins.get("not_run") or [], len(pins.get("cannot_run") or ())
    pinned = f" {nr[0]}" + (f" (and {len(nr) - 1} more, review.{_planning.PINS})" if len(nr) > 1 else "") + "." if nr else ""
    # …and what the plan demands that the person never asked, by rule: the system's own, theirs to keep or strike
    beyond = r.get(_planning.BEYOND) or []
    unasked = (f" {len(beyond)} criterion(s) state nothing their request asks (review.{_planning.BEYOND}): the "
               "system's own requirements, not theirs — name each to them; a note strikes any they do not want."
               if beyond else "")
    return {"path": str(path), "chars": len(text), "parts": [s["id"] for s in p["spec"].get("subtasks") or ()],
            "undecided_obligations": undecided,
            **({_planning.PINS: {**pins, **({"cannot_run": len(pins["cannot_run"])} if "cannot_run" in pins else {})}}
               if pins else {}),
            **({_planning.BEYOND: beyond} if beyond else {}),
            "covered": r.get("semantic_covered"), "notes": len(p["notes"]),
            "how_to_read": "read `text` whole, the file at `path` if there is none (the [inputs] at its end are the "
                           "checks' files, named by hash); "
                           "a check whose `expect` its command cannot print will fail correct work: that is a note. "
                           "A note → refine_plan(plan=path, note); the go → auto_decompose(plan=path)",
            "say": "Write to the person now, before any other call: it splits into "
                   f"{', '.join(s['id'] for s in p['spec'].get('subtasks') or ()) or 'one piece of work'}; "
                   f"{undecided} of what the goal asks no check decides yet; "
                   + (f"{len(deferred)} part(s) ({', '.join(deferred)}) are split only once the parts they consume are "
                      f"accepted — made with those results in hand, their split rounds run after them and lengthen "
                      f"the run; " if deferred else "")
                   + "and any "
                   "decision in the file they never asked for." + unasked + pinned + " " + _after_the_plan(undecided, p["notes"], cannot),
            **({"text": text} if len(text) <= PLAN_TEXT_MAX else {})}


#: what the person hears first wherever this project's work will run on this machine (`Workforce.runs_on_host`)
ON_HOST = ("First: this project's work runs on this machine, outside Docker, as the person, and stays off their "
           "branches. ")


def _shown(engine: Engine, out: dict, spec: Optional[dict] = None, root_id: str = ROOT_ID) -> dict:
    """A plan file written is its project's to show: kept as the one its page shows (`written_plan`), told on its feed,
    and under AUTO its page opened, as the go opens it — the person read a plan only in the client's words, and the go
    under AUTO is the client's too (s17b: the core criterion left the plan unsaid). `spec`: the plan's, the criteria
    the go writes beyond it said with it (`added_at_the_go`)."""
    if path := out.get("path"):
        if engine.workforce.runs_on_host():
            out["say"] = ON_HOST + out.get("say", "")
        _kept.wrote(engine.project_name, path)
        engine.emit_info("plan_written", f"the plan is written: {path}")
        # …said with the plan, before the go: the person agrees to every criterion the go fixes, these too
        if spec is not None and (added := added_at_the_go(engine, spec, root_id)):
            out["added_at_the_go"] = added
            out["say"] = out.get("say", "") + (
                f" The go writes the root criterion `{INTENT}` with the system's text (added_at_the_go), in place of "
                "any of the plan's under that name: a validator other than you reads the result against the person's "
                "own words, and fails it only quoting them — name it to the person with the criteria; their words "
                "switch it off, `set_mode(intent_check=False, user_said=<their words>)`.")
        if mode_kind(engine.graph) == Mode.AUTO:
            open_the_page(engine.project_name)
    return out


def _given_at(engine: Optional[Engine], at: dict) -> Optional[float]:
    """When a go was given on the plan file last written — read off what the go itself records, no flag of its own (ui
    critic: a flag read "not given" on every record written before it, and a re-handed text reset it): the root heard
    this text at a go (`hear(root, "plan", …)`), or the file is older than the root, its go having made it. None: the
    file awaits its go. Heard at any node: in a mode scope the go is given on the person's ask, below the root."""
    root = engine and engine.graph.get_task(TaskId(ROOT_ID))
    if root is None:
        return None
    text = "\n".join(x for x in at["text"].splitlines() if not x.lstrip().startswith("#"))
    heard = any(h.get("act") == "plan" and str(h.get("said", "")).strip() == text.strip()
                for t in engine.all_tasks() for h in heard_on(engine.graph, t.id))
    return at["at"] if heard or at["at"] <= root.created_at.timestamp() else None


def written_plan(project, engine: Optional[Engine] = None) -> dict:
    """The plan file last written for `project`, as its page shows it before the go (`GET /api/plan`); {} for none.
    With its `engine`, the criteria the go adds (`with_the_intent`) among its own, marked `added_at_the_go`."""
    if not (at := _kept.written(project)):
        return {}
    text = at["text"]
    try:
        p = _artifact.parse(text)
    except ValueError:                  # …a kept file that no longer reads is gone as far as its reader can tell
        return {}
    spec, r = (with_the_intent(engine, p["spec"]) if engine else p["spec"]), p["review"]
    added = {c["name"] for c in (added_at_the_go(engine, p["spec"]) if engine else ())}
    return {"path": at["path"], "written_at": at["at"], "given_at": _given_at(engine, at), "goal": p["goal"],
            "executor": p["executor"],
            "parts": [{"id": s["id"], "name": s.get("name", ""), "description": s.get("description", ""),
                       "criteria": [c["name"] for c in s.get("criteria") or ()],
                       "split_after": list((s.get("split_after") or {}).get("after") or ())}
                      for s in spec.get("subtasks") or ()],
            # …each with its words and its checks, so the page shows what the person agrees to before the go (ui)
            "root_criteria": [{"name": c["name"], "description": c.get("description", ""),
                               "check": [{**{k: x.get(k, "" if k != "exact" else False)
                                             for k in ("behaviour", "command", "expect", "exact")},
                                          **({"bound_s": x["bound_s"]} if x.get("bound_s") is not None else {}),
                                          **({"procedure": x["procedure"]} if x.get("procedure") else {})}
                                         for x in c.get("check") or ()],
                               **({"added_at_the_go": True} if c["name"] in added else {})}
                              for c in spec.get("root_criteria") or ()],
            "deps": [[d["from"], d["to"]] for d in spec.get("deps") or ()],
            "open": open_at_the_go(text), "taken_back": r.get("taken_back") or [],
            "refused_by_the_go": _decompose.go_refusals(spec, p["goal"]),
            "undecided": len(r.get("undecided_obligations") or ()),
            "notes": [{"note": n.get("note", ""), "answer": n.get("answer", "")} for n in p["notes"]],
            "documents": _kept.documents(p["goal"])}


def _after_the_plan(undecided: int, notes: list, cannot: int = 0) -> str:
    """What the customer does with a plan just read. A plan with nothing undecided went through three rounds of notes on
    points the person never raised, 8:28 of a 17-minute run, and came out worse, undecided 0→1→8→3 (fresh client, 2026-11-09).
    A note whose round its answer marks NOT ANSWERED is not spent (`planning.still_open`): told "answered", the customer
    gave the go on a plan its own review held open on the very criterion the round added (2026-11-13). A pinned check
    that `cannot` run on any work, left by the authoring's repair, is open like an undecided obligation — and the one
    a note surely repairs: told "nothing is undecided", the go would carry it to the executor's dispute (s16b). Never a
    gate: the go stays theirs."""
    go = "give the go, `auto_decompose(plan=path)`; the work then runs unattended: a few minutes on a small task, hours on a large one, say so."
    pins = (f"{cannot} pinned check(s) cannot run on any work: review.{_planning.PINS}.cannot_run names each, with "
            "bash's words; a note naming them repairs them. " if cannot else "")
    if notes and "NOT ANSWERED" in str(notes[-1].get("answer", "")) and any(
            "NOT ANSWERED" not in str(n.get("answer", "")) for n in notes[:-1]):
        return (pins + "The last note was NOT ANSWERED, and an earlier one was answered: another round is refused on "
                "this file (`refine_plan` says so); tell the person in one line what stays open, and " + go)
    if notes and "NOT ANSWERED" in str(notes[-1].get("answer", "")):
        return (pins + "The last note was NOT ANSWERED (its answer says what stays open): it is not spent — refine again "
                "with it, sharper, or with a stronger `model`; or tell the person in one line what stays open, and " + go)
    if notes:
        # …the one round is spent: the pins stand flagged and the go carries them, never a second note invited (critic)
        stand = (f"{cannot} pinned check(s) still cannot run on any work (review.{_planning.PINS}.cannot_run): they stand "
                 "flagged and the go carries them — an executor's CHALLENGE of such a check is the route left; say so "
                 "in one line. " if cannot else "")
        return f"{stand}The note is answered: what stays open goes to them in one line, and {go}"
    round_ = "a `refine_plan` (2–3 minutes), only for something about the person's result; the rest goes to them in one line."
    if cannot:
        return f"{pins}That is the round: `refine_plan(plan=path, note=<them>)`, then read the new file. Then {go}"
    return (f"Nothing is undecided: {go} A note, if any: {round_}" if not undecided
            else f"An open line alone is no reason for a round: {round_} Then {go}")


@functools.wraps(_tools.create_task)
def create_task(*a, **kw):
    """`gfso.tools.create_task`; the call that makes the root by hand (MANUAL) says what the agents' copy lacks too
    (`_not_imported`), as `auto_decompose` does where it authors the root."""
    at = inspect.signature(_tools.create_task).bind(*a, **kw).arguments
    if not at.get("parent_id") and isinstance(spec := at.get("spec"), dict):
        # …a root made by hand carries what every root door writes (`with_the_intent`)
        at["spec"] = {**spec, "criteria": with_the_intent(at["engine"], {"root_criteria": list(spec.get("criteria") or ())},
                                                          at.get("task_id") or ROOT_ID)["root_criteria"]}
    out = _tools.create_task(**at)
    made_root = isinstance(out, dict) and "error" not in out and not at.get("parent_id")
    return {**out, **_not_imported(at["engine"])} if made_root else out


# …its arguments as the verb's own, so the door's lock reads `parent_id` and `agent` (bound as `*a, **kw` it read none)
create_task.__signature__ = inspect.signature(_tools.create_task)


def _not_imported(engine) -> dict:
    """What of the user's repository the agents' copy lacks (`left_out`), said in the answer of the call that starts
    the work — the import itself runs at a container's first start or on the root's thread, whose log no agent reads."""
    ex = execution_of(engine)
    return {"not_imported": said} if isinstance(ex, ContainerExecution) and (said := left_out(ex.volume.base)) else {}


# The COMPLETE transport registry: structural surface + the LLM verbs. Binding layers use THIS.
def _tracked(name, fn):
    """The three verbs that spawn a model and run for minutes announce themselves in INFLIGHT, so a
    reconcile from another session can see the server is busy and decline to restart it — each
    under the project and node it works on, which the verb's own arguments name."""
    sig = inspect.signature(fn)

    @functools.wraps(fn)
    def wrapper(*a, **kw):
        """Run the verb while it is marked in flight, so a second call can be refused."""
        at = sig.bind_partial(*a, **kw).arguments
        with flight(name, at.get("engine"), at.get("task_id") or at.get("root_id", ROOT_ID)):
            return fn(*a, **kw)
    return wrapper


def _off_the_call(name: str, fn, lands):
    """`fn`, a verb that runs a model, at a door: run in a thread of the server's, as a plan is written (`_once`). What it
    answers within ANSWER_WITHIN_SECONDS is the call's answer — a refusal, a run already in flight, a short run —; past
    that the call answers that it runs, and where its result lands (`lands(engine, node)`), and the run goes on, in flight
    under its node (`flight`), an error it ends with unread said on the feed. A call held for minutes held its client's
    turn, and the person with it: the one wait on a run is the server's (`POST /api/wait`). On the CLI's direct path it
    runs in the call: no thread would outlive its process."""
    sig, answered = inspect.signature(fn), answering(fn)

    @functools.wraps(fn)
    def _call(*a, **kw):
        if _config_written_in_the_call.get():
            return fn(*a, **kw)
        at = sig.bind_partial(*a, **kw).arguments
        engine, node = at.get("engine"), str(at.get("task_id") or ROOT_ID)
        gone, out = threading.Event(), Future()
        _shown_until(kw, gone)

        def run():
            got = answered(*a, **kw)
            out.set_result(got)
            if gone.is_set() and isinstance(got, dict) and got.get("error") and engine is not None:
                engine.emit_info(name, f"{node}: {name} ended with no result: {str(got['error'])[:400]}")
        threading.Thread(target=contextvars.copy_context().run, args=(run,), daemon=True, name=f"gfso-{name}").start()
        try:
            return out.result(timeout=ANSWER_WITHIN_SECONDS)
        except TimeoutError:
            gone.set()
        said = lands(engine, node)
        return {"task_id": node, "running": name, **said,
                "waited": f"answered at {ANSWER_WITHIN_SECONDS:.0f} s, the run going on in the server",
                "say": f"`{name}` runs on in the server, past this call: {said['lands']}. "
                       + how_it_is_waited(engine.project_name if engine is not None else None, "it is yours to read")}
    return _call


def _shown_until(kw: dict, gone: threading.Event) -> None:
    """The door's progress (`_progress`) ends with its call: a run past it narrates to no one."""
    if (shown := kw.get("_progress")) is not None:
        kw["_progress"] = lambda msg: None if gone.is_set() else shown(msg)


def _written_past_its_call(fn):
    """`auto_decompose` at a door: an authoring from a request, or a refine, written in a thread of the server's through
    the plans' one channel (`_once`), its whole answer kept by its handle and `gfso wait` waking on it. Its subtree is
    claimed in the call, under the handle, and let go by the writing at its end (`Authorings.writing`), so from the call
    on every move there is refused naming it (`being_rewritten`) and the frontier holds it in flight. What it answers within
    ANSWER_WITHIN_SECONDS is the call's answer — a refusal, a short run —; past that `{writing}`. An answer that cannot be
    kept — the model's error, the run dead — is its handle's error, said on the feed. In the call: the CLI's direct path,
    a read by handle, and the go on a plan written (`plan`, a closed `spec`), which runs no model."""
    sig = inspect.signature(fn)

    @functools.wraps(fn)
    def _call(*a, **kw):
        at = sig.bind_partial(*a, **kw).arguments
        if (_config_written_in_the_call.get() or at.get("writing") or at.get("plan") is not None
                or at.get("spec") is not None and not at.get("open_plan")):
            return fn(*a, **kw)
        engine, node = at["engine"], str(at.get("root_id") or ROOT_ID)
        key = ("auto_decompose", engine.project_name, node, os.urandom(5).hex())
        handle, gone = _handle_of(key), threading.Event()
        if (other := engine.authorings.take(node, handle)) is not None:
            return _refused_while_written(engine, node, other)
        _shown_until(kw, gone)

        def write() -> dict:
            """The authoring, its subtree let go at its end, an error past the call said on the feed."""
            with engine.authorings.writing(node):
                out = answering(fn)(*a, **kw)
            if out.get("error") and not engine.all_tasks():
                out["error"] = (f"{out['error']} — project {engine.project_name} holds nothing: "
                                f"`delete_project('{engine.project_name}')` removes it")
            if gone.is_set() and out.get("error"):
                engine.emit_info("auto_decompose", f"{node}: the authoring {handle} ended with no plan: "
                                                   f"{str(out['error'])[:400]}")
            return out
        try:
            _once(key, write)
        except BaseException:          # …no writing behind the claim: never a subtree held by nothing (Inv-8)
            engine.authorings.let_go(node)
            raise
        with _PLANNING_LOCK:
            w = _PLANNING.get(key)
        if w is None or _settled_within([w.answer], ANSWER_WITHIN_SECONDS).done:
            return _by_handle(handle, engine.project_name)
        gone.set()
        with _PLANNING_LOCK:      # …answered at its end in between: its answer, not `{writing}`
            if key not in _PLANNING or w.answer.done():
                return _by_handle(handle, engine.project_name)
            return {**_answer_of(key), "running": "auto_decompose", "root_id": node, "task_id": node,
                    "lands": f"the graph it builds is read by `get_graph` as it stands; every move in {node}'s subtree "
                             f"is refused until it ends, `next_steps` naming it in flight"}
    return _call


def _validation_runs(engine, node) -> dict:
    """What a validation running past its call checks, and where its verdict lands."""
    tree, commit = ((engine.delivered(TaskId(node)) if engine is not None else None) or (None, None))[:2]
    return {"checks": {"tree": tree, "commit": commit},
            "lands": f"its verdict lands on the record, `get_verdict('{node}')` reads it; while it runs `next_steps` "
                     f"names the node waiting on it, and validate_result again starts no other"}


#: The verbs that run a model inside them, each answering at a door at once (`_off_the_call`), and where what they run
#: lands. In process — the dispatcher's own validation, an issuer's review (`SYSTEM_TOOLS`) — each answers its result.
#: `auto_decompose` goes off its call through the plans' channel (`_written_past_its_call`).
OFF_THE_CALL = {
    "validate_result": _validation_runs,
    "review_decomposition": lambda engine, node: {
        "lands": f"its verdict lands on the record, `get_review('{node}')` reads it, and the plan's gate opens on it"},
}


def register_agent(engine: Engine, agent_id: str, kind: str, model: str = MODEL_DEFAULT,
                   workdir: Optional[str] = None, validator: Optional[str] = None,
                   oracle_map: Optional[str] = None, max_turns: Optional[int] = None,
                   client: Optional[str] = None, execution: Optional[str] = None,
                   context_budget: Optional[int] = None) -> dict:
    """Register a NON-human participant (humans need no registration — an unregistered Del = human,
    the system stays passive). kind: `llm-executor` (nodes assigned to this id AUTOSTART: headless
    executor with work tools in `workdir`, its report wrapped into ACCEPT/DELIVER/BLOCK/CHALLENGE) ·
    `llm-validator` (the auto-validation instrument, fired on every delivery it is bound to. It also
    SIGNS the verdict when the node's issuer is automated — the standing agent id `user`, or a
    registered role. A PERSON is any other name: their node is validated, recorded, and then waits for
    them to signal, because §10.3 keeps the verdict the issuer's act. Note where that line falls: the
    default identity on every door IS the standing agent, so a caller who never names themselves gets
    the signing too) · `external` (a system
    that sends its own
    signals; nothing spawns). `validator` on an executor entry = a per-executor instrument override
    (else the first registered llm-validator serves everyone). To delegate work after this: just
    assign/reassign nodes to the registered id.

    `workdir` is REQUIRED for `llm-executor` and `llm-validator`: the directory of the project the
    agent works in or validates. Without it the agent would be spawned where the SERVER stands — the
    gfso state home — which holds none of the work, and both ways that failed were silent.

    `client` (optional) ties the role's LIFETIME to your own lease: while that lease is live the role
    is dispatchable, and when it lapses the dispatcher stops starting work for it — nothing is
    cancelled, no state moves, and the same owner returning resumes where the graph stood.

    `execution` (optional) names where this project's sessions and commands run — an execution the server
    DECLARES (its executions.json: a Linux container per project, say); one per project, and none = this host.

    `context_budget` (optional, tokens) is the executor's: a session whose context reaches it writes a handover note
    and a fresh session continues the task from it — whatever the model's provider offers (none = no budget).

    THIS VERB LIVED ON THE AGENT DOOR ALONE. A person driving from the CLI or the HTTP API was told
    by the log to `reassign` a node to a registered role and had no verb anywhere to make one —
    so delegation, parallel execution and an independent validator were unreachable from the human
    door entirely (measured 2026-08-21). The roster is one server-wide fact; every door asks it."""
    # THE PERSON'S NAME IS NOT A ROLE, AND REGISTERING IT MAKES EVERY UNNAMED CALLER ONE.
    # `user` (`agent` before 0.4.0) is what every door hands a caller who does not name themselves — on this server, in
    # every project — so a roster entry under that id is not a participant, it is a redefinition of
    # the default identity. Both halves of that were measured within a day. As a VALIDATOR it made
    # the executing identity the one whose signature closes the seam (closed at the gate: a
    # registration cannot make an id independent of itself). And its registered `workdir` then
    # became the place auto-validation validated in — a stranger on the MCP door watched their delivery
    # validated against ANOTHER session's project, the temp directory a different tester had registered
    # hours earlier, and it caught their fabrication for entirely the wrong reason (wave 23,
    # 2026-09-03). Refused here rather than patched downstream: every consumer of the roster would
    # otherwise need to know that one id means something else.
    if (why := reserved_refusal(agent_id)):  # …the person's, now or before 0.4.0, not this caller's
        return {"refused": True, "error":
                f"{why} It is the STANDING identity this door gives every caller who does not name themselves: "
                f"a role under it would redefine the default identity for every session and project on this "
                f"server — its workdir would become the place unattended validations validate in, and its kind "
                f"would attach to whoever simply omitted a name. Register the role under its own id "
                f"(`{agent_id}-val`, `{agent_id}-exec`, or anything else) and assign nodes to THAT id — which is also what makes the "
                f"delegation visible in the graph."}
    agents = staffed(engine)
    # …a role of this project registered again keeps where it runs: to change its model, its project's only declaring role came back
    # with none, the project on the host and its validations there, said nowhere (critic, ran)
    own = agents.get(agent_id) or {}
    kept = own.get("execution") if own.get("project") == engine.project_name else None
    execution = execution or kept or (_default_execution(engine, engine.mode(), agents) if kind == "llm-executor" else None)
    # …a directory no delivery from it could be judged by, refused with its lift before anything is written
    if workdir and (why := no_repository(workdir, executor=kind == "llm-executor" and not execution)):
        return {"refused": True, "error": f"NOT registered — {why}"}
    out = agents.register(agent_id, kind, model=model, workdir=workdir, validator=validator,
                          oracle_map=oracle_map, max_turns=max_turns, client=client, context_budget=context_budget,
                          project=engine.project_name, execution=execution)
    if kind == "external" and (p := CALLER.get()) is not None and p.person:
        signin.own(agent_id, p.person)           # …a person's kind is its registrant's to sign as
    publish_the_workforce(engine, agents.list())
    # THE SPELLING THAT BINDS, not the one that was typed. The roster stores the workdir RESOLVED,
    # and the workspace binding is decided on that value — while the advice below interpolated the
    # caller's own argument, so a relative `workdir='work'` came back as an instruction that names a
    # different place when run from a different directory.
    workdir = out.get("workdir") or workdir
    record_repository(engine, out.get("workdir"))
    # …AND WHO WILL ACTUALLY VALIDATE THIS ROLE'S WORK. The roster is server-wide, and an executor
    # registered without an explicit `validator` came back with `validator: null` — while the
    # instrument that would really validate it was whichever llm-validator had been registered first,
    # quite possibly another run's, standing in a directory containing none of this work.
    if kind == "llm-executor":
        # …within its project, as the dispatcher binds it: unscoped, the answer named another project's validator in the
        # same directory while this project's own one did the validating (live, otf-smoke-4)
        who = agents.validator_for(agent_id, project=engine.project_name)
        cfg = agents.get(who) if who else None
        # …AND SAY SO IF THAT NAME IS NOT A ROLE YET. `validator=` is taken at its word, so naming a
        # validate that has not been registered came back as a confident `will_be_validated_by: <name>` —
        # a binding to nothing, and a typo would have read exactly the same (agent door, 2026-09-02).
        # The binding is kept: registering the validator afterwards is the normal order. What changes is
        # that the answer stops asserting a party that does not exist.
        if who and cfg is None:
            out["will_be_validated_by"] = (
                f"{who} — NOT REGISTERED YET, so nothing will validate this role's work until it is. "
                f"`register_agent('{who}', 'llm-validator', workdir='{workdir}')` completes the "
                f"binding; the name is kept either way.")
            return out
        out["will_be_validated_by"] = who or (
            f"nobody YET — no validator stands in {workdir} at this moment. Register one there "
            f"(`register_agent(<id>, 'llm-validator', workdir='{workdir}')`) and it binds to this "
            f"role by workspace, in either order; until then the deliveries of this role wait for "
            f"you to validate them; under a project, its own validator binds wherever it works." if workdir else
            "nobody yet — register an llm-validator")
        if who and validator is None:
            out["note"] = (f"you named no validator, so this role inherits '{who}'"
                           + (f" (working in {cfg.get('workdir')})" if cfg else "")
                           + ". Pass `validator=` to bind your own instrument — the roster is "
                             "shared by every session of this server.")
    # …AND A VALIDATOR CLOSES THE LOOP THE EXECUTOR OPENED. Registering the executor first answers
    # "nobody YET — register one in this workdir and it binds, in either order"; registering the
    # validator second answered nothing at all, so the promised binding was unconfirmable until an
    # execution was validated 25 minutes later (HTTP door, 2026-09-02). The question is symmetric and
    # so is the answer.
    if kind in ("llm-validator", "unittest-checker"):
        _bound = sorted(a for a, c in agents.list().items()
                        if c.get("kind") == "llm-executor"
                        and (c.get("validator") == agent_id
                             or (not c.get("validator") and agents.validator_for(a, project=c.get("project")) == agent_id)))
        out["will_validate"] = _bound or (
            f"nothing yet — no executor is registered"
            + (f" in {workdir}" if workdir else "")
            + ". An executor registered there binds to this instrument by workspace, in either order.")
        # …and the declared boundary of the seams the person issues: a delivery records the tree it hands in only where
        # its judge's place is a repository's top, and a tree no delivery records no FAIL can refuse handed in again
        # …a directory below a top delivers that tree's commit, its judge standing in it (`judged_at`)
        top = W.git(workdir, "rev-parse", "--show-toplevel").stdout.strip() if workdir else ""
        if kind == "llm-validator" and workdir and not (top and W.is_repo_top(top)):
            out["seam_boundary"] = (f"{workdir} is in no git repository with a commit: a delivery judged there records "
                                    f"no tree, so a FAIL at a seam the person issues cannot refuse the same work handed "
                                    f"in again — it is observed after it lands. Commit the repository for his seams to "
                                    f"force rework")
    return out


def unregister_agent(engine: Engine, agent_id: str, workdir: Optional[str] = None) -> dict:
    """Take a role OFF the server-wide roster — the inverse of `register_agent`, which could put
    roles on and never take them off, so every run left its executors and validators behind for the
    rest of the installation's life. `workdir` is optional: given, the role goes only while it still
    points at that directory, so tidying up cannot unstaff someone else's same-named role; omitted,
    the role goes unconditionally — refused for a role another project registered.

    What removal changes on this project's live nodes, and the answer lists them: a node assigned to
    the id keeps its Del, a worker already running finishes, and nothing new starts for it; a node
    whose delivery that validator would have validated is validated by the next validator in scope, or by
    none; and a node the role ISSUED (its own decomposition) now waits for a person, because an
    issuer counts as automated only while it is on the roster."""
    if not isinstance(agent_id, str) or not agent_id.strip():
        return {"error": f"agent_id must be the registered role's id (a non-empty string), got {agent_id!r}"}
    agent_id = agent_id.strip()
    role = staffed().list().get(agent_id) or {}
    # the engine's own reading of "this project" — and a guard against an ACCIDENT, not an owner
    # check: `project=` is the caller's word, and an unscoped role (registered with no project)
    # belongs to nobody and can be removed by anyone
    mine = (engine.project_name or DEFAULT_PROJECT) if engine is not None else None
    if workdir is None and role.get("project") and role.get("project") != mine:
        return {"unregistered": None,
                "error": f"{agent_id} was registered by project '{role['project']}', not this one — pass "
                         f"its `workdir` to show it is the role you staffed"}
    out = staffed().unregister(agent_id, workdir=workdir)
    if out.get("unregistered") and engine is not None:
        # …told where a role put on is told: published only by the dispatcher's round, a role taken off reached an open
        # page late, and never in a project no round serves (ui stream, 2026-11-13)
        publish_the_workforce(engine, staffed().list())
        live = [t for t in engine.graph.active_tasks()]
        out["assigned_live"] = sorted(str(t.id) for t in live if str(t.assignee) == agent_id)
        # by the dispatcher's own reading of who issued a node (a root is its own issuer)
        out["issued_live"] = sorted(str(t.id) for t in live
                                    if str(engine.graph.issuer_of(t.id)) == agent_id)
    return out


_MODE_STAFF = {Mode.AUTO: 2, Mode.SEMI: 1, Mode.SOLO: 0}


def _default_execution(engine: Engine, mode: Optional[dict], agents) -> Optional[str]:
    """WHERE A PROJECT'S EXECUTORS NAMING NO EXECUTION WORK: the installation's "default" (`gfso setup` declares it), so
    delegation on a new install runs in a container with no hand step — once a mode is set: with none, the user's agent
    builds nodes in its own chat beside delegated ones, and the whole project moved into a volume that does not hold
    that work (critic). `in_chat` too: its chat's deliveries are kept in the volume (`store.keep`) and its parts' work
    lands back (`workspaces._to_the_chat`). Not where the project already runs somewhere, nor where the user said
    unattended work may run on this host."""
    if not mode or _config_module.local_agents() or declaring_role(engine, agents) is not None:
        return None
    try:
        return DEFAULT_EXECUTION if DEFAULT_EXECUTION in executions() else None
    except ValueError:
        return None          # …an unreadable declaration: the registration names no execution, as before setup


def _executors_into(engine: Engine, execution: Optional[str], agents, which: Optional[list] = None,
                    moved: Optional[list] = None) -> list:
    """The project's executors (`which`, else every one naming no execution) registered again under `execution` — the
    ones it moved, each in `moved` as it moves: a move that raises half way leaves its caller the ones to move back."""
    moved = [] if moved is None else moved
    for aid, c in _movable(engine, agents, which).items():
        agents.register(aid, "llm-executor", **{k: c.get(k) for k in ("model", "workdir", "validator", "oracle_map",
                        "max_turns", "client", "project", "context_budget")}, execution=execution)
        moved.append(aid)
    return moved


def _movable(engine: Engine, agents, which: Optional[list] = None) -> dict:
    """{id: registration} of the project's executors `which`, else of every one naming no execution."""
    return {aid: c for aid, c in agents.list().items()
            if c.get("kind") == "llm-executor" and c.get("project") == engine.project_name
            and (aid in which if which is not None else not c.get("execution"))}


def mode_staffing(engine: Engine, mode: str, perform: str = "dispatch") -> dict:
    """What a mode needs registered in this project, and whether it has it — the one rule `set_mode`
    enforces, readable before anyone asks for the mode (the page shows it; a copy of the rule in the
    page had already drifted from this one). Executors: auto two (the root and its children must be
    different executors, or the children would self-verify), semi one, solo none — and one in any mode
    whose held nodes are DISPATCHED to a session of this project's executor. A validator in every mode:
    the system validates wherever κ ends, whoever holds the node, so solo needs the instrument as much
    as auto does — without one, the agent is its own only verifier."""
    m = Mode(str(mode).strip().lower())
    agents = staffed(engine)
    publish_the_workforce(engine, agents.list())
    pool = [str(a) for a in engine.workforce.executor_pool()]
    validators = _validators_of(engine, agents)
    dispatch = perform == "dispatch" and m != Mode.AUTO          # under AUTO the user-agent holds nothing
    need = max(_MODE_STAFF[m], int(dispatch))
    # …and work dispatched runs unattended: where the project runs refuses it, no count of roles makes the mode ready
    refused = execution_of(engine).agents_refused() if need else None
    ready = len(pool) >= need and bool(validators) and not refused
    missing = "" if ready else refused or (
        f"{m.value} needs {need} registered executor(s) of this project and a validator; it "
        f"has {len(pool)} executor(s) ({', '.join(pool) or 'none'}) and {len(validators)} validator(s)"
        + (" — dispatch performs your nodes in a session of this project's executor" if dispatch else "")
        + ". Register them with `register_agent(<id>, \"llm-executor\" | \"llm-validator\", "
        "workdir=<the work's directory>)` in this project, then set the mode.")
    return {"mode": m.value, "perform": perform, "dispatch": dispatch, "needs_executors": need,
            "executors": pool, "validators": validators, "ready": ready, "missing": missing}


def _validators_of(engine: Engine, agents) -> list:
    """The instruments that validate this project's work: its own, or unscoped ones (shared by design)."""
    return [a for a, c in agents.list().items()
            if c.get("kind") in ("llm-validator", "unittest-checker") and c.get("project") in (engine.project_name, None)]


def run_state(engine: Engine) -> dict:
    """THE RUN'S ONE STATE — `running`; `stopping` once stopped while sessions of this project still run (`working`:
    each one's verb, node and since); `stopped` when none does. Derived from the stop as set and the work in flight,
    never a second flag."""
    if not (stop := engine.stops.paused()):
        return {"state": "running"}
    working = [w for w in in_flight() if w.get("project") == (engine.project_name or DEFAULT_PROJECT)]
    # `off_s` is the doors' own reading of the stop (`model.door_off_s`), nothing a client acts on
    return {"state": "stopping" if working else "stopped", **{k: v for k, v in stop.items() if k != "off_s"},
            "working": working}


def stop_project(engine: Engine, why: str = "", by: Optional[str] = None) -> dict:
    """STOP the project's run: the system starts no new session in it (executor, validator, issuer); those running
    finish and their signals land — `stopping` until the last one has, then `stopped`. No timeout fires while stopped
    and the graph is not changed. `start_project` runs it again."""
    engine.stops.pause(by or caller_id(), why)
    return run_state(engine)


def start_project(engine: Engine, by: Optional[str] = None) -> dict:
    """RUN the project again after `stop_project`; the time it stood stopped is left off its clocks, so no bound ran out
    in it (`project_now`)."""
    engine.stops.resume(by or caller_id())
    return {**run_state(engine), **({} if engine.graph.setting(VOLUME + IMPORTED) else _not_imported(engine))}


def next_steps(engine: Engine, root_id: Optional[str] = None, actor: Optional[str] = None) -> dict:
    """The frontier with the run's state beside it — `run`: running, stopping or stopped (`stop_project` /
    `start_project`). What follows is the frontier's own text (`gfso.tools.next_steps`)."""
    out = _tools.next_steps(engine, root_id, actor)
    for s in out.get("steps") or ():      # …a wait on a named checker that cannot sign yet says how it comes to
        if str(s.get("directive", "")).startswith(OBSERVE) and (signs := how_the_checker_signs(engine, s["task_id"])):
            s["directive"] += f" {signs}."
    return {**out, "run": run_state(engine), **plans_of(engine.project_name)}


next_steps.__doc__ += "\n\n    " + (_tools.next_steps.__doc__ or "").strip()


def needs_its_customer(out: dict) -> Optional[str]:
    """Why a run needs the agent that gave the go, read off its `next_steps` — or None while it does not: a plan it asked
    for written, the root settled, a move that is the caller's, a `stuck` frontier (its directive is for the person), or
    the run stopped."""
    plans = out.get("plans") or {}
    if written := plans.get("written"):
        return "a plan asked for is written: " + "; ".join(
            f'`{h.rsplit("-", 1)[0]}(writing="{h}")` answers it' for h in written)
    if failed := plans.get("failed"):
        return "a plan asked for was not written: " + "; ".join(
            f'`{h.rsplit("-", 1)[0]}(writing="{h}")` says why' for h in failed)
    mine = [s for s in out.get("steps") or () if s.get("mine") and not s.get("optional")]
    run = (out.get("run") or {}).get("state")
    return ("the root is settled" if out.get("complete") else f"{len(mine)} move(s) are yours" if mine
            # …a refuted pass's reopen the mode locks and nobody in the system makes (`frontier.refuted_said`)
            else (f"a pass its later FAIL refutes waits on a reopen nobody in the system makes under this mode: "
                  f"{', '.join(u)} (`get_verdict`)") if (u := out.get("reopen_unmade"))
            else (f"a pass its later FAIL refutes is past its reopen, and its recovery nothing in the system makes: "
                  f"{'; '.join(p)} (`get_verdict`)") if (p := out.get("recovery_unmade"))
            else f"the run is stuck: {str(out.get('directive') or '')[:400]}" if out.get("stuck")
            else f"the run is {run}" if run in ("stopping", "stopped") else None)


def wait_for_the_customer(engine: Engine, root_id: Optional[str] = None, actor: Optional[str] = None,
                          seconds: float = WAIT_MAX_SECONDS) -> dict:
    """The one wait on a run, served on HTTP alone (`POST /api/wait`), never as a verb: a verb holding its call for
    minutes holds its client's turn, and the person with it. `next_steps` asked again on the engine's clock until
    `needs_you` (`needs_its_customer`) or `seconds`, at most `WAIT_MAX_SECONDS`; the sleep is the runner's."""
    began = engine.now()
    deadline = began + min(float(seconds), WAIT_MAX_SECONDS)
    first, stood = True, None
    while True:
        out = next_steps(engine, root_id, actor)
        plans = out.get("plans") or {}
        why, writing = needs_its_customer(out), set(plans.get("writing") or ())
        if first:
            first, stood, watched = False, why, set()
        # …a wait on a writing is about the writing: what already stood when it began does not end it, and each one it
        # saw writing ends it when ITS record ends — written or failed, whoever else read it meanwhile —; one superseded
        # (asked anew) ends nothing, the one asked anew is watched in its place
        if why and why == stood and writing:
            why = None
        ends = _ends(engine.project_name, watched := watched | writing)
        done = {k: sorted(h for h, s in ends.items() if s == k) for k in ("written", "failed")}
        if done["written"] or done["failed"]:          # …what the wait was about first
            why = needs_its_customer({"plans": done})
        if why or engine.now() >= deadline:
            # …a wait woken by an end says the plans as they stand after the ends were read: a writing that ended between
            # the two reads woke it and was still listed writing in the step read before it. Not at the deadline: a plan
            # ending there would be said, marked told and never wake the next wait
            if why:
                out, plans = {**out, "plans": (p := plans_of(engine.project_name).get("plans", {}))}, p
                if not plans:
                    out.pop("plans")
            said_a_plan(engine.project_name, out)
            # …and what each writing it wakes on came to, whole, as its handle reads it
            ended = sorted({*done["written"], *done["failed"],
                            *(h for k in ("written", "failed", "unread") for h in plans.get(k) or ())})
            return {**out, "waited_seconds": round(engine.now() - began, 1),
                    **({"answers": {h: _by_handle(h, engine.project_name, read=False) for h in ended}}
                       if why and ended else {}),
                    **({"needs_you": why} if why else
                       {"waited_note": "nothing needs you yet: the graph is working (`in_flight`) or waiting on a person "
                                       "(`waiting`)"})}
        time.sleep(min(WAIT_POLL_SECONDS, max(0.0, deadline - engine.now())))


def held_steps(engine: Engine) -> dict:
    """What a console's Stop hook reads (`GET /api/steps`, `gfso.hold`): `next_steps` as its signer's, marking nothing
    — a plan named here stays unsaid, for the wait that wakes on it (`said_a_plan` is a reply's) —, with the signer and
    whether its name works in a chat here (`in_chat`: the record its own move over MCP made, `Engine.performs_in_chat`);
    a connection whose holding was refused (`signin.held`) reads as no one's, its `refused` saying why, and a call that
    signs nothing — no credential, or a connection that has taken no name (`signin.BARE`) — as `unsigned`: no move of
    the frontier could sign from it."""
    me, p = caller_id(), CALLER.get()
    # …`current`: the node of the signer's latest move the log took — the task it is on, read off the system's record
    on = next((str(a.task_id) for a in reversed(engine.audit_log()) if not a.rejected and str(a.source or "") == me), None)
    return {**next_steps(engine, actor=me), "signer": me, "in_chat": me in in_chat_names(engine.graph), "current": on,
            **({"refused": p.lift} if p is not None and p.via == signin.REFUSED else
               {"unsigned": True} if p is not None and p.via == signin.BARE.via else {})}


def _settings_given(system_model, planner_model, l2_gate, deadline_s, observe, network, bounds,
                    max_iterations, intent_check=None) -> Union[dict, str]:
    """What `set_mode` was given for the project to set for itself, as the settings table keeps it — or why not."""
    if bounds is not None and (why := bounds_refusal(bounds)):
        return why
    if max_iterations is not None and (isinstance(max_iterations, bool) or not isinstance(max_iterations, int)
                                       or not 1 <= max_iterations <= MAX_ITERATIONS_CEILING):
        return f"max_iterations is a count of rework rounds, 1 to {MAX_ITERATIONS_CEILING}, got {max_iterations!r}"
    if deadline_s is not None and float(deadline_s) <= 0:
        return (f"deadline_s is seconds ahead, more than 0, got {deadline_s!r}: a packet with no deadline does not "
                f"conform (§12.16), and a plan's parts type none, so 0 would leave every one of them refused")
    if network is not None and network != "declared":
        network = {"mode": network} if isinstance(network, str) else network
        try:
            network_of(network if isinstance(network, dict) and "mode" in network else ())
        except ValueError as e:
            return str(e)
    return {k: v for k, v in (("system_model", str(system_model).strip() or None if system_model else None),
                              ("planner_model", str(planner_model).strip() or None if planner_model else None),
                              ("network", None if network is None else "" if network == "declared"
                               else json.dumps(network)),
                              ("l2_gate", None if l2_gate is None else "1" if l2_gate else "0"),
                              ("deadline_s", None if deadline_s is None else float(deadline_s)),
                              ("observe", None if observe is None else "1" if observe else "0"),
                              ("bounds", None if bounds is None else json.dumps(bounds)),
                              ("max_iterations", max_iterations),
                              ("intent_check", None if intent_check is None else "1" if intent_check else "0"))
            if v is not None}


#: what `set_mode(node=…)` answers since the scope was retired: the level a seam is held at is its executor's own act
_NOTHING_AT_A_NODE = {"refused": True, "error": "nothing is set at a node: a seam the person issues to a name that works "
                                                "in a chat is held solo there by that name's own act — its connection "
                                                "taking it (`act_as('<name>')`) — and its verdict and contract are his "
                                                "wherever he issues it. Who checks it is his choice: "
                                                "`set_checker('<seam>', …)`"}


def set_mode(engine: Engine, mode: Optional[str] = None, boundary: Optional[int] = None,
             agent: Optional[str] = None, user_said: str = "", perform: Optional[str] = None,
             system_model: Optional[str] = None, planner_model: Optional[str] = None, l2_gate: Optional[bool] = None,
             deadline_s: Optional[float] = None, observe: Optional[bool] = None,
             network: Optional[Union[str, dict]] = None, bounds: Optional[dict] = None,
             max_iterations: Optional[int] = None, intent_check: Optional[bool] = None,
             workdir: Optional[str] = None, node: Optional[str] = None) -> dict:
    """Set WHO HOLDS WHICH NODES in this project — the user's choice, made once, before the plan.

    - `solo` — you (the user-agent) hold and execute every node; the one seam is the root.
    - `semi` — you hold the top of the tree (by default the upper half of its depth, the root alone on a one-level plan; `boundary=k` holds depths 0…k−1)
      and registered executors of this project hold everything below it; you make the issuer's moves
      over what you hold, the system makes them below.
    - `auto` — the system holds every node, the root included; you stay the root's issuer — the
      customer — state the goal, and read its status. You do not intervene: the system makes every
      issuer move, and the project refuses your structuring and validation verbs on its nodes.

    The choice is the USER's: recommend `auto` and go on, unless they ask for another. It governs nodes
    issued AFTER it (an issued node keeps its Del). A mode that needs executors is refused until this
    project has them: auto needs two (the root and its children must be different executors, or the
    children would self-verify with no validator between them), semi needs one, and every mode — solo
    included — needs a validator: the system validates at every seam and at the top of every part of the
    plan larger than one session, whoever holds the node.

    `perform` — HOW you perform the nodes you hold (solo: all, semi: the top; auto: none): `dispatch` (default) —
    you consent and stay their executor, and the system performs each in a clean session of this project's
    registered executor, started only after your ACCEPT, in the node's own place; `in_chat` — you do the work
    yourself, with your own tools, and nothing keeps it inside the contract but you.

    Once the project has work in it, a change of mode is the person's own, from their page; a setting changed then needs
    `user_said`, the user's own words asking for it, recorded with it.

    What the project sets for itself, recorded with the mode (unset = the server's): `system_model` — the model the
    system's own roles run on here (its issuer, its plan's reviewer, and its author unless named apart); `planner_model`
    — the model that AUTHORS the plan (`auto_decompose`, `plan`, `refine_plan`), when it is to be another than the
    system's: a stronger author once, the system's roles after it; `l2_gate` — whether the plan's
    Level-2 review gates execution (off: the plan was verified where it was authored); `deadline_s` — how far ahead a
    deadline nobody typed is written; `bounds` — each waiting state's own bound here, `{STATE: seconds}` over
    OFFERED, CHALLENGED, BLOCKED, VALIDATING, ESCALATED, CANCELLING (a person who signs answers in days, a run's
    validator in minutes), replacing the project's previous `bounds` whole, `{}` = the defaults — days to months where
    a person owns the wait (you under solo, or over what you hold under semi), the server's where the system does; OFFERED, CHALLENGED and
    BLOCKED also end at the packet deadline, whichever comes first (§12.2), so a long wait the system owns needs `deadline_s` too; `max_iterations` — the rework rounds a node issued here
    without its own bound gets; `intent_check` — whether the go of a plan file adds the root criterion
    `answers_the_persons_words`, read by the validator against the person's recorded words (on where the person holds
    the root's work — solo or semi, `in_chat` — off elsewhere, unless set; turned only with `user_said`, the person's
    words, at any time); `observe` — whether the system runs a node's pinned checks once on its
    place before an executor session and hands it what they printed (on unless set off; `observe.observe_place`);
    `network` — how far this project's container reaches out, where its execution is a container: `open` (everything but
    your host), `off` (nothing), or `{"mode": "allowlist", "hosts": [...]}` (only the named hosts, on 443, through one
    gateway) — it only narrows the execution's own declaration, the more closed of the two holding (the operator's is a
ceiling), `declared` to follow that alone again; a turn ends the project's running container at once. Under
    `allowlist` and `off` a session still reaches its model through the project's model door — list no provider host
    for it (SECURITY.md); the answer names the switch in force, `network_in_force`.

    `workdir` — the top of the repository the work is in: where this project has no validator yet, `<project>-val` is
    registered there (`register_agent`, on `system_model`), so the setup of a small task is this one call; refused,
    the mode leaves none registered.

    `node` — refused, kept so an older page is told why: a seam the person issues to a name that works in a chat is held
    solo there by that name's own act (`act_as`), with nothing set at a node (§10.4: autonomy per task and role).

    Without `mode`, only the settings named change — who holds what stays as recorded (a switch turned mid-run)."""
    try:
        m = None if mode is None else Mode(str(mode).strip().lower())
    except ValueError:
        return {"refused": True, "error": f"mode must be one of solo | semi | auto, got {mode!r}"}
    if no := (_NOTHING_AT_A_NODE if node is not None else _not_the_persons(engine, m, user_said)):
        return no
    # …at any time, before the go too: the default stands for the person against the agent whose work it reads, and
    # only their words turn it (critic over de23af3)
    if intent_check is not None and not str(user_said).strip() and not ((p := CALLER.get()) is not None and p.a_page):
        return {"refused": True, "error": f"`intent_check` — whether the system reads the result against the person's "
                                          f"own words ({INTENT}) — is the person's to turn: ask them, and pass their "
                                          f"words asking for it as `user_said`"}
    if m is None and (boundary is not None or perform is not None or workdir is not None):
        return {"refused": True, "error": "boundary, perform and workdir belong to a mode: name the mode with them"}
    perform = perform or "dispatch"
    if perform not in ("dispatch", "in_chat"):
        return {"refused": True, "error": f"perform must be dispatch | in_chat, got {perform!r}"}
    if perform == "in_chat" and client_kind() == "chat":
        return {"refused": True, "error": "`in_chat` is the work done by your own tools, and this client has only the "
                                          "gfso verbs: `dispatch` has the system perform in your name what you hold"}
    settings = _settings_given(system_model, planner_model, l2_gate, deadline_s, observe, network, bounds, max_iterations,
                               intent_check)
    if isinstance(settings, str):
        return {"refused": True, "error": settings}
    # …asked of the roster, not of the declaration: an unreadable declaration still names a container, whose switch the
    # user must be able to store (it holds the way out shut meanwhile, `execution_of`)
    no_container = {"refused": True, "error": "this project's sessions run on this host — no execution is declared for its "
                                              "roles (`register_agent(..., execution=)`) — so there is no container whose "
                                              "network a switch could turn"}
    if m is None and network is not None and declaring_role(engine) is None:
        return no_container
    if m is None:
        if not settings:
            return {"refused": True, "error": "name a mode, or a setting of this project to change"}
        rec = engine.set_settings(settings, AgentId(agent or caller_id()), said=str(user_said).strip())
        return {**rec, **(_turn_the_way_out(engine) if network is not None else {}), **_short_supplied(engine)}
    # …the project's executors that name no execution placed in the default as the mode is set — the door registers
    # first and sets the mode after, and a registration saw no mode (critic); moved back where the mode is refused, or
    # a refusal shut the user's other choices — in their chat, on this host (critic)
    def held() -> dict:
        """The mode recorded, its staffing read once the default holds the executors — or the refusal."""
        if network is not None and declaring_role(engine) is None:      # …asked here: the default has placed them by now
            return no_container
        staff = mode_staffing(engine, m.value, perform)
        pool, dispatch = [AgentId(a) for a in staff["executors"]], staff["dispatch"]
        if not staff["ready"]:
            return {"refused": True, "error": staff["missing"], "executors": staff["executors"]}
        try:
            rec = engine.set_mode(m, boundary, AgentId(agent or caller_id()), said=str(user_said).strip(),
                                  hands=str(pool[0]) if dispatch else None, settings=settings)
        except ValueError as e:
            return {"refused": True, "error": str(e)}
        return {**rec, "executors": [str(a) for a in pool],
                "holds": {"solo": "you hold every node",
                          "semi": f"you hold depths below {holder_boundary(engine.graph)}; the system the rest",
                          "auto": "the system holds every node; you are the customer"}[m.value]}
    out = _with_its_validator(engine, workdir, system_model, lambda: _in_the_default(
        engine, {"mode": m.value, **({} if m == Mode.AUTO else {"perform": perform})}, held))
    return {**out, **(_turn_the_way_out(engine) if network is not None and not out.get("refused") else {}),
            **({} if out.get("refused") else _short_supplied(engine))}


def _his_intent(engine: Engine, criteria: list, seam: bool, agent: bool = True) -> list:
    """`criteria` as the person's act on a seam he issues to another (`seam`, `persons_node`) installs them — its first
    ASSIGN or a revision he makes: with `answers_the_persons_words` where `intent_check` holds there and they do not
    carry it (his 11-19 «по умолчанию»). The counterpart of his go on his own root; never written by a move of the
    system's, nor mapped: CHECK-1 flags it uncovered at the revision (§12.10), and the seam's holder maps it by its own
    re-admission. While `intent_check` holds, a revision of his that leaves it out gets it back: it is his by default,
    and the page's switch turns it off. Present iff the seam's Del is an agent of the system (`agent`, `_by_an_agent`):
    dropped where it is a human. A call no door served is the system's own, never his act."""
    if not seam or CALLER.get() is None:
        return criteria
    if not agent:
        return [c for c in criteria if c.get("name") != INTENT]
    if not engine.intent_check(seam=True) or any(c.get("name") == INTENT for c in criteria):
        return criteria
    return [*criteria, json.loads(json.dumps(INTENT_CRITERION))]


def _by_an_agent(engine: Engine, held, task=None) -> bool:
    """Does `held` execute a seam of his as an agent of the system — the one classification the default checker reads
    too (`validation.classify_executor`, `executed_by_a_human`): read now at an issue or a re-ASSIGN, the very reading
    its ASSIGN records; as recorded at a revision of `task`'s version. A human's work — meetings, another repository —
    leaves nothing here a pinned probe could read: the words criterion's pin read this repository's `git log`, deciding
    nothing of that work, and a criterion pinning no runnable probe decides nothing either (A1). He checks a human's
    node himself by default, reading his own words; a criterion restating them adds no check, so his criteria there are
    the ones he writes."""
    return not (engine.executed_by_a_human(task.id) if task is not None else a_human(engine.graph, held))


def _his_criteria_mapped(engine: Engine, parent_id, children, mappings) -> list:
    """`children` with each criterion of `parent_id` this act newly maps onto a standing top written into that top's
    packet: his criterion reaches the seam he issued as a criterion of its contract (MODE_PER_SUBTREE §6.1 point 2), the
    top re-issued once and its holder consenting again (Inv-1) — a mapping alone left its packet silent on what it now
    answers for. Elsewhere a child's criteria are its own, as given."""
    parent = engine.graph.get_task(TaskId(str(parent_id)))
    if parent is None or not isinstance(children, list) or not all(isinstance(c, dict) for c in children):
        return children or []
    had = {(m.criterion_name, str(m.child_id)) for m in parent.criterion_mappings}
    his = {c["name"]: c for c in its_criteria(parent)}
    named = {str(c.get("task_id")): c for c in children}
    asked = [(str(m.get("criterion_name")), str(m.get("child_id"))) for m in mappings or () if isinstance(m, dict)] + [
        (str(n), str(c.get("task_id"))) for c in children for n in c.get("covers") or ()]
    for name, kid in dict.fromkeys(asked):
        k = engine.graph.get_task(TaskId(kid))
        if (name, kid) in had or name not in his or k is None or not engine.issued_by_the_person(k.id):
            continue
        c = named.get(kid) or {"task_id": kid, "spec": {}, "assignee": str(k.assignee)}
        crits = list(c["spec"]["criteria"] if "criteria" in c.get("spec", {}) else its_criteria(k))
        if all(x.get("name") != name for x in crits):
            named[kid] = {**c, "spec": {**c.get("spec", {}), "criteria": [*crits, his[name]]}}
    return [named.pop(str(c.get("task_id")), c) for c in children] + list(named.values())


def _with_his_intent(fn, *, issued: bool):
    """`fn`, a verb that issues children (`issued`: `parent_id`/`children`), revises a node's criteria or re-issues it to
    another (`assignee`), with the criterion his act installs on each seam he issues to another (`_his_intent`). His act
    alone: a seam's issuer is him, and every issuer move there is his words or his page (`_the_persons_move`,
    `Engine._the_persons_packet`)."""
    sig = inspect.signature(fn)

    def spec(e, s, seam, agent):
        """`s` with its criteria as his act installs them, where it names criteria."""
        return ({**s, "criteria": _his_intent(e, list(s["criteria"]), seam, agent)}
                if isinstance(s, dict) and "criteria" in s else s)

    @functools.wraps(fn)
    def _call(*a, **kw):
        at = sig.bind(*a, **kw).arguments
        e = at["engine"]
        if issued and at.get("parent_id"):
            p = e.graph.get_task(TaskId(str(at["parent_id"])))
            seam = lambda held: p is not None and his_seam(p.assignee, held)
            if "children" in at:
                at["children"] = [{**c, "spec": spec(e, c["spec"], seam(c.get("assignee")),
                                                     _by_an_agent(e, c.get("assignee")))}
                                  if isinstance(c, dict) and "spec" in c else c
                                  for c in _his_criteria_mapped(e, at["parent_id"], at["children"], at.get("mappings"))]
            else:
                at["spec"] = spec(e, at.get("spec"), seam(at.get("assignee")), _by_an_agent(e, at.get("assignee")))
        elif "assignee" in at and not issued:
            # …a re-ASSIGN handing a seam of his to another Del: the words criterion follows the new Del as its ASSIGN
            # will classify it — added for an agent of the system, dropped for a human —, as one version before it (§12.3:
            # a version moving Del alone carries no criteria)
            t = e.graph.get_task(TaskId(str(at["task_id"])))
            if t is not None and his_seam(e.graph.issuer_of(t.id), at["assignee"]) and (
                    now := _his_intent(e, its_criteria(t), True, _by_an_agent(e, at["assignee"]))) != its_criteria(t):
                _tools.edit_criteria(e, str(t.id), now, agent=str(e.graph.issuer_of(t.id)))
        elif not issued and (t := e.graph.get_task(TaskId(str(at["task_id"])))) is not None and t.parent_id \
                and his_seam(e.graph.issuer_of(t.id), t.assignee):
            # …his revision is a version he signs, so it is his seam by `his_seam`'s own rule; a root's is its go's
            if "criteria" in at:
                at["criteria"] = _his_intent(e, list(at["criteria"] or ()), True, _by_an_agent(e, t.assignee, t))
            else:
                at["spec"] = spec(e, at.get("spec"), True, _by_an_agent(e, t.assignee, t))
        out = fn(**at)
        # …and a seam of his issued where no validator is staffed: named at its issue, not found missing at his PASS
        if issued and at.get("parent_id") and (lift := next(filter(None, (
                e.staffs_his_seam(k.id) for k in e.graph.get_children(TaskId(str(at["parent_id"]))))), None)):
            e.emit_info("validator", f"a seam the person issued under {at['parent_id']} is checked by the project's "
                                     f"validator before his PASS, and none is registered: {lift}")
            out = {**out, "staff": lift} if isinstance(out, dict) else out
        return out
    return _call


def its_criteria(t) -> list[dict]:
    """A node's criteria as a door takes them: each with its checks and the producers it reads."""
    return [{"name": c.name, "description": c.description, "check": [p.to_dict() for p in c.check],
             **({"depends_on": list(c.depends_on)} if c.depends_on else {})} for c in t.spec.criteria]


def _with_its_validator(engine: Engine, workdir: Optional[str], model: Optional[str], held) -> dict:
    """`held()` — the mode recorded, or its refusal — with the project's validator registered at `workdir` before it
    where the project has none (`register_agent`, the roster's one door; `validator` in the answer), and taken off again
    where the mode is refused: every mode needs one (`mode_staffing`), and the setup of a small task was three calls
    for one choice (e2e5 G_3)."""
    if workdir is None or _validators_of(engine, staffed(engine)):
        return held()
    val = register_agent(engine, f"{engine.project_name or DEFAULT_PROJECT}-val", "llm-validator",
                         model=str(model).strip() if model and str(model).strip() else MODEL_DEFAULT, workdir=workdir)
    if val.get("refused") or val.get("error"):
        return {"refused": True, **val}
    if (out := held()).get("refused"):
        unregister_agent(engine, val["registered"], val["workdir"])
        return out
    return {**out, "validator": {k: val.get(k) for k in ("registered", "model", "workdir")}}


def _short_supplied(engine: Engine) -> dict:
    """The live nodes standing on a deadline the engine supplied with under half of the default now written for their
    performer left. A deadline is a packet field: it moves by a revision, the issuer's act, re-offered for consent
    (Inv-1) — never by the system rewriting it under the choice just made — so they are named, and how to extend them."""
    g, now = engine.graph, project_now(engine.graph)
    short = sorted(str(t.id) for t in engine.all_tasks() if t.state not in TERMINAL_STATES and t.deadline_supplied
                   and t.deadline is not None and (span := project_deadline_s(g, t.assignee, g.issuer_of(t.id)))
                   and (t.deadline - now).total_seconds() < span / 2)
    if not short:
        return {}
    days = round(max(project_deadline_s(g, t.assignee, g.issuer_of(t.id)) for t in engine.all_tasks()
                     if str(t.id) in short) / 86_400)
    return {"short_deadlines": short,
            "say": (f"Tell the person: {len(short)} live node(s) ({', '.join(short[:10])}{', …' if len(short) > 10 else ''}) "
                    f"keep the deadline written before this choice, under half of the {days} day(s) now written for such "
                    f"work. A deadline changes only by its issuer's revision — `revise(id, deadline=…)`, which re-offers "
                    f"the node — so the system leaves them as they are.")}


def _not_the_persons(engine: Engine, m: Optional[Mode], user_said: str) -> Optional[dict]:
    """The refusal of a change to a project with work in it that is not the person's: a mode (`in_chat` with it) only
    from their page, signed by it, never the standing agent's connection — an AUTO customer that met a stall passed
    `user_said="the person wants solo"` and took the nodes (measured live); a setting with their words. A call no door
    served is the system's own."""
    if not engine.all_tasks() or (p := CALLER.get()) is not None and p.a_page:
        return None
    if m is not None and p is not None:
        return {"refused": True, "error": "who holds this project's work, once it has work, is the person's own choice, "
                                          "made from their page (`gfso ui` signs it in), not by an agent's connection: "
                                          "tell them what you would change and why"}
    if not str(user_said).strip():
        return {"refused": True, "error":
                "this project already has work in it, and who holds it is the USER's choice: ask the "
                "user, and pass their own words asking for the change as `user_said`."}
    return None


def _in_the_default(engine: Engine, mode: dict, held) -> dict:
    """`held()` — the mode recorded, or its refusal — with the project's executors that name no execution placed in the
    default meanwhile (`_default_execution`), and moved back on any way out but the mode recorded: one that raised past
    the refusals left them in the container and the user with no choice left (critic: a moved executor's workdir gone
    made the move itself raise half done)."""
    agents = staffed(engine)
    default = _default_execution(engine, mode, agents)
    if default and (gone := [a for a, c in _movable(engine, agents).items() if not os.path.isdir(c.get("workdir") or "")]):
        return {"refused": True, "error": f"executor(s) {', '.join(gone)} of this project name a workdir that no longer "
                                          f"exists: `unregister_agent` them, or register them again on an existing one"}
    moved, out = [], {"refused": True}
    try:
        if default:
            _executors_into(engine, default, agents, moved=moved)
        out = held()
        return out
    finally:
        if out.get("refused"):
            _executors_into(engine, None, agents, moved)


def _turn_the_way_out(engine: Engine) -> dict:
    """Read the project's switch NOW: a turned one ends its running container at once (`WayOut.switch`), not at the
    next session's lookup — a session already out under the old one stays out until then (critic). The switch IN FORCE,
    the declaration's ceiling applied: asked `open` under a declared `off`, the user must not read "open" (review)."""
    try:
        mode, hosts = where_it_runs(engine).way.network
    except (ValueError, KeyError):
        mode, hosts = "off", ()             # an unreadable switch or declaration has shut the way out already
    return {"network_in_force": {"mode": mode, "hosts": list(hosts)}}


def list_agents(engine: Engine, match: str = "", limit: int = 25) -> dict:
    """The delegation roster {agent_id → kind/model/workdir}. Unlisted ids = humans. SERVER-WIDE,
    not per project: every session of the one server shares it, so it holds other people's roles
    too, and an executor with no `validator` of its own inherits the first llm-validator in it —
    check `will_be_validated_by` when you register.

    `match` keeps only ids containing it — the roster is shared and grows with every run, and a
    caller who registered two roles was answered with forty-five (~4.5k tokens of other people's
    work) and had to read all of them to find their own (measured on the human door 2026-08-22).
    `limit` (default 25, 0 = all) bounds the rest; both are about the READING, not about isolation:
    the roster really is shared, which is why the answer keeps saying so."""
    # …and say so IN the answer, because `project=` rides on every verb and this is the one where it
    # selects nothing: a caller passed it, got other runs' roles back, and could not tell whether the
    # argument had been ignored or the roster really is shared (measured on the agent door
    # 2026-08-21).
    # The roles under their OWN key, never mixed into the map. Adding the note beside them as a
    # sibling entry put a STRING where every reader expects a role config: the measurement arm's
    # preflight iterated the map and died on `'str' object has no attribute 'get'` (2026-08-22, my
    # own change). A map of roles is a map of roles.
    _reg = staffed()
    _all = _reg.list()
    # …AND WHO WOULD VALIDATE EACH EXECUTOR, which the roster never showed. `validator: null` on every
    # entry means "no per-executor override", not "nobody" — the binding is by workspace and is
    # decided at validation time — so `register_agent`'s promise ("will_be_validated_by: w16-val-1") was
    # unconfirmable from anywhere afterwards (measured on the agent door 2026-08-22).
    _all = {a: ({**c, "validated_by": _reg.validator_for(a, project=c.get("project"))} if c.get("kind") == "llm-executor" else c)
            for a, c in _all.items()}
    _kept = {a: c for a, c in _all.items() if not match or match in a}
    # YOURS FIRST, and counted. The roster being server-wide is the design and the answer says so;
    # what it did not do is let a reader SEE which of the twenty-five rows are theirs. Two doors in
    # wave 26 (2026-09-06) passed `project=` and read the other seventeen projects' roles — with
    # their absolute workdirs — as a leak. It is not one, but "you can filter by `match` if you
    # happened to name your roles with a prefix" is not an answer either. Roles carry their project,
    # so the ordering can.
    # The roster is readable WITHOUT a graph — it is a server fact, not a project one, and one
    # caller reads it with no engine at all. Then nothing is "yours", which is the truth.
    _mine = engine.project_name if engine is not None else None
    # "Yours" means REGISTERED UNDER THIS PROJECT. An unscoped role belongs to nobody in particular
    # (the scope text says so) and must not be counted as yours — with no project at all, `None ==
    # None` made every unscoped row "mine", which is the reading this field exists to prevent.
    _is_mine = (lambda c: bool(_mine) and c.get("project") == _mine)
    _ordered = sorted(_kept.items(), key=lambda kv: (not _is_mine(kv[1]), kv[0]))
    out = {"agents": dict(_ordered[:limit]) if limit else dict(_ordered),
           "total": len(_all),
           "yours": [a for a, c in _ordered if _is_mine(c)],
           "scope": "server-wide: this roster is shared by every session and project of the one "
                    "server. `project=` selects the GRAPH, never the roster — the ids you see "
                    "include other people's roles. Yours (registered under this project) are listed "
                    "in `yours` and sorted first; an UNSCOPED role belongs to nobody in particular "
                    "and is shared by design."}
    if len(out["agents"]) < len(_all):
        out["note"] = (f"{len(_all)} roles registered; showing {len(out['agents'])}"
                       + (f" matching {match!r}" if match else "")
                       + ". `match=<substring>` filters (yours share a prefix if you gave them one), "
                         "`limit=0` returns all.")
    return out


# Re-exported so a door asking "may this verb create a project" has ONE place to ask, the same
# place it gets the verbs themselves (`gfso.tools` owns the set).
# One owner for "did the verb refuse" — both doors ask it (see `gfso.tools`).
is_refusal = _tools.is_refusal
PROJECT_CREATING_VERBS = _tools.PROJECT_CREATING_VERBS
PROJECTLESS_VERBS = _tools.PROJECTLESS_VERBS
MAKES_A_PROJECT = _tools.MAKES_A_PROJECT
opened_for = _tools.opened_for


def issued_by_the_person(engine, name: str) -> bool:
    """Whether a node of `engine`'s graph is held by `name` and its Del was the person's to set (§10.1): issued by him,
    or a root self-assigned to it — made at a door, every caller of which is the person locally; the system's roles
    split, they make no root."""
    g = engine.graph
    return any(str(t.assignee) == name and (str(i := g.issuer_of(t.id)) in FOR_THE_PERSON
                                            or (g.get_parent(t.id) is None and str(i) == name))
               for t in g.all_tasks())


def how_the_checker_signs(engine: Engine, task_id) -> str:
    """Where the party named to check `task_id` is no name anyone can sign as yet — not the person's, none of his names
    (issued or registered), no Del he set —, how it comes to sign: else ""."""
    who = engine.named_checker(TaskId(str(task_id)))
    if not who or who in PERSONS_NAMES or who in signin.names_of(signin.LOCAL_PERSON) or issued_by_the_person(engine, who):
        return ""
    return f"{who} signs by `gfso agent {who}` (a credential issued once)"


def set_checker(engine: Engine, task_id: str, checker: str = "validator", user_said: str = "", agent: str = "") -> dict:
    """WHO CHECKS a node — `"self"`, its issuer himself (`validate_result` still checks it whenever called),
    `"validator"`, the project's validator observing each delivery by itself, its PASS standing on that record, or a
    party BY NAME (`get_task`'s `checker_choices`: never its executor), its PASS waiting on that party's
    `record_verdict`. Either way the signature is the issuer's (§10.2). The person's choice: pass their words asking for it as `user_said`. At a
    node he issues it is his at a seam too, §10.3 asking there only that the check is not the executor's: by default
    himself, and the validator between him and his own agent in his chat. Below a mode scope's top it is that top's
    holder's own choice, the inner node's issuer (§10.3): no words of the person's."""
    inside = (s := engine.scope_at(task_id)) is not None and s["top"] != str(task_id)
    if not inside and not str(user_said).strip() and not ((p := CALLER.get()) is not None and p.a_page):
        return {"refused": True, "error": "who checks a node is the person's to choose: ask them, and pass their words "
                                          "asking for it as `user_said`"}
    try:
        held = engine.set_checker(TaskId(task_id), str(checker), AgentId(agent or caller_id()), user_said,
                                  on_his_page=(p := CALLER.get()) is not None and p.a_page)
    except ValueError as e:
        return {"refused": True, "error": str(e)}
    by_itself = engine.observes_by_itself(TaskId(task_id)) and engine.validator_staffed()
    return {"task_id": task_id, "checker": checker, "checked_by_the_validator": held,
            "say": ((f"the validator now checks each delivery of {task_id} by itself" if by_itself else
                     f"no validator here observes {task_id} by itself: after each delivery call "
                     f"validate_result('{task_id}')") + ", and its PASS stands on that record; you sign it"
                    if checker == "validator" else
                    f"{task_id} is checked by you, its issuer, and you sign it; `validate_result` checks it when called"
                    if checker == "self" else
                    f"{checker} checks each delivery of {task_id} — `record_verdict` by its own credential — and your "
                    f"PASS waits on its PASS record; its FAIL binds (Inv-2). You sign it"
                    + (f". {signs}" if (signs := how_the_checker_signs(engine, task_id)) else ""))}


def canon(engine: Engine, section: str = "") -> dict:
    """THE THEORY GFSO IS BUILT ON, for when the person asks why it works this way or whether it holds at all — read the
    chapter the question is about before answering, and answer from it, citing the section: a guess about the design
    is not an answer. No `section`: the reading map and every heading. `section='12'` a chapter, `'12.4'` one section.
    The text of this version (a checkout's own file, or this release's on GitHub)."""
    return _canon.read(section)


def unchecked_self_pass(engine: Engine, tid, source) -> str:
    """The reminder before an internal node's own holder signs its PASS — its issuer is its holder, so it
    self-verifies (§10.3) and no validator is imposed —, where no check but its holder's own stands on the current
    delivery: an external check is the holder's to ask, never the system's rule (the author, 2026-11-21: «только по
    явному желанию но с напоминанием своевременно»). "" where an external check stands, or the node is no internal one
    of `source`'s — a root is a tree's top, and a seam the person issues has its obligatory check."""
    t = engine.graph.get_task(tid)
    if t is None or engine.graph.get_parent(tid) is None or t.state != State.VALIDATING or str(t.assignee) != str(source) \
            or str(engine.graph.issuer_of(tid)) != str(source) or engine.persons_seam(tid) \
            or engine.issued_by_the_person(tid) or engine.pass_blocked_by(tid):
        # …a PASS the gate refuses is told by its refusal, never offered as signable
        return ""
    if (rec := engine.current_exec_verdict(tid)) and str(rec.get("validator") or "") not in ("", str(source)):
        return ""
    return (f"no external check was made of {tid} — sign anyway? Repeat with confirm=true, or call "
            f"validate_result('{tid}') first")


def _reminded_before_a_self_pass(fn):
    """`fn` (`signal`), where a PASS `unchecked_self_pass` reminds of first is answered with the reminder and
    `confirm_needed` — no refusal, nothing written — until it is repeated with `confirm=true`. The person's own page is
    never reminded: his click is his explicit act, and the reminder is for an agent («агент … может получать
    напоминание»)."""
    @functools.wraps(fn)
    def call(engine, task_id, signal, source, **kw):
        """`fn`, or the reminder it waits behind."""
        page = (p := CALLER.get()) is not None and p.a_page
        if (str(signal).strip().upper() == Verdict.PASS.value and not kw.pop("confirm", False) and not page
                and (why := unchecked_self_pass(engine, TaskId(task_id), source))):
            return {"accepted": False, "confirm_needed": True, "reminder": why}
        kw.pop("confirm", None)
        return fn(engine, task_id, signal, source, **kw)
    return call


@functools.wraps(_tools.signal)
def signal(engine: Engine, task_id: str, signal: str, source: str, **kw) -> dict:
    """`tools.signal`, where a DELIVER whose sender performs the node in its own chat carries a commit of the project's
    repository — what its sender names (`place`: a work tree's or clone's HEAD, or a commit id), else the tip of the
    work's branch past where the work started (`_work_tip`), else refused, its lifts named (`_unnamed`): never a HEAD
    by inference, the person's main tree's or the judge's directory's. Admitted only
    once every refusal its sender lifts has passed and the commit is taken whole into the project's store
    (`store.admit`, read only) — nothing written before —, and kept there by its id once accepted
    (`store.keep`); what is not committed is no part of it, and the answer names it (`not_delivered`). Without it the
    judge copied that directory as it stood when it came, so what was written there after DELIVER was judged as
    delivered (§11.3: the result as it stands at DELIVER). A party whose session the system runs records its own
    place's commit (`reports.committed_place`); a directory inside a work tree delivers that tree's commit, and one in
    none is refused before any write, its lift named. An ACCEPT of such a chat carries the HEAD that repository stood
    on when the work was taken, and the repository: where and from when a node is at work in it, as the system's own record
    (`past.spans`). Either records the repository by its main worktree (`W.main_worktree`): a linked worktree is
    removed once its work is merged, and the record must outlive it."""
    said, tid, sig, after, unaccepted = {}, TaskId(task_id), str(signal).strip().upper(), [], []
    named = kw.pop("place", "") or None
    # …a commit id named, read in the git the chat's place stands in
    commit = named if named and re.fullmatch(r"[0-9a-fA-F]{7,40}", named) else None
    named = None if commit else named
    if sig == "ACCEPT" and (place := chat_place(engine, source, tid, named)) and W.is_repo_top(place) and (
            head := W.git(place, "rev-parse", "--verify", "-q", "HEAD^{commit}").stdout.strip()):
        # …where the work goes on the system's branch, it starts from that branch's tip once it exists: the person's
        # own commit between two takes was the start, and honest work on the branch could descend from it no way
        # (critic over 1d84a75: a part after his commit, a REOPEN after a PASS)
        if switches_branches(engine, tid) and (wb := W.git(place, "rev-parse", "--verify", "-q",
                                                         f"refs/heads/{work_branch(engine)}^{{commit}}").stdout.strip()):
            head = wb
        kw["_recorded"] = (None, head, W.main_worktree(place))
        if switches_branches(engine, tid) and (theirs := on_their_branch(engine, place)):
            said["say"] = theirs
    deliver = sig == "DELIVER" and (st := engine.graph.get_state(tid)) in (State.EXECUTING, State.REWORKING)
    if deliver and (place := chat_place(engine, source, tid, named)):
        if named and (no := not_its_repository(engine, named)):
            return {"accepted": False, "refused": True, "state": st.name, "error": f"NOT delivered — {no}"}
        # …a directory inside a work tree delivers that tree's commit: no directory is judged as it stands
        top = W.git(place, "rev-parse", "--show-toplevel").stdout.strip() if not W.is_repo_top(place) else place
        if top and W.is_repo_top(top):
            no, got = a_chats_delivery(engine, tid, top, commit or ("HEAD" if named else None))
            if no:
                return {"accepted": False, "state": st.name, **no}
            kw["_recorded"], keep = got.pop("_recorded"), got.pop("keep")
            unaccepted.append(got.pop("drop"))
            said.update(got)
            after.append(keep)
        else:
            # …refused, nothing written: accepted, no judge could read it and no verdict could ever come. Only a
            # project with no directory at all — a goal acted out in the world — delivers its report alone
            return {"accepted": False, "refused": True, "state": st.name,
                    "error": f"NOT delivered — {place}, where this node's judge stands, is in no git work tree with a "
                             f"commit, and no judge reads a directory as it stands: commit your work in a repository "
                             f"and DELIVER again, or name the work tree it is committed in (`place=`)"}

    if sig == "DELIVER" and (rec := kw.get("_recorded")):
        try:
            after.append(past.delivered(engine, rec[2], task_id, rec[1]))  # …its range read while git still holds it
        except OSError:
            pass                                                        # …a measure's record, never the delivery's refusal
    try:
        out = _tools.signal(engine, task_id, signal, source, **kw)
    except BaseException:
        for act in unaccepted:
            act()
        raise
    if out.get("accepted") and sig == Verdict.PASS.value and (back := back_to_their_branch(engine, tid)):
        said["say"] = back
        # …and on the feed: signed from the person's page, the PASS's answer goes to the page, and the chat hears it there
        engine.emit_info("verdict", f"{tid}: {back}")
    for act in after if out.get("accepted") else unaccepted:   # …the keep, or what an admission verified, gone
        act()
    return {**out, **said} if said and out.get("accepted") else out


#: …and `confirm`, the holder's answer to the reminder before a self-signed PASS (`unchecked_self_pass`); and `place`,
#: the work tree, clone or commit id of the project's repository a chat's DELIVER names (`a_chats_delivery`)
signal.__signature__ = (lambda sig: sig.replace(parameters=[*sig.parameters.values(), inspect.Parameter(
    "confirm", inspect.Parameter.KEYWORD_ONLY, default=False, annotation=bool),
    inspect.Parameter("place", inspect.Parameter.KEYWORD_ONLY, default="", annotation=str)]))(
    inspect.signature(_tools.signal))


@functools.wraps(_tools.metrics)
def metrics(engine: Engine) -> dict:
    """`tools.metrics`, with the work past the system its records measure: the commits no record of the system holds
    (`past.past_the_system`), and the writes a console's witness saw (`past.witness`) — defects counted beside the
    others, never refused."""
    seen = engine.witnessed_writes()
    return {**(out := _tools.metrics(engine)),
            "past_the_system": past.past_the_system(engine, default_agents()),
            "witnessed": {"count": witnessed_count(seen), "last": seen[-5:]},
            "means": {**out["means"], **{k: DIAGNOSTIC_MEANS[k] for k in ("past_the_system", "witnessed")}}}


def _with_the_persons_words(fn, move: str = Signal.ASSIGN.name):
    """`fn` taking `user_said` — the person's own words on this act — carried to the engine's one door every act that
    installs a packet passes — a re-ASSIGN, an ACCEPT_CHALLENGE (`engine.PERSONS_WORDS`, read by
    `Engine._the_persons_packet`): under `solo` and `semi` a root's criteria change only on them, recorded on the
    feed for the person to see. The same door asks for them where the move on its node is the person's
    (`_the_persons_move`): a signal by its name, any other act as `move`."""
    sig = inspect.signature(fn)
    own = "user_said" in sig.parameters

    @functools.wraps(fn)
    def _call(*a, user_said: str = "", **kw):
        token = PERSONS_WORDS.set(str(user_said or ""))
        try:
            if "task_id" in (got := sig.bind_partial(*a, **kw).arguments) and (no := _the_persons_move(
                    got["engine"], TaskId(str(got["task_id"])), str(got.get("signal", move)).strip().upper())):
                return no
            return fn(*a, **({"user_said": user_said} if own else {}), **kw)
        finally:
            PERSONS_WORDS.reset(token)
    if not own:
        _call.__signature__ = sig.replace(parameters=[*sig.parameters.values(), inspect.Parameter(
            "user_said", inspect.Parameter.KEYWORD_ONLY, default="", annotation=str)])
    return _call


_RAW_TOOLS = {
    **_tools.TOOLS,
    "signal": _with_the_persons_words(_reminded_before_a_self_pass(signal)),                                                                 # a chat's delivery recorded
    "metrics": metrics,                                                               # work past the system counted
    "create_task": _with_his_intent(create_task, issued=True),
    "decompose": _with_his_intent(_tools.TOOLS["decompose"], issued=True),
    "auto_decompose": _with_the_persons_words(_tracked("auto_decompose", auto_decompose)),
    **{n: _with_the_persons_words(_with_his_intent(_tools.TOOLS[n], issued=False) if n in ("revise", "edit_criteria")
                                  else _tools.TOOLS[n])
       for n in ("revise", "edit_criteria", "edit_scope", "edit_accepted_risks")},
    "reassign": _with_the_persons_words(_with_his_intent(_tools.TOOLS["reassign"], issued=False), REASSIGN),
    "plan": plan, "refine_plan": refine_plan,         # a plan with no project, written in its own thread (`_once`)
    "review_decomposition": _tracked("review_decomposition", review_decomposition),   # L2, §9.1
    "validate_result": _tracked("validate_result", validate_result),                  # §10.1
    "set_checker": set_checker,                                                       # §10.2, the issuer's
    "register_agent": register_agent, "unregister_agent": unregister_agent, "list_agents": list_agents,                     # the roster
    "set_mode": set_mode,                                                             # who holds what
    "stop_project": stop_project, "start_project": start_project,                     # the run's switch
    "next_steps": next_steps,
    "canon": canon,                                                                   # the theory, by its sections
}

def _mode_lock(name: str, fn):
    """Refuse, at a door, a move the project's mode gave to the system — checked at the doors only: the system's own
    moves (the dispatcher, the issuer function) call the verbs in-process, so the lock binds the people and agents
    outside and never the system it hands the work to. The key and the holder are `engine.moves`' (`DOOR_KEYS`,
    `door_holder`), the ones every offering sentence is built from.

    Under AUTO the user-agent is the customer and does not intervene: every move but stating the goal
    (`auto_decompose` on a project with no root yet) is refused. Under any mode, a move whose owner the
    mode made a system executor is refused. With no mode set nothing changes."""
    if name not in DOOR_KEYS:
        return fn
    sig = inspect.signature(fn)
    key = DOOR_KEYS[name][0]

    @functools.wraps(fn)
    def _call(*a, **kw):
        try:
            args = sig.bind(*a, **kw).arguments
        except TypeError:
            return fn(*a, **kw)                  # the door answers a malformed call in its own terms
        engine, node = args.get("engine"), args.get(key)
        if engine is None or args.get("writing"):        # …a read by handle moves nothing
            return fn(*a, **kw)
        if (holder := door_holder(engine, name, node, args.get("signal"))) is None:
            # …AND SIGNED BY WHO HOLDS THE ROLE: an unsigned move is the door's standing identity's, and one by anyone
            # else was taken and logged as the holder's (ui's human-door critic, 2026-11-14)
            if (due := signer_due(engine, name, node)) and (signer := args.get(signer_arg(name)) or caller_id()) != due:
                role = "issuer" if door_role(engine, name, node) == "issuer" else "executor (Del)"
                raise ValueError(
                    f"`{name}` on '{node}' is its {role}'s move: '{signer}' is not the {role} of '{node}' — "
                    f"'{due}' is. Sign it as '{due}' (`{signer_arg(name)}`), or ask '{due}' to make it.")
            return fn(*a, **kw)
        mode = engine.mode()
        if mode_kind(engine.graph) == Mode.AUTO:
            raise ValueError(
                f"this project runs in AUTO (set by {mode.get('by')}): every role on its nodes is held "
                f"by a machine — the autonomous level of §10.4 — and you are the goal's customer: you "
                f"state the goal and read its status (`next_steps`, `get_graph`, `get_verdict`), you "
                f"do not intervene. `{name}` is a move on the work, whatever name it is signed with. "
                + ("Nothing is stated yet: `plan(request)` with the user's request writes the plan you read, and `auto_decompose(plan=path)` is the go. "
                   if not engine.all_tasks() else "") +
                f"The mode is the USER's choice, not yours: if the work seems to need another holder, "
                f"tell the user and ask — change it only on their word.")
        raise ValueError(
            f"this project runs in {mode['mode']} (set by {mode.get('by')}): '{node}' is held "
            f"below the boundary, so `{name}` on it is {holder}'s move — a machine's role at the "
            f"autonomous level of §10.4, whatever name the call is signed with. You hold the "
            f"levels above; moving the boundary is the user's choice — ask them.")
    return _call


def _holder_of(engine, verb: str, args: dict) -> Optional[str]:
    """The holder of the role `verb` needs on the node its call names (`moves.role_holder`)."""
    key = DOOR_KEYS.get(verb, (None,))[0]
    return role_holder(engine, verb, args.get(key) if key else None, args.get("signal"))


def _signed(name: str, fn):
    """Sign a door's call by its credential (`config.CALLER`, set by the door): a move no credential signs is refused, a
    signer argument (`moves.SIGNERS`) naming a name the credential may not sign as is refused with what lifts it, and an
    omitted one is its default — a token's name, the standing agent, or for a page session the holder of the role the
    move needs where the person owns that name. The verb then runs as the name it is signed by (`caller_id`). A call no
    door served (the system's own, in process) carries no principal and is untouched."""
    if name in READS:
        return fn
    sig, signers = inspect.signature(fn), SIGNERS.get(name, ())

    @functools.wraps(fn)
    def _call(*a, **kw):
        p = CALLER.get()
        if p is None:
            return fn(*a, **kw)
        refuse_unsigned(f"`{name}`")
        try:
            ba = sig.bind_partial(*a, **kw)
        except TypeError:
            return fn(*a, **kw)                  # the door answers a malformed call in its own terms
        named = [str(ba.arguments[s]) for s in signers if ba.arguments.get(s)]
        if (stranger := next((n for n in named if n not in p.signs_as), None)) is not None:
            raise ValueError(
                f"`{name}` signed as '{stranger}': this call ({p.how}) signs only as {', '.join(p.signs_as)}. A name is "
                f"signed by its credential, never typed: take it on this connection (`act_as('{stranger}')`, a console "
                f"of its own), sign in on the page (`gfso ui`) to sign as any name you own, or launch with that name's "
                f"token (`gfso agent {stranger}`, then GFSO_TOKEN=<token>)")
        holder = _holder_of(ba.arguments.get("engine"), name, ba.arguments) if p.a_page else None
        signer = named[0] if named else holder if holder in p.signs_as else p.name
        if client_kind() is not None and isinstance(e := ba.arguments.get("engine"), Engine):
            e.performs_in_chat(signer)        # …a stream's name moving over MCP — taken or launched with — works in a chat
        # …into a signer the verb requires; one it defaults reads the caller (`caller_id`), and its omission keeps its
        # meaning (a root created naming no issuer is self-assigned)
        a, at = list(a), list(sig.parameters)
        for s in (s for s in signers if not ba.arguments.get(s) and sig.parameters[s].default is inspect.Parameter.empty):
            if (i := at.index(s)) < len(a):
                a[i] = signer
            else:
                kw[s] = signer
        token = CALLER.set(p.signing(signer))
        try:
            return fn(*a, **kw)
        finally:
            CALLER.reset(token)
    # …and no door asks for a signer: omitted, the credential's default signs
    _call.__signature__ = sig.replace(parameters=[
        q.replace(default=None) if q.name in signers and q.default is inspect.Parameter.empty else q
        for q in sig.parameters.values()])
    return _call


# The COMPLETE transport registry the doors bind — every verb wrapped so none of them can raise
# into one (`answering`, above), each signed by its call's credential (`_signed`).
#: the arguments of a move that name a node
_NODE_ARGS = ("task_id", "parent_id", "child_id", "from_id", "to_id", "blocker_task_id", "blocker_task_ids")


def _held_while_written(name: str, fn):
    """A move at a door naming a node inside a subtree an authoring writes now — any node it names: an edge's two ends,
    a blocker list — or, a split, one above it, is refused naming that authoring (`being_rewritten`): nothing lands in a
    subtree while it is written, and the refusal lifts when the authoring ends (§12.16(ii)). A switch of mode waits for
    every authoring of the project: it hands roots between the person and the system party (`Engine._hand_over`) under
    the issuer the authoring was started for. `auto_decompose`'s own entry holds it for an authoring."""
    if name != "set_mode" and (name not in DOOR_KEYS or name == "auto_decompose"):
        return fn
    sig, above = inspect.signature(fn), name == "decompose"

    def _named(at: dict) -> list:
        return [str(x) for k in _NODE_ARGS if at.get(k) for x in ([at[k]] if isinstance(at[k], str) else at[k])]

    @functools.wraps(fn)
    def _call(*a, **kw):
        try:
            at = sig.bind_partial(*a, **kw).arguments
        except TypeError:
            return fn(*a, **kw)                  # the door answers a malformed call in its own terms
        engine = at["engine"]
        if name == "set_mode":
            if not at.get("mode") or not (held := engine.authorings.held()):
                return fn(*a, **kw)
            return {"refused": True, "being_rewritten": [h or n for n, h in held.items()],
                    "error": "being_rewritten: a switch of mode hands roots between the person and the system party, "
                             "and it waits for every authoring of the project — " + "; ".join(
                                 f"{n}" + (f" (`auto_decompose(writing=\"{h}\")`)" if h else "") for n, h in held.items())
                             + " — this call started nothing; it may be made once they have ended (`gfso wait` wakes "
                               "on each), or after `stop_project`"}
        for node in _named(at):
            if (other := engine.authorings.over(node, above and node == str(at.get("parent_id")))) is not None:
                return _refused_while_written(engine, node, other)
        return fn(*a, **kw)
    return _call


def _at_a_door(name: str, fn):
    """`fn` as a door calls it: held while its subtree is written, and off its call where it runs a model."""
    return _held_while_written(name, _written_past_its_call(fn) if name == "auto_decompose" else
                               _off_the_call(name, fn, OFF_THE_CALL[name]) if name in OFF_THE_CALL else fn)


TOOLS = {name: answering(_signed(name, _mode_lock(name, _at_a_door(name, fn)))) for name, fn in _RAW_TOOLS.items()}
# The same verbs for the system's own in-process moves: answering, never locked — the mode hands the
# work TO the system, so a lock here refused its own validation of every AUTO delivery (measured live).
SYSTEM_TOOLS = {name: answering(fn) for name, fn in _RAW_TOOLS.items()}
