"""Signal validation enforcement — L2 wrapper around L1 role rules."""
from __future__ import annotations

import os
from typing import Optional


from gfso.core.types import Signal, SignalData, State, DoneReason
from gfso.core.protocol.validation import Role, required_role
from gfso.core.protocol.invariants import validate_fail_has_criteria
from gfso.core.handlers.structural import run_structural
from gfso.core.handlers.constraint import _parse_numeric_bound
from gfso.core.graph import Graph


class ValidationError(Exception):
    pass


# THE SYNTACTIC LEVEL, whole: §13.4 lists CHECK-1, 1b, 2, 3, 4, 5, 6 at Level 0 and then states, in
# its own words, that "a decomposition that fails the Syntactic level is not admitted to execution".
# So the gate is the level, not a selection from it.
#
# Four of the seven used to gate and three did not: ACCEPTED_RISKS (4), risk nodes (5) and leaf
# delegation (6) were called "completeness documentation" and only surfaced. The observation behind
# that was real — gating the register bought fabricated entries and `edit_accepted_risks` churn — but
# it is an argument about what an agent does under a rule, not about whether the rule is the canon's,
# and §13.1 settles the object: "a decomposition without the register is incomplete by definition".
# A fabricated register is a q_T defect with a name and an owner; a silently ungated level is neither.
#
# CHECK-1c (anti-mock) is an engineering addition with no canon row, so it stays OUT of the gate: the
# gate is exactly the canon's level, in both directions.
_EXEC_GATING_CHECKS = ("CHECK-1:", "CHECK-1b", "CHECK-2", "CHECK-3",
                       "CHECK-4", "CHECK-5", "CHECK-6")


def l2_gate_on() -> bool:
    """Is the Level-2 execution gate active? `GFSO_L2_GATE=0` opts out — the canon's EXPLORE branch
    (§13.5): the plan's causal verification is bought with contact instead of with c_check. Off is
    also the honest setting where no checker instrument exists at all (a pure-human graph)."""
    return os.environ.get("GFSO_L2_GATE", "1") not in ("", "0")


def _l2_undischarged(graph: Graph, node) -> Optional[list[str]]:
    """The Level-2 obligations of `node`'s plan that are not yet discharged — where "plan" is its
    decomposition, or, for a childless node, its claim to BE one unit of work (D(t)=∅ is a value of
    D, and the degenerate plan is checked by the same rule; see gfso.critic._critique_leaf).

    `[]` = discharged (a CURRENT review found no gap, or every gap it named carries a recorded
    dispute). `None` = there is NO current verdict at all — never run, staled by an edit, or the
    checker returned nothing readable (fail-CLOSED: "no verdict is never read as clean", the
    checker's own doctrine — §13.4 Level 2 / gfso.critic).

    What is gated is that the check HAPPENED and its findings were DISPOSITIONED — never that the
    checker is right. L2 is an LLM-review APPROXIMATION over the faithfulness axis (§13.5); the
    real Level-2 verdict belongs to contact (q_D). So a named gap is discharged either by CHANGING
    the plan (any edit stales the review — the record and its disputes die with it, forcing a fresh
    one) or by the issuer RECORDING why the finding is wrong (`dispute_finding`): an explicit,
    logged, falsifiable claim instead of a silent skip (§6.2 making-explicit)."""
    import json
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
    disputed = set((rec.get("disputes") or {}).keys())
    gaps = [str(v.get("criterion")) for v in rec.get("criteria_verdicts") or ()
            if v.get("verdict") != "sufficient" and str(v.get("criterion")) not in disputed]
    gaps += [k for c in rec.get("conflicts") or ()
             if (k := "conflict: " + ", ".join(c.get("between") or ())) not in disputed]
    return gaps


