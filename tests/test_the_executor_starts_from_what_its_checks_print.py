"""Before an executor session the system runs the node's pinned checks once on its place and hands it what they printed.

On the v17 continuation of sql × haiku 4.5 six parts whose work was already there spent 15–49 turns each discovering
that. The observation is machine state, never a verdict: nothing is built for it, it runs in a copy, the place is not
touched, and a project may switch it off for the other arm of a paired row (`set_mode(observe=False)`)."""
from __future__ import annotations

import time
from pathlib import Path

import pytest

import gfso.tools as T
from gfso import observe, sessions as S
from gfso.core.types import AgentId, Mode, TaskId
from gfso.observe import observe_place
from gfso.packets import _executor_packet
from tests.support import DENIAL_ENTRY, UNMODELLED_FAULT, make_engine

_RISK = [{"item": UNMODELLED_FAULT.item, "predictability": "EXTRAORDINARY", "justification": "no precedent",
          "invalidation_condition": "one occurs", "p": 0.01, "impact": "the run stops and is resumed"}, DENIAL_ENTRY]


def _node(*checks):
    e = make_engine()
    e.start()
    T.create_task(e, "root", {"description": "goal", "criteria": [
        {"name": f"c{i}", "description": f"c{i} holds", "check": [c]} for i, c in enumerate(checks)],
        "accepted_risks": _RISK}, assignee="me")
    e.wait_idle()
    return e, e.graph.get_task(TaskId("root"))


def test_each_check_is_seen_as_it_prints_on_the_place(tmp_path):
    place = tmp_path / "place"
    place.mkdir()
    (place / "done.txt").write_text("42\n")
    e, t = _node({"behaviour": "the answer is there", "command": "cat done.txt", "expect": "42"},
                 {"behaviour": "the tool is built", "command": "./tool", "expect": "ok"},
                 {"behaviour": "the inputs are read", "command": "cat {inputs}/in.txt", "expect": "pinned",
                  "inputs": [{"path": "in.txt", "content": "pinned\n"}]},
                 {"behaviour": "it writes only its copy", "command": "echo x > made.txt; cat made.txt", "expect": "x"})
    seen = observe_place(e, [t], str(place))["root"]
    assert [r.get("matched") for r in seen] == [True, False, True, True]
    assert seen[1]["rc"] != 0 and seen[1]["out"], "a check over a program not built shows how it ended"
    assert not (place / "made.txt").exists(), "the checks run in a copy: the session starts on the place as it was"
    text = _executor_packet(e, t, str(place), seen={"root": seen})
    assert "Your place as the system found it" in text and "not a verdict" in text and "no build step" in text
    assert "`cat done.txt` → printed exactly what it must show" in text
    assert "`./tool` → exit" in text and "standing findings" in text, "the text says what it does not cover"


def test_one_command_pinned_twice_is_matched_against_each_expectation(tmp_path):
    (tmp_path / "v.txt").write_text("1")
    e, t = _node({"behaviour": "one", "command": "cat v.txt", "expect": "1"},
                 {"behaviour": "two", "command": "cat v.txt", "expect": "2"})
    assert [r["matched"] for r in observe_place(e, [t], str(tmp_path))["root"]] == [True, False]


def test_a_place_holding_nothing_runs_no_check(tmp_path, monkeypatch):
    """A first session on an empty repository: each check over no work costs a person seconds and tells nothing."""
    monkeypatch.setattr(observe, "run_checks", lambda *a: pytest.fail("a check ran over nothing"))
    e, t = _node({"behaviour": "b", "command": "./tool", "expect": "ok"})
    (tmp_path / ".git").mkdir()
    assert observe_place(e, [t], str(tmp_path)) == {}


def test_a_place_with_nothing_built_reads_as_one_line(tmp_path):
    (tmp_path / "notes.txt").write_text("a place with no program in it")
    e, t = _node(*({"behaviour": f"b{i}", "command": "./sql_database < q.sql", "expect": str(i)} for i in range(5)))
    seen = observe_place(e, [t], str(tmp_path))
    text = _executor_packet(e, t, str(tmp_path), seen=seen)
    assert "none of the 5 checks shows what it must" in text and text.count("./sql_database") <= 5 + 1


def test_a_check_past_its_time_is_named_and_the_rest_of_the_time_is_bounded(tmp_path, monkeypatch):
    monkeypatch.setattr(observe, "PROBE_S", 1)
    (tmp_path / "a").write_text("")
    e, t = _node({"behaviour": "it hangs", "command": "sleep 5", "expect": ""})
    (row,) = observe_place(e, [t], str(tmp_path))["root"]
    assert row["note"] == "did not finish in 1 s" and "matched" not in row


def test_a_project_that_says_no_observes_nothing_and_no_place_nothing(tmp_path):
    e, t = _node({"behaviour": "b", "command": "cat note.txt", "expect": "hi"})
    assert observe_place(e, [t], None) == {}
    e.set_mode(Mode.SOLO, None, AgentId("agent"), settings={"observe": "0"})
    assert observe_place(e, [t], str(tmp_path)) == {}
    assert "Your place as the system found it" not in _executor_packet(e, t, str(tmp_path), seen={})


def test_the_session_still_ends_inside_its_deadline_after_the_observation(monkeypatch):
    e, t = _node({"behaviour": "b", "command": "cat note.txt", "expect": "hi"})
    monkeypatch.setattr(S, "observe_place", lambda *a: (time.sleep(1.2), {})[1])
    seen, cap = S._observed(e, t.id, [t], ".", 100, lambda m: None)
    assert seen == {} and cap <= 99, "what the observation took is the session's no longer"
    assert S._observed(e, t.id, [t], ".", None, lambda m: None)[1] is None
