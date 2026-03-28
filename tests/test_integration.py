"""Integration tests: full flows through Engine (L2)."""
from gfso.core.types import (
    State, Signal, TaskId, AgentId, SignalData,
    Spec, Criteria, Task, CriterionMapping, DepEdge,
    DispatchPayload, AgentPort,
)
from gfso.engine import Engine
from gfso.adapters.storage.memory import MemoryStorage
from gfso.adapters.llm.stub import StubLLM


class AutoAgent(AgentPort):
    """Auto-responds: ASSIGN→ACCEPT→DELIVER→PASS."""
    def __init__(self):
        self.dispatches: list[DispatchPayload] = []

    def dispatch(self, agent_id, payload):
        self.dispatches.append(payload)
        match payload.signal:
            case Signal.ASSIGN:
                return SignalData(signal=Signal.ACCEPT, task_id=payload.task.id, source=agent_id)
            case Signal.ACCEPT:
                return SignalData(signal=Signal.DELIVER, task_id=payload.task.id, source=agent_id)
            case Signal.DELIVER:
                return SignalData(signal=Signal.PASS, task_id=payload.task.id, source=agent_id)
            case _:
                return None


def _engine(agent=None, validate=False) -> Engine:
    return Engine(
        storage=MemoryStorage(),
        agents=agent or AutoAgent(),
        llm=StubLLM(),
        validate_signals=validate,
    )


def test_full_happy_path():
    """ASSIGN → REVIEW → ACCEPT → EXECUTING → DELIVER → VALIDATING → PASS → DONE."""
    engine = _engine()
    engine.start()

    task = engine.assign_task(
        TaskId("t1"),
        Spec("build feature", (Criteria("works", "works"),), ("risks",)),
        AgentId("dev"),
    )

    engine.wait_idle()
    assert engine.get_state(TaskId("t1")) == State.DONE

    task = engine.get_task(TaskId("t1"))
    assert task.done_reason is not None

    # Audit trail exists
    entries = engine.audit_log(TaskId("t1"))
    assert len(entries) > 0
    assert any(e.signal == Signal.ASSIGN for e in entries)
    assert any(e.new_state == State.DONE for e in entries)

    engine.stop()


def test_challenge_flow():
    """ASSIGN → CHALLENGE → ACCEPT_CHALLENGE → ACCEPT → EXECUTING."""

    class ChallengeAgent(AgentPort):
        def __init__(self):
            self.call_count = 0

        def dispatch(self, agent_id, payload):
            self.call_count += 1
            match payload.signal:
                case Signal.ASSIGN:
                    return SignalData(signal=Signal.CHALLENGE, task_id=payload.task.id, source=agent_id, reason="bad spec")
                case Signal.CHALLENGE:
                    return SignalData(signal=Signal.ACCEPT_CHALLENGE, task_id=payload.task.id, source=agent_id)
                case Signal.ACCEPT_CHALLENGE:
                    return SignalData(signal=Signal.ACCEPT, task_id=payload.task.id, source=agent_id)
                case _:
                    return None

    engine = _engine(ChallengeAgent())
    engine.start()
    engine.assign_task(TaskId("t1"), Spec("task", (Criteria("c1", "c1"),), ("r",)), AgentId("dev"))

    engine.wait_idle()
    assert engine.get_state(TaskId("t1")) == State.EXECUTING
    engine.stop()


def test_cancel_cascade():
    """Parent CANCEL cascades to children."""

    class NoopAgent(AgentPort):
        def dispatch(self, agent_id, payload):
            return None

    engine = _engine(NoopAgent())

    # Pre-create parent + child
    parent = Task(id=TaskId("p"), spec=Spec("parent", ()), assignee=AgentId("a"), state=State.EXECUTING)
    child = Task(id=TaskId("c1"), spec=Spec("child", ()), assignee=AgentId("a"), state=State.EXECUTING, parent_id=TaskId("p"))
    engine.graph.save_task(parent)
    engine.graph.save_task(child)

    engine.start()
    engine.send_signal(SignalData(signal=Signal.CANCEL, task_id=TaskId("p"), reason="cancelled"))

    engine.wait_idle()
    assert engine.get_state(TaskId("p")) == State.DONE
    assert engine.get_state(TaskId("c1")) == State.DONE
    engine.stop()


