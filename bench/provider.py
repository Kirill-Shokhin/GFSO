"""BenchProvider: source of BenchTasks from a specific dataset."""
from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Iterator

from .task import BenchTask


class BenchProvider(ABC):
    """Loads tasks from a dataset, builds BenchTask instances with correct
    spec/verifier/hidden-eval for that dataset's conventions."""

    name: str = "bench"

    @abstractmethod
    def all_task_ids(self) -> list[str]:
        ...

    @abstractmethod
    def get_task(self, task_id: str) -> BenchTask:
        ...

    def iter_tasks(self, ids: list[str] | None = None) -> Iterator[BenchTask]:
        for tid in (ids or self.all_task_ids()):
            yield self.get_task(tid)
