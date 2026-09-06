"""Build a CORE graph from a structured decomposition spec THROUGH the FSM (signals) — the SINGLE build path.

Every node enters the graph via a logged ASSIGN (no `_graph.save_task` bypass); Dep is criteria-content
(§10): a seam = a `depends_on` criterion on the CONSUMER, declared at creation so no post-hoc cascade fires;
the DepEdge is derived (`graph.dep_edges()`).
"""
from __future__ import annotations

import logging

from gfso.engine import Engine
from gfso.config import ROOT_ID
from gfso.core.types import (
    Spec, Criteria, AcceptedRiskItem, CriterionMapping, Predictability, TaskId, AgentId,
    Signal, SignalData, State,
)

log = logging.getLogger(__name__)


def _pred(s):
    if s in ("ORDINARY", "STATISTICAL", "EXTRAORDINARY"):
        return Predictability[s]
    return None


def build_graph_live(d: dict, request: str, engine: Engine, root_id: str = ROOT_ID,
                     assignee: str = "human", max_iterations: int | None = None,
                     child_assignee: str | None = None) -> tuple[Engine, TaskId, list[str]]:
    """Build the decomposition into a LIVE (started) engine THROUGH the FSM — the canon-faithful counterpart
    to the offline `build_graph`. The root enters via a logged ASSIGN (if absent); the children via
    `decompose_task` (one ASSIGN each), with each Dep seam declared as a `depends_on` CRITERION **at
    creation** (§10 Dep=criteria-content) so no post-hoc `add_dependency` fires (which would CANCEL+re-ASSIGN
    the consumer and cascade). Every node thus enters the graph by a signal — no `_graph.save_task` bypass.

    Returns (engine, root_id, dropped): `dropped` lists every spec item that could NOT be placed, with its
    reason — nothing is filtered silently; the caller's repair loop feeds these back to the audit.
    Re-running with a corrected spec is safe: an ASSIGN on an existing live node is a REVISION (same id,
    subtree retained, v3.7 §14.4 Inv-1) — wholesale rebuild = wholesale revise."""
    rid, A = TaskId(root_id), AgentId(assignee)
    # QUIESCE the dispatcher for the signal burst: the build is not atomic (root ASSIGN → children
    # ASSIGNs land milliseconds apart), and an event-driven dispatcher evaluating the half-built graph
    # races it — observed live: the root spawned as an EXECUTING "leaf" before its children existed,
    # and a consumer spawned before its producer node was created. Dispatch resumes on the settled
    # graph (the counter nests across the repair loop's re-builds; _dispatch_wake pokes the loop).
    engine._dispatch_quiesce = getattr(engine, "_dispatch_quiesce", 0) + 1
    try:
        return _build_graph_live(d, request, engine, rid, A, max_iterations,
                                 AgentId(child_assignee) if child_assignee else A)
    finally:
        engine._dispatch_quiesce = max(0, getattr(engine, "_dispatch_quiesce", 1) - 1)
        if not engine._dispatch_quiesce:
            getattr(engine, "_dispatch_wake", lambda: None)()


