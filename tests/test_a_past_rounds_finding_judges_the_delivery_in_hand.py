"""A standing finding whose own file reads the copy of the delivery its round judged re-runs over the copy this round
judges, never over that round's.

Series 2 REF 1 (GB_c_compiler_ctx2ref_10291111, root.ext): `sh <round>/batch1/x/cmp.sh <round>/batch1/x/ab.c`, the script
doing `cd <round>/batch1/delivery` — the copy the system made for that run and removed after it. Laid from the record, the
script still went there: gone, its setup failed and it printed its refutation; standing, it ran the old source. Either
way the finding refuted every later round whatever the executor fixed (ENG_QUEUE 2026-10-29, «past-round findings»).

CONTROLS: lay the kept texts unchanged in `findings.lay_files` and both cases go red (`broken`, `OURCFAIL`); give
`packets._regression_line` no judged copy and the packet test goes red.
"""
from __future__ import annotations

import json
import shutil

import pytest

from gfso.adapters.execution import LocalExecution, scratch_of
from gfso.core.types import TaskId, laid_beside
from gfso.engine.findings import keep_files
from gfso.packets import _validator_packet
from tests.test_a_finding_binds_the_criterion_it_refuted import _seam


@pytest.mark.parametrize("old_copy", ["still standing", "removed"])
def test_a_findings_script_over_its_rounds_delivery_copy_runs_over_this_rounds(tmp_path, old_copy):
    r = scratch_of(tmp_path / "ws", "p") / "kid_1791646628"
    old, x = r / "batch1" / "delivery", r / "batch1" / "x"
    old.mkdir(parents=True)
    x.mkdir(parents=True)
    (old / "prog.sh").write_text("echo broken\n")
    (x / "cmp.sh").write_text(f'cd "{old.as_posix()}" || {{ echo OURCFAIL; exit 1; }}\nsh prog.sh\n')
    (x / "bin").write_bytes(b"\x7fELF\0" + str(old).encode())      # …a program's bytes are never rewritten
    cmd = f"sh {(x / 'cmp.sh').as_posix()} {(x / 'bin').as_posix()}"
    e = _seam()
    keep_files(e._graph, e._storage, [cmd])         # filed as that round ended
    if old_copy == "removed":
        shutil.rmtree(old)
    at = tmp_path / "r2" / "batch1"
    (at / "delivery").mkdir(parents=True)
    (at / "delivery" / "prog.sh").write_text("echo fixed\n")
    ex = LocalExecution()
    laid = e.lay_probe_files(cmd, at, ex, judged=at / "delivery")
    got = ex.run([ex.shell() or "bash", "-c", laid], cwd=str(at / "delivery"), timeout=60)
    assert (got.returncode, got.stdout.strip()) == (0, "fixed"), (got.stdout, got.stderr)
    (kept,) = (at / "regression").glob("*/batch1/x/bin")
    assert kept.read_bytes() == b"\x7fELF\0" + str(old).encode()
    e.stop()


def test_the_validators_packet_lays_it_over_the_copy_its_judge_works_in(tmp_path):
    r = scratch_of(tmp_path / "ws", "p") / "kid_1791646628"
    (x := r / "batch1" / "x").mkdir(parents=True)
    (x / "cmp.sh").write_text(f'cd "{(r / "batch1" / "delivery").as_posix()}" && sh prog.sh\n')
    cmd = f"sh {(x / 'cmp.sh').as_posix()}"
    e = _seam()
    e._graph._storage.store_critique(TaskId("kid#regression-probes"), json.dumps({"conf": [
        {"id": "conf#1", "behaviour": "b", "command": cmd, "as_run": cmd, "expect": "ok"}]}))
    at = tmp_path / "r2" / "batch1"
    at.mkdir(parents=True)
    _validator_packet(e, e.graph.get_task(TaskId("kid")), "fixed it", None, scratch=str(at))
    (laid,) = laid_beside(at).glob("*/batch1/x/cmp.sh")
    assert f'cd "{(at / "delivery").as_posix()}"' in laid.read_text(), laid.read_text()
    e.stop()
