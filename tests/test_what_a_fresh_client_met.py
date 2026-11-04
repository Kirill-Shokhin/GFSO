"""What real user-agents met on a clean install, kept: each of these stopped one, or told it something untrue."""
from types import SimpleNamespace

from gfso import tools as T
from gfso.decompose.loop import FOLD_SCHEMA, _audit_fold
from gfso.mcp.server import _with_ui_link


class _Fold:
    def __init__(self, *answers):
        self.answers, self.asked = list(answers), []

    def complete_structured(self, system, user, schema):
        assert schema is FOLD_SCHEMA
        self.asked.append(user)
        return self.answers.pop(0)


PART = {"id": "a", "name": "a", "description": "d", "criteria": [{"name": "c", "description": "d", "check": []}]}


def test_a_fold_whose_parts_name_nothing_is_asked_again_once():
    """No repair round can address a part with no id: the plan was refused minutes later as "left None, None"."""
    llm = _Fold({"add_subtasks": [{"name": "n", "check": []}]}, {"add_subtasks": [PART]})
    assert _audit_fold(llm, "goal", "", "findings") == {"add_subtasks": [PART]}
    assert len(llm.asked) == 2 and "no `id`" in llm.asked[1]


def test_a_fold_with_named_parts_costs_one_call():
    llm = _Fold({"add_subtasks": [PART]})
    assert _audit_fold(llm, "goal", "", "findings") == {"add_subtasks": [PART]}
    assert len(llm.asked) == 1


def test_a_ruling_the_person_may_make_does_not_end_a_wait():
    """Told "nothing moves until you close it", a client stopped the run to ask what the system closed a minute later."""
    step = {"mine": True, "optional": True}
    assert not T._mine_to_do({"steps": [step]})
    assert T._mine_to_do({"steps": [{**step, "optional": False}]})
    assert T._mine_to_do({"steps": [step], "complete": True})


def test_a_wait_reports_what_it_waited():
    """Every wait read 600 s, whatever it was."""
    clock = iter([100.0, 100.0, 101.0, 101.0, 101.0, 107.5, 107.5, 107.5])
    engine = SimpleNamespace(now=lambda: next(clock), next_steps=lambda root: {"steps": []})
    real = T._mark_mine, T.time.sleep
    calls = {"n": 0}

    def marked(_engine, out, _actor):
        calls["n"] += 1
        return {"complete": True} if calls["n"] == 2 else out
    T._mark_mine, T.time.sleep = marked, lambda s: None
    try:
        out = T._waited(engine, None, "agent", 600)
    finally:
        T._mark_mine, T.time.sleep = real
    assert out["waited_seconds"] < 600


def test_the_end_says_what_the_person_is_told():
    """A run ended in one sentence: no verdict, no branch, no link, no way to see the result."""
    out = _with_ui_link("next_steps", {"complete": True}, "p")
    assert "get_verdict" in out["say"] and "gfso/p/accepted" in out["say"] and "git worktree add" in out["say"]


def test_a_go_and_a_new_project_say_it_too():
    assert "unattended" in _with_ui_link("auto_decompose", {"root_id": "root"}, "p")["say"]
    said = _with_ui_link("use_project", {"active": "p"}, "p")["say"]
    assert "claude-haiku-5-5" in said and "gfso/p/accepted" in said


def test_what_is_said_stands_first_in_the_answer():
    """Last in a long answer, it went unsaid: nothing on the plan before a go in 6 runs of 6."""
    assert next(iter(_with_ui_link("auto_decompose", {"root_id": "root", "log": "long"}, "p"))) == "say"
    assert next(iter(_with_ui_link("next_steps", {"steps": [], "complete": True}, "p"))) == "say"
