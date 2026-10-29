"""A server's start leaves every project that stood stopped until its Start (PROJECT_CLOCK.md case 16).

The author, 2026-10-29: «разве они не должны все в стопед переводиться автоматически?» — and, on a «resume all»: «вряд ли
у юзера будет много проектов разом … если нет сложных развилок и проблем то сделай». Engines load lazily, so a project
left running did not run after a restart until something read it, then fired its overdue clock at once. Only the
serving process stops them: a stdio MCP process builds engines on the same files."""
import inspect

import gfso.cli as cli
from gfso.adapters.storage.sqlite import SqliteStorage
from gfso.config import SERVES_ENV, serves, subprocess_env
from gfso.runtime import ProjectRegistry
from tests.support import make_engine


def _registry(monkeypatch, tmp_path, serving=True):
    monkeypatch.setenv("GFSO_DATA_DIR", str(tmp_path))
    monkeypatch.delenv("GFSO_PROJECT", raising=False)
    monkeypatch.setenv(SERVES_ENV, "1") if serving else monkeypatch.delenv(SERVES_ENV, raising=False)
    return ProjectRegistry()


def test_a_project_that_stood_opens_stopped_and_one_made_after_runs(monkeypatch, tmp_path):
    make_engine(storage=SqliteStorage(str(tmp_path / "old.db"))).stop()
    reg = _registry(monkeypatch, tmp_path)
    stop = reg.engine("old").paused()
    assert stop and stop["by"] == "system" and not stop.get("until") and not stop.get("place")
    assert reg.engine("new").paused() is None, "a project made after the start runs"


def test_only_the_serving_process_stops_them(monkeypatch, tmp_path):
    make_engine(storage=SqliteStorage(str(tmp_path / "old.db"))).stop()
    assert _registry(monkeypatch, tmp_path, serving=False).engine("old").paused() is None


def test_a_person_s_stop_stays_his_and_a_start_runs_it(monkeypatch, tmp_path):
    e = make_engine(storage=SqliteStorage(str(tmp_path / "old.db")))
    e.pause("someone", "reading it")
    e.stop()
    eng = _registry(monkeypatch, tmp_path).engine("old")
    assert eng.paused()["by"] == "someone"
    eng.resume("someone")
    assert eng.paused() is None


def test_the_mark_gfso_serve_sets_is_the_one_read_and_no_child_inherits_it(monkeypatch, tmp_path):
    assert "mark_the_server()" in inspect.getsource(cli._serve), "the server marks itself on its own path"
    monkeypatch.delenv(SERVES_ENV, raising=False)
    make_engine(storage=SqliteStorage(str(tmp_path / "old.db"))).stop()
    monkeypatch.setenv("GFSO_DATA_DIR", str(tmp_path))
    monkeypatch.delenv("GFSO_PROJECT", raising=False)
    monkeypatch.setenv(SERVES_ENV, "1")   # what `mark_the_server` sets, restored after the test
    assert serves() and ProjectRegistry().engine("old").paused() is not None
    assert SERVES_ENV not in subprocess_env(), "an agent's own gfso is no server: it must not stop the live one's"


def test_a_project_made_again_after_the_start_runs(monkeypatch, tmp_path):
    st = SqliteStorage(str(tmp_path / "old.db"))
    make_engine(storage=st).stop()
    st.close()                       # …else Windows keeps the file it then deletes
    reg = _registry(monkeypatch, tmp_path)
    assert reg.engine("old").paused() is not None
    reg.delete("old")
    assert reg.engine("old").paused() is None
