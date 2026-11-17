"""`refine` answers a plan question once per node, and never at an AUTO root: each is a multi-minute round, and a
machine issuer answered the same question with one after another. Said only in issuer.md (instruction audit
2026-11-17, row 9); now the moves a question admits (`moves_for`) hold it, counted on the node's log."""
from __future__ import annotations

import contextlib

from gfso import issuer as I
from gfso.config import PIPELINE_PAGE
from gfso.core.types import Mode, TaskId
from tests.support import criterion
from tests.test_the_mode_decides_who_holds_what import _FakeLLM, _admit, _engine, _goal, _kid

VERBS = I.Verbs(llm=None, busy=lambda *a: contextlib.nullcontext(), review=None, refine=lambda engine, node: {})


def test_a_plan_question_takes_one_refine_per_node_and_none_at_an_auto_root(monkeypatch):
    """CONTROL: the `refine` rule removed from `moves_for` — the AUTO root and the second turn keep `refine`, red."""
    e = _engine(Mode.AUTO)
    root, kid = _goal(e)
    _admit(e, "kid", _kid("gk", ["k"], criterion("x", "X holds")))
    monkeypatch.setattr(I, "_still_open", lambda *a: True)
    assert "refine" not in I.moves_for(e, root, "plan")
    assert "refine" in I.moves_for(e, kid, "plan")
    turn = lambda: I.issuer_turn(e, TaskId("kid"), "plan", "exec-1", verbs=VERBS,
                                 _llm=_FakeLLM({"move": "refine", "justification": "re-cut"}))
    assert turn()["status"] == "applied"
    assert "refine" not in I.moves_for(e, e.graph.get_task("kid"), "plan")
    for i in range(PIPELINE_PAGE + 1):      # …nor out of view behind a page of other lines (CONTROL: read unscoped, red)
        e.emit_info("delegate", f"root: line {i}")
    again = turn()
    assert again["status"] == "refused" and "not a move for this question" in again["why"], again


def test_a_refused_refine_spends_nothing(monkeypatch):
    e = _engine(Mode.AUTO)
    _goal(e)
    _admit(e, "kid", _kid("gk", ["k"], criterion("x", "X holds")))
    monkeypatch.setattr(I, "_still_open", lambda *a: True)
    refused = I.Verbs(llm=None, busy=VERBS.busy, review=None, refine=lambda engine, node: {"error": "no split"})
    assert I.issuer_turn(e, TaskId("kid"), "plan", "exec-1", verbs=refused,
                         _llm=_FakeLLM({"move": "refine", "justification": "re-cut"}))["status"] == "refused"
    assert "refine" in I.moves_for(e, e.graph.get_task("kid"), "plan")
