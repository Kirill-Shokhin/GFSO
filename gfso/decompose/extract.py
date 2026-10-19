"""graph → spec: read a built decomposition back into its authoring (spec) form — the exact inverse
of `build_graph_live`, so refine rounds operate on the GRAPH as the state (extract → fold → rebuild
as revision, same ids).

Inverse mapping (see build.py): child ids are de-namespaced (`{root}.{id}` → `{id}`); a child's
`dep__{producer}` criterion (build's encoding of a Dep seam, §2 Dep=criteria-content) becomes a
{from, to, glue} seam and leaves the child's criteria list; only DECLARED seams extract (discovered
edges live in storage independently and survive a rebuild); scope strings pass through verbatim
(build re-emits them as-is via the no-why_out branch — the roundtrip is idempotent).
"""
from __future__ import annotations

from gfso.core.types import TaskId, register_of
from gfso.config import ROOT_ID


def extract_spec(engine, root_id: str = ROOT_ID) -> dict:
    """The live graph read back as the spec shape the fold consumes — the exact DATA inverse of
    `build_graph_live`, so a refine round starts from what the graph really holds rather than from
    what the last round thought it wrote."""
    root = engine.graph.get_task(TaskId(root_id))
    if root is None:
        raise ValueError(f"no node {root_id!r} to extract")
    p = f"{root_id}."

    def dens(nid: str) -> str:
        """The inverse of `ns` — a live id read back as the spec id the fold speaks in."""
        return str(nid).removeprefix(p)

    subtasks, deps = [], []
    for c in engine.graph.get_active_children(TaskId(root_id)):
        crit = []
        for cr in c.spec.criteria:
            if cr.depends_on:  # build's seam encoding: dep__{producer} criterion on the CONSUMER
                deps.append({"from": dens(cr.depends_on), "to": dens(c.id), "glue": cr.description})
            else:
                crit.append({"name": cr.name, "description": cr.description,
                             # …WITH ITS PROCEDURE. This function calls itself the exact data
                             # inverse of `build_graph_live`, and an inverse that drops a field
                             # DELETES it: one refine round stripped every pinned check off a
                             # contract that had just been authored with one, and the plan then
                             # failed A1 where a minute earlier it had passed.
                             "check": [p.to_dict() for p in (cr.check or ())]})
        subtasks.append({"id": dens(c.id), "name": c.spec.name, "description": c.spec.description,
                         "criteria": crit, **_fit(engine, c.id, "")})

    return {
        "name": root.spec.name,
        "root_criteria": [{"name": cr.name, "description": cr.description,
                           "check": [p.to_dict() for p in (cr.check or ())]}
                          for cr in root.spec.criteria],
        "subtasks": subtasks,
        "mappings": [{"criterion": m.criterion_name, "child_id": dens(m.child_id)}
                     for m in root.criterion_mappings],
        "deps": deps,
        "accepted_risks": [n.to_dict() for n in register_of(root).set_aside],
        # the split's denial under the schema's own key, as the decomposer is asked for it (§9.5)
        **{"denial": {"p": n.p, "justification": n.justification} for n in register_of(root).items if n.denial},
        "scope": [{"item": s, "why_out": ""} for s in root.spec.scope],
        **_fit(engine, root.id, "whole_"),
    }


def _fit(engine, task_id, prefix: str) -> dict:
    """The decomposer's recorded count and judgement, under the spec's own keys — absent if never judged."""
    f = engine.session_fit(task_id)
    return {} if f is None else {f"{prefix}volume": f.get("volume", ""),
                                 f"{prefix}fits_one_session": bool(f.get("fits"))}
