"""A rule two doors ask is written once (canon audit 2026-10-26, OD-2/OD-3): copies of it had diverged.

CONTROLS: read only the last batch in `delegate._classify_no_verdict`, or drop the children's clause from
`Engine.seam_keepers` — and the test of that rule goes red."""
from __future__ import annotations

import gfso.delegate as D
from gfso.adapters.llm.stats import the_call_was_cut
from gfso.core.types import AgentId, TaskId
from tests.support import make_engine


def test_a_validation_whose_first_batch_was_cut_was_cut_for_every_reader():
    calls = [{"transport_torn": True, "cost_usd": 0.0}, {"transport_torn": False, "cost_usd": 0.01}]
    llm = type("L", (), {"calls": calls})()
    e = make_engine()
    assert the_call_was_cut(llm, "") and D._classify_no_verdict(e, "t", {"stats": calls}) == "no-verdict:torn"
    e.stop()


def test_no_door_hands_a_node_to_its_own_childs_executor():
    e = make_engine()
    e.workforce.publish_executor_pool({"exec-1": None, "exec-2": None, "exec-3": None})

    class _Kid:
        assignee = AgentId("exec-2")
    e._graph.get_active_children = lambda tid: [_Kid()] if str(tid) == "n" else []
    keepers = [str(a) for a in e.seam_keepers(AgentId("exec-1"), TaskId("n"))]
    assert keepers == ["exec-3"], keepers
    e.stop()
