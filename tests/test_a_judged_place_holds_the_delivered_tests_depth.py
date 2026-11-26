"""A judge's copy of a delivery stands on this host at a bound length past the data directory, whatever the base, the
project and the node are named: the delivered repository's own tests nest their temp and places below it, and Windows
refuses a working directory past 258 characters (WinError 267, measured) and a file past 259 to a tool without long
paths (git's objects) — this repository's suite judged in its validator's copy, 108 characters past the data directory,
failed 187 where 5042 passed (2026-11-25)."""
from __future__ import annotations

import os
import subprocess
import sys
import tempfile
from pathlib import Path

import pytest

from gfso import config
from gfso import workspaces as WS
from gfso.adapters.execution import ContainerExecution, LocalExecution, component, host_rounds, node_key, scratch_of
from gfso.core.protocol.procedure import probe_id, round_of
from gfso.core.types import BATCH, laid_beside, nodes_root
import gfso.validate as VAL

#: Windows' longest working directory, measured; and the longest file a tool with no long paths writes (git's objects)
CWD, FILE = 258, 259
#: what this suite spells between its tree's top and a test's own directory, at its widest (tests/conftest.py): `\.tmp`,
#: the run's process id (7 digits), its worker's number (2), the test's `t<n>` (4); and its worker's home, `\h-<8>`
SUITE, HOME = 5 + 8 + 3 + 6, 5 + 11
#: what a test lays below its own directory for a git of its own: a repository's place and a pack under it,
#: `\.gfso-nodes-base\proj\big` + `\.git\objects\pack\pack-<40>.pack` — the deepest measured over the 926 tests that lay
#: places, rounds and repositories (2026-11-26); its judges' rounds, deeper, are this layout's own (`_judged`), and the
#: system's git there writes long paths (`config.subprocess_env`), their working directory alone bounded
TEST_GIT = 26 + 68
#: what a delivered repository's tests nest below the judge's copy for a file git writes: this suite's, at its widest
NEST = SUITE + TEST_GIT
#: the names a test's fake of places standing apart lays its rounds under on this host, in its home's data — the
#: deepest working directory measured (`\data\places\<10>\.gfso-nodes-base\default\.gfso-scratch-.base\<round>\…`)
APART = ("base", "default", "root")
#: the longest data directory the bound is held for: a home of 36 characters (`C:\Users\<27>`) and `.gfso\data`, or a
#: source checkout's `data` as deep — the room the judged suite's deepest leaves (`test_the_suites_own_…`); this
#: host's is 32
DATA = 47

CASES = [("GFSO", "gfso-dev-draft", "root"),
         ("a-repository-named-at-length", "a-project-named-at-length", "n" * 64 + "/a-node-of-a-long-id")]


def _past(tmp_path, base_name, project, node, apart: bool = False) -> int:
    """How far past the data directory the deepest copy a validation of `node` judges in lies (`_judged`)."""
    judged, data = _judged(tmp_path, base_name, project, node, apart)
    return len(str(judged)) - len(str(data))


def _cwd_nest(past: int, apart: int) -> int:
    """The deepest working directory this suite's tests stand in below its top: a judge's copy in a round of a test's
    own home (`<test>\\data`), as far past it as the judge's above, or of a fake's places apart in its worker's home."""
    return len(os.sep + "data") + max(SUITE + past, HOME + apart)


def test_the_suites_own_directories_hold_the_depth_budget(tmp_path):
    """This suite judged at the deepest judge's copy the bound holds for (`DATA` and the judge's round) keeps what it
    lays within Windows' bounds, and its directories stand as short as `SUITE` and `HOME` say: in pytest's spelling a
    test's stood 73 below the tree's top, and the suite judged at a validator's round failed 68 tests and erred 14 where
    the tree passed every one (2026-11-26)."""
    top = len(str(Path(tempfile.gettempdir()).parent))
    for at, most in ((tmp_path, SUITE), (Path(os.environ["GFSO_HOME"]), HOME)):
        assert len(str(at)) - top <= most, f"{at} {len(str(at)) - top} characters below the tree's top, past {most}"
    past, apart = max(_past(tmp_path / str(i), *c) for i, c in enumerate(CASES)), _past(tmp_path / "a", *APART, apart=True)
    assert DATA + past + NEST <= FILE, f"a test's git object in the judged suite {DATA + past + NEST} deep"
    assert DATA + past + _cwd_nest(past, apart) <= CWD, f"a judge's round in the judged suite {DATA + past + _cwd_nest(past, apart)} deep"


def _judged(tmp_path, base_name, project, node, apart: bool = False) -> tuple[Path, Path]:
    """(the deepest copy a validation of `node` judges in — a batch's run again —, the data directory); `apart`: where
    places stand apart, as a test's fake of them lays its rounds on this host."""
    (base := tmp_path / base_name).mkdir(parents=True)
    workdir = base if node == "root" else nodes_root(base) / component(project) / node_key(node)
    workdir.mkdir(parents=True, exist_ok=True)
    ex = LocalExecution()
    ex.apart = apart
    rnd = VAL._validation_place(node, str(workdir), ex, project=project)
    return Path(rnd) / f"{BATCH}1_again" / "delivery", Path(os.path.realpath(config.data_dir()))


@pytest.mark.parametrize("base_name,project,node", CASES)
def test_the_judged_place_holds_the_delivered_tests_depth(tmp_path, base_name, project, node):
    judged, data = _judged(tmp_path, base_name, project, node)
    assert judged.is_relative_to(data), judged
    if os.name == "nt":
        # …a process started where the delivered tests' deepest stands, below the judge's copy, on this machine
        at, pad = judged, _cwd_nest(len(str(judged)) - len(str(data)), _past(tmp_path / "a", *APART, apart=True)) \
            + DATA - len(str(data))
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
