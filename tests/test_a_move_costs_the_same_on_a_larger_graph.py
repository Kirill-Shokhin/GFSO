"""A move's cost does not grow with the graph it is made in.

Every signal's reply carries the frontier's next step, and the frontier read derived wholes — the live edges, a node's
subtree, the waits, a plan's Dep population — again at each node it walked: a move cost 0.4 s on a 500-node graph and
10 s on a 2,000-node one (measured 2026-11-18). Held by a COUNT, not by a clock: a move asks the store for as many walks
over every node on a graph twice the size.
"""
import contextvars

from gfso import tools as T
from gfso.config import ONE_CALL
from gfso.adapters.storage.sqlite import SqliteStorage
from gfso.core.graph.model import Graph, dep_scope
from tests.support import REGISTER, criterion, make_engine


class Counted(SqliteStorage):
    """The store, counting the reads that walk every node."""
    walks = 0

    def task_view(self):
        Counted.walks += 1
        return super().task_view()

    def get_all_tasks(self):
        Counted.walks += 1
        return super().get_all_tasks()


def a_graph(path, k: int):
    """A goal split into `k` parts of two leaves each, each part's first leaf reading the part before it."""
    e = make_engine(Counted(str(path)))
    e.start()
    T.create_task(e, "root", {"description": "goal", "criteria": [criterion(f"g{i}") for i in range(k)],
                              "accepted_risks": REGISTER}, assignee="user")
    T.decompose(e, "root", [{"task_id": f"root.p{i}", "assignee": "user", "covers": [f"g{i}"],
                             "spec": {"description": f"part {i}", "criteria": [criterion("a"), criterion("b")]}}
                            for i in range(k)], accepted_risks=REGISTER)
    for i in range(k):
        T.decompose(e, f"root.p{i}", [{"task_id": f"root.p{i}.{x}", "assignee": "user", "covers": [x],
                                       "spec": {"description": f"leaf {x} of part {i}", "criteria": [criterion("c")]}}
                                      for x in "ab"], accepted_risks=REGISTER)
        if i:
            T.add_dependency(e, f"root.p{i - 1}.b", f"root.p{i}.a", glue="reads the part before it")
    e.wait_idle()
    return e


def walks_of_a_move(path, k: int) -> int:
    e = a_graph(path, k)
    try:
        leaf = next(s["task_id"] for s in T.next_steps(e, actor="user")["steps"] if s["task_id"].count(".") == 2)
        Counted.walks = 0
        out = T.signal(e, leaf, "ACCEPT", "user")
        assert out["accepted"] and out.get("next"), out
        return Counted.walks
    finally:
        e.stop()


def test_a_move_walks_the_graph_as_often_on_a_graph_twice_the_size(tmp_path):
    small, large = walks_of_a_move(tmp_path / "small.db", 6), walks_of_a_move(tmp_path / "large.db", 12)
    assert large == small, f"a move walked the whole graph {small} times on 19 nodes and {large} times on 37"


class Scanned(list):
    """The log's entries, counting the passes over all of them."""
    passes = 0

    def __iter__(self):
        Scanned.passes += 1
        return super().__iter__()


def per_node_reads(path, k: int, monkeypatch) -> tuple:
    """(readings of the whole graph, passes over the whole log, sqlite steps per node) while every node is asked what it
    waits on, its checks, its history and its plan's Dep population."""
    e = a_graph(path, k)
    whole = {"n": 0}
    for name in ("dep_edges", "subtree_view"):
        real = getattr(Graph, name)
        monkeypatch.setattr(Graph, name, lambda self, *a, _r=real, **kw: whole.update(n=whole["n"] + (
            not (a or kw.get("root_id")))) or _r(self, *a, **kw))
    e._audit._entries = Scanned(e._audit._entries)
    steps = {"n": 0}
    e._storage._conn.set_progress_handler(lambda: steps.update(n=steps["n"] + 1), 10)
    try:
        ids = [t.id for t in e.all_tasks()]
        whole["n"], Scanned.passes, steps["n"] = 0, 0, 0
        for i in ids:
            e.producers_awaited(i)
            e.audit_log(i)
            dep_scope(e.graph, i)
        reads, passes = whole["n"], Scanned.passes
        steps["n"] = 0
        for i in ids:
            e.get_checks(i)
        return reads, passes, steps["n"] / len(ids)
    finally:
        e._storage._conn.set_progress_handler(None, 0)
        e.stop()


def test_a_question_asked_of_every_node_reads_the_whole_graph_as_often_on_a_graph_twice_the_size(tmp_path, monkeypatch):
    """What a node waits on, its checks, its history, its plan's Dep population — each asked of every node, as the
    frontier, the page and the dispatcher do: a reading of the whole graph or log behind each one made the question
    over every node grow with the graph's square (`producers_awaited` over the real graph: 14 s, 0.03 s kept)."""
    small, large = per_node_reads(tmp_path / "s.db", 6, monkeypatch), per_node_reads(tmp_path / "l.db", 12, monkeypatch)
    assert large[:2] == small[:2], (f"readings of the whole graph, passes over the whole log: {small[:2]} on 19 nodes, "
                                    f"{large[:2]} on 37")
    assert large[2] < 1.5 * small[2], f"sqlite steps per node's checks: {small[2]:.1f} on 19 nodes, {large[2]:.1f} on 37"


def test_one_door_call_walks_the_frontier_once_and_the_next_call_anew(tmp_path, monkeypatch):
    """A move's reply carries the frontier's step and a chat client's news reads the frontier again (`_with_news`):
    within one call, of a graph nothing wrote meanwhile, that is one walk; a call after it walks afresh, for what the
    walk reads besides the store (the claims, the clock) moves without a write."""
    e = a_graph(tmp_path / "g.db", 3)
    walked, walk = [], e.frontier._frontier
    monkeypatch.setattr(e.frontier, "_frontier", lambda *a: walked.append(1) or walk(*a))

    def a_call():
        ONE_CALL.set(object())
        return T.next_step(e, actor="user"), T.next_steps(e, actor="user")
    try:
        (one, every), (again, _) = contextvars.copy_context().run(a_call), contextvars.copy_context().run(a_call)
        assert one["task_id"] == every["steps"][0]["task_id"] == again["task_id"]
        assert len(walked) == 2, f"two calls walked the frontier {len(walked)} times"
    finally:
        e.stop()