def _children_from_spec(engine, d: dict, ns, existing_kids: set, C, max_iterations):
    """Read the spec's subtasks into (id, spec, actor) triples — and name what was dropped.

    Building the graph is two jobs: deciding WHAT the children are — ids namespaced under
    the root, deps collected per consumer, every unusable item recorded rather than filtered
    in silence — and LANDING them through the FSM. They lived in one body of eighty
    statements, so a reader after either walked both. Returns
    (children, mappings, deps_by_consumer, dropped)."""
    ids = {str(c["id"]) for c in d.get("subtasks", [])}
    dropped: list[str] = []  # NOTHING is filtered silently — every dropped item is surfaced (returned + logged)
    deps_by_consumer: dict = {}
    for dep in d.get("deps", []):
        f, t = str(dep.get("from", "")), str(dep.get("to", ""))
        if f == t:
            dropped.append(f"dep {f}->{t}: self-dependency (audit defect)")
            continue
        if f not in ids or t not in ids:
            dropped.append(f"dep {f}->{t}: endpoint not a subtask id")
            continue
        seen = deps_by_consumer.setdefault(t, [])
        if not any(ef == f for ef, _ in seen):               # dedup a repeated (producer→consumer) seam
            seen.append((f, dep.get("glue", "")))

    children = []
    for c in d.get("subtasks", []):
        cid = str(c["id"])
        crit = [Criteria(x["name"], x.get("description", "")) for x in c.get("criteria", [])]
        crit += [Criteria(name=f"dep__{f}", description=glue, depends_on=TaskId(ns(f)))
                 for f, glue in deps_by_consumer.get(cid, [])]
        # ONE CRITERION PER NAME. A refine re-derives the set, and a name that appears twice — the
        # decomposer restating a criterion, or a `dep__x` seam described differently on two passes —
        # produced a contract carrying both, with contradictory text under one label. Measured on the
        # human door 2026-08-22: `dep__D1_scaffold` twice, one naming a package that had been renamed
        # away and one naming the real one. It is not only confusing: `record_verdict` takes its
        # evidence as a mapping keyed BY CRITERION NAME, so two criteria of one name cannot be
        # judged separately at all — one silently overwrites the other. The last statement wins,
        # which on a re-derivation is the current one.
        _by_name = {}
        for x in crit:
            _by_name[x.name] = x
        crit = list(_by_name.values())
        # a rebuild-as-revision must not stomp what belongs to OTHER authors (Inv-1): the child's Del
        # is the issuer's separate act (a Del change = the q_Del event), and the child's OWN
        # ACCEPTED_RISKS/scope/risk registers belong to the CHILD'S decomposer (§13.1: ACCEPTED_RISKS is authored
        # per-decomposition — «родитель НЕ авторствует ACCEPTED_RISKS детей») — preserve both; `A` and empty
        # registers apply only to NEW children. The subtree itself is retained by revision semantics.
        existing_child = engine.get_task(TaskId(ns(cid)))
        child_actor = AgentId(existing_child.assignee) if existing_child and existing_child.assignee else C
        child_neg = existing_child.spec.accepted_risks if existing_child else ()
        child_scope = existing_child.spec.scope if existing_child else ()
        child_risk = existing_child.spec.risk_components if existing_child else ()
        children.append((TaskId(ns(cid)), Spec(c.get("description", ""), tuple(crit),
                                               accepted_risks=child_neg, risk_components=child_risk,
                                               scope=child_scope, name=c.get("name", "")), child_actor))

    valid = {c["name"] for c in d.get("root_criteria", [])}
    mappings = []
    for m in d.get("mappings", []):
        if m.get("criterion") not in valid:
            dropped.append(f"mapping '{m.get('criterion')}'->{m.get('child_id')}: no such root criterion "
                           f"(audit name drift — coverage will show as a CHECK-1 hole)")
        elif str(m.get("child_id")) not in ids:
            dropped.append(f"mapping '{m.get('criterion')}'->{m.get('child_id')}: no such subtask id")
        else:
            mappings.append(CriterionMapping(m["criterion"], TaskId(ns(str(m["child_id"])))))

    return children, mappings, deps_by_consumer, dropped


def _children_that_changed(engine, rid, children, mappings, dropped: list) -> list:
    """The children whose contract or coverage actually differs — and which are FROZEN.

    A child already built with the same spec and the same coverage needs no re-ASSIGN, and a
    terminal one admits none at all: the FSM would reject it, so the unapplied change is
    surfaced as a problem rather than lost into a refused signal.
    """
    parent_now = engine.get_task(rid)
    have_covers = {(m.criterion_name, m.child_id)
                   for m in (parent_now.criterion_mappings if parent_now else ())}
    want_by_child: dict = {}
    for m in mappings:
        want_by_child.setdefault(m.child_id, set()).add(m.criterion_name)
    changed = []
    for cid_t, spec_c, actor in children:
        ex = engine.get_task(cid_t)
        if (ex is not None and ex.spec == spec_c
                and all((c, cid_t) in have_covers for c in want_by_child.get(cid_t, ()))):
            continue
        # COMPLETED work is FROZEN: a terminal node admits no revision (§14.3 — the FSM would reject
        # the re-ASSIGN anyway; observed live: a refine fold updated DONE children and its intent
        # vanished into rejected signals). Surface the unapplied change as a problem instead — the
        # repair loop (or the honest holes residue) routes the new obligation to a NEW subtask.
        if ex is not None and ex.state in (State.DONE, State.ABANDONED, State.ESCALATED):
            dropped.append(f"child {cid_t}: {ex.state.name} is terminal — completed work is frozen, "
                           f"the intended contract/coverage change was NOT applied; route new "
                           f"obligations to a NEW subtask (or leave the child as built)")
            continue
        changed.append((cid_t, spec_c, actor))
    return changed


