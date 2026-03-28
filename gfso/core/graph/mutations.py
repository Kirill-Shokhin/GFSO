"""Mutation -> G'. Returns affected child ids for cascade."""
from __future__ import annotations

import logging
from typing import Optional

from gfso.core.types import (
    TaskId, Task, State, Signal, MutationType, DoneReason,
    MutateGraph, TERMINAL_STATES,
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
    )
    graph.save_task(task)
    return []
