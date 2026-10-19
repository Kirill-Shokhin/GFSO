"""Mutation -> G'. Returns affected child ids for cascade."""
from __future__ import annotations

import dataclasses
import logging
from datetime import datetime, timedelta
from typing import Optional

from gfso.core.types import (
    TaskId, Task, State, MutationType, DoneReason, RevisionReason,
    MutateGraph, CriterionMapping, DepEdge, TERMINAL_STATES,
)


def _type_revision(task: Task, effect: MutateGraph, criteria_changed: bool, del_changed: bool) -> None:
    """§15.4 causal typing — the ONE place a revision's reason lands on the node's metric flags.
    Untyped revisions keep each metric's documented bias (q_T under-, q_Del over-approximation);
    a typed reason narrows to the canon member: SPEC_DEFECT → q_T, CAPABILITY_MISMATCH → q_Del."""
    r = effect.revision_reason
    if criteria_changed and r == RevisionReason.SPEC_DEFECT:
        task.spec_defect_criteria_change = True
    if del_changed and r is not None:
        task.reassign_reason_typed = True
        if r == RevisionReason.CAPABILITY_MISMATCH:
            task.reassign_capability_mismatch = True
from .model import Graph, logged_declarations
from gfso.core.types import settled_positive
from gfso.config import default_deadline_s

#: How far inside its parent's deadline a child's DEFAULT lands (§4.5 item 6 wants strictly inside;
#: what the parent needs after the child is its own aggregation and verdict, not a share of the run).
CHILD_MARGIN = _CHILD_MARGIN = timedelta(minutes=5)

log = logging.getLogger(__name__)


class InvariantViolation(Exception):
    pass


def apply(graph: Graph, effect: MutateGraph) -> list[TaskId]:
    """Apply a mutation to the graph. Returns affected child task_ids for cascade."""
    task = graph.get_task(effect.task_id)

    match effect.mutation:
        case MutationType.SET_STATE:
            if task is not None and task.state == State.BLOCKED and effect.new_state != State.BLOCKED:
                _close_unanswered_records(graph, task.id)
            return _set_state(graph, task, effect)
        case MutationType.INCREMENT_ITERATION:
            return _increment_iteration(graph, task)
        case MutationType.CREATE_TASK:
            return _create_task(graph, effect)
        case MutationType.APPLY_SPEC:
            return _apply_spec(graph, task, effect)
        case MutationType.STORE_CHECK_RESULTS:
            return []
        case MutationType.STORE_RECOMMENDATION:
            return []
        case MutationType.RECORD_DEP:
            return _record_dep(graph, effect)
        case MutationType.ADJUDICATE_DEP:
            return _adjudicate_dep(graph, effect)
        case MutationType.REOPEN:
            return _reopen(graph, task, effect)
        case _:
            log.warning(f"unhandled mutation type: {effect.mutation}")
            return []


def _passed_result_key(task_id) -> TaskId:
    """Where a reopened pass keeps the logged result it passed on — what "failed as delivered" compares against."""
    return TaskId(f"{task_id}#reopened-pass-result")


def _a_reopened_pass_meets_its_fresh_verdict(graph: Graph, task: Task, new_state: State, reason) -> None:
    """R′ × q_V (§12.14/§15.4): a DONE(pass/auto) node reopened under the SAME criteria whose FRESH run FAILs the
    re-delivered logged artifact = the old pass refuted by contact — exactly the pass→later-fail member, no new
    machinery. "As delivered": a fresh run on another artifact refutes nothing of the old PASS, so the delivery it
    failed must be the one that passed (its logged result). The marker is consumed at the first fresh verdict either
    way (a fresh pass corroborates)."""
    failed = new_state == State.REWORKING or (new_state in (State.DONE, State.ESCALATED) and reason == DoneReason.FAIL)
    if failed and (graph._storage.get_critique(_passed_result_key(task.id))
                   == (graph._storage.get_deliver_result(task.id) or "")):
        task.false_positive = True
    if failed or (new_state == State.DONE and reason in (DoneReason.PASS, DoneReason.AUTO_PASS)):
        task.reopened_from_pass = False


