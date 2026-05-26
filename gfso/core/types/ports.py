from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Optional

from .primitives import (
    TaskId, AgentId, Task, CheckResult, Recommendation,
    DispatchPayload, SignalData, DepEdge, Spec,
)
from .enums import State


class StoragePort(ABC):
    @abstractmethod
    def get_task(self, task_id: TaskId) -> Optional[Task]:
        ...

    @abstractmethod
    def save_task(self, task: Task) -> None:
        ...

    @abstractmethod
    def get_all_tasks(self) -> list[Task]:
        ...

    @abstractmethod
    def get_children(self, task_id: TaskId) -> list[Task]:
        ...

    @abstractmethod
    def get_parent(self, task_id: TaskId) -> Optional[Task]:
        ...

    @abstractmethod
    def get_active_tasks(self) -> list[Task]:
        """All tasks in non-terminal states."""
        ...

    @abstractmethod
    def get_check_results(self, task_id: TaskId) -> list[CheckResult]:
        ...

    @abstractmethod
    def store_check_results(self, task_id: TaskId, results: list[CheckResult]) -> None:
        ...

    @abstractmethod
    def get_recommendation(self, task_id: TaskId) -> Optional[Recommendation]:
        ...

    @abstractmethod
    def store_recommendation(self, task_id: TaskId, rec: Recommendation) -> None:
        ...

    @abstractmethod
    def add_dep_edge(self, edge: DepEdge) -> None:
        ...

    @abstractmethod
    def get_dep_edges(self) -> list[DepEdge]:
        ...


class LLMProviderPort(ABC):
    @abstractmethod
    def complete(self, prompt: str, context: str = "") -> str:
        ...


class AgentPort(ABC):
    @abstractmethod
    def dispatch(self, agent_id: AgentId, payload: DispatchPayload) -> Optional[SignalData]:
        ...


class VerifierPort(ABC):
    """Runs deterministic verification of a deliverable against a Spec's criteria.

    Implementations are domain-specific (subprocess+stdin, pytest, schema-check, etc).
    Returns one CheckResult per criterion in spec.criteria, in the same order.
    """

    @abstractmethod
    def verify(self, task_id: TaskId, deliverable: str, spec: Spec) -> list[CheckResult]:
        ...
