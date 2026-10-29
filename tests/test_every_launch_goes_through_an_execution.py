"""Every process the product starts for a project's work goes through its execution, and every temporary file an agent
is named stands where that execution can see it.

A project's sessions and commands run where its execution runs them — a Linux container per project on the one server
(docs/notes/ONE_SERVER_EXECUTION.md). A launch written past the port runs on the host however the project is declared, and
a temporary file made in the host's own temp is a path the container cannot open; both are silent. So outside the files
below, no `subprocess` start and no temporary directory without a `dir=` exists in gfso/ — each one listed says why it is
the host's own business.
"""
import ast
from pathlib import Path

GFSO = Path(__file__).resolve().parents[1] / "gfso"
STARTS = {"Popen", "run", "call", "check_output", "check_call"}

#: file -> why a direct start or a host temp there is the host's, not a project's
HOSTS_OWN = {
    "adapters/children.py": "the funnel every child goes through: adopted, in its own group, ended with the server",
    "adapters/lfs.py": "the LFS filter git runs inside a project's container, asking its own git where its store is",
    "adapters/execution.py": "LocalExecution, the host's own start, and the docker client every container call rides",
    "adapters/verifiers/subprocess_verifier.py": "an embedder's verifier adapter, run where the host that wires it is",
    "adapters/verifiers/unittest_verifier.py": "an embedder's verifier adapter, run where the host that wires it is",
    "doctor.py": "the install check of this machine: the CLI and git on its PATH",
    "examples/__init__.py": "an example a person runs on their own machine",
    "examples/autonomous_org.py": "an example a person runs on their own machine",
    "examples/mixed_delegation.py": "an example a person runs on their own machine",
    "mcp/connect.py": "starts the server itself",
    "serverctl.py": "manages the server's own process on this host",
}


def _launches(path: Path) -> list[str]:
    out = []
    for n in ast.walk(ast.parse(path.read_text(encoding="utf-8-sig"))):
        if isinstance(n, ast.Call) and isinstance(n.func, ast.Attribute) and isinstance(n.func.value, ast.Name):
            mod, fn = n.func.value.id, n.func.attr
            if (mod == "subprocess" and fn in STARTS) or (mod == "tempfile" and not any(k.arg == "dir" for k in n.keywords)):
                out.append(f"{mod}.{fn}:{n.lineno}")
    return out


def test_no_launch_and_no_host_temp_outside_the_hosts_own_files():
    found = {p.relative_to(GFSO).as_posix(): got for p in GFSO.rglob("*.py") if (got := _launches(p))}
    stray = {f: got for f, got in found.items() if f not in HOSTS_OWN}
    assert not stray, f"a start or a host temp past the execution port: {stray} — go through `execution_of(engine)`"
    assert not set(HOSTS_OWN) - set(found), f"listed but launching nothing any more: {set(HOSTS_OWN) - set(found)}"


def test_the_guard_sees_a_launch_and_a_host_temp(tmp_path):
    p = tmp_path / "m.py"
    p.write_text("import subprocess, tempfile\nsubprocess.run(['x'])\ntempfile.mkdtemp()\ntempfile.mkdtemp(dir='d')\n")
    assert _launches(p) == ["subprocess.run:2", "tempfile.mkdtemp:3"]
