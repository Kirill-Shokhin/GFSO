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
from gfso.config import PERSON_BOUNDS, PERSON_DEADLINE_S, default_deadline_s, state_bound
from gfso.sessions import _session_cap
from gfso.engine.loop import state_bound_left
from gfso.core.types import AgentId, Mode, Signal, SignalData, State, TaskId
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
        assert (span(root) > 100 * DAY) is person, "the root's deadline follows who owns its waits"
        assert (span(kid) > 100 * DAY) is person,             "the child's answers are its issuer's, the holder's under SEMI: its deadline a person's; all the system's under AUTO"
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


def _plain(**publish):
    """A project with no mode, its roster published as the dispatcher publishes it."""
    e = make_engine(validate_signals=True, state_timeout=0)
    e.start()
    e.project_name = "p"
    e.workforce.publish_roster(publish)
    return e


def _span(e, tid):
    return (e.graph.get_task(TaskId(tid)).deadline - datetime.now()).total_seconds()


def test_a_reassign_to_another_performer_chooses_the_supplied_deadline_for_the_new_one():
    """A supplied deadline is chosen for the node's parties: handed from a person to a session, or back, under a machine
    issuer, it is chosen anew."""
    e = _plain(**{"p-exec-0": "llm-executor", "p-exec-1": "llm-executor"})
    try:
        T.TOOLS["create_task"](e, "root", {"description": "g", "accepted_risks": REGISTER,
                                           "criteria": [criterion("a", "A"), criterion("b", "B")]}, assignee="p-exec-0")
        e.wait_idle()
        T.TOOLS["decompose"](e, "root", [_kid("root.a", ["a"], criterion("a1", "A1")) | {"assignee": "bob"},
                                         _kid("root.b", ["b"], criterion("b1", "B1")) | {"assignee": "p-exec-1"}],
                             accepted_risks=REGISTER)
        e.wait_idle()
        assert _span(e, "root.a") > 100 * DAY and _span(e, "root.b") < 2 * DAY
        T.TOOLS["reassign"](e, "root.a", "p-exec-1", agent="p-exec-0")
        T.TOOLS["reassign"](e, "root.b", "bob", agent="p-exec-0")
        e.wait_idle()
        assert str(e.graph.get_task(TaskId("root.a")).assignee) == "p-exec-1"
        assert _span(e, "root.a") < 2 * DAY, "the session's work keeps the server's deadline"
        assert _span(e, "root.b") > 100 * DAY, "the person's work gets a person's"
    finally:
        e.stop()


def test_a_tree_made_before_the_mode_keeps_its_deadlines_and_the_answer_names_them(tmp_path):
    """A deadline is a packet field: moved only by its issuer's revision (Inv-1), never rewritten by the system — so
    set_mode names the live nodes left on a short supplied one, and how they are extended."""
    repo = tmp_path / "repo"
    repo.mkdir()
    _git(repo, "init", "-q")
    _commit(repo, "README")
    e = make_engine(validate_signals=True, state_timeout=0)
    e.start()
    e.project_name = "p"
    try:
        assert not TL.TOOLS["register_agent"](e, "val-1", "llm-validator", workdir=str(repo)).get("refused")
        T.TOOLS["create_task"](e, "root", {"description": "g", "accepted_risks": REGISTER,
                                           "criteria": [criterion("g", "G")]})
        T.TOOLS["decompose"](e, "root", [_kid("kid", ["g"], criterion("k", "K"))], accepted_risks=REGISTER)
        e.wait_idle()
        for tid, hours in (("root", 24), ("kid", 23)):      # as a server before this choice wrote them: a day
            t = e.graph.get_task(TaskId(tid))
            t.deadline = datetime.now() + timedelta(hours=hours)
            e._graph.save_task(t)
        was = {t: e.graph.get_task(TaskId(t)).deadline for t in ("root", "kid")}
        got = TL.TOOLS["set_mode"](e, "solo", perform="in_chat", user_said="mine")
        assert not got.get("refused"), got
        assert {t: e.graph.get_task(TaskId(t)).deadline for t in ("root", "kid")} == was, "no deadline is rewritten"
        assert got.get("short_deadlines") == ["kid", "root"], got
        assert "revise" in got.get("say", ""), got
    finally:
        e.stop()


def test_with_no_mode_the_standing_agent_is_the_person():
    """Since 0.4.0 `user` is the person on a local server (the page's signer, the connection's OS owner): its own
    graph with no mode runs on its clock, as a holder's does."""
    e = _plain()
    try:
        T.TOOLS["create_task"](e, "root", {"description": "g", "criteria": [criterion("g", "G")]})
        e.wait_idle()
        root = e.graph.get_task(TaskId("root"))
        assert str(root.assignee) == "user" and _span(e, "root") > 100 * DAY
        for state in ("OFFERED", "VALIDATING", "ESCALATED"):
            assert _bound(e.graph, state, root) == PERSON_BOUNDS[state], state
    finally:
        e.stop()


