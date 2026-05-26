"""LiveCodeBench provider: loads competitive programming tasks + bench_inputs.json criteria."""
from __future__ import annotations

import base64
import json
import logging
import pickle
import re
import zlib
from typing import Iterator

from huggingface_hub import hf_hub_download

from gfso.core.types import Spec, Criteria, CheckResult
from gfso.adapters.verifiers import SubprocessVerifier, run_code

from ..task import BenchTask
from ..provider import BenchProvider

log = logging.getLogger(__name__)


def _clean_content(problem: dict) -> str:
    c = re.sub(r"<[^>]+>", "", problem["question_content"])
    return c.replace("&lt;", "<").replace("&gt;", ">").replace("&amp;", "&")


def _hidden_tests(problem: dict) -> list[dict]:
    pub = json.loads(problem["public_test_cases"])
    raw = base64.b64decode(problem["private_test_cases"])
    priv = json.loads(pickle.loads(zlib.decompress(raw)))
    return pub + priv


def _build_hidden_evaluator(problem: dict):
    """Returns a callable(code) -> list[CheckResult] that runs all hidden tests."""
    tests = _hidden_tests(problem)
    starter_code = problem.get("starter_code", "")
    method_name = ""
    if starter_code:
        m = re.search(r"def (\w+)\(self", starter_code)
        if m:
            method_name = m.group(1)

    def evaluate(code: str) -> list[CheckResult]:
        results = []
        for i, tc in enumerate(tests):
            if method_name:
                args = ", ".join(tc["input"].rstrip("\n").split("\n"))
                runnable = f"from typing import *\n{code}\nsol = Solution()\nprint(sol.{method_name}({args}))\n"
                r = run_code(runnable, "")
            else:
                r = run_code(code, tc["input"])
            exp = tc["output"].rstrip("\n")
            act = r.stdout.rstrip("\n")
            ok = (act == exp) and r.returncode == 0 and not r.timed_out
            details = ""
            if not ok:
                if r.timed_out:
                    details = "TIMEOUT"
                elif r.returncode != 0:
                    details = f"CRASH: {r.stderr}"
                else:
                    details = f"WRONG: expected={exp!r} actual={act!r}"
            results.append(CheckResult(check_name=f"hidden_{i}", passed=ok, details=details))
        return results
    return evaluate


class LiveCodeBenchProvider(BenchProvider):
    name = "livecodebench"

    def __init__(self, difficulty: str = "medium", bench_inputs_path: str = "data/bench_inputs.json"):
        self.difficulty = difficulty
        self._problems = self._load_problems(difficulty)
        with open(bench_inputs_path, encoding="utf-8") as f:
            self._inputs_by_idx = {e["problem_index"]: e for e in json.load(f)}

    @staticmethod
    def _load_problems(difficulty: str) -> list[dict]:
        f = hf_hub_download("livecodebench/code_generation_lite", "test.jsonl", repo_type="dataset")
        out = []
        with open(f, encoding="utf-8") as fp:
            for line in fp:
                p = json.loads(line)
                if p["difficulty"] == difficulty:
                    out.append(p)
        return out

    def all_task_ids(self) -> list[str]:
        return [str(i) for i in self._inputs_by_idx.keys()]

    def get_task(self, task_id: str) -> BenchTask:
        idx = int(task_id)
        problem = self._problems[idx]
        bench_input = self._inputs_by_idx[idx]

        content = _clean_content(problem)
        pub = json.loads(problem["public_test_cases"])
        examples = "\n".join(
            f"Input:\n{t['input'].strip()}\nOutput:\n{t['output'].strip()}" for t in pub
        )
        starter_code = problem.get("starter_code", "")
        if starter_code:
            prompt = f"{content}\n\nExamples:\n{examples}\n\nComplete this function:\n{starter_code}"
        else:
            prompt = f"{content}\n\nExamples:\n{examples}"

        criteria = tuple(Criteria(
            name=c["name"],
            description=c.get("description", ""),
            input=c.get("input"),
            expected=c.get("expected"),
            n=c.get("n"),
            timeout=c.get("timeout"),
        ) for c in bench_input["criteria"])
        neglected = tuple(bench_input.get("neglected", []))
        spec = Spec(description=prompt, criteria=criteria, neglected=neglected)

        example_input = pub[0]["input"] if pub else ""
        captured_starter = starter_code
        captured_example = example_input
        def make_verifier(storage):
            return SubprocessVerifier(storage, captured_example, starter_code=captured_starter)

        return BenchTask(
            task_id=task_id,
            title=problem.get("question_title", task_id),
            problem_prompt=prompt,
            is_function=bool(starter_code),
            spec=spec,
            make_verifier=make_verifier,
            evaluate_hidden=_build_hidden_evaluator(problem),
            metadata={
                "platform": problem.get("platform", "unknown"),
                "contest_id": problem.get("contest_id"),
                "difficulty": self.difficulty,
            },
        )
