"""GFSO Engine — Level 2 framework. Public API for building systems."""
from __future__ import annotations

import dataclasses
import json
import logging
import threading
from datetime import datetime, timedelta
from typing import Optional

from gfso.core.types import (
    Signal, State, SignalData, SignalOutcome, Refusal,
    TaskId, AgentId, Verdict, passed, settled_positive,
    Spec, Criteria, Probe, AcceptedRiskItem, Register, register_of, Task, CheckResult, CriterionMapping, DepEdge,
    LLMProviderPort, AgentPort, StoragePort,
    ClockPort, SystemClock, RunnerPort, ThreadRunner,
    TERMINAL_STATES, DoneReason, DEFAULT_MAX_ITERATIONS, Mode,
)
from gfso.core.graph import Graph
from gfso.core.graph.model import (GENERATION, cycle_children, dep_order_refutations, dep_scope, generation_of_task,
                                   non_leaf_ids, replaces_key, root_of, root_issuer_key, register_log_key,
                                   stamp, stamped_with)
from gfso.core.graph.mutations import InvariantViolation, with_its_seams
from gfso.core.handlers.structural import run_structural
from gfso.core.graph import q_T, q_D, q_V, q_Dep, q_Del, false_fail_share, pass_was_refuted
from gfso.core.graph.review import finding_keys, progress_baseline
from gfso.core.graph.projection import build as build_projection, render as render_projection
from gfso.core.protocol.fsm import available_signals, not_admissible_here, transition
from gfso.core.protocol.validation import required_role, Role
from gfso.core.protocol.invariants import (decided_verdict, spoken_verdict, probes_of, probes_that_expected_nothing,
                                          verdict_report_defects, probe_labels, unrun_probes)
from gfso.core.protocol.procedure import (admission_defects, criterionless, parts_not_shown_holding, reads_an_unpinned_set,
                                          refuting_probes, merge_regression, probe_id, layable_over, unrerunnable,
                                          unaccounted_for, orphaned_regression,
                                          claim_digest)

from gfso.config import (
                         PIPELINE_PAGE, USAGE_PAGE,
                         agent_id as _config_agent_id,
                         state_timeout as _config_state_timeout)
from .audit import (AuditLog, AuditEntry, VERSION_INSTALLING, failed_on_current_version,
                    resolved_on_current_version)
from .verdicts import (store_verdict, criterion_version, refuted_versions, ledger_read, ledger_write, CLOSING,
                       OVERRULED, REJECTED_REPORT, REGRESSION, FAILED_THROUGH_PARTS)
from .findings import disputed_findings, ever_pinned, released, regression as standing_regression, standing_rulings
from .frontier import Frontier
from .claims import Claims
from .joins import Joins
from .parking import Parking
from .workforce import Workforce
from .admission import (admit as _admit, admit_register as _admit_register, refuse_a_contract_that_pins_nothing,
                        refuse_a_d_cycle)
from .validation import (AdmissionRefused, _l0_holes, _l2_undischarged, l2_gate_on, no_live_deadline, dep_cycle_closed,
                         issuing_condition, rule_refusal, signer_refusal, whole_waits_for_its_parts,
                         mode_kind, party_kind, is_auto_root,
                         displaces_a_refutation, observation_blocker,
                         fits_one_session as _fits_one_session, checked_by_contact as _checked_by_contact, observed_here as _observed_here,
                         session_fit as _session_fit, scope_top as _scope_top,
                         scope_members as _scope_members, split_owed as _split_owed,
                         parts_procedure as _parts_procedure, settled_procedure as _settled_procedure,
                         observation_binds as _observation_binds,
                         observation_standing, record_stands as _record_stands,
                         redelivery_refusal, execution_admitted as _execution_admitted,
                         hole_kind, project_mode as _project_mode, depth_of as _depth_of,
                         holder_boundary as _holder_boundary, held_plan_node_refusal, hands_of as _hands_of)
from .events import EventBus, TransitionCallback, ErrorCallback, RejectCallback
from .loop import _guard_context, event_loop, refresh_checks, timeout_monitor

log = logging.getLogger(__name__)


# live token ticks ("<stage>: N tokens · Ss") update in place — WS-only, never persisted
import re
_TICK_RE = re.compile(r"tokens · \d+s$")


