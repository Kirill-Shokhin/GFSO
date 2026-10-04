"""Every delivery is observed, whoever holds the node; the observation of an appointed observer binds.

SOLO used to observe nothing below the root: its own protocol text called a validator on an internal node
"pure overhead", the dispatcher observed only where a registered validator was bound, and an internal node
closed on its executor's own word — the bare arm with a log. §10.3 decides who SIGNS an internal node, not
whether anyone observes it, and an observer that is a separate instance costs no independence. So:
the instrument observes every delivery by default, a mode needs one staffed, a PASS under a mode stands on
the observer's record and not on the executor's self-check (the refusal is lifted by the issuer's own move,
`validate_result`, §12.16 (ii)), and where the node's issuer is its executor a divergence an appointed
observer recorded is the criterion's value — no later record turns it into a pass (Inv-2). At a seam
binding would leave the issuer no lift of his own (§12.16 (ii)), so there his own observation stands past it
as a logged disagreement — and only his: another instrument run does not undo a refutation (§10.2). The executor's self-report binds nothing, and neither does a
hand record by a party nobody appointed.
"""
from __future__ import annotations

import pytest

import gfso.tools as T
from gfso.core.types import AgentId, Mode, TaskId
from gfso.engine.verdicts import observations
from tests.support import criterion, instrument_passes, make_engine, parts_held, REGISTER
from tests.test_delegate import _agents, _dispatch_validate

_RISK = REGISTER


def _split(e, executor="agent"):
    """`root` over one part `kid` covering its criterion, the split admitted whole with its register (§11.5, §9.2)."""
    T.create_task(e, "root", {"description": "goal", "criteria": [criterion("g")]})
    T.decompose(e, "root", [{"task_id": "kid", "spec": {"description": "part", "criteria": [criterion("k")]},
                             "assignee": executor, "covers": ["g"]}], accepted_risks=_RISK)

@pytest.fixture(autouse=True)
def _observed(monkeypatch):
    monkeypatch.setenv("GFSO_L2_GATE", "0")
    monkeypatch.delenv("GFSO_VALIDATE_INTERNAL", raising=False)


def _solo_delivered_kid(mode=Mode.SOLO):
    e = make_engine(validate_signals=True, state_timeout=0)
    e.start()
    e.project_name = "p"
    if mode is not None:
        e.set_mode(mode, None, AgentId("agent"))
    _split(e)
    e.wait_idle()
    for s in ("ACCEPT",):
        T.signal(e, "root", s, "agent")
        T.signal(e, "kid", s, "agent")
    T.signal(e, "kid", "DELIVER", "agent", result="ran `check k`: it printed OK", self_validation="PASS")
    e.wait_idle()
    return e


def _fail(e, tid, validator="val-1", **kw):
    return e.record_exec_verdict(TaskId(tid), "FAIL", ["k"], validator, per_criterion=[
        {"criterion": "k", "verdict": "fail", "evidence": "ran check k: it printed NO",
         "divergences": ["printed NO where K holds"]}], **kw)


def test_under_a_mode_an_internal_node_does_not_close_on_its_executors_own_word():
    e = _solo_delivered_kid()
    r = T.signal(e, "kid", "PASS", "agent")
    assert not r.get("accepted") and "validate_result" in str(r), r
    assert e.graph.get_state(TaskId("kid")).name == "VALIDATING"
    e.stop()


def test_the_observers_record_opens_it():
    e = _solo_delivered_kid()
    instrument_passes(e, TaskId("kid"), validator="val-1")
    assert T.signal(e, "kid", "PASS", "agent")["state"] == "DONE"
    e.stop()


def test_with_no_mode_the_self_check_still_closes_an_internal_node():
    """No mode, no staffed instrument: the executor's word is the only record there is (§10.3)."""
    e = _solo_delivered_kid(mode=None)
    assert T.signal(e, "kid", "PASS", "agent")["state"] == "DONE"
    e.stop()


def test_an_observed_fail_is_not_overruled_by_a_later_instrument_pass():
    e = _solo_delivered_kid()
    _fail(e, "kid")
    with pytest.raises(ValueError) as ex:
        instrument_passes(e, TaskId("kid"), validator="val-2")
    assert "Inv-2" in str(ex.value)
    assert e.get_exec_verdict(TaskId("kid"))["verdict"] == "FAIL"
    e.stop()


