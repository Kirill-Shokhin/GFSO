"""A deleted project leaves none of its files in the installation's state: its places on this machine under every base and
its reports refused as verdicts went with nothing (a live in_chat project, 2026-11-17), while another project's stand."""
from __future__ import annotations

from pathlib import Path

from gfso import runtime, tools_llm as TL
from gfso.adapters.execution import LocalExecution
from gfso.core.types import PLACES
from gfso.runtime import ProjectRegistry


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
        assert TL._keep_rejected_report(name, "root", "not a verdict", "text")
    reg.delete("doomed")
    left = sorted(p.relative_to(tmp_path).as_posix() for p in tmp_path.rglob("*") if p.is_file() and "doomed" in p.as_posix())
    assert left == [], left
    assert len(list((tmp_path / PLACES).glob("*/*/kept/node/f.txt"))) == 2
    assert list((tmp_path / "rejected_verdicts" / "kept").iterdir())


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
    assert TL._keep_rejected_report("doomed", "root", "not a verdict", "text")
    reg.delete("doomed")
    left = sorted({p.relative_to(tmp_path).parts[:4] for p in tmp_path.rglob("*") if p.is_file() and "doomed" in p.as_posix()})
    assert left == [(PLACES, "a1b2c3d4e5", ".gfso-nodes-repo", "doomed")], left
    assert forgotten == ["doomed"] and not (tmp_path / "doomed.db").exists()
