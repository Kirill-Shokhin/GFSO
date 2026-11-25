"""How a project's settled nodes closed, read over the engine: who produced each standing verdict and on what evidence
(`closure_of`, `verdict_provenance`), and the graph-wide lists a reader of "is the goal met" must not have to ask a
second verb for — closures by hand, by the clock, over an instrument's opposite word, refuted after the fact, over an
open plan review or open parts, and the questions left standing.

Why a module of its own: these readings write nothing and nothing in the engine's own moves asks them — the frontier
and the doors do. Each reads the engine's public surface only (`engine.graph`, its verdict and finding readers), as
the frontier's module functions do.
"""
from __future__ import annotations

from typing import Optional

from gfso.core.types import DoneReason, TaskId, TERMINAL_STATES, passed, register_of, settled_positive
from gfso.core.graph import pass_stands_refuted
from gfso.core.graph.model import is_its_executor
from gfso.core.protocol.accounting import orphaned_regression
from gfso.core.protocol.procedure import claim_digest, reads_an_unpinned_set


def nodes_with_a_refused_report(engine) -> list[str]:
    """Nodes where a validator ran, reported, and the engine refused the report as ⊥ (§2.3).

    NOT a contradiction and NOT a blocker: ⊥ is not fail, and treating it as one is the precise
    error the canon names. But it must be VISIBLE where completion is announced — measured on
    the HTTP door 2026-09-02, an instrument returned ⊥ on a root that had closed by hand
    forty-six seconds earlier, and `next_steps` went on answering "the goal is met" with nothing
    anywhere saying a validator had tried and failed to decide it.
    """
    return [str(t.id) for t in engine.all_tasks() if engine.rejected_report(t.id)]


def closed_over_an_open_plan_review(engine, root_id: Optional[TaskId] = None) -> list[str]:
    """Settled nodes whose OWN current Level-2 review still names findings nobody dispositioned.

    The gate holds a parent's CHILDREN until its plan is dispositioned — so on a decomposed node
    this cannot happen. On a LEAF it can: there are no children to hold, the review is advisory,
    and nothing consulted it before answering COMPLETE. Two doors closed a leaf root on
    vacuous-but-true criteria and read the contradiction straight off the database (wave 25,
    2026-09-05): `get_review` → `execution_admitted: false` and `next_steps` → `complete: true`,
    same node, same second, and the one that says done is the one that never asks.

    Advisory means advisory: this does not withhold `complete`, because the checker is an
    a-priori approximation (§9.9) and the real Level-2 verdict is contact's. What it does is
    stop the two surfaces from disagreeing in silence.
    """
    return [str(t.id) for t in _within(engine, root_id)
            if settled_positive(t) and (engine.open_l2_findings(t.id) or [])]


def _within(engine, root_id: Optional[TaskId] = None) -> list:
    """The nodes a question scoped to `root_id` is about: that node and its subtree, else all.

    The id-prefix convention was spelled out at four call sites, which is four chances for one
    of them to scope differently from the rest — the exact shape of "a rule that holds at one
    door and not at the next".

    …AND THE SUBTREE IS THE EDGES, not the spelling. Scoping by the `root.child` prefix is true
    of graphs `auto_decompose` builds and false of every graph built by hand, where a person
    names a node `parser` and the engine records its parent perfectly well. Those graphs then
    fell out of every scoped question silently: probed 2026-09-07, a child accepted by the clock
    under `root` was absent from the scoped list and present in the unscoped one. The prefix is
    kept as well — an id that spells its ancestry still answers, even before its parent edge
    exists — but the relation the graph actually holds is what decides.
    """
    tasks = engine.all_tasks()
    if root_id is None:
        return tasks
    by_parent, seen = {}, {str(root_id)}
    for t in tasks:
        by_parent.setdefault(str(t.parent_id), []).append(t)
    frontier = [str(root_id)]
    while frontier:
        for kid in by_parent.get(frontier.pop(), ()):
            if str(kid.id) not in seen:
                seen.add(str(kid.id))
                frontier.append(str(kid.id))
    return [t for t in tasks
            if str(t.id) in seen or str(t.id).startswith(f"{root_id}.")]