def _set_state(graph: Graph, task: Optional[Task], effect: MutateGraph) -> list[TaskId]:
    if task is None:
        log.error(f"task {effect.task_id} not found for SET_STATE")
        return []

    new_state = effect.new_state
    if new_state is None:
        log.error(f"SET_STATE without new_state for {effect.task_id}")
        return []

    # Invariant 1: criteria immutability
    # If spec is being changed (e.g. via ACCEPT_CHALLENGE), validate
    if effect.spec is not None and task.spec.criteria != effect.spec.criteria:
        raise InvariantViolation(
            f"criteria immutability violated for {effect.task_id}: "
            f"criteria change requires revision (re-ASSIGN, §12.3 Inv-1) or the CHALLENGE channel"
        )

    # Track challenge for q_T metric
    if new_state == State.CHALLENGED:
        task.was_challenged = True

    if task.reopened_from_pass:
        _a_reopened_pass_meets_its_fresh_verdict(graph, task, new_state, effect.done_reason)

    task_was = task.state
    if task.state != new_state:
        task.state_entered_at = datetime.now()   # Inv-5: every state carries its own clock
    task.state = new_state

    if effect.done_reason is not None:
        task.done_reason = effect.done_reason
    # …and a node LEAVING the issuer's waiting state into live work carries no settlement reason any
    # more. ESCALATED(FAIL) records that the node's own FAIL came to rest there; once the issuer
    # answers with a revision the FAIL is no longer standing, and a reason left on the node would
    # keep it in the standing-FAIL populations (q_D, `false_fail_share`) and would be read again if
    # the node later settled for an unrelated cause.
    elif task_was == State.ESCALATED and new_state == State.OFFERED:
        # …only into WORK. A node the issuer takes back for another attempt carries no standing FAIL
        # any more. A node he CLOSES does: it goes ESCALATED → CANCELLING → ABANDONED, and clearing
        # the reason on the way through would have made the same settlement read two different ways
        # in `false_fail_share` and q_D depending on whether the issuer acted or stayed silent —
        # which is the opposite of what a measurement of issuer behaviour should do.
        task.done_reason = None

    graph.save_task(task)

    # Cascade fires on CANCEL, i.e. on ENTERING CANCELLING (§12.6: the protocol sends CANCEL to every
    # descendant — each child then runs its own CANCEL→CANCELLING→ABANDONED handshake). Children already
    # settling (CANCELLING) or terminal are skipped.
    if new_state == State.CANCELLING:
        # …AND IT DOES NOT STOP AT A SETTLED CHILD. The cascade used to hand CANCEL to the direct
        # children and rely on each of them to carry it further, so a live grandchild under a child
        # that had already DONE or ABANDONED was never reached: it went on working, under its own
        # contract, for a goal that no longer exists — the ballast-or-stranded-plan case §12.5
        # names, and the one the cascade exists to prevent. A terminal node passes the signal on
        # without taking it: it is settled, and nothing here unsettles it (Inv-7).
        out, seen = [], set()
        frontier = list(graph.get_children(effect.task_id))
        while frontier:
            c = frontier.pop()
            if str(c.id) in seen:
                continue
            seen.add(str(c.id))
            if c.state in TERMINAL_STATES:
                frontier.extend(graph.get_children(c.id))
            elif c.state != State.CANCELLING:
                out.append(c.id)
        return out

    return []


