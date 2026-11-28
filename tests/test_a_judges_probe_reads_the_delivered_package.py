"""A probe a model child runs on the work imports the package of the tree it works in, wherever the probe's own cwd is:
run from a directory above the tree, `import gfso` took THIS host's editable install — the person's live checkout —
beside the tree's own tests, and a correct delivery FAILED on a check of another tree (validator gate, 2026-11-28,
SET.md attempt 12: one file 1 failed from the parent dir, 18 passed inside; a verdict is about the delivered tree,
§11.3). `config.work_env(cwd)` puts the tree first on PYTHONPATH, for both routes a child's commands run by.

CONTROL: `work_env()` without the tree — the same probe prints the installed package."""
import inspect
import os
import subprocess
import sys
from pathlib import Path

import gfso
from gfso import config as C
from gfso.adapters.execution import LocalExecution, path_sep
from gfso.adapters.llm import headless, toolloop

PROBE = [sys.executable, "-c", "import gfso, os; print(os.path.dirname(gfso.__file__))"]


def _tree(tmp_path) -> Path:
    """A delivered tree holding a package of the installed one's name, the judge's copy of it."""
    (pkg := tmp_path / "delivery" / "gfso").mkdir(parents=True)
    (pkg / "__init__.py").write_text("", encoding="utf-8")
    return tmp_path / "delivery"


def test_a_probe_from_above_the_tree_imports_the_trees_package(tmp_path):
    tree = _tree(tmp_path)
    got = subprocess.run(PROBE, cwd=str(tmp_path), env=C.work_env(str(tree)), capture_output=True, text=True).stdout
    assert Path(got.strip()).resolve() == (tree / "gfso").resolve(), got


def test_control_without_the_tree_the_probe_reads_the_installed_package(tmp_path):
    tree = _tree(tmp_path)
    got = subprocess.run(PROBE, cwd=str(tmp_path), env=C.work_env(), capture_output=True, text=True).stdout
    assert Path(got.strip()).resolve() == Path(gfso.__file__).resolve().parent, got
    assert Path(got.strip()).resolve() != (tree / "gfso").resolve()


def test_a_declared_shim_stays_behind_the_tree(tmp_path, monkeypatch):
    monkeypatch.setenv("PYTHONPATH", str(tmp_path / "shim"))
    tree = _tree(tmp_path)
    paths = C.work_env(str(tree))["PYTHONPATH"].split(os.pathsep)
    assert paths[0] == str(tree) and str(tmp_path / "shim") in paths, paths


def test_a_containers_list_is_joined_as_the_container_reads_it(tmp_path, monkeypatch):
    """On a Windows host a Linux container read `;` as one bogus entry: the tree not first, the shim lost (critic)."""
    monkeypatch.setenv("PYTHONPATH", "/w/shim")
    assert C.work_env("/w/tree", ":")["PYTHONPATH"] == "/w/tree:/w/shim"
    assert path_sep(LocalExecution()) == os.pathsep


def test_both_routes_name_their_tree_and_their_places_separator():
    """The CLI child's environment (`headless`) and the chat loop's commands (`toolloop`) each hand `work_env` their
    tree and their place's separator — one rule, read at both doors; a child with no tools is handed no tree."""
    src = inspect.getsource(headless.ClaudeCodeProvider._attempt)
    assert "cwd=cwd if tools_args is not None else None, sep=path_sep(self._exec)" in src, src
    assert "work_env(str(self.cwd), path_sep(self.exec))" in inspect.getsource(toolloop.Place.Bash)