def closure_of(engine, task_id: TaskId) -> Optional[dict]:
    """How ONE node closed: who produced the standing verdict, and what it displaced or contradicts.

    The per-node owner of the facts `_how_this_closed` reports over a whole graph. It exists
    because the graph-wide lists were the ONLY place they were said, and a list of ids is a
    fact about a project, not about the node a reader is looking at: `/api/tasks/<id>` carried
    no verdict provenance at all, so the page a person watches drew every DONE node the same —
    the one earned through an instrument's probes and the one asserted by a name invented in
    the same command (wave 26, 2026-09-06, named by three doors independently).

    None for a node that has not settled positive: there is no closure to describe, and an
    empty dict there would read as "closed, nothing to weigh". The three list methods below
    filter on settledness and then read THIS — one predicate per fact, so a surface and a list
    cannot come to disagree about one node.
    """
    t = engine.graph.get_task(task_id)
    if t is None or not settled_positive(t):
        return None
    # …the record it CLOSED on: a later one landed on top is evidence beside it, not who closed it (`closing_verdict`)
    rec = engine.closing_verdict(task_id) or engine.get_exec_verdict(task_id) or {}
    displaced = engine.overruled_verdict(task_id) or {}
    return {
        # by_hand / self / instrument / none — §10.3's three weights of evidence
        "provenance": verdict_provenance(engine, task_id),
        "by_hand": bool(rec.get("by_hand")),
        # a hand verdict that replaced an instrument's OPPOSITE one on the same delivery
        "overruled": bool(displaced and not displaced.get("by_hand") and rec.get("by_hand")),
        "overruled_verdict": (str(displaced.get("verdict")) if displaced else None),
        # standing at PASS while its own current record says FAIL — a green that is not green
        "refuted": pass_stands_refuted(engine.graph, t),
        # CLOSED BY THE CLOCK, not by anyone's verdict. v4.0 routed a timed-out VALIDATING to
        # DONE(auto_pass) and v4.1 removed it (§16.14) — the clock, answering for a silent party,
        # invents no verdict — so no route produces this any more and what the field reads is a
        # row written by an older build. It stays visible for exactly that reason: a parent's
        # conjunction may still stand on such a child, and an acceptance nobody made is the
        # silent half of a weaker conjunct unless every surface can say which kind of DONE it is
        # looking at.
        "auto_accepted": t.done_reason is DoneReason.AUTO_PASS,
        "validator": rec.get("validator"),
        # WHAT THE CLOSURE ACTUALLY REACHED — the honest half, said at the close rather than
        # left to be inferred. A node closes on the procedure its contract pinned plus whatever
        # the validation went on to explore; everything outside that is UNCHECKED, and a criterion
        # can be decidable and still insensitive to a real divergence. That residue is the FM-3
        # boundary (Ch. 20, §15.7 — no structural check guards it), and naming it is the only
        # honest thing the system can do with it. Measured on `c_compiler`: a root closed PASS
        # by an independent validator, and 205 probes written from the same contract found 34 real
        # divergences in the tree it closed over.
        "checked_by": {
            "procedure_digest": rec.get("procedure_digest"),
            # …AND THE AUTHORING ONE BESIDE IT. A contract narrowed mid-run closes green and
            # the narrowing is visible only to someone who pulls `claim_drift` by hand — which
            # is exactly how the 0.074 of scope the executor-as-issuer cut on `c_compiler` was
            # found: by hand, at call #14. Two digests side by side make it a glance.
            # The WHOLE claim, not the procedures alone: a claim narrows through its risk
            # register as readily as through its checks, and reading one as the other is a
            # false green (measured on `c_compiler`, where the register grew from four
            # entries to ten after the work began and the procedures never moved).
            "authoring_digest": (_auth := engine.authoring_digest(task_id)),
            "claim_digest": (_now := claim_digest(t.spec, register_of(t))),
            "claim_moved_since_authoring": bool(_auth and _auth != _now),
            # …AND WHICH WAY IT MOVED, on the node itself. A flag that says "the claim moved"
            # sends the reader to another verb; a green node is read where it is, and the
            # movement that matters is the one that made passing easier. So the exclusions
            # added after authoring are named here, beside the verdict they qualify.
            "narrowed_after_authoring": ({
                k: v for k, v in (engine.claim_drift(task_id) or {}).items()
                if k in ("risks_added", "scope_added", "dropped", "reworded_after_refutation") and v
            } or None) if _auth and _auth != _now else None,
            # …AND A REFUTATION ITS ISSUER RULED OUT, which moves no digest: the claim reads the same and the PASS
            # re-ran less than what once failed it (`findings`)
            "retired_after_refutation": sorted({r["criterion"] for r in engine.lifted(
                task_id, "retired_after_refutation")["retired_after_refutation"]}) or None,
            "pinned_probes": rec.get("pinned_probes"),
            "pinned_probes_run": rec.get("pinned_probes_run"),
            # …AND WHICH OF THEM READ A SET THE CONTRACT DOES NOT PIN. Such a probe's object can
            # grow or shrink under it while the procedure's digest holds still, so its PASS says
            # less than the record otherwise reads — measured on `c_compiler`, where the corpus
            # went 60 → 79 files under a node that closed with `procedure_moved_since_authoring:
            # false`. Named on the CLOSURE, not only on the node's checks, because this is what
            # a later reading of the verdict has to be able to weigh.
            "probes_over_unpinned_sets": reads_an_unpinned_set(t.spec.criteria) or None,
            "beyond_the_procedure": rec.get("probes_beyond_the_procedure"),
            # …and the behaviours the validator NAMED past a pinned procedure it ran whole: exploration, decided by
            # nothing — the criterion stood on its procedure (`accounting.named_beyond_procedure`)
            "named_not_separately_observed": rec.get("named_beyond_the_procedure") or None,
            # A refutation whose criterion was renamed or replaced by a plan repair: the
            # obligation to re-run it cannot be enforced against a criterion that no longer
            # exists, so it is named here rather than lost. Silence is the failure mode this
            # whole change exists against.
            "orphaned_refutations": orphaned_regression(       # a finding filed under a bare Dep edge is one too
                t.spec.criteria, engine.regression_probes(task_id)) or None,
            # THE RESIDUE, AND IT IS NOT ONE SENTENCE. What the pinned set does not reach is
            # unchecked; so is a pinned probe that never ran (the internal self-report door, §10.3, closes a
            # node without running any); and so is the sensitivity of the procedure ITSELF — no
            # check anywhere decides whether a pinned command CAN fail, and §9.6 says none
            # can. Saying only the first would be the honest-sounding half of three.
            "residue": (
                ("NOT checked by the pinned procedure: "
                 f"{(rec.get('pinned_probes') or 0) - (rec.get('pinned_probes_run') or 0)} of "
                 f"{rec.get('pinned_probes')} pinned probes were never run on this closure "
                 "(an internal node closes on its executor's own report — §10.3). "
                 if (rec.get("pinned_probes_run") or 0) < (rec.get("pinned_probes") or 0)
                 else "checked by the pinned procedure and what the validation explored. ")
                + "Behaviour outside that is UNCHECKED; the procedure's own sensitivity is "
                  "unchecked too (a decidable criterion can be insensitive to a real "
                  "divergence, and no structural check guards that — FM-3, Ch. 8 / §15.7); "
                  "and what a pinned probe's output actually SHOWED is the validator's word — the "
                  "engine matches the command that ran, never the observation it returned"),
        } if rec else None,
    }


