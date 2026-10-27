"""A project's sessions run in the execution its roles declare — one per project, a declared one, on a base that reads
the same inside — and with none declared, on this host as before.

The execution is a project's setting chosen on the existing door (`register_agent(..., execution=)`), never a new endpoint
(the author, 2026-10-25: «плодить костыли и новые ендпоинты нельзя»); the server's `executions.json` declares what may be
named and is never written by a door.
"""
import json
import subprocess
from types import SimpleNamespace

import pytest

import gfso.adapters.execution as E
import gfso.workspaces as WS
from gfso.adapters.execution import ContainerExecution, LocalExecution
from gfso.roster import AgentRegistry


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
    x = WS.execution_of(SimpleNamespace(project_name="p"), agents)
    assert isinstance(x, ContainerExecution) and x.image == "e3-linux-agent:2" and x.base == base.resolve()
    assert x.state_dir().parts[-4:] == ("executions", "e3-linux", "claude", x.container)
    assert WS.execution_of(SimpleNamespace(project_name="p"), agents) is x, "one object per (execution, project)"
    assert isinstance(WS.execution_of(SimpleNamespace(project_name="q"), agents), LocalExecution)



def test_a_turned_network_switch_holds_for_every_holder(declared, tmp_path, monkeypatch):
    """The switch is set outside, in the declaration. A session keeps the execution it started with, so a second object
    under the new switch would lose the container to the first one's next call (critic over the switch): the ONE object
    turns, and whoever holds it starts the container under the switch as declared now."""
    agents, base = declared
    agents.register("p-exec", "llm-executor", workdir=str(base), project="p", execution="e3-linux")
    held = WS.execution_of(SimpleNamespace(project_name="p"), agents)
    ran = []
    monkeypatch.setattr(E, "run", lambda args, **kw: ran.append(args) or subprocess.CompletedProcess(
        args, 0, "true" if args[:2] == ["docker", "inspect"] else "", ""))
    monkeypatch.setattr(E, "_STARTED", {})
    held.start()
    (tmp_path / "executions.json").write_text(json.dumps({"e3-linux": {"image": "e3-linux-agent:2", "env_file": "e.env",
                                                                       "network": {"mode": "off"}}}))
    assert WS.execution_of(SimpleNamespace(project_name="p"), agents) is held and held.way.network == ("off", ())
    held.start()
    held.start()
    seals = [a[-1] for a in ran if a[:4] == ["docker", "exec", "-u", "0"]]
    assert sum(1 for a in ran if a[:2] == ["docker", "run"]) == 2 and seals[-1].startswith(held.way.seal())


@pytest.mark.parametrize("broken", ["{not json", '{"renamed": {"image": "x", "env_file": "e.env"}}'])
def test_a_declaration_that_does_not_read_shuts_a_running_project(declared, tmp_path, broken):
    """A session keeps its execution object; a typo while closing the switch must not leave it out (critic 5)."""
    agents, base = declared
    agents.register("p-exec", "llm-executor", workdir=str(base), project="p", execution="e3-linux")
    held = WS.execution_of(SimpleNamespace(project_name="p"), agents)
    (tmp_path / "executions.json").write_text(broken)
    with pytest.raises((ValueError, KeyError)):
        WS.execution_of(SimpleNamespace(project_name="p"), agents)
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


def test_a_base_off_a_local_drive_is_refused():
    with pytest.raises(ValueError, match="local drive"):
        ContainerExecution("e", "i", "f", "s", "\\\\server\\share\\base", "p")


def test_a_project_re_created_on_another_base_gets_another_execution(declared, tmp_path):
    agents, base = declared
    agents.register("p-exec", "llm-executor", workdir=str(base), project="p", execution="e3-linux")
    first = WS.execution_of(SimpleNamespace(project_name="p"), agents)
    other = tmp_path / "w2" / "base"
    other.mkdir(parents=True)
    agents.unregister("p-exec")
    agents.register("p-exec", "llm-executor", workdir=str(other), project="p", execution="e3-linux")
    again = WS.execution_of(SimpleNamespace(project_name="p"), agents)
    assert again is not first and again.base == other.resolve()
