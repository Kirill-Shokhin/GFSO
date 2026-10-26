"""Every surface tells a party exactly the moves the engine will take from it: the mode lock the doors apply
(`Engine.mode_holder`) is the one the frontier's `mine` and `available_actions` read, each step names who performs it
(`performed_by`), and every `next_steps` answer carries the Dep waits, not only the one that lists steps.

Measured by the UI stream 2026-10-26: under AUTO a CHALLENGED root whose dispute is the system's came back `mine`
to its customer and `/actions` offered him ACCEPT/REJECT_CHALLENGE and CANCEL, all refused at the door; with a
validator in flight a consumer's wait on its producer vanished from `waiting` for the length of the validation.

CONTROLS: let `_mark_mine` skip `mode_holder` and the dispute test goes red; drop the lock from `_gated_out` and the
`/actions` assertions go red; drop the waits from the dict-shaped answers of `Frontier.next_steps` and the wait test
goes red; let `Engine.held_by_mode` answer None and the AUTO prose test goes red; let `Frontier._open_producers` read
`settled_positive` instead of `joins.landed` and the joining test goes red.
"""
from __future__ import annotations

import pytest

import gfso.tools as T
from gfso.core.types import Action, DoneReason, Mode, State, TaskId
from gfso.tools_llm import _mode_lock
from tests.support import criterion
from tests.test_a_ruling_is_part_of_the_acceptance import _auto_root, _challenged_with_a_finding
from tests.test_the_mode_decides_who_holds_what import _admit, _engine, _kid


@pytest.fixture(autouse=True)
def _no_l2(monkeypatch):
    monkeypatch.setenv("GFSO_L2_GATE", "0")


def _door_takes(e, tid, sig) -> bool:
    """The door's own answer, dry: the lock in front of a `signal` that never runs."""
    try:
        _mode_lock("signal", lambda engine, task_id, signal, source=None, **kw: {"accepted": True})(e, tid, sig, "agent")
        return True
    except ValueError:
        return False


def _offered(e, tid, who):
    return T.TOOLS["available_actions"](e, tid, who)["actions"]


def test_under_auto_the_systems_dispute_is_offered_to_no_one_outside():
    e = _engine(Mode.AUTO)
    _auto_root(e)
    _challenged_with_a_finding(e, "root", "g", reason="g cannot be decided as written")
    assert not e.users_dispute(TaskId("root"))
    steps = [s for s in T.next_steps(e, actor="agent")["steps"] if s["task_id"] == "root"]
    assert steps and all(not s["mine"] and s["performed_by"] == "system" for s in steps), steps
    for who in ("agent", "*"):
        acts = _offered(e, "root", who)
        assert [a for a in acts if not _door_takes(e, "root", a)] == [], acts
    e.stop()


def test_under_auto_the_users_own_dispute_stays_his():
    e = _engine(Mode.AUTO)
    _auto_root(e)
    _challenged_with_a_finding(e, "root", "g")
    assert e.users_dispute(TaskId("root"))
    (step,) = [s for s in T.next_steps(e, actor="agent")["steps"] if s["task_id"] == "root"]
    assert step["action"] == Action.RESOLVE and step["mine"] and step["performed_by"] == "agent", step
    out = T.TOOLS["available_actions"](e, "root", "agent")
    assert {"ACCEPT_CHALLENGE", "REJECT_CHALLENGE"} <= set(out["actions"]) and "CANCEL" not in out["actions"], out
    assert all(_door_takes(e, "root", a) for a in out["actions"]) and out["performed_by"]["ACCEPT_CHALLENGE"] == "agent"
    e.stop()


