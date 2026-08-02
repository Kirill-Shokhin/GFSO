"""Unittest-based verifier: runs Python unittest.TestCase suite in a subprocess.

Used for BigCodeBench-style tasks where each `def test_case_N(self)` in a
TestCases class is one criterion.
"""
from __future__ import annotations

import json
import logging
import os
import re
import subprocess
import sys
import tempfile

from gfso.core.types import TaskId, Spec, CheckResult, StoragePort, VerifierPort

log = logging.getLogger(__name__)


# Runner appended to (model_code + test_code) to emit JSON-per-test results.
_RUNNER = r"""
import sys, json, unittest, io
loader = unittest.TestLoader()
try:
    suite = loader.loadTestsFromTestCase(TestCases)
except Exception as e:
    print("__GFSO_VERIFIER_LOAD_FAIL__:" + repr(e))
    sys.exit(0)

# Collect test ids BEFORE run() — TestSuite.run() with default _cleanup=True
# replaces each test with None after executing it.
def iter_cases(s):
    for x in s:
        if isinstance(x, unittest.TestSuite):
            yield from iter_cases(x)
        elif x is not None:
            yield x

test_ids = [c.id() for c in iter_cases(suite)]

stream = io.StringIO()
runner = unittest.TextTestRunner(verbosity=0, stream=stream, failfast=False)
res = runner.run(suite)

failed_ids = {tc.id(): tb for tc, tb in (res.failures + res.errors)}

results = []
for tid in test_ids:
    method = tid.split(".")[-1]
    if tid in failed_ids:
        results.append({"name": method, "passed": False, "details": failed_ids[tid][-1500:]})
    else:
        results.append({"name": method, "passed": True, "details": ""})

print("__GFSO_VERIFIER_RESULTS__" + json.dumps(results))
"""


def _extract_test_names(test_code: str) -> list[str]:
    """Best-effort: find all `def test_*(self)` in the TestCases class."""
    return re.findall(r"def\s+(test_\w+)\s*\(\s*self", test_code)


_PREFIX = (
    # Force non-interactive matplotlib backend so model code that calls plt.show()
    # doesn't pop GUI windows during the bench. Guarded: the checker is a general instrument,
    # and a suite that never touches plotting must not require a plotting library to run.
    "try:\n    import matplotlib\n    matplotlib.use('Agg')\nexcept ImportError:\n    pass\n"
    # Headless mode for tkinter / other GUI toolkits
    "import os\nos.environ.setdefault('MPLBACKEND', 'Agg')\n\n"
)


def _run_suite(model_code: str, test_code: str, timeout: float = 60.0) -> list[dict]:
    """Run model_code + test_code in a subprocess, return list of {name, passed, details}."""
    full = _PREFIX + model_code + "\n\n" + test_code + "\n\n" + _RUNNER
    with tempfile.NamedTemporaryFile("w", suffix=".py", delete=False, encoding="utf-8") as f:
        f.write(full)
        path = f.name
    try:
        r = subprocess.run(
            [sys.executable, path],
            capture_output=True, text=True, timeout=timeout,
            encoding="utf-8", errors="replace",
        )
        out = r.stdout or ""
        if "__GFSO_VERIFIER_LOAD_FAIL__" in out:
            err = out.split("__GFSO_VERIFIER_LOAD_FAIL__:", 1)[1].strip()
            names = _extract_test_names(test_code)
            return [{"name": n, "passed": False, "details": f"LOAD_FAIL: {err}"} for n in names]
        if "__GFSO_VERIFIER_RESULTS__" not in out:
            # Crash before runner ran (syntax error in model code, etc)
            err_blob = (r.stderr or "")[-1500:]
            names = _extract_test_names(test_code)
            return [{"name": n, "passed": False, "details": f"CRASH: {err_blob}"} for n in names]
        payload = out.split("__GFSO_VERIFIER_RESULTS__", 1)[1].strip()
        return json.loads(payload)
    except subprocess.TimeoutExpired:
        names = _extract_test_names(test_code)
        return [{"name": n, "passed": False, "details": f"TIMEOUT after {timeout}s"} for n in names]
    finally:
        try:
            os.unlink(path)
        except OSError:
            pass


def evaluate_unittest(model_code: str, test_code: str, timeout: float = 60.0) -> list[CheckResult]:
    """Public helper: run unittest suite on model_code+test_code, return CheckResults.

    Use directly as a hidden evaluator for BCB-style benches.
    """
    raw = _run_suite(model_code, test_code, timeout=timeout)
    return [CheckResult(check_name=r["name"], passed=r["passed"], details=r["details"]) for r in raw]


class UnittestVerifier(VerifierPort):
    """VerifierPort implementation: runs unittest TestCase suite against delivered code.

    Each Criteria in spec.criteria is matched by name to a test method. Criteria
    whose name doesn't appear in the suite are reported as missing.
    """

    def __init__(self, storage: StoragePort, test_code: str, timeout: float = 60.0):
        self._storage = storage
        self._test_code = test_code
        self._timeout = timeout

    def verify(self, task_id: TaskId, deliverable: str, spec: Spec) -> list[CheckResult]:
        log.info(f"[UnittestVerifier] === VERIFICATION {task_id} ({len(spec.criteria)} criteria) ===")
        raw = _run_suite(deliverable, self._test_code, timeout=self._timeout)
        by_name = {r["name"]: r for r in raw}
        out: list[CheckResult] = []
        for c in spec.criteria:
            r = by_name.get(c.name)
            if r is None:
                out.append(CheckResult(check_name=c.name, passed=False, details="test not found in suite"))
            else:
                out.append(CheckResult(check_name=c.name, passed=r["passed"], details=r["details"]))
        self._storage.store_check_results(task_id, out)
        passed = sum(1 for r in out if r.passed)
        log.info(f"[UnittestVerifier] RESULT: {passed}/{len(out)} passed")
        for r in out:
            status = "PASS" if r.passed else "FAIL"
            log.info(f"[UnittestVerifier] {r.check_name}: {status}")
            if not r.passed and r.details:
                log.info(f"[UnittestVerifier]   {r.details[:500]}")
        return out