def _apply_spec(graph: Graph, task: Optional[Task], effect: MutateGraph) -> list[TaskId]:
    """Apply a renegotiated spec via the sanctioned CHALLENGE channel (ACCEPT_CHALLENGE, §11.2/§14.3).

    The ONLY in-place spec change permitted to alter criteria — it is the *pre-acceptance* negotiation
    (state CHALLENGED, executor has not yet ACCEPTed), distinct from the Inv-1-guarded default path
    where a post-acceptance criteria change requires CANCEL + re-ASSIGN. §14.3 shows ACCEPT_CHALLENGE
    removing criterion c_B2 — so this channel legitimately rewrites criteria/ACCEPTED_RISKS.
    """
    if task is None:
        log.error(f"APPLY_SPEC for a task that is not there: {effect.task_id}")
        return []
    # `spec is None` MEANS KEEP THE CONTRACT — the same rule this function already applies to
    # `assignee`, `deadline` and `max_iterations`. Read as an error it broke the one move §12.5
    # names by name: out of ESCALATED the issuer may re-ASSIGN without restating a contract he is
    # not disputing, to raise the rework bound or give a live deadline. The node went to OFFERED
    # and NOTHING was applied — no new version, no new budget, no new deadline — so the issuer's
    # only work-keeping move was admitted, logged as accepted, and inert: one more round and the
    # node escalated again, for ever. Found by an outside reviewer with a reproduction.
    _type_revision(task, effect,
                   criteria_changed=(effect.spec is not None
                                     and task.spec.criteria != effect.spec.criteria),
                   del_changed=effect.assignee is not None and effect.assignee != task.assignee)
    # §12.4 admits ASSIGN from VALIDATING, and §12.10 prices it exactly: the issuer may revise with the
    # delivery in hand, "at the price of a logged event, a voided DELIVERY (no verdict has been
    # emitted on that path) and a fresh consent and re-delivery". Voiding it is what keeps that
    # price real — otherwise a recorded PASS from the pre-revision delivery still satisfies the
    # verifier ≠ executor gate (§10.3), and the node could complete on a verdict about a contract
    # that no longer exists.
    if task.state == State.VALIDATING:
        graph.void_pending_pass(task.id, "the contract was revised while the delivery was pending "
                                         "(re-ASSIGN from VALIDATING, §12.10)")
    # The contract generation moves with the revision, and this is what a verdict is stamped against:
    # voiding the RECORD alone loses the race to a validator that is still running on the superseded
    # delivery and lands its PASS afterwards, stamped with unchanged (iteration, reopens).
    task.revisions = task.revisions + 1
    # THE REWORKING BUDGET IS THIS VERSION'S, so a new version starts it over (Φ3, §12.15):
    # `max_iterations` is the issuer's forecast of rounds for ONE contract, and counting a previous
    # contract's refusals against a repaired one spends the new forecast before the work begins —
    # the exhaustion then reads as "this plan cannot be met" when what was met was the old plan's
    # budget. The issuer sizes it on each version, which is what keeps the §16.12 row honest.
    # EVERY NEW VERSION RESETS THE REWORKING BUDGET (§12.15), one that changes no field included: ACCEPT_CHALLENGE installs a
    # packet exactly as an ASSIGN does (§11.3), and "the counters are not finiteness devices" — the fresh draws are the
    # issuer's accepting version's to grant (Φ3), the dispute loop bounded by the deadline (Φ2). Reset only where a
    # field moved, the engine closed a loop the canon leaves to the issuer and to the clock (critic B1, F2).
    task.iteration = 0
    if effect.spec is not None and effect.spec != task.spec:
        # A NEW CONTRACT IS A CHANGED PLAN, whichever signal installs it: the Level-2 verdicts over this
        # node's own split and over its parent's were read against the old criteria. A revision staled
        # them (`Engine.revise`); ACCEPT_CHALLENGE — the issuer's answer to a dispute, which §11.3 has install
        # a packet exactly as an ASSIGN does — did not, so a child's weakened criteria stood under a
        # parent verdict no checker had read (reproduced).
        task.verified = False
        if task.parent_id is not None and (parent := graph.get_task(task.parent_id)) is not None                 and parent.verified:
            parent.verified = False
            graph.save_task(parent)
    if effect.spec is not None:
        task.spec = effect.spec
    # THE DEADLINE IS A PACKET FIELD, and Inv-1 names it among the four a revision exists to change.
    # It was write-once: set at creation and unreachable afterwards, so a schedule that had moved
    # could not be repaired — the only exit left was CANCEL, which cascades, which is precisely what
    # Inv-1 says a revision must not do. `None` means KEEP, exactly as it does for `assignee` above:
    # a revision that does not mention the date is not a revision that clears it. (Clearing one has
    # no carrier and is not claimed here — a deadline-less node is not defective, `formal/README` #6.)
    task.deadline, task.deadline_supplied = version_deadline(graph, effect.deadline, task, supplied=effect.deadline_supplied)
    # …AND THE REWORKING BOUND, for the same reason. Running past the budgeted attempts has two
    # readings — the plan is wrong, or the forecast was — and only the issuer can say which.
    # With the bound unrevisable the engine answered for them, and a missed forecast cost a
    # terminal node (at a root: a whole second root with no memory of the refusals).
    if effect.max_iterations is not None:
        task.max_iterations = effect.max_iterations
    task.done_reason = None  # re-authored → a fresh contract, no longer a ABANDONED tombstone (clears stale flag)
    # a criteria change strands this node's own mappings that point at a now-removed criterion → prune them here
    # (logged, part of APPLY_SPEC) so no stale mapping persists; the now-unmapped child surfaces via CHECK-1b.
    _valid = {c.name for c in task.spec.criteria}
    # …AND THE MAPPINGS WHOSE CHILD IS GONE. A cancelled child leaves the parent pointing at a
    # tombstone, and CHECK-1 reads that as an invalid mapping — correctly, and forever: measured on
    # the human door 2026-08-21, a coverage hole that `map_criterion` could only add beside,
    # `edit_criteria` did not touch, `revise` refused, and the person escaped by guessing an
    # undocumented rebuild that wiped every OTHER mapping too. A re-author is the node's own act on
    # its own coverage, so it prunes what no longer exists — the criterion it covered becomes an
    # honest, fixable CHECK-1 hole instead of a permanent one.
    _live = {str(t.id) for t in graph.get_active_children(task.id)} if graph is not None else None
    _dead = (lambda m: _live is not None and str(m.child_id) not in _live)
    if any(m.criterion_name not in _valid or _dead(m) for m in task.criterion_mappings):
        task.criterion_mappings = tuple(m for m in task.criterion_mappings
                                        if m.criterion_name in _valid and not _dead(m))
    if effect.assignee is not None:  # reassign (Del change) via the same pre-acceptance channel
        if effect.assignee != task.assignee:
            task.was_reassigned = True  # q_Del
        task.assignee = effect.assignee
    graph.save_task(task)
    # covers on a re-author: the child (re)declares which parent criteria it covers (§2), appended (dedup) —
    # so a mapping can be set/preserved through re-ASSIGN, not only at CREATE_TASK.
    if effect.covers and task.parent_id:
        parent = graph.get_task(task.parent_id)
        if parent is not None:
            seen = {(m.criterion_name, m.child_id) for m in parent.criterion_mappings}
            new = tuple(CriterionMapping(c, task.id) for c in effect.covers if (c, task.id) not in seen)
            if new:
                parent.criterion_mappings = parent.criterion_mappings + new
                graph.save_task(parent)
    return []


