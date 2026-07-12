"""GFSO Verification adapter: runs code against Spec criteria.

Criterion type determined by fields:
  - input + expected → exact output check
  - input (no expected) → crash check
  - n + timeout → performance check
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
    with tempfile.NamedTemporaryFile(mode='w', suffix='.py', delete=False, encoding='utf-8') as f:
        f.write(code)
        tmp = f.name
    # All I/O via files to avoid ANY pipe deadlock
    out_file = tmp + '.out'
    err_file = tmp + '.err'
    in_file = tmp + '.in'
    try:
        with open(in_file, 'w', encoding='utf-8') as f:
            f.write(stdin_input)
        t0 = time.time()
        with open(in_file, 'r', encoding='utf-8') as fin, \
             open(out_file, 'w', encoding='utf-8') as fout, \
             open(err_file, 'w', encoding='utf-8') as ferr:
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
                log.info(f"[run_code] TIMEOUT after {elapsed:.2f}s")
                return ExecutionResult("", "TIMEOUT", -1, elapsed, True)
        elapsed = time.time() - t0
        with open(out_file, 'r', encoding='utf-8', errors='replace') as f:
            stdout = f.read()
        with open(err_file, 'r', encoding='utf-8', errors='replace') as f:
            stderr = f.read()
        log.info(f"[run_code] rc={proc.returncode} elapsed={elapsed:.2f}s stdout={stdout.rstrip()[:500]}")
        if stderr:
            log.info(f"[run_code] stderr:\n{stderr.rstrip()[:500]}")
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
        log.info(f"[SubprocessVerifier] === VERIFICATION {task_id} ({len(spec.criteria)} criteria) ===")
        results = [self._run(deliverable, c) for c in spec.criteria]
        self._storage.store_check_results(task_id, results)
        passed = sum(1 for r in results if r.passed)
        log.info(f"[SubprocessVerifier] RESULT: {passed}/{len(results)} passed")
        return results

    def _run(self, code: str, crit: Criteria) -> CheckResult:
        if crit.input is not None and crit.expected is not None:
            return self._check_exact(code, crit)
        if crit.input is not None:
            return self._check_crash(code, crit)
        if crit.n is not None:
            return self._check_performance(code, crit)
        log.warning(f"[SubprocessVerifier] {crit.name}: no checkable fields")
        return CheckResult(crit.name, False, "No input/expected/n fields")

    def _build_runnable(self, code: str, test_input: str) -> tuple[str, str]:
        """Build runnable code + stdin. For LeetCode: harness wrapping function. For others: code as-is."""
        if self._method_name:
            # LeetCode: code = function body, wrap with harness
            args = ', '.join(s for s in test_input.split('\n') if s.strip())
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
        log.info(f"[SubprocessVerifier] {crit.name}: exact check")
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
        log.info(f"[SubprocessVerifier] {crit.name}: expected={crit.expected!r} actual={actual!r} → {'PASS' if ok else 'FAIL'}")
        return CheckResult(crit.name, ok, details)

    def _check_crash(self, code: str, crit: Criteria) -> CheckResult:
        log.info(f"[SubprocessVerifier] {crit.name}: crash check")
        runnable, stdin = self._build_runnable(code, crit.input)
        r = run_code(runnable, stdin)
        ok = r.returncode == 0 and not r.timed_out
        details = ""
        if not ok:
            details = "TIMEOUT" if r.timed_out else f"CRASH (rc={r.returncode}): {r.stderr}"
        log.info(f"[SubprocessVerifier] {crit.name}: → {'PASS' if ok else 'FAIL'}")
        return CheckResult(crit.name, ok, details)

    def _check_performance(self, code: str, crit: Criteria) -> CheckResult:
        timeout = crit.timeout or 10
        large_input = self._generate_scaled_input(crit.n)
        if not large_input:
            log.warning(f"[SubprocessVerifier] {crit.name}: cannot generate input, skipping")
            return CheckResult(crit.name, True, "skipped: cannot generate input")
        log.info(f"[SubprocessVerifier] {crit.name}: perf check n={crit.n} timeout={timeout}s ({len(large_input)} chars)")
        runnable, stdin = self._build_runnable(code, large_input)
        r = run_code(runnable, stdin, timeout=float(timeout))
        ok = r.returncode == 0 and not r.timed_out
        details = ""
        if r.timed_out:
            details = f"TIMEOUT after {r.elapsed:.1f}s on n={crit.n}"
        elif r.returncode != 0:
            details = f"CRASH on n={crit.n}: {r.stderr[:500]}"
        log.info(f"[SubprocessVerifier] {crit.name}: {r.elapsed:.2f}s → {'PASS' if ok else 'FAIL'}")
        return CheckResult(crit.name, ok, details)

    def _generate_scaled_input(self, n: int) -> str | None:
        """Scale example input to n elements. Only works for simple formats."""
        if not self._example_input:
            return None
        lines = self._example_input.strip().split('\n')
        first = lines[0].strip()
        rest = lines[1:] if len(lines) > 1 else []
        # LeetCode JSON array format — safe to scale
        if first.startswith('[') and not first.startswith('[['):
            arr = [self._rng.randint(1, 10**9) for _ in range(n)]
            scaled = json.dumps(arr)
            return '\n'.join([scaled] + rest) + '\n'
        # LeetCode string format
        if first.startswith('"'):
            scaled = '"' + ''.join(self._rng.choice('abcdefghij') for _ in range(n)) + '"'
            return '\n'.join([scaled] + rest) + '\n'
        # Other formats (AtCoder, Codeforces) — can't reliably scale
        return None
