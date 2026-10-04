"""A validation cut into batches runs a batch whose report did not parse once more, alone, inside the same validation,
in a fresh scratch place of its own.

Measured (AUTO haiku coreutils, GB_coreutils_tmsiyo732, 2026-10-12): the root's validation ran as seven batches; in
each of fifteen attempts over an hour one or two batches' JSON lost a closing bracket, the whole report "did not
parse", and all seven were run again ($3.95 of validation against $0.42 of execution). Keeping the parsed batches'
entries across attempts was tried and refuted: a share of a split criterion decides nothing alone, and the entries
crossed onto a revised contract (critic over c2b3fcd).

CONTROLS: run `_run` instead of `_run_again_if_unread` for several batches — the validation decides nothing; run the
second call in `place` — the run again sees the first run's place.
"""
from __future__ import annotations

import json

from gfso import tools as T
from gfso import tools_llm as TL
from tests.support import criterion
from tests.test_validate_result import _eng, _fenced

NAMES = ("a", "b", "c")


def _node(e):
    T.create_task(e, "n", {"description": "three criteria, one probe each", "criteria": [
        criterion(k, check=[{"behaviour": f"{k} holds", "command": f"check {k}", "expect": "ok"}]) for k in NAMES]},
        "alice")
    T.signal(e, "n", "ACCEPT", "alice")
    T.signal(e, "n", "DELIVER", "alice", result="built it")


class _Runs:
    """Passes every criterion its packet lists; the first run carrying a name in `broken` (shared by every client)
    answers JSON short of a bracket; `scratch` collects the scratch line of every run carrying `b`."""
    broken: set = set()
    scratch: list = []

    def __init__(self):
        self.calls, self.packets = [], []
        self.last_tool_calls, self.on_tick, self.stage_hint = {"Bash": 1}, None, ""

    def run_agent(self, system, user, allowed_tools, cwd=None, timeout=None):
        self.calls.append({"duration_ms": 1, "input_tokens": 1, "output_tokens": 1})
        self.packets.append(user)
        if "**b**" in user:
            self.scratch.append(next((ln for ln in user.splitlines() if "scratch directory" in ln), ""))
        entries = [{"criterion": k, "verdict": "pass", "evidence": "ran it", "behaviours": [f"{k} holds"],
                    "probe": [{"behaviour": f"{k} holds", "command": f"check {k}", "expect": "ok"}]}
                   for k in NAMES if f"**{k}**" in user]
        report = {"verdict": "PASS", "failed_criteria": [], "per_criterion": entries}
        if hit := next((k for k in sorted(self.broken) if f"**{k}**" in user), None):
            self.broken.discard(hit)
            return "```json\n" + json.dumps(report)[:-2] + "}\n```"        # the array left open
        return _fenced(report)

    def tag_last(self, stage):
        self.calls[-1]["stage"] = stage


def _broken_b(monkeypatch):
    monkeypatch.setenv("GFSO_VALIDATION_BATCH", "1")
    monkeypatch.setattr(_Runs, "broken", {"b"})
    monkeypatch.setattr(_Runs, "scratch", [])


def test_the_unread_batch_alone_is_run_again_and_the_validation_decides(monkeypatch):
    _broken_b(monkeypatch)
    e = _eng()
    _node(e)
    llm = _Runs()
    out = TL.validate_result(e, "n", _llm=llm, workdir=".")
    assert len(llm.packets) == 4 and sum("**b**" in p for p in llm.packets) == 2, len(llm.packets)
    assert out["verdict"] == "PASS", out
    e.stop()


def test_the_run_again_works_in_a_fresh_place_of_its_own(monkeypatch, tmp_path):
    """The batches run at once, each in its own scratch place; the run again got the first run's place with its
    leftovers in it — the scratch exists so no run validates another's (critic over 779eade)."""
    _broken_b(monkeypatch)
    e = _eng()
    _node(e)
    out = TL.validate_result(e, "n", _llm=_Runs(), workdir=str(tmp_path), _spawn=_Runs)
    assert out["verdict"] == "PASS", out
    seen = _Runs.scratch
    assert len(seen) == 2 and seen[0] != seen[1] and "_again" in seen[1], seen
    e.stop()
