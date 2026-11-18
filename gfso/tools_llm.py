"""The LLM half of the action surface — the verbs that SPAWN model runs.

Split from `gfso.tools` (the structural half, L1: core+engine only) so the structural surface
carries zero LLM/adapter dependencies — this module is L2 and pulls decompose/critic/runtime
freely. Same contract as tools.py: pure functions `(engine, *args) -> JSON-able dict`.

`TOOLS` here is the COMPLETE transport registry (structural ∪ LLM) — the binding layers
(MCP / CLI / HTTP) generate their surfaces from THIS dict; `gfso.tools.TOOLS` stays the
structural subset.
"""
from __future__ import annotations

import copy
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
from concurrent.futures import Future, ThreadPoolExecutor
from contextlib import nullcontext, suppress
from pathlib import Path
from datetime import datetime
from dataclasses import asdict
from typing import Optional, Union

from gfso import canon as _canon, past, runtime
from gfso.llm import llm_factory
from gfso.workspaces import declaring_role, delivered_ref, execution_of, performer, where_it_runs, rejected_reports_dir
from gfso.adapters import worktrees as W
from gfso.adapters.snapshots import BuildFailed, NotTheDelivery, Uncopied, snapshot, swap
from gfso.adapters.execution import (IMPORTED, NODES as _NODES, ContainerExecution, committed, left_out,
                                     scratch_of)
from gfso.issuer import CONTACT_ROUND as _CONTACT
from gfso.core.types import (BATCH, HOST, LAID, VOLUME, AgentId, LLMProviderPort, Mode, PlaceUnavailable, State, TaskId, Stage,
                             Verdict, passed)
from gfso.core.protocol.invariants import RED_SET, criterion_meant, probes_of, red_set, spoken_verdict, verdict_word
from gfso.core.protocol.procedure import (SYSTEMS_ACT, canonical_citations, laid_down_dirs, probe_id, with_engine_observations,
                                          with_part_observations)
from gfso.observe import FRESH_S, OBSERVE_S, run_checks
from gfso.places import cheap_to_ask
from gfso.critic import runner as _critic_runner
import gfso.decompose as _decompose
from gfso.adapters.execution import network_of, node_key, take_in
from gfso.decompose import NoPlan, decompose_into, artifact as _artifact, planning as _planning, kept as _kept
from gfso.engine.events import emit_cb
from gfso.engine.findings import record_round
from gfso.engine.moves import DOOR_KEYS, READS, SIGNERS, door_holder, door_role, role_holder, signer_arg, signer_due
from gfso.engine.validation import _l0_holes, _l2_undischarged, whole_waits_for_its_parts
from gfso.core.graph.metrics import DIAGNOSTIC_MEANS
from gfso.core.graph.model import MAX_ITERATIONS_CEILING, bounds_refusal, project_now, project_state_bound, witnessed_count
from gfso.engine.loop import state_bound_left
from gfso.adapters.llm.stats import _stat_line, calls_of, refused_by_limit, the_call_was_cut, what_stopped
from gfso.engine import Engine
from gfso import signin, tools as _tools
from gfso.serverctl import open_the_page
from gfso.tools import _agent_id
from gfso.config import CALLER, agent_id as _config_agent_id, caller_id, client_kind, how_it_is_waited, reserved_refusal
from gfso.config import WRITTEN_IN_THE_CALL as _config_written_in_the_call
from gfso.adapters.llm.structured import parse_structured, schema_instruction
from gfso import config as _config_module
from gfso.config import (DEFAULT_EXECUTION, DEFAULT_PROJECT, ROOT_ID, MODEL_DEFAULT, executions,
                         validation_batch, validate_internal, state_bound, WAIT_MAX_SECONDS, WAIT_POLL_SECONDS)
from gfso.packets import (BUILT, UNCOPIED, TECH_REPORT, _last_deliver_result, _scope_validator_packet, _validator_packet, file_tech_reports,
                          owed_probes, snapshot_note)
from gfso.llm import session_calls
from gfso.inflight import _inflight, in_flight

log = logging.getLogger(__name__)


def validate_internal_on() -> bool:
    """Is every node independently validated, INTERNAL ones included (`GFSO_VALIDATE_INTERNAL`)?

    The one owner of the question, so that the panel reporting it and the code obeying it cannot
    drift: `/api/runtime` is the measurement arm's only preflight, and a declared value that the
    mechanism does not actually have would let a run measure the wrong thing in silence. Read at
    call time — the dial is set per run, after import (§10.3 is the default; this restores
    every-node validation for measurement)."""
    return validate_internal()


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
    graphs; the UI's «AI review» button is this verb."""
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
    _t = engine.graph.get_task(TaskId(task_id))
    _open = _l2_undischarged(engine._graph, _t) if _t is not None else None
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
        "— repair the plan, then review it" if _t is not None and _l0_holes(engine._graph, _t) else
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
    _cb(f"{task_id}: {verdict}" + (f" · checker {_stat_line(llm)}" if out.get("gate_passed")
                                   else " · the Level-2 checker did not run"))
    return out


#: What a validator may do: read and run, never write — the delivery is the executor's.
_VALIDATOR_TOOLS = ("Read", "Bash", "Glob", "Grep")

# The validator's report contract (parsed, never trusted): verdict PASS ⟺ every criterion passes;
# failed_criteria = exactly what the issuer passes to FAIL. Inv-3: a FAIL is never criteria-less.
_VALIDATOR_SCHEMA = {
    "type": "object",
    "properties": {
        "verdict": {"type": "string", "enum": [Verdict.PASS, Verdict.FAIL]},
        "per_criterion": {"type": "array", "items": {
            "type": "object",
            "properties": {"criterion": {"type": "string"},
                           "verdict": {"type": "string", "enum": ["pass", "fail", "undecidable"]},
                           "evidence": {"type": "string"},
                           # WHAT WAS OBSERVED THAT DIFFERS FROM WHAT THE CRITERION STATES — as
                           # DATA, one short line each, not as prose inside the evidence. The
                           # divergence is the criterion's value and that value is fail (Inv-2,
                           # §12.8), so the engine refuses a `pass` carrying one. Measured on
                           # `c_compiler` (2026-09-20/21): the closing verdict marked every
                           # criterion pass and set aside its own observed divergences in prose by
                           # citing ACCEPTED_RISKS — six of them behaviours the contract requires.
                           # A waiver is the ISSUER's act (edit_criteria / accepted_risks), never a
                           # sentence inside a pass, and only a field the engine can read makes
                           # that structurally refusable rather than audit-only.
                           "divergences": {"type": "array", "items": {"type": "string"},
                                           "description": "each thing you OBSERVED that differs "
                                                          "from what this criterion states — what "
                                                          "the criterion demands, what the "
                                                          "artifact did. Leave EMPTY only if there "
                                                          "were none; a non-empty list means this "
                                                          "criterion's verdict is `fail`, however "
                                                          "the plan or the executor explains it"},
                           # What the criterion NAMES, enumerated. A criterion is routinely a
                           # conjunction ("N/P/D loops, hold-space accumulation across the whole
                           # input, and multi-line address ranges"), and one probe over one conjunct
                           # passes it while another is broken. Measured: a root closed DONE on
                           # exactly that — the probe was honest and reproduced, it simply covered
                           # one behaviour of three, and the untested one failed against real sed.
                           # Reproducibility is not coverage; the canon leaves this to runtime
                           # (§9.6: prohibition has no form guard, only FM-3 at runtime), so runtime
                           # is where it is demanded.
                           "behaviours": {"type": "array", "items": {"type": "string"},
                                          "description": "each distinct behaviour this criterion "
                                                         "requires — one entry per conjunct, in the "
                                                         "criterion's own words"},
                           # The claim must be RE-RUNNABLE, on the PASS side as much as the FAIL
                           # side: the measurement's load-bearing direction is the false PASS.
                           # ONE PROBE PER BEHAVIOUR, in the same order.
                           "probe": {"type": "array", "items": {"type": "object", "properties": {
                               # The pinned probe's own name, when this entry is one of them. The
                               # contract pins its procedure before the work (A1/§2, Inv-1 §12.3)
                               # and a PASS that skips a pinned probe is refused — so a report says
                               # which of them it ran. Matching also works by the command text, so
                               # an id is never a thing to fabricate — but a command or a bare hash
                               # that two demanded probes share names neither (`procedure.part_credit`).
                               "id": {"type": "string", "description":
                                   "the id in brackets, when this entry runs a PINNED CHECK or a "
                                   "REGRESSION line of the contract (omit for your own exploration). "
                                   "Without it the probe is matched by its exact command; a command "
                                   "or hash two demanded probes share counts for neither"},
                               # …and for a PART'S PINNED CHECK, whether it held: the verdict is per criterion,
                               # and only this says a failure is the part's, read on this delivery
                               # (`procedure.parts_not_shown_holding`)
                               "held": {"type": "boolean", "description":
                                   "for a PART'S PINNED CHECK: did it show what it must on this delivery. "
                                   "false fails every criterion resting on it; left out, it counts as "
                                   "holding only under a criterion you pass. For a probe of your OWN that refutes "
                                   "the criterion: false — beside a probe that says false, one that says nothing "
                                   "is read as not refuting"},
                               # …and a finding of an earlier validator's that this run does not reproduce
                               "not_refuting": {"type": "string", "description":
                                   "only on a REGRESSION line you re-ran exactly as written, whose output refutes nothing "
                                   "the criterion requires: why. With `printed`, it is demanded no more"},
                               "printed": {"type": "string", "description": "with `not_refuting`: what the command printed"},
                               # …and whether it RAN: a probe whose own setup failed (a cd, a file it writes, a
                               # build) printed whatever its fallback prints, which can be the line it expects
                               "ran": {"type": "boolean", "description":
                                   "false when the command could not run as written — its own setup failed (a cd, "
                                   "a file it writes, a build it needs) and the artifact was never exercised; say "
                                   "why in `expect`. It then observed nothing: it meets no demand, so a criterion "
                                   "whose pinned check or regression line did not run cannot pass"},
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
                                          "substring of the real output, not a paraphrase. It must "
                                          "not be EMPTY, and an absence is where that bites: a "
                                          "command that prints nothing cannot tell 'there are no "
                                          "matches' from 'the command never ran', so a probe "
                                          "expecting no output proves nothing and its behaviour is "
                                          "counted unobserved. Write the absence so it SHOWS: "
                                          "`grep -rc configparser iniq/ | grep -v ':0' | wc -l` "
                                          "expecting `0`, or append `; echo exit=$?` and expect the "
                                          "code. (Three honest reports in a row were sent back over "
                                          "exactly this, at a paid round each — the rule was right "
                                          "and was written down nowhere the writer of the probe "
                                          "could read it: MCP door, wave 23, 2026-09-03.)"},
                               # WHICH behaviour this command observes. Counting probes against
                               # behaviours was a proxy for coverage and wrong in both directions:
                               # one command can honestly observe two behaviours, and two commands
                               # can observe the same one twice. Named, the engine checks coverage;
                               # unnamed, it can only count, and the strict reading stands.
                               "behaviour": {"type": "string", "description":
                                             "the entry of `behaviours` this command observes — "
                                             "repeat the same command with another name when one "
                                             "run genuinely observes several"}},
                               "required": ["command", "expect"]}}},
            "required": ["criterion", "verdict", "evidence", "behaviours", "probe",
                         "divergences"]}},
        "seams": {"type": "string"},
        # WHAT WAS SEEN BEYOND THE CRITERIA, as data for the issuer and never a verdict input (Inv-2): written in prose
        # ("observed but outside the stated criteria … NOT IN (SELECT …) give NULL"), the row's held-out miss was seen
        # at contact and no channel carried it to the one who could write the criterion (§8.3 FM-1.f at contact)
        "outside": {"type": "array", "description":
                    "what you OBSERVED that no criterion here states — a behaviour the goal or the spec plainly needs "
                    "that the delivery lacks. Not a divergence and no verdict: it fails nothing; it goes to the issuer, "
                    "who judges it against the goal. Leave it empty when there was none",
                    "items": {"type": "object", "properties": {
                        "what": {"type": "string", "description": "the behaviour, one line"},
                        "evidence": {"type": "string", "description": "the command you ran and what it printed"}},
                        "required": ["what"]}},
        "failed_criteria": {"type": "array", "items": {"type": "string"}},
        "tech_report": TECH_REPORT,
    },
    # …and neither `verdict` nor `failed_criteria` required: the engine computes both from the entries (§2.3, Inv-3),
    # so a report that left one out was refused as unparsed over a word it did not need (AUTO coreutils, 2026-10-10)
    "required": ["per_criterion"],
}


def _instrument_of(llm, model: str) -> tuple:
    """(the tools it used, the model it ran on) — what a validator's record names about the run."""
    return getattr(llm, "last_tool_calls", None), getattr(llm, "_model", None) or model


def _keep_a_report_that_decided_nothing(engine, task_id: str, defects: str, text: str) -> dict:
    """Store a report that produced no verdict — on disk AND on the node — and say so to the caller.

    Both places, because they answer different readers: the file is the evidence, the node's record
    is what `get_verdict` is built from, and under delegation the tool's caller is the dispatcher,
    which reads a verdict and nothing else. Keeping only the first is how an ordinary user came to
    poll `get_verdict` for four minutes on a node whose validation had already died."""
    kept = _keep_rejected_report(engine.project_name, task_id, defects, text)
    try:
        engine.record_rejected_report(TaskId(task_id), defects, None)
    except Exception:
        log.warning(f"could not keep the unreadable report on {task_id}", exc_info=True)
    return {"verdict": None, "report_text": text, "report_kept_at": kept,
            "verdict_defects": defects,
            "refusals_on_this_node": engine.refusals_on_this_delivery(TaskId(task_id))}


def _keep_rejected_report(project: str, task_id: str, defects: str, text: str) -> "Optional[str]":
    """Persist a report the engine refused to record as a verdict, and return its path.

    ⊥ is not pass (§2), so a refused report ends the node's automatic progress and the issuer must
    decide — which means the refused report is exactly the evidence needed, and it was exactly the
    one thing thrown away: the tool returns `report_text` to its caller, and under delegation the
    caller is the dispatcher, which logged one line and dropped it. Diagnosing why a validator could
    not state a verdict then cost a fresh paid run. The verdict is NOT stored (it is not one); the
    report is, beside the state, with its path named in the log.
    """
    try:
        d = rejected_reports_dir(project)    # …under its project: a node id names a node in every project
        d.mkdir(parents=True, exist_ok=True)
        stamp = datetime.now().strftime("%Y%m%d-%H%M%S")
        f = d / f"{task_id}_{stamp}.txt"
        f.write_text("# refused as a verdict: " + defects + "\n\n" + text, encoding="utf-8")
        return str(f)
    except Exception:
        return None      # evidence-keeping must never break the pipeline it observes