def _reopen(graph: Graph, task: Optional[Task], effect: MutateGraph) -> list[TaskId]:
    """R′ REOPEN (§12.14): the bookkeeping half of the gated quasi-terminal exit. The FSM guard
    (finality-gate + counter) has already admitted the edge in the SAME atomic step; here the
    reopen is SPENT and the stale verdict dropped:

    - `reopens += 1` — ONE sign-agnostic counter (DONE→OFFERED and ABANDONED→OFFERED alike, Inv-5);
    - `done_reason = None` — V=pass is NOT carried forward: the node re-earns its verdict through
      ACCEPT→EXECUTE→DELIVER→VALIDATE (anti-fake: OFFERED, not resurrection);
    - `reopened_from_pass` marks a pass-terminal reopened under the SAME criteria — if the fresh
      run then FAILs, the old pass is refuted: q_V's pass→later-fail member (§15.4);
    - the recorded independent verdict goes STALE by generation stamp, not deletion (the record is
      provenance; `record_exec_verdict` stamps (iteration, reopens), the self-PASS gate and the
      metrics compare both) — an old PASS verdict cannot re-open the verifier≠executor gate;
    - an optional new spec/assignee/covers rides along exactly like a revision (same re-ASSIGN
      semantics, §12.3 Inv-1); spec=None = reopen under the standing contract.

    The compensating event is written FORWARD (this mutation + SET_STATE→OFFERED in the log);
    nothing is rewritten (Inv-7)."""
    if task is None:
        log.error(f"task {effect.task_id} not found for REOPEN")
        return []
    was_pass = settled_positive(task)
    old_criteria = task.spec.criteria
    _type_revision(task, effect,
                   criteria_changed=effect.spec is not None and old_criteria != effect.spec.criteria,
                   del_changed=effect.assignee is not None and effect.assignee != task.assignee)
    task.reopens += 1
    task.done_reason = None
    task.iteration = 0        # a reopen is a new packet version too (Φ3, §12.15)
    task.deadline, task.deadline_supplied = version_deadline(graph, effect.deadline, task, spec=effect.spec,
                                                             supplied=effect.deadline_supplied)
    if effect.max_iterations is not None:
        task.max_iterations = effect.max_iterations
    # THE MAPPINGS THAT POINT AT NOTHING GO, as they do on any other re-authorship: a reopened node
    # whose child was cancelled while it sat terminal kept covering its criterion through a
    # tombstone, and CHECK-1 read that as covered.
    _live = {str(t.id) for t in graph.get_active_children(task.id)} if graph is not None else None
    _dead = (lambda m: _live is not None and str(m.child_id) not in _live)
    if effect.spec is not None:
        task.spec = effect.spec
    _valid = {c.name for c in task.spec.criteria}
    if any(m.criterion_name not in _valid or _dead(m) for m in task.criterion_mappings):
        task.criterion_mappings = tuple(m for m in task.criterion_mappings
                                        if m.criterion_name in _valid and not _dead(m))
    if effect.assignee is not None and effect.assignee != task.assignee:
        task.was_reassigned = True  # q_Del: a Del change is a Del change, reopen or not
        task.assignee = effect.assignee
    task.reopened_from_pass = was_pass and task.spec.criteria == old_criteria
    if task.reopened_from_pass:
        graph._storage.store_critique(_passed_result_key(task.id), graph._storage.get_deliver_result(task.id) or "")
    graph.save_task(task)
    if effect.covers and task.parent_id:
        parent = graph.get_task(task.parent_id)
        if parent is not None:
            seen = {(m.criterion_name, m.child_id) for m in parent.criterion_mappings}
            new = tuple(CriterionMapping(c, task.id) for c in effect.covers if (c, task.id) not in seen)
            if new:
                parent.criterion_mappings = parent.criterion_mappings + new
                graph.save_task(parent)
    return []


