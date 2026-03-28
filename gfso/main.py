"""CLI entry point — Level 3 (specific system)."""
import logging

from gfso.core.types import TaskId, AgentId, Spec, Criteria, Signal
from gfso.engine import Engine
from gfso.adapters.storage.memory import MemoryStorage
from gfso.adapters.agents.human import HumanAgent
from gfso.adapters.llm.stub import StubLLM


def main():
    logging.basicConfig(level=logging.INFO, format="%(message)s")

    engine = Engine(
        storage=MemoryStorage(),
        agents=HumanAgent(),
        llm=StubLLM(),
        check_interval=5.0,
    )

    engine.on_transition(lambda tid, old, new, sig:
        print(f"  [{tid}] {old.name} -> {new.name} ({sig.name})")
    )

    engine.start()

    # Demo
    task = engine.assign_task(
        task_id=TaskId("t1"),
        spec=Spec(
            description="Build v2.0 release",
            criteria=(Criteria("tests_pass", "All tests pass"),),
            neglected=("edge cases in legacy API",),
        ),
        assignee=AgentId("dev-1"),
    )

    try:
        engine.wait_idle()
        print(f"\nTask t1 state: {engine.get_state(TaskId('t1')).name}")
        print(f"Audit entries: {len(engine.audit_log())}")
        print(f"Metrics: {engine.metrics()}")
    except KeyboardInterrupt:
        engine.stop()


if __name__ == "__main__":
    main()
