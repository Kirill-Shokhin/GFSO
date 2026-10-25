"""A project the person stopped is listed as stopped — by whom and why — from its file, never by building its
engine; and a project whose engine is open answers with the stop it holds now, not a peek of the file taken before.

The author, 2026-10-25, on the run's switch: «состояний должно быть три … из тех же кнопок из cli … того единого
ендпоинта». The list read the root and the spend and not the stop, so a stopped import read «unfinished».
"""
from gfso.adapters.storage.sqlite import SqliteStorage, peek_project
from tests.support import make_engine
from gfso.runtime import ProjectRegistry


def test_the_stop_is_read_from_the_file(tmp_path):
    db = str(tmp_path / "p.db")
    eng = make_engine(storage=SqliteStorage(db))
    assert peek_project(db)["stopped"] is None, "a run nobody stopped is not stopped"
    eng.pause("someone", "imported to read")
    assert peek_project(db)["stopped"] | {"at": None} == {"by": "someone", "at": None, "why": "imported to read"}
    eng.resume("someone")
    assert peek_project(db)["stopped"] is None, "started again, it is no longer stopped"


def test_an_open_project_answers_its_stop_as_it_stands(monkeypatch, tmp_path):
    monkeypatch.setenv("GFSO_DATA_DIR", str(tmp_path))
    monkeypatch.delenv("GFSO_PROJECT", raising=False)
    reg = ProjectRegistry()
    eng = reg.engine("p")
    assert reg.about(["p"])["p"]["stopped"] is None
    eng.pause("someone", "")
    assert reg.about(["p"])["p"]["stopped"]["by"] == "someone", "the open engine's stop, not a stale peek"
    eng.resume("someone")
    assert reg.about(["p"])["p"]["stopped"] is None
