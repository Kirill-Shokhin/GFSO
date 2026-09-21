"""The guarantee, not the instance: no state leaves the work alive with nobody able to move it.

Inv-6 asks that the admissible signal set be DEFINED in every state. That is satisfied vacuously by
defining it empty, and empty is right in exactly one case — the work is over (DONE = pass, ABANDONED
= V=⊥ by authority). Anywhere else an empty set means the protocol has stopped naming who must act,
and something outside the protocol then acts, unconstrained by it. In a measured run that something
was the agent holding the whole context: its root escalated, the state admitted nothing, and it built
`root2` and then `root3` and closed the goal on a childless leaf.

Why this file and not another fix of the state that was found: the state was found because a paid run
died on it. A guarantee is what makes the next one of the same shape impossible to introduce, and
under delegation it is not optional — nobody there holds the whole picture, so a fork the protocol
leaves open is either a stall or an invention by an executor who cannot see the goal.
"""
from __future__ import annotations

import time
from datetime import datetime

import pytest

import gfso.engine.loop as engine_loop
import gfso.tools as T
from gfso.core.protocol.fsm import available_signals, transition
from gfso.core.types import (
    DoneReason, GuardContext, Signal, SignalData, State, TaskId,
    TERMINAL_STATES, NON_TERMINAL_STATES,
)
from tests.support import make_engine


SETTLEMENTS = {State.DONE, State.ABANDONED}


def test_a_settlement_is_exactly_a_terminal():
    """The vocabulary itself: terminal means the work is over, and nothing else is filed there."""
    assert TERMINAL_STATES == SETTLEMENTS
    assert State.ESCALATED in NON_TERMINAL_STATES


@pytest.mark.parametrize("state", sorted(State, key=lambda s: s.name))
def test_every_live_state_admits_an_act(state: State):
    """THE invariant. A state where the work is not over names at least one signal that moves it."""
    sigs = available_signals(state)
    if state in SETTLEMENTS:
        # A settlement admits only the R′ reopen affordance, whose own gate may still refuse.
        assert set(sigs) <= {Signal.ASSIGN}, f"{state.name} admits work signals after settling"
        return
    assert sigs, (
        f"{state.name} is not a settlement and admits NO signal: the work is alive and the protocol "
        f"names nobody who can move it. That is the hole this file exists to keep shut.")


def test_the_issuers_waiting_state_admits_exactly_his_three_moves():
    """ESCALATED is the issuer's side of the obligation symmetry (Inv-4), so it carries his answers.

    Raise the bound and change the criteria are both packet fields, hence one act by Inv-1 (re-ASSIGN
    → OFFERED); closing it is the universal CANCEL; and the state's own timeout is what makes silence
    finite (Inv-5) — settling the node, never passing it."""
    sigs = set(available_signals(State.ESCALATED))
    assert Signal.ASSIGN in sigs      # raise the bound / change the criteria (Inv-1)
    assert Signal.CANCEL in sigs      # close it, cascading the live subtree
    assert Signal.TIMEOUT in sigs     # the issuer's silence settles it (Inv-5)


def test_the_silence_of_the_issuer_closes_and_never_passes():
    """…and it closes through CANCELLING, because the SUBTREE has to go with it.

    Escalation cascades nothing, so an escalated node's children are still live under their own
    contracts. Settling only the parent would leave the product handing out work under a goal nobody
    owns — a silence this very edge would create. Silence IS the issuer's cancellation, so it takes
    the cancellation's path: the cascade reaches every live descendant and the settlement is the
    same ABANDONED."""
    out = transition(State.ESCALATED,
                     SignalData(signal=Signal.TIMEOUT, task_id=TaskId("n")),
                     GuardContext(iteration=0, max_iterations=12))
    assert out is not None and out[0] == State.CANCELLING
    # …and CANCELLING settles negatively on its own clock, never at a pass.
    on = transition(State.CANCELLING,
                    SignalData(signal=Signal.TIMEOUT, task_id=TaskId("n")),
                    GuardContext(iteration=0, max_iterations=12))
    assert on is not None and on[0] == State.ABANDONED


