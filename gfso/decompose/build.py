"""Build a CORE graph from a structured decomposition spec THROUGH the FSM (signals) — the SINGLE build path.

Every node enters the graph via a logged ASSIGN (no `_graph.save_task` bypass); Dep is criteria-content
(§2.2): a seam = a `depends_on` criterion on the CONSUMER, declared at creation so no post-hoc cascade fires;
the DepEdge is derived (`graph.dep_edges()`).
"""
from __future__ import annotations

from gfso.engine import Engine
from gfso.core.types import (
    Spec, Criteria, NeglectedItem, CriterionMapping, Predictability, TaskId, AgentId,
    Signal, SignalData, State,
)


def _pred(s):
    if s in ("ORDINARY", "STATISTICAL", "EXTRAORDINARY"):
        return Predictability[s]
    return None


def build_graph_live(d: dict, request: str, engine: Engine, root_id: str = "root",
                     assignee: str = "human") -> tuple[Engine, TaskId]:
    """Build the decomposition into a LIVE (started) engine THROUGH the FSM — the canon-faithful counterpart
    to the offline `build_graph`. The root enters via a logged ASSIGN (if absent); the children via
    `decompose_task` (one ASSIGN each), with each Dep seam declared as a `depends_on` CRITERION **at
    creation** (§2.2 Dep=criteria-content) so no post-hoc `add_dependency` fires (which would CANCEL+re-ASSIGN
    the consumer and cascade). Every node thus enters the graph by a signal — no `_graph.save_task` bypass."""
    rid, A = TaskId(root_id), AgentId(assignee)
    root_crit = tuple(Criteria(c["name"], c.get("description", "")) for c in d.get("root_criteria", []))
    neg = tuple(
        NeglectedItem(n["item"], _pred(n.get("predictability")), n.get("justification", ""),
                      n.get("invalidation", ""))
        for n in d.get("neglected", [])
    )
    existing = engine.get_task(rid)
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
        engine.revise(rid, new_spec, A); engine.wait_idle()

    # a decomposed root is being worked on → ACCEPT it so it is EXECUTING (with children), not REVIEW: a
    # parent that still shows 'accept' interleaved with its children confuses the executor's next_step order.
    if engine.get_state(rid) == State.REVIEW:
        engine.send_signal_sync(SignalData(signal=Signal.ACCEPT, task_id=rid, source=A)); engine.wait_idle()

    ids = {str(c["id"]) for c in d.get("subtasks", [])}
    deps_by_consumer: dict = {}
    for dep in d.get("deps", []):
        f, t = str(dep.get("from", "")), str(dep.get("to", ""))
        if f in ids and t in ids and f != t:                 # consumer t depends on producer f (§2.2)
            seen = deps_by_consumer.setdefault(t, [])
            if not any(ef == f for ef, _ in seen):           # dedup a repeated (producer→consumer) seam
                seen.append((f, dep.get("glue", "")))

    children = []
    for c in d.get("subtasks", []):
        cid = str(c["id"])
        crit = [Criteria(x["name"], x.get("description", "")) for x in c.get("criteria", [])]
        crit += [Criteria(name=f"dep__{f}", description=glue, depends_on=TaskId(f))
                 for f, glue in deps_by_consumer.get(cid, [])]
        children.append((TaskId(cid), Spec(c.get("description", ""), tuple(crit),
                                           name=c.get("name", "")), A))

    valid = {c["name"] for c in d.get("root_criteria", [])}
    mappings = [CriterionMapping(m["criterion"], TaskId(str(m["child_id"])))
                for m in d.get("mappings", [])
                if m.get("criterion") in valid and str(m.get("child_id")) in ids]
    if children:
        engine.decompose_task(rid, children, mappings or None); engine.wait_idle()
    return engine, rid
