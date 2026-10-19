"""L2 critic — the STRUCTURAL GATE + the causal-correctness CHECKER (canon §9.1 Level 2).

Level 2's question is a CHECK, not a hunt: per parent criterion — do the mapped children's
criteria, taken as real-world facts, causally guarantee it? (Plus the semantic FM-2 residue the
formal CHECK-8 cannot see.) EPISTEMIC STATUS (§9.9/§20.8): the Level-2 AXIS is checkable
only by EXECUTION — no pre-contact instrument can verify it (any verdict is itself a Level-2
claim); this checker is the canon's named LLM-OFFERED approximation — an a-priori estimate over
the faithfulness axis — and the real Level-2 verdict stays with contact (q_D). Hence ADVISORY by
construction, never an acceptance blocker.

Two prior designs are deliberately dead: the analyst⊥validator monolithic critic (E2-refuted:
polices form, cannot move content) and the SEARCH-in-diff-mode hole-hunt (the opposite extreme —
"what is missing" is the DECOMPOSER's question and lives in refine, not here). Staged: the L0/L1
gate BLOCKS the checker (L2 presupposes a structurally-complete graph); the verdict never
auto-fixes — the agent fixes via FSM verbs or consciously declares ACCEPTED_RISKS.
"""
from __future__ import annotations

import json
import logging
from dataclasses import asdict
from datetime import datetime
from pathlib import Path
from typing import Optional

from gfso.adapters.llm.structured import parse_structured, schema_instruction
from gfso.config import CHECKER_READINGS, SUFFICIENCY_READINGS
from gfso.core.graph.review import progress_baseline
from gfso.core.types import CriticVerdict, Stage, TaskId
from gfso.engine.validation import _EXEC_GATING_CHECKS
from gfso.adapters.llm.stats import readings, tag_stage
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
    used = llm or engine._llm
    critique = critique_node(engine, node_id, used)
    _node = engine.graph.get_task(node_id)
    rec = {**asdict(critique),   # + review provenance: re-validation UX needs "who reviewed, when"
           # …and the GOAL the obligations were mined out of. The sufficiency check asks a question
           # about this text; when it has not changed, later rounds re-check the answers instead of
           # re-reading it (see `_goal_changed`).
           "goal_text": (_node.spec.description if _node is not None else ""),
           # …and WHICH PLAN was reviewed, so the next round can tell "this is the same plan" from
           # "this is a different one". Without it a criterion already ruled sufficient was
           # re-litigated every round, and the gate answered differently about an unchanged object.
           "plan_generation": list(_plan_generation(_node)) if _node is not None else [],
           # …AND PER CRITERION, because the plan-wide stamp is too coarse to be fair. Whether the
           # children mapped to c entail c depends on c's own text and on those children's criteria —
           # on nothing else in the graph. Keyed on the whole plan, ANY edit anywhere threw away
           # every decision, so a criterion certified in round 2 came back in round 3 with the plan
           # around it changed and itself untouched (measured on the CLI door 2026-09-02: five
           # rounds, ~$1.30, rounds 3 and 4 reopening what 2 and 3 had certified). Conflicts stay
           # out of this: FM-2 satisfiability is a property of ALL the children together, so a new
           # criterion elsewhere really can create one, and those are checked afresh every round.
           "criteria_stamps": (_criterion_stamps(engine, _node) if _node is not None else {}),
           # `_model` is the port's attribute; the public-looking `model` never existed, so every
           # record until now stored an empty string — and provenance you cannot read is no provenance
           # (it hid WHICH model produced a verdict while two runs disagreed about the same plan).
           "model": str(getattr(used, "_model", None) or getattr(used, "model", "") or ""),
           "ts": datetime.now().isoformat(sep=" ", timespec="seconds")}
    # A VERDICT THAT FLIPPED WITH NO EDIT IS RECORDED AS HAVING FLIPPED. The checker is an
    # approximation (§9.9) and may legitimately change its mind — but measured 2026-08-21, a
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
    # below; what is kept is the last thing anyone actually checked.
    # …but a round the checker DID run and that read nothing is the truth about THIS plan ("no verdict"), and
    # it replaces the last record: kept, that record — about a plan since changed — was read as current
    # …AND THE GOAL READING IS ITS OWN PART OF THE RECORD. The obligations belong to the goal text they were
    # mined from, and only a round that read the goal (mined or re-checked them) may change them. A round that
    # did not — no checker, an unreadable or incomplete verdict — stored an empty list stamped with the current
    # goal, and the next readable round, the goal "unchanged", re-checked an empty list: the gate opened on a
    # plan whose obligations nobody had read (critic rounds 7 and 8). Such a round carries the reading on
    # record, or none — and with none the next round reads the goal afresh.
    if not critique.goal_read:
        rec["goal_text"] = _goal_read_in(_before)
        rec["undecided_obligations"] = list(_before.get("undecided_obligations") or ())
        rec["goal_read"] = rec["goal_text"] is not None       # the reading carried is still a reading
    # …AND THE PROGRESS BASELINE IS THE LAST ROUND THAT MEASURED. Compared against a round that read nothing, the
    # next review counted as having moved whatever it said, and the unproductive count reset (critic round 9).
    rec["measured"] = critique.semantic_covered is not None
    if not rec["measured"] and _before:
        rec["baseline_findings"] = progress_baseline(_before)
    stored = bool(critique.gate_passed or critique.criteria_verdicts or critique.undecided_obligations
                  or not _before)
    if stored:
        engine._graph._storage.store_critique(node_id, json.dumps(rec))
    node = engine.graph.get_task(node_id)
    if node is not None:
        # …AND ONLY IF THE CHECKER ACTUALLY RAN. This said `True` unconditionally, three lines under
        # a comment of its own promising that "the node is still marked unverified below" for a round
        # gated out at Level 0 — the prose was right and the code did the other thing. So a review
        # that never checked anything, because the structure was too broken to check, marked the plan
        # verified: `review_decomposition` answered `gate_passed: false, execution_admitted: false`
        # and `get_review` answered `verified: true, execution_admitted: true` about the same node in
        # the same second, with `list_holes` naming the open hole beside them (HTTP door, wave 23,
        # 2026-09-03; reproduced here with a model that raises if it is called). `execution_admitted`
        # is the field this product tells an integrator to gate on, and enforcement held — the FSM
        # still refused the children — so what was broken is the READ, which is the one an outside
        # system trusts. A leaf and a node with no instrument keep `gate_passed=True`: there is
        # nothing for the checker to say about them, and that is a current answer, not a missing one.
        # A round that passed the gate has stored its own record (above), so what `verified` vouches for is
        # always this round's reading — a "no verdict" reading included, which the gate reads as not clean.
        node.verified = bool(critique.gate_passed)
        engine._graph.save_task(node)
    _log_critique(engine, critique)
    return critique


