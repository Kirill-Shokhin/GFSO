"""The go refuses a plan file the admission would refuse and sends the customer to `refine_plan` with a note — and the
round itself built the file first and died on the same refusal (V3_cc2, 2026-11-01): the advice was a dead end. The
admission's refusals are the round's first findings, repaired before the build, and the answer says what changed."""
import copy

import gfso.decompose as D
from gfso.decompose import artifact as A, planning
from tests.test_the_go_only_adds_to_the_plan import GOAL, _plan, _probe


def test_a_plan_the_admission_refuses_is_repaired_by_the_round(monkeypatch):
    good = _plan()
    bad = copy.deepcopy(good)
    bad["root_criteria"][0]["check"].append(_probe("make && ./wc {inputs}/zz.c", "1 3 30", exact=True))
    shown = []

    def fix(llm, request, spec, refused, executor):
        shown.extend(refused)
        return {"root_criteria": good["root_criteria"]}
    monkeypatch.setattr(D, "_audit_fix", fix)
    monkeypatch.setattr(D, "default_llm", lambda *a, **k: object())
    monkeypatch.setattr(D, "refine_with", lambda *a, **k: (False, None, []))
    monkeypatch.setattr(planning, "_review", lambda *a, **k: {})
    out = A.parse(planning.refine(A.render(GOAL, bad), "pin what zz.c needs", "m"))
    assert any("zz.c" in r for r in shown), "the admission's refusal was the round's finding"
    assert out["spec"]["root_criteria"] == good["root_criteria"]
    assert not out["notes"][-1]["answer"].startswith("the plan is unchanged"), out["notes"][-1]["answer"]


def test_a_repair_that_re_emits_part_of_a_list_drops_only_what_its_findings_name():
    """A repair over a few refused probes re-emitted 3 of a plan's 38 criteria, and the rest were dropped silently
    (V3_cc2, haiku): what the patch leaves out stays, unless a finding the repair answers names it."""
    spec = {"subtasks": [{"id": "a"}, {"id": "b"}, {"id": "orphan"}],
            "root_criteria": [{"name": "x"}, {"name": "y", "check": []}]}
    fixed = {"subtasks": [{"id": "a", "name": "fixed"}], "root_criteria": [{"name": "y", "check": ["p"]}]}
    out = D._patched(spec, fixed, "CHECK-1b: part orphan addresses no criterion")
    assert [s["id"] for s in out["subtasks"]] == ["a", "b"] and out["subtasks"][0]["name"] == "fixed"
    assert [c["name"] for c in out["root_criteria"]] == ["y", "x"] and out["root_criteria"][0]["check"] == ["p"]
