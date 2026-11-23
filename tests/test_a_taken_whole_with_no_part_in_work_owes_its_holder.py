"""Consented work owes its executor a move (Inv-8: EXECUTING's owner is the executor), a split under it or not, and the
hold keeps a console on the moves it can make now. A taken node whose parts stood offered to its own holder, none
taken, gave no step at all — the frontier read "its frontier is elsewhere" — so a stream holding nine of the person's
seams read zero steps, and the hold that reads the frontier let its console stop with every one owed (the author,
2026-11-23: «держать хук должен на шве»). The step is read off the states, no filter: a part offered to this holder
that he can take now, or one not yet issued, whatever stands offered to another or is in work beside it. With no such
part his moves wait on another's: no step for the whole.

CONTROL: `_carry_on` returning None turns the first, the mixed and the dispatched tests red; the held-node
branch returning None, the SEMI one.
"""
from __future__ import annotations

import gfso.tools as T
from gfso import hold
from gfso.core.types import AgentId, Mode, TaskId
from tests.support import criterion, make_engine
from tests.test_the_mode_decides_who_holds_what import _RISK, _engine, _kid


def _taken_whole(e, *holders, holder="exec-1"):
    e.record_root_issuer(TaskId("root"), "user")
    T.TOOLS["create_task"](e, "root", {"description": "g", "criteria": [criterion("g", "G holds")]}, assignee=holder)
    T.signal(e, "root", "ACCEPT", holder)
    T.TOOLS["decompose"](e, "root", [{**_kid(f"c{i}", ["g"], criterion(f"k{i}", f"K{i} holds")), "assignee": h}
                                     for i, h in enumerate(holders)], accepted_risks=_RISK)
    e.wait_idle()


def _whole(e, actor="exec-1"):
    out = T.next_steps(e, actor=actor)
    return [s for s in out["steps"] if s["task_id"] == "root"], hold.own_moves(out)


def test_a_taken_whole_whose_parts_stand_offered_to_its_holder_owes_his_move():
    e = _engine()
    _taken_whole(e, "exec-1", "exec-1")
    (step,), own = _whole(e)
    assert step["mine"] and step["state"] == "EXECUTING" and not step["parallel_ok"], step
    assert "c0" in step["directive"] and "ACCEPT" in step["directive"], step
    assert [s["task_id"] for s in own] == ["root"], "the hold sees no move owed on the taken whole"
    e.stop()


def test_a_mixed_split_owes_the_holder_his_own_part_whatever_another_does():
    e = _engine()
    _taken_whole(e, "exec-1", "exec-2")
    assert _whole(e)[0], "his own offered part owes no move while another's stands offered"
    T.signal(e, "c1", "ACCEPT", "exec-2")
    e.wait_idle()
    (step,), _ = _whole(e)
    assert "c0" in step["directive"] and "c1" not in step["directive"], step
    e.stop()


def test_no_part_he_can_take_leaves_the_whole_no_step():
    e = _engine()
    _taken_whole(e, "exec-1", "exec-2")
    T.signal(e, "c0", "ACCEPT", "exec-1")
    e.wait_idle()
    assert not _whole(e)[0], "the whole asks a move while its own part is in work and the other is another's"
    e.stop()


def test_parts_offered_to_another_are_theirs_to_take():
    e = _engine()
    _taken_whole(e, "exec-2", "exec-2")
    assert not _whole(e)[0], "the whole asks its holder to move while its parts wait on another's consent"
    e.stop()


def test_a_dispatched_holders_whole_is_his_own_move_not_his_hands():
    """With hands the leaf's work is theirs; a whole's part is the holder's own to start — told "performed by", the
    console stopped with the whole owed and its hands never ran it (critic, 2026-11-23)."""
    e = make_engine(validate_signals=True, state_timeout=0)
    e.start()
    e.project_name = "p"
    e.workforce.publish_executor_pool({"exec-1": "p"})
    e.set_mode(Mode.SOLO, None, AgentId("user"), hands="exec-1")
    _taken_whole(e, "user", "user", holder="user")
    (step,), own = _whole(e, actor="user")
    assert "PERFORMED BY" not in step["directive"] and not step.get("optional"), step
    assert [s["task_id"] for s in own] == ["root"], own
    e.stop()


def test_in_semi_the_persons_taken_whole_is_his_move_too():
    """SEMI below its boundary: the person's whole is taken and handed in only with a split, and its parts are his —
    the held-node branch returned nothing for the whole, and the parts' offers hold no one (critic, 2026-11-23)."""
    e = _engine(Mode.SEMI, 2)
    T.TOOLS["create_task"](e, "root", {"description": "g", "criteria": [criterion("g", "G holds")]})
    T.TOOLS["decompose"](e, "root", [_kid(f"c{i}", ["g"], criterion(f"k{i}", f"K{i} holds")) for i in range(2)],
                         accepted_risks=_RISK)
    e.wait_idle()
    T.signal(e, "root", "ACCEPT", "user")
    e.wait_idle()
    assert str(e.graph.get_task(TaskId("c0")).assignee) == "user", e.graph.get_task(TaskId("c0")).assignee
    (step,), own = _whole(e, actor="user")
    assert step["mine"] and "c0" in step["directive"], step
    assert [s["task_id"] for s in own] == ["root"], own
    e.stop()