def _left_to_validate(engine: Engine, task) -> tuple[list, list]:
    """(criteria to validate, entries kept) for this attempt.

    WHAT THE LAST, REFUSED ATTEMPT ALREADY DECIDED on this delivery is kept, and only the rest is
    validated again (`Engine.reusable_from_refused`): the retry used to re-validate everything and could
    fail on a gap the first run had not had. Each kept entry carries who validated it
    (`reused_from_refused`), and the merged report is checked whole against THIS run's ledger."""
    kept = engine.reusable_from_refused(task.id)
    names = {str(e.get("criterion")) for e in kept}
    crits = [c for c in task.spec.criteria if c.name not in names]
    if not kept or not crits:
        return list(task.spec.criteria), []
    return crits, kept


def _validation_cap(task, graph) -> Optional[int]:
    """THE VALIDATOR'S PROCESS CAP IS WHAT IS LEFT OF THIS VISIT'S T_validate (§12.2) — one clock, as the
    executor's cap is its deadline. It was the adapter's fixed 900 s: on the delegated coreutils run
    four validations of rich nodes were cut at it mid-stream (725–913 s) and came back ⊥, paid for again
    on a slower tier. And the REMAINDER, not the whole bound: a retry after ⊥ runs in the same visit,
    and a validator outliving it would land its verdict on a node the clock has already handed on."""
    # …and never past the server's own T_validate, in or out of VALIDATING: a project's VALIDATING may be a person's
    # week to sign, while a model validator's process is the machine's, its hour the same in every project (critic)
    # The server's bound switched off (0): the adapter's own process cap, as before (critic)
    if not (machine := state_bound("VALIDATING")):
        return None
    left = (state_bound_left(task, project_now(graph).timestamp(), graph) if task.state.name == "VALIDATING" else None)
    return int(machine) if left is None else max(60, int(min(left, machine)))


def _no_start(llm, ended: str, place: str, error: str) -> str:
    """A validator run that never started, booked as its provider books one (`headless._never_started`): no answer."""
    llm.calls.append({"duration_ms": 0, "ended": ended, "place": place, "error": error, "at": time.time()})
    return ""


def _own_place(scratch: Optional[str], i: int, ex) -> Optional[str]:
    """The directory batch `i` copies the delivery into, under the validation's scratch — None without one."""
    return _fresh(ex, str(Path(scratch) / f"{BATCH}{i + 1}")) if scratch else None


def _fresh(ex, place: str) -> str:
    """`place` made by the system where nothing stood: a batch's own writable root (`execution._writable_root`), which
    no session has held — a directory or a link found there is refused, never copied into."""
    if ex.files.exists(place):
        raise OSError(f"{place} already stands: a batch's directory is made fresh")
    ex.files.mkdir(place)
    return place


def _run_each(llm, spawn, scratch: Optional[str], batches: list, run, ex) -> list:
    """One validator call per batch, `run(batch, client, place)`, the texts in batch order."""
    if spawn is None:
        # …ALONE, STILL IN A COPY: a validator judges the delivery and must not be able to change it (§10.3) — run in
        # the place itself, an edit of its own went into the next commit as the executor's delivery
        return [run(batch, None, _own_place(scratch, i, ex)) for i, batch in enumerate(batches)]
    # THE BATCHES ARE INDEPENDENT, SO THEY RUN AT THE SAME TIME. Splitting the contract unblocked
    # acceptance on a rich node but left its LATENCY additive, and latency is what stalls a run:
    # measured over 170 recorded validations, the median validation takes 46 s at ≤5 criteria, 90 s
    # at 6–12, 132 s at 13–24 and 312 s beyond — and a 25-minute wait is what ended the last
    # `spreadsheet_engine` segment. Each batch carries a DISJOINT share of what the validation owes over
    # the same unchanging delivery, so the conjunction (§2) is the same whichever order they finish in;
    # what they must not share is the client (its per-call tick state is one call's) or the scratch
    # (one run's leftovers validated by another is the bug the scratch exists to prevent).
    texts: list[str] = [""] * len(batches)

    def _one(i_batch):
        i, batch = i_batch
        client = spawn()
        client.on_tick, client.stage_hint = llm.on_tick, llm.stage_hint
        place = _own_place(scratch, i, ex)
        try:
            return i, run(batch, client, place)
        finally:
            # The spend and the tools are the VALIDATION's, whichever client made the call:
            # `record_llm_usage` drains ONE provider, and calls left on a worker are calls that
            # never happened as far as the record is concerned.
            llm.calls.extend(client.calls)
            for k, v in client.last_tool_calls.items():
                llm.last_tool_calls[k] = llm.last_tool_calls.get(k, 0) + v
    with ThreadPoolExecutor(max_workers=len(batches)) as pool:
        for i, text in pool.map(_one, list(enumerate(batches))):
            texts[i] = text
    return texts


def validation_execution(engine):
    """Where a validation of this project runs, read ONCE for all of it — its model, scratch, exact checks and every batch: never the host
    for a project whose places stand in volumes. Each read the roster again, and a role lost meanwhile put the later ones on the host. Work
    in chat with no execution declared validates on the host, as it always did; a project that had one and lost its roles has only lost
    its roles. Nor over a base no session of its project may run in (`agents_refused`): a volume holding a base as a tree gave its
    validator its `.env` (critic)."""
    if (ex := execution_of(engine)).files is not HOST and (why := ex.agents_refused()):
        raise PlaceUnavailable(str(ex.base), why)
    return ex


def _refuse_validation(engine: Engine, task_id: str, deliverable, workdir, _llm, ex):
    """Should a validator run be spent here at all — and if not, the answer that says why.

    Six refusals, each bought by a run spent for nothing: an unknown node; children that
    have not settled (Thm 1 would reject the verdict anyway); an internal node, which
    self-verifies (§10.3); an empty working directory, where a validator would conclude from
    an empty room; a delivery that was never made; and no workdir at all. Returns
    `(reply_or_None, task, deliverable)` — resolving which delivery is being validated belongs
    to the same question."""
    task = engine.graph.get_task(TaskId(task_id))
    if task is None:
        return {"error": f"unknown task {task_id}"}, None, None
    # DON'T SPEND A MODEL ON A VERDICT THE GATE WILL REFUSE. A parent's result is the AND over its
    # children (Thm 1), so while one is still open there is nothing to validate — and the PASS gate
    # already knows it: the verdict would be rejected on arrival. The dispatcher checks this before
    # auto-validating; the hand-called door did not, so the cost fell on whoever asked. Measured
    # 2026-08-20: a root was validated with a person's node still OFFERED, the report honestly
    # reported the missing piece, and the node sat in VALIDATING with the work still undone.
    # DELIVER itself stays admissible exactly as §12.4 writes it — this refuses the model run, not
    # the signal.
    # THE SAME PREDICATE THE GATE USES. This asked whether the children had "settled" and counted
    # an ESCALATED one as settled — while the PASS gate requires every active child to have PASSED
    # (Thm 1). So a parent with an escalated child bought a full validator run whose verdict the
    # gate then refused: exactly the waste this pre-check exists to prevent, in the one case it
    # let through. Two spellings of one rule, and the looser one was the one that spent money.
    # …the owners themselves: the parts that have not landed (`open_parts`), and only where the PASS would wait for
    # them (`whole_waits_for_its_parts`) — at a seam the PASS lands over them (§12.8), and refusing the run there left a
    # hand record the only way to sign it (critic over session 475ba784)
    _t = engine.graph.get_task(TaskId(task_id))
    _open = engine.joins.open_parts(TaskId(task_id)) if whole_waits_for_its_parts(engine.graph, _t) else []
    if _open:
        return {"error": f"not validating {task_id} yet: it aggregates children that have not "
                         f"settled — " + ", ".join(f"'{c.id}' is {c.state.name}" for c in _open)
                         + ". A verdict here would be refused at the gate (Thm 1: the parent is the "
                           "AND over its children), so the run is not spent. Drive those nodes "
                           "first (`next_steps`); one that waits on a person waits.",
                "waiting_on": [str(c.id) for c in _open]}, None, None
    # A VALIDATION STANDS WHERE κ ENDS (`validation.observed_here`): at every seam and at the top of every
    # scope one executor session carries. A node inside such a scope is that executor's own work — the
    # scope's one validation at its top runs its criteria too (§10.3, §3.7).
    if not engine.observed_here(TaskId(task_id)):
        return {"task_id": task_id, "state": task.state.name, "internal": True, "verdict": None,
                "note": "inside the scope of one executor session (its parent's whole was judged to fit one): "
                        "self-verify by running its check yourself, put the evidence in the DELIVER "
                        "self_validation, and PASS it directly — the scope's validation at its top covers "
                        "it (GFSO_VALIDATE_INTERNAL=1 observes every delivery)."}, None, None
    # AN EMPTY TREE IS NOT A FAILING ONE. A validator opened where the work is not reports what it
    # honestly sees — "no implementation exists" — and that lands as a FAIL over every criterion, on
    # code that may be perfect. Measured 2026-08-21: a stale roster entry pointed the instrument at
    # another experiment's scratch directory and a root took a false FAIL on seventeen criteria,
    # which then drove the run into the loop that ended it. The validator does not get to conclude from
    # an empty room; refusing costs one comparison, and the alternative costs a run.
    # …AND THE SAME RULE ABOUT WHAT IS CHEAP TO ASK. This door stats the workdir and then enumerates
    # it, and asking either of a share whose host does not answer costs 7-21 seconds on the caller's
    # own thread — the cost the dispatcher's guard was built to avoid, in the one other place that
    # asks the same question of the same directory. A rule kept in two places moves in one of them,
    # which is the defect this repository keeps paying for; both now read `cheap_to_ask`. A network
    # workdir is therefore not pre-checked: the validator opens it and reports what it finds.
    if _llm is None and cheap_to_ask(workdir) and not any(
            q not in ("__pycache__", ".gfso-scratch") for q in workdir and ex.files.listdir(workdir) or ()):
        # …and the way OUT of the refusal depends on whether the roster was able to answer. It used
        # to read "`list_agents` shows where this node's executor works" in both cases — advice that
        # is a dead end for a node held by a person, and homework the server has already done for a
        # registered one (the caller reaches here only after `_registered_workdir` came back empty).
        _out = ("Point `workdir` at the delivery and run it again." if workdir else
                f"{task.assignee or 'this node'} has no registered workdir (the roster was asked "
                f"first), so name the delivery's directory yourself: "
                f"validate_result('{task_id}', workdir='…').")
        return {"task_id": task_id, "state": task.state.name, "verdict": None,
                "error": f"nothing to validate: the working directory {workdir!r} is empty (or absent), "
                         f"so any verdict from here would be about the DIRECTORY, not the work. "
                         f"{_out} This is the instrument's gap, not the "
                         f"executor's: do not send the node to rework over it (§2.3, ⊥ is not a "
                         f"verdict)."}, None, None
    # …NOR A THIRD RUN ASKED AT A DOOR after two reports on this delivery decided nothing: that is about the contract, not
    # the run (measured 2026-08-21: three ⊥ in a row, four runs, ~$0.5). The system's own asking (`Dispatcher`) is
    # VALIDATING's issuer obtaining its verdict until the bound hands the node on (§16.14), never refused here
    if CALLER.get() is not None and (n := engine.refusals_on_this_delivery(TaskId(task_id))) >= 2:
        return {"task_id": task_id, "state": task.state.name, "verdict": None, "refusals_on_this_node": n,
                "error": f"not validating {task_id} a third time: {n} reports on this delivery could not decide every "
                         f"criterion, which is about the CONTRACT, not the run. Lifted by a move that is yours: its "
                         f"issuer revises what it promises (`edit_criteria`) or records the verdict with what they "
                         f"observed (`record_verdict`), or hands the node on (`reassign`): VALIDATING admits none of its "
                         f"executor's signals. `get_verdict` shows what the refused reports did check."}, None, None
    deliverable = deliverable or _last_deliver_result(engine, TaskId(task_id))
    if not deliverable:
        return {"error": f"nothing to validate: {task_id} has no recorded DELIVER result — "
                         f"pass `deliverable` explicitly (state {task.state.name})"}, None, None

    # NO WORKING DIRECTORY, SAID BEFORE ANYTHING IS SPENT — and said about THIS node. The refusal
    # came from the transport, several steps in: after the in-flight key was claimed and a client
    # built, phrased as a transport complaint that mentioned neither the node nor its state. The
    # caller learnt that something needed a directory, not that their node was waiting for a verdict
    # and where its work lives.
    if not workdir and _llm is None:
        return {"task_id": task_id, "state": task.state.name, "verdict": None,
                "error": f"validate_result needs `workdir` — the directory the work was done in. A "
                         f"validator opened anywhere else validates an empty tree and fails correct "
                         f"work (measured). {task_id} is {task.state.name}; pass the workdir of the "
                         f"role that executed it (`list_agents` shows it), e.g. "
                         f"validate_result('{task_id}', workdir='…')."}, None, None


    return None, task, deliverable


#: the validation rounds this process is running in right now — never pruned, whatever their age (`_validation_place`)
_LIVE_ROUNDS: set = set()


def _round_epoch(name: str) -> int:
    """The second a validation's round was made in, read off its name (`<node>_<epoch>`); 0 where it carries none."""
    tail = name.rsplit("_", 1)[-1]
    return int(tail) if tail.isdigit() else 0


