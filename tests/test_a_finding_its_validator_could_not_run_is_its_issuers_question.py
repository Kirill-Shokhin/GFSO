"""A standing finding a validator honestly reports it could not run (`ran: false`) is asked of the node's issuer, whose
ruling lifts it or keeps it.

Series 2 REF 2 (2026-10-29): a regression line whose own setup failed in a later round observed nothing, so it meets no
demand (`invariants.probes_of`) and the PASS waits on it. The validator lifts that by no truthful move — a false `ran` is
the only other — and nothing asked anyone else: the node re-validated to VALIDATING's bound, and a re-issue out of
ESCALATED left the finding demanded as before (ENG_QUEUE, «v4.1: laying SHELVED»). A refusal only its sender could lift,
and only by misreporting, does not conform (§12.16 (ii)); the signature that decides a criterion is the issuer's (§10.2).

CONTROLS: make `Engine.unrun_findings` return [] and the question and ruling tests go red; drop the contact rule in
`issuer_turn` and the uncontacted test goes red.
"""
from __future__ import annotations

import json

import pytest

from gfso import issuer as I, tools as T
from gfso.core.types import TaskId
from tests.support import pinned
from tests.test_a_finding_binds_the_criterion_it_refuted import _seam
from tests.test_the_issuer_answers_a_dispute import _ContactLLM

KID, CMD, FID = TaskId("kid"), "sh x/cmp.sh x/ab.c", "conf#02d12020"
WHY = "its cd into the round's delivery copy failed: no such directory"


@pytest.fixture(autouse=True)
def _no_l2(monkeypatch):
    monkeypatch.setenv("GFSO_L2_GATE", "0")


def _ok(name, *more):
    return {"criterion": name, "verdict": "pass", "evidence": "ran it", "probe": [
        {"command": p.command, "expect": p.expect, "behaviour": p.behaviour} for p in pinned(name)] + list(more)}


def _refused(e, line):
    """The validator's PASS over `line` under `conf`, refused and kept as the dispatcher keeps it (`tools_llm`)."""
    report = [_ok("other"), _ok("conf", line)]
    with pytest.raises(ValueError, match=FID):
        e.record_exec_verdict(KID, "PASS", [], "val-1", per_criterion=report)
    e.record_rejected_report(KID, "refused", report)


def _standing():
    e = _seam()
    e._graph._storage.store_critique(TaskId("kid#regression-probes"), json.dumps({"conf": [
        {"id": FID, "behaviour": "b", "command": CMD, "as_run": CMD, "expect": "ok"}]}))
    return e


def _rule(e, tmp_path, move, ran=None):
    llm = _ContactLLM({"move": move, "justification": "ran it: cd into a removed round, on any delivery",
                       "retire_findings": [FID]}, ran=ran or {"Bash": 1})
    return I.issuer_turn(e, KID, "unrun", "me", _llm=llm, where=str(tmp_path))


def test_the_issuer_is_asked_and_a_retirement_admits_the_next_pass(tmp_path):
    e = _standing()
    _refused(e, {"id": FID, "command": CMD, "ran": False, "expect": WHY})
    assert (KID, "unrun") in I.open_questions(e)
    said = I.issuer_context(e, KID, "unrun")
    assert FID in said and WHY in said and "`retire`" in said
    assert _rule(e, tmp_path, "retire")["status"] == "applied"
    assert (KID, "unrun") not in I.open_questions(e) and FID not in str(e.regression_probes(KID))
    (row,) = e.findings_not_reproduced(KID)
    assert row["id"] == FID and row["by"] == "me" and WHY in row["why"]
    rec = e.record_exec_verdict(KID, "PASS", [], "val-1", per_criterion=[_ok("other"), _ok("conf")])
    assert str(rec["verdict"]).endswith("PASS")
    e.stop()


def test_a_kept_finding_stays_demanded_and_is_not_asked_again(tmp_path):
    e = _standing()
    _refused(e, {"id": FID, "command": CMD, "ran": False, "expect": WHY})
    assert _rule(e, tmp_path, "keep")["status"] == "applied"
    assert (KID, "unrun") not in I.open_questions(e)
    _refused(e, {"id": FID, "command": CMD, "ran": False, "expect": WHY})
    e.stop()


def test_a_retirement_that_ran_nothing_is_not_an_answer(tmp_path):
    e = _standing()
    _refused(e, {"id": FID, "command": CMD, "ran": False, "expect": WHY})
    assert _rule(e, tmp_path, "retire", ran={"Read": 1})["status"] == "uncontacted"
    assert (KID, "unrun") in I.open_questions(e)
    e.stop()


def test_a_line_not_marked_unrun_asks_nobody(tmp_path):
    e = _standing()
    _refused(e, {"id": "conf#other", "command": "./other", "expect": "x"})    # the finding left out, not said unrun
    assert (KID, "unrun") not in I.open_questions(e)
    e.stop()


def test_a_retirement_after_a_return_lands_and_each_ruling_reaches_the_feed():
    """The standing is the latest ruling's: retired, returned, not run again, the issuer's second retirement is a new
    ruling and takes the finding off — read as "ever returned", it answered `retire` and left it demanded. Each ruling,
    on no signal, is a line of the feed the person's page reads."""
    e, said = _standing(), []
    e.on_info(lambda source, message: said.append((source, message)))
    unrun = {"id": FID, "command": CMD, "ran": False, "expect": WHY}
    _refused(e, unrun)
    assert T.rule_unrun_finding(e, str(KID), [FID], "retire", "its cd fails on any delivery")["ruled"] == "retire"
    assert T.return_finding(e, str(KID), FID, "the person wants it run")["returned"] == FID
    assert FID in str(e.regression_probes(KID))
    _refused(e, unrun)
    assert T.rule_unrun_finding(e, str(KID), [FID], "retire", "still a removed round")["ruled"] == "retire"
    assert FID not in str(e.regression_probes(KID)) and not e.unrun_findings(KID)
    assert [r["kind"] for r in e.finding_rulings(KID, FID)] == ["not_reproduced", "returned", "not_reproduced"]
    lines = [m for s, m in said if s == "ruling"]
    assert len(lines) == 3 and all(str(KID) in m and FID in m for m in lines), said
    assert "returned" in lines[1] and "the person wants it run" in lines[1] and "still a removed round" in lines[2]
    e.stop()


def test_the_user_rules_it_by_a_verb_where_the_run_stopped_for_them():
    """At an AUTO root or in the user's own plan the stop names the user's move (§12.16 (ii)): the verb rules it."""
    e = _standing()
    _refused(e, {"id": FID, "command": CMD, "ran": False, "expect": WHY})
    assert "error" in T.rule_unrun_finding(e, str(KID), [FID], "drop", "x")
    assert "error" in T.rule_unrun_finding(e, str(KID), ["nope"], "retire", "the cd fails on any delivery")
    assert T.rule_unrun_finding(e, str(KID), [FID], "retire", "its cd fails on any delivery")["ruled"] == "retire"
    assert FID not in str(e.regression_probes(KID)) and (KID, "unrun") not in I.open_questions(e)
    e.stop()
