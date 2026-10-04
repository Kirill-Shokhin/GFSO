"""CHECK-3 answered `met` on every decomposition the product builds, because no child could have one.

The engine's `decompose_task` takes a child as `(id, spec, assignee)` OR `(id, spec, assignee,
deadline)`, and its own docstring warns what the short form costs. The `decompose` verb always built
the short one -- so the field never reached the graph, `check_deadlines` looked at an empty set of
child deadlines, and reported met with the details "no child deadlines". Vacuously true on every
product-built plan, which is not a check (audited 2026-09-05, F3).

The absence of deadlines stays silent -- a plan that declares none is not thereby defective
(`formal/README.md` #6). What changed is that a plan which DECLARES one is no longer stripped of it
on the way in.
"""
from __future__ import annotations

from datetime import datetime

import pytest

import gfso.tools as T
from tests.support import criterion, make_engine, REGISTER
from gfso.adapters.storage.sqlite import SqliteStorage
from gfso.api.models import CheckResultOut
from gfso.core.types import CheckResult

_RISK = REGISTER


@pytest.fixture(autouse=True)
def _no_plan_gate(monkeypatch):
    monkeypatch.setenv("GFSO_L2_GATE", "0")


def _decomposed(kid_deadline, parent_deadline="2099-10-01"):
    e = make_engine()
    e.start()
    T.create_task(e, "root", {"description": "goal",
                              "criteria": [criterion("a", "A")],
                              "accepted_risks": _RISK}, assignee="me", deadline=parent_deadline)
    kid = {"task_id": "root.x",
           "spec": {"description": "x", "criteria": [criterion("x1", "X")]},
           "assignee": "me", "covers": ["a"]}
    if kid_deadline:
        kid["deadline"] = kid_deadline
    T.decompose(e, "root", [kid], accepted_risks=REGISTER)
    e.wait_idle()
    # BY THE RULE, NOT BY THE ROW IT USED TO RIDE IN. §4.5(6) is a canon RULE the canon gives no
    # CHECK for, so it reports under its own name and does not gate (F4, same audit).
    check = [c for c in T.get_checks(e, "root") if "4.5(6)" in c["check"]][0]
    out = (e.graph.get_task("root.x").deadline, check["verdict"], check["details"])
    e.stop()
    return out


def test_a_child_keeps_the_deadline_it_was_given():
    deadline, _, _ = _decomposed("2099-09-10")
    assert deadline == datetime.fromisoformat("2099-09-10"), (
        "the verb dropped the field, so CHECK-3's subject could not exist")


def test_the_vertical_rule_gates_the_admission_that_sets_the_deadline():
    """A child that may finish after its parent cannot compose into it (§4.5(6)), and v4.1 §11.5 gates item (6) over
    the deadlines the admission sets while the parent's is ahead: the decomposer gives one inside it."""
    with pytest.raises(ValueError, match=r"item \(6\)"):
        _decomposed("2099-12-01")


def test_a_child_inside_its_parent_still_passes():
    """The control: the check must be answering the question, not refusing every plan with a date."""
    assert _decomposed("2099-09-10")[1] == "met"


def test_a_packet_the_issuer_left_undated_still_carries_a_bound():
    """v4.1 §12.4: every entry into OFFERED carries a live deadline, and the canon asks the PACKET
    to carry one rather than the issuer to type one — the engine writes its default, marked as
    supplied. The default is written INSIDE the parent's own deadline, so §4.5(6) is satisfied by
    construction rather than by absence — where the rule used to have no subject at all."""
    deadline, verdict, _ = _decomposed(None)
    assert deadline is not None and deadline < datetime.fromisoformat("2099-10-01")
    assert verdict == "met"


def test_a_datetime_passes_through_unparsed():
    """The engine's own callers hand a `datetime`; only the doors hand a string. One owner parses,
    and it must not choke on the value that needs no parsing -- `str >= datetime` RAISED inside the
    structural gate when the string went through unparsed, which is a crash where a check belongs."""
    assert _decomposed(datetime.fromisoformat("2099-09-10"))[1] == "met"


def test_a_green_over_nothing_says_so():
    """A check whose SUBJECT is empty passes vacuously, and that is not the same green.

    A leaf's panel showed four ticks — `D acyclic; no dependency edges`, `no dependency edges`,
    `no risk components defined`, `no child deadlines to place` — each a conjunction over ∅, drawn
    exactly like a check that ordered real edges (looked at the page, 2026-09-06). The engine knew
    which was which; nothing carried it. `met_vacuously` is the word at both doors, and the page
    draws `∅` rather than `✓`.
    """
    over_nothing = CheckResultOut.of(
        CheckResult("CHECK-3:deadlines", True, "no dependency edges", vacuous=True))
    over_something = CheckResultOut.of(
        CheckResult("CHECK-3:deadlines", True, "a < b", vacuous=False))

    assert over_nothing.verdict == "met_vacuously" and over_nothing.vacuous is True
    assert over_nothing.passed is True, "it IS true — what is added is what it is true OF"
    assert over_something.verdict == "met" and over_something.vacuous is False


def test_the_vacuity_survives_the_database(tmp_path):
    """A distinction true in memory and false after a round trip is no distinction at all.

    The sqlite adapter wrote five of `CheckResult`'s six fields, so `vacuous` was dropped on the way
    in and every green came back looking earned — the "one field, two doors" defect in miniature,
    and the exact shape that made `false_fail_share` vanish over HTTP a week earlier.
    """
    st = SqliteStorage(str(tmp_path / "g.db"))
    st.store_check_results("t", [CheckResult("CHECK-3:deadlines", True, "no dependency edges",
                                             vacuous=True),
                                 CheckResult("CHECK-1:coverage", True, "c1 <- kid")])

    back = {c.check_name: c for c in st.get_check_results("t")}

    assert back["CHECK-3:deadlines"].vacuous is True
    assert back["CHECK-1:coverage"].vacuous is False
