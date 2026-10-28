"""The system reads and writes a place's files in that place's own container, so no link its agent made leads it out.

What the system decides about a place — whether it stands, what a file holds, what a copy's git is — is read where the
place is (`ContainerFiles`). A check of what the agent wrote before acting on it is a race the agent wins: a link flipped
between the check and the read led a bounded read into another node's place (critic over 90a0407: 67 reads and 109
writes in 200). So the path is routed by the system's own record of it (`_writable_root`) into the container of the
place it lies in, whose mounts are the bound; a place's root and what stands above it, which only the system writes,
are asked in the project's. And a call that did not run is no "not there". Live tests start containers of
e3-linux-agent:2; the fake-driven one needs none.
"""
import shutil
import subprocess
import time
from pathlib import Path

import pytest

import gfso.adapters.execution as E
from gfso.adapters.execution import ContainerExecution
from gfso.adapters.snapshots import _own_git
from gfso.core.types import PlaceUnavailable

IMAGE = "e3-linux-agent:2"


def _docker() -> bool:
    return bool(shutil.which("docker")) and subprocess.run(["docker", "image", "inspect", IMAGE],
                                                           capture_output=True).returncode == 0


live = pytest.mark.skipif(not _docker(), reason=f"needs docker and {IMAGE}")


@pytest.fixture
def project(tmp_path, monkeypatch):
    monkeypatch.setattr(E, "_SESSIONS", {})
    work = tmp_path / "work"
    for d in ("ws", ".gfso-nodes-ws/p/a", ".gfso-nodes-ws/p/b", ".gfso-scratch-ws", ".gfso-tmp-ws", ".gfso-sys-ws"):
        (work / d).mkdir(parents=True, exist_ok=True)
    ex = ContainerExecution("vol-v1", IMAGE, None, str(tmp_path / "state"), str(work / "ws"), "files")
    ex.container = ex.way.container = f"vol-v1-files-{time.time_ns()}"
    ex.way.net, ex.way.gateway = f"{ex.container}-net", f"{ex.container}-gw"
    yield ex
    ex.stop()


def _sh(ex, cwd, command):
    return ex.session(str(cwd)).run(["sh", "-c", command], cwd=str(cwd), timeout=120)


@live
def test_live_a_place_that_is_not_there_does_not_stand(project):
    nodes, scratch = project.parent / ".gfso-nodes-ws/p", project.parent / ".gfso-nodes-ws/p/.gfso-scratch-a"
    assert project.files.exists(str(nodes / "a")) and not project.files.exists(str(nodes / "gone"))
    pruned = scratch / "a_1700000000" / "hh3.c"            # …a finding's file in a round the rotation pruned
    assert not project.files.exists(str(pruned)) and not project.files.exists(str(pruned.parent))
    project.files.write_bytes(str(nodes / "a" / "kept.txt"), b"kept")
    subprocess.run(["docker", "rm", "-f", project.container], capture_output=True)   # …Docker restarted under us
    assert project.files.read_bytes(str(nodes / "a" / "kept.txt")) == b"kept"


@live
def test_live_a_link_flipped_out_of_a_place_never_leads_the_system_into_another(project):
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
