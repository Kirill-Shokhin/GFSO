"""Run GFSO benchmark on LiveCodeBench medium subset.

Usage:
  python scripts/run_livecodebench.py 3
  python scripts/run_livecodebench.py 0 1 2 6 8
  python scripts/run_livecodebench.py all
"""
import io
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")

from anthropic import Anthropic

from bench import BenchRunner, RetryClient
from bench.providers import LiveCodeBenchProvider


MODEL = "claude-haiku-4-5-20251001"
RESULTS_FILE = "runs/bench_results.json"
LOGS_DIR = "runs/bench_logs"


def main():
    args = sys.argv[1:] or ["3"]
    provider = LiveCodeBenchProvider(difficulty="medium")
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
    )
    runner.run_many(ids)


if __name__ == "__main__":
    main()
