"""q_D counted every rework round a parent ever had, including the ones it could not have won.

§15.4's q_D event is "a parent FAILed its own validation **while all its children passed**" — the
FM-1 forgotten-glue signature: the parts are all green and the whole still is not, so what was
wrong was the split. The engine read that precondition off the CURRENT state and the FAIL off
`iteration > 0`, which is any rework round whatsoever. A parent that delivered its aggregate with a
child still red, was rightly FAILed for it, and then passed once that child went green, was counted
as a decomposition defect the moment the child turned — the one reading under which the parent's
delivery could not have been right for a reason that is nobody's decomposition.

The log carries the moment (Thm 11), so the moment is what the population is read at. Both
directions are pinned: the FAIL under a red child must not count, and the FAIL under an all-green
frontier — the real q_D event — must.
"""
from __future__ import annotations

from datetime import datetime, timedelta

from gfso.adapters.storage.memory import MemoryStorage
from gfso.core.graph import Graph, q_D
from gfso.core.types import AgentId, DoneReason, Spec, State, Task, TaskId

T0 = datetime(2026, 9, 23, 12, 0, 0)


def _at(minutes: int) -> str:
    return (T0 + timedelta(minutes=minutes)).isoformat()


def _task(tid, state, done_reason=None, parent_id=None, iteration=0):
    t = Task(id=TaskId(tid), spec=Spec("t", ()), state=state, assignee=AgentId("a1"),
             done_reason=done_reason, parent_id=TaskId(parent_id) if parent_id else None)
    t.iteration = iteration
    return t


def _graph(rows, *tasks):
    st = MemoryStorage()
    g = Graph(st)
    for t in tasks:
        g.save_task(t)
    for r in rows:
        st.append_audit(r)
    return g


def _row(tid, signal, new_state, at):
    return {"ts": _at(at), "task_id": tid, "signal": signal, "new_state": new_state,
            "rejected": False}


DONE_PARENT = _task("p", State.DONE, DoneReason.PASS, iteration=1)
GREEN_CHILDREN = (_task("c1", State.DONE, DoneReason.PASS, parent_id="p"),
                  _task("c2", State.DONE, DoneReason.PASS, parent_id="p"))


def test_a_parent_that_failed_while_a_child_was_still_red_is_no_q_D_defect():
    g = _graph([_row("c1", "PASS", "DONE", 1),
                _row("p", "FAIL", "REWORKING", 2),      # c2 has not passed yet at this moment
                _row("c2", "PASS", "DONE", 3),
                _row("p", "PASS", "DONE", 4)],
               DONE_PARENT, *GREEN_CHILDREN)
    assert q_D(g) == 1.0, \
        "the aggregate could not have been right with a child still failing — that FAIL says " \
        "nothing about the split (§15.4)"


def test_a_parent_that_failed_with_every_child_green_still_is_one():
    """The negative control: a rule that excuses everything is not a rule."""
    g = _graph([_row("c1", "PASS", "DONE", 1),
                _row("c2", "PASS", "DONE", 2),
                _row("p", "FAIL", "REWORKING", 3),      # the real forgotten-glue signature
                _row("p", "PASS", "DONE", 4)],
               DONE_PARENT, *GREEN_CHILDREN)
    assert q_D(g) == 0.0


def test_a_graph_with_no_trail_keeps_the_current_state_proxy():
    """The approximation survives exactly where there is nothing better to read — and nowhere else."""
    g = _graph([], DONE_PARENT, *GREEN_CHILDREN)
    assert q_D(g) == 0.0


def test_a_child_cancelling_at_the_fail_and_abandoned_since_still_was_not_passing():
    """Active = not ABANDONED (§15.4): a CANCELLING child is in the decomposition and not passing. Read off the
    children active NOW, it had left, and the FAIL counted as a refuted split."""
    g = _graph([_row("c1", "PASS", "DONE", 1),
                _row("c2", "CANCEL", "CANCELLING", 2),
                _row("p", "FAIL", "REWORKING", 3),
                _row("c2", "CONFIRM_CANCEL", "ABANDONED", 4),
                _row("p", "PASS", "DONE", 5)],
               DONE_PARENT, GREEN_CHILDREN[0], _task("c2", State.ABANDONED, parent_id="p"))
    assert q_D(g) == 1.0


def test_a_child_abandoned_before_the_fail_is_not_in_its_population():
    g = _graph([_row("c2", "CONFIRM_CANCEL", "ABANDONED", 1),
                _row("c1", "PASS", "DONE", 2),
                _row("p", "FAIL", "REWORKING", 3),
                _row("p", "PASS", "DONE", 4)],
               DONE_PARENT, GREEN_CHILDREN[0], _task("c2", State.ABANDONED, parent_id="p"))
    assert q_D(g) == 0.0, "every child in the decomposition then was green: the real q_D event"
