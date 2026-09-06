"""`gfso status` — the graph as a tree, which no door had.

`get_graph` answers with the whole object, unindented. A tester asking the plainest question there is
— "which nodes are done and which are still validating" — ended up regexing ids and states out of the
raw text with a throwaway one-liner, and said it was the one moment in the whole run where they came
closest to opening the source (CLI door, 2026-09-02). The data was there; the shape was not.
"""
from gfso import driver
from gfso import tools as T
from tests.support import make_engine


def test_the_tree_shows_state_and_holder_per_node_and_what_the_frontier_holds(monkeypatch, capsys):
    e = make_engine(check_interval=10_000)
    e.start()
    T.create_task(e, "root", {"description": "r", "criteria": [{"name": "c", "description": "C"}],
                              "accepted_risks": [{"item": "an unmodelled environment fault",
                                                  "predictability": "EXTRAORDINARY"}]},
                  assignee="agent")
    T.create_task(e, "kid", {"description": "k", "criteria": [{"name": "k1", "description": "K"}]},
                  assignee="worker", parent_id="root")
    T.map_criterion(e, "root", "kid", "c")
    T.signal(e, "kid", "ACCEPT", "worker")

    monkeypatch.setattr(driver, "_through_server", lambda *a, **k: None)
    monkeypatch.setattr(driver, "build_engine_from_env", lambda: e)
    assert driver.status([]) == 0
    out = capsys.readouterr().out

    assert "root" in out and "kid" in out
    assert "EXECUTING" in out and "(worker)" in out          # state and holder, per node
    assert out.index("root") < out.index("kid"), "the child is printed under its parent"
    assert "  [>] kid" in out, "…and indented by depth"
    assert "nodes total" in out and "frontier:" in out
    e.stop()
