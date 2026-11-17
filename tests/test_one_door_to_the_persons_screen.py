"""Whatever gfso puts on the person's screen — a page, a console, an application — goes through one door
(`gfso.adapters.children`: `open_outside`, `console`, `app`), and one setting says the screen is not to be touched
(`GFSO_NO_WINDOWS=1`). Four places opened windows on their own (the go's page past `BROWSER`, doctor's own browser call,
the sign-in console, Docker Desktop), so each measurement on an owner's busy screen found one more (2026-11-16).
CONTROL: drop the `windows_allowed()` check from any one of the three and its test below goes red; add a
`webbrowser.open` anywhere else in gfso and the last test goes red.

A child gfso starts goes through the same module (`popen`, `run`, `detached`): on Windows a console program started by a
parent with no console — the server, an agent's tool — ALLOCATES one and shows it, so each start outside the door that
carries no window flag is one more window. And the switch is read one way: `GFSO_NO_WINDOWS=on` opened windows."""
from __future__ import annotations

import ast
import os
import re
import subprocess
import sys
from pathlib import Path

import pytest

from gfso import cli, config, doctor
from gfso.adapters import children as CH

ROOT = Path(CH.__file__).resolve().parents[1]


def _quiet(monkeypatch):
    monkeypatch.setenv("GFSO_NO_WINDOWS", "1")
    ran = []
    monkeypatch.setattr(CH.subprocess, "Popen", lambda argv, **k: ran.append(("popen", list(argv), k.get("startupinfo"))))
    monkeypatch.setattr(CH.subprocess, "run", lambda argv, **k: ran.append(("run", list(argv))))
    monkeypatch.setattr(CH.webbrowser, "open", lambda url: ran.append(("webbrowser", url)))
    return ran


def test_with_no_windows_the_page_is_not_opened(monkeypatch):
    ran = _quiet(monkeypatch)
    CH.open_outside("http://127.0.0.1:8000/?project=p")
    assert ran == [], ran


def test_with_no_windows_the_application_is_not_started(monkeypatch):
    ran = _quiet(monkeypatch)
    assert CH.app(["docker", "desktop", "start"], 5) is False and ran == [], ran


@pytest.mark.parametrize("platform", [
    pytest.param("win32", marks=pytest.mark.skipif(sys.platform != "win32", reason="a borrowed win32 sends shutil.which "
                                                                                  "to _winapi, which only Windows has")),
    "darwin"])
def test_with_no_windows_the_sign_in_opens_none_and_the_person_is_told_the_steps(monkeypatch, platform):
    """Run hidden, the sign-in's console waited at a prompt nobody could see, and the agent was told a window was open
    (critic). CONTROL: start `console` hidden again under the knob and it is red."""
    ran = _quiet(monkeypatch)
    monkeypatch.setattr(doctor.sys, "platform", platform)
    # …`sys` is the interpreter's: sysconfig loaded under a borrowed platform looks for that platform's data (Linux CI)
    monkeypatch.setattr(doctor, "console_script", lambda: Path("gfso"))
    monkeypatch.setattr(sys, "argv", ["gfso", "credential", "claude", "--sign-in"])
    with pytest.raises(SystemExit) as done:
        cli.main()
    assert ran == [] and "no window to open here" in str(done.value.code), (ran, done.value.code)


@pytest.mark.skipif(os.name == "nt", reason="process groups are POSIX's")
def test_ending_a_child_never_ends_this_process_group(monkeypatch):
    """A fake child's pid 0 made `killpg(0)` — this process's own group: on Linux CI pytest and the runner died with it
    and the job hung to its timeout with no log. A `shown` child leads no group, so its pid names none to end.
    CONTROL: drop the `pgid <= 0` guard, or the `_IN_THE_TERMINAL` check, and it is red."""
    hit = []
    monkeypatch.setattr(CH.os, "killpg", lambda pgid, sig: hit.append(pgid), raising=False)
    CH._kill_group(0)
    CH._kill_group(4321)
    shown = type("P", (), {"pid": 77, "poll": lambda self: 0})()
    CH._IN_THE_TERMINAL.add(shown)
    CH.kill_tree(shown)
    assert hit == [4321], hit


def test_nothing_else_in_gfso_opens_a_window():
    """The door's invariant read off the source: a browser call, a file opened by the shell, a `start`, a new console —
    only in the door (the server's own console in `mcp/connect.py` is started hidden, SW_HIDE, and opens nothing)."""
    pattern = re.compile(r"webbrowser\.open|os\.startfile|\"start\", \"\"|creationflags=NEW_CONSOLE|osascript")
    found = [f"{p.relative_to(ROOT)}:{n}" for p in ROOT.rglob("*.py") if p.name != "children.py"
             for n, line in enumerate(p.read_text(encoding="utf-8").splitlines(), 1)
             if pattern.search(line) and not line.lstrip().startswith("#") and "app([" not in line]
    assert found == [], found


@pytest.mark.parametrize("word, on", [("1", True), ("on", True), ("Yes", True), ("TRUE", True),
                                      ("0", False), ("off", False), ("no", False), ("false", False), ("", False)])
def test_a_switch_is_read_one_way(monkeypatch, word, on):
    """`GFSO_NO_WINDOWS=on` opened windows, `GFSO_OPEN_PAGE=false` opened the page: five readings of an on/off switch.
    CONTROL: put back `windows_allowed`'s own reading (1/true/yes) and `on` is red."""
    monkeypatch.setenv("GFSO_NO_WINDOWS", word)
    monkeypatch.setenv("GFSO_OPEN_PAGE", word)
    monkeypatch.delenv("GFSO_BIND", raising=False)
    assert config.windows_allowed() is not on and config.opens_the_page() is on
    ran = []
    monkeypatch.setattr(CH.webbrowser, "open", lambda url: ran.append(url))
    monkeypatch.setattr(CH.subprocess, "Popen", lambda argv, **k: ran.append(argv))
    CH.open_outside("http://127.0.0.1:8000/")
    assert bool(ran) is not on, ran


