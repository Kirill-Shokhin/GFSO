"""Signal validation enforcement — L2 wrapper around L1 role rules."""
from __future__ import annotations

import os


from gfso.core.types import Signal, SignalData, State, DoneReason
from gfso.core.protocol.validation import Role, required_role
from gfso.core.protocol.invariants import validate_fail_has_criteria
from gfso.core.handlers.structural import run_structural
from gfso.core.graph import Graph


class ValidationError(Exception):
    pass


# The plan-CORRECTNESS checks that gate execution (§5.4): a criterion must be covered (CHECK-1), every
# child must earn its place (CHECK-1b), the graph must be acyclic (CHECK-2), and Dep deadlines coherent
# (CHECK-3). NEGLECTED (CHECK-4) and risk-nodes (CHECK-5) are completeness DOCUMENTATION, not structural
# correctness — they are surfaced advisorily, never block starting work (gating them forced a fake
# NEGLECTED and drove reneglect churn, observed live).
_EXEC_GATING_CHECKS = ("CHECK-1:", "CHECK-1b", "CHECK-2", "CHECK-3")


def l2_gate_on() -> bool:
    """Is the Level-2 execution gate active? `GFSO_L2_GATE=0` opts out — the canon's EXPLORE branch
    (§5.4-bis): the plan's causal verification is bought with contact instead of with c_check. Off is
    also the honest setting where no checker instrument exists at all (a pure-human graph)."""
    return os.environ.get("GFSO_L2_GATE", "1") not in ("", "0")


def _l2_undischarged(graph: Graph, node) -> Optional[list[str]]:
    """The Level-2 obligations of `node`'s plan that are not yet discharged — where "plan" is its
    decomposition, or, for a childless node, its claim to BE one unit of work (D(t)=∅ is a value of
    D, and the degenerate plan is checked by the same rule; see gfso.critic._critique_leaf).

    `[]` = discharged (a CURRENT review found no gap, or every gap it named carries a recorded
    dispute). `None` = there is NO current verdict at all — never run, staled by an edit, or the
    checker returned nothing readable (fail-CLOSED: "no verdict is never read as clean", the
    checker's own doctrine — §5.4 Level 2 / gfso.critic).

    What is gated is that the check HAPPENED and its findings were DISPOSITIONED — never that the
    checker is right. L2 is an LLM-review APPROXIMATION over the faithfulness axis (§5.4-bis); the
    real Level-2 verdict belongs to contact (q_D). So a named gap is discharged either by CHANGING
    the plan (any edit stales the review — the record and its disputes die with it, forcing a fresh
    one) or by the issuer RECORDING why the finding is wrong (`dispute_finding`): an explicit,
    logged, falsifiable claim instead of a silent skip (§17.5 objectification)."""
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


