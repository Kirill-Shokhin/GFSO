"""The check is anyone's; the signature that issues a verdict is the node's issuer's (§10.2). A validator on the roster
signed PASS and FAIL on every node whatever its issuer, so a person's node moved to DONE on a signature its issuer
never gave. Now an instrument's PASS or FAIL moves the node only where its issuer is a machine (`party_kind`: a
registered participant, the standing agent under AUTO or with no mode set); for a person's node the check is recorded
and the person signs it.

CONTROLS: give `signer_refusal` back its exemption for any roster validator and the first test goes red; refuse it
everywhere and the machine-issuer test goes red."""
from __future__ import annotations

import pytest

import gfso.tools as T
from gfso.core.types import TaskId
from tests.support import pinned
from tests.test_a_finding_binds_the_criterion_it_refuted import _seam

KID = TaskId("kid")


@pytest.fixture(autouse=True)
def _no_l2(monkeypatch):
    monkeypatch.setenv("GFSO_L2_GATE", "0")


def _checked(e):
    """`kid` (issued by `me`, executed by `exec-1`) delivered and checked by the roster's `val-1`, its PASS recorded."""
    e._graph.authorized_validators = {"val-1"}
    e.record_exec_verdict(KID, "PASS", [], "val-1", tools_used={"Bash": 1}, per_criterion=[
        {"criterion": n, "verdict": "pass", "evidence": "ran it", "probe": [
            {"command": p.command, "expect": p.expect, "behaviour": p.behaviour} for p in pinned(n)]}
        for n in ("conf", "other")])
    return e


def test_a_validator_does_not_sign_for_a_person_issuer_and_the_person_does():
    e = _checked(_seam())
    out = T.signal(e, "kid", "PASS", "val-1")
    e.wait_idle()
    assert e.graph.get_state(KID).name == "VALIDATING", out
    assert "issuer" in str(out.get("error") or out), out
    T.signal(e, "kid", "PASS", "me")
    e.wait_idle()
    assert e.graph.get_state(KID).name == "DONE", "the issuer's signature over the recorded check was refused"
    e.stop()


def test_a_validator_signs_for_a_machine_issuer():
    e = _checked(_seam())
    e.workforce.publish_roster({"me": "llm-executor", "val-1": "llm-validator"})
    T.signal(e, "kid", "PASS", "val-1")
    e.wait_idle()
    assert e.graph.get_state(KID).name == "DONE"
    e.stop()
