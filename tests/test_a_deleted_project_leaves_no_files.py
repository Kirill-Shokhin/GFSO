"""A deleted project leaves none of its files in the installation's state: its places on this machine under every base and
its reports refused as verdicts went with nothing (a live in_chat project, 2026-11-17), while another project's stand."""
from __future__ import annotations

import subprocess
from pathlib import Path

from gfso import runtime, tools_llm as TL
from gfso.adapters.execution import LocalExecution
from gfso import workspaces as WS
from gfso.adapters import worktrees as W
from gfso.core.types import PLACES, nodes_root
from gfso.runtime import ProjectRegistry
import gfso.validate as VAL


def _lay(at) -> None:
    at.mkdir(parents=True)
    (at / "f.txt").write_text("x", encoding="utf-8")


def test_a_deleted_projects_places_and_refused_reports_go_and_anothers_stand(tmp_path, monkeypatch):
    monkeypatch.setenv("GFSO_DATA_DIR", str(tmp_path))
    monkeypatch.setenv("GFSO_HOME", str(tmp_path))
    reg = ProjectRegistry(default_storage="sqlite", default_llm="stub", seed=False)
    for name in ("doomed", "kept"):
        reg.engine(name)
        for base in ("a1b2c3d4e5/.gfso-nodes-repo", "f6a7b8c9d0/.gfso-nodes-other"):
            _lay(tmp_path / PLACES / base / name / "node")
        assert VAL._keep_rejected_report(name, "root", "not a verdict", "text")
        _lay(tmp_path / "probe_inputs" / name / "root_1")
    reg.delete("doomed")
    left = sorted(p.relative_to(tmp_path).as_posix() for p in tmp_path.rglob("*") if p.is_file() and "doomed" in p.as_posix())
    assert left == [], left
    assert len(list((tmp_path / PLACES).glob("*/*/kept/node/f.txt"))) == 2
    assert list((tmp_path / "rejected_verdicts" / "kept").iterdir()) and (tmp_path / "probe_inputs" / "kept").is_dir()


def test_a_file_a_process_holds_keeps_only_its_directory_and_the_deletion_whole(tmp_path, monkeypatch):
    """A place's file held open (a lock on Windows) raised from inside the deletion after its database was gone: its roles
    stood for a project made again under the name, and every other directory of it stayed too (critics, reproduced)."""
    monkeypatch.setenv("GFSO_DATA_DIR", str(tmp_path))
    monkeypatch.setenv("GFSO_HOME", str(tmp_path))
    forgotten = []
    monkeypatch.setattr(runtime.AgentRegistry, "forget_project", lambda self, name: forgotten.append(name))
    held = tmp_path / PLACES / "a1b2c3d4e5" / ".gfso-nodes-repo" / "doomed"
    real = LocalExecution.remove_tree

    def remove(self, path):
        if Path(path) == held:
            raise PermissionError(32, "the file is held by another process")
        real(self, path)
    monkeypatch.setattr(LocalExecution, "remove_tree", remove)
    reg = ProjectRegistry(default_storage="sqlite", default_llm="stub", seed=False)
    reg.engine("doomed")
    for base in ("a1b2c3d4e5/.gfso-nodes-repo", "f6a7b8c9d0/.gfso-nodes-other"):
        _lay(tmp_path / PLACES / base / "doomed" / "node")
    assert VAL._keep_rejected_report("doomed", "root", "not a verdict", "text")
    reg.delete("doomed")
    left = sorted({p.relative_to(tmp_path).parts[:4] for p in tmp_path.rglob("*") if p.is_file() and "doomed" in p.as_posix()})
    assert left == [(PLACES, "a1b2c3d4e5", ".gfso-nodes-repo", "doomed")], left
    assert forgotten == ["doomed"] and not (tmp_path / "doomed.db").exists()


