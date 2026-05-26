"""BenchRunner: orchestrates A vs B per task. Provider-agnostic."""
from __future__ import annotations

import logging

from .provider import BenchProvider
from .task import BenchTask
from .oneshot import run_oneshot
from .gfso_runner import run_gfso
from .scorer import save_result, load_results
from .logging_setup import setup_task_log


class BenchRunner:
    def __init__(self, provider: BenchProvider, client, model: str,
                 results_file: str, logs_dir: str,
                 max_iterations: int = 3,
                 gfso_criteria_text=None):
        self.provider = provider
        self.client = client
        self.model = model
        self.results_file = results_file
        self.logs_dir = logs_dir
        self.max_iterations = max_iterations
        self._gfso_criteria_text = gfso_criteria_text  # callable(task) -> str | None

    def run_one(self, task_id: str) -> dict:
        task = self.provider.get_task(task_id)
        setup_task_log(self.logs_dir, task_id)
        log = logging.getLogger(__name__)

        n_criteria = len(task.spec.criteria)
        print(f"[{task_id}] {task.title} -- {n_criteria} criteria")

        crit_text = self._gfso_criteria_text(task) if self._gfso_criteria_text else None
        gfso = run_gfso(self.client, self.model, task,
                        max_iterations=self.max_iterations,
                        criteria_text=crit_text)
        attempts = max(1, len(gfso["tokens_per_call"]))
        oneshot = run_oneshot(self.client, self.model, task, attempts=attempts)

        result = {
            "task_id": task_id,
            "title": task.title,
            "metadata": task.metadata,
            "oneshot": oneshot,
            "gfso": gfso,
            "delta": {
                "hidden_tests": gfso["hidden_passed"] - oneshot["hidden_passed"],
                "solved": gfso["solved"] and not oneshot["solved"],
            },
        }
        a, b = oneshot, gfso
        astr = "SOLVED" if a["solved"] else "FAIL"
        bstr = "SOLVED" if b["solved"] else "FAIL"
        print(f"  A: {a['hidden_passed']}/{a['hidden_total']} {astr} | {a['tokens']} tok | best-of-{attempts}")
        print(f"  B: {b['hidden_passed']}/{b['hidden_total']} {bstr} | {b['tokens']} tok | {b['iterations']} reworks")
        print(f"  Delta: {result['delta']['hidden_tests']:+d} tests")
        return result

    def run_many(self, task_ids: list[str]) -> None:
        for tid in task_ids:
            try:
                result = self.run_one(tid)
                save_result(self.results_file, result)
            except Exception as e:
                print(f"[{tid}] FAILED: {type(e).__name__}: {e}")
                logging.getLogger(__name__).exception(f"task {tid} crashed")
        self._print_summary()

    def _print_summary(self):
        data = load_results(self.results_file)
        s = data.get("summary", {})
        print("\n" + "=" * 70)
        print(f"SUMMARY ({s.get('total_problems', 0)} tasks)")
        print("=" * 70)
        print(f"  A solved:    {s.get('oneshot_solved', 0)} ({s.get('oneshot_solved_pct', 0)}%)")
        print(f"  B solved:    {s.get('gfso_solved', 0)} ({s.get('gfso_solved_pct', 0)}%)")
        print(f"  better:      {s.get('gfso_better', 0)}")
        print(f"  same:        {s.get('gfso_same', 0)}")
        print(f"  worse:       {s.get('gfso_worse', 0)}")
        print(f"  Tokens A/B:  {s.get('oneshot_total_tokens', 0)} / {s.get('gfso_total_tokens', 0)}")
        print("=" * 70)
