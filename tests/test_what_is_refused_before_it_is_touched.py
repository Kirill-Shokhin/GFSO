"""What an agent writes is refused before the host touches it, and one installation does not remove another (critic over the
whole stream: a path a model named opened a connection from the host, past any switch; an exported tree ran what an agent
wrote at the user's next git; a second installation removed a first's running container).

CONTROLS: drop the check in `Place.path` and the first goes red; read `at` lexically in `_untar` and the second does; take the
home out of the container's name and the third does; `-name .git` in `_EXPORT` and the live one does."""
import contextlib
import io
import os
import subprocess
import tarfile
from pathlib import Path
from types import SimpleNamespace

import pytest

from gfso import observe as O
from gfso.adapters import execution as E
from gfso.core.types import Criteria, Probe
from gfso.adapters.execution import LocalExecution, _untar
from gfso.adapters.llm.toolloop import Place
from tests.test_a_session_holds_only_its_own_place import made, project  # noqa: F401 — a fixture

BS = chr(92)
UNC = BS * 2 + "unreachable.invalid" + BS + "share" + BS + "f"


@pytest.mark.skipif(os.name != "nt", reason="a network path is Windows'")
def test_a_network_path_a_model_names_is_refused_before_the_host_asks_about_it(tmp_path, monkeypatch):
    place = Place(LocalExecution(), str(tmp_path))
    monkeypatch.setattr(Path, "resolve", lambda self, *a, **k: pytest.fail(f"asked the host about {self}"))
    with pytest.raises(PermissionError, match="network path"):
        place.path(UNC)


@pytest.mark.skipif(os.name != "nt", reason="a device path is Windows'")
@pytest.mark.parametrize("named", [BS * 2 + "?" + BS + "GLOBALROOT" + BS + "Device" + BS + "Mup" + BS + "unreachable.invalid" + BS + "s",
                                   BS * 2 + "." + BS + "Mup" + BS + "unreachable.invalid" + BS + "s",
                                   "//?/UNC/unreachable.invalid/s",
                                   BS + "??" + BS + "UNC" + BS + "unreachable.invalid" + BS + "s"])
def test_no_spelling_of_the_redirector_reaches_the_host(tmp_path, monkeypatch, named):
    place = Place(LocalExecution(), str(tmp_path))
    monkeypatch.setattr(Path, "resolve", lambda self, *a, **k: pytest.fail(f"asked the host about {self}"))
    with pytest.raises(PermissionError, match="network path"):
        place.path(named)


@pytest.mark.skipif(os.name != "nt", reason="a device path is Windows'")
def test_a_place_on_a_share_lets_no_device_spelling_through_either(tmp_path, monkeypatch):
    place = Place(LocalExecution(), str(tmp_path))
    place.cwd = Path(UNC)
    monkeypatch.setattr(Path, "resolve", lambda self, *a, **k: pytest.fail(f"asked the host about {self}"))
    with pytest.raises(PermissionError, match="network path"):
        place.path(BS * 2 + "." + BS + "Mup" + BS + "unreachable.invalid" + BS + "s")


@pytest.mark.skipif(os.name != "nt", reason="a drive letter is Windows'")
def test_a_mapped_drive_in_git_bash_s_spelling_is_refused_as_in_its_own(tmp_path, monkeypatch):
    monkeypatch.setattr("gfso.places._drive_is_local", lambda d: d.lower() != "z:")
    place = Place(LocalExecution(), str(tmp_path))
    monkeypatch.setattr(Path, "resolve", lambda self, *a, **k: pytest.fail(f"asked the host about {self}"))
    with pytest.raises(PermissionError, match="network path"):
        place.path("/z/secret")


def _tar(*names) -> bytes:
    buf = io.BytesIO()
    with tarfile.open(fileobj=buf, mode="w") as t:
        for n in names:
            (f := tarfile.TarInfo(n)).size = 7
            t.addfile(f, io.BytesIO(b"planted"))
    return buf.getvalue()


@pytest.mark.skipif(os.name == "nt", reason="links need a privilege here")
def test_a_chain_of_links_each_inside_by_its_text_leads_nowhere_out(tmp_path):
    (outside := tmp_path / "outside").write_text("the user's")
    buf = io.BytesIO()
    with tarfile.open(fileobj=buf, mode="w") as t:
        (d := tarfile.TarInfo("d")).type, d.mode = tarfile.DIRTYPE, 0o755
        t.addfile(d)
        for name, target in (("d/up", ".."), ("through", "d/up/../outside"), ("kept", "d")):
            (link := tarfile.TarInfo(name)).type, link.linkname = tarfile.SYMTYPE, target
            t.addfile(link)
    to = tmp_path / "to"
    notes = _untar(buf.getvalue(), to)
    assert not any(Path(d, n).is_symlink() and not Path(os.path.realpath(Path(d, n))).is_relative_to(to.resolve())
                   for d, dirs, files in os.walk(to) for n in (*dirs, *files)), notes
    assert (to / "kept").is_symlink(), "a link that stays inside is the delivery's own"
    assert outside.read_text() == "the user's"


