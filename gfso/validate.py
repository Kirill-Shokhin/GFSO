"""Validation — judging a delivery against its contract, one job in one module.

The verbs a door calls (`validate_result`, `validate_scope`: a read-only model run over a copy of the delivery, the
system's own run of its pinned checks beside it, the report recorded per criterion) and the dispatcher's validation of
what it holds (`auto_validate`, `auto_validate_scope`: which instrument is bound, its report, its signature where the
system issues). Reads neither the dispatcher (`gfso.delegate`) nor the verb registry (`gfso.tools_llm`): both read it.
"""
from __future__ import annotations

import copy
import hashlib
import json
import logging
import subprocess
import threading
import time
import uuid
from concurrent.futures import ThreadPoolExecutor
from contextlib import ExitStack, suppress
from datetime import datetime
from pathlib import Path
from typing import Optional

from gfso import past, store
from gfso.llm import llm_factory, session_calls
from gfso.executions import execution_of
from gfso.workspaces import node_workspace, rejected_reports_dir, validator_workdir
from gfso.roster import AgentRegistry, default_agents
from gfso.adapters import worktrees as W
from gfso.adapters.snapshots import BuildFailed, NotTheDelivery, Uncopied, judged_at, snapshot, swap
from gfso.adapters.execution import NODES as _NODES, scratch_of
from gfso.adapters.verifiers import evaluate_unittest
from gfso.adapters.llm.stats import (stat_line, calls_of, is_limit, refused_by_limit, the_call_was_cut, torn_among,
                                     what_stopped)
from gfso.adapters.llm.structured import parse_structured, schema_instruction
from gfso.issuer import CONTACT_ROUND as _CONTACT, signal_ok as _signal, system_issues
from gfso.core.types import (BATCH, HOST, LAID, AgentId, Criteria, LLMProviderPort, PlaceUnavailable, Probe, Signal, Stage,
                             State, TaskId, Verdict, files_at, system_decides)
from gfso.engine.verdicts import BEING_OBSERVED, OUTSIDE, READ_NOT_OBSERVED, carried_outside, outside_seen
from gfso.core.protocol.invariants import INTENT, RED_SET, criterion_meant, probes_of, red_set, spoken_verdict, verdict_word
from gfso.core.protocol.procedure import laid_down_dirs, probe_id
from gfso.core.protocol.accounting import (NOT_ASKED_AGAIN, SYSTEMS_ACT, canonical_citations, with_engine_observations,
                                           with_part_observations)
from gfso.core.graph.model import generation_of_task, project_now, project_state_bound
from gfso.observe import FRESH_S, OBSERVE_S, run_checks
from gfso.places import cheap_to_ask
from gfso.engine import CheckRunning, Engine
from gfso.engine.events import emit_cb
from gfso.engine.findings import record_round
from gfso.engine.loop import state_bound_left
from gfso.engine.validation import StaleRun, whole_waits_for_its_parts
from gfso.engine.closures import verdict_provenance
from gfso.config import CALLER, MODEL_DEFAULT, state_bound, validate_internal, validation_batch
from gfso.packets import (BUILT, TECH_REPORT, UNCOPIED, last_deliver_result, scope_order, scope_validator_packet,
                          validator_packet, file_tech_reports, owed_probes, snapshot_note, change_text)
from gfso.inflight import flight
from gfso.tools import answering

log = logging.getLogger(__name__)

#: the head of the name of the thread a validation's outside probes run in, after its record (`_observe_outside`)
OUTSIDE_RUN = "gfso-outside-"


