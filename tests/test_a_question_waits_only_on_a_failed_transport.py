"""The machine issuer's waits: a transport's failures back a question off, nothing else does. On an own-plan root an
account's limit refused sixteen reviews, each read as an answer that moved nothing; they spent the free answers and every
real answer after waited 32, 64, 120 min — no part started in 4.6 h (GB_sql_database_tnb3ow508, 2026-10-22)."""
import contextlib
import threading
import time

import pytest

import gfso.issuer as I
from gfso.core.types import TaskId
from tests.test_the_mode_decides_who_holds_what import _auto_goal, _sweeps

LIMIT = "rate_limit: You've hit your org's monthly spend limit · resets 3:50pm (UTC)"


def _waits(e, agents, settles, monkeypatch, settle=None) -> list:
    """Sweep once per scripted settle, the clock moved past each wait; the wait each one left, in seconds."""
    script, out = iter(settles), []
    monkeypatch.setattr(I, "settle", settle or (lambda *a, **k: next(script)))
    ledger, cap = {}, threading.Semaphore(1)
    for _ in settles:
        before = set(threading.enumerate())
        I.answer_open_questions(e, agents, lambda k: True, lambda *a, **k: None, cap, None, ledger)
        for th in set(threading.enumerate()) - before:
            if th.ident is not None:   # …one another thread is only starting is listed too, and cannot be joined
                th.join(5)
        out.append(round(max(nb for _, nb, _ in ledger.values()) - time.monotonic()))
        ledger.update({g: (w, 0.0, n) for g, (w, _, n) in ledger.items()})
    return out


def test_a_review_every_call_of_which_the_limit_refused_answered_nothing(tmp_path):
    e, _ = _auto_goal(tmp_path)
    verbs = I.Verbs(llm=None, busy=None, refine=None,
                    review=lambda en, tid: {"stats": [{"error": LIMIT, "duration_ms": 900}]})
    with pytest.raises(I.Unavailable) as got:
        I._review(e, TaskId("root"), verbs)
    assert got.value.limit


def test_an_issuer_turn_the_limit_refused_answered_nothing(tmp_path):
    e, _ = _auto_goal(tmp_path)

    class _Refused:
        stage_hint, calls, last_tool_calls = "", [], {}

        def complete(self, packet, context=None):
            self.calls.append({"error": LIMIT, "duration_ms": 900})
            return "You've hit your org's monthly spend limit"

        def tag_last(self, stage):
            pass
    verbs = I.Verbs(llm=None, busy=lambda *a: contextlib.nullcontext(), review=None, refine=None)
    with pytest.raises(I.Unavailable) as got:
        I._ask(e, TaskId("root"), "escalation", "exec-1", I.MOVE_SCHEMA, "", verbs, _Refused())
    assert got.value.limit


def test_reviews_spend_no_free_answers_and_reset_none(tmp_path, monkeypatch):
    e, agents = _auto_goal(tmp_path)
    idle = {"status": "unproductive", "kind": "review"}
    assert _waits(e, agents, [idle] * (I.FREE_ANSWERS + 6), monkeypatch) == [I.PACE_S] * (I.FREE_ANSWERS + 6)
    fix, moved = {"status": "applied", "kind": "fix"}, {"status": "applied", "kind": "review"}
    ledger = _sweeps(e, agents, [fix, moved] * 5, monkeypatch)
    assert max(n for _, _, n in ledger.values()) == 5, "a review reset the count of fixes: a plan the review rewords "                                                        "after every fix would be asked at the model's pace all version"


def test_the_limit_is_probed_not_doubled_past_it(tmp_path, monkeypatch):
    e, agents = _auto_goal(tmp_path)
    waits = _waits(e, agents, [{"status": "unavailable", "limit": True}] * 8, monkeypatch)
    assert max(waits) <= I.LIMIT_RETRY_S
    assert max(_waits(e, agents, [{"status": "unavailable"}] * 8, monkeypatch)) > I.LIMIT_RETRY_S


def test_an_answer_ends_a_run_of_failed_transports(tmp_path, monkeypatch):
    e, agents = _auto_goal(tmp_path)
    fix = {"status": "applied", "kind": "fix"}
    ledger = _sweeps(e, agents, [{"status": "unavailable"}] * 2 + [fix, {"status": "unavailable"}], monkeypatch)
    assert max(w for w, _, _ in ledger.values()) == 1, "a limit window's failures outlived the answers after it"


def test_a_review_in_flight_is_waited_for_not_backed_off(tmp_path, monkeypatch):
    e, agents = _auto_goal(tmp_path)
    verbs = I.Verbs(llm=None, busy=None, review=lambda en, tid: {"inflight": True}, refine=None)
    assert I._review(e, TaskId("root"), verbs)["status"] == "inflight"
    ledger = _sweeps(e, agents, [{"status": "unavailable"}] + [{"status": "inflight"}] * 5, monkeypatch)
    assert max(w for w, _, _ in ledger.values()) == 1, "a review in flight was counted as a failed transport"


def test_a_context_window_is_no_account_limit():
    assert not I.unanswered([{"error": "invalid_request: input length and `max_tokens` exceed context limit"}]).limit
    assert I.unanswered([{"error": LIMIT}]).limit



def test_the_review_of_a_plan_an_answer_changed_goes_at_once_and_the_rate_is_laid_after_it(tmp_path, monkeypatch):
    """The rate paces the issuer's answers, not the reading of the split an answer just changed: past FREE_ANSWERS an
    own-plan root's admitting review waited 32 min behind its issuer's count (GB_c_compiler_tnl51c552, 2026-10-28).
    Moved, not dropped: a review rewording its findings after every fix must not let fix and review alternate at the
    model's pace (critic over the first fix). As the engine does it: a fix stales the review, a review makes it current."""
    e, agents = _auto_goal(tmp_path)
    fix, read = {"status": "applied", "kind": "fix"}, {"status": "applied", "kind": "review"}
    due = {"now": False}
    script = iter([fix, read] * (I.FREE_ANSWERS + 4))

    def settle(*a, **k):
        out = next(script)
        due["now"] = out is fix
        return out
    monkeypatch.setattr(I, "review_due", lambda en, tid: due["now"])
    waits = _waits(e, agents, [None] * (2 * (I.FREE_ANSWERS + 4)), monkeypatch, settle=settle)
    assert max(waits[0::2]) <= 0, "a review owed after a fix waited behind the answers' count"
    assert waits[-1] > 0, "fix and review alternated at the model's pace past the free count"
