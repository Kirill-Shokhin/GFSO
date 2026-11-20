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
import subprocess
import sys
import sysconfig
import threading

import pytest

from gfso import __version__
from gfso import config as _config
from gfso import doctor as D
from gfso.adapters import execution as E
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


@pytest.mark.no_model_path          # it probes the CLI; in the suite the probe fails as a missing CLI does
def test_doctor_runs_and_reports_this_installation(tmp_path, monkeypatch, capsys):
    monkeypatch.setenv("GFSO_HOME", str(tmp_path))
    code = D.doctor()
    out = capsys.readouterr().out
    assert __version__ in out
    assert str(tmp_path) in out                       # the home it would actually use
    assert "canon v4.1 is a separate line" in out     # the two version lines, said where it matters
    assert code in (0, 1)


@pytest.mark.no_model_path          # it probes the CLI; in the suite the probe fails as a missing CLI does
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


NEW_SESSION = "`/exit`, then `claude -c`"


def _setup_with(monkeypatch, capsys, exe="claude", add=(0, ""), get="") -> tuple[str, list]:
    """What `setup` prints, and the calls it made of a fake CLI whose `mcp list` shows `gfso` — as it does inside a project
    holding a local-scope entry, the list naming no scope — whose `mcp add` ends as `add` says until an entry is removed,
    and whose `mcp get` prints `get`."""
    calls = []

    def run(argv, **kw):
        calls.append(argv)
        removed = any(c[1:3] == ["mcp", "remove"] for c in calls)
        rc, err = add if argv[1:3] == ["mcp", "add"] and not removed else (0, "")
        out = get if argv[1:3] == ["mcp", "get"] else "gfso: gfso connect - connected"
        return type("R", (), {"returncode": rc, "stdout": out, "stderr": err})

    monkeypatch.setattr(D.shutil, "which", lambda name: exe)
    monkeypatch.setattr(D.children, "run", run)
    monkeypatch.setattr(D, "port_state", lambda: ("free", "nothing is listening"))
    monkeypatch.setattr(D, "open_outside", lambda url: None)
    monkeypatch.setattr(D, "desktop_config_path", lambda: None)
    monkeypatch.setattr(D, "install_execution", lambda: "agent image: x")
    monkeypatch.setattr(D, "doctor", lambda: print("the doctor's table") or 0)
    monkeypatch.setattr("gfso.mcp.connect.ensure_correct", lambda *a, **k: {"action": "none"})
    assert D.setup() == 0
    return capsys.readouterr().out, calls


def test_a_local_entry_does_not_stand_for_the_users(monkeypatch, capsys):
    """`"gfso" in stdout` read a project's local entry as the door, and every other directory had none."""
    out, calls = _setup_with(monkeypatch, capsys)
    assert any(c[1:5] == ["mcp", "add", "--scope", "user"] for c in calls), calls
    assert "registered for your user" in out


def test_setup_ends_by_saying_where_the_door_is(monkeypatch, capsys):
    out, _ = _setup_with(monkeypatch, capsys)
    assert out.rindex(NEW_SESSION) > out.rindex("the doctor's table"), out
    assert "An open session has no gfso tools" in out


def test_a_users_entry_already_there_is_said_as_that(monkeypatch, capsys):
    out, _ = _setup_with(monkeypatch, capsys, add=(1, "MCP server gfso already exists in user config"))
    assert "already registered for your user" in out and "could not register" not in out and NEW_SESSION in out, out


@pytest.mark.parametrize("exe, add", [("claude", (1, "boom")), (None, (0, ""))])
def test_no_door_is_promised_where_none_was_registered(monkeypatch, capsys, exe, add):
    out, _ = _setup_with(monkeypatch, capsys, exe, add)
    assert NEW_SESSION not in out, out


EXISTS = (1, "MCP server gfso already exists in user config")


