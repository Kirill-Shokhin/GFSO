"""G = (N, E_D, E_Dep, sigma). Wraps StoragePort."""
from __future__ import annotations

import json
from typing import Optional

from gfso.core.types import (
    TaskId, AgentId, Task, State, Signal, Verdict,
    GuardContext, GraphContext, CheckResult, Recommendation,
    DispatchPayload, DepEdge, StoragePort,
)


def verdict_is_current_pass(rec: dict | None, task) -> bool:
    """Is this recorded verdict a PASS that belongs to the node's CURRENT delivery?

    The question — "does a fresh independent verdict stand here" — was asked in four places with
    three different arities and three different notions of "fresh": one compared reopens only, one
    compared iteration and reopens, one added revisions, and one asked nothing about generation at
    all. They gate a self-PASS at the seam, void a verdict on revision, and feed q_V, so a
    disagreement between them is a disagreement about whether work is accepted.

    The generation is (iteration, reopens, revisions) — the contract-and-delivery stamp §14.3 needs:
    a rework moves the first, a REOPEN the second (the pre-reopen pass must not re-open the gate
    from the past), and a revision the third, because a validator still running on a voided delivery
    can land its verdict afterwards carrying the same first two.
    """
    if not rec or rec.get("verdict") != Verdict.PASS:
        return False
    return all(rec.get(k, 0) == getattr(task, k, 0) for k in ("iteration", "reopens", "revisions"))


def generation_of_task(t) -> tuple:
    """The generation of a node you already HOLD: (iteration, reopens, revisions).

    Same fact as `Graph.generation_of`, for callers that have the object rather than its id — and
    the reason it exists is that they were each spelling it as three defensive `getattr` reads with
    their own defaults. The fields are DECLARED, so they are read as declared: a `getattr` with a
    default over a declared field says the field might not be there, which is a false statement
    about this type and the thing the coupling instrument counts.
    """
    return (t.iteration, t.reopens, t.revisions) if t is not None else (0, 0, 0)