def _l0_holes(graph: Graph, parent) -> list:
    """The FAILING plan-correctness checks of `parent`'s decomposition (coverage / non-redundancy /
    DAG / deadlines). Computed live so a stale cache never gates. Empty = the plan is admissible."""
    children = graph.get_active_children(parent.id)
    if not children:
        return []
    child_ids = {str(c.id) for c in children}
    edges = [(str(e.from_id), str(e.to_id)) for e in graph.dep_edges()
             if str(e.from_id) in child_ids and str(e.to_id) in child_ids]
    return [c for c in run_structural(parent, children, edges)
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

    # Contact-refuted coverage gate (§7.2 q_D made STRUCTURAL). A parent FAIL whose criteria are
    # COVERED by PASSed children is the q_D event: contact refuted the mapping's claimed entailment
    # (child passed its own criteria ∧ the parent criterion stayed red) — the DECOMPOSITION is
    # indicted, not the aggregate artifact. Re-DELIVERing the same aggregate over an UNTOUCHED
    # subtree would launder the refuted decomposition through a fresh validation, mutating the
    # artifact while the responsible children sit frozen in DONE (observed live: BCB/93 run 9) —
    # so the engine REFUSES it: rework flows DOWN (reopen the covering child — the refused parent
    # delivery released it — revise its contract, remap, or add a child; any re-authoring touches
    # the child and re-opens this gate). A failed criterion with NO covering child is the parent's
    # own layer — a parent-level fix is legitimate and passes. Attribution source = the recorded
    # verdict of the refuting FAIL (generation-stamped); a FAIL signaled without a recorded verdict
    # is a named boundary: unattributable, not gated. `state_entered_at` is not persisted — after a
    # restart both sides re-arm to load time, which reads as "untouched" (conservative: the gate
    # may ask for one explicit child touch after a restart, never the reverse).
    if signal_data.signal == Signal.DELIVER:
        task = graph.get_task(signal_data.task_id)
        if task is not None and task.state == State.REWORK and task.criterion_mappings:
            rec = graph.exec_verdict_record(signal_data.task_id)
            if (rec and rec.get("verdict") == "FAIL"
                    and rec.get("reopens", 0) == getattr(task, "reopens", 0)
                    and rec.get("iteration") == getattr(task, "iteration", 0) - 1):
                refuted = []
                for crit in rec.get("failed_criteria") or ():
                    coverers = [m.child_id for m in task.criterion_mappings
                                if m.criterion_name == crit]
                    if not coverers:
                        continue  # parent's own layer — parent-level fix legitimate
                    untouched = []
                    for cid in coverers:
                        child = graph.get_task(cid)
                        if (child is not None and child.state == State.DONE
                                and child.state_entered_at <= task.state_entered_at):
                            untouched.append(str(cid))
                    if untouched and len(untouched) == len(coverers):
                        refuted.append(f"{crit} (covered by: {', '.join(untouched)})")
                if refuted:
                    raise ValidationError(
                        f"cannot re-DELIVER {signal_data.task_id}: the FAILed criteria are covered "
                        f"by children untouched since that FAIL — contact refuted the DECOMPOSITION, "
                        f"not the aggregate ({'; '.join(refuted)}). Rework flows DOWN: reopen the "
                        f"covering child (the refused delivery released it) and rework it there, "
                        f"revise its contract, remap the criterion, or add a covering child — then "
                        f"re-aggregate (§7.2 q_D; §2.2 joint sufficiency)")

    # §5.4: "a decomposition that has not passed Level 0 is NOT admitted to execution." Enforced, not
    # advised: the FIRST execution step of a child (ACCEPT: REVIEW→EXECUTING) is REFUSED while the
    # PARENT's decomposition has an unresolved L0 hole (uncovered criterion, orphan child, cycle,
    # empty/malformed NEGLECTED, …). This moves "verify the plan before you execute it" from the prompt
    # into the system: the agent physically cannot start working a flawed plan, so the plan is completed
    # and checked ONCE, up front — no discover-after-delivery, no reneglect-during-rework churn, and a
    # verified plan means fewer contact-refutations (higher q_D). A root (no parent) is atomic to the
    # system — nothing to verify — and is unaffected; so is an already-clean parent.
    if signal_data.signal == Signal.ACCEPT:
        # How many subtasks a goal splits into is the executor's domain call, NOT set from outside
        # (§2.2: D is the decomposer's to choose). So the engine does NOT force a leaf to justify being
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
                    f"a decomposition that fails L0 is not admitted to execution (§5.4). Resolve first "
                    f"(list_holes on {parent.id}): "
                    + "; ".join(f"{h.check_name}: {h.details}" for h in holes))

            # …and the same for Level 2 (§5.4 Level 2 / §5.4-bis). L0 sees only topology: a criterion
            # that HAS a covering child passes it even when that child's criteria cannot causally carry
            # it — the hole then surfaces after the code is written, as a refused delivery (the rework
            # that indicts the decomposition, q_D↓). The checker sees exactly this class BEFORE contact,
            # so the plan is checked once, up front, and the gap is fixed on the plan instead of paid for
            # in code. Measured on the live substrate (BCB/120, three L0-clean plans): every planted
            # entailment hole named, zero false gaps.
            # The gate is on the PROCESS, not on the checker's authority: run it, then either fix the
            # plan or record why the finding is wrong (`dispute_finding`). The verdict remains advisory
            # — contact keeps the last word (q_D). `GFSO_L2_GATE=0` opts out: that is the canon's own
            # EXPLORE branch (§5.4-bis) — you buy the plan's verification with contact instead of with
            # c_check, consciously and by configuration, never by an agent skipping a step.
            if l2_gate_on():
                gaps = _l2_undischarged(graph, parent)
                if gaps is None:
                    raise ValidationError(
                        f"cannot execute {signal_data.task_id}: its parent's plan has no CURRENT "
                        f"Level-2 verdict — the causal check has not been run over this version of the "
                        f"decomposition (§5.4). Run review_decomposition({parent.id}) first (any edit "
                        f"to the plan stales an earlier review; an unreadable verdict is not a verdict)")
                if gaps:
                    raise ValidationError(
                        f"cannot execute {signal_data.task_id}: its parent's Level-2 review named gaps "
                        f"that are still open — the mapped children's criteria do not carry these parent "
                        f"criteria (§5.4). Fix the plan (edit_criteria / map_criterion / add a child — "
                        f"which re-opens the review) or record why the finding is wrong "
                        f"(dispute_finding({parent.id}, <criterion>, <why>)). Open: " + "; ".join(gaps)
                        + f" — read the reasons with get_review({parent.id})")

    # Revision is incoherent while a node is being validated (§6.4 Inv-1 revision changes the contract;
    # validating a node against a contract that is changing under the validator is meaningless). Enforced
    # at the validation layer (not by dropping VALIDATING from REASSIGNABLE_STATES — that would drift the
    # FSM table from the TLA model): a re-ASSIGN (revise) is REFUSED from VALIDATING; wait for the verdict
    # (PASS/FAIL), then revise if still needed. Observed live (BCB/120): an agent reneglected the ROOT
    # while it was VALIDATING, bouncing it back to REVIEW three times and re-running the validator each
    # time — pure churn. The initial ASSIGN (node creation, no prior state) is unaffected; only an
    # in-place re-ASSIGN onto a VALIDATING node is blocked.
    if signal_data.signal == Signal.ASSIGN and getattr(signal_data, "spec", None) is not None:
        task = graph.get_task(signal_data.task_id)
        if task is not None and task.state == State.VALIDATING:
            raise ValidationError(
                f"cannot revise {signal_data.task_id} while it is VALIDATING — a contract cannot change "
                f"under the validator (§6.4). Wait for the verdict (PASS/FAIL), then revise if needed")

    # Theorem 1 at runtime (§7.1): a DECOMPOSED node PASSes only if every active child has PASSed —
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
        # Verifier ≠ executor (§6.5: self-checking violates IC). When the signer IS the node's
        # executor (collapsed ids — the self-execution regime), the FSM cannot tell an
        # evidence-based issuer PASS from a self-stamp, so the evidence must come from OUTSIDE
        # the id: a recorded independent verdict for the CURRENT delivery (a rework stales it).
        # Distinct ids (source ≠ Del) keep the canon default — the separation already exists.
        # D6 (§6.5): the gate is a GATE-ON-THE-SEAM — it fires on PUBLIC nodes (a root, or
        # Del(child) ≠ Del(parent)), not on every node of the graph. An INTERNAL node (same Del
        # as its parent) is the agent's private decomposition: it legitimately SELF-verifies
        # (DELIVER carries self_validation) and its guarantee is carried by the validation of the
        # public result it rolls up into (T1 non-redundancy) — so a same-Del self-PASS passes here.
        # The ROOT is always a seam: "done" (root DONE/PASS) never completes on a self-stamp.
        task = graph.get_task(signal_data.task_id)
        if (task is not None and signal_data.source and signal_data.source == task.assignee
                and graph.is_public(task)):
            rec = graph.exec_verdict_record(signal_data.task_id)
            it = getattr(task, "iteration", 0)
            ro = getattr(task, "reopens", 0)
            # Generation stamp = (iteration, reopens): a rework stales the verdict, and so does a
            # REOPEN (§6.3 anti-fake — the pre-reopen PASS must not re-open this gate from the past).
            stale = bool(rec) and (rec.get("iteration") != it or rec.get("reopens", 0) != ro)
            if not rec or stale or rec.get("verdict") != "PASS":
                why = ("no independent verdict is recorded" if not rec
                       else "the recorded verdict is STALE — this delivery was reworked/reopened, re-validate"
                       if stale
                       else f"the recorded verdict is {rec.get('verdict')}, not PASS")
                raise ValidationError(
                    f"PASS on {signal_data.task_id} by its own executor ({signal_data.source}) needs "
                    f"an independent validator verdict for the current delivery ({why}) — run "
                    f"validate_result first, or delegate validation; verifier ≠ executor (§14.5)")

    role = required_role(signal_data.signal)

    # System signals: no sender validation needed
    if role == Role.SYSTEM:
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
        # Exception (canon §6.5 — autonomy is per-task per-ROLE): a registered llm-validator is the
        # issuer's AUTHORIZED INSTRUMENT for role V — its PASS/FAIL verdicts are accepted on any node
        # (T11 still records the true actor: source = the validator id, never forged as the issuer).
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
