"""An internal node self-verifies (§10.3): its issuer is its holder, and no validator is imposed on it. Where its holder
signs its PASS with no external check on the current delivery, the door reminds first and asks to confirm — no refusal,
nothing written — so that dozens of parts do not drive the agent into dozens of validator runs, and an external check
stays the holder's explicit wish, reminded in time (the author, 2026-11-21: «только по явному желанию но с напоминанием
своевременно»). A seam the person issues keeps its obligatory check, untouched here.

Each test ran red on the tree before it (no reminder); the mutation named in its docstring turns it red again."""
from __future__ import annotations

import contextlib

import gfso.tools as T
from gfso import signin
import gfso.tools_llm as TL
from gfso.config import CALLER, STANDING
from gfso.core.types import AgentId, Mode, TaskId
from tests.support import REGISTER, criterion, instrument_passes, make_engine


@contextlib.contextmanager
def _as(p):
    token = CALLER.set(p)
    try:
        yield
    finally:
        CALLER.reset(token)


def _part_delivered():
    """His solo root split into a part he holds himself — an internal node, its issuer its holder — delivered."""
    e = make_engine(validate_signals=True, state_timeout=0)
    e.start()
    e.project_name = "p"
    e.set_mode(Mode.SOLO, None, AgentId("user"), hands=None)
    T.create_task(e, "root", {"description": "the goal", "criteria": [criterion("g", "G holds")]})
    e.wait_idle()
    T.signal(e, "root", "ACCEPT", "user")
    T.decompose(e, "root", [{"task_id": "root.a", "covers": ["g"], "spec": {"description": "a part",
                                                                         "criteria": [criterion("a", "A holds")]}}],
                accepted_risks=REGISTER, agent="user")
    e.wait_idle()
    for sig, kw in (("ACCEPT", {}), ("DELIVER", {"result": "a.txt", "self_validation": "PASS"})):
        assert T.signal(e, "root.a", sig, "user", **kw).get("accepted")
        e.wait_idle()
    t = e.graph.get_task(TaskId("root.a"))
    assert t.state.name == "VALIDATING" and str(t.assignee) == str(e.graph.issuer_of(t.id)) == "user"
    return e


def _pass(e, **kw):
    with _as(STANDING):
        return TL.TOOLS["signal"](e, "root.a", "PASS", **kw)


def test_a_self_signed_pass_with_no_external_check_is_reminded_and_confirmed():
    """The first call writes nothing and asks; `confirm=true` signs as before. CONTROL: no reminder — the first call
    signs; `confirm` unread — the second asks again."""
    e = _part_delivered()
    out = _pass(e)
    assert out.get("confirm_needed") and "no external check was made of root.a" in out["reminder"] \
        and "validate_result('root.a')" in out["reminder"] and not out.get("refused") and not out.get("error"), out
    assert e.graph.get_task(TaskId("root.a")).state.name == "VALIDATING", "the reminder wrote"
    out = _pass(e, confirm=True)
    assert out.get("accepted") and not out.get("confirm_needed"), out
    e.wait_idle()
    assert e.graph.get_task(TaskId("root.a")).state.name == "DONE"


def test_where_an_external_check_stands_its_pass_is_not_reminded():
    """CONTROL: the validator's record unread — reminded though checked."""
    e = _part_delivered()
    instrument_passes(e, TaskId("root.a"), validator="val-a")
    out = _pass(e)
    assert out.get("accepted") and not out.get("confirm_needed"), out


def test_a_root_its_holder_signs_is_no_internal_node():
    """A root's issuer reads as its own holder, but it is a tree's top, no part of one. CONTROL: the parent unread —
    the root's PASS reminded."""
    e = make_engine(validate_signals=True, state_timeout=0)
    e.start()
    T.create_task(e, "t1", {"description": "x", "criteria": [criterion("c", "C")]}, assignee="dev")
    e.wait_idle()
    for sig, kw in (("ACCEPT", {}), ("DELIVER", {"result": "done"})):
        T.signal(e, "t1", sig, "dev", **kw)
        e.wait_idle()
    assert e.graph.get_task(TaskId("t1")).state.name == "VALIDATING"
    assert TL.unchecked_self_pass(e, TaskId("t1"), "dev") == ""


def test_his_own_check_by_hand_is_no_external_one():
    """His record of what he observed is the self-verification itself (`record_verdict` on an internal node): the
    reminder still stands. CONTROL: any record read as external — not reminded."""
    e = _part_delivered()
    instrument_passes(e, TaskId("root.a"), validator="user", by_hand=True)
    assert _pass(e).get("confirm_needed")


def test_the_persons_own_page_is_never_reminded():
    """His click on his page is his explicit act; the reminder is for an agent (the author, 2026-11-21: «агент … может
    получать напоминание»). The page cannot confirm, so a reminder there would be a refusal he has no way past (critic).
    CONTROL: the page reminded like an agent — the PASS answers `confirm_needed` and the part stays VALIDATING."""
    e = _part_delivered()
    with _as(signin.PAGE):
        out = TL.TOOLS["signal"](e, "root.a", "PASS")
    e.wait_idle()
    assert not out.get("confirm_needed") and out.get("accepted"), out
    assert e.graph.get_task(TaskId("root.a")).state.name == "DONE"
