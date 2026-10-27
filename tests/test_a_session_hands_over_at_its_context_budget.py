"""A work session's context is handed over by the system before it outgrows what the resource should carry — at the
ceiling always (the window less a margin), at the role's budget where one is set, there at a point the session has
checked — and a fresh session continues on the packet, the session's own note and the place's machine state (the author,
2026-10-27: «ставим 300к … точку. При достижении агент … должен получить инструкцию похожую на наш close-open»). A
MECHANISM under test here; what a budget saves is measured by paired rows, not by this file."""
from __future__ import annotations

import io
import time

import pytest

from gfso import sessions as S
from gfso.adapters import execution as E
from gfso.adapters.llm import budget as B
from gfso.adapters.llm import headless as H
from gfso.adapters.llm.base import RecordingProvider
from tests.support import make_engine


class Worker(RecordingProvider):
    """A provider whose context grows `per_turn` tokens a turn and answers after `work` turns of one conversation;
    asked for a checked point it gives one (`checks`) or delivers (`delivers_at_boundary`)."""
    runs_agents = budgeted = True

    def __init__(self, work: int, per_turn: int = 10_000, budget: int | None = None, step: int = 3, start: int = 0,
                 reports_peak: bool = True, close_ends: str = "answered", window: int | None = None,
                 resumed: bool = False, delivers_at_boundary: bool = False, accelerates: bool = False):
        super().__init__("m")
        self.work, self.per_turn, self.context_budget, self.budget_step = work, per_turn, budget, step
        self.start, self.reports_peak, self.close_ends, self.window = start, reports_peak, close_ends, window
        self.resumed, self.delivers_at_boundary, self.accelerates = resumed, delivers_at_boundary, accelerates
        self.done, self.held, self.prompts, self.caps, self.closed, self.forgot = 0, {}, [], [], [], []

    def agent_round(self, system, user, allowed_tools, cwd, timeout, max_turns, session):
        self.prompts.append(user)
        self.caps.append(max_turns)
        resumed = session in self.held or (self.resumed and not self.closed)
        ctx = self.held.get(session, self.start)
        if user.startswith(B.BOUNDARY):
            self.held[session] = ctx + self.per_turn
            self.calls.append({"turns": 1, "peak_context": self.held[session], "context_window": self.window,
                               "resumed": True})
            return "REPORT" if self.delivers_at_boundary else f"{B.NOTE_MARK}" + chr(10) + f"noted at {self.done}"
        turns = min(max_turns or 10 ** 6, self.work - self.done)
        self.done += turns
        # accelerating: every turn grows the context by 2k and 3% of what it carries — reads get larger as work deepens
        for _ in range(turns if self.accelerates else 0):
            ctx += int(2_000 + 0.03 * ctx)
        self.held[session] = ctx if self.accelerates else ctx + turns * self.per_turn
        cut = self.done < self.work
        self.calls.append({"turns": turns, "peak_context": self.held[session] if self.reports_peak else None,
                           "stop_reason": "max_turns" if cut else None, "context_window": self.window,
                           "resumed": resumed})
        return "" if cut else "REPORT"

    def close_session(self, system, prompt, allowed_tools, cwd, timeout, session):
        self.closed.append((prompt, session))
        self.calls.append({"turns": 1, "ended": self.close_ends})
        return f"NOTE after {self.done} turns" if self.close_ends == "answered" else ""

    def forget(self, session):
        self.forgot.append(session)
        self.held.pop(session, None)


def test_a_one_round_role_runs_as_before():
    w = Worker(work=20, budget=50_000)
    w.budgeted = False                                   # a validator's or a consent's run
    assert w.run_agent("s", "packet", ("Read",), cwd=".") == "REPORT"
    assert w.prompts == ["packet"] and not w.closed


