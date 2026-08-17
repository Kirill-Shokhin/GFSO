"""Runs one BenchTask through the GFSO FSM loop. Picks best iteration by criteria pass count."""
from __future__ import annotations

import logging

from gfso.core.types import TaskId, AgentId, Criteria
from gfso.adapters.storage.memory import MemoryStorage
from bench.bench_agent import BenchAgent
from gfso.engine import Engine

from .task import BenchTask

log = logging.getLogger(__name__)


def _format_criterion(c: Criteria) -> str:
    """Render a criterion in a form suitable for the LLM prompt."""
    def esc(s):
        return s.replace("\n", "\\n") if s else s
    if c.input and c.expected:
        return f"- {c.name}: Returns {esc(c.expected)} for input: {esc(c.input)}"
    if c.input:
        return f"- {c.name}: Does not crash on input: {esc(c.input)}"
    if c.n:
        return f"- {c.name}: Completes within {c.timeout or 10}s for n={c.n}"
    return f"- {c.name}: {c.description}"


def run_gfso(client, model: str, task: BenchTask,
             max_iterations: int = 3,
             criteria_text: str | None = None) -> dict:
    """Run task through GFSO FSM loop.

    `criteria_text` is what the LLM sees about criteria in its prompt. If None,
    each criterion is rendered via _format_criterion. For 'perfect-criteria'
    experiments you can pass a short summary instead, to keep criteria details
    hidden until they fail.
    """
    if criteria_text is None:
        criteria_text = "\n".join(_format_criterion(c) for c in task.spec.criteria)

    storage = MemoryStorage()
    verifier = task.make_verifier(storage)
    agent = BenchAgent(
        client=client, model=model, verifier=verifier,
        problem_prompt=task.problem_prompt, criteria_text=criteria_text,
        is_function=task.is_function,
    )
    engine = Engine(storage=storage, agents=agent, llm=None, validate_signals=False)
    engine.start()

    tid = TaskId("bench-0")
    engine.assign_task(tid, task.spec, AgentId("haiku"), max_iterations=max_iterations)
    engine.wait_idle()

    final_state = engine.get_state(tid)
    fsm_task = engine.get_task(tid)

    # Best iteration by criteria pass count (symmetric to A's best-of-k)
    history = agent.code_history.get(tid, [])
    cr = agent.criteria_results
    if history and cr and len(history) == len(cr):
        best_idx = max(range(len(cr)), key=lambda i: cr[i]["passed"])
        code = history[best_idx]
        log.info(f"[GFSO] best iteration: {best_idx} ({cr[best_idx]['passed']}/{cr[best_idx]['total']} criteria)")
    else:
        code = agent.code.get(tid, "")

    log.info(f"[GFSO] Final state: {final_state.name if final_state else '?'}")
    log.info(f"[GFSO] Iterations: {fsm_task.iteration if fsm_task else '?'}")
    for e in engine.audit_log(tid):
        old = e.old_state.name if e.old_state else "-"
        new = e.new_state.name if e.new_state else "-"
        log.info(f"[GFSO]   {e.signal.name}: {old} -> {new}")

    hidden_results = task.evaluate_hidden(code)
    passed = sum(1 for r in hidden_results if r.passed)
    total = len(hidden_results)
    failures = [f"{r.check_name}: {r.details[:200]}" for r in hidden_results if not r.passed]

    engine.stop()

    return {
        "solved": passed == total and total > 0,
        "hidden_passed": passed,
        "hidden_total": total,
        "tokens": agent.total_tokens,
        "tokens_per_call": agent.tokens_per_call,
        "iterations": fsm_task.iteration if fsm_task else 0,
        "final_state": final_state.name if final_state else "?",
        "criteria_results": agent.criteria_results,
        "hidden_failures": failures,
    }
