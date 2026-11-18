"""A wait a person owns runs on a person's clock; a wait the system's own sessions own keeps the server's.

The server's bounds and default deadline are tuned for AUTO runs (OFFERED a day, VALIDATING an hour, CANCELLING two
minutes). In SOLO, and in the part of SEMI the user-agent holds, the waits move only when the PERSON writes — so a person
away one night had the node's deadline lapse, ESCALATED a day later went to CANCELLING and the subtree was abandoned
(the author, 2026-11-19: «с таймаутами … это вопрос проекта а никак не сервера»; on a graph people hold «часы вести не
для кого»). The canon fixes no numbers (§12.16) and keeps every bound (Inv-5): only the defaults move, chosen by who owns
each wait; the project's own settings win over both.
"""
from __future__ import annotations

import dataclasses
import subprocess
import time
from datetime import datetime, timedelta

import pytest

import gfso.tools as T
import gfso.tools_llm as TL
from gfso.config import PERSON_BOUNDS, PERSON_DEADLINE_S, state_bound
from gfso.engine.loop import state_bound_left
from gfso.core.types import AgentId, Mode, Signal, State, TaskId
from tests.support import criterion, make_engine, REGISTER

DAY = 86_400


@pytest.fixture(autouse=True)
def _a_roster_of_its_own(tmp_path, monkeypatch):
    monkeypatch.setenv("GFSO_AGENTS_PATH", str(tmp_path / "agents.json"))


def _git(repo, *a):
    subprocess.run(["git", "-C", str(repo), *a], capture_output=True, text=True, check=True)


def _commit(repo, name):
    (repo / name).write_text("done\n")
    _git(repo, "add", name)
    _git(repo, "-c", "user.name=u", "-c", "user.email=u@x", "commit", "-q", "-m", name)


def _kid(task_id, covers, *criteria):
    return {"task_id": task_id, "covers": list(covers), "spec": {"description": task_id, "criteria": list(criteria)}}


def _solo_in_chat(tmp_path, **settings):
    """A person's own project, made the product's way: a validator, SOLO performed in the chat, the goal and its split."""
    repo = tmp_path / "repo"
    repo.mkdir()
    _git(repo, "init", "-q")
    _commit(repo, "README")
    e = make_engine(validate_signals=True, check_interval=0.05, state_timeout=0)
    e.start()
    e.project_name = "p"
    assert not TL.TOOLS["register_agent"](e, "val-1", "llm-validator", workdir=str(repo)).get("refused")
    got = TL.TOOLS["set_mode"](e, "solo", perform="in_chat", **settings)
    assert not got.get("refused") and got.get("perform") == "in_chat", got
    T.create_task(e, "root", {"description": "the goal", "accepted_risks": REGISTER,
                              "criteria": [criterion("a", "A holds"), criterion("b", "B holds")]})
    e.wait_idle()
    TL.TOOLS["signal"](e, "root", "ACCEPT", "user")
    out = T.TOOLS["decompose"](e, "root", [_kid("root.a", ["a"], criterion("a1", "A1 holds")),
                                           _kid("root.b", ["b"], criterion("b1", "B1 holds"))], accepted_risks=REGISTER)
    assert isinstance(out, list), out
    e.wait_idle()
    return e, repo


def _the_person_is_away(e, seconds):
    """Project time runs on with nobody writing: every stamp a wait is measured from moves back by `seconds`."""
    back = timedelta(seconds=seconds)
    for t in e.all_tasks():
        t.created_at -= back
        t.state_entered_at = t.state_entered_at and t.state_entered_at - back
        t.deadline = t.deadline and t.deadline - back
        e._graph.save_task(t)


def _bound(g, state, t):
    """The bound the monitor reads for `t` were it in `state` now (`loop.state_bound_left`)."""
    now = datetime.now()
    return state_bound_left(dataclasses.replace(t, state=State[state], state_entered_at=now), now.timestamp(), g)


def _timeouts(e):
    return [(str(t.id), a.old_state.name) for t in e.all_tasks() for a in e.audit_log(t.id)
            if a.signal == Signal.TIMEOUT and not a.rejected]