def test_the_root_entry_of_an_export_is_no_loss_to_report(tmp_path):
    buf = io.BytesIO()
    with tarfile.open(fileobj=buf, mode="w") as t:
        (d := tarfile.TarInfo(".")).type = tarfile.DIRTYPE
        t.addfile(d)
        (f := tarfile.TarInfo("./a")).size = 1
        t.addfile(f, io.BytesIO(b"x"))
    assert _untar(buf.getvalue(), tmp_path / "to") == [] and (tmp_path / "to" / "a").is_file()


def test_a_name_the_disk_reads_as_another_is_said_and_not_written(tmp_path, monkeypatch):
    monkeypatch.setattr(E, "_FOLDING", True)
    to = tmp_path / "to"
    notes = _untar(_tar("r/.git/config", "r/.git./config", "r/git~1/config", "r/.GIT/config", "r/.git/CONFIG",
                        "r/.git /config", "r/.git::$INDEX_ALLOCATION/config", "r/plain.txt"), to)
    assert len(notes) == 6, notes
    assert sorted(p.relative_to(to).as_posix() for p in to.rglob("*") if p.is_file()) == ["r/.git/config", "r/plain.txt"]
    assert any("not written" in n for n in _untar(_tar(f"a{BS}..{BS}r{BS}.git{BS}config"), to)), "a separator of this disk's"


PLANT = "[core]\n\trepositoryformatversion = 0\n\tfsmonitor = echo x > {}\n"
ODD = "[core]\n\tbare = false\n[extensions]\n\tobjectformat = \"sha1\\n[core]\\n\\tfsmonitor = echo\"\n"


def _repo(at: Path, config: str, shaped=True):
    for d in (["objects/info", "refs", "hooks"] if shaped else ["hooks"]):
        (at / d).mkdir(parents=True, exist_ok=True)
    (at / "HEAD").write_text("ref: refs/heads/x\n")
    (at / "config").write_text(config)
    (at / "hooks" / "post-index-change").write_text("#!/bin/sh\necho ran\n")


def test_whatever_landed_is_left_inert_and_said(tmp_path):
    to, marker = tmp_path / "to", tmp_path / "ran"
    _repo(to / "shaped" / "thing", PLANT.format(marker.as_posix()))
    _repo(to / "plain" / ".git", PLANT.format(marker.as_posix()))
    _repo(to / "odd" / ".git", ODD)
    (to / "plain" / ".git" / "objects" / "info" / "alternates").write_text(UNC + "\n")
    (to / "gitfile").mkdir()
    (to / "gitfile" / ".git").write_text("gitdir: ../elsewhere\n")
    (to / "ok" / ".git" / "objects").mkdir(parents=True)
    (to / "ok" / ".git" / "config").write_text("[core]\n\trepositoryformatversion = 0\n\tbare = false\n")
    (to / "honest").mkdir()
    (to / "honest" / "config").write_text("mine\n")
    notes = E._left_inert(to)
    assert (to / "ok" / ".git" / "config").is_file(), "a config of the format alone stays"
    assert (to / "honest" / "config").read_text() == "mine\n", "no repository: its files are its own"
    for gone in ("shaped/thing/config", "shaped/thing/hooks", "plain/.git/config", "plain/.git/hooks", "odd/.git/config",
                 "plain/.git/objects/info/alternates", "gitfile/.git"):
        assert not (to / gone).exists(), gone
        assert any(n.startswith(gone) for n in notes), gone
    for repo in ("shaped/thing", "plain"):
        subprocess.run(["git", "-c", "safe.directory=*", "-C", str(to / repo), "status"], capture_output=True, timeout=60)
    assert not marker.exists(), "git on the host ran what an agent wrote"


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


def _inspected(monkeypatch, lines, killed=()):
    def run(argv, **k):
        if argv[1] == "kill":
            killed.extend(argv[2:])
        return subprocess.CompletedProcess(argv, 0, lines, "")
    monkeypatch.setattr(E, "run", run)
    monkeypatch.setattr(E, "_home", lambda data=None: "mine")


def test_the_watch_ends_only_its_own_installation_s_work_node_or_none(monkeypatch):
    _inspected(monkeypatch, "a mine\nb other\nc mine2\ne <no value>\n")
    assert E._own_of(["a", "b", "c", "d", "e"]) == ["a"] and E._own_of([]) == []


def test_a_turn_of_the_watch_kills_nothing_of_another_installation(monkeypatch):
    killed, turns = [], iter((False, True))
    _inspected(monkeypatch, "b other\n", killed)
    monkeypatch.setattr(E, "ceiling", lambda: ["x"])
    monkeypatch.setattr(E, "_over_share", lambda read, units: ["b"])
    E._watch_ceiling(SimpleNamespace(wait=lambda s: next(turns)))
    assert killed == []


