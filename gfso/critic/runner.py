"""L2 critic — the STRUCTURAL GATE + the causal-correctness CHECKER (canon §13.4 Level 2).

Level 2's question is a CHECK, not a hunt: per parent criterion — do the mapped children's
criteria, taken as real-world facts, causally guarantee it? (Plus the semantic FM-2 residue the
formal CHECK-8 cannot see.) EPISTEMIC STATUS (§13.5/§8): the Level-2 AXIS is checkable
only by EXECUTION — no pre-contact instrument can verify it (any verdict is itself a Level-2
claim); this checker is the canon's named LLM-OFFERED approximation — an a-priori estimate over
the faithfulness axis — and the real Level-2 verdict stays with contact (q_D). Hence ADVISORY by
construction, never an acceptance blocker.

Two prior designs are deliberately dead: the analyst⊥judge monolithic critic (E2-refuted:
polices form, cannot move content) and the SEARCH-in-diff-mode hole-hunt (the opposite extreme —
"what is missing" is the DECOMPOSER's question and lives in refine, not here). Staged: the L0/L1
gate BLOCKS the checker (L2 presupposes a structurally-complete graph); the verdict never
auto-fixes — the agent fixes via FSM verbs or consciously declares ACCEPTED_RISKS.
"""
from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import Optional

from gfso.adapters.llm.structured import parse_structured, schema_instruction
from gfso.config import CHECKER_READINGS, SUFFICIENCY_READINGS
from gfso.core.types import CriticVerdict, Stage, TaskId
from gfso.decompose.loop import _tag
from .types import NodeCritique

log = logging.getLogger(__name__)

# The checker's report contract (parsed, never trusted): one entry per parent criterion; an
# incomplete verdict is treated as NO verdict (semantic_covered=None — never read as clean).
CHECKER_SCHEMA = {
    "type": "object",
    "properties": {
        "criteria": {"type": "array", "items": {
            "type": "object",
            "properties": {"criterion": {"type": "string"},
                           "verdict": {"type": "string",
                                       "enum": list(CriticVerdict)},
                           "why": {"type": "string"}},
            "required": ["criterion", "verdict", "why"]}},
        "conflicts": {"type": "array", "items": {
            "type": "object",
            "properties": {"between": {"type": "array", "items": {"type": "string"}},
                           "why": {"type": "string"}},
            "required": ["between", "why"]}},
    },
    "required": ["criteria"],
}

# The UNDECIDED-OBLIGATIONS contract — the question no gate asked. Named apart from
# CHECK-7:sufficiency on purpose: that one is the L1 numeric-bound tier (are the children's
# NUMBERS enough for the parent's?), this one asks whether the criteria decide the GOAL, and
# one word over two rules is how a package ends up with two owners of neither. Level 2 checks that the CHILDREN's criteria
# carry the parent's; nothing checked that the node's OWN criteria decide its OWN goal, and that is
# FM-1.f ("the goal needed a criterion nobody wrote"). Measured 2026-08-21 on two closed measurement
# runs: a regex engine signed off DONE on two root criteria — "does not import `re`" and "parses
# consistently" — neither of which requires it to MATCH anything, with 21 hidden tests failing; and
# a whole `sed` interpreter had run under a single root criterion. Seven runs, root contracts of
# one to four criteria, and honest complete verdicts over every one of them.
UNDECIDED_SCHEMA = {
    "type": "object",
    "properties": {
        "gaps": {"type": "array", "items": {
            "type": "object",
            # `obligation` is the goal's own words; `admits` is the test of the finding itself — a
            # result that satisfies every criterion and still fails the obligation. A gap whose
            # author cannot describe such a result is not a gap.
            "properties": {"obligation": {"type": "string"}, "admits": {"type": "string"}},
            "required": ["obligation", "admits"]}},
    },
    "required": ["gaps"],
}

# The ATOMICITY report contract (the same check over the degenerate plan D(t)=∅): is the goal one
# unit of work, or does it hold separable, independently-deliverable parts? Incomplete ⇒ no verdict.
ATOMICITY_SCHEMA = {
    "type": "object",
    "properties": {
        "verdict": {"type": "string", "enum": ["atomic", "separable"]},
        "why": {"type": "string"},
        "concerns": {"type": "array", "items": {
            "type": "object",
            "properties": {"name": {"type": "string"},
                           "criteria": {"type": "array", "items": {"type": "string"}}},
            "required": ["name", "criteria"]}},
    },
    "required": ["verdict", "why"],
}


