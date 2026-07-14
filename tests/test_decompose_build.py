"""build_graph_live — the decompose spec applied to a LIVE engine THROUGH the FSM (signals), not via the
offline `_graph.save_task` bypass. The canon-faithful build path E3 wires the agent onto.

Child ids are NAMESPACED under the root (`{root_id}.{spec_id}`): spec ids are LLM-chosen domain words in a
flat global TaskId namespace, so two decompositions of similar domains WOULD collide — and a colliding
ASSIGN is a same-id REVISION of the other tree's node (observed live as cross-tree corruption)."""
from gfso.engine import Engine
from gfso.adapters.storage.memory import MemoryStorage
from gfso.adapters.agents.human import HumanAgent
from gfso.adapters.llm.stub import StubLLM
from gfso.core.types import TaskId, Signal, State
from gfso.decompose.build import build_graph_live

SPEC = {
    "name": "Build the thing",
    "root_criteria": [{"name": "rc1", "description": "thing A done"},
                      {"name": "rc2", "description": "thing B done"}],
    "subtasks": [
        {"id": "a", "name": "Do A", "description": "do A", "criteria": [{"name": "a1", "description": "A works"}]},
        {"id": "b", "name": "Do B", "description": "do B", "criteria": [{"name": "b1", "description": "B works"}]},
    ],
    "mappings": [{"criterion": "rc1", "child_id": "a"}, {"criterion": "rc2", "child_id": "b"}],
    "deps": [{"from": "a", "to": "b", "glue": "B consumes A's output"}],
    "neglected": [{"item": "edge case X", "predictability": "ORDINARY",
                   "justification": "rare", "invalidation": "if X observed"}],
}


def _eng():
    e = Engine(MemoryStorage(), HumanAgent(), StubLLM(), validate_signals=True)
    e.start()
    return e


def test_build_graph_live_is_signal_routed():
    e = _eng()
    _, rid, dropped = build_graph_live(SPEC, "build the thing", e, root_id="root", assignee="human")
    e.wait_idle()
    assert dropped == []                                              # a clean spec places every item

    # every node entered the graph via a logged ASSIGN — NO _graph.save_task bypass
    assigned = {a.task_id for a in e.audit_log() if a.signal == Signal.ASSIGN and not a.rejected}
    assert {TaskId("root"), TaskId("root.a"), TaskId("root.b")} <= assigned

    root = e.get_task(rid)
    assert root.state == State.EXECUTING                             # a decomposed root is accepted (working)
    assert root.spec.name == "Build the thing"                       # short label, separate from description
    assert {c.name for c in root.spec.criteria} == {"rc1", "rc2"}
    assert [n.item for n in root.spec.neglected] == ["edge case X"]
    assert e.get_task(TaskId("root.a")).spec.name == "Do A"          # children carry their short name too

    # children are active (no cascade), parented, mapped — under NAMESPACED ids
    kids = {c.id for c in e.get_active_children(rid)}
    assert kids == {TaskId("root.a"), TaskId("root.b")}
    assert {(m.criterion_name, m.child_id) for m in root.criterion_mappings} == \
        {("rc1", TaskId("root.a")), ("rc2", TaskId("root.b"))}

    # Dep = criteria-content: consumer b carries depends_on=a; the edge is DERIVED a→b (§2.2 direction)
    b = e.get_task(TaskId("root.b"))
    assert any(c.depends_on == TaskId("root.a") for c in b.spec.criteria)
    edges = {(ed.from_id, ed.to_id) for ed in e.graph.dep_edges()}
    assert (TaskId("root.a"), TaskId("root.b")) in edges

    # structural checks hold (coverage via active children, DAG, anti-mock)
    checks = {c.check_name: c for c in e.get_checks(rid)}
    assert checks["CHECK-1:coverage"].passed
    assert checks["CHECK-2:dag"].passed


def test_build_graph_live_into_existing_root_reauthors_it():
    """If the root already exists with hand-written (pseudo)criteria, the decomposer RE-AUTHORS the root to the
    derived V-set — an issuer's criteria are untrusted; keeping them would strand the child `covers` mappings
    (CHECK-1 fail). The subtree is retained (revise ≠ abandon)."""
    e = _eng()
    from gfso.core.types import Spec, Criteria, AgentId
    e.assign_task(TaskId("root"), Spec("build the thing",
                  (Criteria("issuer_made_up", "not the real criteria"),)), AgentId("human"))
    e.wait_idle()
    build_graph_live(SPEC, "build the thing", e, root_id="root", assignee="human")
    e.wait_idle()
    root = e.get_task(TaskId("root"))
    assert {c.name for c in root.spec.criteria} == {"rc1", "rc2"}            # re-authored to the derived V-set
    assert {c.id for c in e.get_active_children(TaskId("root"))} == {TaskId("root.a"), TaskId("root.b")}
    # reconciled: the mappings resolve against the real criteria → coverage passes
    assert {c.check_name: c for c in e.get_checks(TaskId("root"))}["CHECK-1:coverage"].passed


