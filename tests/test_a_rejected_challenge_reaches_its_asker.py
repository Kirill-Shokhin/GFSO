"""A rejected challenge reaches the one who asked — and the issuer who answered it sees his answers.

The executor of root.parse_stmt (GB_sql_database_tn9nii608) raised one challenge 40 times, one every 24 s: its rework
packet said "dispute a finding; only your issuer's ruling retires it" and never carried the ruling, so each round
opened "this is the same rework request as before" — while the issuer's answer named the fix inside its own node.
Nothing refuses asking again (§11.3: a rejected CHALLENGE forces nothing; Φ2 bounds the dispute); the answer is shown."""
import pytest

import gfso.packets as P
import gfso.tools as T
from gfso.core.types import AgentId, Criteria, Spec, TaskId
from gfso.issuer import issuer_context
from gfso.packets import _executor_packet
from tests.support import REGISTER, REGISTER_ITEMS, criterion, make_engine, pinned

W = "worker"
ASKED = "finding F lies outside criterion c as written"
ANSWER = "c says missing parts are ERR; add the guard in your own file"


@pytest.fixture(autouse=True)
def _no_l2(monkeypatch):
    monkeypatch.setenv("GFSO_L2_GATE", "0")


@pytest.fixture
def e():
    eng = make_engine()
    eng.start()
    T.create_task(eng, "root", {"description": "a goal", "criteria": [criterion("c", "C")], "accepted_risks": REGISTER},
                  assignee=W)
    eng.wait_idle()
    T.signal(eng, "root", "ACCEPT", W)
    T.signal(eng, "root", "DELIVER", W, result="built it")
    eng.wait_idle()
    T.signal(eng, "root", "FAIL", W, failed_criteria=["c"])
    eng.wait_idle()
    yield eng
    eng.stop()


def _rejected(e, times=1):
    for _ in range(times):
        assert T.signal(e, "root", "CHALLENGE", W, reason=ASKED)["accepted"]
        assert T.signal(e, "root", "REJECT_CHALLENGE", W, justification=ANSWER)["accepted"]
    e.wait_idle()
    return e.graph.get_task(TaskId("root"))


def test_the_executor_reads_the_rejection_of_its_challenge(e):
    packet = _executor_packet(e, _rejected(e), None)
    assert "REJECTED — each is answered" in packet
    assert ASKED in packet and ANSWER in packet


def test_a_repeated_exchange_is_one_line(e):
    packet = _executor_packet(e, _rejected(e, 3), None)
    assert packet.count(ANSWER) == 1 and "(3 times)" in packet


def test_a_long_ruling_reaches_its_asker_whole(e):
    """The ruling binds, so all of it is shown: cut at 1500 characters, a 2510-character ruling reached its executor as
    «unless it is a reserved wo…» — the reserved set it named was the part that decided the rework, and the executor
    guessed it and failed again (GB_sql_database_tng5od544 root.parse_stmt, 05:18; its own tech report named the cut)."""
    long_answer = "a keyword is an identifier wherever a name is expected " * 40 + "THE RESERVED SET: SELECT, FROM"
    assert T.signal(e, "root", "CHALLENGE", W, reason=ASKED * 30)["accepted"]
    assert T.signal(e, "root", "REJECT_CHALLENGE", W, justification=long_answer)["accepted"]
    e.wait_idle()
    assert long_answer in _executor_packet(e, e.graph.get_task(TaskId("root")), None)
    assert T.signal(e, "root", "CHALLENGE", W, reason="a new observation")["accepted"]
    ctx = issuer_context(e, TaskId("root"), "dispute")
    assert long_answer in ctx and ASKED * 30 in ctx


def test_the_issuer_of_a_dispute_sees_his_earlier_answers(e):
    _rejected(e)
    assert T.signal(e, "root", "CHALLENGE", W, reason="a new observation: the probe printed X")["accepted"]
    ctx = issuer_context(e, TaskId("root"), "dispute")
    assert "you already REJECTED" in ctx and ANSWER in ctx


def test_a_new_version_starts_without_them(e):
    _rejected(e)
    e._revise(TaskId("root"), Spec("a goal, revised", (Criteria("c", "C2", check=pinned("c")),),
                                   accepted_risks=REGISTER_ITEMS), AgentId(W))
    e.wait_idle()
    assert ANSWER not in _executor_packet(e, e.graph.get_task(TaskId("root")), None)


def test_at_an_auto_root_the_rework_order_promises_no_ruling_it_cannot_get(e, monkeypatch):
    """There only the user retires a finding, so the issuer answers without a ruling: the order names the exit that
    exists — the next validation judges the finding against the criterion (critic over the dispute fix; tn9fpg788's
    root disputed one finding 166 times)."""
    t = e.graph.get_task(TaskId("root"))
    assert "only his ruling retires it" in _executor_packet(e, t, None)
    monkeypatch.setattr(P, "is_auto_root", lambda g, task: True)
    packet = _executor_packet(e, t, None)
    assert "only the user retires a finding" in packet and "only his ruling retires it" not in packet