def test_rework_flow():
    """FAIL with iteration < max → REWORK → DELIVER → PASS → DONE."""

    class ReworkAgent(AgentPort):
        def __init__(self):
            self.fail_count = 0

        def dispatch(self, agent_id, payload):
            match payload.signal:
                case Signal.ASSIGN:
                    return SignalData(signal=Signal.ACCEPT, task_id=payload.task.id, source=agent_id)
                case Signal.ACCEPT:
                    return SignalData(signal=Signal.DELIVER, task_id=payload.task.id, source=agent_id)
                case Signal.DELIVER:
                    self.fail_count += 1
                    if self.fail_count <= 1:
                        return SignalData(signal=Signal.FAIL, task_id=payload.task.id, source=agent_id, failed_criteria=("c1",))
                    return SignalData(signal=Signal.PASS, task_id=payload.task.id, source=agent_id)
                case Signal.FAIL:
                    return SignalData(signal=Signal.DELIVER, task_id=payload.task.id, source=agent_id)
                case _:
                    return None

    engine = _engine(ReworkAgent())
    engine.start()
    engine.assign_task(TaskId("t1"), Spec("task", (Criteria("c1", "c1"),), ("r",)), AgentId("dev"))

    engine.wait_idle()
    assert engine.get_state(TaskId("t1")) == State.DONE
    assert engine.get_task(TaskId("t1")).iteration == 1
    engine.stop()


def test_metrics_after_flow():
    """Metrics are computable after task completion."""
    engine = _engine()
    engine.start()

    engine.assign_task(TaskId("t1"), Spec("task", (Criteria("c1", "c1"),), ("r",)), AgentId("dev"))
    engine.wait_idle()

    m = engine.metrics()
    assert "q_T" in m
    assert "q_D" in m
    assert "q_V" in m
    assert "q_Dep" in m
    assert "q_Del" in m
    # q_T should be 1.0 (no challenges in happy path)
    assert m["q_T"] == 1.0
    engine.stop()


def test_events_fire():
    """on_transition callback fires on state changes."""
    transitions = []
    engine = _engine()
    engine.on_transition(lambda tid, old, new, sig: transitions.append((tid, new.name)))
    engine.start()

    engine.assign_task(TaskId("t1"), Spec("task", (Criteria("c1", "c1"),), ("r",)), AgentId("dev"))
    engine.wait_idle()

    assert len(transitions) > 0
    states_seen = [t[1] for t in transitions]
    assert "REVIEW" in states_seen
    assert "DONE" in states_seen
    engine.stop()


def test_decompose_task():
    """decompose_task creates children with parent-child edges + criterion mappings."""
    engine = _engine()
    engine.start()

    parent = engine.assign_task(
        TaskId("p"), Spec("parent", (Criteria("perf", "fast"), Criteria("security", "safe")), ("risks",)),
        AgentId("pm"),
    )
    engine.wait_idle()

    children = engine.decompose_task(
        TaskId("p"),
        [
            (TaskId("c1"), Spec("perf work", (Criteria("latency", "< 100ms"),)), AgentId("dev1")),
            (TaskId("c2"), Spec("security audit", (Criteria("no_vulns", "0 CVEs"),)), AgentId("dev2")),
        ],
        criterion_mappings=[
            CriterionMapping("perf", TaskId("c1")),
            CriterionMapping("security", TaskId("c2")),
        ],
    )

    assert len(children) == 2
    assert engine.get_children(TaskId("p")) != []

    parent = engine.get_task(TaskId("p"))
    assert len(parent.criterion_mappings) == 2

    engine.wait_idle()
    # Children should have been ASSIGN'd and processed
    assert engine.get_state(TaskId("c1")) is not None
    assert engine.get_state(TaskId("c2")) is not None
    engine.stop()


def test_add_dependency():
    """add_dependency tracks edges, affects q_Dep."""
    engine = _engine()
    engine.start()

    engine.assign_task(TaskId("t1"), Spec("a", (), ("r",)), AgentId("d"))
    engine.assign_task(TaskId("t2"), Spec("b", (), ("r",)), AgentId("d"))

    engine.add_dependency(TaskId("t1"), TaskId("t2"), discovered=False)
    engine.add_dependency(TaskId("t2"), TaskId("t1"), discovered=True)

    deps = engine.get_dependencies()
    assert len(deps) == 2
    assert deps[0].discovered is False
    assert deps[1].discovered is True

    m = engine.metrics()
    assert m["q_Dep"] == 0.5  # 1 declared / 2 total
    engine.stop()


def test_tasks_by_state():
    """Query tasks by state."""

    class NoopAgent(AgentPort):
        def dispatch(self, agent_id, payload):
            return None

    engine = _engine(NoopAgent())
    engine.start()

    engine.assign_task(TaskId("t1"), Spec("a", (), ("r",)), AgentId("d"))
    engine.wait_idle()

    review_tasks = engine.tasks_by_state(State.REVIEW)
    assert any(t.id == TaskId("t1") for t in review_tasks)

    all_tasks = engine.all_tasks()
    assert len(all_tasks) >= 1
    engine.stop()


