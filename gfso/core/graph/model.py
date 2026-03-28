"""G = (N, E_D, E_Dep, sigma). Wraps StoragePort."""
from __future__ import annotations

from typing import Optional

from gfso.core.types import (
    TaskId, AgentId, Task, State, Signal,
    GuardContext, GraphContext, CheckResult, Recommendation,
    DispatchPayload, StoragePort,
    TERMINAL_STATES,
)


class Graph:
    def __init__(self, storage: StoragePort):
        self._storage = storage

    def get_state(self, task_id: TaskId) -> Optional[State]:
        task = self._storage.get_task(task_id)
        return task.state if task else None

    def get_task(self, task_id: TaskId) -> Optional[Task]:
        return self._storage.get_task(task_id)

    def get_children(self, task_id: TaskId) -> list[Task]:
        return self._storage.get_children(task_id)

    def get_parent(self, task_id: TaskId) -> Optional[Task]:
        return self._storage.get_parent(task_id)

    def get_guard_context(self, task_id: TaskId) -> GuardContext:
        task = self._storage.get_task(task_id)
        if task is None:
            return GuardContext(iteration=0, max_iterations=3)
        return GuardContext(
            iteration=task.iteration,
            max_iterations=task.max_iterations,
        )

    def get_assignee(self, task_id: TaskId) -> Optional[AgentId]:
        task = self._storage.get_task(task_id)
        return task.assignee if task else None

    def active_tasks(self) -> list[Task]:
        return self._storage.get_active_tasks()

    def save_task(self, task: Task) -> None:
        self._storage.save_task(task)

    def build_context(self, task_id: TaskId) -> GraphContext:
        task = self._storage.get_task(task_id)
        if task is None:
            raise ValueError(f"task {task_id} not found")
        children = self._storage.get_children(task_id)
        parent = self._storage.get_parent(task_id)
        check_results = self._storage.get_check_results(task_id)
        recommendation = self._storage.get_recommendation(task_id)
        return GraphContext(
            task=task,
            children=tuple(children),
            parent=parent,
            check_results=tuple(check_results),
            recommendation=recommendation,
        )

    def build_dispatch_payload(self, task_id: TaskId, signal: Signal) -> DispatchPayload:
        task = self._storage.get_task(task_id)
        if task is None:
            raise ValueError(f"task {task_id} not found")
        check_results = self._storage.get_check_results(task_id)
        recommendation = self._storage.get_recommendation(task_id)
        return DispatchPayload(
            signal=signal,
            task=task,
            check_results=tuple(check_results),
            recommendation=recommendation,
        )

    def store_check_results(self, task_id: TaskId, results: list[CheckResult]) -> None:
        self._storage.store_check_results(task_id, results)

    def store_recommendation(self, task_id: TaskId, rec: Recommendation) -> None:
        self._storage.store_recommendation(task_id, rec)