def _log_critique(engine, critique: NodeCritique) -> None:
    """Append a JSONL line per validation — the raw material for coverage curves."""
    path = getattr(engine, "_critique_log_path", None)
    if not path:
        return
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
    answer — this is not a push to decompose (§2: inventing a pass-through child makes the plan
    WORSE). Advisory exactly like the decomposition checker: the agent fixes or disputes, contact
    decides (§9.9)."""
    nid = str(node_id)
    task = engine.graph.get_task(node_id)
    if llm is None or task is None:
        return NodeCritique(nid, gate_passed=True)   # no instrument — no verdict, never read as clean

    system = (Path(__file__).parent / "prompts" / "atomicity.md").read_text(encoding="utf-8")
    crits = "\n".join(f"- {c.name}: {c.description}" for c in task.spec.criteria)
    user = (f"# GOAL DECLARED ATOMIC (no decomposition)\n"
            f"**{task.spec.name or nid}**\n\n{task.spec.description}\n\n"
            f"## Acceptance criteria\n{crits}\n\n"
            f"Decide: one unit of work, or separable parts?")
    text = llm.complete(prompt=user + schema_instruction(ATOMICITY_SCHEMA), context=system)
    tag_stage(llm, Stage.L2_ATOMICITY)

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
    if short is None:  # the goal was not read — no verdict, never read as clean
        return NodeCritique(nid, gate_passed=True)
    if parsed["verdict"] == "atomic" and not short:
        return NodeCritique(nid, gate_passed=True, semantic_covered=True, goal_read=True,
                            criteria_verdicts=({"criterion": "atomicity", "verdict": CriticVerdict.SUFFICIENT,
                                                "why": parsed.get("why", "")},))
    if parsed["verdict"] == "atomic":
        return NodeCritique(
            nid, gate_passed=True, semantic_covered=False, undecided_obligations=short, goal_read=True,
            semantic_findings="\n".join(
                f"[undecided] {g.get('obligation')} — admits: {g.get('admits')}" for g in short),
            criteria_verdicts=({"criterion": "atomicity", "verdict": CriticVerdict.SUFFICIENT,
                                "why": parsed.get("why", "")},))
    concerns = parsed.get("concerns") or ()
    named = "; ".join(f"{c.get('name')} [{', '.join(c.get('criteria') or ())}]" for c in concerns)
    return NodeCritique(
        nid, gate_passed=True, semantic_covered=False, undecided_obligations=short, goal_read=True,
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
    level less CHECK-3, which gates only the admission (CHECK-1, 1b, 2, 4, 5, 6 — §9.5, §11.5), read from `_EXEC_GATING_CHECKS` so the two gates
    cannot drift apart. The register and risk-node rows are on that level too (§9.2: "a decomposition
    without the register is incomplete by definition"), so a plan with an empty ACCEPTED_RISKS gets no
    Level-2 verdict and no execution — the hole is repaired, not routed around. What that costs is
    real and was measured (gating the register bought fabricated entries and churn), and it is a q_T
    defect with a name and an owner — an argument about incentives, not about whose rule this is.
    One definition of an admissible plan, used by both gates."""
    nid = str(node_id)
    children = engine.graph.get_active_children(node_id)  # cancelled tombstones are not part of the decomposition
    if not children:
        return _critique_leaf(engine, node_id, llm)
    checks = engine.get_checks(node_id)  # CACHED, O(1) — eager-fresh, not recomputed here
    failed = [c for c in checks if not c.passed and not c.skipped
              and c.check_name.startswith(_EXEC_GATING_CHECKS)]
    if failed:
        failures = tuple(f"{c.check_name} — {c.details}" if c.details else c.check_name for c in failed)
        return NodeCritique(nid, gate_passed=False, l0l1_failures=failures)

    task = engine.graph.get_task(node_id)
    if llm is None or task is None:
        return NodeCritique(nid, gate_passed=True)  # structurally clean; checker not run

    system = (Path(__file__).parent / "prompts" / "checker.md").read_text(encoding="utf-8")
    user = (f"# DECOMPOSITION LEVEL UNDER CHECK\n{engine.project(node_id)}\n\n"
            f"Assess EVERY parent criterion listed above — one entry each.")
    # SEVERAL READINGS ON THE FIRST CHECK, UNIONED — the same medicine the sufficiency half got, for
    # the same disease. Measured on the E3 arm 2026-08-22: with the contract no longer inflating (12
    # criteria, steady), the CHECKER still returned exactly one NEW finding per round, three rounds
    # running, and the run ended `l2_not_discharged` without writing code. One reading of a plan is
    # one sample of an assessment that varies; three, unioned, is the same discovery paid for in
    # parallel instead of in rounds. Later rounds read once: the plan has changed by then, and what
    # they check is the change.
    _prior = _prior_review(engine, task)
    # …AND WHAT THIS SAME PLAN HAS ALREADY SETTLED. A criterion ruled sufficient against a plan that
    # has not changed since is carried forward rather than re-asked (`_already_decided`): the gate
    # was non-monotone, which is what made discharging it feel like whack-a-mole.
    _decided = _already_decided(_prior, task, engine)
    parsed, verdicts, conflicts = _read_the_plan(llm, user, system, _prior is None, decided=_decided,
                                                 names=[c.name for c in task.spec.criteria])
    if parsed is None:
        return NodeCritique(nid, gate_passed=True)  # no verdict — never read as clean
    missing = ({c.name for c in task.spec.criteria}
               - {v.get("criterion", "") for v in verdicts})
    if missing:  # incomplete per-criterion coverage of the verdict itself
        return NodeCritique(nid, gate_passed=True, criteria_verdicts=verdicts, conflicts=conflicts,
                            semantic_findings=f"checker verdict INCOMPLETE — unchecked criteria: "
                                              f"{', '.join(sorted(missing))}")

    short = _undecided_obligations(engine, task, llm)
    if short is None:  # the goal was not read — the plan verdict alone is not a verdict on the node
        return NodeCritique(nid, gate_passed=True, criteria_verdicts=verdicts, conflicts=conflicts,
                            semantic_findings="the goal's obligations could not be read this round — no "
                                              "verdict; run the review again")
    gaps = [v for v in verdicts if v.get("verdict") != CriticVerdict.SUFFICIENT]
    covered = not gaps and not conflicts and not short
    findings = "" if covered else "\n".join(
        [f"[{v.get('verdict')}] {v.get('criterion')} — {v.get('why')}" for v in gaps]
        + [f"[conflict] {', '.join(c.get('between', ()))} — {c.get('why')}" for c in conflicts]
        + [f"[undecided on {nid}'s OWN criteria] {g.get('obligation')} — "
           f"admits: {g.get('admits')}" for g in short])
    return NodeCritique(nid, gate_passed=True, semantic_covered=covered,
                        semantic_findings=findings, criteria_verdicts=verdicts, conflicts=conflicts,
                        undecided_obligations=short, goal_read=True)