def test_a_dep_wait_is_in_every_answer_of_next_steps():
    e = _engine(None)
    T.TOOLS["create_task"](e, "root", {"description": "goal", "criteria": [criterion("g", "G holds"), criterion("h", "H holds")]})
    e.wait_idle()
    assert T.signal(e, "root", "ACCEPT", "agent")["accepted"]
    _admit(e, "root", _kid("a", ["g"], criterion("a1", "A holds")), _kid("b", ["h"], criterion("b1", "B holds")))
    T.TOOLS["add_dependency"](e, "a", "b")
    e.wait_idle()
    a = str(e.graph.get_task(TaskId("a")).assignee)
    assert T.signal(e, "a", "ACCEPT", a)["accepted"] and T.signal(e, "a", "DELIVER", a, result="done it")["accepted"]
    e.wait_idle()
    waits = lambda: [(w["task_id"], w["kind"], list(w["waits_on"])) for w in T.next_steps(e, actor="agent").get("waiting", [])]
    assert ("b", "dependency", ["a"]) in waits()
    e.claims.begin_validation(TaskId("a"))
    out = T.next_steps(e, actor="agent")
    assert out.get("in_flight") and not out["steps"], out
    assert ("b", "dependency", ["a"]) in waits(), out
    e.stop()


def _settle(e, tid, state, reason=None):
    t = e._graph.get_task(TaskId(tid))
    t.state, t.done_reason = state, reason
    e._graph.save_task(t)
    e.wait_idle()


def _offers(text) -> list:
    """The moves named in `text` that the door refuses the customer under AUTO."""
    return [v for v in ("revise(", "signal(", "reopen(", "revise the parent", "map_criterion") if v in (text or "")]


@pytest.mark.parametrize("mode", [Mode.AUTO, None])
def test_the_prose_names_the_holder_where_the_mode_holds_the_move(mode):
    """An ESCALATED (FAIL), DONE/FAIL or ABANDONED AUTO root: every sentence names the system as the one who moves and
    offers its customer none of the moves the door refuses him; with no mode set the same sentences still name them."""
    for st, dr in ((State.ESCALATED, DoneReason.FAIL), (State.DONE, DoneReason.FAIL), (State.ABANDONED, None)):
        e = _engine(mode)
        _auto_root(e)
        if mode is None:
            assert T.signal(e, "root", "ACCEPT", "agent")["accepted"]
        _settle(e, "root", st, dr)
        out = T.next_steps(e, actor="agent")
        said = [out.get("directive")] + [s.get("directive") for s in out.get("steps", [])] + [
            s["opens_with"] for s in out.get("stranded", [])]
        if st == State.ESCALATED:
            aa = T.TOOLS["available_actions"](e, "root", "agent")
            said.append(aa.get("recovery"))
            assert aa["waiting_on"] == ("system" if mode else "issuer"), aa
        said = [x for x in said if x]
        if mode:
            assert said and all(not _offers(x) for x in said) and any("system" in x for x in said), (st, said)
        else:
            assert any(_offers(x) for x in said), (st, said)
        e.stop()


def test_a_dep_wait_stands_while_its_producer_is_joined():
    """a→b, `a` passed and being joined where its whole works: `b` is gated (`joins.landed`), so `waiting` names it."""
    e = _engine(None)
    T.TOOLS["create_task"](e, "root", {"description": "goal", "criteria": [criterion("g", "G holds"), criterion("h", "H holds")]})
    e.wait_idle()
    assert T.signal(e, "root", "ACCEPT", "agent")["accepted"]
    _admit(e, "root", _kid("a", ["g"], criterion("a1", "A holds")), _kid("b", ["h"], criterion("b1", "B holds")))
    T.TOOLS["add_dependency"](e, "a", "b")
    e.wait_idle()
    assert T.signal(e, "b", "ACCEPT", "agent")["accepted"]
    _settle(e, "a", State.DONE, DoneReason.PASS)
    e.joins.mark_joining("a", True)
    out = T.next_steps(e, actor="agent")
    assert "b" not in [s["task_id"] for s in out.get("steps", [])], out
    assert ("b", "dependency", ["a"]) in [(w["task_id"], w["kind"], list(w["waits_on"])) for w in out.get("waiting", [])], out
    e.joins.mark_joining("a", False)
    assert [s["action"] for s in T.next_steps(e, actor="agent")["steps"] if s["task_id"] == "b"] == [Action.EXECUTE]
    e.stop()