def _validation_place(task_id: str, workdir, ex, named: tuple = (), graph=None, project=None):
    """Where the validator runs, and what the delivery held before it did.

    Two needs once collapsed into one: a fresh scratch per validation (a shared one let
    a run validate another's leftovers), and the working directory being the DELIVERY's (a
    validator opened in the scratch saw an empty tree and failed correct work). The
    scratch is a SIBLING of the delivery, so a criterion like "every file here belongs
    to this package" stays true. Returns (scratch, files_before)."""
    scratch = None
    if workdir and cheap_to_ask(workdir):
        # …and not beside a delivery on a share: creating the scratch there is the same wait as
        # asking about it, in a place the caller cannot see. Without one, the validator is simply
        # offered no scratch — a path the code already carries (`place = … if scratch else None`).
        # BESIDE the delivery, not inside it. One dotted directory rather than a loose
        # `<task>_<epoch>/` per validation — and a SIBLING of the tree being validated, because a
        # criterion like "every file under the target dir belongs to this package" is then true:
        # our own scratch was sitting in the deliverable while the validator dutifully reported
        # everyone else's leavings (measured on the human door 2026-08-22).
        root = scratch_of(workdir, project)
        # …a round of its own, never one an earlier validation in the same second holds: its batches are made fresh
        at = int(time.time())
        # …one path component, whatever the id spells: `db/schema` had a place and no round, a node stuck with no validator run (critic, ran)
        while ex.files.exists(scratch := str(root / f"{node_key(task_id)}_{at}")):
            at += 1
        ex.files.mkdir(scratch)
        if graph is not None:              # …in the record of the rounds standing, as it goes (`findings.record_round`)
            record_round(graph, scratch, True)
        # Keep the recent ones (a verdict's evidence is worth reading after the fact) and drop
        # the rest: one directory per validation, inside the repository being validated, otherwise
        # accumulates for the life of the project — a rework loop alone makes several.
        # …but never a round a standing finding runs: gone, its probe would read as unrunnable and stop being
        # demanded with no ruling (a 16-round root, GB_c_compiler — critic 2026-10-11)
        # …nor an issuer's contact running in this scratch beside them (`issuer._contact_place`): it removes itself
        # …what was laid for a lone round beside it (`LAID`) going with it
        # …the OLDEST by the epoch each round is named with, never by name (`<node>_<epoch>`: by name a node's every round
        # went before another's), and none a validation is still running in — this process's by its record of them
        # (`_LIVE_ROUNDS`), another's beside it by age, younger than VALIDATING's bound: pruned under a running batch,
        # its directory went (flake, 2026-11-10)
        _LIVE_ROUNDS.add(scratch)
        rounds = sorted((d for d in ex.files.listdir(str(root)) if not d.startswith(_CONTACT) and not d.endswith(LAID)),
                        key=_round_epoch)
        live_since = at - (int(project_state_bound(graph, "VALIDATING")) or 0)
        for old in rounds[:-20]:
            if _round_epoch(old) >= live_since or str(root / old) in _LIVE_ROUNDS:
                continue
            if not any(f"{root.name}/{old}" in str(n).replace("\\", "/") for n in named):
                with suppress(OSError):
                    ex.remove_tree(str(root / (old + LAID)))
                    ex.remove_tree(str(root / old))
                    if graph is not None:
                        record_round(graph, str(root / old), False)
    # What the delivery held BEFORE the validator touched it. The instruction above is a prompt, and
    # a prompt is not enforcement (the lesson this project keeps relearning), so the difference is
    # MEASURED rather than assumed. Nothing is deleted: the executor's tree is not this code's to
    # prune, and a stray named in the record is a fact its owner can act on.
    # …AND `None` MEANS UNKNOWN, WHICH IS NOT "IT WAS EMPTY". An unreadable directory left this an
    # empty SET, and every pre-existing file in the delivery was then named as something the validator
    # had left behind — the exact false accusation the comparison exists to prevent, inverted.
    # ⊥ is not zero here either (§2.3): with no pre-image there is nothing to subtract, so the
    # honest answer about strays is silence.
    _before = None
    if workdir and cheap_to_ask(workdir):     # see `gfso.places.cheap_to_ask`: a share can hang
        try:
            _before = set(ex.files.listdir(workdir)) if ex.files.is_dir(workdir) else None
        except OSError:
            pass                      # …an unlistable delivery is unknown, said just below
        if _before is None:
            log.warning(f"the delivery {workdir} could not be listed before validation — this run can "
                        f"say NOTHING about what the validator left behind, and says nothing")

    return scratch, _before


def _strays_left_behind(engine, task_id: str, workdir, _before, out: dict, _cb) -> None:
    """Name what a validation run that worked in the place itself left there, if anything — a run in a copy is held to
    the delivered commit instead (`_judged_elsewhere`). Nothing is deleted: the executor's tree is not this code's to
    prune, and a stray named in the record is a fact its owner can act on."""
    if workdir and _before is not None and cheap_to_ask(workdir):
        strays = sorted(set(execution_of(engine).files.listdir(workdir)) - _before - {".gfso-scratch"})
        if strays:
            # …AND WHO ELSE COULD HAVE WRITTEN THEM. Two executors of one plan legitimately share
            # a workspace, so files appearing during a validation may be a SIBLING's work, not
            # the validator's — and naming the validator for them is an accusation in the audit trail
            # against the one party that is supposed to be read-only (measured 2026-08-22: a
            # `build/` and an `.egg-info` from a concurrent `pip install .` blamed on the
            # validator). What is certain is the delta; who made it is not, when the directory
            # is shared.
            out["validator_strays"] = strays
            _cb(f"{task_id}: {len(strays)} file(s) appeared in the delivery during this "
                f"validation ({', '.join(strays[:5])}) — NOT part of what was delivered. The "
                f"validator is read-only, so these are either its own leavings or another "
                f"node's executor working in the same directory.")


def _registered_workdir(engine: Engine, task_id: str, validator: Optional[str]) -> Optional[str]:
    """Where the work is, asked of the ONE owner instead of of this door's own order.

    Both halves this door was built for are kept and neither is decided here any more: a
    `validator=` naming a role registered against the delivery is asked (the run that refused with
    "the working directory None is empty" while the roster held it — human door, 2026-08-22), and a
    plain call on a node whose Del is a registered role is answered from the graph rather than
    handed back as homework. What changed is the ORDER, which this door had wrong: it asked the
    roster before the graph, which is the priority a false FAIL over seventeen criteria already
    bought a correction for on the dispatcher's side, in one copy of two (probed 2026-09-07 —
    the two doors sent the validator to different directories for the same node).
    """
    reg = _roster()
    return _delegation().validator_workdir(
        engine, reg, TaskId(task_id), named_validator=validator,
        vcfg=(reg.get(str(validator)) if validator else None))


def _the_validators_answer(engine, task_id, out, parsed, recorded, _cb, llm) -> dict:
    """Assemble what the caller reads from what was RECORDED — never from what was claimed.

    The record is the verdict: the engine demotes an under-probed criterion at the record,
    and a reply built from the report's own `verdict` field would hand back the claim the
    engine had just refused to store. Split out because the run and the answer are two
    things, and the second had grown to half the verb.
    """
    verdict = recorded.get("verdict") or parsed.get("verdict")
    failed = list(recorded.get("failed_criteria") or parsed.get("failed_criteria") or ())
    out.update({"verdict": verdict, "per_criterion": parsed["per_criterion"],
                "failed_criteria": failed, "seams": parsed.get("seams", ""),
                **({"outside": parsed["outside"]} if parsed.get("outside") else {}),
                # WHO IT WAS RECORDED UNDER, read off the record. The reply echoed the `validator`
                # PARAMETER, so a run that named none answered `"validator": null` beside twelve
                # per-criterion verdicts and twenty Bash calls — while the docstring says
                # `get_verdict` names which validator validated (CLI door, wave 27, 2026-09-06).
                "validator": recorded.get("validator"),
                "tools_used": dict(getattr(llm, "last_tool_calls", None) or {})})
    if failed:
        # WHY IT FAILED, at the top of the answer. A FAIL came back as a list of criterion names
        # and a `per_criterion` array whose reason lives under `evidence`; the first read of a
        # refusal was "csv_parsing_robustness -> fail" and nothing else, and the person went
        # looking through the whole object for the sentence (measured on the human door
        # 2026-08-21). The verdict's reason is the point of reading a verdict.
        _ev = {p.get("criterion"): p.get("evidence", "") for p in parsed["per_criterion"]
               if p.get("criterion") in set(failed)}
        out["why_failed"] = _ev
    if verdict != parsed["verdict"]:
        # Say it out loud: the difference between what a validator claimed and what its evidence
        # earned is exactly the thing this instrument exists to surface.
        out["verdict_demoted_from"] = parsed["verdict"]
    # Tell the issuer the ONE signal this verdict calls for — the evidence tool never signals, and a
    # bare verdict left agents guessing (observed live: after a FAIL an agent sent PASS from REWORKING,
    # which the FSM refused, and it hung). The directive rides where the agent looks: this reply.
    # …and say it against the node's CURRENT state, not against the verdict alone. A verdict can
    # be read after the graph has already moved — the dispatcher's own validator signs on
    # delivery, so by the time a caller asks, the node may be DONE. Measured live (2026-08-20):
    # `validate_result` told an agent to `signal FAIL` on a node already DONE/PASS, and on
    # another to `signal PASS`, which the FSM refused ("PASS is not valid in state DONE"). One
    # of those obeyed would have dropped accepted work. A directive is an instruction to act,
    # so it must be about the graph as it stands.
    _node = engine.graph.get_task(TaskId(task_id))
    _state = _node.state.name if _node is not None else None
    if _state != "VALIDATING":
        out["next"] = (
            f"Nothing to sign: '{task_id}' is {_state}, not VALIDATING — this verdict was read "
            f"after the graph moved on (a registered validator signs on delivery, so the node "
            f"may already be settled). Read it as a RECORD, not as an instruction; check the "
            f"node before acting.")
    elif verdict == Verdict.PASS:
        out["next"] = (f"Now sign it: signal('{task_id}','PASS'). This recorded verdict is what "
                       f"unlocks your PASS at the seam (verifier ≠ executor, §10.3).")
    else:
        out["next"] = (f"Now sign it: signal('{task_id}','FAIL', failed_criteria={failed}). "
                       f"The node returns to REWORKING; then fix EXACTLY those criteria and DELIVER again "
                       f"(do NOT send PASS from REWORKING — re-deliver, and the next validation decides).")
    _cb(f"{task_id}: validator verdict {verdict}"
        + (" (demoted from PASS — a criterion's behaviours were never observed)"
           if verdict != parsed["verdict"] else "")
        + (f" — failed: {', '.join(failed)}" if failed else "")
        + f" · {_stat_line(llm)}")
    return out


def _ready_to_validate(engine, task_id, deliverable, workdir, validator, model, _llm, _progress):
    """Everything that can refuse BEFORE a validator is paid for, and the claim on the slot.

    Returns `(refusal, ctx)`: a refusal dict and None, or None and everything the run needs.
    Separate because `validate_result` answers two questions — may this run at all, and what did
    the validator say — and the first had grown into the body of the second.
    """
    workdir = workdir or _registered_workdir(engine, task_id, validator)
    ex = validation_execution(engine)
    _stop, task, deliverable = _refuse_validation(engine, task_id, deliverable, workdir, _llm, ex)
    if _stop is not None:
        return _stop, None
    _cb = emit_cb(engine, "validate_result", _progress)
    llm = _llm or llm_factory(model, execution=ex)
    if not (llm.runs_agents if isinstance(llm, LLMProviderPort) else hasattr(llm, "run_agent")):
        return {"error": f"validate_result needs a provider that runs agents (tool calling): {model!r} answers "
                         f"one-shots only — `gfso provider-check {model}` names the roles it can hold"}, None
    # the claim names the delivery THIS run reads — the node's generation (§10.3 gate) — and where the log stood
    inflight_key = engine.claims.begin_validation(TaskId(task_id))
    if inflight_key is None:
        # `verdict: None` EXPLICITLY, and said. The reply had no `verdict` key at all, so a caller
        # doing the obvious `.get("verdict")` got exactly the value this verb's own help says must
        # never be read as a pass — indistinguishable from "the report did not parse" (CLI door,
        # 2026-09-02). Suppressing the duplicate spawn is right; answering in a shape that reads as
        # ⊥ to a naive caller is not.
        return {"task_id": task_id, "state": task.state.name, "inflight": True, "verdict": None,
                "note": "a validator run is already in flight for this node generation "
                        "(node, iteration, reopens) — duplicate spawn suppressed. This is NOT a "
                        "verdict and not a failure to produce one: the running validator's verdict "
                        "lands by itself, and `get_verdict` reads it when it does. "
                        # …AND THE ARGUMENTS OF THIS CALL WENT NOWHERE, WHICH IS THE HALF THAT
                        # MATTERED. A caller escalating the tier reads "suppressed", waits, and gets
                        # a verdict from whatever was already running — so a `model` they chose
                        # deliberately silently did not apply, and nothing in the reply said which
                        # model would actually answer. Measured on the MCP door (wave 23,
                        # 2026-09-03): "I could never tell whether my escalation had taken effect."
                        "NOTE — this call started NOTHING, so any `model` or `workdir` you passed "
                        "was not applied: the verdict that lands is the running validator's, on its own "
                        "settings. "
                        # …AND THE ADVICE THAT FOLLOWED WAS WRONG IN PRACTICE, which is worse than
                        # none. It said "wait for that verdict — it frees the slot — then re-run
                        # with the model you want", and a stranger tried exactly that twice: where
                        # an instrument is BOUND to the node, the dispatcher takes the freed slot
                        # again immediately, so a hand escalation can never win it (MCP door, wave
                        # 24, 2026-09-04). The bound instrument does its own escalating — its retry
                        # runs on GFSO_VALIDATOR_RETRY_MODEL — and what a person actually has is the
                        # other door.
                        "If an instrument is BOUND to this node it will take the slot again as soon "
                        "as it frees, so a hand-run escalation cannot win the race: the retry it "
                        "does itself is the escalation (`GFSO_VALIDATOR_RETRY_MODEL`), and after "
                        "two reports it cannot decide, it parks the node and says so. Validating it "
                        "yourself — `record_verdict` with what you observed — is the door that does "
                        "not queue behind it."}, None
    return None, (task, deliverable, llm, _cb, inflight_key, workdir, ex)


