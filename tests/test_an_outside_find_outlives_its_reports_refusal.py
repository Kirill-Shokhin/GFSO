"""What a validator saw outside the criteria is the issuer's whether or not its report decided the verdict: a report
refused as ⊥ keeps its outside rows beside the node (`get_verdict`'s `refused_report`), the retry is told they stand,
and the verdict the next report records carries them, to be seen anew by the system's run of their probes (§8.3 FM-1.f;
Inv-2 — never a value of V). Measured, replay r3 on 332fd879: the first report named the injected defect outside the
criteria, was refused for a behaviour it had not observed, and the retry — asked only to close that gap — recorded a
PASS with nothing outside: the find reached nobody.

CONTROL (each red): drop the `carried_outside` line in `_record_node` → the carried test; drop `outside=` from the
refused path's `record_rejected_report` → both tests; drop the `outside` key in `tools`' refused read → the read test;
drop the retry packet's block → the carried test's packet line.
"""
from __future__ import annotations

import json

import gfso.tools_llm as TL
import gfso.validate as VAL
from gfso.core.types import TaskId
from tests.test_a_small_task_takes_the_canons_acts import ASKED, WORDS, _Validator, _filled, _set_up, _worked, chat, pytestmark

__all__ = ["chat", "pytestmark"]

_FIND = {"what": "f.txt is rewritten on every run", "evidence": "read in the diff",
         "probe": {"command": "cat f.txt", "expect": "v1"}}
_OWED = "a behaviour the first report observed nothing of"


class _Refused(_Validator):
    """A validator whose first `refused` reports name a behaviour nothing observed (refused, ⊥) and saw `_FIND`
    outside; every later report is a clean pass with nothing outside."""

    def __init__(self, e, refused: int):
        super().__init__(e)
        self.refused, self.users = refused, []

    def run_agent(self, system, user, allowed_tools, cwd=None, timeout=None):
        self.users.append(user)
        text = super().run_agent(system, user, allowed_tools, cwd, timeout)
        d = json.loads(text.split("```json\n", 1)[1].rsplit("\n```", 1)[0])
        entry = d["per_criterion"][0]
        entry["behaviours"].append(_OWED)
        if len(self.users) > self.refused:              # …the retry observes what the refusal named, and says nothing outside
            entry["probe"].append({**entry["probe"][0], "behaviour": _OWED})
        else:
            d["outside"] = [_FIND]
        return "```json\n" + json.dumps(d) + "\n```"


def _delivered(e, repo, call, monkeypatch, refused: int) -> _Refused:
    v = _Refused(e, refused)
    monkeypatch.setattr(VAL, "llm_factory", lambda *a, **k: v)
    _set_up(call, repo)
    call("auto_decompose", plan=call("plan", plan=_filled(call("plan", ASKED)["text"]))["path"], user_said=WORDS)
    _worked(repo)
    call("signal", "root", "DELIVER", "user", result="f.txt written", self_validation="PASS")
    call("wait", seconds=60)
    return v


def _whats(rows) -> list:
    return [o["what"] for o in rows or ()]


def test_a_refused_reports_outside_find_is_read_beside_the_node(chat, monkeypatch):
    e, repo, call, _ = chat
    _delivered(e, repo, call, monkeypatch, refused=99)
    assert _whats((e.rejected_report(TaskId("root")) or {}).get("outside")) == [_FIND["what"]]
    read = TL.TOOLS["get_verdict"](e, "root").get("refused_report") or {}
    assert _whats(read.get("outside")) == [_FIND["what"]], read


def test_the_verdict_after_the_refusal_carries_the_find(chat, monkeypatch):
    e, repo, call, _ = chat
    v = _delivered(e, repo, call, monkeypatch, refused=1)
    if len(v.users) < 2:                                # …the retry, where the system did not ask it by itself
        call("validate_result", "root")
        call("wait", seconds=60)
    rec = e.current_exec_verdict(TaskId("root")) or {}
    assert len(v.users) == 2 and rec.get("verdict") == "PASS", (len(v.users), rec)
    assert _whats(rec.get("outside")) == [_FIND["what"]], rec
    assert "OUTSIDE the criteria stays on the record" in v.users[1] and _FIND["what"] in v.users[1]
