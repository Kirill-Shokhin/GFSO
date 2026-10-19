"""A Level-2 round gated out at Level 0 must not mark the plan verified.

`review_decomposition` set `verified = True` unconditionally — three lines below a comment of its own
that promised the opposite for exactly this case ("A ROUND THAT DID NOT RUN THE CHECKER … The node is
still marked unverified below"). The prose was right and the code did the other thing, so a review
that checked nothing, because the structure was too broken to check, certified the plan.

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
from tests.support import criterion, make_engine, REGISTER


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
    """A parent whose criterion no child covers — CHECK-1, the Syntactic level (§9.5).

    Canon v4.1: a holed split is never admitted (§11.5), so the hole is made the one way it can exist —
    a revision of the parent's criteria after a clean admission, flagged on the plan (§12.10)."""
    T.create_task(e, "par", {"description": "parent", "criteria": [criterion("g", "G")]},
                  assignee="exec-1")
    T.decompose(e, "par", [{"task_id": "par.kid", "spec": {"description": "kid", "criteria": [criterion("k", "K")]},
                            "assignee": "exec-1", "covers": ["g"]}], accepted_risks=REGISTER)
    T.edit_criteria(e, "par", [criterion("g", "G"), criterion("h", "H")], agent="exec-1")
    e.wait_idle()
    assert [h.get("check") for h in T.list_holes(e)["holes"]] == ["CHECK-1:coverage"], (
        "the probe never produced the structural hole it is about")


def test_a_gated_out_round_leaves_the_plan_unverified():
    e = make_engine(llm=_NeverCalled())
    e.start()
    _a_plan_with_a_hole_in_it(e)

    critique = review_decomposition(e, TaskId("par"))

    assert critique.gate_passed is False
    assert e.graph.get_task(TaskId("par")).verified is False, (
        "a review that checked nothing certified the plan")
    e.stop()


def test_and_the_read_says_so_too():
    """The surface the docs tell an integrator to gate on is the one that was lying.

    Canon v4.1 pins the other half: a hole made by a revision after admission is a FLAG on the plan, never a hold
    on issued work (§12.10, §12.16 (ii)) — so the read says "unverified" while the admitted children keep working."""
    e = make_engine(llm=_NeverCalled())
    e.start()
    _a_plan_with_a_hole_in_it(e)

    review_decomposition(e, TaskId("par"))
    out = T.get_review(e, "par")

    assert out["verified"] is False, out
    assert out["execution_admitted"] is True, ("a flagged hole held the admitted children", out)
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
                              "criteria": [criterion("c", "C")],
                              "accepted_risks": REGISTER},
                  assignee="exec-1")
    e.wait_idle()

    critique = review_decomposition(e, TaskId("leaf"))

    assert critique.gate_passed is True
    assert e.graph.get_task(TaskId("leaf")).verified is True
    e.stop()