def test_with_no_budget_the_session_hands_over_at_its_ceiling_never_at_the_window():
    w = Worker(work=30, window=200_000, step=4)
    w.machine_state = lambda: "c1 — `make test` → exit 1"
    assert w.run_agent("s", "packet", ("Read",), cwd=".", session="sid") == "REPORT"
    ceiling = B.ceiling(200_000)
    assert ceiling == 180_000 and len(w.closed) == 1 and not any(p.startswith(B.BOUNDARY) for p in w.prompts)
    assert max(c.get("peak_context") or 0 for c in w.calls) < 200_000
    reopen = next(p for p in w.prompts if p.startswith("packet") and p != "packet")
    assert B.HANDOVER in reopen and "NOTE after" in reopen and B.STATE in reopen and "`make test` → exit 1" in reopen
    assert w.calls[[c.get("ended") for c in w.calls].index("answered")]["handover"] == 1


def test_past_its_budget_a_session_is_asked_once_for_a_checked_point_and_closes_there():
    w = Worker(work=12, budget=50_000, step=3)
    assert w.run_agent("s", "packet", ("Read",), cwd=".", session="sid") == "REPORT"
    asks = [i for i, p in enumerate(w.prompts) if p.startswith(B.BOUNDARY)]
    assert asks and all(w.prompts[i + 1].startswith("packet") for i in asks)      # once a session, then the reopen
    assert "noted at" in w.prompts[asks[0] + 1] and not w.closed and "sid" in w.forgot


def test_a_session_that_delivers_at_the_boundary_is_not_closed():
    w = Worker(work=40, budget=50_000, step=3, delivers_at_boundary=True)
    assert w.run_agent("s", "packet", ("Read",), cwd=".", session="sid") == "REPORT" and not w.closed


def test_the_packet_never_counts_down():
    w = Worker(work=12, budget=50_000, step=3)
    w.run_agent("s", "packet", ("Read",), cwd=".", session="sid")
    told = " ".join(p for p in w.prompts if not p.startswith(B.BOUNDARY))
    assert "budget" not in told.lower() and "token" not in told.lower()


def test_a_second_close_updates_the_note_it_started_from():
    w = Worker(work=40, budget=50_000, step=3)
    w.run_agent("s", "packet", ("Read",), cwd=".", session="sid")
    asks = [p for p in w.prompts if p.startswith(B.BOUNDARY)]
    assert len(asks) >= 2 and B.PREVIOUS not in asks[0] and B.PREVIOUS in asks[1] and "noted at" in asks[1]


def test_a_conversation_resumed_past_its_budget_closes_it_does_not_switch_the_budget_off():
    w = Worker(work=40, budget=50_000, step=3, start=70_000, resumed=True)     # (A): an earlier round's conversation
    w.run_agent("s", "continue", ("Read",), cwd=".", session="sid")
    assert w.prompts[1].startswith(B.BOUNDARY) and w.prompts[2].startswith("continue" + B.HANDOVER)


def test_a_session_opened_past_its_budget_works_to_twice_its_opening():
    w = Worker(work=40, budget=50_000, step=3, start=60_000, window=200_000)
    assert w.run_agent("s", "packet", ("Read",), cwd=".", session="sid") == "REPORT"
    first = next(i for i, p in enumerate(w.prompts) if p.startswith(B.BOUNDARY))
    assert w.calls[first - 1]["peak_context"] >= 2 * 70_000                   # opened at 70k: asked at 140k, not at once
    assert max(c.get("peak_context") or 0 for c in w.calls) < 200_000


def test_a_budget_just_over_a_reopens_size_does_not_hand_over_every_two_turns():
    """Budget 60k, a reopen opening near 55k: asked for its point after a turn or two, every session, nothing done
    between (critic over 069e91b) — each session now works at least as much as its opening costs."""
    w = Worker(work=60, budget=60_000, step=8, start=55_000, per_turn=3_000, window=1_000_000)
    w.run_agent("s", "packet", ("Read",), cwd=".", session="sid")
    asks = sum(p.startswith(B.BOUNDARY) for p in w.prompts)
    assert asks <= 3, asks


