"""A new installation runs delegated work in a container with no hand step but Docker (the author, 2026-10-30: «для
нового пользователя будет стоять обязательным докер в установке»): `gfso setup` builds the shipped agent image and
declares the execution "default" on it, an executor registered naming no execution takes it, and `gfso doctor` names
in one line what is missing. The user's word for this host (GFSO_LOCAL_AGENTS=allow) is the explicit opt-out.
"""
import json
import subprocess
import subprocess

import pytest

import gfso.adapters.execution as E
import gfso.adapters.llm.headless as H
import gfso.doctor as D
import gfso.tools_llm as TL
import gfso.workspaces as WS
from gfso.adapters.execution import ContainerExecution
from gfso.core.types import AgentId, Mode
from tests.support import make_engine


@pytest.fixture
def home(tmp_path, monkeypatch):
    monkeypatch.setenv("GFSO_EXECUTIONS_PATH", str(tmp_path / "executions.json"))
    monkeypatch.setenv("GFSO_AGENTS_PATH", str(tmp_path / "agents.json"))
    monkeypatch.delenv("GFSO_LOCAL_AGENTS", raising=False)
    monkeypatch.setattr(WS, "_EXECUTIONS", {})
    (tmp_path / "w").mkdir()
    return tmp_path


def _declare(home, **more):
    (home / "executions.json").write_text(json.dumps({"default": {"image": "gfso-agent:x"}, **more}))


def _dispatching():
    """A project whose mode dispatches its nodes to its executor (`perform="dispatch"`)."""
    e = make_engine()
    e.set_mode(Mode.SOLO, None, AgentId("agent"), said="solo, dispatched", hands="p-exec")
    return e


def _registered(e, home, who, kind="llm-executor", **kw):
    got = TL.register_agent(e, who, kind, workdir=str(home / "w"), **kw)
    assert not got.get("refused"), got
    return TL._roster().get(who).get("execution")


def test_an_executor_naming_no_execution_takes_the_default_and_its_project_runs_there(home):
    _declare(home)
    e = _dispatching()
    assert _registered(e, home, "p-exec") == "default"
    assert isinstance(WS.execution_of(e, TL._roster()), ContainerExecution)


def test_the_default_is_not_taken_where_the_work_is_attended_or_placed_already(home, monkeypatch):
    _declare(home, other={"image": "y"})
    assert _registered(make_engine(), home, "p-early") is None,         "no mode set: the user's agent may build nodes in its chat beside delegated ones, on this host"
    e = _dispatching()
    assert _registered(e, home, "p-val", "llm-validator") is None, "a validator alone judges attended work"
    assert _registered(e, home, "p-x", execution="other") == "other"
    assert _registered(e, home, "p-exec") is None, "a project runs in one execution: the one it declared"
    monkeypatch.setenv("GFSO_AGENTS_PATH", str(home / "agents-q.json"))     # …a project with no role yet
    monkeypatch.setenv("GFSO_LOCAL_AGENTS", "allow")
    assert _registered(_dispatching(), home, "q-exec") is None, "the user's word for this host is the opt-out"


def test_a_role_registered_again_keeps_the_execution_it_declares(home):
    """Registered again to change its model, a project's declaring role came back with none, its project on the host and
    its validations there, said nowhere (critic, ran)."""
    _declare(home)
    e = _dispatching()
    assert _registered(e, home, "p-exec") == "default"
    assert _registered(e, home, "p-exec", model="claude-sonnet-5-5") == "default"
    assert isinstance(WS.execution_of(e, TL._roster()), ContainerExecution)


def test_work_in_the_users_own_chat_keeps_its_project_on_this_host(home):
    """`in_chat` is refused under a container: the default would have made the user's own mode unusable."""
    _declare(home)
    e = make_engine()
    e.set_mode(Mode.SOLO, None, AgentId("agent"), said="solo in my chat")
    assert e.mode()["perform"] == "in_chat" and _registered(e, home, "p-exec") is None


