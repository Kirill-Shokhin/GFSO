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
import inspect
import json
import logging
import os
import re
import shutil
import time
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from datetime import datetime
from dataclasses import asdict
from typing import Optional

from gfso import runtime
from gfso.llm import llm_factory
from gfso.core.types import AgentId, Mode, State, TaskId, Stage, Verdict, passed
from gfso.core.protocol.invariants import probes_of, spoken_verdict, verdict_word
from gfso.core.protocol.procedure import laid_down_dirs
from gfso.core.protocol.validation import SIGNAL_ROLES, Role
from gfso.places import cheap_to_ask
from gfso.critic import runner as _critic_runner
import gfso.decompose as _decompose
from gfso.decompose import NoPlan, decompose_into
from gfso.engine.events import emit_cb
from gfso.engine.validation import _l0_holes, _l2_undischarged, whole_waits_for_its_parts
from gfso.engine.loop import state_bound_left
from gfso.adapters.llm.stats import _stat_line, the_call_was_cut
from gfso.engine import Engine
from gfso import tools as _tools
from gfso.tools import _agent_id
from gfso.adapters.llm.structured import parse_structured, schema_instruction
from gfso.config import (DEFAULT_PROJECT, ROOT_ID, MODEL_DEFAULT, validation_batch,
                         validate_internal, state_bound)
from gfso.packets import _last_deliver_result, _scope_validator_packet, _validator_packet, owed_probes
from gfso.llm import session_calls
from gfso.inflight import _inflight

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
            + (" — it made NO model call, so most likely no provider is available (the Claude CLI "
               "on PATH, signed in)" if not a_model_ran else "")
            + ". No verdict is never read as clean (§9.5 fail-closed), so execution stays shut. Run this "
              "again — a reply that could not be read may not recur. If every run comes back like this, two "
              "supported ways on: make a checker available and run this again, or take the canon's "
              "EXPLORE branch — `GFSO_L2_GATE=0` on the server, where the plan's causal check is "
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


def review_decomposition(engine: Engine, task_id: str, model: str = MODEL_DEFAULT) -> dict:
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
    try:
        llm = llm_factory(model)
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
    out["stats"] = list(llm.calls)
    # …AND HOW TO READ IT AGAIN FOR FREE. This verb SPENDS a model run every call, and it is also
    # the only place the review is rendered — so a reader whose first answer scrolled past re-ran it
    # to see the tail, at $0.16 and 65 seconds for a record that had not changed (measured on the
    # agent door 2026-08-22). `get_review` reads the stored one and costs nothing; it was never
    # mentioned where the money is spent.
    out["reread_free"] = (f"this ran the checker ({len(llm.calls)} model call(s)) — `get_review("
                          f"'{task_id}')` reads the SAME record again for free; re-run this verb "
                          f"only after the plan changed.")
    engine.record_llm_usage(Stage.L2_CHECK_PLAN, llm, TaskId(task_id))   # what the check cost, on the record
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
                                   "holding only under a criterion you pass"},
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
        "failed_criteria": {"type": "array", "items": {"type": "string"}},
    },
    # …and `failed_criteria` NOT required: the record derives it from the entries (`_listed_failed`), so a report that
    # left it out was refused as unparsed over a list it did not need (AUTO coreutils, 2026-10-10)
    "required": ["verdict", "per_criterion"],
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
    kept = _keep_rejected_report(task_id, defects, text)
    try:
        engine.record_rejected_report(TaskId(task_id), defects, None)
    except Exception:
        log.warning(f"could not keep the unreadable report on {task_id}", exc_info=True)
    return {"verdict": None, "report_text": text, "report_kept_at": kept,
            "verdict_defects": defects,
            "refusals_on_this_node":
                int((engine.rejected_report(TaskId(task_id)) or {}).get("refusals", 1))}


def _keep_rejected_report(task_id: str, defects: str, text: str) -> "Optional[str]":
    """Persist a report the engine refused to record as a verdict, and return its path.

    ⊥ is not pass (§2), so a refused report ends the node's automatic progress and the issuer must
    decide — which means the refused report is exactly the evidence needed, and it was exactly the
    one thing thrown away: the tool returns `report_text` to its caller, and under delegation the
    caller is the dispatcher, which logged one line and dropped it. Diagnosing why a validator could
    not state a verdict then cost a fresh paid run. The verdict is NOT stored (it is not one); the
    report is, beside the state, with its path named in the log.
    """
    try:
        d = runtime.data_dir() / "rejected_verdicts"
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


def _validation_cap(task) -> Optional[int]:
    """THE VALIDATOR'S PROCESS CAP IS WHAT IS LEFT OF THIS VISIT'S T_validate (§12.2) — one clock, as the
    executor's cap is its deadline. It was the adapter's fixed 900 s: on the delegated coreutils run
    four validations of rich nodes were cut at it mid-stream (725–913 s) and came back ⊥, paid for again
    on a slower tier. And the REMAINDER, not the whole bound: a retry after ⊥ runs in the same visit,
    and a validator outliving it would land its verdict on a node the clock has already handed on."""
    if task.state.name == "VALIDATING" and (left := state_bound_left(task, time.time())) is not None:
        return max(60, int(left))
    return int(state_bound("VALIDATING")) or None


def _run_each(llm, spawn, scratch: Optional[str], batches: list, run) -> list:
    """One validator call per batch, `run(batch, client, place)`, the texts in batch order."""
    if spawn is None:
        return [run(batch) for batch in batches]
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
        place = str(Path(scratch) / f"batch{i + 1}") if scratch else None
        if place:
            Path(place).mkdir(parents=True, exist_ok=True)
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


