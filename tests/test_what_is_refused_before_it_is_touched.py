"""What an agent writes is refused before the host touches it, and one installation does not remove another (critic over the
whole stream: a path a model named opened a connection from the host, past any switch; an exported tree ran what an agent
wrote at the user's next git; a second installation removed a first's running container).

CONTROLS: drop the check in `Place.path` and the first goes red; read `at` lexically in `_untar` and the second does; take the
home out of the container's name and the third does; `-name .git` in `_EXPORT` and the live one does."""
import io
import os
import tarfile
from pathlib import Path

import pytest

from gfso.adapters import execution as E
from gfso.adapters.execution import LocalExecution, _untar
from gfso.adapters.llm.toolloop import Place
from tests.test_a_session_holds_only_its_own_place import made, project  # noqa: F401 — a fixture

UNC = chr(92) * 2 + "unreachable.invalid" + chr(92) + "share" + chr(92) + "f"


@pytest.mark.skipif(os.name != "nt", reason="a network path is Windows'")
def test_a_network_path_a_model_names_is_refused_before_the_host_asks_about_it(tmp_path, monkeypatch):
    place = Place(LocalExecution(), str(tmp_path))
    monkeypatch.setattr(Path, "resolve", lambda self, *a, **k: pytest.fail(f"asked the host about {self}"))
    with pytest.raises(PermissionError, match="network path"):
        place.path(UNC)


@pytest.mark.skipif(os.name == "nt", reason="links need a privilege here")
def test_an_entry_through_a_link_laid_before_it_is_not_written_outside(tmp_path):
    (outside := tmp_path / "outside").mkdir()
    buf = io.BytesIO()
    with tarfile.open(fileobj=buf, mode="w") as t:
        link = tarfile.TarInfo("in")
        link.type, link.linkname = tarfile.SYMTYPE, str(outside)
        t.addfile(link)
        (link2 := tarfile.TarInfo("sub")).type, link2.linkname = tarfile.SYMTYPE, "../outside"
        t.addfile(link2)
        (f := tarfile.TarInfo("sub/planted")).size = 1
        t.addfile(f, io.BytesIO(b"x"))
    _untar(buf.getvalue(), tmp_path / "to")
    assert not (outside / "planted").exists()


def test_two_installations_name_their_containers_apart_and_their_volumes_as_before(tmp_path, monkeypatch):
    (tmp_path / "e.env").write_text("X=1\n")
    (base := tmp_path / "w" / "b").mkdir(parents=True)
    names = []
    for home in ("one", "two"):
        monkeypatch.setattr(E, "_home", lambda data=None, h=home: h)
        x = E.ContainerExecution("default", "image", str(tmp_path / "e.env"), str(tmp_path / "s"), str(base), "p")
        names.append((x.container, x.volume.name.split("-")[1]))
    assert names[0][0] != names[1][0]
    assert x.volume.name.startswith(E.container_name("default", "p") + "-"), "a project's volume keeps its name across this"


def test_live_an_export_neutralises_every_spelling_of_a_repository(project, tmp_path):  # noqa: F811
    made(project, "a/.GIT/hooks", "b")
    project.files.write_bytes(str(project.own / "a/.GIT/config"), b"[core]\n\tfsmonitor = planted\n")
    project.files.write_bytes(str(project.own / "a/.GIT/HEAD"), b"ref: refs/heads/x\n")
    project.files.write_bytes(str(project.own / "b/.git"), b"gitdir: ../elsewhere\n")
    out = tmp_path / "out"
    project.volume.export(project.image, out)
    config = next((p for p in (out / "a").iterdir() if p.name.lower() == ".git"), None) if (out / "a").is_dir() else None
    assert config is not None and not (config / "hooks").exists(), "the spelling was treated as a repository"
    assert not (config / "config").exists() or b"planted" not in (config / "config").read_bytes()
    assert not (out / "b" / ".git").exists(), "a .git that is a file redirects git: removed"
