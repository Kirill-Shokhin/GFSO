"""A decomposed node with no criteria of its own is a HOLE, not a covered node.

Lived: a two-hour run built five well-specified children under a root carrying zero criteria.
Coverage passed (nothing to cover), the Level-2 gate reported `semantic_covered: true` over
`criteria_judged: 0`, every child reached PASS — and the only thing that caught it was the
independent validator refusing to invent a criterion to judge the root by, after the work was done.
"""
from gfso.core.handlers.structural import check_coverage
from gfso.core.types import Spec, Criteria, AgentId, TaskId
from gfso.core.types.primitives import Task
from gfso.core.types.enums import State


def _task(tid: str, criteria=(), mappings=()) -> Task:
    return Task(id=TaskId(tid), spec=Spec("d", tuple(criteria)), state=State.EXECUTING,
                assignee=AgentId("agent"), criterion_mappings=tuple(mappings))


def test_children_without_parent_criteria_is_a_hole():
    parent, child = _task("root"), _task("root.a", [Criteria("c", "d")])
    res = check_coverage(parent, [child])
    assert not res.passed, "an empty contract over children reported as covered"
    assert "no criteria of its own" in res.details


def test_a_leaf_without_criteria_is_not_this_check_s_business():
    """Only the DECOMPOSED case is a hole here: a childless node is CHECK-1's skip, and an empty
    contract on it is caught where contracts are authored, not by coverage."""
    assert check_coverage(_task("root"), []).passed


def test_a_real_coverage_hole_still_reads_as_one():
    parent = _task("root", [Criteria("c1", "d")])
    assert not check_coverage(parent, [_task("root.a", [Criteria("x", "d")])]).passed