def _refuse_validation(engine: Engine, task_id: str, deliverable, workdir, _llm):
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
    _wd = Path(workdir) if workdir and cheap_to_ask(workdir) else None
    if _llm is None and cheap_to_ask(workdir) and (
            _wd is None or not _wd.is_dir()
            or not any(q.name not in ("__pycache__", ".gfso-scratch")
                       for q in _wd.iterdir())):
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


def _validation_place(task_id: str, workdir, named: tuple = ()):
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
        root = Path(workdir).parent / f".gfso-scratch-{Path(workdir).name}"
        scratch = str(root / f"{task_id}_{int(time.time())}")
        Path(scratch).mkdir(parents=True, exist_ok=True)
        # Keep the recent ones (a verdict's evidence is worth reading after the fact) and drop
        # the rest: one directory per validation, inside the repository being validated, otherwise
        # accumulates for the life of the project — a rework loop alone makes several.
        # …but never a round a standing finding runs: gone, its probe would read as unrunnable and stop being
        # demanded with no ruling (a 16-round root, GB_c_compiler — critic 2026-10-11)
        for old_dir in sorted(root.iterdir(), key=lambda d: d.name)[:-20]:
            if old_dir.is_dir() and not any(f"{root.name}/{old_dir.name}" in str(n).replace("\\", "/") for n in named):
                shutil.rmtree(old_dir, ignore_errors=True)
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
            _before = {q.name for q in Path(workdir).iterdir()}
        except OSError as e:
            log.warning(f"the delivery could not be listed before validation ({e}) — this run can "
                        f"say NOTHING about what the validator left behind, and says nothing")

    return scratch, _before


