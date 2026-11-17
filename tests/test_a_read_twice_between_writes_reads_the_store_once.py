"""Whole-table reads are kept until the next write: one question about the frontier read the task table 690 times and
its edges 176 — 24 s on a 400-node graph, every verb's answer and the page waiting on it (measured 2026-11-13). Kept,
they must never be stale: a write is seen at once, and a caller's unsaved change to a task it was handed is not."""
from dataclasses import replace

import pytest

from gfso.adapters.storage.sqlite import SqliteStorage
from gfso.core.types import Criteria, Spec, State, Task, TaskId


def _task(i: str) -> Task:
    return Task(id=TaskId(i), spec=Spec(description=i, criteria=(Criteria(name="c", description="c holds"),)))


def test_reads_between_writes_ask_the_store_once_and_a_write_is_seen_at_once(tmp_path):
    s = SqliteStorage(str(tmp_path / "s.db"))
    s.save_task(_task("a"))
    asked = []
    real = s._conn
    s._conn = type("Counted", (), {"execute": lambda self, q, *a: (asked.append(q), real.execute(q, *a))[1],
                                   "__getattr__": lambda self, n: getattr(real, n)})()
    for _ in range(50):
        assert [str(t.id) for t in s.get_all_tasks()] == ["a"]
        s.get_task(TaskId("a"))
    assert sum(q == "SELECT * FROM tasks" for q in asked) == 1
    s.save_task(_task("b"))
    assert sorted(str(t.id) for t in s.get_all_tasks()) == ["a", "b"]
    s._conn = real


def test_a_change_not_saved_is_not_seen_and_a_saved_one_is(tmp_path):
    s = SqliteStorage(str(tmp_path / "s.db"))
    s.save_task(_task("a"))
    t = s.get_task(TaskId("a"))
    t.state = State.DONE                                         # …set and not saved
    assert s.get_task(TaskId("a")).state == State.IDLE
    s.save_task(replace(t))
    assert s.get_task(TaskId("a")).state == State.DONE


def test_a_write_by_another_connection_is_seen(tmp_path):
    """Kept by one store, a second store's write on the same file went unseen (critic): the file's version decides."""
    a, b = SqliteStorage(str(tmp_path / "s.db")), SqliteStorage(str(tmp_path / "s.db"))
    a.save_task(_task("r"))
    assert [str(t.id) for t in a.get_all_tasks()] == ["r"]
    b.save_task(replace(_task("x"), parent_id=TaskId("r")))
    assert a.get_task(TaskId("x")) is not None and [str(t.id) for t in a.get_children(TaskId("r"))] == ["x"]


def test_a_read_inside_a_write_that_rolls_back_is_not_kept(tmp_path):
    s = SqliteStorage(str(tmp_path / "s.db"))
    s.save_task(_task("a"))
    with pytest.raises(RuntimeError), s._write() as c:
        c.execute("UPDATE tasks SET state = 'DONE' WHERE id = 'a'")
        s.get_task(TaskId("a"))                                  # …a read kept inside the write
        raise RuntimeError("undone")
    assert s.get_task(TaskId("a")).state == State.IDLE


def test_a_store_read_after_its_close_says_so(tmp_path):
    s = SqliteStorage(str(tmp_path / "s.db"))
    s.save_task(_task("a"))
    s.get_task(TaskId("a"))
    s.close()
    with pytest.raises(Exception):
        s.get_task(TaskId("a"))