def validate_result(engine: Engine, task_id: str, deliverable: Optional[str] = None,
                  model: str = MODEL_DEFAULT, workdir: Optional[str] = None,
                  validator: Optional[str] = None,
                  _llm=None, _progress=None, _spawn=None) -> dict:
    """Validate EXECUTION (≠ `review_decomposition`, which checks the decomposition PLAN): spawn ONE independent
    read-only validator agent (Read/Bash/Glob/Grep — it RUNS tests; executed evidence outranks assessment)
    against the node's criteria + the executor's DELIVER report, returning per-criterion verdicts and
    `failed_criteria`. Call it while the node is VALIDATING, after every delivery. This tool is the
    EVIDENCE INSTRUMENT — it never signals ITSELF: you (the issuer) read the report and send PASS or
    FAIL(failed_criteria=...) (verifier = issuer, §10.3; the validator is a fresh context, never the
    work's executor). One case looks otherwise and is not: when a `llm-validator` ROLE is registered
    and the node's ISSUER is automated (the standing agent id, or a registered role — a person who
    names themselves keeps the signature and only the validation is done for them),
    the dispatcher runs that instrument on every delivery and relays ITS verdict as the issuer's
    signal — so a node can reach DONE with no signal from you. That is the registered instrument
    acting, not this verb; `get_verdict` names which validator validated. (Said here because an agent
    read the old sentence and waited to be asked for a PASS that was never coming.) `deliverable` defaults to the node's last DELIVER result from the audit log —
    pass it explicitly if the server restarted since delivery. `workdir` defaults to the registered
    workdir of the node's Del (or of `validator`) — pass it only when the work is somewhere the roster does not say. `verdict: null` = the validator's report
    did not parse; NEVER read that as pass — the raw report_text is attached for your own assessment."""
    _stop, _ctx = _ready_to_validate(engine, task_id, deliverable, workdir, validator, model,
                                 _llm, _progress)
    if _stop is not None:
        return _stop
    task, deliverable, llm, _cb, inflight_key, workdir, ex = _ctx
    try:
        llm.on_tick = _cb
        llm.stage_hint = f"{task_id} node-validator({validator or 'standalone'})"   # names whose trace it is
        _cb(f"{task_id}: independent validator (read-only agent) over the deliverable…")
        out, text = _validation_pass(engine, task_id, [(task, deliverable)], {task_id: inflight_key}, workdir,
                                     validator, model, llm,
                                     _spawn or (None if _llm is not None else lambda: llm_factory(model, execution=ex)), _cb, ex=ex)
        out["state"] = task.state.name
        if out.get("error"):
            # The transport refuses to spawn an agent with no working directory (it would run in the state home
            # and validate artifacts it cannot see — a WRONG verdict, not a missing one). Reported as a result
            # rather than raised, because the caller is an agent session.
            return {"task_id": task_id, "state": task.state.name, "verdict": None,
                    "error": f"{out['error']} — call validate_result(task_id, workdir=…)"}
        if "verdicts" not in out:
            _cb(f"{task_id}: validator report did not parse (verdict=null) · {_stat_line(llm)}"
                + (f" · report kept: {out.get('report_kept_at')}" if out.get("report_kept_at") else ""))
            return out
        recorded, said = out.pop("verdicts")[task_id], out.pop("reports")[task_id]
        if recorded["verdict"] is None:
            # HOW MANY TIMES THIS HAS HAPPENED ON THIS DELIVERY: at two, a run asked at a door is refused
            # (`_refuse_validation`)
            _n = recorded["refusals"]
            out.update({"verdict": None, "verdict_defects": recorded["error"], "report_text": text,
                        "report_kept_at": recorded["report_kept_at"], "refusals_on_this_node": _n,
                        "what_to_do": (
                            f"the probes are the INSTRUMENT's to write, not yours: one more run is "
                            f"the move, or record your own verdict with what you observed "
                            f"(`record_verdict`)" if _n < 2 else
                            f"{_n} reports on this delivery could not decide every criterion, which is about the "
                            f"CONTRACT, not the run, so a third run here is refused. Its issuer revises what this "
                            f"node promises (`edit_criteria`) or records the verdict with what they observed "
                            f"(`record_verdict`); its executor CHALLENGEs the criterion no report could decide. "
                            f"`get_verdict` shows what the refused reports did manage to check.")})
            _cb(f"{task_id}: validator report is NOT a verdict — {recorded['error']} · {_stat_line(llm)}"
                + (f" · report kept: {recorded['report_kept_at']}" if recorded["report_kept_at"] else ""))
            return out
        return _the_validators_answer(engine, task_id, out, said, recorded, _cb, llm)
    finally:
        engine.record_llm_usage(Stage.VALIDATOR, llm, TaskId(task_id))   # the validator's own spend, recorded
        engine.claims.end_validation(inflight_key)


def _naming_the_node(schema: dict) -> dict:
    """The node validator's report schema, each per-criterion entry naming the node it is about."""
    out = copy.deepcopy(schema)
    for key, what in (("per_criterion", "criterion"), ("outside", "observation")):
        item = out["properties"][key]["items"]
        item["properties"]["task_id"] = {"type": "string", "description":
                                         f"the node this {what} belongs to — its id exactly as its heading gives it"}
        item["required"] = list(item["required"]) + ["task_id"]
    return out


#: A scope's report: the node validator's, each entry naming its node. One run validates every node of the
#: scope, and a FAIL still names the node it is about, so attribution stays inside the scope (§4.4).
_SCOPE_VALIDATOR_SCHEMA = _naming_the_node(_VALIDATOR_SCHEMA)


def _scope_batches(engine: Engine, parts: list, size: int) -> list:
    """The scope's validation cut into runs that each OWE at most `size` probes (`config.validation_batch`) — per run,
    [(node, its deliverable, its criteria this run speaks to, {probe id: the criterion it is written under} for the
    probes this run carries)], in scope order; one run where `size` is 0.

    A criterion goes whole into the run with room for it, else into a fresh one; one owing more than `size` alone is
    split between runs, and its value is their conjunction (`_conjoined`). A part's probe is owed once per node, under
    the first criterion resting on it (`packets.owed_probes`), so it is placed in exactly one run; a criterion owing
    nothing costs one, for its verdict."""
    units = [(i, c, [pid for pid, _ in items] or [None]) for i, (t, _, crits) in enumerate(parts)
             for c, items in owed_probes(engine, t, crits)]
    size = size or sum(len(pids) for *_, pids in units) or 1
    runs: list = []
    room = 0
    for i, c, pids in units:
        if len(pids) > room and (len(pids) <= size or not room):
            runs.append([])
            room = size
        while pids:
            take, pids = pids[:room], pids[room:]
            runs[-1].append((i, c, take))
            room -= len(take)
            if pids:
                runs.append([])
                room = size
    return [[(parts[i][0], parts[i][1], list({c.name: c for j, c, _ in run if j == i}.values()),
              {pid: c.name for j, c, take in run if j == i for pid in take if pid is not None})
             for i in dict.fromkeys(j for j, _, _ in run)] for run in runs] or [parts]


def _conjoined(entries: list) -> list:
    """One entry per criterion over the runs of ONE validation: the runs a split criterion's probes went to each speak
    of it over their share, and its value is their conjunction (§2: V = ⋀) — any `fail` fails it, any other word that
    is not `pass` leaves it no pass, and what they observed (probes, behaviours, divergences, evidence) is the union,
    which the record then holds to everything the criterion owes. NOT the last word: that reads a kept entry under a
    fresh one (`_validation_pass`), and read between runs of one validation it would let whichever run finished last
    pass a criterion another run refuted."""
    by: dict = {}
    for e in entries:
        by.setdefault(str(e.get("criterion")), []).append(e)
    return [es[0] if len(es) == 1 else _fold(es) for es in by.values()]


def _fold(es: list) -> dict:
    """Several entries on one criterion as one: the worst word (`fail`, else any non-pass, else `pass`) with its
    evidence first — what a rework reads as the WHY (`Engine.rework_findings`) — and the union."""
    words = [spoken_verdict(e.get("verdict")) for e in es]
    worst = es[words.index("fail")] if "fail" in words else next(
        (e for w, e in zip(words, es) if w != "pass"), es[0])
    return {**es[0], "verdict": worst.get("verdict"),
            "evidence": " | ".join(str(e["evidence"]) for e in [worst] + [x for x in es if x is not worst]
                                   if e.get("evidence")),
            # …a probe of a run that PASSED its share refuted nothing: unioned unmarked into the failed
            # entry, every one was filed as a refutation — one FAIL listed 1,036 probes, one of them refuting, and the
            # store grew to 1,414 findings (GB_sql_database_tmxu0n436, 2026-10-15)
            # (a mark of its own: `held` is the part-credit gate's word, and written here it vouched a part's probe a
            # passing share only cited — critic, 2026-10-15)
            "probe": [dict(p, share="pass") if w == "pass" else p
                      for w, e in zip(words, es) for p in probes_of(e)],
            **{k: [x for e in es for x in e.get(k) or ()] for k in ("behaviours", "divergences")}}


def _entries_by_node(texts: list, parts: list, schema: dict, own: bool) -> Optional[tuple]:
    """({node id: its per-criterion entries}, {node id: what its reports said of it}) read off the batches' reports —
    None where one did not parse (a conjunct missing from every node it covered).

    `own`: the reports are about ONE node, on its own packet — every entry is that node's, whatever it names, and the
    reports' verdict and failed list are its claim, judged at the record (`invariants.verdict_report_defects`), so an
    entry about a criterion it does not have is refused there as an answer to another contract.

    Otherwise each entry goes to the node it names, or by its criterion's name where exactly one node has that
    criterion, and is dropped where neither places it: the node it belonged to is then short of it, which its record
    refuses (⊥). A report over several nodes is judged WHOLE before it is read per node: its word and its failed list
    against its own entries (`_report_contradicts_itself`) — a FAIL that names nothing or names what no entry failed
    decided nothing, for every node it covers (Inv-3; critic V1: read per node, such a report closed a project DONE).
    Each node's failed list is then its own entries' red set — names alone collide, two consumers of one producer both
    carrying a criterion of one name (critic V1)."""
    owners: dict = {}
    for task, _, crits in parts:   # …over the WHOLE contract: a criterion kept from a refused attempt has its owner too
        for name in dict.fromkeys([c.name for c in crits] + [c.name for c in task.spec.criteria]):   # (critic r5)
            owners.setdefault(name, []).append(str(task.id))
    out: dict = {str(t.id): [] for t, _, _ in parts}
    said: dict = {tid: {"verdict": Verdict.PASS if own else None, "failed_criteria": [], "seams": "", "outside": [],
                        "contradiction": None} for tid in out}
    failed_said, unplaced = set(), set()
    for text in texts:
        parsed = _shaped(parse_structured(text or "", schema))
        if parsed is None:
            return None
        # every reader below — the node an entry goes to, the report against its own entries, the record — reads the
        # contract's name, never the label as the validator decorated it
        for e in parsed.get("per_criterion") or ():
            e["criterion"] = criterion_meant(e.get("criterion"), list(owners))
        if parsed.get("failed_criteria"):
            parsed["failed_criteria"] = [criterion_meant(n, list(owners)) for n in parsed["failed_criteria"]]
        _place_outside(parsed, said, own)
        named = set()
        for e in parsed.get("per_criterion") or ():
            tid = next(iter(out)) if own else _named_node(e)
            # …by its criterion's name only where it names no node: naming one outside this validation, a consumer's
            # seam entry was credited to its sibling's like-named seam (critic over the round, 2026-10-19)
            if not tid and len(owners.get(str(e.get("criterion")), ())) == 1:
                tid = owners[str(e.get("criterion"))][0]
            if tid in out:
                out[tid].append(e)
                named.add(tid)
            elif spoken_verdict(e.get("verdict")) != "pass":
                unplaced.add(str(e.get("criterion")))
        # EVERY REPORT IS JUDGED WHOLE, a batch of one node's contract as a scope's report is: a word that decided
        # nothing, or one its own entries contradict, decided nothing for any node it covers (Inv-3, §7.1) — the batches
        # of one node read by a rule of their own made ⊥ or FAIL depend on which malformed word came (critic V4). A
        # node's single report is judged by the same clause at the record, in the record's own words.
        why = _report_contradicts_itself(parsed)   # one node's single report too: the record no longer reads its word
        failed_said.update(_listed_failed(parsed), red_set(parsed.get("per_criterion")))   # held to the names' owners below
        for tid in (out if own else named):
            s = said[tid]
            s["contradiction"] = s["contradiction"] or why
            s["seams"] = (s["seams"] + " " + str(parsed.get("seams") or "")).strip()
            if own:
                # …and the decided words conjoined, in any order; an undecided one kept as said, so the record
                # refuses it by name — None would read there as "derive it from the entries" (critics V2, V3)
                word = Verdict.FAIL if red_set(parsed.get("per_criterion")) else verdict_word(parsed.get("verdict"))
                s["verdict"] = (s["verdict"] if s["verdict"] not in (Verdict.PASS, Verdict.FAIL) else
                                str(parsed.get("verdict") or "").strip() if word is None else
                                Verdict.FAIL if Verdict.FAIL in (word, s["verdict"]) else Verdict.PASS)
                s["failed_criteria"] = list(dict.fromkeys(  # …once each, a criterion split between runs too
                    s["failed_criteria"] + (red_set(parsed.get("per_criterion")) or _listed_failed(parsed))))
    if not own or len(texts) > 1:      # one node's single report: the record holds its list to its entries
        for tid, why in _unanswered_fails(out, owners, failed_said, unplaced).items():
            said[tid]["contradiction"] = said[tid]["contradiction"] or why
    return out, said


def _named_node(x: dict) -> str:
    """The node a scope report's item names in `task_id`, as its heading gives it, the validator's quoting taken off."""
    return str(x.get("task_id") or "").strip().strip("`'\"").strip()


def _place_outside(parsed: dict, said: dict, own: bool) -> None:
    """What the report observed outside the criteria, onto the node each observation names (one node's report: that
    node) — data beside the verdict for its issuer, read by nothing that decides it (Inv-2). One naming no node of
    this validation is dropped, as an unplaced entry is."""
    for o in (o for o in parsed.get("outside") or () if isinstance(o, dict)):
        tid = next(iter(said)) if own else _named_node(o)
        if tid in said and str(o.get("what") or "").strip():
            said[tid]["outside"].append({"what": str(o["what"]).strip(), "evidence": str(o.get("evidence") or "").strip()})


def _shaped(parsed: Optional[dict]) -> Optional[dict]:
    """The report in the shape it is read in, or None — a report that did not parse. `parse_structured` checks keys, not
    types: a `failed_criteria` written as one string was read letter by letter, no letter had an owner, and a node passed
    over its own criterion named failed (critic over 37579f8); entries that are not objects broke the read uncaught."""
    if isinstance((parsed or {}).get("failed_criteria"), str):
        parsed["failed_criteria"] = [parsed["failed_criteria"]]
    ok = (parsed is not None and isinstance(parsed.get("per_criterion") or [], list)
          and isinstance(parsed.get("failed_criteria") or [], list)
          and all(isinstance(e, dict) for e in parsed.get("per_criterion") or ()))
    return parsed if ok else None


def _listed_failed(parsed: dict) -> list:
    """The report's `failed_criteria` — or, where it wrote none or fewer than its own failing entries, those entries'
    non-pass criteria: the list is the red set (Inv-3), derivable from the entries, so an absent or short summary is no
    defect — refused whole for naming one of three red entries, three validations of four nodes left no verdict and the
    clock escalated two delivered parts (GB_sql_database_tmwsep280, 2026-10-15). A list naming what its entries pass
    still disagrees."""
    red = red_set(parsed.get("per_criterion"))
    listed = [str(n) for n in parsed.get("failed_criteria") or ()]
    return listed if "failed_criteria" in parsed and not set(listed) < set(red) else red


def _unanswered_fails(out: dict, owners: dict, failed_said: set, unplaced: frozenset = frozenset()) -> dict:
    """{node: why} — for each criterion some report of this validation calls failed, by its list or by an entry under any
    node's id, every owner of it when no owner's own entry fails it: the word is then a fail its owner does not carry,
    and the owner decides nothing. Held per report or only where a red entry stood, a fail written under a non-owner's
    id, or listed by a batch with no red entry, let the owner pass on its own pass or on one kept from a refused attempt
    (critics over the round, 2026-10-19). A name two nodes share is answered by either owner failing it — except a red
    entry placed under no node (`unplaced`), which may be either's: every owner not failing it itself decides nothing,
    or the other owner's fail answered it and the second passed on a pass kept from a refused attempt (critic over
    37579f8)."""
    red_by = {(tid, n) for tid, es in out.items() for n in red_set(es)}
    unanswered: dict = {}
    for name in sorted(failed_said | set(unplaced)):
        holders = [t for t in owners.get(name, ()) if t in out]
        short = [t for t in holders if (t, name) not in red_by]
        if name in unplaced or not any((t, name) in red_by for t in holders):
            for tid in short:
                unanswered.setdefault(tid, f"a report of this validation calls '{name}' failed and no entry of its node "
                                           f"fails it — {RED_SET}")
    return unanswered


