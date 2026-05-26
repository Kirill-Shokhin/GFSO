"""GFSO Engine — Level 2 framework. Public API for building systems."""
from __future__ import annotations

import logging
import queue
import threading
from typing import Optional

from gfso.core.types import (
    Signal, State, SignalData, TaskId, AgentId,
    Spec, Task, CheckResult, Recommendation, CriterionMapping, DepEdge,
    LLMProviderPort, AgentPort, StoragePort,
    TERMINAL_STATES,
)
from gfso.core.graph import Graph, q_T, q_D, q_V, q_Dep, q_Del

from .audit import AuditLog, AuditEntry
from .events import EventBus, TransitionCallback, ErrorCallback, RejectCallback
from .loop import event_loop, timeout_monitor

log = logging.getLogger(__name__)


class Engine:
    """GFSO Engine — single entry point for building systems on the protocol.

    Usage:
        engine = Engine(storage, agents)
        engine.on_transition(my_callback)
        engine.start()
        engine.assign_task(spec, assignee)
        engine.send_signal(SignalData(...))
    """

    def __init__(
        self,
        storage: StoragePort,
        agents: AgentPort,
        llm: Optional[LLMProviderPort] = None,
        check_interval: float = 10.0,
        validate_signals: bool = True,
    ):
        self._graph = Graph(storage)
        self._agents = agents
        self._llm = llm
        self._check_interval = check_interval
        self._validate = validate_signals

        self._queue: queue.Queue[SignalData] = queue.Queue()
        self._stop = threading.Event()
        self._audit = AuditLog()
        self._events = EventBus()
        self._started = False

    # === Lifecycle ===

    def start(self) -> None:
        """Start event loop and timeout monitor."""
        if self._started:
            return
        self._started = True

        threading.Thread(
            target=event_loop,
            args=(self._graph, self._agents, lambda: self._llm, self._queue,
                  self._audit, self._events, self._validate),
            daemon=True,
        ).start()

        threading.Thread(
            target=timeout_monitor,
            args=(self._graph, self._queue, self._check_interval, self._stop),
            daemon=True,
        ).start()

    def stop(self) -> None:
        """Stop engine gracefully."""
        self._stop.set()
        self._queue.put(None)  # poison pill for event loop
        self._started = False

    # === Signal API ===

    def send_signal(self, signal_data: SignalData) -> None:
        """Send a signal into the engine. Primary entry point."""
        self._queue.put(signal_data)

    def assign_task(
        self,
        task_id: TaskId,
        spec: Spec,
        assignee: AgentId,
        parent_id: Optional[TaskId] = None,
        max_iterations: int = 3,
    ) -> Task:
        """Create a task and send ASSIGN signal. Convenience method."""
        task = Task(
            id=task_id, spec=spec, assignee=assignee,
            parent_id=parent_id, max_iterations=max_iterations,
        )
        self._graph.save_task(task)
        # ASSIGN is an issuer signal — source = parent's assignee or self
        parent = self._graph.get_task(parent_id) if parent_id else None
        source = parent.assignee if parent and parent.assignee else assignee
        self.send_signal(SignalData(signal=Signal.ASSIGN, task_id=task_id, spec=spec, source=source))
        return task

    # === Query API ===

    def get_task(self, task_id: TaskId) -> Optional[Task]:
        return self._graph.get_task(task_id)

    def get_state(self, task_id: TaskId) -> Optional[State]:
        return self._graph.get_state(task_id)

    def get_children(self, task_id: TaskId) -> list[Task]:
        return self._graph.get_children(task_id)

    def get_checks(self, task_id: TaskId) -> list[CheckResult]:
        return self._graph._storage.get_check_results(task_id)

    def active_tasks(self) -> list[Task]:
        return self._graph.active_tasks()

    # === Metrics API ===

    def metrics(self) -> dict[str, float]:
        return {
            "q_T": q_T(self._graph),
            "q_D": q_D(self._graph),
            "q_V": q_V(self._graph),
            "q_Dep": q_Dep(self._graph),
            "q_Del": q_Del(self._graph),
        }

    # === Events API ===

    def on_transition(self, callback: TransitionCallback) -> None:
        self._events.on_transition(callback)

    def on_error(self, callback: ErrorCallback) -> None:
        self._events.on_error(callback)

    def on_reject(self, callback: RejectCallback) -> None:
        self._events.on_reject(callback)

    # === Audit API ===

    def audit_log(self, task_id: Optional[TaskId] = None) -> list[AuditEntry]:
        return self._audit.get_entries(task_id)

    # === Decomposition API ===

    def decompose_task(
        self,
        parent_id: TaskId,
        children: list[tuple[TaskId, Spec, AgentId]],
        criterion_mappings: list[CriterionMapping] | None = None,
    ) -> list[Task]:
        """Atomic decomposition: create children with parent-child edges.

        Each child is (task_id, spec, assignee). Optionally provide
        CriterionMappings linking parent criteria to children.
        Creates all children, updates parent mappings, sends ASSIGN for each.
        """
        parent = self._graph.get_task(parent_id)
        if parent is None:
            raise ValueError(f"parent {parent_id} not found")

        if criterion_mappings:
            parent.criterion_mappings = tuple(criterion_mappings)
            self._graph.save_task(parent)

        created = []
        for child_id, spec, assignee in children:
            task = Task(
                id=child_id, spec=spec, assignee=assignee,
                parent_id=parent_id,
            )
            self._graph.save_task(task)
            self.send_signal(SignalData(signal=Signal.ASSIGN, task_id=child_id, spec=spec))
            created.append(task)

        return created

    # === Dependency API ===

    def add_dependency(self, from_id: TaskId, to_id: TaskId, discovered: bool = False) -> None:
        """Declare a dependency: from_id depends on to_id.

        discovered=True for deps found via BLOCK (not declared upfront).
        Affects q_Dep metric.
        """
        self._graph._storage.add_dep_edge(DepEdge(from_id, to_id, discovered))

    def get_dependencies(self) -> list[DepEdge]:
        return self._graph._storage.get_dep_edges()

    # === Extended Query API ===

    def tasks_by_state(self, state: State) -> list[Task]:
        return [t for t in self._graph._storage.get_all_tasks() if t.state == state]

    def tasks_by_assignee(self, assignee: AgentId) -> list[Task]:
        return [t for t in self._graph._storage.get_all_tasks() if t.assignee == assignee]

    def all_tasks(self) -> list[Task]:
        return self._graph._storage.get_all_tasks()

    # === Sync Signal API ===

    def send_signal_sync(self, signal_data: SignalData, timeout: float = 5.0) -> AuditEntry | None:
        """Send signal and wait for processing. Returns the audit entry."""
        done_event = threading.Event()
        result: list[AuditEntry] = []

        def _capture(tid, old_state, new_state, signal):
            if tid == signal_data.task_id and signal == signal_data.signal:
                entries = self._audit.get_entries(tid)
                if entries:
                    result.append(entries[-1])
                done_event.set()

        def _capture_reject(tid, signal, state):
            if tid == signal_data.task_id and signal == signal_data.signal:
                entries = self._audit.get_entries(tid)
                if entries:
                    result.append(entries[-1])
                done_event.set()

        self._events.on_transition(_capture)
        self._events.on_reject(_capture_reject)
        self._queue.put(signal_data)
        done_event.wait(timeout=timeout)

        # Clean up one-shot callbacks
        if _capture in self._events._on_transition:
            self._events._on_transition.remove(_capture)
        if _capture_reject in self._events._on_reject:
            self._events._on_reject.remove(_capture_reject)

        return result[0] if result else None

    # === Internal ===

    @property
    def graph(self) -> Graph:
        return self._graph

    def wait_idle(self, timeout: float = 5.0) -> None:
        """Wait for queue to drain. Useful for testing."""
        self._queue.join()