def test_a_cap_reached_in_the_round_to_its_point_still_hands_the_note_on():
    """The role's cap landing inside the round asked for a checked point left the conversation ending on the request,
    the note to come back later as an unparsed report (critic over 069e91b): the close runs, and the fresh session gets
    its first turn — the note in its conversation, kept for the next round."""
    w = Worker(work=100, budget=40_000, step=4, per_turn=5_000)
    w.delivers_at_boundary = False
    plain = Worker.agent_round.__get__(w)

    def never_reaches(system, user, *rest):            # the round asked for its point is always cut at its cap
        if user.startswith(B.BOUNDARY):
            w.prompts.append(user)
            w.calls.append({"turns": rest[3] or 1, "peak_context": 60_000, "stop_reason": "max_turns", "resumed": True})
            return ""
        return plain(system, user, *rest)
    w.agent_round = never_reaches
    assert w.run_agent("s", "packet", ("Read",), cwd=".", max_turns=12, session="sid") == ""
    assert w.closed and "sid" in w.held and B.HANDOVER in w.prompts[-1], "the kept conversation opens on the note"


def test_a_work_session_goes_through_the_handover_and_no_other_does(tmp_path):
    """The frame's wiring, not the loop's arithmetic: an executor's session is budgeted with the role's budget, the
    place's machine state and the report's reader; a consent is one round (critic over 069e91b)."""
    e = make_engine()
    e.start()
    seen = {}

    class Probe(Worker):
        def run_agent(self, system, user, allowed_tools, cwd=None, timeout=None, max_turns=None, session=None):
            seen.update(budgeted=self.budgeted, budget=self.context_budget, state=self.machine_state,
                        reads=self.reads_as_report)
            return '{"status": "delivered", "summary": "s"}'
    w = Probe(work=1)
    w.budgeted = False
    S._spawn(e, "n", "exec-1", {"context_budget": 70_000}, w, "executor", "executor.md", "packet", S.EXECUTOR_SCHEMA,
             "delegated_execution", str(tmp_path), None, tasks=())
    assert seen["budgeted"] and seen["budget"] == 70_000 and callable(seen["state"]) and isinstance(seen["state"](), str)
    assert seen["reads"]('{"status": "delivered", "summary": "s"}') and not seen["reads"]("1. Reading — none")
    w2 = Probe(work=1)
    w2.budgeted = False
    S._spawn(e, "n", "exec-1", {}, w2, "consent", "consent.md", "packet", S.CONSENT_SCHEMA, "delegated_consent",
             str(tmp_path), work=False)
    assert seen["budgeted"] is False
    e.stop()


def test_no_close_starts_without_the_time_for_a_session_to_continue_it():
    w = Worker(work=40, window=100_000, step=3)                                # (B): the close's own time, read then
    assert w.run_agent("s", "packet", ("Read",), cwd=".", timeout=B.CLOSE_MIN_S - 1, session="sid") == ""
    assert not w.closed


def test_between_readings_a_session_runs_as_far_as_its_growth_allows():
    w = Worker(work=60, per_turn=1_000, window=200_000, step=4)
    w.run_agent("s", "packet", ("Read",), cwd=".", session="sid")
    assert max(c for c in w.caps if c) == 5 * w.budget_step and not w.closed  # a long session, few processes


def test_a_provider_that_does_not_report_its_context_runs_to_its_end():
    w = Worker(work=12, budget=50_000, step=3, reports_peak=False)
    assert w.run_agent("s", "packet", ("Read",), cwd=".", session="sid") == "REPORT" and not w.closed


def test_a_close_refused_by_the_account_keeps_the_conversation_for_the_lift():
    w = Worker(work=30, window=100_000, step=3, close_ends="limit")
    assert w.run_agent("s", "packet", ("Read",), cwd=".", session="sid") == ""
    assert w.closed and "sid" not in w.forgot and "sid" in w.held


def test_the_roles_turn_cap_counts_every_session_and_keeps_the_conversation():
    w = Worker(work=100, budget=40_000, step=4)
    assert w.run_agent("s", "packet", ("Read",), cwd=".", max_turns=10, session="sid") == ""
    assert w.done <= 10 and "sid" in w.held


