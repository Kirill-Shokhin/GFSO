from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Optional

from .primitives import (
    TaskId, AgentId, Task, CheckResult, Recommendation,
    DispatchPayload, SignalData, DepEdge, Spec,
)


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
    def remove_dep_edge(self, from_id: TaskId, to_id: TaskId) -> None:
        ...

    @abstractmethod
    def get_dep_edges(self) -> list[DepEdge]:
        ...

    def store_critique(self, task_id: TaskId, critique_json: str) -> None:
        """Persist a node's L2 critique (the validation record). Default no-op so
        existing storages stay valid; memory/sqlite override."""
        ...

    def get_critique(self, task_id: TaskId) -> Optional[str]:
        return None

    def store_deliver_result(self, task_id: TaskId, result: str) -> None:
        """Persist the node's LAST DELIVER result (the deliverable pointer — the validator's input;
        must survive a server restart). Default no-op."""
        ...

    def get_deliver_result(self, task_id: TaskId) -> Optional[str]:
        return None

    def store_exec_verdict(self, task_id: TaskId, verdict_json: str) -> None:
        """Persist a node's EXECUTION-validation verdict (the validate_node record; ≠ critique = the
        PLAN's L2). One record per node — the current delivery's verdict. Default no-op."""
        ...

    def get_exec_verdict(self, task_id: TaskId) -> Optional[str]:
        return None

    def log_pipeline(self, ts: str, source: str, message: str) -> None:
        """Persist one pipeline observation line (live token TICKS are excluded by the caller —
        they update in place and are WS-only noise). Default no-op so existing storages stay valid."""
        ...

    def get_pipeline(self, limit: int = 500) -> list[dict]:
        """The most recent pipeline lines, oldest-first: [{ts, source, message}]."""
        return []


class LLMProviderPort(ABC):
    @abstractmethod
    def complete(self, prompt: str, context: str = "") -> str:
        ...

    def complete_structured(self, system: str, user: str, schema: dict) -> dict:
        """Native structured output: model fills `schema` (fields defined upfront).
        Default = degraded empty (no client); real provider overrides. Returns {} on failure."""
        return {}


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