def closures_by_hand(engine, root_id: Optional[TaskId] = None) -> list[str]:
    """Settled nodes whose standing verdict was ASSERTED BY HAND, not produced by an instrument.

    The §10.3 degenerate case, and §15.7's named boundary: at a door where a person names
    themselves, the engine cannot establish that the reviewer is independent or that the
    observations happened. That is a declared limit, not a defect — what was a defect is that it
    was declared in one place and invisible in the two a reader consults. THREE doors reported
    the same thing across two waves (2026-09-04/05): a root closed with zero work through an
    invented reviewer, and `status`, `next_steps` and `q_V` gave it exactly what an earned root
    gets, while `get_verdict` and `gfso log` said plainly whose word it rested on.

    Not a reason to withhold `complete`: a person validating their own project by hand is the
    product's documented solo path. It is the one fact about such a graph a reader must not have
    to ask a second verb for. `hand_overruled_closures` is the sharper subset — those also
    displaced an instrument that said the opposite.
    """
    return [str(t.id) for t in _within(engine, root_id)
            if (closure_of(engine, t.id) or {}).get("by_hand")]


def passes_over_open_parts(engine, root_id: Optional[TaskId] = None) -> list[str]:
    """Wholes that stand PASSed while a part is not accepted — the departure from AND §12.8 reads off the log rather
    than gating, admitted at a seam where the signer could not lift it (`whole_waits_for_its_parts`). FM-4's trace
    where the PASS is untrue; a split's denial carried to its decomposer where the check showed the part unneeded."""
    return [str(t.id) for t in _within(engine, root_id) if passed(t)
            and any(not settled_positive(k) for k in engine.graph.get_active_children(t.id))]


