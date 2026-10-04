"""Signal validation enforcement — L2 wrapper around L1 role rules."""
from __future__ import annotations

import json
import os
import re
from datetime import datetime
from typing import Optional

from gfso.config import agent_id as _config_agent_id
from gfso.config import validate_internal as _validate_internal
from gfso.config import default_deadline_s
from gfso.engine.verdicts import criterion_version, observations, refuted_versions
from gfso.engine.findings import ruling_defect


from gfso.core.types import (Mode, Signal, SignalData, State, CriticVerdict, DoneReason, TaskId,
                             TERMINAL_STATES, Verdict, passed, settled_positive)
from gfso.core.protocol.fsm import available_signals, not_admissible_here
from gfso.core.protocol.validation import Role, required_role
from gfso.core.protocol.invariants import (validate_fail_has_criteria,
                                           fail_names_this_contract)
from gfso.core.handlers.structural import run_structural
from gfso.core.protocol.procedure import criteria_without_procedure, part_criteria
from gfso.core.handlers.constraint import _parse_numeric_bound
from gfso.core.graph import Graph
from gfso.core.graph.mutations import version_deadline
from gfso.core.graph.review import finding_keys
from gfso.core.graph.model import (admission_key, coverage_at, coverage_history, standing_split, dep_scope, generation_of_task, non_leaf_ids, stamped_with,
                                   recorded_by_an_appointed_observer)


class ValidationError(Exception):
    pass


class AdmissionRefused(ValueError):
    """A split the Syntactic level refuses at its admission (§11.5) — liftable by its decomposer alone, so a caller
    authoring the split (`auto_decompose`'s repair loop) reads `holes` as its problems instead of dying on them."""

    def __init__(self, message: str, holes: tuple[str, ...]):
        super().__init__(message)
        self.holes = holes


# THE SYNTACTIC LEVEL, whole: §9.5 lists CHECK-1, 1b, 2, 3, 4, 5, 6 at Level 0 and §11.5 states, in
# its own words, that "a decomposition that fails the Syntactic level is not admitted to execution".
# So the gate is the level, not a selection from it.
#
# Four of the seven used to gate and three did not: ACCEPTED_RISKS (4), risk nodes (5) and leaf
# delegation (6) were called "completeness documentation" and only surfaced. The observation behind
# that was real — gating the register bought fabricated entries and `edit_accepted_risks` churn — but
# it is an argument about what an agent does under a rule, not about whether the rule is the canon's,
# and §9.2 settles the object: "a decomposition without the register is incomplete by definition".
# A fabricated register is a q_T defect with a name and an owner; a silently ungated level is neither.
#
# CHECK-1c (anti-mock) is an engineering addition with no canon row, so it stays OUT of the gate: the
# gate is exactly the canon's level, in both directions.
#
# CHECK-3 is out of it too, by §11.5 and §12.10: a deadline crossing gates only the ADMISSION that sets the
# deadlines (`admission.deadlines_the_act_sets`); met afterwards — a revision, a re-issue — it is a
# flag routed to the consumer's issuer, who may re-ASSIGN or let it run. Gating it here refused the consumer's ACCEPT
# and the parent's PASS over deadlines the machine issuer itself wrote, with no move to lift it (sync audit, B-F1).
_EXEC_GATING_CHECKS = ("CHECK-1:", "CHECK-1b", "CHECK-2",
                       "CHECK-4", "CHECK-5", "CHECK-6")


def hole_kind(check_name: str) -> str:
    """What an unmet check does: `gate` — refuses the admission of a split that carries it (§11.5), and after admission
    is the decomposer's to repair, holding no issued work (§12.10); `flag` — CHECK-3 past the
    admission that set the deadlines, for the consumer's issuer to re-ASSIGN or let run (§12.10); `advisory` — a check
    the canon puts on no level (the anti-mock CHECK-1c). One owner: the frontier's step and `list_holes` read it."""
    return ("gate" if check_name.startswith(_EXEC_GATING_CHECKS) else
            "flag" if check_name.startswith("CHECK-3") else "advisory")


def l2_gate_on() -> bool:
    """Is the Level-2 execution gate active? `GFSO_L2_GATE=0` opts out — the canon's EXPLORE branch
    (§9.9): the plan's causal verification is bought with contact instead of with c_check. Off is
    also the honest setting where no checker instrument exists at all (a pure-human graph)."""
    return os.environ.get("GFSO_L2_GATE", "1") not in ("", "0")


def _l2_undischarged(graph: Graph, node) -> Optional[list[str]]:
    """The Level-2 obligations of `node`'s plan that are not yet discharged — where "plan" is its
    decomposition, or, for a childless node, its claim to BE one unit of work (D(t)=∅ is a value of
    D, and the degenerate plan is checked by the same rule; see gfso.critic._critique_leaf).

    `[]` = discharged (a CURRENT review found no gap, or every gap it named carries a recorded
    dispute). `None` = there is NO current verdict at all — never run, staled by an edit, or the
    checker returned nothing readable (fail-CLOSED: "no verdict is never read as clean", the
    checker's own doctrine — §9.1 Level 2 / gfso.critic).

    What is gated is that the check HAPPENED and its findings were DISPOSITIONED — never that the
    checker is right. L2 is an LLM-review APPROXIMATION over the faithfulness axis (§9.9); the
    real Level-2 verdict belongs to contact (q_D). Two exits, and they are NOT symmetric — which is
    what two doors reported as "the obligations are frozen at first reading" (wave 26, 2026-09-06):
    RECORDING why the finding is wrong (`dispute_finding`) discharges it where it stands, while
    CHANGING the plan RETIRES the verdict instead (any edit stales the review — the record and its
    disputes die with it), so a fix leaves `None` here and execution stays shut until a fresh review
    speaks. That is fail-closed and deliberate — a lowered criterion and an added coverage look
    alike until the checker reads them — but the doors used to promise discharge and deliver a
    re-run, and the refusals now say the two-step shape out loud."""
    if not getattr(node, "verified", False):
        return None                                 # no review current for THIS version of the plan
    raw = graph._storage.get_critique(node.id)
    rec = json.loads(raw) if raw else None
    if not rec:
        return None
    if rec.get("semantic_covered") is True:
        return []
    if rec.get("semantic_covered") is not False:
        return None                                 # no/incomplete verdict — fail-closed
    # THE NAME OF A FINDING HAS ONE AUTHOR (`core.graph.review.finding_keys`). It had three — this
    # gate, the verb that accepts a dispute, and the delta baseline — and they had to agree byte for
    # byte or a dispute would be refused as "not an open finding" while this gate held the node shut
    # on exactly that finding. Among the kinds named there: the obligations of the node's OWN goal
    # that none of its OWN criteria decides (FM-1.f) — the checker asks whether the CHILDREN carry
    # the parent, that one whether the parent carries the GOAL, and until 2026-08-21 no gate asked
    # it (measured: a regex engine signed off on two root criteria, neither requiring it to match
    # anything, with 21 hidden tests red).
    return finding_keys(rec)


def execution_admitted(graph: Graph, node) -> bool:
    """May this node's CHILDREN start? — the question every reading surface was answering itself.

    Three spellings existed. `review_decomposition` had it whole; `get_task` read only the Level-2
    findings and skipped the structural level and the gate flag; `get_review` wrote
    `t.verified and not open_findings`, and `not None` is true — so ⊥, the state the checker's own
    doctrine calls "no verdict is never read as clean", came back as ADMITTED.

    Probed 2026-09-07: a node reviewed by a checker whose reply was unreadable answers
    `execution_admitted: True` at both reading doors while the engine, in the same second, refuses
    its child's ACCEPT and explains exactly why. That is the false green on the Level-2 panel — the
    class this product catches for other people — on its own surface, and the surface it appears on
    is the one a person watches.

    Answered here because this is where the refusal is decided: the same three facts, in one place,
    so an affordance cannot come to disagree with the machine.
    """
    if node is None:
        return False
    return not l2_gate_on() or _l2_undischarged(graph, node) == []


def _fail_extension_shrank(old_desc: str, new_desc: str) -> bool:
    """Did a revision LOOSEN this criterion — decidably, on the tier where that is decidable?

    "Adding coverage so that ⋀criteria(children) ⊨ cᵢ" and "lowering cᵢ to what the children already
    deliver" wear the same shape at a re-delivery; what tells them apart is whether cᵢ's fail-extension
    shrank (§1.3: a criterion forbids exactly by having one). In general that is L2 — but on the
    numeric-bound tier it is O(1) arithmetic (§9.6/CHECK-7), and this is that tier: same metric, same
    operator, a bound that now admits strictly more. Anything else returns False — the undecidable
    middle is routed to the checks, never guessed at here.
    """
    old, new = _parse_numeric_bound(old_desc), _parse_numeric_bound(new_desc)
    if not old or not new:
        return False
    (o_metric, o_op, o_val), (n_metric, n_op, n_val) = old, new
    if o_metric != n_metric or o_op != n_op:
        return False
    return n_val > o_val if o_op in ("<", "<=") else n_val < o_val


def session_fit(graph: Graph, task_id) -> Optional[dict]:
    """The decomposer's recorded count and judgement for a node (`Engine.record_session_fit`), or None."""
    raw = graph._storage.get_setting(f"session_fit:{task_id}")
    try:
        return json.loads(raw) if raw else None
    except (ValueError, TypeError):
        return None


def fits_one_session(graph: Graph, task_id) -> bool:
    """Does one executor session carry this node's whole subtree — build it and check it directly (§3.7)?
    The judgement recorded on the node AND on every active node below it: a part that does not fit makes the
    whole not fit. No judgement is "does not fit", which leaves the seams where they always were."""
    if not (session_fit(graph, task_id) or {}).get("fits"):
        return False
    return all(fits_one_session(graph, c.id) for c in graph.get_active_children(task_id))


def checked_by_contact(graph: Graph, task) -> bool:
    """Is this part's plan checked by contact rather than held for the a-priori review — a part of its own executor's
    split (same Del) whose whole one session of that executor carries? Internal work, validated once at its top (§10.3,
    §3.7): holding it for the review is VERIFY at a c_check the work does not repay — measured, eight review rounds,
    35 min, on a goal one bare session finished in 12 (AUTO haiku coreutils, 2026-10-12) — so it EXPLOREs (§9.9).
    ONE predicate for the machine's ACCEPT rule and the surface that answers "may it start": a surface alone offered
    an ACCEPT the machine refused, and the review that would have lifted it was never asked for (critic, 2026-10-12)."""
    parent = graph.get_parent(task.id)
    return parent is not None and str(task.assignee) == str(parent.assignee) and fits_one_session(graph, parent.id)


def within_a_scope(graph: Graph, task) -> bool:
    """Is this node inside one executor session's scope — its parent's subtree fits one? Then it is that
    executor's internal work (§10.3, below κ): the scope's one validation at its top carries it."""
    parent = graph.get_parent(task.id)
    return parent is not None and fits_one_session(graph, parent.id)


def scope_top(graph: Graph, task):
    """The top of the one-session scope `task` lies in — the highest node above it, through nodes of the same
    Del, whose whole subtree one session of that executor carries — or None where `task` is in no such scope
    of more than one node. Within κ — what one executor session realizes and checks (§3.7) — the executor
    absorbs the structure and presents one result (§10.3); a Del change is a seam and ends the walk."""
    t = task
    while ((p := graph.get_parent(t.id)) is not None and str(p.assignee) == str(t.assignee)
           and fits_one_session(graph, p.id)):
        t = p
    return t if graph.get_active_children(t.id) and fits_one_session(graph, t.id) else None


def scope_members(graph: Graph, top) -> list:
    """The scope's nodes top-down: its top and every active node below it."""
    return [top] + [m for c in graph.get_active_children(top.id) for m in scope_members(graph, c)]