def _report_contradicts_itself(parsed: dict) -> Optional[str]:
    """Why a report decided nothing its entries can carry, or None. Where an entry is red the report is a FAIL on its red
    set, whatever its word or list say: a false FAIL is guarantee-safe (§8.4) and a PASS over a red entry is read as the
    FAIL it is. Refused, one batch's `FAILED` or a list naming another batch's criterion voided a root's every batch and
    the probed FAIL with them — of ~17 batches a round, all had to be well-formed (finder over 190f4db, after
    GB_sql_database_tn03ao788). A FAIL claimed over entries that all pass names nothing observed, and decides nothing."""
    red, listed = set(red_set(parsed.get("per_criterion"))), set(_listed_failed(parsed))
    if red:      # what the list names beyond the red set is held to its owners' entries (`_entries_by_node`)
        return None
    said = verdict_word(parsed.get("verdict"))   # a word that is neither decided nothing: no verdict to agree (§7.1)
    if parsed.get("verdict") is None and not listed:   # …and no word is no claim: the entries are the verdict (§2.3)
        return None
    if said != Verdict.PASS or listed:
        return (f"the report's verdict {parsed.get('verdict') or '(none)'} and failed_criteria {sorted(listed)} contradict its own "
                f"entries, whose non-pass criteria are {sorted(red)} — {RED_SET}")
    return None


def _record_node(engine: Engine, task, entries: list, said: dict, validator, llm, claim, model, workdir,
                 scratch, text: str = "") -> dict:
    """Record ONE node's own verdict — its reports' claim over its entries — by `record_exec_verdict` over that node
    alone, so every gate a node's record passes (a verdict at all, pinned probes run, divergences, regression,
    probes, underprobed) applies to it unchanged. {verdict, failed_criteria, validator}, or verdict None with the
    refusal.

    RECORD FIRST, THEN SPEAK. What is recorded is not always what was claimed: a criterion whose named behaviours
    were never observed is demoted at the record (an unobserved conjunct cannot carry a pass, §2.3), so the caller
    reads the record, never the claim — measured live, a claim read past the record closed a node DONE on evidence
    the engine had refused. A refused report is not a verdict (§2: V = ⋀ over ALL criteria; ⊥ is not pass) and ends
    the node's automatic progress, so it is kept where its reader looks: on disk, and beside the node, where
    `get_verdict` shows what it did manage to check (measured 2026-08-21: a 25-criterion contract refused twice, the
    node parked, and the only trace of what was checked was a text file); with how many refusals the node has had."""
    tools, _model = _instrument_of(llm, model)
    parts = engine.parts_procedure(task.id)
    entries = with_part_observations(parts, canonical_citations(entries, task.spec.criteria, parts))   # the packet's `{id, held}` form, read
    # THE ENGINE'S CONJUNCTION, NOT THE REPORT'S WORD: V is the AND of the per-criterion values (§2.3) and the FAIL
    # payload is their red set (Inv-3), so both are computed here from the entries over this node's criteria; a word or
    # list the report adds decides nothing
    failed = red_set(entries, [c.name for c in task.spec.criteria])
    verdict = Verdict.FAIL if failed else Verdict.PASS
    try:
        if said.get("contradiction"):
            raise ValueError(said["contradiction"])
        # WHOSE INSTRUMENT SPOKE: the registered role's id when one drives this, else the verb's name
        rec = engine.record_exec_verdict(task.id, verdict, failed,
                                         validator or "validate_result", per_criterion=entries,
                                         tools_used=tools, require_probe=True, generation=claim.key[1:],
                                         log_at=claim.log_at, model=_model, workdir=workdir,
                                         outside=said.get("outside") or (),
                                         inputs_dirs=laid_down_dirs(
                                             engine.validation_procedure(task.id), scratch)) or {}
    except ValueError as e:
        kept = _keep_rejected_report(engine.project_name, str(task.id), str(e), text)
        try:
            engine.record_rejected_report(task.id, str(e), entries, tools_used=tools,
                                          validated_by={"validator": validator or "validate_result", "model": _model})
        except Exception:
            log.warning(f"could not keep the refused report on {task.id}", exc_info=True)
        return {"verdict": None, "failed_criteria": [], "error": str(e), "report_kept_at": kept,
                "refusals": engine.refusals_on_this_delivery(task.id)}
    return {"verdict": rec.get("verdict") or verdict,
            "failed_criteria": list(rec.get("failed_criteria") or failed),
            "validator": rec.get("validator")}


def _scope_cap(batch: list, graph) -> Optional[int]:
    """A scope run's cap: the longest bound left among the nodes it validates. One run serves every node in it, and
    each node's own clock hands it on when its own bound passes (`_validation_cap` is that bound for a run of one);
    capped at the first-listed node's remainder, or the shortest, a top that had waited in VALIDATING cut a run over
    deliveries made seconds before to 119 s and 299 s, and every verdict in it came back ⊥ (critics, 2026-09-28)."""
    return max((c for t, *_ in batch if (c := _validation_cap(t, graph))), default=None)


def _observe_pins(engine: Engine, parts: list, workdir, built: Optional[list] = None, ex=None,
                  touched: Optional[set] = None) -> dict:
    """{(node, probe id): {matched, out, printed, note, …}} — every pinned probe of the criteria left to validate, own
    and parts', run by the system itself ON THE DELIVERY: a fresh copy of it with the inputs laid from the contract
    (`observe.run_checks`), once per validation and before any validator run, the `exact` ones first. The validator's
    copy was no such run — a probe that leaves state printed "already exists" there, and the validator's edits changed
    what it printed (critic over 38c16f9) — and a lone validator works in the place itself, so after it no copy is the
    delivery. An exact probe builds what it runs and creates what it reads (`procedure.EXACT_TEXT`); one that is not is
    matched as a part of what it prints, and its PASS is held to what it printed here (`procedure._reproduced`). A
    probe the system could not run is a row with a `note` and no `matched`, said in the record as not observed. Laid
    over the report before it is recorded (`procedure.with_engine_observations`); the place itself is never run in. The
    copy is built first, what ran appended to `built`; a build that fails raises `BuildFailed`, and nothing here runs.
    `touched`: gets the delivered files the checks changed in their copies (`_judged_elsewhere`)."""
    probes = []
    for task, _, crits in parts:
        own = engine.parts_procedure(task.id)
        probes += [((str(task.id), pid), c, p) for c in [*crits, *(pc for x in crits for pc in own.get(x.name, ()))]
                   for p in (c.check or ()) if p.command.strip() and (pid := probe_id(c.name, p))]
    # …the exact ones first: where the budget ends, the pins left unrun are ⊥ for their criteria (`PAST_BOUND`), and the
    # next validation runs those alone, with the whole budget
    probes.sort(key=lambda x: not x[2].exact)
    if not probes:
        return {}
    ex, rows = ex or validation_execution(engine), {}
    shell = bool(workdir) and ex.shell()
    why = ("the delivery could not be copied" if shell else "no shell to run it in" if workdir else
           "the delivery has no place to copy")
    if shell:
        # …in the system's own scratch, never the validation's round: these run the delivery's own scripts, and in the
        # round a judge's copy follows they shared its container and CLI state and could plant or rewrite its tree
        # (critic 3 over the judges slice)
        with ex.scratch("gfso-exact-", system=True) as tmp:
            ex.files.mkdir(str(at := Path(tmp) / "exact"))
            # …a copy the delivery makes impossible raises `NotTheDelivery`: its FAIL, as a judge's copy's (`_unjudged`);
            # one that failed for another cause leaves these not run, said so
            try:
                with snapshot(workdir, at / "delivery", ex, delivered=engine.delivered(*(t.id for t, *_ in parts)),
                              built=built) as tree:
                    if tree:
                        # …the tree DELIVER recorded, built, and never `git clean`ed: one emptied a shared place's
                        # copy inside an enclosing repository (critic over the fresh copy). State an executor's own run
                        # left in a place with no recorded commit is the pin's to start clean of (`EXACT_TEXT`)
                        why, rows = ("its inputs could not be laid",
                                     dict(run_checks(ex, probes, workdir, tree, OBSERVE_S + FRESH_S * len(probes),
                                                     touched)))
            except Uncopied as e:
                why = str(e)
    return {k: rows.get(k) or {"note": f"not run: {why}"} for k, _, _ in probes}


def _judged_elsewhere(out: dict, edits: list, touched: set) -> list:
    """The delivered files a judge changed in its copy that no pinned check changes when the system runs it — each
    changed one said in `out` (`validator_edits`), a fact either way."""
    if edits:
        out["validator_edits"] = sorted(set(edits))
    return sorted(set(edits) - touched)


def _unjudged(parts: list, e: Exception) -> tuple:
    """The reports a validation stands on whose judge's copy could not be made (`NotTheDelivery`) or built
    (`BuildFailed`), shaped as `_entries_by_node` reads them: every criterion left to validate failed on that one
    observation — the delivery's FAIL, the cause said, no check run (JOINT judge-on-the-delivered-tree). A copy that
    cannot be made is no verdict to wait for again and again: a false FAIL is guarantee-safe (§8.4), and its cause
    reaches the executor's next packet (`packets._last_delivery_text`), whose re-delivery lifts it."""
    # …each with the step that failed as its probe — a verdict states what it observed (§2), and a FAIL with none was
    # refused as no verdict —, marked the system's own act: no finding stands on it (`SYSTEMS_ACT`), the next
    # delivery's own build and copy re-check it
    built = isinstance(e, BuildFailed)
    probe = {"command": e.command if built else "the system's checkout of the commit DELIVER recorded",
             "expect": "exit 0" if built else "the tree DELIVER recorded, read back whole", SYSTEMS_ACT: True}
    return ({str(t.id): [{"criterion": c.name, "verdict": "fail", "evidence": str(e),
                          "behaviours": ["the delivered tree builds in the validation's copy" if built else
                                         "the tree DELIVER recorded is copied whole for its judge"],
                          "probe": [probe]} for c in crits] for t, _, crits in parts},
            {str(t.id): {"verdict": Verdict.FAIL, "failed_criteria": [c.name for c in crits], "seams": "",
                         "outside": [], "contradiction": None} for t, _, crits in parts})


def _validator_texts(engine: Engine, llm, parts: list, workdir, scratch, inside: Optional[frozenset], spawn,
                     edits: Optional[list] = None, built: Optional[list] = None, ex=None,
                     seen: Optional[dict] = None, alone: Optional[list] = None) -> list:
    """The validator's reports over the parts' deliveries — one run, or one per batch at the same time (`_run_each`),
    each batch carrying a disjoint share of the probes the validation owes over one unchanging set of deliveries, so
    their conjunction is the verdict whatever order they finish in (§2 V = ⋀ cᵢ; `_scope_batches`, `_conjoined`). A
    scope's parts stand each under its own heading (`inside` its members); a node validated on its own (`inside` None) gets its own packet, its contract whole unless
    batched or partly kept from a refused report. The engine refuses a report that leaves a criterion unspoken (⊥ is
    not a pass, §2.3), and on a rich contract one report did: 44 refused against 57 recorded, two E3 runs stalled at 25
    and 42 root criteria (2026-08-21) — so a long contract is batched, every owed probe carried exactly once.
    `GFSO_VALIDATION_BATCH=0` restores the single run, whatever the size. Each copy is built before its run, what ran
    appended to `built`; a build that fails raises `BuildFailed` (`snapshots._build`). `seen`: what the system's own
    runs of the pinned checks observed (`_observe_pins`), told to the validator in its packet. `alone`: gets an entry
    for each run that worked in the place itself, no copy made."""
    system = (Path(__file__).parent / "mcp" / "prompts" / "validator.md").read_text(encoding="utf-8")
    batches = _scope_batches(engine, parts, validation_batch())
    ex, delivered = ex or validation_execution(engine), engine.delivered(*(t.id for t, *_ in parts))

    def _run(batch, client=None, place=None) -> str:
        if inside is not None:
            body = (_scope_validator_packet(engine, batch, workdir, place or scratch, inside, seen)
                    + schema_instruction(_SCOPE_VALIDATOR_SCHEMA))
            cap = lambda: _scope_cap(batch, engine.graph)
        else:
            (task, deliverable, crits, *carry), = batch
            body = (_validator_packet(engine, task, deliverable, workdir, place or scratch,
                                      criteria=None if len(crits) == len(task.spec.criteria) else crits,
                                      carry=carry[0] if carry else None, seen=seen)
                    + schema_instruction(_VALIDATOR_SCHEMA))
            cap = lambda: _validation_cap(task, engine.graph)
        # RUNS SIDE BY SIDE EACH IN A COPY OF THE PLACE OF ITS OWN (`adapters.snapshots`): sharing the place, one run's
        # pinned `make clean` took the binary from under the others' probes — a false root FAIL (GB_sql_database_tngtvm580).
        # A run alone gets its copy too (`_run_each`); without a scratch it works in the place. Mapped back, the report
        # reads as run in the place.
        # Its cap is read once the copy stands: what is left of T_validate when the run starts, not before the copy took
        # its share — a cap read first let the run outlive the visit by the copy's minutes (`_validation_cap`).
        ran: list = []
        try:
            with snapshot(workdir, Path(place) / "delivery", ex, edits, delivered, ran) if place else nullcontext() as tree:
                if not tree and ex.apart:
                    # …never in the executor's place where places stand apart: its container, its CLI state, its tree
                    # to change (§10.3). No validator started: not a report it failed to write nor a contract to
                    # narrow, nor the place down (it answers) — the never-started run, asked again on its own tier and
                    # then of a person (critics over this slice: read as the place down, the project flapped)
                    return _no_start(client or llm, "uncopied", str(workdir), f"no copy of {workdir} to judge in")
                if tree:
                    body = swap(body, workdir, tree) + snapshot_note(tree, ran[0] if ran else None)
                elif alone is not None:
                    alone.append(workdir)
                text = (client or llm).run_agent(system, body, allowed_tools=_VALIDATOR_TOOLS, cwd=tree or workdir,
                                                 timeout=cap())
                return swap(text, tree, workdir) if tree else text
        except PlaceUnavailable as e:        # …the place down while copying: the stop a call that could not start makes
            return _no_start(client or llm, "unavailable", e.place, str(e))
        except Uncopied as e:                # …no copy, for a cause not the delivery's: no verdict, asked again
            return _no_start(client or llm, "uncopied", str(workdir), str(e))
        finally:
            if built is not None:
                built.extend(ran)
            if place:          # …the run's container ended, whatever its processes left running (`release`)
                ex.release(place)

    def _run_again_if_unread(batch, client=None, place=None) -> str:
        """A batch whose report does not parse is run once more, alone, inside this validation, in a fresh place of its
        own: one or two dropped brackets voided the other batches and the root of coreutils was validated whole fifteen
        times in an hour (AUTO haiku, GB_coreutils_tmsiyo732). Same delivery, same claim — nothing crosses from one
        attempt to another, nor from the first run's scratch to the second's (critic over 779eade)."""
        text = _run(batch, client, place)
        schema = _SCOPE_VALIDATOR_SCHEMA if inside is not None else _VALIDATOR_SCHEMA
        if parse_structured(text or "", schema) is not None:
            return text
        again = f"{place}_again" if place else None
        if again:
            _fresh(ex, again)
            record_round(engine.graph, again, True)
        return _run(batch, client, again)
    # a lone run copies a node's own place; on this host never a shared directory with no git base: that is the user's
    # whole tree (a copy per validation was refused on one of 77k files), and nothing there is isolated to begin with.
    # Where places stand apart it copies whatever it judges, a root's base too: else it would run in its executor's
    # …and wherever DELIVER recorded a commit, that commit checked out — the whole tree, a large one included: a chat's
    # delivery in the user's own tree was recorded and still judged in the tree as it went on to be (inchat-live-1113-1835)
    lone = scratch if workdir and (_NODES in str(workdir) or ex.apart or delivered) else None
    return _run_each(llm, spawn if len(batches) > 1 else None, scratch if len(batches) > 1 else lone, batches,
                     _run_again_if_unread if len(batches) > 1 else _run, ex)


