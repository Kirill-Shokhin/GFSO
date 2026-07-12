from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Optional

from .primitives import (
    TaskId, AgentId, Task, CheckResult, Recommendation,
    DispatchPayload, SignalData, DepEdge, Spec,
)


class StoragePort(ABC):
    """The persistence contract, split explicitly (the embedder's contract):

    MANDATORY CORE (abstract — an adapter cannot exist without them): task/child reads+writes,
    dep edges, check-result cache, AND the append-only signal log (`append_audit`/`load_audit`).
    The log is core, not an extension: the T11/Инв-7 guarantee `state = fold(log)` is CONDITIONED
    on log completeness — an adapter that silently drops entries voids the guarantee, so silence
    is not an option. An adapter whose MEDIUM is ephemeral (in-memory) still implements the log
    honestly for its lifetime; an adapter that consciously chooses not to persist it is a
    DECLARED degraded mode (no T11-over-restart, no replay) — declared in ITS code, never
    defaulted here.

    OPTIONAL EXTENSIONS (defaults below): critique / deliver-result / exec-verdict / pipeline
    records. Missing ones degrade individual features (named in each docstring), never the
    protocol guarantees."""

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

    @abstractmethod
    def append_audit(self, row: dict) -> None:
        """Append ONE signal-log entry (append-only — the T11/Инв-7 carrier; state = fold(log))."""
        ...

    @abstractmethod
    def load_audit(self) -> list[dict]:
        """The full signal log, oldest-first (hydrates the AuditLog on engine construction)."""
        ...

    # --- OPTIONAL EXTENSIONS (feature-level degraded modes, named per method) ---

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


class ClockPort(ABC):
    """The runtime's time source — Инв-5 (finiteness) enforcement reads THIS, never the wall clock
    directly, so a host can substitute virtual time (tests) or an anchored/tamper-resistant source
    (a real deployment; the clock-anchoring question is a DECLARED open end for implementors —
    the port is the seam, not the answer)."""

    @abstractmethod
    def now(self) -> float:
        """Current time as epoch seconds (comparable with datetime.timestamp())."""
        ...

    @abstractmethod
    def wait(self, seconds: float) -> None:
        """Park the calling monitor for `seconds` (virtual time may return immediately)."""
        ...


class SystemClock(ClockPort):
    """The stdlib default. Trivial zero-dependency defaults live WITH their port (the engine may
    import core only — the layer gate); heavier substrates are adapters."""

    def now(self) -> float:
        import time
        return time.time()

    def wait(self, seconds: float) -> None:
        import time
        time.sleep(seconds)


class RunnerPort(ABC):
    """The execution substrate: WHO pumps the signal queue and ticks the timeout monitor. The
    protocol step itself (validate → transition → effects → audit → events) is a pure function
    of one signal (`engine.loop.process_signal`) — this port only decides how it is driven, so
    an asyncio/distributed host swaps the substrate without touching the core."""

    @abstractmethod
    def new_queue(self):
        """A queue with put/get/task_done/join semantics for SignalData items."""
        ...

    @abstractmethod
    def spawn(self, target, name: str) -> None:
        """Run `target()` on the substrate (daemon semantics: dies with the host)."""
        ...


class ThreadRunner(RunnerPort):
    """The stdlib default: one daemon thread per loop, a thread-safe queue."""

    def new_queue(self):
        import queue
        return queue.Queue()

    def spawn(self, target, name: str) -> None:
        import threading
        threading.Thread(target=target, name=name, daemon=True).start()
