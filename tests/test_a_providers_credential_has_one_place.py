"""A provider's credential has one place, one door, and reaches its own client alone.

The author, 2026-10-28: «по регламенту факторки должно быть только одно место для вставки токена и только там»;
«единственное место провайдера должно быть в классе провайдера и едином ендпоинте для всех». Before, a key sat in an
environment variable, a token in a container's env-file, a default in a launcher — and which of them a call ran on
depended on who started it (the E3 rows ran on the author's own login while a second account was meant). So: the store
round trip; a key in the environment is not read and not inherited; the CLI's process gets the stored one and its
tools' shells none; a container call carries a secret by name, its value never in argv; both doors write through the
same act and never answer with a value; and the battery fails an agent role whose tools can print a credential.
"""
import io
import json
import os
import stat
import sys
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from gfso import cli, doctor
from gfso.adapters.execution import ContainerExecution
from gfso.adapters.llm import credentials, registry
from gfso.adapters.llm.headless import ClaudeCodeProvider, client_env
from gfso.adapters.llm.conformance import AGENT_ROLES, ONE_SHOT_ROLES, assess
from gfso.adapters.llm.stub import StubLLM
from gfso.api.server import create_app
from gfso.config import subprocess_env
from gfso.llm import llm_factory
from tests.support import make_engine
from tests.test_a_session_is_launched_the_same_through_its_provider import seen  # noqa: F401 — the fake CLI


def _one(kind, name=None):
    """What the door shows of a provider holding one credential, `name` (default: its kind)."""
    n = name or kind
    return {"active": n, "in_force": n, "order": [n], "held": {n: kind}}


@pytest.fixture(autouse=True)
def store(monkeypatch, tmp_path):
    monkeypatch.setenv("GFSO_DATA_DIR", str(tmp_path / "data"))
    return tmp_path / "data" / "credentials.json"


def test_the_store_keeps_what_was_set_and_shows_only_its_kind(store):
    assert credentials.put("deepseek", "api", " k-ds \n") == {"deepseek": _one("api")}
    assert credentials.get("deepseek") == credentials.Credential("api", "k-ds")
    credentials.put("claude", "token", "t-sub")
    assert credentials.listing() == {"deepseek": _one("api"), "claude": _one("token")}
    assert "k-ds" not in str(credentials.listing()) and "t-sub" not in str(credentials.listing())
    assert credentials.put("deepseek", "api", None) == {"claude": _one("token")} and credentials.get("deepseek") is None
    if os.name != "nt":                        # a mode only a POSIX file system keeps
        assert stat.S_IMODE(store.stat().st_mode) == 0o600


def test_the_door_refuses_a_kind_the_provider_does_not_take():
    with pytest.raises(ValueError):
        registry.set_credential("ollama", "api", "k")          # a local server takes none
    with pytest.raises(ValueError):
        registry.set_credential("deepseek", "token", "t")      # an API key only
    with pytest.raises(ValueError):
        registry.set_credential("nobody", "api", "k")
    registry.set_credential("claude", "token", "sk-ant-oat01-t")
    got = registry.set_credential("claude", "api", "sk-ant-api03-k")["claude"]          # both, each under its name
    assert got["held"] == {"token": "token", "api": "api"} and got["active"] == "token"


def test_a_presets_key_comes_from_the_store_alone(monkeypatch):
    monkeypatch.setenv("DEEPSEEK_API_KEY", "k-env")
    monkeypatch.setenv("GFSO_PROVIDER_DEEPSEEK_API_KEY", "k-env2")
    assert "gfso credential deepseek" in (llm_factory("deepseek/deepseek-chat").wire.missing_key or "")
    registry.set_credential("deepseek", "api", "k-stored")
    llm = llm_factory("deepseek/deepseek-chat")
    assert llm.wire.missing_key is None and llm.wire._key == "k-stored"