def footing(graph: Graph, task) -> list:
    """What this node's result is built from: every part below it (its result is its subtree's artifact) and
    every producer it consumes (its criteria read that output, Ch. 2's Dep)."""
    return ([m for m in scope_members(graph, task) if str(m.id) != str(task.id)]
            + [p for e in graph.dep_edges(adopted=True) if str(e.to_id) == str(task.id)
               if (p := graph.get_task(TaskId(e.from_id))) is not None])


def parts_procedure(graph: Graph, task) -> dict:
    """{criterion of the whole: the pinned procedure of each part mapped to it (`part_criteria`)} — what a
    validation of `task` runs over its delivered result besides its own procedure (`procedure.unrun_parts`).

    Only the parts already DONE: a part still in VALIDATING is validated in the same run as its whole — a scope's
    one validation lays parts and whole over one artifact — and runs its procedure there under its own name; one
    DONE was settled before this validation began, on its own earlier delivery, whoever settled it (an internal
    part's self-check, or a clock that validated nothing, is the more reason). Direct parts only: a part that is
    itself a whole had its own parts' procedures demanded at its own validation, over the artifact as it stood
    then — and so, as a DONE part's procedure, its own DONE parts' too: a part's procedure here is the whole of what
    its validation ran (`settled_procedure`), so a rewrite at any depth below is read on this delivery (critic r1,
    2026-10-04: root → mid → leaf, a rewritten leaf closed the root DONE when only mid's probes were demanded)."""
    done = {str(c.id): c for c in graph.get_active_children(task.id) if settled_positive(c)}
    out: dict = {}
    for name in dict.fromkeys(m.criterion_name for m in task.criterion_mappings):
        kids = dict.fromkeys(str(m.child_id) for m in task.criterion_mappings
                             if m.criterion_name == name and str(m.child_id) in done)
        if crits := tuple(c for k in kids for c in part_criteria(k, settled_procedure(graph, done[k]))):
            out[name] = crits
    return out


def settled_procedure(graph: Graph, task) -> tuple:
    """Every criterion whose pinned probes a validation of `task` runs over its delivery: its own, then its DONE
    parts' (`parts_procedure`) — what a whole above it demands again of it."""
    return tuple(task.spec.criteria) + tuple(c for cs in parts_procedure(graph, task).values() for c in cs)


def record_stands(graph: Graph, audit, task, rec: Optional[dict]) -> bool:
    """Does this verdict record stand for the delivery that stands now — THE one question every reader of a
    record asks before deciding on it: the PASS gate, the observation a signature reads, the frontier, reuse.

    Two conditions. It was made on this delivery (its generation). And nothing in the node's footing was
    delivered again or FAILed since it was made: then it is a verdict on a result that no longer stands. Read
    at the surfaces and not at the gate, a SEMI holder's hand PASS on a whole signed over a part's rework that
    broke it (critic, 2026-09-28). "Since" is the log's order (`log_at`, the log's length when the record was
    made), never the clock's: two stamps inside one tick tie. A record a host wrote with only its time is read by
    it, a tie counting as after. With neither, or no log to read, it cannot be dated, and it is read the way that
    cannot turn into a false acceptance: a FAIL stands — it refuses, and an appointed observer's refutation kept on a
    ledger older than the dating must still bind — and a PASS does not, costing only a validation."""
    if not rec or task is None or not stamped_with(rec, generation_of_task(task)):
        return False
    under = footing(graph, task)
    if not under:
        return True
    if_undated = str(rec.get("verdict")) == Verdict.FAIL
    if audit is None:
        return if_undated
    if isinstance(rec.get("log_at"), int):
        return not any(audit.last_at(m.id, signal=s) >= rec["log_at"]
                       for m in under for s in (Signal.DELIVER, Signal.FAIL))
    try:
        at = datetime.fromisoformat(str(rec.get("ts") or ""))
    except ValueError:
        return if_undated
    return not any(a.signal in (Signal.DELIVER, Signal.FAIL) and not a.rejected and a.timestamp >= at
                   for m in under for a in audit.get_entries(m.id))


def stands_as_pass(graph: Graph, audit, task, rec: Optional[dict]) -> bool:
    """A PASS record that stands for the delivery that stands now (`record_stands`)."""
    return bool(rec) and rec.get("verdict") == Verdict.PASS and record_stands(graph, audit, task, rec)


def split_owed(graph: Graph, task) -> Optional[dict]:
    """Why this CHILDLESS node's work is not a leaf's because its plan's author judged it larger than one session of
    its executor — or None. A node above κ, one executor session (§3.7), is not a leaf (§3.7), and its split is owed:
    authored by its executor as part of performing it (§11.5, deferred decomposition). So the refusal falls on HIS
    act — the DELIVER — whose lift, his own split, is his own move (§12.16 (ii)); on the issuer's PASS only where he
    is the executor too. Refusing the issuer's PASS at a seam would leave its lift with the counterparty.

    Only under a mode: before modes the system makes no split move for a registered executor, which has no tool
    to split with, so the refusal would have no lift at all (§12.16 (ii)) — a node judged too big then parked with
    nobody's move, where it had been delivered and validated (critic, 2026-09-28)."""
    fit = session_fit(graph, task.id) if task is not None else None
    if (not fit or fit.get("fits") is not False or graph.get_active_children(task.id)
            or project_mode(graph) is None):
        return None
    return {"kind": "split_owed", "fails": [],
            "why": (f"its plan's author judged it larger than one session of its executor"
                    + (f" ({fit.get('volume')})" if fit.get("volume") else "")
                    + " — a node above κ, one executor session (§3.7), is not a leaf (§3.7), and its split is owed "
                      "(§11.5, deferred decomposition): its parts are what get delivered and validated"),
            "opens_with": (f"its executor splits it — `auto_decompose(root_id='{task.id}')`, or `decompose` "
                           f"on it — and the parts carry its criteria")}


def observed_here(graph: Graph, task) -> bool:
    """Does the instrument observe this delivery? Where a seam's validation stands: a public node (a result
    crossing into another scope, §10.3), and the top of every scope one executor session carries — a node
    whose parent's subtree is not one session's work, internal or not, since past κ the executor's own check
    is no longer a direct contact-check (§3.7). Inside a scope, no: the scope's validation at its top runs
    every criterion inside it, and a validation per piece bought only a wait for each (a 2.6-minute task
    took 39 to 70). `GFSO_VALIDATE_INTERNAL=1` observes every delivery, for measurement."""
    return graph.is_public(task) or not within_a_scope(graph, task) or _validate_internal()


def observation_binds(graph: Graph, task) -> bool:
    """Does an observed divergence bind the signature on this node? Where its issuer is its executor.

    Whether a refutation binds is the implementation's choice within §12.16 (ii) (§16.13), and (ii) decides
    it. Where the issuer is the executor — an internal node, a self-issued root — the refused party has
    lifts of his own (repair and re-deliver, or revise his own procedure), so the divergence binds: the
    holder does not sign past the system's check. At a seam his only lift would be a revision the executor
    must re-consent to, so binding would leave him none: there the signature reads the latest appointed
    record, and an earlier divergence stands on the ledger as a logged disagreement."""
    return str(graph.issuer_of(task.id) or "") == str(task.assignee or "")


def displaces_a_refutation(graph: Graph, task, recorder, by_hand) -> bool:
    """May this record stand past an earlier refutation of the same delivery? Only the issuer's own
    observation — by his hand, under his name — and only at a seam: it is the one lift §12.16 (ii) requires
    him to have. A run of the instrument, whatever name it is recorded under, or anyone else's record,
    stands BESIDE the refutation and does not undo it."""
    return (bool(by_hand) and not observation_binds(graph, task)
            and str(recorder or "") == str(graph.issuer_of(task.id) or ""))


def observation_standing(graph: Graph, task, audit) -> dict:
    """What the APPOINTED observers recorded on the node's CURRENT delivery: {pass, fails}.

    Every record that stands is read (`record_stands`), not the latest (a later record by anyone does not
    unmake an appointed observer's refutation), with the current record included for rows written before
    the ledger existed. Appointed = the instrument, or the node's issuer where he is not its executor
    (`recorded_by_an_appointed_observer`)."""
    issuer = graph.issuer_of(task.id)
    recs = [r for r in observations(graph._storage, task.id) if record_stands(graph, audit, task, r)]
    cur = graph.exec_verdict_record(task.id)
    if record_stands(graph, audit, task, cur):
        recs.append(cur)
    appointed = [r for r in recs if recorded_by_an_appointed_observer(r, task, issuer)]
    # at a seam the issuer's own latest record is his check, and what came before it is a logged disagreement
    mine = [i for i, r in enumerate(appointed)
            if displaces_a_refutation(graph, task, r.get("validator"), r.get("by_hand"))]
    if mine:
        appointed = appointed[mine[-1]:]
    fails = sorted({str(c) for r in appointed if str(r.get("verdict")) == Verdict.FAIL
                    for c in (r.get("failed_criteria") or ())})
    return {"pass": any(str(r.get("verdict")) == Verdict.PASS for r in appointed), "fails": fails}


def observation_blocker(graph: Graph, task, audit) -> Optional[dict]:
    """Why no PASS may be signed on this delivery, for or against an appointed observation — or None.

    Two grounds, one owner (the record door, the PASS gate, `pass_blocked_by` and so every surface read
    it): an appointed observer recorded a divergence on it (Inv-2: that is the criterion's value, fail);
    or, under a mode, the delivery has not been observed by an appointed observer — at every node, because
    the system observes every delivery whoever holds it, and a mode is where the instrument is staffed
    (C-12). The second is lifted by the refused party's own move, `validate_result` (§12.16 (ii)). With no
    mode a seam keeps the older rule below it (a current PASS on the record, whoever recorded it) —
    the appointed requirement is C-12's, and it came with the modes."""
    if task is None:
        return None
    st = observation_standing(graph, task, audit)
    if st["fails"] and observation_binds(graph, task):
        return {"kind": "observed_fail", "fails": st["fails"],
                "why": (f"an appointed observer recorded this delivery FAIL on {', '.join(st['fails'])}, and "
                        f"where the node's issuer is its executor an observed divergence is that criterion's "
                        f"value (Inv-2, §12.8) — no later record turns it into a pass"),
                "opens_with": (f"signal FAIL with those criteria and re-deliver the repair, or, where the "
                               f"observer's own pinned probe is what is wrong, revise the criterion "
                               f"(`edit_criteria('{task.id}', …)`)")}
    if st["fails"]:
        return {"kind": "observed_fail", "fails": st["fails"],
                "why": (f"an appointed observer recorded this delivery FAIL on {', '.join(st['fails'])} — the "
                        f"check a PASS signature would read does not pass (Inv-2, §10.2)"),
                "opens_with": (f"signal FAIL with those criteria, or, if you observe otherwise, record your own "
                               f"observation (`record_verdict('{task.id}', 'PASS', …)`) — it stands beside the "
                               f"earlier one as a logged disagreement — then sign. Another run of the instrument "
                               f"does not undo a refutation")}
    must = project_mode(graph) is not None and observed_here(graph, task)
    if must and not st["pass"]:
        return {"kind": "unobserved", "fails": [],
                "why": ("no appointed observer has observed this delivery — "
                        + ("it is a seam, where the result crosses into another scope (§10.3)"
                           if graph.is_public(task) else
                           "it is the top of a scope one executor session carries, where that scope's "
                           "validation stands (§3.7, §10.3)")
                        + "; the executor's own self-check is evidence, not the observation, and a hand "
                          "record binds only from the node's issuer where he is not its executor"),
                "opens_with": (f"`validate_result('{task.id}')` observes it now (where the project has a "
                               f"validator it also runs by itself); `get_verdict('{task.id}')` reads the result")}
    return None