def test_a_run_naming_no_conversation_leaves_none():
    w = Worker(work=5, budget=40_000, step=2)
    assert w.run_agent("s", "packet", ("Read",), cwd=".") == "REPORT"
    assert w.forgot and all(s.startswith("budget-") for s in w.forgot)


class _Stdin(io.StringIO):
    def __init__(self):
        super().__init__()
        self.said = None                  # what the call wrote, kept when it closes the pipe

    def close(self):
        self.said = self.getvalue()


class _Proc:
    def __init__(self):
        self.stdin = _Stdin()

    def wait(self, timeout=None):
        return 0


@pytest.fixture
def cli(tmp_path, monkeypatch):
    """The CLI provider over a scripted stream: each call ends as `script` says, at the peak it names."""
    monkeypatch.setenv("CLAUDE_CONFIG_DIR", str(tmp_path / "cfg"))
    seen, script = [], []

    def popen(args, **kw):
        seen.append((args, p := _Proc()))
        if "--session-id" in args:
            f = tmp_path / "cfg" / "projects" / "-place" / f"{args[args.index('--session-id') + 1]}.jsonl"
            f.parent.mkdir(parents=True, exist_ok=True)
            f.write_text("{}\n", encoding="utf-8")
        return p

    def read_stream(self, proc, t0, cap):
        ends, peak = script.pop(0)
        self.last_peak_context = peak
        if ends == "cap":
            return {"is_error": True, "subtype": "error_max_turns", "result": "", "num_turns": 9}, [], 0
        if ends == "gone":
            sid = seen[-1][0][seen[-1][0].index("--resume") + 1]
            return {"is_error": True, "subtype": "error_during_execution",
                    "errors": [f"No conversation found with session ID {sid}"]}, [], 0
        return {"result": ends, "num_turns": 1}, [], 0

    monkeypatch.setattr(H.subprocess, "Popen", popen)
    monkeypatch.setattr(H.ClaudeCodeProvider, "_read_stream", read_stream)
    monkeypatch.setattr(E, "adopt", lambda p: p)
    monkeypatch.setattr(E, "kill_tree", lambda p: None)
    monkeypatch.setattr(E, "release", lambda p: None)
    llm = H.ClaudeCodeProvider()
    llm._cmd, llm.budgeted, llm.context_budget = "claude", True, 50_000
    return llm, seen, script, tmp_path


def _said(proc):
    """What the call wrote to the child — written by the provider's feeder thread."""
    for _ in range(200):
        if proc.stdin.said is not None:
            break
        time.sleep(0.01)
    return proc.stdin.said


def test_the_cli_reaches_a_checked_point_closes_by_its_conversation_and_opens_a_fresh_one(cli):
    llm, seen, script, tmp = cli
    script += [("cap", 30_000), ("cap", 60_000), (B.NOTE_MARK + chr(10) + "parser done", 62_000), ("REPORT", 20_000)]
    assert llm.run_agent("sys", "packet", ("Read", "Edit"), cwd=str(tmp), session="sid") == "REPORT"
    (a1, p1), (a2, p2), (a3, p3), (a4, p4) = seen
    assert "--session-id" in a1 and "--max-turns" in a1 and _said(p1) == "packet"
    assert "--resume" in a2 and _said(p2) == B.CONTINUE                       # under budget: the same conversation
    # the point and its note in ONE round of the same conversation, the same tools (the same cached prefix)
    assert "--resume" in a3 and a3[a3.index("--tools") + 1] == a1[a1.index("--tools") + 1] and _said(p3) == B.BOUNDARY
    assert "--session-id" in a4 and _said(p4).startswith("packet") and "parser done" in _said(p4)
    assert [c["stop_reason"] for c in llm.calls[:2]] == ["max_turns", "max_turns"]


