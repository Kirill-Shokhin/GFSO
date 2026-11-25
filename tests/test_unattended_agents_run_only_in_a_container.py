"""Unattended work runs in a container; on this host the work the system dispatches runs only on its user's word (the
author, 2026-10-27: autonomous runs only in a container, Local only with a person). An executor's session, a scope's,
a system-held parent's consent: a model with tools whose commands nobody watches, and before it the plan's checks of its
place — on this host all of it runs as the user, with nothing between it and the rest of the machine. Without the word
(given on their page: `POST /api/local_agents`, a page session alone) none of it starts here: the round is its project's stop with
the cause named, nothing of the node runs first, and the stop holds until the word is given or an execution is
declared. Work a person does in their own chat, and the validator that judges it, run here as before."""
from __future__ import annotations

import subprocess
import sys
import time

import pytest

from starlette.testclient import TestClient

from gfso import config, signin, sessions as S, tools_llm as TL
from gfso.api.server import create_app
from gfso.adapters import execution as E
from gfso.core.types import THIS_HOST, PlaceUnavailable
import gfso.delegate as D
from gfso.delegate import Dispatcher
from tests.support import make_engine
from tests.test_a_cut_call_does_not_spend_the_nodes_retry import _an_offer
from tests.conftest import REAL_LOCAL_AGENTS
from tests.test_delegate import _agents
from tests.test_the_person_is_the_os_user_at_the_loopback_door import PAGE


@pytest.fixture
def no_word(monkeypatch):
    monkeypatch.setattr(config, "local_agents", lambda: False)


def _nothing_runs(monkeypatch):
    """Every step of a round that would run something of the node on this host, recorded."""
    ran = []
    monkeypatch.setattr(S, "_enter_workspace", lambda *a, **k: ran.append("place") or ("ws", [], None))
    monkeypatch.setattr(S, "_observed", lambda *a, **k: ran.append("checks") or ({}, None))
    monkeypatch.setattr(S, "_spawn", lambda *a, **k: ran.append("session") or (_ for _ in ()).throw(RuntimeError("spawned")))
    return ran


@pytest.mark.parametrize("runner", ["run_executor", "run_scope_executor", "run_consent"])
def test_dispatched_work_does_not_start_on_this_host_without_the_word(no_word, monkeypatch, tmp_path, runner):
    ran = _nothing_runs(monkeypatch)
    e = make_engine(validate_signals=True, state_timeout=0)
    e.start()
    _an_offer(e)
    agents = _agents(tmp_path, ("exec-1", "llm-executor"))
    with pytest.raises(PlaceUnavailable) as got:
        getattr(S, runner)(e, S.TaskId("kid"), "exec-1", agents)
    assert got.value.place == THIS_HOST and "their page" in got.value.why
    assert ran == [], f"{ran} ran on this host before the refusal"
    e.stop()


def test_the_word_lets_it_start(monkeypatch, tmp_path):
    monkeypatch.setattr(config, "local_agents", lambda: True)
    ran = _nothing_runs(monkeypatch)
    e = make_engine(validate_signals=True, state_timeout=0)
    e.start()
    _an_offer(e)
    with pytest.raises(RuntimeError, match="spawned"):
        S.run_consent(e, S.TaskId("kid"), "exec-1", _agents(tmp_path, ("exec-1", "llm-executor")))
    assert ran == ["place", "session"], ran
    e.stop()