def _entry(scope, command):
    return f"gfso:\n  Scope: {scope}\n  Status: x\n  Type: stdio\n  Command: {command}\n  Args: connect\n"


def test_a_users_entry_naming_another_installation_comes_to_this_one(monkeypatch, capsys):
    """`already exists` read as the door, while the entry started a removed venv or the developer's server: a person's
    "clean install" then ran on what it was meant to replace."""
    out, calls = _setup_with(monkeypatch, capsys, add=EXISTS, get=_entry("User config (all projects)", "C:/old/gfso.exe"))
    assert ["claude", "mcp", "remove", "gfso", "-s", "user"] in calls, calls
    added = [c for c in calls if c[1:3] == ["mcp", "add"]]
    assert len(added) == 2 and added[-1][-2:] == [str(D.console_script()), "connect"], calls
    assert "C:/old/gfso.exe" in out and NEW_SESSION in out, out


def test_a_server_on_another_address_is_named_in_the_entry(monkeypatch, capsys):
    """A client started without the variable went to the default port, past the server set up here."""
    monkeypatch.setenv("GFSO_SHARED_URL", "http://127.0.0.1:18000/mcp")
    _, calls = _setup_with(monkeypatch, capsys)
    add = next(c for c in calls if c[1:3] == ["mcp", "add"])
    assert add[add.index("-e") + 1] == "GFSO_SHARED_URL=http://127.0.0.1:18000/mcp" and add.index("-e") > add.index("gfso")


def test_a_replaced_entry_keeps_what_the_person_set_on_it(monkeypatch, capsys):
    held = _entry("User config (all projects)", "C:/old/gfso.exe") + "  Environment:\n    GFSO_HOME=C:/mine\n\nTo remove\n"
    _, calls = _setup_with(monkeypatch, capsys, add=EXISTS, get=held)
    assert "GFSO_HOME=C:/mine" in [c for c in calls if c[1:3] == ["mcp", "add"]][-1], calls


def test_an_entry_on_another_address_comes_to_this_one(monkeypatch, capsys):
    """Only a first add wrote the address: a later `setup` left the client on the old server under "already registered"."""
    monkeypatch.setenv("GFSO_SHARED_URL", "http://127.0.0.1:18000/mcp")
    _, calls = _setup_with(monkeypatch, capsys, add=EXISTS, get=_entry("User config (all projects)", D.console_script()))
    assert "GFSO_SHARED_URL=http://127.0.0.1:18000/mcp" in [c for c in calls if c[1:3] == ["mcp", "add"]][-1], calls


def test_an_entry_that_could_not_come_back_says_the_command(monkeypatch, capsys):
    calls = []

    def run(argv, **kw):
        calls.append(argv)
        out = _entry("User config (all projects)", "C:/old/gfso.exe") if argv[1:3] == ["mcp", "get"] else ""
        return type("R", (), {"returncode": 1 if argv[1:3] == ["mcp", "add"] else 0, "stdout": out,
                              "stderr": EXISTS[1] if len(calls) == 1 else "boom"})
    monkeypatch.setattr(D.children, "run", run)
    assert D._register_door("claude") is False
    assert "claude mcp add --scope user gfso" in capsys.readouterr().out


def test_a_users_entry_naming_this_installation_is_left_alone(monkeypatch, capsys):
    """An entry may carry the person's own environment: only one that starts something else is replaced."""
    _, calls = _setup_with(monkeypatch, capsys, add=EXISTS, get=_entry("User config (all projects)", D.console_script()))
    assert not any(c[1:3] == ["mcp", "remove"] for c in calls), calls


def test_a_directorys_own_entry_is_said_not_removed(monkeypatch, capsys):
    """Here it goes before the user's, and it is the directory's, not this command's, to drop — and setup's last line no
    longer promises a restart's tools: a session started here has the other installation's."""
    out, calls = _setup_with(monkeypatch, capsys, get=_entry("Local config (private to you in this project)", "C:/old/gfso.exe"))
    assert not any(c[1:3] == ["mcp", "remove"] for c in calls), calls
    assert "claude mcp remove gfso -s local" in out and NEW_SESSION not in out, out


