"""CHECK-7 had one composition function wired into it, and §10.1 says the Issuer declares which.

"For each cᵢ ∈ criteria(parent) the Issuer declares *how* the children's criteria secure cᵢ — a
composition function fᵢ", and CHECK-7 is `⋀criteria(tⱼ) ⊨ cᵢ` under it. The tier added the mapped
children's bounds up whatever fᵢ really was, so a parent budget of 200ms secured by a PARALLEL
fan-out — two independent requests, the slower one deciding — was reported as `children sum 200.0
does not entail < 200`: a correct plan flagged as FM-1.d. The mirror case is the expensive one: a
metric that really is additive but declared `max` used to pass on the sum by accident of the
numbers, and does not any more.

Both directions are pinned below, and with them the case that carries the product today — a
criterion that declares NOTHING. The check still runs (a Semantic tier that goes silent on every
undeclared criterion is a tier that never fires), and it now says in the answer that the sum was
its own assumption, so the reader can tell an arithmetic disagreement from a plan defect.
"""
from __future__ import annotations

from gfso.core.handlers.constraint import check_sufficiency
from gfso.core.types.primitives import Criteria, CriterionMapping, Spec, Task, TaskId

PARENT = "response_time < 200"


def _parent(composition=""):
    return Task(id=TaskId("p"),
                spec=Spec(description="a goal",
                          criteria=(Criteria(name=PARENT, description=PARENT,
                                             composition=composition),)),
                criterion_mappings=(CriterionMapping(PARENT, TaskId("a")),
                                    CriterionMapping(PARENT, TaskId("b"))))


def _child(tid, bound):
    return Task(id=TaskId(tid),
                spec=Spec(description="a child",
                          criteria=(Criteria(name=bound, description=bound),)))


def _children(bound_a, bound_b=None):
    return [_child("a", bound_a), _child("b", bound_b or bound_a)]


def test_a_declared_max_takes_the_slowest_child_not_the_total():
    fan_out = check_sufficiency(_parent("max"), _children("response_time < 100"))
    assert fan_out.passed and not fan_out.skipped, \
        f"two parallel children under 100ms cannot take 200ms between them: {fan_out.details}"

    # and the declaration keeps its teeth — the maximum itself has to clear the parent's bound
    too_slow = check_sufficiency(_parent("max"), _children("response_time < 100",
                                                           "response_time < 250"))
    assert not too_slow.passed, "the slowest child is over the parent's budget — that IS the breach"
    assert "max" in too_slow.details, \
        f"the reader is told an entailment failed but not under which fᵢ: {too_slow.details}"


def test_a_declared_max_is_strict_only_where_every_child_at_the_maximum_is():
    """§9.6's strictness clause, under the extremum: `m = max mⱼ ≤ max cⱼ`, and it is strictly
    below the parent's 200 only if every child that ATTAINS 200 is itself strict."""
    loose = check_sufficiency(_parent("max"), _children("response_time <= 200"))
    assert not loose.passed, "`<= 200` twice does not entail `< 200` under max either"

    strict = check_sufficiency(_parent("max"), _children("response_time < 200"))
    assert strict.passed, "`< 200` twice does entail it — a rule that rejects everything is not a rule"


def test_a_declared_sum_is_still_summed():
    """The additive budget is a declaration like any other, and unchanged by it."""
    assert check_sufficiency(_parent("sum"), _children("response_time < 100")).passed
    assert not check_sufficiency(_parent("sum"), _children("response_time < 150")).passed


def test_an_undeclared_composition_is_checked_but_names_its_assumption():
    breach = check_sufficiency(_parent(), _children("response_time < 150"))
    assert not breach.passed, "the tier must keep firing where nothing is declared — nothing is, yet"
    assert "ASSUMED" in breach.details and "composition" in breach.details, \
        f"a breach found under the check's own guess must say so: {breach.details}"

    held = check_sufficiency(_parent(), _children("response_time < 100"))
    assert held.passed
    assert "ASSUMED" in held.details, \
        f"a green resting on an assumed composition says so too: {held.details}"


def test_a_composition_this_tier_cannot_evaluate_is_reported_beyond_it():
    """A declaration the arithmetic cannot read is a fact about the CHECK's reach — never a licence
    to fall back on summation, which would be the check answering a question nobody asked it."""
    out = check_sufficiency(_parent("the union of the covered input classes"),
                            _children("response_time < 150"))
    assert out.passed and out.skipped, \
        f"nothing was machine-checked here, and a skip is what says so: {out.details}"
    assert "beyond" in out.details
