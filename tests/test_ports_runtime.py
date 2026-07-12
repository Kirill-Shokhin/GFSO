"""ClockPort + RunnerPort — the runtime substrate is swappable WITHOUT touching the core.

Three proofs: (1) a FAKE clock drives Инв-5 state-age timeouts in milliseconds of real time
(an HOUR of virtual staleness — no sleep-based test could afford that); (2) the RunnerPort is
the real spawn seam Engine.start goes through; (3) an asyncio host drives `process_signal`
directly from its own loop — no engine thread, no blocking queue — and the FSM/mutations
underneath behave identically.
"""
import time

from gfso.engine import Engine
from gfso.engine.loop import process_signal
from gfso.engine.audit import AuditLog
from gfso.engine.events import EventBus
from gfso.adapters.storage.memory import MemoryStorage
from gfso.adapters.agents.human import HumanAgent
from gfso.core.graph import Graph
from gfso.core.types import (
    TaskId, AgentId, Spec, Criteria, Signal, SignalData, ClockPort, ThreadRunner,
)
from gfso import tools as T


class FakeClock(ClockPort):
    """Virtual time: wait() advances the clock instantly (plus a GIL yield). Starts at the real
    epoch so ages computed against datetime-stamped graph fields stay meaningful."""

    def __init__(self):
        self._t = time.time()

    def now(self) -> float:
        return self._t

    def wait(self, seconds: float) -> None:
        self._t += seconds
        time.sleep(0.001)


def _mk(e, tid="n"):
    T.create_task(e, tid, {"description": "x", "criteria": [{"name": "a", "description": "A"}]}, "w")
    e.wait_idle()


def _await_state(e, tid, names, timeout=3.0):
    dl = time.time() + timeout
    while time.time() < dl:
        st = e.get_state(TaskId(tid))
        if st and st.name in names:
            return st.name
        time.sleep(0.01)
    return e.get_state(TaskId(tid)).name


def test_fake_clock_drives_inv5_state_age_in_milliseconds():
    """An HOUR-scale state_timeout enforced through virtual time: the deadline-less node cannot
    sit in REVIEW forever; the sub-FSM escalates (first timeout → TIMEOUT, repeat → ESCALATED) —
    all in milliseconds of wall time, because Инв-5 reads the ClockPort, not the wall clock."""
    e = Engine(MemoryStorage(), HumanAgent(), llm=None, validate_signals=True,
               check_interval=1800, state_timeout=3600, clock=FakeClock())
    e.start()
    _mk(e)
    got = _await_state(e, "n", {"TIMEOUT", "ESCALATED"})
    assert got in ("TIMEOUT", "ESCALATED")
    assert _await_state(e, "n", {"ESCALATED"}) == "ESCALATED"   # repeated virtual timeout
    e.stop()


def test_runner_port_is_the_spawn_seam():
    """Engine.start goes through the RunnerPort — a host substrate sees (and owns) both loops."""
    class RecordingRunner(ThreadRunner):
        def __init__(self):
            self.spawned = []

        def spawn(self, target, name: str) -> None:
            self.spawned.append(name)
            super().spawn(target, name)

    r = RecordingRunner()
    e = Engine(MemoryStorage(), HumanAgent(), llm=None, validate_signals=True, runner=r,
               state_timeout=0)
    e.start()
    assert sorted(r.spawned) == ["gfso-event-loop", "gfso-timeout-monitor"]
    _mk(e)                                             # and the engine WORKS over that substrate
    assert e.get_state(TaskId("n")).name == "REVIEW"
    e.stop()


def test_asyncio_host_drives_process_signal_without_engine_threads():
    """The protocol step is substrate-free: an asyncio host pumps its own queue and calls
    process_signal per item — no Engine.start, no thread, no queue.Queue. Same FSM semantics."""
    import asyncio

    storage = MemoryStorage()
    graph, audit, events = Graph(storage), AuditLog(storage), EventBus()
    agents = HumanAgent()

    class Sink:                                        # the host's follow-up-signal sink
        def __init__(self, q):
            self.q = q

        def put(self, item):
            self.q.put_nowait(item)

    async def host():
        q: asyncio.Queue = asyncio.Queue()
        sink = Sink(q)
        w = AgentId("w")
        spec = Spec("x", (Criteria("a", "A"),))
        for sd in (SignalData(signal=Signal.ASSIGN, task_id=TaskId("n"), source=w,
                              spec=spec, assignee=w),
                   SignalData(signal=Signal.ACCEPT, task_id=TaskId("n"), source=w)):
            sink.put(sd)
        n = 0
        while not q.empty():
            sd = await q.get()
            process_signal(sd, graph, agents, None, sink, audit, events, validate=True)
            n += 1
        return n

    processed = asyncio.run(host())
    assert processed >= 2
    assert graph.get_state(TaskId("n")).name == "EXECUTING"    # ASSIGN → REVIEW → ACCEPT → EXECUTING
    assert len([a for a in audit.get_entries(TaskId("n")) if not a.rejected]) == 2