def _fail_extension_shrank(old_desc: str, new_desc: str) -> bool:
    """Did a revision LOOSEN this criterion — decidably, on the tier where that is decidable?

    "Adding coverage so that ⋀criteria(children) ⊨ cᵢ" and "lowering cᵢ to what the children already
    deliver" wear the same shape at a re-delivery; what tells them apart is whether cᵢ's fail-extension
    shrank (§2.1: a criterion forbids exactly by having one). In general that is L2 — but on the
    numeric-bound tier it is O(1) arithmetic (§5.4/CHECK-7), and this is that tier: same metric, same
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


def _refuted_coverage_refusal(graph: Graph, task, rec: dict) -> Optional[str]:
    """The disposition of a re-delivery under a contact-refuted decomposition — the FM-1 branch.

    A parent criterion failing while every mapped child passes its OWN is the q_D event (§15.2) and
    an FM-1 defect — FM-1.d (children exist, `⋀criteria(tⱼ) ⊭ cᵢ`) or FM-1.f (the goal needed a
    criterion nobody wrote). The defect is in the DECOMPOSITION, owned by whoever built it, so the
    repair is a **revision of the parent under Inv-1** (§14.4): a re-ASSIGN under the same id with a
    corrected mapping or an added covering child. A revision does not cascade — the subtree is kept,
    staleness surfaces through CHECK-1/CHECK-1b/CHECK-3 — and the consumption gate is never reached,
    which is why this route has no wall where the downward one does (`EVIDENCE_LOG` §13.3).

    Per failed criterion, one of five dispositions; the first that applies to any criterion refuses:
      · DROPPED — the refuted criterion is gone from the packet: the fail-extension collapsed to
        empty, which is a false close, not a repair (its removal is a scope change owned by the
        issuer above, §13.1).
      · LOOSENED — decidably weakened on the numeric tier (above): the same false close.
      · EDITED — the text changed undecidably: legitimate on its face, so it is admitted once the
        revised plan's checks have SPOKEN again (L0 clean + a current, dispositioned L2 verdict).
        What is required is that the check happened, never that the checker is right — the same
        doctrine as the execution gate, and `GFSO_L2_GATE=0` opts out of the L2 half identically.
      · UNREPAIRED — criterion unchanged and every coverer untouched since the FAIL: re-delivering
        an unchanged aggregate over an unchanged plan decides nothing.
      · REPAIRED — a coverer was touched (reopened, revised, or newly added): admitted, as before.
    """
    now = {c.name: c for c in task.spec.criteria}
    was = rec.get("criteria_text") or {}
    dropped, loosened, edited, unrepaired = [], [], [], []
    for crit in rec.get("failed_criteria") or ():
        coverers = [m.child_id for m in task.criterion_mappings if m.criterion_name == crit]
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
        untouched = [str(cid) for cid in coverers
                     if (child := graph.get_task(cid)) is not None and child.state == State.DONE
                     and child.state_entered_at <= task.state_entered_at]
        if len(untouched) == len(coverers):
            unrepaired.append(f"{crit} (covered by: {', '.join(untouched)})")

    revision = (f"The canonical repair is a REVISION OF THIS NODE under Inv-1 (§14.4): re-ASSIGN "
                f"{task.id} with a corrected mapping or an added covering child, so that the mapped "
                f"children's criteria carry the parent's (map_criterion / add a child / edit_criteria "
                f"where the criterion itself was wrong). A revision does not cascade — the subtree is "
                f"kept and the consumption gate is not involved. Reworking a child that already met "
                f"its own criteria asks it to guess (§15.2 q_D; FM-1.d/FM-1.f).")

    if dropped:
        return (f"cannot re-DELIVER {task.id}: the criteria contact refuted were REMOVED rather than "
                f"covered ({', '.join(dropped)}) — a criterion with no fail-extension forbids nothing, "
                f"so this closes the node instead of repairing it (§2.1). Restore the criterion and "
                f"add the coverage; a genuine scope change belongs to the goal above (§13.1). " + revision)
    if loosened:
        return (f"cannot re-DELIVER {task.id}: the refuted criteria were LOOSENED to what the current "
                f"result already delivers ({', '.join(loosened)}) — the bound moved, the work did not. "
                f"That is a false close in the shape of a repair (§2.1 fail-extension). " + revision)
    if edited and l2_gate_on():
        if (holes := _l0_holes(graph, task)):
            return (f"cannot re-DELIVER {task.id}: its criteria were revised after contact refuted "
                    f"them ({', '.join(edited)}), and the revised plan does not pass Level 0 — "
                    f"the mapping must speak again before the aggregate does (§13.4): "
                    + "; ".join(f"{h.check_name}: {h.details}" for h in holes))
        if (gaps := _l2_undischarged(graph, task)) is None:
            return (f"cannot re-DELIVER {task.id}: its criteria were revised after contact refuted "
                    f"them ({', '.join(edited)}) and no CURRENT Level-2 verdict covers the revision — "
                    f"a lowered criterion and an added coverage look alike until CHECK-7 speaks "
                    f"(§13.4). Run review_decomposition({task.id}) first")
        if gaps:
            return (f"cannot re-DELIVER {task.id}: the Level-2 review of the revised plan names gaps "
                    f"that are still open — the mapped children's criteria do not carry these parent "
                    f"criteria (§13.4). Fix the plan or record why the finding is wrong "
                    f"(dispute_finding({task.id}, <criterion>, <why>)). Open: " + "; ".join(gaps))
    if unrepaired:
        return (f"cannot re-DELIVER {task.id}: the FAILed criteria are covered by children untouched "
                f"since that FAIL — contact refuted the DECOMPOSITION, not the aggregate "
                f"({'; '.join(unrepaired)}). " + revision)
    return None


def _l0_holes(graph: Graph, parent) -> list:
    """The FAILING plan-correctness checks of `parent`'s decomposition (coverage / non-redundancy /
    DAG / deadlines). Computed live so a stale cache never gates. Empty = the plan is admissible."""
    children = graph.get_active_children(parent.id)
    if not children:
        return []
    child_ids = {str(c.id) for c in children}
    edges = [(str(e.from_id), str(e.to_id)) for e in graph.dep_edges()
             if str(e.from_id) in child_ids and str(e.to_id) in child_ids]
    # Same leaf information the cached computation gets (`Engine._recompute_checks`): without it
    # CHECK-6 would read every child as a leaf HERE and as a leaf-or-branch THERE, so the gate could
    # refuse a start over a hole `get_checks`/`list_holes` shows green — two views of one plan.
    return [c for c in run_structural(parent, children, edges, graph.non_leaf_ids(children))
            if not c.passed and not c.skipped and c.check_name.startswith(_EXEC_GATING_CHECKS)]


def validate_signal(signal_data: SignalData, graph: Graph) -> None:
    """Check signal validity: role authorization + protocol invariants.

    Raises ValidationError if signal is not authorized or violates invariants.
    """
    # Invariant 3: FAIL must specify failed criteria
    if not validate_fail_has_criteria(signal_data):
        raise ValidationError(
            f"FAIL signal for {signal_data.task_id} must specify failed_criteria"
        )

    # Contact-refuted coverage gate (§15.2 q_D made STRUCTURAL). A parent FAIL whose criteria are
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
    if signal_data.signal == Signal.DELIVER:
        task = graph.get_task(signal_data.task_id)
        # The trigger is "this node has a decomposition", not "it still has mappings": deleting the
        # refuted criterion also deletes the mapping that pointed at it, so a mapping-keyed trigger
        # would let exactly the false close through. A leaf is out of scope by the same reading —
        # its contract belongs to the issuer above, whose CHECK-1 surfaces any hole a rewrite leaves.
        if (task is not None and task.state in (State.REWORKING, State.EXECUTING)
                and graph.get_active_children(task.id)):
            rec = graph.exec_verdict_record(signal_data.task_id)
            if (rec and rec.get("verdict") == "FAIL"
                    and rec.get("reopens", 0) == getattr(task, "reopens", 0)
                    and rec.get("iteration") == getattr(task, "iteration", 0) - 1):
                if (refusal := _refuted_coverage_refusal(graph, task, rec)) is not None:
                    raise ValidationError(refusal)

    # §13.4: "a decomposition that has not passed Level 0 is NOT admitted to execution." Enforced, not
    # advised: the FIRST execution step of a child (ACCEPT: OFFERED→EXECUTING) is REFUSED while the
    # PARENT's decomposition has an unresolved L0 hole (uncovered criterion, orphan child, cycle,
    # empty/malformed ACCEPTED_RISKS, …). This moves "verify the plan before you execute it" from the prompt
    # into the system: the agent physically cannot start working a flawed plan, so the plan is completed
    # and checked ONCE, up front — no discover-after-delivery, no edit_accepted_risks-during-rework churn, and a
    # verified plan means fewer contact-refutations (higher q_D). A root (no parent) is atomic to the
    # system — nothing to verify — and is unaffected; so is an already-clean parent.
    if signal_data.signal == Signal.ACCEPT:
        # How many subtasks a goal splits into is the executor's domain call, NOT set from outside
        # (§10: D is the decomposer's to choose). So the engine does NOT force a leaf to justify being
        # atomic — a taken leaf executes, and the ROOT seam validates the whole result against the
        # issuer's criteria regardless. What the engine DOES enforce is that a decomposition the
        # executor DID choose is causally sound before its parts run (below). (An earlier build gated
        # the leaf itself on an atomicity verdict; that imposed the subtask count from outside and, as a
        # side effect, deadlocked auto_decompose's own builder on its internal ACCEPTs. Removed.)
        parent = graph.get_parent(signal_data.task_id)
        if parent is not None:
            holes = _l0_holes(graph, parent)
            if holes:
                raise ValidationError(
                    f"cannot execute {signal_data.task_id}: its parent's plan is not Level-0 verified — "
                    f"a decomposition that fails L0 is not admitted to execution (§13.4). Resolve first "
                    f"(list_holes on {parent.id}): "
                    + "; ".join(f"{h.check_name}: {h.details}" for h in holes))

            # …and the same for the Pragmatic level — and here the engine goes BEYOND the canon's own
            # rule, deliberately, so the citation says so rather than borrowing authority. §13.4 makes
            # the SYNTACTIC level the admission condition ("a decomposition that fails the Syntactic
            # level is not admitted to execution") and files the Pragmatic level as "runtime detection
            # + learning" — it names no pre-execution gate there, and it could not: causal correctness
            # is formally uncheckable from inside (Ch. 8). What is gated here is therefore NOT the
            # checker's verdict but the canon's verify-vs-explore DECISION (§13.5) made explicit: the
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
            # EXPLORE branch (§13.5) — you buy the plan's verification with contact instead of with
            # c_check, consciously and by configuration, never by an agent skipping a step.
            if l2_gate_on():
                gaps = _l2_undischarged(graph, parent)
                if gaps is None:
                    raise ValidationError(
                        f"cannot execute {signal_data.task_id}: its parent's plan has no CURRENT "
                        f"Level-2 verdict — the causal check has not been run over this version of the "
                        f"decomposition (§13.4). Run review_decomposition({parent.id}) first (any edit "
                        f"to the plan stales an earlier review; an unreadable verdict is not a verdict)")
                if gaps:
                    raise ValidationError(
                        f"cannot execute {signal_data.task_id}: its parent's Level-2 review named gaps "
                        f"that are still open — the mapped children's criteria do not carry these parent "
                        f"criteria (§13.4). Fix the plan (edit_criteria / map_criterion / add a child — "
                        f"which re-opens the review) or record why the finding is wrong "
                        f"(dispute_finding({parent.id}, <criterion>, <why>)). Open: " + "; ".join(gaps)
                        + f" — read the reasons with get_review({parent.id})")

    # A re-ASSIGN from VALIDATING is CANON (§14.3 lists ASSIGN→OFFERED in VALIDATING's admissible set,
    # and §6.3 leans on it when it grades pre-registration: "before settlement ASSIGN is admissible
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
    if signal_data.signal == Signal.PASS:
        unpassed = [c.id for c in graph.get_active_children(signal_data.task_id)
                    if not (c.state == State.DONE and c.done_reason == DoneReason.PASS)]
        if unpassed:
            raise ValidationError(
                f"cannot PASS {signal_data.task_id}: not all children have PASSed (V=AND of children): {unpassed}"
            )
        # Verifier ≠ executor (§14.5: self-checking violates IC). When the signer IS the node's
        # executor (collapsed ids — the self-execution regime), the FSM cannot tell an
        # evidence-based issuer PASS from a self-stamp, so the evidence must come from OUTSIDE
        # the id: a recorded independent verdict for the CURRENT delivery (a rework stales it).
        # Distinct ids (source ≠ Del) keep the canon default — the separation already exists.
        # D6 (§14.5): the gate is a GATE-ON-THE-SEAM — it fires on PUBLIC nodes (a root, or
        # Del(child) ≠ Del(parent)), not on every node of the graph. An INTERNAL node (same Del
        # as its parent) is the agent's private decomposition: it legitimately SELF-verifies
        # (DELIVER carries self_validation) and its guarantee is carried by the validation of the
        # public result it rolls up into (Thm 1 non-redundancy) — so a same-Del self-PASS passes here.
        # The ROOT is always a seam: "done" (root DONE/PASS) never completes on a self-stamp.
        task = graph.get_task(signal_data.task_id)
        if (task is not None and signal_data.source and signal_data.source == task.assignee
                and graph.is_public(task)):
            rec = graph.exec_verdict_record(signal_data.task_id)
            it = getattr(task, "iteration", 0)
            ro = getattr(task, "reopens", 0)
            # Generation stamp = (iteration, reopens): a rework stales the verdict, and so does a
            # REOPEN (§14.3 anti-fake — the pre-reopen PASS must not re-open this gate from the past).
            stale = bool(rec) and (rec.get("iteration") != it or rec.get("reopens", 0) != ro
                                   or rec.get("revisions", 0) != getattr(task, "revisions", 0))
            # …and so does a REVISION, which moves neither counter: §14.3 admits a re-ASSIGN from
            # VALIDATING and §6.3 voids the pending delivery with it, but a validator still running on
            # that delivery can land its verdict AFTER the revision — and it would carry the same
            # (iteration, reopens). The CONTRACT generation is the discriminator, so the record is
            # stamped with it too. Records written before the stamp existed read as generation 0; a
            # node that was never revised is also 0, so they agree exactly where they should.
            if not rec or stale or rec.get("verdict") != "PASS":
                why = ("no independent verdict is recorded" if not rec
                       else "the recorded verdict is STALE — this delivery was reworked, reopened or "
                            "its contract was revised under it, re-validate"
                       if stale
                       else f"the recorded verdict is {rec.get('verdict')}, not PASS")
                raise ValidationError(
                    f"PASS on {signal_data.task_id} by its own executor ({signal_data.source}) needs "
                    f"an independent validator verdict for the current delivery ({why}) — run "
                    f"validate_result first, or delegate validation; verifier ≠ executor (§14.5)")

    role = required_role(signal_data.signal)

    # System signals carry NO sender (§14.2: the timeout "is not a P2P signal (no agent sends it) but
    # a system mechanism enforcing finiteness"). The deadline monitor emits it sourceless
    # (gfso/engine/loop.py), so a SOURCED system signal is by construction an agent impersonating the
    # clock — and it settled nodes: TIMEOUT on VALIDATING routes to DONE(auto_pass), which is a
    # terminal reached around the AND gate (Thm 1), around verifier ≠ executor (§14.5) and around
    # Inv-3. Refused HERE because this is the layer that authorizes senders; the tool door refuses the
    # name outright (gfso/tools.py), so the two are independent — a caller that reaches the engine by
    # another route still cannot sign the clock.
    if role == Role.SYSTEM:
        if signal_data.source:
            raise ValidationError(
                f"{signal_data.signal.name} is a SYSTEM trigger, not a P2P signal (§14.2): no agent "
                f"sends it — it is emitted by the deadline monitor to enforce finiteness (Inv-5). "
                f"'{signal_data.source}' cannot sign it")
        return

    task = graph.get_task(signal_data.task_id)
    if task is None:
        return

    if signal_data.source is None:
        raise ValidationError(
            f"non-system signal {signal_data.signal.name} requires source (sender agent_id)"
        )

    if role == Role.ISSUER:
        # Issuer = the parent's assignee, or — for a ROOT (no parent) — the task's own assignee
        # (matches Engine._issuer_of). A root has no parent, so it must fall back to task.assignee;
        # without it the check was skipped entirely and ANY source could sign an issuer signal on a root.
        # Exception (canon §14.5 — autonomy is per-task per-ROLE): a registered llm-validator is the
        # issuer's AUTHORIZED INSTRUMENT for role V — its PASS/FAIL verdicts are accepted on any node
        # (Thm 11 still records the true actor: source = the validator id, never forged as the issuer).
        parent = graph.get_parent(signal_data.task_id)
        issuer = parent.assignee if (parent and parent.assignee) else task.assignee
        if issuer and signal_data.source != issuer:
            if (signal_data.signal in (Signal.PASS, Signal.FAIL)
                    and signal_data.source in getattr(graph, "_authorized_validators", ())):
                return
            raise ValidationError(
                f"{signal_data.source} is not issuer for {signal_data.task_id} (issuer={issuer})"
            )

    elif role == Role.EXECUTOR:
        if task.assignee and signal_data.source != task.assignee:
            raise ValidationError(
                f"{signal_data.source} is not executor for {signal_data.task_id} "
                f"(executor={task.assignee})"
            )
