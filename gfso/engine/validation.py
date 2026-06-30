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
        # Issuer = whoever created/owns the task (parent's assignee, or task creator)
        parent = graph.get_parent(signal_data.task_id)
        if parent and parent.assignee and signal_data.source != parent.assignee:
            raise ValidationError(
                f"{signal_data.source} is not issuer for {signal_data.task_id} "
                f"(issuer={parent.assignee})"
            )

    elif role == Role.EXECUTOR:
        if task.assignee and signal_data.source != task.assignee:
            raise ValidationError(
                f"{signal_data.source} is not executor for {signal_data.task_id} "
                f"(executor={task.assignee})"
            )
