"""An account that refuses authentication is a stop in substance, as its limit is: no role's call can answer until a
person signs it in, and the redials of a cut call spent an hour on it while every bound ran (GB_c_compiler_tncfs1160,
2026-10-23: "403 Failed to authenticate", four nodes timed out). And a round continued after its turn cap books its own
cost, not the whole conversation's (the CLI's `total_cost_usd` on `--resume`: GB_sql_database_tnildb300, +$5.86)."""
from __future__ import annotations

import io
import json
import threading
import time

import pytest

from gfso import decompose as DEC, tools_llm as TL
from gfso.adapters import execution as E
from gfso.adapters.llm import credentials, headless as H
from gfso.adapters.llm.stats import refused_by_limit
from gfso.core.types import TaskId
from gfso.issuer import LIMIT_RETRY_S
from tests.support import hold_a_credential, make_engine

#: the stream of a refused authentication (the validator's, tncfs1160, trimmed to its result)
REFUSED_STREAM = [{"type": "result", "is_error": True, "subtype": "success", "terminal_reason": "api_error",
                   "api_error": "authentication_error", "result": "API Error: 403 Failed to authenticate"}]


@pytest.fixture(autouse=True)
def _held(monkeypatch, tmp_path):
    """…so a refusal read here is the CLI's 403, not the empty store's (`headless._in_force` books that one alike)."""
    hold_a_credential(monkeypatch, tmp_path)


class _Proc:
    stdin = io.StringIO()

    def __init__(self, lines):
        self.stdout = iter(json.dumps(x) + "\n" for x in lines)

    def wait(self, timeout=None):
        return 0


def _cli(monkeypatch, lines):
    monkeypatch.setattr(H.subprocess, "Popen", lambda args, **kw: _Proc(lines))
    monkeypatch.setattr(E.LocalExecution, "which", lambda self, program: program)   # …a machine with no CLI, as CI is
    for name in ("adopt", "kill_tree", "release"):
        monkeypatch.setattr(E, name, lambda p: p)


def test_the_cli_says_the_account_refused(monkeypatch, tmp_path):
    _cli(monkeypatch, REFUSED_STREAM)
    llm = H.ClaudeCodeProvider()
    llm._cmd = "claude"
    assert llm.run_agent("sys", "packet", ("Read",), cwd=str(tmp_path)) == ""
    assert llm.calls[-1]["ended"] == "unauthorized" and refused_by_limit(llm.calls), llm.calls[-1]


def test_a_refused_account_stops_the_project_and_is_asked_again():
    e = make_engine(llm=None)
    t0 = time.time()
    e.record_llm_usage("validator", [{"ended": "unauthorized", "error": "api_error: 403 Failed to authenticate"}],
                       TaskId("n"))
    stop = e.paused()
    assert stop and "authentication" in stop["why"] and "validator" in stop["why"], stop
    assert t0 + LIMIT_RETRY_S <= stop["until"] <= time.time() + LIMIT_RETRY_S + 60
    e.lift_the_system_stop(stop["until"])
    assert e.paused() is None, "the system did not start what it stopped"


def _plan_refused(monkeypatch) -> tuple:
    """(the error `plan` answers, the stop it left) — a fresh user's first call, through the real provider."""
    monkeypatch.setattr(DEC, "_default_llm", lambda model, execution=None: H.ClaudeCodeProvider(model, execution=execution))
    _cli(monkeypatch, REFUSED_STREAM)
    e = make_engine(llm=None)
    out = TL.TOOLS["plan"](e, request="count the words of a file")
    return str(out.get("error")), e.paused() or {}


def _no_wrong_remedy(said: str) -> None:
    assert "sign it in" not in said and "auto_decompose" not in said, said


def test_a_refused_token_names_the_one_remedy_and_the_verb_called(monkeypatch):
    """`claude login` lifts nothing: no call runs outside the store; and the path's verb is `plan`."""
    err, stop = _plan_refused(monkeypatch)
    assert "token was refused" in err and "`claude setup-token`, then `gfso credential claude`" in err, err
    assert "call plan again" in err, err
    assert "`claude setup-token`" in stop["why"], stop
    _no_wrong_remedy(err), _no_wrong_remedy(stop["why"])


def test_no_credential_at_all_is_named_as_none_with_the_same_remedy(monkeypatch):
    credentials.put("claude", "token", None)
    box = {}     # …on a thread of its own, as a server's first call is: one that had a credential before hid a crash here
    t = threading.Thread(target=lambda: box.update(got=_plan_refused(monkeypatch)))
    t.start(), t.join()
    err, stop = box["got"]
    assert "no credential of 'claude'" in err and "`claude setup-token`, then `gfso credential claude`" in err, err
    assert "was refused" not in err.split(":")[0], err
    assert "call plan again" in err and "no credential of 'claude'" in stop["why"], (err, stop)
    _no_wrong_remedy(err), _no_wrong_remedy(stop["why"])


def test_a_refused_api_key_is_not_told_to_make_a_token(monkeypatch):
    credentials.put("claude", "token", None)
    credentials.put("claude", "api", "sk-ant-api-x")
    err, _ = _plan_refused(monkeypatch)
    assert "API key was refused" in err and "`gfso credential claude --kind api`" in err and "setup-token" not in err, err
    assert "sk-ant-api-x" not in err, "a value is never said"


class _Here(E.LocalExecution):
    def __init__(self, state):
        self.state = state

    def state_dir(self):
        return self.state


def _result(cost, subtype="success"):
    return [{"type": "result", "is_error": subtype != "success", "subtype": subtype, "total_cost_usd": cost,
             "num_turns": 1, "result": "done" if subtype == "success" else ""}]


def test_a_continued_round_books_its_own_cost(monkeypatch, tmp_path):
    llm = H.ClaudeCodeProvider(execution=_Here(tmp_path / "state"))
    llm._cmd = "claude"
    _cli(monkeypatch, _result(1.60, "error_max_turns"))
    llm.run_agent("sys", "packet", ("Read",), cwd=str(tmp_path), session="s1")
    assert llm.calls[-1]["cost_usd"] == 1.60
    (tmp_path / "state" / "projects" / "x").mkdir(parents=True)
    (tmp_path / "state" / "projects" / "x" / "s1.jsonl").write_text("{}")   # the CLI kept the conversation
    _cli(monkeypatch, _result(1.64))
    llm.run_agent("sys", "go on", ("Read",), cwd=str(tmp_path), session="s1")
    assert llm.calls[-1]["resumed"] and abs(llm.calls[-1]["cost_usd"] - 0.04) < 1e-9, llm.calls[-1]
    assert not H.kept(llm.execution, "s1", "spent").exists(), "an answered conversation keeps nothing"


def test_a_round_books_the_life_of_its_process_not_its_last_results(monkeypatch):
    """A command that outlived its result kept the process alive past the CLI's own `duration_ms`: booked 3 s, lived
    729 s, and a timeline could not place the round (ui stream, 2026-10-27)."""
    def slow():
        time.sleep(0.3)
        yield json.dumps({**_result(0.01)[0], "duration_ms": 3}) + "\n"
    _cli(monkeypatch, [])
    monkeypatch.setattr(_Proc, "__init__", lambda self, lines: setattr(self, "stdout", slow()))
    llm = H.ClaudeCodeProvider()
    llm._cmd = "claude"
    llm.run_agent("sys", "packet", ("Read",), cwd=".")
    assert llm.calls[-1]["duration_ms"] >= 250, llm.calls[-1]       # the CLI said 3; the process lived ~300