def review_decomposition(engine, node_id: TaskId, llm=None) -> NodeCritique:
    """L2 validate — the STRUCTURAL gate (cached L0/L1, eager-fresh) + the causal-correctness
    CHECKER. Stores the critique as the validation record + sets verified=True.
    Lives HERE, not on Engine: the critic pulls decompose/adapters, and the engine imports core
    only (the mechanical layer gate) — the engine is an argument, not a host."""
    import json
    from dataclasses import asdict
    from datetime import datetime
    used = llm or engine._llm
    critique = critique_node(engine, node_id, used)
    _node = engine.get_task(node_id)
    rec = {**asdict(critique),   # + review provenance: re-validation UX needs "who judged, when"
           # …and the GOAL the obligations were mined out of. The sufficiency check asks a question
           # about this text; when it has not changed, later rounds re-judge the answers instead of
           # re-reading it (see `_goal_changed`).
           "goal_text": (_node.spec.description if _node is not None else ""),
           # …and WHICH PLAN was judged, so the next round can tell "this is the same plan" from
           # "this is a different one". Without it a criterion already ruled sufficient was
           # re-litigated every round, and the gate answered differently about an unchanged object.
           "plan_generation": list(_plan_generation(_node)) if _node is not None else [],
           # `_model` is the port's attribute; the public-looking `model` never existed, so every
           # record until now stored an empty string — and provenance you cannot read is no provenance
           # (it hid WHICH model produced a verdict while two runs disagreed about the same plan).
           "model": str(getattr(used, "_model", None) or getattr(used, "model", "") or ""),
           "ts": datetime.now().isoformat(sep=" ", timespec="seconds")}
    # A VERDICT THAT FLIPPED WITH NO EDIT IS RECORDED AS HAVING FLIPPED. The checker is an
    # approximation (§13.5) and may legitimately change its mind — but measured 2026-08-21, a
    # criterion went `sufficient` in one round and `insufficient` in the next with nothing about it
    # or its children touched between them, which means a plan can be admitted on the round that
    # happened to be kind. Nothing here decides what to do about that; it stops being invisible.
    _raw = engine._graph._storage.get_critique(node_id)
    _before = (json.loads(_raw) if _raw else None) or {}
    _prev = {v.get("criterion"): v.get("verdict")
             for v in (_before.get("criteria_verdicts") or ())}
    for v in rec.get("criteria_verdicts") or ():
        was = _prev.get(v.get("criterion"))
        if was and was != v.get("verdict"):
            v["changed_from"] = was
    # A ROUND THAT DID NOT RUN THE CHECKER DOES NOT OVERWRITE THE ONE THAT DID. A review gated out at
    # Level 0 records nothing — and storing that emptiness erased the last real verdict, so the NEXT
    # round announced itself as "the first on this node" and four genuinely closed findings vanished
    # from the delta (measured on the human door 2026-08-22). The node is still marked unverified
    # below; what is kept is the last thing anyone actually judged.
    if critique.criteria_verdicts or critique.undecided_obligations or not _before:
        engine._graph._storage.store_critique(node_id, json.dumps(rec))
    node = engine.get_task(node_id)
    if node is not None:
        node.verified = True  # critique is now current for this decomposition
        engine._graph.save_task(node)
    _log_critique(engine, critique)
    return critique


def _log_critique(engine, critique: NodeCritique) -> None:
    """Append a JSONL line per validation — the raw material for coverage curves."""
    path = getattr(engine, "_critique_log_path", None)
    if not path:
        return
    import json
    from datetime import datetime
    rec = {
        "ts": datetime.now().isoformat(),
        "node": critique.node_id,
        "gate_passed": critique.gate_passed,
        "l0l1_failures": list(critique.l0l1_failures),
        "semantic_covered": critique.semantic_covered,
        "insufficient": sum(1 for c in critique.criteria_verdicts
                            if c.get("verdict") == "insufficient"),
        "conflicts": len(critique.conflicts),
    }
    with open(path, "a", encoding="utf-8") as f:
        f.write(json.dumps(rec) + "\n")


