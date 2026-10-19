"""The issuer who let VALIDATING lapse gets the delivery back — not a pass, and not a dead node.

v4.1 §16.14: a timed-out VALIDATING used to close DONE(auto_pass) — an acceptance nobody made, which
AND read upward, and which a parent's executor could obtain over his own child by simply not
validating it. It now routes to ESCALATED, and the canon states what must then remain possible
(§12.3 Inv-1, and the Conformance clause: "no refusal may contradict a move the canon grants —
re-delivering the logged result as it is where the delivery is unvalidated"): the issuer re-presents
the contract, the executor re-delivers the identical artifact, and the issuer validates it.

This is the loop the removal of auto_pass creates, so it is the loop that has to work end to end.
"""
from __future__ import annotations

import time

import gfso.tools as T
from gfso.core.types import State, TaskId
from tests.support import criterion, make_engine, REGISTER

_RISK = REGISTER


def _waits_for(e, tid, state, limit=4.0):
    until = time.time() + limit
    while time.time() < until:
        if e.graph.get_state(TaskId(tid)) is not None and e.graph.get_state(TaskId(tid)).name == state:
            return True
        time.sleep(0.02)
    return False


def test_the_unvalidated_delivery_comes_back_and_is_validated(monkeypatch):
    monkeypatch.setenv("GFSO_BOUND_VALIDATING", "0.05")   # the bound is a protocol parameter (§12.2)
    monkeypatch.setenv("GFSO_L2_GATE", "0")
    e = make_engine(check_interval=0.05)
    e.start()
    try:
        T.create_task(e, "leaf", {"description": "a leaf", "criteria": [criterion("c", "C")],
                                  "accepted_risks": _RISK}, assignee="worker")
        e.wait_idle()
        T.signal(e, "leaf", "ACCEPT", "worker")
        T.signal(e, "leaf", "DELIVER", "worker", result="the artifact")
        assert _waits_for(e, "leaf", "ESCALATED"), "the clock accepted for the issuer"
        assert e.graph.get_task(TaskId("leaf")).done_reason is None

        # the delivery is still on the record — it is what the re-presentation is about
        assert any(a.signal.name == "DELIVER" and a.result == "the artifact"
                   for a in e.audit_log(TaskId("leaf")))

        # the issuer's own move: a re-ASSIGN carrying no spec re-presents the same contract
        T.signal(e, "leaf", "ASSIGN", "worker")   # a self-assigned root: its issuer is external, here the same agent
        assert _waits_for(e, "leaf", "OFFERED")
        T.signal(e, "leaf", "ACCEPT", "worker")
        out = T.signal(e, "leaf", "DELIVER", "worker", result="the artifact")
        assert out.get("accepted") is True, out          # the IDENTICAL artifact, unvalidated before
        assert _waits_for(e, "leaf", "VALIDATING")
        e.record_exec_verdict("leaf", "PASS", [], "validator", per_criterion=[
            {"criterion": "c", "verdict": "pass", "evidence": "ran the pinned probe",
             "behaviours": ["c holds"],
             "probe": [{"behaviour": "c holds", "command": "check c", "expect": "it holds"}]}])
        assert T.signal(e, "leaf", "PASS", "worker").get("accepted") is True
        assert e.graph.get_state(TaskId("leaf")) == State.DONE
    finally:
        e.stop()