def _strays_left_behind(engine, task_id: str, workdir, _before, out: dict, _cb) -> None:
    """Name what the validation run left in the delivery, if anything.

    The instruction to keep out of the tree is a prompt, and a prompt is not enforcement —
    the lesson this project keeps relearning — so the difference is MEASURED rather than
    assumed. Nothing is deleted: the executor's tree is not this code's to prune, and a
    stray named in the record is a fact its owner can act on."""
    if workdir and _before is not None and cheap_to_ask(workdir):
        try:
            strays = sorted({q.name for q in Path(workdir).iterdir()}
                            - _before - {".gfso-scratch"})
        except OSError:
            strays = []
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
    verdict = recorded.get("verdict") or parsed["verdict"]
    failed = list(recorded.get("failed_criteria") or parsed["failed_criteria"])
    out.update({"verdict": verdict, "per_criterion": parsed["per_criterion"],
                "failed_criteria": failed, "seams": parsed.get("seams", ""),
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
    _stop, task, deliverable = _refuse_validation(engine, task_id, deliverable, workdir, _llm)
    if _stop is not None:
        return _stop, None
    _cb = emit_cb(engine, "validate_result", _progress)
    llm = _llm or llm_factory(model)
    if not hasattr(llm, "run_agent"):
        return {"error": "validate_result needs the headless agent-runner (Anthropic transport); "
                         "GFSO_PROVIDER=generic covers zero-tool one-shots only"}, None
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
    return None, (task, deliverable, llm, _cb, inflight_key, workdir)


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
    task, deliverable, llm, _cb, inflight_key, workdir = _ctx
    try:
        llm.on_tick = _cb
        llm.stage_hint = f"{task_id} node-validator({validator or 'standalone'})"   # names whose trace it is
        _cb(f"{task_id}: independent validator (read-only agent) over the deliverable…")
        out, text = _validation_pass(engine, task_id, [(task, deliverable)], {task_id: inflight_key}, workdir,
                                     validator, model, llm,
                                     _spawn or (None if _llm is not None else lambda: llm_factory(model)), _cb)
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
            # HOW MANY TIMES THIS HAS HAPPENED HERE, and what that means for the next call. A ⊥ is not a transient
            # error to retry into: the second refusal on one node is the signal that the CONTRACT is beyond what
            # one report can cover, and the answer is a stronger model or a person's own verdict — not a third
            # paid run (measured 2026-08-21: three ⊥ in a row, four runs, ~$0.5, and no surface said how many
            # attempts is normal).
            _n = recorded["refusals"]
            out.update({"verdict": None, "verdict_defects": recorded["error"], "report_text": text,
                        "report_kept_at": recorded["report_kept_at"], "refusals_on_this_node": _n,
                        "what_to_do": (
                            f"the probes are the INSTRUMENT's to write, not yours: one more run is "
                            f"the move, or record your own verdict with what you observed "
                            f"(`record_verdict`)" if _n < 2 else
                            f"do NOT run this again: {_n} reports in a row could not decide every "
                            f"criterion, which is about the CONTRACT, not the run. Its issuer narrows "
                            f"what this node promises (`edit_criteria`) or records the verdict with "
                            f"what they observed (`record_verdict`); its executor's own move is "
                            f"CHALLENGE, naming the criterion no report could decide. `get_verdict` "
                            f"shows what the refused reports did manage to check.")})
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
    item = out["properties"]["per_criterion"]["items"]
    item["properties"]["task_id"] = {"type": "string", "description":
                                     "the node this criterion belongs to — its id exactly as its heading gives it"}
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
            "probe": [p for e in es for p in probes_of(e)],
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
    carrying `dep__<producer>` (critic V1)."""
    owners: dict = {}
    for task, _, crits in parts:
        for c in crits:
            owners.setdefault(c.name, []).append(str(task.id))
    out: dict = {str(t.id): [] for t, _, _ in parts}
    said: dict = {tid: {"verdict": Verdict.PASS if own else None, "failed_criteria": [], "seams": "",
                        "contradiction": None} for tid in out}
    for text in texts:
        parsed = parse_structured(text or "", schema)
        if parsed is None:
            return None
        named = set()
        for e in parsed.get("per_criterion") or ():
            tid = next(iter(out)) if own else str(e.get("task_id") or "")
            if tid not in out and len(owners.get(str(e.get("criterion")), ())) == 1:
                tid = owners[str(e.get("criterion"))][0]
            if tid in out:
                out[tid].append(e)
                named.add(tid)
        # EVERY REPORT IS JUDGED WHOLE, a batch of one node's contract as a scope's report is: a word that decided
        # nothing, or one its own entries contradict, decided nothing for any node it covers (Inv-3, §7.1) — the batches
        # of one node read by a rule of their own made ⊥ or FAIL depend on which malformed word came (critic V4). A
        # node's single report is judged by the same clause at the record, in the record's own words.
        why = _report_contradicts_itself(parsed) if not own or len(texts) > 1 else None
        for tid in (out if own else named):
            s = said[tid]
            s["contradiction"] = s["contradiction"] or why
            s["seams"] = (s["seams"] + " " + str(parsed.get("seams") or "")).strip()
            if own:
                # …and the decided words conjoined, in any order; an undecided one kept as said, so the record
                # refuses it by name — None would read there as "derive it from the entries" (critics V2, V3)
                word = verdict_word(parsed.get("verdict"))
                s["verdict"] = (s["verdict"] if s["verdict"] not in (Verdict.PASS, Verdict.FAIL) else
                                str(parsed.get("verdict") or "").strip() if word is None else
                                Verdict.FAIL if Verdict.FAIL in (word, s["verdict"]) else Verdict.PASS)
                s["failed_criteria"] = list(dict.fromkeys(  # …once each, a criterion split between runs too
                    s["failed_criteria"] + _listed_failed(parsed)))
    return out, said


def _listed_failed(parsed: dict) -> list:
    """The report's `failed_criteria` — or, where it wrote none or fewer than its own failing entries, those entries'
    non-pass criteria: the list is the red set (Inv-3), derivable from the entries, so an absent or short summary is no
    defect — refused whole for naming one of three red entries, three validations of four nodes left no verdict and the
    clock escalated two delivered parts (GB_sql_database_tmwsep280, 2026-10-15). A list naming what its entries pass
    still disagrees."""
    red = list(dict.fromkeys(str(e.get("criterion")) for e in parsed.get("per_criterion") or ()
                             if spoken_verdict(e.get("verdict")) != "pass"))
    listed = [str(n) for n in parsed.get("failed_criteria") or ()]
    return listed if "failed_criteria" in parsed and not set(listed) < set(red) else red


def _report_contradicts_itself(parsed: dict) -> Optional[str]:
    """Why a report's verdict or failed list disagrees with its own per-criterion entries, or None."""
    red = {str(e.get("criterion")) for e in parsed.get("per_criterion") or ()
           if spoken_verdict(e.get("verdict")) != "pass"}
    said = verdict_word(parsed.get("verdict"))   # a word that is neither decided nothing: no verdict to agree (§7.1)
    listed = set(_listed_failed(parsed))
    if said is None or (said == Verdict.FAIL) != bool(red) or listed != red:
        return (f"the report's verdict {parsed.get('verdict') or '(none)'} and failed_criteria {sorted(listed)} contradict its own "
                f"entries, whose non-pass criteria are {sorted(red)} — the issuer's FAIL payload must be the red set "
                f"(Inv-3)")
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
    # a node read out of a report over several: its claim is its own entries' — every NON-PASS one failed, as the
    # validator reports an undecidable criterion FAIL (validator.md)
    failed = (list(said["failed_criteria"]) if said["verdict"] is not None else
              [str(e.get("criterion")) for e in entries if spoken_verdict(e.get("verdict")) != "pass"])
    verdict = said["verdict"] if said["verdict"] is not None else (Verdict.FAIL if failed else Verdict.PASS)
    try:
        if said.get("contradiction"):
            raise ValueError(said["contradiction"])
        # WHOSE INSTRUMENT SPOKE: the registered role's id when one drives this, else the verb's name
        rec = engine.record_exec_verdict(task.id, verdict, failed,
                                         validator or "validate_result", per_criterion=entries,
                                         tools_used=tools, require_probe=True, generation=claim.key[1:],
                                         log_at=claim.log_at, model=_model, workdir=workdir,
                                         inputs_dirs=laid_down_dirs(
                                             engine.validation_procedure(task.id), scratch)) or {}
    except ValueError as e:
        kept = _keep_rejected_report(str(task.id), str(e), text)
        try:
            engine.record_rejected_report(task.id, str(e), entries, tools_used=tools,
                                          validated_by={"validator": validator or "validate_result", "model": _model})
        except Exception:
            log.warning(f"could not keep the refused report on {task.id}", exc_info=True)
        return {"verdict": None, "failed_criteria": [], "error": str(e), "report_kept_at": kept,
                "refusals": int((engine.rejected_report(task.id) or {}).get("refusals", 1))}
    return {"verdict": rec.get("verdict") or verdict,
            "failed_criteria": list(rec.get("failed_criteria") or failed),
            "validator": rec.get("validator")}


def _scope_cap(batch: list) -> Optional[int]:
    """A scope run's cap: the longest bound left among the nodes it validates. One run serves every node in it, and
    each node's own clock hands it on when its own bound passes (`_validation_cap` is that bound for a run of one);
    capped at the first-listed node's remainder, or the shortest, a top that had waited in VALIDATING cut a run over
    deliveries made seconds before to 119 s and 299 s, and every verdict in it came back ⊥ (critics, 2026-09-28)."""
    return max((c for t, *_ in batch if (c := _validation_cap(t))), default=None)


def _validator_texts(engine: Engine, llm, parts: list, workdir, scratch, inside: Optional[frozenset], spawn) -> list:
    """The validator's reports over the parts' deliveries — one run, or one per batch at the same time (`_run_each`),
    each batch carrying a disjoint share of the probes the validation owes over one unchanging set of deliveries, so
    their conjunction is the verdict whatever order they finish in (§2 V = ⋀ cᵢ; `_scope_batches`, `_conjoined`). A
    scope's parts stand each under its own heading (`inside` its members); a node validated on its own (`inside` None) gets its own packet, its contract whole unless
    batched or partly kept from a refused report. The engine refuses a report that leaves a criterion unspoken (⊥ is
    not a pass, §2.3), and on a rich contract one report did: 44 refused against 57 recorded, two E3 runs stalled at 25
    and 42 root criteria (2026-08-21) — so a long contract is batched, every owed probe carried exactly once.
    `GFSO_VALIDATION_BATCH=0` restores the single run, whatever the size."""
    system = (Path(__file__).parent / "mcp" / "prompts" / "validator.md").read_text(encoding="utf-8")
    batches = _scope_batches(engine, parts, validation_batch())

    def _run(batch, client=None, place=None) -> str:
        if inside is not None:
            body = (_scope_validator_packet(engine, batch, workdir, place or scratch, inside)
                    + schema_instruction(_SCOPE_VALIDATOR_SCHEMA))
            cap = _scope_cap(batch)
        else:
            (task, deliverable, crits, *carry), = batch
            body = (_validator_packet(engine, task, deliverable, workdir, place or scratch,
                                      criteria=None if len(crits) == len(task.spec.criteria) else crits,
                                      carry=carry[0] if carry else None)
                    + schema_instruction(_VALIDATOR_SCHEMA))
            cap = _validation_cap(task)
        return (client or llm).run_agent(system, body, allowed_tools=_VALIDATOR_TOOLS, cwd=workdir, timeout=cap)

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
            Path(again).mkdir(parents=True, exist_ok=True)
        return _run(batch, client, again)
    return _run_each(llm, spawn if len(batches) > 1 else None, scratch, batches,
                     _run_again_if_unread if len(batches) > 1 else _run)


def _validation_pass(engine: Engine, top_id: str, nodes: list, claims: dict, workdir, validator, model, llm, spawn,
                     _cb, inside: Optional[frozenset] = None) -> tuple:
    """ONE validation pass over deliveries — a scope's (`inside` its members), or one node's, a scope of one: the
    validator's reports over every node's criteria left to validate (`_left_to_validate` keeps what a refused attempt
    already decided), then each node's OWN verdict recorded over its own entries (`_record_node`). Records only; the
    signatures are the caller's. `nodes`: [(task, its deliverable)]; `claims`: {node: its validation claim}.

    Returns (out, the reports' text): out = {task_id, stats, verdicts: {node: …}, reports: {node: what its reports
    claimed, with its entries}} — or, where the transport refused to start, `error`; where a report did not parse, the
    kept report and no `verdicts`."""
    left = {str(t.id): _left_to_validate(engine, t) for t, _ in nodes}
    parts = [(t, d, left[str(t.id)][0]) for t, d in nodes]
    # The validator runs WHERE THE WORK IS, with a private scratch BESIDE it (`_validation_place`): a shared scratch
    # let one run validate another's leftovers, and a scratch made the working directory opened the validator in an
    # empty tree, where it failed correct work saying nothing was there. A false FAIL at the seam is worse than none.
    scratch, _before = _validation_place(top_id, workdir, tuple(
        p.get("as_run") or p.get("command") for t in engine.all_tasks()
        for ps in engine.regression_probes(t.id).values() for p in ps))
    try:
        texts = _validator_texts(engine, llm, parts, workdir, scratch, inside, spawn)
    except ValueError as ex:
        return {"task_id": top_id, "error": str(ex)}, ""
    text = "\n\n".join(x or "" for x in texts)
    out: dict = {"task_id": top_id, "stats": session_calls(llm, Stage.VALIDATE_RESULT)}
    _strays_left_behind(engine, top_id, workdir, _before, out, _cb)   # `.gfso-scratch` is the offered place
    read = _entries_by_node(texts, parts, _SCOPE_VALIDATOR_SCHEMA if inside is not None else _VALIDATOR_SCHEMA,
                            own=inside is None)
    if read is None:
        # No retry here: an agent run is minutes-long. The report is KEPT, on disk and on the node, as a report the
        # engine refuses is: under delegation the caller is the dispatcher, which reads a verdict and nothing else,
        # and a validation that died with nothing kept left a user polling `get_verdict` for minutes (wave 25,
        # 2026-09-05). And "it wrote nothing" is not "it wrote something unreadable": a call the transport cut
        # (`the_call_was_cut`, the provider's own observation first) is a run that stopped, worth re-running on the
        # same tier, unlike a report that parsed and decided nothing (measured 2026-09-06: fifteen minutes, one
        # sentence, $0.00).
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
    whole = {tid: left[tid][1] + _conjoined(entries[tid]) for tid in entries}
    out["reports"] = {tid: {**said[tid], "per_criterion": whole[tid]} for tid in entries}
    out["verdicts"] = {str(t.id): _record_node(engine, t, whole[str(t.id)], said[str(t.id)], validator, llm,
                                               claims[str(t.id)], model, workdir, scratch, text)
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
    keys = [engine.claims.begin_validation(t.id) for t in nodes]
    if not nodes or None in keys:
        for k in keys:
            if k is not None:
                engine.claims.end_validation(k)
        return {"task_id": str(top_id), "verdicts": {}, "inflight": bool(nodes)}
    llm = _llm or llm_factory(model)
    try:
        llm.on_tick = _cb = emit_cb(engine, "validate_result")
        llm.stage_hint = f"{top_id} scope-validator({validator or 'standalone'})"
        _cb(f"{top_id}: one independent validator over the scope's {len(nodes)} deliveries…")
        out, _ = _validation_pass(engine, str(top_id), [(t, _last_deliver_result(engine, t.id) or "(none recorded)")
                                                        for t in nodes],
                                  {str(t.id): k for t, k in zip(nodes, keys)}, workdir, validator, model, llm,
                                  _spawn or (None if _llm is not None else lambda: llm_factory(model)), _cb,
                                  inside=frozenset(str(m.id) for m in members))
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
    """The files a new goal's request names that stand in the place its work will be done — the workdirs of
    this project's registered roles — written out under the request, so the goal's contract carries them.

    The plan author, its auditors and the root's reviewer are zero-tool completions: a request saying
    "implement what prompt.md specifies" reached them as its one-paragraph summary, and the plan's criteria
    contradicted the 12 KB statement the root's executor then read in its workdir (spreadsheet_engine, AUTO
    haiku, 2026-10-10 — EVIDENCE_LOG §13.38). Whoever reads the contract now reads what the executor reads."""
    bases = _work_places(engine)
    seen, parts = set(), []
    for tok in re.findall(r"[^\s`'\"(),;<>\[\]]+", request or ""):
        tok = tok.rstrip(".:")
        # a word of prose is no file name; a path to a file that stands is one, `Makefile` included
        if "://" in tok or not (Path(tok).suffix or (Path(tok).is_absolute() and Path(tok).is_file())):
            continue
        # the first base the name stands in is the one it names; a name met again is the same document
        for b in bases:
            p = Path(os.path.normpath(Path(tok) if Path(tok).is_absolute() else b / tok))
            if not p.is_relative_to(b) or not p.is_file():
                continue
            if p not in seen and p.stat().st_size <= _DOC_MAX and b"\0" not in (raw := p.read_bytes()):
                parts.append(f"## {p.relative_to(b).as_posix()}\n\n{raw.decode('utf-8', errors='replace')}")
            seen.add(p)
            break
    return ("\n\n# THE DOCUMENTS THIS REQUEST NAMES, as they stood in the work's place when the goal was set\n\n"
            + "\n\n".join(parts)) if parts else ""


def _work_places(engine: Engine) -> list:
    """The directories this project's registered roles work in — this project's own only: an unscoped or another
    project's role stands in someone else's place."""
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
                 "this directory.")


def _work_place_documents(engine: Engine, request: str, model: str) -> str:
    """The files of the work's place that define the work, as a read-only run in each place names them — their names
    only; `_named_documents` carries their text verbatim. The plan's author is a zero-tool completion: given a
    customer's summary that named no file, it never saw the binary, its input or its output, wrote probes against an
    interface that does not exist and, out of budget, `echo` in their place (AUTO haiku 4.5 sql_database,
    GB_sql_database_tmu9cb784, 0.09 held-out). Criteria take their content from contact with the work (d6, §4.1)."""
    named: list = []
    for base in _work_places(engine):
        llm = llm_factory(model)
        llm.stage_hint = f"root place-reader({engine.project_name})"   # named like every role's trace, so it is read
        try:
            text = llm.run_agent(_PLACE_SYSTEM, (request or "") + schema_instruction(_PLACE_SCHEMA),
                                 allowed_tools=("Read", "Glob", "Grep"), cwd=str(base), timeout=600, max_turns=30)
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


def auto_decompose(engine: Engine, request: str = "", root_id: str = ROOT_ID,
                   assignee: Optional[str] = None, executor: Optional[str] = None,
                   depth: int = 1, model: str = MODEL_DEFAULT, fast: bool = False,
                   max_iterations: Optional[int] = None, spec: Optional[dict] = None,
                   _progress=None, author: Optional[str] = None) -> dict:
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
    executor — is not its issuer; then the split maps onto them as issued (Inv-1). No author named: re-authored. Runs on headless subscription-billed Sonnet one-shots.
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
    questions (whose the goal is, whose the work is). **Under a mode (solo / semi / auto) leave both
    out**: the mode, the user's choice, already answers both.

    `spec` builds a plan already authored — the shape `extract_spec` reads off a graph — as it
    stands, with no search: the way to execute ONE plan twice and compare the executions."""
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
        _kid = engine.del_at(engine.depth_of(TaskId(root_id)) + 1 if _root else 1, AgentId(assignee))
        if executor and str(executor) != str(_kid) and not (
                str(_kid) != _agent_id() and AgentId(executor) in engine.workforce.executor_pool()
                and str(executor) != assignee):
            # the lift is the caller's own call without the name (§12.16 (ii)); naming `set_mode` as the way
            # out handed it the user's choice — measured, a semi holder read it, asked to switch, and stopped
            raise ValueError(
                f"this project runs in {engine.mode()['mode']}: the children of '{root_id}' are held "
                f"by {'the system' if str(_kid) != _agent_id() else 'you'}, so they cannot go to "
                f"{executor}. Call it again without `executor` — the mode assigns them.")
        executor = executor or str(_kid)
    if engine.graph.get_task(TaskId(root_id)) is None:
        # the place is read for the plan's author; a plan handed in (`spec`) has none
        found = "" if spec is not None else _work_place_documents(engine, request, model)
        request = (request or "") + _named_documents(engine, f"{request} {found}")
    planner = _decompose.default_llm(model)   # the one door to the plan's transport, as decompose builds it
    try:
        res = decompose_into(engine, request, root_id=root_id, assignee=assignee or _agent_id(),
                             child_assignee=executor, llm=planner,
                             depth=depth, model=model, fast=fast, progress=_cb,
                             # A term of the CONTRACT, chosen per decomposition: how many
                             # rework rounds a node gets before the loop settles (§12.15).
                             max_iterations=max_iterations, spec=spec, author=author,
                             # WHICH EXECUTOR ONE SESSION IS: the fact the decomposer judges each piece's fit
                             # against, so the seams move with the model rather than with a number we set
                             executor=engine.workforce.executor_session(executor or assignee))
    except NoPlan as no:            # no root built: what was spent is still on the record
        return {"root_id": None, "subtasks": [], "holes": [], "stats": no.stats, "error": str(no)}
    finally:
        # …on every path: a build that raised took its calls with it, and a row's ledger showed no plan at all
        # while the plan's author and auditors had spent $0.56 (GB_sql_database_tmu9cb784)
        engine.record_llm_usage(Stage.DECOMPOSER, planner, TaskId(root_id))
    kids = engine.graph.get_active_children(res.root_id)
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
    if not out["subtasks"] and not res.stats:
        out["error"] = ("no subtasks were produced and the model completed no call — the LLM "
                        "provider answered nothing (unreachable, or not authenticated; see the "
                        "server log). A fact about the provider, not about the goal.")
    return out


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
                   client: Optional[str] = None) -> dict:
    """Register a NON-human participant (humans need no registration — an unregistered Del = human,
    the system stays passive). kind: `llm-executor` (nodes assigned to this id AUTOSTART: headless
    executor with work tools in `workdir`, its report wrapped into ACCEPT/DELIVER/BLOCK/CHALLENGE) ·
    `llm-validator` (the auto-validation instrument, fired on every delivery it is bound to. It also
    SIGNS the verdict when the node's issuer is automated — the standing agent id `agent`, or a
    registered role. A PERSON is any other name: their node is validated, recorded, and then waits for
    them to signal, because §10.3 keeps the verdict the issuer's act. Note where that line falls: the
    default identity on every door IS the standing agent, so a caller who never names themselves gets
    the signing too — pass your own `source`/`assignee` to be a person here) · `external` (a system
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

    THIS VERB LIVED ON THE AGENT DOOR ALONE. A person driving from the CLI or the HTTP API was told
    by the log to `reassign` a node to a registered role and had no verb anywhere to make one —
    so delegation, parallel execution and an independent validator were unreachable from the human
    door entirely (measured 2026-08-21). The roster is one server-wide fact; every door asks it."""
    # THE STANDING AGENT ID IS NOT A ROLE, AND REGISTERING IT MAKES EVERY UNNAMED CALLER ONE.
    # `agent` is what every door hands a caller who does not name themselves — on this server, in
    # every project — so a roster entry under that id is not a participant, it is a redefinition of
    # the default identity. Both halves of that were measured within a day. As a VALIDATOR it made
    # the executing identity the one whose signature closes the seam (closed at the gate: a
    # registration cannot make an id independent of itself). And its registered `workdir` then
    # became the place auto-validation validated in — a stranger on the MCP door watched their delivery
    # validated against ANOTHER session's project, the temp directory a different tester had registered
    # hours earlier, and it caught their fabrication for entirely the wrong reason (wave 23,
    # 2026-09-03). Refused here rather than patched downstream: every consumer of the roster would
    # otherwise need to know that one id means something else.
    if str(agent_id) == _agent_id():
        return {"refused": True, "error":
                f"'{agent_id}' is the STANDING identity this door gives every caller who does not "
                f"name themselves — it is not a participant that can be registered. A role under "
                f"that id would redefine the default identity for every session and project on this "
                f"server: its workdir would become the place unattended validations validate in, and "
                f"its kind would attach to whoever simply omitted a name. Register the role under "
                f"its own id (`{agent_id}-val`, `{agent_id}-exec`, or anything else) and assign "
                f"nodes to THAT id — which is also what makes the delegation visible in the graph."}
    agents = _roster(engine)
    out = agents.register(agent_id, kind, model=model, workdir=workdir, validator=validator,
                          oracle_map=oracle_map, max_turns=max_turns, client=client,
                          project=engine.project_name)
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
        who = agents.validator_for(agent_id)
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
            f"you to validate them. A validator registered for another directory is NOT used: it would "
            f"validate a tree that holds none of this work." if workdir else
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
                             or (not c.get("validator") and agents.validator_for(a) == agent_id)))
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
        live = [t for t in engine.graph.active_tasks()]
        out["assigned_live"] = sorted(str(t.id) for t in live if str(t.assignee) == agent_id)
        # by the dispatcher's own reading of who issued a node (a root is its own issuer)
        out["issued_live"] = sorted(str(t.id) for t in live
                                    if str(engine.graph.issuer_of(t.id)) == agent_id)
    return out


_MODE_STAFF = {Mode.AUTO: 2, Mode.SEMI: 1, Mode.SOLO: 0}


def set_mode(engine: Engine, mode: str, boundary: Optional[int] = None,
             agent: Optional[str] = None, user_said: str = "", perform: str = "dispatch") -> dict:
    """Set WHO HOLDS WHICH NODES in this project — the user's choice, made once, before the plan.

    - `solo` — you (the user-agent) hold and execute every node; the one seam is the root.
    - `semi` — you hold the top of the tree (by default the root; `boundary=k` holds depths 0…k−1)
      and registered executors of this project hold everything below it; you make the issuer's moves
      over what you hold, the system makes them below.
    - `auto` — the system holds every node, the root included; you stay the root's issuer — the
      customer — state the goal, and read its status. You do not intervene: the system makes every
      issuer move, and the project refuses your structuring and validation verbs on its nodes.

    The choice is the USER's: explain the three and ask; do not pick one for them. It governs nodes
    issued AFTER it (an issued node keeps its Del). A mode that needs executors is refused until this
    project has them: auto needs two (the root and its children must be different executors, or the
    children would self-verify with no validator between them), semi needs one, and every mode — solo
    included — needs a validator: the system validates at every seam and at the top of every part of the
    plan larger than one session, whoever holds the node.

    `perform` — HOW you perform the nodes you hold (solo: all, semi: the top; auto: none): `dispatch` (default) —
    you consent and stay their executor, and the system performs each in a clean session of this project's
    registered executor, started only after your ACCEPT, in the node's own place; `in_chat` — you do the work
    yourself, with your own tools, and nothing keeps it inside the contract but you.

    Once the project has work in it, a change needs `user_said` — the user's own words asking for it,
    recorded with the mode: a refusal or a stall is a reason to ask the user, never to switch yourself."""
    try:
        m = Mode(str(mode).strip().lower())
    except ValueError:
        return {"refused": True, "error": f"mode must be one of solo | semi | auto, got {mode!r}"}
    if engine.all_tasks() and not str(user_said).strip():
        # measured live: an AUTO customer that met a stall switched the mode itself and held the project
        return {"refused": True, "error":
                "this project already has work in it, and who holds it is the USER's choice: ask the "
                "user, and pass their own words asking for the change as `user_said`."}
    agents = _roster(engine)
    _delegation().publish_the_workforce(engine, agents.list())
    pool = engine.workforce.executor_pool()
    validators = [a for a, c in agents.list().items()
              if c.get("kind") in ("llm-validator", "unittest-checker")
              and c.get("project") in (engine.project_name, None)]
    if perform not in ("dispatch", "in_chat"):
        return {"refused": True, "error": f"perform must be dispatch | in_chat, got {perform!r}"}
    dispatch = perform == "dispatch" and m != Mode.AUTO          # under AUTO the user-agent holds nothing
    need = max(_MODE_STAFF[m], int(dispatch))
    # A VALIDATOR IN EVERY MODE: the system validates wherever κ ends, whoever holds the node, so solo
    # needs the instrument as much as auto does — without one, the agent is its own only verifier.
    if len(pool) < need or not validators:
        return {"refused": True, "error":
                f"{m.value} needs {need} registered executor(s) of this project and a validator; it "
                f"has {len(pool)} executor(s) ({', '.join(map(str, pool)) or 'none'}) and "
                f"{len(validators)} validator(s)"
                + (" — dispatch performs your nodes in a session of this project's executor" if dispatch else "")
                + f". Register them with `register_agent(<id>, "
                f"\"llm-executor\" | \"llm-validator\", workdir=<the work's directory>)` in this "
                f"project, then set the mode.", "executors": [str(a) for a in pool]}
    try:
        rec = engine.set_mode(m, boundary, AgentId(agent or _agent_id()), said=str(user_said).strip(),
                              hands=str(pool[0]) if dispatch else None)
    except ValueError as e:
        return {"refused": True, "error": str(e)}
    return {**rec, "executors": [str(a) for a in pool],
            "holds": {"solo": "you hold every node",
                      "semi": f"you hold depths below {engine.holder_boundary()}; the system the rest",
                      "auto": "the system holds every node; you are the customer"}[m.value]}


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
    _all = {a: ({**c, "validated_by": _reg.validator_for(a)} if c.get("kind") == "llm-executor" else c)
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

_RAW_TOOLS = {
    **_tools.TOOLS,
    "auto_decompose": _tracked("auto_decompose", auto_decompose),
    "review_decomposition": _tracked("review_decomposition", review_decomposition),   # L2, §9.1
    "validate_result": _tracked("validate_result", validate_result),                  # §10.1
    "register_agent": register_agent, "unregister_agent": unregister_agent, "list_agents": list_agents,                     # the roster
    "set_mode": set_mode,                                                             # who holds what
}

# WHO MAY MOVE WHAT UNDER A MODE — checked at the doors only. The system's own moves (the dispatcher,
# the issuer function) call the verbs in-process, not through this registry, so the lock binds the
# people and agents outside and never the system it hands the work to. Each verb names the node its
# move is about and whose move it is: the ISSUER's (the node's contract, its verdict, its Del) or the
# SPLIT's (the node's decomposition — its executor's act, §11.5 "deferred decomposition").
_MOVE_OWNER = {
    "edit_criteria": ("task_id", "issuer"), "revise": ("task_id", "issuer"),
    "reassign": ("task_id", "issuer"), "reopen": ("task_id", "issuer"),
    "record_verdict": ("task_id", "issuer"),
    "map_criterion": ("parent_id", "split"), "dispute_finding": ("task_id", "split"),
    # the split's register where its Del writes over a split, else the packet's pre-fill — the issuer's (§9.2, §10.1)
    "edit_accepted_risks": ("task_id", "risks"), "create_task": ("parent_id", "split"),
    "decompose": ("parent_id", "split"), "auto_decompose": ("root_id", "split"),
    "signal": ("task_id", "signal"),
    "validate_result": ("task_id", "issuer"), "edit_scope": ("task_id", "issuer"),
    "review_decomposition": ("task_id", "split"),
    "add_dependency": ("to_id", "issuer"), "remove_dependency": ("to_id", "issuer"),
    # the roster names no node: under AUTO re-staffing the validator is a move on the work, below it is free
    "register_agent": (None, None), "unregister_agent": (None, None),
}
#: the executor's signals, read off the one table of who sends what (§11.2) — a hand copy was the second list (D-F18)
_EXECUTOR_SIGNALS = frozenset(s.name for s, r in SIGNAL_ROLES.items() if r is Role.EXECUTOR)


def _mode_lock(name: str, fn):
    """Refuse, at a door, a move the project's mode gave to the system.

    Under AUTO the user-agent is the customer and does not intervene: every move but stating the goal
    (`auto_decompose` on a project with no root yet) is refused. Under any mode, a move whose owner the
    mode made a system executor is refused. With no mode set nothing changes."""
    if name not in _MOVE_OWNER:
        return fn
    sig = inspect.signature(fn)
    key, side = _MOVE_OWNER[name]

    @functools.wraps(fn)
    def _call(*a, **kw):
        try:
            args = sig.bind(*a, **kw).arguments
        except TypeError:
            return fn(*a, **kw)                  # the door answers a malformed call in its own terms
        engine, node = args.get("engine"), args.get(key)
        mode = engine.mode() if engine is not None else None
        if mode is None:
            return fn(*a, **kw)
        if name == "auto_decompose" and not engine.all_tasks():
            return fn(*a, **kw)                  # stating the goal is the customer's one act
        if (name == "signal" and str(args.get("signal", "")).upper() in ("ACCEPT_CHALLENGE", "REJECT_CHALLENGE")
                and node and engine.users_dispute(TaskId(node))):
            return fn(*a, **kw)                  # …and ruling a finding out of his own goal, which the system does not
        if engine.mode_kind() == Mode.AUTO:
            raise ValueError(
                f"this project runs in AUTO (set by {mode.get('by')}): every role on its nodes is held "
                f"by a machine — the autonomous level of §10.4 — and you are the goal's customer: you "
                f"state the goal and read its status (`next_steps`, `get_graph`, `get_verdict`), you "
                f"do not intervene. `{name}` is a move on the work, whatever name it is signed with. "
                + ("Nothing is stated yet: the goal is stated by `auto_decompose(request)` with the user's request. "
                   if not engine.all_tasks() else "") +
                f"The mode is the USER's choice, not yours: if the work seems to need another holder, "
                f"tell the user and ask — change it only on their word.")
        t = engine.graph.get_task(TaskId(node)) if node else None
        if t is None or side is None:
            return fn(*a, **kw)
        if side == "signal":
            role = "split" if str(args.get("signal", "")).upper() in _EXECUTOR_SIGNALS else "issuer"
        elif side == "risks":
            # a machine Del's own moves are in-process, never through this door: here the caller writes as the issuer
            # (the packet's pre-fill) wherever the Del is a machine, and as the split's decomposer otherwise
            role = "issuer" if AgentId(t.assignee) in engine.workforce.executor_pool() else "split"
        else:
            role = side
        owner = engine.graph.issuer_of(t.id) if role == "issuer" else t.assignee
        if owner is not None and AgentId(owner) in engine.workforce.executor_pool():
            raise ValueError(
                f"this project runs in {mode['mode']} (set by {mode.get('by')}): '{t.id}' is held "
                f"below the boundary, so `{name}` on it is {owner}'s move — a machine's role at the "
                f"autonomous level of §10.4, whatever name the call is signed with. You hold the "
                f"levels above; moving the boundary is the user's choice — ask them.")
        return fn(*a, **kw)
    return _call


# The COMPLETE transport registry the doors bind — every verb wrapped so none of them can raise
# into one (`_answering`, above).
TOOLS = {name: _answering(_mode_lock(name, fn)) for name, fn in _RAW_TOOLS.items()}
# The same verbs for the system's own in-process moves: answering, never locked — the mode hands the
# work TO the system, so a lock here refused its own validation of every AUTO delivery (measured live).
SYSTEM_TOOLS = {name: _answering(fn) for name, fn in _RAW_TOOLS.items()}