def test_the_frontier_names_the_owner_and_the_acts_of_an_escalated_node():
    """The protocol half is not enough: the DOOR has to say it, because that is what the agent reads."""
    e = make_engine(None, llm=None, validate_signals=True, state_timeout=0)
    e.start()
    try:
        T.create_task(e, "root", {"description": "the goal",
                                  "criteria": [{"name": "c", "description": "d"}]})
        t = e._graph.get_task(TaskId("root"))
        t.state, t.done_reason = State.ESCALATED, DoneReason.FAIL
        e._graph.save_task(t)
        e.wait_idle()
        said = e.issuer_moves_on(TaskId("root"))
        for act in ("max_iterations", "revise", "CANCEL"):
            assert act in said, f"the issuer's moves do not name {act}: {said}"
        answer = str(e.next_steps(TaskId("root")))
        assert "ISSUER" in answer or "issuer" in answer
    finally:
        e.stop()


# ── what a stranger driving the product found still open, pinned so it cannot come back ──────────
# A guarantee that holds in the FSM and not at the door is not a guarantee: an agent reads the door.
# Each of these was a live defect after the protocol change landed and before this file grew.


def test_the_first_move_the_product_names_actually_exists():
    """`revise(id, max_iterations=…)` is the move the escalation directive names FIRST.

    It did not exist: `revise` had no such parameter, and passing it inside `spec` was accepted and
    did nothing — so of the three moves handed to the issuer, one was fiction. A door that names an
    act it does not have is worse than one that names none: the agent spends its turns on it."""
    e = make_engine(None, llm=None, validate_signals=False, check_interval=10_000)
    e.start()
    try:
        T.create_task(e, "root", {"description": "g",
                                  "criteria": [{"name": "c", "description": "d"}]})
        t = e._graph.get_task(TaskId("root"))
        t.state, t.done_reason = State.ESCALATED, DoneReason.FAIL
        e._graph.save_task(t)
        e.wait_idle()
        out = T.revise(e, "root", agent="agent", max_iterations=20, reason="other")
        assert not out.get("refused"), out
        assert e.get_task(TaskId("root")).max_iterations == 20
        assert e.get_state(TaskId("root")) == State.OFFERED   # re-consent, Inv-1
    finally:
        e.stop()


def test_an_escalated_parent_is_asked_for_a_decision_not_a_plan_review():
    """…and precisely when it HAS a subtree, which is the delegated case this rule exists for.

    The frontier offered `review_decomposition` on an ESCALATED parent — an act its state does not
    admit at all (CANCEL and ASSIGN are what it admits) — while the decision that would move it went
    unnamed. Two doors then disagreed about the same node, and the one an unattended agent is told to
    drive was the wrong one."""
    e = make_engine(None, llm=None, validate_signals=False, check_interval=10_000)
    e.start()
    try:
        T.create_task(e, "root", {"description": "g",
                                  "criteria": [{"name": "c", "description": "d"}]})
        T.create_task(e, "kid", {"description": "k",
                                 "criteria": [{"name": "k1", "description": "d"}]},
                      parent_id="root")
        T.map_criterion(e, "root", "kid", "c")
        t = e._graph.get_task(TaskId("root"))
        t.state, t.done_reason = State.ESCALATED, DoneReason.FAIL
        e._graph.save_task(t)
        e.wait_idle()
        step = e.next_step(TaskId("root"))
        assert "review_decomposition" not in str(step.get("directive", ""))
        assert "ISSUER" in str(step.get("directive", ""))
        assert "CANCEL" in str(step.get("directive", ""))
    finally:
        e.stop()


def test_a_settled_goal_is_not_reported_as_a_structural_block():
    """The LAST branch of the frontier is where a fork hides, and one was hiding there.

    Over a deliberately closed root it asserted "nothing is settled-negative either, so the block is
    structural: check `list_holes`" — false, and `list_holes` answers empty, and the act that does
    exist (`reopen`) went unmentioned while `available_actions` named it."""
    e = make_engine(None, llm=None, validate_signals=False, check_interval=10_000)
    e.start()
    try:
        T.create_task(e, "root", {"description": "g",
                                  "criteria": [{"name": "c", "description": "d"}]})
        t = e._graph.get_task(TaskId("root"))
        t.state, t.done_reason = State.ABANDONED, DoneReason.FAIL
        e._graph.save_task(t)
        e.wait_idle()
        said = str(e.next_steps(TaskId("root")).get("directive", ""))
        assert "structural" not in said
        assert "reopen('root')" in said
    finally:
        e.stop()


