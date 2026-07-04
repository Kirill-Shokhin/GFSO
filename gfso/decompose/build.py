"""Build a CORE graph from a structured decomposition spec THROUGH the FSM (signals) — the SINGLE build path.

Every node enters the graph via a logged ASSIGN (no `_graph.save_task` bypass); Dep is criteria-content
(§2.2): a seam = a `depends_on` criterion on the CONSUMER, declared at creation so no post-hoc cascade fires;
the DepEdge is derived (`graph.dep_edges()`).
"""
from __future__ import annotations

import logging

from gfso.engine import Engine
from gfso.core.types import (
    Spec, Criteria, NeglectedItem, CriterionMapping, Predictability, TaskId, AgentId,
    Signal, SignalData, State,
)

log = logging.getLogger(__name__)


def _pred(s):
    if s in ("ORDINARY", "STATISTICAL", "EXTRAORDINARY"):
        return Predictability[s]
    return None


def build_graph_live(d: dict, request: str, engine: Engine, root_id: str = "root",
                     assignee: str = "human") -> tuple[Engine, TaskId, list[str]]:
    """Build the decomposition into a LIVE (started) engine THROUGH the FSM — the canon-faithful counterpart
    to the offline `build_graph`. The root enters via a logged ASSIGN (if absent); the children via
    `decompose_task` (one ASSIGN each), with each Dep seam declared as a `depends_on` CRITERION **at
    creation** (§2.2 Dep=criteria-content) so no post-hoc `add_dependency` fires (which would CANCEL+re-ASSIGN
    the consumer and cascade). Every node thus enters the graph by a signal — no `_graph.save_task` bypass.

    Returns (engine, root_id, dropped): `dropped` lists every spec item that could NOT be placed, with its
    reason — nothing is filtered silently; the caller's repair loop feeds these back to the audit.
    Re-running with a corrected spec is safe: an ASSIGN on an existing live node is a REVISION (same id,
    subtree retained, v3.7 §6.4 Inv-1) — wholesale rebuild = wholesale revise."""
    rid, A = TaskId(root_id), AgentId(assignee)
    root_crit = tuple(Criteria(c["name"], c.get("description", "")) for c in d.get("root_criteria", []))
    neg = tuple(
        NeglectedItem(n["item"], _pred(n.get("predictability")), n.get("justification", ""),
                      n.get("invalidation", ""))
        for n in d.get("neglected", [])
    )
    existing = engine.get_task(rid)
    # `assignee` (A) delegates the CHILDREN. The issuer-acts on the ROOT (re-author + ACCEPT) are performed by
    # the root's OWN owner — for a root, issuer == executor == its own assignee; using A here would be a foreign
    # actor re-authoring/accepting someone else's root (correctly rejected by the issuer/executor guards).
    root_actor = A if existing is None else AgentId(existing.assignee)
    if existing is None:
        engine.assign_task(rid, Spec(request, root_crit, neg, name=d.get("name", "")), A); engine.wait_idle()
    else:
        # The decomposer OWNS the root's CRITERIA: it re-authors them unconditionally to the derived V-set, so
        # the child `covers` mappings resolve against real criteria. An issuer's hand-written root criteria are
        # pseudo-criteria (untrusted) — keeping them would strand coverage (CHECK-1 fail). But the human's NAME
        # and DESCRIPTION are their framing of the goal — PRESERVE them (only fall back to the derived text if
        # absent). Re-author is safe: revise retains the subtree (no cascade).
        new_spec = Spec(existing.spec.description or request, root_crit, neg,
                        name=existing.spec.name or d.get("name", ""))
        engine.revise(rid, new_spec, root_actor); engine.wait_idle()

    # a decomposed root is being worked on → ACCEPT it so it is EXECUTING (with children), not REVIEW: a
    # parent that still shows 'accept' interleaved with its children confuses the executor's next_step order.
    if engine.get_state(rid) == State.REVIEW:
        engine.send_signal_sync(SignalData(signal=Signal.ACCEPT, task_id=rid, source=root_actor)); engine.wait_idle()

    # Child ids are NAMESPACED under the root: spec ids are LLM-chosen domain words (proration_engine, ...)
    # in a flat global TaskId namespace — two decompositions of similar domains WILL collide, and a colliding
    # ASSIGN is a same-id REVISION of the OTHER tree's node (observed live: cross-tree corruption). Namespacing
    # makes collisions impossible by construction; a repair re-build of the SAME root maps to the same ids =
    # the intended wholesale revision.
    def ns(cid: str) -> str:
        return cid if cid.startswith(f"{root_id}.") else f"{root_id}.{cid}"

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
        children.append((TaskId(ns(cid)), Spec(c.get("description", ""), tuple(crit),
                                               name=c.get("name", "")), A))

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
    if children:
        engine.decompose_task(rid, children, mappings or None); engine.wait_idle()
    for item in dropped:
        log.warning(f"build_graph_live dropped: {item}")
    return engine, rid, dropped
