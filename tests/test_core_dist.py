"""The gfso-core distribution is CLOSED and ZERO-DEPENDENCY — proven on every run, so
publication stays a flip, never a surgery.

Two proofs over packaging/core_manifest.py (the single cut-line source the build shares):
(1) closure — no file in the manifest imports a gfso module outside it, and none imports any
non-stdlib package; (2) a live protocol drive on the STAGED tree alone, with site-packages
stripped from sys.path — the core runs a full ASSIGN→ACCEPT→DELIVER→PASS cycle on the bare
standard library."""
import pathlib
import shutil
import subprocess
import sys

sys.path.insert(0, str(pathlib.Path(__file__).parent.parent / "packaging"))
from core_manifest import core_paths  # noqa: E402
from tests.support import imports_of, module_reached  # noqa: E402

ROOT = pathlib.Path(__file__).parent.parent


def _imports(py: pathlib.Path) -> tuple[set[str], set[str]]:
    """(gfso modules reached; top-level non-gfso packages) — resolved, so `from gfso import x` and a relative import
    are edges too (`support.imports_of`)."""
    found = imports_of(py, ROOT)
    return ({module_reached(ROOT, m, n) for _, m, n in found if m.startswith("gfso")},
            {m.split(".")[0] for _, m, _ in found if not m.startswith("gfso")})


def _shipped() -> set[str]:
    """The modules the manifest ships, by full name — the closure's boundary is what is IN the wheel: a prefix such as
    `gfso.adapters` admitted an import of an adapter the wheel leaves out (critic G2)."""
    return {".".join(p.relative_to(ROOT).with_suffix("").parts).removesuffix(".__init__") for p in core_paths(ROOT)}


def test_manifest_files_exist():
    missing = [str(p) for p in core_paths(ROOT) if not p.exists()]
    assert not missing, f"manifest names nonexistent files: {missing}"


def test_core_dist_is_a_closed_zero_dependency_set():
    allowed = _shipped()
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
sys.path.insert(0, sys.argv[1])

from gfso.engine import Engine
from gfso.adapters.storage.memory import MemoryStorage
from gfso.adapters.agents.human import HumanAgent
from gfso.core.types import TaskId, AgentId, Spec, Criteria, Probe, Signal, SignalData

e = Engine(MemoryStorage(), HumanAgent(), llm=None, validate_signals=True, state_timeout=0)
e.start()
w = AgentId("w")
e.send_signal(SignalData(signal=Signal.ASSIGN, task_id=TaskId("n"), source=w,
                         spec=Spec("x", (Criteria("a", "A", check=(Probe("a holds", "check a", "it holds"),)),)),
                         assignee=w))
for sig, kw in ((Signal.ACCEPT, {}), (Signal.DELIVER, {"result": "done; a met"})):
    e.wait_idle()
    e.send_signal(SignalData(signal=sig, task_id=TaskId("n"), source=w, **kw))
e.wait_idle()
# the verifier≠executor gate demands a RECORDED independent verdict before a self-executed
# PASS — the embedding host runs its own verifier and records, exactly as here
e.record_exec_verdict(TaskId("n"), "PASS", [], "host-verifier",
                      per_criterion=[{"criterion": c.name, "verdict": "pass",
                                      "evidence": "the host's verifier ran it and it holds",
                                      "probe": [{"behaviour": p.behaviour, "command": p.command,
                                                 "expect": p.expect} for p in c.check]}
                                     for c in e.graph.get_task(TaskId("n")).spec.criteria])
e.send_signal(SignalData(signal=Signal.PASS, task_id=TaskId("n"), source=w))
e.wait_idle()
print(e.graph.get_state(TaskId("n")).name)
e.stop()
"""


def test_staged_core_drives_the_protocol_on_bare_stdlib(tmp_path):
    staged = tmp_path / "core"
    for src in core_paths(ROOT):
        dst = staged / src.relative_to(ROOT)
        dst.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(src, dst)
    # `-I -S`: no site, so no editable install's finder — it serves a direct child of `gfso` the wheel left out from
    # the repository (critic G2: with `gfso/config.py` dropped from the manifest, the smoke still printed DONE)
    out = subprocess.run([sys.executable, "-I", "-S", "-c", _SMOKE, str(staged)],
                         capture_output=True, text=True, timeout=60)
    assert out.returncode == 0, out.stderr
    assert out.stdout.strip().endswith("DONE")
