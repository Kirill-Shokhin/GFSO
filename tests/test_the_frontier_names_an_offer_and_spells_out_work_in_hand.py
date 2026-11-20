"""The frontier names every offer and spells out only the work in hand. An offer — a node OFFERED, waiting for its
holder's ACCEPT — carried its whole directive and criteria on every answer, so 243 standing offers made one
`next_steps` 271,290 characters, past what a client reads (the development graph, 2026-11-20). Each owner still sees
his move (Inv-8: the offer is named, with its holder), and its contract is one `get_task` away when he takes it.

The bound: an offer costs its id and name plus a fixed frame, whatever its contract holds."""
import json

from gfso import tools as T
from gfso.core.types import AgentId, CriterionMapping, Spec, TaskId
from tests.support import REGISTER_SPLIT, make_engine

HUMAN = {"name": "c", "description": "holds " * 40,
         "check": [{"behaviour": "holds", "command": "a person reads it", "expect": "ok"}]}
FRAME = 240      # bytes an offer costs beyond its id and name: the keys, its state, its holder, one short line


def _offers(k: int):
    """A root split into k parts, one taken and k-1 standing offers, each held by another party than the caller."""
    e = make_engine()
    e.start()
    T.create_task(e, "root", {"description": "goal", "criteria": [HUMAN]}, assignee="me")
    e.wait_idle()
    T.signal(e, "root", "ACCEPT", "me")
    e.wait_idle()
    crit = e.graph.get_task(TaskId("root")).spec.criteria[0]
    e.decompose_task(TaskId("root"), [(TaskId(f"root.p{i}"), Spec(f"part {i}", (crit,)), AgentId("w")) for i in range(k)],
                     [CriterionMapping("c", TaskId(f"root.p{i}")) for i in range(k)], register=REGISTER_SPLIT)
    e.wait_idle()
    T.signal(e, "root.p0", "ACCEPT", "w")
    e.wait_idle()
    return e


def test_an_offer_is_named_with_its_holder_and_costs_a_fixed_frame():
    e = _offers(200)
    out = T.next_steps(e, actor="me")
    offers = [s for s in out["steps"] if s["action"] == "accept"]
    assert {s["task_id"] for s in offers} == {f"root.p{i}" for i in range(1, 200)}
    for s in offers:
        assert s["performed_by"] == "w" and s["mine"] is False and s["state"] == "OFFERED", s
        assert len(json.dumps(s)) <= len(s["task_id"]) + len(s["name"]) + FRAME, s
    e.stop()


def test_the_work_in_hand_keeps_its_contract_and_its_holder_is_told_how_to_take_an_offer():
    e = _offers(3)
    work = next(s for s in T.next_steps(e, actor="w")["steps"] if s["task_id"] == "root.p0")
    assert work["action"] == "execute" and work["criteria"] == ["c"] and "EXECUTE" in work["directive"]
    mine = [s for s in T.next_steps(e, actor="w")["steps"] if s["action"] == "accept"]
    assert mine and all(s["mine"] and "ACCEPT" in s["directive"] and "get_task" in s["directive"] for s in mine)
    e.stop()