def _validation_pass(engine: Engine, top_id: str, nodes: list, claims: dict, workdir, validator, model, llm, spawn,
                     _cb, inside: Optional[frozenset] = None, ex=None) -> tuple:
    """ONE validation pass over deliveries — a scope's (`inside` its members), or one node's, a scope of one: the
    validator's reports over every node's criteria left to validate (`_left_to_validate` keeps what a refused attempt
    already decided), then each node's OWN verdict recorded over its own entries (`_record_node`). Records only; the
    signatures are the caller's. `nodes`: [(task, its deliverable)]; `claims`: {node: its validation claim}.

    Returns (out, the reports' text): out = {task_id, stats, verdicts: {node: …}, reports: {node: what its reports
    claimed, with its entries}} — or, where the transport refused to start, `error`; where a report did not parse, the
    kept report and no `verdicts`."""
    left = {str(t.id): _left_to_validate(engine, t) for t, _ in nodes}
    parts = [(t, d, left[str(t.id)][0]) for t, d in nodes]
    ex = ex or validation_execution(engine)
    # The validator runs WHERE THE WORK IS, with a private scratch BESIDE it (`_validation_place`): a shared scratch
    # let one run validate another's leftovers, and a scratch made the working directory opened the validator in an
    # empty tree, where it failed correct work saying nothing was there. A false FAIL at the seam is worse than none.
    scratch, _before = _validation_place(top_id, workdir, ex, tuple(
        p.get("as_run") or p.get("command") for t in engine.all_tasks()
        for ps in engine.regression_probes(t.id).values() for p in ps), engine.graph, engine.project_name)
    edits, built, unbuilt, touched, alone = [], [], None, set(), []
    try:
        # the system's own run of the pinned checks FIRST, on the delivery as delivered (`_observe_pins`)
        if observed := _observe_pins(engine, parts, workdir, built, ex, touched):
            _cb(f"{top_id}: the system ran {len(observed)} pinned check(s) on a fresh copy of the delivery — "
                f"{sum(o.get('matched') is True for o in observed.values())} print what they pin, "
                f"{sum('matched' not in o for o in observed.values())} could not be run")
        texts = _validator_texts(engine, llm, parts, workdir, scratch, inside, spawn, edits, built, ex, observed, alone)
    except ValueError as ex:
        return {"task_id": top_id, "error": str(ex)}, ""
    except (BuildFailed, NotTheDelivery) as ex:       # …the delivery's FAIL, nothing checked (`_unjudged`)
        observed, texts, unbuilt = {}, [], ex
        _cb(f"{top_id}: {ex}")
    finally:
        _LIVE_ROUNDS.discard(scratch)                 # …its runs are over: an old round from now on
    if said := str(unbuilt) if unbuilt else built[0] if built else None:
        for t, _ in nodes:          # …said to each node's executor in its next packet (`packets._last_delivery_text`)
            engine.emit_info("validation", f"{t.id}: {UNCOPIED if isinstance(unbuilt, NotTheDelivery) else BUILT}{said}")
    text = "\n\n".join(x or "" for x in texts)
    out: dict = {"task_id": top_id, "stats": session_calls(llm, Stage.VALIDATE_RESULT)}
    # …a run in the place itself: what it left there is all that can be seen of what it wrote
    _strays_left_behind(engine, top_id, workdir, _before if alone else None, out, _cb)
    _schema = _SCOPE_VALIDATOR_SCHEMA if inside is not None else _VALIDATOR_SCHEMA
    for x in texts:
        file_tech_reports(engine, parse_structured(x or "", _schema), "validator", validator or "validator", top_id)
    if moved := _judged_elsewhere(out, edits, touched):    # …each PASS the system's own run does not decide is ⊥
        _cb(f"{top_id}: the validator changed delivered file(s) in its copy ({', '.join(moved[:5])}) — its passes stand "
            f"only where the system's own run of the pinned checks decides the criterion")
    read = _unjudged(parts, unbuilt) if unbuilt else _entries_by_node(texts, parts, _schema, own=inside is None)
    if read is None:
        # No retry here: an agent run is minutes-long. The report is KEPT, on disk and on the node, as a report the
        # engine refuses is: under delegation the caller is the dispatcher, which reads a verdict and nothing else,
        # and a validation that died with nothing kept left a user polling `get_verdict` for minutes (wave 25,
        # 2026-09-05). And "it wrote nothing" is not "it wrote something unreadable": a call the transport cut
        # (`the_call_was_cut`, the provider's own observation first) is a run that stopped, worth re-running on the
        # same tier, unlike a report that parsed and decided nothing (measured 2026-09-06: fifteen minutes, one
        # sentence, $0.00).
        if (_stopped := what_stopped(calls_of(llm))):
            # …AND A CALL THE ACCOUNT'S LIMIT REFUSED IS NO REPORT AT ALL: booked as a refused one, every probe of a
            # limit window raised the node's refusal count — the next validation bought on the retry tier, the issuer
            # told to narrow the contract, the validator told "attempt 16" (critic over this fix, 2026-10-24)
            return {**out, "error": f"{_stopped}: the validator's call was refused — nothing was validated"}, text
        if getattr(llm, "calls", None):
            llm.calls[-1]["parse_failed"] = True
        _said = text.strip()
        out.update(_keep_a_report_that_decided_nothing(
            engine, top_id,
            ("the validator produced NO REPORT — its run returned "
             f"{len(_said)} characters and no structured answer at all"
             + (f" ({_said[:120]!r})" if _said else " (nothing)")
             + ". That is a run that stopped, not a validation: re-running the same tier is the "
               "right move here, unlike a report that parsed and decided nothing"
             if the_call_was_cut(llm, _said) else
             "the validator's report did not parse — no verdict could be read from it"), text))
        return out, text
    entries, said = read
    # the entries kept from a refused attempt FIRST, what this run saw over them: a criterion spoken again was seen again
    # on the same delivery, and the record reads the last word on it — kept last, a kept `pass` hid a fresh `fail`
    # and a PASS over its own red entry closed a node DONE (critic V5; main's order). The runs of THIS validation are
    # read otherwise: a criterion split between them is their conjunction, never the word of whichever came last
    # …and over them what the system itself saw its exact checks print (`_observe_pins`), so the record and the answer
    # both read the same report
    whole = {str(t.id): with_engine_observations(
        left[str(t.id)][1] + _conjoined(entries[str(t.id)]), t.spec.criteria, engine.parts_procedure(t.id),
        {pid: o for (tid, pid), o in observed.items() if tid == str(t.id)}, moved[:10]) for t, _ in nodes}
    out["reports"] = {tid: {**said[tid], "per_criterion": whole[tid]} for tid in entries}
    # …a FAIL the build or the copy made ran no model: it names none (one never asked was signed as the judge)
    out["verdicts"] = {str(t.id): _record_node(engine, t, whole[str(t.id)], said[str(t.id)], validator,
                                               None if unbuilt else llm, claims[str(t.id)],
                                               None if unbuilt else model, workdir, scratch, text)
                       for t, _ in nodes}
    return out, text


