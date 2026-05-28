"""Baseline A: one-shot best-of-k. Same compute budget as the GFSO loop."""
from __future__ import annotations

import logging
import re

from .task import BenchTask

log = logging.getLogger(__name__)


def _extract_code(raw: str) -> str:
    blocks = re.findall(r"```(?:python)?\s*\n(.*?)```", raw, re.DOTALL)
    return blocks[-1].strip() if blocks else raw.strip()


def _one_attempt(client, model: str, task: BenchTask) -> tuple[str, int]:
    if task.is_function:
        system = (
            "Complete the given Python function. Return the COMPLETE module: imports + full function "
            "with body. Output ONLY Python code in a ```python block. No test code."
        )
    else:
        system = "Solve this. Output ONLY Python code in a ```python block."

    resp = client.messages.create(
        model=model,
        max_tokens=4096,
        system=system,
        messages=[{"role": "user", "content": task.problem_prompt}],
    )
    raw = resp.content[0].text
    tokens = resp.usage.input_tokens + resp.usage.output_tokens
    code = _extract_code(raw)
    log.info(f"[OneShot] tokens={tokens}")
    log.info(f"[OneShot] code:\n{code}")
    return code, tokens


def run_oneshot(client, model: str, task: BenchTask, attempts: int = 1) -> dict:
    """Best-of-k attempts. Picks the attempt with the highest hidden-eval pass count."""
    best_passed = -1
    best_total = 0
    best_failures: list[str] = []
    total_tokens = 0
    for i in range(attempts):
        code, tokens = _one_attempt(client, model, task)
        total_tokens += tokens
        results = task.evaluate_hidden(code)
        passed = sum(1 for r in results if r.passed)
        total = len(results)
        failures = [f"{r.check_name}: {r.details[:200]}" for r in results if not r.passed]
        log.info(f"[OneShot] attempt {i+1}/{attempts}: {passed}/{total}")
        if passed > best_passed:
            best_passed, best_total, best_failures = passed, total, failures

    return {
        "solved": best_passed == best_total and best_total > 0,
        "hidden_passed": best_passed,
        "hidden_total": best_total,
        "tokens": total_tokens,
        "attempts": attempts,
        "hidden_failures": best_failures,
    }
