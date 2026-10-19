"""Inv-5 (finiteness) ENFORCED, not narrated: every non-terminal state carries a clock. A
deadline-less node can no longer wait forever (observed live: a stuck VALIDATING root with
deadline=None had no escape) — the per-state age walks it through the table: a wait's first fire
→ ESCALATED, the issuer's silence there → CANCELLING → ABANDONED; issuer inaction on VALIDATING
hands the delivery back to him and passes nothing (§12.4/§16.14)."""
import time

from gfso.core.types import TaskId, AgentId, Spec, Criteria, SignalData, Signal, Task, State
from tests.support import make_engine, pinned
from gfso.adapters.storage.memory import MemoryStorage


def _eng(state_timeout):
    e = make_engine(llm=None, validate_signals=True,
                     check_interval=0.05, state_timeout=state_timeout)
    e.start()
    return e


def _wait_state(e, tid, name, timeout=8.0):
    t0 = time.time()
    while time.time() - t0 < timeout:
        if e.graph.get_state(TaskId(tid)).name == name:
            return True
        time.sleep(0.03)
    return False


def test_deadline_less_node_escalates_by_state_age():
    e = _eng(state_timeout=0.25)
    try:
        e.assign_task(TaskId("n"), Spec("no deadline anywhere", (Criteria("c", "C", check=pinned("c")),)),
                      AgentId("human"))
        assert _wait_state(e, "n", "ABANDONED")   # finiteness holds: the walk reaches a settlement
        route = [(a.old_state.name, a.new_state.name) for a in e.audit_log(TaskId("n"))
                 if a.signal == Signal.TIMEOUT and not a.rejected]
        # the state clock fired without any deadline, and the first fire handed over at once (E1)
        assert route == [("OFFERED", "ESCALATED"), ("ESCALATED", "CANCELLING"),
                         ("CANCELLING", "ABANDONED")], route
    finally:
        e.stop()


def test_validating_hands_the_unvalidated_delivery_back_to_its_issuer():
    e = _eng(state_timeout=0.6)
    try:
        e.assign_task(TaskId("v"), Spec("deliverable", (Criteria("c", "C", check=pinned("c")),)), AgentId("human"))
        e.send_signal_sync(SignalData(signal=Signal.ACCEPT, task_id=TaskId("v"),
                                      source=AgentId("human")))
        e.send_signal_sync(SignalData(signal=Signal.DELIVER, task_id=TaskId("v"),
                                      source=AgentId("human"), result="done; see files"))
        # §16.14: VALIDATING's bound ends the executor's wait; it does not accept for the issuer.
        assert _wait_state(e, "v", "ESCALATED")
        assert e.graph.get_task(TaskId("v")).done_reason is None
    finally:
        e.stop()


def test_blocked_escalates_directly_on_state_age():
    """§12.5 spec-target: BLOCKED → ESCALATED directly (the block already signals a problem)."""
    e = _eng(state_timeout=0.3)
    try:
        e.assign_task(TaskId("b"), Spec("will block", (Criteria("c", "C", check=pinned("c")),)), AgentId("human"))
        e.send_signal_sync(SignalData(signal=Signal.ACCEPT, task_id=TaskId("b"),
                                      source=AgentId("human")))
        e.send_signal_sync(SignalData(signal=Signal.BLOCK, task_id=TaskId("b"),
                                      source=AgentId("human"), reason="external outage"))
        assert e.graph.get_state(TaskId("b")).name == "BLOCKED"
        assert _wait_state(e, "b", "ESCALATED")
    finally:
        e.stop()


def test_cancelling_settles_to_cancelled_on_state_age():
    """§12.6 spec-target: CANCELLING → ABANDONED on timeout (cancellation is authoritative — an
    unresponsive executor cannot hold the abandon handshake open)."""
    e = _eng(state_timeout=0.3)
    try:
        e.assign_task(TaskId("x"), Spec("will cancel", (Criteria("c", "C", check=pinned("c")),)), AgentId("human"))
        e.send_signal_sync(SignalData(signal=Signal.CANCEL, task_id=TaskId("x"),
                                      source=AgentId("human"), reason="obsolete"))
        assert e.graph.get_state(TaskId("x")).name == "CANCELLING"
        assert _wait_state(e, "x", "ABANDONED")            # settles without CONFIRM_CANCEL
    finally:
        e.stop()


def test_state_timeout_disabled_keeps_old_behavior():
    e = _eng(state_timeout=0)                     # declared degraded mode
    try:
        e.assign_task(TaskId("d"), Spec("no deadline", (Criteria("c", "C", check=pinned("c")),)), AgentId("human"))
        time.sleep(0.4)
        assert e.graph.get_state(TaskId("d")).name == "OFFERED"   # nothing fires without a deadline
    finally:
        e.stop()


def test_idle_carries_no_clock_and_a_crash_orphan_is_recovered():
    """Corner #1, closed: IDLE is the one non-terminal Inv-5 exempts (§12.12) — deadlines attach at
    ASSIGN, so the pre-contract state has no clock and no timeout row walks it anywhere.

    The row that used to give it one existed for a crash orphan: a node whose CREATE_TASK persisted
    while the SET_STATE of the same ASSIGN did not. That case is now met where the defect lives —
    the engine finishes the interrupted transition at startup, so the orphan leaves IDLE by landing
    its own ASSIGN rather than by aging into a timeout it never contracted for.
    """
    storage = MemoryStorage()
    storage.save_task(Task(id=TaskId("orphan"), spec=Spec("half-created", (Criteria("c", "C", check=pinned("c")),)),
                           state=State.IDLE, assignee=AgentId("human")))
    e = make_engine(storage, llm=None, validate_signals=True,
                     check_interval=0.05, state_timeout=0.25)
    e.start()
    try:
        assert _wait_state(e, "orphan", "OFFERED")          # the interrupted ASSIGN landed
        t = e.graph.get_task(TaskId("orphan"))
        assert t.spec.description == "half-created"        # recovered, not re-created
        assert any(a.task_id == TaskId("orphan") and a.signal == Signal.ASSIGN
                   for a in e.audit_log())                 # and logged, never a silent write
    finally:
        e.stop()