def _critique_leaf(engine, node_id: TaskId, llm=None) -> NodeCritique:
    """The same Level-2 question over the DEGENERATE plan: D(t)=∅ — "this goal is one unit of work".

    That is a claim like any other in the plan, and until it is checked it is the cheapest way to
    route around the method entirely: declare the goal atomic and no decomposition exists to review
    (observed live — a fresh agent took an issued 6-criteria goal straight to code). So a leaf is
    reviewed too, by its own question: do these acceptance criteria describe separable,
    independently-deliverable parts? A `separable` verdict names them as a partition of the criteria;
    an `atomic` verdict closes the check and the node executes as a leaf, which is a perfectly good
    answer — this is not a push to decompose (§10: inventing a pass-through child makes the plan
    WORSE). Advisory exactly like the decomposition checker: the agent fixes or disputes, contact
    decides (§13.5)."""
    nid = str(node_id)
    task = engine.get_task(node_id)
    if llm is None or task is None:
        return NodeCritique(nid, gate_passed=True)   # no instrument — no verdict, never read as clean

    from gfso.adapters.llm.structured import schema_instruction, parse_structured
    from gfso.decompose.loop import _tag

    system = (Path(__file__).parent / "prompts" / "atomicity.md").read_text(encoding="utf-8")
    crits = "\n".join(f"- {c.name}: {c.description}" for c in task.spec.criteria)
    user = (f"# GOAL DECLARED ATOMIC (no decomposition)\n"
            f"**{task.spec.name or nid}**\n\n{task.spec.description}\n\n"
            f"## Acceptance criteria\n{crits}\n\n"
            f"Judge: one unit of work, or separable parts?")
    text = llm.complete(prompt=user + schema_instruction(ATOMICITY_SCHEMA), context=system)
    _tag(llm, Stage.L2_ATOMICITY)

    parsed = parse_structured(text or "", ATOMICITY_SCHEMA)
    if parsed is None:
        return NodeCritique(nid, gate_passed=True)   # no verdict — never read as clean
    # …AND THE SECOND QUESTION, which a leaf needs more than a decomposed node does: do THESE
    # criteria decide THIS goal? Measured 2026-08-21 by a person driving the doors: on a leaf whose
    # goal was "backs up and restores" under the single criterion "a file named backup.sh exists",
    # the atomicity checker wrote in its own reasoning that "whatever backup/restore functionality
    # it contains is unconstrained by any decidable criterion here" — and then returned `sufficient`
    # and admitted execution. It saw the gap, said it out loud, and let the node through, because
    # nothing was asking that question. A leaf is where the work happens and where nothing below it
    # can compensate for a thin contract (there is no child to carry it), so the check belongs here.
    short = _undecided_obligations(engine, task, llm)
    if parsed["verdict"] == "atomic" and not short:
        return NodeCritique(nid, gate_passed=True, semantic_covered=True,
                            criteria_verdicts=({"criterion": "atomicity", "verdict": CriticVerdict.SUFFICIENT,
                                                "why": parsed.get("why", "")},))
    if parsed["verdict"] == "atomic":
        return NodeCritique(
            nid, gate_passed=True, semantic_covered=False, undecided_obligations=short,
            semantic_findings="\n".join(
                f"[undecided] {g.get('obligation')} — admits: {g.get('admits')}" for g in short),
            criteria_verdicts=({"criterion": "atomicity", "verdict": CriticVerdict.SUFFICIENT,
                                "why": parsed.get("why", "")},))
    concerns = parsed.get("concerns") or ()
    named = "; ".join(f"{c.get('name')} [{', '.join(c.get('criteria') or ())}]" for c in concerns)
    return NodeCritique(
        nid, gate_passed=True, semantic_covered=False, undecided_obligations=short,
        semantic_findings=f"[separable] {parsed.get('why', '')}" + (f" — concerns: {named}" if named else "")
        + "".join(f"\n[undecided] {g.get('obligation')} — admits: {g.get('admits')}"
                   for g in short),
        criteria_verdicts=({"criterion": "atomicity", "verdict": "insufficient",
                            "why": f"{parsed.get('why', '')}" + (f" Concerns: {named}" if named else "")},))


