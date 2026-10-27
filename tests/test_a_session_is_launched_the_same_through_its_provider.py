"""A session's launch is its provider's, and moving it there changes nothing.

The provider factory's first step (docs/notes/PROVIDER_FACTORY.md) moves the `claude -p` path out of hardcode into one
provider class handing its process to an execution — the author: «текущее просто вынесется из хардкода в общий класс с
прокидкой всего того же что есть сейчас без изменений». So what every call starts with is pinned here byte for byte:
the program, the argv, the environment it inherits, the place it runs in and the prompt it is fed — for a one-shot, an
agent run opening a conversation, one continuing it, and the API key set in the provider's one place. How a call is ENDED
(the cap's timer, the mid-stream cap, `finally`, the cold retry) is not pinned here: the silent-child, conversation and
cut-call tests hold those (critic over ad639bc, by mutation).
"""
import io
import json
import os
import shutil
import subprocess
from pathlib import Path

import pytest

from gfso.adapters.llm import credentials
from gfso.config import SECRET_ENV
from gfso.llm import llm_factory

SETTINGS = '{"disableAllHooks": true, "language": ""}'
HEAD = ["/bin/claude", "-p", "--model", "m", "--system-prompt", "SYS", "--strict-mcp-config", "--settings", SETTINGS,
        "--safe-mode"]
STREAM = ["--output-format", "stream-json", "--include-partial-messages", "--verbose"]
ANSWER = {"type": "result", "result": "OK", "is_error": False, "usage": {"input_tokens": 3, "output_tokens": 1},
          "num_turns": 1, "total_cost_usd": 0.01}


class _Fed(io.StringIO):
    def __init__(self):
        super().__init__()
        self.fed = None

    def close(self):
        self.fed = self.getvalue()
        super().close()


class _Seen(list):
    """The calls started, and the fake process class that answers them."""


@pytest.fixture
def seen(monkeypatch, tmp_path):
    seen = _Seen()

    class _Proc:
        pid, returncode = 2 ** 22 + 7, 0       # no such group: a POSIX kill of it finds nothing

        def __init__(self, argv, **kw):
            seen.append({"argv": argv, **kw, "place_existed": bool(kw.get("cwd")) and Path(kw["cwd"]).is_dir()})
            self.stdin, self.stdout = _Fed(), iter([json.dumps(self.answer) + "\n"])
            seen[-1]["proc"] = self

        answer = ANSWER

        def poll(self):
            return 0

        def wait(self, timeout=None):
            return 0

        def kill(self):
            pass

    monkeypatch.setattr(subprocess, "Popen", _Proc)
    monkeypatch.setattr(shutil, "which", lambda cmd: "/bin/" + cmd)
    monkeypatch.setenv("CLAUDE_CONFIG_DIR", str(tmp_path / "cli"))
    monkeypatch.setenv("ANTHROPIC_API_KEY", "k")
    monkeypatch.setenv("GFSO_SERVING", "1")
    monkeypatch.delenv("CLAUDE_CODE_MAX_OUTPUT_TOKENS", raising=False)
    monkeypatch.delenv("GFSO_PROVIDER", raising=False)
    monkeypatch.setenv("GFSO_DATA_DIR", str(tmp_path / "data"))
    seen.Proc = _Proc
    return seen


#: what every call's environment drops and adds: no inherited key or token, no server mark; room to answer, and its
#: tools' shells scrubbed of the credential the CLI itself is given
def DROPPED() -> set:
    return {k for k in os.environ if SECRET_ENV.search(k)} | {"GFSO_SERVING"}


ADDED ={"CLAUDE_CODE_MAX_OUTPUT_TOKENS": "64000", "CLAUDE_CODE_SUBPROCESS_ENV_SCRUB": "1"}


def _env_change(env: dict) -> tuple[set, dict]:
    """What the child's environment drops from this process's and what it adds or changes."""
    return ({k for k in os.environ if k not in env},
            {k: v for k, v in env.items() if os.environ.get(k) != v})


def _spawn_keywords(call: dict) -> dict:
    return {k: call.get(k) for k in ("stdin", "stdout", "stderr", "text", "encoding", "creationflags",
                                     "start_new_session")}


SPAWN = {"stdin": subprocess.PIPE, "stdout": subprocess.PIPE, "stderr": subprocess.DEVNULL, "text": True,
         "encoding": "utf-8",
         "creationflags": subprocess.CREATE_NO_WINDOW if os.name == "nt" else None,
         "start_new_session": None if os.name == "nt" else True}


def test_a_one_shot_starts_in_an_empty_place_of_its_own_with_no_tools(seen):
    assert llm_factory("m").complete("hello", "SYS") == "OK"
    [call] = seen
    assert call["argv"] == HEAD + ["--no-session-persistence"] + STREAM + ["--disallowedTools", "*"]
    assert Path(call["cwd"]).name.startswith("gfso-noplace-") and call["place_existed"]
    assert not Path(call["cwd"]).exists(), "the empty place is removed once the call ends"
    assert "ANTHROPIC_API_KEY" in DROPPED() and _env_change(call["env"]) == (DROPPED(), ADDED)
    assert _spawn_keywords(call) == SPAWN
    assert call["proc"].stdin.fed == "hello"


def test_an_agent_run_opens_its_conversation_then_continues_it_only_after_its_turn_cap(seen, tmp_path):
    work = tmp_path / "work"
    work.mkdir()
    llm = llm_factory("m")
    tools = ("Read", "Bash(git:*)", "Bash(ls)")
    tail = ["--tools", "Read,Bash", "--allowedTools", "Read Bash(git:*) Bash(ls)", "--dangerously-skip-permissions",
            "--max-turns", "5"]
    assert llm.run_agent("SYS", "do it", tools, cwd=str(work), max_turns=5, session="sid") == "OK"
    assert seen[0]["argv"] == HEAD + ["--session-id", "sid"] + STREAM + tail
    assert Path(seen[0]["cwd"]) == work and seen[0]["proc"].stdin.fed == "do it"

    kept = tmp_path / "cli" / "projects" / "enc" / "sid.jsonl"
    kept.parent.mkdir(parents=True)
    kept.write_text("{}")
    seen.Proc.answer = {**ANSWER, "is_error": True, "subtype": "error_max_turns", "result": ""}
    llm.run_agent("SYS", "go on", tools, cwd=str(work), max_turns=5, session="sid")
    assert seen[1]["argv"] == HEAD + ["--resume", "sid"] + STREAM + tail
    assert kept.exists(), "a round cut at its turn cap keeps the conversation the next round continues"

    seen.Proc.answer = ANSWER
    llm.run_agent("SYS", "finish", tools, cwd=str(work), session="sid")
    assert seen[2]["argv"] == HEAD + ["--resume", "sid"] + STREAM + tail[:-2]
    assert not kept.exists(), "an answered round forgets its conversation"


def test_per_token_billing_runs_on_the_stored_key_not_the_inherited_one(seen):
    credentials.put("claude", "api", "k-stored")
    llm_factory("m").complete("x", "SYS")
    assert _env_change(seen[0]["env"]) == (DROPPED() - {"ANTHROPIC_API_KEY"}, {**ADDED, "ANTHROPIC_API_KEY": "k-stored"})


def test_an_agent_run_without_a_place_is_refused_before_anything_starts(seen):
    with pytest.raises(ValueError):
        llm_factory("m").run_agent("SYS", "u", ("Read",))
    assert seen == []