def _dispatched():
    e = make_engine(validate_signals=True, check_interval=0.05, state_timeout=0)
    e.start()
    e.project_name = "p"
    e.workforce.publish_executor_pool({"exec-1": "p"})
    e.set_mode(Mode.SOLO, None, AgentId("user"), hands="exec-1")
    T.TOOLS["create_task"](e, "root", {"description": "g", "criteria": [criterion("g", "G")]})
    T.TOOLS["decompose"](e, "root", [_kid("kid", ["g"], criterion("k", "K"))], accepted_risks=REGISTER)
    e.wait_idle()
    return e


def test_dispatched_hands_the_persons_consent_waits_and_the_session_is_cut_on_the_servers_clock():
    """SOLO performed by dispatch: the holder consents and signs, the system's session does the work. The deadline is
    the contract's — OFFERED ends at it, and the consent is the person's — so a person's; the session's process is cut
    by the server's own bound, never by a deadline chosen short (`sessions._session_cap`)."""
    e = _dispatched()
    try:
        kid = e.graph.get_task(TaskId("kid"))
        assert str(kid.assignee) == "user" and kid.state.name == "OFFERED"
        assert _bound(e.graph, "CANCELLING", kid) == state_bound("CANCELLING"), "the session's handshake"
        for state in ("OFFERED", "VALIDATING", "ESCALATED"):
            assert _bound(e.graph, state, kid) == PERSON_BOUNDS[state], state
        assert _session_cap(e, [kid]) <= default_deadline_s(), "the session is cut on the server's scale"
        _the_person_is_away(e, 1.5 * DAY)
        time.sleep(1.0)
        assert not _timeouts(e), f"the person's consent lapsed in a night and a half: {_timeouts(e)}"
    finally:
        e.stop()


def test_a_semi_childs_challenge_waits_for_the_person_who_answers_it():
    """SEMI: the system's executor challenges a child the holder issued — the answer is the person's, so the deadline
    the challenge ends at is a person's."""
    e = make_engine(validate_signals=True, check_interval=0.05, state_timeout=0)
    e.start()
    e.project_name = "p"
    try:
        e.workforce.publish_executor_pool({"exec-1": "p", "exec-2": "p"})
        e.set_mode(Mode.SEMI, None, AgentId("user"))
        T.TOOLS["create_task"](e, "root", {"description": "g", "criteria": [criterion("g", "G")]})
        T.TOOLS["decompose"](e, "root", [_kid("kid", ["g"], criterion("k", "K"))], accepted_risks=REGISTER)
        e.wait_idle()
        kid = e.graph.get_task(TaskId("kid"))
        e.send_signal_sync(SignalData(signal=Signal.CHALLENGE, task_id=kid.id, source=kid.assignee, reason="K is vague"))
        assert e.graph.get_state(kid.id).name == "CHALLENGED"
        _the_person_is_away(e, 1.5 * DAY)
        time.sleep(1.0)
        assert not _timeouts(e), f"the person's answer lapsed in a night and a half: {_timeouts(e)}"
    finally:
        e.stop()


def test_after_in_chat_turns_to_dispatch_a_hung_session_is_still_cut_on_the_servers_clock(tmp_path):
    """A tree made in the chat stands on a person's deadlines; dispatched afterwards, its session must not run for months."""
    e, _ = _solo_in_chat(tmp_path)
    try:
        kid = e.graph.get_task(TaskId("root.b"))
        assert (kid.deadline - datetime.now()).total_seconds() > 100 * DAY
        e.workforce.publish_executor_pool({"exec-1": "p"})
        e.set_mode(Mode.SOLO, None, AgentId("user"), hands="exec-1")
        assert _session_cap(e, [kid]) <= default_deadline_s(), "a hung session runs to the person's deadline"
    finally:
        e.stop()


def test_a_projects_own_deadline_lifts_its_sessions_cut(tmp_path):
    """A project that sets its own `deadline_s` sets its sessions' bound too: an AUTO chain meant to run three days is not
    cut at the server's one (whole critic over the bounds). CONTROL: `_session_cap` reading the server's bound alone — red."""
    e, _ = _solo_in_chat(tmp_path)
    try:
        kid = e.graph.get_task(TaskId("root.b"))
        e.set_settings({"deadline_s": 200 * DAY}, AgentId("user"))
        assert _session_cap(e, [kid]) > default_deadline_s() * 2, "the project's own deadline did not reach its sessions"
    finally:
        e.stop()
