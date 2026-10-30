"""While `auto_decompose` writes a subtree, the machine issuer answers no question in it. The authoring now converges
the plan on the gate itself; the issuer answered the plan question on the same root meanwhile — two writers on one
split, and the authoring died (gb-coreutils-tnq7tv040, 2026-10-30).

CONTROL: drop `being_rewritten` from the sweep and the question is answered under the authoring."""
import threading

import gfso.issuer as I
from gfso.core.types import TaskId
from gfso.inflight import _inflight
from tests.test_the_mode_decides_who_holds_what import _auto_goal


def _sweep(e, agents, monkeypatch):
    asked = []
    monkeypatch.setattr(I, "open_questions", lambda en: [(TaskId("root"), "plan")])
    monkeypatch.setattr(I, "system_mover", lambda *a, **k: "exec-1")
    monkeypatch.setattr(I, "settle", lambda *a, **k: asked.append(1) or {"status": "noop"})
    before = set(threading.enumerate())
    I.answer_open_questions(e, agents, lambda k: True, lambda *a, **k: None, threading.Semaphore(1), None, {})
    for th in set(threading.enumerate()) - before:
        th.join(5)
    return asked


def test_no_plan_question_is_answered_while_the_authoring_writes_the_root(tmp_path, monkeypatch):
    e, agents = _auto_goal(tmp_path)
    with _inflight("auto_decompose", e, "root"):
        assert _sweep(e, agents, monkeypatch) == [], "the issuer answered under the authoring"
    assert _sweep(e, agents, monkeypatch) == [1], "once the authoring ended the question is answered"
