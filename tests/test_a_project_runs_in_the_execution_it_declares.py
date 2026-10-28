"""A project's sessions run in the execution its roles declare — one per project, a declared one, on a base that reads
the same inside — and with none declared, on this host as before.

The execution is a project's setting chosen on the existing door (`register_agent(..., execution=)`), never a new endpoint
(the author, 2026-10-25: «плодить костыли и новые ендпоинты нельзя»); the server's `executions.json` declares what may be
named and is never written by a door.
"""
import json
import os
import subprocess
from types import SimpleNamespace

import pytest

import gfso.adapters.execution as E
import gfso.workspaces as WS
from gfso.adapters.execution import ContainerExecution, LocalExecution
from gfso.roster import AgentRegistry
import gfso.tools_llm as TL
from gfso.core.types import AgentId, Mode
from tests.support import make_engine


def _p(name, **settings):
    """An engine as `execution_of` reads it: its project's name and its own settings, which it may write."""
    return SimpleNamespace(project_name=name, graph=SimpleNamespace(setting=settings.get, store_setting=settings.__setitem__))


@pytest.fixture
def declared(tmp_path, monkeypatch):
    p = tmp_path / "executions.json"
    p.write_text(json.dumps({"e3-linux": {"image": "e3-linux-agent:2", "env_file": "e.env"},
                             "other": {"image": "x", "env_file": "e.env"}}))
    monkeypatch.setenv("GFSO_EXECUTIONS_PATH", str(p))
    monkeypatch.setattr(WS, "_EXECUTIONS", {})
    monkeypatch.setattr(E, "_SWITCH", {})
    base = tmp_path / "w" / "base"
    base.mkdir(parents=True)
    return AgentRegistry(path=str(tmp_path / "agents.json")), base


def test_a_role_names_a_declared_execution_and_the_project_runs_there(declared):
    agents, base = declared
    agents.register("p-exec", "llm-executor", workdir=str(base), project="p", execution="e3-linux")
    agents.register("q-exec", "llm-executor", workdir=str(base), project="q")
    x = WS.execution_of(_p("p"), agents)
    assert isinstance(x, ContainerExecution) and x.image == "e3-linux-agent:2" and x.base == base.resolve()
    assert x.state_dir() == x.own / ".gfso-state" and x.way.log().parts[-6:-3] == ("executions", "e3-linux", "claude")
    assert WS.execution_of(_p("p"), agents) is x, "one object per (execution, project)"
    assert isinstance(WS.execution_of(_p("q"), agents), LocalExecution)



def test_a_turned_network_switch_holds_for_every_holder(declared, tmp_path, monkeypatch):
    """The switch is set outside, in the declaration. A session keeps the execution it started with, so a second object
    under the new switch would lose the container to the first one's next call (critic over the switch): the ONE object
    turns, and whoever holds it starts the container under the switch as declared now."""
    agents, base = declared
    agents.register("p-exec", "llm-executor", workdir=str(base), project="p", execution="e3-linux")
    held = WS.execution_of(_p("p"), agents)
    ran = []
    monkeypatch.setattr(E, "run", lambda args, **kw: ran.append(args) or subprocess.CompletedProcess(
        args, 0, "true" if args[:2] == ["docker", "inspect"] else "", ""))
    monkeypatch.setattr(E, "_STARTED", {})
    held.start()
    (tmp_path / "executions.json").write_text(json.dumps({"e3-linux": {"image": "e3-linux-agent:2", "env_file": "e.env",
                                                                       "network": {"mode": "off"}}}))
    assert WS.execution_of(_p("p"), agents) is held and held.way.network == ("off", ())
    held.start()
    held.start()
    seals = [a[-1] for a in ran if a[:4] == ["docker", "exec", "-u", "0"]]
    assert sum(1 for a in ran if a[:3] == ["docker", "run", "-d"]) == 2 and seals[-1].startswith(held.way.seal())


@pytest.mark.parametrize("broken", ["{not json", '{"renamed": {"image": "x", "env_file": "e.env"}}'])
def test_a_declaration_that_does_not_read_shuts_a_running_project(declared, tmp_path, broken):
    """A session keeps its execution object; a typo while closing the switch must not leave it out (critic 5)."""
    agents, base = declared
    agents.register("p-exec", "llm-executor", workdir=str(base), project="p", execution="e3-linux")
    held = WS.execution_of(_p("p"), agents)
    (tmp_path / "executions.json").write_text(broken)
    with pytest.raises((ValueError, KeyError)):
        WS.execution_of(_p("p"), agents)
    assert held.way.network == ("off", ())

