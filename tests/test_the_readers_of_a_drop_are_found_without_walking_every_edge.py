"""Who reads a dropped node is looked up, not searched: the readers of every node are one index, made once per write
of the store from the declared edges and the criteria's references — a search over every node's edges at each drop
cost 1.9 s on 1,000 nodes and 35 s on 4,000, on every reshape. Held by a COUNT, not a clock."""
from gfso import tools as T
from gfso.adapters.storage.sqlite import SqliteStorage
from tests.test_a_move_costs_the_same_on_a_larger_graph import Counted, a_graph


def reads_of_a_drop(path, k: int) -> int:
    """The whole-store reads (every node, every Dep edge) finding who reads `root.p0`'s subtree, after a write."""
    e = a_graph(path, k)
    try:
        Counted.walks = 0
        found = T._readers(e, "root.p0")
        assert "root.p1.a" in {str(t.id) for t, _ in found}, found
        return Counted.walks
    finally:
        e.stop()


def test_the_readers_of_a_drop_cost_the_same_on_a_graph_twice_the_size(tmp_path, monkeypatch):
    monkeypatch.setattr(Counted, "get_dep_edges", lambda self: setattr(Counted, "walks", Counted.walks + 1)
                        or SqliteStorage.get_dep_edges(self), raising=False)
    small, large = reads_of_a_drop(tmp_path / "s.db", 6), reads_of_a_drop(tmp_path / "l.db", 12)
    assert large == small, f"finding a drop's readers read the store whole {small} times on 19 nodes, {large} on 37"