def _split_the_fail_refutes(graph: Graph, task, covered_then, audit, fail_at: int):
    """(the split as it stands, the children that had left it before the FAIL). §12.6: a settled cancellation takes its
    child out of the plan. Read raw, a coverer ABANDONED before the FAIL was never DONE, so no failed criterion it
    co-covered ever read as refuted — the machine issuer CANCELled `head` and its parent's FAIL then opened no repair
    (GB_coreutils_tmiy4m001). One that left AFTER the FAIL changed the coverage: a repair, as before."""
    split, kids = standing_split(graph, task)
    active = {str(k.id) for k in kids}
    return split, {k for _, k in covered_then or () if k not in active and -1 < audit.last_at(TaskId(k)) < fail_at}


def _refuted_coverage_refusal(graph: Graph, task, rec: dict, audit) -> Optional[str]:
    """The disposition of a re-delivery under a contact-refuted decomposition — the FM-1 branch.

    A parent criterion failing while every mapped child passes its OWN is the q_D event (§15.4) and
    an FM-1 defect — FM-1.d (children exist, `⋀criteria(tⱼ) ⊭ cᵢ`) or FM-1.f (the goal needed a
    criterion nobody wrote). The defect is in the DECOMPOSITION, owned by whoever built it, so the
    repair is a **revision of the parent under Inv-1** (§12.3): a re-ASSIGN under the same id with a
    corrected mapping or an added covering child. A revision does not cascade — the subtree is kept,
    staleness surfaces through CHECK-1/CHECK-1b/CHECK-3 — and the consumption gate is never reached,
    which is why this route has no wall where the downward one does (`EVIDENCE_LOG` §13.3).

    Per failed criterion, one of five dispositions; the first that applies to any criterion refuses:
      · DROPPED — the refuted criterion is gone from the packet: the fail-extension collapsed to
        empty, which is a false close, not a repair (its removal is a scope change owned by the
        issuer above, §9.2).
      · LOOSENED — decidably weakened on the numeric tier (above): the same false close.
      · EDITED — the text changed undecidably: legitimate on its face, so it is admitted once the
        revised plan's checks have SPOKEN again (L0 clean + a current, dispositioned L2 verdict).
        What is required is that the check happened, never that the checker is right — the same
        doctrine as the execution gate, and `GFSO_L2_GATE=0` opts out of the L2 half identically.
      · UNREPAIRED — criterion unchanged and every coverer untouched since the FAIL: re-delivering
        an unchanged aggregate over an unchanged plan decides nothing. A coverer whose own pinned probe the
        FAIL showed not holding is not untouched in this sense — it failed on the delivered result (§8.5),
        so the repair is the aggregate's — and so is one the FAIL did not show holding there: the pattern needs
        every child shown passing on the delivered result (`procedure.parts_not_shown_holding`, with the record).
      · REPAIRED — a coverer was touched (reopened, revised, or newly added), or the criterion's coverage was
        re-admitted (§2.4: a remap is the split's, and moves no child): admitted, as before.
    """
    now = {c.name: c for c in task.spec.criteria}
    was = rec.get("criteria_text") or {}
    fail_at = audit.last_at(task.id, signal=Signal.FAIL)
    covered_then, _ = coverage_at(coverage_history(graph._storage, audit, task.id), fail_at)
    # …A PART WHOSE OWN PINNED PROBE REFUTED THE CRITERION was read on this node's delivered result, not on its own
    # earlier delivery: the whole's delivery broke it, its executor repairs it, and that is no refuted decomposition.
    read_here = rec.get("parts_not_shown_holding") or {}
    dropped, loosened, edited, unrepaired = [], [], [], []
    split, left = _split_the_fail_refutes(graph, task, covered_then, audit, fail_at)
    for crit in rec.get("failed_criteria") or ():
        coverers = [m.child_id for m in split.criterion_mappings if m.criterion_name == crit]
        if crit not in now:
            dropped.append(crit)
            continue
        if not coverers:
            continue                      # the parent's own layer — a parent-level fix is legitimate
        old_desc = was.get(crit)
        if old_desc is not None and old_desc != now[crit].description:
            (loosened if _fail_extension_shrank(old_desc, now[crit].description)
             else edited).append(crit)
            continue
        # …OR ITS PROCEDURE WAS REVISED: the refutation came from the observer's pinned probe, and the
        # canon's remedy against a deterministic observer is a revision that corrects that procedure
        # (Inv-1) — nothing a child could re-do repairs it. Refusing it as "the decomposition was
        # refuted" left a good delivery after a false observation no way through (2026-09-27). The
        # revision stays on the record (`claim_drift` names a criterion rewritten after refutation).
        # …through the same re-check an edited text gets (L0 + a current L2 verdict): a probe loosened to
        # what the result already prints is the cheapest false close there is.
        refuted = refuted_versions(graph._storage, task.id).get(crit)
        if refuted and criterion_version(now[crit].description,
                                         [p.to_dict() for p in (now[crit].check or ())]) not in refuted:
            edited.append(crit)
            continue
        # …and none is untouched where the split was re-admitted with this criterion's coverage changed (§2.4)
        untouched = [str(cid) for cid in coverers
                     if (covered_then is None
                         or {k for c, k in covered_then if c == crit and k not in left} == {str(k) for k in coverers})
                     and (child := graph.get_task(cid)) is not None and child.state == State.DONE
                     and audit.last_at(cid) < fail_at and str(cid) not in read_here.get(crit, ())]
        if len(untouched) == len(coverers):
            unrepaired.append(f"{crit} (covered by: {', '.join(untouched)})")

    revision = (f"The canonical repair is the DECOMPOSITION's: re-admit {task.id}'s split with a corrected "
                f"mapping or an added covering child, so that the mapped children's criteria carry the "
                f"parent's (map_criterion / add a child — §11.5), or revise this node (edit_criteria, "
                f"§12.3) where the criterion itself was wrong. Neither cascades — the subtree is "
                f"kept and the consumption gate is not involved. Reworking a child that already met "
                f"its own criteria asks it to guess (§15.4 q_D; FM-1.d/FM-1.f).")

    if dropped:
        return (f"cannot re-DELIVER {task.id}: the criteria contact refuted were REMOVED rather than "
                f"covered ({', '.join(dropped)}) — a criterion with no fail-extension forbids nothing, "
                f"so this closes the node instead of repairing it (§1.3). Restore the criterion and "
                f"add the coverage; a genuine scope change belongs to the goal above (§9.2). " + revision)
    if loosened:
        return (f"cannot re-DELIVER {task.id}: the refuted criteria were LOOSENED to what the current "
                f"result already delivers ({', '.join(loosened)}) — the bound moved, the work did not. "
                f"That is a false close in the shape of a repair (§1.3 fail-extension). " + revision)
    if edited and l2_gate_on():
        if (holes := _l0_holes(graph, task)):
            return (f"cannot re-DELIVER {task.id}: its criteria were revised after contact refuted "
                    f"them ({', '.join(edited)}), and the revised plan does not pass Level 0 — "
                    f"the mapping must speak again before the aggregate does (§9.5): "
                    + "; ".join(f"{h.check_name}: {h.details}" for h in holes))
        if (gaps := _l2_undischarged(graph, task)) is None:
            return (f"cannot re-DELIVER {task.id}: its criteria were revised after contact refuted "
                    f"them ({', '.join(edited)}) and no CURRENT Level-2 verdict covers the revision — "
                    f"a lowered criterion and an added coverage look alike until CHECK-7 speaks "
                    f"(§9.6). Run review_decomposition({task.id}) first")
        if gaps:
            return (f"cannot re-DELIVER {task.id}: the Level-2 review of the revised plan names gaps "
                    f"that are still open — the mapped children's criteria do not carry these parent "
                    f"criteria (§9.1). TWO EXITS, and the first one takes two steps: fix the "
                    f"plan (edit_criteria / map_criterion / add a child) AND re-run "
                    f"review_decomposition({task.id}) — the fix RETIRES this verdict rather than "
                    f"discharging it, so until the fresh review speaks there is no current verdict "
                    f"at all; or record why the finding is wrong (dispute_finding({task.id}, "
                    f"<criterion>, <why>)), which discharges it in one. Open: " + "; ".join(gaps))
    if unrepaired:
        return (f"cannot re-DELIVER {task.id}: the FAILed criteria are covered by children untouched "
                f"since that FAIL — contact refuted the DECOMPOSITION, not the aggregate "
                f"({'; '.join(unrepaired)}). " + revision)
    return None


def _l0_holes(graph: Graph, parent) -> list:
    """The FAILING plan-correctness checks of `parent`'s decomposition (coverage / non-redundancy /
    DAG / deadlines). Computed live so a stale cache never gates. Empty = the plan is admissible."""
    parent, children = standing_split(graph, parent)
    if not children:
        return []
    # THE SAME POPULATION THE CACHE SEES (`Graph.dep_scope`) — the subtree, not the direct
    # siblings. Filtered to sibling pairs here, the gate admitted execution over a plan whose
    # cross-branch seam ran backwards in time or closed a cycle, and said `count: 0` while doing it.
    scoped, deadlines = dep_scope(graph, parent.id)
    edges = [(str(e.from_id), str(e.to_id)) for e in scoped]
    # Same leaf information the cached computation gets (`Engine._recompute_checks`): without it
    # CHECK-6 would read every child as a leaf HERE and as a leaf-or-branch THERE, so the gate could
    # refuse a start over a hole `get_checks`/`list_holes` shows green — two views of one plan.
    return [c for c in run_structural(parent, children, edges,
                                     non_leaf_ids(graph, children), deadlines)
            if not c.passed and not c.skipped and c.check_name.startswith(_EXEC_GATING_CHECKS)]


def whole_waits_for_its_parts(graph: Graph, task) -> bool:
    """Is a PASS on this whole refused while its parts are open or its split is red — true only where the whole's
    issuer is its own Del: the PASS is the issuer's (an instrument signs it for him), and only one who is also the
    decomposer and the children's issuer lifts that refusal by his own moves (§12.16 (ii)).

    The canon gates neither: the issuer's check is "a contact over the delivered result reading no child state", and
    its departure from AND is read off the log (§12.8). At a seam the issuer can do nothing about another scope's
    children or split, so there the PASS is admitted and the departure said (`Engine.passes_over_open_parts`; sync
    audit, B-F4 = A-F2)."""
    return task is not None and str(graph.issuer_of(task.id)) == str(task.assignee)


