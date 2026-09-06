"""The LLM half of the action surface — the verbs that SPAWN model runs.

Split from `gfso.tools` (the structural half, L1: core+engine only) so the structural surface
carries zero LLM/adapter dependencies — this module is L2 and pulls decompose/critic/runtime
freely. Same contract as tools.py: pure functions `(engine, *args) -> JSON-able dict`.

`TOOLS` here is the COMPLETE transport registry (structural ∪ LLM) — the binding layers
(MCP / CLI / HTTP) generate their surfaces from THIS dict; `gfso.tools.TOOLS` stays the
structural subset.
"""
from __future__ import annotations

import contextlib
import functools
import inspect
import json
import logging
import os
import shutil
import time
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from datetime import datetime
from dataclasses import asdict
from typing import Optional

from gfso import runtime
from gfso.runtime import llm_factory
from gfso.core.types import TaskId, Signal, Stage, Verdict, passed
from gfso.critic import runner as _critic_runner
from gfso.decompose import decompose_into
from gfso.engine.events import emit_cb
from gfso.engine.validation import _l0_holes, _l2_undischarged, l2_gate_on
from gfso.adapters.llm.stats import _stat_line
from gfso.engine import Engine
from gfso import tools as _tools
from gfso.tools import _agent_id
from gfso.adapters.llm.structured import parse_structured, schema_instruction
from gfso.config import (ROOT_ID, MODEL_DEFAULT, MODEL_VALIDATOR_RETRY, validation_batch,
                         validate_internal)

log = logging.getLogger(__name__)


# WHAT THIS PROCESS IS DOING RIGHT NOW, by verb name. Read by `/api/runtime`, so that a reconcile
# arriving from another session can see there is work in flight and decline to restart the server
# out from under it — a killed server does not take its `claude` children with it.
# A COUNTER, not a set. As a set, the first of two concurrent `validate_result` calls to finish
# cleared the flag while the second was still running — and every tool now runs in its own thread,
# so concurrent calls of one verb are ordinary rather than impossible.
INFLIGHT: "collections.Counter[str]" = __import__("collections").Counter()


def _inflight(name: str):
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


