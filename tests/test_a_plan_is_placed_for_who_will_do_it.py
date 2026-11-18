"""A plan file's parts are judged against the session of the executor that will do them (§3.7: a leaf lies within its
holder's κ): under a mode, `plan(request)` — the user's path, no executor named — takes the one the go hands the root's
children to, as `auto_decompose` does. Unnamed before, the planner judged against an unknown agent (critic, 2026-11-11)."""
import pytest

import gfso.tools_llm as TL
from gfso.core.types import AgentId, Mode
from tests.support import written
from tests.test_the_mode_decides_who_holds_what import _engine


@pytest.fixture
def seen(monkeypatch):
    got = {}
    monkeypatch.setattr(TL._planning, "author", lambda req, model, ex, *a, **k: got.update(executor=ex) or "")
    monkeypatch.setattr(TL, "_plan_written", lambda text: {})
    monkeypatch.setattr(TL, "_PLANNING", {})
    return got


def _staffed(mode):
    e = _engine(mode)
    for a in ("exec-1", "exec-2"):
        e.workforce._executor_sessions[a] = f"claude-haiku-5-5, up to 150 turns ({a})"
    return e


def test_under_auto_the_plan_is_judged_against_the_executor_the_go_will_use(seen):
    e = _staffed(Mode.AUTO)
    try:
        written(TL.plan, e, "sort a file")
        kid = str(e.del_at(1, e.del_at(0, None)))
        assert kid in ("exec-1", "exec-2") and seen["executor"] == e.workforce.executor_session(kid) != ""
    finally:
        e.stop()


def test_an_executor_named_by_the_caller_still_decides(seen):
    e = _staffed(Mode.AUTO)
    try:
        written(TL.plan, e, "sort a file", executor="exec-2")
        assert seen["executor"] == "claude-haiku-5-5, up to 150 turns (exec-2)"
    finally:
        e.stop()


def test_with_no_mode_nobody_is_assumed(seen):
    e = _staffed(None)
    try:
        written(TL.plan, e, "sort a file")
        assert seen["executor"] == ""
    finally:
        e.stop()


def test_held_by_the_user_agent_and_dispatched_the_plan_is_judged_against_its_hands(seen):
    """SOLO with hands: the user-agent consents, its hands' session does the parts — the fit is that session's."""
    e = _staffed(None)
    try:
        e.set_mode(Mode.SOLO, None, AgentId("user"), hands="exec-1")
        written(TL.plan, e, "sort a file")
        assert seen["executor"] == "claude-haiku-5-5, up to 150 turns (exec-1)"
    finally:
        e.stop()


def test_held_in_its_own_chat_nobody_is_assumed(seen):
    e = _staffed(None)
    try:
        e.set_mode(Mode.SOLO, None, AgentId("user"))
        written(TL.plan, e, "sort a file", model="claude-haiku-5-5")   # …named: a solo chat's own plan asks no model
        assert seen["executor"] == ""
    finally:
        e.stop()


def test_the_go_judges_the_same_hands(monkeypatch):
    got = {}
    monkeypatch.setattr(TL, "decompose_into", lambda *a, **k: got.update(executor=k.get("executor"))
                        or (_ for _ in ()).throw(RuntimeError("stop after the fit's session is chosen")))
    e = _staffed(None)
    try:
        e.set_mode(Mode.SOLO, None, AgentId("user"), hands="exec-1")
        with pytest.raises(RuntimeError, match="stop after"):
            TL.auto_decompose(e, request="sort a file")
        assert got["executor"] == "claude-haiku-5-5, up to 150 turns (exec-1)"
    finally:
        e.stop()


def test_a_name_the_go_would_refuse_is_refused_by_the_plan_too(seen):
    """SOLO holds the parts: the go refuses `executor="exec-2"`; a plan placed for it would run in exec-1's hands."""
    e = _staffed(None)
    try:
        e.set_mode(Mode.SOLO, None, AgentId("user"), hands="exec-1")
        with pytest.raises(ValueError, match="cannot go to exec-2"):
            TL.plan(e, "sort a file", executor="exec-2")
        written(TL.plan, e, "sort a file", executor="user")          # its own name: its hands' session, as the go reads it
        assert seen["executor"] == "claude-haiku-5-5, up to 150 turns (exec-1)"
    finally:
        e.stop()