def _pass_rules(signal_data: SignalData, graph: Graph, audit) -> None:
    """PASS: Theorem 1 over the children, and the seam's independent verdict.

    One rule family per function: `validate_signal` had grown to seventy statements over
    four unrelated signals, and a reader looking for what refuses a PASS had to walk the
    DELIVER and RESOLVE_BLOCK rules to get there. Raises ValidationError, as before.
    """
    if signal_data.signal == Signal.PASS and graph.get_state(signal_data.task_id) == State.VALIDATING:
        # …ONLY WHERE A PASS IS A MOVE AT ALL. These rules are about a DELIVERY — is it validated, do
        # the children carry it — and they were checked before the FSM had said whether the signal
        # moves anything here, so a PASS on a node that had delivered NOTHING was answered "no
        # independent verdict is recorded … `record_verdict(…)` and then signal PASS". Following
        # that advice records a verdict about work that does not exist, or fails again for the real
        # reason nobody named: nothing has been delivered (measured on the human door 2026-08-22).
        # Outside VALIDATING the FSM's own answer is the true one, and it is what the caller gets.
        # …AND THE CONJUNCTION ASKS WHETHER THE CHILD WAS ACCEPTED, not whether its pass was
        # earned. §12.4 states it outright — "DONE is reached through acceptance (PASS ∨ auto_pass),
        # never through fail" — and §16.14 calls the timeout edge auto-ACCEPTANCE. Reading the
        # conjunction as `passed` (DONE with a verdict someone gave) excluded auto_pass, and since
        # the child is terminal and, once its parent has delivered, CONSUMED, there was no way
        # back: probed 2026-09-07 end to end — the parent's PASS refused, `reopen` refused as
        # consumed, and `next_step` reporting `stuck: false` while advising the very signal the
        # engine forbids. A permanent lock with a green frontier over it.
        # The auto-acceptance is not thereby laundered into an earned pass: it stays recorded apart
        # (§16.14), q_D still excludes it, q_V still carries its risk through the pass→later-fail
        # term, and the acceptance below NAMES the children it stood on rather than absorbing them
        # silently — the making-explicit answer to a weaker conjunct, instead of a stalled graph.
        _t0 = graph.get_task(signal_data.task_id)
        _waits = whole_waits_for_its_parts(graph, _t0)
        unaccepted = [c.id for c in graph.get_active_children(signal_data.task_id)
                      if not settled_positive(c)]
        if unaccepted and _waits:
            raise ValidationError(
                f"cannot PASS {signal_data.task_id}: not all children have PASSed "
                f"(V=AND of children): {unaccepted}"
            )
        # …AND THE AND MUST STILL BE ABOUT THIS GOAL. Thm 1 (§7.3) makes a parent's PASS the
        # conjunction over its children, and that conjunction only establishes the PARENT because
        # the children jointly cover its criteria — which is what L0 checks. The L0 gate fired in
        # ONE place: a child's ACCEPT, against its parent's plan. So it was a precondition on one
        # instant rather than a property of the run, and a plan broken AFTERWARDS was never
        # re-read. Probed 2026-09-05 (audit F2): both children ACCEPT under a clean plan, one is
        # then CANCELled, `get_active_children` correctly drops it, CHECK-1 goes red — and the root
        # reached DONE/PASS with its own coverage check unmet and one criterion covered by nothing
        # at all. `edit_criteria` adding an uncovered criterion does the same without CANCEL, and a
        # ROOT's own plan was gated nowhere at any point in its life, having no parent to be a child
        # of. The letter held ("not admitted to execution" — it was admitted under a clean plan);
        # the purpose did not.
        #
        # Childless nodes are unaffected: `_l0_holes` is empty where there is no decomposition.
        if _t0 is not None and observation_binds(graph, _t0) and (_owed := split_owed(graph, _t0)) is not None:
            raise ValidationError(f"cannot PASS {signal_data.task_id}: {_owed['why']}. {_owed['opens_with'][:1].upper()}"
                                  f"{_owed['opens_with'][1:]}.")
        if _waits and (_holes := _l0_holes(graph, _t0)):
            raise ValidationError(
                f"cannot PASS {signal_data.task_id}: its own decomposition does not pass the "
                f"Syntactic level NOW (§9.5), so the AND over its children is not a verdict about "
                f"THIS goal (Thm 1): "
                + "; ".join(f"{h.check_name} — {h.details}" for h in _holes)
                + ". The plan was admissible when the children started and is not any more — repair "
                  "it (map the criterion to a child, add a coverer, or revise the contract) and the "
                  "aggregate can be claimed again. `list_holes` lists the same thing.")
        # Verifier ≠ executor (§10.3: self-checking violates IC). When the signer IS the node's
        # executor (collapsed ids — the self-execution regime), the FSM cannot tell an
        # evidence-based issuer PASS from a self-stamp, so the evidence must come from OUTSIDE
        # the id: a recorded independent verdict for the CURRENT delivery (a rework stales it).
        # Distinct ids (source ≠ Del) keep the canon default — the separation already exists.
        # §10.3: the gate is a GATE-ON-THE-SEAM — it fires on PUBLIC nodes (a root, or
        # Del(child) ≠ Del(parent)), not on every node of the graph. An INTERNAL node (same Del
        # as its parent) is the agent's private decomposition: it legitimately SELF-verifies
        # (DELIVER carries self_validation) and its guarantee is carried by the validation of the
        # public result it rolls up into (Thm 1 non-redundancy) — so a same-Del self-PASS passes here.
        # The ROOT is always a seam: "done" (root DONE/PASS) never completes on a self-stamp.
        task = graph.get_task(signal_data.task_id)
        # …and on an INTERNAL node the canon still asks for something. §10.3 says such a node
        # self-verifies — "DELIVER carries `self_validation`" — and §2.3 says ⊥ is not a pass. With
        # neither a self-check nor a recorded verdict, its PASS stands on nothing at all: measured on
        # the human door 2026-08-21, a leaf went DELIVER → PASS by its own executor eight seconds
        # apart and reached DONE while `get_verdict` answered "it has not been validated" about the
        # same node. What is required here is the DECIDED self-report the canon names, not
        # independence (that is owed at the seam, and the branch below is where it is enforced):
        # deliver with `self_validation`, or record your own verdict — both leave a record.
        # …AND THE GUARD ASKS FOR THE RECORD, NOT FOR THE SIGNER'S NAME. It carried
        # `signal_data.source == task.assignee`, so it fired only on the executor — and on an
        # internal node the role check admits exactly two parties, the executor and an id on
        # `authorized_validators`. The second walked past this branch, `is_public` is False so the
        # seam branch below never ran either, and NOTHING was left: probed 2026-09-08 with a paired
        # control — a child delivered "I wrote nothing at all" reaches DONE/PASS on a roster id's
        # signature with `verdict record: None, provenance: none, per_criterion: []`, while the same
        # delivery signed by its own executor is refused. The difference between a refusal and a
        # false close was one name on a roster.
        # This is the SAME rule the seam branch was corrected to on 2026-09-05 and which was never
        # mirrored here — "an id on a roster is a CLAIM about who is signing; the record is the
        # evidence that validation happened, and ⊥ is not a pass (§2.3) no matter whose name is on
        # it". Nothing legitimate is lost: `self_validation` on the DELIVER records itself
        # (`engine/loop.py::_keep_the_self_check`), and a validator that actually validates records
        # before it signs — both leave exactly the record this asks for.
        # …AND THE OBSERVATION OF THIS DELIVERY, one predicate for every door and surface: an appointed
        # observer's divergence stands (Inv-2), and at a seam — under a mode, at every node — a PASS stands
        # on an appointed observer's record, never on the executor's self-check or a passer-by's hand.
        _rec = graph.exec_verdict_record(signal_data.task_id) if task is not None else None
        if task is not None and (_ob := observation_blocker(graph, task, audit)):
            raise ValidationError(f"cannot PASS {signal_data.task_id}: {_ob['why']}. {_ob['opens_with'][:1].upper()}"
                                  f"{_ob['opens_with'][1:]}.")
        if (task is not None and signal_data.source
                and not graph.is_public(task)
                and not stands_as_pass(graph, audit, task, _rec)):
            _own = signal_data.source == task.assignee
            raise ValidationError(
                f"PASS on {signal_data.task_id} by "
                + (f"its own executor ({signal_data.source})" if _own
                   else f"'{signal_data.source}'")
                + f" carries no "
                f"self-check for this delivery. An INTERNAL node (same Del as its parent) self-verifies "
                f"rather than being validated independently (§10.3) — but a verdict with no check behind "
                f"it is ⊥, not a pass (§2.3). Say what you checked: `record_verdict({signal_data.task_id}, "
                f"\"PASS\", observed={{<criterion>: <what you ran and what it printed>}})` — that IS the "
                f"record this node is validated on — and then signal PASS. (From the next delivery on, "
                f"carrying `self_validation` in the DELIVER packet records it for you.)")
        # A SEAM NEEDS A VERDICT, NOT A SIGNER WHO IS NOT THE EXECUTOR. This condition used to read
        # `source == task.assignee` as well, so the requirement fired only against a SELF-stamp —
        # and §10.3 asks for something else: at a seam the result crosses into an independent scope,
        # so an independent verdict for THIS delivery must be on the record. Measured on the agent
        # door 2026-08-22, and then reproduced directly: a delegated child (Del=an executor) was
        # PASSed by its ISSUER with NO verdict recorded at all — accepted, DONE — and in the wave's
        # own run with a STALE FAIL standing on the node while its validator was still running. The
        # identity check passed vacuously because the signer was not the executor, and nothing else
        # was consulted. That is a false PASS reachable in one call from the ordinary door, in the
        # one product whose claim is that nothing completes by impression.
        #
        # The record can come from either place, which is what keeps a person free to validate by hand:
        # `validate_result` (the instrument) or `record_verdict` (a person saying what they observed
        # — refused without evidence). What is refused is a PASS standing on nothing.
        # An AUTHORIZED INSTRUMENT (§10.4: the issuer's role-V instrument — a registered
        # `llm-validator` or `unittest-checker`) opens this gate BY WHAT IT RECORDED, not by whose
        # name is on the signal. Until 2026-09-05 the rule read the other way — "its signature is the
        # verdict, not an impression about one, so it opens the gate without a second record" — and
        # the two paragraphs below are the two cuts that were taken out of that sentence before the
        # whole of it went: first the node's own executor, then the class itself.
        # …NOT WHEN THE INSTRUMENT IS THE NODE'S OWN EXECUTOR. Registration says what an id IS;
        # it cannot say that an id is independent OF ITSELF. `agent` is the standing identity every
        # door hands a caller who does not name themselves, so `register_agent("agent",
        # "llm-validator", …)` — an ordinary documented call — made the executing identity the one
        # whose signature closes the seam, for every node on the server, in every project (the
        # roster is one server-wide fact by design). A stranger on the CLI door then delivered a
        # leaf with "I claim it is done (nothing was written)" and signed it DONE, with no verdict
        # on the record at all; reproduced with a paired control an hour later — the same shape
        # signed by an id NOT on the roster was refused (wave 23, 2026-09-03). §10.3 is a statement
        # about the node's two parties, and no registration satisfies it by collapsing them.
        # …AND A SIGNATURE IS A VERDICT ONLY WHERE IT CANNOT BE TYPED. This branch used to step
        # aside for anyone on the validator roster — "an authorized instrument signing directly IS
        # the independent verdict, so it opens the gate without a second record" — and wave 23
        # narrowed that to exclude the node's own executor. The narrowing was right and the class
        # stayed open: `source` is CALLER-SUPPLIED on two of the three doors (`api/server.py`,
        # `driver.py` pass the body straight through; only MCP derives it from the transport), and
        # `register_agent` is an ordinary documented verb. So `register_agent("ghost-val",
        # "llm-validator")` followed by `signal <root> PASS ghost-val` closed a root that had
        # delivered "nothing was actually written" — DONE/PASS, `verdict record: None`, provenance
        # `none`, and q_V reporting 1.0 over a seam nothing had validated (audited and probed
        # 2026-09-05). An id on a roster is a CLAIM about who is signing; the record is the evidence
        # that validation happened, and ⊥ is not a pass (§2.3) no matter whose name is on it.
        #
        # Nothing legitimate is lost: every instrument path in this product RECORDS its verdict and
        # then signs it (`delegate._validate_with` → `record_exec_verdict` → `_signal`), so the
        # requirement it now meets is one it already met. What is refused is a signature standing
        # on nothing — which is what the whole gate is for.
        _on_roster = str(signal_data.source or "") in graph.authorized_validators
        if task is not None and graph.is_public(task):
            rec = graph.exec_verdict_record(signal_data.task_id)
            it, ro, rev = generation_of_task(task)
            # The question "does a CURRENT pass stand here" has one owner (`record_stands`); what stays
            # here is only the WHY, which this refusal has to say in the caller's own terms.
            current = stands_as_pass(graph, audit, task, rec)
            # Generation stamp = (iteration, reopens): a rework stales the verdict, and so does a
            # REOPEN (§12.14 anti-fake — the pre-reopen PASS must not re-open this gate from the past).
            stale = bool(rec) and not stamped_with(rec, (it, ro, rev))
            # …and so does a REVISION, which moves neither counter: §12.4 admits a re-ASSIGN from
            # VALIDATING and §12.10 voids the pending delivery with it, but a validator still running on
            # that delivery can land its verdict AFTER the revision — and it would carry the same
            # (iteration, reopens). The CONTRACT generation is the discriminator, so the record is
            # stamped with it too. Records written before the stamp existed read as generation 0; a
            # node that was never revised is also 0, so they agree exactly where they should.
            if not current:
                why = ("no independent verdict is recorded" if not rec
                       else "the recorded verdict is STALE — this delivery was reworked, reopened or "
                            "its contract was revised under it, re-validate"
                       if stale
                       else f"the recorded verdict is {rec.get('verdict')}, not PASS"
                       if rec.get("verdict") != Verdict.PASS
                       else "the recorded PASS is on a result that no longer stands — something this node is "
                            "built from (a part below it, a producer it consumes) was delivered again or "
                            "FAILed since it was recorded, re-validate")
                _self = bool(signal_data.source) and signal_data.source == task.assignee
                _who = (f"by its own executor ({signal_data.source})" if _self
                        else f"by {signal_data.source}" if signal_data.source else "")
                raise ValidationError(
                    f"PASS on {signal_data.task_id} {_who} needs an independent verdict for THIS "
                    f"delivery ({why}) — this node is a SEAM (a root, or its Del differs from its "
                    f"parent's), where the result crosses into another scope and is validated there "
                    f"(§10.3). Run `validate_result({signal_data.task_id}, workdir=…)`, which spawns "
                    f"an independent validator and records what it observed"
                    # …AND ONLY OFFER THE OTHER DOOR TO SOMEONE IT WOULD LET THROUGH. Told to sign,
                    # the executor was sent to `record_verdict` — which refuses them by the same
                    # rule, for the same reason, on the same node. Two refusals pointing at each
                    # other read as a product with no exit at all (agent door, 2026-09-02), when the
                    # exit is the instrument, or a party who is not the executor.
                    + (f". Your own observation is not that record here: verifier ≠ executor "
                       f"(§10.3), so the verdict has to come from the instrument or from someone "
                       f"else — `register_agent(<id>, \"llm-validator\", workdir=…)` gives this "
                       f"project a standing one, under an id that is NOT this node's executor."
                       # …AND SAY IT WHEN THE CALLER HAS ALREADY DONE THE THING THIS ADVICE MEANT.
                       # The sentence above, unqualified, is what a tester read before registering
                       # the standing agent id itself as the llm-validator — after which their own
                       # signature closed every seam they signed. The engine knows which of the two
                       # situations it is in; a refusal that does not say so reads as a bug, and
                       # they spent an hour attacking a mechanism that had never run (wave 23).
                       + (f" NOTE: '{signal_data.source}' IS on the validator roster, and that is "
                          f"why this looks inconsistent — but it is also this node's executor, and "
                          f"registration cannot make an id independent of itself. You cannot validate "
                          f"your own work under either hat; register a different id, or let the "
                          f"instrument validate this node."
                          if _on_roster else "")
                       if _self else
                       f", or record what YOU observed — `record_verdict({signal_data.task_id}, "
                       f"\"PASS\", observed={{<criterion>: <what you ran and what it printed>}})` "
                       f"— and then signal PASS."))

