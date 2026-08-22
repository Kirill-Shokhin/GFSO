"""GFSO verification adapter for BENCHMARK tasks: runs a delivered program against Spec criteria.

Scope, so nobody mistakes this for the product's notion of a criterion. A criterion in the canon is
a decidable condition on a task's result (A1, §2.1), and in normal use a validator reads the
delivery and runs what the criterion names. THIS adapter decides a narrower, mechanical payload —
the competitive-programming shape the E0 benchmark work needed (`docs/EVIDENCE_LOG.md` §3). It is
constructed by that harness and by nothing inside this package.

The payload rides four `Criteria` fields (`input`, `expected`, `n`, `timeout`). They are persisted
by the SQLite adapter, but **neither `create_task` nor `edit_criteria` carries them** — both build
`Criteria(name, description, depends_on=…)` and drop the rest silently — so they can only be set by
constructing `Criteria` directly, as a host or a harness does. A criterion authored through a door
therefore arrives here with none of them and is reported failed, "No input/expected/n fields".

Criterion type, dispatched in this order — first match wins:
  - input + expected → exact output check: run it, compare stdout with ALL trailing newlines
    stripped against `expected`; also requires exit 0 and no timeout
  - input, no expected → crash check: exit 0 and no timeout
  - n (no input)      → performance check: scale the example input to n elements, require it to
                        finish within `timeout` (default 10s)
  - none of them      → not decidable here; reported FAILED, never silently skipped

Two ways this passes WITHOUT measuring, both of them real:
  * The performance check needs `example_input` — a constructor argument that defaults to `""`. With
    it unset (and nothing in this package sets it) `_generate_scaled_input` returns None and the
    criterion is recorded PASSED with "skipped: cannot generate input" in its details. Even when it
    is set, scaling is defined only for a first line that is a flat JSON array or a quoted string.
    A green performance criterion is evidence of nothing until its detail line is read.
  * `starter_code` changes what a criterion MEANS. With a `def <name>(self` in it, the deliverable
    is spliced at module level, `from typing import *` is prepended, and the harness calls
    `Solution().<name>(<the input lines as literal arguments>)` — so the deliverable must itself
    define `class Solution`, stdin is empty, and `expected` is compared against `print()` of the
    returned object. Without it the deliverable is run as a program reading `input` on stdin.
"""
from __future__ import annotations

import json
import logging
import os
import random
import re
import subprocess
import sys
import tempfile
import time
from dataclasses import dataclass

from gfso.core.types import TaskId, Spec, Criteria, CheckResult, StoragePort, VerifierPort

log = logging.getLogger(__name__)


@dataclass(frozen=True)
class ExecutionResult:
    stdout: str
    stderr: str
    returncode: int
    elapsed: float
    timed_out: bool


def run_code(code: str, stdin_input: str, timeout: float = 10.0) -> ExecutionResult:
    with tempfile.NamedTemporaryFile(mode="w", suffix=".py", delete=False, encoding="utf-8") as f:
        f.write(code)
        tmp = f.name
    # All I/O via files to avoid ANY pipe deadlock
    out_file = tmp + ".out"
    err_file = tmp + ".err"
    in_file = tmp + ".in"
    try:
        with open(in_file, "w", encoding="utf-8") as f:
            f.write(stdin_input)
        t0 = time.time()
        with open(in_file, "r", encoding="utf-8") as fin, \
             open(out_file, "w", encoding="utf-8") as fout, \
             open(err_file, "w", encoding="utf-8") as ferr:
            proc = subprocess.Popen(
                [sys.executable, tmp],
                stdin=fin, stdout=fout, stderr=ferr,
                # Windows: don't pop a console window (same class as the headless adapter)
                **({"creationflags": subprocess.CREATE_NO_WINDOW} if os.name == "nt" else {}),
            )
            try:
                proc.wait(timeout=timeout)
            except subprocess.TimeoutExpired:
                proc.kill()
                proc.wait()
                elapsed = time.time() - t0
                log.info(f"TIMEOUT after {elapsed:.2f}s")
                return ExecutionResult("", "TIMEOUT", -1, elapsed, True)
        elapsed = time.time() - t0
        with open(out_file, "r", encoding="utf-8", errors="replace") as f:
            stdout = f.read()
        with open(err_file, "r", encoding="utf-8", errors="replace") as f:
            stderr = f.read()
        log.info(f"rc={proc.returncode} elapsed={elapsed:.2f}s stdout={stdout.rstrip()[:500]}")
        if stderr:
            log.info(f"stderr:\n{stderr.rstrip()[:500]}")
        return ExecutionResult(stdout, stderr, proc.returncode, elapsed, False)
    finally:
        for f in [tmp, out_file, err_file, in_file]:
            try:
                os.unlink(f)
            except OSError:
                pass


