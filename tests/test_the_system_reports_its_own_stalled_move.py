"""A move the system owes is made in time, or the system says it is stuck. Inv-8 promises only that a move exists; a
dispute the issuer failed to rule froze a row 2 h 26 m (series 2 REF 2), disputes over findings shown without their
inputs looped 5 h (series 3) — both seen by a human, hours late. The sweep that owes the move now says so itself: one
TECH REPORT per node version and question, nothing else changed."""
import threading

import gfso.issuer as I
from gfso.core.types import TaskId
from tests.test_the_mode_decides_who_holds_what import _auto_goal


def _sweeper(e, agents, monkeypatch, status):
    q = {"now": [(TaskId("root"), "dispute")]}
    monkeypatch.setattr(I, "open_questions", lambda en: q["now"])
    monkeypatch.setattr(I, "system_mover", lambda *a, **k: "exec-1")
    monkeypatch.setattr(I, "settle", lambda *a, **k: dict(status))
    ledger, owed, cap = {}, {}, threading.Semaphore(1)

    def sweep():
        before = set(threading.enumerate())
        I.answer_open_questions(e, agents, lambda k: True, lambda *a, **k: None, cap, None, ledger, owed)
        for th in set(threading.enumerate()) - before:
            th.join(5)
        ledger.update({g: (w, 0.0, n) for g, (w, _, n) in ledger.items()})   # every sweep runs past the wait
    return sweep, q, owed


def _stuck(e):
    return [r for r in e.tech_reports() if r["actor"] == "liveness"]


def test_answers_that_leave_the_question_standing_are_reported_once(tmp_path, monkeypatch):
    e, agents = _auto_goal(tmp_path)
    sweep, _, _ = _sweeper(e, agents, monkeypatch, {"status": "noop"})
    for _ in range(I.STUCK_ANSWERS):
        sweep()
    assert not _stuck(e), "reported before the count was reached"
    for _ in range(3):
        sweep()
    reports = _stuck(e)
    assert len(reports) == 1 and "dispute" in reports[0]["text"] and reports[0]["node"] == "root"


def test_a_question_owed_past_its_bound_is_reported(tmp_path, monkeypatch):
    e, agents = _auto_goal(tmp_path)
    sweep, _, owed = _sweeper(e, agents, monkeypatch, {"status": "unavailable", "why": "the place changed"})
    sweep()
    assert not _stuck(e)
    owed.update({k: (since - I.STUCK_S - 1, done) for k, (since, done) in owed.items()})
    sweep()
    sweep()
    assert len(_stuck(e)) == 1 and "unanswered" in _stuck(e)[0]["text"]


def test_a_question_that_closes_starts_its_clock_over(tmp_path, monkeypatch):
    e, agents = _auto_goal(tmp_path)
    sweep, q, owed = _sweeper(e, agents, monkeypatch, {"status": "unavailable", "why": "x"})
    sweep()
    owed.update({k: (since - I.STUCK_S - 1, done) for k, (since, done) in owed.items()})
    q["now"] = []                      # answered: the question left before the next sweep
    sweep()
    assert owed == {}
    q["now"] = [(TaskId("root"), "dispute")]
    sweep()
    assert not _stuck(e), "a question asked anew inherited the old one's time"


def test_control_without_the_monitor_nothing_is_said(tmp_path, monkeypatch):
    e, agents = _auto_goal(tmp_path)
    monkeypatch.setattr(I, "open_questions", lambda en: [(TaskId("root"), "dispute")])
    monkeypatch.setattr(I, "system_mover", lambda *a, **k: "exec-1")
    monkeypatch.setattr(I, "settle", lambda *a, **k: {"status": "noop"})
    ledger, cap = {}, threading.Semaphore(1)
    for _ in range(I.STUCK_ANSWERS + 3):
        before = set(threading.enumerate())
        I.answer_open_questions(e, agents, lambda k: True, lambda *a, **k: None, cap, None, ledger)
        for th in set(threading.enumerate()) - before:
            th.join(5)
        ledger.update({g: (w, 0.0, n) for g, (w, _, n) in ledger.items()})
    assert not _stuck(e)
