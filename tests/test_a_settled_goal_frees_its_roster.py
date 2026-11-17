"""Under AUTO the roster is the system's while the goal is worked, and anyone's once it ended.

The mode lock keyed the roster verbs to no node, so under AUTO they stayed the system's for good: the roles of a DONE
project could be taken off by no door (live, 2026-11-10). The lock lapses on the engine's own reading of the end
(`Engine.nothing_left`), not on "every task terminal": that is vacuous on an empty graph — the go's own authoring, or
the time between `set_mode` and the go — and blind to a verdict still running and to a root's join not landed (closing
critic over 760499c).

CONTROL: drop the `nothing_left` line from `moves.door_holder` and the last test goes red; replace the predicate by
"no open node" and the empty-graph, in-flight-verdict and unlanded-join tests go red.
"""
import pytest

import gfso.tools_llm as TL
from gfso import tools as T
from gfso.core.types import AgentId, Mode, TaskId
from gfso.engine.moves import door_holder
from tests.support import criterion, instrument_passes, make_engine


def _auto():
    e = make_engine(validate_signals=True, state_timeout=0)
    e.start()
    e.workforce.publish_executor_pool({"exec-1": None})
    e.set_mode(Mode.AUTO, None, AgentId("user"))
    return e


def _locked(e) -> bool:
    return all(door_holder(e, v, None) is not None for v in ("register_agent", "unregister_agent"))


def _root(e):
    T.create_task(e, "root", {"description": "goal", "criteria": [criterion("c", "C")]}, assignee="exec-1")
    e.wait_idle()
    T.signal(e, "root", "ACCEPT", "exec-1")
    T.signal(e, "root", "DELIVER", "exec-1", result="done")


def _sign(e):
    instrument_passes(e, TaskId("root"))
    T.signal(e, "root", "PASS", str(e.graph.issuer_of(TaskId("root"))))
    e.wait_idle()


def test_an_empty_graph_under_auto_keeps_the_roster_the_systems():
    e = _auto()
    assert not e.nothing_left() and _locked(e)
    e.stop()


def test_a_goal_in_work_keeps_the_roster_the_systems():
    e = _auto()
    _root(e)
    assert e.open_nodes() and _locked(e)
    e.stop()


def test_a_verdict_still_running_on_a_settled_node_keeps_the_lock():
    e = _auto()
    _root(e)
    _sign(e)
    key = e.claims.begin_validation(TaskId("root"))
    assert key and _locked(e)
    e.claims.end_validation(key)
    assert not _locked(e)
    e.stop()


@pytest.mark.parametrize("joining", [True, False])
def test_a_passed_root_whose_result_has_not_landed_keeps_the_lock(joining):
    e = _auto()
    e.joins.set_join_owed(lambda t: True)
    _root(e)
    _sign(e)
    if joining:
        e.joins.mark_joining(TaskId("root"), True)
    assert _locked(e)                                     # joining, or never marked landed
    e.joins.mark_joining(TaskId("root"), False)
    assert e.nothing_left() and not _locked(e)
    e.stop()


def test_once_nothing_is_left_the_roles_come_off_at_the_door():
    e = _auto()
    _root(e)
    _sign(e)
    TL._roster().register("exec-1", "external", project=e.project_name or "default")
    out = TL.TOOLS["unregister_agent"](e, "exec-1")
    assert out.get("unregistered"), out
    e.stop()
