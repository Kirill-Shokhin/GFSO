"""The examples are WORKING code that SHIPS, not documentation prose.

They live inside the package (`gfso/examples/`) because an example only a cloner can run is not part
of the product: the front page's first instruction is to watch the gate refuse a self-signed PASS,
and `pip install gfso` used to leave nothing to run it with. So they are exercised the way a user
reaches them — through the installed module path and through `gfso demo` — and the deterministic
ones run end to end with their printed outcomes asserted. The two that spawn models are compiled AND
driven through their setup with no model reachable — compiling alone had let a crash ship, on their
second line — but never to the spawn itself: that costs tokens and is a deliberate user act.
"""
import os
import pathlib
import py_compile
import subprocess
import sys

import gfso.examples
from gfso.examples import DEMOS, NEEDS_MODEL

HERE = pathlib.Path(gfso.examples.__file__).parent


def _run_module(name: str) -> str:
    out = subprocess.run([sys.executable, "-m", f"gfso.examples.{name}"],
                         capture_output=True, text=True, timeout=120)
    assert out.returncode == 0, out.stderr
    return out.stdout


def test_human_only_runs_and_the_gate_bites():
    out = _run_module("human_only")
    assert "accepted? False" in out          # the self-PASS was rejected
    assert "final: DONE" in out              # the independent record unlocked it


def test_async_precompute_runs_clean():
    out = _run_module("async_precompute")
    assert "holes after applying the precomputed structure: []" in out
    assert "'from': 'copy'" in out and "'to': 'deploy'" in out


def test_llm_examples_compile():
    for name in NEEDS_MODEL:
        py_compile.compile(str(HERE / f"{name}.py"), doraise=True)


def test_the_model_examples_stop_cleanly_when_there_is_no_model():
    """With the Claude CLI absent they must say so, not raise."""
    env = dict(os.environ, PATH=os.path.dirname(sys.executable))
    for name in NEEDS_MODEL:
        out = subprocess.run([sys.executable, "-m", f"gfso.examples.{name}"],
                             capture_output=True, text=True, encoding="utf-8", errors="replace",
                             timeout=180, env=env)
        assert "Traceback" not in out.stderr, f"{name} raised instead of reporting: {out.stderr[-800:]}"


def test_every_agent_the_examples_register_names_its_working_directory():
    """The class that shipped a crash, checked where it actually lives.

    The registry began refusing an `llm-executor`/`llm-validator` with no `workdir` — correctly, it
    cannot work without one — and both model examples registered a validator without it, so they
    died on their second line with a raw traceback while README called them working scripts. The
    run-based test above cannot reach that line (with no CLI they exit before it) and compiling
    never could, so the registration itself is what gets read: every such call, in every shipped
    example, must name a directory."""
    import ast

    for name in DEMOS:
        tree = ast.parse((HERE / f"{name}.py").read_text(encoding="utf-8"))
        for node in ast.walk(tree):
            if not (isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute)
                    and node.func.attr == "register"):
                continue
            kind = next((a.value for a in node.args[1:2] if isinstance(a, ast.Constant)), None)
            if kind not in ("llm-executor", "llm-validator"):
                continue
            assert any(kw.arg == "workdir" for kw in node.keywords), (
                f"{name}.py registers a {kind} with no workdir — the registry refuses that, so the "
                f"example raises at this line")


def test_the_demo_command_reaches_every_listed_example():
    """`gfso demo <name>` is how an installed user runs these, so what the listing advertises and
    what the package carries must be the same set — a demo named and missing is the failure with no
    symptom, which is the class this whole file exists to close."""
    import importlib.util
    for name in DEMOS:
        assert importlib.util.find_spec(f"gfso.examples.{name}") is not None, name
    out = subprocess.run([sys.executable, "-m", "gfso.cli", "demo"],
                         capture_output=True, text=True, timeout=60)
    assert out.returncode == 0, out.stderr
    for name in DEMOS:
        assert name in out.stdout
