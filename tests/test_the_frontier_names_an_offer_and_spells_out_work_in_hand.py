"""The frontier names every offer and spells out only the work in hand. An offer — a node OFFERED, waiting for its
holder's ACCEPT — carried its whole directive and criteria on every answer, so 243 standing offers made one
`next_steps` 271,290 characters, past what a client reads (the development graph, 2026-11-20). Each owner still sees
his move (Inv-8: the offer is named, with its holder), and its contract is one `get_task` away when he takes it.

The bound: an offer costs its id and name plus a fixed frame, whatever its contract holds."""
import asyncio
import json

from gfso import tools as T, tools_llm as TL
from gfso.core.types import AgentId, CriterionMapping, Spec, TaskId
from gfso.mcp.server import _bind
from tests.support import REGISTER_SPLIT, declare, make_engine

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


def _at_the_agents_door(e) -> dict:
    """`next_steps` as an agent's MCP client receives it."""
    return asyncio.run(_bind(e, TL.TOOLS["next_steps"])())


def test_at_the_agents_door_an_offer_costs_its_id_and_name_and_a_few_bytes():
    """Through the MCP door an offer is its id and name under its holder: the answer grows by no more than that and 40
    bytes per offer, and no offer is left out (Inv-8)."""
    sizes, outs = {}, {}
    for k in (2, 200):
        e = _offers(k)
        outs[k] = _at_the_agents_door(e)
        sizes[k] = len(json.dumps(outs[k], default=str))
        e.stop()
    per = (sizes[200] - sizes[2]) / 198
    assert per <= len("root.p100") * 2 + 40, per
    assert outs[200]["offers"]["w"] == {f"root.p{i}": f"root.p{i}" for i in range(1, 200)}
    assert [s["task_id"] for s in outs[200]["steps"]] == ["root.p0"]


def test_at_the_agents_door_a_reason_every_wait_shares_is_said_once():
    e = _offers(4)
    for i in (1, 2, 3):
        declare(e, "root.p0", f"root.p{i}")
    e.wait_idle()
    out = _at_the_agents_door(e)
    waits = [w for w in out["waiting"] if w["kind"] == "dependency"]
    assert len(waits) == 3 and len({w["why"] for w in waits}) == 1, out["waiting"]
    key = waits[0]["why"]
    assert out["why"][key].startswith("it consumes what those nodes produce") and json.dumps(out).count("it consumes") == 1
    e.stop()