def test_a_deleted_projects_node_branches_go_from_its_base_and_its_result_stays(tmp_path, monkeypatch):
    """A project made again under a deleted one's name started its nodes from the old attempt's branches left in the
    person's repository; the author, 2026-11-18: «Давай удалять, это разумно» — all but `accepted`, which is theirs."""
    monkeypatch.setenv("GFSO_DATA_DIR", str(tmp_path / "data"))
    monkeypatch.setenv("GFSO_HOME", str(tmp_path))
    monkeypatch.setenv("GFSO_AGENTS_PATH", str(tmp_path / "agents.json"))
    base = tmp_path / "repo"
    base.mkdir()
    git = lambda *a: subprocess.run(["git", "-C", str(base), "-c", "user.name=t", "-c", "user.email=t@t", *a],
                                    check=True, capture_output=True, text=True).stdout
    git("init", "-q")
    git("commit", "-q", "--allow-empty", "-m", "start")
    for ref in ("refs/heads/gfso/doomed/root", "refs/heads/gfso/doomed/accepted", "refs/heads/gfso/doomed/joined/root",
                "refs/gfso/doomed/delivered/root", "refs/heads/gfso/kept/root", "refs/heads/gfso/doomed-too/root"):
        git("update-ref", ref, "HEAD")
    reg = ProjectRegistry(default_storage="sqlite", default_llm="stub", seed=False)
    reg.engine("doomed")
    runtime.AgentRegistry().register("doomed-exec", "llm-executor", workdir=str(base), project="doomed")
    reg.delete("doomed")
    left = sorted(git("for-each-ref", "--format=%(refname)").split())
    assert left == ["refs/heads/gfso/doomed-too/root", "refs/heads/gfso/doomed/accepted", "refs/heads/gfso/kept/root",
                    "refs/heads/master"] or left == ["refs/heads/gfso/doomed-too/root", "refs/heads/gfso/doomed/accepted",
                                                     "refs/heads/gfso/kept/root", "refs/heads/main"], left


def _repo(at, *refs):
    at.mkdir()
    git = lambda *a: subprocess.run(["git", "-C", str(at), "-c", "user.name=t", "-c", "user.email=t@t", *a],
                                    check=True, capture_output=True, text=True).stdout
    git("init", "-q")
    git("commit", "-q", "--allow-empty", "-m", "start")
    for ref in refs:
        git("update-ref", ref, "HEAD")
    return git


def test_a_branch_in_hand_stays_and_a_base_only_the_places_record_knows_is_cleared(tmp_path, monkeypatch):
    """A checked-out branch deleted left the person's tree on an unborn branch; a role moved to another repository, or
    registered for no project, hid its first base from the deletion (critic, probes)."""
    monkeypatch.setenv("GFSO_DATA_DIR", str(tmp_path / "data"))
    monkeypatch.setenv("GFSO_HOME", str(tmp_path))
    monkeypatch.setenv("GFSO_AGENTS_PATH", str(tmp_path / "agents.json"))
    held = _repo(tmp_path / "held", "refs/heads/gfso/doomed/root", "refs/heads/gfso/doomed/in-hand")
    held("worktree", "add", "-q", str(tmp_path / "looking"), "gfso/doomed/in-hand")
    moved = _repo(tmp_path / "moved", "refs/heads/gfso/doomed/root")
    nodes_root(tmp_path / "moved").joinpath("doomed").mkdir(parents=True)     # …a place was made there; no role now
    reg = ProjectRegistry(default_storage="sqlite", default_llm="stub", seed=False)
    reg.engine("doomed")
    runtime.AgentRegistry().register("doomed-exec", "llm-executor", workdir=str(tmp_path / "held"), project="doomed")
    reg.delete("doomed")
    assert "refs/heads/gfso/doomed/in-hand" in held("for-each-ref", "--format=%(refname)").split()
    assert "refs/heads/gfso/doomed/root" not in held("for-each-ref", "--format=%(refname)").split()
    assert "gfso/doomed" not in moved("for-each-ref", "--format=%(refname)")


