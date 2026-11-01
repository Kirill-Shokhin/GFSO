"""A work session's context handed over from inside its one CLI process: the handover hook reads the context after every
tool call, asks once for a checked point past the budget's line and stops the session at its ceiling, the note then asked
for by its conversation (the author, 2026-10-27: «хук нормальный нельзя сделать там? или по колву токенов смотреть»).
The reading is the rounds' (`test_a_session_hands_over_at_its_context_budget.py`), made after each tool call."""
from __future__ import annotations

import json
import subprocess
import sys

import pytest

from gfso.adapters import execution as E
from gfso.adapters.llm import budget as B
from gfso.adapters.llm import handover_hook as K
from gfso.adapters.llm import headless as H
from gfso.adapters.llm.base import RecordingProvider
from tests.support import hold_a_credential

ARMED = {"budget": 50_000, "ceiling": 180_000, "reopen": False, "resumed": False, "boundary": "point"}


def _readings(state: dict, *contexts: int) -> list[dict]:
    said = []
    for ctx in contexts:
        say, state = K.decide(state, ctx)
        said.append(say)
    return said


def test_past_the_line_the_hook_asks_once_and_at_the_ceiling_it_stops():
    said = _readings(dict(ARMED), 10_000, 40_000, 55_000, 70_000, 185_000)
    assert said[:2] == [{}, {}] and said[2]["hookSpecificOutput"]["additionalContext"] == "point"
    assert said[3] == {} and said[4]["continue"] is False


def test_the_line_is_never_under_twice_the_opening_and_a_continued_conversation_opened_earlier():
    assert _readings(dict(ARMED), 40_000, 60_000, 79_000)[1:] == [{}, {}]          # opened at 40k: the line is 80k
    resumed = _readings({**ARMED, "resumed": True}, 40_000, 60_000)
    assert resumed[1]["hookSpecificOutput"]["additionalContext"] == "point"         # the budget's own line


def test_a_reopen_at_its_ceiling_on_its_first_reading_works_on():
    assert _readings({**ARMED, "reopen": True}, 185_000, 190_000) == [{}, {}]
    assert _readings(dict(ARMED), 185_000)[0]["continue"] is False                   # a first session does close


def test_a_stopped_session_is_not_stopped_again_in_its_close():
    """The close asks for the note by the stopped conversation; stopped again on its spare turn it left no note."""
    said = _readings(dict(ARMED), 10_000, 185_000, 186_000, 187_000)
    assert said[1]["continue"] is False and said[2:] == [{}, {}]


def test_the_hook_reads_the_tool_result_it_was_handed():
    """The turn the transcript last reports was read before the tool's result, so a large read seen one result late
    overshot the ceiling's margin (critic over the hook path)."""
    assert K.result("x" * 100_000) == 25_000 and K.result({"stdout": "ab"}) > 0 and K.result(None) >= 0


def test_with_no_budget_only_the_ceiling_speaks():
    assert _readings({**ARMED, "budget": None}, 60_000, 120_000, 181_000)[:2] == [{}, {}]


def test_the_hook_as_the_cli_runs_it(tmp_path):
    """The file the CLI runs, run as it does: its state beside it, the transcript's last usage read, its answer printed."""
    hook = tmp_path / "handover_hook.py"
    hook.write_bytes(H._HOOK.read_bytes())
    (tmp_path / "sid.hook").write_text(json.dumps({**ARMED, "ceiling": 30_000}), encoding="utf-8")
    t = tmp_path / "t.jsonl"
    t.write_text("\n".join(json.dumps({"message": {"usage": u}}) for u in (
        {"input_tokens": 5, "cache_read_input_tokens": 1_000},
        {"input_tokens": 2, "cache_creation_input_tokens": 20_000, "cache_read_input_tokens": 15_000})), encoding="utf-8")
    run = lambda: subprocess.run([sys.executable, str(hook)], input=json.dumps(
        {"session_id": "sid", "transcript_path": str(t)}), capture_output=True, text=True, timeout=60)
    assert json.loads(run().stdout)["continue"] is False                          # 35 002 ≥ 30 000
    assert json.loads((tmp_path / "sid.hook").read_text())["stopped"] is True
    (tmp_path / "sid.hook").unlink()
    assert run().stdout == ""                                                     # a session armed for nothing


