"""Инв-5 (finiteness) ENFORCED, not narrated: every non-terminal state carries a clock. A
deadline-less node can no longer wait forever (observed live: a stuck VALIDATING root with
deadline=None had no escape) — the per-state age walks it through the sub-FSM: first fire →
TIMEOUT, repeat → ESCALATED; issuer inaction on VALIDATING auto-passes (§6.3/§16.7)."""
import time

from gfso.engine import Engine
from gfso.adapters.storage.memory import MemoryStorage
from gfso.adapters.agents.human import HumanAgent
from gfso.core.types import TaskId, AgentId, Spec, Criteria, SignalData, Signal


def _eng(state_timeout):
    e = Engine(MemoryStorage(), HumanAgent(), llm=None, validate_signals=True,
               check_interval=0.05, state_timeout=state_timeout)
    e.start()
    return e


def _wait_state(e, tid, name, timeout=8.0):
    t0 = time.time()
    while time.time() - t0 < timeout:
        if e.get_state(TaskId(tid)).name == name:
            return True
        time.sleep(0.03)
    return False


def test_deadline_less_node_escalates_by_state_age():
    e = _eng(state_timeout=0.25)
    try:
        e.assign_task(TaskId("n"), Spec("no deadline anywhere", (Criteria("c", "C"),)),
                      AgentId("human"))
        assert _wait_state(e, "n", "TIMEOUT")     # the state clock fired without any deadline
        assert _wait_state(e, "n", "ESCALATED")   # repeat fire → terminal: finiteness holds
    finally:
        e.stop()


def test_validating_auto_passes_on_issuer_inaction():
    e = _eng(state_timeout=0.6)
    try:
        e.assign_task(TaskId("v"), Spec("deliverable", (Criteria("c", "C"),)), AgentId("human"))
        e.send_signal_sync(SignalData(signal=Signal.ACCEPT, task_id=TaskId("v"),
                                      source=AgentId("human")))
        e.send_signal_sync(SignalData(signal=Signal.DELIVER, task_id=TaskId("v"),
                                      source=AgentId("human"), result="done; see files"))
        assert _wait_state(e, "v", "DONE")        # VALIDATING aged out → auto_pass (§16.7)
        assert e.get_task(TaskId("v")).done_reason.name == "AUTO"
    finally:
        e.stop()


def test_blocked_escalates_directly_on_state_age():
    """§6.3 spec-target: BLOCKED → ESCALATED directly (the block already signals a problem —
    no intermediate TIMEOUT parking)."""
    e = _eng(state_timeout=0.3)
    try:
        e.assign_task(TaskId("b"), Spec("will block", (Criteria("c", "C"),)), AgentId("human"))
        e.send_signal_sync(SignalData(signal=Signal.ACCEPT, task_id=TaskId("b"),
                                      source=AgentId("human")))
        e.send_signal_sync(SignalData(signal=Signal.BLOCK, task_id=TaskId("b"),
                                      source=AgentId("human"), reason="external outage"))
        assert e.get_state(TaskId("b")).name == "BLOCKED"
        assert _wait_state(e, "b", "ESCALATED")            # direct, never TIMEOUT
    finally:
        e.stop()


def test_cancelling_settles_to_cancelled_on_state_age():
    """§6.3 spec-target: CANCELLING → CANCELLED on timeout (cancellation is authoritative — an
    unresponsive executor cannot hold the abandon handshake open)."""
    e = _eng(state_timeout=0.3)
    try:
        e.assign_task(TaskId("x"), Spec("will cancel", (Criteria("c", "C"),)), AgentId("human"))
        e.send_signal_sync(SignalData(signal=Signal.CANCEL, task_id=TaskId("x"),
                                      source=AgentId("human"), reason="obsolete"))
        assert e.get_state(TaskId("x")).name == "CANCELLING"
        assert _wait_state(e, "x", "CANCELLED")            # settles without CANCEL_ACK
    finally:
        e.stop()


def test_state_timeout_disabled_keeps_old_behavior():
    e = _eng(state_timeout=0)                     # declared degraded mode
    try:
        e.assign_task(TaskId("d"), Spec("no deadline", (Criteria("c", "C"),)), AgentId("human"))
        time.sleep(0.4)
        assert e.get_state(TaskId("d")).name == "REVIEW"   # nothing fires without a deadline
    finally:
        e.stop()