def test_the_refusal_is_the_projects_stop_until_the_word_is_given(no_word, monkeypatch, tmp_path):
    """Through the dispatcher's own round: the project stopped as the system with the cause, nothing parked, and the
    stop lifts only once the word is there."""
    ran = _nothing_runs(monkeypatch)
    e = make_engine(validate_signals=True, state_timeout=0)
    e.start()
    _an_offer(e)
    said = []
    e.emit_info = lambda src, msg, _s=said: _s.append(msg)
    d = Dispatcher(e, _agents(tmp_path, ("exec-1", "llm-executor"), ("val-1", "llm-validator")))
    for _ in range(4):
        d.dispatch_once()
        time.sleep(0.3)
    stop = e.stops.paused()
    assert stop and stop["by"] == "system" and stop["place"] == THIS_HOST and "unattended" in stop["why"], (stop, said)
    assert ran == [] and "kid" not in {str(x) for x in e.parking.parked_executions()}, (ran, said)
    assert e.graph.get_task(S.TaskId("kid")).state.name == "OFFERED", "consented in its executor's name, then refused"
    e.stops.lift_the_system_stop(time.time())
    assert e.stops.paused(), "the stop lifted with nothing changed"
    monkeypatch.setattr(config, "local_agents", lambda: True)
    e.stops.lift_the_system_stop(time.time())
    assert e.stops.paused() is None
    e.stop()


def test_a_mode_that_dispatches_is_not_ready_where_its_work_would_be_refused(no_word, monkeypatch, tmp_path):
    e = make_engine(validate_signals=True, state_timeout=0)
    monkeypatch.setattr(TL, "staffed", lambda engine: _agents(tmp_path, ("exec-1", "llm-executor"),
                                                              ("exec-2", "llm-executor"), ("val-1", "llm-validator")))
    for mode, perform in (("solo", "dispatch"), ("semi", "dispatch"), ("auto", "dispatch")):
        got = TL.mode_staffing(e, mode, perform)
        assert not got["ready"] and "their page" in got["missing"], (mode, got)
    assert TL.mode_staffing(e, "solo", "in_chat")["ready"], "work done in the chat is attended"
    monkeypatch.setattr(config, "local_agents", lambda: True)
    assert TL.mode_staffing(e, "auto", "dispatch")["ready"]


def test_a_container_execution_over_a_repository_needs_no_word(no_word, tmp_path):
    for args in (["init", "-q"], ["-c", "user.name=t", "-c", "user.email=t@t", "commit", "-q", "--allow-empty", "-m", "s"]):
        subprocess.run(["git", "-C", str(tmp_path), *args], check=True, capture_output=True)
    ex = E.ContainerExecution("x", "img", str(tmp_path / "env"), str(tmp_path / "state"), str(tmp_path), "p")
    assert ex.agents_refused() is None
    assert E.LocalExecution().agents_refused()


def test_the_word_is_the_persons_page_alone_and_read_from_its_record(tmp_path, monkeypatch):
    """Host execution was decided by `GFSO_LOCAL_AGENTS` in the environment or data/serve.json — both the agent's to
    write: it starts the server with its own environment and declares through the CLI (instruction audit, row 7)."""
    monkeypatch.setenv("GFSO_DATA_DIR", str(tmp_path))
    monkeypatch.setattr(config, "local_agents", REAL_LOCAL_AGENTS)
    monkeypatch.setenv("GFSO_LOCAL_AGENTS", "allow")
    (tmp_path / "serve.json").write_text('{"GFSO_LOCAL_AGENTS": "allow"}', encoding="utf-8")
    assert not config.local_agents(), "the agent's own words decide nothing"
    e = make_engine(validate_signals=True)
    e.start()
    app = create_app(e)
    agent = TestClient(app, base_url="http://127.0.0.1:8000")
    agent.cookies.clear()
    assert agent.post("/api/local_agents", json={"allow": True}).status_code == 403
    _, token = signin.issue("engineering")
    assert TestClient(app, base_url="http://127.0.0.1:8000", headers={"Authorization": f"Bearer {token}"}).post(
        "/api/local_agents", json={"allow": True}).status_code == 403
    assert not config.local_agents()
    page = TestClient(app, base_url="http://127.0.0.1:8000", headers=PAGE)
    page.cookies.clear()
    assert page.post("/api/local_agents", json={"allow": True}).json() == {"local_agents": True}
    assert config.local_agents() and page.get("/api/runtime").json()["local_agents"] is True
    assert page.post("/api/local_agents", json={"allow": False}).json() == {"local_agents": False}
    assert page.post("/api/local_agents", json={"allow": "yes"}).status_code == 422
    e.stop()


