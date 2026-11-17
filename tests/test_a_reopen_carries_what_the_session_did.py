"""A session reopened on a handover is handed, beside the note, what the last session did as its own tool calls record
it: the files it read and changed with the last range of each, and the last commands it ran that do more than look,
with their exit status (E4, variant C). The record is the system's — a call that failed did nothing to the place and is
not in it — and each session's starts empty.

CONTROLS: drop the `RECORD + done` term from `budget._reopen` and the wiring test goes red; drop the `note_session`
call from `RecordingProvider.note_tools` and the stream test goes red.
"""
from __future__ import annotations

from gfso.adapters.llm import budget as B
from gfso.adapters.llm import headless as H
from gfso.adapters.llm.session_record import SessionRecord
from tests.test_a_session_hands_over_at_its_context_budget import Worker


def _use(i, name, **inp):
    return {"type": "tool_use", "id": i, "name": name, "input": inp}


def _res(i, text, error=False):
    return {"type": "tool_result", "tool_use_id": i, "content": text, "is_error": error}


def _fed(*calls) -> SessionRecord:
    """`calls`: (tool_use, tool_result[, the event's tool_use_result])."""
    r = SessionRecord()
    for u, x, *detail in calls:
        r.use(u)
        r.result(x, *detail)
    return r


#: the CLI's own words, as real traces carry them
EDITED = "The file src/sema.c has been updated successfully."
REFUSED = "Permission to use Bash with command python wipe.py has been denied."


def test_the_record_names_what_was_read_changed_and_run():
    r = _fed((_use("1", "Read", file_path="src/sema.c", offset=40, limit=3), _res("1", "    40→a")),
             (_use("2", "Edit", file_path="src/sema.c"), _res("2", EDITED),
              {"structuredPatch": [{"newStart": 55, "newLines": 6}]}),
             (_use("3", "Bash", command="cd build && make test"), _res("3", "Exit code 2" + chr(10) + "fail", error=True)),
             (_use("4", "Bash", command="ls src && cat src/a.h"), _res("4", "sema.c")),
             (_use("5", "Read", file_path="gone.c"), _res("5", "File does not exist.", error=True)),
             (_use("6", "Bash", command="python wipe.py"), _res("6", REFUSED, error=True)),
             (_use("7", "Bash", command="cat > gen.py <<'X'" + chr(10) + "x=1" + chr(10) + "X"), _res("7", "")),
             (_use("8", "Bash", command="echo 1+1 | ./calc"), _res("8", "2")),
             (_use("9", "Read", file_path="src/sema.c"), _res("9", "Wasted call - file unchanged since your last Read")))
    out = r.render()
    assert "- src/sema.c: 55-60" in out and "- src/sema.c: 40-42" in out, out
    assert "- gen.py: ? (shell write)" in out and "- src/a.h: whole" in out
    assert "- exit 0: `echo 1+1 | ./calc`" in out and "- exit 2: `cd build && make test`" in out
    assert out.index("./calc") < out.index("make test"), "newest first"
    assert "ls src" not in out and "gone.c" not in out and "wipe.py" not in out and "cat > gen.py" not in out


def test_an_edit_without_its_patch_says_only_that_it_was_edited():
    assert "- a.c: edited" in _fed((_use("1", "Edit", file_path="a.c"), _res("1", EDITED))).render()


def test_a_result_of_an_odd_shape_is_read_as_no_text():
    r = _fed((_use("1", "Bash", command="make"), {"type": "tool_result", "tool_use_id": "1", "content": 7}))
    assert "- exit 0: `make`" in r.render()


def test_a_session_that_did_nothing_hands_on_no_record():
    assert SessionRecord().render() == ""


class _Doer(Worker):
    """The first session reads and builds; the others do nothing the record keeps."""

    def agent_round(self, system, user, allowed_tools, cwd, timeout, max_turns, session):
        if self.session_record is not None and not self.closed and self.done == 0:
            self.session_record.use(_use("a", "Read", file_path="lex.c"))
            self.session_record.result(_res("a", "     1→x"))
        return super().agent_round(system, user, allowed_tools, cwd, timeout, max_turns, session)


def test_the_reopen_carries_the_last_sessions_record_and_the_next_starts_empty():
    w = _Doer(work=30, window=100_000, step=4)
    assert w.run_agent("s", "packet", ("Read",), cwd=".", session="sid") == "REPORT"
    reopens = [p for p in w.prompts if p.startswith("packet") and p != "packet"]
    assert len(reopens) >= 2, "two handovers at least"
    assert B.RECORD in reopens[0] and "- lex.c: whole" in reopens[0]
    assert B.RECORD not in reopens[1], "the second session read nothing: its record is its own, empty"
    assert w.session_record is None, "no record outlives the run"


def test_the_stream_feeds_every_call_of_a_message_and_its_results():
    p = H.ClaudeCodeProvider("m")
    p.session_record = SessionRecord()
    p._observe({"type": "assistant", "message": {"content": [_use("1", "Read", file_path="a.c", offset=7, limit=2),
                                                             _use("2", "Bash", command="make"),
                                                             _use("3", "Edit", file_path="b.c")]}}, {})
    p._observe({"type": "user", "message": {"content": [_res("1", "     7→x"), _res("2", "built")]}}, {})
    p._observe({"type": "user", "message": {"content": [_res("3", EDITED)]},
                "tool_use_result": {"structuredPatch": [{"newStart": 3, "newLines": 2}]}}, {})
    out = p.session_record.render()
    assert "- a.c: 7-8" in out and "- exit 0: `make`" in out and "- b.c: 3-4" in out


def test_a_path_under_the_place_is_named_from_it():
    r = SessionRecord("C:" + chr(92) + "w" + chr(92) + "node")
    r.use(_use("1", "Write", file_path="C:" + chr(92) + "w" + chr(92) + "node" + chr(92) + "src" + chr(92) + "a.c"))
    r.result(_res("1", "File created"))
    r.use(_use("2", "Write", file_path="/elsewhere/b.c"))
    r.result(_res("2", "File created"))
    assert "- src/a.c: whole" in r.render() and "- /elsewhere/b.c: whole" in r.render()