@pytest.mark.parametrize("scope, command, expected, said", [
    ("Local config (private to you in this project)", "C:/old/gfso.exe", False, "claude mcp remove gfso -s local"),
    ("User config (all projects)", "C:/old/gfso.exe", False, "`gfso setup` registers this one"),
    ("User config (all projects)", None, True, "registered"),
])
def test_the_doctor_reads_the_entry_a_session_here_starts(monkeypatch, scope, command, expected, said):
    """A stale entry connects: read by its line alone it was "registered" while a session here started another
    installation."""
    command = command or str(D.console_script())
    monkeypatch.setattr(D.shutil, "which", lambda name: "claude")
    monkeypatch.setattr(D.children, "run", lambda argv, **kw: type("R", (), {"returncode": 0, "stdout": (
        _entry(scope, command) if argv[1:3] == ["mcp", "get"] else f"gfso: {command} connect - ✓ Connected")}))
    ok, line = D.mcp_registered()
    assert ok is expected and said in line, line


@pytest.mark.parametrize("listing, expected", [
    ("my-gfso-tools: python -c pass - ✓ Connected", False),
    ("gfso: /gone/gfso.exe connect - ✘ Failed to connect", False),
    ("other: gfso connect - ✓ Connected\ngfso: gfso.exe connect - ✓ Connected", True),
])
def test_the_doctor_reads_the_door_by_its_name_and_its_connection(monkeypatch, listing, expected):
    monkeypatch.setattr(D.shutil, "which", lambda name: "claude")
    monkeypatch.setattr(D.children, "run", lambda argv, **kw: type("R", (), {"returncode": 0, "stdout": listing}))
    assert D.mcp_registered()[0] is expected


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
    monkeypatch.setattr(D.children, "run",
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


def test_the_end_of_setup_says_what_is_left_for_the_person(monkeypatch, capsys):
    """Told "installed", a fresh client stopped before setup, and after it handed the person steps they had to ask for
    (2026-11-08); under one heading "tell the person", the client told the person --sign-in instead of running it
    (11-09): the commands are its own to run, the new session the person's to know, and "Installed." waits for the token."""
    monkeypatch.setattr(D.credentials, "held", lambda: [])
    out, _ = _setup_with(monkeypatch, capsys)
    do, tell = out.split("Do now yourself, without asking:", 1)[1].split("Tell the person:", 1)
    assert "gfso credential claude --sign-in" in do and "--wait" in do and "never in the chat" in do and "gfso demo human_only" in do
    assert NEW_SESSION in tell and "--sign-in" not in tell and "Installed." not in out
    monkeypatch.setattr(D.credentials, "held", lambda: ["a-token"])
    out, _ = _setup_with(monkeypatch, capsys)
    do = out.split("Do now yourself, without asking:", 1)[1]
    assert "--sign-in" not in do and "gfso demo human_only" in do and "Installed." in out


def test_no_person_is_told_of_a_door_setup_did_not_make(monkeypatch, capsys):
    monkeypatch.setattr(D.credentials, "held", lambda: ["a-token"])
    out, _ = _setup_with(monkeypatch, capsys, exe=None)
    assert "Tell the person:" not in out and "Do now yourself, without asking:" in out


def test_doctor_ends_on_ready_or_on_what_is_left(monkeypatch, capsys):
    """A verdict a client can quote: the last line, ready or how many things are left and which."""
    _doctor_with(monkeypatch, held=["a-token"])
    assert D.doctor() == 0
    assert capsys.readouterr().out.rstrip().splitlines()[-1] == "ready"
    _doctor_with(monkeypatch, held=[])
    assert D.doctor() == 0, "no credential does not block the machine, it is left to do"
    assert capsys.readouterr().out.rstrip().splitlines()[-1] == "1 thing left: a credential (`gfso credential claude --sign-in`)"
    _doctor_with(monkeypatch, held=[], blocking=["a thing that blocks"])
    assert D.doctor() == 1
    assert capsys.readouterr().out.rstrip().splitlines()[-1] == "2 things left: a thing that blocks; a credential (`gfso credential claude --sign-in`)"


def _doctor_with(monkeypatch, held, blocking=()):
    monkeypatch.setattr(D, "_execution_report", lambda: ([("docker", "ok")], list(blocking)))
    monkeypatch.setattr(D, "port_state", lambda: ("free", "nothing is listening"))
    monkeypatch.setattr(D, "claude_cli", lambda: (True, "present"))
    monkeypatch.setattr(D, "mcp_registered", lambda: (True, "registered"))
    monkeypatch.setattr(D, "_live_server_report", lambda *a: ({}, [], []))
    monkeypatch.setattr(D, "local_word", lambda: False)
    monkeypatch.setattr(D.credentials, "held", lambda: held)


@pytest.mark.parametrize("platform, starts", [("win32", True), ("darwin", True), ("linux", False)])
def test_setup_starts_an_installed_docker_desktop_whose_daemon_is_down(monkeypatch, platform, starts):
    """A Docker installed and not running stopped a fresh client on a step a command does; Docker Engine on Linux starts
    under sudo, so there it is only said."""
    ran, states = [], iter([(True, "engine 29")])
    monkeypatch.setenv("GFSO_NO_WINDOWS", "0")              # …nothing is started: the run is a fake
    monkeypatch.setattr(D.sys, "platform", platform)
    monkeypatch.setattr(D.shutil, "which", lambda name: "docker")
    monkeypatch.setattr(D.children, "run", lambda argv, **kw: ran.append(argv))
    monkeypatch.setattr(D, "docker_state", lambda: next(states))
    assert D.start_docker(5) is starts
    assert (ran == [["docker", "desktop", "start", "--timeout", "5"]]) is starts


def test_doctor_names_the_command_that_installs_docker_here(monkeypatch):
    monkeypatch.setattr(D.shutil, "which", lambda name: None)
    monkeypatch.setattr(D.sys, "platform", "win32")
    assert "winget install -e --id Docker.DockerDesktop" in D.docker_state()[1]


def test_a_moved_state_directory_holds_the_declaration_the_server_reads(tmp_path, monkeypatch):
    """With `GFSO_DATA_DIR` set, `serve.json` was written under the home and read from the state directory: a
    switch the person declared was in force nowhere (ortho audit F16). CONTROL: compose `declared_path` from the home
    again and it is red."""
    monkeypatch.setenv("GFSO_HOME", str(tmp_path / "home"))
    monkeypatch.setenv("GFSO_DATA_DIR", str(tmp_path / "elsewhere"))
    monkeypatch.delenv("GFSO_NETWORK_RECORD", raising=False)
    serverctl.declare("GFSO_NETWORK_RECORD", "off")
    assert _config.network_record_off() and serverctl.declared()["GFSO_NETWORK_RECORD"] == "off"


def test_a_declaration_written_while_it_is_read_lands_whole(tmp_path, monkeypatch):
    """A reader holding `serve.json` for an instant refused a write over it on Windows, and a write in place left it
    empty to every reader meanwhile: written beside and moved over, the move waited for (`config.write_atomic`).
    CONTROL: drop the retry and it is red on Windows."""
    monkeypatch.setenv("GFSO_DATA_DIR", str(tmp_path))
    serverctl.declare("A", "1")
    held = open(serverctl.declared_path(), encoding="utf-8")
    threading.Timer(0.2, held.close).start()
    serverctl.declare("B", "2")
    assert json.loads(serverctl.declared_path().read_text(encoding="utf-8")) == {"A": "1", "B": "2"}
    assert [p.name for p in tmp_path.iterdir()] == ["serve.json"], "a temporary was left"


def test_doctor_and_every_execution_ask_docker_one_question(monkeypatch):
    """"Is Docker up" was decided three times with three timeouts and three readings of its failure (ortho audit F13):
    doctor and an execution's refusal read one `docker_server`."""
    down = "failed to connect to the docker API at npipe:////./pipe/dockerDesktopLinuxEngine"
    monkeypatch.setattr(D.shutil, "which", lambda name: "docker")
    monkeypatch.setattr(E, "run", lambda args, **kw: subprocess.CompletedProcess(args, 1, "", down))
    assert D.docker_state() == (False, f"installed, its daemon does not answer — start Docker (docker): {down}")
    assert E._unavailable(None, storage=False) == down
    monkeypatch.setattr(E, "run", lambda args, **kw: subprocess.CompletedProcess(args, 0, "28.0.0|Docker Desktop 4.43.0", ""))
    assert "CVE-2025-9074" in D.docker_state()[1] and D.docker_state()[1] == E._unavailable(None, storage=False)


@pytest.mark.parametrize("declared, exported, served, drifted", [
    ("1", None, False, True), ("1", None, True, False), ("0", "1", True, True), (None, "1", False, False),
    (None, None, True, False)])
def test_a_server_whose_screen_is_not_the_installations_has_drifted(monkeypatch, declared, exported, served, drifted):
    """The screen is its owner's: `gfso up` restarts a server whose knob is not what the installation declares
    (serve.json), and a connecting client's own export never does — one restarted an idle server under its own knob and
    the next go would have put a page on the owner's screen (2026-11-17). CONTROL: drop the screen from `drift`, or read
    the export there, and it is red."""
    monkeypatch.delenv("GFSO_NO_WINDOWS", raising=False)
    if exported:
        monkeypatch.setenv("GFSO_NO_WINDOWS", exported)
    monkeypatch.setattr(serverctl, "declared", lambda: {} if declared is None else {"GFSO_NO_WINDOWS": declared})
    rt = {"version": __version__, "code_version": "f", "no_windows": served}
    assert any("no_windows" in d for d in serverctl.drift(rt, {"GFSO_AGENTS_PATH": ""}, "f")) is drifted


@pytest.mark.skipif(sys.platform == "win32", reason="POSIX mode bits")
def test_a_file_written_over_keeps_its_mode(tmp_path):
    """Replaced by a new file, a 0600 declaration came back readable by everyone (critic). CONTROL: drop the mode's
    carry in `write_atomic` and it is red."""
    (p := tmp_path / "serve.json").write_text("{}")
    p.chmod(0o600)
    _config.write_atomic(p, '{"A": "1"}')
    assert p.stat().st_mode & 0o777 == 0o600 and p.read_text() == '{"A": "1"}'
    _config.write_atomic(fresh := tmp_path / "new.json", "x", 0o600)
    assert fresh.stat().st_mode & 0o777 == 0o600


def test_setup_says_it_starts_no_docker_where_no_window_may_open(monkeypatch, capsys):
    """With no windows allowed `app` runs nothing, yet setup printed «starting Docker Desktop», and a fresh client told the
    person a start was tried and failed (s24g1)."""
    ran = []
    monkeypatch.setenv("GFSO_NO_WINDOWS", "1")
    monkeypatch.setattr(D.sys, "platform", "win32")
    monkeypatch.setattr(D.shutil, "which", lambda name: "docker")
    monkeypatch.setattr(D.children, "run", lambda argv, **kw: ran.append(argv))
    monkeypatch.setattr(D, "docker_state", lambda: (False, "its daemon does not answer"))
    assert D.start_docker(5) is False and ran == []
    out = capsys.readouterr().out
    assert "starting" not in out and "not started from here" in out, out
