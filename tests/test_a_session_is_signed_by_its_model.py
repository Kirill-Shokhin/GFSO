"""A model session is recorded with what a person needs to read the work it did: the model that ran it, what it
read from the cache apart from what it wrote, how full its context got against its model's window, its turns —
and a project is listed with the models that ran it.

The author, 2026-10-25: «нигде нет подписи моделей … модель это реальный исполнитель ноды … сколько было реальных
контекстов, насколько они по итогу заполнены, какое разбиение по вкладу в цену — это то, что я спрашиваю у агента,
а должен разумеется видеть». The ledger kept the model but summed the cache read with the cache written, and the
envelope's own usage sums every turn, so how close a session came to its window was nowhere.
"""
import io
import json
import sqlite3

import pytest

from gfso.adapters import execution as E
from gfso.adapters.llm import headless as H
from gfso.adapters.storage.sqlite import SqliteStorage, peek_project
from tests.support import hold_a_credential, make_engine


@pytest.fixture(autouse=True)
def _held(monkeypatch, tmp_path):
    hold_a_credential(monkeypatch, tmp_path)


def _turn(i, w, r, out=10, mid="m1"):
    return {"type": "assistant", "message": {"id": mid, "content": [{"type": "text", "text": "."}],
            "usage": {"input_tokens": i, "cache_creation_input_tokens": w, "cache_read_input_tokens": r, "output_tokens": out}}}


_RESULT = {"type": "result", "subtype": "success", "result": "done", "num_turns": 2, "total_cost_usd": 0.31,
           "usage": {"input_tokens": 5, "output_tokens": 20, "cache_read_input_tokens": 68618, "cache_creation_input_tokens": 5208},
           "modelUsage": {"claude-haiku-4-5": {"costUSD": 0.01, "contextWindow": 200000},
                          "claude-sonnet-5-5": {"costUSD": 0.30, "contextWindow": 1000000}}}


class _Proc:
    def __init__(self, events):
        self.stdout = iter(json.dumps(e) + "\n" for e in events)
        self.stdin, self.pid = io.StringIO(), 0

    def wait(self, timeout=None):
        return 0

    def poll(self):
        return 0


def _run(monkeypatch, events):
    monkeypatch.setattr(H.subprocess, "Popen", lambda *a, **k: _Proc(events))
    for name in ("adopt", "kill_tree", "release"):               # a fake child has no process to end
        monkeypatch.setattr(E, name, (lambda p: p) if name == "adopt" else (lambda p: None))
    llm = H.ClaudeCodeProvider(model="sonnet")   # asked by its alias
    llm._cmd = llm._cmd or "claude"
    assert llm.complete("x") == "done"
    return llm.calls[-1]


def test_a_session_keeps_its_fullest_turn_its_window_and_its_turns(monkeypatch):
    call = _run(monkeypatch, [_turn(2, 5108, 28618, mid="a"), _turn(3, 100, 40000, mid="b"), _RESULT])
    assert call["peak_context"] == 3 + 100 + 40000, "the fullest turn, not the sum over turns"
    assert call["model"] == "claude-sonnet-5-5", "the model that ran it, not the alias it was asked by"
    assert call["context_window"] == 1000000, "the window of the model that cost most in the session"
    assert call["turns"] == 2
    assert (call["cache_read_input_tokens"], call["cache_creation_input_tokens"]) == (68618, 5208)
    assert call["ended"] == "answered"


def test_a_session_whose_stream_says_nothing_of_it_records_nothing(monkeypatch):
    call = _run(monkeypatch, [{"type": "result", "result": "done", "total_cost_usd": 0.01}])
    assert (call["peak_context"], call["context_window"], call["turns"]) == (None, None, None)
    assert call["model"] == "sonnet", "with no word on which model ran, the one asked for"


