"""In-memory StoragePort implementation."""
from __future__ import annotations

from typing import Optional

from gfso.core.types import (
    TaskId, Task, CheckResult, Recommendation, DepEdge,
    StoragePort, TERMINAL_STATES,
)


class MemoryStorage(StoragePort):
    def __init__(self):
        self._tasks: dict[TaskId, Task] = {}
        self._children: dict[TaskId, list[TaskId]] = {}
        self._parent: dict[TaskId, TaskId] = {}
        self._check_results: dict[TaskId, list[CheckResult]] = {}
        self._recommendations: dict[TaskId, Recommendation] = {}
        self._dep_edges: list[DepEdge] = []
        self._critiques: dict[TaskId, str] = {}
        self._exec_verdicts: dict[TaskId, str] = {}
        self._deliver_results: dict[TaskId, str] = {}
        self._pipeline: list[dict] = []
        self._audit_rows: list[dict] = []

    def get_task(self, task_id: TaskId) -> Optional[Task]:
        return self._tasks.get(task_id)

    def save_task(self, task: Task) -> None:
        self._tasks[task.id] = task
        if task.parent_id is not None:
            self._parent[task.id] = task.parent_id
            self._children.setdefault(task.parent_id, [])
            if task.id not in self._children[task.parent_id]:
                self._children[task.parent_id].append(task.id)

    def get_all_tasks(self) -> list[Task]:
        return list(self._tasks.values())

    def get_children(self, task_id: TaskId) -> list[Task]:
        child_ids = self._children.get(task_id, [])
        return [self._tasks[cid] for cid in child_ids if cid in self._tasks]

    def get_parent(self, task_id: TaskId) -> Optional[Task]:
        parent_id = self._parent.get(task_id)
        if parent_id is None:
            return None
        return self._tasks.get(parent_id)

    def get_active_tasks(self) -> list[Task]:
        return [t for t in self._tasks.values() if t.state not in TERMINAL_STATES]

    def get_check_results(self, task_id: TaskId) -> list[CheckResult]:
        return self._check_results.get(task_id, [])

    def store_check_results(self, task_id: TaskId, results: list[CheckResult]) -> None:
        self._check_results[task_id] = results

    def get_recommendation(self, task_id: TaskId) -> Optional[Recommendation]:
        return self._recommendations.get(task_id)

    def store_recommendation(self, task_id: TaskId, rec: Recommendation) -> None:
        self._recommendations[task_id] = rec

    def store_critique(self, task_id: TaskId, critique_json: str) -> None:
        self._critiques[task_id] = critique_json

    def get_critique(self, task_id: TaskId) -> Optional[str]:
        return self._critiques.get(task_id)

    def store_exec_verdict(self, task_id: TaskId, verdict_json: str) -> None:
        self._exec_verdicts[task_id] = verdict_json

    def get_exec_verdict(self, task_id: TaskId):
        return self._exec_verdicts.get(task_id)

    def store_deliver_result(self, task_id: TaskId, result: str) -> None:
        self._deliver_results[task_id] = result

    def get_deliver_result(self, task_id: TaskId):
        return self._deliver_results.get(task_id)

    def log_pipeline(self, ts: str, source: str, message: str) -> None:
        self._pipeline.append({"ts": ts, "source": source, "message": message})
        del self._pipeline[:-10000]  # same pragmatic cap as sqlite

    def get_pipeline(self, limit: int = 500) -> list[dict]:
        return list(self._pipeline[-limit:])

    def add_dep_edge(self, edge: DepEdge) -> None:
        self._dep_edges.append(edge)

    def remove_dep_edge(self, from_id: TaskId, to_id: TaskId) -> None:
        self._dep_edges = [
            e for e in self._dep_edges if not (e.from_id == from_id and e.to_id == to_id)
        ]

    def get_dep_edges(self) -> list[DepEdge]:
        return list(self._dep_edges)

    # --- the MANDATORY append-only signal log (T11/Инв-7: state = fold(log)) ---
    # In-memory is this adapter's declared MEDIUM, not a contract degradation: the log is complete
    # and replayable for the process lifetime, exactly as ephemeral as every other record it holds.

    def append_audit(self, row: dict) -> None:
        self._audit_rows.append(dict(row))

    def load_audit(self) -> list[dict]:
        return [dict(r) for r in self._audit_rows]