def _record_dep(graph: Graph, effect: MutateGraph) -> list[TaskId]:
    """BLOCK named an undeclared prerequisite node → provisional discovered-Dep edge (§11.3/§15.5).

    Two-phase record: this registers provisional (provenance = the BLOCK event, Thm 11); RESOLVE_BLOCK
    adjudicates. A cyclic discovered edge is RECORDED (a Dep cycle is the FM-5 finding to surface, §9.5,
    not reject). Idempotent per (from, to)."""
    if effect.dep_from is None:
        log.error(f"RECORD_DEP without dep_from for {effect.task_id}")
        return []
    if graph.get_task(effect.dep_from) is None:
        # §11.3: only a producible in-scope artifact (an existing candidate producer node) promotes to a Dep
        # edge; a non-node blocker is the FM-5 currency line — nothing to record.
        log.warning(f"RECORD_DEP: blocker {effect.dep_from} is not a node — no edge (FM-5 line)")
        return []
    # ONE RECORD PER PREREQUISITE PER NODE — and a repeat REOPENS its adjudication (§15.5), asked FIRST: a pair a
    # BLOCK named before any declaration stays a discovery once declared, and its repeated BLOCK reopens it (critic 4). The
    # record was simply dropped, so a blocker the issuer had answered and the executor met AGAIN
    # stayed settled on the old answer: the latest answer governs, which means the latest report
    # puts the question back. The edge is not duplicated; it returns to provisional.
    for e in graph._storage.get_dep_edges():
        if e.from_id == effect.dep_from and e.to_id == effect.task_id:
            if not e.provisional:              # confirmed, closed or refuted: this report asks again
                _rewrite(graph, e, glue=e.glue or effect.glue, provisional=True, closed=False, refuted=False)
            return []
    # …AND A PREREQUISITE THE PLAN ALREADY DECLARED IS NOT A DISCOVERY (§15.5: "declared" means
    # declared BEFORE the first record of its discovery). BLOCK records on any node it names, so a
    # blocker on an edge the plan had declared all along — the ordinary case of a producer simply
    # running late — was stamped discovered, and q_Dep fell to zero for a plan that had declared it.
    # The metric asks, of the discoveries that were made, how many the plan had declared in advance
    # (§15.5); this edge was declared, and nothing about it was discovered.
    _blocked = graph.get_task(effect.task_id)
    if _blocked is not None and any(str(c.depends_on) == str(effect.dep_from)
                                    for c in _blocked.spec.criteria if c.depends_on):
        return []
    graph._storage.add_dep_edge(_first_record(graph, effect.dep_from, effect.task_id, effect.glue, provisional=True))
    return []


def _rewrite(graph: Graph, e: DepEdge, **change) -> None:
    """One record changed in place, every other field carried — a fresh DepEdge per write dropped what it did not name."""
    graph._storage.remove_dep_edge(e.from_id, e.to_id)
    graph._storage.add_dep_edge(dataclasses.replace(e, **change))


def _first_record(graph: Graph, src: TaskId, to: TaskId, glue: str, **kw) -> DepEdge:
    """A pair's FIRST record, made at the BLOCK that first names it: whether a version already installed had declared
    the pair is fixed now, the one moment the order "declared before any BLOCK named it" is visible (§15.5)."""
    known = {(f, t) for f, t, _g in logged_declarations(graph._storage.load_audit())}
    return DepEdge(src, to, discovered=True, glue=glue, declared_first=(str(src), str(to)) in known, **kw)


def _close_unanswered_records(graph: Graph, task_id: TaskId) -> None:
    """The node left BLOCKED, and what its BLOCK recorded that nobody answered no longer asks (§15.5: closed
    without adjudication — still counted). RESOLVE_BLOCK adjudicates before the node moves, so only records
    left by a re-ASSIGN, a CANCEL or the block's bound reach here. Read as standing, such a record came back
    with the node's NEXT block and was blamed for it (critic, 2026-09-27)."""
    for e in graph._storage.get_dep_edges():
        if str(e.to_id) == str(task_id) and e.provisional:
            _rewrite(graph, e, provisional=False, closed=True)


