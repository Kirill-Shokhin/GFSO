"""What a build, a check or an agent's filter prints reaches the server's memory, past every container's limit and the
machine's ceiling, none of which count it: held whole, a loop on print added 100 MiB a second to the server (critic, on
the running code). Each stream is kept to a head and a tail, and a unittest-checker, which runs a delivery in the server's
own process, is refused where the project's work runs in a container.

CONTROLS: let `run_printing` read with `communicate` and the first test goes red; drop the refusal and the last does."""
from __future__ import annotations

import subprocess
import sys

import pytest

from gfso.adapters import children as C
from gfso.adapters.execution import LocalExecution
from gfso.delegate import _checker_validate

PRINTS = "import sys\nfor _ in range(%d): sys.stdout.write('head' + 'x' * 65532); sys.stderr.write('e' * 1024)\nprint('the end')"


def test_a_program_printing_without_end_is_kept_to_its_head_and_tail(monkeypatch):
    monkeypatch.setattr(C, "PRINTED_CAP", 2 ** 20)
    got = C.run_printing([sys.executable, "-c", PRINTS % 2000], timeout=120)      # 131 MB on its stdout
    assert got.returncode == 0
    assert got.stdout.startswith("head") and got.stdout.rstrip().endswith("the end")
    assert "bytes printed here, not kept" in got.stdout and len(got.stdout) < 2 ** 20 + 200


def test_what_is_under_the_bound_comes_whole_and_its_code_with_it():
    got = C.run_printing([sys.executable, "-c", "import sys; print('out'); print('err', file=sys.stderr); sys.exit(3)"],
                         timeout=60)
    assert (got.returncode, got.stdout.strip(), got.stderr.strip()) == (3, "out", "err")
    assert LocalExecution().run([sys.executable, "-c", "print('hello')"], cwd=".", timeout=60).returncode == 0


def test_a_program_past_its_time_is_ended_and_raises():
    with pytest.raises(subprocess.TimeoutExpired):
        C.run_printing([sys.executable, "-c", "import time; time.sleep(60)"], timeout=1)


class _InAContainer:
    files = object()


def test_a_checker_does_not_run_a_delivery_on_this_machine_for_a_project_in_a_container(tmp_path):
    out = _checker_validate(None, "t", {"oracle_map": str(tmp_path / "none")}, str(tmp_path), _InAContainer())
    assert out["verdict"] is None and "refused" in out["note"]
