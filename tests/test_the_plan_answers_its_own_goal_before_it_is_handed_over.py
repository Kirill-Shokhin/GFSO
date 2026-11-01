"""The question the gate will ask, asked by whoever writes the answer.

`auto_decompose` authored a root whose own Level-2 gate then named five to twelve obligations of that
same goal that none of its criteria decides (FM-1.f) — a minute after the criteria were written, by
the same product, and the caller paid two review rounds to repair it (measured on both agent doors,
2026-09-02). It is one question; what changed is only who asks it and when.

Bounded to ONE pass on purpose: the loop is what cost twenty-six rounds and $19.44 on the measurement
arm before it was bounded, and the switch exists because that arm must still be able to author a plan
this has NOT pre-repaired — otherwise the two halves of the experiment are the same half.
"""
import pytest

import gfso.decompose as D
import gfso.decompose.loop as L
from gfso.config import sufficiency_at_authoring


@pytest.fixture(autouse=True)
def _repairs_alone(monkeypatch):
    """The repair loop alone: the stored goal reading and the checker's reading at the last repair have tests of their own."""
    monkeypatch.setattr(D, "record_goal_reading", lambda *a, **k: None)
    monkeypatch.setenv("GFSO_CHECKER_AT_AUTHORING", "0")


def test_named_obligations_are_folded_in_and_the_residue_is_measured(monkeypatch):
    """…and MEASURED, not claimed: the first version announced the close and handed over the same
    seven still open, because it never asked again (CLI door, 2026-09-02)."""
    calls, asked = [], []
    def _check(engine, task, llm, **k):
        asked.append(1)
        return ({"obligation": "it must actually sort"},) if len(asked) == 1 else ()
    monkeypatch.setattr(D, "_undecided_obligations", _check)
    # the open obligations go to the parts at once (`_pin_by_part`), each part pinning what it builds
    monkeypatch.setattr(D, "_pin_by_part", lambda engine, request, rid, assignee, llm, gaps, *a: (
        calls.append(" | ".join(g["obligation"] for g in gaps)) or (True, {"after": True}, [])))

    class _Eng:
        graph = property(lambda self: self)

        def get_task(self, _):
            return object()

    spec, holes, residue = D._close_the_goals_obligations(_Eng(), "sort a file", "root", "agent",
                                                          None, {"before": True}, ["a hole"], None)
    assert spec == {"after": True} and holes == []
    assert "it must actually sort" in calls[0], "the obligation reaches the verb that repairs plans, as its findings"
    assert asked == [1, 1], "it asked again after the repair"
    assert residue == (), "…and this time the answer was empty, so nothing is claimed falsely"


def test_what_the_repair_did_not_close_is_named(monkeypatch):
    """A residue is the caller's to know BEFORE they pay a review round for it."""
    monkeypatch.setattr(D, "_undecided_obligations",
                        lambda engine, task, llm, **k: ({"obligation": "it must handle a missing column"},))
    monkeypatch.setattr(D, "_pin_by_part", lambda *a, **k: (True, {"after": True}, []))
    monkeypatch.setattr(D, "_refine_round", lambda *a, **k: (True, {"after": True}, []))

    class _Eng:
        graph = property(lambda self: self)

        def get_task(self, _):
            return object()

    _, _, residue = D._close_the_goals_obligations(_Eng(), "g", "root", "agent", None, {}, [], None)
    assert residue == ("it must handle a missing column",)


def test_a_check_that_names_nothing_changes_nothing(monkeypatch):
    """⊥ is not "the goal is covered" (§2.3) — an empty answer must not look like a clean bill."""
    monkeypatch.setattr(D, "_undecided_obligations", lambda engine, task, llm, **k: ())
    monkeypatch.setattr(D, "_refine_round",
                        lambda *a, **k: (_ for _ in ()).throw(AssertionError("nothing to fold")))

    class _Eng:
        graph = property(lambda self: self)

        def get_task(self, _):
            return object()

    assert D._close_the_goals_obligations(_Eng(), "g", "root", "agent", None, {"s": 1}, ["h"],
                                          None) == ({"s": 1}, ["h"], ())


def test_the_measurement_arm_can_author_a_plan_this_has_not_touched(monkeypatch):
    assert sufficiency_at_authoring() is True
    monkeypatch.setenv("GFSO_SUFFICIENCY_AT_AUTHORING", "0")
    assert sufficiency_at_authoring() is False