def _adjudicate_dep(graph: Graph, effect: MutateGraph) -> list[TaskId]:
    """RESOLVE_BLOCK adjudicates the provisional discovered-Dep(s) targeting this task (§15.5):
    no payload → CONFIRM ALL (provisional=False); dep_external → REFUTE ALL (blocker non-producible —
    the FM-5 line, not a Dep); a source set (dep_froms / legacy dep_from) → the corrected FULL set
    (SET semantics, mirroring decompose's mappings reconciliation): unlisted provisionals are refuted,
    each listed source is written confirmed (glue kept where the source matches a provisional).
    A refuted record is KEPT, marked: deleted, the order of its BLOCK and a later declaration of the pair was lost
    (§15.5 counts a pair named by a BLOCK before any declaration as a discovery for ever after).
    An escalated-unresolved provisional is simply never adjudicated — it stays counted (the hole
    was real)."""
    # the records the answer reaches: the block's open ones — and, answered by a re-ASSIGN or CANCEL, those its lapse
    # closed unanswered (`dep_unanswered`); a refuted one is answered already
    provisional = [e for e in graph._storage.get_dep_edges() if e.to_id == effect.task_id
                   and (e.provisional or (effect.dep_unanswered and e.closed and not e.refuted))]
    if effect.dep_external:
        for e in provisional:
            _rewrite(graph, e, provisional=False, refuted=True)
        return []
    corrected = effect.dep_froms or ((effect.dep_from,) if effect.dep_from else ())
    if corrected:
        listed = {str(s) for s in corrected}
        default_glue = provisional[0].glue if provisional else ""
        for e in provisional:
            if str(e.from_id) not in listed:
                _rewrite(graph, e, provisional=False, refuted=True)
        records = {str(e.from_id): e for e in graph._storage.get_dep_edges() if str(e.to_id) == str(effect.task_id)}
        for src in dict.fromkeys(corrected):
            if graph.get_task(src) is None:
                continue
            if (e := records.get(str(src))) is None:
                graph._storage.add_dep_edge(_first_record(graph, src, effect.task_id, default_glue, provisional=False))
            elif e.provisional or e.refuted or e.closed:
                _rewrite(graph, e, provisional=False, refuted=False, closed=False)
        return []
    for e in provisional:  # confirm
        _rewrite(graph, e, provisional=False, closed=False)
    return []


def _increment_iteration(graph: Graph, task: Optional[Task]) -> list[TaskId]:
    if task is None:
        return []
    task.iteration += 1
    graph.save_task(task)
    return []


def with_its_seams(old, new, severing: tuple = ()):
    """`new` with every Dep seam of `old` it omits carried over: an edge is not deleted by omission (a `dep__*` criterion
    a wholesale replacement leaves out), only by naming the producer it severs (`severing`, `remove_dependency`). One
    owner: a revision writes this contract, and an admission that revises its node's contract checks this one (critic
    r9: the battery read the contract without the carried seam the revision then wrote)."""
    if new is None or old is None or not old.criteria:
        return new
    named, cut = {c.name for c in (new.criteria or ())}, set(severing)
    carry = tuple(c for c in old.criteria if c.depends_on and c.name not in named and c.depends_on not in cut)
    return dataclasses.replace(new, criteria=tuple(new.criteria or ()) + carry) if carry else new


def producers_of(spec) -> tuple[str, ...]:
    """The nodes whose results this contract's criteria reference — its producers along Dep (§2.7)."""
    return tuple(str(c.depends_on) for c in (spec.criteria if spec is not None else ()) if c.depends_on is not None)


#: The finest margin the writer tries before it gives up on an order: one clock tick of the log.
_TICK = timedelta(seconds=1)


