"""Mutation -> G'. Returns affected child ids for cascade."""
from __future__ import annotations

import logging
from typing import Optional

from gfso.core.types import (
    TaskId, Task, State, MutationType, DoneReason, RevisionReason,
    MutateGraph, CriterionMapping, DepEdge, TERMINAL_STATES,
)


def _type_revision(task: Task, effect: MutateGraph, criteria_changed: bool, del_changed: bool) -> None:
    """§24.5 causal typing — the ONE place a revision's reason lands on the node's metric flags.
    Untyped revisions keep each metric's documented bias (q_T under-, q_Del over-approximation);
    a typed reason narrows to the canon member: SPEC_DEFECT → q_T, CAPABILITY_MISMATCH → q_Del."""
    r = effect.revision_reason
    if criteria_changed and r == RevisionReason.SPEC_DEFECT:
        task.spec_defect_criteria_change = True
    if del_changed and r is not None:
        task.reassign_reason_typed = True
        if r == RevisionReason.CAPABILITY_MISMATCH:
            task.reassign_capability_mismatch = True
from .model import Graph

log = logging.getLogger(__name__)


class InvariantViolation(Exception):
    pass


def apply(graph: Graph, effect: MutateGraph) -> list[TaskId]:
    """Apply a mutation to the graph. Returns affected child task_ids for cascade."""
    task = graph.get_task(effect.task_id)

    match effect.mutation:
        case MutationType.SET_STATE:
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
            f"criteria change requires revision (re-ASSIGN, §14.4 Inv-1) or the CHALLENGE channel"
        )

    # Track challenge for q_T metric
    if new_state == State.CHALLENGED:
        task.was_challenged = True

    # R′ × q_V (§14.3/§15.2): a DONE(pass/auto) node reopened under the SAME criteria whose FRESH run
    # FAILs = the old pass refuted by contact — exactly the pass→later-fail member, no new machinery.
    # The marker is consumed at the first fresh verdict either way (a fresh pass corroborates).
    if task.reopened_from_pass:
        if new_state == State.REWORKING or (new_state in (State.DONE, State.ESCALATED)
                                         and effect.done_reason == DoneReason.FAIL):
            task.false_positive = True
            task.reopened_from_pass = False
        elif new_state == State.DONE and effect.done_reason in (DoneReason.PASS, DoneReason.AUTO_PASS):
            task.reopened_from_pass = False

    if task.state != new_state:
        from datetime import datetime
        task.state_entered_at = datetime.now()   # Inv-5: every state carries its own clock
    task.state = new_state

    if effect.done_reason is not None:
        task.done_reason = effect.done_reason

    graph.save_task(task)

    # Cascade fires on CANCEL, i.e. on ENTERING CANCELLING (§14.2: the protocol sends CANCEL to every
    # descendant — each child then runs its own CANCEL→CANCELLING→ABANDONED handshake). Children already
    # settling (CANCELLING) or terminal are skipped.
    if new_state == State.CANCELLING:
        children = graph.get_children(effect.task_id)
        return [
            c.id for c in children
            if c.state not in TERMINAL_STATES and c.state != State.CANCELLING
        ]

    return []


