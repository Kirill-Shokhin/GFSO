"""
LEGACY: GFSO Benchmark with PERFECT criteria proxy (verifier sees hidden tests).

Was used once to probe the GFSO loop's ceiling on LiveCodeBench when criteria
equal ground-truth hidden tests. Lessons distilled into docs/EVIDENCE_LOG.md.
Kept for reference; not in the active path.

Usage:
  python scripts/bench_perfect.py 3
  python scripts/bench_perfect.py 2 3 6
  python scripts/bench_perfect.py all

Results: runs/bench_results_perfect.json
Logs:    runs/bench_logs_perfect/{idx}.log
"""
import os
import sys
import json
import logging

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import bench_single as bs
from gfso.core.types import TaskId, AgentId, Spec, Criteria
from gfso.adapters.storage.memory import MemoryStorage
from gfso.adapters.verifiers import SubprocessVerifier as CodeVerifier
from bench.bench_agent import BenchAgent
from gfso.engine import Engine

bs.RESULTS_FILE = "runs/bench_results_perfect.json"
bs.LOGS_DIR = "runs/bench_logs_perfect"


def run_gfso_perfect(problem, hidden_tests):
    """Like bs.run_gfso, but criteria=hidden tests (verifier-only). Prompt shows only public examples."""
    log = logging.getLogger(__name__)
    content = bs.clean_content(problem)
    pub = json.loads(problem['public_test_cases'])
    examples = "\n".join(
        f"Input:\n{t['input'].strip()}\nOutput:\n{t['output'].strip()}" for t in pub
    )
    starter_code = problem.get('starter_code', '')
    if starter_code:
        problem_prompt = f"{content}\n\nExamples:\n{examples}\n\nComplete this function:\n{starter_code}"
    else:
        problem_prompt = f"{content}\n\nExamples:\n{examples}"

    # criteria for verifier = all hidden tests
    criteria = tuple(
        Criteria(name=f"test_{i}", input=tc['input'].rstrip('\n'), expected=tc['output'].rstrip('\n'))
        for i, tc in enumerate(hidden_tests)
    )

    # criteria_text for LLM prompt = short summary only (hidden inputs not revealed)
    criteria_text = (
        f"Solution must pass all {len(criteria)} test cases.\n"
        f"Public examples shown above. Additional hidden tests will validate edge cases and constraints."
    )

    spec = Spec(description=problem_prompt, criteria=criteria, accepted_risks=())
    storage = MemoryStorage()
    example_input = pub[0]['input'] if pub else ""
    verifier = CodeVerifier(storage, example_input, starter_code=starter_code)
    agent = BenchAgent(
        client=bs.client, model=bs.MODEL, verifier=verifier,
        problem_prompt=problem_prompt, criteria_text=criteria_text,
        is_function=bool(starter_code),
    )
    engine = Engine(storage=storage, agents=agent, llm=None, validate_signals=False)
    engine.start()

    task_id = TaskId("bench-0")
    engine.assign_task(task_id, spec, AgentId("haiku"), max_iterations=3)
    engine.wait_idle()

    final_state = engine.get_state(task_id)
    task = engine.get_task(task_id)

    history = agent.code_history.get(task_id, [])
    cr = agent.criteria_results
    if history and cr and len(history) == len(cr):
        best_idx = max(range(len(cr)), key=lambda i: cr[i]['passed'])
        code = history[best_idx]
        log.info(f"[GFSO] best iteration: {best_idx} ({cr[best_idx]['passed']}/{cr[best_idx]['total']} criteria)")
    else:
        code = agent.code.get(task_id, "")

    log.info(f"[GFSO] Final state: {final_state.name if final_state else '?'}")
    log.info(f"[GFSO] Iterations: {task.iteration if task else '?'}")

    hidden_results = bs.run_hidden_tests(code, hidden_tests, starter_code)
    hidden_passed = sum(1 for r in hidden_results if r.passed)
    hidden_failures = [f"{r.check_name}: {r.details[:200]}" for r in hidden_results if not r.passed]

    engine.stop()

    return {
        "solved": hidden_passed == len(hidden_tests),
        "hidden_passed": hidden_passed,
        "hidden_total": len(hidden_tests),
        "tokens": agent.total_tokens,
        "tokens_per_call": agent.tokens_per_call,
        "iterations": task.iteration if task else 0,
        "final_state": final_state.name if final_state else "?",
        "criteria_results": agent.criteria_results,
        "hidden_failures": hidden_failures,
    }


def run_problem_perfect(problems, idx):
    p = problems[idx]
    bs.setup_problem_log(idx)
    log = logging.getLogger(__name__)
    title = p.get('question_title', '?')
    rating = p.get('contest_id', '?')
    hidden = bs.get_hidden_tests(p)
    print(f"[{idx}] {title} ({rating}) -- {len(hidden)} hidden tests (= criteria)")

    gfso = run_gfso_perfect(p, hidden)
    attempts = len(gfso['tokens_per_call'])
    oneshot = bs.run_oneshot(p, hidden, attempts=attempts)

    result = {
        "problem_index": idx,
        "platform": p.get('platform', 'unknown'),
        "title": title,
        "oneshot": oneshot,
        "gfso": gfso,
        "delta": {
            "solved": int(gfso['solved']) - int(oneshot['solved']),
            "hidden_tests": gfso['hidden_passed'] - oneshot['hidden_passed'],
            "tokens": gfso['tokens'] - oneshot['tokens'],
        },
    }
    bs.save_result(result)
    a, b = oneshot, gfso
    astr = "SOLVED" if a['solved'] else "FAIL"
    bstr = "SOLVED" if b['solved'] else "FAIL"
    print(f"  A: {a['hidden_passed']}/{a['hidden_total']} {astr} | {a['tokens']} tok | best-of-{attempts}")
    print(f"  B: {b['hidden_passed']}/{b['hidden_total']} {bstr} | {b['tokens']} tok | {b['iterations']} reworks")
    print(f"  Delta: {result['delta']['hidden_tests']:+d} tests")


def main():
    args = sys.argv[1:]
    problems = bs.load_problems()
    indices = list(range(len(problems))) if args and args[0] == "all" else [int(a) for a in args]

    for idx in indices:
        try:
            run_problem_perfect(problems, idx)
        except Exception as e:
            print(f"[idx={idx}] FAILED: {type(e).__name__}: {e}")
            logging.getLogger(__name__).exception(f"problem {idx} crashed")

    data = bs.load_results()
    s = data.get('summary', {})
    print("\n" + "=" * 70)
    print(f"SUMMARY ({s.get('total_problems', 0)} problems) -- PERFECT CRITERIA")
    print("=" * 70)
    print(f"  One-shot solved: {s.get('oneshot_solved', 0)} ({s.get('oneshot_solved_pct', 0)}%)")
    print(f"  GFSO solved:     {s.get('gfso_solved', 0)} ({s.get('gfso_solved_pct', 0)}%)")
    print(f"  better:          {s.get('gfso_better', 0)}")
    print(f"  same:            {s.get('gfso_same', 0)}")
    print(f"  worse:           {s.get('gfso_worse', 0)}")
    print("=" * 70)


if __name__ == '__main__':
    main()
