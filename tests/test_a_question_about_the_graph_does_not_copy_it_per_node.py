"""One question about the graph copies the whole of it a fixed number of times, whatever its size. The graph's own walks
(a subtree, the live edges) took a copy of every node at every step: 394 whole copies for one `next_steps` on 57 nodes,
2,344 on 421 — 24.5 s through the MCP door on the development graph (measured 2026-11-13). Counted, not timed: a
timing on a loaded machine spreads fourfold, a count does not."""
from gfso import tools as T
from gfso.adapters.storage import sqlite as S
from gfso.adapters.storage.sqlite import SqliteStorage
from gfso.core.types import AgentId, CriterionMapping, Spec, TaskId
from tests.support import REGISTER_SPLIT, make_engine

_BY_PARENT = S.by_parent
HUMAN = {"name": "c", "description": "holds", "check": [{"behaviour": "holds", "command": "a person reads it", "expect": "ok"}]}


def _whole_copies(tmp_path, k: int, monkeypatch) -> tuple:
    """`next_steps` on a root split into k parts of k parts each: how many times it asked for every node, and how many
    times the children were read by scanning every node (the parent index built anew)."""
    e = make_engine(storage=SqliteStorage(str(tmp_path / f"g{k}.db")))
    e.start()
    T.create_task(e, "root", {"description": "goal", "criteria": [HUMAN]}, assignee="me")
    e.wait_idle()
    T.signal(e, "root", "ACCEPT", "me")
    e.wait_idle()
    crit = e.graph.get_task(TaskId("root")).spec.criteria[0]

    def split(parent: str) -> None:
        e.decompose_task(TaskId(parent), [(TaskId(f"{parent}.{i}"), Spec(f"p{i}", (crit,)), AgentId("me")) for i in range(k)],
                         [CriterionMapping("c", TaskId(f"{parent}.{i}")) for i in range(k)], register=REGISTER_SPLIT)
        e.wait_idle()
    split("root")
    for i in range(k):
        T.signal(e, f"root.{i}", "ACCEPT", "me")
        e.wait_idle()
        split(f"root.{i}")
    store, asked, scans = e.graph._storage, [], []
    whole = store.get_all_tasks
    store.get_all_tasks = lambda: (asked.append(1), whole())[1]
    monkeypatch.setattr(S, "by_parent", lambda tasks: (scans.append(1), _BY_PARENT(tasks))[1])
    T.TOOLS["next_steps"](e)
    e.stop()
    return len(asked), len(scans)


def test_the_whole_graph_is_copied_as_often_on_a_large_graph_as_on_a_small_one(tmp_path, monkeypatch):
    (small, small_scans), (large, large_scans) = _whole_copies(tmp_path, 3, monkeypatch), _whole_copies(tmp_path, 8, monkeypatch)
    assert large == small <= 8, (small, large)
    assert large_scans == small_scans <= 2, (small_scans, large_scans)
