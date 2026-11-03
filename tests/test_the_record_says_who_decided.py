"""§11.6 Thm 11: every decision's record carries its author. Under AUTO the system signs in the name of the goal's issuer
(§10.1), so the signer alone read "by agent" on an ACCEPT_CHALLENGE no agent of the user's made (ui-live-1, audit row 24).
The signer stays what the gates read; `by_system` says who decided."""
from __future__ import annotations

import contextlib
import sqlite3
import threading

from gfso import delegate as D, issuer as I, tools as T
from gfso.adapters.storage.sqlite import SqliteStorage
from gfso.api.models import audit_to_out
from gfso.core.types import AgentId, Mode, Signal, State, TaskId, Verdict
from gfso.decompose import decompose_into
from gfso.decompose.build import build_graph_live
from gfso.engine.audit import AuditLog
from tests.support import criterion
from tests.test_the_mode_decides_who_holds_what import _FakeLLM, _Roster, _admit, _engine, _goal, _kid, _split


def _rows(e, task, signal):
    return [a for a in e.audit_log(TaskId(task)) if a.signal == signal and not a.rejected]


def _one(e, task, signal):
    rows = _rows(e, task, signal)
    assert len(rows) == 1, rows
    return rows[0]


def _disputed_root():
    e = _engine(Mode.AUTO)
    _goal(e)
    T.signal(e, "root", "ACCEPT", "exec-1")
    T.signal(e, "root", "CHALLENGE", "exec-1", reason="g's pinned probe expects what g's own text refutes")
    e.wait_idle()
    return e


def _accepting(e):
    """The issuer's model accepts the dispute: the root's criterion as it stands, and one added beside it."""
    kept = [{"name": c.name, "description": c.description,
             "check": [{"behaviour": p.behaviour, "command": p.command, "expect": p.expect} for p in c.check]}
            for c in e.graph.get_task(TaskId("root")).spec.criteria]
    return I.Verbs(llm=lambda m: _FakeLLM({"decision": "accept", "justification": "the dispute holds; the goal needs more",
                                           "criteria": kept + [criterion("extra", "E holds")]}),
                   busy=lambda *a: contextlib.nullcontext(), review=None, refine=None)


def test_under_auto_the_systems_answer_at_the_root_says_the_system_decided():
    e = _disputed_root()
    out = I.settle(e, _Roster(), TaskId("root"), "dispute", "agent", _accepting(e))
    e.wait_idle()
    assert out["status"] == "applied", out
    row = _one(e, "root", Signal.ACCEPT_CHALLENGE)
    assert str(row.source) == "agent", "the signer is what `signer_refusal` reads: it stays the goal's issuer"
    assert row.by_system, "the record reads 'by agent' on a decision the system's issuer model made (Thm 11)"
    assert audit_to_out(row).by_system, "the door serves it"


def test_control_the_customers_go_and_his_own_answer_carry_no_mark():
    e = _disputed_root()
    assert not _rows(e, "root", Signal.ASSIGN)[0].by_system, "the first root ASSIGN is the customer's go"
    T.signal(e, "root", "REJECT_CHALLENGE", "agent", justification="the goal asks for what g's probe checks, as written")
    e.wait_idle()
    assert str(_one(e, "root", Signal.REJECT_CHALLENGE).source) == "agent"
    assert not any(row.by_system for row in e.audit_log(TaskId("root")))


def test_control_a_system_move_leaves_nothing_behind_on_the_thread():
    e = _disputed_root()
    I.settle(e, _Roster(), TaskId("root"), "dispute", "agent", _accepting(e))
    e.wait_idle()
    T.signal(e, "root", "ACCEPT", "exec-1")
    T.signal(e, "kid", "CANCEL", "exec-1", reason="a door's own")
    e.wait_idle()
    assert not _one(e, "kid", Signal.CANCEL).by_system


