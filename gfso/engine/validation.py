"""Signal validation enforcement — L2 wrapper around L1 role rules."""
from __future__ import annotations


from gfso.core.types import Signal, SignalData, State, DoneReason
from gfso.core.protocol.validation import Role, required_role
from gfso.core.protocol.invariants import validate_fail_has_criteria
from gfso.core.graph import Graph


class ValidationError(Exception):
    pass


def validate_signal(signal_data: SignalData, graph: Graph) -> None:
    """Check signal validity: role authorization + protocol invariants.

    Raises ValidationError if signal is not authorized or violates invariants.
    """
    # Invariant 3: FAIL must specify failed criteria
    if not validate_fail_has_criteria(signal_data):
        raise ValidationError(
            f"FAIL signal for {signal_data.task_id} must specify failed_criteria"
        )

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
                    f"validate_result first, or delegate validation; verifier ≠ executor (§6.5)")

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
