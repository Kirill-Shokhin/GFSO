"""A provider over a chat API holds what a client's session holds under the closed switch: its model is called from the
server, every command its tools run goes through the system's shell into the commands' container, on the record, in
reach of nothing the system runs (the author, 2026-10-28: «все что под единым классом провайдера готово - то работает
одинаково и бесшовно - безопасно»; 2026-11-02, on local models: «мне больше нужно понять гарантии про off»).
"""
import subprocess
import time

import pytest
from tests.support import a_repository

import gfso.adapters.execution as E
from gfso.adapters.execution import ContainerExecution
from gfso.adapters.llm.chat import ChatProvider, OpenAIWire
from tests.test_a_provider_runs_every_role_through_its_wire import wire_server  # noqa: F401 — a fixture
from tests.test_a_session_holds_only_its_own_place import IMAGE, made


@pytest.fixture
def closed(tmp_path, monkeypatch):
    monkeypatch.setattr(E, "_SESSIONS", {})
    monkeypatch.setattr(E, "_SWITCH", {})
    a_repository(base := tmp_path / "work" / "ws")
    (tmp_path / "e.env").write_text("NOTHING=1\n")
    x = ContainerExecution(f"t{time.time_ns()}", IMAGE, str(tmp_path / "e.env"), str(tmp_path / "state"), str(base), "p",
                           network={"mode": "off"})
    yield x
    x.stop()
    x.volume.remove()


def _left(container: str, what: str) -> str:
    return subprocess.run(["docker", "exec", container, "sh", "-c", f"pgrep -c -f '^{what}' || true"],
                          capture_output=True, text=True).stdout.strip()


def test_live_a_chat_providers_commands_are_recorded_apart_under_the_closed_switch(closed, wire_server):
    url, script, seen = wire_server
    port = url.split(":")[2].split("/")[0]
    made(closed, "a")
    place = str(closed.own / "a")
    closed.session(place).start()          # …the system's git first, as a real flow: the record still says who works here
    reach = (f"python3 -I -c \"import socket; socket.create_connection(('host.docker.internal', {port}), 5)\"; "
             "echo reached=$?")
    during = {}

    def leaves(body):
        s = closed.session(place, "agent-1")
        during.update(system=_left(s.container, "sleep 303"), commands=_left(s.client().commands.name, "sleep 303"))
        return {"content": "done"}

    script += [{"tools": [("Bash", {"command": reach})]},
               {"tools": [("Bash", {"command": "echo made > made.txt; sleep 303 >/dev/null 2>&1 &"})]},
               leaves]
    llm = ChatProvider(OpenAIWire(url, "m"), "m", execution=closed)
    llm.stage_hint = "a executor(agent-1)"
    assert llm.agent_round("s", "go", ("Bash",), cwd=place, timeout=120) == "done", "its model answers: the server calls it"

    out = seen[1]["body"]["messages"][-1]["content"]
    assert "reached=0" not in out and "reached=" in out, f"a command reached the host past the closed switch: {out}"
    assert during["system"] in ("", "0") and during["commands"] == "1", f"a command's process stands apart from the system's calls: {during}"

    s = closed.session(place, "agent-1").client()
    ended = [r for r in s.commands.record() if "rc" in r]
    began = [r for r in s.commands.record() if "argv" in r and r.get("run")]      # …not the system's own check at its start
    assert [r["argv"][-1] for r in began] == [reach, "echo made > made.txt; sleep 303 >/dev/null 2>&1 &"]
    assert all(r[E.AGENT] == "agent-1" and r[E.NODE] == s.node for r in began), began
    assert any("made.txt" in " ".join(r.get("changed", ())) for r in ended), ended
    assert _left(s.commands.name, "sleep 303") == "0", "what its commands left running ends with the run"


def test_live_a_chat_providers_command_finds_the_images_programs_the_systems_calls_their_own(closed, wire_server):
    url, script, seen = wire_server
    made(closed, "a")
    place = str(closed.own / "a")
    lay = 'mkdir -p "$HOME/.local/bin" && printf "#!/bin/sh\necho mine\n" > "$HOME/.local/bin/ls" && chmod +x "$HOME/.local/bin/ls"'
    script += [{"tools": [("Bash", {"command": lay})]}, {"tools": [("Bash", {"command": "ls"})]}, {"content": "done"}]
    llm = ChatProvider(OpenAIWire(url, "m"), "m", execution=closed)
    assert llm.agent_round("s", "go", ("Bash",), cwd=place, timeout=120) == "done"
    assert "mine" in seen[2]["body"]["messages"][-1]["content"], "a command works in the image's environment"
    s = closed.session(place)
    assert ".local" not in s.run(["sh", "-c", "command -v ls"], cwd=place, timeout=60).stdout, "the system's calls do not"


def test_live_a_chat_providers_file_tools_run_in_its_client_container(closed, wire_server):
    """They ran in the system's container of the place, following what a command linked, beside the system's calls; and read
    the base itself, every sibling's delivery named in its refs (critic)."""
    url, script, seen = wire_server
    made(closed, "a")
    place = str(closed.own / "a")
    s = closed.session(place).client()
    script += [{"tools": [("Bash", {"command": "ln -s /etc/hostname h; ln -s /proc/1/cmdline c"})]},
               {"tools": [("Read", {"file_path": "h"})]}, {"content": "done"}]
    llm = ChatProvider(OpenAIWire(url, "m"), "m", execution=closed)
    assert llm.agent_round("s", "go", ("Bash", "Read"), cwd=place, timeout=120) == "done"
    host = subprocess.run(["docker", "exec", s.container, "cat", "/etc/hostname"], capture_output=True, text=True).stdout.strip()
    assert host and host in seen[2]["body"]["messages"][-1]["content"], seen[2]["body"]["messages"][-1]["content"]
