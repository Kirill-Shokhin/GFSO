"""Run GFSO benchmark on BigCodeBench-Hard (148 tasks).

Phase 1 of the GFSO roadmap: tests the criteria-gate loop with strong
ground-truth criteria (real unittest methods, written by humans).

Usage:
  python scripts/run_bcb.py BigCodeBench/13
  python scripts/run_bcb.py BigCodeBench/13 BigCodeBench/27
  python scripts/run_bcb.py all
"""
import io
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")

from anthropic import Anthropic

from bench import BenchRunner, RetryClient
from bench.providers import BigCodeBenchProvider


MODEL = "claude-haiku-4-5-20251001"
RESULTS_FILE = "runs/bench_results_bcb.json"
LOGS_DIR = "runs/bench_logs_bcb"


def short_criteria_text(task):
    """The full test code is already in problem_prompt (seen by both A and B).
    In the GFSO loop's own prompt section, just point at it — no duplication."""
    n = len(task.spec.criteria)
    return f"Acceptance: all {n} unit tests in the problem above must pass."


def main():
    args = sys.argv[1:]
    if not args:
        print("Usage: python scripts/run_bcb.py <task_id> [task_id ...] | all")
        sys.exit(1)

    provider = BigCodeBenchProvider(split="v0.1.4", hard=True)
    if args[0] == "all":
        ids = provider.all_task_ids()
    else:
        ids = args

    client = RetryClient(Anthropic())
    runner = BenchRunner(
        provider=provider,
        client=client,
        model=MODEL,
        results_file=RESULTS_FILE,
        logs_dir=LOGS_DIR,
        max_iterations=3,
        gfso_criteria_text=short_criteria_text,
    )
    runner.run_many(ids)


if __name__ == "__main__":
    main()
