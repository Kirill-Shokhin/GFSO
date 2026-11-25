"""A judge's copy of a delivery stands on this host at a bound length past the data directory, whatever the base, the
project and the node are named: the delivered repository's own tests nest their temp and places below it, and Windows
refuses a working directory past 258 characters (WinError 267, measured) and a file past 259 to a tool without long
paths (git's objects) — this repository's suite judged in its validator's copy, 108 characters past the data directory,
failed 187 where 5042 passed (2026-11-25)."""
from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

import pytest

from gfso import config
from gfso import workspaces as WS
from gfso.adapters.execution import ContainerExecution, LocalExecution, component, host_rounds, node_key, scratch_of
from gfso.core.protocol.procedure import probe_id, round_of
from gfso.core.types import BATCH, laid_beside, nodes_root
import gfso.validate as VAL

#: Windows' longest working directory, measured
CWD = 258
#: what a delivered repository's tests nest below the judge's copy: this suite's pytest temp and a git object under it
#: measured at 117 past the repository's top
NEST = 110
#: the longest data directory the bound is held for: a home of 40 characters (`C:\Users\<30>`) and `.gfso\data`, or a
#: source checkout's `data` as deep
DATA = 60

CASES = [("GFSO", "gfso-dev-draft", "root"),
         ("a-repository-named-at-length", "a-project-named-at-length", "n" * 64 + "/a-node-of-a-long-id")]


def _judged(tmp_path, base_name, project, node) -> tuple[Path, Path]:
    """(the deepest copy a validation of `node` judges in — a batch's run again —, the data directory)."""
    (base := tmp_path / base_name).mkdir()
    workdir = base if node == "root" else nodes_root(base) / component(project) / node_key(node)
    workdir.mkdir(parents=True, exist_ok=True)
    rnd = VAL._validation_place(node, str(workdir), LocalExecution(), project=project)
    return Path(rnd) / f"{BATCH}1_again" / "delivery", Path(os.path.realpath(config.data_dir()))


@pytest.mark.parametrize("base_name,project,node", CASES)
def test_the_judged_place_holds_the_delivered_tests_depth(tmp_path, base_name, project, node):
    judged, data = _judged(tmp_path, base_name, project, node)
    assert judged.is_relative_to(data), judged
    past = len(str(judged)) - len(str(data))
    assert past <= CWD - NEST - DATA, f"the judge's copy {past} characters past the data directory: {judged}"
    if os.name == "nt":
        # …a process started where the delivered tests' deepest stands, below the judge's copy, on this machine
        at, pad = judged, NEST + DATA - len(str(data))
        while pad > 1:
            n = min(pad - 1, 50)
            at, pad = at / ("t" * n), pad - n - 1
        at.mkdir(parents=True)
        assert subprocess.run([sys.executable, "-c", "0"], cwd=at).returncode == 0, len(str(at))


def test_a_scratch_of_this_host_is_one_per_place_and_project(tmp_path):
    (a := tmp_path / "a").mkdir()
    ex = LocalExecution()
    assert scratch_of(a, "p", ex) == scratch_of(a, "p", ex), "one place, one scratch: a probe's id folds its rounds"
    assert len({scratch_of(a, "p", ex), scratch_of(a, "q", ex), scratch_of(tmp_path / "b", "p", ex),
                scratch_of(nodes_root(a) / "p" / "n1", "p", ex)}) == 4
    assert scratch_of(a, "p", ex).parent == host_rounds("p") != host_rounds("q")
    x = ContainerExecution("e", "img", None, str(tmp_path / "state"), str(a), "p")
    assert scratch_of(a, "p", x) == x.own / ".gfso-scratch-.a", "where places stand apart, among them as before"


def test_a_round_of_this_hosts_scratch_reads_as_a_round(tmp_path):
    (a := tmp_path / "a").mkdir()
    s = scratch_of(a, "p", LocalExecution())
    rnd = s / "kid_1791646628"
    assert round_of(rnd / "batch1" / "t.c") == (str(rnd), f"{s.name}/{rnd.name}")
    cmd = lambda r: {"command": f"./cc {(s / r / 't.c').as_posix()}"}
    assert probe_id("c", cmd("kid_1791646628")) == probe_id("c", cmd("kid_1791646999")), "the round folded out"
    assert laid_beside(rnd / "x") == Path(f"{rnd}.laid") / "x", "laid beside the round, never under it"
    assert laid_beside(rnd / "batch1" / "delivery") == Path(f"{rnd / 'batch1'}.laid") / "delivery"


def test_a_scratch_laid_before_the_move_still_reads(tmp_path):
    """A round recorded among a project's places before the move: still a round, laid beside, cleared at the close."""
    rnd = nodes_root(tmp_path / "a") / "p" / ".gfso-scratch-n1" / "n1_1791646628"
    assert round_of(rnd / "t.c") == (str(rnd), f".gfso-scratch-n1/{rnd.name}")
    assert laid_beside(rnd / "x") == Path(f"{rnd}.laid") / "x"


def test_a_deleted_projects_scratch_goes_with_it(tmp_path):
    (a := tmp_path / "a").mkdir()
    (r := scratch_of(a, "gone", LocalExecution()) / "kid_1").mkdir(parents=True)
    (other := scratch_of(a, "kept", LocalExecution()) / "kid_1").mkdir(parents=True)
    WS.drop_host_files("gone")
    assert not r.parent.parent.exists() and other.is_dir()