def _accept_rules(signal_data: SignalData, graph: Graph) -> None:
    """ACCEPT / REJECT_CHALLENGE: the plan gate that admits work (§11.5).

    One rule family per function: `validate_signal` had grown to seventy statements over
    four unrelated signals, and a reader looking for what refuses a PASS had to walk the
    DELIVER and RESOLVE_BLOCK rules to get there. Raises ValidationError, as before.
    """
    if signal_data.signal in (Signal.ACCEPT, Signal.REJECT_CHALLENGE):
        # How many subtasks a goal splits into is the executor's domain call, NOT set from outside
        # (§4.5: D is the decomposer's to choose). So the engine does NOT force a leaf to justify being
        # atomic — a taken leaf executes, and the ROOT seam validates the whole result against the
        # issuer's criteria regardless. What the engine DOES enforce is that a decomposition the
        # executor DID choose is causally sound before its parts run (below). (An earlier build gated
        # the leaf itself on an atomicity verdict; that imposed the subtask count from outside and, as a
        # side effect, deadlocked auto_decompose's own builder on its internal ACCEPTs. Removed.)
        # THE PINNED-PROCEDURE GATE IS NOT HERE ANY MORE. It used to refuse the executor's ACCEPT
        # on a contract whose criteria pinned no check — a refusal whose only lift was the ISSUER
        # writing the procedure, which the conformance clause (§12.16 (ii)) forbids: what lifts a
        # refusal must be producible by the refused party's own admissible moves. The requirement
        # itself stands and is A1's; it is enforced where the issuer acts, at ASSIGN admission
        # (`admission.refuse_a_contract_that_pins_nothing`), so the party who can satisfy it is the
        # party the engine refuses.
        # THE SYNTACTIC LEVEL IS NOT HERE EITHER, for the same reason: it gates the ADMISSION, where the decomposer can
        # lift it (`admission.admit`); refused on this ACCEPT, its lift was the
        # issuer's, never the executor's (§12.16 (ii); sync audit, corner 9).
        parent = graph.get_parent(signal_data.task_id)
        if parent is not None:

            # …and the same for the Pragmatic level — and here the engine goes BEYOND the canon's own
            # rule, deliberately, so the citation says so rather than borrowing authority. §11.5 makes
            # the SYNTACTIC level the admission condition ("a decomposition that fails the Syntactic
            # level is not admitted to execution") and files the Pragmatic level as "runtime detection
            # + learning" — it names no pre-execution gate there, and it could not: causal correctness
            # is formally uncheckable from inside (Ch. 20). What is gated here is therefore NOT the
            # checker's verdict but the canon's verify-vs-explore DECISION (§9.9) made explicit: the
            # check must have HAPPENED over this version of the plan, and its findings must have been
            # dispositioned. That is an engineering corner, declared in `formal/README.md`, not a canon
            # row. (An earlier comment cited "§13.4-bis" — an address that exists in no version of the
            # canon.) L0 sees only topology: a criterion
            # that HAS a covering child passes it even when that child's criteria cannot causally carry
            # it — the hole then surfaces after the code is written, as a refused delivery (the rework
            # that indicts the decomposition, q_D↓). The checker sees exactly this class BEFORE contact,
            # so the plan is checked once, up front, and the gap is fixed on the plan instead of paid for
            # in code. Measured on the live substrate (BCB/120, three L0-clean plans): every planted
            # entailment hole named, zero false gaps.
            # The gate is on the PROCESS, not on the checker's authority: run it, then either fix the
            # plan or record why the finding is wrong (`dispute_finding`). The verdict remains advisory
            # — contact keeps the last word (q_D). `GFSO_L2_GATE=0` opts out: that is the canon's own
            # EXPLORE branch (§9.9) — you buy the plan's verification with contact instead of with
            # c_check, consciously and by configuration, never by an agent skipping a step.
            # …REFUSED ONLY TO WHOEVER CAN LIFT IT (§12.16 (ii)): the review and the disposition of its findings are
            # the decomposer's moves, so the refusal binds a child his own executor takes (an internal node). A child
            # under another executor is not refused for its issuer's missing review — the system holds its own spawn
            # there (`Engine.execution_blocked_by`, read by the dispatcher), and a person taking it explores (§9.9).
            if (l2_gate_on() and str(signal_data.source) == str(parent.assignee)
                    and not (checked_by_contact(graph, graph.get_task(signal_data.task_id))
                             and not _l0_holes(graph, parent))):   # L2 only: the Syntactic level always runs (§9.9)
                gaps = _l2_undischarged(graph, parent)
                if gaps is None:
                    # …AND WHEN THE ADVICE IS THE THING THAT JUST FAILED, SAY THE OTHER WAY. "Run
                    # review_decomposition first" is right when no review has been run. It is a loop
                    # when one HAS been run and came back with nothing readable — which is what
                    # happens to every user with no checker available: probed 2026-09-05 with the
                    # Claude CLI off the PATH, the verb answered and the engine sent them straight
                    # back to it, with no exit named anywhere. The exit is the canon's own EXPLORE
                    # branch, and the comment above has known it all along; it just never reached
                    # the person reading the refusal.
                    _rec = graph._storage.get_critique(parent.id)
                    _ran_and_said_nothing = bool(_rec) and bool(parent.verified)
                    if _holes := _l0_holes(graph, parent):
                        # …and no review runs over a plan with a Level-0 hole: the repair is the first step (r14)
                        raise ValidationError(
                            f"cannot execute {signal_data.task_id}: its parent's plan has Level-0 holes since its "
                            f"admission (" + "; ".join(f"{h.check_name}: {h.details}" for h in _holes)
                            + f"), and no Level-2 review runs over it until they close — repair the split by its "
                              f"re-admission (`decompose`; `list_holes` names them), then "
                              f"review_decomposition({parent.id})")
                    raise ValidationError(
                        f"cannot execute {signal_data.task_id}: its parent's plan has no CURRENT "
                        f"Level-2 verdict — the causal check has not been run over this version of the "
                        f"decomposition (§9.1). Run review_decomposition({parent.id}) first (any edit "
                        f"to the plan stales an earlier review; an unreadable verdict is not a verdict)"
                        + (f". A review of THIS version was run and returned no readable verdict: run it "
                           f"again — a reply that could not be read may not recur. If every run comes back "
                           f"like this, give the server a checker "
                           f"(the Claude CLI on PATH, signed in), or take the canon's EXPLORE branch "
                           f"with `GFSO_L2_GATE=0`, where the plan's verification is bought with "
                           f"contact instead (§9.9) — a deployment decision, not a skipped step"
                           if _ran_and_said_nothing else ""))
                if gaps:
                    raise ValidationError(
                        f"cannot execute {signal_data.task_id}: its parent's Level-2 review named gaps "
                        f"that are still open — the mapped children's criteria do not carry these parent "
                        f"criteria (§9.1). TWO EXITS, and the first takes two steps: fix the plan "
                        f"(edit_criteria / map_criterion / add a child) AND re-run "
                        f"review_decomposition({parent.id}) — a fix RETIRES this verdict rather than "
                        f"discharging it, so until the fresh review speaks there is no current "
                        f"verdict and this stays shut; or record why the finding is wrong "
                        f"(dispute_finding({parent.id}, <criterion>, <why>)), which discharges it "
                        f"where it stands. Open: " + "; ".join(gaps)
                        + f" — read the reasons with get_review({parent.id})")

#: The signals that carry the issuer's answer to a block's records (§15.5: "RESOLVE_BLOCK's action or a re-ASSIGN's or
#: CANCEL's reason"), and the states a re-ASSIGN or CANCEL ends a block from — BLOCKED, or ESCALATED its lapse entered.
_ANSWERS_A_BLOCK = (Signal.RESOLVE_BLOCK, Signal.ASSIGN, Signal.CANCEL)
_ENDS_A_BLOCK = (State.BLOCKED, State.ESCALATED)


def is_auto_root(graph: Graph, task) -> bool:
    """Is this the root of a project the system runs in AUTO — where its criteria are the user's goal, and every move
    on it the system's on the user's behalf? One predicate for every rule that keeps that goal from being argued away:
    the machine issuer's dispute of a review finding, its answer to a challenge, a ruling retiring a finding."""
    return task is not None and task.parent_id is None and mode_kind(graph) == Mode.AUTO