def test_no_default_declared_registers_as_before(home):
    (home / "executions.json").write_text(json.dumps({"other": {"image": "y"}}))
    assert _registered(_dispatching(), home, "p-exec") is None


def test_setup_declares_the_default_moves_it_on_an_upgrade_and_keeps_a_users_own(home):
    stands = lambda: json.loads((home / "executions.json").read_text())["default"]["image"]
    assert "declared" in D.declare_default("gfso-agent:a") and stands() == "gfso-agent:a"
    D.declare_default("gfso-agent:b")
    assert stands() == "gfso-agent:b", "an upgrade that changed the image kept running the old one (critic)"
    _declare(home, other={"image": "y"})
    (home / "executions.json").write_text(json.dumps({"default": {"image": "my-own:1"}}))
    assert "your own" in D.declare_default("gfso-agent:c") and stands() == "my-own:1"


def test_an_upgrade_moves_the_image_and_keeps_the_switch_set_on_the_default(home):
    """The whole entry was replaced, so `off` on setup's own `default` turned `open` at the next image, with nothing said."""
    (home / "executions.json").write_text(json.dumps({"default": {"image": "gfso-agent:a", "network": {"mode": "off"}}}))
    D.declare_default("gfso-agent:b")
    assert json.loads((home / "executions.json").read_text())["default"] == {"image": "gfso-agent:b", "network": {"mode": "off"}}


def test_the_switch_is_set_with_the_mode_that_places_the_executors_in_the_default(home):
    """Asked before the default held them, the call was refused as work "on this host": the usual order, register then mode."""
    _declare(home)
    e = make_engine()
    for args in (["init", "-q"], ["-c", "user.email=x@x", "-c", "user.name=x", "commit", "-q", "--allow-empty", "-m", "one"]):
        subprocess.run(["git", *args], cwd=home / "w", check=True)
    assert TL.register_agent(e, "p-exec", "llm-executor", workdir=str(home / "w")).get("refused") is not True
    assert TL.register_agent(e, "p-val", "llm-validator", workdir=str(home / "w")).get("refused") is not True
    got = TL.set_mode(e, "solo", network={"mode": "off"}, perform="dispatch")
    assert not got.get("refused"), got


def test_the_switch_with_no_container_to_turn_is_still_refused(home):
    e = make_engine()
    assert "no execution is declared" in TL.set_mode(e, "solo", network={"mode": "off"}, perform="in_chat")["error"]


def test_the_image_is_named_by_its_file():
    assert D.agent_image().startswith("gfso-agent:") and D.AGENT_IMAGE_FILE.is_file()


def test_doctor_names_what_stops_delegated_work_in_one_line_each(home, monkeypatch):
    monkeypatch.setattr(D, "local_word", lambda: False)
    monkeypatch.setattr(D.shutil, "which", lambda name: None)
    rows, blocking = D._execution_report()
    assert dict(rows)["docker"].startswith("NOT USABLE") and "NONE DECLARED" in dict(rows)["execution"]
    assert any("Docker" in b for b in blocking) and any("no container execution" in b for b in blocking)

    _declare(home)
    monkeypatch.setattr(D, "docker_state", lambda: (True, "engine 29"))
    monkeypatch.setattr(D, "image_present", lambda tag: False)
    rows, blocking = D._execution_report()
    assert "IMAGE ABSENT" in dict(rows)["execution"] and any("image" in b for b in blocking)

    monkeypatch.setattr(D, "local_word", lambda: True)
    monkeypatch.setattr(D, "docker_state", lambda: (False, "not on PATH"))
    rows, blocking = D._execution_report()
    assert not blocking and "THIS HOST" in dict(rows)["execution"], "the opt-out is named, not blocked"