def test_a_system_directory_s_temp_goes_with_it_and_is_mounted_once(tmp_path):
    (tmp_path / "e.env").write_text("X=1" + chr(10))
    (base := tmp_path / "w" / "b").mkdir(parents=True)
    x = E.ContainerExecution("default", "image", str(tmp_path / "e.env"), str(tmp_path / "s"), str(base), "p")
    check = str(x.sys / "gfso-check-1")
    assert x.temp_of(check) == check
    held = [d for d, _ in E.PlaceContainer(x, Path(check))._mounts()]
    assert len(held) == len(set(held)) and Path(check) in held


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


def test_live_an_export_neutralises_a_repository_by_its_shape_and_git_there_runs_nothing(project, tmp_path):  # noqa: F811
    """`git status` of the user's own, in each directory of the export: none runs what an agent planted — under no `.git`
    name, a bare one's shape, one reached by a newline in its parent's name (Linux hosts), a repository nested in another."""
    marker = tmp_path / "ran"
    plant = f"[core]\n\trepositoryformatversion = 0\n\tfsmonitor = echo x > {marker.as_posix()}\n\tbare = false\n".encode()
    for d in ("shaped/thing", "shaped/.git/modules/nested", "plain/.git"):
        made(project, f"{d}/objects", f"{d}/refs", f"{d}/hooks")
        project.files.write_bytes(str(project.own / d / "HEAD"), b"ref: refs/heads/x\n")
        project.files.write_bytes(str(project.own / d / "config"), plant)
    made(project, "locked/.git/objects", "locked/.git/refs", "locked/.git/hooks")     # …left read-only by the agent
    project.files.write_bytes(str(project.own / "locked/.git/HEAD"), b"ref: refs/heads/x\n")
    project.files.write_bytes(str(project.own / "locked/.git/config"), plant)
    project.run(["sh", "-c", f"chmod -R a-w {(project.own / 'locked').as_posix()}"], cwd=str(project.base), timeout=60, root=True)
    made(project, "honest/config")
    project.files.write_bytes(str(project.own / "honest/HEAD"), b"a file of the project's, named so\n")
    project.files.write_bytes(str(project.own / "honest/config/kept"), b"kept")
    out = tmp_path / "out"
    project.volume.export(project.image, out)
    assert (out / "honest/config/kept").read_bytes() == b"kept", "a directory not shaped as a repository keeps its files"
    for args in (["-C", str(out / "shaped/thing"), "status"], ["-C", str(out / "plain"), "status"],
                 ["-C", str(out / "locked"), "status"]):
        subprocess.run(["git", "-c", "safe.directory=*", *args], capture_output=True, timeout=60)
    assert not marker.exists(), "git on the host ran what an agent wrote"
    for d in ("shaped/thing", "shaped/.git/modules/nested", "plain/.git", "locked/.git"):
        at = out / d
        assert b"fsmonitor" not in (at / "config").read_bytes() and not (at / "hooks").exists(), d


@pytest.mark.parametrize("version, platform, refused", [
    ("23.0.10", "Docker Engine - Community", True), ("23.0.11", "Docker Engine - Community", False),
    ("24.0.9", "Docker Engine - Community", True), ("25.0.4", "Docker Engine - Community", True),
    ("25.0.5", "Docker Engine - Community", False), ("26.0.0", "Docker Engine - Community", False),
    ("20.10.24", "", True), ("24.0.9", "Docker Desktop 4.90.0 (1)", False), ("", "Docker Engine - Community", False),
])
def test_a_linux_engine_whose_internal_network_leaks_names_is_refused(version, platform, refused):
    assert bool(E.refused_docker(version, platform)) is refused


def test_every_start_asks_the_engine_s_version(monkeypatch):
    monkeypatch.setattr(E, "run", lambda argv, **k: subprocess.CompletedProcess(argv, 0, "24.0.9|Docker Engine - Community", ""))
    assert "CVE-2024-29018" in E._unavailable(None, False)


def test_a_check_the_disk_s_watch_ended_says_so(monkeypatch, tmp_path):


    monkeypatch.setattr(O, "_run", lambda *a: {"rc": 137, "out": "", "stdout": "", "stderr": ""})
    monkeypatch.setattr(O, "ended_by_watch", lambda ex: False)
    monkeypatch.setattr(O, "past_disk", lambda ex: "its work past its bound")
    ex = SimpleNamespace(release=lambda t: None, copy_tree=lambda a, b: None, files=None, session=lambda p: None,
                         system_writes=lambda p, **k: contextlib.nullcontext(), scratch=lambda *a, **k: contextlib.nullcontext(str(tmp_path)))
    c = Criteria("c", check=(Probe("b", "x", "ok", exact=True),))
    got = O._fresh_run(ex, "sh", c, c.check[0], str(tmp_path), 5, str(tmp_path), [])
    assert "past its bound" in got["out"] and got["stdout"] == ""