def test_what_the_parts_left_reaches_the_round_that_repairs_seams(monkeypatch):
    """Part by part first; what no single part builds goes on to the round that may add a root criterion for the
    integration and pin it on each child — routed to the parts alone, c_compiler's cross-part residue reached no
    repair (critic over the pin-by-part authoring, 2026-10-31). A first round that added nothing still hands it on."""
    left = ({"obligation": "two units link into one program", "admits": "each compiles, the link fails"},)
    reads = iter([left, left, ()])
    monkeypatch.setattr(D, "_undecided_obligations", lambda *a, **k: next(reads))
    parts, seams = [], []
    monkeypatch.setattr(D, "_pin_by_part", lambda *a, **k: parts.append(1) or (False, {}, []))
    monkeypatch.setattr(D, "_refine_round", lambda *a, findings="", **k: seams.append(findings) or (True, {"s": 1}, []))

    class _Eng:
        graph = property(lambda self: self)

        def get_task(self, _):
            return object()

    _, _, residue = D._close_the_goals_obligations(_Eng(), "g", "root", "agent", None, {}, [], None)
    assert parts == [1] and len(seams) == 1, "the parts first, then the seams' round"
    assert "two units link into one program" in seams[0]
    assert residue == ()


def test_root_criteria_the_children_do_not_entail_reach_a_repair(monkeypatch):
    """The checker's unentailed root criteria are no obligation a part builds: they go to the seams' round with the
    obligations still open, never to the parts alone."""
    monkeypatch.setenv("GFSO_CHECKER_AT_AUTHORING", "1")
    gap = ({"obligation": "o", "admits": "a"},)
    reads = iter([gap, ()])
    monkeypatch.setattr(D, "_undecided_obligations", lambda *a, **k: next(reads))
    monkeypatch.setattr(D, "_pin_by_part", lambda *a, **k: (True, {}, []))

    class _Verdict:
        semantic_covered = False
        criteria_verdicts = ({"criterion": "links", "verdict": "insufficient", "why": "no child links"},)
        undecided_obligations = gap
    monkeypatch.setattr(D, "critique_node", lambda *a, **k: _Verdict())
    seams = []
    monkeypatch.setattr(D, "_refine_round", lambda *a, findings="", **k: seams.append(findings) or (True, {}, []))

    class _Eng:
        graph = property(lambda self: self)

        def get_task(self, _):
            return object()

    D._close_the_goals_obligations(_Eng(), "g", "root", "agent", None, {}, [], None)
    assert len(seams) == 1 and "root criterion links is not entailed" in seams[0]


def test_a_part_answer_of_the_wrong_shape_or_a_name_twice_loses_nothing_else(monkeypatch):
    """A malformed part answer ended the whole paid authoring, and a name added twice landed twice (critic)."""
    spec = {"subtasks": [{"id": "a", "criteria": []}, {"id": "b", "criteria": []}]}
    good = {"name": "n", "description": "d", "check": [{"behaviour": "x", "command": "./prog --one", "expect": "1"}]}
    answers = {"a": {"add_criteria": [good, dict(good), "bare", {"name": "m", "check": "echo"}]},
               "b": {"add_criteria": "two criteria"}}

    class _LLM:
        def complete_structured(self, system, user, schema):
            return answers["a" if "# YOUR PART: a" in user else "b"]
    monkeypatch.setattr(D, "extract_spec", lambda *a, **k: spec)
    monkeypatch.setattr(D, "fan", lambda llm, items, fn, stage: [fn(i) for i in items])
    built = []
    monkeypatch.setattr(D, "_build_verified", lambda new, *a, **k: built.append(new) or (None, new, []))
    changed, out, _ = D._pin_by_part(None, "g", "root", "agent", _LLM(), [{"obligation": "o"}], None, "", None)
    (a,) = [p for p in out["subtasks"] if p["id"] == "a"]
    assert changed and [c["name"] for c in a["criteria"]] == ["n"]


def test_the_measurement_arm_authors_with_no_reading_of_the_gate(monkeypatch):
    """`GFSO_SUFFICIENCY_AT_AUTHORING=0` authors a plan the gate has not pre-repaired: no obligations reach the first
    fold, and the gate's reading is never asked (critic over the first fold)."""
    monkeypatch.setenv("GFSO_SUFFICIENCY_AT_AUTHORING", "0")
    monkeypatch.setattr(L, "goal_obligations", lambda *a: (_ for _ in ()).throw(AssertionError("the gate was read")))
    monkeypatch.setattr(L, "_search", lambda *a, **k: "found by search")
    seen = []
    monkeypatch.setattr(L, "_audit_fold", lambda llm, request, prev, holes, **k: seen.append(holes) or {})
    L.decompose_spec("g", llm=type("Q", (), {"on_tick": "absent"})())
    assert seen == ["found by search"]
