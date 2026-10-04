"""A node's split is its executor's move; its criteria are its issuer's packet (§10.1, §11.5, Inv-1).

The refine round that authors a split re-authored the node's criteria to the set it derived, so the system could
never make an owed split at an AUTO root (the user's criteria) nor under a holder issuer (his) — a childless AUTO root
judged larger than one session had no mover at all (sync audit, B-F6). Authored by someone who is not the node's
issuer, the split now maps onto the contract as issued and re-authors none.
"""
from __future__ import annotations

import gfso.delegate as D
import gfso.tools as T
from gfso.core.types import AgentId, Mode, Signal, TaskId
import gfso.decompose as DEC
from gfso.decompose import decompose_into
from gfso.roster import AgentRegistry
from gfso.issuer import open_questions, system_splits
from gfso.mcp.server import _PINNED_ACTOR
from tests.support import REGISTER, criterion, make_engine

_PLAN = {"name": "g", "root_criteria": [criterion("g", "G holds"), criterion("z", "a goal the author made up")],
         "subtasks": [{"id": "a", "name": "a", "description": "part a", "criteria": [criterion("a_ok", "a holds")]}],
         "mappings": [{"criterion": "g", "child_id": "a"}, {"criterion": "z", "child_id": "a"}], "deps": [],
         "accepted_risks": REGISTER, "scope": []}


def _goal(tmp_path=None):
    """A root the standing agent issues and exec-1 holds — the goal's contract is the agent's; with `tmp_path`, under
    AUTO, the system's executor holds it."""
    e = make_engine(validate_signals=True, state_timeout=0)
    e.start()
    if tmp_path is not None:
        e.project_name = "p"
        agents = AgentRegistry(path=str(tmp_path / "agents.json"))
        agents.register("exec-1", "llm-executor", workdir=str(tmp_path), project="p")
        D.publish_the_workforce(e, agents.list())
        e.set_mode(Mode.AUTO, None, AgentId("agent"))
    else:
        e.record_root_issuer(TaskId("root"), AgentId("agent"))
    T.create_task(e, "root", {"description": "the goal", "criteria": [criterion("g", "G holds")]}, "exec-1")
    e.wait_idle()
    return e


def _versions(e) -> int:
    return sum(1 for a in e.audit_log(TaskId("root")) if a.signal == Signal.ASSIGN and not a.rejected)


def test_a_split_authored_by_the_executor_maps_onto_the_issued_contract():
    e = _goal()
    plan = dict(_PLAN, mappings=[{"criterion": "g", "child_id": "a"}])   # `z` is no criterion of the contract issued
    decompose_into(e, "", root_id="root", assignee="exec-1", spec=plan, llm=object(), author="exec-1")
    e.wait_idle()
    root = e.graph.get_task(TaskId("root"))
    assert [c.name for c in root.spec.criteria] == ["g"], "the executor re-authored his issuer's contract"
    assert _versions(e) == 1, "no revision of the node"
    assert [str(k.id) for k in e.graph.get_active_children(TaskId("root"))] == ["root.a"]
    e.stop()


def test_the_issuer_authoring_the_split_still_writes_the_contract():
    e = _goal()
    decompose_into(e, "", root_id="root", assignee="exec-1", spec=dict(_PLAN), llm=object(), author="agent")
    e.wait_idle()
    assert [c.name for c in e.graph.get_task(TaskId("root")).spec.criteria] == ["g", "z"]
    e.stop()


def test_an_auto_root_whose_split_is_owed_has_the_system_as_its_mover(tmp_path):
    e = _goal(tmp_path)
    root = e.graph.get_task(TaskId("root"))
    e.record_session_fit(root.id, "~2000 lines, 30 checks", False)
    assert str(e.graph.issuer_of(root.id)) != str(root.assignee), "the user's goal, a system executor"
    assert system_splits(e, e.graph.get_task(root.id)), "a childless AUTO root's owed split had no mover"
    assert (root.id, "split") in open_questions(e)
    e.stop()


def test_a_held_split_of_a_consumer_maps_its_dep_seam_too():
    """CHECK-1 reads every criterion of the node, its Dep seams included (§9.5): left out of the names a held split may
    map onto, a consumer's seam was a hole no repair round could close (critic r5)."""
    e = _goal()
    T.decompose(e, "root", [
        {"task_id": "p", "spec": {"description": "produce", "criteria": [criterion("p_ok", "made")]},
         "assignee": "w", "covers": ["g"]},
        {"task_id": "c", "spec": {"description": "consume", "criteria": [
            criterion("c_ok", "used"), {"name": "dep__p", "description": "reads p", "depends_on": "p"}]},
         "assignee": "w", "covers": ["g"]}], accepted_risks=REGISTER)
    e.wait_idle()
    plan = {"name": "c", "root_criteria": [criterion("c_ok", "used")],
            "subtasks": [{"id": "c1", "name": "c1", "description": "part", "criteria": [criterion("c1_ok", "c1")]}],
            "mappings": [{"criterion": "c_ok", "child_id": "c1"}, {"criterion": "dep__p", "child_id": "c1"}],
            "deps": [], "accepted_risks": REGISTER, "scope": []}
    decompose_into(e, "", root_id="c", assignee="w", spec=plan, llm=object(), author="w")
    e.wait_idle()
    assert [str(k.id) for k in e.graph.get_active_children(TaskId("c"))] == ["c.c1"]
    e.stop()


def test_the_mcp_door_names_the_author_itself():
    """Who authors a split decides whether a contract may be re-authored — a name the caller chose would let any agent
    claim to be any node's issuer (critic r5)."""
    assert "author" in _PINNED_ACTOR["auto_decompose"]


def test_a_held_refine_round_spends_no_repair_on_the_contract_it_does_not_author(monkeypatch):
    """Critic r7 (P4): the held contract's criteria read as "pinning no check" sent both repair calls after a phantom.
    The contract held as issued is not the round's to repair, so its probes are not read."""
    e = _goal()
    decompose_into(e, "", root_id="root", assignee="exec-1", spec=dict(_PLAN, mappings=[{"criterion": "g", "child_id": "a"}]),
                   llm=object(), author="exec-1")
    e.wait_idle()
    calls = []
    monkeypatch.setattr(DEC, "_search", lambda llm, req, view: "a missing part b")
    monkeypatch.setattr(DEC, "_audit_fold", lambda llm, req, view, holes, executor="": {"add_subtasks": [
        {"id": "b", "name": "b", "description": "part b", "criteria": [criterion("b_ok", "b holds")]}],
        "add_mappings": [{"criterion": "g", "child_id": "b"}]})
    monkeypatch.setattr(DEC, "_audit_fix", lambda llm, req, sp, refused, ex="": calls.append(refused) or {})
    for n in ("_hint", "tag_stage"):
        monkeypatch.setattr(DEC, n, lambda *a, **k: None)
    monkeypatch.setattr(DEC, "_stat_line", lambda llm: "")
    changed, _, problems = DEC._refine_round(e, "", "root", "exec-1", object(), contract_fixed=True)
    assert changed and problems == [] and calls == [], calls
    e.stop()