class Schedule:
    """THE ONE WRITER of an ordered deadline nobody typed (§2.5 with §2.7), for every door that installs a packet with
    a Dep — the admission, a child created into a split, a revision adding a producer, a reopen, the machine issuer's
    re-issue and promotion. Each wrote its own, and each saw a different part of the graph: equal defaults down a
    chain, a node lifted over its own consumers, a promoted producer due after the node it unblocks (critic r2, F3).

    The act is every node it gives a version: id → (typed deadline or None, the producers it reads, the supplied
    deadline it stands on now or None). Its bounds: the parent's deadline while it is ahead (§11.5 — past it, no
    default exists inside it and the issuer types one, §12.16), the producers and consumers standing outside the act,
    and each other. One pass in Dep order: backward, each untyped node's latest — inside the parent's and before each
    consumer's, one margin each; forward, its earliest — one margin after each producer and one ahead of now (shorter is
    no contract anybody meets); it keeps the deadline it stands on where that still fits, else takes `want` (the default
    span, or the issuer's own wish) clamped between the two. By order, not by recursion, so the answer is the same
    however the act lists its nodes (critic over F3). The margin halves down to one tick before the writer admits no
    order exists; then the ceilings hold — the parent's and the consumers' — and the producers' floors give way, the
    crossing standing at the producer's edge as CHECK-3's flag for the issuers whose deadlines bound it (§11.5). Only a
    live deadline ahead bounds anything: a settled end orders nothing to come (§11.5), a spent one is re-issued."""

    def __init__(self, graph: Graph, parent: Optional[Task], act: dict, want: Optional[datetime] = None):
        self.now = datetime.now()
        self.graph = graph
        self.act = {str(k): (typed, tuple(str(p) for p in reads), keep) for k, (typed, reads, keep) in act.items()}
        dated = parent is not None and parent.deadline is not None
        self.spent = dated and parent.deadline <= self.now
        self.due = parent.deadline if dated and not self.spent else None
        span = default_deadline_s()
        self.want = want or (self.now + timedelta(seconds=span) if span else None)
        edges = graph.dep_edges(adopted=True) if graph is not None else []
        self.reads = {x: set(r) | {str(e.from_id) for e in edges if str(e.to_id) == x and e.discovered}
                      for x, (_t, r, _k) in self.act.items()}
        self.read_by = {x: {y for y in self.act if x in self.reads[y]}
                        | {str(e.to_id) for e in edges if str(e.from_id) == x and str(e.to_id) not in self.act}
                        for x in self.act}
        self.order = self._in_dep_order()

    def standing(self, tid: str) -> Optional[datetime]:
        """A node outside this act: its deadline, where it still orders something — live, ahead, unsettled."""
        t = self.graph.get_task(TaskId(tid)) if self.graph is not None else None
        return t.deadline if (t is not None and t.state not in TERMINAL_STATES and t.deadline is not None
                              and t.deadline > self.now) else None

    def _in_dep_order(self) -> Optional[list]:
        """The act's nodes, every producer before its consumers — None for a ring (CHECK-2's refusal, not ours)."""
        out, left = [], set(self.act)
        while left:
            ready = sorted(x for x in left if not (self.reads[x] & left))
            if not ready:
                return None
            out += ready
            left -= set(ready)
        return out

    def _solve(self, margin: timedelta, lead: timedelta, want: Optional[datetime], free: bool,
               outside: frozenset = frozenset({"floors", "ceilings"})) -> Optional[dict]:
        """Each variable node's deadline at this margin — the untyped, or every one of the act's (`free`) — or None
        where no choice orders every edge it holds. The edges among the act's own variable nodes and the parent's
        bound always hold; those to ends the act does not choose hold as `outside` says — their "floors" (producers),
        their "ceilings" (consumers). A deadline the node already stands on is kept where it still fits."""
        if self.order is None:
            return None
        var = {x for x, (typed, _r, _k) in self.act.items() if free or typed is None}
        fixed = lambda y: (None if y in var else self.act[y][0]) if y in self.act else self.standing(y)
        latest: dict = {}
        for x in reversed(self.order):
            if x in var:
                bounds = [self.due - margin] if self.due else []
                bounds += [latest[c] - margin for c in self.read_by[x] if c in var]
                if "ceilings" in outside:
                    bounds += [d - margin for c in self.read_by[x] if c not in var and (d := fixed(c))]
                latest[x] = min(bounds, default=datetime.max)
        out: dict = {}
        for x in self.order:
            if x not in var:
                continue
            after = [out[p] for p in self.reads[x] if p in var]
            if "floors" in outside:
                after += [d for p in self.reads[x] if p not in var and (d := fixed(p))]
            keep = None if free else self.act[x][2]
            if keep is not None and max([self.now] + after) < keep <= latest[x]:
                out[x] = keep            # it stands on a deadline that still fits: kept, short or not
                continue
            earliest = max([self.now + lead] + [d + margin for d in after])
            if earliest > latest[x]:
                return None
            out[x] = min(max(want, earliest), latest[x]) if want else latest[x]
        return out

    def defaults(self) -> dict:
        """The chosen deadline of every node of the act with none typed — None where nothing lies ahead to choose.
        Where no order holds every edge, the edges to ends the act does not choose give way — first the producers',
        then the consumers' too — the act's own edges and the parent's bound never; each crossing so written stands as
        CHECK-3's flag. Past that, the parent's bound alone."""
        untyped = [x for x, (typed, _r, _k) in self.act.items() if typed is None]
        if self.want is None or self.spent:
            return dict.fromkeys(untyped)
        for outside in (frozenset({"floors", "ceilings"}), frozenset({"ceilings"}), frozenset()):
            margin = _CHILD_MARGIN
            while margin >= _TICK:
                if (out := self._solve(margin, _CHILD_MARGIN, self.want, free=False, outside=outside)) is not None:
                    return out
                margin /= 2
        top = min(self.want, self.due - _CHILD_MARGIN) if self.due else self.want
        return dict.fromkeys(untyped, top if top > self.now else None)

    def orderable(self) -> bool:
        """Does some choice of the deadlines this act leaves free (the untyped) order every edge, strictly (§11.5's
        gate)? An edge whose two ends are both fixed is no choice's to order (critic r3 over F3: with nothing free the
        answer was a vacuous yes, and an issued child's re-issue was refused for a crossing it did not set)."""
        at = lambda y: self.act[y][0] if y in self.act else self.standing(y)
        fixed = ([(p, x) for x, (d, _r, _k) in self.act.items() if d is not None
                  for p in self.reads[x] if (dp := at(p)) is not None and dp >= d]
                 + [(x, c) for x, (d, _r, _k) in self.act.items() if d is not None
                    for c in self.read_by[x] if c not in self.act and (dc := at(c)) is not None and d >= dc])
        return not fixed and self._solve(_TICK, _TICK, None, free=False) is not None