def test_the_executors_own_fail_binds_nothing():
    e = _solo_delivered_kid()
    e.record_reviewer_verdict(TaskId("kid"), "FAIL", ["k"], reviewer="agent", observed={"k": "printed NO"})
    assert instrument_passes(e, TaskId("kid"), validator="val-1")["verdict"] == "PASS"
    e.stop()


def test_a_hand_fail_by_a_party_nobody_appointed_is_a_report_and_binds_nothing():
    e = _solo_delivered_kid()
    e.record_reviewer_verdict(TaskId("kid"), "FAIL", ["k"], reviewer="passer-by", observed={"k": "printed NO"})
    assert instrument_passes(e, TaskId("kid"), validator="val-1")["verdict"] == "PASS"
    e.stop()


def test_a_rework_ends_the_binding():
    e = _solo_delivered_kid()
    _fail(e, "kid")
    T.signal(e, "kid", "FAIL", "agent", failed_criteria=["k"])
    T.signal(e, "kid", "DELIVER", "agent", result="fixed: `check k` now prints OK", self_validation="PASS")
    e.wait_idle()
    assert instrument_passes(e, TaskId("kid"), validator="val-1")["verdict"] == "PASS"
    e.stop()


def test_a_revision_that_corrects_the_observers_procedure_lets_the_good_delivery_through():
    """Against a deterministic observer — a pinned probe — a re-delivery repairs nothing; the remedy is a
    revision correcting that probe (Inv-1). The re-delivery gate read only the criterion TEXT, so it
    refused that revision as "contact refuted the DECOMPOSITION" and a good delivery after a false
    observation had no way through."""
    e = make_engine(validate_signals=True, state_timeout=0)
    e.start()
    _split(e)
    e.wait_idle()
    T.signal(e, "root", "ACCEPT", "agent")
    T.signal(e, "kid", "ACCEPT", "agent")
    T.signal(e, "kid", "DELIVER", "agent", result="ran `check k`: it printed OK", self_validation="PASS")
    e.wait_idle()
    assert T.signal(e, "kid", "PASS", "agent")["state"] == "DONE"
    T.signal(e, "root", "DELIVER", "agent", result="aggregate: ran `check g`: it printed OK")
    e.record_exec_verdict(TaskId("root"), "FAIL", ["g"], "val-1", per_criterion=[
        {"criterion": "g", "verdict": "fail", "evidence": "the pinned probe quoted the input wrongly",
         "divergences": ["printed NO"], "probe": parts_held(e, "root", "g")}])
    T.signal(e, "root", "FAIL", "agent", failed_criteria=["g"])
    e.wait_idle()
    assert not T.signal(e, "root", "DELIVER", "agent", result="same aggregate").get("accepted")
    fixed = criterion("g")
    fixed["check"] = [dict(fixed["check"][0], command=fixed["check"][0]["command"] + " --quoted-right")]
    T.edit_criteria(e, "root", [fixed])
    T.signal(e, "root", "ACCEPT", "agent")
    r = T.signal(e, "root", "DELIVER", "agent", result="same aggregate, observed by the corrected probe")
    assert r.get("accepted") and r["state"] == "VALIDATING", r
    e.stop()


def test_a_hand_pass_by_a_party_nobody_appointed_does_not_open_the_solo_gate():
    e = _solo_delivered_kid()
    e.record_reviewer_verdict(TaskId("kid"), "PASS", [], reviewer="bob",
                              observed={"k": {"note": "ran `check k`, it printed OK", "ran": ["check k"]}})
    assert not T.signal(e, "kid", "PASS", "agent").get("accepted")
    e.stop()


