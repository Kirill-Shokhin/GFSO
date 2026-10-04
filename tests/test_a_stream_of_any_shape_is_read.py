"""The CLI's event stream is read whatever shape its values arrive in.

Measured in two E3 runs (`GB_coreutils_tlr68k360`, `GB_c_compiler_tlnz9l001`): an event whose `message`
was a string killed the whole call on `.get`, and the validator's answer became a ⊥ it never earned. The
guard is structural, so the test names no field: every node of every sample event is replaced, one at a
time, by a value of each other shape, and the reader must still return the call's result.
"""
import copy
import builtins
import json

from gfso.adapters.llm.headless import HeadlessClaudeLLM

_SAMPLES = [
    {"type": "stream_event", "event": {"type": "content_block_delta", "delta": {"type": "text_delta", "text": "hi"},
                                       "usage": {"output_tokens": 3}}},
    {"type": "assistant", "message": {"content": [{"type": "tool_use", "name": "Bash", "input": {}}],
                                      "usage": {"output_tokens": 5}}},
    {"type": "content_block_start", "content_block": {"type": "tool_use", "name": "Read"},
     "delta": {"text": "x"}, "usage": {"output_tokens": 1}},
]
_RESULT = {"type": "result", "result": "THE ANSWER", "usage": {"output_tokens": 9}, "total_cost_usd": 0.01}
_SHAPES = ["a string", ["a", "list"], 7, None, True]


def _paths(v, path=()):
    yield path
    if isinstance(v, dict):
        for k, x in v.items():
            yield from _paths(x, path + (k,))
    elif isinstance(v, list):
        for i, x in enumerate(v):
            yield from _paths(x, path + (i,))


def _replaced(ev, path, shape):
    if not path:
        return shape
    out = copy.deepcopy(ev)
    cur = out
    for k in path[:-1]:
        cur = cur[k]
    cur[path[-1]] = shape
    return out


class _Proc:
    def __init__(self, lines):
        self.stdout = iter(lines)


def _read(events):
    llm = HeadlessClaudeLLM.__new__(HeadlessClaudeLLM)
    llm.on_tick, llm.stage_hint, llm._tick_every, llm.last_tool_calls = None, "", 2.0, {}
    lines = [json.dumps(e) + "\n" for e in events]
    return llm._read_stream(_Proc(lines), 0.0, float("inf"))


def test_every_node_of_every_event_may_arrive_in_any_shape():
    cases = 0
    for ev in _SAMPLES:
        for path in _paths(ev):
            for shape in _SHAPES:
                envelope, _text, _tok = _read([_replaced(ev, path, shape), _RESULT])
                assert envelope and envelope.get("result") == "THE ANSWER", (path, shape)
                cases += 1
    assert cases > 50                      # the walk reached the nested fields, not only the top


def test_a_line_that_is_not_an_object_is_skipped():
    envelope, _t, _o = _read(["a bare string", [1, 2], 3, _RESULT])
    assert envelope.get("result") == "THE ANSWER"


def test_an_agent_runs_stream_is_kept_when_asked(tmp_path, monkeypatch):
    """`--no-session-persistence` left no record of what a delegated executor or validator ran, so an audit
    of its tool calls (a leak check) had nothing to read. With `GFSO_AGENT_TRACE_DIR` every line is kept."""
    monkeypatch.setenv("GFSO_AGENT_TRACE_DIR", str(tmp_path / "traces"))
    events = [_SAMPLES[1], _RESULT]
    envelope, _t, _o = _read(events)
    assert envelope.get("result") == "THE ANSWER"
    files = list((tmp_path / "traces").glob("*.jsonl"))
    assert len(files) == 1
    kept = [json.loads(l) for l in files[0].read_text(encoding="utf-8").splitlines()]
    assert kept == events


def test_a_trace_that_cannot_be_written_never_costs_the_call(tmp_path, monkeypatch):
    """The trace is an audit aid: a disk that refuses it (write or the final flush) must not turn the
    call's answer into an exception."""
    monkeypatch.setenv("GFSO_AGENT_TRACE_DIR", str(tmp_path / "traces"))
    real_open = builtins.open

    class _Full:
        def write(self, _):
            raise OSError(28, "No space left on device")

        def close(self):
            raise OSError(28, "No space left on device")

    monkeypatch.setattr(builtins, "open", lambda f, *a, **k: _Full() if "traces" in str(f) else real_open(f, *a, **k))
    envelope, _t, _o = _read([_SAMPLES[0], _RESULT])
    assert envelope.get("result") == "THE ANSWER"


def test_an_agent_run_loads_only_the_tools_it_may_use(tmp_path):
    """The approval list approves; `--tools` is what loads. Without it every validator call re-read the
    schemas of all built-in tools (58% of its cached input, 2026-09-27) and held Write and Edit."""
    seen = {}
    llm = HeadlessClaudeLLM.__new__(HeadlessClaudeLLM)
    llm._call = lambda system, user, tools_args=None, cwd=None, timeout=None: seen.update(args=tools_args) or ""
    llm.run_agent("s", "u", ("Read", "Bash(git *)", "Glob", "Bash"), cwd=str(tmp_path))
    a = seen["args"]
    assert a[a.index("--tools") + 1] == "Read,Bash,Glob"
    assert a[a.index("--allowedTools") + 1] == "Read Bash(git *) Glob Bash"


_BG_ON = {"type": "system", "subtype": "background_tasks_changed", "tasks": [{"task_id": "b1"}]}
_BG_OFF = {"type": "system", "subtype": "background_tasks_changed", "tasks": []}


def test_a_result_that_answers_is_the_answer_whatever_runs_on():
    """root.tail (AUTO haiku coreutils, 2026-10-12): the report came first, a command it had left in the background kept
    the session alive, and a later turn's line replaced the report — read as unparsable, retried."""
    report = {"type": "result", "result": '{"status": "delivered"}'}
    later = {"type": "result", "result": "the background task was stopped"}
    envelope, _, _ = _read([_BG_ON, report, _BG_OFF, later])
    assert envelope["result"] == '{"status": "delivered"}'


def test_a_result_that_waits_on_a_live_background_task_is_not_the_answer():
    """The other real shape (critic, CLI 2.1.296): the session ends its turn to wait for a background command, then
    reports after the notification — the first result is "WAITING", the report is the second."""
    waiting = {"type": "result", "result": "WAITING"}
    report = {"type": "result", "result": '{"status": "delivered", "summary": "FINISHED"}'}
    envelope, _, _ = _read([_BG_ON, waiting, _BG_OFF, report])
    assert envelope["result"] == report["result"]
    envelope, _, _ = _read([_SAMPLES[0], _RESULT, waiting])
    assert envelope["result"] == "THE ANSWER", "with nothing running in the background a plain answer is the answer"