def loose_finding_key(text: str) -> str:
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
        self._storage = storage           # the port this engine was given — its own, not reached for under the graph
        self._agents = agents
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
        self._graph.audit = self._audit   # R′'s finality reads consumption off the log (`Graph.is_consumed`)
        self._events = EventBus()
        self._started = False
        self.frontier = Frontier(self)    # what the graph owes next, and to whom (`next_step(s)`)
        # WHICH PROJECT THIS ENGINE IS. Set by the registry that builds it; the roster is one
        # server-wide file, so this is what tells another run's validator role from yours.
        self.project_name: Optional[str] = None
        #: keys of notices that must be said once, not once per poll (`say_once`)
        self._said_once: set = set()
        self.claims = Claims(self._graph, self._clock, self._audit)   # who runs a model over a node now
        self.joins = Joins(self._graph)          # where each passed result stands (`mark_joining`)
        self.workforce = Workforce(self._graph, lambda: self.project_name)   # who works here (published)
        self.parking = Parking(self._graph, self.accepted_moves)   # what waits on an undecided park

    # === Lifecycle ===

    def start(self) -> None:
        """Start event loop and timeout monitor."""
        if self._started:
            return
        self._started = True
        # THE CACHED CHECKS ARE THIS BUILD'S: a project written by an older one carried its verdicts, and `list_holes`
        # answered [] from them while the plan gate, reading the live rule, named the hole (critic r15)
        for t in self.all_tasks():
            if self._graph.get_active_children(t.id):
                refresh_checks(self._graph, t.id)

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
        exempts it by name (§12.12) — a starved IDLE child surfaces as its PARENT's timeout, whose
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
        for t in self._storage.get_all_tasks():
            if t.state == State.IDLE and t.spec is not None and t.assignee:
                log.warning("recovering crash orphan %s: ASSIGN persisted the node but its landing "
                            "did not — completing the interrupted transition", t.id)
                self._queue.put(SignalData(signal=Signal.ASSIGN, task_id=t.id,
                                           source=self._graph.issuer_of(t.id)))

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
        issuer: Optional[AgentId] = None,
        covers: tuple = (),
    ) -> Task:
        """Create a task and send ASSIGN signal. Convenience method.

        `issuer` matters only for a ROOT: the goal's issuer, when it is not the root's own Del (a user
        handing the whole goal to a system executor stays its customer — `Graph.issuer_of`). Below a
        root the issuer is the parent's Del by definition, and a different one is refused.

        deadline completes the T=(spec, criteria, deadline) primitive (§2);
        without it CHECK-3 (deadline consistency) is vacuous.

        `max_iterations` bounds the DELIVER→FAIL loop (§12.15) and is a field of the CONTRACT, not a
        property of the installation: the canon fixes the number by fiat (§12.15: "pinned by no
        FM"), so it is chosen per task by whoever issues it. The default exists so an unattended
        loop cannot retry all night unnoticed — it is a convenience, not a bound on the project.
        """
        if max_iterations is None:
            max_iterations = DEFAULT_MAX_ITERATIONS
        # ONE ROOT PER PROJECT. A parentless node is not a free-standing task, it is THE goal: V(root)
        # is the project's verdict, and the canon's one composition rule (V(parent)=AND(children))
        # needs a parent, so a second parentless node is a second verdict with nothing to combine
        # them. Nothing forbade it, and what filled the gap was an agent whose escalated root admitted
        # no act: it built `root2`, then `root3`, and closed the goal green on a childless leaf while
        # the work hung under the dead one. The refusal names the two acts that were actually meant.
        existing_root = root_of(self.all_tasks()) if parent_id is None else None
        if existing_root is not None and str(existing_root.id) != str(task_id):
            raise InvariantViolation(
                f"this project already has its root, '{existing_root.id}' "
                f"({existing_root.label(60)}), and a project "
                f"has exactly one: the root carries the goal's criteria, so a second one is a second "
                f"verdict with no rule composing them. If '{task_id}' is part of that goal, it enters the "
                f"root's split: `decompose` admits a split whole (the children with their `covers`, the "
                f"register), and `create_task(parent_id=…, covers=[…])` adds one child to a split that "
                f"already stands. If it "
                f"is a different goal, it belongs in a different project (`use_project`)."
            )
        refuse_a_d_cycle(self._graph, task_id, parent_id)
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
        # D is a DAG over NODES (§15.3), which is the same rule the self-parent and cycle guards
        # beside this one enforce; an edge to a non-node is not an edge in it.
        if parent_id and parent is None:
            raise ValueError(
                f"parent {parent_id!r} does not exist, so {task_id} cannot hang under it — D is a "
                f"DAG over NODES (§15.3), and an edge to something that is not one is not an edge in "
                f"it. Create the parent first (`create_task {parent_id} …`), or — only while this "
                f"project has no root yet — leave `parent_id` out and this node becomes it: a "
                f"project has exactly one.")
        if why := issuing_condition(parent, task_id):
            raise ValueError(why)
        refuse_a_contract_that_pins_nothing(self._graph, task_id, spec)
        if issuer and parent is not None and str(issuer) != str(parent.assignee):
            raise ValueError(
                f"the issuer of '{task_id}' is its parent's executor ({parent.assignee}), not "
                f"{issuer}: below a root the issuer is Del(parent) by definition (§10.1).")
        if parent is not None and self._graph.get_task(task_id) is None:
            # a child created into a split is an admission of it (§11.5): the same act `decompose_task` performs
            self._admit(parent_id, [(task_id, spec, assignee, deadline)], {str(task_id): tuple(covers)},
                        max_iterations=max_iterations)
            return self._graph.get_task(task_id)
        if issuer and parent is not None and str(issuer) != str(parent.assignee):
            raise ValueError(
                f"the issuer of '{task_id}' is its parent's executor ({parent.assignee}), not "
                f"{issuer}: below a root the issuer is Del(parent) by definition (§10.1).")
        if issuer and parent is None and self._graph.get_task(task_id) is None:
            self.record_root_issuer(task_id, issuer)
        source = (parent.assignee if parent and parent.assignee
                  else self._graph.issuer_of(task_id) if self._graph.get_task(task_id) is not None
                  else AgentId(self._storage.get_setting(root_issuer_key(task_id)) or assignee))
        a = self.send_signal_sync(SignalData(
            signal=Signal.ASSIGN, task_id=task_id, spec=spec, source=source,
            assignee=assignee, parent_id=parent_id, deadline=deadline, max_iterations=max_iterations,
            covers=tuple(covers),
        ))
        if a is not None and a.rejected:
            # a refused ASSIGN creates nothing — said in the rule's own sentence, not as a node that is not there
            raise ValueError(self.refusal_of(task_id, Signal.ASSIGN, a).refusal.why)
        if parent_id:
            # cross-node invalidation: a (re-)assigned child changes the parent's
            # CHECK-1/CHECK-7 (coverage / sufficiency read child criteria) → recompute + dirty.
            self._recompute_checks(parent_id)
        return self._graph.get_task(task_id)

    # === Authoring operations (UPPER layer — desugar to the 12 signals, NOT new signals) ===

    def revise(self, task_id: TaskId, new_spec: Spec, agent: AgentId, reason=None,
               deadline=None, max_iterations: Optional[int] = None,
               block_sources: tuple = (), block_refuted: bool = False) -> Task:
        """Revise a node's spec — canon v3.7 §12.3 Inv-1: a packet change on a live node = **re-ASSIGN under
        the SAME id → OFFERED** (NOT the CANCEL signal). The executor re-ACCEPTs/CHALLENGEs the new contract;
        each version is appended to the log (Inv-7: the immutable record is the LOG, not the node).

        `agent` must be the issuer (ASSIGN is an issuer signal — validated). The subtree is RETAINED
        (revision ≠ abandonment): no cascade; coverage staleness surfaces via CHECK-1 + non-redundancy/
        CHECK-1b (dangling covers) + CHECK-3 (Dep consumers) for the agent to resolve (surface-don't-destroy).
        Only a genuine abandon (CANCEL → CANCELLING → ABANDONED) cascades. The only IN-PLACE spec change is
        ACCEPT_CHALLENGE (executor-initiated negotiation; CHALLENGE answers FM-1/FM-2, §11.2).

        `reason` (optional RevisionReason, §15.4): the causal type of the revision — SPEC_DEFECT
        (criteria were wrong → counts in q_T) / SCOPE_EXPANSION (sanctioned §15.4 — never counts) /
        CAPABILITY_MISMATCH (Del change → counts in q_Del) / OTHER. Untyped keeps each metric's
        documented bias.

        `block_sources` / `block_refuted`: a revision of a BLOCKED node may answer its block's records as RESOLVE_BLOCK
        does — the confirmed source set, or refuted (§15.5: a re-ASSIGN's reason adjudicates); unanswered, they close.
        """
        return self._revise(task_id, new_spec, agent, reason=reason, deadline=deadline,
                            max_iterations=max_iterations, block_sources=block_sources, block_refuted=block_refuted)

    def edit_accepted_risks(self, task_id: TaskId, accepted_risks: tuple, agent: AgentId) -> Task:
        """UPPER convenience = read-modify-write over REVISE: replace a node's ACCEPTED_RISKS, keep the rest.
        Desugars to the lower signal path (no new command, no bypass). The whole packet is re-sent; the
        unchanged fields are carried for you (the human/agent edits one field)."""
        t = self._graph.get_task(task_id)
        if t is None:
            raise ValueError(f"task {task_id} not found")
        new_spec = dataclasses.replace(t.spec, accepted_risks=tuple(accepted_risks))
        return self.revise(task_id, new_spec, agent)

    def admit_register(self, task_id: TaskId, register: Register, agent: AgentId) -> Task:
        """The decomposer's act on his own node: the split's register admitted with it (§11.5) — `admission`."""
        t = _admit_register(self._graph, self._storage, len(self._audit), task_id, register, agent, self._validate)
        self._recompute_checks(task_id)
        return t

    def edit_criteria(self, task_id: TaskId, criteria: tuple, agent: AgentId, reason=None) -> Task:
        """UPPER convenience = RMW over REVISE: replace a node's criteria, keep description/ACCEPTED_RISKS.
        Dep criteria (depends_on) are part of `criteria` — pass the full set (RMW carries the unchanged).
        `reason` (§15.4): SPEC_DEFECT = the criteria were WRONG (counts in q_T); SCOPE_EXPANSION =
        sanctioned growth of the goal (§15.4 — never counts); untyped = uncounted (documented bias)."""
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
        # connected it to (FM-5 — the freshness face of an undeclared coupling, §8.6).
        # Removing an edge stays possible and stays EXPLICIT: `remove_dependency`, or passing the
        # `dep__` criterion yourself, which this respects.
        named = {c.name for c in criteria}
        carried = tuple(c for c in t.spec.criteria
                        if c.depends_on and c.name not in named)
        # …AND THE PINNED PROCEDURE OF A CRITERION THE CALLER RE-SENT WITHOUT ONE. Same argument as
        # the seam above, one field along: nobody rewording a criterion is asking to DELETE the
        # check that decides it, and losing it is invisible until the node is refused for pinning
        # nothing — after the work exists, which is when a procedure may no longer be authored
        # honestly. Passing the criterion WITH a `check` still replaces it, so an issuer who means
        # to change the procedure can; only silence carries the old one forward.
        # …AND ITS COMPOSITION FUNCTION, one field further along the same argument: nobody
        # rewording a criterion is asking to withdraw the statement of HOW its children secure it
        # (§2.4), and losing it puts CHECK-7 back on its assumed sum without a word.
        _had = {c.name: c.check for c in t.spec.criteria if c.check}
        _had_fn = {c.name: c.composition for c in t.spec.criteria if c.composition}
        criteria = tuple(Criteria(c.name, c.description, c.input, c.expected, c.n, c.timeout,
                                  c.depends_on, c.check or _had.get(c.name, ()),
                                  c.composition or _had_fn.get(c.name, ""))
                         for c in criteria)
        new_spec = dataclasses.replace(t.spec, criteria=tuple(criteria) + carried)
        return self.revise(task_id, new_spec, agent, reason=reason)

    def reassign(self, task_id: TaskId, new_assignee: AgentId, reason=None) -> Task:
        """UPPER: change a node's executor (Del). Canon Inv-1 fixes Del(t) at ASSIGN too → a change is a
        revision: re-ASSIGN (same id) carrying the new executor (the issuer acts). `reason` (§15.4):
        CAPABILITY_MISMATCH counts in q_Del; another typed reason (load, handoff) does NOT; untyped
        keeps the documented over-approximation (every untyped Del change counts). Same node returned."""
        t = self._graph.get_task(task_id)
        if t is None:
            raise ValueError(f"task {task_id} not found")
        return self._revise(task_id, t.spec, self._graph.issuer_of(task_id), new_assignee=new_assignee,
                            reason=reason)

    def reopen(self, task_id: TaskId, agent: AgentId) -> Task:
        """UPPER convenience over the R′ edge (§12.14): re-ASSIGN a quasi-terminal (DONE/ABANDONED)
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
        # …AND ITS PARENT MUST STILL BE LIVE. A child's REOPEN re-issues it (§12.14), so it is
        # refused under a parent that is settling or settled for the same reason its first ASSIGN is:
        # work re-issued under a closed goal is owed to nobody.
        if why := issuing_condition(self._graph.get_parent(task_id), task_id):
            raise ValueError(why)
        # REOPEN is restoration of a SETTLED node. ESCALATED is not settled — it is waiting for this
        # very caller — so the verb is refused and the act that exists is named instead. Left
        # unrefused it would have quietly worked (the edge out of ESCALATED is an ordinary re-ASSIGN),
        # and the two verbs would blur: one spends a reopen against the finality gate, the other is
        # the issuer answering a question the protocol asked him.
        if t.state == State.ESCALATED:
            raise ValueError(
                f"{task_id} is not settled — it is ESCALATED, which means it is waiting for YOU "
                f"(§12.5). `reopen` restores a node that finished; here nothing finished. "
                f"{self.issuer_moves_on(task_id)}")
        return self._revise(task_id, t.spec, agent)

    # === Query API ===


    def get_checks(self, task_id: TaskId) -> list[CheckResult]:
        """Read the CACHED L0/L1 checks (O(1)) — kept fresh by _recompute_checks on
        every decomposition change (cheap eager invalidation). Many watchers read this
        without recomputing."""
        return self._storage.get_check_results(task_id)

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
        refresh_checks(self._graph, node_id, stale_review)

    # === L2 critic / validation API ===
    # The L2 validate itself lives ABOVE the engine: gfso.critic.runner.review_decomposition(engine,
    # node_id) — the critic pulls decompose/adapters, and the engine imports core ONLY (the layer gate).
    # The engine keeps the pure storage reads its layer owns.

    # === The mode: who holds which nodes (the user's one knob) ===

    def record_root_issuer(self, task_id: TaskId, issuer: AgentId) -> None:
        """Record who issues a root about to be created — the goal's issuer, when the root's Del is
        someone else (`Graph.issuer_of`). Only before the root exists: a goal's issuer is fixed by its
        creation, and changing it afterwards would re-attribute every move already on the log."""
        if self._graph.get_task(task_id) is not None:
            raise ValueError(f"'{task_id}' exists — its issuer was fixed when it was created")
        self._storage.store_setting(root_issuer_key(task_id), str(issuer))

    def tally(self, key: str, add: int = 0) -> int:
        """A counter kept with the project (its settings), surviving a restart — `add` bumps it first."""
        n = int(self._storage.get_setting(f"tally:{key}") or 0) + add
        if add:
            self._storage.store_setting(f"tally:{key}", str(n))
        return n

    def mode(self) -> Optional[dict]:
        """The project's mode as set — {mode, boundary, by} — or None: no mode set, and every rule
        that reads it behaves as it did before modes existed."""
        return _project_mode(self._graph)

    def set_mode(self, mode: Mode, boundary: Optional[int], author: AgentId, said: str = "",
                 hands: Optional[str] = None) -> dict:
        """Record the user's choice. It governs nodes issued AFTER it: an issued node keeps its Del,
        which only a logged re-ASSIGN changes (Inv-1). `hands`: the executor whose session performs the
        nodes the user-agent holds (dispatch, `hands_of`); None — it performs them in its own chat."""
        if boundary is not None and (mode != Mode.SEMI or boundary < 1):
            raise ValueError(
                f"a boundary is the depth down to which the user-agent holds the tree in SEMI-AUTO, "
                f"at least 1 (the root); SOLO holds everything and AUTO nothing, so {mode.value} takes "
                f"none")
        # numbered and stamped: a mode switched and switched back leaves a DIFFERENT record, so a reader
        # comparing records (an experiment's validity check, an audit) sees that it moved at all
        rec = {"mode": mode.value, "boundary": boundary, "by": str(author),
               "seq": ((self.mode() or {}).get("seq") or 0) + 1, "at": datetime.now().isoformat(),
               # where in the log THIS MODE began: consent given before it was given under another mode. A
               # re-record of the same mode (the user moving SEMI's boundary) does not move it — else every
               # consent given under SEMI read as given before it (critic round 17)
               "log_at": (prev.get("log_at", len(self._audit)) if (prev := self.mode() or {}).get("mode")
                          == mode.value else len(self._audit)),
               # HOW the user-agent performs what it holds — nothing to say under AUTO, where it holds nothing
               **({} if mode == Mode.AUTO else {"perform": "dispatch" if hands else "in_chat"}),
               **({"hands": str(hands)} if hands else {}),
               **({"user_said": said} if said else {})}
        self._storage.store_setting("mode", json.dumps(rec))
        self.emit_info("mode", f"mode set to {mode.value}"
                       + (f" (boundary {boundary})" if boundary is not None else "") + f" by {author}")
        return rec

    def hands_of(self, party) -> Optional[str]:
        """The executor whose session performs `party`'s nodes, or None (`validation.hands_of`)."""
        return _hands_of(self._graph, party)

    def depth_of(self, task_id: TaskId) -> int:
        """How many edges from the root down to this node (the root is 0)."""
        return _depth_of(self._graph, task_id)

    def holder_boundary(self) -> Optional[float]:
        """b: the user-agent holds depths < b, the system holds b and below; None with no mode set
        (`validation.holder_boundary` — one reading, shared with the engine's own rule on held nodes)."""
        return _holder_boundary(self._graph)

    def held_by_the_user_agent(self, depth: int) -> Optional[bool]:
        """Does the mode put a node at this depth in the user-agent's hands? None with no mode set."""
        b = self.holder_boundary()
        return None if b is None else depth < b

    def held_node_refusal(self, task_id: TaskId, signal: Signal) -> Optional[str]:
        """Why the mode refuses the user-agent this ACCEPT/DELIVER on a node it holds, or None — the engine's
        own rule, read by anything that advises a move so it never advises one the rule refuses."""
        return held_plan_node_refusal(self._graph, self._graph.get_task(task_id), signal, self._audit)

    def get_critique(self, node_id: TaskId) -> Optional[dict]:
        raw = self._storage.get_critique(node_id)
        return json.loads(raw) if raw else None

    def dispute_review_finding(self, node_id: TaskId, criterion: str, why: str,
                               agent: AgentId) -> dict:
        """Record the issuer's justified refusal of ONE Level-2 finding — the one way to discharge
        it where it stands (fixing the plan RETIRES the verdict instead, and needs a fresh review). The checker is an approximation over the faithfulness
        axis (§9.9) and can be wrong; what the system refuses is a SILENT skip, so the dispute is
        written into the review record with its author and time (§19.3: an explicit falsifiable claim
        instead of an unstated one). It dies with that record — any edit to the decomposition stales
        the review, and the next `review_decomposition` overwrites it, so a dispute never launders a
        finding across plan versions: it must be re-stated against the fresh verdict.

        Refused when there is no current verdict, or when the named criterion is not one the checker
        actually flagged (nothing to dispute)."""
        node = self._graph.get_task(node_id)
        if node is None:
            raise ValueError(f"unknown task {node_id}")
        raw = self._storage.get_critique(node_id)
        rec = json.loads(raw) if raw else None
        # …A VERDICT THAT STANDS, not a record: a round that read nothing carries the goal reading on record
        # with no verdict, and a dispute against it "discharged" a finding no gate held (critic round 11)
        if not rec or not getattr(node, "verified", False) or rec.get("semantic_covered") is None:
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
            near = [f for f in flagged if loose_finding_key(f) == loose_finding_key(criterion)]
            if len(near) != 1:
                raise ValueError(
                    f"{criterion!r} is not an open Level-2 finding on {node_id} — open: "
                    f"{', '.join(sorted(flagged)) or '(none)'}"
                    + (". Two of the open findings match it once punctuation is ignored, so name one "
                       "of them exactly." if len(near) > 1 else ""))
            criterion = near[0]
        # …AND ONLY AN OPEN ONE. A dispute of a finding already disputed closes nothing; admitted, it was a
        # move that always "applied" — the machine issuer re-disputed one key without end (critic round 7:
        # a hyphen for an em-dash passed its own near-match, then matched the disputed key exactly here).
        if criterion in (rec.get("disputes") or {}):
            raise ValueError(f"{criterion!r} is already disputed on {node_id} — open: "
                             f"{', '.join(sorted(flagged - set(rec['disputes']))) or '(none)'}")
        rec.setdefault("disputes", {})[criterion] = {
            "why": why, "by": str(agent),
            "ts": datetime.now().isoformat(sep=" ", timespec="seconds")}
        self._storage.store_critique(node_id, json.dumps(rec))
        return {"task_id": str(node_id), "disputed": criterion,
                "open_findings": sorted(flagged - set(rec["disputes"]))}


    # === Metrics API ===

    def metrics(self) -> dict[str, float | None]:  # None = ⊥, пустая популяция (§15.4) — рендерится прочерком
        """The five quality metrics of this graph, plus the false-FAIL diagnostic (§15.4).

        A `None` is ⊥ — the population was empty — and never a score of zero: no observation is
        not a bad result, and rendering it as one is the misreading this whole vector invites.
        """
        return {
            "q_T": q_T(self._graph),
            "q_D": q_D(self._graph),
            "q_V": q_V(self._graph),
            "q_Dep": q_Dep(self._graph),
            "q_Del": q_Del(self._graph),
            # Diagnostic, NOT a Q component (§15.4: false-FAIL is guarantee-safe, outside the
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
                self._storage.log_pipeline(
                    datetime.now().isoformat(sep=" ", timespec="seconds"), source, message)
            except Exception:
                pass  # observation is presentation — never break the pipeline

    def pipeline_log(self, limit: int = PIPELINE_PAGE) -> list[dict]:
        """The persisted observation history, oldest-first: [{ts, source, message}]."""
        return self._storage.get_pipeline(limit)

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
            self._storage.log_usage({
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
        return self._storage.get_usage(limit)

    def usage_totals(self, limit: int = USAGE_PAGE) -> dict:
        """{calls, tokens…, cost_usd, by_stage} over the recorded model calls of THIS project.

        `cost_usd` sums what the transport REPORTED; a provider that reports none contributes 0 and
        says so through `costed_calls` — a total that silently mixes "free" with "not reported" is
        the ⊥-as-zero error in a money column."""
        rows = self._storage.get_usage(limit)
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


    def record_exec_verdict(self, task_id: TaskId, verdict: str, failed_criteria: list,
                            validator_id: str, per_criterion: Optional[list] = None,
                            tools_used: Optional[dict] = None,
                            require_probe: bool = False,
                            generation: Optional[tuple] = None,
                            model: Optional[str] = None,
                            workdir: Optional[str] = None,
                            by_hand: bool = False, inputs_dirs: tuple = (),
                            log_at: Optional[int] = None) -> dict:
        """Store the independent validator's verdict for the node's CURRENT delivery (stamped with the
        node's GENERATION (iteration, reopens, revisions) — a rework, a reopen OR a revision
        invalidates it: the next
        delivery needs a fresh verdict; the superseded record is replaced, never trusted forward).

        When the report carries per-criterion evidence, the engine RECORDS ONLY A VERDICT: a report
        that leaves a criterion unspoken or contradicts its own evidence is ⊥, not a verdict (§2
        V=⋀cᵢ), and is REFUSED here — at the record, not in a prompt (visibility ≠ enforcement). The
        refusal composes with the self-PASS gate (§10.3): with no recorded PASS, the node cannot
        complete on its executor's own stamp. The evidence is persisted with the verdict — the
        Thm 11 trail must show WHAT was verified, not just the answer (§15.8: the q_V open-event
        carrier).

        RETURNS what was actually recorded — {verdict, failed_criteria} — because it is not always
        what was passed in: an underprobed criterion is demoted here, and a caller that goes on
        holding the claimed verdict signs the claim rather than the record. Measured live: a report
        claiming PASS over two criteria whose behaviours were never observed was stored as FAIL,
        logged as PASS, and signed PASS — the node closed DONE on evidence the engine had already
        refused to let carry a pass. The demotion is only a guarantee if it reaches the signal."""
        # THE WORD IS COERCED TO THE ENUM HERE, or refused — never stored as the text that arrived.
        # Typed `str` and compared with `== Verdict.PASS`, a value in any other casing matched
        # NEITHER branch: every check below fell through as a no-op, the string went in verbatim, and
        # downstream nothing recognised it — the parent's AND never closed, no signal was ever sent,
        # and the node sat in VALIDATING for ever WITH a verdict on its record. The schema declares
        # the enum and the reply parser does not enforce it, so `"pass"` from a model is an ordinary
        # answer. The human door has always coerced (`tools._self_check_verdict`); the record, which
        # is where EVERY door lands, did not.
        verdict = decided_verdict(verdict)
        task = self._graph.get_task(task_id)
        # A NODE WITH NO CRITERIA HAS NOTHING A VERDICT COULD BE ABOUT, whichever door produced it.
        # V is the conjunction over the node's criteria (§2), and over the empty set that is
        # vacuously TRUE — which is not a verdict. `record_verdict` refused this by name from
        # 2026-09-02; `validate_result` did not, so a stranger on the HTTP door delivered a
        # criteria-less root with "nothing to do here", had the instrument sign a `PASS` with
        # `per_criterion: []`, and reached root DONE/PASS with COMPLETE on every surface (wave 23,
        # 2026-09-03). The rule now lives where every verdict lands, so a second door cannot be
        # written past it — the guard was one door wide, which is the class this product keeps
        # finding in itself.
        if task is not None and criterionless(task.spec.criteria):
            raise ValueError(
                f"not a verdict on {task_id}: it has no criteria, so there is nothing a verdict "
                f"could be ABOUT. V is the conjunction over a node's criteria (§2), and over an "
                f"empty set that is vacuously true — which is not a verdict. Give it criteria "
                f"(`edit_criteria`) and validate those.")
        # …AND A PASS THAT SPEAKS OF NOTHING IS THE SAME ABSENCE, one step along. The guard above
        # catches a node with no criteria; this catches a node whose criteria were simply never
        # addressed. The battery below was gated on `per_criterion is not None`, so a report that
        # observed nothing did not fail the battery — it turned the battery OFF, which is the
        # defensive default disabling its own guard. Reproduced 2026-09-07 through ordinary verbs:
        # a self-named reviewer recorded PASS with `observed={}`, the record went in with
        # `per_criterion: []`, and the node closed DONE/PASS on a record whose own independence line
        # says its weight IS the observation text beside each criterion. A FAIL is left alone: Inv-3
        # asks it for the red set, not for a line per conjunct, and tightening that would refuse
        # honest work.
        if verdict == Verdict.PASS and not per_criterion and task is not None and task.spec.criteria:
            raise ValueError(
                f"not a verdict on {task_id} (⊥, not pass — §2.3): a PASS was recorded that says "
                f"nothing about any of its {len(task.spec.criteria)} criteria. V is the conjunction "
                f"over the contract (§2); a conjunct nobody spoke to is ⊥, and ⊥ does not carry a "
                f"pass. Say what was observed per criterion, or record what actually happened.")
        if per_criterion is not None and task is not None:
            defects = verdict_report_defects([c.name for c in task.spec.criteria], verdict,
                                             per_criterion, list(failed_criteria or ()),
                                             require_probe=require_probe)
            if defects:
                raise ValueError(f"not a verdict on {task_id} (⊥, not pass — §2): "
                                 + "; ".join(defects))
            # A criterion whose named behaviours were not all probed is UNDECIDED, not passed: the
            # report stays a verdict (it is well-formed), but an unobserved conjunct cannot carry a
            # pass (§2.3). Demoted here rather than refused above, because refusing stalls the node
            # and ends the run over an incomplete proof, while demoting sends it back for rework
            # naming exactly what was never observed — which is the loop this evidence exists for.
            # …AND A PROBE THAT NAMES A COMMAND IN A RUN WITH NO SHELL IN ITS LEDGER. Same demotion,
            # different question: `underprobed` asks whether enough was probed, this asks whether the
            # probing HAPPENED. The record has promised exactly this since `tools_used` was added
            # ("refuted structurally, without parsing a word of its prose") and nothing did it — one
            # reader in the tree, a test asserting the contradiction is merely STORED. Folded into
            # `gaps` so the disposition below (⊥ belongs to the INSTRUMENT, never to the executor's
            # rework budget) applies unchanged.
            gaps = unaccounted_for(task, per_criterion, by_hand, validator_id,
                                   self.regression_probes(task_id),
                                   internal=not self._graph.is_public(task), dirs=inputs_dirs,
                                   parts=self.parts_procedure(task_id), delivery=workdir)
            for _c in unrun_probes(per_criterion, tools_used):
                gaps.setdefault(_c, []).append(
                    "its probe names a command, and this validation run's tool ledger records no shell "
                    "at all — the command was not run here")
            # …EXCEPT WHERE THE REPORT REFUTED SOMETHING. Under-probing means an unobserved conjunct
            # cannot carry a PASS — that is the whole of §2.3's asymmetry — and it says nothing
            # against a criterion the report FAILED with evidence: a refutation is a decision, and
            # the evidence for "this test does not exist" is an absence, which has no `expect` line
            # to show. Measured on the human door 2026-08-21: a deliberately garbage delivery (two
            # tests, one of them `assert True`, no CLI coverage) was caught exactly right, and the
            # engine threw the FAIL away because the probes behind it had empty `expect` fields. A
            # rule against false PASSES that suppresses a true NEGATIVE is worse than the hole it
            # guards: the bad work went back looking accepted.
            _refuted = {str(e.get("criterion")) for e in per_criterion
                        if spoken_verdict(e.get("verdict")) == "fail" and str(e.get("evidence", "")).strip()}
            gaps = {c: b for c, b in gaps.items() if c not in _refuted}
            for _c, _why in self._refiled_rulings(task_id, per_criterion, inputs_dirs).items():
                gaps.setdefault(_c, []).append(_why)
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
                # retry, then a NAMED parking for the issuer (§2.3: ⊥ is not pass).
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
                        f"not a verdict on {task_id} (⊥, not pass — §2.3): the report names "
                        f"behaviours it never observed and refutes nothing, so it decides nothing. "
                        + "; ".join(f"criterion '{c}' — unobserved: {', '.join(b)}"
                                    for c, b in sorted(gaps.items()))
                        + ". Re-run the validation running each criterion's WHOLE pinned procedure — a "
                          "criterion stands on it — and, where a criterion pins none, a probe for EVERY "
                          "behaviour it names (one command may observe several — label it with `behaviour`). "
                          "This is the instrument's gap, not the executor's: do not send the node "
                          "to rework over it. The probes are the INSTRUMENT's to write; the other way "
                          "through is `record_verdict` with what YOU observed."
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
        # A FAIL OBSERVED ON THIS DELIVERY STANDS. A divergence an independent observer recorded between the
        # result and a criterion IS that criterion's value, fail, and no later record turns it into a pass
        # (Inv-2, §12.8): what changes it is the issuer's FAIL (the executor re-delivers) or a revision of
        # the criteria (Inv-1, re-consented) — both of which move the generation this compares. The rule
        # read the other way until 2026-09-27 ("a person MAY overrule an instrument … what it must not be is
        # SILENT"), and a self-named reviewer's `record_verdict` PASS then opened the gate over a recorded
        # fail. The dissent is kept on the log as a report; it removes nothing. What binds is an APPOINTED
        # observer's record — the instrument, or the node's issuer — never the executor's own self-report
        # (it would let an executor veto an independent issuer's PASS at a seam) and never a hand record by
        # some other self-named party, which stays a report.
        # …SAVE THE ONE LIFT §12.16 (ii) REQUIRES: at a seam the issuer's own observation stands past it, as a
        # logged disagreement (`displaces_a_refutation`); another instrument run does not.
        if (verdict == Verdict.PASS and task is not None
                and not displaces_a_refutation(self._graph, task, validator_id, by_hand)
                and tuple(generation or self._graph.generation_of(task_id)) == generation_of_task(task)
                and (fails := observation_standing(self._graph, task, self._audit)["fails"])):
            self.emit_info("verdict", f"{task_id}: {validator_id} observed a PASS where an appointed observer had "
                                      f"recorded FAIL on {', '.join(fails)} for the same delivery — kept as a "
                                      f"report; the FAIL stands (Inv-2)")
            raise ValueError(
                f"not recorded on {task_id}: an appointed observer recorded this delivery FAIL on "
                f"{', '.join(fails)}, and an observed divergence is that criterion's value (Inv-2, §12.8) — a "
                f"later record does not turn it into a pass. The issuer's moves are FAIL (the executor "
                f"re-delivers) or a revision of the criteria (Inv-1). Your observation is on the log.")
        # THE VERDICT THAT CLOSED THE NODE IS KEPT. A record may legitimately land on a node that has
        # already settled — that is q_V's whole discovery carrier, and how a pass is found to have
        # been wrong — but it OVERWROTE the one that did the closing. Measured on the HTTP door
        # 2026-09-02: a hand-asserted PASS containing false statements closed a node, an instrument
        # reported 46 seconds later, its SIGNAL was refused (the node was terminal) and its record
        # was written anyway, so every surface then said the node had been validated by an instrument
        # and the record that actually closed it was reachable from nowhere. The two surfaces this
        # product offers as its guarantee are "the record" and "in writing"; that was both of them.
        if task is not None and task.state in TERMINAL_STATES:
            if not ledger_read(self._storage, task_id, CLOSING) and (prior := self.get_exec_verdict(task_id)):
                ledger_write(self._storage, task_id, CLOSING, prior)
        # …AND THE SAME BEFORE THE CLOSE, WHICH THAT RULE DID NOT COVER. The block above keeps the
        # record a node CLOSED on; a verdict that overwrites a contradicting one while the node is
        # still being validated left no trace at all. Measured on the CLI door (wave 24, 2026-09-04):
        # an instrument validated a node on which nothing had been built and recorded FAIL; a
        # hand-asserted PASS naming a reviewer invented in that same call replaced it; and
        # `get_verdict` then read PASS with `failed_criteria: []`, `gfso status` showed the tick an
        # earned node gets, `next_steps` said COMPLETE and `q_V` was 1.0. The instrument's refutation
        # survived only in the chronological log. `refuted_passes` does not fire here — it is about
        # verdicts landing AFTER a close — so four of five surfaces reported an earned green.
        # A person MAY overrule an instrument: §10.2 keeps the verdict the issuer's act, and §15.7
        # says the engine cannot check a self-named party's independence. What it must not be is
        # SILENT, which is this product's whole position on the degenerate case.
        elif (prior := self.get_exec_verdict(task_id)) and prior.get("verdict") != verdict:
            _gen = tuple(generation or self._graph.generation_of(task_id))
            if stamped_with(prior, _gen):
                ledger_write(self._storage, task_id, OVERRULED, prior)
        # THE REGRESSION SET GROWS, AND ONLY GROWS. Kept beside the node rather than folded into
        # the criterion: the pinned procedure is the issuer's pre-registered claim, and rewriting
        # it at validation time would move the contract under the executor (Inv-1). Promotion into
        # the contract stays an issuer's act (`edit_criteria`), and `claim_drift` shows it.
        # …AND ONLY GROWS UNTIL ITS ISSUER RULES ONE OUT (`findings`) — each with the text it refuted as the run
        # VALIDATED it, the one he rules on, not the spec standing when the record lands
        if per_criterion:
            _found = refuting_probes(per_criterion, inputs_dirs, texts={
                **{c.name: c.description for c in (task.spec.criteria if task else ())},
                **{n: v[0] for n, v in self._validated_versions(task_id).items()}})
            if _found:
                ledger_write(self._storage, task_id, REGRESSION, merge_regression(self._stored_regression(task_id), _found))
        # …placed where the run READ it: an instrument hands in the position its claim took when it began
        # (`ValidationClaim.log_at`) — a footing that moved while it ran is after its record; a hand record reads now
        store_verdict(self._storage, task_id, task, verdict, failed_criteria, validator_id,
                      generation or self._graph.generation_of(task_id), len(self._audit) if log_at is None else log_at,
                      per_criterion=per_criterion, tools_used=tools_used, model=model,
                      workdir=workdir, by_hand=by_hand, validated=self._validated_versions(task_id),
                      inputs_dirs=inputs_dirs,
                      # …which parts this FAIL did not show holding on the delivered result, read now, while this
                      # round's inputs directories still name what the report ran (`_refuted_coverage_refusal`)
                      parts_not_shown_holding=parts_not_shown_holding(self.parts_procedure(task_id), per_criterion or (),
                                                          inputs_dirs, own=task.spec.criteria)
                      if task is not None and verdict == Verdict.FAIL else {})
        return {"verdict": verdict, "failed_criteria": list(failed_criteria or ())}

    def _refiled_rulings(self, task_id: TaskId, per_criterion: list, dirs) -> dict:
        """{criterion: why} for each FAIL of this report resting only on findings its issuer ruled outside the criterion.
        A retired finding filed again is that ruling's subject, not a fresh observation — counted as a FAIL, it
        re-opened the dispute the ruling closed; so it is no refutation, and the record treats it as unobserved."""
        ruled = {(r.get("criterion"), r.get("id")) for r in self.retired_findings(task_id)}
        again = refuting_probes(per_criterion, dirs)
        out = {}
        for e in per_criterion:
            ps = again.get(name := " ".join(str(e.get("criterion", "")).split()), ())
            if ps and spoken_verdict(e.get("verdict")) == "fail" and all((name, p["id"]) in ruled for p in ps):
                out[str(e.get("criterion"))] = ("its refutation rests only on findings its issuer ruled outside this "
                                                f"criterion ({', '.join(p['id'] for p in ps)}) — filed again, they are "
                                                f"not a refutation")
        return out

    def _validated_versions(self, task_id: TaskId) -> dict:
        """{criterion: version} as it stood at the node's last DELIVER — what a verdict validates.

        Not the spec as it stands when the verdict is WRITTEN: a validation runs for minutes, and a
        criterion edited inside that window would be recorded as refuted though nobody validated it."""
        in_force: dict = {}
        validated: dict = {}
        for e in self._audit.get_entries(task_id):
            if e.signal in VERSION_INSTALLING and not e.rejected and e.spec:
                try:
                    in_force = {c.get("name"): criterion_version(c.get("description"), c.get("check"))
                                for c in (json.loads(e.spec).get("criteria") or ()) if c.get("name")}
                except (ValueError, TypeError):
                    in_force = {}
            elif e.signal == Signal.DELIVER and not e.rejected:
                validated = dict(in_force)
        return validated

    def overruled_verdict(self, task_id: TaskId) -> Optional[dict]:
        """A verdict on THIS delivery that a later, contradicting one replaced before the close.

        Not the same fact as `closing_verdict`, which is about a record landing after the node had
        already settled. This one is the disagreement inside the validation window: two parties validated
        one delivery and said opposite things, and only the second was left standing."""
        rec = ledger_read(self._storage, task_id, OVERRULED)
        if not rec:
            return None
        # Only while it is still ABOUT the standing delivery: a rework moves the generation and the
        # old disagreement is then history, not a contradiction anyone has to weigh.
        task = self._graph.get_task(task_id)
        gen = generation_of_task(task) if task is not None else (0, 0, 0)
        return rec if stamped_with(rec, gen) else None

    def closing_verdict(self, task_id: TaskId) -> Optional[dict]:
        """The verdict this node actually CLOSED on, when a later record has landed on top of it.

        None when nothing has overwritten it — then `get_exec_verdict` is the closing one.
        """
        return ledger_read(self._storage, task_id, CLOSING)

    def record_reviewer_verdict(self, task_id: TaskId, verdict: str, failed_criteria: list,
                                reviewer: str, observed: Optional[dict] = None) -> None:
        """The HUMAN counterpart of validate_result's record: an independent reviewer's verdict on
        the node's CURRENT delivery (feeds the same self-pass gate). The engine REFUSES a reviewer
        who IS the node's executor — recording a verdict on your own work would open the
        verifier≠executor gate from the inside (§16.13 IC; visibility ≠ enforcement: the refusal is
        here, not in a prompt). FAIL requires failed_criteria (Inv-3)."""
        task = self._graph.get_task(task_id)
        if task is None:
            raise ValueError(f"unknown task {task_id}")
        if verdict not in (Verdict.PASS, Verdict.FAIL):
            raise ValueError(f"verdict must be PASS or FAIL, got {verdict!r}")
        if verdict == Verdict.FAIL and not failed_criteria:
            raise ValueError("FAIL requires failed_criteria (Inv-3: a FAIL is never criteria-less)")
        # A VERDICT IS ABOUT A DELIVERY THAT IS STILL BEING VALIDATED. On a settled node this recorded
        # happily, answered `recorded: true`, changed nothing, and then told the caller to signal —
        # which the FSM refuses, because a terminal state admits no signal (§12.4). Two false things
        # in one reply, and the second sends the reader after a move that cannot be made. The only
        # route back to validating a settled node is REOPEN, and it has its own gate (§12.14 finality).
        if task.state in TERMINAL_STATES:
            raise ValueError(
                f"{task_id} is {task.state.name} — a settled node is not being validated, so a verdict "
                f"about it changes nothing and no signal follows it (§12.4 admits none from a "
                f"terminal state). If the result must be re-validated, `reopen` it first — that is the "
                f"one route back, and it refuses a node the graph has already built on.")
        # …AND THE SAME SENTENCE APPLIES BEFORE THE DELIVERY, WHICH IT DID NOT COVER. The rule read
        # "not settled"; what it means is "there is a delivery standing to be validated", and only
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
                f"{task_id} is {task.state.name} — there is no delivery standing to be validated, so "
                f"there is nothing this verdict could be ABOUT. A verdict belongs to a DELIVERY "
                f"(§10.2): it is recorded while the node is VALIDATING, between the DELIVER that "
                f"offers the work and the PASS/FAIL that settles it. In REWORKING the previous "
                f"delivery was refused and the work is being redone — wait for the next DELIVER and "
                f"validate that.")
        # THE SEAM IS WHERE INDEPENDENCE IS OWED — §10.3, and only there. On an INTERNAL node
        # (its Del is its parent's) the canon says the executor self-verifies, and its guarantee is
        # carried by the validation of the public result above it. This refused that everywhere, and
        # the two doors then disagreed about one act: `record_verdict` said no while `signal PASS`
        # said yes — correctly, since the FSM applies the gate on public nodes only. Measured
        # 2026-08-21: the door that would have LEFT A RECORD was the one that refused, so a lone
        # person's node reached DONE with no evidence anywhere, and the honest path was the closed
        # one. On a seam this still refuses; on an internal node the self-verdict is recorded, with
        # what was observed, which is exactly what §10.3 asks a self-verifying node to carry.
        if (task.assignee and str(reviewer) == str(task.assignee)
                and self._graph.is_public(task)):
            raise ValueError(f"reviewer {reviewer!r} is the node's own executor and {task_id} is a "
                             f"SEAM (a root, or its Del differs from its parent's) — an independent "
                             f"verdict cannot come from the executor there (verifier ≠ executor, "
                             f"§10.3). Run `validate_result`, or have someone else record it. (On an "
                             f"INTERNAL node — same Del as its parent — your own verdict IS the "
                             f"record the canon asks for, and this verb takes it.)")
        # …AND A PASS ON A WHOLE WAITS FOR ITS PARTS, as the instrument's door does (`validate_result`): what a
        # whole's check runs includes every DONE part's procedure (`parts_procedure`), so a PASS made while a part is
        # still open demanded nothing of it, and it stood after the part passed (critic r2, 2026-10-04). A FAIL needs
        # no wait — a refutation is a verdict already. Lifted by settling the parts, the issuer's own moves.
        if verdict == Verdict.PASS and whole_waits_for_its_parts(self._graph, task) and (_open := self.joins.open_parts(task_id)):
            raise ValueError(f"not recording a PASS on {task_id} yet: it aggregates parts that have not passed — "
                             + ", ".join(f"'{c.id}' is {c.state.name}" for c in _open)
                             + ". Its check runs their pinned procedure over this delivery once they have; "
                               "settle them first (`next_steps`), or record a FAIL if this delivery already fails")
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
        # …AND WHICH OF THE PINNED PROBES THE PERSON RAN. A reviewer is still not asked to WRITE
        # commands — that rule stands, and the sentence remains the human-sized grade of evidence.
        # What they are asked is which of the procedure the contract ALREADY pins they executed:
        # `observed={'c1': {'note': 'ran it, it printed 42', 'ran': ['c1#2ad15c16']}}`, or the
        # commands themselves. Without that a hand PASS would be the one door where a pinned
        # procedure may be skipped in silence — and the hand door is where the false passes this
        # product keeps finding were measured (2026-08-20, 2026-09-02, wave 23).
        _crit = {c.name: c for c in (task.spec.criteria if task is not None else ())}
        _parts = self.parts_procedure(task_id)      # a part's pinned probe is cited under the criterion it rests on

        def _entry(k, v):
            note = v.get("note", v.get("observed", "")) if isinstance(v, dict) else v
            ran = [str(x) for x in (v.get("ran") or ())] if isinstance(v, dict) else []
            pinned = {probe_id(c.name, p): p for c in ([_crit[k]] if k in _crit else []) + list(_parts.get(k, ()))
                      for p in (c.check or ())}
            named = [dict(p.to_dict(), id=pid)
                     for pid, p in pinned.items()
                     if pid in ran or any(str(p.command).strip() and str(p.command).strip() in r
                                          for r in ran)]
            # …AND WHAT THE PERSON SAW THAT DIFFERS FROM WHAT THE CRITERION STATES. Same field the
            # instrument's report carries, and for the same reason: a divergence IS the criterion's
            # value (Inv-2, §12.8), so it must be recordable at the hand door too — otherwise the
            # one door where a waiver is easiest to write is the one where nothing can be refused.
            div = [str(d) for d in ((v.get("divergences") or ()) if isinstance(v, dict) else ())]
            e = {"criterion": k, "verdict": "fail" if k in _red else "pass", "evidence": str(note)}
            if div:
                e["divergences"] = div
            return dict(e, probe=named) if named else e

        self.record_exec_verdict(
            task_id, verdict, list(failed_criteria or ()), str(reviewer),
            per_criterion=[_entry(k, v) for k, v in (observed or {}).items()] or None,
            by_hand=True)

    def record_rejected_report(self, task_id: TaskId, defects: str,
                               per_criterion: Optional[list] = None,
                               tools_used: Optional[dict] = None,
                               validated_by: Optional[dict] = None) -> None:
        """Keep a report the engine REFUSED to record as a verdict — as evidence, never as one.

        §2.3: ⊥ is not a pass, so a refused report stops the node and the issuer decides. They were
        given nothing to decide WITH: the observations lived in a return value the dispatcher does
        not read and in a text file whose path went past in a log line. This stores what the validator
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
        gen = generation_of_task(self._graph.get_task(task_id))
        _same = stamped_with(prev, gen)
        ledger_write(self._storage, task_id, REJECTED_REPORT,
                     {"defects": defects,
                         "per_criterion": list(per_criterion or ()),
                         # the run's tool ledger, so an entry reused on the next attempt keeps the
                         # evidence that a shell ran behind it (`unrun_probes`)
                         "tools_used": dict(tools_used or {}),
                         # …and WHO validated, so an entry reused later says so on the verdict
                         "validated_by": dict(validated_by or {}),
                         "refusals": (int(prev.get("refusals", 0)) + 1) if _same else 1,
                         **stamp(gen),
                         "ts": datetime.now().isoformat(sep=" ", timespec="seconds")})


    def pass_blocked_by(self, task_id: TaskId) -> Optional[dict]:
        """Why a PASS on this node would be refused whoever signs it — or None when nothing does.

        The sibling of `execution_blocked_by`, for the other end of a node's life, and it exists for
        the same reason: the rule was asked in two places with two answers. `engine/validation.py`
        refuses PASS on three grounds — the AND over unsettled children (Thm 1, §7.3), the node's
        OWN decomposition failing the Syntactic level (§9.5, so the AND is not a verdict about this
        goal), and the seam's independent verdict (§10.3) — and the affordance surface modelled the
        third, then the first as a hand-copy, and never the second. A node whose children have all
        settled but whose plan has since gone red (a child CANCELled out from under a `covers`
        mapping, `edit_criteria` adding an uncovered criterion) was therefore offered a PASS the
        engine refuses by rule.

        The two rules here are the ones this owner carries. The seam and self-check rules stayed
        with the surface because they were once said to "turn on who is signing" — and as of
        2026-09-08 neither does: both ask whether a verdict for THIS delivery is on the record, and
        the engine refuses them to every signer alike. That sentence was the stale rationale keeping
        two more copies where they are; folding them in is the next step and is not this one. Returns {why, opens_with} in the same shape the plan gate answers in.
        """
        t = self._graph.get_task(task_id)
        if t is None:
            return None
        # the rule `_pass_rules` keeps: these refuse only where the whole's issuer is its Del (§12.16 (ii), §12.8)
        waits = whole_waits_for_its_parts(self._graph, t)
        if waits and (unpassed := [c.id for c in self.joins.open_parts(task_id)]):
            return {"why": (f"it aggregates children that have not passed "
                            f"({', '.join(str(c) for c in unpassed)}), and a parent's verdict is "
                            f"the AND over them (Thm 1, §7.3)"),
                    "opens_with": "drive those children first; `next_steps` names the move on each",
                    "unpassed": [str(c) for c in unpassed]}
        if waits and (holes := _l0_holes(self._graph, t)):
            return {"why": ("its own decomposition does not pass the Syntactic level NOW (§9.5), "
                            "so the AND over its children is not a verdict about THIS goal "
                            "(Thm 1): "
                            + "; ".join(f"{h.check_name}: {h.details}" for h in holes)),
                    "opens_with": (f"repair the plan — map the criterion to a child, add a coverer, "
                                   f"or revise the contract; `list_holes('{task_id}')` lists it"),
                    "unpassed": []}
        if (ob := (_split_owed(self._graph, t) if _observation_binds(self._graph, t) else None)
                  or observation_blocker(self._graph, t, self._audit)):
            return {**ob, "unpassed": []}
        return None

    def execution_blocked_by(self, task_id: TaskId) -> Optional[dict]:
        """Why the PLAN gate holds this node's start — or None when it may start.

        §11.5: a decomposition that fails the Syntactic level is not admitted to execution, and this
        engine additionally holds the Pragmatic check to have HAPPENED over this version of the plan
        with its findings dispositioned (declared in `formal/README.md`). The question was asked in
        three places with three answers: the frontier, to decide whether to offer the step; the
        dispatcher, before paying for an executor; and the affordance surface, to decide whether to
        list ACCEPT. One rule, one owner — the three of them cannot disagree about whether a node may
        start.

        It holds whom the gate binds (C9-L2, §12.16 (ii)): the decomposer's own child, whose ACCEPT the machine
        refuses until he lifts it, and a child the dispatcher would start, the system holding its own spawn. Another
        party's child is not held — its ACCEPT is admitted, an EXPLORE (§9.9) — so no surface withholds it.

        Returns {why, opens_with} — the reason in the caller's own terms and the one call that opens
        the gate."""
        # THE PINNED-PROCEDURE RULE IS NOT ASKED HERE ANY MORE. It is an ADMISSION rule now, held at
        # the issuer's ASSIGN (§12.16's conformance clause: a refusal must be liftable by the refused
        # party's own moves, and the executor cannot author the contract he was handed), so no node
        # admitted since carries a criterion without one. Left here it made this surface STRICTER
        # than the machine — the frontier withholding an ACCEPT the FSM takes — which is the same
        # disagreement, mirrored, that `test_the_surface_offers_only_what_the_machine_accepts`
        # exists for. A row written by an older build still shows the A1:procedure hole on its node.
        t = self._graph.get_task(task_id)
        # …BUT NO NODE IS READY OVER NO CRITERIA, a root included: "every criterion has its check" holds of the
        # empty set, and the measured root with `criteria: []` was spawned, delivered, and waited in VALIDATING for a
        # verdict over nothing (§2.2). The admission refuses such a packet now; this holds one that predates it.
        if t is not None and (why := criterionless(t.spec.criteria)):
            return {"parent_id": str(t.parent_id or t.id), "waits_on": f"the contract of '{t.id}'",
                    "why": f"'{t.id}' is not ready to execute: {why}",
                    "opens_with": f"its issuer revises '{t.id}' with criteria (`edit_criteria`); its executor may "
                                  f"CHALLENGE the packet meanwhile"}
        parent = self._graph.get_parent(task_id)
        if parent is None:
            return None                          # a root has no plan above it to admit it
        if not l2_gate_on():          # the Syntactic level gates the admission, not this ACCEPT (corner 9)
            return None
        if t is None or (str(t.assignee) != str(parent.assignee)
                         and not self.workforce.is_system_executor(t.assignee)):
            return None
        if _checked_by_contact(self._graph, t) and not _l0_holes(self._graph, parent):   # L2 only: the Syntactic level always runs (§9.9)
            return None
        gaps = _l2_undischarged(self._graph, parent)
        if gaps == []:
            return None
        if gaps is None and (holes := _l0_holes(self._graph, parent)):
            # no review runs over a plan with a Level-0 hole, so the repair comes first (critic r14)
            return {"parent_id": str(parent.id),
                    "why": "its plan has Level-0 holes since its admission, and no Level-2 review runs until they close: "
                           + "; ".join(f"{h.check_name}: {h.details}" for h in holes),
                    "opens_with": f"repair the split of '{parent.id}' by its re-admission (`decompose`; `list_holes` "
                                  f"names the holes), then review_decomposition('{parent.id}')"}
        return {"parent_id": str(parent.id),
                "why": ("no CURRENT Level-2 verdict covers its decomposition" if gaps is None else
                        f"the Level-2 review left findings open: {gaps}"),
                "opens_with": f"review_decomposition('{parent.id}')"}

    def is_seam(self, task) -> bool:
        """Is this node a delegation SEAM (§10.3) — a root, or Del(child) ≠ Del(parent)?

        Where independence is owed, and therefore where the verifier ≠ executor gate fires. The
        classification is the graph's (`Graph.is_public`); this is the engine's public way to ask it,
        so the surfaces that must agree with the machine do not each reach for a private attribute."""
        return self._graph.is_public(task)

    def stored_review_findings(self, task_id: TaskId) -> Optional[list[str]]:
        """The findings of the LAST stored Level-2 review, current or not.

        `open_l2_findings` answers about the gate — and returns None the moment an edit stales the
        verdict, which is the very moment a caller re-runs the check. For "what did the previous
        review say", the record is the answer."""
        raw = self._storage.get_critique(task_id)
        if not raw:
            return None
        try:
            rec = json.loads(raw)
        except (ValueError, json.JSONDecodeError):
            return None
        # A ROUND THAT MEASURED NOTHING IS NOT A BASELINE. A review gated out at Level 0 records no
        # findings, and comparing a later round against it reported eight genuinely closed findings as zero
        # closed (measured on the human door 2026-08-22); a round that read neither the plan nor the goal
        # counted a closing review as unproductive (critic round 8) and an unchanged one as progress (round
        # 9). The last MEASURING round's findings ride through it instead (`progress_baseline`).
        return progress_baseline(rec)

    def open_l2_findings(self, task_id: TaskId) -> Optional[list[str]]:
        """The Level-2 findings still open on this node's plan — `[]` discharged, `None` no current
        verdict. The EXACT strings `dispute_review_finding` accepts, so the read surface and the
        gate cannot drift apart about what is open (the tool layer used to reach into the graph for
        this itself)."""
        node = self._graph.get_task(task_id)
        return _l2_undischarged(self._graph, node) if node is not None else None

    def split_holes(self, task_id: TaskId) -> list:
        """The Syntactic holes of this node's own split (§9.5 Level 0) — what the plan gate names first."""
        node = self._graph.get_task(task_id)
        return _l0_holes(self._graph, node) if node is not None else []

    def decomposition_refuted(self, task_id: TaskId) -> Optional[str]:
        """Did contact refute this node's split — a standing FAIL on criteria its untouched children
        cover (the re-delivery gate's own question, asked as a predicate, not as a refused signal)."""
        task = self._graph.get_task(task_id)
        return self._redelivery_refusal(task) if task is not None else None

    def rejected_report(self, task_id: TaskId) -> Optional[dict]:
        """The last refused report on this node, or None. Evidence, not a verdict."""
        return ledger_read(self._storage, task_id, REJECTED_REPORT)

    def deliver_result(self, task_id: TaskId) -> Optional[str]:
        """The executor's own DELIVER report — where the work lives and how each criterion is
        claimed met. Stored because the validator reads it, and reachable from no door until now:
        the frontier tells an issuer to check "the deliverable" and nothing returned it."""
        return self._storage.get_deliver_result(task_id)

    def get_exec_verdict(self, task_id: TaskId) -> Optional[dict]:
        return self._graph.exec_verdict_record(task_id)

    #: the three counters that together identify WHICH delivery a record validated (`model.GENERATION`)
    VERDICT_GENERATION = GENERATION

    def in_rework(self, t: Task) -> bool:
        """Is this node's holder working against a FAIL on the packet version that stands?

        Not the same question as "is it in REWORKING": a challenge rejected there, or a block
        resolved, returns it to EXECUTING under the same version with the refusal still standing
        — and a packet or a directive keyed on the state label dropped the failed criteria at
        exactly that moment."""
        return (t.state in (State.EXECUTING, State.REWORKING)
                and failed_on_current_version(self.audit_log(t.id)))

    def current_exec_verdict(self, task_id: TaskId) -> Optional[dict]:
        """The stored verdict IF it validates the delivery that stands now, else None.

        One owner for "is this record current". `get_verdict` needed it to mark a stale record, and
        the frontier needs the same answer to know whether a VALIDATING node still needs validation or
        only a signature — and a frontier that did not ask kept saying "check the deliverable
        against criteria …" to an issuer whose validator had already reported, so the reader paid
        for a second validation or waited for one that had already arrived (measured on the human
        door 2026-08-22)."""
        t = self._graph.get_task(task_id)
        rec = self.get_exec_verdict(task_id)
        if t is None or rec is None:
            return None
        # A FAIL's OWN side effect is not evidence against it: the FAIL sent the node to REWORKING and
        # bumped its iteration, so the verdict CAUSING the current state would otherwise announce
        # itself as validating an earlier one. It stands until a new delivery is made.
        own_bump = (bool(rec.get("failed_criteria")) and self.in_rework(t)
                    and rec.get("iteration", 0) + 1 == t.iteration
                    and rec.get("reopens", 0) == t.reopens and rec.get("revisions", 0) == t.revisions)
        if own_bump:
            return rec
        return rec if _record_stands(self._graph, self._audit, t, rec) else None

    # === Audit API ===

    def audit_log(self, task_id: Optional[TaskId] = None) -> list[AuditEntry]:
        """The append-only signal log — the whole graph's, or one node's. This is the record Thm 11
        and Inv-7 rest on: the node's attributes are a projection of it, never the other way round."""
        return self._audit.get_entries(task_id)

    def log_position(self, task_id: TaskId, *, signal: Optional[Signal] = None,
                     new_state: Optional[State] = None) -> int:
        """Where the last accepted entry on this node matching stands in the log, or -1 — for "did this
        happen after that", which the log's order answers and a clock does not (`AuditLog.last_at`)."""
        return self._audit.last_at(task_id, signal=signal, new_state=new_state)

    def _authoring_digest(self, task_id: TaskId) -> Optional[str]:
        """The procedure digest of the contract this node was FIRST assigned — the pre-registered
        one. Read off the append-only log (every ASSIGN stores its spec), so nothing is duplicated."""
        for e in self._audit.get_entries(task_id):
            if e.signal != Signal.ASSIGN or e.rejected or not e.spec:
                continue
            try:
                d = json.loads(e.spec)
            except (ValueError, TypeError):
                return None
            first = self._authored_register(task_id)
            return claim_digest(Spec(
                d.get("description", ""),
                tuple(Criteria(c.get("name", ""), c.get("description", ""),
                               check=tuple(Probe.of(p) for p in (c.get("check") or ())))
                      for c in (d.get("criteria") or ())),
                tuple(AcceptedRiskItem(str(n.get("item", "") if isinstance(n, dict) else n))
                      for n in (d.get("accepted_risks") or ())),
                scope=tuple(str(x) for x in (d.get("scope") or ()))),
                first)
        return None

    def _authored_register(self, task_id: TaskId) -> Optional[Register]:
        """The split register as the split was AUTHORED: its first admitted version, whenever the split came — a split
        deferred past consent is authored then (§11.5, "at or after the node's issue"), not narrowed (critic r4 over
        A-F6); None where the split has none of its own (the packet's, as authored, is the baseline)."""
        first = self.register_versions(task_id)[:1]
        return (Register(tuple(AcceptedRiskItem.of(n) for n in first[0]["items"]), tuple(first[0].get("components", ())))
                if first else None)

    def record_replacement(self, task_id: TaskId, dropped: list) -> None:
        """`task_id` was admitted to stand in for the `dropped` children of the same act (`carried_work`)."""
        self._storage.store_critique(replaces_key(task_id),
                                     json.dumps(sorted({*self.replaces(task_id), *map(str, dropped)})))

    def replaces(self, task_id: TaskId) -> list[str]:
        """The dropped children this node stands in for."""
        return json.loads(self._storage.get_critique(replaces_key(task_id)) or "[]")

    def carried_work(self, task_id: TaskId) -> list[Task]:
        """The work a node carries on from what it replaced (§12.16 (ii): work-keeping): each child it stands in for,
        whatever that child carried in turn, and every PASSed node of their subtrees — a dropped child's committed work
        and its DONE parts, which the cancellation of its subtree would otherwise leave behind."""
        out, todo = {}, list(self.replaces(task_id))
        while todo:
            t = self._graph.get_task(TaskId(todo.pop()))
            if t is None or str(t.id) in out:
                continue
            out[str(t.id)] = t
            todo += self.replaces(t.id)
            out.update({str(d.id): d for d in self._graph.subtree(t.id) if d.state == State.DONE})
        return list(out.values())

    def register_versions(self, task_id: TaskId) -> list[dict]:
        """Every version of the node's split register as admitted — {at, by, log_at, items, components} (Thm 11)."""
        return json.loads(self._storage.get_critique(register_log_key(task_id)) or "[]")

    def regression_probes(self, task_id: TaskId) -> dict:
        """{criterion: [probes that have REFUTED it on this node]} — the set every later PASS must re-run. Grows at
        each verdict that refutes something; shrinks only by its issuer's ruling in force (`findings`)."""
        task = self._graph.get_task(task_id)
        return standing_regression(self._storage, self._audit.get_entries(task_id), task) if task is not None else {}

    def retired_findings(self, task_id: TaskId) -> list[dict]:
        """The rulings in force on this node — each finding its issuer's ACCEPT_CHALLENGE retired, while its criterion
        reads as that act left it: {criterion, id, command, by, at, why, text} (`findings.rulings`)."""
        return standing_rulings(self._storage, self._audit.get_entries(task_id), task_id)

    def carry_findings(self, to_id: TaskId, from_id: TaskId, onto: dict) -> int:
        """The findings standing on `from_id` handed to `to_id`, which replaces it, each under the names its criterion
        has there (`onto`: name → [names], else its own) — re-keyed, its id with it, `carried_from` naming where it
        stood. Merged out of a cycle, root.pp's 254 standing findings went nowhere and the merged child began with none
        (critic over 28bd5e7); one on a seam the merge dropped went under a name the child has not, and gated nothing
        (critic over 868ede5): what contact found is the work too. Returns how many."""
        moved = {}
        for name, ps in self.regression_probes(from_id).items():
            for to in onto.get(name) or [name]:
                for p in ps:
                    was = str(p.get("as_run") or p.get("command") or "")
                    run = was.replace(f"{{inputs:{name}#", f"{{inputs:{to}#")
                    # its id moves with its criterion and keeps what it was filed over (`finding_id`), the files it
                    # read then being gone now; a run re-pointed onto renamed inputs is another command
                    pid = (f"{' '.join(to.split())}#{str(p.get('id')).rsplit('#', 1)[-1]}" if run == was
                           else probe_id(to, {"command": run}))
                    moved.setdefault(to, []).append({**p, "id": pid, "as_run": run,
                                                     "carried_from": f"{from_id}:{p.get('id')}"})
        if moved:
            ledger_write(self._storage, to_id, REGRESSION, merge_regression(self._stored_regression(to_id), moved))
        return sum(map(len, moved.values()))

    def _stored_regression(self, task_id: TaskId) -> dict:
        """The regression set as stored — every refutation ever recorded; what grows it merges into THIS."""
        return ledger_read(self._storage, task_id, REGRESSION, {})

    def _rewritten_after_refutation(self, task_id: TaskId, log, now: dict, crit, version) -> list:
        """Criteria whose version now differs from ANY version of them that was refuted.

        A later re-ASSIGN that copies a criterion unchanged is no rewrite. The refuted versions come
        from every FAIL verdict, which keeps what it validated when it is written (a verdict alone sends
        no signal, and a reviewer's FAIL may carry no probe), and from the FSM FAILs in the log, read
        against the version in force at the last DELIVER — the log is the order (Inv-7), a clock may tie.
        """
        refuted = refuted_versions(self._storage, task_id)
        in_force: dict = {}
        validated: dict = {}
        for e in log:
            if e.signal in VERSION_INSTALLING and not e.rejected and e.spec:
                in_force = crit(e.spec)
            elif e.signal == Signal.DELIVER and not e.rejected:
                validated = dict(in_force)
            elif e.signal == Signal.FAIL and not e.rejected:
                for c in e.failed_criteria or ():
                    if c in validated:
                        refuted.setdefault(c, []).append(version(validated[c]))
        return sorted(n for n, vs in refuted.items()
                      if n in now and any(v != version(now[n]) for v in vs))

    def claim_drift(self, task_id: TaskId) -> dict:
        """How this node's CLAIM moved between the contract it was authored with and the one it
        closed on — criterion by criterion, with the engine's own revision reasons beside it.

        The author's rule, and the reason this is a RECORD and not a prohibition: an agent may
        sharpen a criterion, add a node, write down what it found — it must never leave the plan
        worse ("weakly better"). Locking the contract would make the run artificial, because a
        criterion CAN turn out to be a false mock and only contact reveals it. So nothing here
        refuses anything; it makes the movement readable, which is what turns "the claim narrowed
        before the work" from an anecdote into a measurement. Measured on `c_compiler`
        (2026-09-19/20): of a 0.184 gap between a bare agent and the graph, ≈0.074 was scope the
        executor-as-issuer had cut BEFORE coding — visible only because someone read the register
        by hand at call #14.

        Reads the append-only log (Inv-1/Inv-7: every re-ASSIGN appends the version it installed),
        so it needs no second copy of the contract and cannot fall out of step with one.
        """
        _log = self._audit.get_entries(task_id)
        entries = [e for e in _log if e.signal in VERSION_INSTALLING and not e.rejected and e.spec]
        if not entries:
            return {"task_id": str(task_id), "versions": 0,
                    "note": "no ASSIGN with a recorded contract — nothing to compare"}

        def _crit(raw: str) -> dict:
            try:
                d = json.loads(raw)
            except (ValueError, TypeError):
                return {}
            return {c.get("name"): c for c in (d.get("criteria") or ()) if c.get("name")}

        def _reg(raw: str) -> tuple[set, set]:
            """(accepted risks, scope) as a version declared them."""
            try:
                d = json.loads(raw)
            except (ValueError, TypeError):
                return set(), set()
            risks = {str(n.get("item", "") if isinstance(n, dict) else n).strip()
                     for n in (d.get("accepted_risks") or ())}
            return {r for r in risks if r}, {str(x).strip() for x in (d.get("scope") or ()) if str(x).strip()}

        def _challenged_for(e) -> str:
            """An accepted challenge's revision is moved by the challenge it answers — its reason is that one."""
            if e.signal != Signal.ACCEPT_CHALLENGE:
                return ""
            before = [x for x in _log if x.signal == Signal.CHALLENGE and not x.rejected and x.timestamp <= e.timestamp]
            return f"accepted challenge: {before[-1].reason}" if before and before[-1].reason else "accepted challenge"

        first, last = _crit(entries[0].spec), _crit(entries[-1].spec)
        task = self._graph.get_task(task_id)
        now = {c.name: {"description": c.description,
                        "check": [p.to_dict() for p in (c.check or ())]}
               for c in (task.spec.criteria if task is not None else ())} or last
        added = sorted(set(now) - set(first))
        dropped = sorted(set(first) - set(now))
        reworded = sorted(n for n in set(first) & set(now)
                          if (first[n].get("description") or "") != (now[n].get("description") or ""))
        def _version(c: Optional[dict]):
            return None if c is None else criterion_version(c.get("description"), c.get("check"))

        reprobed = sorted(n for n in set(first) & set(now)
                          if _version(first[n])[1] != _version(now[n])[1])
        # THE REGISTER IS HALF THE CLAIM, and it was missing from this report. A plan narrows as
        # readily by excluding as by dropping a criterion — more readily, because an exclusion
        # looks like diligence. Measured on `c_compiler` (2026-09-20/21): the criteria and their
        # procedures never moved, so every surface said the claim stood, while the register grew
        # from four entries to ten AFTER the work began — six of the divergences an independent
        # corpus later found were contract requirements filed there as missing.
        # The author's rule is "weakly better": an agent may sharpen and record, never leave the
        # plan worse — and the answer to a narrowing is a RECORD, so the record has to contain it.
        # both carriers at both ends — the packet's pre-fill (its issuer's) and the split's register (its decomposer's,
        # as first admitted): one read at authoring and the other now reported an untouched pre-fill as dropped
        _risks0, _scope0 = _reg(entries[0].spec)
        _risks0 |= {n.item for n in (self._authored_register(task_id) or Register()).items}
        _risksN, _scopeN = ((({n.item for n in task.spec.accepted_risks + register_of(task).items}, set(task.spec.scope))
                             if task is not None else _reg(entries[-1].spec)))
        # …AND A CRITERION REWRITTEN AFTER IT WAS REFUTED. Whether new wording is sharper or
        # looser is not decidable from structure, so it cannot be reported as "not narrowed".
        # Measured on `json_parser` (2026-09-21): a validator FAILed `error_contract_consistency`,
        # the issuer rewrote it as a spec defect from "ValueError" to "TypeError or ValueError",
        # and this report said `narrowed: false`. Such a criterion makes the answer ⊥, not a green.
        _moved_after = self._rewritten_after_refutation(task_id, _log, now, _crit, _version)
        _structural = bool((_risksN - _risks0) or (_scopeN - _scope0) or (set(first) - set(now)))
        return {
            "task_id": str(task_id),
            "versions": len(entries),
            # narrowing: what the plan stopped promising after it was authored
            "risks_added": sorted(_risksN - _risks0),
            "scope_added": sorted(_scopeN - _scope0),
            "reworded_after_refutation": _moved_after,
            # …AND THE CRITERIA WHOSE REFUTATIONS ITS ISSUER RULED OUT: a PASS over them no longer re-runs what once
            # failed them — the claim moved after a refutation as surely as by a rewording, so `narrowed` reads ⊥ too
            "retired_after_refutation": (_retired := sorted({r["criterion"] for r in self.retired_findings(task_id)})),
            "narrowed": True if _structural else (None if _moved_after or _retired else False),
            "risks_dropped": sorted(_risks0 - _risksN),
            "authored": {"at": entries[0].timestamp.isoformat(sep=" ", timespec="seconds"),
                         "criteria": sorted(first)},
            "now": {"criteria": sorted(now)},
            "added": added, "dropped": dropped,
            "reworded": reworded, "procedure_changed": reprobed,
            # The engine's own words for each move, in order — a revision that names no reason is
            # itself the finding (§15.4 splits spec_defect from scope_expansion for exactly this).
            "revisions": [{"at": e.timestamp.isoformat(sep=" ", timespec="seconds"),
                           "by": str(e.source or ""), "reason": e.reason or _challenged_for(e) or "(none recorded)"}
                          for e in entries[1:]],
            "accepted_risks_now": [n.item for n in (register_of(task).items if task else ())],
            "scope_now": list(task.spec.scope) if task is not None else [],
            "retired_findings": self.retired_findings(task_id),
        }

    # === Decomposition API ===

    def decompose_task(
        self,
        parent_id: TaskId,
        children: list[tuple],
        criterion_mappings: list[CriterionMapping] | None = None,
        max_iterations: int | None = None,
        register: Optional[Register] = None,
        drops: tuple = (),
        contract: Optional[Spec] = None,
    ) -> list[Task]:
        """A split's admission (§11.5) — `admission.admit`, the one act every door performs. Each child is
        (task_id, spec, assignee[, deadline]); `criterion_mappings` given = the node's FULL coverage, None adds to
        it; `drops` — live children this re-admission leaves out; `contract` — the node's own contract re-authored
        with its split by its issuer, revised only once the act is admitted."""
        covers = {}
        for m in (criterion_mappings or []):
            covers.setdefault(str(m.child_id), []).append(m.criterion_name)
        self._admit(parent_id, children, covers, replace=criterion_mappings is not None, register=register,
                    drops=drops, contract=contract, max_iterations=max_iterations)
        return [self._graph.get_task(TaskId(str(c[0]))) for c in children]

    def _admit(self, parent_id, children, covers, **act):
        """The engine's hands for the act: its signals, its issuer's revision, its R′ gate, its log."""
        return _admit(self._graph, self._storage, lambda: len(self._audit), parent_id, children, covers,
                      send=self.send_signal_sync, reopen_refusal=self.reopen_refusal, check=self._validate,
                      revise=lambda c: self._revise(TaskId(str(parent_id)), c,
                                                    self._graph.issuer_of(TaskId(str(parent_id)))), **act)

    # === Dependency API ===

    def add_dependency(self, from_id: TaskId, to_id: TaskId, discovered: bool = False, glue: str = "",
                       check: tuple = ()) -> None:
        """Record a dependency: to_id depends on from_id's output.

        DECLARED (discovered=False): Dep is **criteria-content** (§2) — recorded as a criterion on the
        CONSUMER (to_id) referencing from_id (glue = its description), applied via REVISE (logged, no
        bypass). A cycle is rejected (CHECK-2's Dep clause / FM-5). The DepEdge is then DERIVED (graph.dep_edges()).
        DISCOVERED (discovered=True, surfaced via BLOCK): runtime provenance — stored as an edge, even if
        cyclic (a Dep cycle IS the FM-5 finding to surface, not hide). Affects q_Dep.
        """
        if discovered:
            # Test/offline convenience ONLY. The canonical runtime path for a discovered Dep is the BLOCK
            # signal carrying `blocker_task_id` (→ RECORD_DEP effect, provisional; RESOLVE_BLOCK adjudicates —
            # §11.3/§15.5, v3.7). This direct write stays off every transport surface (tools/api/mcp/cli pass
            # discovered=False).
            self._storage.add_dep_edge(DepEdge(from_id, to_id, True, glue))
            self._recompute_seam_parents(from_id, to_id)
            return
        to = self._graph.get_task(to_id)
        if to is None:
            raise ValueError(f"consumer {to_id} not found")
        if why := dep_cycle_closed(self._graph, to_id, to.spec.criteria + (Criteria("dep", "", depends_on=from_id),)):
            raise ValueError(why)
        if not any(c.depends_on == from_id for c in to.spec.criteria):  # idempotent
            dep_crit = Criteria(name=f"dep__{from_id}", description=glue, depends_on=from_id,
                                check=tuple(check or ()))
            # `scope` carried EXPLICITLY. Declaring a dependency desugars to a re-author of the
            # consumer, and this rebuilt its Spec positionally without the scope field — so the
            # node's declared boundary ("what this goal deliberately does NOT include", §9.2)
            # vanished the moment anyone drew an edge into it. Silent, and invisible in the diff:
            # the field simply defaulted to empty.
            new_spec = dataclasses.replace(to.spec, criteria=to.spec.criteria + (dep_crit,))
            self._revise(to_id, new_spec, self._graph.issuer_of(to_id))
        self._recompute_seam_parents(from_id, to_id)

    def remove_dependency(self, from_id: TaskId, to_id: TaskId) -> None:
        """Drop a dependency. Declared → remove the consumer's dep criterion (re-author); a stored (discovered)
        record for the pair is CLOSED: it stops asking and leaves E_Dep, and the discovery that was made stays in
        q_Dep's population — only an adjudication refuting it takes it out (§15.5)."""
        to = self._graph.get_task(to_id)
        if to is not None and any(c.depends_on == from_id for c in to.spec.criteria):
            new_crits = tuple(c for c in to.spec.criteria if c.depends_on != from_id)
            new_spec = dataclasses.replace(to.spec, criteria=new_crits)
            self._revise(to_id, new_spec, self._graph.issuer_of(to_id), severing=(from_id,))
        for e in self._storage.get_dep_edges():
            if str(e.from_id) == str(from_id) and str(e.to_id) == str(to_id) and not e.closed:
                self._storage.remove_dep_edge(from_id, to_id)
                self._storage.add_dep_edge(dataclasses.replace(e, provisional=False, closed=True))
        self._recompute_seam_parents(from_id, to_id)


    def map_criterion(self, parent_id: TaskId, covers: dict) -> Task:
        """Bind EXISTING children to the parent's criteria (`covers`: child → criteria) — a re-admission of the
        parent's split (§11.5), the battery over the split as it will then stand, logged as the admission it is.
        The mapping is the split's (§2.4), not a field of a child's packet (§10.1), so no child is revised: it was a
        re-ASSIGN of the child, which re-offered work in progress and was refused on a delivered or passed one
        (critic r15)."""
        parent = self._graph.get_task(parent_id)
        if parent is None:
            raise ValueError(f"parent {parent_id} not found")
        active = {str(k.id) for k in self._graph.get_active_children(parent_id)}
        names = {c.name for c in parent.spec.criteria}
        for child_id, crits in covers.items():
            if str(child_id) not in active:
                raise ValueError(f"{child_id} is not an active child of {parent_id}")
            if bad := [c for c in crits if c not in names]:
                raise ValueError(f"no criterion {', '.join(map(repr, bad))} on parent {parent_id}")
        self._admit(parent_id, [], {str(k): tuple(v) for k, v in covers.items()})
        # the trail a person reads says what happened: coverage bound by the split's re-admission, no contract revised
        self.emit_info("admission", f"{parent_id}: coverage bound — " + "; ".join(
            f"{', '.join(v)} → {k}" for k, v in covers.items())
            + " (the split re-admitted; every child's contract as it was)")
        return self._graph.get_task(parent_id)


    def users_dispute(self, task_id: TaskId) -> list[str]:
        """The findings a CHALLENGE at an AUTO root asks to rule out of the user's goal — a question only the user, the
        root's issuer, answers (§10.1): the system makes no move on it, and the clock bounds his silence (Inv-5).
        Answered by the system it could only accept without a ruling, and the finding, still demanded, came back
        round after round until the rework bound cancelled the root (critic over 3982699). [] where it is not one."""
        t = self._graph.get_task(task_id)
        if t is None or t.state != State.CHALLENGED or not is_auto_root(self._graph, t):
            return []
        return disputed_findings(self._storage, self._audit.get_entries(task_id), t)

    def challenge_reason(self, task_id: TaskId) -> Optional[str]:
        """The reason the standing CHALLENGE carried — the issuer cannot answer what he cannot read."""
        for e in reversed(self.audit_log(task_id)):
            if e.rejected:
                continue
            if e.signal in (Signal.ACCEPT_CHALLENGE, Signal.REJECT_CHALLENGE, Signal.ASSIGN):
                return None                      # answered or superseded by a new version (Inv-1)
            if e.signal == Signal.CHALLENGE:
                return e.reason
        return None


    def _revise(self, task_id: TaskId, new_spec: Spec, agent: AgentId,
                new_assignee: Optional[AgentId] = None, covers: tuple = (),
                reason=None, severing: tuple = (), deadline=None,
                max_iterations: Optional[int] = None,
                block_sources: tuple = (), block_refuted: bool = False) -> Task:
        """Canon v3.7 Inv-1 (§12.3): a spec/Del change = REVISION — ONE re-ASSIGN under the SAME id → OFFERED,
        never an in-place mutation and never the CANCEL signal (revision ≠ abandonment; no CANCELLING pass,
        no cascade). The id persists (Inv-7) so references (the parent's mapping, dependents' depends_on)
        stay valid; the superseded contract lives in the append-only log. `agent` must be the issuer
        (ASSIGN is an issuer signal → FSM-validated). Returns the revised node (back in OFFERED —
        the executor must re-ACCEPT)."""
        old = self._graph.get_task(task_id)
        if old is None:
            raise ValueError(f"task {task_id} not found")
        # …AND A REVISION IS AN ASSIGN. Admitting the first packet on a pinned procedure and letting
        # the next version strip it would make the gate a formality: the same contract, one act
        # later, deciding nothing.
        refuse_a_contract_that_pins_nothing(self._graph, task_id, new_spec)
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
        new_spec = with_its_seams(old.spec, new_spec, severing)
        # Snapshot the CONTENT before the signal: ASSIGN applies the new spec onto the same live
        # object, so reading `old.spec` afterwards compares the new contract with itself.
        _before = (old.spec.description, old.spec.criteria, old.spec.accepted_risks,
                   old.spec.scope, old.spec.name)
        _old_parent = old.parent_id
        a = self.send_signal_sync(SignalData(
            signal=Signal.ASSIGN, task_id=task_id, spec=new_spec, source=agent,
            assignee=new_assignee or old.assignee, covers=tuple(covers),
            deadline=deadline,               # None = keep the one the node has (Inv-1)
            # …and the REWORKING bound, the packet field an escalated node's issuer most often means:
            # exhausting the attempts reads two ways, and "the forecast was short" is answered by
            # raising it. None = keep.
            max_iterations=max_iterations,
            blocker_task_ids=tuple(TaskId(str(b)) for b in block_sources), external=block_refuted,
            revision_reason=reason))
        if a is None or a.rejected:
            # WHICH of the three, said by name. The refusal printed the node's state and then a
            # disjunction asserting it was in states it demonstrably was not — measured 2026-08-20:
            # `state=State.OFFERED` followed by "the node is in OVERDUE/CANCELLING/ESCALATED … or
            # the agent is not its issuer", with a Python repr leaked into it. Each branch is
            # cheap to ask, and each has a different answer.
            st = self._graph.get_state(task_id)
            cur = self._graph.get_task(task_id)
            issuer = self._graph.issuer_of(task_id)
            _rejected = next((a for a in reversed(self.audit_log(task_id)[-4:]) if a.rejected), None)
            _said = self.refusal_of(task_id, Signal.ASSIGN, _rejected).refusal if _rejected else None
            if st == State.CANCELLING:
                why = ("a node in CANCELLING takes no revision (§12.3). "
                       "Let it settle first — the cancellation handshake decides.")
            elif str(agent) != str(issuer):
                why = (f"'{agent}' is not the issuer of {task_id} — its issuer is '{issuer}' (the "
                       f"parent's Del, or the node's own for a root), and a contract is revised by "
                       f"the side that set it (§11.2).")
            elif _said is not None and _said.kind == "rule":
                why = _said.why       # a rule above the FSM refused, in its own words — not a guess from the state
            elif st is not None and st.name in ("DONE", "ABANDONED"):
                why = (f"{task_id} is {st.name} and the R′ finality-gate refused it: it is either "
                       f"CONSUMED (the graph built on this result — then it is locked for good and "
                       f"the repair is re-decomposition) or out of reopens "
                       f"({cur.reopens}/{cur.max_reopens} spent). "
                       f"`reopen` names which.")
            else:
                # …AND ONLY IF IT REALLY DID. This sentence was printed whenever the node had not
                # moved, whatever the reason — including a step that RAISED and was dropped, which
                # is a fact about a malformed value and not about the FSM. A tester read it as the
                # plan-repair verbs being closed in the states nodes actually occupy and worked
                # around a wall that was not there (agent door, 2026-09-02). §12.4 admits ASSIGN
                # from every reassignable state, so "the FSM refused" is a claim that has to be
                # checked against the record before it is made.
                why = (_said.why if _said is not None else
                       (f"the revision did not take, and the FSM recorded no refusal — the step was "
                        f"dropped before it reached {task_id} (the server log carries the reason). "
                        f"§12.4 admits ASSIGN from {st.name if st else 'this state'}, so this is not "
                        f"a rule refusing you: read the log, or re-read the node and try again."))
            raise ValueError(f"revise refused on {task_id}: {why}")
        # Did the CONTRACT change, or only who holds it? A delegation carries the same spec and a
        # new Del; the parent's Level-2 claim is about the children's criteria, not their owners.
        # A revision is the answer to a dispute — the node goes back to OFFERED under a contract its
        # executor gets to take or refuse afresh, so the recorded dispute is settled by construction.
        self.parking.uncontest(task_id)
        content_changed = (new_spec.description, new_spec.criteria, new_spec.accepted_risks,
                           new_spec.scope, new_spec.name) != _before or bool(covers)
        self._recompute_checks(task_id, stale_review=content_changed)   # kept its subtree → refresh
        if _old_parent:
            self._recompute_checks(_old_parent, stale_review=content_changed)
        return self._graph.get_task(task_id)

    def _recompute_seam_parents(self, from_id: TaskId, to_id: TaskId) -> None:
        """A Dep change affects the checks (DAG/deadlines/anti-mock) of every node whose SUBTREE
        contains the seam — so every ancestor of both endpoints, not the direct parents alone.

        CHECK-2 and CHECK-3 quantify over the Dep pairs inside a node's subtree (`dep_scope`), and a
        seam between two BRANCHES is inside no direct parent's population — it is inside their common
        ancestor's. Refreshing the parents only left that ancestor's CACHE saying `no dependency
        edges` while the live gate refused execution over the very violation the cache called absent:
        two doors, one node, opposite answers, which is the class this fix exists to remove.
        """
        stale = set()
        for nid in (from_id, to_id):
            t = self._graph.get_task(nid)
            while t is not None and t.parent_id is not None:
                if str(t.parent_id) in stale:
                    break                      # this chain is already marked, and so is its tail
                stale.add(str(t.parent_id))
                t = self._graph.get_task(t.parent_id)
        for node_id in stale:
            self._recompute_checks(TaskId(node_id))

    def get_dependencies(self) -> list[DepEdge]:
        """Every Dep record that still says something, declared and discovered alike (a record closed unanswered
        is left out: it asks and waits on nothing — `q_Dep` counts it, `Graph.dep_edges(closed=True)`)."""
        return self._graph.dep_edges()

    def adopted_dependencies(self) -> list[DepEdge]:
        """E_Dep — what the execution order reads: declared edges and confirmed discoveries (§11.3)."""
        return self._graph.dep_edges(adopted=True)

    @staticmethod
    def _refutation_line(e) -> str:
        return (f"`{e.to_id}` needs `{e.from_id}` ({'its BLOCK, not yet answered' if e.provisional else 'confirmed'}), "
                f"while `{e.from_id}` cannot finish before `{e.to_id}` does — through the plan's seams, another "
                f"block, or its own children")

    def _asks_the_split(self, e) -> bool:
        """A record on a cycle of waits is its blocked node's issuer's to answer (the BLOCK is his, Inv-8) — until
        it is confirmed, or raised again after a block of the same contract was answered: then the executor holds
        to it against an answer, and the plan's order, not the report, is what stands refuted."""
        return not e.provisional or resolved_on_current_version(self.audit_log(TaskId(str(e.to_id))))

    def block_is_the_splits(self, task_id: TaskId) -> bool:
        """Is this node's standing block now its split's question (`_asks_the_split`) rather than its issuer's?"""
        # …and a split exists to ask: a root blocked on itself has none above it, and its own issuer keeps it
        return any(str(e.to_id) == str(task_id) and self._asks_the_split(e) and self._refuted_split(e) is not None
                   for e in dep_order_refutations(self._graph))

    def dep_order_refuted(self, task_id: TaskId) -> Optional[str]:
        """Did contact refute the ORDER of this node's split — a discovery on a cycle of waits that is confirmed,
        or held to after an answer (§15.5)? The split's issuer's: re-decomposition is the one repair. A block
        answered by nobody yet is its own node's issuer's (`order_refuted_by`)."""
        return "; ".join(self._refutation_line(e) + " — the plan's order is refuted by contact; reshape the split"
                         for e in self._split_refutations(task_id)) or None

    def _split_refutations(self, task_id: TaskId) -> list:
        """The refuted waits whose repair is this node's split's (`dep_order_refuted`)."""
        return [e for e in dep_order_refutations(self._graph)
                if self._asks_the_split(e) and str(self._refuted_split(e)) == str(task_id)]

    def dep_order_cycle_children(self, task_id: TaskId) -> list[list[str]]:
        """The children of this node each of its split's refuted cycles runs through (`cycle_children`)."""
        return cycle_children(self._graph, task_id, self._split_refutations(task_id))

    def block_clears_itself(self, t: Task) -> bool:
        """Will this BLOCK end with no issuer move — the dispatcher confirming it once its producers pass? Only
        where it names live producers, none of which waits on it (that is the split's order refuted,
        `order_refuted_by`), and one of them is still to finish, or finished after the block, or the block is
        the first on this contract. A repeat block on producers already passed was confirmed again and again,
        each time a paid executor run that blocked once more (critic, 2026-09-27): that block is its issuer's."""
        ins = [e for e in self._graph.dep_edges() if str(e.to_id) == str(t.id)]
        prods = [p for e in ins if (p := self._graph.get_task(TaskId(str(e.from_id)))) is not None]
        if (not prods or any(p.state in (State.CANCELLING, State.ABANDONED) for p in prods)
                or self.order_refuted_by(t.id)):
            return False
        if any(p.state != State.DONE for p in prods):
            return True
        at = self.log_position(t.id, new_state=State.BLOCKED)
        return (any(self.log_position(p.id, new_state=State.DONE) > at for p in prods)
                or (any(e.provisional for e in ins) and not resolved_on_current_version(self.audit_log(t.id))))

    def _refuted_split(self, e) -> Optional[TaskId]:
        """Whose split a refuted wait belongs to: the lowest node both ends sit under — or, where the BLOCK named
        its own ancestor or itself, the blocked node's parent, whose split put it there."""
        def _chain(tid: object) -> list[str]:
            chain, t = [], self._graph.get_task(TaskId(str(tid)))
            while t is not None:
                chain.append(str(t.id))
                t = self._graph.get_task(t.parent_id) if t.parent_id else None
            return chain
        above_consumer = _chain(e.to_id)
        common = next((a for a in _chain(e.from_id) if a in above_consumer), None)
        if common is None or common == str(e.from_id):
            consumer = self._graph.get_task(TaskId(str(e.to_id)))
            return consumer.parent_id if consumer is not None else None
        return TaskId(common)

    def order_refuted_by(self, task_id: TaskId) -> Optional[str]:
        """What this node's own BLOCK names that cannot finish before it, or None. No wait ends it: its issuer
        answers the block (refutes the record, re-issues, closes), or its split's issuer reshapes the split."""
        return "; ".join(self._refutation_line(e) for e in dep_order_refutations(self._graph)
                         if str(e.to_id) == str(task_id)) or None

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

    # === Actions API (per-role affordances, §11.2) ===

    def nodes_with_a_refused_report(self) -> list[str]:
        """Nodes where a validator ran, reported, and the engine refused the report as ⊥ (§2.3).

        NOT a contradiction and NOT a blocker: ⊥ is not fail, and treating it as one is the precise
        error the canon names. But it must be VISIBLE where completion is announced — measured on
        the HTTP door 2026-09-02, an instrument returned ⊥ on a root that had closed by hand
        forty-six seconds earlier, and `next_steps` went on answering "the goal is met" with nothing
        anywhere saying a validator had tried and failed to decide it.
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
        a-priori approximation (§9.9) and the real Level-2 verdict is contact's. What it does is
        stop the two surfaces from disagreeing in silence.
        """
        return [str(t.id) for t in self._within(root_id)
                if settled_positive(t) and (self.open_l2_findings(t.id) or [])]

    def _within(self, root_id: Optional[TaskId] = None) -> list:
        """The nodes a question scoped to `root_id` is about: that node and its subtree, else all.

        The id-prefix convention was spelled out at four call sites, which is four chances for one
        of them to scope differently from the rest — the exact shape of "a rule that holds at one
        door and not at the next".

        …AND THE SUBTREE IS THE EDGES, not the spelling. Scoping by the `root.child` prefix is true
        of graphs `auto_decompose` builds and false of every graph built by hand, where a person
        names a node `parser` and the engine records its parent perfectly well. Those graphs then
        fell out of every scoped question silently: probed 2026-09-07, a child accepted by the clock
        under `root` was absent from the scoped list and present in the unscoped one. The prefix is
        kept as well — an id that spells its ancestry still answers, even before its parent edge
        exists — but the relation the graph actually holds is what decides.
        """
        tasks = self.all_tasks()
        if root_id is None:
            return tasks
        by_parent, seen = {}, {str(root_id)}
        for t in tasks:
            by_parent.setdefault(str(t.parent_id), []).append(t)
        frontier = [str(root_id)]
        while frontier:
            for kid in by_parent.get(frontier.pop(), ()):
                if str(kid.id) not in seen:
                    seen.add(str(kid.id))
                    frontier.append(str(kid.id))
        return [t for t in tasks
                if str(t.id) in seen or str(t.id).startswith(f"{root_id}.")]

    def execution_admitted(self, task_id: TaskId) -> bool:
        """May this node's children start? — the gate's own answer, for the surfaces that display it.

        On the facade rather than reachable through `_graph`, because a door that reads the engine's
        insides to re-derive a rule is how the three spellings of this question came about in the
        first place (§11.5; probed 2026-09-07 — two of them called a ⊥ review "admitted" while this
        gate was refusing the child in the same second).
        """
        return _execution_admitted(self._graph, self._graph.get_task(task_id))

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
        t = self._graph.get_task(task_id)
        if t is None or not settled_positive(t):
            return None
        rec = self.get_exec_verdict(task_id) or {}
        displaced = self.overruled_verdict(task_id) or {}
        return {
            # by_hand / self / instrument / none — §10.3's three weights of evidence
            "provenance": self.verdict_provenance(task_id),
            "by_hand": bool(rec.get("by_hand")),
            # a hand verdict that replaced an instrument's OPPOSITE one on the same delivery
            "overruled": bool(displaced and not displaced.get("by_hand") and rec.get("by_hand")),
            "overruled_verdict": (str(displaced.get("verdict")) if displaced else None),
            # standing at PASS while its own current record says FAIL — a green that is not green
            "refuted": pass_was_refuted(self._graph, t),
            # CLOSED BY THE CLOCK, not by anyone's verdict. v4.0 routed a timed-out VALIDATING to
            # DONE(auto_pass) and v4.1 removed it (§16.14) — the clock, answering for a silent party,
            # invents no verdict — so no route produces this any more and what the field reads is a
            # row written by an older build. It stays visible for exactly that reason: a parent's
            # conjunction may still stand on such a child, and an acceptance nobody made is the
            # silent half of a weaker conjunct unless every surface can say which kind of DONE it is
            # looking at.
            "auto_accepted": t.done_reason is DoneReason.AUTO_PASS,
            "validator": rec.get("validator"),
            # WHAT THE CLOSURE ACTUALLY REACHED — the honest half, said at the close rather than
            # left to be inferred. A node closes on the procedure its contract pinned plus whatever
            # the validation went on to explore; everything outside that is UNCHECKED, and a criterion
            # can be decidable and still insensitive to a real divergence. That residue is the FM-3
            # boundary (Ch. 20, §15.7 — no structural check guards it), and naming it is the only
            # honest thing the system can do with it. Measured on `c_compiler`: a root closed PASS
            # by an independent validator, and 205 probes written from the same contract found 34 real
            # divergences in the tree it closed over.
            "checked_by": {
                "procedure_digest": rec.get("procedure_digest"),
                # …AND THE AUTHORING ONE BESIDE IT. A contract narrowed mid-run closes green and
                # the narrowing is visible only to someone who pulls `claim_drift` by hand — which
                # is exactly how the 0.074 of scope the executor-as-issuer cut on `c_compiler` was
                # found: by hand, at call #14. Two digests side by side make it a glance.
                # The WHOLE claim, not the procedures alone: a claim narrows through its risk
                # register as readily as through its checks, and reading one as the other is a
                # false green (measured on `c_compiler`, where the register grew from four
                # entries to ten after the work began and the procedures never moved).
                "authoring_digest": (_auth := self._authoring_digest(task_id)),
                "claim_digest": (_now := claim_digest(t.spec, register_of(t))),
                "claim_moved_since_authoring": bool(_auth and _auth != _now),
                # …AND WHICH WAY IT MOVED, on the node itself. A flag that says "the claim moved"
                # sends the reader to another verb; a green node is read where it is, and the
                # movement that matters is the one that made passing easier. So the exclusions
                # added after authoring are named here, beside the verdict they qualify.
                "narrowed_after_authoring": ({
                    k: v for k, v in (self.claim_drift(task_id) or {}).items()
                    if k in ("risks_added", "scope_added", "dropped", "reworded_after_refutation") and v
                } or None) if _auth and _auth != _now else None,
                # …AND A REFUTATION ITS ISSUER RULED OUT, which moves no digest: the claim reads the same and the PASS
                # re-ran less than what once failed it (`findings`)
                "retired_after_refutation": sorted({r["criterion"] for r in self.retired_findings(task_id)}) or None,
                "pinned_probes": rec.get("pinned_probes"),
                "pinned_probes_run": rec.get("pinned_probes_run"),
                # …AND WHICH OF THEM READ A SET THE CONTRACT DOES NOT PIN. Such a probe's object can
                # grow or shrink under it while the procedure's digest holds still, so its PASS says
                # less than the record otherwise reads — measured on `c_compiler`, where the corpus
                # went 60 → 79 files under a node that closed with `procedure_moved_since_authoring:
                # false`. Named on the CLOSURE, not only on the node's checks, because this is what
                # a later reading of the verdict has to be able to weigh.
                "probes_over_unpinned_sets": reads_an_unpinned_set(t.spec.criteria) or None,
                "beyond_the_procedure": rec.get("probes_beyond_the_procedure"),
                # …and the behaviours the validator NAMED past a pinned procedure it ran whole: exploration, decided by
                # nothing — the criterion stood on its procedure (`procedure.named_beyond_procedure`)
                "named_not_separately_observed": rec.get("named_beyond_the_procedure") or None,
                # A refutation whose criterion was renamed or replaced by a plan repair: the
                # obligation to re-run it cannot be enforced against a criterion that no longer
                # exists, so it is named here rather than lost. Silence is the failure mode this
                # whole change exists against.
                "orphaned_refutations": orphaned_regression(
                    t.spec.criteria, self.regression_probes(task_id)) or None,
                # THE RESIDUE, AND IT IS NOT ONE SENTENCE. What the pinned set does not reach is
                # unchecked; so is a pinned probe that never ran (the internal self-report door, §10.3, closes a
                # node without running any); and so is the sensitivity of the procedure ITSELF — no
                # check anywhere decides whether a pinned command CAN fail, and §9.6 says none
                # can. Saying only the first would be the honest-sounding half of three.
                "residue": (
                    ("NOT checked by the pinned procedure: "
                     f"{(rec.get('pinned_probes') or 0) - (rec.get('pinned_probes_run') or 0)} of "
                     f"{rec.get('pinned_probes')} pinned probes were never run on this closure "
                     "(an internal node closes on its executor's own report — §10.3). "
                     if (rec.get("pinned_probes_run") or 0) < (rec.get("pinned_probes") or 0)
                     else "checked by the pinned procedure and what the validation explored. ")
                    + "Behaviour outside that is UNCHECKED; the procedure's own sensitivity is "
                      "unchecked too (a decidable criterion can be insensitive to a real "
                      "divergence, and no structural check guards that — FM-3, Ch. 8 / §15.7); "
                      "and what a pinned probe's output actually SHOWED is the validator's word — the "
                      "engine matches the command that ran, never the observation it returned"),
            } if rec else None,
        }

    def closures_by_hand(self, root_id: Optional[TaskId] = None) -> list[str]:
        """Settled nodes whose standing verdict was ASSERTED BY HAND, not produced by an instrument.

        The §10.3 degenerate case, and §15.7's named boundary: at a door where a person names
        themselves, the engine cannot establish that the reviewer is independent or that the
        observations happened. That is a declared limit, not a defect — what was a defect is that it
        was declared in one place and invisible in the two a reader consults. THREE doors reported
        the same thing across two waves (2026-09-04/05): a root closed with zero work through an
        invented reviewer, and `status`, `next_steps` and `q_V` gave it exactly what an earned root
        gets, while `get_verdict` and `gfso log` said plainly whose word it rested on.

        Not a reason to withhold `complete`: a person validating their own project by hand is the
        product's documented solo path. It is the one fact about such a graph a reader must not have
        to ask a second verb for. `hand_overruled_closures` is the sharper subset — those also
        displaced an instrument that said the opposite.
        """
        return [str(t.id) for t in self._within(root_id)
                if (self.closure_of(t.id) or {}).get("by_hand")]

    def passes_over_open_parts(self, root_id: Optional[TaskId] = None) -> list[str]:
        """Wholes that stand PASSed while a part is not accepted — the departure from AND §12.8 reads off the log rather
        than gating, admitted at a seam where the signer could not lift it (`whole_waits_for_its_parts`). FM-4's trace
        where the PASS is untrue; a split's denial carried to its decomposer where the check showed the part unneeded."""
        return [str(t.id) for t in self._within(root_id) if passed(t)
                and any(not settled_positive(k) for k in self._graph.get_active_children(t.id))]

    def auto_accepted_closures(self, root_id: Optional[TaskId] = None) -> list[str]:
        """Settled nodes that reached DONE on the CLOCK — the issuer never answered (§12.4, §16.14).

        The third weight of evidence beside a hand verdict and an instrument's: none at all. The
        canon makes auto_pass an acceptance (§16.14), so a parent's conjunction stands on such a
        child exactly as it stands on a validated one — which is why the fact has to travel. Before
        this, the conjunction refused it instead, and a child accepted by the clock locked its whole
        ancestry with no exit (probed 2026-09-07: the parent's PASS refused, `reopen` refused as
        consumed, `next_step` reporting `stuck: false`). Accepting it and SAYING so is the trade;
        accepting it silently would be the same lock's mirror image, a green nobody can weigh.
        """
        return [str(t.id) for t in self._within(root_id)
                if (self.closure_of(t.id) or {}).get("auto_accepted")]

    def hand_overruled_closures(self, root_id: Optional[TaskId] = None) -> list[str]:
        """Settled nodes that closed on a HAND verdict which displaced an instrument's opposite one.

        The sibling of `refuted_passes`, for the other order of events. There, the instrument's
        refutation lands after the signature and the state is left showing the signature. Here it
        landed FIRST, on the same delivery, and a self-named party's record replaced it before the
        close — so the node's current verdict agrees with its state and nothing was contradicted at
        the moment anyone looked (CLI door, wave 24, 2026-09-04).

        Overruling is legitimate: the verdict is the issuer's act (§10.2), and §15.7 says no
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
        an INTERNAL node's own executor stamping its DELIVER (§10.3), and a registered instrument
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
        task = self._graph.get_task(task_id)
        if task is not None and str(rec.get("validator") or "") == str(task.assignee or ""):
            return "self"
        return "instrument"


    def accepted_moves(self, task_id: TaskId) -> int:
        """How many transitions of this node the log has ACCEPTED — changes with every one (Thm 11), which
        neither the generation (a BLOCK and its resolution leave it) nor the entry time (a re-entry
        inside one clock tick) is guaranteed to do."""
        return sum(1 for x in self.audit_log(task_id) if not x.rejected)


    def issuer_kind(self, task_id: TaskId, registered=None) -> str:
        """`validation.party_kind` of this node's issuer — who makes its issuer moves (holder / machine / legacy /
        person), over the dispatcher's registry when given, else the roster it published."""
        return party_kind(self._graph, str(self._graph.issuer_of(task_id)),
                          self.workforce.roster() if registered is None else registered)

    def mode_kind(self) -> Optional[Mode]:
        """The project's mode, typed (`validation.mode_kind`)."""
        return mode_kind(self._graph)

    def holder_signs(self, task_id: TaskId) -> bool:
        """Is this node's verdict its HOLDER's to sign on the observation? Under SOLO or SEMI the user's
        agent holds nodes, and where it is a node's issuer the verdict is its decision, not the
        instrument's: the issuer decides, the validator observes (the author, 2026-09-27). The instrument
        still runs and records. AUTO is not here — there the system makes every issuer move."""
        return self.issuer_kind(task_id) == "holder"

    def validated_by_instrument(self, task_id: TaskId) -> bool:
        """Will a registered instrument validate this node's delivery without being asked?

        Two facts, and both live here: an instrument is published to the graph (the dispatcher does
        it each round), and the node's ISSUER is automated — a person's node is validated FOR them and
        then waits for their signature, so only an automated issuer makes the instrument's verdict
        the signal too. Asked as one question because every surface that answers "wait" or "act"
        needs the same one, and a door that composed it for itself would reach past this object into
        the graph (and, in its first spelling, into the delegation layer the layer gate forbids it).
        """
        task = self._graph.get_task(task_id)
        if task is None or not self.workforce.has_an_instrument() or self.holder_signs(task_id):
            return False
        issuer = str(self._graph.issuer_of(task_id))
        return issuer == _config_agent_id() or self.workforce.kind_of(issuer) is not None


    def record_session_fit(self, task_id: TaskId, volume: str, fits: Optional[bool]) -> None:
        """The decomposer's count of a node's work and its judgement that one executor session builds and
        checks it — kept beside the contract, not in it: a changed estimate is not a revision (Inv-1)."""
        self._storage.store_setting(f"session_fit:{task_id}",
                                           json.dumps({"volume": volume, "fits": fits}))

    def session_fit(self, task_id: TaskId) -> Optional[dict]:
        """The recorded count and judgement for a node (`validation.session_fit`)."""
        return _session_fit(self._graph, task_id)

    def fits_one_session(self, task_id: TaskId) -> bool:
        """Does one executor session carry this node's whole subtree (`validation.fits_one_session`)?"""
        return _fits_one_session(self._graph, task_id)

    def observed_here(self, task_id: TaskId) -> bool:
        """Does the instrument observe this node's deliveries (`validation.observed_here`)?"""
        t = self._graph.get_task(task_id)
        return t is not None and _observed_here(self._graph, t)

    def scope_top(self, task_id: TaskId) -> Optional[Task]:
        """The top of the one-session scope this node lies in, or None (`validation.scope_top`)."""
        t = self._graph.get_task(task_id)
        return _scope_top(self._graph, t) if t is not None else None

    def parts_procedure(self, task_id: TaskId) -> dict:
        """{criterion: the pinned procedure of the DONE parts mapped to it} a validation of this node also runs
        over its delivered result (`validation.parts_procedure`)."""
        t = self._graph.get_task(task_id)
        return _parts_procedure(self._graph, t) if t is not None else {}

    def layable(self, task_id: TaskId) -> set:
        """The pinned probes whose inputs a validation of this node lays down — its own and its parts', as the PASS
        gate reads them (`unaccounted_for`): a finding over any other's inputs cannot run."""
        t = self._graph.get_task(task_id)
        return layable_over(t.spec.criteria, self.parts_procedure(task_id)) if t is not None else set()

    def validation_procedure(self, task_id: TaskId) -> tuple:
        """Every criterion whose pinned probes a validation of this node runs: its own, then its parts'."""
        t = self._graph.get_task(task_id)
        return _settled_procedure(self._graph, t) if t is not None else ()

    def scope_members(self, top_id: TaskId) -> list[Task]:
        """The scope's nodes top-down, its top first (`validation.scope_members`)."""
        t = self._graph.get_task(top_id)
        return _scope_members(self._graph, t) if t is not None else []

    def note_failed_through_parts(self, task_id: TaskId, through: dict) -> None:
        """Record, for the FAIL just signed on this whole, which of its cited criteria it carries only through
        parts that failed ({criterion: [parts]}) — keyed to the generation that FAIL opened, so a later FAIL of
        any other origin is never read as one of these."""
        t = self._graph.get_task(task_id)
        ledger_write(self._storage, task_id, FAILED_THROUGH_PARTS,
                     {"generation": list(generation_of_task(t)), "through": through})

    def failed_through_parts(self, task_id: TaskId) -> dict:
        """{criterion: [parts]} the standing FAIL of this whole cited only through its failed parts, or {}."""
        t, rec = self._graph.get_task(task_id), ledger_read(self._storage, task_id, FAILED_THROUGH_PARTS)
        return dict(rec["through"]) if t is not None and rec and rec.get("generation") == list(
            generation_of_task(t)) else {}

    def split_owed(self, task_id: TaskId) -> Optional[dict]:
        """Why this childless node's split is owed before its work is a leaf's, or None (`validation.split_owed`)."""
        t = self._graph.get_task(task_id)
        return _split_owed(self._graph, t) if t is not None else None

    def del_for(self, parent_id: Optional[TaskId]) -> Optional[AgentId]:
        """Del of a node about to be issued under `parent_id` (None: the root), as the mode says —
        or None when no mode is set (the caller's own default stands, as before modes).

        The user-agent holds depths above the boundary, and only under a parent it holds itself: the
        held part is a connected top of the tree. Everything else goes to an executor from this
        project's pool that is NOT the parent's Del, so every system node is a seam (§10.3) — an
        executor under itself would self-verify with no validator in between."""
        parent = self._graph.get_task(parent_id) if parent_id else None
        return self.del_at(0 if parent is None else self.depth_of(parent.id) + 1,
                           parent.assignee if parent is not None else None)

    def del_at(self, depth: int, parent_del: Optional[AgentId]) -> Optional[AgentId]:
        """`del_for` for a node that does not exist yet under a parent that may not either — the
        decomposition verb issues a root and its children in one build."""
        held = self.held_by_the_user_agent(depth)
        if held is None:
            return None
        me = AgentId(_config_agent_id())
        if held and (depth == 0 or str(parent_del) == str(me)):
            return me
        pool = [a for a in self.workforce.executor_pool() if depth == 0 or str(a) != str(parent_del)]
        if not pool:
            raise ValueError(
                f"the project runs in {self.mode()['mode']} and a node at depth {depth} is the "
                f"system's, but no registered executor of this project can take it"
                + (f" other than its parent's ({parent_del}), which would leave no seam"
                   if depth else "")
                + ". Register one more (`register_agent(<id>, \"llm-executor\", workdir=…)` in "
                  "this project).")
        return pool[0]

    def now(self) -> float:
        """This engine's clock reading — the ClockPort's, never the wall's.

        Published because callers that WAIT need it and were reaching into `_clock` to get it: a
        fake-clock host must not be made to sit through a real wait just because a door asked the
        wrong object.
        """
        return self._clock.now()

    def unmet_producers(self, task_id: TaskId) -> list[str]:
        """The nodes this one consumes that have not passed — the reason it cannot start yet.

        §12.4 admits ACCEPT from OFFERED whatever the seams say, and the engine is not narrower than
        the canon: taking a node is allowed. What the frontier knew and the ACCEPT reply did not was
        that the work cannot begin — so a graph showed EXECUTING for nodes provably unable to run
        (CLI door, 2026-09-02). One owner for the question the frontier already asks.
        """
        # The id is compared and looked up as a STRING: a malformed edge that carried a list once
        # reached the DAG check and raised `unhashable type` inside the protocol step (2026-09-02).
        # The door refuses that value now, and a read is still not the place to fall over it.
        return sorted({str(e.from_id) for e in self._graph.dep_edges(adopted=True)
                       if str(e.to_id) == str(task_id)
                       and not settled_positive(self._graph.get_task(TaskId(str(e.from_id))))})

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


    def refusal_of(self, task_id: TaskId, signal: Signal, entry=None) -> SignalOutcome:
        """The system's answer to a transition that moved nothing — ONE record, every door.

        The kinds are not decoration: a signal the STATE does not admit, a signal it admits whose
        transition GUARD said no, and a signal a RULE above the FSM refused (the seam's verdict, the
        AND over children, the plan gate) are three different facts, and a caller who cannot tell
        them apart cannot tell "wrong button" from "not yet" from "not yours". The log's own entry
        is preferred when it carries the reason, because that is the sentence the engine already
        wrote for this exact attempt."""
        st = self._graph.get_state(task_id)
        _admits = [s for s in self.available_actions(task_id)]
        # THE KIND IS STRUCTURAL, AND IT IS NOT READ OFF THE SENTENCE. It used to be: an entry with
        # any error at all became `rule` whenever the state admitted the signal — so a GUARD refusal
        # that came back through the door, carrying the guard's own sentence, was relabelled `rule`
        # on the way. Probed 2026-09-07 on ASSIGN over a live node: `refusal_of(...)` called directly
        # said `guard`, and the identical refusal through `signal` said `rule`, both under the very
        # words "its transition GUARD refused it". The kind flipped on a round trip — the one
        # distinction this docstring says a caller needs.
        # The discriminator is where the refusal came FROM, and `loop.py` knows it exactly: a
        # `ValidationError` out of `validate_signal` (a rule above the FSM) or a `transition` that
        # returned None (the FSM itself). What the log carries of the second is authored by ONE
        # function, `not_admissible_here` — so an error equal to what it would say IS the FSM path,
        # and anything else is the rule layer. Which also removes the reason the drift was possible:
        # both FSM sentences were hand-copied here, a second implementation of a rule that already
        # had an owner.
        # A NODE THAT IS NOT THERE STILL OWES A SENTENCE. With no state there is no FSM sentence to
        # borrow, and an earlier spelling of this let `_why` fall through as None — so a typo'd id
        # on any door answered `{"accepted": false, "error": "", "refused_by": "state"}`: the exact
        # silence this function exists to prevent, in the most ordinary way to reach it.
        _fsm_said = (not_admissible_here(signal, st) if st is not None else
                     f"{signal.name} moved nothing: there is no task '{task_id}' in this project "
                     f"(check the id, and `project` — every verb takes one, and a graph you are not "
                     f"pointed at looks exactly like an empty one).")
        _why = entry.error if entry is not None else None
        if _why and _why != _fsm_said:
            kind = "rule"
        else:
            kind = "guard" if (st is not None and signal in _admits) else "state"
            _why = _fsm_said or _why
        return SignalOutcome(task_id=task_id, signal=signal, accepted=False, from_state=st,
                             refusal=Refusal(kind=kind, why=_why))

    def refusal_for(self, task_id: TaskId, signal: Signal, signer: Optional[AgentId] = None,
                    spec: Optional[Spec] = None) -> Optional[Refusal]:
        """Would this signal be refused here, and why — the machine's own answer, asked without sending (§12.16 (ii)
        names a refusal by the requirement it operationalizes). ONE dry run over the gate the loop runs: the state, the
        rules above the FSM (`rule_refusal`), the signer (`signer_refusal`), the transition's guard. A surface that
        lists moves reads this and writes no rule again (ortho audit, D-F1: four hand mirrors offered refused moves).

        The payload is what a caller would send to make the move at all — a live deadline and the standing contract on
        an ASSIGN, a criterion of the contract on a FAIL — so what comes back is a refusal of the MOVE, not of an empty
        message. `signer` None asks as the party the move belongs to; `spec`, an ASSIGN's new contract — a revision asked
        before an act that must not write half of itself (the issuer's remap with the child's revision, critic r17)."""
        t = self._graph.get_task(task_id)
        if t is None or signal not in available_signals(t.state):
            return Refusal(kind="state", why=not_admissible_here(signal, t.state) if t else f"no task '{task_id}'")
        role = required_role(signal)
        source = signer or (self._graph.issuer_of(task_id) if role == Role.ISSUER else t.assignee if role == Role.EXECUTOR
                            else None)
        terminal = t.state in TERMINAL_STATES
        sd = SignalData(signal=signal, task_id=task_id, source=source,
                        spec=None if terminal else (spec or t.spec) if signal == Signal.ASSIGN else None,
                        # …a revision asked with its contract carries the deadline the revision will: none, the
                        # node's own kept — a live one invented here approved what the revision then refused (critic C1)
                        deadline=datetime.now() + timedelta(hours=1) if signal == Signal.ASSIGN and spec is None else None,
                        failed_criteria=tuple(c.name for c in t.spec.criteria[:1]) if signal == Signal.FAIL else (),
                        result="the delivered result" if signal == Signal.DELIVER else None)
        if why := signer_refusal(self._graph, task_id, signal, source):
            return Refusal(kind="role", why=why)
        if spec is not None and signal == Signal.ASSIGN:
            try:
                refuse_a_contract_that_pins_nothing(self._graph, task_id, spec)   # what `_revise` refuses first
            except ValueError as ex:
                return Refusal(kind="rule", why=str(ex))
        if why := rule_refusal(sd, self._graph, self._audit):
            return Refusal(kind="rule", why=why)
        if transition(t.state, sd, _guard_context(self._graph, self._audit, task_id, t.state)) is None:
            return Refusal(kind="guard", why=(self.reopen_refusal(task_id) if terminal and signal == Signal.ASSIGN
                                              else None) or not_admissible_here(signal, t.state))
        return None

    def reopen_refusal(self, task_id: TaskId) -> Optional[str]:
        """Why R′'s edge is shut on this settled node, or None (§12.14): the issuing condition below a root, then the
        finality gate — consumed, or its reopens spent. The FSM guard decides; this says which part bit."""
        t = self._graph.get_task(task_id)
        if why := issuing_condition(self._graph.get_parent(task_id), task_id):
            return why
        if self._graph.is_consumed(t):
            return (f"{task_id} is CONSUMED — something rests on it or the plan moved past it since it settled (its "
                    f"parent delivered over it, a Dep-consumer worked on it, a re-admission covered around it, or the "
                    f"parent's version maps it to nothing), and once logged that stands, so the terminal is final "
                    f"(§12.14). Recovery is RE-DECOMPOSITION by the issuer — auto_decompose on the parent — never a reopen.")
        if t.reopens >= t.max_reopens:
            return (f"{task_id} has spent its reopens ({t.reopens}/{t.max_reopens}) — the counter is what makes the "
                    f"reopened node finite (Inv-5). Re-decompose around it, or re-author it as a new node.")
        # …and the version it would enter OFFERED with (§2.5, §12.16) — the same owner the signal gate reads, so the
        # door that carries no deadline answers in words instead of raising (critic over session 475ba784)
        if why := no_live_deadline(self._graph, t):
            return (f"reopening {task_id} under its standing contract: {why} — `reopen` carries none; "
                    f"`revise('{task_id}', …, deadline=…)` reopens it with one")
        return None

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
        # WHO SIGNS WHAT is asked of the machine's own rule (`signer_refusal`) — a hand copy here (`_roles_of`) came
        # apart from it at the root-issuer corner and the roster-instrument exception (probed 2026-09-07).
        return [s for s in sigs if signer_refusal(self._graph, task_id, s, agent_id) is None]

    def _roles_of(self, agent_id: AgentId, task: Task) -> set:
        """All roles this agent holds on the node — executor and issuer are not exclusive — read off the machine's
        signer rule (`signer_refusal`) by a signal of each role that no instrument exception touches."""
        return {r for r, sig in ((Role.EXECUTOR, Signal.ACCEPT), (Role.ISSUER, Signal.CANCEL))
                if signer_refusal(self._graph, task.id, sig, agent_id) is None}

    def _role_of(self, agent_id: AgentId, task: Task) -> Optional[Role]:
        """The single role to SHOW a caller, when one label is wanted instead of the set.

        Derived from `_roles_of` rather than re-deriving the rule: two functions answering one
        question in two hand-written copies is how the root-issuer corner above came apart in the
        first place. Executor wins the label when an agent holds both — it is the role they act in
        on the node itself."""
        roles = self._roles_of(agent_id, task)
        return Role.EXECUTOR if Role.EXECUTOR in roles else (Role.ISSUER if roles else None)

    # === Extended Query API ===

    def tasks_by_state(self, state: State) -> list[Task]:
        """Every node in that state, terminal states included."""
        return [t for t in self._storage.get_all_tasks() if t.state == state]

    def tasks_by_assignee(self, assignee: AgentId) -> list[Task]:
        """Every node held by that participant (Del), whatever state it is in."""
        return [t for t in self._storage.get_all_tasks() if t.assignee == assignee]

    def all_tasks(self) -> list[Task]:
        """Every node of this graph, including the settled ones."""
        return self._storage.get_all_tasks()

    # === Execution forcing-point ===


    def refused_report_for_this_delivery(self, task_id: TaskId) -> Optional[dict]:
        """The refused report standing on the CURRENT delivery of this node, or None.

        One owner for a record three readers need: the frontier's directive, `get_verdict`, and —
        the one that pays for it — the packet handed to the validator on its next attempt. Scoped to the
        generation, because a refusal from before a rework is about a delivery nobody made.
        """
        rec = self.rejected_report(task_id) or {}
        task = self._graph.get_task(task_id)
        if not rec or task is None:
            return None
        gen = generation_of_task(task)
        return rec if stamped_with(rec, gen) else None

    def reusable_from_refused(self, task_id: TaskId) -> list:
        """The entries of the refused report on THIS delivery that decide their criterion
        on their own — so the next attempt validates only the rest.

        A report is refused whole for one gap, and a retry that re-validates everything can fail on a
        different one: measured 2026-09-22, 7 of 10 refused reports on a delegated `coreutils` run
        failed that way. The engine already splits a node's criteria across parallel validators and takes
        the union (`validation_batch`), so an entry kept from the last run on the SAME delivery is a
        batch that finished early. Each kept entry passes, alone, the very checks the merged report
        will face again — a well-formed PASS with a probe, every named behaviour observed, every
        pinned probe and every once-refuting probe run — and the merged report is re-checked whole.
        """
        rec = self.refused_report_for_this_delivery(task_id)
        task = self._graph.get_task(task_id)
        if not rec or task is None:
            return []
        entries = [e for e in (rec.get("per_criterion") or ()) if isinstance(e, dict)]
        # A report that refuted anything is not mined: its refutation never reached the regression
        # set (that is written on a recorded verdict), and trusting half of a report that disagreed
        # with itself is trusting the half nobody can tell apart from the other.
        if any(spoken_verdict(e.get("verdict")) != "pass" for e in entries):
            return []
        known = {c.name for c in task.spec.criteria}
        regression, parts = self.regression_probes(task_id), self.parts_procedure(task_id)
        # Each entry against ITS OWN run's ledger — a shell in the next run must not vouch for a
        # probe the earlier one never executed (`unrun_probes`).
        # An entry already reused once keeps its FIRST stamp — who validated it, when, and that run's
        # ledger — through a chain of refusals; the record's own fields describe only the last run.
        # `judged_by`: the key this record carried before 2026-09-25 — stores written then still hold it
        this_run = {**(rec.get("validated_by") or rec.get("judged_by") or {}), "ts": rec.get("ts"),
                    "tools_used": rec.get("tools_used") or {}}
        stamped = [{**e, "reused_from_refused": e.get("reused_from_refused") or this_run}
                   for e in entries]
        return [e for e in stamped
                if str(e.get("criterion")) in known
                and not verdict_report_defects([str(e.get("criterion"))], Verdict.PASS, [e], [],
                                               require_probe=True)
                and not unaccounted_for(task, [e], False, None, regression, parts=parts)
                and not unrun_probes([e], e["reused_from_refused"].get("tools_used"))]


    def _redelivery_refusal(self, task) -> Optional[str]:
        """What the re-delivery gate would say about this node right now, or None if it would pass.

        Asked by the frontier so the directive names the repair the engine will actually accept —
        and asked THROUGH the rule the signal path enforces (`validation.redelivery_refusal`), not
        by re-assembling its condition here. The two had drifted: this one asked only "is the
        standing verdict a FAIL", the gate also asks whether that FAIL is about the delivery that
        stands (same reopens, previous iteration), and a node the gate would let through could be
        told to repair a plan that needed nothing.
        """
        try:
            return redelivery_refusal(self._graph, task, self._audit)
        except Exception:                 # a directive is never worth an exception on the frontier
            return None

    #: How many FAILs on the SAME criterion make the contract, rather than the work, the suspect.
    #: Three is where the canon already bounds the ordinary loop (§12.15: max_iterations default 3).
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

    def rework_findings(self, task_id: TaskId) -> list[tuple[str, str, list[str]]]:
        """(criterion, the validator's evidence, the commands of the probes that refuted it) for each criterion
        the standing FAIL names — WHY the work failed, the executor's only window into it (it does not see the
        validator's probes). One owner for every door: the delegated executor's packet carried the names alone,
        so an executor re-ran its packet's own checks, found them green and re-delivered the unchanged file round
        after round (AUTO json_parser, 2026-09-27: the refuting probe `c2ffd553` never reached it)."""
        return self._rework(task_id)[0]

    def rework_settled(self, task_id: TaskId) -> dict:
        """{criterion: the ids of the probes behind the standing FAIL the next PASS no longer runs} — named to the
        executor as settled: an observation that also came through one still in force is shown whole, and the settled
        part of it was disputed five times over (critic r5, GB_coreutils_tmsfo4636 root.build_cat)."""
        return self._rework(task_id)[1]

    def _rework(self, task_id: TaskId) -> tuple[list, dict]:
        rec = self._graph.exec_verdict_record(task_id)
        if not rec or rec.get("verdict") != Verdict.FAIL:
            return [], {}
        per = {p.get("criterion"): p.get("evidence", "") for p in (rec.get("per_criterion") or [])}
        # …LESS WHAT THE NEXT PASS POSITIVELY NO LONGER RUNS: a withdrawn pinned probe's run (its refutation was of the
        # probe, `without_pinned_runs`), a retired finding, one that cannot run. Shown as an order, it was disputed a
        # dozen times and no ruling could retire it (AUTO haiku coreutils, root.build, 2026-10-12, three rows); what was
        # observed goes with it once every probe it was observed through is such
        task, entries = self._graph.get_task(task_id), self._audit.get_entries(task_id)
        lay, standing = self.layable(task_id), self.regression_probes(task_id)
        now = {probe_id(c.name, p) for c in task.spec.criteria for p in (c.check or ())} if task else set()
        retired = self.retired_findings(task_id)
        dead = [(c, p) for c, ps in standing.items() for p in ps if unrerunnable(p, lay, rec.get("workdir"))]
        gone = {**{w: c for w, c in ever_pinned(entries, task).items() if w not in now},
                **{str(r["id"]): str(r.get("command") or "") for r in retired},
                **{str(p.get("id")): str(p.get("command") or "") for _, p in dead}}
        # …each under ITS criterion: one probe refutes two criteria as two findings, and retiring one left the other
        # standing while its run read as settled (critic r6)
        seen = frozenset((str(c), " ".join(str(x).split()))
                         for c, x in [(r["criterion"], r.get("seen")) for r in retired]
                         + [(c, p.get("seen") or p.get("as_run")) for c, p in dead] if x)
        # …AS WRITTEN: the regression store keeps each command whitespace-normalized (its identity), which turns a
        # multi-line probe into one line that no shell runs; the verdict keeps the raw command of this round's probes
        this_round, spent, settled = {}, set(), {}
        for pc in rec.get("per_criterion") or ():
            if spoken_verdict(pc.get("verdict")) == "fail":
                c, ps = str(pc.get("criterion")), list(probes_of(pc))
                kept = [p for p in ps if not released(p, c, gone, seen)]
                if ps and not kept:
                    spent.add(c)
                settled.setdefault(c, []).extend(str(p.get("id") or probe_id(c, p)) for p in ps if p not in kept)
                this_round.setdefault(c, []).extend(str(p.get("command")) for p in kept if p.get("command"))
        for r in retired:
            settled.setdefault(str(r["criterion"]), []).append(str(r["id"]))
        # …AS RUN, concretely: the probes of this round first, then every earlier finding, over the directories it
        # really read rather than the name the store gives them
        return [(c, "" if c in spent else (per.get(c) or "").strip(),
                 list(dict.fromkeys(this_round.get(c, []) + [str(p.get("seen") or p.get("as_run") or p.get("command"))
                                                              for p in standing.get(c) or ()
                                                              if p.get("command") and str(p.get("id")) not in gone])))
                for c in rec.get("failed_criteria") or []], {c: list(dict.fromkeys(v)) for c, v in settled.items() if v}


    def next_step(self, root_id: Optional[TaskId] = None) -> dict:
        """The ONE next required action from the graph's current state, or `complete=True` (`Frontier.next_step`)."""
        return self.frontier.next_step(root_id)

    def next_steps(self, root_id: Optional[TaskId] = None) -> dict:
        """The parallel frontier: every currently actionable node, priority-ordered (`Frontier.next_steps`)."""
        return self.frontier.next_steps(root_id)


    def in_flight_nodes(self) -> list[dict]:
        """The nodes that are BUSY right now — being validated, or being worked on by a machine.

        The frontier lists what a caller can take; a node in VALIDATING or one held by a registered
        executor is neither takeable nor stuck, and having no name for that state is what made an
        empty frontier read as a dead graph."""
        out = []
        for t in self.all_tasks():
            if self.claims.review_in_flight(t.id):
                out.append({"task_id": str(t.id), "state": t.state.name,
                            "why": "has its plan being checked — a Level-2 review of this version "
                                   "is running",
                            "opens_with": "nothing: its verdict arrives by itself"})
                continue
            if t.state == State.VALIDATING:
                out.append({"task_id": str(t.id), "state": t.state.name,
                            "why": ("is being validated — an independent validation of this delivery "
                                    "is running" if self.claims.validation_in_flight(t.id) else
                                    "is delivered and waits for its issuer's verdict"),
                            "opens_with": ("nothing: its verdict arrives by itself"
                                           if self.claims.validation_in_flight(t.id) else
                                           f"the issuer validates it (`validate_result('{t.id}')` runs "
                                           f"the instrument)")})
            elif (t.state in (State.EXECUTING, State.REWORKING)
                  and self.workforce.kind_of(t.assignee) == "llm-executor"
                  and not self.parking.is_execution_parked(t)):
                out.append({"task_id": str(t.id), "state": t.state.name,
                            "why": f"is being worked on by '{t.assignee}', a registered executor",
                            "opens_with": "nothing: the dispatcher started it and its report follows"})
        # …and a passed node whose result is still being joined where its whole works (`mark_joining`)
        out += [{"task_id": t, "state": "DONE", "why": "has passed and its result is being joined where its whole "
                 "works", "opens_with": "nothing: the join ends by itself"} for t in self.joins.joining_nodes()]
        return out


    def issuer_moves_on(self, task_id) -> str:
        """The acts an ESCALATED node admits, WRITTEN ONCE because three surfaces said otherwise.

        ESCALATED is the issuer's waiting state (§12.5): the executor stopped and the decision is
        his. Every surface that met the state used to end its sentence with "a terminal node is not
        reopened and takes no revision" — which named no act at all, and an agent told that a node
        it must move admits nothing does not stop: it builds a new root beside the dead one, which
        is what a measured run did twice in one graph.

        WHICH moves, though, depends on HOW the node got here — §12.5 names three routes and only
        one of them is a spent rework loop. Written once does not mean written blind: offering
        "raise the rework bound" to a node that timed out is offering the one move that provably
        cannot help (the bound touches neither clock), and saying "its loop was exhausted" of it is
        simply false. The route is decidable: only the exhausted-loop cell carries DoneReason.FAIL.
        """
        t = self._graph.get_task(task_id)
        if t is None:
            return "the ISSUER decides — the node is gone from this graph."
        spent = t.done_reason == DoneReason.FAIL
        first = (f"raise the rework bound (`revise('{task_id}', max_iterations=N)`; "
                 f"{t.iteration}/{t.max_iterations} spent) if the forecast was short rather than "
                 f"the plan wrong"
                 if spent else
                 f"give it more time (`revise('{task_id}', deadline=…)`) if the clock is what ran "
                 f"out — but if what ran out was a BLOCKER nobody cleared, more time alone will not "
                 f"help: RESOLVE_BLOCK is not admissible here, so clear it outside the graph and "
                 f"revise, or revise the contract around it (`get_dependencies('{task_id}')` names "
                 f"what it was waiting on)")
        return (f"the ISSUER decides, and has three moves: {first}; change or narrow the criteria "
                f"(`revise`) if the plan is what is wrong; or close it "
                f"(`signal('{task_id}', 'CANCEL')`, which cascades the live subtree). Silence "
                f"closes it too, by the state's own timeout — it never drifts to PASS.")

    def why_escalated(self, task_id) -> str:
        """Why this node is waiting — the same route split, said where a reader meets the state."""
        t = self._graph.get_task(task_id)
        if t is not None and t.done_reason == DoneReason.FAIL:
            return (f"its rework loop is spent ({t.iteration}/{t.max_iterations}, §12.5) — a "
                    f"standing FAIL, and a parent's PASS is the AND over its children, so nothing "
                    f"above it completes until its issuer decides")
        return ("it ran out of time (§12.5: a deadline missed, a block nobody cleared, or a delivery nobody "
                "validated in time) — "
                "not a verdict on the work, and nothing above it completes until its issuer decides")

    def stranded_nodes(self) -> list:
        """Nodes the graph cannot move past: settled NEGATIVE (§12.5 — the exhausted rework loop
        escalates, and ESCALATED means "this needs attention"), or cancelled.

        Read by the stuck branch AND by every ordinary frontier answer, because they were only ever
        named when NOTHING else was actionable: a root with one escalated child and one takeable
        sibling reported the sibling and said nothing about the child that had already made the root
        impossible (walked by hand 2026-08-21). A parent's PASS is the AND over its children."""
        return sorted((t for t in self.all_tasks()
                       if t.state in (State.ESCALATED, State.ABANDONED)
                       or (t.state == State.DONE and t.done_reason == DoneReason.FAIL)),
                      key=lambda t: str(t.id))


    def graph_holes(self, root_id: Optional[TaskId] = None) -> list[dict]:
        """Every UNMET structural check across the whole graph (or the subtree under root_id), each with what it does
        (`kind`, `hole_kind`): a `gate` is resolved ∨ consciously declared BEFORE execution; a `flag` (CHECK-3 past the
        admission) is the consumer's issuer's to re-ASSIGN or let run (§12.10); `advisory` holds nothing. A freshly
        `decompose`d graph can carry holes (the model isn't perfect); this is how you SEE them all at once instead of
        one refusal at a time. Returns [{task_id, name, check, kind, details}], ordered by node then check."""
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
                                  "check": c.check_name, "kind": hole_kind(c.check_name), "details": c.details})
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
