"""graph → spec: read a built decomposition back into its authoring (spec) form — the exact inverse
of `build_graph_live`, so refine rounds operate on the GRAPH as the state (extract → fold → rebuild
as revision, same ids).

Inverse mapping (see build.py): child ids are de-namespaced (`{root}.{id}` → `{id}`); a child's
`dep__{producer}` criterion (build's encoding of a Dep seam, §10 Dep=criteria-content) becomes a
{from, to, glue} seam and leaves the child's criteria list; only DECLARED seams extract (discovered
edges live in storage independently and survive a rebuild); scope strings pass through verbatim
(build re-emits them as-is via the no-why_out branch — the roundtrip is idempotent).
"""
from __future__ import annotations

from gfso.core.types import TaskId
from gfso.config import ROOT_ID


def extract_spec(engine, root_id: str = ROOT_ID) -> dict:
    root = engine.get_task(TaskId(root_id))
    if root is None:
        raise ValueError(f"no node {root_id!r} to extract")
    p = f"{root_id}."

    def dens(nid: str) -> str:
        return str(nid).removeprefix(p)

    subtasks, deps = [], []
    for c in engine.get_active_children(TaskId(root_id)):
        crit = []
        for cr in c.spec.criteria:
            if cr.depends_on:  # build's seam encoding: dep__{producer} criterion on the CONSUMER
                deps.append({"from": dens(cr.depends_on), "to": dens(c.id), "glue": cr.description})
            else:
                crit.append({"name": cr.name, "description": cr.description})
        subtasks.append({"id": dens(c.id), "name": c.spec.name, "description": c.spec.description,
                         "criteria": crit})

    return {
        "name": root.spec.name,
        "root_criteria": [{"name": cr.name, "description": cr.description}
                          for cr in root.spec.criteria],
        "subtasks": subtasks,
        "mappings": [{"criterion": m.criterion_name, "child_id": dens(m.child_id)}
                     for m in root.criterion_mappings],
        "deps": deps,
        "accepted_risks": [{"item": n.item,
                       "predictability": n.predictability.name if n.predictability else "",
                       "justification": n.justification, "invalidation": n.invalidation_condition}
                      for n in root.spec.accepted_risks],
        "scope": [{"item": s, "why_out": ""} for s in root.spec.scope],
    }
