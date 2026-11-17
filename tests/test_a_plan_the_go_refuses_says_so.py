"""`plan`'s answer names what the go will refuse, by the go's own reading (`go_refusals`: the admission's rules, then its
split built where nothing is kept), before the customer gives the go: the authoring's last repair could leave seams the go
refuses, and a customer read a 40-minute c_compiler plan, gave the go and met 23 refusals (2026-11-11). The way on is
one `refine_plan` with them; still refused after it, the person is told."""
import pytest

import gfso.tools_llm as TL
from gfso import decompose as D
from gfso.core.types import Mode
from gfso.decompose import artifact as A
from tests.test_the_go_only_adds_to_the_plan import GOAL, SRC, _plan, _probe, go  # noqa: F401 — `go` is a fixture
from tests.test_the_mode_decides_who_holds_what import _engine


def _by_rule():          # a root probe the admission refuses (a shared path)
    spec = _plan()
    spec["root_criteria"][0]["check"].append(_probe("make && ./wc2 {inputs}/a.c", "1 3 30", exact=True,
                                                    inputs={"a.c": SRC}))
    return spec


def _by_build():         # a criterion no part covers: the split the trial build refuses (CHECK-1)
    spec = _plan()
    spec["mappings"] = spec["mappings"][:1]
    return spec


@pytest.mark.parametrize("broken", [_by_rule, _by_build], ids=["rule", "build"])
def test_what_the_go_refuses_the_plans_answer_names_first(broken, go, monkeypatch):
    text = A.render(GOAL, broken(), {"by": "m", "gate_passed": True})
    monkeypatch.setattr(TL._planning, "kept", lambda t: "plans/x.gfso")
    answer = TL._plan_written(text)
    assert answer.get("refused_by_the_go") and "Do not give the go" in answer["say"] and "refine_plan" in answer["say"]
    with pytest.raises(ValueError, match="refused as it stands") as refused:
        TL.auto_decompose(_engine(Mode.AUTO), plan=text)
    assert all(point in str(refused.value) for point in answer["refused_by_the_go"])


def test_a_plan_the_go_admits_is_offered_for_it(go, monkeypatch):
    monkeypatch.setattr(TL._planning, "kept", lambda t: "plans/x.gfso")
    answer = TL._plan_written(A.render(GOAL, _plan(), {"by": "m", "gate_passed": True}))
    assert "refused_by_the_go" not in answer and "auto_decompose" in answer["say"]
    go(A.render(GOAL, _plan(), {"by": "m", "gate_passed": True}))


def test_still_refused_after_its_one_round_the_person_is_told_not_sent_round_again(go, monkeypatch):
    monkeypatch.setattr(TL._planning, "kept", lambda t: "plans/x.gfso")
    text = A.render(GOAL, _by_build(), {"by": "m", "gate_passed": True}, notes=[{"note": "n", "answer": "a"}])
    answer = TL._plan_written(text)
    assert answer["refused_by_the_go"] and "left the plan unrunnable" in answer["say"]
    assert "refine_plan(" not in answer["say"]


def test_the_repair_after_the_build_is_told_what_the_go_would_refuse(monkeypatch):
    """The post-build patch rewrote parts and seams and nothing read its seams again: the round after the build gets the
    admission's refusals beside the build's own problems."""
    told = []
    monkeypatch.setattr(D, "_repaired_before_build", lambda spec, *a, **k: spec)
    monkeypatch.setattr(D, "admission_refusals", lambda spec, *a, **k: ["seam a → b: names nothing"])
    monkeypatch.setattr(D, "_audit_fix", lambda llm, request, spec, problems, executor: told.extend(problems) or {})
    e = _engine(Mode.AUTO)
    try:
        D._build_verified(_plan(), GOAL, e, "root", "user", llm=None)
    finally:
        e.stop()
    assert "seam a → b: names nothing" in told
