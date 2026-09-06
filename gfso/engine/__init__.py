"""GFSO Engine — Level 2 framework. Public API for building systems."""
from __future__ import annotations

import json
import logging
import os
import threading
from datetime import datetime
from typing import Optional

from gfso.core.types import (
    Signal, State, Action, CriticVerdict, SignalData, SignalOutcome, Refusal, Wait,
    TaskId, AgentId, Verdict, passed, settled_positive,
    Spec, Criteria, Task, CheckResult, Recommendation, CriterionMapping, DepEdge,
    LLMProviderPort, AgentPort, StoragePort,
    ClockPort, SystemClock, RunnerPort, ThreadRunner,
    TERMINAL_STATES, DoneReason,
)
from gfso.core.graph import Graph
from gfso.core.graph.model import generation_of_task
from gfso.core.graph import q_T, q_D, q_V, q_Dep, q_Del, false_fail_share, pass_was_refuted
from gfso.core.graph.review import finding_keys
from gfso.core.graph.projection import build as build_projection, render as render_projection
from gfso.core.protocol.fsm import available_signals
from gfso.core.protocol.validation import required_role, Role
from gfso.core.protocol.invariants import (probes_that_expected_nothing,
                                          verdict_report_defects, underprobed, probe_labels,
                                          unrun_probes)
from gfso.core.handlers import run_all_checks
from gfso.core.handlers.structural import check_dag

from gfso.config import (DEFAULT_PROJECT,
                         MODEL_VALIDATOR_RETRY, PIPELINE_PAGE, USAGE_PAGE, VALIDATION_CLAIM_TTL,
                         agent_id as _config_agent_id,
                         state_timeout as _config_state_timeout)
from .audit import AuditLog, AuditEntry
from .verdicts import store_verdict
from .validation import (_l0_holes, _l2_undischarged, l2_gate_on, _refuted_coverage_refusal,
                         _EXEC_GATING_CHECKS)
from .events import EventBus, TransitionCallback, ErrorCallback, RejectCallback
from .loop import event_loop, timeout_monitor

log = logging.getLogger(__name__)

# live token ticks ("<stage>: N tokens · Ss") update in place — WS-only, never persisted
import re
_TICK_RE = re.compile(r"tokens · \d+s$")


def _loose_key(text: str) -> str:
    """A finding's key with the characters a console can mangle taken out of the comparison.

    Only for MATCHING an offered key against the ones on record — never for storing one. What is
    compared is the ASCII skeleton: letters, digits and a few structural marks. Dashes and quotes are
    dropped rather than normalized, because a dash that went through a legacy code page comes back as
    several characters (an em-dash arrives as "вЂ”"), one of which is itself a quote — so mapping
    them to ASCII equivalents leaves the two spellings still different. Two findings that differ only
    in what this drops therefore collide, which is why a match is used only when it is UNIQUE."""
    keep = "_.:/[]()<>{}!?,;=+*#$%&@|~^ "
    out = [ch for ch in str(text).lower()
           if ch.isascii() and (ch.isalnum() or ch in keep)]
    return " ".join("".join(out).split())