def test_the_cli_is_given_the_stored_token_and_no_inherited_one(seen, monkeypatch):  # noqa: F811
    monkeypatch.setenv("CLAUDE_CODE_OAUTH_TOKEN", "t-inherited")   # beside the fixture's inherited ANTHROPIC_API_KEY
    credentials.put("claude", "token", "t-stored")
    llm_factory("m").complete("x", "SYS")
    env = seen[0]["env"]
    assert "ANTHROPIC_API_KEY" not in env and env["CLAUDE_CODE_OAUTH_TOKEN"] == "t-stored"
    assert env["CLAUDE_CODE_SUBPROCESS_ENV_SCRUB"] == "1"


def test_an_empty_store_runs_no_call_on_the_hosts_login(seen, store):  # noqa: F811
    """The author: «как она фолбекается на логин без самого фолбек механизма который задан в кредах?» — a fallback is
    an entry of the list, so with none in force the call is refused and no CLI process starts."""
    llm = llm_factory("m")
    assert llm.complete("x", "SYS") == "" and seen == []
    [rec] = llm.calls
    assert rec["ended"] == "unauthorized" and str(store) in rec["error"] and rec["credential"] is None


def test_a_provider_made_with_no_credential_runs_no_call_on_the_hosts_login(seen, store):  # noqa: F811
    """`credential=None` once meant the host's login: the same undeclared fallback by another door, refused alike."""
    credentials.put("claude", "token", "t-stored")          # a store in force does not stand in for the None given
    llm = ClaudeCodeProvider(model="m", credential=None)
    assert llm.complete("x", "SYS") == "" and seen == []
    assert llm.calls[-1]["ended"] == "unauthorized" and "no credential" in llm.calls[-1]["error"]


def test_every_child_starts_without_a_key(monkeypatch):
    for k in ("ANTHROPIC_API_KEY", "ANTHROPIC_AUTH_TOKEN", "CLAUDE_CODE_OAUTH_TOKEN", "X_SECRET", "DB_PASSWORD"):
        monkeypatch.setenv(k, "v")
    env = subprocess_env()
    assert not {"ANTHROPIC_API_KEY", "ANTHROPIC_AUTH_TOKEN", "CLAUDE_CODE_OAUTH_TOKEN", "X_SECRET", "DB_PASSWORD"} & set(env)


def _container(tmp_path, monkeypatch):
    base = tmp_path / "work" / "base"
    base.mkdir(parents=True)
    x = ContainerExecution("e3-linux", "img", None, str(tmp_path / "state"), str(base), "p")
    monkeypatch.setattr(x, "start", lambda: None)
    return x, base


def test_a_container_call_carries_a_secret_by_name_and_its_value_beside_argv(tmp_path, monkeypatch):
    x, base = _container(tmp_path, monkeypatch)
    argv, client = x._exec_argv(["claude", "-p"], {"CLAUDE_CODE_OAUTH_TOKEN": "t-1", "MAX_THINKING_TOKENS": "9"},
                                str(base), "c1")
    assert "CLAUDE_CODE_OAUTH_TOKEN" in argv and not any("t-1" in a for a in argv)
    assert "MAX_THINKING_TOKENS=9" in argv and client["CLAUDE_CODE_OAUTH_TOKEN"] == "t-1"


def test_a_container_without_an_env_file_is_run_without_one(tmp_path, monkeypatch):
    assert "--env-file" not in _container(tmp_path, monkeypatch)[0].run_args()


def test_the_cli_door_writes_and_never_prints_the_value(monkeypatch, capsys):
    monkeypatch.setattr(sys, "argv", ["gfso", "credential", "deepseek"])
    monkeypatch.setattr(sys, "stdin", io.StringIO("k-cli-secret\n"))
    with pytest.raises(SystemExit) as done:
        cli.main()
    said = capsys.readouterr()
    assert done.value.code == 0 and credentials.get("deepseek") == credentials.Credential("api", "k-cli-secret")
    assert "k-cli-secret" not in said.out + said.err and json.loads(said.out) == {"deepseek": _one("api")}


