"""A refinement round re-authors the root's criteria. It must not quietly empty its risk register.

`auto_decompose` on an already-decomposed node runs REFINE rounds, and the root's contract is
rebuilt by hand in `decompose/build.py` — description, criteria, accepted_risks, scope, name. That
hand-built `Spec` omitted `risk_components`, which is the fourth POSITIONAL field, so every refine
defaulted it to `()`.

The data loss is the smaller half. CHECK-5 (STD-3, §9.4 — a risk node per grouped component)
quantifies over exactly that tuple, so emptying it does not make the check FAIL, it makes the check
VACUOUS: `∀ component K: ∃ a risk node` over an empty set is true. Probed end to end 2026-09-07:

    before a refine   CHECK-5  RED    "no children to cover 2 risk components"
    after  a refine   CHECK-5  GREEN  "no risk components defined"

with no component covered and no child added in between. This repository has now met that shape —
a rule that is true at zero X, and a step that produces the zero — often enough that it has a name:
`criteria: []` made the per-criterion floor vacuous, `required: []` made a schema check vacuous, and
here a refine manufactures the empty set the check reads.

The test calls `build.py`'s OWN construction (`refined_root_spec`) rather than `auto_decompose`,
which needs a model: what is under test is the contract a refine writes, and that is a pure object.
The construction has a name for this reason — the first version of this file built the `Spec`
itself, passing the field along, and would have passed with the defect fully in place.
"""
from __future__ import annotations

import pytest

import gfso.tools as T
from gfso.core.types import AgentId, CriterionMapping, Register, Spec, TaskId
from gfso.decompose.build import refined_root_spec
from tests.support import criterion, make_engine, REGISTER_ITEMS


def _root_with(components: tuple[str, ...]):
    e = make_engine(validate_signals=True, state_timeout=0)
    e.start()
    spec = Spec("a goal with grouped risks", _criteria(), REGISTER_ITEMS, components,
                name="root")
    e.assign_task(TaskId("root"), spec, AgentId("agent"))
    return e


def _criteria():
    return T._spec_from({"description": "g",
                         "criteria": [criterion("g", "G holds")]}).criteria


def _check5(e):
    return [c for c in e.get_checks(TaskId("root")) if c.check_name.startswith("CHECK-5")]


def _refine_spec(existing) -> Spec:
    """The contract a refine writes — from the PRODUCT's own owner, not rebuilt here.

    The first version of this file constructed the `Spec` itself, passing `risk_components` along,
    and so would have passed with the defect fully in place: it tested its own helper. That is the
    blindness this whole session kept meeting, so the construction was given a name in `build.py`
    (`refined_root_spec`) and the test calls it. The arguments are what a refine round supplies —
    the decomposer's re-authored criteria, its register, its scope, its name."""
    return refined_root_spec(existing.spec, "the request as re-stated",
                             existing.spec.criteria, existing.spec.accepted_risks,
                             existing.spec.scope, "derived name")


def test_a_refine_keeps_the_components_it_did_not_author() -> None:
    e = _root_with(("supply_chain", "infra_outage"))
    before = e.graph.get_task("root").spec.risk_components
    assert before == ("supply_chain", "infra_outage")

    e.revise(TaskId("root"), _refine_spec(e.graph.get_task("root")), AgentId("agent"))
    e.wait_idle()

    assert e.graph.get_task("root").spec.risk_components == before, (
        "the refine rebuilt the root's contract and dropped its risk components; the decomposer "
        "re-authors CRITERIA by design and does not author the register"
    )


def test_the_risk_check_does_not_go_green_across_a_refine() -> None:
    """The half that matters: an unmet CHECK-5 must not be satisfied by erasing its own subject.
    Canon v4.1 (§9.2, §9.4): CHECK-5 reads the SPLIT's register, its decomposer's, not the packet's — so the
    components are his, written after a clean admission (a flag, §12.10), and the refine must leave them standing.
    Canon v4.1 (§11.5, §12.10): the components ride the split's register into a CLEAN admission (a risk node per
    component); the RED is what a child cancelled after it leaves — a flag on the plan — and a refine must not clear it."""
    e = _root_with(("supply_chain", "infra_outage"))
    kids = [(TaskId(f"root.{r}"), T._spec_from({"description": f"mitigates {r}", "covers_risks": [r],
                                                "criteria": [criterion("k", "K holds")]}), AgentId("agent"))
            for r in ("supply_chain", "infra_outage")]
    e.decompose_task(TaskId("root"), kids, [CriterionMapping("g", k[0]) for k in kids],
                     register=Register(REGISTER_ITEMS, ("supply_chain", "infra_outage")))
    assert _check5(e)[0].passed                            # admitted whole: a risk node per component
    T.signal(e, "root.infra_outage", "CANCEL", "agent")    # the decomposer cancels one mitigation …
    T.signal(e, "root.infra_outage", "CONFIRM_CANCEL", "agent", in_flight="nothing started")
    e.wait_idle()
    before = _check5(e)
    assert before and not before[0].passed, before      # red: two components, a risk node for one

    e.revise(TaskId("root"), _refine_spec(e.graph.get_task("root")), AgentId("agent"))
    e.wait_idle()

    after = _check5(e)
    assert after and not after[0].passed, (
        f"CHECK-5 was RED before the refine ({before[0].details!r}) and is now {after[0].details!r}. "
        f"Nothing was covered and no child was added — the check went green because the refine "
        f"emptied the set it quantifies over. A rule that is vacuously true at zero is not a guard."
    )


@pytest.mark.parametrize("components", [(), ("one_root_cause",)])
def test_the_control_in_both_directions(components: tuple[str, ...]) -> None:
    """A root that genuinely has no components must still read as having none, and one that has
    them must not gain any: the repair carries the value across, it does not invent or force one."""
    e = _root_with(components)
    e.revise(TaskId("root"), _refine_spec(e.graph.get_task("root")), AgentId("agent"))
    e.wait_idle()
    assert e.graph.get_task("root").spec.risk_components == components
