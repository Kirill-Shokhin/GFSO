"""The diagnostic and the one-command setup — the code that decides what a first-time stranger sees.

This layer was the untested one, which is the wrong way round: everything below it exists to be
correct, and this exists to be BELIEVED. A doctor that prints a path the live server is not using,
or a setup that writes a Claude Desktop entry naming an executable that does not exist, is worse
than no diagnostic at all — it ends the search that would have found the real problem.
"""
import inspect
import json
import pathlib
import sqlite3
import sys
import sysconfig

import pytest

from gfso import __version__
from gfso import doctor as D
from gfso import serverctl
from gfso.adapters.storage.sqlite import SqliteStorage
from gfso.mcp import connect
from tests import test_distribution as TD


def test_the_console_script_it_names_is_the_one_that_exists():
    """`Path(sys.executable).parent / "gfso"` is right only inside a virtualenv.

    On a conda environment, a python.org install or `pip install --user`, scripts live in a
    `Scripts`/`bin` directory that is NOT beside the interpreter — so the guess named a file that
    does not exist, and Claude Desktop, handed it, showed a server that failed to start with no
    diagnosis. The test asserts existence, because the shape of the path is what looked right.
    """
    script = D.console_script()
    assert script.is_absolute()
    assert script.exists(), f"{script} does not exist — a Desktop entry naming it would not start"
    # …and it is THIS installation's. `shutil.which` alone named the development copy while the
    # code ran from a freshly installed venv, so the entry pointed at a different gfso entirely.
    assert script.parent == pathlib.Path(sysconfig.get_path("scripts")), (
        f"{script} is not the console script of the interpreter running this code")


def test_the_desktop_entry_names_that_script_and_this_home(tmp_path, monkeypatch):
    monkeypatch.setenv("GFSO_HOME", str(tmp_path))
    entry = D.desktop_entry()
    assert pathlib.Path(entry["command"]).exists()
    assert entry["args"] == ["connect"]
    assert entry["env"]["GFSO_HOME"] == str(tmp_path)
    json.dumps({"mcpServers": {"gfso": entry}})       # must survive a JSON encoder on any platform


def test_port_state_calls_a_closed_port_free_and_never_guesses(monkeypatch):
    """`free` and `foreign` are different facts, and the launcher used to conflate both with
    `gfso`. Driven here through a port nothing serves; the foreign branch is covered where its fix
    lives, in tests/test_ports_runtime.py."""
    monkeypatch.setattr(serverctl, "PORT", 1)                 # nothing listens on :1
    monkeypatch.setattr(serverctl, "runtime", lambda *a, **k: None)
    state, detail = D.port_state()
    assert state == "free" and "nothing is listening" in detail


def test_assets_the_doctor_checks_are_the_assets_the_packaging_test_checks():
    """Two hand-maintained lists of the same eleven files is one list too many: the day they differ,
    one of them is wrong and nothing says which."""
    ok, line = D._assets_ok()
    assert ok, line
    src = inspect.getsource(D._assets_ok)
    required = {r for r in TD.REQUIRED if not r.startswith("gfso/examples/")}
    missing_from_doctor = [r for r in required if r.split("gfso/", 1)[1] not in src]
    assert not missing_from_doctor, (
        f"the distribution test requires {missing_from_doctor} but `gfso doctor` does not check "
        f"them — an installation missing one would be reported healthy")


def test_doctor_runs_and_reports_this_installation(tmp_path, monkeypatch, capsys):
    monkeypatch.setenv("GFSO_HOME", str(tmp_path))
    code = D.doctor()
    out = capsys.readouterr().out
    assert __version__ in out
    assert str(tmp_path) in out                       # the home it would actually use
    assert "canon v4.0 is a separate line" in out     # the two version lines, said where it matters
    assert code in (0, 1)


def test_doctor_refuses_to_call_a_foreign_holder_a_server(monkeypatch, capsys):
    monkeypatch.setattr(D, "port_state", lambda: ("foreign", ":8000 is held by another process"))
    assert D.doctor() == 1                            # a blocked installation exits non-zero
    assert "blocking" in capsys.readouterr().out


def test_setup_refuses_a_foreign_holder_instead_of_waiting_it_out(monkeypatch, capsys):
    """Measured before this existed: 114 seconds of silence, then a success line quoting a code
    fingerprint for a process that did not exist."""
    monkeypatch.setattr(D, "port_state", lambda: ("foreign", ":8000 is held by another process"))
    assert D.setup() == 1
    assert "held by another process" in capsys.readouterr().out


def test_a_database_from_a_newer_gfso_is_refused_by_name(tmp_path):
    """The silent direction of an upgrade. A newer schema used to surface as a KeyError deep inside
    a read — a blank UI — rather than as a sentence naming the cause."""
    db = tmp_path / "future.db"
    conn = sqlite3.connect(db)
    conn.execute(f"PRAGMA user_version = {SqliteStorage.SCHEMA_VERSION + 1}")
    conn.commit()
    conn.close()

    with pytest.raises(RuntimeError, match="newer gfso"):
        SqliteStorage(str(db))

    fresh = tmp_path / "fresh.db"
    SqliteStorage(str(fresh)).close()                 # and a new one is stamped, once
    got = sqlite3.connect(fresh).execute("PRAGMA user_version").fetchone()[0]
    assert got == SqliteStorage.SCHEMA_VERSION


def test_the_core_wheel_builder_still_finds_the_version():
    """`build_core.py` read the version out of `[project] version`, which became `dynamic` — and
    the closure test re-implements its staging loop, so nothing executed the script itself and the
    core wheel could not be built at all."""
    sys.path.insert(0, str(pathlib.Path(__file__).parent.parent / "packaging"))
    try:
        import build_core          # late by necessity: `packaging/` is on sys.path only from the line above
        assert build_core._main_version() == __version__
    finally:
        sys.path.pop(0)


def test_asking_whether_the_door_is_registered_cannot_restart_the_server(monkeypatch):
    """`gfso doctor` took the live server down and put its own in its place.

    `claude mcp list` STARTS every configured server to report on it, and this product's entry point
    reconciles THE one server to the probing process's environment — which inside the test suite is
    a temporary home. Measured 2026-08-22: every full suite run replaced the live server with one
    homed in a tempdir, and twice that killed a paid measurement run mid-flight. A question may not
    have that effect."""
    seen = {}

    class _Out:
        returncode, stdout = 0, "gfso: ..."

    monkeypatch.setattr(D.shutil, "which", lambda name: "claude")
    monkeypatch.setattr(D.subprocess, "run",
                        lambda argv, **kw: seen.update(env=kw.get("env") or {}) or _Out())
    assert D.mcp_registered()[0] is True
    assert seen["env"].get("GFSO_NO_RECONCILE") == "1", "the probe was allowed to reconcile"


def test_a_process_told_not_to_reconcile_reports_instead(monkeypatch):
    """…and the flag is honoured where the reconciling happens, not only where it is set."""
    monkeypatch.setenv("GFSO_NO_RECONCILE", "1")
    monkeypatch.setattr(serverctl, "runtime", lambda *a, **k: {"code_version": "OLD", "sessions": 0})
    monkeypatch.setattr(serverctl, "source_fingerprint", lambda *a, **k: "NEW")
    monkeypatch.setattr(connect, "ensure_server",
                        lambda *a, **k: pytest.fail("it started a server anyway"))
    out = connect.ensure_correct(verbose=False)
    assert out["action"] == "left-alone" and "NO_RECONCILE" in out["why"]
