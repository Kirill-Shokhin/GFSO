"""A Level-2 round gated out at Level 0 must not mark the plan verified.

`review_decomposition` set `verified = True` unconditionally — three lines below a comment of its own
that promised the opposite for exactly this case ("A ROUND THAT DID NOT RUN THE CHECKER … The node is
still marked unverified below"). The prose was right and the code did the other thing, so a review
that judged nothing, because the structure was too broken to judge, certified the plan.

A stranger on the HTTP door read all three surfaces in one instant and quoted them (wave 23,
2026-09-03):

    list_holes           -> [{"check": "CHECK-1:coverage", "details": "no criterion mappings declared"}]
    review_decomposition -> {"gate_passed": false, "execution_admitted": false, "l0l1_failures": [...]}
    get_review           -> {"verified": true, "execution_admitted": true, "open_findings": []}

`execution_admitted` is the field this product tells an integrator to gate on. Enforcement itself
held — the state machine still refused the children — so what was wrong was the READ, which is the
half an outside system actually trusts.

The probe below needs no model: the Level-0 gate short-circuits before the checker, and the stub here
raises if anything calls it, so a green run is also evidence that no round was paid for.
"""
from __future__ import annotations

from gfso import tools as T
from gfso.core.types import TaskId
from gfso.critic.runner import review_decomposition
from tests.support import UNMODELLED_FAULT, make_engine


class _NeverCalled:
    """A model port that fails the test if the checker reaches it. `_model` is provenance, not a call."""

    _model = "never-called"

    def complete(self, *a, **k):
        raise AssertionError("the Level-2 checker was CALLED — this probe is invalid")

    def run(self, *a, **k):
        raise AssertionError("the Level-2 checker was CALLED — this probe is invalid")

    def __call__(self, *a, **k):
        raise AssertionError("the Level-2 checker was CALLED — this probe is invalid")


def _a_plan_with_a_hole_in_it(e):
    """A parent whose criterion no child covers — CHECK-1, the Syntactic level (§13.4)."""
    T.create_task(e, "par", {"description": "parent",
                             "criteria": [{"name": "g", "description": "G"}],
                             "accepted_risks": [{"item": UNMODELLED_FAULT.item,
                                                 "predictability": "EXTRAORDINARY"}]},
                  assignee="exec-1")
    T.create_task(e, "par.kid", {"description": "kid",
                                 "criteria": [{"name": "k", "description": "K"}]},
                  assignee="exec-1", parent_id="par")
    e.wait_idle()
    assert [h.get("check") for h in T.list_holes(e)["holes"]] == ["CHECK-1:coverage"], (
        "the probe never produced the structural hole it is about")


def test_a_gated_out_round_leaves_the_plan_unverified():
    e = make_engine(llm=_NeverCalled())
    e.start()
    _a_plan_with_a_hole_in_it(e)

    critique = review_decomposition(e, TaskId("par"))

    assert critique.gate_passed is False
    assert e.get_task(TaskId("par")).verified is False, (
        "a review that judged nothing certified the plan")
    e.stop()


def test_and_the_read_says_so_too():
    """The surface the docs tell an integrator to gate on is the one that was lying."""
    e = make_engine(llm=_NeverCalled())
    e.start()
    _a_plan_with_a_hole_in_it(e)

    review_decomposition(e, TaskId("par"))
    out = T.get_review(e, "par")

    assert out["verified"] is False, out
    assert out["execution_admitted"] is False, out
    e.stop()


def test_a_leaf_still_counts_as_answered():
    """The negative control: `gate_passed` is True where there is nothing for the checker to say.

    An installation with no instrument has no checker to run, and answers `gate_passed=True`
    deliberately — "no instrument, no verdict, never read as clean". That must not be turned into
    "unverified" by this rule, or a graph with no model configured acquires a plan gate nothing can
    ever open. (A leaf WITH an instrument does call it — atomicity is a question about the leaf — so
    the no-instrument case is the one this control can state without paying for a round.)
    """
    e = make_engine(llm=None)
    e.start()
    T.create_task(e, "leaf", {"description": "a leaf",
                              "criteria": [{"name": "c", "description": "C"}],
                              "accepted_risks": [{"item": UNMODELLED_FAULT.item,
                                                  "predictability": "EXTRAORDINARY"}]},
                  assignee="exec-1")
    e.wait_idle()

    critique = review_decomposition(e, TaskId("leaf"))

    assert critique.gate_passed is True
    assert e.get_task(TaskId("leaf")).verified is True
    e.stop()
