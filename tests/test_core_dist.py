"""The gfso-core distribution is CLOSED and ZERO-DEPENDENCY — proven on every run, so
publication stays a flip, never a surgery.

Two proofs over packaging/core_manifest.py (the single cut-line source the build shares):
(1) closure — no file in the manifest imports a gfso module outside it, and none imports any
non-stdlib package; (2) a live protocol drive on the STAGED tree alone, with site-packages
stripped from sys.path — the core runs a full ASSIGN→ACCEPT→DELIVER→PASS cycle on the bare
standard library."""
import ast
import pathlib
import shutil
import subprocess
import sys

sys.path.insert(0, str(pathlib.Path(__file__).parent.parent / "packaging"))
from core_manifest import core_paths, covered_module_prefixes  # noqa: E402

ROOT = pathlib.Path(__file__).parent.parent


def _imports(py: pathlib.Path) -> tuple[set[str], set[str]]:
    tree = ast.parse(py.read_text(encoding="utf-8-sig"))
    gfso, external = set(), set()
    for n in ast.walk(tree):
        names = ()
        if isinstance(n, ast.Import):
            names = tuple(a.name for a in n.names)
        elif isinstance(n, ast.ImportFrom) and n.module and n.level == 0:
            names = (n.module,)
        for name in names:
            if name.startswith("gfso"):
                gfso.add(".".join(name.split(".")[:2]))
            else:
                external.add(name.split(".")[0])
    return gfso, external


def test_manifest_files_exist():
    missing = [str(p) for p in core_paths(ROOT) if not p.exists()]
    assert not missing, f"manifest names nonexistent files: {missing}"


def test_core_dist_is_a_closed_zero_dependency_set():
    allowed = covered_module_prefixes() | {"gfso"}
    stdlib = sys.stdlib_module_names
    violations = []
    for py in core_paths(ROOT):
        gfso_imps, ext = _imports(py)
        out = gfso_imps - allowed
        if out:
            violations.append(f"{py.relative_to(ROOT)} imports outside the core dist: {sorted(out)}")
        nonstd = {e for e in ext if e not in stdlib and e != "__future__"}
        if nonstd:
            violations.append(f"{py.relative_to(ROOT)} imports non-stdlib: {sorted(nonstd)}")
    assert not violations, "core-dist closure broken:\n" + "\n".join(violations)


_SMOKE = r"""
import sys
sys.path = [p for p in sys.path if "site-packages" not in p and "dist-packages" not in p]
sys.path.insert(0, sys.argv[1])

from gfso.engine import Engine
from gfso.adapters.storage.memory import MemoryStorage
from gfso.adapters.agents.human import HumanAgent
from gfso.core.types import TaskId, AgentId, Spec, Criteria, Signal, SignalData

e = Engine(MemoryStorage(), HumanAgent(), llm=None, validate_signals=True, state_timeout=0)
e.start()
w = AgentId("w")
e.send_signal(SignalData(signal=Signal.ASSIGN, task_id=TaskId("n"), source=w,
                         spec=Spec("x", (Criteria("a", "A"),)), assignee=w))
for sig, kw in ((Signal.ACCEPT, {}), (Signal.DELIVER, {"result": "done; a met"})):
    e.wait_idle()
    e.send_signal(SignalData(signal=sig, task_id=TaskId("n"), source=w, **kw))
e.wait_idle()
# the verifier≠executor gate demands a RECORDED independent verdict before a self-executed
# PASS — the embedding host runs its own verifier and records, exactly as here
e.record_exec_verdict(TaskId("n"), "PASS", [], "host-verifier")
e.send_signal(SignalData(signal=Signal.PASS, task_id=TaskId("n"), source=w))
e.wait_idle()
print(e.get_state(TaskId("n")).name)
e.stop()
"""


def test_staged_core_drives_the_protocol_on_bare_stdlib(tmp_path):
    staged = tmp_path / "core"
    for src in core_paths(ROOT):
        dst = staged / src.relative_to(ROOT)
        dst.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(src, dst)
    out = subprocess.run([sys.executable, "-c", _SMOKE, str(staged)],
                         capture_output=True, text=True, timeout=60)
    assert out.returncode == 0, out.stderr
    assert out.stdout.strip().endswith("DONE")
