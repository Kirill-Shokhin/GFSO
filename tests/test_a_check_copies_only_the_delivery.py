"""A delivery with no recorded commit is copied for its judge as the tree git sees, and the copy is a bounded wait.

Measured (thread dumps, 2026-11-22): `validate_result` on a node delivered with nothing to commit, its place the top of
a git repository, sat over an hour in `shutil.copytree` — the place copied whole, its ignored data and ~20 agent
worktrees included (12.8 GB), with no bound and nothing said. A delivery is the result as it stands at DELIVER (§11.3);
in a work tree that is the tracked files as they stand plus the untracked ones not ignored — never the ignored ones, as
a delivery with a commit is judged as its checkout. A directory with no git is copied whole, as before.
"""
from __future__ import annotations

import shutil
import subprocess
from pathlib import Path

import pytest

from gfso.adapters import snapshots as S
from gfso.adapters.execution import LocalExecution

pytestmark = pytest.mark.skipif(shutil.which("git") is None, reason="a work tree needs git")


def _git(cwd, *args):
    subprocess.run(["git", "-c", "user.name=t", "-c", "user.email=t@t", *args], cwd=cwd, check=True,
                   capture_output=True)


def _files(root: Path) -> set:
    return {p.relative_to(root).as_posix() for p in root.rglob("*") if p.is_file() and ".git" not in p.parts}


@pytest.fixture
def place(tmp_path):
    """A work tree delivered with nothing committed since: a big ignored directory, a tracked file changed on disk, an
    untracked file not ignored, an ignored file tracked all the same, an ignored file beside a kept one."""
    p = tmp_path / "place"
    (p / "src").mkdir(parents=True)
    (p / ".gitignore").write_text("data/\n*.log\n")
    (p / "src" / "a.py").write_text("committed\n")
    (p / "forced.log").write_text("tracked though ignored\n")
    _git(p, "init", "-q")
    _git(p, "add", ".gitignore", "src/a.py")
    _git(p, "add", "-f", "forced.log")
    _git(p, "commit", "-q", "-m", "start")
    (p / "src" / "a.py").write_text("changed on disk\n")
    (p / "src" / "new.py").write_text("untracked, not ignored\n")
    (p / "src" / "run.log").write_text("ignored\n")
    for i in range(40):
        (d := p / "data" / f"d{i}").mkdir(parents=True)
        for j in range(50):
            (d / f"f{j}").write_text("x")
    return p


def test_a_work_tree_is_copied_without_what_git_ignores(place, tmp_path):
    with S.snapshot(place, tmp_path / "scratch" / "copy", LocalExecution()) as at:
        at = Path(at)
        got = _files(at)
        assert not (at / "data").exists() and "src/run.log" not in got, sorted(got)[:10]   # …the ignored left out
        assert got == {".gitignore", "forced.log", "src/a.py", "src/new.py"}, got
        assert (at / "src" / "a.py").read_text() == "changed on disk\n"                     # …as it stands on disk


def test_a_directory_with_no_git_is_copied_whole(tmp_path):
    p = tmp_path / "plain"
    (p / "data").mkdir(parents=True)
    (p / ".gitignore").write_text("data/\n")               # …no git reads it here
    (p / "data" / "x").write_text("x")
    (p / "main.c").write_text("int main;\n")
    with S.snapshot(p, tmp_path / "scratch" / "copy", LocalExecution()) as at:
        assert _files(Path(at)) == {".gitignore", "data/x", "main.c"}


def test_a_copy_past_its_bound_ends_the_run_with_its_reason(place, tmp_path, monkeypatch):
    monkeypatch.setattr(S, "COPY_S", 0, raising=False)
    (place / "data" / "keep").mkdir()                       # …enough left in to copy past a bound of nothing
    for j in range(200):
        (place / "src" / f"k{j}.py").write_text("x")
    at = tmp_path / "scratch" / "copy"
    with pytest.raises(S.Uncopied, match="outran its bound"):
        with S.snapshot(place, at, LocalExecution()):
            pytest.fail("a copy past its bound was handed to the run")
    assert not at.exists()                                  # …its partial copy gone with it