def test_the_ledger_keeps_cache_read_apart_from_cache_written_and_an_absent_reading_absent(tmp_path):
    e = make_engine(storage=SqliteStorage(str(tmp_path / "p.db")))
    e._storage.log_usage({"ts": "2026-10-25 01:00:00", "stage": "executor", "model": "claude-sonnet-5-5", "node_id": "root",
                          "cache_input_tokens": 73826, "cache_read_tokens": 68618, "cache_write_tokens": 5208,
                          "peak_context": 40103, "context_window": 1000000, "turns": 2, "cost_usd": 0.31})
    e._storage.log_usage({"ts": "2026-10-25 01:01:00", "stage": "validator", "model": "claude-haiku-4-5", "node_id": "root",
                          "cache_input_tokens": 900, "cost_usd": 0.02})
    new, old = e.usage_calls()
    assert (new["cache_read_tokens"], new["cache_write_tokens"], new["peak_context"], new["context_window"], new["turns"]) \
        == (68618, 5208, 40103, 1000000, 2)
    assert (old["cache_read_tokens"], old["peak_context"], old["cache_input_tokens"]) == (None, None, 900), \
        "a reading the session did not give is absent, not zero"
    about = peek_project(str(tmp_path / "p.db"))
    assert about["models"] == ["claude-sonnet-5-5", "claude-haiku-4-5"], "the models that ran it, costliest first"


def test_a_database_from_before_the_readings_opens_with_them_absent(tmp_path):
    path = str(tmp_path / "old.db")
    with sqlite3.connect(path) as c:
        c.execute("CREATE TABLE llm_usage (id INTEGER PRIMARY KEY AUTOINCREMENT, ts TEXT NOT NULL, stage TEXT NOT NULL, "
                  "model TEXT DEFAULT '', node_id TEXT, input_tokens INTEGER DEFAULT 0, output_tokens INTEGER DEFAULT 0, "
                  "cache_input_tokens INTEGER DEFAULT 0, cost_usd REAL DEFAULT 0.0, duration_ms INTEGER DEFAULT 0)")
        c.execute("INSERT INTO llm_usage (ts, stage, model, cache_input_tokens) VALUES ('2026-10-01 10:00:00', 'executor', 'm', 7)")
    rows = SqliteStorage(path).get_usage()
    assert rows[0]["cache_input_tokens"] == 7 and rows[0]["peak_context"] is None


def test_a_cut_session_is_signed_by_the_model_its_turns_name(monkeypatch):
    """A stream cut before its result event names no `modelUsage`; its turns still say which model answered. A
    refusal the CLI makes itself (an account limit) names `<synthetic>`, which is no model."""
    named = dict(_turn(1, 0, 900), message={**_turn(1, 0, 900)["message"], "model": "claude-haiku-4-5-20251001"})
    monkeypatch.setattr(H.subprocess, "Popen", lambda *a, **k: _Proc([named]))
    for name in ("adopt", "kill_tree", "release"):
        monkeypatch.setattr(E, name, (lambda p: p) if name == "adopt" else (lambda p: None))
    llm = H.ClaudeCodeProvider(model="haiku")
    llm._cmd = llm._cmd or "claude"
    llm.complete("x")
    assert llm.calls[-1]["model"] == "claude-haiku-4-5-20251001" and llm.calls[-1]["transport_torn"]
    refusal = dict(_turn(0, 0, 0), message={**_turn(0, 0, 0)["message"], "model": "<synthetic>"})
    monkeypatch.setattr(H.subprocess, "Popen", lambda *a, **k: _Proc([refusal, {"type": "result", "is_error": True,
                                                                               "result": "You've hit your session limit"}]))
    llm.complete("x")
    assert llm.calls[-1]["model"] == "haiku", "a refusal names no model that ran"


def _ended(monkeypatch, events, asked="haiku"):
    monkeypatch.setattr(H.subprocess, "Popen", lambda *a, **k: _Proc(events))
    for name in ("adopt", "kill_tree", "release"):
        monkeypatch.setattr(E, name, (lambda p: p) if name == "adopt" else (lambda p: None))
    llm = H.ClaudeCodeProvider(model=asked)
    llm._cmd = llm._cmd or "claude"
    llm.complete("x")
    return llm.calls[-1]