@pytest.mark.parametrize("given", [[], ["--kind", "token"]])
def test_an_api_key_given_as_a_token_is_held_as_what_it_is(monkeypatch, capsys, given):
    """At Claude's default prompt it was held as a token, and the first call was refused with a remedy for another fault."""
    monkeypatch.setattr(sys, "argv", ["gfso", "credential", "claude", *given])
    monkeypatch.setattr(sys, "stdin", io.StringIO("sk-ant-api03-secret\n"))
    with pytest.raises(SystemExit) as done:
        cli.main()
    said = capsys.readouterr()
    assert done.value.code == 0 and credentials.get("claude") == credentials.Credential("api", "sk-ant-api03-secret")
    assert "secret" not in said.out + said.err and json.loads(said.out) == {"claude": _one("api")}


def test_a_token_stays_a_token():
    registry.set_credential("claude", "token", "sk-ant-oat01-x")
    assert credentials.get("claude").kind == "token"


def test_the_http_door_writes_and_never_answers_the_value():
    engine = make_engine(llm=StubLLM(), validate_signals=False)
    engine.start()
    c = TestClient(create_app(engine))
    put = c.put("/api/credentials/deepseek", json={"value": "k-http-secret"})
    assert put.status_code == 200 and put.json() == {"deepseek": _one("api")}
    got = c.get("/api/credentials")
    assert got.json() == {"deepseek": _one("api")} and "k-http-secret" not in got.text
    assert c.put("/api/credentials/deepseek", json={"value": " "}).status_code == 422
    assert c.put("/api/credentials/deepseek", json={"kind": "token", "value": "t"}).status_code == 422
    assert c.put("/api/credentials/deepseek", json={"remove": True}).json() == {}


class _Agent:
    """A provider passing every case of the battery, its tools' shell holding `shell` besides PATH."""
    runs_agents, execution, last_tool_calls = True, None, {"Bash": 1}

    def __init__(self, shell: str = ""):
        self.shell, self.calls = shell, [{"input_tokens": 1, "output_tokens": 1}]

    def complete(self, *a, **k):
        return "pong"

    def complete_structured(self, *a, **k):
        return {"answer": 5}

    def run_agent(self, system, user, tools, *, cwd, **k):
        if "probe.txt" in user:
            (Path(cwd) / "probe.txt").write_text("41")
            return "42"
        if "env.txt" in user:
            (Path(cwd) / "env.txt").write_text("PATH=/usr/bin\n" + self.shell)
            return "done"
        return '```json\n{"status": "delivered", "printed": "5050"}\n```'


@pytest.mark.parametrize("shell", ["", "HOME=/home/agent\n"])
def test_an_agent_whose_tools_see_no_credential_holds_every_role(shell):
    credentials.put("deepseek", "api", "k-stored-value")
    found = assess(_Agent(shell))
    assert found["checks"]["credential hidden"]["pass"] and found["roles"] == [*ONE_SHOT_ROLES, *AGENT_ROLES]


@pytest.mark.parametrize("shell", ["SOME_API_KEY=x\n", "INNOCENT=k-stored-value\n"])
def test_an_agent_whose_tools_print_a_credential_holds_no_agent_role(shell):
    credentials.put("deepseek", "api", "k-stored-value")
    found = assess(_Agent(shell))
    assert not found["checks"]["credential hidden"]["pass"] and found["roles"] == list(ONE_SHOT_ROLES)


def test_an_execution_whose_env_file_holds_a_credential_is_refused(tmp_path):
    """The container's env-file was a second place, live in every call the system makes inside (critic over S4)."""
    env = tmp_path / "e.env"
    env.write_text("TZ=UTC\nCLAUDE_CODE_OAUTH_TOKEN=x\n", encoding="utf-8")
    with pytest.raises(ValueError, match="CLAUDE_CODE_OAUTH_TOKEN"):
        ContainerExecution("e3-linux", "img", str(env), str(tmp_path / "state"), str(tmp_path / "ws"), "p")
    env.write_text("TZ=UTC\n", encoding="utf-8")
    ContainerExecution("e3-linux", "img", str(env), str(tmp_path / "state"), str(tmp_path / "ws"), "p")


