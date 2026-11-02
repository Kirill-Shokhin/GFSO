"""The system reads and writes a place's files in that place's own container, so no link its agent made leads it out.

What the system decides about a place — whether it stands, what a file holds, what a copy's git is — is read where the
place is (`ContainerFiles`). A check of what the agent wrote before acting on it is a race the agent wins: a link flipped
between the check and the read led a bounded read into another node's place (critic over 90a0407: 67 reads and 109
writes in 200). So the path is routed by the system's own record of it (`_writable_root`) into the container of the
place it lies in, whose mounts are the bound; a place's root and what stands above it, which only the system writes,
are asked in the project's. And a call that did not run is no "not there". Live tests start containers of
e3-linux-agent:2; the fake-driven one needs none.
"""
import os
import shutil
import subprocess
import time
from pathlib import Path

import pytest

import gfso.adapters.execution as E
from gfso.adapters.execution import ContainerExecution
from gfso.adapters.snapshots import _own_git
from gfso.core.types import PlaceUnavailable

IMAGE = os.environ.get("GFSO_TEST_IMAGE", "e3-linux-agent:2")   # CI: the product's own image


def _docker() -> bool:
    return bool(shutil.which("docker")) and subprocess.run(["docker", "image", "inspect", IMAGE],
                                                           capture_output=True).returncode == 0


live = pytest.mark.skipif(not _docker(), reason=f"needs docker and {IMAGE}")


@pytest.fixture
def project(tmp_path, monkeypatch):
    monkeypatch.setattr(E, "_SESSIONS", {})
    (work := tmp_path / "work" / "ws").mkdir(parents=True)
    ex = ContainerExecution("vol-v1", IMAGE, None, str(tmp_path / "state"), str(work), "p")
    ex.container = ex.way.container = f"vol-v1-files-{time.time_ns()}"
    ex.way.net, ex.way.gateway = f"{ex.container}-net", f"{ex.container}-gw"
    ex.volume.name, ex.volume.state = f"{ex.container}-v", f"{ex.container}-state"
    try:
        yield ex
    finally:
        ex.stop()
        ex.volume.remove()                      # …every run left its two volumes on the machine (104 by 2026-10-29)
    assert not ex.own.exists(), "the places stand in the project's volume alone"


def _places(ex) -> None:
    """Its two nodes' places and the system's directories, made as the system makes them: inside, in the volume."""
    ex.run(["mkdir", "-p", *[str(ex.own / d) for d in ("a", "b", ".gfso-tmp", ".gfso-sys")]], cwd=str(ex.base),
           timeout=60).check_returncode()


def _sh(ex, cwd, command):
    return ex.session(str(cwd)).run(["sh", "-c", command], cwd=str(cwd), timeout=120)


@live
def test_live_a_place_that_is_not_there_does_not_stand(project):
    _places(project)
    nodes, scratch = project.parent / ".gfso-nodes-ws/p", project.parent / ".gfso-nodes-ws/p/.gfso-scratch-a"
    assert project.files.exists(str(nodes / "a")) and not project.files.exists(str(nodes / "gone"))
    pruned = scratch / "a_1700000000" / "hh3.c"            # …a finding's file in a round the rotation pruned
    assert not project.files.exists(str(pruned)) and not project.files.exists(str(pruned.parent))
    project.files.write_bytes(str(nodes / "a" / "kept.txt"), b"kept")
    subprocess.run(["docker", "rm", "-f", project.container], capture_output=True)   # …Docker restarted under us
    assert project.files.read_bytes(str(nodes / "a" / "kept.txt")) == b"kept"


@live
def test_live_a_link_flipped_out_of_a_place_never_leads_the_system_into_another(project):
    _places(project)
    a, b = project.parent / ".gfso-nodes-ws/p/a", project.parent / ".gfso-nodes-ws/p/b"
    project.files.write_bytes(str(b / "secret"), b"SECRET-B\n")
    project.files.write_bytes(str(a / "ok"), b"benign\n")
    inside = project.to_inside(str(b / "secret"))
    # the agent of `a`, in its own container, flips a link between its own file and the other place's, detached
    _sh(project, a, f"nohup sh -c 'while :; do ln -sfn ok x; ln -sfn {inside} x; done' >/dev/null 2>&1 &")
    time.sleep(1)
    try:
        for _ in range(200):
            assert project.files.read_bytes(str(a / "x")) != b"SECRET-B\n"      # …its own file, or nothing
            try:
                project.files.write_bytes(str(a / "x"), b"PWNED\n")
            except OSError:
                pass                                       # …refused where the link led nowhere
        assert project.files.read_bytes(str(b / "secret")) == b"SECRET-B\n"
    finally:
        _sh(project, a, "pkill -f 'ln -sfn' || true")