def test_a_procedure_only_revision_still_waits_for_the_plan_re_check(monkeypatch):
    """The revision is the remedy against a wrong probe — and a probe loosened to what the result already
    prints is the cheapest false close, so it passes the same re-check an edited text does."""
    e = make_engine(validate_signals=True, state_timeout=0)
    e.start()
    _split(e)
    e.wait_idle()
    T.signal(e, "root", "ACCEPT", "agent")
    T.signal(e, "kid", "ACCEPT", "agent")
    T.signal(e, "kid", "DELIVER", "agent", result="ran `check k`: it printed OK", self_validation="PASS")
    e.wait_idle()
    T.signal(e, "kid", "PASS", "agent")
    T.signal(e, "root", "DELIVER", "agent", result="aggregate: ran `check g`: it printed OK")
    e.record_exec_verdict(TaskId("root"), "FAIL", ["g"], "val-1", per_criterion=[
        {"criterion": "g", "verdict": "fail", "evidence": "printed NO", "divergences": ["printed NO"]}])
    T.signal(e, "root", "FAIL", "agent", failed_criteria=["g"])
    loose = criterion("g")
    loose["check"] = [{"behaviour": loose["check"][0]["behaviour"], "command": "test -d . && echo ok", "expect": "ok"}]
    T.edit_criteria(e, "root", [loose])
    T.signal(e, "root", "ACCEPT", "agent")
    monkeypatch.setenv("GFSO_L2_GATE", "1")
    r = T.signal(e, "root", "DELIVER", "agent", result="same aggregate")
    assert not r.get("accepted") and "Level-2" in str(r), r
    e.stop()


def test_under_solo_the_instrument_observes_and_the_holder_signs(tmp_path, monkeypatch):
    """The issuer decides, the validator observes: under SOLO/SEMI, where the user's agent is a node's issuer,
    the dispatcher runs the instrument and records — and leaves the signature to the agent."""
    e = _solo_delivered_kid()
    agents = _agents(tmp_path, ("p-val", "llm-validator"))
    agents._agents["p-val"]["project"] = "p"
    started, _ = _dispatch_validate(e, agents, {"verdict": "PASS", "failed_criteria": [], "per_criterion": [
        {"criterion": "k", "verdict": "pass", "evidence": "ran `check k`: OK", "behaviours": ["the criterion holds"],
         "probe": [{"command": "check k", "expect": "it holds"}]}]})
    assert "validate:kid" in started
    assert e.graph.get_state(TaskId("kid")).name == "VALIDATING"            # observed, not signed
    assert e.get_exec_verdict(TaskId("kid"))["verdict"] == "PASS"
    assert T.signal(e, "kid", "PASS", "agent")["state"] == "DONE"      # the issuer's own decision
    e.stop()


def test_a_later_hand_fail_does_not_launder_the_instruments_fail_away():
    """Every observation of the delivery is read, not the latest record: instrument FAIL → a passer-by's
    FAIL → a PASS used to land, because the guard compared against the record just before it."""
    e = _solo_delivered_kid()
    _fail(e, "kid")
    e.record_reviewer_verdict(TaskId("kid"), "FAIL", ["k"], reviewer="passer-by", observed={"k": "printed NO"})
    with pytest.raises(ValueError, match="Inv-2"):
        instrument_passes(e, TaskId("kid"), validator="val-2")
    assert not T.signal(e, "kid", "PASS", "agent").get("accepted")
    e.stop()


def test_under_solo_the_root_does_not_close_on_a_hand_pass_nobody_appointed():
    e = _solo_delivered_kid()
    instrument_passes(e, TaskId("kid"), validator="val-1")
    T.signal(e, "kid", "PASS", "agent")
    T.signal(e, "root", "DELIVER", "agent", result="aggregate: ran `check g`: it printed OK")
    e.record_reviewer_verdict(TaskId("root"), "PASS", [], reviewer="bob",
                              observed={"g": {"note": "ran `check g`, it printed OK", "ran": ["check g", "check k"]}})
    assert not T.signal(e, "root", "PASS", "agent").get("accepted")
    step = next((s for s in e.next_steps()["steps"] if s["task_id"] == "root"), None)
    assert step and "validate_result" in step["directive"], step        # the surface says what the gate says
    instrument_passes(e, TaskId("root"), validator="val-1")
    assert T.signal(e, "root", "PASS", "agent")["state"] == "DONE"
    e.stop()