def validate_internal_on() -> bool:
    """Is every node independently validated, INTERNAL ones included (`GFSO_VALIDATE_INTERNAL`)?

    The one owner of the question, so that the panel reporting it and the code obeying it cannot
    drift: `/api/runtime` is the measurement arm's only preflight, and a declared value that the
    mechanism does not actually have would let a run measure the wrong thing in silence. Read at
    call time — the dial is set per run, after import (§14.5 D6 is the default; this restores
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
                                    "Syntactic level (§13.4) is not clean — `list_holes` names "
                                    "those, and they are what to fix first.")}
    if open_findings is None:
        return {"open_count": None, "open_count_note": _nothing_was_judged(a_model_ran)}
    return {"open_count": len(open_findings)}


def _nothing_was_judged(a_model_ran: bool) -> str:
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
            + ". No verdict is never read as clean (§13.4 fail-closed), so execution stays shut. Two "
              "supported ways on: make a checker available and run this again, or take the canon's "
              "EXPLORE branch — `GFSO_L2_GATE=0` on the server, where the plan's causal check is "
              "bought with contact instead of with the checker (§13.5). The second is a deployment "
              "decision, not a workaround: it is what a system with no checker honestly is.")


def _delta_since_the_last_review(out: dict, prev_open, prev_ts) -> None:
    """What changed since the last check of the SAME plan — and the SAME KEYS every time.

    The checker is an approximation (§13.5) and may legitimately differ between runs: on a plan whose
    criteria were byte-identical, one finding vanished and another appeared. A reader who sees which
    findings are NEW can tell a plan that is converging from one that is being re-read.

    Its own owner because the answer's shape is its own contract: `delta_note` was present on a
    node's first review and ABSENT on the second, replaced by `compared_with`, and a client reading
    it raised KeyError on its second call (HTTP door, wave 27, 2026-09-06). Every branch below sets
    all four keys.
    """
    if prev_open is not None and out.get("gate_passed"):
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
    fails ⇒ fix those first) + the L2 CHECKER (canon §13.4 Level 2): one zero-tool call judging, per
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
    _slot = engine.begin_review(TaskId(task_id))
    if _slot is None:
        return {"task_id": task_id, "inflight": True, "verdict": None,
                "note": "a Level-2 check is already running over this version of the plan — "
                        "duplicate spawn suppressed; its verdict lands by itself (`get_review` "
                        "reads it when it does)."}
    llm = llm_factory(model)
    llm.on_tick = _cb
    llm.stage_hint = f"{task_id} L2-checker"
    _cb(f"{task_id}: L2 checker (causal entailment per parent criterion)…")
    # What stood open BEFORE this run, so the reply can say which findings are new (see below).
    # From the STORED review, not from the gate's current view: the gate answers None the moment an
    # edit stales the verdict — which is exactly the situation in which someone re-runs the check —
    # so the delta went blank in the rounds that changed something. Measured on the human door
    # 2026-08-22, on the round where the checker CONTRADICTED two earlier ones: "the round that
    # actually regressed is the round where the delta reporting silently switched off".
    _prev_open = engine.stored_review_findings(TaskId(task_id))
    _prev_ts = (engine.get_critique(TaskId(task_id)) or {}).get("ts")
    try:
        out = asdict(_critic_runner.review_decomposition(engine, TaskId(task_id), llm=llm))
    finally:                      # the slot is released whether the check answers or dies
        engine.end_review(_slot)
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
    _t = engine.get_task(TaskId(task_id))
    _open = _l2_undischarged(engine._graph, _t) if _t is not None else None
    out["execution_admitted"] = bool(
        _t is not None and not _l0_holes(engine._graph, _t)
        and (not l2_gate_on() or _open == []))
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
        "the children may NOT start yet: Level-0 checks are open (`list_holes`)"
        if _t is not None and _l0_holes(engine._graph, _t) else
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
            "required": ["criterion", "verdict", "evidence", "behaviours", "probe"]}},
        "seams": {"type": "string"},
        "failed_criteria": {"type": "array", "items": {"type": "string"}},
    },
    "required": ["verdict", "per_criterion", "failed_criteria"],
}


def _last_deliver_result(engine: Engine, task_id: TaskId) -> Optional[str]:
    stored = engine.deliver_result(task_id)                       # persisted on DELIVER — survives restarts
    if stored:
        return stored
    for e in reversed(engine.audit_log(task_id)):                 # in-memory fallback (older DBs)
        if e.signal == Signal.DELIVER and not e.rejected and e.result:
            return e.result
    return None


def _validator_packet(engine: Engine, task, deliverable: str, workdir: Optional[str],
                      scratch: Optional[str] = None, criteria=None) -> str:
    """The validator's self-contained input: contract + seams + ACCEPTED_RISKS + the DELIVER report.
    Embedded by the system — the validator has no graph access (read-only instrument, §14.5).

    `criteria` names the SUBSET this run judges (all of them by default). A rich contract is judged
    in batches whose conjunction is the same verdict (§10 V = ⋀ cᵢ), because the coverage discipline
    is what one report fails when the contract is long."""
    tid = str(task.id)
    _crits = tuple(criteria if criteria is not None else task.spec.criteria)
    crits = "\n".join(f"- **{c.name}**: {c.description}" for c in _crits) or "- (none)"
    ups = []
    for e in engine.get_dependencies():
        if str(e.to_id) == tid:
            prod = engine.get_task(TaskId(e.from_id))
            name = prod.spec.name or prod.spec.description[:40] if prod else "?"
            state = prod.state.name if prod else "?"
            ups.append(f"- consumes `{e.from_id}` ({name}, state {state})"
                       + (f" — glue: {e.glue}" if e.glue else ""))
    # WHAT THE LAST ATTEMPT ON THIS DELIVERY WAS MISSING. Measured across every run this
    # installation has recorded (2026-09-05): the judge is 56.5% of all spend — $441.77 of
    # $782.10 over 904 calls — and 151 of its reports decided NOTHING, of which **140 named
    # behaviours they never probed**. The rule that refuses them is load-bearing (an unobserved
    # conjunct cannot carry a pass, §11.2) and the failure is not capability: the report was
    # well-formed and its commands were real, it simply did not run one per behaviour it had
    # listed. So the retry re-judged the whole node from scratch at a HIGHER tier — paying twice
    # for a bookkeeping gap — while the one thing that would close it, the list of what went
    # unobserved, sat in the record and reached nobody. An ordinary user had all three of their
    # nodes refused on the first report, at a paid round each, and called the validation loop the
    # worst part of the honest path (wave 25).
    _gap = engine.refused_report_for_this_delivery(TaskId(tid)) or {}
    prior = (f"\n## YOUR PREVIOUS REPORT ON THIS DELIVERY WAS REFUSED — read this first\n"
             f"{_gap.get('defects')}\n\n"
             f"Nothing about the work has changed since; what was missing is the EVIDENCE. "
             f"Judge the same delivery again and give a labelled probe — a command, what its "
             f"output must show, and the `behaviour` it observes — for every behaviour you "
             f"name. Naming three behaviours and probing one is refused; naming one behaviour "
             f"and probing it is not. This is attempt {int(_gap.get('refusals', 1)) + 1}.\n"
             if _gap else "")
    negl = "\n".join(f"- {n.item}" for n in task.spec.accepted_risks)
    return (f"# Node under validation: {tid} — {task.spec.name}\n\n{task.spec.description}\n{prior}\n"
            + (f"## Contract — the criteria (the ENTIRE obligation; use these EXACT names in your "
               f"report)\n" if len(_crits) == len(task.spec.criteria) else
               f"## Contract — the criteria THIS RUN JUDGES ({len(_crits)} of "
               f"{len(task.spec.criteria)}; the others are judged by their own runs, and the node's "
               f"verdict is their conjunction, §10). Use these EXACT names and report on EVERY "
               f"one:\n")
            + f"{crits}\n\n"
            f"## Upstream dependencies (seams — check against the REAL producer output, not a stub)\n"
            f"{chr(10).join(ups) or '- none'}\n\n"
            f"## ACCEPTED_RISKS (declared assumptions of the plan — do NOT fail for these)\n"
            f"{negl or '- none'}\n\n"
            f"## Executor's DELIVER report (where the work lives, how each criterion is claimed met)\n"
            f"{deliverable}\n\n"
            f"Working directory for your tools: {workdir}\n"
            + (f"A private scratch directory, fresh for THIS validation: {scratch}\n"
               f"When you run pytest, pass `-p no:cacheprovider`: its cache directory would "
               f"otherwise be written INTO the delivery, which is the one thing you must not do.\n"
               f"WRITE NOTHING INTO THE DELIVERY. Fixtures, sample inputs, temporary outputs and any "
               f"copy you make go in that scratch — the working directory belongs to the executor, "
               f"and files you leave there become part of what the next judge sees (measured: a "
               f"120 MB fixture and a stray CSV left behind in a delivered tree). Read and RUN "
               f"anything you like in place; create nothing.\n" if scratch else ""))



def _keep_a_report_that_decided_nothing(engine, task_id: str, defects: str, text: str) -> dict:
    """Store a report that produced no verdict — on disk AND on the node — and say so to the caller.

    Both places, because they answer different readers: the file is the evidence, the node's record
    is what `get_verdict` is built from, and under delegation the tool's caller is the dispatcher,
    which reads a verdict and nothing else. Keeping only the first is how an ordinary user came to
    poll `get_verdict` for four minutes on a node whose judging had already died."""
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

    ⊥ is not pass (§10), so a refused report ends the node's automatic progress and the issuer must
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


def _judge(engine: Engine, task, llm, system: str, deliverable: str,
           workdir: Optional[str], scratch: Optional[str], spawn=None) -> str:
    """Run the validator over the node's contract and return ONE report, judging a long contract in
    BATCHES whose conjunction is the same verdict (§10 V = ⋀ cᵢ).

    The bottleneck this exists for was measured on 2026-08-21: the engine refuses a report that
    leaves any criterion unspoken or any named behaviour unobserved (§11.2 — ⊥ is not a pass), and on
    a rich contract that is what reports do. 44 refused reports against 57 recorded verdicts, one
    node refused five times, and two E3 runs stalled at 25 and 42 root criteria. Splitting the
    contract does not weaken the rule: every criterion is judged exactly once, by a run that had room
    to probe it, and the merged report is refused on the same terms as any other.

    `GFSO_VALIDATION_BATCH=0` restores the single run, whatever the contract's size."""
    crits = list(task.spec.criteria)
    size = validation_batch() or len(crits) or 1
    batches = [crits[i:i + size] for i in range(0, len(crits), size)] or [crits]

    def _run(subset, client=None, place=None) -> str:
        return (client or llm).run_agent(
            system,
            _validator_packet(engine, task, deliverable, workdir, place or scratch,
                              criteria=subset if len(batches) > 1 else None)
            + schema_instruction(_VALIDATOR_SCHEMA),
            allowed_tools=("Read", "Bash", "Glob", "Grep"), cwd=workdir)

    if len(batches) == 1:
        return _run(batches[0])

    # THE BATCHES ARE INDEPENDENT, SO THEY RUN AT THE SAME TIME. Splitting the contract unblocked
    # acceptance on a rich node but left its LATENCY additive, and latency is what stalls a run:
    # measured over 170 recorded validations, the median judgement takes 46 s at ≤5 criteria, 90 s
    # at 6–12, 132 s at 13–24 and 312 s beyond — and a 25-minute wait is what ended the last
    # `spreadsheet_engine` segment. Each batch judges a DISJOINT set of criteria over the same
    # unchanging delivery, so the conjunction (§10) is the same whichever order they finish in;
    # what they must not share is the client (its per-call tick state is one call's) or the scratch
    # (one run's leftovers judged by another is the bug the scratch exists to prevent).
    texts: list[str] = [""] * len(batches)
    if spawn is not None:
        def _one(i_batch):
            i, batch = i_batch
            client = spawn()
            client.on_tick, client.stage_hint = llm.on_tick, llm.stage_hint
            place = str(Path(scratch) / f"batch{i + 1}") if scratch else None
            if place:
                Path(place).mkdir(parents=True, exist_ok=True)
            try:
                return i, _run(batch, client, place)
            finally:
                # The spend and the tools are the JUDGEMENT's, whichever client made the call:
                # `record_llm_usage` drains ONE provider, and calls left on a worker are calls that
                # never happened as far as the record is concerned.
                llm.calls.extend(client.calls)
                for k, v in client.last_tool_calls.items():
                    llm.last_tool_calls[k] = llm.last_tool_calls.get(k, 0) + v
        with ThreadPoolExecutor(max_workers=len(batches)) as pool:
            for i, text in pool.map(_one, list(enumerate(batches))):
                texts[i] = text
    else:
        texts = [_run(batch) for batch in batches]

    merged: dict = {"verdict": Verdict.PASS, "per_criterion": [], "failed_criteria": [], "seams": ""}
    for text in texts:
        parsed = parse_structured(text or "", _VALIDATOR_SCHEMA)
        if parsed is None:
            # An unparsed BATCH is an unparsed report: the conjunction is missing a conjunct, and a
            # verdict over the rest would be a verdict over a contract nobody agreed to.
            return ""
        merged["per_criterion"] += list(parsed.get("per_criterion") or ())
        merged["failed_criteria"] += list(parsed.get("failed_criteria") or ())
        merged["seams"] = (merged["seams"] + " " + str(parsed.get("seams") or "")).strip()
        if parsed.get("verdict") != Verdict.PASS:
            merged["verdict"] = Verdict.FAIL
    return json.dumps(merged)