@live
def test_live_a_copys_git_reaches_no_other_place_through_its_agents_links(project):
    _places(project)
    a, b = project.parent / ".gfso-nodes-ws/p/a", project.parent / ".gfso-nodes-ws/p/b"
    project.files.write_bytes(str(b / "secret"), b"SECRET-B\n")
    _sh(project, a, f"mkdir -p x && printf 'gitdir: x\\n' > .git && printf '.\\n' > x/commondir && "
                    f"ln -s {project.to_inside(str(b))} x/loot")
    round_ = project.parent / ".gfso-nodes-ws/p/.gfso-scratch-a/a_1700000001"
    project.files.mkdir(str(round_))
    project.copy_tree(str(a), str(round_ / "delivery"))
    _own_git(a, round_ / "delivery", project)
    assert project.files.read_bytes(str(round_ / "delivery" / ".git" / "loot" / "secret")) is None
    assert not _sh(project, round_, f"cat {project.to_inside(str(round_))}/delivery/.git/loot/secret").stdout


def test_a_call_that_did_not_run_is_no_absence(project, monkeypatch):
    answers = []

    def _docker_client(args, **kw):
        if args[:2] == ["docker", "exec"] and any(a.startswith("GFSO_CALL=") for a in args) and answers:
            rc, err = answers.pop(0)
            return subprocess.CompletedProcess(args, rc, b"", err.encode())
        return subprocess.CompletedProcess(args, 0, "" if kw.get("text") else b"", "" if kw.get("text") else b"")
    monkeypatch.setattr(E, "run", _docker_client)
    root = str(project.parent / ".gfso-nodes-ws/p")
    answers[:] = [(1, "")]
    assert project.files.exists(root) is False, "the operation's own no"
    answers[:] = [(126, "OCI runtime exec failed")]
    with pytest.raises(OSError):
        project.files.read_bytes(root)
    answers[:] = [(1, "Error response from daemon: No such container: x")] * 2
    with pytest.raises(OSError):
        project.files.is_dir(root)
    answers[:] = [(1, "Error response from daemon: No such container: x"), (0, "")]
    assert project.files.is_dir(root), "gone under a live server: started again, once"
    answers[:] = [(1, "failed to connect to the docker API at npipe:////./pipe/dockerDesktopLinuxEngine")]
    with pytest.raises(PlaceUnavailable):
        project.files.listdir(root)


@pytest.mark.parametrize("storage", ["its storage does not answer: Input/output error", None])
def test_an_io_error_stops_the_place_only_where_the_systems_own_probe_fails(project, monkeypatch, storage):
    """The daemon answered while its host mounts threw I/O errors for 35 min: every session died, nothing stopped the
    project (clock case 15). The error's words alone stop nothing — a session's output, or a link of its own to
    `/proc/self/mem`, can print them; the probe of the storage decides."""
    def _docker_client(args, **kw):
        err = "cat: x: Input/output error"
        if args[:2] == ["docker", "exec"] and any(a.startswith("GFSO_CALL=") for a in args):
            return subprocess.CompletedProcess(args, 1, "" if kw.get("text") else b"", err if kw.get("text") else err.encode())
        return subprocess.CompletedProcess(args, 0, "" if kw.get("text") else b"", "" if kw.get("text") else b"")
    monkeypatch.setattr(E, "run", _docker_client)
    monkeypatch.setattr(E, "run_printing", lambda args, **kw: _docker_client(args, text=True, **kw))
    monkeypatch.setattr(ContainerExecution, "unavailable", lambda self, storage=False, _said=storage: _said if storage
                        else None)
    where = str(project.parent / ".gfso-nodes-ws/p")
    if storage:
        with pytest.raises(PlaceUnavailable, match="does not answer"):
            project.files.read_bytes(where)
        with pytest.raises(PlaceUnavailable):
            project.run(["cat", "x"], cwd=where, timeout=10)
    else:
        assert project.files.read_bytes(where) is None                      # …the operation's own no
        assert project.run(["cat", "x"], cwd=where, timeout=10).returncode == 1


def test_the_storage_probe_reads_the_base_through_the_mount_the_project_stands_on(project, monkeypatch):
    """Row 2's outage (engineering, 2026-10-28): a FRESH mount of the base passed at 09:45 while the standing mounts
    threw I/O errors, and only at 10:02 did a new one fail. Its project's container running, the base is read through
    that container's own mount; a container of its own reads it only where none runs."""
    ran = []

    def _docker_client(args, **kw):
        ran.append(args)
        if args[:2] == ["docker", "exec"] and project.container in args:
            return subprocess.CompletedProcess(args, 1, "", "ls: /gfso-place/ws: Input/output error")
        return subprocess.CompletedProcess(args, 0, "ok" if args[:2] == ["docker", "run"] else "", "")
    monkeypatch.setattr(E, "run", _docker_client)
    monkeypatch.setitem(E._STARTED, project.container, ("args", ("open", ())))
    assert "Input/output error" in (project.unavailable(storage=True) or ""), "down, though a fresh mount passes"
    E._STARTED.pop(project.container)
    assert project.unavailable(storage=True) is None and [a for a in ran if a[:2] == ["docker", "run"]], \
        "no container running: one of its own reads it"


@live
def test_live_the_storage_probe_answers_on_storage_that_works(project):
    _places(project)
    assert project.unavailable(storage=True) is None
