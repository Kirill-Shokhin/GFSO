"""An unchanged re-delivery is no new attempt, and the rework packet says so: handing the same files again moves nothing.
Measured 2026-10-25 on two AUTO projects whose plan the user gave whole: root.joins (GB_sql_database_tngo2o700) and
root.scaffold (tngn3j412) were each FAILed four times over ONE git tree, the executor re-handing it while its report
said the fix lay in another node's file. No count of FAILs, over one tree or over four, owes a split: no count measures
κ (`test_equal_fails_do_not_measure_kappa`).

CONTROLS: let `Engine.fails_over_new_work` return every FAIL (`list(self.fails_of(task_id))`), and the first test goes
red; let `commit_all` return the commit, not its tree, and the second does; drop `artifact` from the sqlite
row, and the third does; render this round's probes without their id, and the fourth does.
"""
from __future__ import annotations

import shutil
from datetime import datetime

import pytest

import gfso.delegate as D
import gfso.tools as T
from gfso import packets
from gfso.adapters import worktrees as W
from gfso.adapters.storage.sqlite import SqliteStorage
from gfso.core.types import Signal, State, TaskId
from gfso.engine.audit import AuditEntry, AuditLog
from gfso.issuer import ISSUER_SCHEMA
from gfso.reports import _report_into_signals
from gfso.sessions import EXECUTOR_SCHEMA
from gfso.tools_llm import _SCOPE_VALIDATOR_SCHEMA, _VALIDATOR_SCHEMA
from tests.support import criterion, make_engine, REGISTER
from tests.test_equal_fails_do_not_measure_kappa import _leaf, _leaves
from tests.test_a_node_works_in_its_own_place import _repo
from tests.test_one_session_carries_a_scope import _entry, _free_claim


def _fail_over(e, tid, crit, tree, probe=None):
    """One round of `tid`: delivered as the files `tree` names, FAILed on `crit` — by the validator's own `probe`, if
    one is given, beside the criterion's pinned one."""
    t = e.graph.get_task(TaskId(tid))
    ex = str(t.assignee)
    if t.state == State.OFFERED:
        assert D._signal(e, t.id, Signal.ACCEPT, ex)
    assert D._signal(e, t.id, Signal.DELIVER, ex, result="r", self_validation="PASS", artifact=tree)
    e.wait_idle()
    key = _free_claim(e, tid)
    entry = _entry(tid, crit, "fail")
    entry["probe"] += [{"command": probe, "expect": "an error", "behaviour": f"{crit} holds"}] if probe else []
    e.record_exec_verdict(t.id, "FAIL", [crit], "val-1", per_criterion=[entry],
                          require_probe=True, log_at=key.log_at if key else None)
    if key:
        e.claims.end_validation(key)
    iss = str(e.graph.issuer_of(t.id))
    assert (D._signal(e, t.id, Signal.FAIL, "val-1", failed_criteria=(crit,), reason="no")
            or D._signal(e, t.id, Signal.FAIL, iss, failed_criteria=(crit,), reason="no"))
    e.wait_idle()


def test_four_fails_over_one_tree_owe_no_split_and_neither_do_four_attempts(tmp_path, monkeypatch):
    e, _, d = _leaves(tmp_path, monkeypatch)
    for _ in range(4):
        _fail_over(e, "root.a", "a_ok", "tree-1")
    assert not d._split_owed_said(_leaf(e)) and e.split_owed(TaskId("root.a")) is None
    packet = packets._rework_section(e, _leaf(e))
    # the contract stays the suspect — an unchanged re-delivery only sharpens that — and the packet says what moves it
    assert "a_ok failed in each of the last 3 rounds" in packet and packets._REHANDED in packet, packet
    assert "the node is split" not in packet, packet
    for tree in ("tree-2", "tree-3"):
        _fail_over(e, "root.a", "a_ok", tree)
    assert not d._split_owed_said(_leaf(e)) and packets._REHANDED not in packets._rework_section(e, _leaf(e))
    _fail_over(e, "root.a", "a_ok", "tree-4")             # four attempts: the work is not there yet, κ is not shown
    assert not d._split_owed_said(_leaf(e)) and e.split_owed(TaskId("root.a")) is None
    e.stop()


@pytest.mark.skipif(shutil.which("git") is None, reason="the node workspaces are git worktrees")
def test_a_delivery_is_named_by_its_files_not_by_its_commit(tmp_path):
    base = _repo(tmp_path / "ws")
    place = tmp_path / "place"
    W.ensure(base, place, "gfso/p/a", base)
    (place / "a.py").write_text("x = 1\n")
    first = W.commit_all(base, place, "gfso: a delivery", "exec-1")
    assert W.commit_all(base, place, "gfso: a delivery", "exec-1") == first     # a new commit, the same files
    (place / "a.py").write_text("x = 2\n")
    assert W.commit_all(base, place, "gfso: a delivery", "exec-1") not in (first, "")