def test_runs_for_parallel_tool_calls_leave_the_state_whole(tmp_path):
    """Three runs at once on one session's state, one of them crossing the line: the state stays readable and read —
    torn, it read as "no handover armed" and the session ran on unasked (GB_sql_database_tnl5do036, root.select)."""
    hook = tmp_path / "handover_hook.py"
    hook.write_bytes(H._HOOK.read_bytes())
    t = tmp_path / "t.jsonl"
    t.write_text(json.dumps({"message": {"usage": {"input_tokens": 10_000}}}), encoding="utf-8")
    for _ in range(60):
        (tmp_path / "sid.hook").write_text(json.dumps({**ARMED, "budget": 25_000, "ceiling": 180_000}), encoding="utf-8")
        runs = [subprocess.Popen([sys.executable, "-I", str(hook)], stdin=subprocess.PIPE, stdout=subprocess.DEVNULL,
                                 text=True) for _ in range(3)]
        for k, p in enumerate(runs):                  # every run fed before any is waited for: they run at once
            p.stdin.write(json.dumps({"session_id": "sid", "transcript_path": str(t), "tool_response": "y" * 50_000 * k}))
            p.stdin.close()
        for p in runs:
            p.wait(timeout=60)
        assert json.loads((tmp_path / "sid.hook").read_text(encoding="utf-8"))["read"] is True
        assert not list(tmp_path.glob("sid.hook.*")), "a lock or a temp file was left behind"


class Hooked(RecordingProvider):
    """A provider whose one round per session ends as `ends` says — the hook asked (and the session wrote its note or
    delivered), stopped it at the ceiling, or never spoke."""
    runs_agents = budgeted = handover_hook = True

    def __init__(self, *ends, budget: int | None = 50_000):
        super().__init__("m")
        self.ends, self.context_budget = list(ends), budget
        self.prompts, self.systems, self.armed, self.closed, self.forgot = [], [], [], [], []

    def arm(self, sid, state, cwd=None):
        self.armed.append(state)

    def agent_round(self, system, user, allowed_tools, cwd, timeout, max_turns, session):
        self.prompts.append(user)
        self.systems.append(system)
        end = self.ends.pop(0)
        self.calls.append({"turns": 5, "hook": {"asked": end in ("note", "report"), "stopped": end == "stopped"}})
        return {"note": f"{B.NOTE_MARK}\nparser done", "report": "REPORT", "stopped": ""}.get(end, end)

    def close_session(self, system, prompt, allowed_tools, cwd, timeout, session):
        self.closed.append(prompt)
        self.calls.append({"turns": 1, "ended": "answered"})
        return "NOTE at the ceiling"

    def forget(self, session):
        self.forgot.append(session)


def test_a_session_asked_for_its_point_hands_its_note_to_a_fresh_one():
    w = Hooked("note", "REPORT")
    assert w.run_agent("s", "packet", ("Read",), cwd=".", session="sid") == "REPORT"
    assert w.prompts[0] == "packet" and B.HANDOVER in w.prompts[1] and "parser done" in w.prompts[1]
    assert [a["reopen"] for a in w.armed] == [False, True] and not w.closed
    assert w.armed[0]["boundary"].startswith(B.SAYS + " " + B.BOUNDARY) and B.NOTICE in w.systems[0]


def test_a_session_the_hook_stopped_writes_its_note_by_its_conversation():
    w = Hooked("stopped", "REPORT")
    assert w.run_agent("s", "packet", ("Read",), cwd=".", session="sid") == "REPORT"
    assert w.closed and w.closed[0].startswith(B.CLOSE) and "NOTE at the ceiling" in w.prompts[1]


def test_a_report_at_the_point_and_a_session_the_hook_never_spoke_to_are_the_answer():
    assert Hooked("report").run_agent("s", "packet", ("Read",), cwd=".", session="sid") == "REPORT"
    quiet = Hooked("REPORT", budget=None)
    assert quiet.run_agent("s", "packet", ("Read",), cwd=".", session="sid") == "REPORT"
    assert B.NOTICE not in quiet.systems[0] and quiet.armed[0]["budget"] is None


def test_the_second_session_is_asked_to_update_the_note_it_started_from():
    w = Hooked("note", "note", "REPORT")
    w.run_agent("s", "packet", ("Read",), cwd=".", session="sid")
    assert B.PREVIOUS not in w.armed[0]["boundary"] and B.PREVIOUS in w.armed[1]["boundary"]


