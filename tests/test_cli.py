"""The `gfso run` door as a script sees it: what it prints, what it narrates, what it EXITS with."""
import json
import re
import threading

import pytest

from gfso import driver
from gfso.config import agent_id
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


def test_the_help_says_what_the_callers_own_id_is(capsys):
    """A person at this door was invited to name themselves and then refused for doing it.

    Measured on the human door 2026-09-01: `next_step` reported `"assignee": "agent", "mine": true`,
    `signal --help` said a person names themselves, so the tester sent `source=w18c-human` and was
    told `w18c-human is not executor for root (executor=agent)`. The refusal is right; the
    invitation before it was the defect — a graph built by `auto_decompose` assigns every node to
    the literal id `agent`, and nothing said that this door's caller IS `agent`."""
    assert run(["signal", "--help"]) == 0
    out = capsys.readouterr().out
    assert agent_id() in out and "auto_decompose" in out
    assert "your id at this door" in out.lower()
    # …and the case where a person really does name themselves survives (nodes they assigned).
    assert "assignee" in out and "reassign" in out


def test_the_listing_shows_the_project_argument_every_command_takes(capsys):
    """`gfso run` listed thirty command names and not one of them showed `project=`.

    Measured on the human door 2026-09-01: the hard rule for anything multi-project is to pass the
    project explicitly, and the listing — the first thing anybody reads — hid it while the
    per-command `--help` showed it."""
    assert run([]) == 0
    lines = [ln for ln in capsys.readouterr().out.splitlines() if ln.startswith("  ")]
    assert lines, "the listing printed no commands"
    assert all("project=" in ln for ln in lines), \
        [ln for ln in lines if "project=" not in ln]


def test_edit_criteria_help_shows_the_object_and_warns_it_replaces(capsys):
    """`edit_criteria` takes an object shape documented nowhere.

    Measured on the human door 2026-09-01: `--help` said `<criteria>` and the listing said "a nested
    one wants an object, not a word", but never WHICH object — the tester guessed
    `[{"name": …, "description": …}]` and got lucky — and nothing warned that the call REPLACES the
    set, which nearly cost the hand-rebuilt node its dependency criteria."""
    assert run(["edit_criteria", "--help"]) == 0
    out = capsys.readouterr().out
    example = re.search(r"\[\s*\{.*?\}\s*\]", out, re.S)
    assert example, "the help shows no concrete criteria object"
    parsed = json.loads(re.sub(r"\s+", " ", example.group(0)))
    assert isinstance(parsed, list) and {"name", "description"} <= set(parsed[0])
    assert "REPLACE" in out and "dep__" in out


def test_an_unreadable_file_argument_answers_in_words(tmp_path, capsys):
    """Every `@file` refusal came back as a TypeError traceback above the sentence it had written.

    `_parse_args` printed its refusal and returned `1` out of a function whose contract is a triple,
    so `run` unpacked an int and crashed — for a missing file and, once a broken one started being
    named, for that too (found 2026-09-06 while making a broken JSON file say which file it was).
    A door that refuses has to refuse in its own shape, and with a non-zero exit code.
    """
    broken = tmp_path / "criteria.json"
    broken.write_text('{"broken": ', encoding="utf-8")

    assert run(["create_task", f"spec=@{broken}"]) == 1
    said = capsys.readouterr().out
    assert "does not parse as JSON" in said and broken.name in said, (
        "the sentence has to name the FILE — the whole point of the refusal")
    assert "Traceback" not in said

    assert run(["create_task", "spec=@definitely-not-here.json"]) == 1
    assert "no such file" in capsys.readouterr().out