def test_a_cli_whose_execution_cannot_scrub_is_not_told_to():
    """On Linux the CLI's scrub needs bubblewrap; told to scrub without it, the CLI exited before its first turn and
    every call of a row's planner came back cut (probed: e3-linux-agent:2, CLI 2.1.310)."""
    tok = credentials.Credential("token", "t")
    assert client_env(tok, True)["CLAUDE_CODE_SUBPROCESS_ENV_SCRUB"] == "1"
    assert client_env(tok, False) == {"CLAUDE_CODE_SUBPROCESS_ENV_SCRUB": "0", "CLAUDE_CODE_OAUTH_TOKEN": "t"}


Ran = lambda rc: type("R", (), {"returncode": rc})


@pytest.mark.parametrize("platform", ["win32", "darwin"])
def test_the_agent_opens_a_window_that_runs_one_gfso_command_and_returns(monkeypatch, capsys, platform):
    """The author: «почему это не может инициировать агент?»; «чтобы не складывалось впечатление что gfso ворует
    токены». A generated shell script ran a backticked `--remove` under macOS and stopped at an npm `claude.cmd` under
    Windows (critic, 2026-11-08): the window runs one gfso command, and the agent's call returns at once."""
    opened = []
    monkeypatch.setattr(doctor.sys, "platform", platform)
    monkeypatch.setattr(doctor.subprocess, "Popen", lambda argv, **kw: opened.append((argv, kw)))
    monkeypatch.setattr(doctor.subprocess, "run", lambda argv, **kw: opened.append((argv, kw)) or Ran(0))
    monkeypatch.setattr(cli, "console_script", lambda: r"C:\Users\Имя Фамилия\gfso.exe")
    monkeypatch.setattr(sys, "argv", ["gfso", "credential", "claude", "--sign-in"])
    with pytest.raises(SystemExit) as done:
        cli.main()
    (argv, kw), = opened
    said = " ".join(argv)
    assert done.value.code == 0 and "--sign-in-here" in said and "`" not in said and "Имя Фамилия" in said
    told = capsys.readouterr().out
    assert ("creationflags" in kw) is (platform == "win32") and "never passes the chat" in told
    assert "gfso credential claude --wait" in told and "again" in told, "the agent is sent to wait for the store, not for the person"


def _waited(monkeypatch) -> pytest.ExceptionInfo:
    monkeypatch.setattr(sys, "argv", ["gfso", "credential", "claude", "--wait"])
    with pytest.raises(SystemExit) as done:
        cli.main()
    return done


def test_wait_returns_as_soon_as_the_window_has_kept_the_token(monkeypatch, capsys):
    """Told "write to me when done", the client stood still until the person said so (e2e1, 2026-11-09): the window writes
    the one store, so an agent's bounded call sees it."""
    calls = []
    monkeypatch.setattr(doctor.time, "sleep",
                        lambda s: calls.append(s) or registry.set_credential("claude", "token", "sk-ant-oat01-" + "w" * 95))
    assert _waited(monkeypatch).value.code == 0 and len(calls) == 1
    assert "held" in capsys.readouterr().out


def test_wait_says_not_yet_and_stays_under_a_clients_limit_on_a_call(monkeypatch):
    """Bounded: a client's own limit on one command is two minutes by default."""
    assert doctor.WAIT_S < 120
    monkeypatch.setattr(doctor, "WAIT_S", 0)
    done = _waited(monkeypatch)
    assert done.value.code not in (0, None) and "not yet" in str(done.value.code) and "--wait" in str(done.value.code)


