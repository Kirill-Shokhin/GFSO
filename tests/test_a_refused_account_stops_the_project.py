"""An account that refuses authentication is a stop in substance, as its limit is: no role's call can answer until a
person signs it in, and the redials of a cut call spent an hour on it while every bound ran (GB_c_compiler_tncfs1160,
2026-10-23: "403 Failed to authenticate", four nodes timed out). And a round continued after its turn cap books its own
cost, not the whole conversation's (the CLI's `total_cost_usd` on `--resume`: GB_sql_database_tnildb300, +$5.86)."""
from __future__ import annotations

import io
import json
import time

from gfso.adapters import execution as E
from gfso.adapters.llm import headless as H
from gfso.adapters.llm.stats import refused_by_limit
from gfso.core.types import TaskId
from gfso.issuer import LIMIT_RETRY_S
from tests.support import make_engine

#: the stream of a refused authentication (the validator's, tncfs1160, trimmed to its result)
REFUSED_STREAM = [{"type": "result", "is_error": True, "subtype": "success", "terminal_reason": "api_error",
                   "api_error": "authentication_error", "result": "API Error: 403 Failed to authenticate"}]


class _Proc:
    stdin = io.StringIO()

    def __init__(self, lines):
        self.stdout = iter(json.dumps(x) + "\n" for x in lines)

    def wait(self, timeout=None):
        return 0


def _cli(monkeypatch, lines):
    monkeypatch.setattr(H.subprocess, "Popen", lambda args, **kw: _Proc(lines))
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
    assert not llm._spent_file("s1").exists(), "an answered conversation keeps nothing"
