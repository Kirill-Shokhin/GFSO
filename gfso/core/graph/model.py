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
            reopens=task.reopens,
            max_reopens=task.max_reopens,
            # Computed HERE, consumed by the pure FSM guard in the SAME process_signal step —
            # gate+edge are one log-serialized atomic act (Инв-7): a concurrent DELIVER that would
            # consume the node is still in the queue, it cannot interleave (no TOCTOU).
            consumed=self.is_consumed(task) if task.state in (State.DONE, State.CANCELLED) else True,
        )

    def is_public(self, task: Task) -> bool:
        """D6 (§6.5): public node ⟺ a DELEGATION SEAM — the node's scope of responsibility differs
        from its parent's, operationally Del(child) ≠ Del(parent), OR the node is a root (assigned
        into the graph by an external issuer — the one seam "done" must cross). An INTERNAL node
        (Del(child) = Del(parent)) is the agent's private decomposition: it SELF-verifies (DELIVER
        carries self_validation), and its guarantee is carried by the validation of the agent's
        public result (T1's non-redundancy direction). A missing/unassigned parent reads as a seam
        — fail-closed toward the stricter side."""
        if task.parent_id is None:
            return True
        parent = self.get_parent(task.id)
        if parent is None or parent.assignee is None or task.assignee is None:
            return True
        return parent.assignee != task.assignee

    def is_consumed(self, task: Task) -> bool:
        """R′ finality-gate (§6.3): a terminal is LOCALLY reversible ⟺ not consumed in the graph.
        Consumption is typed per edge sign and read from the STANDING graph state — a conservative,
        log-visible over-approximation of "the downstream cone presumes this node" (§6.3: the
        threshold moment is the one design freedom; we take delivered-upward / accepted-into-work).
        A stake withdrawn by an AUTHORIZED gated act (the parent itself reopened back to REVIEW)
        releases consumption — the chain unwinds one gated level at a time, each step in T11.

        POSITIVE (DONE): consumed ⟺ the parent staked its aggregate on V=pass — it DELIVERed upward
        (VALIDATING/REWORK/DONE are reachable only through DELIVER) — OR a Dep-consumer
        read-and-built on the result (EXECUTING/BLOCKED/VALIDATING/REWORK/DONE are reachable only
        through ACCEPT: the packet embeds upstream DELIVER results).

        NEGATIVE (CANCELLED, V=⊥ — no pass value): consumed ⟺ the cascade SETTLED (every descendant
        terminal) AND the parent REPLANNED around the hole — another active child covers a parent
        criterion this node covered (reviving it would double-cover, FM-1.e)."""
        if task.state == State.DONE:
            parent = self.get_parent(task.id)
            if parent is not None and parent.state in (
                    State.VALIDATING, State.REWORK, State.DONE):
                return True
            built_on = (State.EXECUTING, State.BLOCKED, State.VALIDATING, State.REWORK, State.DONE)
            for e in self.dep_edges():
                if e.from_id == task.id:
                    consumer = self.get_task(e.to_id)
                    if consumer is not None and consumer.state in built_on:
                        return True
            return False
        if task.state == State.CANCELLED:
            # cascade settled? — any live (non-terminal) descendant keeps the window open
            stack = [c for c in self.get_children(task.id)]
            while stack:
                n = stack.pop()
                if n.state not in (State.DONE, State.CANCELLED, State.ESCALATED):
                    return False
                stack.extend(self.get_children(n.id))
            # parent replanned around the hole? — a criterion this node covered is now covered
            # by another non-cancelled sibling (revival would double-cover, FM-1.e)
            parent = self.get_parent(task.id)
            if parent is None:
                return False
            mine = {m.criterion_name for m in parent.criterion_mappings if m.child_id == task.id}
            if not mine:
                return False
            for m in parent.criterion_mappings:
                if m.criterion_name in mine and m.child_id != task.id:
                    sibling = self.get_task(m.child_id)
                    if sibling is not None and sibling.state not in (State.CANCELLING, State.CANCELLED):
                        return True
            return False
        return True  # non-quasi-terminal states have no reopen question — fail-closed

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

    def exec_verdict_record(self, task_id: TaskId) -> Optional[dict]:
        """THE one reader of the stored independent-validation record ({verdict, failed_criteria,
        validator, iteration, ts} or None) — the self-PASS gate, q_V and false_fail_share all
        consume it; parsing lived in three copies before."""
        import json
        raw = self._storage.get_exec_verdict(task_id)
        if not raw:
            return None
        try:
            return json.loads(raw)
        except (ValueError, TypeError):
            return None

    def store_check_results(self, task_id: TaskId, results: list[CheckResult]) -> None:
        self._storage.store_check_results(task_id, results)

    def store_recommendation(self, task_id: TaskId, rec: Recommendation) -> None:
        self._storage.store_recommendation(task_id, rec)