def test_tasks_by_assignee():
    """Query tasks by assignee."""

    class NoopAgent(AgentPort):
        def dispatch(self, agent_id, payload):
            return None

    engine = _engine(NoopAgent())
    engine.start()

    engine.assign_task(TaskId("t1"), Spec("a", (), ("r",)), AgentId("alice"))
    engine.assign_task(TaskId("t2"), Spec("b", (), ("r",)), AgentId("bob"))
    engine.wait_idle()

    alice_tasks = engine.tasks_by_assignee(AgentId("alice"))
    assert len(alice_tasks) == 1
    assert alice_tasks[0].id == TaskId("t1")
    engine.stop()


def test_send_signal_sync():
    """send_signal_sync returns audit entry."""

    class NoopAgent(AgentPort):
        def dispatch(self, agent_id, payload):
            return None

    engine = _engine(NoopAgent())
    engine.start()

    # Pre-create task in EXECUTING state
    task = Task(id=TaskId("t1"), spec=Spec("t", ()), state=State.EXECUTING, assignee=AgentId("d"))
    engine.graph.save_task(task)

    entry = engine.send_signal_sync(SignalData(signal=Signal.BLOCK, task_id=TaskId("t1"), reason="blocked"))

    assert entry is not None
    assert entry.new_state == State.BLOCKED
    assert not entry.rejected
    engine.stop()


# === Validation enforcement ===

def test_validation_rejects_fail_without_criteria():
    """FAIL without failed_criteria is rejected when validation enabled."""

    class NoopAgent(AgentPort):
        def dispatch(self, agent_id, payload):
            return None

    engine = _engine(NoopAgent(), validate=True)
    engine.start()

    task = Task(id=TaskId("t1"), spec=Spec("t", (Criteria("c1", "c1"),)),
                state=State.VALIDATING, assignee=AgentId("d"))
    engine.graph.save_task(task)

    entry = engine.send_signal_sync(
        SignalData(signal=Signal.FAIL, task_id=TaskId("t1"), source=AgentId("d"),
                   failed_criteria=()),  # empty — should be rejected
    )
    assert entry is not None
    assert entry.rejected
    engine.stop()


def test_validation_rejects_missing_source():
    """Non-system signal without source is rejected when validation enabled."""

    class NoopAgent(AgentPort):
        def dispatch(self, agent_id, payload):
            return None

    engine = _engine(NoopAgent(), validate=True)
    engine.start()

    task = Task(id=TaskId("t1"), spec=Spec("t", ()), state=State.EXECUTING, assignee=AgentId("d"))
    engine.graph.save_task(task)

    entry = engine.send_signal_sync(
        SignalData(signal=Signal.BLOCK, task_id=TaskId("t1"), source=None),  # no source
    )
    assert entry is not None
    assert entry.rejected
    engine.stop()


def test_validation_allows_system_signals_without_source():
    """System signals (TIMEOUT) don't need source."""

    class NoopAgent(AgentPort):
        def dispatch(self, agent_id, payload):
            return None

    engine = _engine(NoopAgent(), validate=True)
    engine.start()

    task = Task(id=TaskId("t1"), spec=Spec("t", ()), state=State.EXECUTING, assignee=AgentId("d"))
    engine.graph.save_task(task)

    entry = engine.send_signal_sync(
        SignalData(signal=Signal.TIMEOUT, task_id=TaskId("t1")),
    )
    assert entry is not None
    assert not entry.rejected
    assert entry.new_state == State.TIMEOUT
    engine.stop()


# === Callback tests ===

def test_on_reject_fires():
    """on_reject callback fires on rejected signals."""
    rejections = []

    class NoopAgent(AgentPort):
        def dispatch(self, agent_id, payload):
            return None

    engine = _engine(NoopAgent())
    engine.on_reject(lambda tid, sig, state: rejections.append((tid, sig.name, state.name)))
    engine.start()

    # Send invalid signal: PASS to IDLE task
    task = Task(id=TaskId("t1"), spec=Spec("t", ()), state=State.IDLE, assignee=AgentId("d"))
    engine.graph.save_task(task)
    engine.send_signal_sync(SignalData(signal=Signal.PASS, task_id=TaskId("t1"), source=AgentId("d")))

    assert len(rejections) == 1
    assert rejections[0][1] == "PASS"
    engine.stop()