def _refuse_validation(engine: Engine, task_id: str, deliverable, workdir, _llm):
    """Should a validator run be spent here at all — and if not, the answer that says why.

    Six refusals, each bought by a run spent for nothing: an unknown node; children that
    have not settled (Thm 1 would reject the verdict anyway); an internal node, which
    self-verifies (§14.5 D6); an empty working directory, where a judge would conclude from
    an empty room; a delivery that was never made; and no workdir at all. Returns
    `(reply_or_None, task, deliverable)` — resolving which delivery is being judged belongs
    to the same question."""
    task = engine.get_task(TaskId(task_id))
    if task is None:
        return {"error": f"unknown task {task_id}"}, None, None
    # DON'T SPEND A MODEL ON A VERDICT THE GATE WILL REFUSE. A parent's result is the AND over its
    # children (Thm 1), so while one is still open there is nothing to judge — and the PASS gate
    # already knows it: the verdict would be rejected on arrival. The dispatcher checks this before
    # auto-validating; the hand-called door did not, so the cost fell on whoever asked. Measured
    # 2026-08-20: a root was validated with a person's node still OFFERED, the report honestly
    # reported the missing piece, and the node sat in VALIDATING with the work still undone.
    # DELIVER itself stays admissible exactly as §14.3 writes it — this refuses the model run, not
    # the signal.
    # THE SAME PREDICATE THE GATE USES. This asked whether the children had "settled" and counted
    # an ESCALATED one as settled — while the PASS gate requires every active child to have PASSED
    # (Thm 1). So a parent with an escalated child bought a full validator run whose verdict the
    # gate then refused: exactly the waste this pre-check exists to prevent, in the one case it
    # let through. Two spellings of one rule, and the looser one was the one that spent money.
    _open = [c for c in engine._graph.get_active_children(TaskId(task_id)) if not passed(c)]
    if _open:
        return {"error": f"not validating {task_id} yet: it aggregates children that have not "
                         f"settled — " + ", ".join(f"'{c.id}' is {c.state.name}" for c in _open)
                         + ". A verdict here would be refused at the gate (Thm 1: the parent is the "
                           "AND over its children), so the run is not spent. Drive those nodes "
                           "first (`next_steps`); one that waits on a person waits.",
                "waiting_on": [str(c.id) for c in _open]}, None, None
    # D6 (§14.5): independent validation belongs at the SEAM (a root, or Del(child)≠Del(parent)).
    # An INTERNAL node self-verifies (its DELIVER carries self_validation) and its guarantee is
    # carried by the root's validation (Thm 1) — so spawning a validator here is pure overhead. Enforced
    # in the engine, not the prompt (measured live: a Haiku agent ran a validator on every internal
    # child despite the protocol telling it not to — visibility ≠ enforcement). The GFSO_VALIDATE_INTERNAL
    # dial restores every-node validation for measurement runs.
    if not validate_internal_on() and not engine._graph.is_public(task):
        return {"task_id": task_id, "state": task.state.name, "internal": True, "verdict": None,
                "note": "internal node (same Del as its parent) — no independent validation needed "
                        "(D6/§14.5): self-verify by running its check yourself, put the evidence in the "
                        "DELIVER self_validation, and PASS it directly. Independent validation happens "
                        "once, at the root/seam."}, None, None
    # AN EMPTY TREE IS NOT A FAILING ONE. A validator opened where the work is not reports what it
    # honestly sees — "no implementation exists" — and that lands as a FAIL over every criterion, on
    # code that may be perfect. Measured 2026-08-21: a stale roster entry pointed the instrument at
    # another experiment's scratch directory and a root took a false FAIL on seventeen criteria,
    # which then drove the run into the loop that ended it. The judge does not get to conclude from
    # an empty room; refusing costs one comparison, and the alternative costs a run.
    _wd = Path(workdir) if workdir else None
    if _llm is None and (_wd is None or not _wd.is_dir()
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
                "error": f"nothing to judge: the working directory {workdir!r} is empty (or absent), "
                         f"so any verdict from here would be about the DIRECTORY, not the work. "
                         f"{_out} This is the instrument's gap, not the "
                         f"executor's: do not send the node to rework over it (§11.2, ⊥ is not a "
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
                         f"validator opened anywhere else judges an empty tree and fails correct "
                         f"work (measured). {task_id} is {task.state.name}; pass the workdir of the "
                         f"role that executed it (`list_agents` shows it), e.g. "
                         f"validate_result('{task_id}', workdir='…')."}, None, None


    return None, task, deliverable


