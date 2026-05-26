"""Zero-shot comparison on BigCodeBench: with vs without explicit criteria.

No GFSO loop, no rework — single attempt per task per mode. Tests whether
showing the unit-test code upfront (as explicit acceptance criteria, per
GFSO §3.2) raises baseline pass rate vs the standard "docstring only" prompt.

Usage:
  python scripts/run_bcb_zeroshot.py BigCodeBench/15            # one task
  python scripts/run_bcb_zeroshot.py all                        # full BCB-Hard
  python scripts/run_bcb_zeroshot.py --full all                 # full BCB (1140)

Output: runs/bench_results_zeroshot.json
Logs:   runs/bench_logs_zeroshot/{task}.log
"""
from __future__ import annotations

import io
import json
import logging
import os
import re
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")

from anthropic import Anthropic

from bench import RetryClient
from bench.providers import BigCodeBenchProvider
from bench.logging_setup import setup_task_log
from bench.scorer import save_result, load_results


MODEL = "claude-haiku-4-5-20251001"
RESULTS_FILE = "runs/bench_results_zeroshot.json"
LOGS_DIR = "runs/bench_logs_zeroshot"

client = RetryClient(Anthropic())

SYSTEM = (
    "Complete the given Python function. Return the COMPLETE module: imports + full function "
    "with body. Output ONLY Python code in a ```python block. No test code."
)


def _docstring_only_prompt(complete_prompt: str) -> str:
    return (
        "Complete the following Python function. Return the COMPLETE module: "
        "all imports + the full function with body.\n\n"
        f"{complete_prompt}"
    )


def _docstring_plus_tests_prompt(complete_prompt: str, test_code: str) -> str:
    return (
        "Complete the following Python function. Return the COMPLETE module: "
        "all imports + the full function with body. Do NOT include test code in your output.\n\n"
        f"{complete_prompt}\n\n"
        "ACCEPTANCE CRITERIA — your solution will be verified by the following unit tests. "
        "Implement the function so that ALL tests pass.\n\n"
        f"```python\n{test_code}\n```"
    )


def _extract_code(raw: str) -> str:
    blocks = re.findall(r"```(?:python)?\s*\n(.*?)```", raw, re.DOTALL)
    return blocks[-1].strip() if blocks else raw.strip()


def _call(prompt: str) -> tuple[str, int]:
    resp = client.messages.create(
        model=MODEL, max_tokens=4096, system=SYSTEM,
        messages=[{"role": "user", "content": prompt}],
    )
    raw = resp.content[0].text
    tokens = resp.usage.input_tokens + resp.usage.output_tokens
    return _extract_code(raw), tokens


def _run_mode(label: str, prompt: str, task) -> dict:
    log = logging.getLogger(__name__)
    code, tokens = _call(prompt)
    log.info(f"[{label}] tokens={tokens}")
    log.info(f"[{label}] code:\n{code}")
    results = task.evaluate_hidden(code)
    passed = sum(1 for r in results if r.passed)
    total = len(results)
    failures = [f"{r.check_name}: {r.details[:200]}" for r in results if not r.passed]
    log.info(f"[{label}] {passed}/{total}")
    return {
        "solved": passed == total and total > 0,
        "hidden_passed": passed,
        "hidden_total": total,
        "tokens": tokens,
        "code_len_lines": len(code.splitlines()),
        "hidden_failures": failures,
    }


def run_one(provider, task_id: str) -> dict:
    task = provider.get_task(task_id)
    setup_task_log(LOGS_DIR, task_id)

    complete_prompt = task.metadata.get("test_code") and task.metadata
    # Recover the raw complete_prompt from the provider's row
    row = provider._by_id[task_id]
    docstring_prompt = _docstring_only_prompt(row["complete_prompt"])
    tests_prompt = _docstring_plus_tests_prompt(row["complete_prompt"], row["test"])

    print(f"[{task_id}] -- {len(task.spec.criteria)} criteria")
    no_spec = _run_mode("NO_SPEC", docstring_prompt, task)
    with_spec = _run_mode("WITH_SPEC", tests_prompt, task)

    result = {
        "task_id": task_id,
        "title": task_id,
        "metadata": task.metadata,
        "oneshot": no_spec,         # A = no explicit criteria
        "gfso": with_spec,          # B = explicit criteria (no loop)
        "delta": {
            "hidden_tests": with_spec["hidden_passed"] - no_spec["hidden_passed"],
            "solved": with_spec["solved"] and not no_spec["solved"],
        },
    }
    a, b = no_spec, with_spec
    astr = "SOLVED" if a["solved"] else "FAIL"
    bstr = "SOLVED" if b["solved"] else "FAIL"
    print(f"  NO_SPEC:   {a['hidden_passed']}/{a['hidden_total']} {astr} | {a['tokens']} tok")
    print(f"  WITH_SPEC: {b['hidden_passed']}/{b['hidden_total']} {bstr} | {b['tokens']} tok")
    print(f"  Delta: {result['delta']['hidden_tests']:+d} tests")
    return result


def main():
    args = sys.argv[1:]
    full = "--full" in args
    args = [a for a in args if a != "--full"]

    provider = BigCodeBenchProvider(split="v0.1.4", hard=not full)
    if args and args[0] == "all":
        ids = provider.all_task_ids()
    elif not args:
        print("Usage: python scripts/run_bcb_zeroshot.py [--full] <task_id|all> ...")
        sys.exit(1)
    else:
        ids = args

    print(f"Running {len(ids)} tasks (full={full})")
    for tid in ids:
        try:
            result = run_one(provider, tid)
            save_result(RESULTS_FILE, result)
        except Exception as e:
            print(f"[{tid}] FAILED: {type(e).__name__}: {e}")
            logging.getLogger(__name__).exception(f"task {tid} crashed")

    data = load_results(RESULTS_FILE)
    s = data.get("summary", {})
    print("\n" + "=" * 70)
    print(f"ZERO-SHOT SUMMARY ({s.get('total_problems', 0)} tasks)")
    print("=" * 70)
    print(f"  NO_SPEC solved:   {s.get('oneshot_solved', 0)} ({s.get('oneshot_solved_pct', 0)}%)")
    print(f"  WITH_SPEC solved: {s.get('gfso_solved', 0)} ({s.get('gfso_solved_pct', 0)}%)")
    print(f"  WITH_SPEC better: {s.get('gfso_better', 0)}")
    print(f"  same:             {s.get('gfso_same', 0)}")
    print(f"  WITH_SPEC worse:  {s.get('gfso_worse', 0)}")
    print(f"  Tokens A/B:       {s.get('oneshot_total_tokens', 0)} / {s.get('gfso_total_tokens', 0)}")
    print("=" * 70)


if __name__ == "__main__":
    main()