def test_build_graph_live_reauthors_a_root_owned_by_another_agent():
    """Regression: `assignee` delegates the CHILDREN; the ROOT stays owned by whoever created it. Re-authoring
    and ACCEPTing the root must be done by the root's OWN owner (its issuer), not by the children's assignee —
    else the issuer/executor guards (correctly) reject a foreign actor acting on someone else's root."""
    e = _eng()
    from gfso.core.types import Spec, Criteria, AgentId
    e.assign_task(TaskId("root"), Spec("build the thing",
                  (Criteria("issuer_made_up", "not the real criteria"),)), AgentId("owner"))
    e.wait_idle()
    build_graph_live(SPEC, "build the thing", e, root_id="root", assignee="worker")   # children ≠ root owner
    e.wait_idle()
    root = e.get_task(TaskId("root"))
    assert {c.name for c in root.spec.criteria} == {"rc1", "rc2"}          # re-authored despite a distinct owner
    assert root.assignee == AgentId("owner")                              # root ownership unchanged
    assert e.get_state(TaskId("root")).name == "EXECUTING"               # ACCEPTed by its owner, not "worker"
    assert {c.assignee for c in e.get_active_children(TaskId("root"))} == {AgentId("worker")}  # children → assignee


def test_build_graph_live_surfaces_dropped_items():
    """Nothing is filtered silently: a self-dep, an unknown dep endpoint, and a mapping onto a nonexistent
    root criterion are all RETURNED with reasons (the repair loop's input), not swallowed."""
    e = _eng()
    bad = {**SPEC,
           "deps": [{"from": "a", "to": "a", "glue": "self"},
                    {"from": "ghost", "to": "b", "glue": "missing producer"},
                    {"from": "a", "to": "b", "glue": "B consumes A's output"}],
           "mappings": SPEC["mappings"] + [{"criterion": "no_such_criterion", "child_id": "a"}]}
    _, rid, dropped = build_graph_live(bad, "build the thing", e, root_id="root", assignee="human")
    e.wait_idle()
    assert len(dropped) == 3
    assert any("self-dependency" in d for d in dropped)
    assert any("ghost" in d for d in dropped)
    assert any("no_such_criterion" in d for d in dropped)
    # the valid parts still landed
    assert {c.id for c in e.get_active_children(rid)} == {TaskId("root.a"), TaskId("root.b")}


def test_build_graph_live_no_cross_tree_collision():
    """REGRESSION (observed live on T01): two decompositions whose specs share LLM-chosen child ids must land
    in DISJOINT trees. Without namespacing, the second build's ASSIGN on an existing id REVISED the first
    tree's node in place (same-id revision, foreign parent) — corrupting both graphs."""
    e = _eng()
    build_graph_live(SPEC, "thing one", e, root_id="r1", assignee="human"); e.wait_idle()
    build_graph_live(SPEC, "thing two", e, root_id="r2", assignee="human"); e.wait_idle()
    assert {c.id for c in e.get_active_children(TaskId("r1"))} == {TaskId("r1.a"), TaskId("r1.b")}
    assert {c.id for c in e.get_active_children(TaskId("r2"))} == {TaskId("r2.a"), TaskId("r2.b")}
    # r1's tree is untouched by the r2 build
    assert e.get_task(TaskId("r1.a")).spec.description == "do A"
    # a repair-style REBUILD of the SAME root is still the intended wholesale revision (same ids, no dupes)
    build_graph_live(SPEC, "thing one", e, root_id="r1", assignee="human"); e.wait_idle()
    assert {c.id for c in e.get_active_children(TaskId("r1"))} == {TaskId("r1.a"), TaskId("r1.b")}


def test_rebuild_reuses_hand_built_bare_ids_no_duplicates():
    """Refine over a HAND-built graph (bare child ids, no root. namespace): the rebuild must REVISE
    those nodes in place, never create namespaced duplicates (observed live in the L2 gate
    experiment: C1..C9 + root.C1..C9 doubled the subtree and orphaned every mapping)."""
    from gfso import tools as T
    e = _eng()
    T.create_task(e, "root", {"description": "goal", "criteria": [{"name": "rc1", "description": "A"}]}, "human")
    T.decompose(e, "root", [
        {"task_id": "C1", "spec": {"description": "do A", "criteria": [{"name": "a1", "description": "old"}]}, "assignee": "human"},
        {"task_id": "C2", "spec": {"description": "do B", "criteria": [{"name": "b1", "description": "B"}]}, "assignee": "human"},
    ], [{"criterion_name": "rc1", "child_id": "C1"}])
    e.wait_idle()
    spec = {"name": "goal", "root_criteria": [{"name": "rc1", "description": "A"}],
            "subtasks": [
                {"id": "C1", "name": "Do A", "description": "do A", "criteria": [{"name": "a1", "description": "NEW tighter"}]},
                {"id": "C2", "name": "Do B", "description": "do B", "criteria": [{"name": "b1", "description": "B"}]}],
            "mappings": [{"criterion": "rc1", "child_id": "C1"}],
            "deps": [], "neglected": [{"item": "x", "predictability": "STATISTICAL", "justification": "j", "invalidation": "i"}]}
    build_graph_live(spec, "goal", e, root_id="root", assignee="human")
    e.wait_idle()
    kids = {str(c.id) for c in e.get_active_children(TaskId("root"))}
    assert kids == {"C1", "C2"}          # revised in place - no root.C1/root.C2 duplicates
    assert e.get_task(TaskId("C1")).spec.criteria[0].description == "NEW tighter"
    e.stop()