def _judging_place(task_id: str, workdir):
    """Where the validator runs, and what the delivery held before it did.

    Two needs once collapsed into one: a fresh scratch per validation (a shared one let
    a run judge another's leftovers), and the working directory being the DELIVERY's (a
    validator opened in the scratch saw an empty tree and failed correct work). The
    scratch is a SIBLING of the delivery, so a criterion like "every file here belongs
    to this package" stays true. Returns (scratch, files_before)."""
    scratch = None
    if workdir:
        # BESIDE the delivery, not inside it. One dotted directory rather than a loose
        # `<task>_<epoch>/` per validation — and a SIBLING of the tree being judged, because a
        # criterion like "every file under the target dir belongs to this package" is then true:
        # our own scratch was sitting in the deliverable while the validator dutifully reported
        # everyone else's leavings (measured on the human door 2026-08-22).
        root = Path(workdir).parent / f".gfso-scratch-{Path(workdir).name}"
        scratch = str(root / f"{task_id}_{int(time.time())}")
        Path(scratch).mkdir(parents=True, exist_ok=True)
        # Keep the recent ones (a verdict's evidence is worth reading after the fact) and drop
        # the rest: one directory per validation, inside the repository being judged, otherwise
        # accumulates for the life of the project — a rework loop alone makes several.
        for old_dir in sorted(root.iterdir(), key=lambda d: d.name)[:-20]:
            if old_dir.is_dir():
                shutil.rmtree(old_dir, ignore_errors=True)
    # What the delivery held BEFORE the judge touched it. The instruction above is a prompt, and
    # a prompt is not enforcement (the lesson this project keeps relearning), so the difference is
    # MEASURED rather than assumed. Nothing is deleted: the executor's tree is not this code's to
    # prune, and a stray named in the record is a fact its owner can act on.
    # …AND `None` MEANS UNKNOWN, WHICH IS NOT "IT WAS EMPTY". An unreadable directory left this an
    # empty SET, and every pre-existing file in the delivery was then named as something the judge
    # had left behind — the exact false accusation the comparison exists to prevent, inverted.
    # ⊥ is not zero here either (§11.2): with no pre-image there is nothing to subtract, so the
    # honest answer about strays is silence.
    _before = None
    if workdir:
        try:
            _before = {q.name for q in Path(workdir).iterdir()}
        except OSError as e:
            log.warning(f"the delivery could not be listed before validation ({e}) — this run can "
                        f"say NOTHING about what the judge left behind, and says nothing")

    return scratch, _before


