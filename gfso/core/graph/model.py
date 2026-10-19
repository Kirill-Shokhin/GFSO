"""G = (N, E_D, E_Dep, sigma). Wraps StoragePort."""
from __future__ import annotations

import dataclasses

import json
from typing import Optional

from gfso.core.types import (
    TaskId, AgentId, Task, State, Signal, Verdict,
    GuardContext, GraphContext, CheckResult, Recommendation,
    DispatchPayload, DepEdge, StoragePort, DEFAULT_MAX_ITERATIONS, TERMINAL_STATES,
)


#: WHICH delivery a record is about: a rework moves the first, a REOPEN the second (a pre-reopen pass must not re-open
#: a gate from the past), a revision the third (a validator still running on a voided delivery lands its verdict after
#: it carrying the same first two, §12.10). One owner of the triple — it was spelt out ten times (ortho audit, D-F4).
GENERATION = ("iteration", "reopens", "revisions")


def stamp(generation: tuple) -> dict:
    """A record's generation fields, as stored."""
    return dict(zip(GENERATION, generation))


def stamped_with(rec: dict | None, generation: tuple) -> bool:
    """Was this record made for this generation? A record older than a field reads it as 0."""
    return bool(rec) and all(rec.get(k, 0) == g for k, g in zip(GENERATION, generation))


def recorded_by_an_appointed_observer(rec: dict | None, task, issuer) -> bool:
    """Was this verdict record made by an observer someone APPOINTED — the one kind that binds?

    The instrument (whoever runs it, the issuer or the system), or the node's issuer himself where he is
    not its executor. Never the executor: his own word is a report, and letting it bind would let him
    veto an independent issuer's PASS at a seam. Never a hand record by any other self-named party: that
    is a report too (C-12, 2026-09-27). One owner, because two rules read it — a PASS over a recorded
    FAIL (Inv-2) and the observation a PASS under a mode stands on — and they must not disagree."""
    if not rec or task is None:
        return False
    who = str(rec.get("validator"))
    return who != str(task.assignee) and (not rec.get("by_hand") or who == str(issuer))


def generation_of_task(t) -> tuple:
    """The generation of a node you already HOLD: (iteration, reopens, revisions).

    Same fact as `Graph.generation_of`, for callers that have the object rather than its id — and
    the reason it exists is that they were each spelling it as three defensive `getattr` reads with
    their own defaults. The fields are DECLARED, so they are read as declared: a `getattr` with a
    default over a declared field says the field might not be there, which is a false statement
    about this type and the thing the coupling instrument counts.
    """
    return (t.iteration, t.reopens, t.revisions) if t is not None else (0, 0, 0)



def register_log_key(task_id) -> str:
    """Where the versions of a node's split register are recorded, each with its author and time (Thm 11)."""
    return f"register:{task_id}"


def coverage_history(storage, audit, parent_id) -> list:
    """The split's coverage {(criterion, child)} as each logged act that set it left it, in log order: [(key, coverage)].
    An admission sets it whole — its logged mappings (§11.5); a version of the node itself keeps what its criteria still
    name (§12.10). Coverage is the split's (§2.4), so no child's ASSIGN is a step of it. Keyed for `coverage_at`: an
    admission logged at `log_at` L stands just before entry L, a version on its own entry. Empty where no admission was
    logged — a graph from before admissions were."""
    steps = [((r.get("log_at", 0), -1), r) for r in json.loads(storage.get_critique(admission_key(parent_id)) or "[]")]
    if not steps:
        return []
    steps += [((i, 0), e) for i, e in enumerate(audit.get_entries() if audit is not None else ())
              if e.task_id == parent_id and not e.rejected and e.spec]
    out, cov = [], None
    for key, x in sorted(steps, key=lambda s: s[0]):
        if isinstance(x, dict):
            cov = frozenset((c, k) for c, k in x.get("mappings", ()))
        elif cov is not None:
            names = {c.get("name") for c in json.loads(x.spec).get("criteria", ())}
            cov = frozenset((c, k) for c, k in cov if c in names)
        if cov is not None:
            out.append((key, cov))
    return out


