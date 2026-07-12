"""The StoragePort contract: the append-only signal log is MANDATORY CORE
(state = fold(log) is conditioned on log completeness — a silently-dropping adapter cannot
exist), and Criteria serialize in FULL (input/expected/n/timeout are contract content)."""
import pytest

from gfso.adapters.storage.memory import MemoryStorage
from gfso.adapters.storage.sqlite import SqliteStorage
from gfso.core.types import TaskId, AgentId, Task, Spec, Criteria, State, StoragePort


def test_port_refuses_an_adapter_without_the_signal_log():
    """append_audit/load_audit are abstract: an adapter that would silently lose the T11 log
    fails at INSTANTIATION, not at the first lost entry."""

    class LossyStorage(StoragePort):
        def get_task(self, task_id): return None
        def save_task(self, task): ...
        def get_all_tasks(self): return []
        def get_children(self, task_id): return []
        def get_parent(self, task_id): return None
        def get_active_tasks(self): return []
        def get_check_results(self, task_id): return []
        def store_check_results(self, task_id, results): ...
        def get_recommendation(self, task_id): return None
        def store_recommendation(self, task_id, rec): ...
        def add_dep_edge(self, edge): ...
        def remove_dep_edge(self, from_id, to_id): ...
        def get_dep_edges(self): return []
        # append_audit / load_audit MISSING — the declared-degraded adapter must implement
        # them consciously (even as a visible no-op in ITS code), never by omission

    with pytest.raises(TypeError):
        LossyStorage()


def test_memory_log_is_complete_for_its_lifetime():
    s = MemoryStorage()
    s.append_audit({"ts": "t1", "task_id": "n", "signal": "ASSIGN"})
    s.append_audit({"ts": "t2", "task_id": "n", "signal": "ACCEPT"})
    assert [r["signal"] for r in s.load_audit()] == ["ASSIGN", "ACCEPT"]


def test_criteria_serialize_in_full_over_sqlite(tmp_path):
    """input/expected/n/timeout survive the roundtrip — a verifier reads them; dropping them
    silently was a declared storage-contract leak (§3A audit)."""
    s = SqliteStorage(str(tmp_path / "c.db"))
    crit = Criteria("io", "echoes the input", input="ping", expected="pong", n=3, timeout=15)
    t = Task(id=TaskId("n"), spec=Spec("x", (crit,)), assignee=AgentId("w"), state=State.REVIEW)
    s.save_task(t)
    back = s.get_task(TaskId("n")).spec.criteria[0]
    assert (back.input, back.expected, back.n, back.timeout) == ("ping", "pong", 3, 15)