def test_with_no_git_the_deletion_completes(tmp_path, monkeypatch):
    monkeypatch.setenv("GFSO_DATA_DIR", str(tmp_path / "data"))
    monkeypatch.setenv("GFSO_HOME", str(tmp_path))
    monkeypatch.setenv("GFSO_AGENTS_PATH", str(tmp_path / "agents.json"))
    (tmp_path / "repo").mkdir()

    def no_git(*a, **k):
        raise FileNotFoundError("git")
    monkeypatch.setattr(WS.W, "git", no_git)
    reg = ProjectRegistry(default_storage="sqlite", default_llm="stub", seed=False)
    reg.engine("doomed")
    runtime.AgentRegistry().register("doomed-exec", "llm-executor", workdir=str(tmp_path / "repo"), project="doomed")
    _lay(tmp_path / "data" / "probe_inputs" / "doomed" / "root_1")
    reg.delete("doomed")
    assert not (tmp_path / "data" / "probe_inputs" / "doomed").exists() and not (tmp_path / "data" / "doomed.db").exists()


def test_a_result_the_new_one_does_not_contain_is_kept_before_its_branch_moves(tmp_path):
    """A project made again under a deleted one's name landed over the old result, left only in the reflog."""
    git = _repo(tmp_path / "base")
    ref = "refs/heads/gfso/p/accepted"
    git("commit", "-q", "--allow-empty", "-m", "old result")
    old = git("rev-parse", "HEAD").strip()
    git("update-ref", ref, old)
    git("checkout", "-q", "--orphan", "fresh")
    git("commit", "-q", "--allow-empty", "-m", "an unrelated new result")
    new = git("rev-parse", "HEAD").strip()
    kept = W.move_result(tmp_path / "base", ref, new)
    assert kept and kept.startswith(ref + "-") and git("rev-parse", kept).strip() == old, kept
    assert git("rev-parse", ref).strip() == new
    git("commit", "-q", "--allow-empty", "-m", "built on it")
    assert W.move_result(tmp_path / "base", ref, git("rev-parse", "HEAD").strip()) is None, "contained: moved as before"


def test_the_kept_results_stay_with_accepted_when_the_project_is_deleted(tmp_path, monkeypatch):
    monkeypatch.setenv("GFSO_DATA_DIR", str(tmp_path / "data"))
    monkeypatch.setenv("GFSO_HOME", str(tmp_path))
    monkeypatch.setenv("GFSO_AGENTS_PATH", str(tmp_path / "agents.json"))
    git = _repo(tmp_path / "repo", "refs/heads/gfso/doomed/accepted", "refs/heads/gfso/doomed/accepted-20261118T000000Z",
                "refs/heads/gfso/doomed/root", "refs/heads/gfso/doomed/accepted-criteria")
    reg = ProjectRegistry(default_storage="sqlite", default_llm="stub", seed=False)
    reg.engine("doomed")
    runtime.AgentRegistry().register("doomed-exec", "llm-executor", workdir=str(tmp_path / "repo"), project="doomed")
    reg.delete("doomed")
    assert sorted(r for r in git("for-each-ref", "--format=%(refname)").split() if "gfso" in r) == [
        "refs/heads/gfso/doomed/accepted", "refs/heads/gfso/doomed/accepted-20261118T000000Z"]


def test_a_landing_through_land_keeps_the_result_it_would_have_lost(tmp_path):
    """The wiring: `land` itself, on this host, over an `accepted` the new result does not contain — a mutation that put
    a plain update-ref back at the call site passed every test before this one (critic)."""
    git = _repo(tmp_path / "base")
    ref = "refs/heads/gfso/p/accepted"
    git("commit", "-q", "--allow-empty", "-m", "the earlier result")
    old = git("rev-parse", "HEAD").strip()
    git("update-ref", ref, old)
    git("checkout", "-q", "--orphan", "fresh")
    git("commit", "-q", "--allow-empty", "-m", "a new root's result")
    new = git("rev-parse", "HEAD").strip()
    assert W.land(tmp_path / "base", ref, LocalExecution(), None, rev=new) == new
    refs = dict(line.split() for line in git("for-each-ref", "--format=%(refname) %(objectname)").splitlines())
    assert refs[ref] == new and [r for r, s in refs.items() if r.startswith(ref + "-") and s == old], refs
