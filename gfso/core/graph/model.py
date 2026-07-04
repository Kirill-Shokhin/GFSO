"""G = (N, E_D, E_Dep, sigma). Wraps StoragePort."""
from __future__ import annotations

from typing import Optional

from gfso.core.types import (
    TaskId, AgentId, Task, State, Signal, DoneReason,
    GuardContext, GraphContext, CheckResult, Recommendation,
    DispatchPayload, StoragePort,
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
        """ALL children incl. CANCELLED tombstones — provenance view (§7.3.1: nothing deleted)."""
        return self._storage.get_children(task_id)

    def get_active_children(self, task_id: TaskId) -> list[Task]:
        """Children in the ACTIVE decomposition — excludes cancellation (CANCELLING/CANCELLED).

        A cancelled node persists in the graph forever (provenance, §7.3.1 / Утв.6) but is no longer
        part of the current decomposition: it must not count toward coverage / non-redundancy / the
        critic's view. Cancellation is authoritative (§6.3: the executor confirms, not disputes) — the
        node leaves the decomposition at CANCEL; CANCELLING is just the settlement of the handshake.
        DONE(PASS) and DONE(FAIL) children ARE active (delivered work)."""
        return [
            c for c in self._storage.get_children(task_id)
            if c.state not in (State.CANCELLING, State.CANCELLED)
        ]

    def get_parent(self, task_id: TaskId) -> Optional[Task]:
        return self._storage.get_parent(task_id)

    def dep_edges(self) -> list:
        """All dependency edges. DECLARED edges are DERIVED from criteria (§2.2): a criterion with
        `depends_on=X` means this task depends on X's output, with the criterion's description as the
        glue (anti-mock truth-maker) — Dep is criteria-content, not a standalone stored record.
        DISCOVERED edges (surfaced at runtime via BLOCK) remain stored. This is the single read path
        for every Dep consumer (checks / projection / q_Dep / cycle-check)."""
        from gfso.core.types import DepEdge
        edges = [
            DepEdge(from_id=c.depends_on, to_id=t.id, discovered=False, glue=c.description)
            for t in self._storage.get_all_tasks()
            if t.state not in (State.CANCELLING, State.CANCELLED)  # cancellation excluded (§6.3)
            for c in t.spec.criteria
            if c.depends_on
        ]
        edges.extend(self._storage.get_dep_edges())  # discovered (BLOCK) / legacy-stored
        return edges

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
        children = self.get_active_children(task_id)  # solver/checks judge the ACTIVE decomposition
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