def critique_node(engine, node_id: TaskId, llm=None) -> NodeCritique:
    """The L0/L1 STRUCTURAL gate (cached, O(1)) + the L2 CHECKER. A leaf or a structural CORRECTNESS
    failure ⇒ gate_passed=False (checker gated out — L2 presupposes structure). A structurally-clean
    non-leaf with an `llm` ⇒ ONE zero-tool call over the node's projection (the one canonical
    read): per parent criterion sufficient/insufficient/uncertain + FM-2 conflicts. A failed,
    absent or INCOMPLETE verdict ⇒ semantic_covered=None — never read as clean.

    "Structurally clean" means the SAME checks that admit a plan to execution: the whole Syntactic
    level (CHECK-1, 1b, 2, 3, 4, 5, 6 — §13.4), read from `_EXEC_GATING_CHECKS` so the two gates
    cannot drift apart. The register and risk-node rows are on that level too (§13.1: "a decomposition
    without the register is incomplete by definition"), so a plan with an empty ACCEPTED_RISKS gets no
    Level-2 verdict and no execution — the hole is repaired, not routed around. What that costs is
    real and was measured (gating the register bought fabricated entries and churn), and it is a q_T
    defect with a name and an owner — an argument about incentives, not about whose rule this is.
    One definition of an admissible plan, used by both gates."""
    from gfso.engine.validation import _EXEC_GATING_CHECKS
    nid = str(node_id)
    children = engine.get_active_children(node_id)  # cancelled tombstones are not part of the decomposition
    if not children:
        return _critique_leaf(engine, node_id, llm)
    checks = engine.get_checks(node_id)  # CACHED, O(1) — eager-fresh, not recomputed here
    failed = [c for c in checks if not c.passed and not c.skipped
              and c.check_name.startswith(_EXEC_GATING_CHECKS)]
    if failed:
        failures = tuple(f"{c.check_name} — {c.details}" if c.details else c.check_name for c in failed)
        return NodeCritique(nid, gate_passed=False, l0l1_failures=failures)

    task = engine.get_task(node_id)
    if llm is None or task is None:
        return NodeCritique(nid, gate_passed=True)  # structurally clean; checker not run

    from gfso.adapters.llm.structured import schema_instruction, parse_structured
    from gfso.decompose.loop import _tag

    system = (Path(__file__).parent / "prompts" / "checker.md").read_text(encoding="utf-8")
    user = (f"# DECOMPOSITION LEVEL UNDER CHECK\n{engine.project(node_id)}\n\n"
            f"Judge EVERY parent criterion listed above — one entry each.")
    # SEVERAL READINGS ON THE FIRST CHECK, UNIONED — the same medicine the sufficiency half got, for
    # the same disease. Measured on the E3 arm 2026-08-22: with the contract no longer inflating (12
    # criteria, steady), the CHECKER still returned exactly one NEW finding per round, three rounds
    # running, and the run ended `l2_not_discharged` without writing code. One reading of a plan is
    # one sample of a judgement that varies; three, unioned, is the same discovery paid for in
    # parallel instead of in rounds. Later rounds read once: the plan has changed by then, and what
    # they judge is the change.
    _prior = _prior_review(engine, task)
    # …AND WHAT THIS SAME PLAN HAS ALREADY SETTLED. A criterion ruled sufficient against a plan that
    # has not changed since is carried forward rather than re-asked (`_already_decided`): the gate
    # was non-monotone, which is what made discharging it feel like whack-a-mole.
    _decided = _already_decided(_prior, task)
    parsed, verdicts, conflicts = _read_the_plan(llm, user, system, _prior is None,
                                                 decided=_decided)
    if parsed is None:
        return NodeCritique(nid, gate_passed=True)  # no verdict — never read as clean
    missing = ({c.name for c in task.spec.criteria}
               - {v.get("criterion", "") for v in verdicts})
    if missing:  # incomplete per-criterion coverage of the verdict itself
        return NodeCritique(nid, gate_passed=True, criteria_verdicts=verdicts, conflicts=conflicts,
                            semantic_findings=f"checker verdict INCOMPLETE — unjudged criteria: "
                                              f"{', '.join(sorted(missing))}")

    short = _undecided_obligations(engine, task, llm)
    gaps = [v for v in verdicts if v.get("verdict") != CriticVerdict.SUFFICIENT]
    covered = not gaps and not conflicts and not short
    findings = "" if covered else "\n".join(
        [f"[{v.get('verdict')}] {v.get('criterion')} — {v.get('why')}" for v in gaps]
        + [f"[conflict] {', '.join(c.get('between', ()))} — {c.get('why')}" for c in conflicts]
        + [f"[undecided on {nid}'s OWN criteria] {g.get('obligation')} — "
           f"admits: {g.get('admits')}" for g in short])
    return NodeCritique(nid, gate_passed=True, semantic_covered=covered,
                        semantic_findings=findings, criteria_verdicts=verdicts, conflicts=conflicts,
                        undecided_obligations=short)


