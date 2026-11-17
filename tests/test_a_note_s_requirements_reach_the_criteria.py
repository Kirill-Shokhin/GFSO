"""A customer's note names what the person wants — «compile, search, match, fullmatch, findall, sub, groups, flags» — and
the refine round carried all but `sub`; the reviews read the goal alone, so nothing saw it, and the AUTO run delivered an
engine without it (FM-1.f, regex, haiku, 2026-11-13). The notes' requirements are read as obligations by the gate's own
question, handed to the round, and decided against the plan after it: one no pinned check probes is said in the answer
(the note not spent) and stays in the review the next round and the go read."""
import copy
import json

import gfso.decompose as D
from gfso.critic import runner
from gfso.critic.types import NodeCritique
from gfso.decompose import artifact as A, planning
from tests.test_the_go_only_adds_to_the_plan import GOAL, _plan

NOTE = "the counter must offer --lines and --bytes"
ASKED = [{"obligation": "offers --lines", "admits": "no --lines"}, {"obligation": "offers --bytes", "admits": "no --bytes"}]


class _Says:
    """A model that answers every call with `text`."""
    calls: list = []

    def __init__(self, text):
        self.text = text

    def complete(self, prompt="", context=""):
        return self.text


def _refined(monkeypatch, decided: list[str]) -> tuple[str, dict]:
    """(what the round was handed, the plan file after it) — the round leaving the plan as it was, the reviewer finding
    the numbered obligations of `decided` probed by a pin and the rest open."""
    handed = []
    monkeypatch.setattr(D, "default_llm", lambda *a, **k: _Says(json.dumps({"gaps": ASKED})))
    monkeypatch.setattr(D, "repaired_before_build", lambda spec, *a, **k: spec)
    monkeypatch.setattr(D, "refine_with", lambda e, g, rid, a, llm, findings, **k: (handed.append(findings), (False, None, []))[1])
    monkeypatch.setattr(planning, "extract_spec", lambda *a, **k: copy.deepcopy(_plan()))
    monkeypatch.setattr(runner, "review_decomposition", lambda e, rid, llm=None: NodeCritique(str(rid), gate_passed=True))
    still = {"decided": decided, "open": [{"n": n, "admits": "no pin runs it"} for n in ("1", "2") if n not in decided]}
    monkeypatch.setattr(planning, "llm_factory", lambda *a, **k: _Says(json.dumps(still)))
    out = A.parse(planning.refine(A.render(GOAL, _plan()), NOTE, "m"))
    return handed[0], out


def test_a_clause_of_the_note_no_pinned_check_probes_is_said_and_kept_open(monkeypatch):
    handed, out = _refined(monkeypatch, ["1"])
    assert "WHAT THE CUSTOMER'S NOTES REQUIRE" in handed and "offers --bytes" in handed, handed
    answer = out["notes"][-1]["answer"]
    assert "NOT ANSWERED" in answer and "offers --bytes" in answer.split("NOT ANSWERED", 1)[1], answer
    assert "offers --lines" not in answer, "a clause a pin probes is carried"
    assert [g["obligation"] for g in out["review"]["undecided_obligations"] if g.get("of") == "note"] == ["offers --bytes"]


def test_a_note_every_clause_of_which_a_pin_probes_is_answered(monkeypatch):
    _, out = _refined(monkeypatch, ["1", "2"])
    assert "NOT ANSWERED" not in out["notes"][-1]["answer"]