class Graph:
    def __init__(self, storage: StoragePort):
        self._storage = storage
        # WHO MAY SPEAK AS THE ISSUER'S ROLE-V INSTRUMENT (§14.5): the registered `llm-validator` /
        # `unittest-checker` ids, published downward by the dispatcher each round. Declared here
        # because two validation rules read it — who may sign PASS/FAIL at all, and whether a seam's
        # PASS still needs a recorded verdict — and a field born outside `__init__` had both of them
        # reading it defensively, which is how a rule silently becomes "empty set" on any graph the
        # dispatcher never touched.
        self.authorized_validators: set[str] = set()
        # …and who the dispatcher will DRIVE. A promise like "the block is then resolved for you" is
        # true only where something automated holds the node; on a person's node the signal stays
        # theirs (§14.5). Published downward by the dispatcher, beside the validators.
        self.authorized_executors: set[str] = set()

    def get_state(self, task_id: TaskId) -> Optional[State]:
        """The node's current state, or `None` if this id is not in the graph. `None` is what the
        protocol step reads as "unknown node" — it is not a state."""
        task = self._storage.get_task(task_id)
        return task.state if task else None

    def get_task(self, task_id: TaskId) -> Optional[Task]:
        return self._storage.get_task(task_id)

    def get_children(self, task_id: TaskId) -> list[Task]:
        """ALL children incl. ABANDONED tombstones — provenance view (§15.1: nothing deleted)."""
        return self._storage.get_children(task_id)

    def get_active_children(self, task_id: TaskId) -> list[Task]:
        """Children in the ACTIVE decomposition — excludes cancellation (CANCELLING/ABANDONED).

        A cancelled node persists in the graph forever (provenance, §15.1 / Prop 6) but is no longer
        part of the current decomposition: it must not count toward coverage / non-redundancy / the
        critic's view. Cancellation is authoritative (§14.3: the executor confirms, not disputes) — the
        node leaves the decomposition at CANCEL; CANCELLING is just the settlement of the handshake.
        DONE(PASS) and DONE(FAIL) children ARE active (delivered work)."""
        return [
            c for c in self._storage.get_children(task_id)
            if c.state not in (State.CANCELLING, State.ABANDONED)
        ]

    def non_leaf_ids(self, children: list[Task]) -> set[str]:
        """Which of these children decompose further — the fact CHECK-6 needs and a single split
        does not carry (§13.4 quantifies over LEAVES). A node that splits is accountable through its
        own children; demanding an executor for it reads Del as a label rather than as §10's
        per-node accountability."""
        return {str(c.id) for c in children if self.get_active_children(c.id)}

    def get_parent(self, task_id: TaskId) -> Optional[Task]:
        return self._storage.get_parent(task_id)

    def dep_edges(self) -> list:
        """All dependency edges. DECLARED edges are DERIVED from criteria (§10): a criterion with
        `depends_on=X` means this task depends on X's output, with the criterion's description as the
        glue (anti-mock truth-maker) — Dep is criteria-content, not a standalone stored record.
        DISCOVERED edges (surfaced at runtime via BLOCK) remain stored. This is the single read path
        for every Dep consumer (checks / projection / q_Dep / cycle-check)."""
        edges = [
            DepEdge(from_id=c.depends_on, to_id=t.id, discovered=False, glue=c.description)
            for t in self._storage.get_all_tasks()
            if t.state not in (State.CANCELLING, State.ABANDONED)  # cancellation excluded (§14.3)
            for c in t.spec.criteria
            if c.depends_on
        ]
        edges.extend(self._storage.get_dep_edges())  # discovered (BLOCK) / legacy-stored
        return edges

    def get_guard_context(self, task_id: TaskId) -> GuardContext:
        """What the FSM needs to decide a transition beyond the state itself: the rework counter and
        its cap, the reopen counter and its cap, and whether this terminal is consumed (§14.3).

        Assembled here because a guard that read the graph itself would make the transition depend on
        storage, and the point of the FSM is that it does not."""
        task = self._storage.get_task(task_id)
        if task is None:
            return GuardContext(iteration=0, max_iterations=3)
        return GuardContext(
            iteration=task.iteration,
            max_iterations=task.max_iterations,
            reopens=task.reopens,
            max_reopens=task.max_reopens,
            # Computed HERE, consumed by the pure FSM guard in the SAME process_signal step —
            # gate+edge are one log-serialized atomic act (Inv-7): a concurrent DELIVER that would
            # consume the node is still in the queue, it cannot interleave (no TOCTOU).
            consumed=self.is_consumed(task) if task.state in (State.DONE, State.ABANDONED) else True,
        )

    def is_public(self, task: Task) -> bool:
        """D6 (§14.5): public node ⟺ a DELEGATION SEAM — the node's scope of responsibility differs
        from its parent's, operationally Del(child) ≠ Del(parent), OR the node is a root (assigned
        into the graph by an external issuer — the one seam "done" must cross). An INTERNAL node
        (Del(child) = Del(parent)) is the agent's private decomposition: it SELF-verifies (DELIVER
        carries self_validation), and its guarantee is carried by the validation of the agent's
        public result (Thm 1's non-redundancy direction). A missing/unassigned parent reads as a seam
        — fail-closed toward the stricter side."""
        if task.parent_id is None:
            return True
        parent = self.get_parent(task.id)
        if parent is None or parent.assignee is None or task.assignee is None:
            return True
        return parent.assignee != task.assignee

    def is_consumed(self, task: Task) -> bool:
        """R′ finality-gate (§14.3): a terminal is LOCALLY reversible ⟺ not consumed in the graph.
        Consumption is typed per edge sign and read from the STANDING graph state — a conservative,
        log-visible over-approximation of "the downstream cone presumes this node" (§14.3: the
        threshold moment is the one design freedom; we take delivered-upward / accepted-into-work).
        A stake withdrawn by an AUTHORIZED gated act (the parent itself reopened back to OFFERED)
        releases consumption — the chain unwinds one gated level at a time, each step in Thm 11.

        POSITIVE (DONE): consumed ⟺ the parent staked its aggregate on V=pass — it DELIVERed upward
        and the stake is LIVE: VALIDATING (delivery pending judgment) or DONE (accepted). A parent
        in REWORKING does NOT lock: its delivery was REFUSED (FAIL) — the stake died with the refusal,
        and rework is exactly when the executor must be able to reopen the failing child (otherwise
        the only legal move is mutating the artifact under frozen-DONE children — the graph stops
        telling the truth about where the defect lives; observed live, BCB/93 run 9). A Dep-consumer
        that read-and-built keeps locking regardless of its state — information transfer is not
        undone by the consumer's own rework (EXECUTING/BLOCKED/VALIDATING/REWORKING/DONE are reachable
        only through ACCEPT: the packet embeds upstream DELIVER results).

        NEGATIVE (ABANDONED, V=⊥ — no pass value): consumed ⟺ the cascade SETTLED (every descendant
        terminal) AND the parent REPLANNED around the hole — another active child covers a parent
        criterion this node covered (reviving it would double-cover, FM-1.e)."""
        if task.state == State.DONE:
            parent = self.get_parent(task.id)
            if parent is not None and parent.state in (State.VALIDATING, State.DONE):
                return True
            built_on = (State.EXECUTING, State.BLOCKED, State.VALIDATING, State.REWORKING, State.DONE)
            for e in self.dep_edges():
                if e.from_id == task.id:
                    consumer = self.get_task(e.to_id)
                    if consumer is not None and consumer.state in built_on:
                        return True
            return False
        if task.state == State.ABANDONED:
            # cascade settled? — any live (non-terminal) descendant keeps the window open
            stack = [c for c in self.get_children(task.id)]
            while stack:
                n = stack.pop()
                if n.state not in (State.DONE, State.ABANDONED, State.ESCALATED):
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
                    if sibling is not None and sibling.state not in (State.CANCELLING, State.ABANDONED):
                        return True
            return False
        return True  # non-quasi-terminal states have no reopen question — fail-closed

    def get_assignee(self, task_id: TaskId) -> Optional[AgentId]:
        """Who holds this node (Del) — the only party whose signals it moves on."""
        task = self._storage.get_task(task_id)
        return task.assignee if task else None

    def active_tasks(self) -> list[Task]:
        """Every node not in a terminal state. What "settled" means is the graph's to say, and it says
        it once: two spellings of it disagreed about an ESCALATED child and cost a paid run."""
        return self._storage.get_active_tasks()

    def save_task(self, task: Task) -> None:
        self._storage.save_task(task)

    def build_context(self, task_id: TaskId) -> GraphContext:
        """The node plus its neighbourhood — parent, children, dep edges — as the AI layer reads it."""
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
        """The packet handed to a participant on ASSIGN: the contract, and nothing about how it was
        derived. What is NOT here is deliberate — an executor that could read the plan around it
        would be judged on a contract it did not consent to (Inv-1)."""
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

    def generation_of(self, task_id: TaskId) -> tuple:
        """The node's CONTRACT-AND-DELIVERY generation: (iteration, reopens, revisions).

        A verdict is about the delivery a validator READ, so it must be stamped with the generation
        that stood when the run STARTED — stamping at record time makes a late verdict describe
        whatever the node has become since (a rework, a reopen, or a revision under §14.3), which is
        exactly the state the self-PASS gate then reads as current. A graph fact, owned here: the
        engine asks it, the signal pump asks it, and `verdict_is_current_pass` compares against it."""
        t = self.get_task(task_id)
        # A node that is not there has no generation; the fields themselves are declared, so they
        # are read as declared.
        return generation_of_task(t)

    def exec_verdict_record(self, task_id: TaskId) -> Optional[dict]:
        """THE one reader of the stored independent-validation record ({verdict, failed_criteria,
        validator, iteration, ts} or None) — the self-PASS gate, q_V and false_fail_share all
        consume it; parsing lived in three copies before."""
        raw = self._storage.get_exec_verdict(task_id)
        if not raw:
            return None
        try:
            return json.loads(raw)
        except (ValueError, TypeError):
            return None

    def void_pending_pass(self, task_id: TaskId, reason: str) -> None:
        """Void a recorded PASS whose delivery no longer stands (§14.3/§6.3: a re-ASSIGN "voids the
        pending delivery" — the node re-earns its verdict through ACCEPT→DELIVER→VALIDATE).

        Only a PASS is voided. A recorded FAIL is left exactly as it is: it opens no gate, and it
        carries the refutation the re-delivery disposition reads (the criteria snapshot that tells a
        repair from a lowered criterion). The record is rewritten in place — this store holds the
        CURRENT verdict and always did ("the superseded record is replaced, never trusted forward");
        the event itself stays in the log (Inv-7)."""
        rec = self.exec_verdict_record(task_id)
        if not rec or rec.get("verdict") != Verdict.PASS:
            return
        rec = dict(rec, verdict="VOID", superseded_verdict=Verdict.PASS, voided_because=reason)
        self._storage.store_exec_verdict(task_id, json.dumps(rec))

    def store_check_results(self, task_id: TaskId, results: list[CheckResult]) -> None:
        self._storage.store_check_results(task_id, results)

    def store_recommendation(self, task_id: TaskId, rec: Recommendation) -> None:
        self._storage.store_recommendation(task_id, rec)