class SubprocessVerifier(VerifierPort):
    """Verifies code by running it as a Python subprocess. Supports stdin-based and
    LeetCode-style function-completion tasks (when starter_code defines a method).
    """

    def __init__(self, storage: StoragePort, example_input: str = "", seed: int = 42,
                 starter_code: str = ""):
        self._storage = storage
        self._example_input = example_input
        self._rng = random.Random(seed)
        self._starter_code = starter_code
        # Extract method name from starter_code for harness
        self._method_name = ""
        if starter_code:
            m = re.search(r'def (\w+)\(self', starter_code)
            if m:
                self._method_name = m.group(1)

    def verify(self, task_id: TaskId, deliverable: str, spec: Spec) -> list[CheckResult]:
        log.info(f"=== VERIFICATION {task_id} ({len(spec.criteria)} criteria) ===")
        results = [self._run(deliverable, c) for c in spec.criteria]
        self._storage.store_check_results(task_id, results)
        passed = sum(1 for r in results if r.passed)
        log.info(f"RESULT: {passed}/{len(results)} passed")
        return results

    def _run(self, code: str, crit: Criteria) -> CheckResult:
        if crit.input is not None and crit.expected is not None:
            return self._check_exact(code, crit)
        if crit.input is not None:
            return self._check_crash(code, crit)
        if crit.n is not None:
            return self._check_performance(code, crit)
        log.warning(f"{crit.name}: no checkable fields")
        return CheckResult(crit.name, False, "No input/expected/n fields")

    def _build_runnable(self, code: str, test_input: str) -> tuple[str, str]:
        """Build runnable code + stdin. For LeetCode: harness wrapping function. For others: code as-is."""
        if self._method_name:
            # LeetCode: code = function body, wrap with harness
            args = ", ".join(s for s in test_input.split('\n') if s.strip())
            harness = (
                "from typing import *\n"
                f"{code}\n"
                f"sol = Solution()\n"
                f"print(sol.{self._method_name}({args}))\n"
            )
            return harness, ""
        else:
            # Codeforces/AtCoder: code reads stdin
            return code, test_input

    def _check_exact(self, code: str, crit: Criteria) -> CheckResult:
        log.info(f"{crit.name}: exact check")
        runnable, stdin = self._build_runnable(code, crit.input)
        r = run_code(runnable, stdin)
        actual = r.stdout.rstrip('\n')
        ok = (actual == crit.expected) and r.returncode == 0 and not r.timed_out
        details = ""
        if not ok:
            if r.timed_out:
                details = "TIMEOUT"
            elif r.returncode != 0:
                details = f"CRASH: {r.stderr}"
            else:
                details = f"input={crit.input!r} expected={crit.expected!r} got={actual!r}"
        log.info(f"{crit.name}: expected={crit.expected!r} actual={actual!r} → {'PASS' if ok else 'FAIL'}")
        return CheckResult(crit.name, ok, details)

    def _check_crash(self, code: str, crit: Criteria) -> CheckResult:
        log.info(f"{crit.name}: crash check")
        runnable, stdin = self._build_runnable(code, crit.input)
        r = run_code(runnable, stdin)
        ok = r.returncode == 0 and not r.timed_out
        details = ""
        if not ok:
            details = "TIMEOUT" if r.timed_out else f"CRASH (rc={r.returncode}): {r.stderr}"
        log.info(f"{crit.name}: → {'PASS' if ok else 'FAIL'}")
        return CheckResult(crit.name, ok, details)

    def _check_performance(self, code: str, crit: Criteria) -> CheckResult:
        timeout = crit.timeout or 10
        large_input = self._generate_scaled_input(crit.n)
        if not large_input:
            log.warning(f"{crit.name}: cannot generate input, skipping")
            return CheckResult(crit.name, True, "skipped: cannot generate input")
        log.info(f"{crit.name}: perf check n={crit.n} timeout={timeout}s ({len(large_input)} chars)")
        runnable, stdin = self._build_runnable(code, large_input)
        r = run_code(runnable, stdin, timeout=float(timeout))
        ok = r.returncode == 0 and not r.timed_out
        details = ""
        if r.timed_out:
            details = f"TIMEOUT after {r.elapsed:.1f}s on n={crit.n}"
        elif r.returncode != 0:
            details = f"CRASH on n={crit.n}: {r.stderr[:500]}"
        log.info(f"{crit.name}: {r.elapsed:.2f}s → {'PASS' if ok else 'FAIL'}")
        return CheckResult(crit.name, ok, details)

    def _generate_scaled_input(self, n: int) -> str | None:
        """Scale example input to n elements. Only works for simple formats."""
        if not self._example_input:
            return None
        lines = self._example_input.strip().split('\n')
        first = lines[0].strip()
        rest = lines[1:] if len(lines) > 1 else []
        # LeetCode JSON array format — safe to scale
        if first.startswith("[") and not first.startswith("[["):
            arr = [self._rng.randint(1, 10**9) for _ in range(n)]
            scaled = json.dumps(arr)
            return '\n'.join([scaled] + rest) + '\n'
        # LeetCode string format
        if first.startswith('"'):
            scaled = '"' + "".join(self._rng.choice("abcdefghij") for _ in range(n)) + '"'
            return '\n'.join([scaled] + rest) + '\n'
        # Other formats (AtCoder, Codeforces) — can't reliably scale
        return None