def test_a_container_runs_no_dispatched_work_over_a_base_that_is_no_repository(tmp_path):
    """A base with no commit has no places: every session of the project would share one tree and one model client's
    state. Refused with the cause and its remedy; a repository with a commit runs."""
    base = tmp_path / "base"
    base.mkdir()
    ex = E.ContainerExecution("t", "img", None, str(tmp_path / "state"), str(base), "p")
    assert "git init" in ex.agents_refused()
    for args in (["init", "-q"], ["-c", "user.name=t", "-c", "user.email=t@t", "commit", "-q", "--allow-empty", "-m", "s"]):
        subprocess.run(["git", "-C", str(base), *args], check=True, capture_output=True)
    assert E.ContainerExecution("t", "img", None, str(tmp_path / "state"), str(base), "p").agents_refused() is None
    (base / "sub").mkdir()
    inside = E.ContainerExecution("t", "img", None, str(tmp_path / "state"), str(base / "sub"), "p").agents_refused()
    assert str(base) in inside and "if the work is that repository's" in inside,         "the repository it lies in is named as one choice, never as the only one: it may be the user's home (critic)"


def _repo(at):
    at.mkdir(parents=True, exist_ok=True)
    for args in (["init", "-q"], ["-c", "user.name=t", "-c", "user.email=t@t", "commit", "-q", "--allow-empty", "-m", "s"]):
        subprocess.run(["git", "-C", str(at), *args], check=True, capture_output=True)
    return at


def _refused(tmp_path, base):
    return E.ContainerExecution("t", "img", None, str(tmp_path / "state"), str(base), "p").agents_refused()


@pytest.mark.skipif(sys.platform != "win32", reason="a junction is Windows'")
def test_a_top_reached_through_a_junction_is_the_top(tmp_path):
    """git names the junction's target, and a top compared as text was refused as "inside" itself (critic)."""
    top = _repo(tmp_path / "repo")
    subprocess.run(["cmd", "/c", "mklink", "/J", str(tmp_path / "junc"), str(top)], check=True, capture_output=True)
    assert E._no_places(tmp_path / "junc") is None, "the gate resolves its base; the reason itself must not misread one"


def test_the_remedy_never_names_the_users_home_nor_inits_inside_a_git_directory(tmp_path, monkeypatch):
    """A home kept as a dotfiles repository is no work's top: naming it told the agent to import the home (critic)."""
    home = _repo(tmp_path / "home")
    monkeypatch.setenv("USERPROFILE", str(home)), monkeypatch.setenv("HOME", str(home))
    (work := home / "tmp" / "work").mkdir(parents=True)
    said = _refused(tmp_path, work)
    assert "git init" in said and str(home) not in said.replace(str(work), ""), said
    said = _refused(tmp_path, home / ".git")
    assert "`.git` directory" in said and "git init" not in said, said


def test_a_stopped_project_ends_its_containers_once_nothing_of_it_runs_and_keeps_its_work(tmp_path, monkeypatch):
    """Stopped, a project's containers stood up for as long as it stood, holding the machine's memory (engineering): they
    end once nothing of it runs, once per stop — its volumes kept, its next start makes them again."""
    rested, working = [], [{"project": "default"}]
    monkeypatch.setattr(D, "where_it_runs", lambda *a, **k: type("X", (), {"stop": lambda self: rested.append(1)})())
    monkeypatch.setattr(D, "in_flight", lambda: working)
    e = make_engine()
    d = Dispatcher(e, _agents(tmp_path, ("exec-1", "llm-executor")))
    e.stops.pause("me", "stop")
    d.dispatch_once()
    assert rested == [], "a session of it still runs"
    working.clear()
    d.dispatch_once(), d.dispatch_once()
    assert rested == [1], "ended once, when nothing of it runs"
    e.stops.resume("me")
    d.dispatch_once()
    e.stops.pause("me", "again")
    d.dispatch_once()
    assert rested == [1, 1], "each stop its own"
