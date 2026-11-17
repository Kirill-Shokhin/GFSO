"""A project is offered for deletion only when it never ran — and a graph people hold calls no model: by spend alone a
400-node development graph, hundreds of signed moves in it, was offered for deletion (the author, 2026-11-13). What its
parties did counts as running it."""
import sqlite3
from pathlib import Path

from gfso import tools as T
from gfso.adapters.storage.sqlite import SqliteStorage, peek_project
from tests.support import make_engine

HUMAN = {"name": "accepted", "description": "accepted",
         "check": [{"behaviour": "holds", "command": "a person reads it", "expect": "accepts"}]}


def test_a_move_made_in_a_project_is_on_its_peek_and_the_page_reads_it(tmp_path):
    db = str(tmp_path / "p.db")
    e = make_engine(storage=SqliteStorage(db))
    e.start()
    T.create_task(e, "root", {"description": "goal", "criteria": [HUMAN]}, assignee="author")
    e.wait_idle()
    assert peek_project(db)["moves"] == 0            # …the work given out and nothing done: it never ran
    T.signal(e, "root", "ACCEPT", "author")
    e.wait_idle()
    assert peek_project(db)["moves"] == 1
    e.stop()
    page = (Path(__file__).parents[1] / "gfso" / "web" / "js" / "projects.js").read_text(encoding="utf-8")
    rule = page[page.index("const neverRan"):page.index(";", page.index("const neverRan"))]
    assert "!p.moves" in rule and "!p.cost" in rule


def test_a_lapse_of_the_clock_is_no_move(tmp_path):
    """The clock's lapse is no one working in it (`acted` already says so)."""
    db = str(tmp_path / "p.db")
    e = make_engine(storage=SqliteStorage(db))
    e.start()
    T.create_task(e, "root", {"description": "goal", "criteria": [HUMAN]}, assignee="author")
    e.wait_idle()
    e.stop()
    c = sqlite3.connect(db)
    c.execute("INSERT INTO audit_log (ts, task_id, signal, rejected, source) VALUES ('2026-11-13', 'root', 'TIMEOUT', 0, NULL)")
    c.commit()
    c.close()
    assert peek_project(db)["moves"] == 0