def validate_scope(engine: Engine, top_id: str, workdir: Optional[str], validator: Optional[str] = None,
                   model: str = MODEL_DEFAULT, _llm=None, _spawn=None, only=None) -> dict:
    """ONE validation over the deliveries of a scope one executor session carried (`only`: those of the named
    nodes, the others' records standing): every delivered node's
    criteria, pinned probes and regression lines in one run (batched across nodes as one node's contract
    is), then each node's OWN verdict recorded over its own entries. Records only; the signatures are the
    caller's. {verdicts: {node: {verdict, failed_criteria}}, stats} — `inflight` where a run already holds
    one of them, and no verdicts where the report did not parse."""
    members = engine.scope_members(TaskId(top_id))
    nodes = [t for t in members if t.state.name == "VALIDATING" and (only is None or str(t.id) in only)]
    ex = validation_execution(engine) if nodes else None    # …before a claim: refused past them, they stood held until a restart
    keys = [engine.claims.begin_validation(t.id) for t in nodes]
    if not nodes or None in keys:
        for k in keys:
            if k is not None:
                engine.claims.end_validation(k)
        return {"task_id": str(top_id), "verdicts": {}, "inflight": bool(nodes)}
    llm = _llm or llm_factory(model, execution=ex)
    try:
        llm.on_tick = _cb = emit_cb(engine, "validate_result")
        llm.stage_hint = f"{top_id} scope-validator({validator or 'standalone'})"
        _cb(f"{top_id}: one independent validator over the scope's {len(nodes)} deliveries…")
        out, _ = _validation_pass(engine, str(top_id), [(t, _last_deliver_result(engine, t.id) or "(none recorded)")
                                                        for t in nodes],
                                  {str(t.id): k for t, k in zip(nodes, keys)}, workdir, validator, model, llm,
                                  _spawn or (None if _llm is not None else lambda: llm_factory(model, execution=ex)), _cb,
                                  inside=frozenset(str(m.id) for m in members), ex=ex)
        out.pop("reports", None)
        out["verdicts"] = {tid: {"verdict": v["verdict"], "failed_criteria": v["failed_criteria"],
                                 **({"error": v["error"]} if v.get("error") else {})}
                           for tid, v in (out.get("verdicts") or {}).items()}
        if out["verdicts"]:
            _cb(f"{top_id}: scope validated — " + ", ".join(f"{k} {v['verdict']}" for k, v in out["verdicts"].items()))
        return out
    finally:
        engine.record_llm_usage(Stage.VALIDATOR, llm, TaskId(top_id))
        for k in keys:
            engine.claims.end_validation(k)


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
    return sorted({Path(os.path.normpath(w)) for c in _roster().list().values()
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
            str(kid) != _agent_id() and str(executor) in map(str, engine.seam_keepers(AgentId(assignee)))):
        # the lift is the caller's own call without the name (§12.16 (ii)); naming `set_mode` as the way
        # out handed it the user's choice — measured, a semi holder read it, asked to switch, and stopped
        raise ValueError(
            f"this project runs in {engine.mode()['mode']}: the children of '{root_id}' are held "
            f"by {'the system' if str(kid) != _agent_id() else 'you'}, so they cannot go to "
            f"{executor}. Call it again without `executor` — the mode assigns them.")
    return executor or str(kid)


def auto_decompose(engine: Engine, request: str = "", root_id: str = ROOT_ID,
                   assignee: Optional[str] = None, executor: Optional[str] = None,
                   depth: int = 1, model: Optional[str] = None, fast: bool = False,
                   max_iterations: Optional[int] = None, spec: Optional[dict] = None,
                   _progress=None, author: Optional[str] = None, open_plan: bool = False,
                   plan: Optional[str] = None, _contact: str = "") -> dict:
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
    and the plan the file holds, exactly or refused; from then on contact may repair it, for the system wrote it."""
    request, spec = (_the_go(engine, plan, request, spec) if plan is not None
                     else (request, _no_deferral_nobody_makes(spec, open_plan or engine.mode_kind() != Mode.AUTO)))
    given, model = request, model or engine.planner_model()
    _cb = emit_cb(engine, "decompose", _progress)
    # …and SAY it, once, at the moment it happens: naming someone else here makes them the issuer of
    # every child, which is the opposite of what "delegate the work" usually means to the caller.
    if assignee and assignee != _agent_id() and not executor:
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
            f"{assignee or _agent_id()}, who issues them.")
    # UNDER A MODE the mode decides both answers, and a name that contradicts it is refused
    # (`del_by_mode`): the knob is the user's choice of who holds what, not a default a habitual
    # argument re-decides. The root keeps its creator as the goal's issuer (`Graph.issuer_of`).
    if engine.mode() is not None:
        _root = engine.graph.get_task(TaskId(root_id))
        if _root is None:
            _want = engine.del_at(0, None)
            assignee = str(_tools.del_by_mode(engine, None, assignee)) if assignee else str(_want)
            engine.record_root_issuer(TaskId(root_id), AgentId(_agent_id()))
        else:
            assignee = str(_root.assignee)
        executor = _childrens_executor(engine, root_id, assignee, executor,
                                       engine.del_at(engine.depth_of(TaskId(root_id)) + 1 if _root else 1,
                                                     AgentId(assignee)))
    if fresh := engine.graph.get_task(TaskId(root_id)) is None:
        # the place is read for the plan's author; a plan handed in (`spec`) has none
        found = "" if spec is not None else _work_place_documents(engine, request, model)
        # …a plan file's goal already carries the documents it names (`plan`)
        request = (request or "") + ("" if plan is not None else _named_documents(engine, f"{request} {found}"))
    planner = _decompose.default_llm(model, execution=execution_of(engine))   # the one door to the plan's transport
    try:
        res = decompose_into(engine, request, root_id=root_id, assignee=assignee or _agent_id(),
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
                             executor=engine.workforce.executor_session(engine.hands_of(executor or assignee)
                                                                        or executor or assignee))
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
    if plan is not None and (left := open_at_the_go(plan)):
        out["open_at_the_go"] = left
    return {**out, **(recorded_at_the_go(engine, given) if fresh else {})}


def recorded_at_the_go(engine: Engine, goal: str) -> dict:
    """What the person must hear at the go, as the graph read says it too: what of their repository the agents' copy lacks
    and the goal as given, verbatim, derived once and recorded with the project (`tools.at_the_go`); whether its work runs
    on this machine, by the one reading of the roster as published (`Workforce.runs_on_host`)."""
    said = {"not_imported": [], **_not_imported(engine), "goal_as_given": goal}
    engine.graph.store_setting(_tools.AT_THE_GO, json.dumps(said))
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
        return _answering(write)()
    handle, project = _handle_of(key), key[1]
    with _PLANNING_LOCK:
        _kept.sweep()
        if key not in _PLANNING and (out := _kept.answer(handle)) is not None:
            _kept.mark(project, handle, read=True)
            return dict(out)
        # …and a writing started anew is the record's anew, same handle or not: a re-ask after its failure or restart was
        # read kept `read` and the old error, and the plan written again was listed to no one (critic)
        if (rec := _kept.record(project)) is None or rec.get("handle") != handle or key not in _PLANNING:
            _kept.set_record(project, {"handle": handle, "state": "writing", "told": False, "read": False})
        if started := key not in _PLANNING:
            w = _PLANNING[key] = _Writing(key)
            threading.Thread(target=contextvars.copy_context().run, args=(_written_in_its_thread, key, w, write, engine),
                             daemon=True, name=f"gfso-{key[0]}").start()
        return _answer_of(key, started)


def _answer_of(key: tuple, started: bool = False) -> dict:
    """What a writing in memory answers now (called under `_PLANNING_LOCK`): `{writing}` while it runs, else its error,
    answered once."""
    w = _PLANNING[key]
    if not w.answer.done():
        return _being_written(w.handle, key[1], started)
    del _PLANNING[key]
    _kept.mark(key[1], w.handle, read=True)
    return dict(w.answer.result())


def _by_handle(handle: str, project) -> dict:
    """The writing `handle` names, answered as its own call again would be: no second writing, whatever drifted."""
    with _PLANNING_LOCK:
        if (key := next((k for k, w in _PLANNING.items() if w.handle == handle), None)) is not None:
            return _answer_of(key)
        if (out := _kept.answer(handle)) is not None:
            _kept.mark(project, handle, read=True)
            return dict(out)
        rec = _kept.record(project)
        if rec and rec.get("handle") == handle and rec.get("state") in ("failed", "writing"):
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
    """Write one plan, marked in flight under its project, so a reconcile from another session does not restart under it;
    what it came to is kept: the answer by its handle, and the state of the plan its project waits on."""
    with _inflight(key[0], engine, ROOT_ID):
        out = _answering(write)()
    with _PLANNING_LOCK:
        if "error" in out:
            _kept.mark(key[1], w.handle, state="failed", error=str(out["error"])[:2000])
        else:
            _kept.keep_answer(key[1], w.handle, out)
            _kept.mark(key[1], w.handle, state="written")     # …or let go, its project waiting on another now
            _PLANNING.pop(key, None)
        w.answer.set_result(out)


def _being_written(handle: str, project, started: bool) -> dict:
    """The answer while a plan is written: the facts of its writing, and how its agent learns it is written."""
    verb = handle.rsplit("-", 1)[0]
    return {"writing": handle, "started": started,
            "say": (f"The plan is being written ({'about 3–8 minutes on a small task' if verb == 'plan' else '2–3 minutes'}"
                    f"): `{verb}(writing=\"{handle}\")` answers it once written, and `next_steps` names it under "
                    f"`plans`. " + how_it_is_waited(project, "it is written"))}


def plans_of(project) -> dict:
    """The plan `project` waits on, as `next_steps` names it: `writing`; `written` or `failed`, not yet said (either ends
    a wait); `unread`, said and not read. A writing the server lost at a restart is `failed`."""
    with _PLANNING_LOCK:
        rec = _kept.record(project)
        if not rec or rec.get("read"):
            return {}
        h, state = rec["handle"], rec.get("state")
        if state == "writing" and not any(w.handle == h for w in _PLANNING.values()):
            state = "failed"
    key = "writing" if state == "writing" else "unread" if rec.get("told") else state
    return {"plans": {key: [h]}}


def plan(engine: Engine, request: str = "", model: Optional[str] = None, executor: Optional[str] = None,
         depth: int = 1, review_model: Optional[str] = None, writing: Optional[str] = None) -> dict:
    """Author a plan for `request` WITHOUT a project: the plan file (`.gfso`) — the goal, the split with its criteria,
    pinned checks, mappings, dependencies and register, the Level-2 review over it — for the customer to read whole.
    Nothing executes and no project is made. Answers at once: `{writing}` while it is written (about 3–8 minutes on a small
    task), and `plan(writing=<handle>)` (or the same call again), once written, holds the file's whole `text` beside its
    `path`, unless it is longer than PLAN_TEXT_MAX characters. Send a note with `refine_plan`; give the go with
    `auto_decompose(plan=<path>)`, which builds the project from the file as it stands. `executor` names the registered
    executor whose session the fit of each part is judged against."""
    if writing:
        return _by_handle(writing, engine.project_name)
    if not str(request or "").strip():
        return {"refused": True, "error": "plan needs the request, or `writing=<handle>` to read one being written"}
    model = model or engine.planner_model()
    # …the fit judged against WHO WILL DO the parts (§3.7: a leaf is within its holder's κ) — under a mode, the executor
    # the go hands the root's children to, as `auto_decompose` defaults it. Unnamed, the planner judged against an
    # unknown agent, and the user's path (`plan(request)`) got a plan placed for a session it would not run in (critic)
    if engine.mode() is not None:
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
        executor = engine.hands_of(executor) or (None if str(executor) == _agent_id() else executor)
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
        return _shown(engine, _plan_written(text))
    return _once(("plan", engine.project_name, request, model, executor, depth, review_model or engine.system_model()),
                 write, engine)


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
        return _shown(engine, _plan_written(text))
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
    secure (`insufficient`), or were not judged on (`uncertain`). The go runs the plan as it stands (`_the_go` turns the
    gate off, its review in the file), so each goes in carrying its FM-1.d (§11.5): the root's checks still decide the
    result, but a failure there names no part. Said, never silent — a tester's run started on two such criteria with
    nothing said, and its failures pointed nowhere."""
    review = _artifact.parse(_planning.text_of(plan)).get("review") or {}
    lines = [x.strip() for x in str(review.get("semantic_findings") or "").splitlines()]
    return [x[:300] for x in lines if x.startswith(("[insufficient]", "[uncertain]"))]


def _the_go(engine: Engine, plan: str, request: str, spec) -> tuple[str, dict]:
    """The goal and the plan a plan file holds, for the go — refused beside a second plan or another goal."""
    if spec is not None:
        raise ValueError("auto_decompose: pass the plan file (`plan`) or a spec (`spec`), not both")
    p = _artifact.parse(_planning.text_of(plan))
    if (request or "").strip() and request.strip() != p["goal"].strip():
        raise ValueError("auto_decompose: `request` differs from the goal the plan file answers — the go builds "
                         "the plan for its own goal; leave `request` out, or plan the new goal anew")
    # …its review ran where it was written and its customer read it: a second one, over the same file, was minutes and
    # one more round of findings before any work (critic: no row ever ran this; every row of a plan handed in had the
    # gate off, as `set_mode` says of a plan verified where it was authored). And not closed after its build, for the
    # system wrote it (`auto_decompose`): a check of its own that contact refutes is repaired, where a closed plan spun on
    # a true CHALLENGE, its issuer's right answer thrown away 29 times, 27 min (tracker, 2026-11-03; the author:
    # «подчинять систему безоговорочно этому плану нельзя, он может быть сильным но не идеальным»). `spec` stays closed.
    engine.set_settings({"l2_gate": "0"}, AgentId(_agent_id()), "the go on a plan file: its review is in the file")
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
    return {"path": str(path), "chars": len(text), "parts": [s["id"] for s in p["spec"].get("subtasks") or ()],
            "undecided_obligations": undecided,
            **({_planning.PINS: {**pins, **({"cannot_run": len(pins["cannot_run"])} if "cannot_run" in pins else {})}}
               if pins else {}),
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
                   "decision in the file they never asked for." + pinned + " " + _after_the_plan(undecided, p["notes"], cannot),
            **({"text": text} if len(text) <= PLAN_TEXT_MAX else {})}


#: what the person hears first wherever this project's work will run on this machine (`Workforce.runs_on_host`)
ON_HOST = ("First: this project's work runs on this machine, outside Docker, as the person, and stays off their "
           "branches. ")


def _shown(engine: Engine, out: dict) -> dict:
    """A plan file written is its project's to show: kept as the one its page shows (`written_plan`), told on its feed,
    and under AUTO its page opened, as the go opens it — the person read a plan only in the client's words, and the go
    under AUTO is the client's too (s17b: the core criterion left the plan unsaid)."""
    if path := out.get("path"):
        if engine.workforce.runs_on_host():
            out["say"] = ON_HOST + out.get("say", "")
        _kept.wrote(engine.project_name, path)
        engine.emit_info("plan_written", f"the plan is written: {path}")
        if engine.mode_kind() == Mode.AUTO:
            open_the_page(engine.project_name)
    return out


def written_plan(project) -> dict:
    """The plan file last written for `project`, as its page shows it before the go (`GET /api/plan`); {} for none."""
    if not (at := _kept.written(project)):
        return {}
    text = at["text"]
    try:
        p = _artifact.parse(text)
    except ValueError:                  # …a kept file that no longer reads is gone as far as its reader can tell
        return {}
    spec, r = p["spec"], p["review"]
    return {"path": at["path"], "written_at": at["at"], "goal": p["goal"], "executor": p["executor"],
            "parts": [{"id": s["id"], "name": s.get("name", ""), "description": s.get("description", ""),
                       "criteria": [c["name"] for c in s.get("criteria") or ()],
                       "split_after": list((s.get("split_after") or {}).get("after") or ())}
                      for s in spec.get("subtasks") or ()],
            "root_criteria": [c["name"] for c in spec.get("root_criteria") or ()],
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
    out = _tools.create_task(*a, **kw)
    at = inspect.signature(_tools.create_task).bind(*a, **kw).arguments
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
        with _inflight(name, at.get("engine"), at.get("task_id") or at.get("root_id", ROOT_ID)):
            return fn(*a, **kw)
    return wrapper


def _answering(fn):
    """A verb ANSWERS; it does not raise into a door.

    The three doors are generated from this registry, so an exception is not a polite failure: over
    HTTP it is a 500 with an empty body, over MCP a protocol error, over the CLI a traceback printed
    at a person — and the careful message the engine raised (`predictability 'HIGH' is not one of the
    three STD-2 categories …`) is lost in every one of them. Measured 2026-08-20: `create_task` with
    a string spec and a wrong `predictability` both arrived as bare failures, and a sweep over the
    whole registry then found eleven more verbs that raise on ordinary wrong input.

    The refusals the engine states — ValueError/KeyError/TypeError — become `{error: …}`, which every
    door already knows how to carry. Anything else is still answered rather than thrown, and marked
    `unexpected: true`: a defect in here must be visible as a defect, not disguised as a refusal.
    """
    sig = inspect.signature(fn)

    @functools.wraps(fn)
    def _call(*a, **kw):
        # The SHAPE of the call is checked outside the guard on purpose: a missing or unknown
        # argument is not a refusal by the verb, it is a call that never happened, and each door
        # already answers it in its own terms (the HTTP door names the parameter and lists the rest;
        # the CLI names the typo). Swallowing those into `{error: …}` took that away.
        sig.bind(*a, **kw)
        try:
            return fn(*a, **kw)
        except (ValueError, KeyError, TypeError) as ex:
            msg = str(ex) or f"{type(ex).__name__} with no message"
            # `refused` marks THIS path — the verb could not act at all. A verb's own `{error: …}`
            # is a different thing: `signal` reporting `accepted: false` DID interact with the FSM
            # and is a successful call with a negative outcome. The HTTP door reads the marker to
            # choose its status code, which is why it is here rather than guessed from the shape.
            # A KeyError from INSIDE a verb means the caller's payload is missing a key the verb
            # needs — not that it passed an unknown one. The old wording said "unknown key
            # 'task_id'" to someone who had never written `task_id`, and they reverse-engineered
            # three payload shapes by feeding wrong ones and reading which key it named next
            # (measured 2026-08-21, ~40% of that session).
            if isinstance(ex, KeyError):
                msg = (f"the payload is missing a required key: {msg}. `gfso run {fn.__name__} "
                       f"--help` (or the tool's description) gives the shape it expects.")
            return {"error": msg, "refused": True}
        except PlaceUnavailable as ex:
            # …met outside a model call — a place's file read or written through its execution: the stop a booked call
            # makes (`Engine.stop_for_the_place`)
            if (engine := sig.bind(*a, **kw).arguments.get("engine")) is not None:
                engine.stop_for_the_place(ex.place, str(ex))
            return {"error": str(ex)}
        except Exception as ex:                                   # noqa: BLE001 — see the docstring
            log.exception(f"{getattr(fn, '__name__', 'verb')} failed")
            return {"error": f"{type(ex).__name__}: {ex}", "unexpected": True}
    return _call


def _roster(engine: Engine = None):
    """The one server-wide delegation roster, with this engine's dispatcher attached.

    Imported here rather than at module scope because `gfso.delegate` imports THIS module (the
    dispatcher asks it whether internal nodes are being validated), and one lazy accessor is the
    whole of that cycle rather than one import inside each verb that needs the roster."""
    agents = _delegation().default_agents()
    if engine is not None:
        _delegation().ensure_dispatcher(engine, agents)
    return agents


_DELEGATION = None


def _delegation():
    """The ONE lazy door to `gfso.delegate`, crossed once for the whole module.

    `gfso.delegate` imports this module at module level, so the edge back can only be taken at call
    time — and the accessor above already said that a single lazy crossing is the whole of the
    cycle "rather than one import inside each verb that needs it". A second verb needing a second
    thing from there is exactly the drift that sentence was written against, so it goes through
    here instead of growing a new import of its own.
    """
    global _DELEGATION
    if _DELEGATION is None:
        from gfso import delegate as _d
        _DELEGATION = _d
    return _DELEGATION


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
    agents = _roster(engine)
    # …a role of this project registered again keeps where it runs: to change its model, its project's only declaring role came back
    # with none, the project on the host and its validations there, said nowhere (critic, ran)
    own = agents.get(agent_id) or {}
    kept = own.get("execution") if own.get("project") == engine.project_name else None
    execution = execution or kept or (_default_execution(engine, engine.mode(), agents) if kind == "llm-executor" else None)
    out = agents.register(agent_id, kind, model=model, workdir=workdir, validator=validator,
                          oracle_map=oracle_map, max_turns=max_turns, client=client, context_budget=context_budget,
                          project=engine.project_name, execution=execution)
    if kind == "external" and (p := CALLER.get()) is not None and p.person:
        signin.own(agent_id, p.person)           # …a person's kind is its registrant's to sign as
    _delegation().publish_the_workforce(engine, agents.list())
    # THE SPELLING THAT BINDS, not the one that was typed. The roster stores the workdir RESOLVED,
    # and the workspace binding is decided on that value — while the advice below interpolated the
    # caller's own argument, so a relative `workdir='work'` came back as an instruction that names a
    # different place when run from a different directory.
    workdir = out.get("workdir") or workdir
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
    role = _roster().list().get(agent_id) or {}
    # the engine's own reading of "this project" — and a guard against an ACCIDENT, not an owner
    # check: `project=` is the caller's word, and an unscoped role (registered with no project)
    # belongs to nobody and can be removed by anyone
    mine = (engine.project_name or DEFAULT_PROJECT) if engine is not None else None
    if workdir is None and role.get("project") and role.get("project") != mine:
        return {"unregistered": None,
                "error": f"{agent_id} was registered by project '{role['project']}', not this one — pass "
                         f"its `workdir` to show it is the role you staffed"}
    out = _roster().unregister(agent_id, workdir=workdir)
    if out.get("unregistered") and engine is not None:
        # …told where a role put on is told: published only by the dispatcher's round, a role taken off reached an open
        # page late, and never in a project no round serves (ui stream, 2026-11-13)
        _delegation().publish_the_workforce(engine, _roster().list())
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
    that work (critic). `in_chat` too: its chat's deliveries are taken into the volume (`take_in`) and its parts' work
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
    agents = _roster(engine)
    _delegation().publish_the_workforce(engine, agents.list())
    pool = [str(a) for a in engine.workforce.executor_pool()]
    validators = [a for a, c in agents.list().items()
                  if c.get("kind") in ("llm-validator", "unittest-checker")
                  and c.get("project") in (engine.project_name, None)]
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


def run_state(engine: Engine) -> dict:
    """THE RUN'S ONE STATE — `running`; `stopping` once stopped while sessions of this project still run (`working`:
    each one's verb, node and since); `stopped` when none does. Derived from the stop as set and the work in flight,
    never a second flag."""
    if not (stop := engine.paused()):
        return {"state": "running"}
    working = [w for w in in_flight() if w.get("project") == (engine.project_name or DEFAULT_PROJECT)]
    # `off_s` is the doors' own reading of the stop (`model.door_off_s`), nothing a client acts on
    return {"state": "stopping" if working else "stopped", **{k: v for k, v in stop.items() if k != "off_s"},
            "working": working}


def stop_project(engine: Engine, why: str = "", by: Optional[str] = None) -> dict:
    """STOP the project's run: the system starts no new session in it (executor, validator, issuer); those running
    finish and their signals land — `stopping` until the last one has, then `stopped`. No timeout fires while stopped
    and the graph is not changed. `start_project` runs it again."""
    engine.pause(by or _agent_id(), why)
    return run_state(engine)


def start_project(engine: Engine, by: Optional[str] = None) -> dict:
    """RUN the project again after `stop_project`; the time it stood stopped is left off its clocks, so no bound ran out
    in it (`project_now`)."""
    engine.resume(by or _agent_id())
    return {**run_state(engine), **({} if engine.graph.setting(VOLUME + IMPORTED) else _not_imported(engine))}


def next_steps(engine: Engine, root_id: Optional[str] = None, actor: Optional[str] = None) -> dict:
    """The frontier with the run's state beside it — `run`: running, stopping or stopped (`stop_project` /
    `start_project`). What follows is the frontier's own text (`gfso.tools.next_steps`)."""
    return {**_tools.next_steps(engine, root_id, actor), "run": run_state(engine), **plans_of(engine.project_name)}


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
        why = needs_its_customer(out)
        if first:
            first, stood, writing = False, why, "writing" in plans
        # …a wait on a plan being written is about the plan: what already stood when it began does not end it, and the
        # plan written since does, whoever else was told of it meanwhile
        if why and why == stood and "writing" in plans:
            why = None
        if not why and writing and "writing" not in plans and (done := plans.get("unread") or []):
            why = "a plan asked for is written: " + "; ".join(
                f'`{h.rsplit("-", 1)[0]}(writing="{h}")` answers it' for h in done)
        if why or engine.now() >= deadline:
            said_a_plan(engine.project_name, out)
            return {**out, "waited_seconds": round(engine.now() - began, 1), **(
                {"needs_you": why} if why else
                {"waited_note": "nothing needs you yet: the graph is working (`in_flight`) or waiting on a person "
                                "(`waiting`)"})}
        time.sleep(min(WAIT_POLL_SECONDS, max(0.0, deadline - engine.now())))


def _settings_given(system_model, planner_model, l2_gate, deadline_s, observe, network, bounds,
                    max_iterations) -> Union[dict, str]:
    """What `set_mode` was given for the project to set for itself, as the settings table keeps it — or why not."""
    if bounds is not None and (why := bounds_refusal(bounds)):
        return why
    if max_iterations is not None and (isinstance(max_iterations, bool) or not isinstance(max_iterations, int)
                                       or not 1 <= max_iterations <= MAX_ITERATIONS_CEILING):
        return f"max_iterations is a count of rework rounds, 1 to {MAX_ITERATIONS_CEILING}, got {max_iterations!r}"
    if deadline_s is not None and float(deadline_s) < 0:
        return f"deadline_s is seconds ahead, 0 or more, got {deadline_s!r}"
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
                              ("max_iterations", max_iterations)) if v is not None}