def test_an_undeclared_execution_is_refused(declared):
    agents, base = declared
    with pytest.raises(ValueError, match="not declared"):
        agents.register("p-exec", "llm-executor", workdir=str(base), project="p", execution="nowhere")


def test_one_project_runs_in_one_execution(declared):
    agents, base = declared
    agents.register("p-exec", "llm-executor", workdir=str(base), project="p", execution="e3-linux")
    with pytest.raises(ValueError, match="one project runs in one execution"):
        agents.register("p-val", "llm-validator", workdir=str(base), project="p", execution="other")
    agents.register("p-val", "llm-validator", workdir=str(base), project="p", execution="e3-linux")


def test_a_base_that_checks_out_crlf_is_refused(declared):
    agents, base = declared
    for cmd in (["init", "-q"], ["config", "core.autocrlf", "true"], ["commit", "-q", "--allow-empty", "-m", "s"]):
        subprocess.run(["git", "-c", "user.name=t", "-c", "user.email=t@t", *cmd], cwd=base, check=True)
    with pytest.raises(ValueError, match="autocrlf"):
        agents.register("p-exec", "llm-executor", workdir=str(base), project="p", execution="e3-linux")
    subprocess.run(["git", "config", "core.autocrlf", "false"], cwd=base, check=True)
    agents.register("p-exec", "llm-executor", workdir=str(base), project="p", execution="e3-linux")


@pytest.mark.skipif(os.name != "nt", reason="a network share's path is Windows'")
def test_a_base_on_a_network_share_is_refused():
    with pytest.raises(ValueError, match="network share"):
        ContainerExecution("e", "i", "f", "s", "\\\\server\\share\\base", "p")


def test_a_project_re_created_on_another_base_gets_another_execution(declared, tmp_path):
    agents, base = declared
    agents.register("p-exec", "llm-executor", workdir=str(base), project="p", execution="e3-linux")
    first = WS.execution_of(_p("p"), agents)
    other = tmp_path / "w2" / "base"
    other.mkdir(parents=True)
    agents.unregister("p-exec")
    agents.register("p-exec", "llm-executor", workdir=str(other), project="p", execution="e3-linux")
    again = WS.execution_of(_p("p"), agents)
    assert again is not first and again.base == other.resolve()



def test_the_projects_switch_can_only_close_what_the_declaration_opens(declared, tmp_path):
    """«вкл выкл сети должен быть рубильниками просто наружу» (the author, 2026-10-28): the user turns it per project, and
    the operator's declaration stays a ceiling — an emergency `off` there closes every project (critic over the first
    wiring, where the project's word won)."""
    agents, base = declared
    agents.register("p-exec", "llm-executor", workdir=str(base), project="p", execution="e3-linux")
    held = WS.execution_of(_p("p"), agents)
    assert held.way.network == ("open", ())
    WS.execution_of(_p("p", network='{"mode": "allowlist", "hosts": ["api.anthropic.com", "pypi.org"]}'), agents)
    assert held.way.network == ("allowlist", ("api.anthropic.com", "pypi.org"))
    decl = {"image": "e3-linux-agent:2", "env_file": "e.env"}
    (tmp_path / "executions.json").write_text(json.dumps({"e3-linux": {**decl, "network": {"mode": "off"}}}))
    WS.execution_of(_p("p", network='{"mode": "open"}'), agents)
    assert held.way.network == ("off", ()), "the project's open overrode the operator's off"
    (tmp_path / "executions.json").write_text(json.dumps({"e3-linux": {**decl, "network": {
        "mode": "allowlist", "hosts": ["pypi.org", "github.com"]}}}))
    WS.execution_of(_p("p", network='{"mode": "allowlist", "hosts": ["api.anthropic.com", "pypi.org"]}'), agents)
    assert held.way.network == ("allowlist", ("pypi.org",))
    with pytest.raises(ValueError):
        WS.execution_of(_p("p", network="{garbled"), agents)
    assert held.way.network == ("off", ()), "a switch that does not read shuts the way out"


