"""GFSO Engine — Level 2 framework. Public API for building systems."""
from __future__ import annotations

import logging
import threading
from datetime import datetime
from typing import Optional

from gfso.core.types import (
    Signal, State, SignalData, TaskId, AgentId,
    Spec, Criteria, Task, CheckResult, Recommendation, CriterionMapping, DepEdge,
    LLMProviderPort, AgentPort, StoragePort,
    ClockPort, SystemClock, RunnerPort, ThreadRunner,
    TERMINAL_STATES, DoneReason,
)
from gfso.core.graph import Graph, q_T, q_D, q_V, q_Dep, q_Del, false_fail_share
from gfso.core.graph.projection import build as build_projection, render as render_projection
from gfso.core.protocol.fsm import available_signals
from gfso.core.protocol.validation import required_role, Role
from gfso.core.handlers.structural import check_dag

from .audit import AuditLog, AuditEntry
from .events import EventBus, TransitionCallback, ErrorCallback, RejectCallback
from .loop import event_loop, timeout_monitor

log = logging.getLogger(__name__)

# live token ticks ("<stage>: N tokens · Ss") update in place — WS-only, never persisted
import re as _re
_TICK_RE = _re.compile(r"tokens · \d+s$")


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
        state_timeout: Optional[float] = None,
        clock: Optional[ClockPort] = None,
        runner: Optional[RunnerPort] = None,
    ):
        self._graph = Graph(storage)
        self._agents = agents
        self._llm = llm
        self._check_interval = check_interval
        # Инв-5 per-STATE finiteness clock (seconds), GFSO_STATE_TIMEOUT. The MECHANISM is built and
        # tested; the QUESTION stays OPEN (author, 2026-07-11): a real clock binding must anchor to
        # real UTC dates (or something stronger — tamper-resistant time is an exploit surface), which
        # is an implementor's open end, not this codebase's to settle; for plain LLM-system operation
        # it carries little value. So the DEFAULT IS 0 = OFF (equivalent to the mechanism's absence —
        # no magic 24h figure silently escalating long-lived graphs): Инв-5 finiteness beyond node
        # deadlines is OPT-IN until the clock question is decided.
        if state_timeout is None:
            import os
            try:
                state_timeout = float(os.environ.get("GFSO_STATE_TIMEOUT", "0"))
            except ValueError:
                state_timeout = 0.0
        self._state_timeout = state_timeout
        self._validate = validate_signals
        self._critique_log_path = critique_log_path

        # The execution substrate + time source are PORTS (fake clock / asyncio host swap in
        # without touching the core); the stdlib defaults preserve the historical behavior exactly.
        self._clock: ClockPort = clock or SystemClock()
        self._runner: RunnerPort = runner or ThreadRunner()
        self._queue = self._runner.new_queue()
        self._stop = threading.Event()
        self._audit = AuditLog(storage)   # persists + hydrates when the storage carries audit methods
        self._events = EventBus()
        self._started = False

    # === Lifecycle ===

    def start(self) -> None:
        """Start event loop and timeout monitor."""
        if self._started:
            return
        self._started = True

        self._runner.spawn(
            lambda: event_loop(self._graph, self._agents, lambda: self._llm, self._queue,
                               self._audit, self._events, self._validate),
            name="gfso-event-loop")

        self._runner.spawn(
            lambda: timeout_monitor(self._graph, self._queue, self._check_interval, self._stop,
                                    self._state_timeout, self._clock),
            name="gfso-timeout-monitor")

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

    def revise(self, task_id: TaskId, new_spec: Spec, agent: AgentId, reason=None) -> Task:
        """Revise a node's spec — canon v3.7 §6.4 Inv-1: a packet change on a live node = **re-ASSIGN under
        the SAME id → REVIEW** (NOT the CANCEL signal). The executor re-ACCEPTs/CHALLENGEs the new contract;
        each version is appended to the log (Inv-7: the immutable record is the LOG, not the node).

        `agent` must be the issuer (ASSIGN is an issuer signal — validated). The subtree is RETAINED
        (revision ≠ abandonment): no cascade; coverage staleness surfaces via CHECK-1 + non-redundancy/
        CHECK-1b (dangling covers) + CHECK-3 (Dep consumers) for the agent to resolve (surface-don't-destroy).
        Only a genuine abandon (CANCEL → CANCELLING → CANCELLED) cascades. The only IN-PLACE spec change is
        ACCEPT_CHALLENGE (executor-initiated negotiation, FM-7→FM-5).

        `reason` (optional RevisionReason, §16.5): the causal type of the revision — SPEC_DEFECT
        (criteria were wrong → counts in q_T) / SCOPE_EXPANSION (sanctioned §5.1 — never counts) /
        CAPABILITY_MISMATCH (Del change → counts in q_Del) / OTHER. Untyped keeps each metric's
        documented bias.
        """
        return self._revise(task_id, new_spec, agent, reason=reason)

    def reneglect(self, task_id: TaskId, neglected: tuple, agent: AgentId) -> Task:
        """UPPER convenience = read-modify-write over REVISE: replace a node's NEGLECTED, keep the rest.
        Desugars to the lower signal path (no new command, no bypass). The whole packet is re-sent; the
        unchanged fields are carried for you (the human/agent edits one field)."""
        t = self._graph.get_task(task_id)
        if t is None:
            raise ValueError(f"task {task_id} not found")
        new_spec = Spec(t.spec.description, t.spec.criteria, tuple(neglected), t.spec.risk_components,
                        scope=t.spec.scope, name=t.spec.name)
        return self.revise(task_id, new_spec, agent)

    def edit_criteria(self, task_id: TaskId, criteria: tuple, agent: AgentId, reason=None) -> Task:
        """UPPER convenience = RMW over REVISE: replace a node's criteria, keep description/NEGLECTED.
        Dep criteria (depends_on) are part of `criteria` — pass the full set (RMW carries the unchanged).
        `reason` (§16.5): SPEC_DEFECT = the criteria were WRONG (counts in q_T); SCOPE_EXPANSION =
        sanctioned growth of the goal (§5.1 — never counts); untyped = uncounted (documented bias)."""
        t = self._graph.get_task(task_id)
        if t is None:
            raise ValueError(f"task {task_id} not found")
        new_spec = Spec(t.spec.description, tuple(criteria), t.spec.neglected, t.spec.risk_components,
                        scope=t.spec.scope, name=t.spec.name)
        return self.revise(task_id, new_spec, agent, reason=reason)

    def reassign(self, task_id: TaskId, new_assignee: AgentId, reason=None) -> Task:
        """UPPER: change a node's executor (Del). Canon Inv-1 fixes Del(t) at ASSIGN too → a change is a
        revision: re-ASSIGN (same id) carrying the new executor (the issuer acts). `reason` (§16.5):
        CAPABILITY_MISMATCH counts in q_Del; another typed reason (load, handoff) does NOT; untyped
        keeps the documented over-approximation (every untyped Del change counts). Same node returned."""
        t = self._graph.get_task(task_id)
        if t is None:
            raise ValueError(f"task {task_id} not found")
        parent = self._graph.get_parent(task_id)
        issuer = parent.assignee if parent and parent.assignee else t.assignee
        return self._revise(task_id, t.spec, issuer, new_assignee=new_assignee, reason=reason)

    def reopen(self, task_id: TaskId, agent: AgentId) -> Task:
        """UPPER convenience over the R′ edge (§6.3): re-ASSIGN a quasi-terminal (DONE/CANCELLED)
        under its OWN standing contract — the node returns to REVIEW to re-earn its verdict by fresh
        contact (REOPEN is restoration, not a 13th signal). Double-gated in the FSM at the
        chokepoint: finality-gate (not consumed — positive: the parent has not staked its aggregate
        and no Dep-consumer built on the result; negative: cascade not settled / parent not
        replanned) ∧ reopens < max_reopens (one sign-agnostic counter, Инв-5). A CONSUMED terminal
        is finally locked — recovery there is re-decomposition by the issuer, not reopen. To reopen
        WITH a new contract, use `revise` (same edge, spec carried)."""
        t = self._graph.get_task(task_id)
        if t is None:
            raise ValueError(f"task {task_id} not found")
        return self._revise(task_id, t.spec, agent)

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
    # The L2 validate itself lives ABOVE the engine: gfso.critic.runner.review_decomposition(engine,
    # node_id) — the critic pulls decompose/adapters, and the engine imports core ONLY (the layer gate).
    # The engine keeps the pure storage reads its layer owns.

    def get_critique(self, node_id: TaskId) -> Optional[dict]:
        import json
        raw = self._graph._storage.get_critique(node_id)
        return json.loads(raw) if raw else None

    def active_tasks(self) -> list[Task]:
        return self._graph.active_tasks()

    # === Metrics API ===

    def metrics(self) -> dict[str, float | None]:  # None = ⊥, пустая популяция (§13) — рендерится прочерком
        return {
            "q_T": q_T(self._graph),
            "q_D": q_D(self._graph),
            "q_V": q_V(self._graph),
            "q_Dep": q_Dep(self._graph),
            "q_Del": q_Del(self._graph),
            # Diagnostic, NOT a Q component (§16.5: false-FAIL is guarantee-safe, outside the
            # scalar by design; the SHARE is the over-strict-validator diagnostic). HIGH = bad.
            "false_fail_share": false_fail_share(self._graph),
        }

    # === Events API ===

    def on_transition(self, callback: TransitionCallback) -> None:
        self._events.on_transition(callback)

    def on_error(self, callback: ErrorCallback) -> None:
        self._events.on_error(callback)

    def on_reject(self, callback: RejectCallback) -> None:
        self._events.on_reject(callback)

    def on_info(self, callback) -> None:
        self._events.on_info(callback)

    def emit_info(self, source: str, message: str) -> None:
        """Broadcast a pipeline-progress line to live observers (UI window via /ws/events) AND persist it
        (SQLite pipeline_log) so the observation history survives refresh/restart. Live token TICKS are
        broadcast-only: they update in place and would be stored-every-2s noise."""
        self._events.emit_info(source, message)
        if not _TICK_RE.search(message):
            try:
                self._graph._storage.log_pipeline(
                    datetime.now().isoformat(sep=" ", timespec="seconds"), source, message)
            except Exception:
                pass  # observation is presentation — never break the pipeline

    def pipeline_log(self, limit: int = 500) -> list[dict]:
        """The persisted observation history, oldest-first: [{ts, source, message}]."""
        return self._graph._storage.get_pipeline(limit)

    # === Execution-validation record (the validate_result verdict; feeds the self-pass gate) ===

    def record_exec_verdict(self, task_id: TaskId, verdict: str, failed_criteria: list,
                            validator_id: str) -> None:
        """Store the independent validator's verdict for the node's CURRENT delivery (stamped with the
        node's GENERATION (iteration, reopens) — a rework OR a reopen invalidates it: the next
        delivery needs a fresh verdict; the superseded record is replaced, never trusted forward)."""
        import json as _json
        task = self.get_task(task_id)
        self._graph._storage.store_exec_verdict(task_id, _json.dumps({
            "verdict": verdict, "failed_criteria": list(failed_criteria or ()),
            "validator": validator_id, "iteration": getattr(task, "iteration", 0),
            "reopens": getattr(task, "reopens", 0),
            "ts": datetime.now().isoformat(sep=" ", timespec="seconds")}))

    def record_reviewer_verdict(self, task_id: TaskId, verdict: str, failed_criteria: list,
                                reviewer: str) -> None:
        """The HUMAN counterpart of validate_result's record: an independent reviewer's verdict on
        the node's CURRENT delivery (feeds the same self-pass gate). The engine REFUSES a reviewer
        who IS the node's executor — recording a verdict on your own work would open the
        verifier≠executor gate from the inside (§6.5 IC; visibility ≠ enforcement: the refusal is
        here, not in a prompt). FAIL requires failed_criteria (Inv-3)."""
        task = self.get_task(task_id)
        if task is None:
            raise ValueError(f"unknown task {task_id}")
        if verdict not in ("PASS", "FAIL"):
            raise ValueError(f"verdict must be PASS or FAIL, got {verdict!r}")
        if verdict == "FAIL" and not failed_criteria:
            raise ValueError("FAIL requires failed_criteria (Inv-3: a FAIL is never criteria-less)")
        if task.assignee and str(reviewer) == str(task.assignee):
            raise ValueError(f"reviewer {reviewer!r} is the node's own executor — an independent "
                             f"verdict cannot come from the executor (verifier ≠ executor, §6.5)")
        self.record_exec_verdict(task_id, verdict, list(failed_criteria or ()), str(reviewer))

    def get_exec_verdict(self, task_id: TaskId) -> Optional[dict]:
        return self._graph.exec_verdict_record(task_id)

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

        # `criterion_mappings is not None` = the FULL coverage list — RECONCILE (the documented
        # contract: "pass the full list to SET; None adds children without wiping"): a pair the
        # decomposer no longer asserts is REMOVED, so a child it dropped becomes visibly UNMAPPED —
        # CHECK-1b/non-redundancy surfaces it as a hole. The node itself is NEVER killed here:
        # abandoning work is the issuer's explicit CANCEL (cascade), not a decomposition side effect —
        # the decomposer owns the FORM (coverage), the issuer owns the work's disposition.
        if criterion_mappings is not None:
            p = self._graph.get_task(parent_id)
            want = {(m.criterion_name, m.child_id) for m in criterion_mappings}
            kept = tuple(m for m in p.criterion_mappings
                         if (m.criterion_name, m.child_id) in want)
            if len(kept) != len(p.criterion_mappings):
                p.criterion_mappings = kept
                self._graph.save_task(p)

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
            # Test/offline convenience ONLY. The canonical runtime path for a discovered Dep is the BLOCK
            # signal carrying `blocker_task_id` (→ RECORD_DEP effect, provisional; RESOLVE_BLOCK adjudicates —
            # §6.2/§7.2, v3.7). This direct write stays off every transport surface (tools/api/mcp/cli pass
            # discovered=False).
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
            self._revise(to_id, new_spec, self._issuer_of(to_id))
        self._recompute_seam_parents(from_id, to_id)

    def remove_dependency(self, from_id: TaskId, to_id: TaskId) -> None:
        """Drop a dependency. Declared → remove the consumer's dep criterion (re-author); also clears
        any stored (discovered) edge for the pair."""
        to = self._graph.get_task(to_id)
        if to is not None and any(c.depends_on == from_id for c in to.spec.criteria):
            new_crits = tuple(c for c in to.spec.criteria if c.depends_on != from_id)
            new_spec = Spec(to.spec.description, new_crits, to.spec.neglected, to.spec.risk_components,
                            name=to.spec.name)
            self._revise(to_id, new_spec, self._issuer_of(to_id))
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
        self._revise(child_id, child.spec, self._issuer_of(child_id), covers=(criterion_name,))
        return self._graph.get_task(parent_id)

    def _revise(self, task_id: TaskId, new_spec: Spec, agent: AgentId,
                new_assignee: Optional[AgentId] = None, covers: tuple = (),
                reason=None) -> Task:
        """Canon v3.7 Inv-1 (§6.4): a spec/Del change = REVISION — ONE re-ASSIGN under the SAME id → REVIEW,
        never an in-place mutation and never the CANCEL signal (revision ≠ abandonment; no CANCELLING pass,
        no cascade). The id persists (Inv-7) so references (the parent's mapping, dependents' depends_on)
        stay valid; the superseded contract lives in the append-only log. `agent` must be the issuer
        (ASSIGN is an issuer signal → FSM-validated). Returns the revised node (back in REVIEW —
        the executor must re-ACCEPT)."""
        old = self._graph.get_task(task_id)
        if old is None:
            raise ValueError(f"task {task_id} not found")
        a = self.send_signal_sync(SignalData(
            signal=Signal.ASSIGN, task_id=task_id, spec=new_spec, source=agent,
            assignee=new_assignee or old.assignee, covers=tuple(covers),
            revision_reason=reason))
        if a is None or a.rejected:
            raise ValueError(
                f"revise rejected at re-ASSIGN (state={self.get_state(task_id)}): the node is in "
                f"TIMEOUT/CANCELLING/ESCALATED (no revision there, §6.3), a quasi-terminal that is "
                f"FINAL (consumed ∨ reopens exhausted — the R′ finality-gate, §6.3), or the agent "
                f"is not its issuer.")
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

    def _frontier(self, root_id: Optional[TaskId] = None):
        """Collect ALL currently actionable candidates, priority-ordered (children before parents,
        dep order respected). Returns either a terminal dict ({complete}/{stuck}/empty-graph) or a list of
        (priority, task, action, directive) tuples. Shared by next_step (v1 single directive) and
        next_steps (v2 parallel frontier)."""
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

        cands = []  # (priority, task, action, directive); lower priority acts first
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
            elif t.state == State.CANCELLING:
                # settlement of the cancellation handshake (§6.3) — never preempts real work (lowest priority)
                cand = (7, t, "cancel_ack",
                        f"CONFIRM cancellation of '{t.id}' ({nm}): signal CANCEL_ACK, reporting the in-flight "
                        f"state at cancellation (what was done/undone) via `in_flight`.")
            else:
                continue  # EXECUTING with unfinished children, terminal, or IDLE → its frontier is elsewhere
            cands.append(cand)

        if not cands:
            return {"complete": False, "stuck": True,
                    "directive": "Stuck: no actionable node, but the root is not DONE/PASS — inspect node states."}
        cands.sort(key=lambda c: (c[0], str(c[1].id)))
        return cands

    def _step_out(self, t: Task, action: str, directive: str) -> dict:
        # Surface the structural gate the executor can't otherwise see: a node cannot legitimately PASS while
        # L0/L1 checks fail (e.g. CHECK-4 empty NEGLECTED, CHECK-1 coverage) — hand them over with the directive.
        unmet = [f"{c.check_name}: {c.details}" for c in self.get_checks(t.id) if not c.passed and not c.skipped]
        if unmet:
            directive += f" | UNMET structural checks (resolve before PASS): {unmet}"
        return {"complete": False, "task_id": str(t.id), "name": t.spec.name or str(t.id),
                "state": t.state.name, "action": action, "assignee": t.assignee, "unmet_checks": unmet,
                "criteria": [c.name for c in t.spec.criteria if not c.depends_on], "directive": directive}

    def next_step(self, root_id: Optional[TaskId] = None) -> dict:
        """The execution forcing-point (v1, single-agent form). From the graph's CURRENT state, return the
        ONE next required action — or `complete=True`. Children before parents (a parent only DELIVERs once
        its children PASS); completion is GATED on the root being DONE/PASS, so the agent cannot stop early.

        Returns a dict: {complete, [task_id, name, state, action, criteria], directive}. `action` ∈
        {accept, execute, deliver, validate, resolve, rework, cancel_ack}. For parallel delegation use
        next_steps (the full frontier)."""
        result = self._frontier(root_id)
        if isinstance(result, dict):
            return result
        _, t, action, directive = result[0]
        return self._step_out(t, action, directive)

    def next_steps(self, root_id: Optional[TaskId] = None) -> dict:
        """The PARALLEL frontier (v2): every currently actionable node, priority-ordered, with a
        `parallel_ok` marker on the execute-class steps.

        All returned `execute` steps are pairwise independent by construction: each is a leaf whose Dep
        producers have PASSED (§2.2 dep order), and distinct ready leaves share no unresolved edge — so the
        orchestrator may delegate them to executors CONCURRENTLY. Non-execute steps (accept / validate /
        rework / resolve / deliver / cancel_ack) are issuer-side and cheap — do them in the returned order
        before/between delegations. Returns {complete, steps: [step...]} (each step shaped like next_step's
        output + `parallel_ok`)."""
        result = self._frontier(root_id)
        if isinstance(result, dict):
            return result if result.get("complete") or "steps" in result else {**result, "steps": []}
        steps = []
        for _, t, action, directive in result:
            step = self._step_out(t, action, directive)
            step["parallel_ok"] = action == "execute"
            steps.append(step)
        return {"complete": False, "steps": steps}

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
