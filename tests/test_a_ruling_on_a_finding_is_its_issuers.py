"""A ruling on a node's findings — retiring or keeping one its validator could not run (`rule_unrun_finding`), giving
back one a later validator did not reproduce (`return_finding`) — moves what the node's PASS waits on, so it is the
issuer's signature (§10.2), not any caller's: both verbs took `agent` as sent, so the node's own executor could retire
the finding standing against its delivery. At a door they are now signed by the node's issuer, as every other issuer
move is (`moves.DOOR_KEYS`); where the criteria are the user's (an AUTO root, a plan he handed in) the ruling stays his.

CONTROLS: drop the two verbs from `DOOR_KEYS` and the executor's rulings are taken again."""
from __future__ import annotations

from gfso import tools_llm as TL
from gfso.core.types import Mode
from tests.test_the_mode_decides_who_holds_what import _engine, _goal
from tests.test_a_finding_its_validator_could_not_run_is_its_issuers_question import (CMD, FID, KID, WHY, _no_l2,  # noqa: F401
                                                                                      _refused, _standing)


def _unrun():
    e = _standing()
    _refused(e, {"id": FID, "command": CMD, "ran": False, "expect": WHY})
    return e


def test_the_executor_cannot_retire_the_finding_against_its_own_delivery():
    e = _unrun()
    out = TL.TOOLS["rule_unrun_finding"](e, str(KID), [FID], "retire", "it never runs", agent="exec-1")
    assert TL.is_refusal(out) and "issuer" in out["error"], out
    assert FID in str(e.regression_probes(KID)), "a refused ruling retired the finding"
    e.stop()


def test_under_auto_the_user_rules_on_his_goal_and_not_on_the_systems_plan():
    """The AUTO root's criteria are the user's goal, so the ruling the run stops for there is his; a part of the plan the
    system wrote is ruled by the system's issuer, and the door refuses the customer that move."""
    e = _engine(Mode.AUTO)
    _goal(e)
    assert TL.TOOLS["return_finding"](e, "root", "g#none", "the goal asks for it") == {
        "error": "no finding g#none on root stands as not reproduced"}
    out = TL.TOOLS["return_finding"](e, "kid", "k#none", "the goal asks for it")
    assert TL.is_refusal(out) and "AUTO" in out["error"], out
    e.stop()


def test_the_issuer_rules_and_only_the_issuer_gives_it_back():
    e = _unrun()
    assert TL.TOOLS["rule_unrun_finding"](e, str(KID), [FID], "retire", "its cd fails on any delivery",
                                          agent="me")["ruled"] == "retire"
    out = TL.TOOLS["return_finding"](e, str(KID), FID, "the goal asks for it", agent="exec-1")
    assert TL.is_refusal(out) and "issuer" in out["error"], out
    assert FID not in str(e.regression_probes(KID)), "a refused return demanded the finding again"
    assert TL.TOOLS["return_finding"](e, str(KID), FID, "the goal asks for it", agent="me")["returned"] == FID
    e.stop()
