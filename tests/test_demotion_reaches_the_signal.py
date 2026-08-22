"""What the record says is what everyone downstream acts on — and WHO pays for a hole in it.

The engine refuses to let an unobserved conjunct carry a pass. The original defect was that the
refusal stayed in the database: `validate_result` built its reply, its `next` directive and its log
line from the CLAIMED verdict before recording, so the caller went on holding PASS. Measured live
2026-08-19 on this repository's own graph — the record stored FAIL, the log said PASS, the
auto-validation signed PASS, and the node closed DONE. A guarantee that does not reach the signal is
not one.

The seam moved on 2026-08-20, because the first repair charged the hole to the wrong party. The
validator ENUMERATES the behaviours and WRITES the probes, so a behaviour it named and did not
observe is a defect of its own report — yet the node was sent to rework over it, on the executor's
bounded budget. Three independent runs that day retired nodes carrying correct work: 14 of 16
criteria `pass` and fully probed, killed by two `undecidable`, with the failed set drifting between
rounds so the loop could never converge.

So the two halves are now separate, and both are held here: a criterion contact genuinely REFUTED is
a fact about the work → FAIL and rework, reaching the signal exactly as before; a criterion merely
UNDER-OBSERVED is ⊥ about the instrument → it never enters `failed_criteria`, and when it is the
only thing standing between the node and a pass the report is refused as a non-verdict, leaving the
node in VALIDATING for the dispatcher's retry-and-park loop.
"""
from __future__ import annotations

import json

import gfso.tools as T
import gfso.tools_llm as TL
from tests.test_validate_result import _ValidatorLLM, _delivered_node, _eng, _fenced


def _claimed_pass_over_an_unobserved_behaviour() -> str:
    """A well-formed report — no self-contradiction — whose probe covers one behaviour of two."""
    return _fenced({
        "verdict": "PASS",
        "per_criterion": [
            {"criterion": "flush", "verdict": "pass", "evidence": "flush ok",
             "behaviours": ["nail head is flush"],
             "probe": [{"command": "pytest -q", "expect": "passed"}]},
            {"criterion": "holds", "verdict": "pass", "evidence": "looks solid",
             # two behaviours named, one probe given — the second was never observed
             "behaviours": ["it holds a picture", "it holds a 2kg frame"],
             "probe": [{"command": "pytest -q", "expect": "passed"}]}],
        "failed_criteria": []})


def _refuted_and_underprobed() -> str:
    """A report that genuinely REFUTES one criterion and under-observes another."""
    return _fenced({
        "verdict": "FAIL",
        "per_criterion": [
            {"criterion": "flush", "verdict": "fail", "evidence": "stands 2mm proud",
             "behaviours": ["nail head is flush"],
             "probe": [{"command": "pytest -q", "expect": "1 failed"}]},
            {"criterion": "holds", "verdict": "pass", "evidence": "looks solid",
             "behaviours": ["it holds a picture", "it holds a 2kg frame"],
             "probe": [{"command": "pytest -q", "expect": "passed"}]}],
        "failed_criteria": ["flush"]})


def test_a_claimed_pass_over_an_unobserved_behaviour_never_reaches_the_signal():
    """The guarantee, at its new seam.

    Under-observation is a hole in the VALIDATOR's own report — it names the behaviours and writes
    the probes — so it is ⊥ about the instrument, not a fact about the work. When nothing was
    actually refuted, the report decides nothing and is refused at the record: the claimed PASS
    still never reaches a signature, which is what this file exists to hold. What changed is who
    pays: the node stays in VALIDATING for the dispatcher's retry-and-park loop instead of being
    sent to rework over a criterion the executor cannot fix.
    """
    e = _eng()
    _delivered_node(e)
    out = TL.validate_result(e, "n1", _llm=_ValidatorLLM(_claimed_pass_over_an_unobserved_behaviour()))

    assert out["verdict"] is None, "an under-probed report decided something"
    assert "holds" in out["verdict_defects"] and "unobserved" in out["verdict_defects"]
    assert "not the executor" in out["verdict_defects"], "the report blames the wrong party"
    assert e.get_exec_verdict(T.TaskId("n1")) is None, "a non-verdict was stored as one"
    assert e.get_task(T.TaskId("n1")).state.name == "VALIDATING", "the node moved on ⊥"
    e.stop()


def test_a_real_refutation_still_demotes_and_still_reaches_the_signal():
    """The other half, unchanged: what contact actually refuted is a fact about the work, so the
    node goes to rework — and the under-observed criterion beside it is NOT added to the list the
    executor is told to fix."""
    e = _eng()
    _delivered_node(e)
    out = TL.validate_result(e, "n1", _llm=_ValidatorLLM(_refuted_and_underprobed()))

    assert out["verdict"] == "FAIL"
    assert out["failed_criteria"] == ["flush"], (
        f"the executor was sent to fix an unobserved criterion: {out['failed_criteria']}")
    assert "'FAIL'" in out["next"] and "flush" in out["next"] and "'PASS'" not in out["next"]
    assert e.get_exec_verdict(T.TaskId("n1"))["verdict"] == "FAIL"
    e.stop()


def test_an_honest_pass_is_still_a_pass():
    """The demotion must bite only where a behaviour went unobserved — not on every report."""
    e = _eng()
    _delivered_node(e)
    honest = _fenced({
        "verdict": "PASS",
        "per_criterion": [
            {"criterion": "flush", "verdict": "pass", "evidence": "flush ok",
             "behaviours": ["nail head is flush"],
             "probe": [{"command": "pytest -q", "expect": "passed"}]},
            {"criterion": "holds", "verdict": "pass", "evidence": "hung a 2kg frame on it",
             "behaviours": ["it holds a 2kg frame"],
             "probe": [{"command": "pytest -q", "expect": "passed"}]}],
        "failed_criteria": []})
    out = TL.validate_result(e, "n1", _llm=_ValidatorLLM(honest))
    assert out["verdict"] == "PASS" and "verdict_demoted_from" not in out
    assert "'PASS'" in out["next"]
    e.stop()
