"""The leaf test (§3.7) is not read off a count: a leaf the system executes that fails the same criteria round after
round has its work not there yet, not a κ shown smaller — no split is owed by it, the node keeps its sessions, and a
refutation an earlier engine stored that way reads as nothing (GB_sql_database_tnha1f292, every stopped session
having ended by itself, turns to spare)."""
import json

import gfso.delegate as D
from gfso.core.types import Signal, State, TaskId
from gfso.packets import _rework_section
from tests.test_one_session_carries_a_scope import _LLM, _dispatcher, _entry, _free_claim, _project


def _leaves(tmp_path, monkeypatch):
    """AUTO over root → a, b with nobody's session judgement: each node takes a session of its own."""
    monkeypatch.setattr(D, "answer_open_questions", lambda *a, **k: [])
    e, agents = _project(tmp_path, fits=False)
    for t in ("root", "root.a", "root.b"):
        e.record_session_fit(TaskId(t), "", None)
    return e, agents, _dispatcher(e, agents, _LLM(), _LLM(), [])


def _fail_once(e, tid, crit):
    t = e.graph.get_task(TaskId(tid))
    ex = str(t.assignee)
    if t.state == State.OFFERED:
        assert D._signal(e, t.id, Signal.ACCEPT, ex)
    assert D._signal(e, t.id, Signal.DELIVER, ex, result="r", self_validation="PASS"), e.graph.get_state(t.id)
    e.wait_idle()
    key = _free_claim(e, tid)
    e.record_exec_verdict(t.id, "FAIL", [crit], "val-1", per_criterion=[_entry(tid, crit, "fail")],
                          require_probe=True, log_at=key.log_at if key else None)
    if key:
        e.claims.end_validation(key)
    iss = str(e.graph.issuer_of(t.id))
    assert (D._signal(e, t.id, Signal.FAIL, "val-1", failed_criteria=(crit,), reason="no")
            or D._signal(e, t.id, Signal.FAIL, iss, failed_criteria=(crit,), reason="no"))
    e.wait_idle()


def _leaf(e):
    return e.graph.get_task(TaskId("root.a"))


def test_equal_fails_owe_no_split_and_the_packet_still_names_the_challenge(tmp_path, monkeypatch):
    e, _, d = _leaves(tmp_path, monkeypatch)
    for _ in range(6):
        _fail_once(e, "root.a", "a_ok")
        assert not d._split_owed_said(_leaf(e)) and e.split_owed(TaskId("root.a")) is None
    text = _rework_section(e, _leaf(e))
    assert "a_ok failed in each of the last 3 rounds" in text and "split" not in text
    e.stop()


def test_a_refutation_an_earlier_engine_stored_reads_as_nothing(tmp_path, monkeypatch):
    e, _, d = _leaves(tmp_path, monkeypatch)
    for _ in range(4):
        _fail_once(e, "root.a", "a_ok")
    leaf = _leaf(e)
    e._storage.store_setting("session_fit:root.a", json.dumps({"volume": "", "fits": None, "refuted": {
        "version": [leaf.reopens, leaf.revisions], "open": True, "upto": {"root.a": [[0, 0], 4]}}}))
    assert (e.session_fit(TaskId("root.a")) or {}).get("fits") is None
    assert e.split_owed(TaskId("root.a")) is None and not d._split_owed_said(_leaf(e))
    e.stop()