def version_deadline(graph: Graph, deadline: Optional[datetime], task: Optional[Task] = None,
                     parent_id=None, spec=None, task_id=None, supplied: bool = False) -> tuple[Optional[datetime], bool]:
    """The deadline this packet version enters OFFERED with (§12.3).

    "Every entry into OFFERED carries a live deadline": T carries the deadline as the bound of the
    activity (Ch. 2), and a bound already passed leaves no activity that can meet it — a node
    reopened or revised under a spent deadline is overdue on arrival and spends its new contract in
    a zero-length transit. The canon requires the PACKET to carry one, not the issuer to type one,
    so an implementation may write a default, logged as supplied, inside the parent's own deadline
    (§2.5, §4.5 item 6) — chosen by `Schedule`, ordered along Dep. A typed one the version keeps while
    it is live; a supplied one while it still fits — a revision that adds a producer re-chooses it.
    Under a parent whose deadline has already gone there is no default inside it: none is written, and
    the signal gate refuses a version that would enter so — "under a parent whose deadline has passed
    the issuer types one" (§12.16; `validation.no_live_deadline`)."""
    if deadline is not None:
        return deadline, supplied          # handed in: typed, or a default `Schedule` chose for the act (§2.5)
    kept = (task.deadline, task.deadline_supplied) if task is not None else (None, False)
    tid = str(task_id if task_id is not None else task.id if task is not None else "")
    live = task is not None and task.deadline is not None and task.deadline > datetime.now()
    if live and not task.deadline_supplied:
        return kept
    pid = parent_id if parent_id is not None else (task.parent_id if task is not None else None)
    parent = graph.get_task(pid) if (pid and graph is not None) else None
    reads = producers_of(spec if spec is not None else task.spec if task is not None else None)
    chosen = Schedule(graph, parent, {tid: (None, reads, task.deadline if live else None)}).defaults()[tid]
    return (chosen, True) if chosen is not None else kept


def _create_task(graph: Graph, effect: MutateGraph) -> list[TaskId]:
    if effect.spec is None:
        log.error(f"CREATE_TASK without spec for {effect.task_id}")
        return []
    _deadline = version_deadline(graph, effect.deadline, parent_id=effect.parent_id, spec=effect.spec,
                                 task_id=effect.task_id, supplied=effect.deadline_supplied)
    task = Task(
        id=effect.task_id,
        spec=effect.spec,
        assignee=effect.assignee,
        parent_id=effect.parent_id,
        deadline=_deadline[0], deadline_supplied=_deadline[1],
        max_iterations=effect.max_iterations,
        # the claim as authored, frozen here and nowhere else (revisions leave it alone)
        authored=effect.spec,
    )
    graph.save_task(task)
    # Mapping = the child declares which parent criteria it covers (§2 non-redundancy). Recorded as a
    # logged effect of THIS child's ASSIGN, not a direct write to the parent. Appends (incremental-safe).
    if effect.covers and effect.parent_id:
        parent = graph.get_task(effect.parent_id)
        if parent is not None:
            seen = {(m.criterion_name, m.child_id) for m in parent.criterion_mappings}
            new = tuple(CriterionMapping(c, effect.task_id) for c in effect.covers
                        if (c, effect.task_id) not in seen)
            if new:
                parent.criterion_mappings = parent.criterion_mappings + new
                graph.save_task(parent)
    return []
