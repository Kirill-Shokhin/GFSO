"""A server's start leaves every project that stood, where the system carries its work, stopped until its Start
(PROJECT_CLOCK.md case 16); a graph people hold runs on — its deadlines are the people's, never suspended (§12.2).

The author, 2026-10-29: «разве они не должны все в стопед переводиться автоматически?» — and, on a «resume all»: «вряд ли
у юзера будет много проектов разом … если нет сложных развилок и проблем то сделай». Engines load lazily, so a project
left running did not run after a restart until something read it, then fired its overdue clock at once. Only the
serving process stops them: a stdio MCP process builds engines on the same files."""
import inspect
import json

import gfso.cli as cli
from gfso.adapters.storage.sqlite import SqliteStorage
from gfso.config import SERVES_ENV, serves, subprocess_env
from gfso.runtime import HELD_AT_START, ProjectRegistry
from tests.support import make_engine


def _stood(path, mode: str | None = "auto"):
    """A project that stood when the server started; with a mode, the system carries its work."""
    e = make_engine(storage=SqliteStorage(str(path)))
    if mode:
        e.graph.store_setting("mode", json.dumps({"mode": mode}))
    e.stop()
    return e


def _registry(monkeypatch, tmp_path, serving=True):
    monkeypatch.setenv("GFSO_DATA_DIR", str(tmp_path))
    monkeypatch.delenv("GFSO_PROJECT", raising=False)
    monkeypatch.setenv(SERVES_ENV, "1") if serving else monkeypatch.delenv(SERVES_ENV, raising=False)
    return ProjectRegistry()


def test_a_project_that_stood_opens_stopped_and_one_made_after_runs(monkeypatch, tmp_path):
    _stood(tmp_path / "old.db")
    reg = _registry(monkeypatch, tmp_path)
    stop = reg.engine("old").paused()
    assert stop and stop["by"] == "system" and not stop.get("until") and not stop.get("place")
    assert reg.engine("new").paused() is None, "a project made after the start runs"


def test_only_the_serving_process_stops_them(monkeypatch, tmp_path):
    _stood(tmp_path / "old.db")
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
    _stood(tmp_path / "old.db")
    monkeypatch.setenv("GFSO_DATA_DIR", str(tmp_path))
    monkeypatch.delenv("GFSO_PROJECT", raising=False)
    monkeypatch.setenv(SERVES_ENV, "1")   # what `mark_the_server` sets, restored after the test
    assert serves() and ProjectRegistry().engine("old").paused() is not None
    assert SERVES_ENV not in subprocess_env(), "an agent's own gfso is no server: it must not stop the live one's"


def test_a_project_made_again_after_the_start_runs(monkeypatch, tmp_path):
    st = _stood(tmp_path / "old.db").graph._storage
    st.close()                       # …else Windows keeps the file it then deletes
    reg = _registry(monkeypatch, tmp_path)
    assert reg.engine("old").paused() is not None
    reg.delete("old")
    assert reg.engine("old").paused() is None


def test_the_list_says_a_project_that_stood_is_stopped_before_it_is_opened(monkeypatch, tmp_path):
    """Its file says nothing of the stop until its first opening makes it, and the project list read it running."""
    _stood(tmp_path / "old.db")
    e = make_engine(storage=SqliteStorage(str(tmp_path / "held.db")))
    e.pause("someone", "reading it")
    e.stop()
    reg = _registry(monkeypatch, tmp_path)
    about = reg.about(["old", "held"])
    assert about["old"]["stopped"]["by"] == "system", "a project that stood is listed stopped before it is opened"
    assert about["held"]["stopped"]["by"] == "someone", "a stop already on file is said as it stands"
    reg.engine("old").resume("someone")
    assert reg.about(["old"])["old"]["stopped"] is None, "opened and started, it is listed running"
    assert _registry(monkeypatch, tmp_path, serving=False).about(["held", "old"])["old"]["stopped"] is None


def test_a_graph_people_hold_runs_on_at_the_server_s_start(monkeypatch, tmp_path):
    """The author, 2026-11-15: «там очевидно и часы вести не для кого» — no mode and no node a machine holds: nothing of
    the system's runs there, and a stop would only stand the people's deadlines still."""
    _stood(tmp_path / "people.db", mode=None)
    reg = _registry(monkeypatch, tmp_path)
    assert reg.about(["people"])["people"]["stopped"] is None, "listed running before it is opened"
    assert reg.engine("people").paused() is None, "opened running"


def test_the_stop_an_earlier_start_left_on_a_people_s_graph_comes_off(monkeypatch, tmp_path):
    """A graph people hold, stopped by an earlier server's start before it was told apart: nobody made that stop, and it
    stood their deadlines still — the author's graphs kept it (critic, 2026-11-15). A person's own stop stays his."""
    for name, by in (("people", "system"), ("own", "someone")):
        e = make_engine(storage=SqliteStorage(str(tmp_path / f"{name}.db")))
        e.pause(by, HELD_AT_START if by == "system" else "reading it")
        e.stop()
    reg = _registry(monkeypatch, tmp_path)
    assert reg.about(["people"])["people"]["stopped"] is None, "listed as its opening will leave it"
    assert reg.engine("people").paused() is None, "the start's stop comes off at its opening"
    assert reg.engine("own").paused()["by"] == "someone", "a person's stop is never lifted for him"