def ruling_refusal(signal_data: SignalData, graph: Graph, audit=None) -> Optional[str]:
    """Why the ruling this signal carries (`retire_findings`) is refused, or None — the signal refused whole, so the
    node stays CHALLENGED with both truthful answers open: ACCEPT_CHALLENGE without a ruling, or REJECT_CHALLENGE
    (Inv-8). A ruling rides an ACCEPT_CHALLENGE only, and names findings standing on the node that the CHALLENGE named
    by id (`findings.ruling_defect`). Who may make it is not this gate's to tell: at an AUTO root the user and the
    system both sign as the root's issuer, and only the system is barred — it makes no move on such a dispute
    (`Engine.users_dispute`), while the user's own ruling there is his to make."""
    sd = signal_data
    if not sd.retire_findings:
        return None
    if sd.signal != Signal.ACCEPT_CHALLENGE:
        return f"{sd.signal.name} carries `retire_findings` — a ruling on findings rides an ACCEPT_CHALLENGE only"
    return ruling_defect(graph._storage, audit.get_entries(sd.task_id) if audit is not None else [],
                         graph.get_task(sd.task_id), sd.retire_findings)


def _adjudication_rules(signal_data: SignalData, graph: Graph, state) -> None:
    """The answer to a block's records, on any signal that carries one. Carried where no block ends it answered nothing
    and the door reported success (critic 5); a source naming the node itself or one of its ancestors names no
    prerequisite — a node cannot wait on its own result or its parent's, whose verdict waits on it (§2.4, §2.7) —
    and was adopted as a "discovery" no BLOCK named."""
    sd = signal_data
    if sd.signal not in _ANSWERS_A_BLOCK or not (sd.blockers or sd.external):
        return
    if sd.signal != Signal.RESOLVE_BLOCK and state not in _ENDS_A_BLOCK:
        raise ValidationError(
            f"{sd.signal.name} on {sd.task_id} carries an answer to a block (`blocker_task_ids` / `external`), but the "
            f"node is {state.name if state else 'unknown'}: a block's records are answered as the block ends — out of "
            f"BLOCKED, or out of ESCALATED where its lapse handed you the decision (§15.5, §12.5). Send it without them.")
    ancestors, t = set(), graph.get_task(sd.task_id)
    while t is not None and t.parent_id:
        ancestors.add(str(t.parent_id))
        t = graph.get_task(t.parent_id)
    if bad := [str(b) for b in sd.blockers if graph.get_task(b) is None or str(b) == str(sd.task_id)
               or str(b) in ancestors]:
        raise ValidationError(
            f"{sd.signal.name} on {sd.task_id} names {bad} as its prerequisites: not a node, the node itself or one of "
            f"its ancestors — none can be a prerequisite of {sd.task_id} (its parent's verdict waits on it). Name the "
            f"nodes whose result it really needs, or answer `external=true` if none was.")


def _resolve_block_rules(signal_data: SignalData, graph: Graph) -> None:
    """RESOLVE_BLOCK: a block clears when its blockers passed (§2 dep order).

    One rule family per function: `validate_signal` had grown to seventy statements over
    four unrelated signals, and a reader looking for what refuses a PASS had to walk the
    DELIVER and RESOLVE_BLOCK rules to get there. Raises ValidationError, as before.
    """
    if signal_data.signal == Signal.RESOLVE_BLOCK:
        # A BLOCK ON A NODE THAT HAS NOT DELIVERED IS NOT CLEARED BY SAYING SO. RESOLVE_BLOCK returns
        # the node to EXECUTING, and the dispatcher then correctly refuses to spawn against an input
        # that does not exist — so the node sat in EXECUTING with nothing running for eleven minutes,
        # and the frontier filed it under `waiting` while its state said otherwise (measured on the
        # human door 2026-08-22). "EXECUTING" has to mean someone can execute.
        # …unless this resolve RETRACTS the dependency. §15.5 lets RESOLVE_BLOCK adjudicate what the
        # BLOCK claimed: `external=True` says the issuer worked around the blocker, and a corrected
        # `blocker_task_ids` re-attributes it. Both are assessments about whether the edge holds at
        # all; what is refused here is CONFIRMING an edge and resuming anyway.
        _corrected = signal_data.blocker_task_ids or (
            (signal_data.blocker_task_id,) if signal_data.blocker_task_id else ())
        _claimed = ({str(b) for b in _corrected} if _corrected else
                    {str(e.from_id) for e in graph.dep_edges()
                     if str(e.to_id) == str(signal_data.task_id)})
        # A blocker that is not a node at all (a phantom the executor named) is not an unpassed
        # producer — that case is what the retracting form is for, and reading it as "unpassed"
        # made the auto-resolve refuse its own signal in a loop.
        _open = sorted({p for p in _claimed
                        if (_t := graph.get_task(TaskId(p))) is not None and not settled_positive(_t)})
        if _open and not signal_data.external:
            # …AND THE LIFT NAMED IS THE REFUSED PARTY'S OWN. RESOLVE_BLOCK is an ISSUER signal
            # (§11.2), so the party refused here is the issuer, and §12.16's conformance clause (ii)
            # asks that what lifts a refusal be producible by HIS admissible moves — "never only by
            # the counterparty". This named exactly one route, the producer's delivery and its
            # verdict: another executor's act and another issuer's verdict, which he cannot make.
            # The refusal itself conforms and stays — RESOLVE_BLOCK is the PURE-UNBLOCK edge (§12.4)
            # and means the blocker cleared; admitting it here would make the signal a false report,
            # and §12.16(ii) protects honesty, not passage. What did not conform is the sentence: it
            # sent the owner of the state to wait on somebody else while three of his own moves and
            # the state's own bound were open. Each is named now, and each stays a true report only
            # where it is true — the retraction and the re-attribution are adjudications of what the
            # BLOCK claimed (§15.5), not ways around it.
            # …AND ONLY LIFTS THAT ACTUALLY LIFT ARE OFFERED. A first version of this message named
            # `external=true` and a bare re-ASSIGN without qualification; an outside review measured
            # both inert (2026-09-23): `_adjudicate_dep` retracts only PROVISIONAL edges, so on a
            # PLANNED one the node reaches EXECUTING and stalls identically, and `_apply_spec`
            # never touches dep edges, so a revision leaves `_deps_ready` counting the same edge.
            # `remove_dependency` is the verb that moves it, and a refusal that names a lift which
            # does not lift is the same defect as one that names the counterparty's.
            # The wait is deliberately NOT listed among the moves: §12.16(ii) excludes the clock as a
            # lift, and §12.9 grants discharge-by-abstention to OFFERED only.
            raise ValidationError(
                f"cannot RESOLVE_BLOCK {signal_data.task_id}: it waits on {', '.join(_open)}, and "
                f"none of those has passed — the block has not cleared, and returning the node to "
                f"EXECUTING would leave it there with nothing able to run (§2 dep order). "
                f"RESOLVE_BLOCK is the pure-unblock edge (§12.4): it reports that the blocker is "
                f"gone. Your own moves here, if one of them is true: send it with `external=true` "
                f"if you worked around the blocker, or with a corrected `blocker_task_ids` if the "
                f"edge was misattributed (both adjudicate what the BLOCK claimed, §15.5 — and both "
                f"retract only a PROVISIONAL edge, so neither moves one the plan declared nor "
                f"one an earlier RESOLVE_BLOCK already confirmed; those go by "
                f"`remove_dependency`); if the contract no longer needs that input at all, "
                f"`remove_dependency` and then revise the node; or CANCEL it. "
                f"\nIf none of those is true, the node is genuinely blocked and waiting is the "
                f"honest state — not a move, but the correct absence of one: BLOCKED is bounded "
                f"and its expiry hands you the decision at ESCALATED (§12.5).")

def _deliver_rules(signal_data: SignalData, graph: Graph, audit) -> None:
    """DELIVER: what a delivery must carry to be validated at all.

    One rule family per function: `validate_signal` had grown to seventy statements over
    four unrelated signals, and a reader looking for what refuses a PASS had to walk the
    DELIVER and RESOLVE_BLOCK rules to get there. Raises ValidationError, as before.
    """
    if signal_data.signal == Signal.DELIVER:
        task = graph.get_task(signal_data.task_id)
        if (_owed := split_owed(graph, task)) is not None:
            raise ValidationError(f"cannot DELIVER {signal_data.task_id} as a leaf: {_owed['why']}. "
                                  f"{_owed['opens_with'][:1].upper()}{_owed['opens_with'][1:]}.")
        # A DELIVERY WITH NOTHING IN IT IS NOT A DELIVERY. `result` is the validator's input — "paths
        # plus how each criterion is met" — and the empty string was admitted straight to VALIDATING,
        # where `get_verdict` then showed `delivered: null` on a node that went on to close. Two doors
        # named the asymmetry in the same words (wave 25, 2026-09-05): the evidence floor guards
        # VERDICTS and not the thing they are about, so `record_verdict observed="ok"` is refused
        # while a delivery of "" is not. This is the same floor, at the same grade: what is refused
        # is nothing written down at all. It cannot refuse a false sentence, and does not pretend to.
        if not str(signal_data.result or "").strip():
            raise ValidationError(
                f"DELIVER on {signal_data.task_id} carries no `result`: it is what the validator "
                f"reads and what the record keeps — the paths you produced and, per criterion, the "
                f"check you ran and what it printed. A delivery with nothing in it leaves the validator "
                f"to guess and the log with nothing about the work. Say what you did.")
        # The trigger is "this node has a decomposition", not "it still has mappings": deleting the
        # refuted criterion also deletes the mapping that pointed at it, so a mapping-keyed trigger
        # would let exactly the false close through. A leaf is out of scope by the same reading —
        # its contract belongs to the issuer above, whose CHECK-1 surfaces any hole a rewrite leaves.
        if (refusal := redelivery_refusal(graph, task, audit)) is not None:
            raise ValidationError(refusal)


def project_mode(graph: Graph) -> Optional[dict]:
    """The project's mode as set — {mode, boundary, by} — or None."""
    raw = graph._storage.get_setting("mode")
    return json.loads(raw) if raw else None


def mode_kind(graph: Graph) -> Optional[Mode]:
    """The project's mode, typed — None with no mode set. A rule branching on the mode reads this, never the stored
    string (ortho audit, D-F9: raw `"semi"` / `"auto"` compares in eight places)."""
    m = project_mode(graph)
    return Mode(m["mode"]) if m else None


def party_kind(graph: Graph, party: str, registered=None) -> str:
    """WHO makes a party's issuer moves — the one owner of a question four places answered four ways (D-F9):
    `holder` — the user's standing agent under SOLO/SEMI, whose moves the system never makes;
    `machine` — the standing agent under AUTO (the customer, who does not intervene), or a registered participant;
    `legacy` — the standing agent with no mode set: as before modes, the system answers its disputes and resolves its
    mechanical blocks, the instrument signs, and its plan moves stay its own;
    `person` — anyone else, unregistered: the system is passive.
    The standing agent is read first: a role registered under the user's own id does not make it a machine.
    `registered` is the registry consulted (the dispatcher's own; the engine's published roster by default)."""
    if str(party) == str(_config_agent_id()):
        kind = mode_kind(graph)
        return "legacy" if kind is None else "machine" if kind == Mode.AUTO else "holder"
    return "machine" if (registered or {}).get(str(party)) is not None else "person"


def hands_of(graph: Graph, party) -> Optional[str]:
    """The registered executor whose session performs the nodes `party` holds, or None — the party performs them
    itself. Only the standing agent under a mode that DISPATCHES has hands: it consents and stays Del, every signal
    its own (§10.1), and the work runs in a clean session the system starts after its ACCEPT — no seam inside one
    agent (§10.3), so how it performs is its own. In its own chat nothing structural keeps the work inside the
    contract (§16.9 exception 11); a session the system starts only after consent does."""
    m = project_mode(graph)
    return (m.get("hands") if m and m.get("perform") == "dispatch" and str(party) == str(_config_agent_id())
            else None)


def depth_of(graph: Graph, task_id: TaskId) -> int:
    """How many edges from the root down to this node (the root is 0)."""
    d, t = 0, graph.get_task(task_id)
    while t is not None and t.parent_id is not None:
        d, t = d + 1, graph.get_task(t.parent_id)
    return d


