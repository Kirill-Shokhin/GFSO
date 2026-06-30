"""GFSO Engine — Level 2 framework. Public API for building systems."""
from __future__ import annotations

import logging
import queue
import threading
from datetime import datetime
from typing import Optional

from gfso.core.types import (
    Signal, State, SignalData, TaskId, AgentId,
    Spec, Criteria, Task, CheckResult, Recommendation, CriterionMapping, DepEdge,
    LLMProviderPort, AgentPort, StoragePort,
    TERMINAL_STATES, DoneReason,
)
from gfso.core.graph import Graph, q_T, q_D, q_V, q_Dep, q_Del
from gfso.core.graph.projection import build as build_projection, render as render_projection
from gfso.core.protocol.fsm import available_signals
from gfso.core.protocol.validation import required_role, Role
from gfso.core.handlers.structural import check_dag

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
        critique_log_path: Optional[str] = None,
    ):
        self._graph = Graph(storage)
        self._agents = agents
        self._llm = llm
        self._check_interval = check_interval
        self._validate = validate_signals
        self._critique_log_path = critique_log_path

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
        deadline: Optional[datetime] = None,
    ) -> Task:
        """Create a task and send ASSIGN signal. Convenience method.

        deadline completes the T=(spec, criteria, deadline) primitive (§2.2);
        without it CHECK-3 (deadline consistency) is vacuous.
        """
        # Creation is the ASSIGN effect (CREATE_TASK), logged — no unlogged pre-save. ASSIGN is an
        # issuer signal: source = parent's assignee or self. send_signal_sync so the node exists on return.
        parent = self._graph.get_task(parent_id) if parent_id else None
        source = parent.assignee if parent and parent.assignee else assignee
        self.send_signal_sync(SignalData(
            signal=Signal.ASSIGN, task_id=task_id, spec=spec, source=source,
            assignee=assignee, parent_id=parent_id, deadline=deadline, max_iterations=max_iterations,
        ))
        if parent_id:
            # cross-node invalidation: a (re-)assigned child changes the parent's
            # CHECK-1/CHECK-7 (coverage / sufficiency read child criteria) → recompute + dirty.
            self._recompute_checks(parent_id)
        return self._graph.get_task(task_id)

    # === Authoring operations (UPPER layer — desugar to the 12 signals, NOT new signals) ===

    def revise(self, task_id: TaskId, new_spec: Spec, agent: AgentId) -> Task:
        """Re-author a node's spec — canon §6.4 Inv-1: a spec is IMMUTABLE after ASSIGN, so a change is
        **CANCEL + re-ASSIGN**, never an in-place edit. The old node becomes a tombstone (§7.3.1, its id
        spent); a fresh node (new id) carries `new_spec`, the same parent/Del, and re-declares the parent
        criteria it covered. Returns the NEW node (its id differs from `task_id`).

        `agent` must be the issuer (CANCEL and ASSIGN are issuer signals — the FSM validates). The subtree is
        RETAINED (revise ≠ abandon — the node continues under a new contract, same id): re-authoring does NOT
        cascade-cancel children. If a criteria change stales a child's coverage, that surfaces as a CHECK-1
        failure the agent must resolve (surface-don't-destroy). Only a genuine abandon (raw CANCEL) cascades.
        The only IN-PLACE spec change is ACCEPT_CHALLENGE (executor-initiated negotiation, FM-7→FM-5).
        """
        return self._cancel_and_reassign(task_id, new_spec, agent)

    def reneglect(self, task_id: TaskId, neglected: tuple, agent: AgentId) -> Task:
        """UPPER convenience = read-modify-write over REVISE: replace a node's NEGLECTED, keep the rest.
        Desugars to the lower signal path (no new command, no bypass). The whole packet is re-sent; the
        unchanged fields are carried for you (the human/agent edits one field)."""
        t = self._graph.get_task(task_id)
        if t is None:
            raise ValueError(f"task {task_id} not found")
        new_spec = Spec(t.spec.description, t.spec.criteria, tuple(neglected), t.spec.risk_components,
                        name=t.spec.name)
        return self.revise(task_id, new_spec, agent)

    def edit_criteria(self, task_id: TaskId, criteria: tuple, agent: AgentId) -> Task:
        """UPPER convenience = RMW over REVISE: replace a node's criteria, keep description/NEGLECTED.
        Dep criteria (depends_on) are part of `criteria` — pass the full set (RMW carries the unchanged)."""
        t = self._graph.get_task(task_id)
        if t is None:
            raise ValueError(f"task {task_id} not found")
        new_spec = Spec(t.spec.description, tuple(criteria), t.spec.neglected, t.spec.risk_components,
                        name=t.spec.name)
        return self.revise(task_id, new_spec, agent)

    def reassign(self, task_id: TaskId, new_assignee: AgentId) -> Task:
        """UPPER: change a node's executor (Del). Canon Inv-1 fixes Del(t) at ASSIGN too → a change is
        CANCEL + re-ASSIGN with the new executor (the issuer acts; q_Del↑). Returns the NEW node."""
        t = self._graph.get_task(task_id)
        if t is None:
            raise ValueError(f"task {task_id} not found")
        parent = self._graph.get_parent(task_id)
        issuer = parent.assignee if parent and parent.assignee else t.assignee
        return self._cancel_and_reassign(task_id, t.spec, issuer, new_assignee=new_assignee)

    # === Query API ===

    def get_task(self, task_id: TaskId) -> Optional[Task]:
        return self._graph.get_task(task_id)

    def get_state(self, task_id: TaskId) -> Optional[State]:
        return self._graph.get_state(task_id)

    def get_children(self, task_id: TaskId) -> list[Task]:
        """ALL children incl. CANCELLED tombstones (provenance, §7.3.1)."""
        return self._graph.get_children(task_id)

    def get_active_children(self, task_id: TaskId) -> list[Task]:
        """Children in the ACTIVE decomposition (excludes CANCELLED tombstones). The unit the critic
        and correctness checks reason over — a removed (cancelled) node persists for provenance but no
        longer participates in coverage/non-redundancy/projection."""
        return self._graph.get_active_children(task_id)

    def get_checks(self, task_id: TaskId) -> list[CheckResult]:
        """Read the CACHED L0/L1 checks (O(1)) — kept fresh by _recompute_checks on
        every decomposition change (cheap eager invalidation). Many watchers read this
        without recomputing."""
        return self._graph._storage.get_check_results(task_id)

    def _recompute_checks(self, node_id: TaskId) -> None:
        """Recompute + cache a node's L0/L1+anti-mock checks AND mark its L2 stale
        (verified=False). Eager invalidation: called on any change to the node's
        decomposition (decompose, dep add/remove, child spec change)."""
        from gfso.core.handlers import run_all_checks
        node = self._graph.get_task(node_id)
        if node is None:
            return
        children = self._graph.get_active_children(node_id)  # cancelled tombstones excluded from checks
        deps = self._graph.dep_edges()
        self._graph.store_check_results(node_id, run_all_checks(node, children, deps))
        if node.verified:  # decomposition changed → stored L2 verdict no longer current
            node.verified = False
            self._graph.save_task(node)

    # === L2 critic / validation API ===

    def validate_decomposition(self, node_id: TaskId, llm: Optional[LLMProviderPort] = None):
        """L2 validate — currently the STRUCTURAL gate only (cached L0/L1, eager-fresh). The semantic
        hole-hunt (search(diff)⊕audit, the same machinery as decompose) is deferred — see gfso/critic.
        Stores the critique as the validation record + sets verified=True (advisory). Returns a NodeCritique."""
        import json
        from dataclasses import asdict
        from gfso.critic.runner import critique_node
        critique = critique_node(self, node_id, llm or self._llm)
        self._graph._storage.store_critique(node_id, json.dumps(asdict(critique)))
        node = self._graph.get_task(node_id)
        if node is not None:
            node.verified = True  # critique is now current for this decomposition
            self._graph.save_task(node)
        self._log_critique(critique)
        return critique

    def get_critique(self, node_id: TaskId) -> Optional[dict]:
        import json
        raw = self._graph._storage.get_critique(node_id)
        return json.loads(raw) if raw else None

    def _log_critique(self, critique) -> None:
        """Append a JSONL line per validation — the raw material for coverage curves."""
        if not self._critique_log_path:
            return
        import json
        from datetime import datetime
        rec = {
            "ts": datetime.now().isoformat(),
            "node": critique.node_id,
            "gate_passed": critique.gate_passed,
            "l0l1_failures": list(critique.l0l1_failures),
            "n_holes": len(critique.holes),
            "n_confirmed": len(critique.confirmed),
            "n_dismissed": len(critique.holes) - len(critique.confirmed) if critique.gate_passed else 0,
        }
        with open(self._critique_log_path, "a", encoding="utf-8") as f:
            f.write(json.dumps(rec) + "\n")

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
        children: list[tuple],
        criterion_mappings: list[CriterionMapping] | None = None,
    ) -> list[Task]:
        """Atomic decomposition: create children with parent-child edges.

        Each child is (task_id, spec, assignee) or (task_id, spec, assignee, deadline).
        Optionally provide CriterionMappings linking parent criteria to children.
        Creates all children, updates parent mappings, sends ASSIGN for each.
        """
        parent = self._graph.get_task(parent_id)
        if parent is None:
            raise ValueError(f"parent {parent_id} not found")

        # A mapping is the CHILD's declaration of which parent criteria it covers — carried on that child's
        # ASSIGN (`covers`) and written to the parent as a logged CREATE_TASK effect. No direct parent write.
        covers_by_child: dict = {}
        for m in (criterion_mappings or []):
            covers_by_child.setdefault(m.child_id, []).append(m.criterion_name)

        # ASSIGN is an issuer signal — source = the parent's assignee (the issuer of these children).
        # Each child is CREATED by its ASSIGN effect (logged), no unlogged pre-save. Sync so they exist.
        source = parent.assignee
        created = []
        for child_id, spec, assignee, *rest in children:
            deadline = rest[0] if rest else None
            self.send_signal_sync(SignalData(
                signal=Signal.ASSIGN, task_id=child_id, spec=spec, source=source,
                assignee=assignee, parent_id=parent_id, deadline=deadline,
                covers=tuple(covers_by_child.get(child_id, [])),
            ))
            created.append(self._graph.get_task(child_id))

        self._recompute_checks(parent_id)  # eager: parent's checks now reflect its children
        return created

    # === Dependency API ===

    def add_dependency(self, from_id: TaskId, to_id: TaskId, discovered: bool = False, glue: str = "") -> None:
        """Record a dependency: to_id depends on from_id's output.

        DECLARED (discovered=False): Dep is **criteria-content** (§2.2) — recorded as a criterion on the
        CONSUMER (to_id) referencing from_id (glue = its description), applied via REVISE (logged, no
        bypass). A cycle is rejected (CHECK-2 / FM-4). The DepEdge is then DERIVED (graph.dep_edges()).
        DISCOVERED (discovered=True, surfaced via BLOCK): runtime provenance — stored as an edge, even if
        cyclic (the cycle IS the FM-4 finding to surface, not hide). Affects q_Dep.
        """
        if discovered:
            # OPEN ENDPOINT (v2/E3, BLOCK-provenance): this is the ONE remaining graph-relation write that does
            # NOT go through a signal (a direct storage edge). Today it is DORMANT — no signal emits it (BLOCK
            # records no edge) and it is off every interface surface (tools/api/mcp/cli pass discovered=False).
            # TODO: route discovered deps through a logged BLOCK effect so this too is a signal-driven mutation.
            self._graph._storage.add_dep_edge(DepEdge(from_id, to_id, True, glue))
            self._recompute_seam_parents(from_id, to_id)
            return
        edges = [(e.from_id, e.to_id) for e in self._graph.dep_edges()]
        edges.append((from_id, to_id))
        if not check_dag(self._graph._storage.get_all_tasks(), edges).passed:
            raise ValueError(f"dependency {from_id} -> {to_id} would create a cycle")
        to = self._graph.get_task(to_id)
        if to is None:
            raise ValueError(f"consumer {to_id} not found")
        if not any(c.depends_on == from_id for c in to.spec.criteria):  # idempotent
            dep_crit = Criteria(name=f"dep__{from_id}", description=glue, depends_on=from_id)
            new_spec = Spec(to.spec.description, to.spec.criteria + (dep_crit,),
                            to.spec.neglected, to.spec.risk_components, name=to.spec.name)
            self._cancel_and_reassign(to_id, new_spec, self._issuer_of(to_id))
        self._recompute_seam_parents(from_id, to_id)

    def remove_dependency(self, from_id: TaskId, to_id: TaskId) -> None:
        """Drop a dependency. Declared → remove the consumer's dep criterion (re-author); also clears
        any stored (discovered) edge for the pair."""
        to = self._graph.get_task(to_id)
        if to is not None and any(c.depends_on == from_id for c in to.spec.criteria):
            new_crits = tuple(c for c in to.spec.criteria if c.depends_on != from_id)
            new_spec = Spec(to.spec.description, new_crits, to.spec.neglected, to.spec.risk_components,
                            name=to.spec.name)
            self._cancel_and_reassign(to_id, new_spec, self._issuer_of(to_id))
        self._graph._storage.remove_dep_edge(from_id, to_id)
        self._recompute_seam_parents(from_id, to_id)

    def _issuer_of(self, task_id: TaskId) -> AgentId:
        """The node's issuer = the parent's assignee, or the node itself for a root."""
        t = self._graph.get_task(task_id)
        parent = self._graph.get_parent(task_id)
        return parent.assignee if parent and parent.assignee else t.assignee

    def map_criterion(self, parent_id: TaskId, child_id: TaskId, criterion_name: str) -> Task:
        """Bind an EXISTING child to a parent criterion (add/repair a coverage mapping) — the op that was
        missing: `decompose` only maps NEW children. Declared as the child's `covers` via a LOGGED re-author
        (CANCEL + re-ASSIGN of the child; APPLY_SPEC appends the mapping to the parent) — NO direct parent
        write, so the closed-FSM 'every mutation is a logged signal' invariant holds. A stale mapping from an
        earlier parent criteria-change is already pruned at that re-author, so there is nothing to clean here."""
        parent = self._graph.get_task(parent_id)
        child = self._graph.get_task(child_id)
        if parent is None:
            raise ValueError(f"parent {parent_id} not found")
        if child is None:
            raise ValueError(f"child {child_id} not found")
        if criterion_name not in {c.name for c in parent.spec.criteria}:
            raise ValueError(f"no criterion '{criterion_name}' on parent {parent_id}")
        self._cancel_and_reassign(child_id, child.spec, self._issuer_of(child_id), covers=(criterion_name,))
        return self._graph.get_task(parent_id)

    def _cancel_and_reassign(self, task_id: TaskId, new_spec: Spec, agent: AgentId,
                             new_assignee: Optional[AgentId] = None, covers: tuple = ()) -> Task:
        """Canon Inv-1 (§6.4): a spec/Del change = CANCEL + re-ASSIGN under the SAME id, never an in-place
        mutation. CANCELs the node (its old contract a logged tombstone, §7.3.1; cascades the subtree —
        empty for a leaf in planning) then re-ASSIGNs the same id with `new_spec` + the (possibly new)
        executor → REVIEW. The id-slot persists so references (the parent's mapping, dependents' depends_on)
        stay valid — re-id would break the graph. `agent` must be the issuer (CANCEL & ASSIGN are issuer
        signals → FSM-validated). Returns the re-authored node."""
        old = self._graph.get_task(task_id)
        if old is None:
            raise ValueError(f"task {task_id} not found")
        # reassigning=True → this CANCEL is a revise, not an abandon: the subtree is NOT cascaded (the node
        # continues under a new contract). Any coverage staleness from a criteria change surfaces via the
        # recomputed CHECKs, not by destroying valid sub-work (surface-don't-destroy).
        c = self.send_signal_sync(SignalData(signal=Signal.CANCEL, task_id=task_id, source=agent,
                                             reassigning=True))
        if c is None or c.rejected:
            raise ValueError(
                f"revise rejected at CANCEL (state={self.get_state(task_id)}): the node is terminal, or "
                f"the agent is not its issuer.")
        a = self.send_signal_sync(SignalData(
            signal=Signal.ASSIGN, task_id=task_id, spec=new_spec, source=agent,
            assignee=new_assignee or old.assignee, covers=tuple(covers)))
        if a is None or a.rejected:
            raise ValueError(f"revise rejected at re-ASSIGN (state={self.get_state(task_id)}).")
        self._recompute_checks(task_id)          # the node kept its subtree → refresh its own coverage/checks
        if old.parent_id:
            self._recompute_checks(old.parent_id)
        return self._graph.get_task(task_id)

    def _recompute_seam_parents(self, from_id: TaskId, to_id: TaskId) -> None:
        """A Dep change affects the checks (DAG/deadlines/anti-mock) of the node whose
        children include the seam — recompute each endpoint's parent."""
        seen = set()
        for nid in (from_id, to_id):
            t = self._graph.get_task(nid)
            if t and t.parent_id and t.parent_id not in seen:
                seen.add(t.parent_id)
                self._recompute_checks(t.parent_id)

    def get_dependencies(self) -> list[DepEdge]:
        return self._graph.dep_edges()

    # === Projection API (read-only critic input contract) ===

    def project(self, node_id: TaskId) -> str:
        """Read-only markdown projection of a node's decomposition (critic input).

        The unit a semantic critic reasons over: goal + breakdown (subtasks,
        criteria, coverage, seams, NEGLECTED) + already-run Solver checks.
        """
        node = self._graph.get_task(node_id)
        if node is None:
            raise ValueError(f"node {node_id} not found")
        children = self._graph.get_active_children(node_id)  # critic reasons over the ACTIVE decomposition
        deps = self._graph.dep_edges()
        checks = self.get_checks(node_id)  # one on-demand path (no stale store)
        # Build the typed NodeProjection, then render it at the LLM/API str boundary.
        return render_projection(build_projection(node, children, deps, checks))

    # === Actions API (per-role affordances, §6.2) ===

    def available_actions(self, task_id: TaskId, agent_id: Optional[AgentId] = None) -> list[Signal]:
        """Signals valid in this task's current state, filtered by the agent's role.

        Role is derived structurally: executor = task.assignee; issuer = parent.assignee.
        agent_id=None → all non-system signals for the state (UI shows everything).
        System signals (TIMEOUT) are never offered as actions.
        """
        task = self._graph.get_task(task_id)
        if task is None:
            return []
        sigs = [s for s in available_signals(task.state) if required_role(s) != Role.SYSTEM]
        if agent_id is None:
            return sigs
        role = self._role_of(agent_id, task)
        if role is None:
            return []
        return [s for s in sigs if required_role(s) == role]

    def _role_of(self, agent_id: AgentId, task: Task) -> Optional[Role]:
        if task.assignee == agent_id:
            return Role.EXECUTOR
        parent = self._graph.get_parent(task.id) if task.parent_id else None
        if parent and parent.assignee == agent_id:
            return Role.ISSUER
        # Root issuer: a task with no parent is issued by its own creator context.
        if task.parent_id is None:
            return Role.ISSUER
        return None

    # === Extended Query API ===

    def tasks_by_state(self, state: State) -> list[Task]:
        return [t for t in self._graph._storage.get_all_tasks() if t.state == state]

    def tasks_by_assignee(self, assignee: AgentId) -> list[Task]:
        return [t for t in self._graph._storage.get_all_tasks() if t.assignee == assignee]

    def all_tasks(self) -> list[Task]:
        return self._graph._storage.get_all_tasks()

    # === Execution forcing-point ===

    def next_step(self, root_id: Optional[TaskId] = None) -> dict:
        """The execution forcing-point. From the graph's CURRENT state, return the ONE next required action
        for the executor agent — or `complete=True`. Children before parents (a parent only DELIVERs once its
        children PASS); completion is GATED on the root being DONE/PASS, so the agent cannot stop early. The
        agent loops this and does exactly what `directive` says: the graph drives, the agent executes.

        Returns a dict: {complete, [task_id, name, state, action, criteria], directive}. `action` ∈
        {accept, execute, deliver, validate, resolve, rework}. Single-agent / self-report (v1): no external
        verification yet — it only forces the agent THROUGH every node, not that the work is real."""
        def _passed(t: Task) -> bool:
            return t.state == State.DONE and t.done_reason == DoneReason.PASS

        tasks = self.all_tasks()
        if not tasks:
            return {"complete": False,
                    "directive": "No graph yet — create the root task (create_task) then decompose it."}
        root = self._graph.get_task(root_id) if root_id else \
            next((t for t in tasks if t.parent_id is None), tasks[0])
        if root is not None and _passed(root):
            return {"complete": True,
                    "directive": f"COMPLETE — root '{root.id}' is DONE/PASS. Execution finished."}

        deps = self._graph.dep_edges()
        def _deps_ready(tid: TaskId) -> bool:
            """A consumer is executable only once every producer it depends on has PASSED (dep order)."""
            return all(_passed(self._graph.get_task(e.from_id)) for e in deps if e.to_id == tid)

        best = None  # (priority, task, action, directive); lower priority acts first (children before parents)
        for t in tasks:
            kids = self.get_active_children(t.id)
            crits = [c.name for c in t.spec.criteria if not c.depends_on]
            nm = t.spec.name or str(t.id)
            if t.state == State.VALIDATING:
                cand = (1, t, "validate",
                        f"VALIDATE '{t.id}' ({nm}): check the deliverable against criteria {crits}; signal "
                        f"PASS if every criterion holds, else FAIL with the failed criteria.")
            elif t.state == State.REWORK:
                cand = (2, t, "rework",
                        f"REWORK '{t.id}' ({nm}): it FAILED — fix the work so criteria {crits} hold, then DELIVER again.")
            elif t.state == State.EXECUTING and not kids:
                if not _deps_ready(t.id):
                    continue  # a consumer waits until its producers PASS — do them first (dep order)
                cand = (3, t, "execute",
                        f"EXECUTE leaf '{t.id}' ({nm}): do the actual work so criteria {crits} hold, then "
                        f"signal DELIVER with the result. (If it turns out multi-part, decompose it instead.)")
            elif t.state == State.REVIEW and kids:
                # a re-authored parent dropped back to REVIEW — re-ACCEPT it BEFORE driving its subtree, so the
                # graph doesn't finish all children while the parent still shows 'accept' (obs: odd ordering).
                cand = (0, t, "accept",
                        f"RE-ACCEPT '{t.id}' ({nm}): it was re-authored → signal ACCEPT to put it back to work "
                        f"(its existing subtree is retained). Then its children proceed.")
            elif t.state == State.REVIEW:
                cand = (4, t, "accept",
                        f"TAKE '{t.id}' ({nm}): signal ACCEPT (or CHALLENGE if its spec is wrong). Then decide by "
                        f"the criteria {crits}: DECOMPOSE (auto_decompose/decompose) ONLY if it is genuinely "
                        f"multi-part; otherwise EXECUTE it directly as a leaf — do NOT over-decompose an atomic task.")
            elif t.state == State.BLOCKED:
                cand = (5, t, "resolve", f"'{t.id}' ({nm}) is BLOCKED — clear the blocker, then RESOLVE_BLOCK.")
            elif t.state == State.EXECUTING and kids and all(_passed(k) for k in kids):
                cand = (6, t, "deliver",
                        f"AGGREGATE '{t.id}' ({nm}): all its children PASSED — integrate them and signal "
                        f"DELIVER (the parent's criteria {crits} must hold over the REAL aggregate, not mocks).")
            else:
                continue  # EXECUTING with unfinished children, terminal, or IDLE → its frontier is elsewhere
            if best is None or cand[0] < best[0]:
                best = cand

        if best is None:
            return {"complete": False, "stuck": True,
                    "directive": "Stuck: no actionable node, but the root is not DONE/PASS — inspect node states."}
        _, t, action, directive = best
        # Surface the structural gate the executor can't otherwise see: a node cannot legitimately PASS while
        # L0/L1 checks fail (e.g. CHECK-4 empty NEGLECTED, CHECK-1 coverage) — hand them over with the directive.
        unmet = [f"{c.check_name}: {c.details}" for c in self.get_checks(t.id) if not c.passed and not c.skipped]
        if unmet:
            directive += f" | UNMET structural checks (resolve before PASS): {unmet}"
        return {"complete": False, "task_id": str(t.id), "name": t.spec.name or str(t.id),
                "state": t.state.name, "action": action, "unmet_checks": unmet,
                "criteria": [c.name for c in t.spec.criteria if not c.depends_on], "directive": directive}

    def graph_holes(self, root_id: Optional[TaskId] = None) -> list[dict]:
        """Every UNMET structural check across the whole graph (or the subtree under root_id) — the full gap
        list to resolve ∨ consciously declare BEFORE driving execution. Aggregates each node's cached L0/L1
        checks (coverage, DAG, glue, non-redundancy, NEGLECTED, …). A freshly `decompose`d graph can carry
        holes (the model isn't perfect); this is how you SEE them all at once instead of one PASS-rejection at
        a time. Returns [{task_id, name, check, details}], most structural first (ordered by node then check)."""
        scope = self.all_tasks()
        if root_id is not None:
            keep, frontier = set(), [root_id]
            while frontier:
                nid = frontier.pop()
                if nid in keep:
                    continue
                keep.add(nid)
                frontier.extend(c.id for c in self._graph.get_active_children(nid))
            scope = [t for t in scope if t.id in keep]
        holes = []
        for t in scope:
            for c in self.get_checks(t.id):
                if not c.passed and not c.skipped:
                    holes.append({"task_id": str(t.id), "name": t.spec.name or str(t.id),
                                  "check": c.check_name, "details": c.details})
        return holes

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
