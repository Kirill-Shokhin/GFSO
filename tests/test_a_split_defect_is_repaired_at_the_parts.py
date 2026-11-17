"""A review that marks a root criterion `insufficient` says the split's children do not secure it — the decomposer's
defect, repaired at the parts (§2.4 joint sufficiency, §9.7). The refine round over a plan file was never handed those
verdicts, only the goal's undecided obligations, and answered each note by adding root criteria the next review marked
insufficient too, the children's criteria as they were (regex run, haiku, 2026-11-13)."""
import copy

import gfso.decompose as D
from gfso.decompose import artifact as A, planning
from tests.test_the_go_only_adds_to_the_plan import GOAL, _plan, _probe

GAP = "core's criteria do not fix which count is printed"
VERDICTS = {"criteria_verdicts": [{"criterion": "counts", "verdict": "insufficient", "why": GAP},
                                {"criterion": "errors", "verdict": "sufficient", "why": "io exits 1"}]}


def _refined(monkeypatch, after) -> tuple[str, str]:
    """(what the round was handed, the answer it got) for the plan reviewed with VERDICTS, the round leaving `after`."""
    handed = []
    monkeypatch.setattr(D, "default_llm", lambda *a, **k: object())
    monkeypatch.setattr(D, "repaired_before_build", lambda spec, *a, **k: spec)
    monkeypatch.setattr(D, "refine_with", lambda e, g, rid, a, llm, findings, **k: (handed.append(findings), (True, None, []))[1])
    monkeypatch.setattr(planning, "extract_spec", lambda *a, **k: copy.deepcopy(after))
    monkeypatch.setattr(planning, "_review", lambda *a, **k: {})
    out = A.parse(planning.refine(A.render(GOAL, _plan(), VERDICTS), "make the counts right", "m"))
    return handed[0], out["notes"][-1]["answer"]


def test_the_round_is_handed_the_criterion_its_children_do_not_secure_as_theirs_to_repair(monkeypatch):
    handed, _ = _refined(monkeypatch, _plan())
    assert f"[insufficient] counts — {GAP}" in handed, handed
    assert "parts" in handed.split("[insufficient] counts")[0].rsplit("#", 1)[1], "framed as the split's defect"
    assert "errors" not in handed, "a sufficient criterion is no finding"


def test_a_round_that_answered_it_with_a_root_criterion_is_said_to_have_left_it(monkeypatch):
    wider = _plan()
    wider["root_criteria"].append({"name": "counts-exact", "description": "prints 1 3 29", "check": [_probe("./wc2 x")]})
    wider["mappings"].append({"criterion": "counts-exact", "child_id": "core"})
    _, answer = _refined(monkeypatch, wider)
    assert "NOT REPAIRED" in answer and "counts" in answer.split("NOT REPAIRED", 1)[1], answer


def test_a_round_that_gave_the_parts_the_check_repaired_it(monkeypatch):
    fixed = _plan()
    fixed["subtasks"][0]["criteria"].append({"name": "c2", "description": "prints lines words bytes",
                                             "check": [_probe("./core_test2", "1 3 29")]})
    _, answer = _refined(monkeypatch, fixed)
    assert "NOT REPAIRED" not in answer, answer
