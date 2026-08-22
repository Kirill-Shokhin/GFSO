"""The `gfso run` door as a script sees it: what it prints, what it narrates, what it EXITS with."""
import json
import threading

import pytest

from gfso import driver
from gfso.driver import run



def test_a_refused_verb_leaves_a_failing_exit_code(capsys):
    """Every 422 came back as rc 0, so a script proceeded past refusals.

    Measured on the human door 2026-08-21: a batch of `gfso run` calls reported success on the two
    the engine had refused, and the person only noticed because they happened to be printing bodies.
    The verbs answer rather than raise — that is about the SHAPE of the answer, not about pretending
    the act happened — and a script has only the exit code to read it by."""
    assert run(["nosuchverb"]) == 1
    assert run([]) == 0                       # …the listing is not a failure


def test_a_long_verb_narrates_itself_to_stderr(monkeypatch, capsys):
    """The door blocked on a multi-minute verb with nothing on screen.

    Measured on the agent door 2026-08-21: three and a half minutes of silence, on a server that was
    also serving someone else's run, with no way to tell a working call from a hung one. The engine
    already narrates itself into the observation field — this door simply was not listening. stderr,
    not stdout: stdout is the door's JSON, and a progress line printed into it corrupts the answer."""
    stop = threading.Event()
    stop.set()                                    # one pass, then return
    driver._narrate("wave-probe", stop)           # an unreachable server must not raise
    assert "auto_decompose" in driver._LONG_VERBS and "get_task" not in driver._LONG_VERBS


def test_a_long_argument_can_come_from_a_file(tmp_path, capsys):
    """`criteria=@file.json` is what a person reaches for when the value is longer than a shell line.

    It was passed through as the literal string "@file.json" and arrived inside the verb as a Python
    TypeError about string indices (measured on the human door 2026-08-21). Reading the file is what
    they meant, and a file that is not there is a sentence rather than a traceback."""
    src = tmp_path / "criteria.json"
    src.write_text(json.dumps([{"name": "a", "description": "b"}]), encoding="utf-8")
    assert driver._coerce(f"@{src}") == [{"name": "a", "description": "b"}]
    with pytest.raises(ValueError, match="no such file"):
        driver._coerce("@definitely-not-here.json")
    assert driver._as_list(f"@{src}") == [{"name": "a", "description": "b"}]   # …list params too