def _plan_generation(task) -> tuple:
    """What makes this a DIFFERENT plan: the node's revisions, plus the shape of its decomposition.

    A review judges a plan, and the same plan judged twice must not answer differently. The counter
    alone is not enough — a child added or remapped is a new plan whether or not the parent was
    revised — so the criteria and their coverage go into the stamp."""
    return (task.revisions,
            tuple(sorted(c.name for c in task.spec.criteria)),
            tuple(sorted((m.criterion_name, str(m.child_id))
                         for m in (task.criterion_mappings or ()))))


def _already_decided(prior: Optional[dict], task) -> dict:
    """The criteria a PREVIOUS reading of this SAME plan ruled sufficient, by name.

    THE CHECKER WAS NON-MONOTONE, and that is what made the gate feel like whack-a-mole. Measured on
    the agent door 2026-08-22: `output_format_consistency_across_commands` was ruled sufficient
    TWICE with a stated reason, and after an edit that touched a different node's packaging criteria
    it came back insufficient with the opposite claim — three rounds, $0.86, and each round closing
    findings while opening others that had been true all along. A criterion already decided against
    an unchanged plan is not re-litigated; anything else — insufficient, uncertain, newly added, or
    any criterion at all once the plan changes — is judged afresh, which is where a checker's
    judgement belongs."""
    if not prior or prior.get("plan_generation") != list(_plan_generation(task)):
        return {}
    return {str(v.get("criterion")): v for v in (prior.get("criteria_verdicts") or ())
            if v.get("verdict") == CriticVerdict.SUFFICIENT}


def _read_the_plan(llm, user: str, system: str, first_pass: bool, decided: Optional[dict] = None):
    """Read the decomposition once, or several times on the FIRST pass, and union what it doubts.

    Measured on the E3 arm 2026-08-22: with the contract no longer inflating (twelve criteria,
    steady), the checker still returned exactly one NEW finding per round for three rounds, and the
    run ended `l2_not_discharged` without a line of code written. One reading of a plan is one sample
    of a judgement that varies; a doubt raised by ANY reading is a doubt to answer. Later rounds read
    once — by then the plan has changed, and what they judge is the change.

    Returns (first parsed answer, per-criterion verdicts with every reading's doubts folded in,
    conflicts)."""
    parsed, conflicts, gaps = None, (), {}
    decided = decided or {}
    for _ in range(max(1, CHECKER_READINGS) if first_pass else 1):
        text = llm.complete(prompt=user + schema_instruction(CHECKER_SCHEMA), context=system)
        _tag(llm, Stage.L2_CHECKER)
        one = parse_structured(text or "", CHECKER_SCHEMA)
        if one is None:
            continue
        parsed = parsed or one
        for v in one.get("criteria") or ():
            name = str(v.get("criterion"))
            if name in decided:
                continue          # settled against this same plan; a re-reading does not reopen it
            if v.get("verdict") != CriticVerdict.SUFFICIENT and name not in gaps:
                gaps[name] = v
        conflicts += tuple(c for c in (one.get("conflicts") or ()) if c not in conflicts)
    if parsed is None:
        return None, (), ()
    return (parsed,
            tuple(decided.get(str(v.get("criterion")),
                              gaps.get(str(v.get("criterion")), v)) for v in parsed["criteria"]),
            conflicts)


def _prior_review(engine, task) -> Optional[dict]:
    """The last stored review of this node, or None — what the goal was read against before."""
    try:
        raw = engine._graph._storage.get_critique(task.id)
    except Exception:
        return None
    if not raw:
        return None
    try:
        return json.loads(raw)
    except (ValueError, json.JSONDecodeError):
        return None


