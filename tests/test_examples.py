"""The examples are WORKING code, not documentation prose: the deterministic ones run end-to-end
(their printed outcomes asserted), the LLM ones at least compile (their real runs spawn models —
a deliberate user act, not a CI one)."""
import pathlib
import py_compile
import subprocess
import sys

EXAMPLES = pathlib.Path(__file__).parent.parent / "examples"


def _run(name: str) -> str:
    out = subprocess.run([sys.executable, str(EXAMPLES / name)],
                         capture_output=True, text=True, timeout=120)
    assert out.returncode == 0, out.stderr
    return out.stdout


def test_human_only_runs_and_the_gate_bites():
    out = _run("human_only.py")
    assert "accepted? False" in out          # the self-PASS was rejected
    assert "final: DONE" in out              # the independent record unlocked it


def test_async_precompute_runs_clean():
    out = _run("async_precompute.py")
    assert "holes after applying the precomputed structure: []" in out
    assert "'from': 'copy'" in out and "'to': 'deploy'" in out


def test_llm_examples_compile():
    for name in ("mixed_delegation.py", "autonomous_org.py"):
        py_compile.compile(str(EXAMPLES / name), doraise=True)