#: Actions whose signal is the ISSUER's to give (§14.2) — everything else is the executor's.
_ISSUER_ACTIONS = frozenset({Action.VALIDATE, Action.RESOLVE, Action.REVISE, Action.CHECK_PLAN})


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
        # WHO, OF THE NON-HUMAN PARTICIPANTS, IS WHAT — {id: kind}, published downward by the
        # dispatcher each round. Declared here because three surfaces read it (the frontier's
        # in-flight view, the affordance layer's "a human or a machine holds this", the tool door's
        # wait message) and a field born in the dispatcher had all three reading it defensively —
        # which reads as "nobody is registered" on any engine the dispatcher has not touched yet.
        self._roster: dict[str, str] = {}
        #: WHOSE each published instrument is — `{validator id: project or None}`, written by
        #: the dispatcher beside `_roster`. Declared here rather than read defensively, because
        #: a field a reader has to guess at is a field two readers will guess differently.
        #: `None` for an entry means UNSCOPED, which is shared by design; an empty dict means
        #: no dispatcher has published yet, which is not the same as "no instruments".
        self._validator_projects: dict[str, object] = {}
        self._llm = llm
        self._check_interval = check_interval
        # Inv-5 per-STATE finiteness clock (seconds), GFSO_STATE_TIMEOUT. The MECHANISM is built and
        # tested; the QUESTION stays OPEN (author, 2026-07-11): a real clock binding must anchor to
        # real UTC dates (or something stronger — tamper-resistant time is an exploit surface), which
        # is an implementor's open end, not this codebase's to settle; for plain LLM-system operation
        # it carries little value. So the DEFAULT IS 0 = OFF (equivalent to the mechanism's absence —
        # no magic 24h figure silently escalating long-lived graphs): Inv-5 finiteness beyond node
        # deadlines is OPT-IN until the clock question is decided.
        if state_timeout is None:
            try:
                state_timeout = _config_state_timeout()
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
        #: in-flight validator runs — {(node, iteration, reopens): when it was claimed}. The
        #: TIME is what makes an abandoned claim recoverable: a run that dies without
        #: unwinding cannot release it, and a claim nobody is behind must not park a node.
        self._val_inflight: dict = {}
        # …and the same for the PLAN's check. `validate_result` has suppressed a duplicate spawn for
        # a while; `review_decomposition` had nothing of the kind, so the frontier went on telling a
        # driver to run it while one was running — a duplicate paid round for the same plan
        # (measured on the human door 2026-08-22, where the two surfaces disagreed about it).
        self._review_inflight: set = set()
        self._held_by_plan: list = []     # last frontier's plan-gated nodes (not steps, not silence)
        # WHICH PROJECT THIS ENGINE IS. Set by the registry that builds it; the roster is one
        # server-wide file, so this is what tells another run's validator role from yours.
        self.project_name: Optional[str] = None
        # Nodes where AUTOMATIC validation gave up (two reports, no verdict). The dispatcher says so
        # in the log and the node then sits in VALIDATING forever with the frontier still printing
        # "VALIDATE this" — measured 2026-08-20: two nodes stood 9 and 5 minutes, and only a hand
        # `validate_result` moved them. In-memory on purpose: a restarted dispatcher re-tries the
        # validation from scratch, so the parking is exactly as durable as the decision behind it.
        self._validation_parked: set = set()
        #: node id → the instrument bound to it {id, project, workdir}, published by
        #: the dispatcher each round (see `bound_judge`).
        self._bound_judges: dict = {}
        #: keys of notices that must be said once, not once per poll (`say_once`)
        self._said_once: set = set()
        # Nodes whose EXECUTOR disputes the contract from a state where CHALLENGE is not
        # admissible (§14.3 admits it from OFFERED only). The dispute is real and belongs to
        # the issuer; without somewhere to put it the signal was refused and the node stood
        # still with its round spent — a run died that way on 2026-08-21. In memory on
        # purpose, like `_validation_parked`: a restart re-offers the node to its executor,
        # and if the dispute is real it will be raised again.
        self._contested: dict[str, str] = {}
        self._val_lock = threading.Lock()

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

        self._recover_orphans()

    def _recover_orphans(self) -> None:
        """Finish an ASSIGN that was interrupted mid-effects — the escape hatch that replaces the
        `(IDLE, TIMEOUT)` row (corner #1 of `formal/README.md`).

        IDLE carries NO clock: it precedes any contract, deadlines attach at ASSIGN, and Inv-5
        exempts it by name (§14.4) — a starved IDLE child surfaces as its PARENT's timeout, whose
        contract does carry the clock. But a node is OBSERVABLE in IDLE for one reason only: the
        process died between CREATE_TASK and the SET_STATE→OFFERED of the same ASSIGN, leaving a
        crash orphan whose creation persisted and whose landing did not — and a ROOT orphan has no
        parent whose clock could surface it. Giving IDLE a timeout answered that with a protocol
        edge the canon denies; the defect is not a stalled contract but an unfinished mutation, so
        the repair is to FINISH it: re-send the ASSIGN with no packet, which falls through to the
        ordinary `(IDLE, ASSIGN)` row and lands the state, the checks, and the dispatch. It goes
        through the queue like any signal, so it is validated, logged, and visible (Thm 11) — never
        a silent state write. A node with no spec is not an orphan of this kind and is left alone.
        """
        for t in self._graph._storage.get_all_tasks():
            if t.state == State.IDLE and t.spec is not None and t.assignee:
                log.warning("recovering crash orphan %s: ASSIGN persisted the node but its landing "
                            "did not — completing the interrupted transition", t.id)
                self._queue.put(SignalData(signal=Signal.ASSIGN, task_id=t.id,
                                           source=self.issuer_of(t.id)))

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
        max_iterations: Optional[int] = None,
        deadline: Optional[datetime] = None,
    ) -> Task:
        """Create a task and send ASSIGN signal. Convenience method.

        deadline completes the T=(spec, criteria, deadline) primitive (§10);
        without it CHECK-3 (deadline consistency) is vacuous.

        `max_iterations` bounds the DELIVER→FAIL loop (§14.3) and is a field of the CONTRACT, not a
        property of the installation: the canon fixes the number by fiat (§26.9(b): "pinned by no
        FM"), so it is chosen per task by whoever issues it. The default exists so an unattended
        loop cannot retry all night unnoticed — it is a convenience, not a bound on the project.
        """
        if max_iterations is None:
            max_iterations = 3
        self._assert_no_d_cycle(task_id, parent_id)
        # Creation is the ASSIGN effect (CREATE_TASK), logged — no unlogged pre-save. ASSIGN is an
        # issuer signal: source = parent's assignee or self. send_signal_sync so the node exists on return.
        parent = self._graph.get_task(parent_id) if parent_id else None
        # A PARENT THAT IS NOT A NODE IS NOT A PARENT. This looked the parent up and, finding
        # nothing, went on: the child was created carrying a `parent_id` that names no node, and
        # `/api/graph` then emitted an EDGE with an endpoint outside its own node set. Found by
        # opening the page (2026-09-06): the whole graph rendered EMPTY, because a renderer handed
        # an edge to a nonexistent source refuses the batch — the header counted fifteen nodes over
        # a blank canvas, with nothing said. Its own origin is instructive: the CLI door ate
        # `--assignee me` into the POSITIONAL slot, so `parent_id` became the string "me" (fixed the
        # same day) — an unnoticed typo silently produced a graph that cannot be drawn.
        # D is a DAG over NODES (§10), which is the same rule the self-parent and cycle guards
        # beside this one enforce; an edge to a non-node is not an edge in it.
        if parent_id and parent is None:
            raise ValueError(
                f"parent {parent_id!r} does not exist, so {task_id} cannot hang under it — D is a "
                f"DAG over NODES (§10), and an edge to something that is not one is not an edge in "
                f"it. Create the parent first (`create_task {parent_id} …`), or leave `parent_id` "
                f"out and this node is a root of its own.")
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

    def _assert_no_d_cycle(self, task_id: TaskId, parent_id: Optional[TaskId]) -> None:
        """D is a DAG (§10: "a cycle → infinite recursion → an A1 violation"). CHECK-2 sees one
        split at a time; the ancestor chain is only visible here, so the edge that would CLOSE a
        cycle is refused at the door rather than reported after the fact — a self-parented node was
        accepted through `create_task` and then owned itself, which no later check can undo (its own
        children query returns itself, and the AND gate would wait on it forever)."""
        if not parent_id:
            return
        if str(parent_id) == str(task_id):
            raise ValueError(f"{task_id} cannot be its own parent — D must be a DAG (§10)")
        seen, cur = {str(task_id)}, self._graph.get_task(parent_id)
        while cur is not None:
            if str(cur.id) in seen:
                raise ValueError(
                    f"parent {parent_id} is a descendant of {task_id} — this edge would close a "
                    f"cycle in the decomposition graph, and D must be a DAG (§10)")
            seen.add(str(cur.id))
            cur = self._graph.get_task(cur.parent_id) if cur.parent_id else None

    # === Authoring operations (UPPER layer — desugar to the 12 signals, NOT new signals) ===

    def revise(self, task_id: TaskId, new_spec: Spec, agent: AgentId, reason=None) -> Task:
        """Revise a node's spec — canon v3.7 §14.4 Inv-1: a packet change on a live node = **re-ASSIGN under
        the SAME id → OFFERED** (NOT the CANCEL signal). The executor re-ACCEPTs/CHALLENGEs the new contract;
        each version is appended to the log (Inv-7: the immutable record is the LOG, not the node).

        `agent` must be the issuer (ASSIGN is an issuer signal — validated). The subtree is RETAINED
        (revision ≠ abandonment): no cascade; coverage staleness surfaces via CHECK-1 + non-redundancy/
        CHECK-1b (dangling covers) + CHECK-3 (Dep consumers) for the agent to resolve (surface-don't-destroy).
        Only a genuine abandon (CANCEL → CANCELLING → ABANDONED) cascades. The only IN-PLACE spec change is
        ACCEPT_CHALLENGE (executor-initiated negotiation, FM-7→FM-5).

        `reason` (optional RevisionReason, §24.5): the causal type of the revision — SPEC_DEFECT
        (criteria were wrong → counts in q_T) / SCOPE_EXPANSION (sanctioned §13.1 — never counts) /
        CAPABILITY_MISMATCH (Del change → counts in q_Del) / OTHER. Untyped keeps each metric's
        documented bias.
        """
        return self._revise(task_id, new_spec, agent, reason=reason)

    def edit_accepted_risks(self, task_id: TaskId, accepted_risks: tuple, agent: AgentId) -> Task:
        """UPPER convenience = read-modify-write over REVISE: replace a node's ACCEPTED_RISKS, keep the rest.
        Desugars to the lower signal path (no new command, no bypass). The whole packet is re-sent; the
        unchanged fields are carried for you (the human/agent edits one field)."""
        t = self._graph.get_task(task_id)
        if t is None:
            raise ValueError(f"task {task_id} not found")
        new_spec = Spec(t.spec.description, t.spec.criteria, tuple(accepted_risks), t.spec.risk_components,
                        scope=t.spec.scope, name=t.spec.name)
        return self.revise(task_id, new_spec, agent)

    def edit_criteria(self, task_id: TaskId, criteria: tuple, agent: AgentId, reason=None) -> Task:
        """UPPER convenience = RMW over REVISE: replace a node's criteria, keep description/ACCEPTED_RISKS.
        Dep criteria (depends_on) are part of `criteria` — pass the full set (RMW carries the unchanged).
        `reason` (§24.5): SPEC_DEFECT = the criteria were WRONG (counts in q_T); SCOPE_EXPANSION =
        sanctioned growth of the goal (§13.1 — never counts); untyped = uncounted (documented bias)."""
        t = self._graph.get_task(task_id)
        if t is None:
            raise ValueError(f"task {task_id} not found")
        # A Dep SEAM is stored as a criterion (`dep__{producer}` carrying `depends_on`), so a
        # wholesale replacement of the criteria array deletes the graph's EDGES — silently, with no
        # diff and no warning. The verb's own contract says "replace the criteria, carry the rest",
        # and an edge is emphatically the rest: nobody editing what a node must ACHIEVE is asking to
        # sever what it WAITS FOR. Worse, restoring a staled plan gate forces the caller through
        # this verb, so the trap sits on the recovery path. Measured 2026-08-20: an agent rebuilt
        # each array by hand from the previous response, none of the rebuilt entries carried
        # `depends_on`, and the loss is invisible until a consumer runs against an input nothing
        # connected it to (FM-5 — the freshness face of an undeclared coupling, §12.2).
        # Removing an edge stays possible and stays EXPLICIT: `remove_dependency`, or passing the
        # `dep__` criterion yourself, which this respects.
        named = {c.name for c in criteria}
        carried = tuple(c for c in t.spec.criteria
                        if c.depends_on and c.name not in named)
        new_spec = Spec(t.spec.description, tuple(criteria) + carried,
                        t.spec.accepted_risks, t.spec.risk_components,
                        scope=t.spec.scope, name=t.spec.name)
        return self.revise(task_id, new_spec, agent, reason=reason)

    def reassign(self, task_id: TaskId, new_assignee: AgentId, reason=None) -> Task:
        """UPPER: change a node's executor (Del). Canon Inv-1 fixes Del(t) at ASSIGN too → a change is a
        revision: re-ASSIGN (same id) carrying the new executor (the issuer acts). `reason` (§24.5):
        CAPABILITY_MISMATCH counts in q_Del; another typed reason (load, handoff) does NOT; untyped
        keeps the documented over-approximation (every untyped Del change counts). Same node returned."""
        t = self._graph.get_task(task_id)
        if t is None:
            raise ValueError(f"task {task_id} not found")
        parent = self._graph.get_parent(task_id)
        issuer = parent.assignee if parent and parent.assignee else t.assignee
        return self._revise(task_id, t.spec, issuer, new_assignee=new_assignee, reason=reason)

    def reopen(self, task_id: TaskId, agent: AgentId) -> Task:
        """UPPER convenience over the R′ edge (§14.3): re-ASSIGN a quasi-terminal (DONE/ABANDONED)
        under its OWN standing contract — the node returns to OFFERED to re-earn its verdict by fresh
        contact (REOPEN is restoration, not a 13th signal). Double-gated in the FSM at the
        chokepoint: finality-gate (not consumed — positive: the parent has not staked its aggregate
        and no Dep-consumer built on the result; negative: cascade not settled / parent not
        replanned) ∧ reopens < max_reopens (one sign-agnostic counter, Inv-5). A CONSUMED terminal
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
        """The node's state, or `None` when this graph has no such id."""
        return self._graph.get_state(task_id)

    def get_children(self, task_id: TaskId) -> list[Task]:
        """ALL children incl. ABANDONED tombstones (provenance, §15.1)."""
        return self._graph.get_children(task_id)

    def get_active_children(self, task_id: TaskId) -> list[Task]:
        """Children in the ACTIVE decomposition (excludes ABANDONED tombstones). The unit the critic
        and correctness checks reason over — a removed (cancelled) node persists for provenance but no
        longer participates in coverage/non-redundancy/projection."""
        return self._graph.get_active_children(task_id)

    def get_checks(self, task_id: TaskId) -> list[CheckResult]:
        """Read the CACHED L0/L1 checks (O(1)) — kept fresh by _recompute_checks on
        every decomposition change (cheap eager invalidation). Many watchers read this
        without recomputing."""
        return self._graph._storage.get_check_results(task_id)

    def _recompute_checks(self, node_id: TaskId, stale_review: bool = True) -> None:
        """Recompute + cache a node's L0/L1+anti-mock checks, and (by default) mark its L2 stale.

        `stale_review=False` is for a revision that changed no CONTENT — in practice, naming a
        different executor. The Level-2 question is whether the mapped children's criteria causally
        carry the parent's; WHO will execute a child is not part of that claim, so a delegation
        cannot make the verdict wrong. The L0 checks still recompute, because those DO read Del
        (CHECK-6: every leaf has an owner).

        Why this matters, measured 2026-08-20: delegating IS a re-ASSIGN, so assigning executors
        staled the plan verdict that had just been obtained. A run then spent 50 minutes and $2.71
        in the loop `review_decomposition → assign executors → verdict stale → review_decomposition` — and worse, an executor
        that had already produced 157 seconds of work had its ACCEPT refused ("its parent's plan has
        no CURRENT Level-2 verdict") and the work was thrown away. The gate and the delegation verb
        were destroying each other, and the ordering that avoids it was documented nowhere.
        """
        node = self._graph.get_task(node_id)
        if node is None:
            return
        children = self._graph.get_active_children(node_id)  # cancelled tombstones excluded from checks
        deps = self._graph.dep_edges()
        self._graph.store_check_results(
            node_id, run_all_checks(node, children, deps, self._graph.non_leaf_ids(children)))
        if stale_review and node.verified:  # decomposition changed → stored L2 verdict no longer current
            node.verified = False
            self._graph.save_task(node)

    # === L2 critic / validation API ===
    # The L2 validate itself lives ABOVE the engine: gfso.critic.runner.review_decomposition(engine,
    # node_id) — the critic pulls decompose/adapters, and the engine imports core ONLY (the layer gate).
    # The engine keeps the pure storage reads its layer owns.

    def get_critique(self, node_id: TaskId) -> Optional[dict]:
        raw = self._graph._storage.get_critique(node_id)
        return json.loads(raw) if raw else None

    def dispute_review_finding(self, node_id: TaskId, criterion: str, why: str,
                               agent: AgentId) -> dict:
        """Record the issuer's justified refusal of ONE Level-2 finding — the one way to discharge
        it where it stands (fixing the plan RETIRES the verdict instead, and needs a fresh review). The checker is an approximation over the faithfulness
        axis (§13.5) and can be wrong; what the system refuses is a SILENT skip, so the dispute is
        written into the review record with its author and time (§6.2: an explicit falsifiable claim
        instead of an unstated one). It dies with that record — any edit to the decomposition stales
        the review, and the next `review_decomposition` overwrites it, so a dispute never launders a
        finding across plan versions: it must be re-stated against the fresh verdict.

        Refused when there is no current verdict, or when the named criterion is not one the checker
        actually flagged (nothing to dispute)."""
        node = self._graph.get_task(node_id)
        if node is None:
            raise ValueError(f"unknown task {node_id}")
        raw = self._graph._storage.get_critique(node_id)
        rec = json.loads(raw) if raw else None
        if not rec or not getattr(node, "verified", False):
            raise ValueError(
                f"no current Level-2 verdict on {node_id} — run review_decomposition first "
                f"(a finding can only be disputed against the review that named it)")
        # …by the SAME names the gate holds the node shut on, and the same the delta baseline reads
        # (`core.graph.review.finding_keys`) — three spellings of one name is three chances for a
        # dispute to be refused as "not an open finding" against a finding that is open. Including
        # the sufficiency ones: an obligation of the goal that no criterion decides is disputed
        # exactly like any other — in writing, against the review that named it.
        flagged = set(finding_keys(rec, exclude_disputed=False))
        if criterion not in flagged:
            # …AND A KEY THAT DIFFERS ONLY IN PUNCTUATION IS THE SAME KEY. A finding's text carries
            # the em-dashes and curly quotes a model writes, and a caller who copies one back through
            # a console with a legacy code page hands over a string that LOOKS identical and is not:
            # the refusal then reads "not an open finding" and lists that same finding as open, which
            # cost a tester twenty minutes and locked them out of the only exit from the plan gate
            # (measured on the human door 2026-08-21). One unambiguous near-match is accepted, and the
            # answer says which key it landed on; anything else refuses as before.
            near = [f for f in flagged if _loose_key(f) == _loose_key(criterion)]
            if len(near) != 1:
                raise ValueError(
                    f"{criterion!r} is not an open Level-2 finding on {node_id} — open: "
                    f"{', '.join(sorted(flagged)) or '(none)'}"
                    + (". Two of the open findings match it once punctuation is ignored, so name one "
                       "of them exactly." if len(near) > 1 else ""))
            criterion = near[0]
        rec.setdefault("disputes", {})[criterion] = {
            "why": why, "by": str(agent),
            "ts": datetime.now().isoformat(sep=" ", timespec="seconds")}
        self._graph._storage.store_critique(node_id, json.dumps(rec))
        return {"task_id": str(node_id), "disputed": criterion,
                "open_findings": sorted(flagged - set(rec["disputes"]))}

    def active_tasks(self) -> list[Task]:
        """Every node not in a terminal state — what the frontier and the metrics both walk."""
        return self._graph.active_tasks()

    # === Metrics API ===

    def metrics(self) -> dict[str, float | None]:  # None = ⊥, пустая популяция (§21) — рендерится прочерком
        """The five quality metrics of this graph, plus the false-FAIL diagnostic (§15.2/§24.5).

        A `None` is ⊥ — the population was empty — and never a score of zero: no observation is
        not a bad result, and rendering it as one is the misreading this whole vector invites.
        """
        return {
            "q_T": q_T(self._graph),
            "q_D": q_D(self._graph),
            "q_V": q_V(self._graph),
            "q_Dep": q_Dep(self._graph),
            "q_Del": q_Del(self._graph),
            # Diagnostic, NOT a Q component (§24.5: false-FAIL is guarantee-safe, outside the
            # scalar by design; the SHARE is the over-strict-validator diagnostic). HIGH = bad.
            "false_fail_share": false_fail_share(self._graph),
        }

    # === Events API ===

    def on_transition(self, callback: TransitionCallback) -> None:
        """Subscribe to state changes on this engine's bus."""
        self._events.on_transition(callback)

    def on_error(self, callback: ErrorCallback) -> None:
        """Subscribe to errors raised while a signal was handled."""
        self._events.on_error(callback)

    def on_reject(self, callback: RejectCallback) -> None:
        """Subscribe to signals the FSM REFUSED — the refusals are events, not silence."""
        self._events.on_reject(callback)

    def on_info(self, callback) -> None:
        """Subscribe to the observation stream long verbs write while they run."""
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

    def pipeline_log(self, limit: int = PIPELINE_PAGE) -> list[dict]:
        """The persisted observation history, oldest-first: [{ts, source, message}]."""
        return self._graph._storage.get_pipeline(limit)

    # === What the graph COST (the model calls it took) ===

    def record_llm_usage(self, stage: str, llm_or_calls, node_id: Optional[TaskId] = None) -> int:
        """Drain a provider's per-call records into storage, tagged with the ROLE that spent them.

        The numbers were always there — per call, inside whichever verb happened to run — and were
        summarised into a progress line as text, then dropped. So the system could not answer what a
        graph cost, and anything that needed the answer (an experiment's cost column, a user asking
        why a decomposition was expensive) had to reconstruct it from its own side of the wire,
        which only ever sees the calls it makes itself. Draining is idempotent per call: the records
        are consumed here, so a second call cannot double-count them."""
        # A provider (drained) or a plain list of call records — decompose returns the records
        # rather than the provider that made them, and both are the same fact about spend.
        llm = llm_or_calls if hasattr(llm_or_calls, "calls") else None
        calls = list(llm.calls if llm is not None else (llm_or_calls or ()))
        n = 0
        for c in calls:
            # MARKED, not consumed. Clearing the provider's list made the drain idempotent and took
            # the caller's own view with it: `validate_result` returns those records as `stats`, and
            # a test that reads `llm.calls[-1]` after the verdict found an empty list. The records
            # belong to whoever made the call; this only records that they have been counted.
            if c.get("_usage_recorded"):
                continue
            self._graph._storage.log_usage({
                "ts": datetime.now().isoformat(sep=" ", timespec="seconds"),
                # THE CALL'S OWN LABEL WINS. `tag_last` exists so a caller can say which stage a
                # particular call belonged to — and the ledger threw every one of them away, writing
                # the argument this method was given instead. Two sides of one accounting said
                # different words for the same spend (`tag_last("validate_result")` against
                # `record_llm_usage("validator", …)`), and a stage nobody passed as the argument —
                # the sufficiency check, sharing the reviewer's client — never appeared at all,
                # which is how it looked like it had not run.
                "stage": c.get("stage") or stage,
                "model": c.get("model") or "", "node_id": str(node_id or ""),
                "input_tokens": c.get("input_tokens") or 0,
                "output_tokens": c.get("output_tokens") or 0,
                "cache_input_tokens": (c.get("cache_read_input_tokens") or 0)
                                      + (c.get("cache_creation_input_tokens") or 0),
                "cost_usd": c.get("cost_usd") or 0.0,
                "duration_ms": c.get("duration_ms") or 0,
            })
            try:
                c["_usage_recorded"] = True
            except Exception as e:
                log.warning(f"usage record could not be marked as counted ({e}) — the next drain may count it again")
            n += 1
        return n

    def usage_calls(self, limit: int = USAGE_PAGE) -> list:
        """The recorded model calls themselves — stage, model, node, tokens, cost, duration."""
        return self._graph._storage.get_usage(limit)

    def usage_totals(self, limit: int = USAGE_PAGE) -> dict:
        """{calls, tokens…, cost_usd, by_stage} over the recorded model calls of THIS project.

        `cost_usd` sums what the transport REPORTED; a provider that reports none contributes 0 and
        says so through `costed_calls` — a total that silently mixes "free" with "not reported" is
        the ⊥-as-zero error in a money column."""
        rows = self._graph._storage.get_usage(limit)
        tot = {"calls": len(rows), "costed_calls": 0, "input_tokens": 0, "output_tokens": 0,
               "cache_input_tokens": 0, "cost_usd": 0.0, "by_stage": {}}
        for r in rows:
            tot["input_tokens"] += r.get("input_tokens") or 0
            tot["output_tokens"] += r.get("output_tokens") or 0
            tot["cache_input_tokens"] += r.get("cache_input_tokens") or 0
            c = r.get("cost_usd") or 0.0
            tot["cost_usd"] += c
            tot["costed_calls"] += 1 if c else 0
            st = tot["by_stage"].setdefault(r.get("stage") or "?",
                                            {"calls": 0, "cost_usd": 0.0, "output_tokens": 0})
            st["calls"] += 1
            st["cost_usd"] += c
            st["output_tokens"] += r.get("output_tokens") or 0
        tot["cost_usd"] = round(tot["cost_usd"], 4)
        for st in tot["by_stage"].values():
            st["cost_usd"] = round(st["cost_usd"], 4)
        return tot

    # === Execution-validation record (the validate_result verdict; feeds the self-pass gate) ===

    def validation_in_flight(self, task_id: TaskId) -> bool:
        """Is an instrument judging THIS generation right now — asked without claiming the slot.

        `begin_validation` answers the same question by taking the slot, which a read must not do.
        Same TTL rule, so a leaked claim does not make a node permanently "being judged": a claim
        older than any run this product waits for is not a run.
        """
        key = (str(task_id), *self.generation_of(task_id))
        with self._val_lock:
            since = self._val_inflight.get(key)
            return since is not None and self._clock.now() - since <= VALIDATION_CLAIM_TTL

    def begin_validation(self, task_id: TaskId):
        """Claim the in-flight validator slot for the node's CURRENT generation (node, iteration,
        reopens). Returns the claimed key, or None if a run is already in flight — concurrent
        spawns (manual validate_result × the dispatcher's auto-validation, observed live: three
        parallel validators on one VALIDATING node) duplicate minutes of agent work whose losing
        verdict the FSM rejects anyway. Release with end_validation(key)."""
        key = (str(task_id), *self.generation_of(task_id))
        with self._val_lock:
            if (since := self._val_inflight.get(key)) is not None:
                # …UNLESS NOBODY IS BEHIND IT ANY MORE. The claim is released in a `finally`, so an
                # ORDERLY end always frees it — and a run that dies without unwinding (a killed
                # subprocess, a torn-down thread) left it set forever. The node then reads as "being
                # judged" on every surface while nothing is running, `validate_result` refuses the
                # re-run its own refusal advises, and polling never ends: measured on the agent door
                # 2026-09-02, ~15 minutes on each of two nodes with the reports already refused.
                # A claim older than any run this product will wait for is not a run; it is a leak.
                if self._clock.now() - since <= VALIDATION_CLAIM_TTL:
                    return None
                log.warning(f"the validation claim on {task_id} is older than "
                            f"{VALIDATION_CLAIM_TTL:.0f}s with nothing behind it — reclaiming")
            self._val_inflight[key] = self._clock.now()
            return key

    def generation_of(self, task_id: TaskId) -> tuple:
        """The node's CONTRACT-AND-DELIVERY generation: (iteration, reopens, revisions).

        A verdict is about the delivery a validator READ, so it must be stamped with the generation
        that stood when the run STARTED — stamping at record time makes a late verdict describe
        whatever the node has become since (a rework, a reopen, or a revision under §14.3), which is
        exactly the state the self-PASS gate then reads as current. The rule lives on the graph
        (`Graph.generation_of`) — the signal pump needs it too, and one answer is the point."""
        return self._graph.generation_of(task_id)

    def end_validation(self, key) -> None:
        """Release the in-flight validator claim taken by `begin_validation`. Idempotent: a key that is
        no longer held (reclaimed after its run died without unwinding) simply has nothing to drop."""
        with self._val_lock:
            self._val_inflight.pop(key, None)

    def record_exec_verdict(self, task_id: TaskId, verdict: str, failed_criteria: list,
                            validator_id: str, per_criterion: Optional[list] = None,
                            tools_used: Optional[dict] = None,
                            require_probe: bool = False,
                            generation: Optional[tuple] = None,
                            model: Optional[str] = None,
                            workdir: Optional[str] = None,
                            by_hand: bool = False) -> dict:
        """Store the independent validator's verdict for the node's CURRENT delivery (stamped with the
        node's GENERATION (iteration, reopens) — a rework OR a reopen invalidates it: the next
        delivery needs a fresh verdict; the superseded record is replaced, never trusted forward).

        When the report carries per-criterion evidence, the engine RECORDS ONLY A VERDICT: a report
        that leaves a criterion unspoken or contradicts its own evidence is ⊥, not a verdict (§10
        V=⋀cᵢ), and is REFUSED here — at the record, not in a prompt (visibility ≠ enforcement). The
        refusal composes with the self-PASS gate (§14.5): with no recorded PASS, the node cannot
        complete on its executor's own stamp. The evidence is persisted with the verdict — the
        Thm 11 trail must show WHAT was verified, not just the answer (§24.5: the q_V open-event
        carrier).

        RETURNS what was actually recorded — {verdict, failed_criteria} — because it is not always
        what was passed in: an underprobed criterion is demoted here, and a caller that goes on
        holding the claimed verdict signs the claim rather than the record. Measured live: a report
        claiming PASS over two criteria whose behaviours were never observed was stored as FAIL,
        logged as PASS, and signed PASS — the node closed DONE on evidence the engine had already
        refused to let carry a pass. The demotion is only a guarantee if it reaches the signal."""
        task = self.get_task(task_id)
        # A NODE WITH NO CRITERIA HAS NOTHING A VERDICT COULD BE ABOUT, whichever door produced it.
        # V is the conjunction over the node's criteria (§10), and over the empty set that is
        # vacuously TRUE — which is not a judgement. `record_verdict` refused this by name from
        # 2026-09-02; `validate_result` did not, so a stranger on the HTTP door delivered a
        # criteria-less root with "nothing to do here", had the instrument sign a `PASS` with
        # `per_criterion: []`, and reached root DONE/PASS with COMPLETE on every surface (wave 23,
        # 2026-09-03). The rule now lives where every verdict lands, so a second door cannot be
        # written past it — the guard was one door wide, which is the class this product keeps
        # finding in itself.
        if task is not None and not task.spec.criteria:
            raise ValueError(
                f"not a verdict on {task_id}: it has no criteria, so there is nothing a verdict "
                f"could be ABOUT. V is the conjunction over a node's criteria (§10), and over an "
                f"empty set that is vacuously true — which is not a judgement. Give it criteria "
                f"(`edit_criteria`) and judge those.")
        if per_criterion is not None and task is not None:
            defects = verdict_report_defects([c.name for c in task.spec.criteria], verdict,
                                             per_criterion, list(failed_criteria or ()),
                                             require_probe=require_probe)
            if defects:
                raise ValueError(f"not a verdict on {task_id} (⊥, not pass — §10): "
                                 + "; ".join(defects))
            # A criterion whose named behaviours were not all probed is UNDECIDED, not passed: the
            # report stays a verdict (it is well-formed), but an unobserved conjunct cannot carry a
            # pass (§11.2). Demoted here rather than refused above, because refusing stalls the node
            # and ends the run over an incomplete proof, while demoting sends it back for rework
            # naming exactly what was never observed — which is the loop this evidence exists for.
            # …AND A PROBE THAT NAMES A COMMAND IN A RUN WITH NO SHELL IN ITS LEDGER. Same demotion,
            # different question: `underprobed` asks whether enough was probed, this asks whether the
            # probing HAPPENED. The record has promised exactly this since `tools_used` was added
            # ("refuted structurally, without parsing a word of its prose") and nothing did it — one
            # reader in the tree, a test asserting the contradiction is merely STORED. Folded into
            # `gaps` so the disposition below (⊥ belongs to the INSTRUMENT, never to the executor's
            # rework budget) applies unchanged.
            gaps = underprobed(per_criterion)
            for _c in unrun_probes(per_criterion, tools_used):
                gaps.setdefault(_c, []).append(
                    "its probe names a command, and this judging run's tool ledger records no shell "
                    "at all — the command was not run here")
            # …EXCEPT WHERE THE REPORT REFUTED SOMETHING. Under-probing means an unobserved conjunct
            # cannot carry a PASS — that is the whole of §11.2's asymmetry — and it says nothing
            # against a criterion the report FAILED with evidence: a refutation is a decision, and
            # the evidence for "this test does not exist" is an absence, which has no `expect` line
            # to show. Measured on the human door 2026-08-21: a deliberately garbage delivery (two
            # tests, one of them `assert True`, no CLI coverage) was caught exactly right, and the
            # engine threw the FAIL away because the probes behind it had empty `expect` fields. A
            # rule against false PASSES that suppresses a true NEGATIVE is worse than the hole it
            # guards: the bad work went back looking accepted.
            _refuted = {str(e.get("criterion")) for e in per_criterion
                        if e.get("verdict") == "fail" and str(e.get("evidence", "")).strip()}
            gaps = {c: b for c, b in gaps.items() if c not in _refuted}
            if gaps:
                # …SAYING WHAT THE LINK WAS SOUGHT IN. A missing probe and a probe under another
                # wording are different facts, and both used to read "NOT OBSERVED" (HTTP door,
                # wave 27, 2026-09-06: a present, run probe refused over a paraphrase, at the cost
                # of a wasted run and a costlier retry).
                _labels = probe_labels(per_criterion)
                per_criterion = [dict(e, verdict="undecidable",
                                      evidence=f"{e.get('evidence', '')} | NOT OBSERVED: "
                                               f"{'; '.join(gaps[str(e.get('criterion'))])}"
                                               + (f" | probes on this criterion were labelled: "
                                                  f"{'; '.join(_labels[str(e.get('criterion'))])}"
                                                  if _labels.get(str(e.get("criterion"))) else ""))
                                 if str(e.get("criterion")) in gaps else e
                                 for e in per_criterion]
                # WHOSE DEFECT IS AN UNOBSERVED CONJUNCT. The behaviours are enumerated and the
                # probes are written by the VALIDATOR, so a criterion it named and did not observe
                # is a hole in ITS report — and charging that to the executor's rework budget is
                # what killed nodes carrying correct work. Measured on three independent runs
                # (2026-08-20): `slugify` finished 14 of 16 criteria `pass`, fully probed, and was
                # retired with two `undecidable` (2 probes for 3 behaviours, 2 for 4); `dedupe`
                # the same. The failed set DRIFTED between rounds — the executor fixed what was
                # named and the next report flagged a different sub-clause it had not gone to
                # check — so the loop cannot converge, and `max_iterations` (3 by default) turns
                # that into a terminal.
                #
                # So the two halves are separated. A criterion the report genuinely REFUTED is a
                # fact about the work: FAIL, rework, exactly as before. A criterion merely
                # UNDER-OBSERVED is ⊥ about the instrument, and it never enters `failed_criteria` —
                # the executor has nothing to fix there. When under-observation is the ONLY reason
                # the node cannot pass, the report is not a verdict at all: it is refused here, the
                # node stays in VALIDATING, and the dispatcher's existing path takes over — one
                # retry, then a NAMED parking for the issuer (§11.2: ⊥ is not pass).
                #
                # This is NOT the rule that was tried and withdrawn. That one refused EVERY
                # under-probed report and stalled a run for 37 minutes with no way forward; the
                # refusal here fires only when nothing was actually refuted, and it lands on
                # machinery that did not exist then — the retry-and-park loop in `delegate.py`.
                real = [c for c in (failed_criteria or ()) if c not in gaps]
                if real:
                    verdict, failed_criteria = Verdict.FAIL, sorted(set(real))
                else:
                    raise ValueError(
                        f"not a verdict on {task_id} (⊥, not pass — §11.2): the report names "
                        f"behaviours it never observed and refutes nothing, so it decides nothing. "
                        + "; ".join(f"criterion '{c}' — unobserved: {', '.join(b)}"
                                    for c, b in sorted(gaps.items()))
                        + ". Re-run the validation with a probe for EVERY behaviour each criterion "
                          "names (one command may observe several — label it with `behaviour`). "
                          "This is the instrument's gap, not the executor's: do not send the node "
                          "to rework over it. And the probes are the INSTRUMENT's to write: a caller "
                          "cannot fix them by re-running the same tier — validate_result(model="
                          f"'{MODEL_VALIDATOR_RETRY}') is what usually closes a coverage gap, and "
                          "`record_verdict` with what YOU observed is the other way through."
                        # …AND WHICH OF THE TWO GAPS THIS IS. A probe written, labelled and run, but
                        # expecting NO output, is discarded — rightly, since empty output cannot tell
                        # an absence from a command that never ran — and the message above then reads
                        # "unobserved" to someone who is looking at their probe. That is the whole
                        # distance between "write a probe" and "make this probe print something", and
                        # it cost three paid rounds on honest work before it was said out loud.
                        + (" NOTE — this report DOES carry a probe for some of these, discarded for "
                           "expecting no output: "
                           + "; ".join(f"'{c}': {', '.join(cmds)}"
                                       for c, cmds in sorted(_silent.items()))
                           + ". An absence has to SHOW: count it (`grep -rc … | grep -v ':0' | wc -l`"
                             " expecting `0`) or append `; echo exit=$?` and expect the code."
                           if (_silent := probes_that_expected_nothing(per_criterion)) else ""))
        # THE VERDICT THAT CLOSED THE NODE IS KEPT. A record may legitimately land on a node that has
        # already settled — that is q_V's whole discovery carrier, and how a pass is found to have
        # been wrong — but it OVERWROTE the one that did the closing. Measured on the HTTP door
        # 2026-09-02: a hand-asserted PASS containing false statements closed a node, an instrument
        # reported 46 seconds later, its SIGNAL was refused (the node was terminal) and its record
        # was written anyway, so every surface then said the node had been judged by an instrument
        # and the record that actually closed it was reachable from nowhere. The two surfaces this
        # product offers as its guarantee are "the record" and "in writing"; that was both of them.
        if task is not None and task.state in TERMINAL_STATES:
            _closing = self._graph._storage.get_critique(TaskId(f"{task_id}#closing-verdict"))
            if not _closing and (prior := self.get_exec_verdict(task_id)):
                self._graph._storage.store_critique(TaskId(f"{task_id}#closing-verdict"),
                                                  json.dumps(prior, default=str))
        # …AND THE SAME BEFORE THE CLOSE, WHICH THAT RULE DID NOT COVER. The block above keeps the
        # record a node CLOSED on; a verdict that overwrites a contradicting one while the node is
        # still being judged left no trace at all. Measured on the CLI door (wave 24, 2026-09-04):
        # an instrument judged a node on which nothing had been built and recorded FAIL; a
        # hand-asserted PASS naming a reviewer invented in that same call replaced it; and
        # `get_verdict` then read PASS with `failed_criteria: []`, `gfso status` showed the tick an
        # earned node gets, `next_steps` said COMPLETE and `q_V` was 1.0. The instrument's refutation
        # survived only in the chronological log. `refuted_passes` does not fire here — it is about
        # verdicts landing AFTER a close — so four of five surfaces reported an earned green.
        # A person MAY overrule an instrument: §14.5 keeps the verdict the issuer's act, and §13.6
        # says the engine cannot check a self-named party's independence. What it must not be is
        # SILENT, which is this product's whole position on the degenerate case.
        elif (prior := self.get_exec_verdict(task_id)) and prior.get("verdict") != verdict:
            _gen = tuple(generation or self.generation_of(task_id))
            if all(prior.get(k, 0) == g
                   for k, g in zip(("iteration", "reopens", "revisions"), _gen)):
                self._graph._storage.store_critique(TaskId(f"{task_id}#overruled-verdict"),
                                                    json.dumps(prior, default=str))
        store_verdict(self._graph._storage, task_id, task, verdict, failed_criteria, validator_id,
                      generation or self.generation_of(task_id),
                      per_criterion=per_criterion, tools_used=tools_used, model=model,
                      workdir=workdir, by_hand=by_hand)
        return {"verdict": verdict, "failed_criteria": list(failed_criteria or ())}

    def overruled_verdict(self, task_id: TaskId) -> Optional[dict]:
        """A verdict on THIS delivery that a later, contradicting one replaced before the close.

        Not the same fact as `closing_verdict`, which is about a record landing after the node had
        already settled. This one is the disagreement inside the judging window: two parties judged
        one delivery and said opposite things, and only the second was left standing."""
        raw = self._graph._storage.get_critique(TaskId(f"{task_id}#overruled-verdict"))
        rec = json.loads(raw) if raw else None
        if not rec:
            return None
        # Only while it is still ABOUT the standing delivery: a rework moves the generation and the
        # old disagreement is then history, not a contradiction anyone has to weigh.
        task = self.get_task(task_id)
        gen = generation_of_task(task) if task is not None else (0, 0, 0)
        return rec if all(rec.get(k, 0) == g
                          for k, g in zip(("iteration", "reopens", "revisions"), gen)) else None

    def closing_verdict(self, task_id: TaskId) -> Optional[dict]:
        """The verdict this node actually CLOSED on, when a later record has landed on top of it.

        None when nothing has overwritten it — then `get_exec_verdict` is the closing one.
        """
        raw = self._graph._storage.get_critique(TaskId(f"{task_id}#closing-verdict"))
        return json.loads(raw) if raw else None

    def record_reviewer_verdict(self, task_id: TaskId, verdict: str, failed_criteria: list,
                                reviewer: str, observed: Optional[dict] = None) -> None:
        """The HUMAN counterpart of validate_result's record: an independent reviewer's verdict on
        the node's CURRENT delivery (feeds the same self-pass gate). The engine REFUSES a reviewer
        who IS the node's executor — recording a verdict on your own work would open the
        verifier≠executor gate from the inside (§14.5 IC; visibility ≠ enforcement: the refusal is
        here, not in a prompt). FAIL requires failed_criteria (Inv-3)."""
        task = self.get_task(task_id)
        if task is None:
            raise ValueError(f"unknown task {task_id}")
        if verdict not in (Verdict.PASS, Verdict.FAIL):
            raise ValueError(f"verdict must be PASS or FAIL, got {verdict!r}")
        if verdict == Verdict.FAIL and not failed_criteria:
            raise ValueError("FAIL requires failed_criteria (Inv-3: a FAIL is never criteria-less)")
        # A VERDICT IS ABOUT A DELIVERY THAT IS STILL BEING JUDGED. On a settled node this recorded
        # happily, answered `recorded: true`, changed nothing, and then told the caller to signal —
        # which the FSM refuses, because a terminal state admits no signal (§14.3). Two false things
        # in one reply, and the second sends the reader after a move that cannot be made. The only
        # route back to judging a settled node is REOPEN, and it has its own gate (§14.3 finality).
        if task.state in TERMINAL_STATES:
            raise ValueError(
                f"{task_id} is {task.state.name} — a settled node is not being judged, so a verdict "
                f"about it changes nothing and no signal follows it (§14.3 admits none from a "
                f"terminal state). If the result must be re-judged, `reopen` it first — that is the "
                f"one route back, and it refuses a node the graph has already built on.")
        # …AND THE SAME SENTENCE APPLIES BEFORE THE DELIVERY, WHICH IT DID NOT COVER. The rule read
        # "not settled"; what it means is "there is a delivery standing to be judged", and only
        # VALIDATING is that. A node in REWORKING has had its delivery REFUSED and is redoing the
        # work: a verdict recorded there is about nothing — and it is stamped with the generation the
        # rework just moved to, so it reads as CURRENT for the delivery that has not happened yet.
        # A stranger on the CLI door used exactly that: FAIL → REWORKING → record a PASS naming a
        # reviewer invented in the same second → re-DELIVER "same delivery, nothing changed" → the
        # reply announced "an independent verdict for THIS delivery is already on the record", and
        # the executor's own PASS closed the node (wave 23, 2026-09-03; reproduced in four calls).
        # The docs promise the opposite in as many words: "a rework, a reopen or a revision under it
        # makes the record about an earlier delivery". The generation stamp cannot carry that alone —
        # it moves at the rework, so a verdict written AFTER the move looks fresh.
        if task.state != State.VALIDATING:
            raise ValueError(
                f"{task_id} is {task.state.name} — there is no delivery standing to be judged, so "
                f"there is nothing this verdict could be ABOUT. A verdict belongs to a DELIVERY "
                f"(§14.5): it is recorded while the node is VALIDATING, between the DELIVER that "
                f"offers the work and the PASS/FAIL that settles it. In REWORKING the previous "
                f"delivery was refused and the work is being redone — wait for the next DELIVER and "
                f"judge that.")
        # THE SEAM IS WHERE INDEPENDENCE IS OWED — §14.5 D6, and only there. On an INTERNAL node
        # (its Del is its parent's) the canon says the executor self-verifies, and its guarantee is
        # carried by the validation of the public result above it. This refused that everywhere, and
        # the two doors then disagreed about one act: `record_verdict` said no while `signal PASS`
        # said yes — correctly, since the FSM applies the gate on public nodes only. Measured
        # 2026-08-21: the door that would have LEFT A RECORD was the one that refused, so a lone
        # person's node reached DONE with no evidence anywhere, and the honest path was the closed
        # one. On a seam this still refuses; on an internal node the self-verdict is recorded, with
        # what was observed, which is exactly what §14.5 asks a self-verifying node to carry.
        if (task.assignee and str(reviewer) == str(task.assignee)
                and self._graph.is_public(task)):
            raise ValueError(f"reviewer {reviewer!r} is the node's own executor and {task_id} is a "
                             f"SEAM (a root, or its Del differs from its parent's) — an independent "
                             f"verdict cannot come from the executor there (verifier ≠ executor, "
                             f"§14.5). Run `validate_result`, or have someone else record it. (On an "
                             f"INTERNAL node — same Del as its parent — your own verdict IS the "
                             f"record the canon asks for, and this verb takes it.)")
        # The human's own words, stored per criterion exactly where a machine verdict stores its
        # probes — so "who accepted this, and on what" is answerable from the record either way.
        # WHICH criterion failed, from the payload that says which. This painted EVERY observed
        # criterion with the OVERALL verdict, so a reviewer who ran two criteria and saw one red and
        # one green could not record what they saw: the verb built `red = {both}`, the invariant
        # compared it with `failed_criteria = {one}` and refused the caller for a shape the VERB had
        # made. Observing only the failing one fails too ("criterion has no verdict" — ⊥ is not
        # pass), so the human path for a partial FAIL was closed in both directions while the
        # machine validator's report had always carried per-criterion verdicts (found 2026-09-05
        # while probing Inv-3). `failed_criteria` is exactly the red set (Inv-3); everything else
        # the reviewer observed passed.
        _red = {str(f) for f in (failed_criteria or ())}
        self.record_exec_verdict(
            task_id, verdict, list(failed_criteria or ()), str(reviewer),
            per_criterion=[{"criterion": k, "verdict": "fail" if k in _red else "pass",
                            "evidence": str(v)} for k, v in (observed or {}).items()] or None,
            by_hand=True)

    def record_rejected_report(self, task_id: TaskId, defects: str,
                               per_criterion: Optional[list] = None) -> None:
        """Keep a report the engine REFUSED to record as a verdict — as evidence, never as one.

        §11.2: ⊥ is not a pass, so a refused report stops the node and the issuer decides. They were
        given nothing to decide WITH: the observations lived in a return value the dispatcher does
        not read and in a text file whose path went past in a log line. This stores what the judge
        managed to observe beside the node, under its own key, so nothing can mistake it for a
        verdict and `get_verdict` can still show it to whoever has to act.

        Counts the refusals on this node, because nothing did: three ⊥ in a row on one node cost four
        paid runs, three minutes and about half a dollar with no surface anywhere saying how many
        attempts is normal (measured on the human door 2026-08-21). The count is what lets the caller
        be told, at the second one, that re-running is no longer the move."""
        prev = self.rejected_report(task_id) or {}
        # …STAMPED WITH THE DELIVERY IT IS ABOUT, and counted per delivery. Without the stamp the
        # count is a lifetime total: a node that produced two ⊥, was reworked and re-delivered
        # cleanly still reads "two reports in a row could not decide" — advice about a delivery
        # nobody attempted. It is the same generation rule every other record here carries, and the
        # frontier now reads this one, so a stale count would be advice given to a driver.
        gen = generation_of_task(self.get_task(task_id))
        _same = all(prev.get(k, 0) == g for k, g in zip(("iteration", "reopens", "revisions"), gen))
        self._graph._storage.store_critique(
            TaskId(f"{task_id}#rejected-report"),
            json.dumps({"defects": defects,
                         "per_criterion": list(per_criterion or ()),
                         "refusals": (int(prev.get("refusals", 0)) + 1) if _same else 1,
                         **dict(zip(("iteration", "reopens", "revisions"), gen)),
                         "ts": datetime.now().isoformat(sep=" ", timespec="seconds")}))

    def get_parent(self, task_id: TaskId):
        """The node's parent, or None for a root — the issuer's side of every seam question."""
        return self._graph.get_parent(task_id)

    def execution_blocked_by(self, task_id: TaskId) -> Optional[dict]:
        """Why this node's ACCEPT would be refused by the PLAN gate — or None when it is admitted.

        §13.4: a decomposition that fails the Syntactic level is not admitted to execution, and this
        engine additionally holds the Pragmatic check to have HAPPENED over this version of the plan
        with its findings dispositioned (declared in `formal/README.md`). The question was asked in
        three places with three answers: the frontier, to decide whether to offer the step; the
        dispatcher, before paying for an executor; and the affordance surface, to decide whether to
        list ACCEPT. One rule, one owner — the three of them cannot disagree about whether a node may
        start.

        Returns {why, opens_with} — the reason in the caller's own terms and the one call that opens
        the gate."""
        parent = self._graph.get_parent(task_id)
        if parent is None:
            return None                          # a root has no plan above it to admit it
        if holes := _l0_holes(self._graph, parent):
            return {"parent_id": str(parent.id),
                    "why": ("its decomposition fails the Syntactic level (§13.4): "
                            + "; ".join(f"{h.check_name}: {h.details}" for h in holes)),
                    "opens_with": f"close the holes `list_holes('{parent.id}')` lists"}
        if not l2_gate_on():
            return None
        gaps = _l2_undischarged(self._graph, parent)
        if gaps == []:
            return None
        return {"parent_id": str(parent.id),
                "why": ("no CURRENT Level-2 verdict covers its decomposition" if gaps is None else
                        f"the Level-2 review left findings open: {gaps}"),
                "opens_with": f"review_decomposition('{parent.id}')"}

    def is_seam(self, task) -> bool:
        """Is this node a delegation SEAM (§14.5 D6) — a root, or Del(child) ≠ Del(parent)?

        Where independence is owed, and therefore where the verifier ≠ executor gate fires. The
        classification is the graph's (`Graph.is_public`); this is the engine's public way to ask it,
        so the surfaces that must agree with the machine do not each reach for a private attribute."""
        return self._graph.is_public(task)

    def stored_review_findings(self, task_id: TaskId) -> Optional[list[str]]:
        """The findings of the LAST stored Level-2 review, current or not.

        `open_l2_findings` answers about the gate — and returns None the moment an edit stales the
        verdict, which is the very moment a caller re-runs the check. For "what did the previous
        review say", the record is the answer."""
        raw = self._graph._storage.get_critique(task_id)
        if not raw:
            return None
        try:
            rec = json.loads(raw)
        except (ValueError, json.JSONDecodeError):
            return None
        if not rec.get("criteria_verdicts") and not rec.get("undecided_obligations"):
            # A ROUND THAT MEASURED NOTHING IS NOT A BASELINE. A review gated out at Level 0 records
            # no findings, and comparing a later round against it reported eight genuinely closed
            # findings as zero closed (measured on the human door 2026-08-22). None means "no review
            # to compare with", which is the truth here.
            return None
        return finding_keys(rec)

    def open_l2_findings(self, task_id: TaskId) -> Optional[list[str]]:
        """The Level-2 findings still open on this node's plan — `[]` discharged, `None` no current
        verdict. The EXACT strings `dispute_review_finding` accepts, so the read surface and the
        gate cannot drift apart about what is open (the tool layer used to reach into the graph for
        this itself)."""
        node = self.get_task(task_id)
        return _l2_undischarged(self._graph, node) if node is not None else None

    def rejected_report(self, task_id: TaskId) -> Optional[dict]:
        """The last refused report on this node, or None. Evidence, not a verdict."""
        raw = self._graph._storage.get_critique(TaskId(f"{task_id}#rejected-report"))
        return json.loads(raw) if raw else None

    def deliver_result(self, task_id: TaskId) -> Optional[str]:
        """The executor's own DELIVER report — where the work lives and how each criterion is
        claimed met. Stored because the validator reads it, and reachable from no door until now:
        the frontier tells an issuer to check "the deliverable" and nothing returned it."""
        return self._graph._storage.get_deliver_result(task_id)

    def get_exec_verdict(self, task_id: TaskId) -> Optional[dict]:
        return self._graph.exec_verdict_record(task_id)

    #: the three counters that together identify WHICH delivery a record judged
    VERDICT_GENERATION = ("iteration", "reopens", "revisions")

    def current_exec_verdict(self, task_id: TaskId) -> Optional[dict]:
        """The stored verdict IF it judges the delivery that stands now, else None.

        One owner for "is this record current". `get_verdict` needed it to mark a stale record, and
        the frontier needs the same answer to know whether a VALIDATING node still needs judging or
        only a signature — and a frontier that did not ask kept saying "check the deliverable
        against criteria …" to an issuer whose validator had already reported, so the reader paid
        for a second judgement or waited for one that had already arrived (measured on the human
        door 2026-08-22)."""
        t = self.get_task(task_id)
        rec = self.get_exec_verdict(task_id)
        if t is None or rec is None:
            return None
        gen = self.VERDICT_GENERATION
        # A FAIL's OWN side effect is not evidence against it: the FAIL sent the node to REWORKING and
        # bumped its iteration, so the verdict CAUSING the current state would otherwise announce
        # itself as judging an earlier one. It stands until a new delivery is made.
        own_bump = (bool(rec.get("failed_criteria")) and t.state == State.REWORKING
                    and rec.get("iteration", 0) + 1 == t.iteration
                    and rec.get("reopens", 0) == t.reopens and rec.get("revisions", 0) == t.revisions)
        if own_bump:
            return rec
        return None if any(rec.get(k, 0) != getattr(t, k, 0) for k in gen) else rec

    # === Audit API ===

    def audit_log(self, task_id: Optional[TaskId] = None) -> list[AuditEntry]:
        """The append-only signal log — the whole graph's, or one node's. This is the record Thm 11
        and Inv-7 rest on: the node's attributes are a projection of it, never the other way round."""
        return self._audit.get_entries(task_id)

    # === Decomposition API ===

    def decompose_task(
        self,
        parent_id: TaskId,
        children: list[tuple],
        criterion_mappings: list[CriterionMapping] | None = None,
        max_iterations: int | None = None,
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
            self._assert_no_d_cycle(child_id, parent_id)   # D is a DAG (§10) — refuse the closing edge
            self.send_signal_sync(SignalData(
                signal=Signal.ASSIGN, task_id=child_id, spec=spec, source=source,
                assignee=assignee, parent_id=parent_id, deadline=deadline,
                covers=tuple(covers_by_child.get(child_id, [])),
                # The rework bound rides the ASSIGN because it is a term of the CONTRACT (§14.3),
                # decided by whoever issues the node — not a property of the process that happens to
                # be serving. Omitted, each child keeps the schema default.
                **({"max_iterations": max_iterations} if max_iterations else {}),
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

        DECLARED (discovered=False): Dep is **criteria-content** (§10) — recorded as a criterion on the
        CONSUMER (to_id) referencing from_id (glue = its description), applied via REVISE (logged, no
        bypass). A cycle is rejected (CHECK-2 / FM-4). The DepEdge is then DERIVED (graph.dep_edges()).
        DISCOVERED (discovered=True, surfaced via BLOCK): runtime provenance — stored as an edge, even if
        cyclic (the cycle IS the FM-4 finding to surface, not hide). Affects q_Dep.
        """
        if discovered:
            # Test/offline convenience ONLY. The canonical runtime path for a discovered Dep is the BLOCK
            # signal carrying `blocker_task_id` (→ RECORD_DEP effect, provisional; RESOLVE_BLOCK adjudicates —
            # §14.2/§15.2, v3.7). This direct write stays off every transport surface (tools/api/mcp/cli pass
            # discovered=False).
            self._graph._storage.add_dep_edge(DepEdge(from_id, to_id, True, glue))
            self._recompute_seam_parents(from_id, to_id)
            return
        edges = [(e.from_id, e.to_id) for e in self._graph.dep_edges()]
        edges.append((from_id, to_id))
        if not check_dag(self._graph._storage.get_all_tasks(), edges).passed:
            # …and what the caller is supposed to do about it. A Dep is criteria-content (§10) and a
            # cycle in it is an A1 violation (infinite recursion) — but "would create a cycle" alone
            # leaves a person guessing which of the two nodes they got backwards, when the existing
            # path is right there to be named.
            _path = " → ".join([str(to_id)] + [str(e.to_id) for e in self._graph.dep_edges()
                                               if str(e.from_id) == str(to_id)][:3])
            raise ValueError(
                f"dependency {from_id} -> {to_id} would create a cycle: {to_id} already reaches "
                f"{from_id} through the seams already declared ({_path}…). A Dep says the CONSUMER "
                f"waits for its PRODUCER — if the direction is backwards, `remove_dependency` the "
                f"other one first; if both really need each other, the split is wrong and the two "
                f"belong in one node (§10: the graph of D is a DAG)")
        to = self._graph.get_task(to_id)
        if to is None:
            raise ValueError(f"consumer {to_id} not found")
        if not any(c.depends_on == from_id for c in to.spec.criteria):  # idempotent
            dep_crit = Criteria(name=f"dep__{from_id}", description=glue, depends_on=from_id)
            # `scope` carried EXPLICITLY. Declaring a dependency desugars to a re-author of the
            # consumer, and this rebuilt its Spec positionally without the scope field — so the
            # node's declared boundary ("what this goal deliberately does NOT include", §13.1)
            # vanished the moment anyone drew an edge into it. Silent, and invisible in the diff:
            # the field simply defaulted to empty.
            new_spec = Spec(to.spec.description, to.spec.criteria + (dep_crit,),
                            to.spec.accepted_risks, to.spec.risk_components,
                            scope=to.spec.scope, name=to.spec.name)
            self._revise(to_id, new_spec, self.issuer_of(to_id))
        self._recompute_seam_parents(from_id, to_id)

    def remove_dependency(self, from_id: TaskId, to_id: TaskId) -> None:
        """Drop a dependency. Declared → remove the consumer's dep criterion (re-author); also clears
        any stored (discovered) edge for the pair."""
        to = self._graph.get_task(to_id)
        if to is not None and any(c.depends_on == from_id for c in to.spec.criteria):
            new_crits = tuple(c for c in to.spec.criteria if c.depends_on != from_id)
            new_spec = Spec(to.spec.description, new_crits, to.spec.accepted_risks,
                            to.spec.risk_components, scope=to.spec.scope, name=to.spec.name)
            self._revise(to_id, new_spec, self.issuer_of(to_id), severing=(from_id,))
        self._graph._storage.remove_dep_edge(from_id, to_id)
        self._recompute_seam_parents(from_id, to_id)

    def issuer_of(self, task_id: TaskId) -> AgentId:
        """WHOSE the node's issuer signals are — the parent's assignee, or the node's own for a root.

        The rule the PASS gate enforces (§14.1: the issuer forms the task and validates the result),
        published because the surfaces have to agree with it. `next_steps` marked a VALIDATE step by
        the PARENT alone, so on a root — which has none — every caller was told the step was theirs,
        including one whose signal the gate then refused (measured on the human door 2026-08-22)."""
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
        self._revise(child_id, child.spec, self.issuer_of(child_id), covers=(criterion_name,))
        return self._graph.get_task(parent_id)

    def begin_review(self, task_id: TaskId):
        """Claim the in-flight slot for THIS version of the node's plan, or None if one is running."""
        key = (str(task_id), *self.generation_of(task_id))
        with self._val_lock:
            if key in self._review_inflight:
                return None
            self._review_inflight.add(key)
            return key

    def end_review(self, key) -> None:
        """Release the slot — whether the check answered or died, so a failed round is retryable."""
        with self._val_lock:
            self._review_inflight.discard(key)

    def review_in_flight(self, task_id: TaskId) -> bool:
        """Is a Level-2 check already running over THIS version of the plan?"""
        return (str(task_id), *self.generation_of(task_id)) in self._review_inflight

    def validation_in_flight(self, task_id: TaskId) -> bool:
        """Is an independent validator run already under way for this node's CURRENT delivery?

        The in-flight set is keyed by generation (node, iteration, reopens), so a run against an
        older delivery does not mask a node that needs judging again."""
        since = self._val_inflight.get((str(task_id), *self.generation_of(task_id)))
        return since is not None and self._clock.now() - since <= VALIDATION_CLAIM_TTL

    def contest(self, task_id: TaskId, why: str) -> None:
        """Record that the node's EXECUTOR disputes its contract from a state where CHALLENGE is not
        admissible (§14.3 admits it from OFFERED only). The frontier hands it to the issuer, whose
        `revise` settles it by construction — the node returns to OFFERED to be taken afresh."""
        self._contested[str(task_id)] = (why or "no reason given")[:600]

    def contested_reason(self, task_id: TaskId) -> Optional[str]:
        """Why this node's executor disputes its contract, or None."""
        return self._contested.get(str(task_id))

    def _revise(self, task_id: TaskId, new_spec: Spec, agent: AgentId,
                new_assignee: Optional[AgentId] = None, covers: tuple = (),
                reason=None, severing: tuple = ()) -> Task:
        """Canon v3.7 Inv-1 (§14.4): a spec/Del change = REVISION — ONE re-ASSIGN under the SAME id → OFFERED,
        never an in-place mutation and never the CANCEL signal (revision ≠ abandonment; no CANCELLING pass,
        no cascade). The id persists (Inv-7) so references (the parent's mapping, dependents' depends_on)
        stay valid; the superseded contract lives in the append-only log. `agent` must be the issuer
        (ASSIGN is an issuer signal → FSM-validated). Returns the revised node (back in OFFERED —
        the executor must re-ACCEPT)."""
        old = self._graph.get_task(task_id)
        if old is None:
            raise ValueError(f"task {task_id} not found")
        # A Dep SEAM RIDES IN `criteria`, AND AN EDGE IS NOT DELETED BY OMISSION. `edit_criteria`
        # has carried `dep__*` across a replacement since 2026-08-20, with the argument written
        # out there: nobody editing what a node must ACHIEVE is asking to sever what it WAITS
        # FOR, and the loss is invisible until a consumer runs against an input nothing connected
        # it to. That rule sat on ONE door. `revise` — the verb whose whole contract IS wholesale
        # replacement — went straight past it, so the defect the comment describes happened
        # through the widest door onto the same edge. Two strangers hit it the same afternoon
        # (2026-09-05), and the graph then read CLEAN: `list_holes` empty and CHECK-2 answering
        # "D acyclic; no dependency edges" — a check passing because its subject was destroyed.
        # Carried here, at the chokepoint every spec change lands on. Removing an edge stays
        # possible and stays EXPLICIT — `remove_dependency` says WHICH producer it is severing
        # (`severing`), and nothing else can sever one. Without that the carry became a CAGE:
        # `remove_dependency` re-authors the consumer WITHOUT the criterion, which is exactly
        # the shape being defended against, so the edge came straight back and the verb for
        # deleting edges stopped deleting them (caught by its own test, minutes after the fix).
        if new_spec is not None and old.spec.criteria:
            _named = {c.name for c in (new_spec.criteria or ())}
            _cut = set(severing)
            _carry = tuple(c for c in old.spec.criteria
                           if c.depends_on and c.name not in _named and c.depends_on not in _cut)
            if _carry:
                new_spec = Spec(new_spec.description, tuple(new_spec.criteria or ()) + _carry,
                                new_spec.accepted_risks, new_spec.risk_components,
                                scope=new_spec.scope, name=new_spec.name)
        # Snapshot the CONTENT before the signal: ASSIGN applies the new spec onto the same live
        # object, so reading `old.spec` afterwards compares the new contract with itself.
        _before = (old.spec.description, old.spec.criteria, old.spec.accepted_risks,
                   old.spec.scope, old.spec.name)
        _old_parent = old.parent_id
        a = self.send_signal_sync(SignalData(
            signal=Signal.ASSIGN, task_id=task_id, spec=new_spec, source=agent,
            assignee=new_assignee or old.assignee, covers=tuple(covers),
            revision_reason=reason))
        if a is None or a.rejected:
            # WHICH of the three, said by name. The refusal printed the node's state and then a
            # disjunction asserting it was in states it demonstrably was not — measured 2026-08-20:
            # `state=State.OFFERED` followed by "the node is in OVERDUE/CANCELLING/ESCALATED … or
            # the agent is not its issuer", with a Python repr leaked into it. Each branch is
            # cheap to ask, and each has a different answer.
            st = self.get_state(task_id)
            cur = self._graph.get_task(task_id)
            issuer = self.issuer_of(task_id)
            if st is not None and st.name in ("OVERDUE", "CANCELLING", "ESCALATED"):
                why = (f"a node in {st.name} takes no revision (§14.3). "
                       + ("It is terminal: recovery is re-decomposition around it by ITS issuer."
                          if st.name == "ESCALATED" else
                          "Let it settle first — the clock or the cancellation handshake decides."))
            elif st is not None and st.name in ("DONE", "ABANDONED"):
                why = (f"{task_id} is {st.name} and the R′ finality-gate refused it: it is either "
                       f"CONSUMED (the graph built on this result — then it is locked for good and "
                       f"the repair is re-decomposition) or out of reopens "
                       f"({cur.reopens}/{cur.max_reopens} spent). "
                       f"`reopen` names which.")
            elif str(agent) != str(issuer):
                why = (f"'{agent}' is not the issuer of {task_id} — its issuer is '{issuer}' (the "
                       f"parent's Del, or the node's own for a root), and a contract is revised by "
                       f"the side that set it (§14.2).")
            else:
                # …AND ONLY IF IT REALLY DID. This sentence was printed whenever the node had not
                # moved, whatever the reason — including a step that RAISED and was dropped, which
                # is a fact about a malformed value and not about the FSM. A tester read it as the
                # plan-repair verbs being closed in the states nodes actually occupy and worked
                # around a wall that was not there (agent door, 2026-09-02). §14.3 admits ASSIGN
                # from every reassignable state, so "the FSM refused" is a claim that has to be
                # checked against the record before it is made.
                _rejected = any(a.rejected for a in self.audit_log(task_id)[-4:])
                why = ((f"the FSM refused ASSIGN in {st.name if st else '?'} — see the audit log for "
                        f"the recorded rejection.") if _rejected else
                       (f"the revision did not take, and the FSM recorded no refusal — the step was "
                        f"dropped before it reached {task_id} (the server log carries the reason). "
                        f"§14.3 admits ASSIGN from {st.name if st else 'this state'}, so this is not "
                        f"a rule refusing you: read the log, or re-read the node and try again."))
            raise ValueError(f"revise refused on {task_id}: {why}")
        # Did the CONTRACT change, or only who holds it? A delegation carries the same spec and a
        # new Del; the parent's Level-2 claim is about the children's criteria, not their owners.
        # A revision is the answer to a dispute — the node goes back to OFFERED under a contract its
        # executor gets to take or refuse afresh, so the recorded dispute is settled by construction.
        self._contested.pop(str(task_id), None)
        content_changed = (new_spec.description, new_spec.criteria, new_spec.accepted_risks,
                           new_spec.scope, new_spec.name) != _before or bool(covers)
        self._recompute_checks(task_id, stale_review=content_changed)   # kept its subtree → refresh
        if _old_parent:
            self._recompute_checks(_old_parent, stale_review=content_changed)
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
        """Every Dep edge in this graph, declared and discovered alike — `q_Dep` is their ratio."""
        return self._graph.dep_edges()

    # === Projection API (read-only critic input contract) ===

    def project(self, node_id: TaskId) -> str:
        """Read-only markdown projection of a node's decomposition (critic input).

        The unit a semantic critic reasons over: goal + breakdown (subtasks,
        criteria, coverage, seams, ACCEPTED_RISKS) + already-run Solver checks.
        """
        node = self._graph.get_task(node_id)
        if node is None:
            raise ValueError(f"node {node_id} not found")
        children = self._graph.get_active_children(node_id)  # critic reasons over the ACTIVE decomposition
        deps = self._graph.dep_edges()
        checks = self.get_checks(node_id)  # one on-demand path (no stale store)
        # Build the typed NodeProjection, then render it at the LLM/API str boundary.
        return render_projection(build_projection(node, children, deps, checks))

    # === Actions API (per-role affordances, §14.2) ===

    def nodes_with_a_refused_report(self) -> list[str]:
        """Nodes where a judge ran, reported, and the engine refused the report as ⊥ (§11.2).

        NOT a contradiction and NOT a blocker: ⊥ is not fail, and treating it as one is the precise
        error the canon names. But it must be VISIBLE where completion is announced — measured on
        the HTTP door 2026-09-02, an instrument returned ⊥ on a root that had closed by hand
        forty-six seconds earlier, and `next_steps` went on answering "the goal is met" with nothing
        anywhere saying a judge had tried and failed to decide it.
        """
        return [str(t.id) for t in self.all_tasks() if self.rejected_report(t.id)]

    def closed_over_an_open_plan_review(self, root_id: Optional[TaskId] = None) -> list[str]:
        """Settled nodes whose OWN current Level-2 review still names findings nobody dispositioned.

        The gate holds a parent's CHILDREN until its plan is dispositioned — so on a decomposed node
        this cannot happen. On a LEAF it can: there are no children to hold, the review is advisory,
        and nothing consulted it before answering COMPLETE. Two doors closed a leaf root on
        vacuous-but-true criteria and read the contradiction straight off the database (wave 25,
        2026-09-05): `get_review` → `execution_admitted: false` and `next_steps` → `complete: true`,
        same node, same second, and the one that says done is the one that never asks.

        Advisory means advisory: this does not withhold `complete`, because the checker is an
        a-priori approximation (§13.5) and the real Level-2 verdict is contact's. What it does is
        stop the two surfaces from disagreeing in silence.
        """
        return [str(t.id) for t in self._within(root_id)
                if settled_positive(t) and (self.open_l2_findings(t.id) or [])]

    def _within(self, root_id: Optional[TaskId] = None) -> list:
        """The nodes a question scoped to `root_id` is about: that node and its subtree, else all.

        The id-prefix convention was spelled out at four call sites, which is four chances for one
        of them to scope differently from the rest — the exact shape of "a rule that holds at one
        door and not at the next".
        """
        tasks = self.all_tasks()
        if root_id is None:
            return tasks
        return [t for t in tasks if t.id == root_id or str(t.id).startswith(f"{root_id}.")]

    def closure_of(self, task_id: TaskId) -> Optional[dict]:
        """How ONE node closed: who produced the standing verdict, and what it displaced or contradicts.

        The per-node owner of the facts `_how_this_closed` reports over a whole graph. It exists
        because the graph-wide lists were the ONLY place they were said, and a list of ids is a
        fact about a project, not about the node a reader is looking at: `/api/tasks/<id>` carried
        no verdict provenance at all, so the page a person watches drew every DONE node the same —
        the one earned through an instrument's probes and the one asserted by a name invented in
        the same command (wave 26, 2026-09-06, named by three doors independently).

        None for a node that has not settled positive: there is no closure to describe, and an
        empty dict there would read as "closed, nothing to weigh". The three list methods below
        filter on settledness and then read THIS — one predicate per fact, so a surface and a list
        cannot come to disagree about one node.
        """
        t = self.get_task(task_id)
        if t is None or not settled_positive(t):
            return None
        rec = self.get_exec_verdict(task_id) or {}
        displaced = self.overruled_verdict(task_id) or {}
        return {
            # by_hand / self / instrument / none — §13.6's three weights of evidence
            "provenance": self.verdict_provenance(task_id),
            "by_hand": bool(rec.get("by_hand")),
            # a hand verdict that replaced an instrument's OPPOSITE one on the same delivery
            "overruled": bool(displaced and not displaced.get("by_hand") and rec.get("by_hand")),
            "overruled_verdict": (str(displaced.get("verdict")) if displaced else None),
            # standing at PASS while its own current record says FAIL — a green that is not green
            "refuted": pass_was_refuted(self._graph, t),
            "validator": rec.get("validator"),
        }

    def closures_by_hand(self, root_id: Optional[TaskId] = None) -> list[str]:
        """Settled nodes whose standing verdict was ASSERTED BY HAND, not produced by an instrument.

        The §14.5 degenerate case, and §13.6's named boundary: at a door where a person names
        themselves, the engine cannot establish that the reviewer is independent or that the
        observations happened. That is a declared limit, not a defect — what was a defect is that it
        was declared in one place and invisible in the two a reader consults. THREE doors reported
        the same thing across two waves (2026-09-04/05): a root closed with zero work through an
        invented reviewer, and `status`, `next_steps` and `q_V` gave it exactly what an earned root
        gets, while `get_verdict` and `gfso log` said plainly whose word it rested on.

        Not a reason to withhold `complete`: a person judging their own project by hand is the
        product's documented solo path. It is the one fact about such a graph a reader must not have
        to ask a second verb for. `hand_overruled_closures` is the sharper subset — those also
        displaced an instrument that said the opposite.
        """
        return [str(t.id) for t in self._within(root_id)
                if (self.closure_of(t.id) or {}).get("by_hand")]

    def hand_overruled_closures(self, root_id: Optional[TaskId] = None) -> list[str]:
        """Settled nodes that closed on a HAND verdict which displaced an instrument's opposite one.

        The sibling of `refuted_passes`, for the other order of events. There, the instrument's
        refutation lands after the signature and the state is left showing the signature. Here it
        landed FIRST, on the same delivery, and a self-named party's record replaced it before the
        close — so the node's current verdict agrees with its state and nothing was contradicted at
        the moment anyone looked (CLI door, wave 24, 2026-09-04).

        Overruling is legitimate: the verdict is the issuer's act (§14.5), and §13.6 says no
        structural check can establish that a self-named reviewer is independent. So this is not a
        reason to withhold `complete` — a run where a person correctly overrode a wrong instrument
        would never finish. It is the one fact about such a graph that a reader has to weigh, and
        the surfaces carry it beside the answer instead of instead of it.
        """
        return [str(t.id) for t in self._within(root_id)
                if (self.closure_of(t.id) or {}).get("overruled")]

    def refuted_passes(self, root_id: Optional[TaskId] = None) -> list[str]:
        """Nodes standing at PASS whose OWN current record says FAIL — a green that is not green.

        The engine has always detected this (it is q_V's numerator, and `q_V_from` names the nodes),
        but only the metric said so: measured on the CLI door 2026-09-02, a node signed PASS, an
        instrument returned FAIL four seconds later, the FSM correctly refused that signal because
        the node was terminal — and from then on `status` printed `[x] DONE` and the frontier
        answered COMPLETE, permanently, while `get_verdict` on the same node said FAIL. Two sources
        of truth disagreeing, with every surface a person reads on the wrong side of it.

        One predicate, and the surfaces read it rather than each deciding for themselves.
        """
        return [str(t.id) for t in self._within(root_id)
                if (self.closure_of(t.id) or {}).get("refuted")]

    def verdict_provenance(self, task_id: TaskId) -> str:
        """WHAT KIND OF PARTY produced this node's standing verdict: by_hand / self / instrument.

        Three kinds, not two. A record a person asserted at a door where identity is self-declared,
        an INTERNAL node's own executor stamping its DELIVER (§14.5 D6), and a registered instrument
        that is somebody other than the executor are three different weights of evidence, and the
        read collapsed the middle one into the last: a self-report came back as "produced by the
        registered instrument named in `validator`" while the evidence line beside it said
        SELF-REPORTED (measured on the MCP door 2026-09-02). Anything keying on the summary read a
        self-stamp as an independent check.

        The dispatcher has decided this correctly since the day it stopped REUSING a self-report as
        an independent verdict — the same comparison, in the same words. One owner, so the two
        cannot drift into disagreeing about one record.
        """
        rec = self.get_exec_verdict(task_id)
        if not rec:
            return "none"
        if rec.get("by_hand"):
            return "by_hand"
        task = self.get_task(task_id)
        if task is not None and str(rec.get("validator") or "") == str(task.assignee or ""):
            return "self"
        return "instrument"

    def parked_validations(self) -> frozenset:
        """Nodes whose automatic judging has GIVEN UP — read by the doors, written by the dispatcher.

        Asked through a method because a door reaching for the field by `getattr` with a default is
        the duck-typed private reach the coupling ratchet counts, and because the default silently
        turns "the engine has no such idea" into "nothing is parked" — the two are not the same
        answer and only one of them is true."""
        return frozenset(self._validation_parked)

    def publish_bound_judge(self, task_id: TaskId, judge: Optional[dict]) -> None:
        """The dispatcher's half of `bound_judge` — who it will send at this node, for the doors.

        A method rather than an attribute the dispatcher writes: the coupling ratchet counts a reach
        into another module's private field, and it was right to — what the doors need is a fact
        this object owns, not a dictionary somebody else keeps in it."""
        if judge and judge.get("id"):
            self._bound_judges[str(task_id)] = dict(judge)
        else:
            self._bound_judges.pop(str(task_id), None)

    def bound_judge(self, task_id: TaskId) -> dict:
        """The instrument the dispatcher bound to this node, as facts a door may read: id, project,
        workdir. `{}` when nothing is bound.

        Published FROM the dispatcher, exactly like `_roster` and `authorized_validators`, because
        the doors may not reach into the delegation layer to ask (the mechanical layer gate) and the
        answer depends on the roster, which is that layer's. What the doors do with it is say WHOSE
        judge is about to read their work — a role registered for another project, standing in a
        directory that holds none of this delivery, was announced as "an independent validator" and
        five strangers had to read the log to find out (waves 23–25)."""
        return dict(self._bound_judges.get(str(task_id)) or {})

    def judged_by_instrument(self, task_id: TaskId) -> bool:
        """Will a registered instrument judge this node's delivery without being asked?

        Two facts, and both live here: an instrument is published to the graph (the dispatcher does
        it each round), and the node's ISSUER is automated — a person's node is judged FOR them and
        then waits for their signature, so only an automated issuer makes the instrument's verdict
        the signal too. Asked as one question because every surface that answers "wait" or "act"
        needs the same one, and a door that composed it for itself would reach past this object into
        the graph (and, in its first spelling, into the delegation layer the layer gate forbids it).
        """
        task = self.get_task(task_id)
        if task is None or not self._instrument_for_this_project():
            return False
        issuer = str(self.issuer_of(task_id))
        return issuer == _config_agent_id() or self.kind_of(issuer) is not None

    def _instrument_for_this_project(self) -> bool:
        """Is any published instrument one that would be given THIS project's nodes?

        The roster is one server-wide file, so "an instrument is registered" and "an instrument will
        judge you" are different facts, and this asked the first while every caller meant the second.
        Measured on the HTTP door 2026-09-06: a project that had registered nothing was told on every
        delivery to wait for a bound validator, because other projects' roles filled the set — and the
        same sentence told them that recording their own verdict "would race it". There was nothing
        to race. The scoping is `validator_for`'s, said once more: this project's roles, or UNSCOPED
        ones (which are shared by design), never another project's.
        """
        whose = self._validator_projects
        if not whose:                          # nothing published yet — the set is all we know
            return bool(self._graph.authorized_validators)
        # THE DECLARED SPELLING. This engine carries the project under two names — `project_name`,
        # which every reader in the product uses, and `_project_name`, which `runtime` also sets
        # and calls "the older spelling, still read downstream". A third one written here would
        # be the same defect one turn later.
        mine = self.project_name or DEFAULT_PROJECT
        return any(p in (None, "", mine) for aid, p in whose.items()
                   if aid in self._graph.authorized_validators)

    def publish_validator_projects(self, whose: dict) -> None:
        """The dispatcher's answer to "whose is each instrument" — `{validator id: project or None}`.

        A setter rather than an attribute the dispatcher writes into, for the same reason
        `publish_bound_judge` is one: the layer below must not be reached into from the layer above,
        and a field written from outside is a field with no owner.
        """
        self._validator_projects = dict(whose or {})

    def now(self) -> float:
        """This engine's clock reading — the ClockPort's, never the wall's.

        Published because callers that WAIT need it and were reaching into `_clock` to get it: a
        fake-clock host must not be made to sit through a real wait just because a door asked the
        wrong object.
        """
        return self._clock.now()

    def unmet_producers(self, task_id: TaskId) -> list[str]:
        """The nodes this one consumes that have not passed — the reason it cannot start yet.

        §14.3 admits ACCEPT from OFFERED whatever the seams say, and the engine is not narrower than
        the canon: taking a node is allowed. What the frontier knew and the ACCEPT reply did not was
        that the work cannot begin — so a graph showed EXECUTING for nodes provably unable to run
        (CLI door, 2026-09-02). One owner for the question the frontier already asks.
        """
        # The id is compared and looked up as a STRING: a malformed edge that carried a list once
        # reached the DAG check and raised `unhashable type` inside the protocol step (2026-09-02).
        # The door refuses that value now, and a read is still not the place to fall over it.
        return sorted({str(e.from_id) for e in self._graph.dep_edges()
                       if str(e.to_id) == str(task_id)
                       and not passed(self._graph.get_task(TaskId(str(e.from_id))))})

    def say_once(self, key: str) -> bool:
        """True the FIRST time this key is asked about, False afterwards — for a line that must be
        said once per node rather than once per poll.

        Owned here because the callers are not one object: the dispatcher has its own bag for its own
        notices, and a free function that needed the same thing duck-typed a private attribute onto
        this engine — which both instruments caught in the same run.
        """
        if key in self._said_once:
            return False
        self._said_once.add(key)
        return True

    def kind_of(self, agent_id: str) -> Optional[str]:
        """What KIND of participant this id is — `llm-executor` / `llm-validator` / … — or None for
        a human (an unregistered Del IS a human, §14.5). The roster is the dispatcher's, published
        downward; this is the question the read surfaces actually ask, so they ask it rather than
        reading the map."""
        return self._roster.get(str(agent_id))

    def signs_as_instrument(self, agent_id: str) -> bool:
        """Is this id the issuer's authorized role-V instrument (§14.5)? One owner for the question:
        the surfaces that must agree with the seam gate used to read the graph's own field."""
        return str(agent_id) in self._graph.authorized_validators

    def refusal_of(self, task_id: TaskId, signal: Signal, entry=None) -> SignalOutcome:
        """The system's answer to a transition that moved nothing — ONE record, every door.

        The kinds are not decoration: a signal the STATE does not admit, a signal it admits whose
        transition GUARD said no, and a signal a RULE above the FSM refused (the seam's verdict, the
        AND over children, the plan gate) are three different facts, and a caller who cannot tell
        them apart cannot tell "wrong button" from "not yet" from "not yours". The log's own entry
        is preferred when it carries the reason, because that is the sentence the engine already
        wrote for this exact attempt."""
        st = self.get_state(task_id)
        _admits = [s for s in self.available_actions(task_id)]
        _why = entry.error if entry is not None else None
        if _why:
            kind = ("rule" if signal in _admits else "state")
        elif signal in _admits:
            kind, _why = "guard", (f"{signal.name} is admitted by state {st.name if st else '?'} but "
                                   f"its transition GUARD refused it — the precondition does not "
                                   f"hold for this node")
        else:
            kind, _why = "state", (f"{signal.name} is not admitted by state {st.name if st else '?'} "
                                   f"(§14.3) — admitted here: "
                                   + ", ".join(s.name for s in _admits))
        return SignalOutcome(task_id=task_id, signal=signal, accepted=False, from_state=st,
                             refusal=Refusal(kind=kind, why=_why))

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
        # EVERY role the agent holds, not the first one found. One person is routinely both the
        # node's executor and (through its parent) its issuer — the ordinary solo case — and
        # resolving to EXECUTOR alone made this verb answer `[]` on a node the FSM would happily
        # move for them. Measured 2026-08-20: a person was told they had no action while `signal
        # PASS` on that same node was accepted; the affordance surface and the machine disagreed.
        roles = self._roles_of(agent_id, task)
        if not roles:
            return []
        return [s for s in sigs if required_role(s) in roles]

    def _roles_of(self, agent_id: AgentId, task: Task) -> set:
        """All roles this agent holds on the node — executor and issuer are not exclusive."""
        roles = set()
        if task.assignee == agent_id:
            roles.add(Role.EXECUTOR)
        parent = self._graph.get_parent(task.id) if task.parent_id else None
        if parent and parent.assignee == agent_id:
            roles.add(Role.ISSUER)
        if task.parent_id is None:
            roles.add(Role.ISSUER)            # a root is issued by whoever assigned it in
        return roles

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
        """Every node in that state, terminal states included."""
        return [t for t in self._graph._storage.get_all_tasks() if t.state == state]

    def tasks_by_assignee(self, assignee: AgentId) -> list[Task]:
        """Every node held by that participant (Del), whatever state it is in."""
        return [t for t in self._graph._storage.get_all_tasks() if t.assignee == assignee]

    def all_tasks(self) -> list[Task]:
        """Every node of this graph, including the settled ones."""
        return self._graph._storage.get_all_tasks()

    # === Execution forcing-point ===

    def _nothing_to_take(self, tasks, deps, _deps_ready, _passed) -> dict:
        """The answer when no node is takeable: working, blocked by dep order, or stuck.

        Three different facts share one silence — an instrument is running, a producer has
        not passed, or a settled-negative node has stopped the graph — and telling them
        apart is the whole value of this branch. It lived inside `_frontier`, which made
        that function answer two unrelated questions in ninety statements."""
        # NAME WHAT IS IN THE WAY. "Inspect node states" is true and useless: the caller is
        # looping `next_steps` under an instruction that says loop until complete, and the one
        # thing it needs — which node made completion impossible — is the thing it was not
        # told. Measured live (2026-08-20): two leaves escalated under a root, the frontier
        # returned no steps, and the driving agent tried four recovery verbs against a node it
        # had to find by reading the raw graph. A settled-negative node is exactly where the
        # canon sends the issuer (§14.3: exhausting the bounded FAIL↔REWORKING loop IS the
        # escalation trigger, and ESCALATED means "this needs attention"), so the frontier says
        # so by name rather than making the reader look.
        # NOTHING TO TAKE IS NOT THE SAME AS STUCK. A node being judged, or an executor
        # working, is the graph doing exactly what it should — and this branch called it a
        # block, told the reader the dependency order was at fault, and prescribed
        # `remove_dependency` on a correct edge. Measured on BOTH doors 2026-08-22: four
        # occurrences in one run with a validator mid-flight (`list_holes` empty, producers
        # DONE), and ten minutes of polling on the other while the verdict was already on the
        # record. What is running is a fact the engine holds; it is said here first.
        _running = self.in_flight_nodes()
        if _running:
            return {"complete": False, "stuck": False, "steps": [], "in_flight": _running,
                    **({"waiting": list(self._held_by_plan)} if self._held_by_plan else {}),
                    "directive": (
                        "Nothing to take right now — the graph is working: "
                        + "; ".join(f"'{w['task_id']}' {w['why']}" for w in _running)
                        + ". Those arrive by themselves; a second instrument on the same "
                          "delivery would judge it twice. Poll again in a minute.")}
        stranded = self.stranded_nodes()
        where = "; ".join(f"'{t.id}' ({t.spec.name or t.id}) is {t.state.name}"
                          for t in stranded)
        waiting = [
            f"'{t.id}' waits on " + ", ".join(
                sorted(f"'{e.from_id}'" for e in deps if e.to_id == t.id
                       and not (self._graph.get_task(e.from_id) is not None
                                and _passed(self._graph.get_task(e.from_id)))))
            for t in tasks
            if t.state in (State.OFFERED, State.EXECUTING, State.REWORKING)
            and not _deps_ready(t.id)]
        return {"complete": False, "stuck": True,
                "blocked_by": [str(t.id) for t in stranded],
                "directive": (
                    f"Stuck: no actionable node, and the root is not DONE/PASS. {where} — a "
                    f"settled node the graph cannot move past, and the canon hands that to the "
                    f"ISSUER (§14.3). Re-decompose around it (revise the parent so another child "
                    f"carries the criteria it left uncovered); a terminal node is not reopened."
                    if stranded else
                    # …and when the hold IS the dependency order, name the pair. The frontier
                    # now gates OFFERED and REWORKING on producers too (a leaf handed out before
                    # its input exists can only BLOCK), so this branch is reachable with every
                    # node simply waiting — and "check the Dep producers" would leave the reader
                    # to work out which, exactly as the ESCALATED case used to.
                    (f"Stuck: no actionable node, and the root is not DONE/PASS. What is waiting "
                     f"is the dependency order: " + "; ".join(waiting) + ". Those producers are "
                     f"not PASSED, and nothing else can run meanwhile — drive them, or drop the "
                     f"edge (`remove_dependency`) if it was declared in error."
                     if waiting else
                     "Stuck: no actionable node, but the root is not DONE/PASS — and nothing is "
                     "settled-negative either, so the block is structural: check `list_holes` and "
                     "the nodes' Dep producers."))}

    def _step_for(self, t, kids, crits, nm, cands, held, _deps_ready, _passed):
        """What the holder of this node is asked to do next — one answer per state.

        Sign a verdict already on the record · judge one that is not · repair a plan a
        re-delivery cannot save · fix what failed · take the node · aggregate · confirm a
        cancellation. Seven answers to one question, which is not the question the plan gate
        answers, and they shared a body with it. None = nothing to offer for this node."""
        if t.state == State.VALIDATING:
            # On a SEAM, say what a PASS costs before it is refused. The directive read "signal
            # PASS if every criterion holds" to everyone, including the very executor whose PASS
            # the gate rejects (§14.5) — so a person following it literally walked into the
            # refusal, and one who happened to hold both roles walked into the belief that they
            # had signed something. The instrument is named here, where the reader already is.
            seam = self._graph.is_public(t)
            if (_rec := self.current_exec_verdict(t.id)) is not None:
                # THE JUDGING IS DONE; ONLY THE SIGNATURE IS MISSING. The step still read "check
                # the deliverable against criteria …" after the validator had reported on THIS
                # delivery, so the reader either ran a second instrument over the same artifact
                # or waited for a report already on the record (measured on the human door
                # 2026-08-22). What is owed here is the signal, and the record is what it is
                # signed on — `get_verdict` reads it in full.
                _f = _rec.get("failed_criteria") or []
                cand = (1, t, Action.VALIDATE,
                        # …AND CALL IT WHAT IT IS. On an internal node the record is legitimately
                        # the executor's own self-check (§14.5 D6) — and this sentence called that
                        # "an independent verdict … by agent", where `agent` was the executor who
                        # had just delivered it (agent door, 2026-09-02). The record says which kind
                        # of party produced it; the directive has to read the same field.
                        f"SIGN THE VERDICT on '{t.id}' ({nm}): "
                        + ("the executor's own self-check for THIS delivery is on the record "
                           "(§14.5 D6 lets an internal node self-verify)"
                           if str(_rec.get("validator") or "") == str(t.assignee or "")
                           else "an independent verdict for THIS delivery is already on the record")
                        + (f" by {_rec['validator']}" if _rec.get("validator") else "")
                        + " — " + (f"{Verdict.FAIL} on {', '.join(map(str, _f))}" if _f
                                    else str(Verdict.PASS))
                        + f". Read it with `get_verdict {t.id}`, then signal "
                        + (f"{Verdict.FAIL} with those criteria." if _f else f"{Verdict.PASS}.")
                        + " Judging it again would judge the same artifact twice.")
                return cand
            # …and the ISSUER's own share of the same fact: a criterion that has failed round
            # after round is a criterion to re-read, not only a delivery to judge. The engine
            # knows the count; whoever holds the verdict was never told it.
            _stuck_note = (f" NOTE: {', '.join(_st)} has failed {self.CONTRACT_SUSPECT_ROUNDS} "
                           f"rounds running here. If the criterion cannot be met as written, the "
                           f"repair is the CONTRACT — `edit_criteria('{t.id}', …)` (a revision, "
                           f"Inv-1) — not another FAIL."
                           if (_st := self.stuck_on(t.id)) else "")
            # …AND WHETHER AN INSTRUMENT HAS ALREADY TRIED AND COME BACK WITH NOTHING. The engine
            # stores every refused report on the node, with a count, and tells the CALLER of
            # `validate_result` what it means — but the caller of a hand-driven validation is not
            # the person who comes back to the graph later, and the step they read said "VALIDATE
            # this" as though nothing had happened. Three doors measured the consequence as the same
            # symptom: a node sitting in VALIDATING for twelve minutes, forty-five minutes, or
            # "forever", with the frontier cheerfully naming a step that was never going to
            # complete (wave 23, 2026-09-03). The dispatcher's own path has said this since August
            # (`_validation_parked`); the hand-driven one had the fact and no reader.
            _bot = self._bottom_attempts(t)
            _bot_note = (f" NOTE: {_bot} instrument report(s) on THIS delivery produced no verdict "
                         f"(⊥ is not a pass, §11.2) — `get_verdict {t.id}` shows what they did "
                         f"manage to check. "
                         + ("Re-running the same tier usually returns the same gap: try a stronger "
                            "model, or record your own verdict with what you observed."
                            if _bot < 2 else
                            "Do NOT run the same tier again: repeated ⊥ on one node is about the "
                            "CONTRACT, not the run — narrow what this node promises "
                            f"(`edit_criteria('{t.id}', …)`), escalate the model, or record your "
                            "own verdict.") if _bot else "")
            cand = (1, t, Action.VALIDATE,
                    f"VALIDATE '{t.id}' ({nm}): check the deliverable against criteria {crits}; signal "
                    f"PASS if every criterion holds, else FAIL with the failed criteria."
                    + _bot_note
                    + _stuck_note
                    + (f" This node is a SEAM, so its own executor ({t.assignee}) cannot sign a "
                       f"PASS until an INDEPENDENT verdict is on the record for this delivery — "
                       f"`validate_result` (a fresh read-only agent that RUNS the criteria) or "
                       f"`record_verdict` by another person. With one recorded, the signal is "
                       f"accepted from them as usual." if seam else ""))
        elif t.state == State.REWORKING and (_refusal := self._redelivery_refusal(t)):
            # THE DIRECTIVE MUST NOT ASK FOR A DELIVERY THE GATE WILL REFUSE. When the failed
            # criteria are covered by children nobody touched, contact refuted the DECOMPOSITION
            # and a re-DELIVER is rejected on arrival (§15.2 q_D, FM-1.d/f) — but the step still
            # read "fix exactly what failed, then DELIVER again". Measured 2026-08-20 on a
            # measurement run: three full rework rounds against that wall, ~13 minutes and two
            # executor calls each, and the run ended `redelivery_refused` with the graph exactly
            # where it started. The engine already knows the repair; this is it, said BEFORE the
            # work rather than after.
            cand = (2, t, Action.REVISE,
                    f"REPAIR THE PLAN of '{t.id}' ({nm}) — a re-DELIVER here is REFUSED, and "
                    f"redoing the aggregate cannot help: {_refusal}")
        elif t.state == State.REWORKING:
            if not _deps_ready(t.id):
                return None  # same dep order as EXECUTING: a rework against an input that does not
                          # exist yet can only re-BLOCK (the directive used to send it anyway)
            # …AND THE OTHER ROUTE, WHEN IT IS THE CONTRACT THAT CANNOT HOLD. The directive said
            # "fix exactly what failed, then DELIVER again" and nothing else, so an executor
            # facing an unsatisfiable criterion obeyed it five times over (measured 2026-08-22).
            # After ACCEPT the channel for "this criterion is wrong" is BLOCK (§14.3 admits it
            # from REWORKING precisely so a defect met in the work is not unreportable — FM-7).
            _stuck = self.stuck_on(t.id)
            # …AND NAME WHAT FAILED, or stop claiming a failure. "Fix exactly what failed" is
            # unfollowable when nothing on the record says what did — and a wave read exactly that
            # on a node whose reports carried an empty `failed_criteria` (agent door, 2026-09-02).
            # Inv-3 makes a FAIL name its criteria, so a rework with none named is a state to
            # explain, not a verdict to relay.
            _failed = list((self.current_exec_verdict(t.id) or {}).get("failed_criteria") or ())
            cand = (2, t, Action.FIX,
                    (f"FIX AND RE-DELIVER '{t.id}' ({nm}): the validator FAILED it on "
                     f"{', '.join(map(str, _failed))}. Fix exactly that, then DELIVER again."
                     if _failed else
                     f"RE-DELIVER '{t.id}' ({nm}): it is in REWORKING, and no current verdict names "
                     f"a failed criterion — read `get_verdict {t.id}` before changing anything, "
                     f"because there may be nothing here to fix.")
                    + f"{self._rework_feedback(t.id)}"
                    + (f" | {', '.join(_stuck)} has now failed {self.CONTRACT_SUSPECT_ROUNDS} "
                       f"rounds running. If it cannot be met AS WRITTEN, do not deliver against "
                       f"it a fourth time — send BLOCK(reason=\"<why the criterion cannot hold>\"): "
                       f"the issuer answers it by changing the contract, which returns this node "
                       f"to OFFERED for your consent (Inv-1)." if _stuck else ""))
        elif t.state == State.EXECUTING and not kids:
            if not _deps_ready(t.id):
                return None  # a consumer waits until its producers PASS — do them first (dep order)
            cand = (3, t, Action.EXECUTE,
                    f"EXECUTE leaf '{t.id}' ({nm}): do the actual work so criteria {crits} hold. Then "
                    f"BEFORE you DELIVER, self-check by RUNNING: for each criterion write a tiny check, "
                    f"run it, read the ACTUAL output, and signal from what you OBSERVED — not from "
                    f"'I implemented it' (an optimistic self-pass the root later fails drops q_D). "
                    f"DELIVER with, per criterion, the check you ran and what it printed.")
        elif t.state == State.OFFERED and kids:
            # a re-authored parent dropped back to OFFERED — re-ACCEPT it BEFORE driving its subtree, so the
            # graph doesn't finish all children while the parent still shows 'accept' (obs: odd ordering).
            cand = (0, t, Action.ACCEPT,
                    f"RE-ACCEPT '{t.id}' ({nm}): it was re-authored → signal ACCEPT to put it back to work "
                    f"(its existing subtree is retained). Then its children proceed.")
        elif t.state == State.OFFERED:
            if not _deps_ready(t.id):
                return None  # a leaf whose producers have not passed is not takeable yet — the
                          # frontier used to hand it out anyway, and whoever took it discovered
                          # the missing input by BLOCKing on it. (The re-ACCEPT of a PARENT above
                          # is deliberately not gated: consent to resume is what lets its subtree
                          # run at all.)
            if self._validate and (_shut := self.execution_blocked_by(t.id)) is not None:
                # THE FRONTIER MUST NOT OFFER WHAT THE ENGINE REFUSES. This node's ACCEPT is
                # gated on its PARENT's plan being checked (§13.4), and the step above says so —
                # but the child was still listed as takeable, `mine: true`, with a directive to
                # signal ACCEPT. Whoever obeyed spent the call to be told no (measured on the MCP
                # door 2026-08-21). The parent's plan step is the real one; this reappears the
                # moment it is discharged.
                held.append(Wait(task_id=str(t.id), state=t.state.name, assignee=t.assignee,
                                 kind="plan",
                                 waits_on=(f"the plan of '{_shut['parent_id']}'",),
                                 why=_shut["why"], opens_with=_shut["opens_with"]).as_dict())
                return None
            cand = (4, t, Action.ACCEPT,
                    f"TAKE '{t.id}' ({nm}): signal ACCEPT (or CHALLENGE if its spec is wrong). Then "
                    f"decide by the criteria {crits}: DECOMPOSE it into subtasks if that fits the goal "
                    f"(their number is YOUR call — then review_decomposition checks the split for "
                    f"causal gaps), or execute it directly as a leaf.")
        elif t.state == State.BLOCKED:
            cand = (5, t, Action.RESOLVE, f"'{t.id}' ({nm}) is BLOCKED — clear the blocker, then RESOLVE_BLOCK.")
        elif t.state == State.EXECUTING and kids and all(_passed(k) for k in kids):
            cand = (6, t, Action.DELIVER,
                    f"AGGREGATE '{t.id}' ({nm}): all its children PASSED — integrate them. Before you "
                    f"DELIVER, self-check the WHOLE by running: each parent criterion {crits} must hold "
                    f"over the REAL integrated result (not mocks, not the children's word for it). "
                    f"Signal from what the run actually shows.")
        elif t.state == State.CANCELLING:
            # settlement of the cancellation handshake (§14.3) — never preempts real work (lowest priority)
            cand = (7, t, Action.CONFIRM_CANCEL,
                    f"CONFIRM cancellation of '{t.id}' ({nm}): signal CONFIRM_CANCEL, reporting the in-flight "
                    f"state at cancellation (what was done/undone) via `in_flight`.")
        else:
            return None  # EXECUTING with unfinished children, terminal, or IDLE → its frontier is elsewhere

        return cand

    def _not_complete_because_refuted(self, refuted: list[str]) -> dict:
        """The one answer given about nodes standing at PASS over their own FAIL.

        Written twice — once for the whole graph, once for a named root — is how the scoped door came
        to answer COMPLETE about a node the unscoped one called contradicted."""
        return {"complete": False,
                # named as DATA as well as prose: the CLI marks these nodes in its tree, and
                # parsing them back out of a sentence is a second spelling of one fact.
                "refuted_passes": refuted,
                "directive": (f"NOT COMPLETE — {', '.join(refuted)} stand(s) at PASS while the "
                              f"current recorded verdict for it is FAIL. A signature landed "
                              f"before the instrument's verdict did, and the graph is showing "
                              f"the signature. Read `get_verdict` on it; recovery is `reopen` "
                              f"if it is not consumed, and re-decomposition around it if it is.")}

    def _how_this_closed(self, root_id: "Optional[TaskId]" = None) -> dict:
        """The facts a reader must weigh about a graph that answers COMPLETE.

        ONE owner, because there are TWO completion answers — the whole-graph one and the per-root
        one — and only the first carried them. Asking about a root BY NAME is what `next_step(<id>)`
        does, what every signal reply calls, and what the documentation's own loop runs; it answered
        a bare `complete: true` while the unscoped call carried the contradiction (HTTP door, wave
        26, 2026-09-06). The comment on the refutation check ten lines above says the same lesson
        about the same pair of paths, written when THAT rule was found missing from this one: a rule
        that holds at one door and not at the next is the class this product keeps finding in itself.
        None of these withholds COMPLETE. Overruling an instrument is the issuer's act (§14.5) and no
        check can establish that a self-named reviewer is independent (§13.6) — so a correct override
        must stay finishable. What must not happen is that it finishes SILENTLY.
        """
        extra: dict = {}
        if _open_plan := self.closed_over_an_open_plan_review(root_id):
            extra |= {"closed_over_an_open_plan_review": _open_plan,
                      "closed_over_an_open_plan_review_note":
                          (f"{', '.join(_open_plan)} passed while its own Level-2 review still "
                           f"names findings nobody answered \u2014 `get_review` lists them. On a node "
                           f"with children the gate would have held them; on a leaf there is "
                           f"nothing to hold, so the review is advice and this is the only place "
                           f"it is said. The checker is an approximation (\u00a713.5) and contact is "
                           f"the real verdict \u2014 read both.")}
        if _byhand := self.closures_by_hand(root_id):
            extra |= {"closures_by_hand": _byhand,
                      "closures_by_hand_note":
                          (f"{', '.join(_byhand)} closed on a verdict ASSERTED BY HAND. That is a "
                           f"legitimate path \u2014 \u00a714.5 keeps the verdict the issuer's act, and the "
                           f"solo human door has no one else to ask \u2014 and it is the one thing "
                           f"here no check can establish (\u00a713.6): the engine cannot tell whether "
                           f"the reviewer was independent or whether the observations happened. "
                           f"`get_verdict` carries who asserted it and what they said they saw.")}
        if _hand := self.hand_overruled_closures(root_id):
            extra |= {"hand_overruled_closures": _hand,
                      "hand_overruled_note":
                          (f"{', '.join(_hand)} closed on a verdict ASSERTED BY HAND that "
                           f"replaced an instrument's opposite verdict on the same delivery. "
                           f"That is a legitimate act \u2014 the verdict is the issuer's (\u00a714.5) \u2014 "
                           f"and it is the one thing here nothing can check (\u00a713.6): read both "
                           f"with `get_verdict`, which carries the displaced one under "
                           f"`overruled`.")}
        return extra

    def _frontier_terminal(self, tasks, root_id):
        """The whole-graph answers that are not steps: no graph at all, or a finished root.

        Returns (terminal_dict, root). Both answers are about the WHOLE graph rather than about
        any candidate, and keeping them inside the collecting loop made that loop look as though
        it might return a terminal from anywhere in its body.
        """
        _passed = passed
        if not tasks:
            return ({"complete": False,
                    # The protocol handed to an agent says `auto_decompose` authors the root from
                    # the request itself, with no hand-made `create_task` — so this directive, the
                    # first thing a session is told on an empty project, contradicted it.
                    "directive": "No graph yet — `auto_decompose(request)` authors the root and its "
                                 "subtree from your goal; `create_task` + `decompose` is the manual "
                                 "path when you want to build the structure yourself."}, None)
        if root_id:
            root = self._graph.get_task(root_id)
            if root is not None and _passed(root):
                # …UNLESS THAT ROOT IS A GREEN THAT IS NOT GREEN. The refutation test below was
                # installed on the WHOLE-GRAPH answer only, so asking about a node BY NAME — which is
                # what `next_step(<id>)` does, and what every signal reply calls — walked past it:
                # `gfso status` printed `[X] PASS CONTRADICTED` and `next_steps <id>` answered
                # `complete: true` about the same node in the same second, with no `refuted_passes`
                # key at all (CLI door, wave 23, 2026-09-03; reproduced directly). One question, one
                # predicate, both ways of asking it — a rule that holds at one door and not at the
                # next is the class this product keeps finding in itself.
                if refuted := self.refuted_passes(root_id):
                    return (self._not_complete_because_refuted(refuted), None)
                return ({"complete": True,
                         "directive": f"COMPLETE — root '{root.id}' is DONE/PASS. "
                                      f"Execution finished.",
                         **self._how_this_closed(root_id)}, None)
            return None, root
        # A PROJECT MAY BE A FOREST, and "complete" is a claim about ALL of it. This took the FIRST
        # parentless node and, if that one had passed, announced that execution was finished — while
        # another root sat mid-flight with work owed on it (measured on the MCP door 2026-09-02,
        # where a second root had been created deliberately). Saying a graph is done while it is not
        # is the one kind of wrong answer this product exists to make impossible.
        roots = [t for t in tasks if t.parent_id is None] or [tasks[0]]
        # A GREEN THAT IS NOT GREEN IS NOT COMPLETE. A node can stand at PASS while its own current
        # record says FAIL — the signature landed first and the instrument's verdict was refused on a
        # node already terminal. Answering COMPLETE over that is the false green this product exists
        # to refuse, and it is the one answer a person cannot check for themselves.
        if refuted := self.refuted_passes():
            return (self._not_complete_because_refuted(refuted), None)
        if all(_passed(r) for r in roots):
            # …AND NOT WHILE ANYTHING IS STILL OPEN. A child can be attached to a node that has
            # already closed — which the canon's own recovery path needs, since re-decomposition
            # AROUND a consumed terminal is how a defect found later is repaired — and the roots
            # stay passed, so this answered COMPLETE over a graph with an unstarted node visibly in
            # it (HTTP door, 2026-09-02: "5 Done · 1 Not started · root DONE — the goal is met" on
            # one line). V(parent) is the AND over its children (Thm 1), so a passed parent with an
            # unsettled child is a claim that no longer holds; the honest answer is what is open.
            if open_now := [str(t.id) for t in tasks if t.state not in TERMINAL_STATES]:
                return ({"complete": False,
                         "open_nodes": open_now,
                         "directive": (f"NOT COMPLETE — the root(s) passed, but {', '.join(open_now)} "
                                       f"{'is' if len(open_now) == 1 else 'are'} still open. A "
                                       f"parent's result is the AND over its children (Thm 1), so a "
                                       f"node attached after its parent closed leaves that parent's "
                                       f"verdict standing on work nobody has done.")}, None)
            # …and a ⊥ that landed anyway is SAID, never used to withhold the answer. A judge that
            # could not decide is not a judge that decided against: withholding COMPLETE over one
            # would be reading ⊥ as fail, which §11.2 forbids in those words.
            unresolved = self.nodes_with_a_refused_report()
            extra = ({"unresolved_reports": unresolved,
                      # …AND THE MACHINE-READABLE HALF OF THE SAME SENTENCE. The note below says
                      # this does not make the graph unfinished; a dashboard keying on the LIST
                      # still painted a finished root red (HTTP door, wave 27, 2026-09-06). The
                      # answer to "does this block completion" is a boolean, not a paragraph.
                      "unresolved_reports_block_completion": False,
                      "unresolved_reports_note":
                          (f"a judge ran on {', '.join(unresolved)} and the engine REFUSED its "
                           f"report as ⊥ — evidence, not a verdict, and NOT a reason this is "
                           f"unfinished (§11.2: ⊥ is not fail). `get_verdict` shows what it managed "
                           f"to observe, if you want to decide it yourself.")}
                     if unresolved else {})
            # …and a delivery two parties judged in OPPOSITE directions, where the one left standing
            # was asserted by hand. Beside the answer, never instead of it: overruling an instrument
            # is the issuer's right (§14.5) and no check can establish that a self-named reviewer is
            # independent (§13.6), so withholding COMPLETE would make a correct override unfinishable.
            # What the reader must not be able to miss is that the closure was contested at all —
            # measured on the CLI door (wave 24, 2026-09-04): a hand PASS displaced an instrument's
            # FAIL on a node where nothing had been built, and four of the five surfaces a person
            # reads showed an earned green.
            # …AND HOW THE PASSED ROOTS WERE JUDGED AT ALL. Three doors asked for this line in two
            # waves: a hand-asserted verdict and an instrument's produce the same `[x]` and the same
            # `complete: true`, and the difference is the whole of what this product measures.
            # SCOPED TO THE ROOT THE CALLER ASKED ABOUT. These three facts were computed over the
            # WHOLE graph while the answer around them is about one root — so `next_steps(root_id=X)`,
            # the loop the documentation tells you to run, carried none of them for X. Measured on
            # the HTTP door (wave 26, 2026-09-06): a hand PASS displaced an instrument's FAIL, and
            # the per-root call answered a bare `complete: true` while the unscoped one carried the
            # contradiction. The documented call was the one that hid it.
            extra = {**extra, **self._how_this_closed(root_id)}
            if len(roots) == 1:
                return ({"complete": True,
                         "directive": f"COMPLETE — root '{roots[0].id}' is DONE/PASS. "
                                      f"Execution finished.", **extra}, None)
            named = ", ".join(f"'{r.id}'" for r in roots)
            return ({"complete": True,
                     "directive": f"COMPLETE — every root ({named}) is DONE/PASS. "
                                  f"Execution finished.", **extra}, None)
        # …and the root handed on is one with work LEFT, never a finished one, or the step search
        # below starts from a node whose subtree is already closed.
        return None, next((r for r in roots if not _passed(r)), roots[0])

    def _frontier(self, root_id: Optional[TaskId] = None):
        """Collect ALL currently actionable candidates, priority-ordered (children before parents,
        dep order respected). Returns either a terminal dict ({complete}/{stuck}/empty-graph) or a list of
        (priority, task, action, directive) tuples. Shared by next_step (v1 single directive) and
        next_steps (v2 parallel frontier)."""
        _passed = passed          # one owner for "did this node earn a pass" (gfso.core.types)
        # …and the nodes the PLAN GATE holds back: not steps, but not silence either. Kept beside the
        # frontier so `next_steps` can say what they wait on and the dispatcher can say it once per
        # node, without either of them offering an ACCEPT the engine would refuse. Reset per call.
        self._held_by_plan = held = []

        tasks = self.all_tasks()
        terminal, root = self._frontier_terminal(tasks, root_id)
        if terminal is not None:
            return terminal

        deps = self._graph.dep_edges()
        def _deps_ready(tid: TaskId) -> bool:
            """A consumer is executable only once every producer it depends on has PASSED (dep order)."""
            # A producer that does not EXIST yet counts as not ready (mid-build a consumer's ASSIGN
            # can land before its producer's) — `_passed(None)` would have raised here instead.
            return all(self._graph.get_task(e.from_id) is not None
                       and _passed(self._graph.get_task(e.from_id))
                       for e in deps if e.to_id == tid)

        cands = []  # (priority, task, action, directive); lower priority acts first
        for t in tasks:
            kids = self.get_active_children(t.id)
            # EVERY criterion, seams included. The directive listed only the node's OWN criteria and
            # dropped the `dep__` ones — and V is the conjunction over ALL of them (§10), which is
            # what `record_verdict` enforces: a person who judged exactly the printed list was
            # refused for "criterion 'dep__x' has no verdict" (measured on the human door
            # 2026-08-22, two round-trips). Following the instruction has to be enough.
            crits = [c.name for c in t.spec.criteria]
            nm = t.spec.name or str(t.id)
            if self._plan_gate_step(t, kids, crits, nm, cands, held, _passed):
                continue
            if self._waits_on_work_in_progress(t, kids, held, _passed):
                continue
            _c = self._step_for(t, kids, crits, nm, cands, held, _deps_ready, _passed)
            if _c is not None:
                cands.append(_c)

        if not cands:
            return self._nothing_to_take(tasks, deps, _deps_ready, _passed)
        cands.sort(key=lambda c: (c[0], str(c[1].id)))
        return cands

    def _plan_gate_step(self, t, kids, crits, nm, cands, held, _passed) -> bool:
        """Whether this node's PLAN, not its own state, decides what happens here (§13.4).

        A parent whose decomposition has an open Syntactic hole or an undischarged Level-2
        finding gates its children's ACCEPT, so the repair is the step ITSELF; a check already
        in flight is not a step at all. Appends to `cands`/`held` exactly as the frontier would
        and answers whether the node is accounted for — the frontier asks nothing else of it.
        """
        # A plan whose causal check is not discharged is the actionable step ITSELF, ahead of the
        # work it gates (§13.4): the engine will refuse those children's ACCEPT, so an agent driving
        # the frontier must be TOLD to review — a gate that only refuses is a wall to walk into.
        # Ordered after validate/rework (finishing delivered work is never blocked by a plan check)
        # and before execute/accept (which it gates). Only while it still gates something: some
        # active child sitting in OFFERED, waiting to start.
        # THE PLAN STEP IS ABOUT THE PLAN, NOT ABOUT WHERE THE PARENT STANDS. This asked for
        # EXECUTING, and a parent that has DELIVERED sits in VALIDATING — so a repair made from
        # REWORKING (revise the plan, re-open the children, re-deliver) landed in exactly the
        # state where no step existed at all: the children were held by the gate, the parent's
        # own validation is skipped while they are unsettled, and the frontier went empty.
        # Measured on the E3 arm 2026-08-21: 51 minutes of a live run with nothing to do and
        # nothing said. Any non-terminal parent whose children wait on its plan gets the step.
        _gating = (kids and self._validate and not _passed(t)
                   and any(k.state == State.OFFERED for k in kids))
        if _gating and (_holes := _l0_holes(self._graph, t)):
            # …and the SYNTACTIC level first, which had no step at all: with an L0 hole open the
            # engine refuses the children's ACCEPT exactly as it does for L2, but the frontier
            # named neither the parent nor the repair — it just kept offering the children.
            cands.append((2.5, t, Action.CHECK_PLAN,
                          f"FIX THE PLAN of '{t.id}' ({nm}): its children cannot start while its "
                          f"decomposition fails the Syntactic level (§13.4) — "
                          + "; ".join(f"{h.check_name}: {h.details}" for h in _holes)
                          + f". `list_holes` shows them across the graph."))
            return True
        if _gating and l2_gate_on() and self.review_in_flight(t.id):
            # A CHECK ALREADY RUNNING IS NOT A STEP. The frontier kept saying "call
            # review_decomposition" while one was mid-flight — a duplicate paid round over a
            # plan that had not changed, and the other in-flight surface (`validate_result`)
            # already knew better.
            held.append(Wait(task_id=str(t.id), state=t.state.name, assignee=t.assignee,
                             kind="plan", waits_on=("the Level-2 check already running on this "
                                                    "version of the plan",),
                             why=("its causal check is in flight — a second one would judge the "
                                  "same plan twice and cost twice"),
                             opens_with="nothing: its verdict arrives by itself").as_dict())
            return True
        if _gating and l2_gate_on() and not _l0_holes(self._graph, t):
            open_l2 = _l2_undischarged(self._graph, t)
            if open_l2 is None:
                cands.append((2.5, t, Action.CHECK_PLAN,
                              f"CHECK THE PLAN of '{t.id}' ({nm}): its children cannot start until the "
                              f"decomposition has a current Level-2 verdict — call "
                              f"review_decomposition('{t.id}') (do the mapped children's criteria "
                              f"causally carry {crits}?)."))
                return True
            if open_l2:
                _own = [g for g in open_l2 if str(g).startswith("undecided: ")]
                cands.append((2.5, t, Action.CHECK_PLAN,
                              # …AS A COUNT AND A LIST, not as a paragraph of interpolated
                              # findings. Eleven were pasted into one wall of text and a reader
                              # counted eleven problems where there were five — the checker's own
                              # fold had already marked some as one obligation in several
                              # wordings (agent door, 2026-09-02).
                              f"CLOSE THE PLAN GAPS of '{t.id}' ({nm}): the Level-2 review named "
                              f"{len(open_l2)} finding(s) not carried by the mapped children — "
                              + "; ".join(f"({i + 1}) {g}" for i, g in enumerate(open_l2))
                              + f". One reason can answer several: `dispute_finding('{t.id}', "
                                f"[<keys>], '<why>')`. Fix the plan "
                              f"(edit_criteria / map_criterion / add a child) and re-run "
                              f"review_decomposition('{t.id}'), or record why the finding is wrong "
                              f"(dispute_finding). Reasons: get_review('{t.id}')."
                              + (f" NOTE — the `undecided` findings ({len(_own)}) are about "
                                 f"'{t.id}'s OWN criteria, not its children's: a criterion added "
                                 f"to a CHILD does not close one, and the finding comes back word "
                                 f"for word. `edit_criteria('{t.id}', …)` is what closes them."
                                 if _own else "")))
                return True
        return False

    def _waits_on_work_in_progress(self, t, kids, held, _passed) -> bool:
        """Whether this node can take no step because something else must finish first.

        Two cases, both of which a verdict here would be refused for: children of its own have
        not passed (a parent's result is the AND over them, Thm 1), or an independent validator
        is already judging THIS delivery. Both are recorded in `held` with what they wait on,
        because a node in neither list is a node the frontier never mentions."""
        if t.state == State.VALIDATING and kids and not all(_passed(k) for k in kids):
            # …AND SAY WHERE IT WENT. Skipping the parent is right — a verdict on it would be
            # refused (Thm 1) — but it left the node in NO list at all: a person who delivered a
            # parent early watched it sit in VALIDATING for an hour, absent from `steps` and from
            # `waiting`, with the frontier that exists to say what to do never mentioning it
            # (measured on the human door 2026-08-21).
            held.append(Wait(task_id=str(t.id), state=t.state.name, assignee=t.assignee,
                             kind="children",
                             waits_on=tuple(str(k.id) for k in kids if not _passed(k)),
                             why=("it was delivered while children of its own have not passed, "
                                  "and a parent's verdict is the AND over them (Thm 1) — so no "
                                  "verdict can be given here yet"),
                             opens_with="finish those children; validation follows by itself").as_dict())
            # A VERDICT NOW WOULD BE REFUSED, so this is not the step. The parent's result is
            # the AND over its children (Thm 1) and the PASS gate knows it; offering `validate`
            # here put the highest-priority step on the one node that cannot move, and whoever
            # took it waited on a verdict nobody could give. Measured 2026-08-20 on a live run:
            # a root sat nineteen minutes in VALIDATING after its own plan repair added a child,
            # while that child's `accept` step sat below it on the same frontier. Skipping the
            # parent surfaces the children — and if they cannot move either, the stuck branch
            # below names them.
            return True
        if t.state == State.VALIDATING and self.validation_in_flight(t.id):
            held.append(Wait(task_id=str(t.id), state=t.state.name, assignee=t.assignee,
                             kind="validator",
                             waits_on=("the validator already running on this delivery",),
                             why=("an independent validation of THIS generation is in flight — a "
                                  "second one would judge the same delivery twice and cost twice"),
                             opens_with="nothing: its verdict arrives by itself").as_dict())
            # A VALIDATOR IS ALREADY RUNNING on this delivery. The step said "VALIDATE this" to
            # whoever asked, so a caller who obeyed either spent a second instrument on the same
            # generation or waited four minutes not knowing whether silence meant work or
            # nobody (measured 2026-08-21). It is not an actionable step while the instrument
            # holds it; the frontier says so and moves on.
            return True
        return False

    def refused_report_for_this_delivery(self, task_id: TaskId) -> Optional[dict]:
        """The refused report standing on the CURRENT delivery of this node, or None.

        One owner for a record three readers need: the frontier's directive, `get_verdict`, and —
        the one that pays for it — the packet handed to the judge on its next attempt. Scoped to the
        generation, because a refusal from before a rework is about a delivery nobody made.
        """
        rec = self.rejected_report(task_id) or {}
        task = self.get_task(task_id)
        if not rec or task is None:
            return None
        gen = generation_of_task(task)
        return rec if all(rec.get(k, 0) == g
                          for k, g in zip(("iteration", "reopens", "revisions"), gen)) else None

    def _bottom_attempts(self, task) -> int:
        """How many instrument reports on THIS delivery were refused as ⊥, or 0.

        One reader for a fact three surfaces need: the frontier's directive, `get_verdict`, and
        whoever comes back to a node that has been sitting in VALIDATING. Scoped to the current
        generation, because a count carried across a rework is advice about a delivery nobody made.
        """
        return int((self.refused_report_for_this_delivery(task.id) or {}).get("refusals", 0))

    def _redelivery_refusal(self, task) -> Optional[str]:
        """What the re-delivery gate would say about this node right now, or None if it would pass.

        Asked by the frontier so the directive names the repair the engine will actually accept."""
        rec = self._graph.exec_verdict_record(task.id)
        if not rec or rec.get("verdict") != Verdict.FAIL:
            return None
        try:
            return _refuted_coverage_refusal(self._graph, task, rec)
        except Exception:                 # a directive is never worth an exception on the frontier
            return None

    #: How many FAILs on the SAME criterion make the contract, rather than the work, the suspect.
    #: Three is where the canon already bounds the ordinary loop (§14.3: max_iterations default 3).
    CONTRACT_SUSPECT_ROUNDS = 3

    def stuck_on(self, task_id: TaskId, rounds: int = CONTRACT_SUSPECT_ROUNDS) -> list[str]:
        """The criteria that failed in EVERY one of this node's last `rounds` FAILs, or [].

        A node can fail the same criterion round after round for two very different reasons — the
        work is not there yet, or the criterion cannot be met as written — and nothing distinguished
        them for either side. Measured on a live run 2026-08-22: an executor re-delivered five times
        against `unicode_and_surrogate_policy`, which asks for a round-trip of lone surrogates and is
        unsatisfiable with strict UTF-8; the artifact scored 0.972 on the held-out suite and the run
        stalled. The count is a fact in the log; this reads it out so both doors can say it."""
        fails = [e for e in self._audit.get_entries(task_id)
                 if e.signal == Signal.FAIL and not e.rejected]
        if len(fails) < max(2, rounds):
            return []
        sets = [set(e.failed_criteria or ()) for e in fails[-rounds:]]
        return sorted(set.intersection(*sets)) if all(sets) else []

    def _rework_feedback(self, task_id: TaskId) -> str:
        """The validator's failure detail for the current REWORKING — the failed criteria and, when the
        recorded verdict carries per-criterion evidence (e.g. a unittest-checker's assertion output),
        that evidence. This is the executor's ONLY window into WHY it failed (it does not see the tests):
        a FAIL with only criterion names cannot steer a fix on a values/exact-output criterion."""
        rec = self._graph.exec_verdict_record(task_id)
        if not rec or rec.get("verdict") != Verdict.FAIL:
            return ""
        per = {p.get("criterion"): p.get("evidence", "") for p in (rec.get("per_criterion") or [])}
        lines = []
        for c in rec.get("failed_criteria") or []:
            ev = (per.get(c) or "").strip().replace("\n", " ")
            # …CUT AT A WORD, AND SAID SO. This sliced at 300 characters mid-token — a directive
            # ending `On column name = ['Al` — so a reader could not tell a truncation from a
            # garbled record, and the rest was reachable only through a verb nobody named it
            # (measured on the agent door 2026-08-22).
            if ev and ev != "passed":
                _short = (ev if len(ev) <= 300 else ev[:300].rsplit(" ", 1)[0]
                          + f"… (the rest: `get_verdict('{task_id}')`)")
                lines.append(f"\n  - {c}: {_short}")
            else:
                lines.append(f"\n  - {c}")
        return " Failed:" + "".join(lines) if lines else ""

    def _step_out(self, t: Task, action: str, directive: str) -> dict:
        # Surface unmet checks, split by what the engine actually does with them. The whole Syntactic
        # level BLOCKS execution — CHECK-1, 1b, 2, 3, 4, 5, 6 (§13.4: "a decomposition that fails the
        # Syntactic level is not admitted to execution"), which is exactly `_EXEC_GATING_CHECKS` — so
        # those read "resolve first". What stays advisory is what the canon does not put on that level:
        # the anti-mock CHECK-1c, an engineering addition with no canon row (see the gate's own note).
        allc = [c for c in self.get_checks(t.id) if not c.passed and not c.skipped]
        unmet = [f"{c.check_name}: {c.details}" for c in allc if c.check_name.startswith(_EXEC_GATING_CHECKS)]
        advisory = [f"{c.check_name}: {c.details}" for c in allc if not c.check_name.startswith(_EXEC_GATING_CHECKS)]
        if str(t.id) in getattr(self, "_validation_parked", ()):
            directive += (" | AUTOMATIC VALIDATION GAVE UP here: two validator reports carried no "
                          "verdict, so no automatic verdict is coming and the node will sit in "
                          "VALIDATING until you act (§11.2: ⊥ is not pass). Run `validate_result` "
                          "yourself — a stronger model often settles it — or record a verdict and "
                          "sign as the issuer."
                          + (" What the judge DID observe before it gave up is on the record: "
                             "`get_verdict` shows it under `refused_report` — evidence, not a "
                             "verdict." if self.rejected_report(t.id) else ""))
        if (_why := self.contested_reason(t.id)):
            directive += (f" | ITS EXECUTOR DISPUTES THE CONTRACT and could not say so in a signal "
                          f"(§14.3 admits CHALLENGE from OFFERED only, and the node is past it): "
                          f"\"{_why}\". This is YOURS — nothing will move until you settle it. "
                          f"`revise` the node if the dispute is right (that returns it to OFFERED, "
                          f"where its executor takes it again under the new contract), or "
                          f"`reassign` it if the contract stands and this executor cannot do it. "
                          f"Re-running the same executor under the same contract reproduces the "
                          f"dispute and pays for it.")
        if unmet:
            directive += f" | UNMET plan checks (resolve before executing): {unmet}"
        if advisory:
            directive += f" | advisory (optional): {advisory}"
        # …AND WHO THE SIGNAL WOULD BE SIGNED BY. A directive names the exact next command — "signal
        # ACCEPT to put it back to work" — and on a door where `source` is required that command is
        # incomplete: the caller sent it, got "signal needs source", and had to go read the help
        # (CLI door, 2026-09-02). The engine knows whose move it is; the step says so, and a door
        # that takes the signer as an argument can copy it.
        return {"complete": False, "task_id": str(t.id), "name": t.spec.name or str(t.id),
                "state": t.state.name, "action": action, "assignee": t.assignee, "unmet_checks": unmet,
                "signed_by": str(self.issuer_of(t.id)) if action in _ISSUER_ACTIONS else str(t.assignee or ""),
                # ALL of them, seams included: a `dep__` criterion is a criterion of this node, V
                # is the conjunction over the whole contract (§10), and `record_verdict` enforces
                # that — so a step that lists fewer is a step whose instruction cannot be followed.
                "criteria": [c.name for c in t.spec.criteria], "directive": directive}

    def next_step(self, root_id: Optional[TaskId] = None) -> dict:
        """The execution forcing-point (v1, single-agent form). From the graph's CURRENT state, return the
        ONE next required action — or `complete=True`. Children before parents (a parent only DELIVERs once
        its children PASS); completion is GATED on the root being DONE/PASS, so the agent cannot stop early.

        Returns a dict: {complete, [task_id, name, state, action, criteria], directive}. `action` ∈
        {accept, execute, deliver, validate, resolve, rework, confirm_cancel}. For parallel delegation use
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
        producers have PASSED (§10 dep order), and distinct ready leaves share no unresolved edge — so the
        orchestrator may delegate them to executors CONCURRENTLY. Non-execute steps (accept / validate /
        rework / resolve / deliver / confirm_cancel) are issuer-side and cheap — do them in the returned order
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
        # …AND WHAT IS WAITING, which the list alone never showed. A node held by the dependency
        # order is simply ABSENT from the steps — correct, it is not actionable — so a reader saw
        # one step and no reason for the rest of the graph's silence. Measured 2026-08-20 through
        # the MCP door: two of three children were dep-blocked and appeared nowhere, while
        # `get_dependencies` had every edge and glue note. The pairs go in the answer, not in a
        # second verb the reader has to know about.
        out = {"complete": False, "steps": steps, **self._waiting_on(steps)}
        if self._held_by_plan:
            out["waiting"] = list(out.get("waiting", ())) + self._held_by_plan
        if stranded := [t for t in self.stranded_nodes() if t.state != State.ABANDONED]:
            # …AND WHAT THE GRAPH CANNOT MOVE PAST, whether or not something else is actionable.
            out["stranded"] = [
                {"task_id": str(t.id), "state": t.state.name,
                 "why": (f"its rework loop was exhausted (§14.3) — a settled FAIL, and a parent's "
                         f"PASS is the AND over its children, so nothing above it can complete"),
                 "opens_with": (f"re-decompose around it: add a child that carries what "
                                f"'{t.id}' left uncovered and map it (`map_criterion`). A terminal "
                                f"node is not reopened and takes no revision.")}
                for t in stranded]
        return out

    def in_flight_nodes(self) -> list[dict]:
        """The nodes that are BUSY right now — being judged, or being worked on by a machine.

        The frontier lists what a caller can take; a node in VALIDATING or one held by a registered
        executor is neither takeable nor stuck, and having no name for that state is what made an
        empty frontier read as a dead graph."""
        out = []
        for t in self.all_tasks():
            if self.review_in_flight(t.id):
                out.append({"task_id": str(t.id), "state": t.state.name,
                            "why": "has its plan being checked — a Level-2 review of this version "
                                   "is running",
                            "opens_with": "nothing: its verdict arrives by itself"})
                continue
            if t.state == State.VALIDATING:
                out.append({"task_id": str(t.id), "state": t.state.name,
                            "why": ("is being judged — an independent validation of this delivery "
                                    "is running" if self.validation_in_flight(t.id) else
                                    "is delivered and waits for its issuer's verdict"),
                            "opens_with": ("nothing: its verdict arrives by itself"
                                           if self.validation_in_flight(t.id) else
                                           f"the issuer judges it (`validate_result('{t.id}')` runs "
                                           f"the instrument)")})
            elif (t.state in (State.EXECUTING, State.REWORKING)
                  and self._roster.get(str(t.assignee)) == "llm-executor"):
                out.append({"task_id": str(t.id), "state": t.state.name,
                            "why": f"is being worked on by '{t.assignee}', a registered executor",
                            "opens_with": "nothing: the dispatcher started it and its report follows"})
        return out

    def stranded_nodes(self) -> list:
        """Nodes the graph cannot move past: settled NEGATIVE (§14.3 — the exhausted rework loop
        escalates, and ESCALATED means "this needs attention"), or cancelled.

        Read by the stuck branch AND by every ordinary frontier answer, because they were only ever
        named when NOTHING else was actionable: a root with one escalated child and one takeable
        sibling reported the sibling and said nothing about the child that had already made the root
        impossible (walked by hand 2026-08-21). A parent's PASS is the AND over its children."""
        return sorted((t for t in self.all_tasks()
                       if t.state in (State.ESCALATED, State.ABANDONED)
                       or (t.state == State.DONE and t.done_reason == DoneReason.FAIL)),
                      key=lambda t: str(t.id))

    def _waiting_on(self, steps: list) -> dict:
        """`waiting`: the nodes not on the frontier because a producer of theirs has not passed."""
        shown = {s["task_id"] for s in steps}
        deps = self._graph.dep_edges()
        out = []
        for t in self._graph._storage.get_all_tasks():
            if str(t.id) in shown or t.state.name in ("DONE", "ABANDONED", "ESCALATED"):
                continue
            open_prod = sorted({str(e.from_id) for e in deps if str(e.to_id) == str(t.id)
                                and not passed(self._graph.get_task(e.from_id))})
            if open_prod:
                # The SAME shape as a plan-gated wait, because the two sat side by side in one answer
                # with only one of them explaining itself (measured on the human door 2026-08-21).
                out.append(Wait(task_id=str(t.id), state=t.state.name, assignee=t.assignee,
                                kind="dependency", waits_on=tuple(open_prod),
                                why=("it consumes what those nodes produce (§10: a Dep is criteria "
                                     "content — this node's criteria name their result), and they "
                                     "have not passed"),
                                opens_with=f"finish {', '.join(open_prod)}").as_dict())
        return {"waiting": out} if out else {}

    def graph_holes(self, root_id: Optional[TaskId] = None) -> list[dict]:
        """Every UNMET structural check across the whole graph (or the subtree under root_id) — the full gap
        list to resolve ∨ consciously declare BEFORE driving execution. Aggregates each node's cached L0/L1
        checks (coverage, DAG, glue, non-redundancy, ACCEPTED_RISKS, …). A freshly `decompose`d graph can carry
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
        """The Graph object itself — for a host that must read structure this facade does not expose.

        A read handle, deliberately: mutations go through the protocol (a signal), because the log is
        the single sequencer and a second writer would end the guarantee it carries."""
        return self._graph

    def wait_idle(self, timeout: float = 5.0) -> None:
        """Wait for queue to drain. Useful for testing."""
        self._queue.join()