def _goal_changed(prior: Optional[dict], task) -> bool:
    """Is the node's own GOAL text different from the one the obligations were mined out of?

    The sufficiency check asks a question ABOUT THE GOAL: what does this text require that no
    criterion decides. Its answer belongs to that text, not to the current plan — and re-asking it
    open-endedly after every criteria edit is what made it discover a fresh corner each round.
    Measured to its conclusion on the E3 arm 2026-08-21: twenty-six rounds on one root, the contract
    grown to fifty-one criteria, $19.44 spent on the gate, and NOT ONE executor call — the run died
    before any code was written. When the goal has not moved, later rounds re-judge the obligations
    already named instead of mining the text again."""
    return prior is None or str(prior.get("goal_text", "")) != str(task.spec.description)


#: One judgement over a FIXED list — the later rounds of a node whose goal has not changed.
STILL_SCHEMA = {
    "type": "object",
    "properties": {"decided": {"type": "array", "items": {"type": "string"}}},
    "required": ["decided"],
}


def _still_undecided(engine, task, llm, prior: tuple) -> tuple[dict, ...]:
    """Which of the obligations already named are STILL not decided by this node's criteria.

    A cheap judgement over a fixed list, instead of another open-ended reading of the goal. It
    cannot invent an obligation — new ones arrive only when the goal text itself changes — which is
    the point: the gate asks its question once and then checks whether the answers have been met.
    A ⊥ here keeps the list as it stood, because "the check could not run" is not "the gap closed".
    """
    if not prior:
        return ()
    listed = "\n".join(f"{i + 1}. {g.get('obligation', '')}" for i, g in enumerate(prior))
    crits = "\n".join(f"- {c.name}: {c.description}"
                      for c in task.spec.criteria if not c.depends_on) or "- (none)"
    user = (f"# THE NODE: {task.id}\n\n# GOAL\n{task.spec.description}\n\n"
            f"# ITS CRITERIA NOW\n{crits}\n\n"
            f"# OBLIGATIONS NAMED EARLIER AS UNDECIDED BY THEM\n{listed}\n\n"
            f"For EACH numbered obligation decide one thing only: do the criteria as they now stand "
            f"DECIDE it — would a result satisfying every criterion necessarily have it? Answer with "
            f"the numbers of the obligations that are now decided. Name nothing new: what the goal "
            f"carries was enumerated when it was read, and this round is about what the criteria "
            f"have since covered.")
    try:
        text = llm.complete(prompt=user + schema_instruction(STILL_SCHEMA),
                            context="You judge whether stated criteria decide stated obligations. "
                                    "Nothing else.")
        _tag(llm, Stage.UNDECIDED_OBLIGATIONS)
        parsed = parse_structured(text or "", STILL_SCHEMA)
    except Exception:
        log.warning(f"re-judging the undecided obligations failed on {task.id}", exc_info=True)
        return tuple(prior)
    if parsed is None:
        return tuple(prior)
    done = {str(n).strip() for n in (parsed.get("decided") or ())}
    return tuple(g for i, g in enumerate(prior, 1) if str(i) not in done)