def test_a_docker_desktop_whose_containers_reach_its_api_is_no_floor():
    """CVE-2025-9074: before 4.44.3 a container reached Docker Desktop's Engine API unauthenticated — every boundary
    the system draws with containers stands on Docker itself holding."""
    assert E.below_floor("Docker Desktop 4.44.2 (202017)") and E.below_floor("Docker Desktop 4.9.0 (1)")
    assert E.below_floor("Docker Desktop 4.44.3 (1)") is None and E.below_floor("Docker Desktop 5.0.0 (1)") is None
    assert E.below_floor("Docker Engine - Community") is None and E.below_floor("") is None


def test_on_the_doors_order_the_mode_places_the_executors_already_registered(home):
    """The door registers its roles first and sets the mode after (ORCHESTRATOR): a registration then sees no mode, and
    the default was never taken — the mode found no executor it could dispatch to (critic, through `set_mode`)."""
    _declare(home)
    for args in (["init", "-q"], ["-c", "user.name=t", "-c", "user.email=t@t", "commit", "-q", "--allow-empty", "-m", "s"]):
        subprocess.run(["git", "-C", str(home / "w"), *args], check=True, capture_output=True)
    e = make_engine()
    assert _registered(e, home, "p-exec") is None and _registered(e, home, "p-val", "llm-validator") is None
    got = TL.set_mode(e, "solo")
    assert not got.get("refused"), got
    assert TL._roster().get("p-exec")["execution"] == "default" and e.mode()["perform"] == "dispatch"
    assert TL._roster().get("p-val").get("execution") is None, "a validator alone keeps its registration"


def test_a_docker_below_the_floor_stops_every_container_execution_not_only_doctor(monkeypatch):
    """An existing install that never ran setup again: its containers must not start on a Docker they could command."""
    monkeypatch.setattr(E, "run", lambda args, **kw: subprocess.CompletedProcess(args, 0, "28.0.0|Docker Desktop 4.43.0 (1)\n", ""))
    assert "CVE-2025-9074" in E._unavailable(None, storage=False)


def test_a_refused_mode_leaves_the_executors_where_they_were(home):
    """A first run on a directory that is no repository: the mode is refused, and the executors it had moved into the
    container shut the user's other choices — in their chat, on this host (critic)."""
    _declare(home)
    e = make_engine()
    _registered(e, home, "p-exec"), _registered(e, home, "p-val", "llm-validator")
    assert TL.set_mode(e, "solo").get("refused")
    assert TL._roster().get("p-exec").get("execution") is None
    assert not TL.set_mode(e, "solo", perform="in_chat").get("refused"), "the user's own chat still open to them"


def test_a_mode_that_raises_or_cannot_move_every_executor_leaves_them_where_they_were(home, monkeypatch):
    """Past the refusals too: a moved executor whose workdir is gone made the move raise half done, and anything raising
    after it (a git timeout, the staffing read) left the project in the container (critic, reproduced)."""
    _declare(home)
    (home / "w2").mkdir()
    e = make_engine()
    _registered(e, home, "p-exec"), _registered(e, home, "p-val", "llm-validator")
    assert not TL.register_agent(e, "p-exec2", "llm-executor", workdir=str(home / "w2")).get("refused")
    (home / "w2").rmdir()
    got = TL.set_mode(e, "solo")
    assert got.get("refused") and "p-exec2" in got["error"], got
    assert {a: TL._roster().get(a).get("execution") for a in ("p-exec", "p-exec2")} == {"p-exec": None, "p-exec2": None}
    TL.unregister_agent(e, "p-exec2")
    monkeypatch.setattr(TL, "mode_staffing", lambda *a, **k: (_ for _ in ()).throw(TimeoutError("git")))
    with pytest.raises(TimeoutError):
        TL.set_mode(e, "solo")
    assert TL._roster().get("p-exec").get("execution") is None


def test_a_container_with_no_login_is_a_sign_in_to_name_not_an_empty_session():
    said = {"is_error": True, "result": "Not logged in · Please run /login", "terminal_reason": "api_error"}
    assert H._ended(said, False) == "unauthorized"