def _build_graph_live(d: dict, request: str, engine: Engine, rid: TaskId,
                      A: AgentId, max_iterations: int | None = None,
                      C: AgentId | None = None) -> tuple[Engine, TaskId, list[str]]:
    root_id = str(rid)
    # Whose the ROOT is and whose the WORK is are two questions. `A` answers the first (the root's
    # Del, and so the ISSUER of every child, §14.1); `C` answers the second. They coincide unless a
    # caller asked to delegate the children — which is what a caller passing an executor's id almost
    # always meant, and getting the first when they wanted the second locked one out of their own
    # plan for fifteen minutes (measured 2026-08-21).
    C = C or A
    root_crit = tuple(Criteria(c["name"], c.get("description", "")) for c in d.get("root_criteria", []))
    neg = tuple(
        AcceptedRiskItem(n["item"], _pred(n.get("predictability")), n.get("justification", ""),
                      n.get("invalidation", ""))
        # The schema is a CALIBRATED artifact: a model answers in the vocabulary it was asked in,
        # and a key the parser does not read returns an EMPTY register silently — a CHECK-4 hole the
        # plan never had. Which is why this key and the one in the prompt schema move together.
        for n in d.get("accepted_risks", [])
    )
    scp = tuple(f"{s['item']} — {s['why_out']}" if s.get("why_out") else s["item"]
                for s in d.get("scope", []))  # §13.1 scope-boundary exclusions — objectified on the root
    existing = engine.get_task(rid)
    # `assignee` (A) delegates the CHILDREN. The issuer-acts on the ROOT (re-author + ACCEPT) are performed by
    # the root's OWN owner — for a root, issuer == executor == its own assignee; using A here would be a foreign
    # actor re-authoring/accepting someone else's root (correctly rejected by the issuer/executor guards).
    root_actor = A if existing is None else AgentId(existing.assignee)
    root_revised = False
    if existing is None:
        engine.assign_task(rid, Spec(request, root_crit, neg, scope=scp, name=d.get("name", "")), A,
                           max_iterations=max_iterations); engine.wait_idle()
    else:
        # The decomposer OWNS the root's CRITERIA: it re-authors them to the derived V-set, so the child
        # `covers` mappings resolve against real criteria. An issuer's hand-written root criteria are
        # pseudo-criteria (untrusted) — keeping them would strand coverage (CHECK-1 fail). But the human's
        # NAME and DESCRIPTION are their framing of the goal — PRESERVE them (only fall back to the derived
        # text if absent). Re-author is safe: revise retains the subtree (no cascade). IDEMPOTENT: an
        # unchanged contract emits no signal (a refine that didn't touch the root leaves it in place).
        new_spec = Spec(existing.spec.description or request, root_crit, neg, scope=scp,
                        name=existing.spec.name or d.get("name", ""))
        if new_spec != existing.spec:
            engine.revise(rid, new_spec, root_actor); engine.wait_idle()
            root_revised = True

    # a decomposed root is being worked on → ACCEPT it so it is EXECUTING (with children), not OFFERED: a
    # parent that still shows 'accept' interleaved with its children confuses the executor's next_step order.
    if engine.get_state(rid) == State.OFFERED:
        engine.send_signal_sync(SignalData(signal=Signal.ACCEPT, task_id=rid, source=root_actor)); engine.wait_idle()

    # Child ids are NAMESPACED under the root: spec ids are LLM-chosen domain words (proration_engine, ...)
    # in a flat global TaskId namespace — two decompositions of similar domains WILL collide, and a colliding
    # ASSIGN is a same-id REVISION of the OTHER tree's node (observed live: cross-tree corruption). Namespacing
    # makes collisions impossible by construction; a repair re-build of the SAME root maps to the same ids =
    # the intended wholesale revision.
    existing_kids = {str(c.id) for c in engine.get_active_children(rid)}

    def ns(cid: str) -> str:
        """Namespace a spec id into the live graph's id space (`<root>.<id>`), so two decompositions
    of different roots cannot collide on `a`."""
        if cid in existing_kids:   # a HAND-built child carries a bare id — a rebuild must be a REVISION
            return cid             # of that node, never a namespaced duplicate (observed live: refine over
                                   # a manual graph doubled the subtree, C1..C9 + root.C1..C9)
        return cid if cid.startswith(f"{root_id}.") else f"{root_id}.{cid}"

    children, mappings, deps_by_consumer, dropped = _children_from_spec(
        engine, d, ns, existing_kids, C, max_iterations)
    # IDEMPOTENT REBUILD: an untouched child costs ZERO signals — its live state (EXECUTING, a
    # delivered result, its own registers) survives a parent-level refine; only a child whose contract
    # or coverage actually changed is re-ASSIGNed (→ OFFERED: the executor re-consents, Inv-1).
    changed = _children_that_changed(engine, rid, children, mappings, dropped)
    if changed:
        engine.decompose_task(rid, changed, mappings or None, max_iterations); engine.wait_idle()
    elif root_revised:
        engine._recompute_checks(rid)  # criteria changed but no child re-ASSIGN ran the recompute
    for item in dropped:
        log.warning(f"build_graph_live dropped: {item}")
    return engine, rid, dropped
