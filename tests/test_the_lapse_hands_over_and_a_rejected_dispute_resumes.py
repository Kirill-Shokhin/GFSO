"""Two table changes agreed with the theory stream (2026-09-24), driven through the engine.

E1 — OVERDUE is gone: a wait's first timeout hands the node to its issuer at once, and a node a
database still holds in OVERDUE is moved to ESCALATED when the database opens — as a migration, not
as a signal nobody sent.

E2 — REJECT_CHALLENGE returns the node to the wait the challenge interrupted: OFFERED when the
executor had not ACCEPTed the current packet version, EXECUTING when he had; the contract itself
does not move. "The current version" begins at the latest version-installing event (an ASSIGN in
any form, an ACCEPT_CHALLENGE) — not at the latest entry into OFFERED. And a node whose rework is
resumed in EXECUTING (a rejected challenge, a resolved block) is still reworking. The table-level half (C3) is in `test_canon_fsm_table.py`; this is the log half —
that the engine reads consent off the log the way the table assumes.
"""
from __future__ import annotations

import sqlite3
from datetime import datetime, timedelta

import pytest
from fastapi.testclient import TestClient

import gfso.tools as T
from gfso.api.server import create_app
from gfso.adapters.storage.sqlite import SqliteStorage
from gfso.core.types import (Action, AgentId, Criteria, Signal, SignalData, Spec, State, Task,
                             TaskId)
from gfso.packets import _executor_packet
from gfso.engine import Engine, audit
from gfso.engine.audit import AuditEntry, AuditLog, consented_on_current_version
from tests.support import criterion, make_engine, pinned, REGISTER_ITEMS, REGISTER

_RISK = REGISTER
W = "worker"                       # a root's executor is its own issuer


@pytest.fixture(autouse=True)
def _no_l2(monkeypatch):
    monkeypatch.setenv("GFSO_L2_GATE", "0")


@pytest.fixture
def e():
    eng = make_engine()
    eng.start()
    T.create_task(eng, "root", {"description": "a goal", "criteria": [criterion("c", "C")],
                                "accepted_risks": _RISK}, assignee=W)
    eng.wait_idle()
    yield eng
    eng.stop()


def _contract(e):
    t = e.graph.get_task(TaskId("root"))
    return (t.spec, t.deadline, t.iteration, t.revisions, t.reopens)


def _dispute_rejected(e):
    assert T.signal(e, "root", "CHALLENGE", W, reason="criterion c is ambiguous")["accepted"]
    assert e.graph.get_state(TaskId("root")) == State.CHALLENGED
    before = _contract(e)
    assert T.signal(e, "root", "REJECT_CHALLENGE", W, justification="c stands as written")["accepted"]
    assert _contract(e) == before, "a rejected dispute moved the contract"


def test_a_dispute_rejected_before_consent_returns_to_the_offer(e):
    _dispute_rejected(e)
    assert e.graph.get_state(TaskId("root")) == State.OFFERED     # he owes the ACCEPT he never gave
    _dispute_rejected(e)                                     # …and a second round is the same
    assert e.graph.get_state(TaskId("root")) == State.OFFERED
    assert T.signal(e, "root", "ACCEPT", W)["accepted"]
    assert e.graph.get_state(TaskId("root")) == State.EXECUTING


def test_a_dispute_rejected_after_consent_returns_to_the_work(e):
    assert T.signal(e, "root", "ACCEPT", W)["accepted"]
    _dispute_rejected(e)
    assert e.graph.get_state(TaskId("root")) == State.EXECUTING


def test_consent_to_an_earlier_version_is_not_consent(e):
    """The ACCEPT has to be of the CURRENT version: a revision after it re-opens the question."""
    assert T.signal(e, "root", "ACCEPT", W)["accepted"]
    e._revise(TaskId("root"), Spec("a goal, revised", (Criteria("c", "C2", check=pinned("c")),),
                                   accepted_risks=REGISTER_ITEMS), AgentId(W))
    e.wait_idle()
    assert e.graph.get_state(TaskId("root")) == State.OFFERED
    _dispute_rejected(e)
    assert e.graph.get_state(TaskId("root")) == State.OFFERED