def _plan_generation(task) -> tuple:
    """What makes this a DIFFERENT plan: the node's revisions, plus the shape of its decomposition.

    A review checks a plan, and the same plan checked twice must not answer differently. The counter
    alone is not enough — a child added or remapped is a new plan whether or not the parent was
    revised — so the criteria and their coverage go into the stamp."""
    return (task.revisions,
            tuple(sorted(c.name for c in task.spec.criteria)),
            tuple(sorted((m.criterion_name, str(m.child_id))
                         for m in (task.criterion_mappings or ()))))


def _criterion_stamps(engine, task) -> dict:
    """What each parent criterion's sufficiency question is ABOUT: the criterion's own text, the
    children answering for it, and those children's criteria — NAME AND TEXT BOTH.

    The text half was missing and the docstring promised it. A child's criterion could be rewritten
    to anything at all while keeping its name, and the stamp did not move: `edit_criteria` honestly
    staled the review, the caller honestly re-ran it, and the re-run handed back the PREVIOUS
    verdict — whose stored rationale was then false about the graph it described. Measured on the CLI
    door (wave 25, 2026-09-05): a child's only criterion was replaced by "parse_kv exists and is
    callable" against a parent demanding three behaviours including two ValueError paths, and the
    review answered `sufficient` because "w25cli-kv's criterion is textually identical to the
    parent". Reproduced with "the developer has thought about parsing and feels reasonably
    confident" — same verdict, same sentence. Appending " (rev2)" to the PARENT's text forced a real
    re-derivation, which was immediately correct: the checker was capable, it was simply not asked.
    A gate that re-runs and returns a lie is worse than one that does not re-run.
    """
    kids = {str(k.id): tuple(sorted((c.name, c.description) for c in k.spec.criteria))
            for k in engine._graph.get_children(task.id)}
    out = {}
    for c in task.spec.criteria:
        covering = tuple(sorted(str(m.child_id) for m in (task.criterion_mappings or ())
                                if m.criterion_name == c.name))
        out[c.name] = [c.description, list(covering),
                       [[k, list(kids.get(k, ()))] for k in covering]]
    return out


