"""A part whose validation's bound passed with no verdict reaches its issuer with its delivery standing unvalidated
(§12.4): that says nothing against the work, so the system's issuer is offered the re-presentation, not `cancel` — a
machine issuer cancelled such a delivery "contract fully satisfied" and re-issued it (tn7a14284, 2026-10-20), and on a
plan the user handed in a cancel stops the whole run. Re-presented, the same result is re-delivered and validated."""
import pytest

from gfso import issuer as I, tools as T
from gfso.core.types import Mode, Signal, SignalData, State, TaskId
from tests.support import criterion
from tests.test_the_mode_decides_who_holds_what import _admit, _engine, _kid


def _escalated_by(state_lapsed, users=False):
    e = _engine(Mode.AUTO)
    T.TOOLS["create_task"](e, "root", {"description": "the goal", "criteria": [criterion("g", "G holds")]})
    _admit(e, "root", _kid("root.a", ["g"], criterion("ka", "A holds")))
    if users:
        e.give_users_plan("root")
    a = e.graph.get_task(TaskId("root.a"))
    if state_lapsed == State.VALIDATING:
        e.send_signal_sync(SignalData(signal=Signal.ACCEPT, task_id=a.id, source=a.assignee))
        e.send_signal_sync(SignalData(signal=Signal.DELIVER, task_id=a.id, source=a.assignee, result="a.py written"))
    elif state_lapsed == State.EXECUTING:
        e.send_signal_sync(SignalData(signal=Signal.ACCEPT, task_id=a.id, source=a.assignee))
    a = e.graph.get_task(TaskId("root.a"))
    assert a.state == state_lapsed
    e.send_signal_sync(SignalData(signal=Signal.TIMEOUT, task_id=a.id, visit=(a.state, a.state_entered_at)))
    a = e.graph.get_task(TaskId("root.a"))
    assert a.state == State.ESCALATED
    return e, a


@pytest.mark.parametrize("users", [False, True])
def test_a_delivery_whose_validation_lapsed_is_re_presented_not_cancelled(users):
    e, a = _escalated_by(State.VALIDATING, users)
    moves = I.moves_for(e, a, "escalation")
    assert "cancel" not in moves and "reassign" in moves, moves
    assert "Its delivery stands unvalidated" in I.issuer_context(e, a.id, "escalation")
    # …the move it is owed works: the contract re-presented, the same result re-delivered, validated then
    ok, why = I._reassign(e, a, str(e.graph.issuer_of(a.id)), {}, "re-present the unvalidated delivery", None)
    assert ok, why
    a = e.graph.get_task(TaskId("root.a"))
    assert a.state == State.OFFERED
    e.send_signal_sync(SignalData(signal=Signal.ACCEPT, task_id=a.id, source=a.assignee))
    e.send_signal_sync(SignalData(signal=Signal.DELIVER, task_id=a.id, source=a.assignee, result="a.py written"))
    assert e.graph.get_state(a.id) == State.VALIDATING
    e.stop()


def test_a_work_state_that_lapsed_keeps_its_close():
    """A missed deadline in the work is the forecast refuted (§12.15 Φ3): closing it stays the issuer's move."""
    e, a = _escalated_by(State.EXECUTING)
    assert "cancel" in I.moves_for(e, a, "escalation")
    assert "Its delivery stands unvalidated" not in I.issuer_context(e, a.id, "escalation")
    e.stop()