def test_the_first_timeout_of_every_wait_hands_over_at_once(e):
    route = []
    for prep in ([], ["CHALLENGE"], ["ACCEPT"], ["ACCEPT", "DELIVER", "FAIL"]):
        if route:                                   # the issuer takes it back out of ESCALATED
            e._revise(TaskId("root"), Spec("again", (Criteria("c", "C", check=pinned("c")),),
                                           accepted_risks=REGISTER_ITEMS), AgentId(W))
            e.wait_idle()
        for sig in prep:
            T.signal(e, "root", sig, W, reason="r", result="v", failed_criteria=["c"])
        waiting = e.graph.get_state(TaskId("root"))
        e.send_signal_sync(SignalData(signal=Signal.TIMEOUT, task_id=TaskId("root")))
        route.append((waiting.name, e.graph.get_state(TaskId("root")).name))
    assert route == [("OFFERED", "ESCALATED"), ("CHALLENGED", "ESCALATED"),
                     ("EXECUTING", "ESCALATED"), ("REWORKING", "ESCALATED")], route


def test_a_node_stored_in_overdue_opens_in_escalated(tmp_path):
    """The migration: once, at open, logged as a migration — and no signal in the audit log."""
    db = str(tmp_path / "g.db")
    s = SqliteStorage(db)
    s.save_task(Task(id=TaskId("n"), spec=Spec("g", (Criteria("c", "C"),)), state=State.EXECUTING,
                     assignee=AgentId(W), state_entered_at=datetime.now() - timedelta(days=3)))
    s.append_audit({"ts": datetime.now().isoformat(), "task_id": "n", "signal": "TIMEOUT",
                    "old_state": "EXECUTING", "new_state": "OVERDUE", "effects": []})
    s.close()
    with sqlite3.connect(db) as c:                      # the row an older build left behind
        c.execute("UPDATE tasks SET state = 'OVERDUE' WHERE id = 'n'")

    s = SqliteStorage(db)
    t = s.get_task(TaskId("n"))
    assert t.state == State.ESCALATED
    assert datetime.now() - t.state_entered_at < timedelta(minutes=1), \
        "the issuer's window starts at the migration, not at the old state's entry"
    said = [r["message"] for r in s.get_pipeline() if r["source"] == "migration"]
    assert len(said) == 1 and "OVERDUE" in said[0] and "not a signal" in said[0], said
    rows = AuditLog(s).get_entries(TaskId("n"))
    assert [(r.signal, r.new_state) for r in rows] == [(Signal.TIMEOUT, State.ESCALATED)], \
        "the old row reads through the retired name; the migration wrote no signal"
    s.close()

    s = SqliteStorage(db)                               # idempotent: the second open says nothing
    assert [r["message"] for r in s.get_pipeline() if r["source"] == "migration"] == said
    s.close()


# ── consent is read against the latest VERSION-INSTALLING event, not the latest entry into OFFERED ──

def _log(*steps):
    """A synthetic log: (signal, new_state) pairs, all accepted."""
    return [AuditEntry(timestamp=datetime.now(), task_id=TaskId("n"), signal=Signal[sig],
                       old_state=None, new_state=State[to], effects=()) for sig, to in steps]


CONSENT_CASES = [
    # a pre-consent REJECT_CHALLENGE enters OFFERED and installs nothing; the ACCEPT after it counts
    (_log(("ASSIGN", "OFFERED"), ("CHALLENGE", "CHALLENGED"), ("REJECT_CHALLENGE", "OFFERED"),
          ("ACCEPT", "EXECUTING"), ("CHALLENGE", "CHALLENGED")), True),
    # the two readings part here: an OFFERED entry that installs nothing leaves the ACCEPT standing
    # (unreachable through the engine — a REJECT_CHALLENGE reaches OFFERED only WITHOUT consent —
    # so it is shown on the definition itself)
    (_log(("ASSIGN", "OFFERED"), ("ACCEPT", "EXECUTING"), ("REJECT_CHALLENGE", "OFFERED"),
          ("CHALLENGE", "CHALLENGED")), True),
    # a revision installs a version: the earlier ACCEPT is of a contract that no longer stands
    (_log(("ASSIGN", "OFFERED"), ("ACCEPT", "EXECUTING"), ("ASSIGN", "OFFERED"),
          ("CHALLENGE", "CHALLENGED")), False),
    # …and so does an accepted dispute
    (_log(("ASSIGN", "OFFERED"), ("ACCEPT", "EXECUTING"), ("CHALLENGE", "CHALLENGED"),
          ("ACCEPT_CHALLENGE", "OFFERED"), ("CHALLENGE", "CHALLENGED")), False),
    (_log(("ASSIGN", "OFFERED"), ("ACCEPT", "EXECUTING"), ("CHALLENGE", "CHALLENGED")), True),
    ([], False),
]


