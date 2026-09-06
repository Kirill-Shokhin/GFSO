"""The question the gate will ask, asked by whoever writes the answer.

`auto_decompose` authored a root whose own Level-2 gate then named five to twelve obligations of that
same goal that none of its criteria decides (FM-1.f) — a minute after the criteria were written, by
the same product, and the caller paid two review rounds to repair it (measured on both agent doors,
2026-09-02). It is one question; what changed is only who asks it and when.

Bounded to ONE pass on purpose: the loop is what cost twenty-six rounds and $19.44 on the measurement
arm before it was bounded, and the switch exists because that arm must still be able to author a plan
this has NOT pre-repaired — otherwise the two halves of the experiment are the same half.
"""
import gfso.decompose as D
from gfso.config import sufficiency_at_authoring


def test_named_obligations_are_folded_in_and_the_residue_is_measured(monkeypatch):
    """…and MEASURED, not claimed: the first version announced the close and handed over the same
    seven still open, because it never asked again (CLI door, 2026-09-02)."""
    calls, asked = [], []
    def _check(engine, task, llm, **k):
        asked.append(1)
        return ({"obligation": "it must actually sort"},) if len(asked) == 1 else ()
    monkeypatch.setattr(D, "_undecided_obligations", _check)
    monkeypatch.setattr(D, "_refine_round",
                        lambda *a, **k: (calls.append(a[1]) or (True, {"after": True}, [])))

    class _Eng:
        def get_task(self, _):
            return object()

    spec, holes, residue = D._close_the_goals_obligations(_Eng(), "sort a file", "root", "agent",
                                                          None, {"before": True}, ["a hole"], None)
    assert spec == {"after": True} and holes == []
    assert "it must actually sort" in calls[0], "the obligation reaches the verb that repairs plans"
    assert asked == [1, 1], "it asked again after the repair"
    assert residue == (), "…and this time the answer was empty, so nothing is claimed falsely"


def test_what_the_repair_did_not_close_is_named(monkeypatch):
    """A residue is the caller's to know BEFORE they pay a review round for it."""
    monkeypatch.setattr(D, "_undecided_obligations",
                        lambda engine, task, llm, **k: ({"obligation": "it must handle a missing column"},))
    monkeypatch.setattr(D, "_refine_round", lambda *a, **k: (True, {"after": True}, []))

    class _Eng:
        def get_task(self, _):
            return object()

    _, _, residue = D._close_the_goals_obligations(_Eng(), "g", "root", "agent", None, {}, [], None)
    assert residue == ("it must handle a missing column",)


def test_a_check_that_names_nothing_changes_nothing(monkeypatch):
    """⊥ is not "the goal is covered" (§11.2) — an empty answer must not look like a clean bill."""
    monkeypatch.setattr(D, "_undecided_obligations", lambda engine, task, llm, **k: ())
    monkeypatch.setattr(D, "_refine_round",
                        lambda *a, **k: (_ for _ in ()).throw(AssertionError("nothing to fold")))

    class _Eng:
        def get_task(self, _):
            return object()

    assert D._close_the_goals_obligations(_Eng(), "g", "root", "agent", None, {"s": 1}, ["h"],
                                          None) == ({"s": 1}, ["h"], ())


def test_the_measurement_arm_can_author_a_plan_this_has_not_touched(monkeypatch):
    assert sufficiency_at_authoring() is True
    monkeypatch.setenv("GFSO_SUFFICIENCY_AT_AUTHORING", "0")
    assert sufficiency_at_authoring() is False