def test_a_solo_project_in_the_chat_survives_its_person_away_two_days(tmp_path):
    e, repo = _solo_in_chat(tmp_path)
    try:
        TL.TOOLS["signal"](e, "root.a", "ACCEPT", "user")
        _commit(repo, "a.txt")
        out = TL.TOOLS["signal"](e, "root.a", "DELIVER", "user", result="a.txt written", self_validation="PASS")
        assert out.get("accepted"), out
        e.wait_idle()
        before = {str(t.id): t.state.name for t in e.all_tasks()}
        assert before == {"root": "EXECUTING", "root.a": "VALIDATING", "root.b": "OFFERED"}, before
        _the_person_is_away(e, 2 * DAY)
        time.sleep(1.0)                     # twenty ticks of the monitor
        assert not _timeouts(e), f"a wait the person owns fired in two days: {_timeouts(e)}"
        assert {str(t.id): t.state.name for t in e.all_tasks()} == before
        dl = e.graph.get_task(TaskId("root")).deadline
        assert dl - datetime.now() > timedelta(days=100), "the deadline written for the person's own work is a person's"
        # …and every wait still has a bound that fires (Inv-5): finite, the person's
        for tid, state in before.items():
            assert _bound(e.graph, state, e.graph.get_task(TaskId(tid))) in (None, PERSON_BOUNDS.get(state))
        assert _bound(e.graph, "ESCALATED", e.graph.get_task(TaskId("root"))) == PERSON_BOUNDS["ESCALATED"]
    finally:
        e.stop()


def _staffed(mode):
    e = make_engine(validate_signals=True, state_timeout=0)
    e.start()
    e.project_name = "p"
    e.workforce.publish_executor_pool({"exec-1": "p", "exec-2": "p"})
    e.set_mode(mode, None, AgentId("user"))
    T.TOOLS["create_task"](e, "root", {"description": "the goal", "criteria": [criterion("g", "G holds")]})
    T.TOOLS["decompose"](e, "root", [_kid("kid", ["g"], criterion("k", "K holds"))], accepted_risks=REGISTER)
    e.wait_idle()
    return e


@pytest.mark.parametrize("mode", [Mode.SEMI, Mode.AUTO])
def test_the_systems_waits_keep_the_servers_and_the_holders_go_to_a_persons(mode):
    """SEMI: the user-agent holds the root and issues the child — the root's waits and the child's issuer waits are a
    person's, the child's own consent and its work the system's. AUTO: every wait the system's, as before."""
    e = _staffed(mode)
    try:
        g = e.graph
        root, kid = g.get_task(TaskId("root")), g.get_task(TaskId("kid"))
        person = mode == Mode.SEMI
        want = lambda state, p: PERSON_BOUNDS[state] if p else state_bound(state)
        assert _bound(g, "OFFERED", root) == want("OFFERED", person)
        assert _bound(g, "ESCALATED", root) == want("ESCALATED", person), \
            "the root's issuer is the customer: the holder under SEMI, one who never intervenes under AUTO"
        assert _bound(g, "OFFERED", kid) == want("OFFERED", False), "the child's executor is the system's"
        assert _bound(g, "CANCELLING", kid) == want("CANCELLING", False)
        for state in ("VALIDATING", "ESCALATED", "CHALLENGED", "BLOCKED"):
            assert _bound(g, state, kid) == want(state, person), f"{state}: the child's issuer moves"
        span = lambda t: (t.deadline - datetime.now()).total_seconds()
        assert (span(root) > 100 * DAY) is person, "the root's deadline follows who performs it"
        assert span(kid) < 2 * DAY, "the system's work keeps the server's deadline"
    finally:
        e.stop()


def test_the_projects_own_bounds_and_deadline_win_over_a_persons(tmp_path):
    e, _ = _solo_in_chat(tmp_path, bounds={"OFFERED": 600}, deadline_s=3 * DAY)
    try:
        kid = e.graph.get_task(TaskId("root.b"))
        assert _bound(e.graph, "OFFERED", kid) == 600, "the project's own bound"
        assert _bound(e.graph, "ESCALATED", kid) == PERSON_BOUNDS["ESCALATED"], \
            "a state the project leaves out is the person's, not the server's day"
        assert (kid.deadline - datetime.now()).total_seconds() < 3 * DAY, "the project's own deadline"
        assert PERSON_DEADLINE_S > 3 * DAY
    finally:
        e.stop()
