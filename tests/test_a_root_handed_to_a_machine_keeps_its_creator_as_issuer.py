"""A root's issuer is the goal's issuer — the party that created it (§10.1, §15.2) — whoever holds the root afterwards.
Recorded only where the system held the root at its creation, a root its creator held and then reassigned to a
registered executor made that executor its own issuer: the system answered the executor's dispute of the user's goal in
the executor's name, and the creator's own answer was refused as "not issuer" (critic over 05c6903, 2026-10-27)."""
import gfso.tools as T
import gfso.tools_llm as TL
from gfso import issuer as I
from gfso.core.types import AgentId, State, TaskId
from tests.support import criterion
from tests.test_the_mode_decides_who_holds_what import _RISK, _Roster, _engine


def _goal(e, **kw):
    T.TOOLS["create_task"](e, "root", {"description": "g", "accepted_risks": _RISK,
                                       "criteria": [criterion("g", "G holds")]}, **kw)
    e.wait_idle()


def test_a_root_reassigned_to_a_machine_keeps_its_creator_as_issuer():
    e = _engine()
    e.workforce.publish_roster({"exec-1": "llm-executor"})
    _goal(e)
    T.TOOLS["reassign"](e, "root", "exec-1", reason="capability_mismatch")
    T.signal(e, "root", "ACCEPT", "exec-1")
    T.signal(e, "root", "CHALLENGE", "exec-1", reason="g is unmeetable")
    assert e.graph.issuer_of(TaskId("root")) == AgentId("agent")
    # with no mode the system answers a dispute at a seam — in the ISSUER's name, never in the disputant's own
    assert I.system_mover(e, _Roster(), TaskId("root"), "dispute") == "agent"
    out = TL.TOOLS["signal"](e, "root", "REJECT_CHALLENGE", "agent", reason="the goal stands")
    assert "error" not in str(out).lower()[:200], out
    assert e.graph.get_task(TaskId("root")).state == State.EXECUTING
    e.stop()


def test_a_root_its_creator_holds_is_self_issued_as_before():
    e = _engine()
    _goal(e)
    assert e.graph.issuer_of(TaskId("root")) == e.graph.get_task(TaskId("root")).assignee
    e.stop()