def test_a_lost_conversation_reopens_on_the_packet_not_on_continue(cli):
    llm, seen, script, tmp = cli
    script += [("cap", 30_000), ("gone", 0), ("REPORT", 25_000)]
    assert llm.run_agent("sys", "packet", ("Read",), cwd=str(tmp), session="sid") == "REPORT"
    (_a1, _p1), (a2, p2), (a3, p3) = seen
    assert "--resume" in a2 and _said(p2) == B.CONTINUE
    assert "--session-id" in a3 and _said(p3) == "packet"                       # the cold retry carries the task
    assert llm.resume_fallback is None


@pytest.mark.parametrize("note", ["```\nparser done\n```", "Stopping at a checked point.\nparser done",
                                  "1. Reading of the task — none\n2. Done and checked — parser done"])
def test_whatever_is_not_the_roles_report_is_the_note(note):
    """A note in a fence, after a preamble or without its mark was read as the run's answer and lost with the
    conversation (critic over 542a3c0): the frame's own reader of the report tells them apart."""
    w = Worker(work=40, budget=50_000, step=3)
    w.reads_as_report = lambda text: text.startswith("{")
    w.agent_round = _answers_at_boundary(w, note)
    w.run_agent("s", "packet", ("Read",), cwd=".", session="sid")
    reopen = next(p for p in w.prompts if B.HANDOVER in p)
    assert "parser done" in reopen


def test_a_report_given_at_the_boundary_is_the_runs_answer():
    w = Worker(work=40, budget=50_000, step=3)
    w.reads_as_report = lambda text: text.startswith("{")
    w.agent_round = _answers_at_boundary(w, '{"status": "delivered"}')
    assert w.run_agent("s", "packet", ("Read",), cwd=".", session="sid") == '{"status": "delivered"}'


def _answers_at_boundary(w, answer):
    plain = Worker.agent_round.__get__(w)

    def round_(system, user, *rest):
        if user.startswith(B.BOUNDARY):
            w.prompts.append(user)
            w.calls.append({"turns": 1, "peak_context": 60_000, "resumed": True})
            return answer
        return plain(system, user, *rest)
    return round_


def test_a_session_that_grows_past_its_budget_in_its_first_turns_keeps_the_budget():
    """The first round's peak was read after a whole step, so a session that GREW past the budget read as one that
    STARTED past it, and the budget went off for the run (critic over 542a3c0)."""
    w = Worker(work=40, budget=50_000, step=8, start=5_000, per_turn=8_000, window=200_000)
    w.run_agent("s", "packet", ("Read",), cwd=".", session="sid")
    assert any(p.startswith(B.BOUNDARY) for p in w.prompts) and w.caps[0] == 1


def test_rounds_aim_short_of_the_ceiling_so_an_accelerating_session_never_meets_the_window():
    """Aimed at the ceiling itself, a round whose turns grow faster than the last ones ran past the window, where on
    the CLI the conversation is lost with no note (critic over 542a3c0)."""
    w = Worker(work=200, window=200_000, step=8, accelerates=True)
    w.run_agent("s", "packet", ("Read",), cwd=".", session="sid")
    assert w.closed and max(c.get("peak_context") or 0 for c in w.calls) < 200_000


def test_a_provider_that_reports_no_window_still_has_a_ceiling():
    w = Worker(work=40, per_turn=10_000, step=4)                              # no window reported, no budget
    w.run_agent("s", "packet", ("Read",), cwd=".", session="sid")
    assert w.closed and max(c.get("peak_context") or 0 for c in w.calls) < B.DEFAULT_WINDOW


def test_a_ceiling_met_on_the_roles_last_turn_still_hands_the_note_on():
    """The close and the fresh session's first turn are the system's: met on the cap's last turn, the session still
    closes, and the conversation kept for the next round is the fresh one, the note in it."""
    w = Worker(work=100, per_turn=10_000, window=60_000, step=4)                  # ceiling 40k, reached at turn 4
    assert w.run_agent("s", "packet", ("Read",), cwd=".", max_turns=4, session="sid") == ""
    assert w.closed and "sid" in w.held and B.HANDOVER in w.prompts[-1]