def _cases_hold(reader) -> None:
    for entries, want in CONSENT_CASES:
        assert reader(entries) is want, [(e.signal.name, e.new_state.name) for e in entries]


def test_consent_is_an_accept_after_the_latest_version_installing_event():
    _cases_hold(consented_on_current_version)


def test_control_the_offered_entry_reading_is_caught():
    """The reading this replaced — "an entry into OFFERED resets consent" — fails the cases."""
    def offered_reading(entries):
        for e in reversed(entries):
            if e.signal == Signal.ACCEPT:
                return True
            if e.new_state == State.OFFERED:
                return False
        return False
    with pytest.raises(AssertionError):
        _cases_hold(offered_reading)


@pytest.mark.parametrize("dropped", [Signal.ASSIGN, Signal.ACCEPT_CHALLENGE])
def test_control_each_version_installing_signal_is_load_bearing(monkeypatch, dropped):
    monkeypatch.setattr(audit, "VERSION_INSTALLING", audit.VERSION_INSTALLING - {dropped})
    with pytest.raises(AssertionError):
        _cases_hold(consented_on_current_version)


# ── a reworking node resumed in EXECUTING keeps its failed-criteria pointer ──────────────────────

def _failed_then(e, *resume):
    for sig in ("ACCEPT", "DELIVER", "FAIL", *resume):
        assert T.signal(e, "root", sig, W, reason="r", result="v", failed_criteria=["c"],
                        justification="c stands")["accepted"], sig
    return e.graph.get_task(TaskId("root"))


def _still_reworking(e, t) -> None:
    assert e.in_rework(t)
    assert "the validator FAILED these criteria" in _executor_packet(e, t, None)
    assert e.next_steps(TaskId("root"))["steps"][0]["action"] == Action.FIX


@pytest.mark.parametrize("resume", [("CHALLENGE", "REJECT_CHALLENGE"), ("BLOCK", "RESOLVE_BLOCK")])
def test_a_resumed_rework_still_carries_its_failure(e, resume):
    t = _failed_then(e, *resume)
    assert t.state == State.EXECUTING
    _still_reworking(e, t)


def test_a_new_version_ends_the_rework(e):
    _failed_then(e)
    e._revise(TaskId("root"), Spec("a goal, revised", (Criteria("c", "C2", check=pinned("c")),),
                                   accepted_risks=REGISTER_ITEMS), AgentId(W))
    e.wait_idle()
    assert T.signal(e, "root", "ACCEPT", W)["accepted"]
    t = e.graph.get_task(TaskId("root"))
    assert t.state == State.EXECUTING and not e.in_rework(t)
    assert "the validator FAILED" not in _executor_packet(e, t, None)


def test_control_the_state_label_loses_the_failure(e, monkeypatch):
    t = _failed_then(e, "CHALLENGE", "REJECT_CHALLENGE")
    monkeypatch.setattr(Engine, "in_rework", lambda self, t: t.state == State.REWORKING)
    with pytest.raises(AssertionError):
        _still_reworking(e, t)


# ── a retired name read from anywhere is refused or translated, never a crash ──────────────────

def test_an_overdue_row_written_after_open_still_reads(tmp_path):
    db = str(tmp_path / "g.db")
    s = SqliteStorage(db)
    s.save_task(Task(id=TaskId("n"), spec=Spec("g", (Criteria("c", "C"),)), state=State.EXECUTING))
    s._conn.execute("UPDATE tasks SET state = 'OVERDUE' WHERE id = 'n'")   # another process
    s._conn.commit()
    assert s.get_task(TaskId("n")).state == State.ESCALATED
    s.close()


def test_the_api_refuses_a_retired_or_unknown_state_with_a_reason():
    eng = make_engine(validate_signals=False)
    eng.start()
    try:
        c = TestClient(create_app(eng))
        for name, said in (("OVERDUE", "now ESCALATED"), ("NONSENSE", "no state is called")):
            r = c.get("/api/tasks", params={"state": name})
            assert r.status_code == 422 and said in r.text, (name, r.status_code, r.text)
        assert c.get("/api/tasks", params={"state": "ESCALATED"}).status_code == 200
    finally:
        eng.stop()