def _strays_left_behind(engine, task_id: str, workdir, _before, out: dict, _cb) -> None:
    """Name what the judging run left in the delivery, if anything.

    The instruction to keep out of the tree is a prompt, and a prompt is not enforcement —
    the lesson this project keeps relearning — so the difference is MEASURED rather than
    assumed. Nothing is deleted: the executor's tree is not this code's to prune, and a
    stray named in the record is a fact its owner can act on."""
    if workdir and _before is not None:
        try:
            strays = sorted({q.name for q in Path(workdir).iterdir()}
                            - _before - {".gfso-scratch"})
        except OSError:
            strays = []
        if strays:
            # …AND WHO ELSE COULD HAVE WRITTEN THEM. Two executors of one plan legitimately share
            # a workspace, so files appearing during a validation may be a SIBLING's work, not
            # the judge's — and naming the judge for them is an accusation in the audit trail
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
    """Where the work is, asked of the roster instead of the caller.

    Both halves were measured as refusals the server could have answered itself. `validator=w-val`
    was passed with the role registered against the delivery's directory and the run refused with
    "the working directory None is empty" — the roster held it and nobody asked. Then the same
    refusal met a plain `validate_result(<node>)` whose Del is a registered role, and told the caller
    to go read `list_agents`: the answer the server was already holding, handed back as homework
    (measured on the human door 2026-08-22 — the tester passed the directory by hand, and the
    hand-passed argument is what then crashed). The Del is the role that DID the work, so its
    registered workdir is the delivery's; a name the roster does not know is a person, and there the
    refusal is the honest answer."""
    reg = _roster()
    task = engine.get_task(TaskId(task_id))
    # …AND THE BOUND JUDGE IS THE THIRD PLACE TO ASK. A ROOT is normally held by the caller
    # themselves — an unregistered id, so the first two questions come back empty — while the
    # project's registered validator stands exactly in the delivery. The refusal then said "agent has
    # no registered workdir (the roster was asked first)" while a judge with the right directory was
    # in the same roster, and the same call went on to produce the verdict anyway (HTTP door,
    # 2026-09-02: "had I trusted the error and stopped, I would have reported the run as stalled
    # while it was in fact passing").
    _bound = reg.validator_for(task.assignee if task else None, project=engine.project_name)
    for who in (validator, task.assignee if task else None, _bound):
        if who and (wd := (reg.get(str(who)) or {}).get("workdir")):
            return wd
    return None


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
                # `get_verdict` names which validator judged (CLI door, wave 27, 2026-09-06).
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
    _node = engine.get_task(TaskId(task_id))
    _state = _node.state.name if _node is not None else None
    if _state != "VALIDATING":
        out["next"] = (
            f"Nothing to sign: '{task_id}' is {_state}, not VALIDATING — this verdict was read "
            f"after the graph moved on (a registered validator signs on delivery, so the node "
            f"may already be settled). Read it as a RECORD, not as an instruction; check the "
            f"node before acting.")
    elif verdict == Verdict.PASS:
        out["next"] = (f"Now sign it: signal('{task_id}','PASS'). This recorded verdict is what "
                       f"unlocks your PASS at the seam (verifier ≠ executor, §14.5).")
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