def test_control_a_persons_own_signals_carry_no_mark():
    e = _engine()
    T.TOOLS["create_task"](e, "report", {"description": "r", "criteria": [criterion("c", "C holds")]}, assignee="ann")
    e.wait_idle()
    issuer = str(e.graph.issuer_of(TaskId("report")))
    T.signal(e, "report", "ACCEPT", "ann")
    T.signal(e, "report", "DELIVER", "ann", result="r")
    T.signal(e, "report", "FAIL", issuer, failed_criteria=["c"])
    e.wait_idle()
    assert _rows(e, "report", Signal.FAIL), e.audit_log(TaskId("report"))
    assert not any(a.by_system for a in e.audit_log(TaskId("report")))


def test_the_system_door_marks_an_issuer_move_and_never_an_executors():
    """`signal_ok` is the door the dispatcher, the report relay and the issuer sign through: the verdicts, the mechanical
    RESOLVE_BLOCKs, a node's closing. A registered executor's own consent passes it too, and that is the executor's."""
    assert D._signal is I.signal_ok
    e = _engine(Mode.AUTO)
    _goal(e)
    assert I.signal_ok(e, TaskId("kid"), Signal.ACCEPT, "exec-2")
    T.signal(e, "kid", "DELIVER", "exec-2", result="r")
    e.wait_idle()
    assert I.signal_ok(e, TaskId("kid"), Signal.FAIL, "exec-1", failed_criteria=("k",))
    e.wait_idle()
    assert not _one(e, "kid", Signal.ACCEPT).by_system
    fail = _one(e, "kid", Signal.FAIL)
    assert fail.by_system and str(fail.source) == "exec-1", "a registered parent: the signer is the machine, marked too"


def test_a_revision_the_issuer_turn_makes_is_marked(monkeypatch):
    e = _engine(Mode.AUTO)
    _goal(e)
    monkeypatch.setattr(I, "_still_open", lambda *a: True)
    kid = e.graph.get_task(TaskId("kid"))
    monkeypatch.setattr(I, "_ask", lambda *a, **k: ({"move": "reassign", "justification": "the budget was short",
                                                     "max_iterations": kid.max_iterations + 2}, {}))
    out = I.settle(e, _Roster(), TaskId("kid"), "escalation", "exec-1", None)
    e.wait_idle()
    assert out["status"] == "applied", out
    first, revision = _rows(e, "kid", Signal.ASSIGN)
    assert revision.by_system and str(revision.source) == "exec-1"
    assert not first.by_system, "this kid came by the test's own door, not by the system"


def test_the_issuers_cancel_and_its_cascade_are_marked(monkeypatch):
    e = _engine(Mode.AUTO)
    _goal(e)
    _admit(e, "kid", _kid("deep", ["k"], criterion("d", "D holds")))
    monkeypatch.setattr(I, "_still_open", lambda *a: True)
    monkeypatch.setattr(I, "_ask", lambda *a, **k: ({"move": "cancel", "justification": "this part cannot be met"}, {}))
    out = I.settle(e, _Roster(), TaskId("kid"), "escalation", "exec-1", None)
    e.wait_idle()
    assert out["status"] == "applied", out
    kid, deep = _one(e, "kid", Signal.CANCEL), _one(e, "deep", Signal.CANCEL)
    assert kid.by_system and str(kid.source) == "exec-1"
    assert deep.by_system and deep.reason == "cascade from parent cancel"


def test_a_re_presentation_is_marked():
    e = _engine(Mode.AUTO)
    _goal(e)
    T.signal(e, "kid", "ACCEPT", "exec-2")
    T.signal(e, "kid", "DELIVER", "exec-2", result="r")
    e.wait_idle()
    assert D._represent(e, e.graph.get_task(TaskId("kid")), "exec-1", {"x"})
    e.wait_idle()
    assert _rows(e, "kid", Signal.ASSIGN)[-1].by_system