def test_set_mode_turns_the_switch_alone_in_the_mode_record_and_at_once(monkeypatch):
    """Turned mid-run: the switch alone, carried in the mode record (numbered, the user's words on it), no staffing to
    close it, at once; refused where nothing could be switched or the value is no switch (critics)."""
    e = make_engine()
    turned = []
    monkeypatch.setattr(TL, "declaring_role", lambda engine, agents=None: None)
    assert "no container" in TL.set_mode(e, "auto", network="off")["error"]
    monkeypatch.setattr(TL, "declaring_role", lambda engine, agents=None: {"execution": "t"})
    monkeypatch.setattr(E, "_SWITCH", {})
    container = ContainerExecution("t", "img", "e.env", "state", ".", "p")

    def lookup(engine, agents=None):
        own = engine.graph.setting("network")
        turned.append(own)
        container.way.switch(json.loads(own) if own else None)
        return container
    monkeypatch.setattr(TL, "execution_of", lookup)
    got = TL.set_mode(e, network="off")
    assert e.mode() is None and got["network_in_force"] == {"mode": "off", "hosts": []},         "a project with no mode could not close its network without choosing who holds it"
    e.set_mode(Mode.SEMI, 2, AgentId("agent"), said="semi please")
    before = e.mode()
    for bad in ({"mode": "allowlist", "hosts": ["not a host"]}, "sideways", False, [], {}, 0, {"hosts": ["a.b"]}):
        assert TL.set_mode(e, network=bad)["refused"], bad
    assert TL.set_mode(e, network="off", boundary=3)["refused"], "a boundary without its mode was dropped silently"
    monkeypatch.setattr(TL, "mode_staffing", lambda *a: {"ready": False, "missing": "no executor registered"})
    turned.clear()
    got = TL.set_mode(e, network="off", user_said="close it")
    now = e.mode()
    assert now["boundary"] == 2 and now["mode"] == "semi", "the switch re-recorded who holds what"
    assert now["seq"] == before["seq"] + 1 and now["settings"]["network"] == '{"mode": "off"}' and now["user_said"] == "close it"
    assert {k: v for k, v in got.items() if k != "network_in_force"} == now and json.loads(e.graph.setting("network")) == {"mode": "off"}
    assert turned[-1] == '{"mode": "off"}', "a turn waited for the next session's lookup"
    assert got["network_in_force"] == {"mode": "off", "hosts": []}
    assert "user_said" not in TL.set_mode(e, network="off"), "the record carried an earlier change's words"
    e.set_mode(Mode.SOLO, None, AgentId("agent"), said="solo")
    assert e.mode()["settings"]["network"] == '{"mode": "off"}', "a mode change dropped the switch from the record"
    TL.set_mode(e, network="declared")
    assert not e.graph.setting("network") and "network" not in (e.mode().get("settings") or {})


def test_a_switch_turned_before_any_mode_stands_in_the_mode_set_after(monkeypatch):
    """D1: the mode record copied settings only from the previous record, so a switch turned while no mode stood went
    missing from it while `off` held — the settings table is the one carrier, the record reads it."""
    e = make_engine()
    monkeypatch.setattr(TL, "declaring_role", lambda engine, agents=None: {"execution": "t"})
    monkeypatch.setattr(TL, "execution_of", lambda engine, agents=None: (_ for _ in ()).throw(ValueError("no read")))
    TL.set_mode(e, network="off")
    e.set_mode(Mode.SEMI, 2, AgentId("agent"), said="semi please")
    assert json.loads(e.mode()["settings"]["network"]) == {"mode": "off"}


def test_a_switch_is_stored_where_the_declaration_does_not_read(monkeypatch):
    """D2: set_mode(network=…) raised on an unreadable declaration and the user's `off` did not land; the roster says
    a container is declared, the switch is stored, and the answer says the way out is shut."""
    e = make_engine()
    monkeypatch.setattr(TL, "declaring_role", lambda engine, agents=None: {"execution": "t"})
    monkeypatch.setattr(TL, "execution_of", lambda engine, agents=None: (_ for _ in ()).throw(KeyError("t")))
    got = TL.set_mode(e, network="off")
    assert not got.get("refused") and got["network_in_force"] == {"mode": "off", "hosts": []}
    assert json.loads(e.graph.setting("network")) == {"mode": "off"}


def test_two_allowlists_with_no_host_in_common_are_off():
    assert E.stricter(("allowlist", ("a.com",)), ("allowlist", ("b.com",))) == ("off", ())
