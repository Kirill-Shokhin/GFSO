"""A round of a node's work cut at its turn cap is continued by the next round; every other round starts clean.

Measured on three sql_database rows (haiku 4.5, 2026-10-21): 9 of 56 executor sessions ended at the turn cap mid-work
and the next round started from zero. Continuing EVERY round was measured too (GB_sql_database_tn9nii608): a disputing
executor repeated its challenge out of the conversation every 24 s, 40 calls, each one's input 16k tokens longer — the
clean context per round each agent works in is what makes the automatic mode cheap (the author, 2026-09-27)."""
from __future__ import annotations

import contextlib
import io

import pytest

from gfso import sessions as S
from gfso.adapters import execution as E
from gfso.adapters.llm import headless as H
from gfso.workspaces import session_key


class _Proc:
    def __init__(self):
        self.stdin = io.StringIO()

    def wait(self, timeout=None):
        return 0


@pytest.fixture
def cli(tmp_path, monkeypatch):
    """A stand-in for the CLI: `--session-id` writes the transcript where the real one does, `--resume` reads it;
    `ends` is how the next call ends: "answer", "cap" (cut at the turn cap) or "gone" (a resume the CLI cannot take)."""
    monkeypatch.setenv("CLAUDE_CONFIG_DIR", str(tmp_path / "cfg"))
    seen, state = [], {"ends": "answer"}

    def popen(args, **kw):
        seen.append(args)
        if "--session-id" in args:
            f = tmp_path / "cfg" / "projects" / "-node-place" / f"{args[args.index('--session-id') + 1]}.jsonl"
            f.parent.mkdir(parents=True, exist_ok=True)
            f.write_text("{}\n", encoding="utf-8")
        return _Proc()

    def read_stream(self, proc, t0, cap):
        args, ends = seen[-1], state["ends"]
        if ends == "cap":
            return {"is_error": True, "subtype": "error_max_turns", "terminal_reason": "max_turns", "result": ""}, [], 0
        if ends == "gone" and "--resume" in args:
            state["ends"] = "answer"
            return {"is_error": True, "subtype": "error_during_execution",
                    "errors": [f"No conversation found with session ID {args[args.index('--resume') + 1]}"]}, [], 0
        return {"result": "REPORT"}, [], 0

    monkeypatch.setattr(H.subprocess, "Popen", popen)
    monkeypatch.setattr(H.ClaudeCodeProvider, "_read_stream", read_stream)
    monkeypatch.setattr(E, "adopt", lambda p: p)
    monkeypatch.setattr(E, "kill_tree", lambda p: None)
    monkeypatch.setattr(E, "release", lambda p: None)
    llm = H.ClaudeCodeProvider()
    llm._cmd = "claude"
    return llm, seen, state, tmp_path


def _run(llm, place, session):
    return llm.run_agent("sys", "packet", ("Read",), cwd=str(place), session=session)


_SID = session_key("proj", "root.dml", "", "exec-2", "executor")


def test_a_round_that_answered_leaves_nothing_to_continue(cli):
    llm, seen, _s, tmp = cli
    assert _run(llm, tmp, _SID) == "REPORT" and _run(llm, tmp, _SID) == "REPORT"
    assert "--session-id" in seen[0] and "--session-id" in seen[1] and not llm._transcripts(_SID)


def test_a_round_cut_at_its_turn_cap_is_continued(cli):
    llm, seen, state, tmp = cli
    state["ends"] = "cap"
    assert _run(llm, tmp, _SID) == ""
    assert llm._transcripts(_SID)
    state["ends"] = "answer"
    assert _run(llm, tmp, _SID) == "REPORT"
    assert seen[1][seen[1].index("--resume") + 1] == _SID and not llm._transcripts(_SID)


def test_a_continued_round_cut_again_stays_continued(cli):
    llm, seen, state, tmp = cli
    state["ends"] = "cap"
    _run(llm, tmp, _SID)
    _run(llm, tmp, _SID)
    assert len(seen) == 2 and "--resume" in seen[1] and llm._transcripts(_SID)


def test_a_conversation_the_cli_cannot_take_up_runs_the_round_cold(cli):
    llm, seen, state, tmp = cli
    state["ends"] = "cap"
    _run(llm, tmp, _SID)
    state["ends"] = "gone"
    assert _run(llm, tmp, _SID) == "REPORT"
    assert "--resume" in seen[1] and "--session-id" in seen[2]


def test_a_call_naming_no_conversation_saves_none(cli):
    llm, seen, _s, tmp = cli
    _run(llm, tmp, None)
    assert "--no-session-persistence" in seen[0] and "--resume" not in seen[0] and "--session-id" not in seen[0]


def test_another_executor_or_role_is_another_conversation():
    k = session_key
    assert k("proj", "root.dml", "", "exec-2", "executor") != k("proj", "root.dml", "", "exec-3", "executor")
    assert k("proj", "root.dml", "", "exec-2", "executor") != k("proj", "root.dml", "", "exec-2", "scope-executor")


def test_the_executor_round_names_its_nodes_conversation(monkeypatch):
    """The wiring: a work round of `_spawn` passes the node's key; a read-only one passes none."""
    got = []
    monkeypatch.setattr(S, "_run_session", lambda llm, system, user, cfg, cap, cwd, session=None: got.append(session) or "")

    class _E:
        project_name = "proj"
        def record_llm_usage(self, *a): pass
        def emit_info(self, *a): pass
        def audit_log(self, task_id): return []

    class _L:
        calls = []
        def run_agent(self, *a, **k): got.append(k.get("session")); return ""

    monkeypatch.setattr(S, "_inflight", lambda *a: contextlib.nullcontext())
    monkeypatch.setattr(S, "session_calls", lambda *a: {})
    monkeypatch.setattr(S, "emit_cb", lambda *a: (lambda m: None))
    S._spawn(_E(), "root.dml", "exec-2", {}, _L(), "executor", "executor.md", "p", S.EXECUTOR_SCHEMA, "v", ".")
    S._spawn(_E(), "root.dml", "exec-2", {}, _L(), "consent", "consent.md", "p", S.CONSENT_SCHEMA, "v", ".", work=False)
    assert got == [_SID, None]