def test_under_auto_the_go_is_the_customers_and_the_plan_below_it_the_systems():
    """The measured shape: row 1 the customer's go, signed `agent`; rows 2-5 the split, signed by the root's executor."""
    e = _engine(Mode.AUTO)
    e.record_root_issuer(TaskId("root"), AgentId("agent"))
    build_graph_live(_split(False, whole=False), "the goal", e, assignee="exec-1")
    e.wait_idle()
    go = _rows(e, "root", Signal.ASSIGN)[0]
    assert str(go.source) == "agent" and not go.by_system
    kids = e.graph.get_active_children(TaskId("root"))
    assert kids and all(_one(e, k.id, Signal.ASSIGN).by_system for k in kids)
    assert {str(_one(e, k.id, Signal.ASSIGN).source) for k in kids} == {"exec-1"}


def test_a_plan_the_customer_hands_in_closed_is_his_and_one_the_system_authors_is_not():
    """`decompose_into`, whose `closed` is the user's plan handed in whole, or the go on a plan file. The split is signed
    by the root's executor either way; only the open one is the system's decision."""
    for closed, marked in ((True, False), (False, True)):
        e = _engine(Mode.AUTO)
        e.record_root_issuer(TaskId("root"), AgentId("agent"))
        decompose_into(e, "the goal", root_id="root", assignee="exec-1", child_assignee="exec-2", llm=_FakeLLM({}),
                       spec=_split(False, whole=False), closed=closed)
        e.wait_idle()
        rows = [_rows(e, k.id, Signal.ASSIGN)[0] for k in e.graph.get_active_children(TaskId("root"))]
        assert rows and all(r.by_system is marked for r in rows), (closed, rows)
        assert {str(r.source) for r in rows} == {"exec-1"}
        assert not _rows(e, "root", Signal.ASSIGN)[0].by_system, "the go is his either way"


def test_the_mark_survives_the_threads_the_system_answers_on(tmp_path):
    """A ContextVar does not cross into a new thread. Nothing has to: `signal_ok` and `settle` open it on the thread that
    builds the signal, here the sweep's own `_run` and a dispatcher thread as `_validate_queued` runs on."""
    e = _disputed_root()
    agents = D.AgentRegistry(path=str(tmp_path / "agents.json"))
    for a in ("exec-1", "exec-2"):
        agents.register(a, "llm-executor", workdir=str(tmp_path))
    before = set(threading.enumerate())
    I.answer_open_questions(e, agents, lambda k: True, lambda *a, **k: None, threading.Semaphore(1), _accepting(e), {})
    for th in set(threading.enumerate()) - before:
        if th.ident is not None:   # …one another thread is only starting is listed too, and cannot be joined
            th.join(10)
    e.wait_idle()
    assert _one(e, "root", Signal.ACCEPT_CHALLENGE).by_system

    T.signal(e, "root", "ACCEPT", "exec-1")
    e.wait_idle()
    th = threading.Thread(target=I.signal_ok, args=(e, TaskId("kid"), Signal.CANCEL, "exec-1"), kwargs={"reason": "r"})
    th.start()
    th.join(10)
    e.wait_idle()
    assert _one(e, "kid", Signal.CANCEL).by_system


def test_a_verdict_is_the_systems_signature_where_it_signs_and_the_parties_where_they_do():
    """§10.2: the check is V's evaluation, the signature issues the verdict and is the node's issuer's. An instrument's
    verdict reaches a signal only where that issuer's signature is automated (`sign`), so the row is the system's
    signature over the instrument's check; `source` names the instrument. The same id at the door signs for itself."""
    e = _engine(Mode.AUTO)
    _goal(e)
    e._graph.authorized_validators.add("val")
    T.signal(e, "kid", "ACCEPT", "exec-2")
    T.signal(e, "kid", "DELIVER", "exec-2", result="r")
    e.wait_idle()
    assert D._replay_a_standing_verdict(e, TaskId("kid"), {"verdict": Verdict.FAIL, "failed_criteria": ["k"]}, "val",
                                        True) == "fail"
    e.wait_idle()
    T.signal(e, "kid", "DELIVER", "exec-2", result="again")
    e.wait_idle()
    T.signal(e, "kid", "FAIL", "val", failed_criteria=["k"])
    e.wait_idle()
    signed, own = _rows(e, "kid", Signal.FAIL)
    assert (str(signed.source), signed.by_system) == ("val", True)
    assert (str(own.source), own.by_system) == ("val", False)