def _already_decided(prior: Optional[dict], task, engine=None) -> dict:
    """The criteria a PREVIOUS reading of this SAME plan ruled sufficient, by name.

    THE CHECKER WAS NON-MONOTONE, and that is what made the gate feel like whack-a-mole. Measured on
    the agent door 2026-08-22: `output_format_consistency_across_commands` was ruled sufficient
    TWICE with a stated reason, and after an edit that touched a different node's packaging criteria
    it came back insufficient with the opposite claim — three rounds, $0.86, and each round closing
    findings while opening others that had been true all along. A criterion already decided against
    an unchanged plan is not re-litigated; anything else — insufficient, uncertain, newly added, or
    any criterion at all once the plan changes — is checked afresh, which is where a checker's
    assessment belongs."""
    if not prior:
        return {}
    _sufficient = {str(v.get("criterion")): v for v in (prior.get("criteria_verdicts") or ())
                   if v.get("verdict") == CriticVerdict.SUFFICIENT}
    if engine is None:      # no graph to ask: fall back to the coarse whole-plan stamp
        return _sufficient if prior.get("plan_generation") == list(_plan_generation(task)) else {}
    _then, _now = prior.get("criteria_stamps") or {}, _criterion_stamps(engine, task)
    if not _then:           # a record written before stamps existed carries the old, coarser rule
        return _sufficient if prior.get("plan_generation") == list(_plan_generation(task)) else {}
    return {name: v for name, v in _sufficient.items()
            if name in _then and _still_entailed(_then[name], _now.get(name))}