def _undecided_obligations(engine, task, llm) -> tuple[dict, ...]:
    """Obligations of the node's OWN goal that none of its OWN criteria decides (FM-1.f).

    A separate call against its own prompt rather than a question bolted onto the checker's,
    deliberately: the checker's verdict is what the E3 measurement reads, and its provenance stays
    one unchanged thing.

    Empty on failure — a check that could not run names no gap. That is a ⊥, not a clean bill, and
    it is why the caller keeps its own fail-closed rule for the checker: this one may not manufacture
    findings, and it may not be read as proof there are none.

    SEVERAL INDEPENDENT READINGS, UNIONED (`config.SUFFICIENCY_READINGS`). The check was discovering
    its objections serially: eight review rounds on one graph, ~20 minutes and ~$1.50, findings
    7→5→2→2→1→1→1→0, each round naming a fresh obligation out of a NEW reading of the same goal text
    (measured on the MCP door 2026-08-21). Every finding was true — what cost was the shape of the
    loop, and a user with less patience stops at round three and starts disputing correct findings.
    Sampling the same reading N times and taking the union pays for that discovery in parallel
    instead of in rounds. Same prompt, same schema: this is the harness, not a rewrite of the
    question. Duplicates are folded by the obligation's own words.
    """
    system = (Path(__file__).parent / "prompts" / "undecided.md").read_text(encoding="utf-8")
    crits = "\n".join(f"- {c.name}: {c.description}"
                      for c in task.spec.criteria if not c.depends_on) or "- (none)"
    excluded = "\n".join(f"- {x}" for x in task.spec.scope) or "- (none declared)"
    user = (f"# THE NODE UNDER CHECK: {task.id}\n"
            f"Its OWN criteria are the whole of what you quantify over — never its children's.\n\n"
            f"# GOAL\n{task.spec.description}\n\n"
            f"# CRITERIA OF {task.id}\n{crits}\n\n"
            f"# DECLARED SCOPE EXCLUSIONS (deliberate absences — never gaps)\n{excluded}\n\n"
            f"Name the obligations of the GOAL that none of these criteria decides.")
    prior = _prior_review(engine, task)
    if not _goal_changed(prior, task):
        # THE GOAL HAS NOT MOVED, so the obligations it carries have not either. What CAN have
        # changed is whether the node's criteria now decide them, and that is what this round asks —
        # about the list already on record, not about the text again.
        return _still_undecided(engine, task, llm, tuple(prior.get("undecided_obligations") or ()))
    prompt = user + schema_instruction(UNDECIDED_SCHEMA)
    out, seen = [], []
    readings = max(1, SUFFICIENCY_READINGS)
    for _ in range(readings):
        try:
            text = llm.complete(prompt=prompt, context=system)
            _tag(llm, Stage.UNDECIDED_OBLIGATIONS)
            parsed = parse_structured(text or "", UNDECIDED_SCHEMA)
        except Exception:
            log.warning(f"undecided-obligations check failed on {task.id}", exc_info=True)
            continue          # one reading that could not run is not a verdict about the others
        for gap in (parsed.get("gaps") or ()) if parsed else ():
            words = _obligation_words(gap.get("obligation", ""))
            if not words:
                continue
            same = next((i for i, w in enumerate(seen) if _same_obligation(words, w)), None)
            if same is None:
                seen.append(words)
                out.append(gap)
            else:
                # FOLDED, NOT DROPPED. The threshold is a heuristic and it can be wrong, so the
                # other reading's wording rides along with the finding it was folded into: a caller
                # who thinks they are two obligations can see both, and one who does not is handed
                # one finding instead of three (2026-08-21).
                phrasings = out[same].setdefault("also_phrased", [])
                if gap.get("obligation") not in phrasings:
                    phrasings.append(gap.get("obligation"))
    return tuple(out)


# Words that carry no obligation on their own — dropped before two findings are compared, so
# "a README exists" and "a README is provided" are one obligation rather than two.
_NOISE = frozenset("a an the is are be to of and or that it its this for with as by on in exists "
                   "provided present available must should shall does do".split())


def _obligation_words(text) -> frozenset:
    """The obligation's content words, for comparing two phrasings of one requirement."""
    cleaned = "".join(c if c.isalnum() or c in "-_ " else " " for c in str(text).lower())
    return frozenset(w for w in cleaned.split() if w not in _NOISE and len(w) > 1)


def _same_obligation(a: frozenset, b: frozenset) -> bool:
    """Two findings naming ONE requirement in different words.

    Measured 2026-08-21 while checking the multi-reading union: three readings of one goal returned
    "CLI invoked as `python -m linestat FILE`", "package structure runnable as `python -m linestat
    FILE`" and "package is invocable as `python -m linestat FILE`" — one obligation, three phrasings,
    and exact-text dedup let all three through. Handing a caller the same gap three times is a cost
    the union has no business adding. Jaccard over content words, at the threshold that separated
    those from genuinely different obligations in that sample. Folded findings keep the other
    wording under `also_phrased` — the threshold may be wrong, and nothing is dropped on its word.

    CONTAINMENT counts too, and it is the case a ratio cannot see: "a README exists" against "README
    documenting the package" shares every word of the shorter one and scores 0.33, because the longer
    phrasing simply says more ABOUT the same obligation. One naming inside the other is the same
    requirement, at two levels of detail."""
    if not (a and b):
        return False
    if a <= b or b <= a:
        return True
    return bool(a & b) and len(a & b) / len(a | b) >= 0.4