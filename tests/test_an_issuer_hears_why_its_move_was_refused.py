"""A machine issuer's next turn hears why its last move on the node's contract was refused.

GB_sql_database_tn8rdk788 `value` (haiku 4.5, 2026-10-21): the issuer's acceptance of a dispute rewrote a probe the
admission refuses (a shared `/tmp` scratch, `cd` into an absolute directory); only the retry inside one settle saw the
reason, every later sweep asked blind, and the same refusal came back 33 times over 180 minutes while each turn fell
back to rejecting the dispute. The reason is read off the log; a contract installed since starts clean."""
import pytest

import gfso.tools as T
from gfso.core.types import AgentId, Criteria, Probe, Signal, SignalData, Spec, TaskId
from gfso.issuer import refused_on_this_version
from tests.support import DENIAL_ENTRY, UNMODELLED_FAULT, criterion, make_engine

_RISK = [{"item": UNMODELLED_FAULT.item, "predictability": "EXTRAORDINARY", "justification": "no precedent",
          "invalidation_condition": "one occurs", "p": 0.01, "impact": "the run stops and is resumed"}, DENIAL_ENTRY]
_LEAVES = Probe.of({"behaviour": "compiles alone", "command": "cp v.c /tmp/t.c && cd /tmp && gcc -c t.c && echo ok",
                    "expect": "ok"})


@pytest.fixture(autouse=True)
def _no_l2(monkeypatch):
    monkeypatch.setenv("GFSO_L2_GATE", "0")


@pytest.fixture
def disputed():
    e = make_engine()
    e.start()
    T.create_task(e, "root", {"description": "goal", "criteria": [criterion("conf")], "accepted_risks": _RISK},
                  assignee="me")
    e.wait_idle()
    T.signal(e, "root", "ACCEPT", "me")
    T.signal(e, "root", "DELIVER", "me", result="built it")
    e.wait_idle()
    T.signal(e, "root", "FAIL", "me", failed_criteria=["conf"])
    T.signal(e, "root", "CHALLENGE", "me", reason="the contract asks two things that cannot both hold")
    yield e
    e.stop()


def _accept(e, check):
    """The acceptance as the log records it (a refused one included)."""
    t = e.graph.get_task("root")
    e.send_signal_sync(SignalData(signal=Signal.ACCEPT_CHALLENGE, task_id=TaskId("root"), source=AgentId("me"),
                                  new_spec=Spec(t.spec.description, (Criteria("conf", "c", check=check),),
                                                accepted_risks=t.spec.accepted_risks)))
    return [x for x in e.audit_log(TaskId("root")) if x.signal == Signal.ACCEPT_CHALLENGE][-1]


def test_the_refusal_reaches_the_next_turn_across_a_rejected_dispute(disputed):
    e = disputed
    assert refused_on_this_version(e, TaskId("root"), "me") == ""
    entry = _accept(e, (_LEAVES,))
    assert entry is not None and entry.rejected
    said = refused_on_this_version(e, TaskId("root"), "me")
    assert said.startswith("An earlier ACCEPT_CHALLENGE of yours on this contract was refused:") and entry.error in said
    # the issuer falls back to rejecting, the executor disputes again: the same contract, the reason still owed
    T.signal(e, "root", "REJECT_CHALLENGE", "me", justification="the contract stands")
    T.signal(e, "root", "CHALLENGE", "me", reason="the contract asks two things that cannot both hold")
    assert entry.error in refused_on_this_version(e, TaskId("root"), "me")
    assert refused_on_this_version(e, TaskId("root"), "someone-else") == ""


def test_a_contract_installed_since_starts_clean(disputed):
    e = disputed
    assert _accept(e, (_LEAVES,)).rejected
    ok = Probe.of({"behaviour": "compiles alone", "command": "T=$(mktemp -d) && cp v.c $T/t.c && echo ok",
                   "expect": "ok"})
    landed = _accept(e, (ok,))
    assert landed is not None and not landed.rejected, landed and landed.error
    assert refused_on_this_version(e, TaskId("root"), "me") == ""