def _still_entailed(then, now) -> bool:
    """Does a criterion's stamped `sufficient` still hold — identical stamp, or a STRENGTHENED plan?

    Identity was the whole rule, and it made the gate reopen certified criteria whenever a covering
    child gained anything: an integrator watched `constructor_input_validation` go sufficient →
    insufficient → sufficient across four rounds while the only edit was ADDING a criterion to the
    child that covers it, at ~4 minutes and ~$0.25 a round (HTTP door, wave 27, 2026-09-06 — "I
    would not promise a CI budget on it").

    Adding is not changing. The sufficiency question is whether ⋀criteria(children) ⊨ cᵢ (§9.6,
    CHECK-7), and a conjunction only ever gets stronger when a conjunct is added: if the children
    entailed the parent criterion before, they entail it with an extra criterion on one of them. So
    a stamp whose parent text is unchanged, whose covering set has not SHRUNK, and whose covering
    children's criteria are a superset of what was checked, carries its verdict forward.

    Everything else is checked afresh, and that is the point: a criterion REWORDED (same name, new
    text) or REMOVED weakens the conjunction, so the entailment has to be re-derived. Nothing here
    is a claim that the checker was right the first time — it is a claim about which edits can make
    an earlier `sufficient` wrong.
    """
    if then == now:
        return True
    if not isinstance(then, (list, tuple)) or not isinstance(now, (list, tuple)):
        return False
    if len(then) != 3 or len(now) != 3:
        return False
    then_desc, then_cov, then_kids = then
    now_desc, now_cov, now_kids = now
    if str(then_desc) != str(now_desc):          # the parent criterion itself was rewritten
        return False
    if not set(map(str, then_cov or ())) <= set(map(str, now_cov or ())):
        return False                             # a coverer was removed: fewer conjuncts, re-derive
    _now_by_kid = {str(k): {tuple(map(str, c)) for c in (cs or ())} for k, cs in (now_kids or ())}
    for kid, crits in (then_kids or ()):
        held = {tuple(map(str, c)) for c in (crits or ())}
        if not held <= _now_by_kid.get(str(kid), set()):
            return False                         # a child's criterion was reworded or dropped
    return True


def _named(said: str, names) -> str:
    """The node's criterion a checker's entry is about. The projection lists `name: description`, and a model that
    copied the whole line keyed every verdict by it: all eight criteria then read as unchecked, a complete verdict was
    stored as "no verdict", and those rounds counted toward closing the goal (AUTO haiku coreutils, 2026-10-11)."""
    if said in names:
        return said
    hit = [n for n in names if said.startswith(f"{n}:")]
    return hit[0] if len(hit) == 1 else said


