"""Every surface tells a party exactly the moves the engine will take from it: the mode lock the doors apply
(`tools.mode_holder`) is the one the frontier's `mine` and `available_actions` read, each step names who performs it
(`performed_by`), and every `next_steps` answer carries the Dep waits, not only the one that lists steps.

Measured by the UI stream 2026-10-26: under AUTO a CHALLENGED root whose dispute is the system's came back `mine`
to its customer and `/actions` offered him ACCEPT/REJECT_CHALLENGE and CANCEL, all refused at the door; with a
validator in flight a consumer's wait on its producer vanished from `waiting` for the length of the validation.

CONTROLS: let `_mark_mine` skip `mode_holder` and the dispute test goes red; drop the lock from `_gated_out` and the
`/actions` assertions go red; drop the waits from the dict-shaped answers of `Frontier.next_steps` and the wait test
goes red.
"""
from __future__ import annotations

import pytest

import gfso.tools as T
from gfso.core.types import Action, Mode, TaskId
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