def holder_boundary(graph: Graph) -> Optional[float]:
    """b: the user-agent holds depths < b, the system holds b and below; None with no mode set.

    SEMI's default is the middle of the plan's actual depth, (D+1)/2 — equidistant from SOLO
    (b = D+1) and AUTO (b = 0), so it leans neither way. `auto_decompose` issues root + children
    (D = 1), so the default there is exactly 1: the agent holds the root, the system every child."""
    m = project_mode(graph)
    if m is None:
        return None
    if mode_kind(graph) == Mode.SOLO:
        return float("inf")
    if mode_kind(graph) == Mode.AUTO:
        return 0
    if m.get("boundary"):
        return m["boundary"]
    deepest = max((depth_of(graph, t.id) for t in graph._storage.get_all_tasks()), default=1)
    return max(1, (max(deepest, 1) + 1) / 2)


def _consented_before_the_mode(audit, task, mode: dict) -> bool:
    """Was the node's work first consented to before the mode was chosen? Its FIRST ACCEPT, not its last: a
    revision re-offers the same work, and reading the latest consent moved the refusal one state on instead of
    lifting it (critic round 16). Read by position in the log, not by clock — the mode record and the
    engine's clock are different clocks."""
    at = mode.get("log_at")
    if audit is None:
        return False
    if at is None:   # a mode record older than `log_at`: its consents are taken as given before it (critic round 14)
        return True
    first = next((i for i, e in enumerate(audit.get_entries()) if e.task_id == task.id
                  and e.signal == Signal.ACCEPT and not e.rejected), None)
    return first is not None and first < at


def held_plan_node_refusal(graph: Graph, task, signal: Signal = Signal.ACCEPT, audit=None) -> Optional[str]:
    """Why the user-agent may not take or hand in `task` in SEMI, or None.

    SEMI is a boundary in the plan's depth: the user-agent holds the plan above it and the system executes
    below. Its holder doing the work is SOLO under another name (measured three times: the semi holder
    authored a childless root and wrote everything itself). One rule on the NODE, at the engine every ACCEPT
    and DELIVER reaches, and asked by every surface that advises a move (`Engine.held_node_refusal`):

    - A HELD NODE WITH A SPLIT is delivered as the aggregate of what the system did below it, so its delivery
      waits for exactly what its PASS waits for: the AND over its children (Thm 1) and a plan that passes the
      Syntactic level (§9.5) — no criterion without a child to carry it. Asking only whether a split existed
      let the holder deliver its own work over a child nobody had started and cancel the child (round 15);
      asking only the children let it deliver work for a criterion no child carried and split afterwards
      (round 17). The holder keeps its moves on the children it issued (revise, reassign, cancel, a re-split).
    - A HELD NODE WITH NO SPLIT is neither taken nor handed in: the lift is the holder's own split, admissible
      from the offer (§11.5). HELD means by the mode's depth, not merely by name (critic rounds 7, 8).
    - A NODE BELOW THE BOUNDARY that still names the user-agent — a plan built before SEMI, or a boundary the
      user moved up, keeps its Del (Inv-1) — is handed over, not worked: the holder executed every leaf with no
      refusal and advice pointing it at the work (round 18). The lift is its own issuer move, `reassign`.
    - Work whose FIRST consent predates the mode is kept wherever the split is missing or the node lies below
      — its only lift would discard work already done (§12.16 (ii); rounds 8, 13, 16); never where a split
      stands unfinished (round 16).

    WHAT THIS RULE CANNOT SEE, named. Who wrote the files: a holder that writes the work itself under
    children that pass is not excluded by any structural rule — the root is still validated independently at
    its seam, so it is not a false "done", and a run's record reads the holder's own edits. And a consent
    given under an earlier SEMI when the user switched to another mode and back: the mode in between gave
    that node to whoever held it then."""
    m = project_mode(graph) if task is not None else None
    if mode_kind(graph) != Mode.SEMI or str(task.assignee) != str(_config_agent_id()):
        return None
    if depth_of(graph, task.id) >= holder_boundary(graph):
        if _consented_before_the_mode(audit, task, m):
            return None
        return (f"this project runs in semi (set by {m.get('by')}): '{task.id}' lies below the boundary, where "
                f"the system executes, yet it names you — hand it over (`reassign` it to one of this project's "
                f"registered executors).")
    if kids := graph.get_active_children(task.id):
        if signal != Signal.DELIVER:
            return None
        unpassed = [str(c.id) for c in kids if not settled_positive(c)]
        holes = [f"{h.check_name}: {h.details}" for h in _l0_holes(graph, task)]
        if not (unpassed or holes):
            return None
        return (f"this project runs in semi (set by {m.get('by')}): '{task.id}' is handed in as the aggregate "
                f"of what the system executes below it, and "
                + (f"its children {', '.join(unpassed)} have not passed — drive them first (you are their "
                   f"issuer: answer what they ask)" if unpassed else
                   f"its split does not carry its contract ({'; '.join(holes)}) — add or map the child that "
                   f"carries it")
                + "; if the plan is wrong, re-split it.")
    if _consented_before_the_mode(audit, task, m):
        return None
    return (f"this project runs in semi (set by {m.get('by')}): you hold the plan and the system "
            f"executes below it, and '{task.id}' has no split — split it first (`auto_decompose` on it, "
            f"with no `executor`: the mode assigns the children); if this is one person's work, that is "
            f"the SOLO mode, and the mode is the user's to change — ask them.")


def redelivery_refusal(graph: Graph, task, audit) -> Optional[str]:
    """Why a re-DELIVER of `task` would be refused right now, or None — asked by the RULE and by
    the FRONTIER, from one owner.

    The trigger is "this node has a decomposition", not "it still has mappings": deleting the
    refuted criterion also deletes the mapping that pointed at it, so a mapping-keyed trigger
    would let exactly the false close through. A leaf is out of scope by the same reading — its
    contract belongs to the issuer above, whose CHECK-1 surfaces any hole a rewrite leaves.

    ASKED BY THE FRONTIER TOO, because the two were saying opposite things about the same node. On a
    live run (2026-09-06, `http2_protocol`) the engine refused the re-delivery — the failed criteria
    were covered by children untouched since that FAIL, so contact refuted the DECOMPOSITION — while
    the frontier, in the same second, told the executor "AGGREGATE: all its children PASSED —
    integrate them … DELIVER". The executor obeyed the directive, was refused twice, and the run
    ended there. Advice the engine forbids is worse than no advice.
    """
    if task is None or task.state not in (State.REWORKING, State.EXECUTING):
        return None
    if not graph.get_active_children(task.id):
        return None
    rec = graph.exec_verdict_record(task.id)
    # THE STANDING FAIL IS THE ONE THIS NODE HAS NOT ANSWERED — not "the one exactly one rework
    # round back". The arithmetic `iteration - 1` was a way of saying "the last round", and since
    # v4.1 every new packet version resets the rework budget (Φ3, §12.15), so a repair made through
    # the canonical route — `edit_criteria`, which IS a revision — put the counter back to zero and
    # the standing refutation stopped matching: the gate that refuses a re-delivery over a criterion
    # the repair REMOVED went quiet exactly where the repair happens.
    if not (rec and rec.get("verdict") == Verdict.FAIL and rec.get("reopens", 0) == task.reopens):
        return None
    return _refuted_coverage_refusal(graph, task, rec, audit)


def no_live_deadline(graph: Graph, task, parent_id=None) -> Optional[str]:
    """Why a version typing no deadline would enter OFFERED without a live one, or None (§2.5, §12.16): it keeps a spent
    one, or its parent leaves no time inside its own for a default. With the default switched off
    (`GFSO_DEFAULT_DEADLINE_S=0`) a packet without one is the installation's choice; only a spent kept one is refused."""
    dl, _ = version_deadline(graph, None, task, parent_id)
    if dl is not None and dl > datetime.now() or dl is None and not default_deadline_s():
        return None
    return ((f"it would keep {dl:%Y-%m-%d %H:%M}, already passed" if dl is not None else
             "its parent leaves no time inside its own for a default")
            + " — a task is given out with a live deadline, and under a parent whose deadline has passed the issuer "
              "types one (§2.5, §12.16); give one")


def issuing_condition(parent, task_id) -> Optional[str]:
    """Why `task_id` cannot be issued under `parent`, or None. A child's first ASSIGN — and its REOPEN, a re-issue (§12.14)
    — is admissible only while the parent is live and not in CANCELLING (§12.7): "a child issued after the cascade fired
    would escape it, and under a settled parent nothing is owed". Read by the signal gate, so no door goes around it —
    a REOPEN through `revise` did (sync audit, B-F3)."""
    if parent is None:
        return None
    if parent.state == State.IDLE:
        return (f"'{parent.id}' has not been issued yet, so it cannot issue '{task_id}': a child's contract is with its "
                f"issuer, and the issuer of a child is the executor of its parent (§10.1). ASSIGN the parent first.")
    if parent.state in TERMINAL_STATES or parent.state == State.CANCELLING:
        return (f"'{parent.id}' is {parent.state.name}, so '{task_id}' cannot be issued under it (§12.7): a child issued "
                f"while the parent settles escapes the cascade that settles the subtree, and under a parent already "
                f"settled nothing is owed. Reopen the parent (`reopen`) if the goal is live again, or issue this work "
                f"under a live node.")
    return None


def dep_cycle_closed(graph: Graph, task_id, criteria) -> Optional[str]:
    """Why a contract for `task_id` with these criteria would close a Dep cycle, or None. Of the guards a revision
    re-runs only CHECK-2's Dep clause refuses (§12.10): the node's declared edges are its criteria's `depends_on`, the rest
    of E_Dep stands. One owner — the signal gate (every ASSIGN and ACCEPT_CHALLENGE) and `add_dependency` read it; a
    revision closing a cycle used to be admitted wherever it did not come through `add_dependency` (sync audit, A-F4)."""
    tid = str(task_id)
    rest = [(str(e.from_id), str(e.to_id)) for e in graph.dep_edges(adopted=True) if e.discovered or str(e.to_id) != tid]
    new = [(str(c.depends_on), tid) for c in criteria if c.depends_on is not None]
    if not new:
        return None
    # THIS contract closes a cycle iff one of its producers is reached from the node itself — asked of the node, not of
    # the whole graph: a cycle standing elsewhere is not this act's, and read globally it refused every later
    # `depends_on` anywhere with a refusal its sender could not lift (critic over session 475ba784)
    below = {}
    for a, b in rest:
        below.setdefault(a, []).append(b)
    path, frontier, producers = {tid: [tid]}, [tid], {a for a, _ in new}
    while frontier and not producers & path.keys():
        x = frontier.pop(0)
        for y in below.get(x, ()):
            if y not in path:
                path[y] = path[x] + [y]
                frontier.append(y)
    hit = next(iter(producers & path.keys()), None)
    if hit is None:
        return None
    return (f"{tid} would depend on {hit or ', '.join(sorted(producers))}, which already depends on it "
            f"({' → '.join(path[hit]) if hit else 'through the seams already declared'}) — a Dep cycle (CHECK-2, §12.10). "
            f"A Dep says the CONSUMER waits for its PRODUCER: if the direction is backwards, `remove_dependency` the other one first; if "
            f"both really need each other, the split is wrong and the two belong in one node")


def child_not_admitted(graph: Graph, parent_id, task_id) -> Optional[str]:
    """Why an ASSIGN creating `task_id` under `parent_id` is no admission's, or None. The Syntactic level gates the
    admission (§11.5); a child created by a bare ASSIGN entered a split no battery had read, and nothing later held
    it (critic r10 — on main the battery sat on its ACCEPT)."""
    log_ = json.loads(graph._storage.get_critique(admission_key(parent_id)) or "[]")
    if log_ and str(task_id) in log_[-1].get("issued", ()):
        return None
    return (f"{task_id} would enter {parent_id}'s split by a bare ASSIGN, and a child enters a split only by its "
            f"admission, which reads the split as it will stand (§11.5) — `decompose` the split whole, new or "
            f"re-admitted, or `create_task(parent_id=…, covers=[…])` to add one child to a split that already "
            f"stands")


