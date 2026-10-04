"""What the authoring path pays for, once: findings in hand are not searched for again, a structured answer cut at the
output limit is asked for SHORTER (the same request hits the same limit), and a carried obligation's argument is
written once however many rounds carry it (AUTO haiku coreutils, 2026-10-11/12)."""
import json
import threading
import time as _t

import gfso.decompose as D
from gfso.adapters.llm.headless import HeadlessClaudeLLM
from gfso.adapters.llm.stats import readings
from gfso.adapters.llm.structured import RETRY_SHORTER, RETRY_SUFFIX
from gfso.core.types.ports import LLMProviderPort
from gfso.critic import runner as R
from gfso.issuer import _standing_ids
from tests.support import make_engine, spec
from gfso.core.types import AgentId, TaskId


def test_given_findings_skip_the_search(monkeypatch):
    e = make_engine(llm=None, check_interval=10_000)
    e.start()
    try:
        e.assign_task(TaskId("root"), spec("goal", "c1"), AgentId("agent"))
        e.wait_idle()
        searched, folded = [], []
        monkeypatch.setattr(D, "_search", lambda *a, **k: searched.append(1) or "found")
        monkeypatch.setattr(D, "_audit_fold", lambda llm, req, state, holes, **k: folded.append(holes) or {})
        D._refine_round(e, "goal", "root", "agent", object(), findings="the listed obligations")
        D._refine_round(e, "goal", "root", "agent", object())
    finally:
        e.stop()
    assert searched == [1], "only the round with no findings searched"
    assert folded == ["the listed obligations", "found"]


def _llm_answering(*outs):
    llm = HeadlessClaudeLLM.__new__(HeadlessClaudeLLM)
    llm.calls, asked, it = [], [], iter(outs)

    def _call(system, user, **k):
        text, stop = next(it)
        asked.append(user)
        llm.calls.append({"stop_reason": stop})
        return text
    llm._call = _call
    return llm, asked


def test_an_answer_cut_at_the_limit_is_asked_for_shorter():
    schema = {"type": "object", "properties": {"a": {"type": "string"}}, "required": ["a"]}
    llm, asked = _llm_answering(('```json\n{"a": "x', "max_tokens"), ('```json\n{"a": "x"}\n```', "end_turn"))
    assert llm.complete_structured("s", "u", schema) == {"a": "x"}
    assert asked[1].endswith(RETRY_SHORTER)
    llm, asked = _llm_answering(("not json", "end_turn"), ('```json\n{"a": "x"}\n```', "end_turn"))
    llm.complete_structured("s", "u", schema)
    assert asked[1].endswith(RETRY_SUFFIX), "an answer that was not cut is asked again as before"


def test_a_carried_obligation_says_its_argument_once(monkeypatch):
    monkeypatch.setattr(R, "parse_structured", lambda *a, **k: {"decided": []})

    class _LLM:
        def complete(self, prompt, context=""):
            return "{}"

    task = type("T", (), {"id": TaskId("root"),
                          "spec": type("S", (), {"description": "g", "criteria": ()})()})()
    rows = ({"obligation": "it sorts", "admits": "an unsorted result"},)
    for _ in range(4):
        rows = R._still_undecided(None, task, _LLM(), rows)
    assert rows[0]["admits"].count("RE-CHECKED") == 1
    assert rows[0]["admits"].endswith("an unsorted result")


def test_independent_readings_run_at_once_and_each_call_carries_its_stage():
    """Three readings of one question are independent; serially the authoring paid them back to back (~100 s, twice
    per plan). On a provider that may be called at once they overlap, and every call made is labelled with the stage."""
    class _P(LLMProviderPort):
        parallel_safe = True

        def __init__(self):
            self.calls, self.live, self.peak, self._l = [], 0, 0, threading.Lock()

        def complete(self, prompt, context=None):
            with self._l:
                self.live += 1
                self.peak = max(self.peak, self.live)
            _t.sleep(0.05)
            with self._l:
                self.live -= 1
                self.calls.append({"stage": None})
            return "x"

    p = _P()
    assert readings(p, 3, lambda: p.complete("q"), "undecided-obligations") == ["x"] * 3
    assert p.peak == 3
    assert [c["stage"] for c in p.calls] == ["undecided-obligations"] * 3
    p.parallel_safe = False
    p.peak = 0
    readings(p, 3, lambda: p.complete("q"), "s")
    assert p.peak == 1, "a provider that does not say so is read one at a time"


def test_a_ruling_names_its_findings_as_the_engine_keeps_them():
    """Named by a bare hash, the issuer's ruling was refused whole and a true challenge was rejected a dozen times over
    17 min (root.build, 2026-10-12); a finding that no longer stands names nothing to retire — and an acceptance left
    with nothing to retire and no criterion changed decides nothing (re-offered unchanged, it was challenged ten times)."""
    class _E:
        def regression_probes(self, _):
            return {"Dispatch": [{"id": "Dispatch#94cafe8f"}], "Other": [{"id": "Other#0f075147"}]}

    assert _standing_ids(_E(), "n", ["94cafe8f", "gone#123", "Other#0f075147", "94cafe8f"]) == \
        ["Dispatch#94cafe8f", "Other#0f075147"]