def auto_accepted_closures(engine, root_id: Optional[TaskId] = None) -> list[str]:
    """Settled nodes that reached DONE on the CLOCK — the issuer never answered (§12.4, §16.14).

    The third weight of evidence beside a hand verdict and an instrument's: none at all. The
    canon makes auto_pass an acceptance (§16.14), so a parent's conjunction stands on such a
    child exactly as it stands on a validated one — which is why the fact has to travel. Before
    this, the conjunction refused it instead, and a child accepted by the clock locked its whole
    ancestry with no exit (probed 2026-09-07: the parent's PASS refused, `reopen` refused as
    consumed, `next_step` reporting `stuck: false`). Accepting it and SAYING so is the trade;
    accepting it silently would be the same lock's mirror image, a green nobody can weigh.
    """
    return [str(t.id) for t in _within(engine, root_id)
            if (closure_of(engine, t.id) or {}).get("auto_accepted")]


def hand_overruled_closures(engine, root_id: Optional[TaskId] = None) -> list[str]:
    """Settled nodes that closed on a HAND verdict which displaced an instrument's opposite one.

    The sibling of `refuted_passes`, for the other order of events. There, the instrument's
    refutation lands after the signature and the state is left showing the signature. Here it
    landed FIRST, on the same delivery, and a self-named party's record replaced it before the
    close — so the node's current verdict agrees with its state and nothing was contradicted at
    the moment anyone looked (CLI door, wave 24, 2026-09-04).

    Overruling is legitimate: the verdict is the issuer's act (§10.2), and §15.7 says no
    structural check can establish that a self-named reviewer is independent. So this is not a
    reason to withhold `complete` — a run where a person correctly overrode a wrong instrument
    would never finish. It is the one fact about such a graph that a reader has to weigh, and
    the surfaces carry it beside the answer instead of instead of it.
    """
    return [str(t.id) for t in _within(engine, root_id)
            if (closure_of(engine, t.id) or {}).get("overruled")]


def open_nodes(engine, root_id: Optional[TaskId] = None) -> list[str]:
    """The nodes not settled yet: what a goal's end, a clearing of its places and `complete` all ask of it (Thm 1: a
    passed parent over an open child is a claim that no longer holds)."""
    return [str(t.id) for t in _within(engine, root_id) if t.state not in TERMINAL_STATES]


def questions_left_standing(engine, root_id: Optional[TaskId] = None) -> list[str]:
    """What validators observed outside the criteria and no issuer answered, over nodes now settled: asked of no one any
    more (`issuer.open_questions` stops at a settled node), so said where a person reads the end."""
    return [f"{t.id}: {o['node']} saw {o['what']}" for t in _within(engine, root_id) if t.state in TERMINAL_STATES
            for o in engine.outside_the_criteria(t.id, own=engine.graph.get_parent(t.id) is None)]


def refuted_passes(engine, root_id: Optional[TaskId] = None) -> list[str]:
    """Nodes standing at PASS whose OWN current record says FAIL — a green that is not green.

    The engine has always detected this (it is q_V's numerator, and `q_V_from` names the nodes),
    but only the metric said so: measured on the CLI door 2026-09-02, a node signed PASS, an
    instrument returned FAIL four seconds later, the FSM correctly refused that signal because
    the node was terminal — and from then on `status` printed `[x] DONE` and the frontier
    answered COMPLETE, permanently, while `get_verdict` on the same node said FAIL. Two sources
    of truth disagreeing, with every surface a person reads on the wrong side of it.

    One predicate, and the surfaces read it rather than each deciding for themselves.
    """
    return [str(t.id) for t in _within(engine, root_id)
            if (closure_of(engine, t.id) or {}).get("refuted")]


def verdict_provenance(engine, task_id: TaskId) -> str:
    """WHAT KIND OF PARTY produced this node's standing verdict: by_hand / self / instrument.

    Three kinds, not two. A record a person asserted at a door where identity is self-declared,
    an INTERNAL node's own executor stamping its DELIVER (§10.3), and a registered instrument
    that is somebody other than the executor are three different weights of evidence, and the
    read collapsed the middle one into the last: a self-report came back as "produced by the
    registered instrument named in `validator`" while the evidence line beside it said
    SELF-REPORTED (measured on the MCP door 2026-09-02). Anything keying on the summary read a
    self-stamp as an independent check.

    The dispatcher has decided this correctly since the day it stopped REUSING a self-report as
    an independent verdict — the same comparison, in the same words. One owner, so the two
    cannot drift into disagreeing about one record.
    """
    rec = engine.get_exec_verdict(task_id)
    if not rec:
        return "none"
    if rec.get("by_hand"):
        return "by_hand"
    task = engine.graph.get_task(task_id)
    if task is not None and is_its_executor(task, rec.get("validator")):
        return "self"
    return "instrument"