def refuse_a_version_with_no_live_deadline(signal_data: SignalData, graph: Graph) -> Optional[str]:
    """An ASSIGN or ACCEPT_CHALLENGE typing no deadline, refused where the version could enter with no live one
    (critic r7 A3, sync audit B-F5)."""
    if signal_data.signal not in (Signal.ASSIGN, Signal.ACCEPT_CHALLENGE) or signal_data.deadline is not None:
        return None
    task = graph.get_task(signal_data.task_id)
    why = no_live_deadline(graph, task, None if task is not None else signal_data.parent_id)
    return why and f"{signal_data.signal.name} on {signal_data.task_id} types no deadline: {why}"


def packet_refusal(signal_data: SignalData, graph: Graph, state) -> Optional[str]:
    """What a packet an ASSIGN or ACCEPT_CHALLENGE installs must meet, said where it does not, or None — the rules that
    sit where the packet lands, so no door goes around them: a live deadline (§2.5: a spent one entered OFFERED only to
    lapse on the next tick, B-F2; none at all, §12.16), the issuing condition on a first ASSIGN and on a REOPEN (§12.7,
    §12.14), and no Dep cycle closed by its criteria (§12.10)."""
    if signal_data.signal not in (Signal.ASSIGN, Signal.ACCEPT_CHALLENGE):
        return None
    if signal_data.deadline is not None and signal_data.deadline <= datetime.now():
        return (f"{signal_data.signal.name} on {signal_data.task_id} carries a deadline already passed "
                f"({signal_data.deadline:%Y-%m-%d %H:%M}) — a task is given out with a live deadline, one still ahead "
                f"(§2.5); give one that is")
    if why := refuse_a_version_with_no_live_deadline(signal_data, graph):
        return why
    if signal_data.signal == Signal.ASSIGN and (state is None or state == State.IDLE or state in TERMINAL_STATES):
        t = graph.get_task(signal_data.task_id)
        pid = t.parent_id if t is not None else signal_data.parent_id
        if why := issuing_condition(graph.get_task(pid) if pid else None, signal_data.task_id):
            return why
        if t is None and pid and (why := child_not_admitted(graph, pid, signal_data.task_id)):
            return why
    # the dispute's answer installs `new_spec` exactly as ASSIGN installs `spec` (§12.16)
    packet = signal_data.spec or signal_data.new_spec
    return dep_cycle_closed(graph, signal_data.task_id, packet.criteria) if packet else None


def signer_refusal(graph: Graph, task_id, signal: Signal, source) -> Optional[str]:
    """Why `source` may not sign `signal` on this node, or None — the one owner of who signs what: the machine reads it
    and so does every surface that lists a caller's moves (`Engine.available_actions` kept a hand copy, `_roles_of`,
    that came apart from this at the root-issuer corner, ortho audit D-F1).

    System signals carry NO sender (§12.2: the timeout "is not a P2P signal (no agent sends it) but a system mechanism
    enforcing finiteness"), so a SOURCED one is an agent impersonating the clock. An issuer signal is the issuer's —
    the parent's Del, or for a root the goal's issuer (`Graph.issuer_of`) — save that a registered llm-validator, the
    issuer's AUTHORIZED INSTRUMENT for role V, signs PASS/FAIL on any node (Thm 11 still records the true actor)."""
    role = required_role(signal)
    if role == Role.SYSTEM:
        return (f"{signal.name} is a SYSTEM trigger, not a P2P signal (§12.2): no agent sends it — it is emitted by the "
                f"deadline monitor to enforce finiteness (Inv-5). '{source}' cannot sign it") if source else None
    task = graph.get_task(task_id)
    if task is None:
        return None
    if source is None:
        return f"non-system signal {signal.name} requires source (sender agent_id)"
    if role == Role.ISSUER:
        issuer = graph.issuer_of(task_id)
        if issuer and source != issuer and not (signal in (Signal.PASS, Signal.FAIL)
                                                and str(source) in graph.authorized_validators):
            return f"{source} is not issuer for {task_id} (issuer={issuer})"
    elif role == Role.EXECUTOR and task.assignee and source != task.assignee:
        return f"{source} is not executor for {task_id} (executor={task.assignee})"
    return None


def validate_signal(signal_data: SignalData, graph: Graph, audit=None) -> None:
    """Check signal validity — the state, the rules above the FSM, the signer — raising ValidationError with the first
    that refuses. THE STATE ANSWERS FIRST, because it is the reason the caller can act on: the role check ran before it,
    so a signal the state did not admit at all came back "X is not issuer for Y" — the caller fixed their identity, sent
    it again, and only then learnt the state was wrong (human door, 2026-08-22)."""
    _st = graph.get_state(signal_data.task_id)
    if _st is not None and signal_data.signal not in available_signals(_st):
        raise ValidationError(not_admissible_here(signal_data.signal, _st))
    if why := rule_refusal(signal_data, graph, audit) or signer_refusal(graph, signal_data.task_id, signal_data.signal,
                                                                         signal_data.source):
        raise ValidationError(why)


def rule_refusal(signal_data: SignalData, graph: Graph, audit=None) -> Optional[str]:
    """Why a rule above the FSM refuses this signal with this payload, or None. One owner: the machine raises it
    (`validate_signal`) and every surface that lists a move asks it (`Engine.refusal_for`) — a surface that wrote the
    rules again offered moves the machine refused, five times over (ortho audit, D-F1)."""
    try:
        _rules(signal_data, graph, audit)
    except ValidationError as ex:
        return str(ex)
    return None


def _rules(signal_data: SignalData, graph: Graph, audit=None) -> None:
    """The rule families in turn, each raising ValidationError (one family per function, `_pass_rules` and kin)."""
    _st = graph.get_state(signal_data.task_id)
    if signal_data.signal in (Signal.ACCEPT, Signal.DELIVER) and             (why := held_plan_node_refusal(graph, graph.get_task(signal_data.task_id), signal_data.signal, audit)):
        raise ValidationError(why)

    if why := packet_refusal(signal_data, graph, _st):
        raise ValidationError(why)
    _adjudication_rules(signal_data, graph, _st)
    if why := ruling_refusal(signal_data, graph, audit):
        raise ValidationError(why)

    # Invariant 3: FAIL must specify failed criteria
    if not validate_fail_has_criteria(signal_data):
        raise ValidationError(
            f"FAIL signal for {signal_data.task_id} must specify failed_criteria"
        )
    # …AND THEY MUST BE THIS NODE'S. The rule above counted them; nothing asked what they were, so a
    # FAIL naming "the tests" or a typo was admitted, moved the node to REWORKING and spent one of
    # its bounded iterations (§12.4) against an obligation that does not exist — leaving the
    # executor a list it cannot act on. The same rule already binds the machine validator's report
    # one file over (`verdict_report_defects`), which made it a rule enforced for the instrument and
    # advisory for the person (audited 2026-09-05, F5).
    _t = graph.get_task(signal_data.task_id)
    if signal_data.signal == Signal.FAIL and _t is not None:
        _names = [c.name for c in _t.spec.criteria]
        if _foreign := fail_names_this_contract(signal_data.failed_criteria, _names):
            raise ValidationError(
                f"FAIL on {signal_data.task_id} names {_foreign} — not criteria of this node, whose "
                f"contract is exactly [{', '.join(_names)}]. A FAIL says WHICH obligation was not "
                f"met (Inv-3), and a name outside the contract names none: the executor would be "
                f"sent to rework with nothing to fix. If the contract itself is wrong, that is a "
                f"revision, not a verdict.")

    # Contact-refuted coverage gate (§15.4 q_D made STRUCTURAL). A parent FAIL whose criteria are
    # COVERED by PASSed children is the q_D event: contact refuted the mapping's claimed entailment
    # (child passed its own criteria ∧ the parent criterion stayed red) — the DECOMPOSITION is
    # indicted, not the aggregate artifact. Re-DELIVERing the same aggregate over an UNTOUCHED
    # subtree would launder the refuted decomposition through a fresh validation, mutating the
    # artifact while the responsible children sit frozen in DONE (observed live: BCB/93 run 9) —
    # so the engine REFUSES it, and `_refuted_coverage_refusal` says with what repair (an FM-1
    # defect is repaired by revising THIS node under Inv-1, not by reworking a child that met its
    # own criteria) and which same-shaped move is a false close instead.
    # The check follows the node across the repair route, not just the rework state: a revision
    # lands the node in OFFERED→EXECUTING, so gating REWORKING alone would let the criterion-lowering
    # route through unexamined. Attribution source = the recorded verdict of the refuting FAIL
    # (generation-stamped); a FAIL signaled without a recorded verdict is a named boundary:
    # unattributable, not gated. `state_entered_at` is not persisted — after a restart both sides
    # re-arm to load time, which reads as "untouched" (conservative: the gate may ask for one
    # explicit child touch after a restart, never the reverse).
    _deliver_rules(signal_data, graph, audit)

    # §11.5: "a decomposition that has not passed Level 0 is NOT admitted to execution." Enforced, not
    # advised: the FIRST execution step of a child (ACCEPT: OFFERED→EXECUTING) is REFUSED while the
    # PARENT's decomposition has an unresolved L0 hole (uncovered criterion, orphan child, cycle,
    # empty/malformed ACCEPTED_RISKS, …). This moves "verify the plan before you execute it" from the prompt
    # into the system: the agent physically cannot start working a flawed plan, so the plan is completed
    # and checked ONCE, up front — no discover-after-delivery, no edit_accepted_risks-during-rework churn, and a
    # verified plan means fewer contact-refutations (higher q_D). A root (no parent) is atomic to the
    # system — nothing to verify — and is unaffected; so is an already-clean parent.
    # EVERY DOOR INTO EXECUTION, not just the front one. The gate asked its question on ACCEPT
    # alone — and CHALLENGE → REJECT_CHALLENGE lands the node in EXECUTING too (§12.4), so a child
    # whose parent's plan had no current Level-2 verdict got there by disputing its contract and
    # being told no. Found by walking the protocol as a person would, 2026-08-21: the gate refused
    # the ACCEPT and the node was already executing. (Since E2 a REJECT_CHALLENGE lands in EXECUTING
    # only after an ACCEPT of the current version, and in OFFERED otherwise; the gate is kept on it
    # either way — this layer reads the graph, not the log that decides which, and the stricter side
    # costs the issuer at most the plan repair the next ACCEPT would demand anyway.)
    _resolve_block_rules(signal_data, graph)
    _accept_rules(signal_data, graph)

    # A re-ASSIGN from VALIDATING is CANON (§12.4 lists ASSIGN→OFFERED in VALIDATING's admissible set,
    # and §12.14 leans on it when it grades pre-registration: "before settlement ASSIGN is admissible
    # from VALIDATING, so an issuer may revise criteria with the delivery in hand — at the price of a
    # logged event, a voided delivery and a fresh consent"). It used to be REFUSED here, over churn
    # measured live (BCB/120: an agent rewrote the root's risks three times under the validator). That
    # observation is about what an agent does under a rule, not about whose rule it is — and the price
    # the canon names is now actually charged: the pending PASS is voided at the revision
    # (`Graph.void_pending_pass`), so the node re-earns its verdict instead of completing on one that
    # was about a contract it no longer carries.

    # Theorem 1 at runtime (§15.1): a DECOMPOSED node PASSes only if every active child has PASSed —
    # V(parent) = AND(V(children)). The per-node FSM stays graph-blind (proven closed over single nodes); this
    # cross-node composition invariant is enforced here (the validation layer sees the graph), not just advised
    # by next_step's ordering. A leaf (no children) is unaffected.
    _pass_rules(signal_data, graph, audit)