def _ready_to_judge(engine, task_id, deliverable, workdir, validator, model, _llm, _progress):
    """Everything that can refuse BEFORE a judge is paid for, and the claim on the slot.

    Returns `(refusal, ctx)`: a refusal dict and None, or None and everything the run needs.
    Separate because `validate_result` answers two questions — may this run at all, and what did
    the judge say — and the first had grown into the body of the second.
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
    generation = engine.generation_of(TaskId(task_id))   # the delivery THIS run reads (§14.5 gate)
    inflight_key = engine.begin_validation(TaskId(task_id))
    if inflight_key is None:
        # `verdict: None` EXPLICITLY, and said. The reply had no `verdict` key at all, so a caller
        # doing the obvious `.get("verdict")` got exactly the value this verb's own help says must
        # never be read as a pass — indistinguishable from "the report did not parse" (CLI door,
        # 2026-09-02). Suppressing the duplicate spawn is right; answering in a shape that reads as
        # ⊥ to a naive caller is not.
        return {"task_id": task_id, "state": task.state.name, "inflight": True, "verdict": None,
                "note": "a validator run is already in flight for this node generation "
                        "(node, iteration, reopens) — duplicate spawn suppressed. This is NOT a "
                        "verdict and not a failure to produce one: the running judge's verdict "
                        "lands by itself, and `get_verdict` reads it when it does. "
                        # …AND THE ARGUMENTS OF THIS CALL WENT NOWHERE, WHICH IS THE HALF THAT
                        # MATTERED. A caller escalating the tier reads "suppressed", waits, and gets
                        # a verdict from whatever was already running — so a `model` they chose
                        # deliberately silently did not apply, and nothing in the reply said which
                        # model would actually answer. Measured on the MCP door (wave 23,
                        # 2026-09-03): "I could never tell whether my escalation had taken effect."
                        "NOTE — this call started NOTHING, so any `model` or `workdir` you passed "
                        "was not applied: the verdict that lands is the running judge's, on its own "
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
                        "two reports it cannot decide, it parks the node and says so. Judging it "
                        "yourself — `record_verdict` with what you observed — is the door that does "
                        "not queue behind it."}, None
    return None, (task, deliverable, llm, _cb, generation, inflight_key, workdir)


def validate_result(engine: Engine, task_id: str, deliverable: Optional[str] = None,
                  model: str = MODEL_DEFAULT, workdir: Optional[str] = None,
                  validator: Optional[str] = None,
                  _llm=None, _progress=None, _spawn=None) -> dict:
    """Validate EXECUTION (≠ `review_decomposition`, which checks the decomposition PLAN): spawn ONE independent
    read-only validator agent (Read/Bash/Glob/Grep — it RUNS tests; executed evidence outranks judgment)
    against the node's criteria + the executor's DELIVER report, returning per-criterion verdicts and
    `failed_criteria`. Call it while the node is VALIDATING, after every delivery. This tool is the
    EVIDENCE INSTRUMENT — it never signals ITSELF: you (the issuer) read the report and send PASS or
    FAIL(failed_criteria=...) (verifier = issuer, §14.5; the validator is a fresh context, never the
    work's executor). One case looks otherwise and is not: when a `llm-validator` ROLE is registered
    and the node's ISSUER is automated (the standing agent id, or a registered role — a person who
    names themselves keeps the signature and only the judging is done for them),
    the dispatcher runs that instrument on every delivery and relays ITS verdict as the issuer's
    signal — so a node can reach DONE with no signal from you. That is the registered instrument
    acting, not this verb; `get_verdict` names which validator judged. (Said here because an agent
    read the old sentence and waited to be asked for a PASS that was never coming.) `deliverable` defaults to the node's last DELIVER result from the audit log —
    pass it explicitly if the server restarted since delivery. `workdir` defaults to the registered
    workdir of the node's Del (or of `validator`) — pass it only when the work is somewhere the roster does not say. `verdict: null` = the validator's report
    did not parse; NEVER read that as pass — the raw report_text is attached for your own judgment."""
    _stop, _ctx = _ready_to_judge(engine, task_id, deliverable, workdir, validator, model,
                                 _llm, _progress)
    if _stop is not None:
        return _stop
    task, deliverable, llm, _cb, generation, inflight_key, workdir = _ctx
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
        scratch, _before = _judging_place(task_id, workdir)
        try:
            text = _judge(engine, task, llm, system, deliverable, workdir, scratch,
                          spawn=(_spawn or (None if _llm is not None else lambda: llm_factory(model))))
        except ValueError as ex:
            # The transport refuses to spawn an agent with no working directory (it would run in
            # the state home and judge artifacts it cannot see — a WRONG verdict, not a missing
            # one). Reported as a result rather than raised, because the caller is an agent session.
            return {"task_id": task_id, "state": task.state.name, "verdict": None,
                    "error": f"{ex} — call validate_result(task_id, workdir=…)"}
        if hasattr(llm, "tag_last"):
            llm.tag_last(Stage.VALIDATE_RESULT)
        out: dict = {"task_id": task_id, "state": task.state.name, "stats": list(getattr(llm, "calls", []))}
        # …and what it left behind. `.gfso-scratch` is the offered place and does not count.
        _strays_left_behind(engine, task_id, workdir, _before, out, _cb)
        parsed = parse_structured(text, _VALIDATOR_SCHEMA)
        if parsed is None:
            # No retry: an agent run is minutes-long; the raw report is still evidence for the issuer.
            if getattr(llm, "calls", None):
                llm.calls[-1]["parse_failed"] = True
            # …AND KEPT, exactly as a report the ENGINE refuses is kept. This branch returned the raw
            # text to its caller and stored nothing — which is invisible under delegation, where the
            # caller is the dispatcher and it reads a verdict and nothing else. Two doors measured
            # the same consequence from opposite ends (wave 25, 2026-09-05): the log said "report not
            # kept — see the validate_result output" for a run whose output no person ever saw, and
            # an ordinary user polled `get_verdict` for four minutes on a node whose automatic
            # judging had already died, because the one surface the DELIVER reply had pointed them at
            # is built from this record and there was no record. A judge ran, produced something, and
            # it was gone: against the one promise the audit trail is sold on.
            out.update(_keep_a_report_that_decided_nothing(
                engine, task_id,
                "the validator's report did not parse — no verdict could be read from it", text))
            _cb(f"{task_id}: validator report did not parse (verdict=null) · {_stat_line(llm)}"
                + (f" · report kept: {out.get('report_kept_at')}" if out.get("report_kept_at") else ""))
            return out
        # RECORD FIRST, THEN SPEAK. What is recorded is not always what was claimed: a criterion
        # whose named behaviours were never observed is demoted at the record (an unobserved conjunct
        # cannot carry a pass, §11.2). Building the reply from the CLAIM instead left the demotion
        # inside the database — measured live: a report claiming PASS over two criteria the validator
        # could not run was stored as FAIL, reported as PASS, signed PASS by the auto-validation, and
        # the node closed DONE on evidence the engine had already refused. A guarantee that does not
        # reach the signal is not a guarantee.
        #
        # A report that contradicts its own evidence or leaves a criterion unspoken is NOT a verdict
        # (§10: V = ⋀ over ALL criteria; ⊥ is not pass) — the engine refuses to record it, and the
        # tool reports verdict=null, which NEVER auto-signals (delegate escalates to the issuer).
        # Measured live: a PASS returned over a red `test_values` excused as "ACCEPTED_RISKS-declared".
        try:  # the recorded verdict is what unlocks a self-executed node's PASS (verifier ≠ executor gate)
            # WHOSE INSTRUMENT SPOKE. The record named the VERB — every verdict in a run read
            # `validator: "validate_result"` — so `register_agent`'s promise ("will_be_judged_by:
            # w5-val-1") was unconfirmable afterwards from anywhere (measured on the MCP door
            # 2026-08-21). When a registered role drives this, its id is what goes on the record.
            recorded = engine.record_exec_verdict(TaskId(task_id), parsed["verdict"],
                                       list(parsed["failed_criteria"]), validator or "validate_result",
                                       per_criterion=parsed["per_criterion"],
                                       tools_used=getattr(llm, "last_tool_calls", None),
                                       # THIS instrument must be re-runnable; a human reviewer's
                                       # record (record_reviewer_verdict) is not held to it.
                                       require_probe=True,
                                       generation=generation,
                                       model=getattr(llm, "_model", None) or model,
                                       workdir=workdir) or {}
        except ValueError as e:
            kept = _keep_rejected_report(task_id, str(e), text)
            # …AND INTO THE GRAPH, where the issuer looks. A refused report ends the node's automatic
            # progress and hands the decision to a person — who was then handed nothing: the evidence
            # lived in the tool's return value (which under delegation nobody reads) and in a file
            # whose path scrolled past in a log line. What was actually OBSERVED is not a verdict and
            # is not stored as one; it is stored beside the node so `get_verdict` can show it.
            # Measured 2026-08-21: with a 25-criterion contract the validator returned no verdict
            # twice, the node parked, and the only way to see what it had managed to check was to go
            # find a text file.
            try:
                engine.record_rejected_report(TaskId(task_id), str(e), parsed.get("per_criterion"))
            except Exception:
                log.warning(f"could not keep the refused report on {task_id}", exc_info=True)
            # HOW MANY TIMES THIS HAS HAPPENED HERE, and what that means for the next call. A ⊥ is
            # not a transient error to retry into: the second refusal on one node is the signal that
            # the CONTRACT is beyond what one report can cover, and the answer is a stronger model or
            # a person's own verdict — not a third paid run (measured 2026-08-21: three ⊥ in a row,
            # four runs, ~$0.5, and no surface said how many attempts is normal).
            _n = int((engine.rejected_report(TaskId(task_id)) or {}).get("refusals", 1))
            out.update({"verdict": None, "verdict_defects": str(e), "report_text": text,
                        "report_kept_at": kept, "refusals_on_this_node": _n,
                        "what_to_do": (
                            f"the probes are the INSTRUMENT's to write, not yours, so re-running the "
                            f"same tier usually returns the same gap: "
                            f"validate_result('{task_id}', model='{MODEL_VALIDATOR_RETRY}') is the "
                            f"move, or record your own verdict with what you observed "
                            f"(`record_verdict`)" if _n < 2 else
                            f"do NOT run this again: {_n} reports in a row could not decide every "
                            f"criterion, which is about the CONTRACT, not the run. Either narrow "
                            f"what this node promises (`edit_criteria`), validate a stronger model "
                            f"(validate_result(model=\"opus\")), or record your own verdict with "
                            f"what you observed (`record_verdict`). `get_verdict` shows what the "
                            f"refused reports did manage to check.")})
            _cb(f"{task_id}: validator report is NOT a verdict — {e} · {_stat_line(llm)}"
                + (f" · report kept: {kept}" if kept else ""))
            return out
        except Exception:
            recorded = {}
        # An engine that recorded nothing (an older storage path, a swallowed error) leaves the claim
        # standing — the fallback is the claim, never a silent pass invented here.
        return _the_validators_answer(engine, task_id, out, parsed, recorded, _cb, llm)
    finally:
        engine.record_llm_usage(Stage.VALIDATOR, llm, TaskId(task_id))   # the judge's own spend, recorded
        engine.end_validation(inflight_key)


def auto_decompose(engine: Engine, request: str = "", root_id: str = ROOT_ID,
                   assignee: Optional[str] = None, executor: Optional[str] = None,
                   depth: int = 1, model: str = MODEL_DEFAULT, fast: bool = False,
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
    tokens.

    **`assignee` names the Del of the ROOT, and therefore the ISSUER of every child** (the issuer of
    a node is its parent's Del, §14.1). Passing an executor's id here hands them the whole graph:
    your own `edit_criteria`, `map_criterion` and PASS/FAIL on the children are then refused,
    because you are not their issuer. Measured 2026-08-21 — a caller delegated by passing the
    executor here and spent fifteen minutes locked out of their own plan before `reassign`ing the
    root back. To build a graph someone else owns end to end, this is the parameter for it.

    **`executor` is the other thing you probably meant: the Del of the CHILDREN.** The root stays
    with you — you keep your issuer rights over the whole plan — and the work goes to them, which is
    what "delegate it to X" means everywhere else. Both may be passed; they answer different
    questions (whose the goal is, whose the work is)."""
    _cb = emit_cb(engine, "decompose", _progress)
    # …and SAY it, once, at the moment it happens: naming someone else here makes them the issuer of
    # every child, which is the opposite of what "delegate the work" usually means to the caller.
    if assignee and assignee != _agent_id() and not executor:
        # …and ONLY when they have not already done the other thing. The remedy also interpolated
        # the CALLER's own id ("pass executor=<you>"), which is not the delegation anyone means, and
        # it printed one line before the message saying the children HAD been delegated (measured on
        # the human door 2026-08-22: "the remedy interpolates the wrong variable, and it contradicts
        # the very next line").
        _cb(f"{root_id}: Del={assignee} — that makes {assignee} the ISSUER of every child (§14.1: "
            f"the issuer is the parent's Del), so `edit_criteria` / `map_criterion` / PASS on them "
            f"belong to {assignee} and not to you. To delegate the WORK instead, leave the root with "
            f"you and pass `executor=<the executor's id>`: the children go to them, and the root — "
            f"with the issuer rights over the plan — stays yours.")
    if executor:
        _cb(f"{root_id}: the children are delegated to {executor}; the root stays with "
            f"{assignee or _agent_id()}, who issues them.")
    res = decompose_into(engine, request, root_id=root_id, assignee=assignee or _agent_id(),
                         child_assignee=executor,
                         depth=depth, model=model, fast=fast, progress=_cb,
                         # A term of the CONTRACT, chosen per decomposition: how many
                         # rework rounds a node gets before the loop settles (§14.3).
                         max_iterations=max_iterations)
    engine.record_llm_usage(Stage.DECOMPOSER, res.stats, res.root_id)   # what the plan cost, on the record
    kids = engine.get_active_children(res.root_id)
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
            + (f"{len(res.undecided_obligations)} obligation(s) of the goal are decided by no "
               f"criterion (`undecided_obligations`), so the gate will refuse execution — fix the "
               f"criteria they name and run `review_decomposition('{res.root_id}')`."
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
    reconcile from another session can see the server is busy and decline to restart it."""
    @functools.wraps(fn)
    def wrapper(*a, **kw):
        """Run the verb while its name is marked in flight, so a second call can be refused."""
        with _inflight(name):
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
    # LEFT: import cycle gfso.tools_llm ↔ gfso.delegate — `gfso.delegate` imports this module at
    # module level, so the roster is reached from here only at call time.
    from gfso.delegate import default_agents, ensure_dispatcher
    agents = default_agents()
    if engine is not None:
        ensure_dispatcher(engine, agents)
    return agents


def register_agent(engine: Engine, agent_id: str, kind: str, model: str = MODEL_DEFAULT,
                   workdir: Optional[str] = None, validator: Optional[str] = None,
                   oracle_map: Optional[str] = None, max_turns: Optional[int] = None,
                   client: Optional[str] = None) -> dict:
    """Register a NON-human participant (humans need no registration — an unregistered Del = human,
    the system stays passive). kind: `llm-executor` (nodes assigned to this id AUTOSTART: headless
    executor with work tools in `workdir`, its report wrapped into ACCEPT/DELIVER/BLOCK/CHALLENGE) ·
    `llm-validator` (the auto-validation instrument, fired on every delivery it is bound to. It also
    SIGNS the verdict when the node's issuer is automated — the standing agent id `agent`, or a
    registered role. A PERSON is any other name: their node is judged, recorded, and then waits for
    them to signal, because §14.5 keeps the verdict the issuer's act. Note where that line falls: the
    default identity on every door IS the standing agent, so a caller who never names themselves gets
    the signing too — pass your own `source`/`assignee` to be a person here) · `external` (a system
    that sends its own
    signals; nothing spawns). `validator` on an executor entry = a per-executor instrument override
    (else the first registered llm-validator serves everyone). To delegate work after this: just
    assign/reassign nodes to the registered id.

    `workdir` is REQUIRED for `llm-executor` and `llm-validator`: the directory of the project the
    agent works in or judges. Without it the agent would be spawned where the SERVER stands — the
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
    # became the place auto-validation judged in — a stranger on the MCP door watched their delivery
    # judged against ANOTHER session's project, the temp directory a different tester had registered
    # hours earlier, and it caught their fabrication for entirely the wrong reason (wave 23,
    # 2026-09-03). Refused here rather than patched downstream: every consumer of the roster would
    # otherwise need to know that one id means something else.
    if str(agent_id) == _agent_id():
        return {"refused": True, "error":
                f"'{agent_id}' is the STANDING identity this door gives every caller who does not "
                f"name themselves — it is not a participant that can be registered. A role under "
                f"that id would redefine the default identity for every session and project on this "
                f"server: its workdir would become the place unattended validations judge in, and "
                f"its kind would attach to whoever simply omitted a name. Register the role under "
                f"its own id (`{agent_id}-val`, `{agent_id}-exec`, or anything else) and assign "
                f"nodes to THAT id — which is also what makes the delegation visible in the graph."}
    agents = _roster(engine)
    out = agents.register(agent_id, kind, model=model, workdir=workdir, validator=validator,
                          oracle_map=oracle_map, max_turns=max_turns, client=client,
                          project=engine.project_name)
    # …AND WHO WILL ACTUALLY JUDGE THIS ROLE'S WORK. The roster is server-wide, and an executor
    # registered without an explicit `validator` came back with `validator: null` — while the
    # instrument that would really judge it was whichever llm-validator had been registered first,
    # quite possibly another run's, standing in a directory containing none of this work.
    if kind == "llm-executor":
        who = agents.validator_for(agent_id)
        cfg = agents.get(who) if who else None
        # …AND SAY SO IF THAT NAME IS NOT A ROLE YET. `validator=` is taken at its word, so naming a
        # judge that has not been registered came back as a confident `will_be_judged_by: <name>` —
        # a binding to nothing, and a typo would have read exactly the same (agent door, 2026-09-02).
        # The binding is kept: registering the judge afterwards is the normal order. What changes is
        # that the answer stops asserting a party that does not exist.
        if who and cfg is None:
            out["will_be_judged_by"] = (
                f"{who} — NOT REGISTERED YET, so nothing will judge this role's work until it is. "
                f"`register_agent('{who}', 'llm-validator', workdir='{workdir}')` completes the "
                f"binding; the name is kept either way.")
            return out
        out["will_be_judged_by"] = who or (
            f"nobody YET — no validator stands in {workdir} at this moment. Register one there "
            f"(`register_agent(<id>, 'llm-validator', workdir='{workdir}')`) and it binds to this "
            f"role by workspace, in either order; until then the deliveries of this role wait for "
            f"you to judge them. A validator registered for another directory is NOT used: it would "
            f"judge a tree that holds none of this work." if workdir else
            "nobody yet — register an llm-validator")
        if who and validator is None:
            out["note"] = (f"you named no validator, so this role inherits '{who}'"
                           + (f" (working in {cfg.get('workdir')})" if cfg else "")
                           + ". Pass `validator=` to bind your own instrument — the roster is "
                             "shared by every session of this server.")
    # …AND A VALIDATOR CLOSES THE LOOP THE EXECUTOR OPENED. Registering the executor first answers
    # "nobody YET — register one in this workdir and it binds, in either order"; registering the
    # validator second answered nothing at all, so the promised binding was unconfirmable until an
    # execution was judged 25 minutes later (HTTP door, 2026-09-02). The question is symmetric and
    # so is the answer.
    if kind in ("llm-validator", "unittest-checker"):
        _bound = sorted(a for a, c in agents.list().items()
                        if c.get("kind") == "llm-executor"
                        and (c.get("validator") == agent_id
                             or (not c.get("validator") and agents.validator_for(a) == agent_id)))
        out["will_judge"] = _bound or (
            f"nothing yet — no executor is registered"
            + (f" in {workdir}" if workdir else "")
            + ". An executor registered there binds to this instrument by workspace, in either order.")
    return out


def list_agents(engine: Engine, match: str = "", limit: int = 25) -> dict:
    """The delegation roster {agent_id → kind/model/workdir}. Unlisted ids = humans. SERVER-WIDE,
    not per project: every session of the one server shares it, so it holds other people's roles
    too, and an executor with no `validator` of its own inherits the first llm-validator in it —
    check `will_be_judged_by` when you register.

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
    # …AND WHO WOULD JUDGE EACH EXECUTOR, which the roster never showed. `validator: null` on every
    # entry means "no per-executor override", not "nobody" — the binding is by workspace and is
    # decided at judgement time — so `register_agent`'s promise ("will_be_judged_by: w16-val-1") was
    # unconfirmable from anywhere afterwards (measured on the agent door 2026-08-22).
    _all = {a: ({**c, "judged_by": _reg.validator_for(a)} if c.get("kind") == "llm-executor" else c)
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
    "review_decomposition": _tracked("review_decomposition", review_decomposition),   # L2, §13.4
    "validate_result": _tracked("validate_result", validate_result),                  # §14.1
    "register_agent": register_agent, "list_agents": list_agents,                     # the roster
}

# The COMPLETE transport registry the doors bind — every verb wrapped so none of them can raise
# into one (`_answering`, above).
TOOLS = {name: _answering(fn) for name, fn in _RAW_TOOLS.items()}
