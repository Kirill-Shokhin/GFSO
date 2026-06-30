"""Mutation -> G'. Returns affected child ids for cascade."""
from __future__ import annotations

import logging
from typing import Optional

from gfso.core.types import (
    TaskId, Task, State, MutationType, DoneReason,
    MutateGraph, CriterionMapping, TERMINAL_STATES,
)
from .model import Graph

log = logging.getLogger(__name__)


class InvariantViolation(Exception):
    pass


def apply(graph: Graph, effect: MutateGraph) -> list[TaskId]:
    """Apply a mutation to the graph. Returns affected child task_ids for cascade."""
    task = graph.get_task(effect.task_id)

    match effect.mutation:
        case MutationType.SET_STATE:
            return _set_state(graph, task, effect)
        case MutationType.INCREMENT_ITERATION:
            return _increment_iteration(graph, task)
        case MutationType.CREATE_TASK:
            return _create_task(graph, effect)
        case MutationType.APPLY_SPEC:
            return _apply_spec(graph, task, effect)
        case MutationType.STORE_CHECK_RESULTS:
            return []
        case MutationType.STORE_RECOMMENDATION:
            return []
        case _:
            log.warning(f"unhandled mutation type: {effect.mutation}")
            return []


def _set_state(graph: Graph, task: Optional[Task], effect: MutateGraph) -> list[TaskId]:
    if task is None:
        log.error(f"task {effect.task_id} not found for SET_STATE")
        return []

    new_state = effect.new_state
    if new_state is None:
        log.error(f"SET_STATE without new_state for {effect.task_id}")
        return []

    # Invariant 1: criteria immutability
    # If spec is being changed (e.g. via ACCEPT_CHALLENGE), validate
    if effect.spec is not None and task.spec.criteria != effect.spec.criteria:
        raise InvariantViolation(
            f"criteria immutability violated for {effect.task_id}: "
            f"criteria change requires CANCEL + re-ASSIGN"
        )

    # Track challenge for q_T metric
    if new_state == State.CHALLENGED:
        task.was_challenged = True

    task.state = new_state

    if effect.done_reason is not None:
        task.done_reason = effect.done_reason

    graph.save_task(task)

    # Cascade: if task moved to DONE with CANCELLED reason, return children for cascade
    if new_state == State.DONE and effect.done_reason == DoneReason.CANCELLED:
        children = graph.get_children(effect.task_id)
        return [
            c.id for c in children
            if c.state not in TERMINAL_STATES
        ]

    return []


def _apply_spec(graph: Graph, task: Optional[Task], effect: MutateGraph) -> list[TaskId]:
    """Apply a renegotiated spec via the sanctioned CHALLENGE channel (ACCEPT_CHALLENGE, §6.2/§6.6).

    The ONLY in-place spec change permitted to alter criteria — it is the *pre-acceptance* negotiation
    (state CHALLENGED, executor has not yet ACCEPTed), distinct from the Inv-1-guarded default path
    where a post-acceptance criteria change requires CANCEL + re-ASSIGN. §6.6 shows ACCEPT_CHALLENGE
    removing criterion c_B2 — so this channel legitimately rewrites criteria/NEGLECTED.
    """
    if task is None or effect.spec is None:
        log.error(f"APPLY_SPEC without task/spec for {effect.task_id}")
        return []
    task.spec = effect.spec
    task.done_reason = None  # re-authored → a fresh contract, no longer a CANCELLED tombstone (clears stale flag)
    # a criteria change strands this node's own mappings that point at a now-removed criterion → prune them here
    # (logged, part of APPLY_SPEC) so no stale mapping persists; the now-unmapped child surfaces via CHECK-1b.
    _valid = {c.name for c in task.spec.criteria}
    if any(m.criterion_name not in _valid for m in task.criterion_mappings):
        task.criterion_mappings = tuple(m for m in task.criterion_mappings if m.criterion_name in _valid)
    if effect.assignee is not None:  # reassign (Del change) via the same pre-acceptance channel
        if effect.assignee != task.assignee:
            task.was_reassigned = True  # q_Del
        task.assignee = effect.assignee
    graph.save_task(task)
    # covers on a re-author: the child (re)declares which parent criteria it covers (§2.2), appended (dedup) —
    # so a mapping can be set/preserved through re-ASSIGN, not only at CREATE_TASK.
    if effect.covers and task.parent_id:
        parent = graph.get_task(task.parent_id)
        if parent is not None:
            seen = {(m.criterion_name, m.child_id) for m in parent.criterion_mappings}
            new = tuple(CriterionMapping(c, task.id) for c in effect.covers if (c, task.id) not in seen)
            if new:
                parent.criterion_mappings = parent.criterion_mappings + new
                graph.save_task(parent)
    return []


def _increment_iteration(graph: Graph, task: Optional[Task]) -> list[TaskId]:
    if task is None:
        return []
    task.iteration += 1
    graph.save_task(task)
    return []


def _create_task(graph: Graph, effect: MutateGraph) -> list[TaskId]:
    if effect.spec is None:
        log.error(f"CREATE_TASK without spec for {effect.task_id}")
        return []
    task = Task(
        id=effect.task_id,
        spec=effect.spec,
        assignee=effect.assignee,
        parent_id=effect.parent_id,
        deadline=effect.deadline,
        max_iterations=effect.max_iterations,
    )
    graph.save_task(task)
    # Mapping = the child declares which parent criteria it covers (§2.2 non-redundancy). Recorded as a
    # logged effect of THIS child's ASSIGN, not a direct write to the parent. Appends (incremental-safe).
    if effect.covers and effect.parent_id:
        parent = graph.get_task(effect.parent_id)
        if parent is not None:
            seen = {(m.criterion_name, m.child_id) for m in parent.criterion_mappings}
            new = tuple(CriterionMapping(c, effect.task_id) for c in effect.covers
                        if (c, effect.task_id) not in seen)
            if new:
                parent.criterion_mappings = parent.criterion_mappings + new
                graph.save_task(parent)
    return []