def _apply_spec(graph: Graph, task: Optional[Task], effect: MutateGraph) -> list[TaskId]:
    """Apply a renegotiated spec via the sanctioned CHALLENGE channel (ACCEPT_CHALLENGE, §14.2/§14.6).

    The ONLY in-place spec change permitted to alter criteria — it is the *pre-acceptance* negotiation
    (state CHALLENGED, executor has not yet ACCEPTed), distinct from the Inv-1-guarded default path
    where a post-acceptance criteria change requires CANCEL + re-ASSIGN. §14.6 shows ACCEPT_CHALLENGE
    removing criterion c_B2 — so this channel legitimately rewrites criteria/ACCEPTED_RISKS.
    """
    if task is None or effect.spec is None:
        log.error(f"APPLY_SPEC without task/spec for {effect.task_id}")
        return []
    _type_revision(task, effect,
                   criteria_changed=task.spec.criteria != effect.spec.criteria,
                   del_changed=effect.assignee is not None and effect.assignee != task.assignee)
    # §14.3 admits ASSIGN from VALIDATING, and §6.3 prices it exactly: the issuer may revise with the
    # delivery in hand, "at the price of a logged event, a voided DELIVERY (no verdict has been
    # emitted on that path) and a fresh consent and re-delivery". Voiding it is what keeps that
    # price real — otherwise a recorded PASS from the pre-revision delivery still satisfies the
    # verifier ≠ executor gate (§14.5), and the node could complete on a verdict about a contract
    # that no longer exists.
    if task.state == State.VALIDATING:
        graph.void_pending_pass(task.id, "the contract was revised while the delivery was pending "
                                         "(re-ASSIGN from VALIDATING, §14.3)")
    # The contract generation moves with the revision, and this is what a verdict is stamped against:
    # voiding the RECORD alone loses the race to a validator that is still running on the superseded
    # delivery and lands its PASS afterwards, stamped with unchanged (iteration, reopens).
    task.revisions = getattr(task, "revisions", 0) + 1
    task.spec = effect.spec
    task.done_reason = None  # re-authored → a fresh contract, no longer a ABANDONED tombstone (clears stale flag)
    # a criteria change strands this node's own mappings that point at a now-removed criterion → prune them here
    # (logged, part of APPLY_SPEC) so no stale mapping persists; the now-unmapped child surfaces via CHECK-1b.
    _valid = {c.name for c in task.spec.criteria}
    if any(m.criterion_name not in _valid for m in task.criterion_mappings):
        task.criterion_mappings = tuple(m for m in task.criterion_mappings if m.criterion_name in _valid)
    if effect.assignee is not None:  # reassign (Del change) via the same pre-acceptance channel
        if effect.assignee != task.assignee:
            task.was_reassigned = True  # q_Del
        task.assignee = effect.assignee
    graph.save_task(task)
    # covers on a re-author: the child (re)declares which parent criteria it covers (§10), appended (dedup) —
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
    """R′ REOPEN (§14.3): the bookkeeping half of the gated quasi-terminal exit. The FSM guard
    (finality-gate + counter) has already admitted the edge in the SAME atomic step; here the
    reopen is SPENT and the stale verdict dropped:

    - `reopens += 1` — ONE sign-agnostic counter (DONE→OFFERED and ABANDONED→OFFERED alike, Inv-5);
    - `done_reason = None` — V=pass is NOT carried forward: the node re-earns its verdict through
      ACCEPT→EXECUTE→DELIVER→VALIDATE (anti-fake: OFFERED, not resurrection);
    - `reopened_from_pass` marks a pass-terminal reopened under the SAME criteria — if the fresh
      run then FAILs, the old pass is refuted: q_V's pass→later-fail member (§15.2/§24.7);
    - the recorded independent verdict goes STALE by generation stamp, not deletion (the record is
      provenance; `record_exec_verdict` stamps (iteration, reopens), the self-PASS gate and the
      metrics compare both) — an old PASS verdict cannot re-open the verifier≠executor gate;
    - an optional new spec/assignee/covers rides along exactly like a revision (same re-ASSIGN
      semantics, §14.4 Inv-1); spec=None = reopen under the standing contract.

    The compensating event is written FORWARD (this mutation + SET_STATE→OFFERED in the log);
    nothing is rewritten (Inv-7)."""
    if task is None:
        log.error(f"task {effect.task_id} not found for REOPEN")
        return []
    was_pass = task.state == State.DONE and task.done_reason in (DoneReason.PASS, DoneReason.AUTO_PASS)
    old_criteria = task.spec.criteria
    _type_revision(task, effect,
                   criteria_changed=effect.spec is not None and old_criteria != effect.spec.criteria,
                   del_changed=effect.assignee is not None and effect.assignee != task.assignee)
    task.reopens += 1
    task.done_reason = None
    if effect.spec is not None:
        task.spec = effect.spec
        _valid = {c.name for c in task.spec.criteria}
        if any(m.criterion_name not in _valid for m in task.criterion_mappings):
            task.criterion_mappings = tuple(
                m for m in task.criterion_mappings if m.criterion_name in _valid)
    if effect.assignee is not None and effect.assignee != task.assignee:
        task.was_reassigned = True  # q_Del: a Del change is a Del change, reopen or not
        task.assignee = effect.assignee
    task.reopened_from_pass = was_pass and task.spec.criteria == old_criteria
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
    """BLOCK named an undeclared prerequisite node → provisional discovered-Dep edge (§14.2/§15.2).

    Two-phase record: this registers provisional (provenance = the BLOCK event, Thm 11); RESOLVE_BLOCK
    adjudicates. A cyclic discovered edge is RECORDED (the cycle is the FM-4 finding to surface, not
    reject). Idempotent per (from, to)."""
    if effect.dep_from is None:
        log.error(f"RECORD_DEP without dep_from for {effect.task_id}")
        return []
    if graph.get_task(effect.dep_from) is None:
        # §14.2: only a producible in-scope artifact (an existing candidate producer node) promotes to a Dep
        # edge; a non-node blocker is the FM-5 currency line — nothing to record.
        log.warning(f"RECORD_DEP: blocker {effect.dep_from} is not a node — no edge (FM-5 line)")
        return []
    if any(e.from_id == effect.dep_from and e.to_id == effect.task_id
           for e in graph._storage.get_dep_edges()):
        return []
    graph._storage.add_dep_edge(DepEdge(effect.dep_from, effect.task_id,
                                        discovered=True, glue=effect.glue, provisional=True))
    return []