def _read_the_plan(llm, user: str, system: str, first_pass: bool, decided: Optional[dict] = None, names=()):
    """Read the decomposition once, or several times on the FIRST pass, and union what it doubts.

    Measured on the E3 arm 2026-08-22: with the contract no longer inflating (twelve criteria,
    steady), the checker still returned exactly one NEW finding per round for three rounds, and the
    run ended `l2_not_discharged` without a line of code written. One reading of a plan is one sample
    of an assessment that varies; a doubt raised by ANY reading is a doubt to answer. Later rounds read
    once — by then the plan has changed, and what they check is the change.

    Returns (first parsed answer, per-criterion verdicts with every reading's doubts folded in,
    conflicts)."""
    parsed, conflicts, gaps = None, (), {}
    decided = decided or {}
    texts = readings(llm, max(1, CHECKER_READINGS) if first_pass else 1,
                     lambda: llm.complete(prompt=user + schema_instruction(CHECKER_SCHEMA), context=system),
                     Stage.L2_CHECKER)
    for text in texts:
        one = parse_structured(text or "", CHECKER_SCHEMA)
        if one is None:
            continue
        one = {**one, "criteria": [{**v, "criterion": _named(str(v.get("criterion")), names)}
                                   for v in one.get("criteria") or ()]}
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
    before any code was written. When the goal has not moved, later rounds re-check the obligations
    already named instead of mining the text again."""
    return prior is None or _goal_read_in(prior) is None or str(_goal_read_in(prior)) != str(task.spec.description)


def _goal_read_in(rec: dict) -> Optional[str]:
    """The goal text a stored record READ, or None when it read none. A record older than `goal_read` is
    taken as unread: a round that read nothing was stamped with the goal all the same, and one whose goal
    reading failed looks exactly like a clean one — taken as read, either opened the gate (critic rounds 9,
    10). The cost is one fresh reading of the goal per node, once, after the upgrade."""
    if not rec.get("goal_read"):
        return None
    return rec.get("goal_text")


#: One assessment over a FIXED list — the later rounds of a node whose goal has not changed.
STILL_SCHEMA = {
    "type": "object",
    "properties": {"decided": {"type": "array", "items": {"type": "string"}}},
    "required": ["decided"],
}


def _still_undecided(engine, task, llm, prior: tuple, *,
                     stage: Stage = Stage.UNDECIDED_OBLIGATIONS) -> tuple[dict, ...]:
    """Which of the obligations already named are STILL not decided by this node's criteria.

    A cheap assessment over a fixed list, instead of another open-ended reading of the goal. It
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
    def _not_rechecked(why: str) -> tuple:
        """⊥ IS NOT "STILL OPEN". The list stands — a check that could not run closes nothing — but
        the reader must be able to tell an assessment from a silence. Two doors reported these
        obligations as "frozen at the first reading" (wave 26, 2026-09-06) with no way to see
        whether the round had re-checked them at all."""
        log.warning(f"re-checking the undecided obligations on {task.id}: {why} — the list stands "
                    f"unchanged, and each finding says it was not re-checked")
        return tuple({**g, "carried": True, "rechecked": False, "first_reading": _first_reading(g),
                      "admits": (f"(NOT RE-CHECKED this round — {why}. This obligation stands as it "
                                 f"was named when the goal was first read; that is a silence, not a "
                                 f"finding that your fix failed. Run the review again.) "
                                 + _first_reading(g))} for g in prior)

    try:
        text = llm.complete(prompt=user + schema_instruction(STILL_SCHEMA),
                            context="You assess whether stated criteria decide stated obligations. "
                                    "Nothing else.")
        tag_stage(llm, stage)
        parsed = parse_structured(text or "", STILL_SCHEMA)
    except Exception:
        log.warning(f"re-checking the undecided obligations failed on {task.id}", exc_info=True)
        return _not_rechecked("the checker did not answer")
    if parsed is None:
        return _not_rechecked("the checker's answer could not be read")
    done = {str(n).strip() for n in (parsed.get("decided") or ())}
    # …AND A CARRIED FINDING DOES NOT CARRY ITS OLD ARGUMENT. The DECISION here is current — these
    # obligations are still undecided by the criteria as they now stand — but the `why`/`admits`
    # text was written against the criteria as they stood when the goal was first read. A tester was
    # told "No criterion mentions tests at all" while a criterion named `pytest_suite_runs_green` was
    # in the set, because the argument enumerated the pre-edit contract (CLI door, 2026-09-02). The
    # user acts on the text, so the text may not assert a state of the graph it has not re-read.
    _kept = tuple(g for i, g in enumerate(prior, 1) if str(i) not in done)
    return tuple({**g, "carried": True, "rechecked": True, "first_reading": _first_reading(g),
                  "admits": ("(RE-CHECKED against the criteria as they stand now and still not "
                             "decided by them — so fixing the criteria IS what closes it, and the "
                             "next review will drop it; the argument below is the FIRST reading of "
                             "the goal and does not describe the contract as it stands) "
                             + _first_reading(g))} for g in _kept)


def _first_reading(g: dict) -> str:
    """The obligation's argument as the goal's first reading wrote it — a carried finding's `admits` is that text
    behind this round's note, and prefixing the stored text again stacked one note per round (four, measured)."""
    return str(g.get("first_reading", g.get("admits", "")))


def _undecided_obligations(engine, task, llm, *, stage: Stage = Stage.UNDECIDED_OBLIGATIONS) -> Optional[tuple[dict, ...]]:
    """Obligations of the node's OWN goal that none of its OWN criteria decides (FM-1.f).

    A separate call against its own prompt rather than a question bolted onto the checker's,
    deliberately: the checker's verdict is what the E3 measurement reads, and its provenance stays
    one unchanged thing.

    None on failure — a check that could not run names no gap. That is a ⊥, not a clean bill, and
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
        return _still_undecided(engine, task, llm, tuple(prior.get("undecided_obligations") or ()),
                                stage=stage)
    prompt = user + schema_instruction(UNDECIDED_SCHEMA)
    out, seen, read = [], [], False
    def _one():
        try:
            return parse_structured(llm.complete(prompt=prompt, context=system) or "", UNDECIDED_SCHEMA), True
        except Exception:
            log.warning(f"undecided-obligations check failed on {task.id}", exc_info=True)
            return None, False    # one reading that could not run is not a verdict about the others
    for parsed, ran in readings(llm, max(1, SUFFICIENCY_READINGS), _one, stage):
        if not ran:
            continue
        read = read or parsed is not None
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
    # NO READING PARSED IS ⊥, NOT "NO GAPS": returned as `()`, it counted as clean and was stored as the goal's
    # reading — the gate opened, and every later round re-checked the empty list (critic round 9)
    return tuple(out) if read else None


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