def test_wait_is_the_subscriptions(monkeypatch):
    monkeypatch.setattr(sys, "argv", ["gfso", "credential", "deepseek", "--wait"])
    with pytest.raises(SystemExit) as done:
        cli.main()
    assert "claude" in str(done.value.code)


def test_the_window_keeps_one_paste_and_says_what_it_kept(monkeypatch, capsys):
    """The author: «токен получил а дальше не понятно что»; «может я дважды скопировал»: each step is said where it is
    taken, a doubled paste is refused and asked again, and what was kept is shown, never the whole."""
    token = "sk-ant-oat01-" + "q" * 90 + "Zq9w"
    pastes = iter([token + token, token])
    ran = []
    monkeypatch.setattr(doctor.subprocess, "run", lambda argv, **kw: ran.append(argv) or Ran(0))
    monkeypatch.setattr(doctor.getpass, "getpass", lambda prompt: next(pastes))
    monkeypatch.setattr("builtins.input", lambda prompt="": "")
    assert doctor.sign_in_here() == 0
    out = capsys.readouterr().out
    assert ran[0][-1] == "setup-token" and credentials.get("claude") == credentials.Credential("token", token)
    assert "What it is for" in out and "pasted twice" in out and "Step 2 of 2" in out and "…Zq9w (107 characters)" in out and "q" * 20 not in out
    assert "go back to your chat; your agent sees this by itself" in out


def test_with_no_window_to_open_the_steps_are_said(monkeypatch):
    monkeypatch.setattr("gfso.doctor.sys.platform", "linux")
    monkeypatch.setattr(sys, "argv", ["gfso", "credential", "claude", "--sign-in"])
    with pytest.raises(SystemExit) as done:
        cli.main()
    assert "claude setup-token" in str(done.value.code) and "gfso credential claude" in str(done.value.code)


@pytest.mark.parametrize("pasted, why", [("sk-ant-oat01-aaa" * 2, "pasted twice"), ("sk-ant-oat01-aaa\nhello", "line breaks")])
def test_a_paste_made_twice_or_with_text_around_it_is_refused(pasted, why):
    """The author: «при вставке не видно сколько символов вставилось… может я дважды скопировал»."""
    with pytest.raises(ValueError, match=why):
        registry.set_credential("claude", "token", pasted)
    assert credentials.get("claude") is None


def test_the_person_is_shown_what_was_kept_and_never_the_whole(monkeypatch, capsys):
    monkeypatch.setattr(sys, "argv", ["gfso", "credential", "claude"])
    monkeypatch.setattr(sys, "stdin", io.StringIO("sk-ant-oat01-" + "x" * 90 + "Zq9w\n"))
    with pytest.raises(SystemExit):
        cli.main()
    said = capsys.readouterr()
    assert "kept sk-ant-oat01-…Zq9w (107 characters)" in said.err and "x" * 20 not in said.out + said.err


@pytest.mark.parametrize("paste", ["", "   "])
def test_an_empty_paste_is_refused_and_a_held_token_stays(paste):
    """An empty Enter in the window stored an empty token over a good one, and `doctor` read it as set (critic)."""
    registry.set_credential("claude", "token", "sk-ant-oat01-good")
    with pytest.raises(ValueError, match="nothing was given"):
        registry.set_credential("claude", "token", paste)
    assert credentials.get("claude") == credentials.Credential("token", "sk-ant-oat01-good")


def test_a_sign_in_that_did_not_finish_says_so_and_keeps_nothing(monkeypatch, capsys):
    monkeypatch.setattr(doctor.subprocess, "run", lambda argv, **kw: Ran(1))
    monkeypatch.setattr(doctor.getpass, "getpass", lambda prompt: pytest.fail("asked a paste of a token never shown"))
    monkeypatch.setattr("builtins.input", lambda prompt="": print(prompt))
    assert doctor.sign_in_here() == 1
    assert "did not finish" in capsys.readouterr().out and credentials.get("claude") is None