def test_a_session_says_why_it_gave_no_answer(monkeypatch):
    """A context grown past the window and an account limit both come back as zero tokens at zero cost; the page
    named every such session "an account limit, a refusal" — 78 context overflows of one run among them."""
    err = lambda **k: {"type": "result", "is_error": True, "total_cost_usd": 0, **k}
    assert _ended(monkeypatch, [err(terminal_reason="prompt_too_long", result="Prompt is too long")])["ended"] == "prompt_too_long"
    assert _ended(monkeypatch, [err(result="You've hit your session limit")])["ended"] == "limit"
    assert _ended(monkeypatch, [err(result="403 Request not allowed")])["ended"] == "error"


def _message(mid, i, w, r, out):
    """One turn as the CLI streams it: the message starts with what it is read over and a token of output, its
    closing `message_delta` (which names no message) carries the output, and the full message repeats the start."""
    usage = {"input_tokens": i, "cache_creation_input_tokens": w, "cache_read_input_tokens": r, "output_tokens": 1}
    return [{"type": "stream_event", "event": {"type": "message_start", "message": {"id": mid, "usage": usage}}},
            {"type": "stream_event", "event": {"type": "content_block_delta", "delta": {"type": "text_delta", "text": "."}}},
            {"type": "stream_event", "event": {"type": "message_delta", "usage": {"output_tokens": out}}},
            {"type": "assistant", "message": {"id": mid, "content": [{"type": "text", "text": "."}], "usage": usage}}]


def test_a_cut_session_keeps_the_tokens_its_turns_spent(monkeypatch):
    """Cut before its result, a session was recorded with its last tick's output alone; its turns, once per message,
    are what it spent — the output as each turn's closing `message_delta` says it."""
    call = _ended(monkeypatch, _message("a", 5, 1000, 2000, 40) + _message("b", 7, 300, 3000, 60))
    assert call["ended"] == "cut"
    assert (call["input_tokens"], call["output_tokens"]) == (12, 100), "each message once, its output from its delta"
    assert (call["cache_read_input_tokens"], call["cache_creation_input_tokens"]) == (5000, 1300)


def test_a_project_lists_only_the_models_that_did_work(tmp_path):
    e = make_engine(storage=SqliteStorage(str(tmp_path / "p.db")))
    e._storage.log_usage({"ts": "2026-10-25 01:00:00", "stage": "executor", "model": "claude-haiku-4-5-20251001",
                          "output_tokens": 50, "cost_usd": 0.1})
    e._storage.log_usage({"ts": "2026-10-25 01:01:00", "stage": "executor", "model": "haiku", "ended": "limit"})
    assert peek_project(str(tmp_path / "p.db"))["models"] == ["claude-haiku-4-5-20251001"], "a refusal did no work"


def test_a_call_that_continued_a_conversation_says_so(monkeypatch):
    """A round cut at its turn cap is continued (`--resume`) by the next: that call is no context of its own, and
    real contexts are counted as the calls that did not continue one."""
    monkeypatch.setattr(H.subprocess, "Popen", lambda *a, **k: _Proc([_RESULT]))
    for name in ("adopt", "kill_tree", "release"):
        monkeypatch.setattr(E, name, (lambda p: p) if name == "adopt" else (lambda p: None))
    monkeypatch.setattr(H.ClaudeCodeProvider, "forget", lambda self, sid: None)
    llm = H.ClaudeCodeProvider(model="sonnet")
    llm._cmd = llm._cmd or "claude"
    monkeypatch.setattr(H.ClaudeCodeProvider, "_transcripts", lambda self, sid: ["a transcript"])
    llm._call("s", "u", session="sid")
    assert llm.calls[-1]["resumed"] is True
    monkeypatch.setattr(H.ClaudeCodeProvider, "_transcripts", lambda self, sid: [])
    llm._call("s", "u", session="sid")
    llm._call("s", "u")
    assert [c["resumed"] for c in llm.calls[-2:]] == [False, False]