def test_the_issuers_silence_has_a_bottom_on_a_default_install():
    """"Silence closes it too, by the state's own timeout" has to be TRUE where it is printed.

    It was not: the per-state age clock is opt-in and off by default (`GFSO_STATE_TIMEOUT=0`), so a
    node with no deadline sat in ESCALATED for ever while the product promised otherwise. Inv-5
    demands finiteness of a live state, and a bound that can be switched off is not a bound — the
    same reasoning that gave CANCELLING its own grace, and for the same reason: the only other exits
    belong to a party that may never answer."""
    was = engine_loop._ESCALATED_GRACE_S, engine_loop._CANCELLING_GRACE_S
    engine_loop._ESCALATED_GRACE_S = engine_loop._CANCELLING_GRACE_S = 0.05          # the same bound, shortened so the test is finite
    e = make_engine(None, llm=None, validate_signals=False, check_interval=0.05, state_timeout=0)
    e.start()
    try:
        T.create_task(e, "root", {"description": "g",
                                  "criteria": [{"name": "c", "description": "d"}]})
        t = e._graph.get_task(TaskId("root"))
        t.state, t.done_reason = State.ESCALATED, DoneReason.FAIL
        t.state_entered_at = datetime.now()
        e._graph.save_task(t)
        e.wait_idle()
        for _ in range(400):
            if e.get_state(TaskId("root")) == State.ABANDONED:
                break
            time.sleep(0.05)
        assert e.get_state(TaskId("root")) == State.ABANDONED, "the issuer's silence must CLOSE it"
    finally:
        engine_loop._ESCALATED_GRACE_S, engine_loop._CANCELLING_GRACE_S = was
        e.stop()


def test_the_silence_takes_the_subtree_with_it():
    """The hole the new timeout edge would otherwise OPEN, pinned.

    Escalation does not cascade, so an escalated node's children keep their contracts and their
    executors. Settling only the parent — which is what a direct ESCALATED → ABANDONED edge does —
    leaves the frontier handing out work under a goal nobody owns any more, indefinitely, and the
    "the goal itself is settled" answer never fires because something IS actionable. Routing the
    silence through CANCELLING is what makes the cascade reach them."""
    was = engine_loop._ESCALATED_GRACE_S, engine_loop._CANCELLING_GRACE_S
    engine_loop._ESCALATED_GRACE_S = engine_loop._CANCELLING_GRACE_S = 0.05
    e = make_engine(None, llm=None, validate_signals=False, check_interval=0.05, state_timeout=0)
    e.start()
    try:
        T.create_task(e, "root", {"description": "g",
                                  "criteria": [{"name": "c", "description": "d"}]})
        T.create_task(e, "kid", {"description": "k",
                                 "criteria": [{"name": "k1", "description": "d"}]},
                      parent_id="root")
        T.map_criterion(e, "root", "kid", "c")
        t = e._graph.get_task(TaskId("root"))
        t.state, t.done_reason = State.ESCALATED, DoneReason.FAIL
        t.state_entered_at = datetime.now()
        e._graph.save_task(t)
        e.wait_idle()
        for _ in range(400):
            if e.get_state(TaskId("kid")) == State.ABANDONED:
                break
            time.sleep(0.05)
        assert e.get_state(TaskId("kid")) == State.ABANDONED, (
            "the child is still live under a goal that has been closed")
    finally:
        engine_loop._ESCALATED_GRACE_S, engine_loop._CANCELLING_GRACE_S = was
        e.stop()


def test_overdue_names_its_owner_too():
    """The same hole, one state over — found by driving after the first one was closed.

    OVERDUE answered "Stuck: no actionable node … the usual cause is a plan that does not admit its
    own children", which is false of a childless leaf, and pointed at a `list_holes` that returns
    nothing; `available_actions` gave a bare ["CANCEL"] with none of the prose every other state
    gets. The state is legitimately signal-poor — it accepts no progress signal by design — and that
    is a reason to say WHOSE move is coming, not a licence to say nothing."""
    e = make_engine(None, llm=None, validate_signals=False, check_interval=10_000)
    e.start()
    try:
        T.create_task(e, "root", {"description": "g",
                                  "criteria": [{"name": "c", "description": "d"}]})
        t = e._graph.get_task(TaskId("root"))
        t.state = State.OVERDUE
        e._graph.save_task(t)
        e.wait_idle()
        said = str(e.next_steps(TaskId("root")).get("directive", ""))
        assert "structural" not in said, said
        assert "OVERDUE" in said and "ISSUER" in said, said
        av = T.available_actions(e, "root")
        assert av.get("waiting_on") == "clock", av
        assert "deadline" in str(av.get("recovery")), av
    finally:
        e.stop()
