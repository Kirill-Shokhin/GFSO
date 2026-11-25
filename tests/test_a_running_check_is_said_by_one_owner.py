"""What check the machine runs on a node is answered by one owner, `Engine.checks_running`, and said by one table,
`frontier.CHECKS_RUNNING`: the graph at work (`in_flight_nodes`) and the held step read both. Two hand copies had drifted
— the graph at work and the frontier said one running review in two wordings.

Control: spell a row's text by hand back into `in_flight_nodes` or the frontier, and the source count goes red."""
from pathlib import Path

from gfso import tools as T
from gfso.core.types import TaskId
from gfso.engine.frontier import CHECKS_RUNNING
from tests.support import criterion, make_engine, REGISTER


def test_a_running_review_is_the_graph_at_work_in_the_tables_words():
    e = make_engine(check_interval=10_000)
    e.start()
    assert "error" not in T.create_task(e, "root", {"description": "the whole", "criteria": [criterion("c1", "C1")],
                                                    "accepted_risks": REGISTER}, assignee="user")
    e.wait_idle()
    assert e.checks_running(TaskId("root")) == []
    claim = e.claims.begin_review(TaskId("root"))
    assert e.checks_running(TaskId("root")) == ["plan"]
    row = next(n for n in e.in_flight_nodes() if n["task_id"] == "root")
    assert row["why"] == CHECKS_RUNNING["plan"][0]
    e.claims.end_review(claim)
    assert e.checks_running(TaskId("root")) == []
    e.stop()


def test_each_running_check_is_spelled_once():
    src = "".join(p.read_text(encoding="utf-8") for p in Path(__file__).parents[1].joinpath("gfso").rglob("*.py"))
    for check, texts in CHECKS_RUNNING.items():
        for text in texts[:1] + texts[2:3]:
            assert src.count(text[:40]) == 1, f"{check}: {text[:40]!r} spelled outside CHECKS_RUNNING"