def set_mode(engine: Engine, mode: Optional[str] = None, boundary: Optional[int] = None,
             agent: Optional[str] = None, user_said: str = "", perform: Optional[str] = None,
             system_model: Optional[str] = None, planner_model: Optional[str] = None, l2_gate: Optional[bool] = None,
             deadline_s: Optional[float] = None, observe: Optional[bool] = None,
             network: Optional[Union[str, dict]] = None, bounds: Optional[dict] = None,
             max_iterations: Optional[int] = None) -> dict:
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
    deadline nobody typed is written (0 = none); `bounds` — each waiting state's own bound here, `{STATE: seconds}` over
    OFFERED, CHALLENGED, BLOCKED, VALIDATING, ESCALATED, CANCELLING (a person who signs answers in days, a run's
    validator in minutes), replacing the project's previous `bounds` whole, `{}` = the defaults — days to months where
    a person owns the wait (you under solo, or over what you hold under semi), the server's where the system does; OFFERED, CHALLENGED and
    BLOCKED also end at the packet deadline, whichever comes first (§12.2), so a long wait the system owns needs `deadline_s` too; `max_iterations` — the rework rounds a node issued here
    without its own bound gets; `observe` — whether the system runs a node's pinned checks once on its
    place before an executor session and hands it what they printed (on unless set off; `observe.observe_place`);
    `network` — how far this project's container reaches out, where its execution is a container: `open` (everything but
    your host), `off` (nothing), or `{"mode": "allowlist", "hosts": [...]}` (only the named hosts, on 443, through one
    gateway) — it only narrows the execution's own declaration, the more closed of the two holding (the operator's is a
ceiling), `declared` to follow that alone again; a turn ends the project's running container at once. Under
    `allowlist` and `off` a session still reaches its model through the project's model door — list no provider host
    for it (SECURITY.md); the answer names the switch in force, `network_in_force`.

    Without `mode`, only the settings named change — who holds what stays as recorded (a switch turned mid-run)."""
    try:
        m = None if mode is None else Mode(str(mode).strip().lower())
    except ValueError:
        return {"refused": True, "error": f"mode must be one of solo | semi | auto, got {mode!r}"}
    if no := _not_the_persons(engine, m, user_said):
        return no
    if m is None and (boundary is not None or perform is not None):
        return {"refused": True, "error": "boundary and perform belong to a mode: name the mode with them"}
    perform = perform or "dispatch"
    if perform not in ("dispatch", "in_chat"):
        return {"refused": True, "error": f"perform must be dispatch | in_chat, got {perform!r}"}
    if perform == "in_chat" and client_kind() == "chat":
        return {"refused": True, "error": "`in_chat` is the work done by your own tools, and this client has only the "
                                          "gfso verbs: `dispatch` has the system perform in your name what you hold"}
    settings = _settings_given(system_model, planner_model, l2_gate, deadline_s, observe, network, bounds, max_iterations)
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
        rec = engine.set_settings(settings, AgentId(agent or _agent_id()), said=str(user_said).strip())
        return {**rec, **(_turn_the_way_out(engine) if network is not None else {})}
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
            rec = engine.set_mode(m, boundary, AgentId(agent or _agent_id()), said=str(user_said).strip(),
                                  hands=str(pool[0]) if dispatch else None, settings=settings)
        except ValueError as e:
            return {"refused": True, "error": str(e)}
        return {**rec, "executors": [str(a) for a in pool],
                "holds": {"solo": "you hold every node",
                          "semi": f"you hold depths below {engine.holder_boundary()}; the system the rest",
                          "auto": "the system holds every node; you are the customer"}[m.value]}
    out = _in_the_default(engine, {"mode": m.value, **({} if m == Mode.AUTO else {"perform": perform})}, held)
    return {**out, **(_turn_the_way_out(engine) if network is not None and not out.get("refused") else {})}


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
    agents = _roster(engine)
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
    _reg = _roster()
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
may_make_a_project = _tools.may_make_a_project


def canon(engine: Engine, section: str = "") -> dict:
    """THE THEORY GFSO IS BUILT ON, for when the person asks why it works this way or whether it holds at all — read the
    chapter the question is about before answering, and answer from it, citing the section: a guess about the design
    is not an answer. No `section`: the reading map and every heading. `section='12'` a chapter, `'12.4'` one section.
    The text of this version (a checkout's own file, or this release's on GitHub)."""
    return _canon.read(section)


@functools.wraps(_tools.signal)
def signal(engine: Engine, task_id: str, signal: str, source: str, **kw) -> dict:
    """`tools.signal`, where a DELIVER whose sender performs the node in its own chat carries the commit that chat's
    repository stands on — the directory its judge stands in (`validator_workdir`) —, kept by the system under its own
    ref (`W.record_head`) and taken where its judge copies it (`take_in`); what is not committed is no part of it, and
    the answer names it (`not_delivered`). Without it the judge copied that directory as it stood when it came, so what
    was written there after DELIVER was judged as delivered (§11.3: the result as it stands at DELIVER). A party whose
    session the system runs records its own place's commit (`reports.committed_place`); a directory that is no
    repository's top with a commit is read as before — said in the answer (`not_recorded`). An ACCEPT of such a chat
    carries the HEAD that repository stood on when the work was taken, and the repository: where and from when a node
    is at work in it, as the system's own record (`past.spans`)."""
    said, tid, sig = {}, TaskId(task_id), str(signal).strip().upper()

    def in_chat():
        """Where `source` performs the node in its own chat — its judge's directory —, or a falsy answer."""
        agents = _delegation().default_agents()
        return performer(engine, agents, source)[0] is None and _delegation().validator_workdir(engine, agents, tid)
    if sig == "ACCEPT" and (place := in_chat()) and W.is_repo_top(place) and (
            head := W.git(place, "rev-parse", "--verify", "-q", "HEAD^{commit}").stdout.strip()):
        kw["_recorded"] = (None, head, str(place))
    if (sig == "DELIVER" and (st := engine.graph.get_state(tid)) in (State.EXECUTING, State.REWORKING)
            and (place := in_chat())):
        if W.is_repo_top(place):
            try:
                tree, commit, left = W.record_head(place, delivered_ref(engine, tid))
                if inner := W.nested(place, commit):        # …refused where its sender lifts it, not FAILed at the copy
                    return {"accepted": False, "state": st.name, "error": f"NOT delivered — {W.nested_cause(inner)}"}
                take_in(execution_of(engine), delivered_ref(engine, tid))   # …a project's volume, never this host
                kw["_recorded"] = (tree, commit, str(place))
            except OSError as ex:
                return {"accepted": False, "state": st.name,
                        "error": f"NOT delivered — the commit at {place} could not be recorded: {ex}"}
            if left:
                said["not_delivered"] = (f"delivered: commit {commit[:12]}; not committed, so no part of it: "
                                         f"{', '.join(left[:10])}{', …' if len(left) > 10 else ''}")
        elif W.git(place, "rev-parse", "--is-inside-work-tree").stdout.strip() == "true":
            said["not_recorded"] = (f"{place}, where this node's judge stands, is not the top of a git repository with a "
                                    f"commit: the delivery is not recorded as a commit, and its judge reads what stands "
                                    f"there when it comes — register the validator at the top of a repository with a "
                                    f"commit, and commit your work, for a verdict on what you delivered")
    out = _tools.signal(engine, task_id, signal, source, **kw)
    return {**out, **said} if said and out.get("accepted") else out


@functools.wraps(_tools.metrics)
def metrics(engine: Engine) -> dict:
    """`tools.metrics`, with the work past the system its records measure: the commits no record of the system holds
    (`past.past_the_system`), and the writes a console's witness saw (`past.witness`) — defects counted beside the
    others, never refused."""
    seen = engine.witnessed_writes()
    return {**(out := _tools.metrics(engine)),
            "past_the_system": past.past_the_system(engine, _delegation().default_agents()),
            "witnessed": {"count": witnessed_count(seen), "last": seen[-5:]},
            "means": {**out["means"], **{k: DIAGNOSTIC_MEANS[k] for k in ("past_the_system", "witnessed")}}}


_RAW_TOOLS = {
    **_tools.TOOLS,
    "signal": signal,                                                                 # a chat's delivery recorded
    "metrics": metrics,                                                               # work past the system counted
    "create_task": create_task,
    "auto_decompose": _tracked("auto_decompose", auto_decompose),
    "plan": plan, "refine_plan": refine_plan,         # a plan with no project, written in its own thread (`_once`)
    "review_decomposition": _tracked("review_decomposition", review_decomposition),   # L2, §9.1
    "validate_result": _tracked("validate_result", validate_result),                  # §10.1
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
        if engine is None:
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
        if engine.mode_kind() == Mode.AUTO:
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
        if not p.signs_as:
            raise ValueError(f"`{name}` is a move, and this call is signed by no one: {p.lift}")
        try:
            ba = sig.bind_partial(*a, **kw)
        except TypeError:
            return fn(*a, **kw)                  # the door answers a malformed call in its own terms
        named = [str(ba.arguments[s]) for s in signers if ba.arguments.get(s)]
        if (stranger := next((n for n in named if n not in p.signs_as), None)) is not None:
            raise ValueError(
                f"`{name}` signed as '{stranger}': this call ({p.how}) signs only as {', '.join(p.signs_as)}. A name is "
                f"signed by its credential, never typed: sign in on the page (`gfso ui`) to sign as any name you own, or "
                f"launch with that name's token (`gfso agent {stranger}`, then GFSO_TOKEN=<token>)")
        holder = _holder_of(ba.arguments.get("engine"), name, ba.arguments) if p.a_page else None
        signer = named[0] if named else holder if holder in p.signs_as else p.name
        # …into a signer the verb requires; one it defaults reads the caller (`_agent_id`), and its omission keeps its
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
# into one (`_answering`, above), each signed by its call's credential (`_signed`).
TOOLS = {name: _answering(_signed(name, _mode_lock(name, fn))) for name, fn in _RAW_TOOLS.items()}
# The same verbs for the system's own in-process moves: answering, never locked — the mode hands the
# work TO the system, so a lock here refused its own validation of every AUTO delivery (measured live).
SYSTEM_TOOLS = {name: _answering(fn) for name, fn in _RAW_TOOLS.items()}
