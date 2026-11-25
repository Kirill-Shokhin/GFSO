"""Who checks a node the person issues is one answer: `get_task`'s checker names the party the gate and the verdict read
(`Engine.appointee`, his appointment or its default) — a page reading the checker shows who really decides."""
from __future__ import annotations

import json

import pytest

import gfso.tools as T
import gfso.tools_llm as TL
from gfso.core.types import AgentId, Mode, TaskId
from gfso.delegate import ensure_dispatcher
from gfso.engine.validation import VALIDATOR_CHOSEN
from gfso.signin import PAGE
from tests.support import REGISTER, a_repository, criterion, instrument_passes, make_engine
from tests.test_a_named_party_checks_a_seam import _call

SEAM = "root.s"


@pytest.fixture(autouse=True)
def _home(tmp_path, monkeypatch):
    monkeypatch.setenv("GFSO_AGENTS_PATH", str(tmp_path / "agents.json"))
    monkeypatch.setenv("GFSO_L2_GATE", "0")
    monkeypatch.delenv("GFSO_VALIDATE_INTERNAL", raising=False)


def _his_seam(tmp_path, holder, validator):
    """His root, a seam he issues from his page to `holder` (`bob` is on no roster: a human; `eng` a registered agent)."""
    a_repository(tmp_path)
    e = make_engine(validate_signals=True, state_timeout=0)
    e.start()
    e.project_name = "p"
    if validator:
        assert not TL.register_agent(e, "p-val", "llm-validator", workdir=str(tmp_path)).get("refused")
        ensure_dispatcher(e).stop()
    e.workforce.publish_roster({**e.workforce.roster(), "eng": "llm-executor", "rev": "external"})
    _call(PAGE, "create_task", e, "root", {"description": "g", "criteria": [criterion("g")]}, assignee="user")
    covers = [c.name for c in e.graph.get_task(TaskId("root")).spec.criteria]
    _call(PAGE, "decompose", e, "root", [{"task_id": SEAM, "assignee": holder, "covers": covers,
                                          "spec": {"description": "d", "criteria": [criterion("d")]}}],
          accepted_risks=REGISTER)
    e.wait_idle()
    return e


@pytest.mark.parametrize("holder", ["bob", "eng"])
@pytest.mark.parametrize("validator", [True, False])
@pytest.mark.parametrize("appointed", [None, "self", "validator", "rev"])
def test_the_checker_said_is_the_one_the_gate_reads(tmp_path, holder, validator, appointed):
    e = _his_seam(tmp_path, holder, validator)
    if appointed is not None:
        out = _call(PAGE, "set_checker", e, SEAM, appointed, agent="user")
        assert out.get("checker") == appointed, out
    said = T.get_task(e, SEAM)["checker"]
    assert said == e.appointee(TaskId(SEAM)), (said, e.appointee(TaskId(SEAM)))



def _internal_kid(chosen, mode=True):
    """A part below the person's root, issued by its own holder (Del(kid) = Del(root): internal, §10.3), its check
    chosen by that issuer — through `set_checker` under a mode, or as the chosen-set setting written before the
    modes."""
    e = make_engine(validate_signals=True, state_timeout=0)
    e.start()
    e.project_name = "p"
    if mode:
        e.set_mode(Mode.SOLO, None, AgentId("user"))
    T.create_task(e, "root", {"description": "goal", "criteria": [criterion("g")]})
    T.decompose(e, "root", [{"task_id": "kid", "spec": {"description": "part", "criteria": [criterion("k")]},
                             "assignee": "user", "covers": ["g"]}], accepted_risks=REGISTER)
    e.wait_idle()
    if mode:
        e.set_checker(TaskId("kid"), chosen, AgentId("user"), "")
    else:
        e._storage.store_setting(VALIDATOR_CHOSEN, json.dumps(["kid"]))
    for tid in ("root", "kid"):
        T.signal(e, tid, "ACCEPT", "user")
    T.signal(e, "kid", "DELIVER", "user", result="ran `check k`: it printed OK", self_validation="PASS")
    e.wait_idle()
    return e


def test_appointee_internal_reads_the_validator_its_issuer_chose():
    """The gate waits for the validator its issuer chose at an internal node; the verdict of record reads the same
    checker — the executor's self-report stands beside it, never as «PASS, validator <executor>»."""
    e = _internal_kid("validator")
    kid = TaskId("kid")
    assert e.appointee(kid) == "validator" == T.get_task(e, "kid")["checker"]
    assert (e.pass_blocked_by(kid) or {}).get("kind") == "unobserved"
    assert e.get_exec_verdict(kid) is None, e.get_exec_verdict(kid)
    assert [r["validator"] for r in e.others_records(kid)] == ["user"]
    instrument_passes(e, kid, validator="p-val")
    assert T.signal(e, "kid", "PASS", "user").get("accepted"), e.pass_blocked_by(kid)
    e.stop()


def test_appointee_internal_self_leaves_an_observed_fail_binding():
    """«self» at an internal node names the default self-verification: its executor is its issuer, so an instrument's
    FAIL on the delivery still binds him (§12.16 (ii)) — never a signature over a refutation of his own work."""
    e = _internal_kid("self")
    kid = TaskId("kid")
    assert e.appointee(kid) is None and T.get_task(e, "kid")["checker"] == "self"
    e.record_exec_verdict(kid, "FAIL", ["k"], "p-val",
                          per_criterion=[{"criterion": "k", "verdict": "fail", "evidence": "ran it: it printed NO"}])
    assert (e.pass_blocked_by(kid) or {}).get("kind") == "observed_fail"
    assert not T.signal(e, "kid", "PASS", "user").get("accepted")
    e.stop()


def test_appointee_internal_self_lapses_where_the_instrument_became_owed(monkeypatch):
    """«self» chosen before the node became one the instrument is owed at: the gate's record decides, and the PASS goes
    through on it — never a node no record can close."""
    e = _internal_kid("self")
    kid = TaskId("kid")
    monkeypatch.setenv("GFSO_VALIDATE_INTERNAL", "1")
    assert e.appointee(kid) is None
    instrument_passes(e, kid, validator="p-val")
    assert T.signal(e, "kid", "PASS", "user").get("accepted"), e.pass_blocked_by(kid)
    e.stop()


def test_appointee_internal_a_choice_with_no_mode_reads_as_the_gate_does():
    """The chosen-set setting with no mode over the node: the gate does not wait (`observation_blocker` waits on a
    choice only under a mode), so its self-report closes it — as before the modes."""
    e = _internal_kid("validator", mode=False)
    kid = TaskId("kid")
    assert e.appointee(kid) is None and e.pass_blocked_by(kid) is None
    assert T.signal(e, "kid", "PASS", "user").get("accepted")
    e.stop()