def test_what_a_deliver_handed_over_is_on_its_row_after_a_restart(tmp_path, monkeypatch):
    db = str(tmp_path / "p.db")
    AuditLog(SqliteStorage(db)).record(AuditEntry(timestamp=datetime.now(), task_id=TaskId("n"), signal=Signal.DELIVER,
                                                  old_state=State.EXECUTING, new_state=State.VALIDATING, effects=(),
                                                  artifact="2c3e0b54", commit="c0ffee01"))
    got = AuditLog(SqliteStorage(db)).get_entries()[0]
    assert (got.artifact, got.commit) == ("2c3e0b54", "c0ffee01")
    # …and the report puts it there: the tree its delivery commit names
    e = make_engine(validate_signals=True, state_timeout=0)
    e.start()
    T.create_task(e, "n", {"description": "the work", "accepted_risks": REGISTER, "criteria": [criterion("g", "G")]},
                  assignee="worker")
    T.signal(e, "n", "ACCEPT", "worker")
    monkeypatch.setattr(W, "commit_all", lambda *a, **k: "2c3e0b54")
    monkeypatch.setattr(W, "head", lambda *a, **k: "c0ffee01")
    monkeypatch.setattr(W, "merging", lambda *a, **k: False)
    monkeypatch.setattr("gfso.reports.still_unjoined", lambda *a, **k: [])
    monkeypatch.setattr("gfso.reports._settle_internal", lambda *a, **k: None)
    _report_into_signals(e, TaskId("n"), "worker", e.graph.get_task("n"), {"status": "delivered", "summary": "s"},
                         "delivered", type("L", (), {"calls": []})(), lambda s: None, workspace=("b", "p"))
    e.wait_idle()
    assert [(x.artifact, x.commit) for x in e.audit_log(TaskId("n")) if x.signal == Signal.DELIVER] ==         [("2c3e0b54", "c0ffee01")]
    e.stop()


def test_every_probe_a_rework_shows_carries_the_id_it_is_disputed_by(tmp_path, monkeypatch):
    e, _, _ = _leaves(tmp_path, monkeypatch)
    _fail_over(e, "root.a", "a_ok", "tree-1", probe="echo 'SELECT id FROM a, b;' | ./db")
    (found,) = e.regression_probes(TaskId("root.a"))["a_ok"]
    packet = packets._rework_section(e, _leaf(e))
    assert f"probe [{found['id']}]: `echo 'SELECT id FROM a, b;' | ./db`" in packet, packet
    e.stop()


def test_a_tech_report_names_the_cases_it_is_for_and_every_role_can_file_one():
    said = packets.TECH_REPORT["description"]
    assert not said.startswith("Leave it out")
    for case in ("unchanged result because the fix lies in another node's file", "no id to dispute",
                 "ruling contradicts itself", "\"no defect found\" is no report", "moves nothing"):
        assert case in said, case
    for schema in (EXECUTOR_SCHEMA, ISSUER_SCHEMA, _VALIDATOR_SCHEMA, _SCOPE_VALIDATOR_SCHEMA):
        assert schema["properties"]["tech_report"] == packets.TECH_REPORT


def test_a_settled_finding_is_shown_with_what_it_ran(tmp_path, monkeypatch):
    """Settled ids alone, an executor could not tell that the probe its observation still quoted was the one retired,
    and disputed it again (root.joins, audit 52)."""
    e, _, _ = _leaves(tmp_path, monkeypatch)
    _fail_over(e, "root.a", "a_ok", "tree-1", probe="echo 'SELECT * FROM a JOIN b ON a.id=b.id, n1;' | ./db")
    (found,) = e.regression_probes(TaskId("root.a"))["a_ok"]
    leaf = _leaf(e)
    assert D._signal(e, leaf.id, Signal.CHALLENGE, str(leaf.assignee), reason=f"{found['id']} is the parser's grammar")
    e.wait_idle()
    assert D._signal(e, leaf.id, Signal.ACCEPT_CHALLENGE, str(e.graph.issuer_of(leaf.id)), new_spec=leaf.spec,
                     retire_findings=(found["id"],), justification="parser scope")
    e.wait_idle()
    packet = packets._rework_section(e, _leaf(e))
    assert f"[{found['id']}]: `echo 'SELECT * FROM a JOIN b ON a.id=b.id, n1;' | ./db`" in packet, packet
    e.stop()
