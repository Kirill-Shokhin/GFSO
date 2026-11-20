"""Under `solo` and `semi` the root's issuer is the goal's issuer, the person, outside the graph (§10.1), and the moves
§11.2 gives an issuer are signed by him (§10.2): ACCEPT_CHALLENGE, REJECT_CHALLENGE, RESOLVE_BLOCK, CANCEL, the re-ASSIGN
of an ESCALATED root, as PASS and FAIL already were. Their agent both executes the root and holds the connection, so it
asked the person "which line ending?" by a CHALLENGE, read "This is YOURS … REJECT_CHALLENGE", and answered its own
question in his name — accepted, nothing of his said (critic, in-process). Each is now taken from an agent's connection
only with his words, heard on the feed, or from his page; refused otherwise, nothing written (§12.16 (ii)). PASS and
FAIL taken with his words: `test_a_small_task_takes_the_canons_acts`, `test_the_mode_decides_who_holds_what`."""
from __future__ import annotations

import pytest

from gfso import tools_llm as TL
from gfso.config import CALLER, Principal
from gfso.core.types import AgentId, DoneReason, Mode, Signal, SignalData, State, TaskId
from tests.test_a_solo_chat_writes_its_own_plan_and_the_person_gives_the_go import ASKED, _filled, _gone, no_model  # noqa: F401
from tests.test_the_mode_decides_who_holds_what import _engine

ROOT = TaskId("root")
WORDS = "LF, как в остальных файлах"


def _root_in(mode, state):
    """A root the person gave the go on in a solo chat — at work once it is taken — under `mode`, brought to `state` the
    way its agent brings it there."""
    e = _engine(Mode.SOLO)
    _gone(e, _filled(TL.plan(e, ASKED)["text"]))
    e.set_mode(mode, None, AgentId("user"))
    move = lambda s, **k: (e.send_signal_sync(SignalData(signal=s, task_id=ROOT, source=AgentId("user"), **k)),
                           e.wait_idle())
    if e.graph.get_state(ROOT) == State.OFFERED:
        move(Signal.ACCEPT)
    if state == State.CHALLENGED:
        move(Signal.CHALLENGE, justification="which line ending does the person want?")
    elif state == State.BLOCKED:
        move(Signal.BLOCK, reason="the person's sample file is not in the repository", external=True)
    elif state == State.ESCALATED:
        t = e.graph.get_task(ROOT)
        t.state, t.done_reason = State.ESCALATED, DoneReason.FAIL
        e.graph.save_task(t)
    assert e.graph.get_state(ROOT) == state
    return e


def _feed(e):
    said = []
    real = e.emit_info
    e.emit_info = lambda kind, msg, *a, **k: (said.append(msg), real(kind, msg, *a, **k))[1]
    return said


MOVES = [(State.CHALLENGED, lambda e, **w: TL.TOOLS["signal"](e, "root", "REJECT_CHALLENGE", "user",
                                                                justification="the contract stands", **w)),
         (State.CHALLENGED, lambda e, **w: TL.TOOLS["signal"](e, "root", "ACCEPT_CHALLENGE", "user", **w)),
         (State.BLOCKED, lambda e, **w: TL.TOOLS["signal"](e, "root", "RESOLVE_BLOCK", "user", external=True, **w)),
         (State.EXECUTING, lambda e, **w: TL.TOOLS["signal"](e, "root", "CANCEL", "user", **w)),
         (State.ESCALATED, lambda e, **w: TL.TOOLS["reassign"](e, "root", "user", **w)),
         (State.ESCALATED, lambda e, **w: TL.TOOLS["revise"](e, "root", deadline="2099-01-01T00:00:00", **w))]
IDS = ["reject_challenge", "accept_challenge", "resolve_block", "cancel", "reassign_escalated", "revise_escalated"]


@pytest.mark.parametrize("mode", [Mode.SOLO, Mode.SEMI])
@pytest.mark.parametrize("state,move", MOVES, ids=IDS)
def test_an_issuer_move_on_the_root_without_the_persons_words_is_refused_and_writes_nothing(no_model, mode, state, move):
    e = _root_in(mode, state)
    before, log = e.graph.get_state(ROOT), len(e.audit_log(ROOT))
    out = move(e)
    e.wait_idle()
    assert TL.is_refusal(out) and "person" in out["error"] and "user_said" in out["error"], out
    assert e.graph.get_state(ROOT) == before and len(e.audit_log(ROOT)) == log, "a refused move writes nothing"


@pytest.mark.parametrize("mode", [Mode.SOLO, Mode.SEMI])
def test_a_reassign_of_the_root_at_work_without_the_persons_words_is_refused_and_writes_nothing(no_model, mode):
    """A reassign is a re-ASSIGN of the root, an issuer's move (§11.2, §11.3) and so the person's in every state, not only
    once ESCALATED: unasked, the agent re-issued his goal at work, voiding the consent it stood on (EXECUTING to OFFERED)."""
    e = _root_in(mode, State.EXECUTING)
    log = len(e.audit_log(ROOT))
    out = TL.TOOLS["reassign"](e, "root", "user", reason="other")
    e.wait_idle()
    assert TL.is_refusal(out) and "person" in out["error"] and "user_said" in out["error"], out
    assert e.graph.get_state(ROOT) == State.EXECUTING and len(e.audit_log(ROOT)) == log, "a refused move writes nothing"


def test_a_reassign_of_the_root_at_work_with_the_persons_words_is_taken(no_model):
    e = _root_in(Mode.SOLO, State.EXECUTING)
    said = _feed(e)
    out = TL.TOOLS["reassign"](e, "root", "user", reason="other", user_said=WORDS)
    e.wait_idle()
    assert not TL.is_refusal(out) and e.graph.get_state(ROOT) == State.OFFERED, out
    assert any(WORDS in m for m in said), said


@pytest.mark.parametrize("state,move", MOVES, ids=IDS)
def test_the_same_move_with_the_persons_words_is_taken_and_heard_on_the_feed(no_model, state, move):
    e = _root_in(Mode.SOLO, state)
    said = _feed(e)
    out = move(e, user_said=WORDS)
    e.wait_idle()
    assert not TL.is_refusal(out) and e.graph.get_state(ROOT) != state, out
    assert any(WORDS in m for m in said), said


def test_the_persons_page_answers_the_challenge_with_no_words(no_model):
    e = _root_in(Mode.SOLO, State.CHALLENGED)
    token = CALLER.set(Principal("user", ("user",), "session", "a page", "local"))
    try:
        out = TL.TOOLS["signal"](e, "root", "REJECT_CHALLENGE", "user", justification="the contract stands")
    finally:
        CALLER.reset(token)
    e.wait_idle()
    assert not TL.is_refusal(out) and e.graph.get_state(ROOT) != State.CHALLENGED, out


def test_under_auto_the_system_still_answers_its_own_roots_dispute(no_model):
    """The root's issuer under `auto` is the system (§10.1): its moves need nobody's words."""
    assert TL._the_persons_move(_engine(Mode.AUTO), ROOT, "REJECT_CHALLENGE") is None


@pytest.mark.parametrize("state", [State.CHALLENGED, State.BLOCKED, State.ESCALATED])
def test_the_step_on_the_roots_issuer_move_says_it_is_the_persons(no_model, state):
    e = _root_in(Mode.SOLO, state)
    step = next(s for s in TL.TOOLS["next_steps"](e)["steps"] if s["task_id"] == "root")
    assert "This is YOURS" not in step["directive"] and "It is YOURS" not in step["directive"], step
    assert "the person's to answer" in step["directive"] and "user_said" in step["directive"], step
