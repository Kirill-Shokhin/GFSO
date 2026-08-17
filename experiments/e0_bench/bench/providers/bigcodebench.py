"""BigCodeBench-Hard provider: function-completion tasks with unittest TestCases."""
from __future__ import annotations

import logging
import re

from datasets import load_dataset

from gfso.core.types import Spec, Criteria
from gfso.adapters.verifiers import UnittestVerifier, evaluate_unittest

from ..task import BenchTask
from ..provider import BenchProvider

log = logging.getLogger(__name__)


def _extract_test_names(test_code: str) -> list[str]:
    return re.findall(r"def\s+(test_\w+)\s*\(\s*self", test_code)


def _build_prompt(complete_prompt: str, test_code: str) -> str:
    """Frame the BCB function-completion task for the agent.

    Per GFSO §3.2, criteria are explicit predicates known up front. For BCB
    those are the unit tests — include them in the initial prompt as the
    acceptance contract. Both A (one-shot) and B (GFSO loop) see the same
    spec; B additionally gets failure-detail feedback on rework.
    """
    return (
        f"Complete the following Python function. Return the COMPLETE module: "
        f"all imports + the full function with body. Do NOT include test code "
        f"in your output.\n\n"
        f"{complete_prompt}\n\n"
        f"ACCEPTANCE CRITERIA — your solution will be verified by the following "
        f"unit tests. Implement the function so that ALL tests pass.\n\n"
        f"```python\n{test_code}\n```"
    )


class BigCodeBenchProvider(BenchProvider):
    name = "bigcodebench_hard"

    def __init__(self, split: str = "v0.1.4", hard: bool = True, verify_timeout: float = 60.0):
        repo = "bigcode/bigcodebench-hard" if hard else "bigcode/bigcodebench"
        self._ds = load_dataset(repo, split=split)
        self._by_id = {row["task_id"]: row for row in self._ds}
        self._verify_timeout = verify_timeout

    def all_task_ids(self) -> list[str]:
        return list(self._by_id.keys())

    def get_task(self, task_id: str) -> BenchTask:
        row = self._by_id[task_id]
        complete_prompt = row["complete_prompt"]
        test_code = row["test"]
        entry_point = row["entry_point"]

        prompt = _build_prompt(complete_prompt, test_code)
        test_names = _extract_test_names(test_code)
        criteria = tuple(Criteria(name=n, description=f"unittest method {n}") for n in test_names)
        spec = Spec(description=prompt, criteria=criteria, accepted_risks=())

        captured_test = test_code
        captured_timeout = self._verify_timeout
        def make_verifier(storage):
            return UnittestVerifier(storage, test_code=captured_test, timeout=captured_timeout)
        def evaluate_hidden(code: str):
            return evaluate_unittest(code, captured_test, timeout=captured_timeout)

        return BenchTask(
            task_id=task_id,
            title=task_id,
            problem_prompt=prompt,
            is_function=True,
            spec=spec,
            make_verifier=make_verifier,
            evaluate_hidden=evaluate_hidden,
            metadata={
                "entry_point": entry_point,
                "libs": list(row.get("libs") or []),
                "split": "hard",
                "test_code": test_code,
            },
        )