def test_where_the_system_signs_a_binding_fail_is_signed_not_left_standing(tmp_path):
    """The issuer's own hand FAIL binds (he is not the executor); the replay of standing verdicts skips hand
    records, so where the system makes the issuer's moves the node sat in VALIDATING with a validation paid
    every round and no move of the system's (reproduced under AUTO with the system issuer's name)."""
    e = make_engine(validate_signals=True, state_timeout=0)
    e.start()
    e.project_name = "p"
    agents = _agents(tmp_path, ("exec-1", "llm-executor"), ("exec-2", "llm-executor"), ("p-val", "llm-validator"))
    agents._agents["p-val"]["project"] = "p"
    _split(e, "exec-2")
    e.wait_idle()
    T.signal(e, "kid", "ACCEPT", "exec-2")
    T.signal(e, "kid", "DELIVER", "exec-2", result="ran `check k`: it printed OK", self_validation="PASS")
    e.wait_idle()
    e.record_reviewer_verdict(TaskId("kid"), "FAIL", ["k"], reviewer="agent", observed={"k": "printed NO"})
    started, _ = _dispatch_validate(e, agents, {"verdict": "PASS", "failed_criteria": [], "per_criterion": []})
    assert "fail:kid" in started and not any(s == "validate:kid" for s in started), started
    assert e.graph.get_state(TaskId("kid")).name == "REWORKING"
    e.stop()


def _seam_delivered_kid():
    """A child its issuer does not execute: a seam (§10.3), the issuer `agent`, the executor `exec-1`."""
    e = make_engine(validate_signals=True, state_timeout=0)
    e.start()
    _split(e, "exec-1")
    e.wait_idle()
    T.signal(e, "root", "ACCEPT", "agent")
    T.signal(e, "kid", "ACCEPT", "exec-1")
    T.signal(e, "kid", "DELIVER", "exec-1", result="ran `check k`: it printed OK", self_validation="PASS")
    e.wait_idle()
    return e


def test_at_a_seam_the_issuer_signs_on_his_own_observation_and_the_instruments_divergence_stays_on_record():
    """§16.13: whether a refutation binds the signature is the implementation's, within §12.16 (ii). At a seam
    binding would leave the issuer no lift of his own — a revision needs the executor's re-consent — so the
    signature reads the latest appointed record; an earlier divergence is a logged disagreement."""
    e = _seam_delivered_kid()
    _fail(e, "kid")
    r = T.signal(e, "kid", "PASS", "agent")
    assert not r.get("accepted"), r                         # his PASS must read a check, and the last one fails
    T.record_verdict(e, "kid", "PASS", reviewer="agent",
                     observed={"k": {"note": "ran check k myself: it printed OK", "ran": ["check k"]}})
    assert T.signal(e, "kid", "PASS", "agent")["state"] == "DONE"
    assert any(str(o.get("verdict")) == "FAIL" for o in observations(e._graph._storage, TaskId("kid")))
    e.stop()


def test_at_a_seam_another_instrument_run_does_not_undo_a_refutation():
    """Only the issuer's own observation is the lift §12.16 (ii) requires; re-running the validator until it
    passes is not one (the `floor_17` false close)."""
    e = _seam_delivered_kid()
    _fail(e, "kid")
    with pytest.raises(ValueError, match="Inv-2"):
        instrument_passes(e, TaskId("kid"), validator="val-1")
    assert not T.signal(e, "kid", "PASS", "agent").get("accepted")
    e.stop()


def test_at_a_seam_an_instrument_pass_does_not_undo_the_issuer_s_own_fail():
    e = _seam_delivered_kid()
    e.record_reviewer_verdict(TaskId("kid"), "FAIL", ["k"], reviewer="agent",
                              observed={"k": "ran `check k` myself: it printed NO"})
    with pytest.raises(ValueError, match="Inv-2"):
        instrument_passes(e, TaskId("kid"), validator="val-1")
    e.stop()


def test_an_instrument_run_recorded_under_the_issuer_s_name_is_still_an_instrument_run():
    """`validate_result(validator=<the issuer's id>)` records the instrument under his name; it is not his
    observation and does not undo a refutation — the re-roll the seam rule exists to exclude."""
    e = _seam_delivered_kid()
    _fail(e, "kid")
    with pytest.raises(ValueError, match="Inv-2"):
        instrument_passes(e, TaskId("kid"), validator="agent")
    e.stop()
