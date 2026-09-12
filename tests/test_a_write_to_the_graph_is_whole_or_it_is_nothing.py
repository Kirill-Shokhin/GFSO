"""One connection, many dispatcher threads: a write is seen whole, or not at all.

`SqliteStorage` opens ONE connection with `check_same_thread=False` and the dispatcher hands it to
every worker thread it spawns. Two things followed, and neither is theoretical:

* **A torn read.** `store_check_results` is DELETE + INSERT. On a shared connection a reader between
  the two statements does not see the old rows and does not yet see the new ones — it sees a node
  whose checks are the EMPTY SET, which is the shape a vacuous green is made of.
* **A partial write published by somebody else.** Nothing rolled back. A statement that raised left
  its half of the mutation pending on the connection, and the next thread to `commit()` — any thread,
  writing anything — published it.

The owner of both is `_write`: one lock over every statement of a mutation plus its commit, rollback
on the way out. `_read` takes the same lock so a reader never lands inside a write.

The controls that make this test worth having are named at each case: remove the lock from `_write`
(or from `_read`) and the first case goes red; remove the rollback and the second and third do.
"""
import threading

import pytest

from gfso.adapters.storage.sqlite import SqliteStorage
from gfso.core.types import AgentId, CheckResult, Criteria, Spec, Task, TaskId


class _ConnWith:
    """The real connection with ONE method replaced.

    `sqlite3.Connection` refuses attribute assignment, so the interception has to sit beside it.
    Everything the storage touches — `execute`, `commit`, `rollback`, `close` — passes straight
    through, so what is under test is the storage's real code path, not a stand-in for it.
    """

    def __init__(self, conn, **replaced):
        self._conn, self._replaced = conn, replaced

    def __getattr__(self, name):
        if name in self._replaced:
            return self._replaced[name]
        return getattr(self._conn, name)


def _storage(tmp_path) -> SqliteStorage:
    # A FILE, not ":memory:" — the run's store is a file, and the locking behaviour under test is
    # the file one.
    return SqliteStorage(str(tmp_path / "gfso.db"))


def _task(tid="t1") -> Task:
    return Task(id=TaskId(tid), spec=Spec("s", (Criteria("c", "c"),), (), ()),
                assignee=AgentId("a1"))


def _checks(n: int) -> list[CheckResult]:
    return [CheckResult(f"CHECK-{i}", True, "d", False, False) for i in range(n)]


def test_a_reader_between_the_delete_and_the_insert_sees_the_old_checks(tmp_path):
    """CONTROL: drop the lock from `_write` (or from `_read`) and the reader sees zero checks."""
    s = _storage(tmp_path)
    s.save_task(_task())
    s.store_check_results(TaskId("t1"), _checks(3))

    mid_write = threading.Event()
    reader_done = threading.Event()
    seen = []
    real = s._conn

    def _pause_between_the_statements(*a, **kw):
        # The DELETE has run; the INSERT has not. This is the exact instant the defect lived in.
        mid_write.set()
        reader_done.wait(timeout=2.0)
        return real.executemany(*a, **kw)

    s._conn = _ConnWith(real, executemany=_pause_between_the_statements)

    def _reader():
        mid_write.wait(timeout=2.0)
        seen.append(len(s.get_check_results(TaskId("t1"))))
        reader_done.set()

    r = threading.Thread(target=_reader)
    r.start()
    s.store_check_results(TaskId("t1"), _checks(5))
    r.join(timeout=5.0)
    s._conn = real
    assert not r.is_alive()

    # The reader was made to try mid-write. Under the lock it waits and reads the FINISHED write;
    # what it must never report is the empty set that lives between the two statements.
    assert seen == [5], seen


def test_a_write_that_raises_leaves_the_previous_state_standing(tmp_path):
    """CONTROL: remove the `rollback` from `_write` and the checks come back as zero."""
    s = _storage(tmp_path)
    s.save_task(_task())
    s.store_check_results(TaskId("t1"), _checks(3))

    def _boom(*a, **kw):
        raise RuntimeError("the INSERT half never ran")

    real = s._conn
    s._conn = _ConnWith(real, executemany=_boom)
    with pytest.raises(RuntimeError):
        s.store_check_results(TaskId("t1"), _checks(5))
    s._conn = real

    # The DELETE was half of a mutation that did not happen. Without the rollback it stays pending
    # on the connection and the next commit — by ANY thread — publishes it.
    assert len(s.get_check_results(TaskId("t1"))) == 3
    s.save_task(_task())                                   # somebody else commits
    assert len(s.get_check_results(TaskId("t1"))) == 3


def test_the_pending_half_of_a_failed_write_is_not_published_by_another_thread(tmp_path):
    """The same defect in the shape it kills a run in: two threads over one connection."""
    s = _storage(tmp_path)
    s.save_task(_task())
    s.store_check_results(TaskId("t1"), _checks(3))

    def _boom(*a, **kw):
        raise RuntimeError("model returned nothing to insert")

    real = s._conn
    s._conn = _ConnWith(real, executemany=_boom)
    with pytest.raises(RuntimeError):
        s.store_check_results(TaskId("t1"), _checks(5))
    s._conn = real

    done = threading.Event()

    def _neighbour():
        for i in range(20):
            s.save_task(_task(f"n{i}"))
            s.append_audit({"ts": "t", "task_id": f"n{i}", "signal": "ASSIGN"})
        done.set()

    t = threading.Thread(target=_neighbour)
    t.start()
    t.join(timeout=10.0)
    assert done.is_set()
    assert len(s.get_check_results(TaskId("t1"))) == 3


def test_many_threads_writing_the_same_store_lose_nothing(tmp_path):
    """The dispatcher's real shape: several workers writing at once, holding no lock of their own."""
    s = _storage(tmp_path)
    errors = []

    def _worker(k: int):
        try:
            for i in range(25):
                tid = f"t{k}-{i}"
                s.save_task(_task(tid))
                s.store_check_results(TaskId(tid), _checks(3))
                s.append_audit({"ts": "t", "task_id": tid, "signal": "ASSIGN"})
                assert len(s.get_check_results(TaskId(tid))) == 3
        except BaseException as ex:            # noqa: BLE001 — the assertion IS the subject
            errors.append(ex)

    threads = [threading.Thread(target=_worker, args=(k,)) for k in range(6)]
    for t in threads:
        t.start()
    for t in threads:
        t.join(timeout=30.0)
    assert not any(t.is_alive() for t in threads)
    assert not errors, errors
    assert len(s.get_all_tasks()) == 6 * 25
    assert len(s.load_audit()) == 6 * 25