@pytest.fixture
def cli(tmp_path, monkeypatch):
    """The CLI provider over a scripted stream, its argv kept."""
    monkeypatch.setenv("CLAUDE_CONFIG_DIR", str(tmp_path / "cfg"))
    hold_a_credential(monkeypatch, tmp_path)
    seen = []

    class _P:
        stdin = None

        def wait(self, timeout=None):
            return 0

    def popen(args, **kw):
        seen.append(args)
        p = _P()
        p.stdin = type("S", (), {"write": lambda *a: None, "close": lambda *a: None})()
        return p

    monkeypatch.setattr(H.subprocess, "Popen", popen)
    monkeypatch.setattr(H.ClaudeCodeProvider, "_read_stream", lambda self, proc, t0, cap: (
        {"result": "REPORT", "num_turns": 1, "modelUsage": {"m": {"costUSD": 1, "contextWindow": 200_000}}}, [], 0))
    for f in ("adopt",):
        monkeypatch.setattr(E, f, lambda p: p)
    monkeypatch.setattr(E, "kill_tree", lambda p: None)
    monkeypatch.setattr(E, "release", lambda p: None)
    llm = H.ClaudeCodeProvider()
    llm._cmd = "claude"
    return llm, seen, tmp_path


def test_an_armed_session_loads_no_setting_source_and_carries_the_hook_alone(cli):
    """`--safe-mode` drops the hooks `--settings` brings (probed: the hook never ran) and still loads the cwd's
    `.claude/settings.json`, which a delivered tree carries (critic, live): every call loads no setting source."""
    llm, seen, tmp = cli
    llm.agent_round("s", "packet", ("Read",), cwd=str(tmp), session="plain")
    llm.arm("sid", dict(ARMED))
    assert (tmp / "cfg" / "gfso-sessions" / "handover_hook.py").read_bytes() == H._HOOK.read_bytes()
    llm.agent_round("s", "packet", ("Read",), cwd=str(tmp), session="sid")
    plain, armed = seen
    assert "--safe-mode" not in plain and plain[plain.index("--setting-sources") + 1] == ""
    assert "disableAllHooks" in plain[plain.index("--settings") + 1]
    assert "--safe-mode" not in armed and armed[armed.index("--setting-sources") + 1] == ""
    hooks = json.loads(armed[armed.index("--settings") + 1])["hooks"]["PostToolUse"][0]["hooks"]
    assert hooks[0]["command"].endswith('gfso-sessions/handover_hook.py"')
    assert llm.window() == 200_000


def test_a_conversation_the_hook_stopped_is_kept_for_its_note(cli):
    llm, seen, tmp = cli
    llm.arm("sid", dict(ARMED))
    (tmp / "cfg" / "gfso-sessions" / "sid.hook").write_text(json.dumps({**ARMED, "stopped": True}), encoding="utf-8")
    llm.agent_round("s", "packet", ("Read",), cwd=str(tmp), session="sid")
    assert llm.calls[-1]["hook"]["stopped"] and "sid" in llm.hooks.armed
    llm.arm("other", dict(ARMED))
    llm.agent_round("s", "packet", ("Read",), cwd=str(tmp), session="other")
    assert "other" not in llm.hooks.armed and not (tmp / "cfg" / "gfso-sessions" / "other.hook").exists()


def test_a_session_whose_hook_never_ran_sends_the_next_ones_back_to_rounds():
    """A session that called tools while its hook read nothing had no ceiling (an image without python3, a CLI that runs
    no hooks): the provider's next sessions read their context between rounds."""
    w = Hooked("REPORT")
    w.last_tool_calls = {"Bash": 3}
    w.run_agent("s", "packet", ("Read",), cwd=".", session="sid")
    assert w.handover_hook is False


def test_a_note_written_on_the_roles_last_turn_is_carried_into_the_fresh_session():
    """At the role's cap the reopened session still runs its first round: the note is the system's, and dropping it
    there lost the note with a conversation already forgotten (critic over the hook path)."""
    w = Hooked("note", "REPORT")
    assert w.run_agent("s", "packet", ("Read",), cwd=".", session="sid", max_turns=5) == "REPORT"
    assert B.HANDOVER in w.prompts[1] and "parser done" in w.prompts[1]


def test_a_cold_run_replacing_a_lost_conversation_is_armed_again(cli):
    """Forgotten with the conversation the CLI could not resume, the hook left the cold run without a ceiling and sent
    the provider back to rounds for good (critic over the hook path): armed again as armed, its readings gone."""
    llm, seen, tmp = cli
    llm.arm("sid", dict(ARMED))
    (tmp / "cfg" / "gfso-sessions" / "sid.hook").write_text(json.dumps({**ARMED, "read": True, "peak": 90_000}))
    llm.hooks.across("sid", llm.forget)
    again = llm.hooks.state("sid")
    assert "sid" in llm.hooks.armed and again["budget"] == ARMED["budget"] and "peak" not in again
