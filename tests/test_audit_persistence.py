"""Thm 11/Inv-7 survives a restart: the audit log is APPEND-ONLY in SQLite — a fresh engine on the
same DB hydrates the full signal history (it was in-memory only: a restarted server had NO trail,
so state=fold(log) could not be claimed across the process boundary)."""
from gfso.engine import Engine
from gfso.adapters.storage.sqlite import SqliteStorage
from gfso.adapters.agents.human import HumanAgent
from gfso.core.types import TaskId, AgentId, Spec, Criteria, SignalData, Signal


def _mk(db):
    e = Engine(SqliteStorage(str(db)), HumanAgent(), llm=None, validate_signals=True,
               state_timeout=0)
    e.start()
    return e


def test_audit_log_survives_restart(tmp_path):
    db = tmp_path / "t.db"
    e = _mk(db)
    e.assign_task(TaskId("n"), Spec("work", (Criteria("c", "C"),)), AgentId("human"))
    e.send_signal_sync(SignalData(signal=Signal.ACCEPT, task_id=TaskId("n"), source=AgentId("human")))
    # a REJECTED signal is history too (the refusal is provenance)
    e.send_signal_sync(SignalData(signal=Signal.PASS, task_id=TaskId("n"), source=AgentId("human")))
    before = e.audit_log()
    assert [a.signal.name for a in before] == ["ASSIGN", "ACCEPT", "PASS"]
    assert before[-1].rejected                               # PASS in EXECUTING → refused, recorded
    e.stop()

    e2 = _mk(db)                                             # the "restarted server"
    after = e2.audit_log()
    assert [a.signal.name for a in after] == ["ASSIGN", "ACCEPT", "PASS"]
    assert after[-1].rejected and after[1].source == AgentId("human")
    assert after[0].new_state is not None                    # enums round-tripped
    # and the log keeps APPENDING after hydration
    e2.send_signal_sync(SignalData(signal=Signal.DELIVER, task_id=TaskId("n"),
                                   source=AgentId("human"), result="out"))
    assert [a.signal.name for a in e2.audit_log(TaskId("n"))][-1] == "DELIVER"
    e2.stop()

    e3 = _mk(db)
    assert len(e3.audit_log()) == 4                          # the appended entry persisted too
    e3.stop()


def test_memory_storage_keeps_inmemory_audit(tmp_path):
    from gfso.adapters.storage.memory import MemoryStorage
    e = Engine(MemoryStorage(), HumanAgent(), llm=None, validate_signals=True, state_timeout=0)
    e.start()
    e.assign_task(TaskId("m"), Spec("work", (Criteria("c", "C"),)), AgentId("human"))
    assert len(e.audit_log()) == 1                           # old behavior intact (ephemeral storage)
    e.stop()