def coverage_at(history: list, at: int):
    """The coverage standing at or before log entry `at` (None before the first admission), and every later one."""
    before = [c for key, c in history if key <= (at, 0)]
    return (before[-1] if before else None), [c for key, c in history if key > (at, 0)]


def admission_key(task_id) -> str:
    """Where a node's split admissions are recorded (§11.5: a logged act of its own) — each with the children it
    issued, its drops, its mappings and its place in the signal log."""
    return f"admission:{task_id}"


def replaces_key(task_id) -> str:
    """Where the dropped children a node was admitted to stand in for are recorded — whose work it carries on."""
    return f"replaces:{task_id}"


def drops_key(task_id) -> str:
    """Where the children a re-admission of this node's split dropped are recorded, each with its place in the signal
    log (§11.5) — out of the plan at the drop (§12.6), whatever their cancellation's progress."""
    return f"dropped:{task_id}"


def root_issuer_key(task_id) -> str:
    """The setting that records a root's issuer — the one spelling both writer and reader use."""
    return f"issuer:{task_id}"


class Graph:
    def __init__(self, storage: StoragePort):
        self._storage = storage
        # the signal log, when a host holds one (`Engine` hands it in): consumption is read off it (`is_consumed`)
        self.audit = None
        # WHO MAY SPEAK AS THE ISSUER'S ROLE-V INSTRUMENT (§10.3): the registered `llm-validator` /
        # `unittest-checker` ids, published downward by the dispatcher each round. Declared here
        # because two validation rules read it — who may sign PASS/FAIL at all, and whether a seam's
        # PASS still needs a recorded verdict — and a field born outside `__init__` had both of them
        # reading it defensively, which is how a rule silently becomes "empty set" on any graph the
        # dispatcher never touched.
        self.authorized_validators: set[str] = set()

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
        """Children in the ACTIVE decomposition: every child but an ABANDONED one (§12.6: "a child is active unless
        ABANDONED or dropped by a re-admission … a settled cancellation, or the drop, takes it out of the plan").

        A cancelled node persists in the graph forever (provenance, §15.1 / Prop 6) but leaves the decomposition when
        its cancellation SETTLES, not at CANCEL: until CONFIRM_CANCEL or CANCELLING's bound, it still stands where it
        stood — the AND waits on it, and its coverage still counts (sync audit, A-F9: read as gone at CANCEL, a
        parent could close over a child whose closing had not been acknowledged). A dropped unissued child leaves by
        its CANCEL from IDLE, settled the same way. A child DROPPED by a re-admission is out at the drop (§12.6:
        "unless ABANDONED or dropped by a re-admission"): the re-admission's battery already read the split without it,
        and read back in while its cancellation runs, it was an orphan that refused every later admission (critic r6)."""
        dropped = {d["child"] for d in json.loads(self._storage.get_critique(drops_key(task_id)) or "[]")}
        return [c for c in self._storage.get_children(task_id) if c.state != State.ABANDONED and str(c.id) not in dropped]

    def get_parent(self, task_id: TaskId) -> Optional[Task]:
        return self._storage.get_parent(task_id)


    def dep_edges(self, adopted: bool = False, closed: bool = False) -> list:
        """The dependency records that still SAY something — the declared edges and every discovered one
        open or confirmed. A record CLOSED unanswered asks nothing and waits on nothing: read as live by the
        dispatcher and the RESOLVE_BLOCK rule, it held a re-issued node's next block on a producer it no longer
        names (critic, 2026-09-27); `closed=True` adds those — what q_Dep counts. `adopted=True` reads E_Dep instead (§11.3, §15.5), what the
        plan's checks, the execution order and consumption read: every declared edge, and a discovered
        record only once its issuer CONFIRMED it and only if it closes no cycle. A provisional record is a
        report awaiting that answer — CHECK-2 ran over it, and a BLOCK naming two siblings that already
        consumed the blocked node read as a Dep cycle that froze every sibling of the plan (AUTO
        json_parser, 2026-09-25). A confirmed record that would close a cycle refutes the plan's ordering,
        which only a re-decomposition restores (`dep_order_refutations`), and still counts in q_Dep."""
        declared, stored = self._dep_records(ever=closed)
        if not closed:
            stored = [e for e in stored if not e.closed]
        if not adopted:
            return declared + stored
        live = {str(t.id) for t in self._storage.get_all_tasks()
                if t.state not in (State.CANCELLING, State.ABANDONED)}
        out = list(declared)
        for e in stored:
            if not e.provisional and str(e.to_id) in live and not _closes_cycle(out, e):
                out.append(e)
        return out

    def _dep_records(self, ever: bool = False) -> tuple[list, list]:
        """(declared, stored-only). DECLARED edges are DERIVED from criteria (§2): a criterion with
        `depends_on=X` means this task depends on X's output, with the criterion's description as the
        glue (anti-mock truth-maker) — Dep is criteria-content, not a standalone stored record.
        DISCOVERED edges (surfaced at runtime via BLOCK) remain stored. `ever`: the declared edges of cancelled
        consumers too — the plan that was, which q_Dep counts "whatever state it reaches later" (§15.4); filtered,
        a declared edge left the population when its consumer was cancelled and a discovered one never did
        (critic B1: 0.5 → 0.0)."""
        found = self._storage.get_dep_edges()      # discovered (BLOCK) / legacy-stored
        # A PAIR ALREADY DISCOVERED STAYS DISCOVERED (§15.5). "Declared" means declared at
        # admission, and the declared side is derived from the criteria as they stand NOW — so
        # writing the seam into the plan after a BLOCK exposed it moved the edge from the
        # denominator's discovered half into its declared half, and q_Dep — the share of the
        # discoveries that WERE made that the plan had declared in advance (§15.5; it is not a share
        # of S, which nobody observes) — rose for the repair.
        pair = lambda e: (str(e.from_id), str(e.to_id))
        records = [e for e in found if not e.refuted]     # a refuted record asks nothing and is no edge (§15.5)
        _discovered = {pair(e) for e in records if e.discovered}
        if ever:
            # …and q_Dep reads DISCOVERIES, not records: a record whose pair a version had declared before its first
            # BLOCK met a known dependency (declared), and a pair a BLOCK named first and the issuer refuted is in
            # neither half — a later declaration does not make it "declared before any BLOCK named it" (§15.5)
            _discovered = {pair(e) for e in records if e.discovered and not e.declared_first}
            _out = {pair(e) for e in found if e.refuted and not e.declared_first}
        edges = [
            DepEdge(from_id=c.depends_on, to_id=t.id, glue=c.description,
                    discovered=(str(c.depends_on), str(t.id)) in _discovered)
            for t in self._storage.get_all_tasks()
            if ever or t.state not in (State.CANCELLING, State.ABANDONED)  # cancellation excluded (§12.6)
            for c in t.spec.criteria
            if c.depends_on
        ]
        _have = {(str(e.from_id), str(e.to_id)) for e in edges}
        if ever:
            # …and the edges a LATER version took out: a dependency removed from its consumer's criteria
            # (`remove_dependency`) was declared all the same, and §15.5 has no clause taking a declared edge out
            # of the population — read off every version the log installed (Inv-7), not the criteria standing now
            for frm, to, glue in logged_declarations(self._storage.load_audit()):
                if (frm, to) not in _have:
                    _have.add((frm, to))
                    edges.append(DepEdge(from_id=TaskId(frm), to_id=TaskId(to), glue=glue,
                                         discovered=(frm, to) in _discovered))
            return ([e for e in edges if pair(e) not in _out],
                    [dataclasses.replace(e, discovered=pair(e) in _discovered) for e in records if pair(e) not in _have])
        return edges, [e for e in records if pair(e) not in _have]

    def subtree(self, root_id: Optional[TaskId] = None) -> list[Task]:
        """`root_id` and every node beneath it, by the parent edges the graph actually holds.

        The relation, not the spelling: scoping by an id prefix is true of the graphs
        `auto_decompose` builds and false of every graph built by hand, where a person names a node
        `parser` and the engine records its parent perfectly well. The prefix is honoured as well,
        so an id that spells its ancestry answers even before its parent edge exists.

        Cancellation is excluded for the same reason `get_active_children` excludes it: a cancelled
        node persists as provenance but has left the decomposition.
        """
        tasks = [t for t in self._storage.get_all_tasks()
                 if t.state not in (State.CANCELLING, State.ABANDONED)]
        if root_id is None:
            return tasks
        root, by_parent = str(root_id), {}
        for t in tasks:
            by_parent.setdefault(str(t.parent_id), []).append(t)
        seen, frontier = {root}, [root]
        while frontier:
            for child in by_parent.get(frontier.pop(), []):
                if str(child.id) not in seen:
                    seen.add(str(child.id))
                    frontier.append(str(child.id))
        seen |= {str(t.id) for t in tasks if str(t.id).startswith(root + ".")}
        return [t for t in tasks if str(t.id) in seen]

    def get_guard_context(self, task_id: TaskId) -> GuardContext:
        """What the FSM needs to decide a transition beyond the state itself: the rework counter and
        its cap, the reopen counter and its cap, and whether this terminal is consumed (§12.14).

        Assembled here because a guard that read the graph itself would make the transition depend on
        storage, and the point of the FSM is that it does not."""
        task = self._storage.get_task(task_id)
        if task is None:
            return GuardContext(iteration=0, max_iterations=DEFAULT_MAX_ITERATIONS)
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
        """§10.3: public node ⟺ a DELEGATION SEAM — the node's scope of responsibility differs
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
        """R′'s finality gate (§12.14): is this terminal CONSUMED — something rests on it, or the plan moved past it —
        so that reversing it would reverse its downstream cone. Read from the first logged moment of THIS terminal
        visit (`at`), and once logged it stands: a parent's FAIL after its DELIVER does not give the child back.

        - the AND leg (DONE only): the parent DELIVERED after the child settled — its aggregate rests on the pass;
        - the Dep leg (DONE only): an adopted consumer stood in work or was validated after the pass (the read is not
          logged, so "in work" is the visible over-approximation the canon chooses);
        - covered around: a re-admission after `at` gives a criterion of the parent's this node is mapped to a
          responsible child it did not have before, read off the logged admissions' mappings on either side (§12.14);
          on a graph whose admissions were not logged, a sibling re-ASSIGNed after `at` now carrying such a criterion
          — the canon's visible over-approximation (a sibling co-covering from before consumes nothing);
        - mapped to no criterion of the parent's current version.
        A root is consumed only through Dep. A settled cascade alone consumes nothing. Without the log (a bare graph)
        `at` is unknown and the legs read the standing state — the stricter side: a parent that ever delivered.
        Past consumption the recovery is the issuer's re-decomposition; within its own rework, the whole's
        executor repairs the artifact it delivers (a part read on that delivery fails there, §8.4)."""
        if task.state not in (State.DONE, State.ABANDONED):
            return True                    # no reopen question outside the quasi-terminals — fail-closed
        audit = self.audit
        at = audit.last_at(task.id, new_state=task.state) if audit is not None else -1
        after = (lambda tid, **kw: audit.last_at(TaskId(tid), **kw) > at) if audit is not None else None
        parent = self.get_parent(task.id)
        if task.state == State.DONE:
            if parent is not None and (after(parent.id, signal=Signal.DELIVER) if after else
                                       parent.iteration > 0 or parent.state in (State.VALIDATING, State.DONE)):
                return True
            built_on = {State.EXECUTING, State.BLOCKED, State.VALIDATING, State.REWORKING, State.DONE}
            for e in self.dep_edges(adopted=True):
                if e.from_id != task.id or (consumer := self.get_task(e.to_id)) is None:
                    continue
                if (audit.occupied_since(consumer.id, at) if audit is not None else {consumer.state}) & built_on:
                    return True
        if parent is None:
            return False
        mine = {m.criterion_name for m in parent.criterion_mappings if m.child_id == task.id}
        history = coverage_history(self._storage, audit, parent.id)
        then, later = coverage_at(history, at)
        me = str(task.id)
        if not mine or any(all(k != me for _, k in cov) for cov in later):
            return True                    # mapped to no criterion — now, or as a logged act after it settled left it
        if history:                        # …once logged, it stands: a later remap does not give the node back
            mine = {c for c, k in then if k == me} if then is not None else mine
            # covered around: a re-admission after it settled gave one of its criteria a child it did not have
            return any(c in mine and k != me and (c, k) not in (then or ()) for cov in later for c, k in cov)
        for m in parent.criterion_mappings:   # no admission logged: a sibling re-ASSIGNed after it — the proxy
            if m.criterion_name in mine and m.child_id != task.id and (sib := self.get_task(m.child_id)) is not None \
                    and sib.state not in (State.CANCELLING, State.ABANDONED) \
                    and (after(sib.id, signal=Signal.ASSIGN) if after else True):
                return True                # covered around by a re-admission after it settled
        return False

    def issuer_of(self, task_id: TaskId) -> Optional[AgentId]:
        """WHOSE the node's issuer signals are (§10.1): the parent's Del — or, at a root, the goal's
        issuer, recorded when the root was created. One owner, because the rule was written twice (the
        engine's `issuer_of` and the signal validator's role check) and the two have to agree.

        A root's issuer is the party that created it (§15.2), and it is NOT always the root's Del: a
        user who hands the whole goal to a system executor stays its customer. Reading it as Del(root)
        made that executor its own issuer — answering its own disputes and extending its own contract,
        the self-check §16.13 names as an IC violation. A root created before the record existed has
        none, and reads as it always did: its own Del ("at a self-assigned root the same agent holds
        the role")."""
        parent = self.get_parent(task_id)
        if parent is not None and parent.assignee:
            return parent.assignee
        recorded = self._storage.get_setting(root_issuer_key(task_id))
        if recorded:
            return AgentId(recorded)
        task = self.get_task(task_id)
        return task.assignee if task is not None else None

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
        children = self.get_active_children(task_id)  # solver/checks validate the ACTIVE decomposition
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
        would be validated on a contract it did not consent to (Inv-1)."""
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
        whatever the node has become since (a rework, a reopen, or a revision under §12.10), which is
        exactly the state the self-PASS gate then reads as current. A graph fact, owned here: the
        engine asks it, the signal pump asks it, and `stamped_with` compares a record against it."""
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
        """Void a recorded PASS whose delivery no longer stands (§12.10/§12.14: a re-ASSIGN "voids the
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



def root_of(tasks: list[Task]) -> Optional[Task]:
    """THE root of this project — the one node that carries the goal, or None before there is one.

    A project has exactly one. The derivation is the composition rule, not taste: the root carries the
    goal's criteria, so V(root) IS the goal's verdict, and the canon's one composition rule is
    V(parent) = AND(V(children)), which needs a parent. Two parentless nodes have no parent, so a
    project holding two has no object that says whether the PROJECT is done. Two tasks that share
    nothing compose to nothing — those are two projects; two that share something have the thing they
    share as their parent, and that parent is the root. There is no third case, and so no version of
    this where a second root means something.

    Read rather than stored, so it cannot disagree with the graph it describes; a free function over
    the node list rather than a method, because `Graph` is at its class-size limit and this is a shape
    question like `dep_scope` and `non_leaf_ids` beside it. It takes EVERY node, tombstones included:
    a cancelled root is still this project's root, and skipping it would re-open the very path the
    rule closes — refuse the goal, then build a fresh root beside its corpse."""
    roots = [t for t in tasks if t.parent_id is None]
    if not roots:
        return None
    # A graph written BEFORE the rule can hold several, and the measured run that motivated the rule
    # produced exactly that. Nothing here can decide which of them was the goal, so this at least
    # does not decide it DIFFERENTLY on each read: oldest first, ties by id. An arbitrary answer
    # that changes between calls is how one reader's "the root" stops being another's.
    return min(roots, key=lambda t: (t.created_at, str(t.id)))


def dep_order_refutations(graph: Graph) -> list:
    """The discovered records that ASK and sit on a cycle of live WAITS: contact found a consumer needs a
    producer that cannot finish before it (§15.5). The waits are E_Dep, the asking records and a parent's
    wait on its children (its PASS is their AND, Thm 1), each only while its producer is unfinished — a
    wait on a DONE node is over. So two blocks naming each other, or a block naming its own ancestor or
    itself, is on such a cycle (critic, 2026-09-27: read over E_Dep alone, the pair was asked by nobody).

    A record ASKS while it is open — the BLOCK that made it stands — or confirmed, not adopted, and both ends
    live. An open one is its blocked node's issuer's to answer (the BLOCK is his, Inv-8); a confirmed one
    refutes the plan's ORDER, which only its split's issuer can restore by re-decomposing."""
    asking, waits = _live_waits(graph)
    return [e for e in asking if e in waits and _closes_cycle(waits, e)]


def _live_waits(graph: Graph) -> tuple[list, list]:
    """(the discovered records that ASK, every live WAIT) — the population `dep_order_refutations` reads its cycles in."""
    adopted = graph.dep_edges(adopted=True)
    have = {(str(e.from_id), str(e.to_id)) for e in adopted}
    live = {str(t.id): t for t in graph.subtree(None)}
    unfinished = {i for i, t in live.items() if t.state != State.DONE}
    asking = [e for e in graph.dep_edges()
              if (str(e.from_id), str(e.to_id)) not in have and str(e.from_id) in live and str(e.to_id) in live]
    return asking, [e for e in adopted + asking if str(e.from_id) in unfinished] + [
        DepEdge(from_id=t.id, to_id=t.parent_id) for i, t in live.items()
        if i in unfinished and t.parent_id is not None]


def _reach(adj: dict, start: str) -> set:
    """Every node `adj` leads to from `start`, `start` included."""
    seen, stack = set(), [start]
    while stack:
        if (n := stack.pop()) not in seen:
            seen.add(n)
            stack.extend(adj.get(n, ()))
    return seen


def _closes_cycle(edges: list, e) -> bool:
    """Would adding `e` let its consumer reach its producer along `edges` (or is it its own producer)?"""
    adj: dict[str, list[str]] = {}
    for x in edges:
        adj.setdefault(str(x.from_id), []).append(str(x.to_id))
    return str(e.from_id) in _reach(adj, str(e.to_id))


def cycle_children(graph: Graph, parent_id, refuted: list) -> list[list[str]]:
    """The parent's live children each refuted wait's cycle runs through — every child on a path of live waits from the
    consumer's child back to the producer's, the waits read between the children that contain their ends — grouped
    where cycles share a child, each group sorted. A wait whose ends sit in one child, or outside the parent's
    children (a block naming its own ancestor), puts no group here: no merge of children restores it."""
    kids = {str(k.id) for k in graph.get_active_children(parent_id)}

    def child(x) -> str | None:
        """The parent's child that `x` is or sits under, or None."""
        t = graph.get_task(TaskId(str(x)))
        while t is not None and str(t.id) not in kids:
            t = graph.get_task(t.parent_id) if t.parent_id else None
        return str(t.id) if t is not None else None
    fwd: dict[str, set] = {}
    back: dict[str, set] = {}
    for w in _live_waits(graph)[1]:
        a, b = child(w.from_id), child(w.to_id)
        if a and b and a != b:
            fwd.setdefault(a, set()).add(b)
            back.setdefault(b, set()).add(a)
    groups: list[set] = []
    for e in refuted:
        p, c = child(e.from_id), child(e.to_id)
        if not (p and c) or p == c:
            continue
        g = (_reach(fwd, c) & _reach(back, p)) | {p, c}
        for h in [h for h in groups if h & g]:
            groups.remove(h)
            g |= h
        groups.append(g)
    return [sorted(g) for g in groups]

def dep_scope(graph: Graph, root_id: TaskId) -> tuple[list, dict[str, object]]:
    """The Dep pairs a node's plan checks quantify over, and the deadlines of their endpoints.

    ONE owner, because there were two and they disagreed. The cached computation
    (`Engine._recompute_checks`) handed the checks EVERY edge in the graph; the execution gate
    (`validation._l0_holes`) handed them only edges with both endpoints among the node's direct
    children. The checks themselves then silently dropped whatever fell outside the sibling set,
    so a Dep edge between two nodes under DIFFERENT parents — the ordinary shape of a seam once
    a plan has two branches — was examined by nobody: `list_holes` said `count: 0`, the plan gate
    admitted execution, and `check_dag` over the whole graph named the very cycle those surfaces
    called clean. The canon quantifies CHECK-2 and CHECK-3 over Dep itself (§9.5), so the
    population is the SUBTREE: at the root that is the whole relation, and below it the seams
    that decomposition owns. Reported at the node whose plan declares them.
    """
    inside = {str(t.id): t for t in graph.subtree(root_id)}
    known = {str(t.id) for t in graph.subtree(None)}
    edges = []
    for e in graph.dep_edges(adopted=True):
        ends = (str(e.from_id), str(e.to_id))
        if all(x in inside for x in ends):
            edges.append(e)
        elif any(x in inside for x in ends) and not all(x in known for x in ends):
            # A DANGLING endpoint is not "outside this population", it is a plan naming a producer
            # that does not exist — the node's own defect, and the node's own checks must see it.
            # Filtering purely on membership swallowed it: a criterion whose `depends_on` was a LIST
            # (the malformed value that ended a live run) stringifies to an id no node has, so the
            # edge silently left every population and the contract carrying it was stored clean.
            # Skipping an edge because it is outside a subtree is right; skipping one because its
            # endpoint is nowhere is the same "not examined by anybody" this function exists to end.
            edges.append(e)
    # EVERY LIVE DEADLINE, a supplied default included: §9.5's CHECK-3 is over every Dep pair, and §2.5 lets an
    # implementation write a default inside the parent's — it does not waive §2.7 for it. Exempting them left every
    # undated plan's Dep time guard inert while the clock still enforced deadlines written equal along a chain (critic
    # over session 475ba784; every door now writes them ordered, `mutations.Schedule`). A SETTLED node's
    # deadline orders nothing still to come, and CHECK-3 reads no edge with a settled end (§11.5).
    return edges, {i: (None if t.state in TERMINAL_STATES else t.deadline)
                   for i, t in inside.items()}


def standing_split(graph, node):
    """(node, its active children) with the node's mappings onto those children only — the split as it stands (§12.6:
    a settled cancellation takes its child out of the plan, and the battery reads the active children). A mapping left
    onto a child out of the plan covers nothing: read as coverage it was an "invalid mapping" no repair but a whole
    re-decomposition cleared, while the admission, reading the active children, had already covered around it."""
    kids = graph.get_active_children(node.id)
    ids = {str(k.id) for k in kids}
    return dataclasses.replace(node, criterion_mappings=tuple(
        m for m in node.criterion_mappings if str(m.child_id) in ids)), kids


def non_leaf_ids(graph: Graph, children: list[Task]) -> set[str]:
    """Which of these children decompose further — the fact CHECK-6 needs and a single split does
    not carry (§9.5 quantifies over LEAVES). A node that splits is accountable through its own
    children; demanding an executor for it reads Del as a label rather than as §2's per-node
    accountability.

    A derived question over the public surface, so it lives beside the graph rather than on it: a
    class that answers every question ABOUT a thing is how a facade stops being one.
    """
    return {str(c.id) for c in children if graph.get_active_children(c.id)}


def logged_declarations(log: list) -> list[tuple[str, str, str]]:
    """(producer, consumer, glue) for every `depends_on` criterion of every packet version the log (`load_audit` rows)
    installed."""
    out = []
    for row in log:
        if row.get("rejected") or not row.get("spec"):
            continue
        try:
            crits = json.loads(row["spec"]).get("criteria") or []
        except (TypeError, ValueError, AttributeError):
            continue
        out += [(str(c["depends_on"]), str(row.get("task_id")), str(c.get("description") or ""))
                for c in crits if isinstance(c, dict) and c.get("depends_on")]
    return out