def validate_internal_on() -> bool:
    """Is every node independently validated, INTERNAL ones included (`GFSO_VALIDATE_INTERNAL`)?

    The one owner of the question, so that the panel reporting it and the code obeying it cannot
    drift: `/api/runtime` is the measurement arm's only preflight, and a declared value that the
    mechanism does not actually have would let a run measure the wrong thing in silence. Read at
    call time — the dial is set per run, after import (§10.3 is the default; this restores
    every-node validation for measurement)."""
    return validate_internal()


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
                           # …each word's meaning where the report is written (§2.3, Inv-3; §11.2 for
                           # `not_decidable`): two ⊥s apart — the instrument's, which another validation can cure, and
                           # the text's, which only its author repairs; one word for both sent a delivery that did not
                           # build to «rewrite the criterion» instead of rework (critic over cc4da2d)
                           "verdict": {"type": "string", "enum": ["pass", "fail", "undecidable", "not_decidable"],
                                       "description":
                                       "`pass` only when every behaviour was observed holding; `fail` with an "
                                       "observation that refutes it — the delivery not building, not running or "
                                       "lacking what the criterion needs is such an observation; `undecidable` when "
                                       "you observed nothing that decides it — it fails nothing and is asked again; "
                                       "`not_decidable` only when the criterion's own words cannot be decided on any "
                                       "delivery (an action, an opinion, nothing observable) — a defect of its text, "
                                       "its `evidence` saying what in the words makes it so"},
                           "evidence": {"type": "string", "description":
                                        "one line: the command and what it printed, or the file and what it holds"},
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
                                                         "criterion's own words. A behaviour is what can "
                                                         "be false on its own: two clauses that cannot "
                                                         "fail apart (a fact and its negative restatement) "
                                                         "are one"},
                           # …and the person's words a fail of `answers_the_persons_words` stands on, checked against
                           # their record (`invariants.verdict_report_defects`)
                           "quote": {"type": "string", "description":
                                     f"only on `{INTENT}` failed: the span of the person's own words the result misses — "
                                     "3 words or more of one thing they said, or all of a shorter one, never the plan — "
                                     "one unbroken span copied as written, no `…`; any verdict short of pass on it needs one"},
                           # The claim must be RE-RUNNABLE, on the PASS side as much as the FAIL
                           # side: the measurement's load-bearing direction is the false PASS.
                           # ONE PROBE PER BEHAVIOUR, in the same order.
                           "probe": {"type": "array", "description":
                                     "the observations this verdict stands on, on the pass side as on the fail side: "
                                     "every behaviour in `behaviours` observed by a probe labelled with it — a pinned "
                                     "check the system ran, cited by its id, or a command of your own",
                                     "items": {"type": "object", "properties": {
                               # The pinned probe's own name, when this entry is one of them. The
                               # contract pins its procedure before the work (A1/§2, Inv-1 §12.3)
                               # and a PASS that skips a pinned probe is refused — so a report says
                               # which of them it ran. Matching also works by the command text, so
                               # an id is never a thing to fabricate — but a command or a bare hash
                               # that two demanded probes share names neither (`accounting.part_credit`).
                               "id": {"type": "string", "description":
                                   "the id in brackets, when this entry runs a PINNED CHECK or a "
                                   "REGRESSION line of the contract (omit for your own exploration). "
                                   "Without it the probe is matched by its exact command; a command "
                                   "or hash two demanded probes share counts for neither. A pinned check "
                                   "is cited or run exactly as the packet gives it, however broken it "
                                   "looks — a command of yours in its place observes nothing it pins"},
                               # …and for a PART'S PINNED CHECK, whether it held: the verdict is per criterion,
                               # and only this says a failure is the part's, read on this delivery
                               # (`accounting.parts_not_shown_holding`)
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
                                          "code. Never fabricated: an absence you did not search for "
                                          "is unobserved. (Three honest reports in a row were sent back over "
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
                                             "run genuinely observes several. Unlabelled probes are "
                                             "only counted against the behaviours, and a behaviour "
                                             "they do not reach is unobserved"}},
                               "required": ["command", "expect"]}}},
            "required": ["criterion", "verdict", "evidence", "behaviours", "probe",
                         "divergences"]}},
        "seams": {"type": "string", "description":
                  "an advisory: a dependency the delivery stubs instead of using its producer's real output — it "
                  "decides nothing; where it makes a criterion fail, that criterion's own evidence shows it"},
        # WHAT WAS SEEN BEYOND THE CRITERIA, as data for the issuer and never a verdict input (Inv-2): written in prose
        # ("observed but outside the stated criteria … NOT IN (SELECT …) give NULL"), the row's held-out miss was seen
        # at contact and no channel carried it to the one who could write the criterion (§8.3 FM-1.f at contact)
        "outside": {"type": "array", "description":
                    "what you OBSERVED that no criterion here states — a behaviour the goal or the spec plainly needs "
                    "that the delivery lacks. Not a divergence and no verdict: it fails nothing; it goes to the issuer, "
                    "who judges it against the goal. Leave it empty when there was none",
                    "items": {"type": "object", "properties": {
                        "what": {"type": "string", "description": "the behaviour, one line"},
                        "evidence": {"type": "string", "description": "the command you ran and what it printed"},
                        # …and the scenario that shows it, which the SYSTEM runs on a fresh copy of the delivery as it
                        # runs a pinned check (`_observe_outside`): the issuer is told whether it was seen there
                        "probe": {"type": "object", "description":
                                  "the command that shows it, re-runnable as-is in the delivered directory, and a "
                                  "substring its output shows: the system runs it on the delivery and tells the issuer "
                                  "what it printed; without one the entry reaches them as read, not observed",
                                  "properties": {"command": {"type": "string"}, "expect": {"type": "string"}},
                                  "required": ["command", "expect"]}},
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
    # …but a node the person's agent holds in its chat it may have checked whenever it calls: its own check at any node
    # (§10.2), as the kit's critic is called on a piece of work (the author, 2026-11-20)
    if not engine.observed_here(TaskId(task_id)) and not engine.held_in_chat(TaskId(task_id)):
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
                         f"criterion, which is about the CONTRACT, not the run. Lifted by a move that is yours: "
                         + ("its issuer revises what it promises (`edit_criteria`) or records the verdict with what "
                            "they observed (`record_verdict`), or hands the node on (`reassign`): VALIDATING admits "
                            "none of its executor's signals." if task.state == State.VALIDATING else
                            "its holder CHALLENGEs the criterion no report could decide, and its issuer revises what "
                            "it promises (`edit_criteria`); a repair of what failed is a new tree, checked afresh.")
                         + " `get_verdict` shows what the refused reports did check."}, None, None
    deliverable = deliverable or last_deliver_result(engine, TaskId(task_id))
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
    """The second a validation's round was made in, read off its name (`<node digest>_<epoch>`); 0 where it carries none."""
    tail = name.rsplit("_", 1)[-1]
    return int(tail) if tail.isdigit() else 0


def _validation_place(task_id: str, workdir, ex, named: tuple = (), graph=None, project=None):
    """Where the validator runs: a round of its own in the scratch beside the delivery, which its copy is read into.

    Two needs once collapsed into one: a fresh scratch per validation (a shared one let
    a run validate another's leftovers), and the working directory being the DELIVERY's (a
    validator opened in the scratch saw an empty tree and failed correct work). The
    scratch is a SIBLING of the delivery, so a criterion like "every file here belongs
    to this package" stays true. None: no scratch (a delivery on a share), and no judge runs."""
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
        root = scratch_of(workdir, project, ex)
        # …a round of its own, never one an earlier validation in the same second holds: its batches are made fresh
        at = int(time.time())
        # …one path component, whatever the id spells: `db/schema` had a place and no round, a node stuck with no validator run (critic, ran)
        # …named by a digest of the node, not its id: the copy and the work its checks make lie below, and a long id put
        # their paths past Windows' 260 — `git init` refused in the validator's round alone, three validations of one
        # node read {} where the system's own run, in a short temp, passed (2026-11-22..24)
        key = hashlib.sha256(str(task_id).encode()).hexdigest()[:10]
        while ex.files.exists(scratch := str(root / f"{key}_{at}")):
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
    return scratch


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
    reg = default_agents()
    return validator_workdir(
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
        + f" · {stat_line(llm)}")
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
    inflight_key = engine.claims.begin_validation(TaskId(task_id), (engine.delivered(TaskId(task_id)) or (None,))[0])
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


def _before_its_delivery(engine: Engine, task_id: str, workdir, validator) -> Optional[dict]:
    """{tree, commit, workdir, deliverable} of a check before the delivery — a seam the person issued, at work, its
    holder's place a repository's top with a commit —, the refusal naming what is missing, or None: no such check here,
    the validation as it always was."""
    t = engine.graph.get_task(TaskId(task_id))
    # …a check already running is not skipped here: the claim answers it (`CheckRunning`) — skipped, a second call in
    # the same instant fell to the plain path on a node at work and could leave no verdict (critic over d7f8dc5)
    if t is None or t.state not in (State.EXECUTING, State.REWORKING) or not engine.persons_seam(t.id):
        return None
    place = (workdir or validator_workdir(engine, default_agents(), t.id)
             or _registered_workdir(engine, task_id, validator))
    head = W.git(place, "rev-parse", "--verify", "-q", "HEAD^{commit}").stdout.strip() if place and W.is_repo_top(place) \
        else ""
    if not head:
        return {"task_id": task_id, "state": t.state.name, "verdict": None,
                "error": f"nothing to check before {task_id}'s delivery: {place or 'no place'} is not the top of a git "
                         f"repository with a commit — the check judges the committed tree you will deliver; commit "
                         f"your work there, or pass `workdir=` naming that repository"}
    tree = W.git(place, "rev-parse", f"{head}^{{tree}}").stdout.strip()
    return {"tree": tree, "commit": head, "workdir": str(place),
            "deliverable": f"the committed tree of {task_id} at {place} (commit {head[:12]}), checked before its "
                           f"delivery: what the holder will hand in"}


def validate_result(engine: Engine, task_id: str, deliverable: Optional[str] = None,
                  model: str = MODEL_DEFAULT, workdir: Optional[str] = None,
                  validator: Optional[str] = None,
                  _llm=None, _progress=None, _spawn=None) -> dict:
    """Validate EXECUTION (≠ `review_decomposition`, which checks the decomposition PLAN): spawn ONE independent
    read-only validator agent (Read/Bash/Glob/Grep — it RUNS tests; executed evidence outranks assessment)
    against the node's criteria + the executor's DELIVER report, recording per-criterion verdicts and
    `failed_criteria`. Call it while the node is VALIDATING, after every delivery. Answers at once: a refusal or a
    run already in flight as itself, else `{running, checks: {tree, commit}}` while the validator runs on in the
    server (minutes) — its verdict lands on the record, `get_verdict(task_id)` reads it, the node is in flight on
    `next_steps` meanwhile, and a second call starts no other; the one wait on it is the server's (`gfso wait`). This tool is the
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
    did not parse; NEVER read that as pass — the raw report_text is attached for your own assessment
    (`get_verdict` shows what a refused report did manage to check).

    At a seam the person issued, called by its holder while the node is at work (EXECUTING, REWORKING), it checks the
    holder's committed tree before the delivery: the same validator over that commit, recorded as a check of that tree,
    no state moved. Its DELIVER of that tree is admitted once that check passes (`validation.unchecked_at_his_seam`)."""
    if engine.judges_before_delivery(task_id):
        return _a_check_running(engine, task_id)
    if (before := _before_its_delivery(engine, task_id, workdir, validator)) is not None:
        if before.get("error"):
            return before
        with ExitStack() as held:
            try:      # …the claim on the check, taken at once: a second started with it starts nothing
                held.enter_context(engine.judging_before_delivery(task_id, before["tree"], before["commit"]))
            except CheckRunning:
                return _a_check_running(engine, task_id)
            out = _validated(engine, task_id, deliverable or before["deliverable"], model, before["workdir"],
                             validator, _llm, _progress, _spawn)
        return {**out, "checked_before_delivery": {"tree": before["tree"], "commit": before["commit"]}}
    return _validated(engine, task_id, deliverable, model, workdir, validator, _llm, _progress, _spawn)


def _a_check_running(engine: Engine, task_id: str) -> dict:
    """The answer to a check asked while one of the node's committed tree before its delivery runs."""
    tree, commit = (engine.delivered(TaskId(task_id)) or (None, None))[:2]
    return {"task_id": task_id, "inflight": True, "verdict": None, "checks": {"tree": tree, "commit": commit},
            "note": f"a check of {task_id}'s committed tree before its delivery is running now: this call started "
                    f"nothing, and its verdict lands by itself — `get_verdict('{task_id}')` reads it"}


def _validated(engine: Engine, task_id: str, deliverable, model, workdir, validator, _llm, _progress, _spawn) -> dict:
    """The validator run `validate_result` makes, once whether it checks a tree before its delivery is decided."""
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
            _cb(f"{task_id}: validator report did not parse (verdict=null) · {stat_line(llm)}"
                + (f" · report kept: {out.get('report_kept_at')}" if out.get("report_kept_at") else ""))
            return out
        recorded, said = out.pop("verdicts")[task_id], out.pop("reports")[task_id]
        if recorded.get("stale"):        # …an earlier round's run: no verdict, and no ⊥ of the round at work either
            return {**out, "verdict": None, "stale": recorded["error"]}
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
            _cb(f"{task_id}: validator report is NOT a verdict — {recorded['error']} · {stat_line(llm)}"
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
    return {**es[0], "verdict": worst.get("verdict"), **({"quote": worst["quote"]} if worst.get("quote") else {}),
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
    this validation is dropped, as an unplaced entry is. Its `probe` is kept where it names a command and what it
    must show: the system runs it (`_observe_outside`)."""
    for o in (o for o in parsed.get("outside") or () if isinstance(o, dict)):
        tid = next(iter(said)) if own else _named_node(o)
        if tid in said and str(o.get("what") or "").strip():
            p = o.get("probe") if isinstance(o.get("probe"), dict) else {}
            probe = {k: str(p.get(k) or "").strip() for k in ("command", "expect")}
            # …`row`: where the system's run of its probe, made after the record, writes what it saw (`see_outside`)
            said[tid]["outside"].append({"what": str(o["what"]).strip(), "evidence": str(o.get("evidence") or "").strip(),
                                         **({"probe": probe} if all(probe.values()) else {}),
                                         "observed": BEING_OBSERVED if all(probe.values()) else READ_NOT_OBSERVED,
                                         "row": uuid.uuid4().hex[:12]})


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
    # WHAT A REFUSED ATTEMPT SAW OUTSIDE THE CRITERIA STANDS: a contact reading for the issuer (§8.3 FM-1.f), no value of
    # V, so the refusal of that report's verdict refuses none of it. Dropped with the report, the issuer never heard it,
    # and the retry — asked to close the gap — did not find it again (replay r3, 2026-11-28: named at 02:19, refused, lost)
    said["outside"] = carried_outside(said.get("outside") or [], engine.refused_report_for_this_delivery(task.id))
    try:
        if said.get("contradiction"):
            raise ValueError(said["contradiction"])
        # WHOSE INSTRUMENT SPOKE: the registered role's id when one drives this, else the verb's name
        rec = engine.record_exec_verdict(task.id, verdict, failed,
                                         validator or "validate_result", per_criterion=entries,
                                         tools_used=tools, require_probe=True, generation=claim.key[1:],
                                         log_at=claim.log_at, tree=claim.tree, model=_model, workdir=workdir,
                                         outside=said.get("outside") or (),
                                         inputs_dirs=laid_down_dirs(
                                             engine.validation_procedure(task.id), scratch)) or {}
    except StaleRun as e:       # …a run of an earlier round decides nothing now, nor counts against the round at work
        return {"verdict": None, "failed_criteria": [], "error": str(e), "stale": True}
    except ValueError as e:
        kept = _keep_rejected_report(engine.project_name, str(task.id), str(e), text)
        try:
            engine.record_rejected_report(task.id, str(e), entries, tools_used=tools,
                                          validated_by={"validator": validator or "validate_result", "model": _model},
                                          outside=said["outside"])
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
    matched as a part of what it prints, and its PASS is held to what it printed here (`accounting._reproduced`). A
    probe the system could not run is a row with a `note` and no `matched`, said in the record as not observed. Laid
    over the report before it is recorded (`accounting.with_engine_observations`); the place itself is never run in. The
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
    return _on_the_delivery(engine, parts, workdir, probes, ex, built, touched) if probes else {}


def _on_the_delivery(engine: Engine, parts: list, workdir, probes: list, ex=None, built: Optional[list] = None,
                     touched: Optional[set] = None, delivered=None) -> dict:
    """{key: row} — each `(key, criterion, probe)` of `probes` run by the system on a fresh copy of the delivery of
    `parts`, in its own scratch, by `observe.run_checks`, within what is left of the validation's bound: the one door by
    which the system runs a command on a delivery (`_observe_pins`, `_observe_outside`). A probe that could not run is
    a row with a `note` and no `matched`. Raises `BuildFailed` / `NotTheDelivery` where the copy cannot be built or made."""
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
                # …the delivery judged, read once where a run in a thread of its own is started: read inside it, a later
                # check of a new commit could stand there (`Engine.delivered` while judging) — critic over 6b8475ea
                delivered = delivered or engine.delivered(*(t.id for t, *_ in parts))
                with snapshot(_read_by_id(engine, delivered, workdir, ex), at / "delivery", ex, delivered=delivered,
                              built=built) as tree:
                    if tree:
                        # …the tree DELIVER recorded, built, and never `git clean`ed: one emptied a shared place's
                        # copy inside an enclosing repository (critic over the fresh copy). State an executor's own run
                        # left in a place with no recorded commit is the pin's to start clean of (`EXACT_TEXT`)
                        why, rows = ("its inputs could not be laid",
                                     dict(run_checks(ex, probes, workdir, judged_at(tree, workdir, ex),
                                                     _pins_budget(probes, _scope_cap(parts, engine.graph)), touched)))
            except Uncopied as e:
                why = str(e)
    return {k: rows.get(k) or {"note": f"not run: {why}"} for k, _, _ in probes}


def _observe_outside(engine: Engine, parts: list, workdir, said: dict, ex=None, _cb=None, top_id: str = "",
                     delivered=None) -> int:
    """Each observation outside the criteria (`_place_outside`) given what the system's own run of its `probe` showed,
    as `observed` (`outside_seen`) — run as a pinned check is, on a fresh copy of the delivery (`_on_the_delivery`):
    a find read off the diff is a suspicion until it is seen, and the validator told to probe it wrote "I built no
    scenario and ran nothing" (live, 2026-11). Made AFTER the verdict is recorded and written onto its rows there
    (`Engine.see_outside`): data for the issuer, read by nothing that decides the verdict (Inv-2; §8.3 FM-1.f), so
    nothing of it may cost the verdict paid for — a failure of its own is its rows' «not run», and the second copy's
    build spends no time the record needed: run in a thread of its own once the record is written (`OUTSIDE_RUN`,
    `_validation_pass`), said through `_cb`. Returns how many the run showed."""
    probes = [((tid, n), Criteria(OUTSIDE), Probe(o["what"], o["probe"]["command"], o["probe"]["expect"]))
              for tid, s in said.items() for n, o in enumerate(s["outside"]) if o.get("probe")]
    try:
        rows = _on_the_delivery(engine, parts, workdir, probes, ex, delivered=delivered) if probes else {}
    except Exception as e:         # noqa: BLE001 — no verdict rests on it: whatever stopped it is said on its rows
        rows = {k: {"note": f"not run: {e}"} for k, _, _ in probes}
    for tid, s in said.items():
        for n, o in enumerate(s["outside"]):
            o["observed"] = outside_seen(o.get("probe"), rows.get((tid, n)))
        try:
            engine.see_outside(TaskId(tid), {o["row"]: o["observed"] for o in s["outside"]})
        except Exception:          # noqa: BLE001 — the rows stay «read, not observed» on the record
            log.warning(f"could not write what the system saw outside the criteria on {tid}", exc_info=True)
    shown = sum(r.get("matched") is True for r in rows.values())
    if _cb:
        _cb(f"{top_id}: the system ran {len(probes)} probe(s) of what the validator saw outside the criteria — "
            f"{shown} shown on the delivery")
    return shown


def _pins_budget(probes: list, cap: Optional[int]) -> float:
    """The seconds the system's run of a validation's pinned checks may take in all: OBSERVE_S, FRESH_S a check, and the
    whole of each bound a check's issuer stated (`Probe.bound_s`) on top — one the shared budget cut would be no bound
    at all — never past `cap`, what is left of the validation's own bound (`_scope_cap`): a run outliving it lands its
    verdict on a node the clock has handed on."""
    asked = OBSERVE_S + sum(FRESH_S + (p.bound_s or 0) for *_, p in probes)
    return asked if cap is None else min(asked, cap)


def _change(engine: Engine, task, commit: str, ex) -> str:
    """What `commit`, the delivery judged, changed since `task`'s work was taken (`packets.change_text`): from the
    commit the record says that work started at — a chat's ACCEPT, its go for a root (`past.start_of`) — read in the
    project's store, which holds the delivery once its judge's copy is read (`store.change`). A node whose work the
    record says no start of — performed by a role of the system, whose ACCEPT records none — is said so, never a base
    inferred from where its branch happens to stand."""
    base = past.start_of(engine, task.id) or None
    try:
        return change_text(commit, base, base and store.change(engine, ex, base, commit))
    except (OSError, subprocess.TimeoutExpired) as e:
        return change_text(commit, base, None, str(e))


def _read_by_id(engine: Engine, delivered: Optional[tuple], workdir, ex):
    """Where a judge's copy of `delivered` is read from, as `snapshot` reads it when the copy is taken: the project's
    store by its id, kept first if absent — from the
    judge's directory, where the work stands, else where its record says it was made (`store.held`). `Absent`, an
    `Uncopied`, where nothing holds it: no verdict. No commit recorded: the directory itself, which `snapshot` refuses
    to copy as it stands."""
    if not (delivered and delivered[1]):
        return workdir
    places = [(str(p), ex) for p in (workdir, W.base_of(str(workdir))) if p]   # …a node's place, its base
    return lambda: store.held(engine, ex, delivered[1], *places)


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
                     seen: Optional[dict] = None) -> list:
    """The validator's reports over the parts' deliveries — one run, or one per batch at the same time (`_run_each`),
    each batch carrying a disjoint share of the probes the validation owes over one unchanging set of deliveries, so
    their conjunction is the verdict whatever order they finish in (§2 V = ⋀ cᵢ; `_scope_batches`, `_conjoined`). A
    scope's parts stand each under its own heading (`inside` its members); a node validated on its own (`inside` None) gets its own packet, its contract whole unless
    batched or partly kept from a refused report. The engine refuses a report that leaves a criterion unspoken (⊥ is
    not a pass, §2.3), and on a rich contract one report did: 44 refused against 57 recorded, two E3 runs stalled at 25
    and 42 root criteria (2026-08-21) — so a long contract is batched, every owed probe carried exactly once.
    `GFSO_VALIDATION_BATCH=0` restores the single run, whatever the size. Each copy is built before its run, what ran
    appended to `built`; a build that fails raises `BuildFailed` (`snapshots._build`). `seen`: what the system's own
    runs of the pinned checks observed (`_observe_pins`), told to the validator in its packet."""
    system = (Path(__file__).parent / "mcp" / "prompts" / "validator.md").read_text(encoding="utf-8")
    batches = _scope_batches(engine, parts, validation_batch())
    ex, delivered = ex or validation_execution(engine), engine.delivered(*(t.id for t, *_ in parts))

    def _run(batch, client=None, place=None) -> str:
        if inside is not None:
            body = lambda changes=None: (scope_validator_packet(engine, batch, workdir, place or scratch, inside, seen,
                                                                changes) + schema_instruction(_SCOPE_VALIDATOR_SCHEMA))
            cap = lambda: _scope_cap(batch, engine.graph)
        else:
            (task, deliverable, crits, *carry), = batch
            body = lambda changes=None: (validator_packet(
                engine, task, deliverable, workdir, place or scratch,
                criteria=None if len(crits) == len(task.spec.criteria) else crits,
                carry=carry[0] if carry else None, seen=seen, changes=changes) + schema_instruction(_VALIDATOR_SCHEMA))
            cap = lambda: _validation_cap(task, engine.graph)
        # RUNS SIDE BY SIDE EACH IN A COPY OF THE PLACE OF ITS OWN (`adapters.snapshots`): sharing the place, one run's
        # pinned `make clean` took the binary from under the others' probes — a false root FAIL (GB_sql_database_tngtvm580).
        # A run alone gets its copy too (`_run_each`); without a scratch no run starts: the delivery is read by its id
        # into a scratch, never judged in the place. Mapped back, the report reads as run in the place.
        # Its cap is read once the copy stands: what is left of T_validate when the run starts, not before the copy took
        # its share — a cap read first let the run outlive the visit by the copy's minutes (`_validation_cap`).
        ran: list = []
        if workdir and not place:
            # …no scratch to read the delivery into (a place on a share): never the executor's place in its stead —
            # its container, its CLI state, its tree to change (§10.3). No validator started: the never-started
            # run, asked again on its own tier and then of a person (critics: read as the place down, it flapped)
            return _no_start(client or llm, "uncopied", str(workdir), f"no scratch beside {workdir} to copy the "
                                                                       f"delivery into: no judge runs in the place")
        try:
            if not workdir:
                # …a goal acted out in the world, no directory anywhere: its judge reads the world at contact (§3.5).
                # A directory with no commit delivered is no such goal: no copy (`snapshot`), no verdict
                return (client or llm).run_agent(system, body(), allowed_tools=_VALIDATOR_TOOLS, cwd=place or None,
                                                 timeout=cap())
            with snapshot(_read_by_id(engine, delivered, workdir, ex), Path(place) / "delivery", ex, edits, delivered,
                          ran) as tree:
                here = judged_at(tree, workdir, ex)       # …the judge's own directory of the commit
                # …what the delivery changed, read once the store holds it: the copy's reading kept it there
                text = (swap(body({str(t.id): _change(engine, t, delivered[1], ex) for t, *_ in batch}), workdir, here)
                        + snapshot_note(here, ran[0] if ran else "nothing"))
                text = (client or llm).run_agent(system, text, allowed_tools=_VALIDATOR_TOOLS, cwd=here, timeout=cap())
                return swap(text, here, workdir)
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
    scratch = _validation_place(top_id, workdir, ex, tuple(
        p.get("as_run") or p.get("command") for t in engine.all_tasks()
        for ps in engine.regression_probes(t.id).values() for p in ps), engine.graph, engine.project_name)
    edits, built, unbuilt, touched = [], [], None, set()
    try:
        # the system's own run of the pinned checks FIRST, on the delivery as delivered (`_observe_pins`)
        if observed := _observe_pins(engine, parts, workdir, built, ex, touched):
            _cb(f"{top_id}: the system ran {len(observed)} pinned check(s) on a fresh copy of the delivery — "
                f"{sum(o.get('matched') is True for o in observed.values())} print what they pin, "
                f"{sum('matched' not in o for o in observed.values())} could not be run")
        texts = _validator_texts(engine, llm, parts, workdir, scratch, inside, spawn, edits, built, ex, observed)
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
    # …and only then, OFF the caller's path, what the validator saw outside the criteria, run by the system: the caller
    # signs the recorded verdict, and a second build and its probes before that sign let VALIDATING's bound pass under
    # a paid verdict (critic over 76e0d949). A server stopping mid-run leaves its rows «being observed», whose words say what that means minutes on
    if not unbuilt and any(o.get("probe") for s in said.values() for o in s["outside"]):
        threading.Thread(target=_observe_outside, args=(engine, parts, workdir, copy.deepcopy(said), ex, _cb, top_id),
                         kwargs={"delivered": engine.delivered(*(t.id for t, _ in nodes))},
                         name=f"{OUTSIDE_RUN}{top_id}", daemon=True).start()
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
    keys = [engine.claims.begin_validation(t.id, (engine.delivered(t.id) or (None,))[0]) for t in nodes]
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
        out, _ = _validation_pass(engine, str(top_id), [(t, last_deliver_result(engine, t.id) or "(none recorded)")
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


def _standing_instrument_verdict(engine, task_id: TaskId) -> Optional[dict]:
    """An instrument's verdict that stands on THIS delivery — {verdict, failed_criteria}, reused rather than paid for
    twice — or None. Current: on this delivery, with nothing it is built from delivered again or FAILed since (the
    engine's own currency rule, `record_stands`, through `current_exec_verdict` — the one question a signature asks
    too; read off the generation alone, a PASS over parts delivered again was replayed into a gate that refused it,
    three times, critic 2026-09-28). An instrument's: a self-report and a verdict asserted by hand are the
    executor's and the issuer's own words, and replaying either under the registered validator's name put verdicts
    an instrument never gave into the log as its PASS (both stranger doors, 2026-09-02)."""
    rec = engine.current_exec_verdict(task_id)
    if (rec is None or verdict_provenance(engine, task_id) != "instrument"
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
    The whole is re-delivered with its parts' rework, in the same session (`scope_report_into_signals`)."""
    failing, undecided, again = set(), set(), set()
    for t in [t for t in scope_order(engine, engine.scope_members(top.id)) if str(t.id) in verdicts]:
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
            # …every undecided node ⊥ where asking again cannot change it (`not_asked_again`): the same tree times out again,
            # a criterion not decidable as written is refused again
            # …read over the nodes a refusal left undecided: one waiting on an undecided part carries no refusal of its
            # own, and read as a re-askable one it hid its part's class from the scope's route
            _not_asked_again([w for x in undecided if (w := str((verdicts.get(x) or {}).get("error") or ""))])
            or "no-verdict"
            if undecided and not again else "rejected")


def _not_asked_again(refusals: list) -> Optional[str]:
    """`no-verdict:spent` where every refusal says no re-asked validation changes it (`accounting.not_asked_again`), else
    None — one word, one route for every class it names."""
    return "no-verdict:spent" if refusals and all(NOT_ASKED_AGAIN in r for r in refusals) else None


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


def auto_validate_scope(engine, top_id: TaskId, agents: AgentRegistry, _llm=None, sign: bool = True) -> str:
    """The scope's ONE validation, and its signatures: the instrument bound to the scope's executor validates
    every delivery the scope holds in one run, each node's own verdict is recorded, and `_sign_scope` signs
    them. 'pass' / 'fail' / 'recorded' / 'rejected' / 'no-verdict' / 'no-instrument', as `auto_validate`."""
    top = engine.graph.get_task(top_id)
    validator_id = _which_instrument_validates(engine, top, top_id, agents, engine.project_name)
    if validator_id is None:
        engine.emit_info("delegate", f"{top_id}: no llm-validator registered — the scope's validation stays manual")
        return "no-instrument"
    verdicts, out = _standing_verdicts(engine, top_id), {}
    if (missing := {str(t.id) for t in engine.scope_members(top_id) if t.state.name == "VALIDATING"} - set(verdicts)):
        vcfg = agents.get(validator_id) or {}
        # …in flight for every reader while it runs, as each session the system starts is: a stop read `stopped` over it
        with flight("validate_scope", engine, top_id):
            out = validate_scope(engine, str(top_id),
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
    project = getattr(engine, "project_name", None) or "default"
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


def _validate_with(engine, agents, task_id, task, validator_id, vcfg, sign, model_override, _llm) -> dict:
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
        ex = execution_of(engine, agents)
        out = _checker_validate(engine, task_id, vcfg, node_workspace(engine, agents, task_id), ex)
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
        # …in flight while it runs, as the verb's own door marks it: a restart, a container's rest and the page read
        # that record, and the dispatcher's own validation left it unmarked when it stopped going through the door
        with flight("validate_result", engine, task_id):
            out = answering(validate_result)(engine, str(task_id),
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
        for kid in engine.graph.get_active_children(task_id):
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


def pass_held_by_parts_outside(engine, agents, task_id: TaskId, judged: tuple) -> bool:
    """Is this whole, still VALIDATING on the delivery `judged`, missing an active part from that delivery
    (`Engine.parts_outside_the_delivery`, which a machine's PASS meets in its own step)? Where the system issues the
    delivery is re-presented, as `_sign_scope` does a footing being redone, and comes again over the part; each add_child
    can cost one. Elsewhere an open part waits in VALIDATING, its issuer's to move, and its bound hands it to him (§16.14)."""
    t = engine.graph.get_task(task_id)
    if (t is None or t.state != State.VALIDATING or generation_of_task(t) != judged
            or whole_waits_for_its_parts(engine.graph, t) or not (named := engine.parts_outside_the_delivery(t))):
        return False                                    # …the signal's own refusal is the answer
    if not system_issues(engine, agents, task_id):
        engine.emit_info("delegate", f"{task_id}: its validator's PASS stands on the record, not signed: "
                                     f"{', '.join(sorted(named))} stand(s) open under it (Thm 1)")
    elif not _represent(engine, t, str(engine.graph.issuer_of(t.id)), named):
        engine.emit_info("delegate", f"{task_id}: its validator's PASS is not signed: {', '.join(sorted(named))} not in it")
    return True


def _replay_a_standing_verdict(engine, agents, task_id: TaskId, rec: Optional[dict], validator_id, sign: bool, judged=None):
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
        if _signal(engine, task_id, sig, validator_id,
                   **({"failed_criteria": tuple(rec.get("failed_criteria") or ())}
                      if sig == Signal.FAIL else {})):
            return "pass" if sig == Signal.PASS else "fail"
        if sig == Signal.PASS and pass_held_by_parts_outside(engine, agents, task_id, judged):
            return "rejected"
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
    if spent := _not_asked_again([f"{_why} {out.get('verdict_defects') or ''}"]):     # …a refused report's reason rides here
        return spent
    if refused_by_limit(_stats) or is_limit(_why):
        return "no-verdict:limit"
    if torn_among(_stats):
        return "no-verdict:torn"
    return "no-verdict" if (_stats or _spent) else "no-verdict:never-ran"


def auto_validate(engine, task_id: TaskId, agents: AgentRegistry, _llm=None,
                   model_override: str | None = None, sign: bool = True) -> str | None:
    """DELIVER→VALIDATING auto-fires the registered validator instrument; the verdict AUTO_PASS-SIGNALS
    (PASS → DONE; FAIL(failed_criteria) → REWORKING — the rework loop lives in the FSM, max_iterations
    bounds it). verdict:null NEVER auto-signals — the one escalation to the issuer. Returns the
    outcome for the dispatcher: 'pass'/'fail' (signed), 'rejected' (the FSM refused the verdict —
    ≠ no-verdict: the graph wasn't ready, revalidate on its next change), 'no-verdict'."""
    task = engine.graph.get_task(task_id)
    judged = generation_of_task(task)      # …the delivery this run reads: a PASS arriving later is about no other
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
    if engine.current_exec_verdict(task_id) is not None and verdict_provenance(engine, task_id) == "by_hand":
        _say_it_is_hand_asserted(engine, task_id, engine.current_exec_verdict(task_id))
    if (out := _replay_a_standing_verdict(
            engine, agents, task_id, _standing_instrument_verdict(engine, task_id) if _vkind != "unittest-checker" else None,
            validator_id, sign, judged)) is not None:
        return out
    vcfg = agents.get(validator_id) or {}
    out = _validate_with(engine, agents, task_id, task, validator_id, vcfg, sign,
                      model_override, _llm)
    if out.get("inflight") or out.get("waiting_on") or out.get("stale"):
        # Neither of these is a failed validation, so neither may cost the node its one
        # no-verdict retry: `inflight` = another validator run (e.g. a manual `validate_result`)
        # already holds this generation; `waiting_on` = the node aggregates children that have
        # not settled, so there is nothing to validate yet (Thm 1). Both behave like a rejected
        # verdict — free the dedup key and revalidate on the graph's next change.
        engine.emit_info(
        "delegate",
        f"{task_id}: validator already in flight — duplicate spawn suppressed"
        if out.get("inflight") else f"{task_id}: {out['stale']}" if out.get("stale") else
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
            # …a root under solo or semi is the person's to sign: their agent shows the verdict and asks (s21: a client
            # signing it itself was stopped as self-approval)
            engine.emit_info(
                "delegate",
                f"{task_id}: validated for you — the verdict is {verdict}, on the record "
                f"(`get_verdict {task_id}`). " + (
                    f"{theirs}." if (theirs := engine.persons_verdict(task_id)) else
                    f"Signing is yours: `signal {task_id} {verdict} <you>` when you agree with it."))
        return "recorded" if verdict else _classify_no_verdict(engine, task_id, out)
    _why: list = []
    if verdict == Verdict.PASS:
        if _signal(engine, task_id, Signal.PASS, validator_id, _why=_why):
            return "pass"
        if pass_held_by_parts_outside(engine, agents, task_id, judged):
            return "rejected"
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
