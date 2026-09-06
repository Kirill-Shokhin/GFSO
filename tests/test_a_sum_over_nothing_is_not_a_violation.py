"""CHECK-7 summed the children's numeric bounds — over no children — and called the total a breach.

An ordinary user's first plan carried the criterion *"Output contains only content-equivalence
classes of size >= 2"*. No child was mapped to it yet, so the sum ran over an empty set, produced
0.0, and the check reported `children sum 0.0 < parent bound 2.0`. They read it as the number 2 being
a budget their children had to add up to, reworded a perfectly good criterion to "two or more files",
and moved on (wave 25, 2026-09-05).

Nothing to sum is not a sum of zero. An uncovered criterion is CHECK-1's finding and CHECK-1 states
it correctly; CHECK-7 restating it in the vocabulary of arithmetic is a second owner giving the wrong
name to a real thing. The same ⊥ ≠ 0 rule this codebase applies to every metric it publishes, applied
to a check that publishes one.
"""
from __future__ import annotations

from gfso import tools as T
from gfso.core.types import TaskId
from tests.support import UNMODELLED_FAULT, make_engine

_BOUNDED = {"name": "group_size",
            "description": "output contains only content-equivalence classes of size >= 2"}


def _checks(e, tid="root"):
    return {c["check"]: c for c in T.get_checks(e, tid)}


def test_an_uncovered_bounded_criterion_is_not_reported_as_a_sum_breach():
    e = make_engine()
    e.start()
    T.create_task(e, "root", {"description": "goal", "criteria": [_BOUNDED],
                              "accepted_risks": [{"item": UNMODELLED_FAULT.item,
                                                  "predictability": "EXTRAORDINARY"}]},
                  assignee="agent")
    T.create_task(e, "root.kid", {"description": "a child that covers nothing yet",
                                  "criteria": [{"name": "k", "description": "K holds"}]},
                  assignee="agent", parent_id="root")
    e.wait_idle()

    seven = _checks(e).get("CHECK-7:sufficiency")

    assert seven is not None
    assert "children sum" not in str(seven.get("details") or ""), seven
    e.stop()


def test_and_the_hole_is_still_named_by_the_check_that_owns_it():
    """The negative control that matters: the uncovered criterion must not become invisible."""
    e = make_engine()
    e.start()
    T.create_task(e, "root", {"description": "goal", "criteria": [_BOUNDED],
                              "accepted_risks": [{"item": UNMODELLED_FAULT.item,
                                                  "predictability": "EXTRAORDINARY"}]},
                  assignee="agent")
    T.create_task(e, "root.kid", {"description": "a child that covers nothing yet",
                                  "criteria": [{"name": "k", "description": "K holds"}]},
                  assignee="agent", parent_id="root")
    e.wait_idle()

    holes = {h["check"]: h for h in T.list_holes(e)["holes"]}

    assert "CHECK-1:coverage" in holes, holes
    # It says "no criterion mappings declared" rather than naming the criterion, which is CHECK-1's
    # own wording and its own business — what matters here is that the hole is REPORTED by the check
    # that owns it, and not a second time in arithmetic by the one that does not.
    assert holes["CHECK-1:coverage"]["details"], holes
    e.stop()


def test_a_covered_bounded_criterion_is_still_summed():
    """The rule keeps its teeth where there is something to add up."""
    e = make_engine()
    e.start()
    T.create_task(e, "root", {"description": "goal",
                              "criteria": [{"name": "throughput",
                                            "description": "handles >= 100 requests per second"}],
                              "accepted_risks": [{"item": UNMODELLED_FAULT.item,
                                                  "predictability": "EXTRAORDINARY"}]},
                  assignee="agent")
    T.create_task(e, "root.kid", {"description": "the only child",
                                  "criteria": [{"name": "k",
                                                "description": "handles >= 10 requests per second"}]},
                  assignee="agent", parent_id="root")
    T.map_criterion(e, "root", "root.kid", "throughput")
    e.wait_idle()

    seven = _checks(e).get("CHECK-7:sufficiency")

    assert "children sum" in str(seven.get("details") or ""), (
        f"the arithmetic tier stopped measuring what it is for: {seven}")
    e.stop()