def test_a_switch_set_to_no_word_of_it_is_refused_by_name(monkeypatch):
    monkeypatch.setenv("GFSO_NO_WINDOWS", "maybe")
    with pytest.raises(ValueError, match="GFSO_NO_WINDOWS='maybe'.*1/true/yes/on or 0/false/no/off"):
        config.windows_allowed()


class _Proc:
    pid, returncode = 0, 0

    def __init__(self, argv, **kw):
        _Proc.seen.append((list(argv), kw))

    def communicate(self, input=None, timeout=None):
        return "", ""

    poll = wait = kill = lambda self, *a: 0


@pytest.fixture
def started(monkeypatch):
    _Proc.seen = []
    monkeypatch.setattr(subprocess, "Popen", _Proc)
    return _Proc.seen


@pytest.mark.skipif(os.name != "nt", reason="a console window is Windows' alone")
def test_what_doctor_runs_opens_no_console(monkeypatch, started):
    """`gfso doctor` runs from an agent's tool, a parent with no console: each of its ten `claude`/`docker` runs went past
    the door with no window flag. CONTROL: drop `popen`'s CREATE_NO_WINDOW and it is red."""
    monkeypatch.setattr(doctor.shutil, "which", lambda name: name)
    doctor.claude_cli()
    doctor.docker_state()
    doctor.image_present("img")
    assert [a[0] for a, _ in started] == ["claude", "docker", "docker"], started
    assert all(kw["creationflags"] == subprocess.CREATE_NO_WINDOW for _, kw in started), started


@pytest.mark.skipif(os.name != "nt", reason="a console window is Windows' alone")
def test_a_build_left_running_holds_a_console_nobody_sees(monkeypatch, started, tmp_path):
    """The image build outlives setup: started with no console, every console program under it would open one; under a
    hidden console of its own they attach to it (`detached`, as the shared server is started)."""
    monkeypatch.setenv("GFSO_NO_WINDOWS", "0")
    doctor._spawn_build("img", tmp_path / "build.log")
    ((_, kw),) = started
    assert kw["creationflags"] & 0x10 and kw["startupinfo"].wShowWindow == 0, kw


@pytest.mark.skipif(os.name != "nt", reason="a console window is Windows' alone")
@pytest.mark.parametrize("console, flags", [(1, 0), (0, 0x08000000)])   # CREATE_NO_WINDOW: Windows' name, read at collection
def test_a_program_shown_to_the_person_runs_in_their_console_and_makes_none(monkeypatch, started, console, flags):
    """`claude setup-token` in the sign-in's window, an install's progress: in this process's console where it has one,
    no window made for it where it has none."""
    monkeypatch.setattr(CH.ctypes, "WinDLL", lambda name: type("K", (), {"GetConsoleWindow": lambda: console}))
    CH.run(["claude", "setup-token"], timeout=None, shown=True)
    ((_, kw),) = started
    assert kw["creationflags"] == flags and kw["stdout"] is None and kw["stdin"] is None, kw


#: files whose code runs in no process of the person's screen: a container's listener, git's filter in a container
ELSEWHERE = {"adapters/shell.py", "adapters/lfs.py"}
STARTS = {"Popen", "run", "call", "check_call", "check_output"}
FLAGS = {"creationflags", "startupinfo", "start_new_session"}


def _past_the_door(path: Path) -> list[str]:
    """A start of a child, or a window flag, written past `children`."""
    out = []
    for n in ast.walk(ast.parse(path.read_text(encoding="utf-8-sig"))):
        if isinstance(n, ast.Call) and isinstance(n.func, ast.Attribute) and isinstance(n.func.value, ast.Name) \
                and n.func.value.id == "subprocess" and n.func.attr in STARTS:
            out.append(f"subprocess.{n.func.attr}:{n.lineno}")
        if isinstance(n, ast.Call):
            out += [f"{k.arg}=:{n.lineno}" for k in n.keywords if k.arg in FLAGS]
        if isinstance(n, ast.Attribute) and isinstance(n.value, ast.Name) and n.value.id == "subprocess"                 and (n.attr.startswith("CREATE_") or n.attr == "STARTUPINFO"):
            out.append(f"{n.attr}:{n.lineno}")
    return out


def test_every_child_of_gfso_starts_through_the_door():
    """CONTROL: a bare `subprocess.run([...])` added to `doctor.py` is red."""
    found = {f: got for p in ROOT.rglob("*.py") if (f := p.relative_to(ROOT).as_posix()) not in ELSEWHERE
             and p.name != "children.py" and (got := _past_the_door(p))}
    assert found == {}, found


def test_the_door_guard_sees_a_start_and_a_flag(tmp_path):
    (p := tmp_path / "m.py").write_text("import subprocess\nsubprocess.run(['x'])\nPopen(['y'], creationflags=8)\n")
    assert _past_the_door(p) == ["subprocess.run:2", "creationflags=:3"]


@pytest.mark.skipif(os.name == "nt", reason="a process group is POSIX's")
def test_a_program_the_person_works_in_stays_in_their_terminals_session(started):
    """In a session of its own, `claude setup-token` got no Ctrl-C and left the terminal raw (critic): only a child no
    one works in gets a group of its own. CONTROL: give `shown` runs `spawn_kw` again and it is red."""
    CH.run(["claude", "setup-token"], timeout=None, shown=True)
    CH.run(["git", "status"], timeout=5)
    (_, shown), (_, kept) = started
    assert "start_new_session" not in shown and kept["start_new_session"] is True, started