def test_control_a_holders_own_auto_decompose_is_his():
    """The same builder under SEMI: the holder asked for the split and signs it, and the model is his instrument."""
    e = _engine(Mode.SEMI)
    e.record_root_issuer(TaskId("root"), AgentId("agent"))
    build_graph_live(_split(False, whole=False), "the goal", e, assignee="agent", child_assignee="exec-1")
    e.wait_idle()
    kids = e.graph.get_active_children(TaskId("root"))
    assert kids and not any(_one(e, k.id, Signal.ASSIGN).by_system for k in kids)


def test_under_semi_the_holder_is_itself_and_the_split_below_it_the_systems(monkeypatch):
    e = _engine(Mode.SEMI)
    _goal(e)
    assert not _one(e, "kid", Signal.ASSIGN).by_system, "the holder's split is the holder's"
    assert str(_one(e, "kid", Signal.ASSIGN).source) == "agent"
    T.signal(e, "kid", "ACCEPT", "exec-1")
    e.wait_idle()

    def _split_it(engine, node):
        _admit(engine, node, _kid("deep", ["k"], criterion("d", "D holds")))
        return {"subtasks": [{"id": "deep"}]}

    monkeypatch.setattr(I, "_still_open", lambda *a: True)
    out = I.settle(e, _Roster(), TaskId("kid"), "split", "exec-1",
                   I.Verbs(llm=None, busy=None, review=None, refine=_split_it))
    e.wait_idle()
    assert out["status"] == "applied", out
    deep = _one(e, "deep", Signal.ASSIGN)
    assert deep.by_system and str(deep.source) == "exec-1"
    assert e.graph.get_state(TaskId("deep")) == State.OFFERED


#: The audit table as a database written before the column has it.
_BEFORE = """CREATE TABLE audit_log (id INTEGER PRIMARY KEY AUTOINCREMENT, ts TEXT NOT NULL, task_id TEXT NOT NULL,
    signal TEXT NOT NULL, old_state TEXT, new_state TEXT, effects_json TEXT DEFAULT '[]', rejected INTEGER DEFAULT 0,
    error TEXT, source TEXT, reason TEXT, justification TEXT, result TEXT, failed_criteria_json TEXT DEFAULT '[]',
    action TEXT, in_flight TEXT, spec_json TEXT, revision_reason TEXT, retire_findings_json TEXT)"""


def test_a_database_written_without_the_column_opens_and_keeps_its_rows(tmp_path):
    path = tmp_path / "old.db"
    c = sqlite3.connect(path)
    c.execute(_BEFORE)
    c.execute("INSERT INTO audit_log (ts, task_id, signal, new_state, source) VALUES "
              "('2026-11-04T00:00:00', 'root', 'ACCEPT_CHALLENGE', 'OFFERED', 'agent')")
    c.commit()
    c.close()
    storage = SqliteStorage(str(path))
    log = AuditLog(storage)
    old = log.get_entries()[0]
    assert str(old.source) == "agent" and not old.by_system, "what an old row never said is not invented"
    e = _engine(Mode.AUTO)
    _goal(e)
    assert I.signal_ok(e, TaskId("kid"), Signal.CANCEL, "exec-1", reason="the system's")
    e.wait_idle()
    log.record(_one(e, "kid", Signal.CANCEL))
    storage.close()
    reopened = SqliteStorage(str(path))
    assert [a.by_system for a in AuditLog(reopened).get_entries()] == [False, True], "the mark survives a restart"
    reopened.close()