def _adjudicate_dep(graph: Graph, effect: MutateGraph) -> list[TaskId]:
    """RESOLVE_BLOCK adjudicates the provisional discovered-Dep(s) targeting this task (§14.2):
    no payload → CONFIRM ALL (provisional=False); dep_external → RETRACT ALL (blocker non-producible —
    the FM-5 line, not a Dep); a source set (dep_froms / legacy dep_from) → the corrected FULL set
    (SET semantics, mirroring decompose's mappings reconciliation): unlisted provisionals retract,
    each listed source is written confirmed (glue kept where the source matches a provisional).
    An escalated-unresolved provisional is simply never adjudicated — it stays counted (the hole
    was real)."""
    provisional = [e for e in graph._storage.get_dep_edges()
                   if e.to_id == effect.task_id and e.provisional]
    if effect.dep_external:
        for e in provisional:
            graph._storage.remove_dep_edge(e.from_id, e.to_id)
        return []
    corrected = effect.dep_froms or ((effect.dep_from,) if effect.dep_from else ())
    if corrected:
        glue_by_src = {e.from_id: e.glue for e in provisional}
        default_glue = provisional[0].glue if provisional else ""
        for e in provisional:
            graph._storage.remove_dep_edge(e.from_id, e.to_id)
        existing = {(e.from_id, e.to_id) for e in graph._storage.get_dep_edges()}
        for src in dict.fromkeys(corrected):
            if graph.get_task(src) is not None and (src, effect.task_id) not in existing:
                graph._storage.add_dep_edge(DepEdge(src, effect.task_id, discovered=True,
                                                    glue=glue_by_src.get(src, default_glue),
                                                    provisional=False))
        return []
    for e in provisional:  # confirm
        graph._storage.remove_dep_edge(e.from_id, e.to_id)
        graph._storage.add_dep_edge(DepEdge(e.from_id, e.to_id, discovered=True,
                                            glue=e.glue, provisional=False))
    return []


def _increment_iteration(graph: Graph, task: Optional[Task]) -> list[TaskId]:
    if task is None:
        return []
    task.iteration += 1
    graph.save_task(task)
    return []


def _create_task(graph: Graph, effect: MutateGraph) -> list[TaskId]:
    if effect.spec is None:
        log.error(f"CREATE_TASK without spec for {effect.task_id}")
        return []
    task = Task(
        id=effect.task_id,
        spec=effect.spec,
        assignee=effect.assignee,
        parent_id=effect.parent_id,
        deadline=effect.deadline,
        max_iterations=effect.max_iterations,
    )
    graph.save_task(task)
    # Mapping = the child declares which parent criteria it covers (§10 non-redundancy). Recorded as a
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
