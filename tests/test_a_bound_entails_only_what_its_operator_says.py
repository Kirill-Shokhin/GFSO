"""CHECK-7 and CHECK-8 read the bound's NUMBER and dropped its operator — in both directions.

§13.4 annotates its own worked example with the exact trap: `backend < 100 ∧ frontend < 100 ⟹ sum
< 200 ✓` holds *"with both child bounds STRICT; the non-strict test alone would not entail the
strict parent criterion"*. The tier summed the values and never looked at `<` versus `<=`, so two
children bounded `<= 100` under a parent bounded `< 200` came back as `verified 1 numeric bound(s)`
— a positive green on the Semantic level for an entailment that does not hold, which is the one
outcome this tier exists to prevent (FM-1.d passing CHECK-7).

The same omission ran the other way in CHECK-8: `x <= 5` and `x >= 5` are jointly satisfied by
x = 5, and the consistency check called them an FM-2 contradiction — a check inventing the class of
defect it is there to find, and misquoting the criteria while doing it ("requires <5.0" where the
plan said `<= 5`).

What the children entail is `m < Σc` when at least one of them is strict and `m ≤ Σc` when none is;
at Σc = P those two differ exactly on a strict parent bound. Each case below is paired with the
control that must come out the other way — a check that only ever says "fine" is not a check.
"""
from __future__ import annotations

from gfso.core.handlers.constraint import check_consistency, check_sufficiency
from gfso.core.types.primitives import Criteria, CriterionMapping, Spec, Task, TaskId

PARENT_BOUND = "response_time < 200"


def _task(tid, descriptions, mappings=()):
    return Task(id=TaskId(tid),
                spec=Spec(description="a goal",
                          criteria=tuple(Criteria(name=d, description=d) for d in descriptions)),
                criterion_mappings=tuple(mappings))


def _parent():
    return _task("p", [PARENT_BOUND],
                 [CriterionMapping(criterion_name=PARENT_BOUND, child_id=TaskId("a")),
                  CriterionMapping(criterion_name=PARENT_BOUND, child_id=TaskId("b"))])


def _children(bound):
    return [_task("a", [bound]), _task("b", [bound])]


def test_two_non_strict_children_do_not_entail_a_strict_parent_bound():
    loose = check_sufficiency(_parent(), _children("response_time <= 100"))
    assert not loose.passed, \
        "100 + 100 under `< 200` holds only if a child bound is strict — §13.4 says so in the " \
        "line that states the example"
    assert "strict" in loose.details, \
        "the reader is told a sum was rejected but not that the operators are why"

    canon = check_sufficiency(_parent(), _children("response_time < 100"))
    assert canon.passed and not canon.skipped, \
        "the canon's own worked example must still pass — a rule that rejects everything is not " \
        "a rule (§13.4)"

    over = check_sufficiency(_parent(), _children("response_time < 150"))
    assert not over.passed, "150 + 150 > 200 is the arithmetic breach CHECK-7 already caught"


def test_bounds_that_meet_at_a_point_both_admit_are_not_a_contradiction():
    touching = check_consistency([_task("a", ["queue_depth <= 5"]), _task("b", ["queue_depth >= 5"])])
    assert touching.passed, \
        "x = 5 satisfies both, so this is no FM-2: a check that invents contradictions costs the " \
        "same plan repair a real one does"

    disjoint = check_consistency([_task("a", ["queue_depth < 5"]), _task("b", ["queue_depth > 5"])])
    assert not disjoint.passed, "the real contradiction must still be found"
    assert "<5.0" in disjoint.details and ">5.0" in disjoint.details, \
        "the message quotes the operators the plan actually carries"
