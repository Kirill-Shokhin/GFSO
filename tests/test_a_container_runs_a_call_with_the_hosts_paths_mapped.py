"""A call inside a project's container runs where its place is, sees container paths, and gives host paths back.

One server runs every project's work isolated by EXECUTION, never by a second server (the author, 2026-10-25: «разве не
должно быть так что сервер один а исполнение все равно изолировано?»). The container holds the base and the project's
own system directories beside it at `/gfso-place`, from any absolute parent — a Windows drive's or a POSIX one; a path crossing the boundary is mapped both ways, a place outside them is
refused, the host's network is shut (Docker Desktop forwards 192.168.65.254 to the host's loopback, :8000 included), and a
call is ended inside, its own group and whatever left it — killing the `docker exec` client leaves them running (probes
P1, P8: docs/notes/ONE_SERVER_PROBES.md).
"""
import os
import shutil
import subprocess
import time
from pathlib import PurePosixPath, PureWindowsPath

import pytest

import gfso.adapters.execution as E
from gfso.adapters.execution import ContainerExecution, _writable_root, scratch_of
from gfso.core.types import files_at, hold_places

IMAGE = os.environ.get("GFSO_TEST_IMAGE", "e3-linux-agent:2")   # CI: the product's own image


@pytest.fixture
def place(tmp_path):
    base = tmp_path / "work" / "base"
    base.mkdir(parents=True)
    return base


def _ex(base, tmp_path, env_file="envf"):
    return ContainerExecution("e3-linux", IMAGE, str(env_file), str(tmp_path / "state"), str(base), "GB proj")


def _windows(tmp_path, monkeypatch):
    """A Windows parent on whatever host runs the test. Its spellings are a Windows path's: under a POSIX parent a
    backslash is a character of a file's name and another case another directory, so they are not that parent
    (`test_a_posix_parent_maps_paths_both_ways`)."""
    monkeypatch.setattr(E, "_real", PureWindowsPath)
    p = "C:\\Users\\u\\work"
    return ContainerExecution("e3-linux", IMAGE, None, str(tmp_path / "state"), p + "\\base", "p"), p


def test_a_path_is_mapped_both_ways_where_the_tests_run(place, tmp_path):
    """The host's own parent, resolved by the host: a Windows drive's on Windows, a POSIX one on Linux."""
    x, p = _ex(place, tmp_path), place.parent.as_posix()
    assert x.to_inside(f"see {p}/base/a/b.c now") == "see /gfso-place/base/a/b.c now"
    assert x.to_outside("cd /gfso-place/base && ls") == f"cd {p}/base && ls"
    assert x.to_inside(p + "X/y") == p + "X/y", "a sibling that only starts like the parent is not it"
    assert x.to_outside("/gfso-placed") == "/gfso-placed"


def test_a_path_is_mapped_both_ways_in_any_spelling(tmp_path, monkeypatch):
    x, p = _windows(tmp_path, monkeypatch)
    for host in (p + "\\base\\a\\b.c", p.replace("\\", "/") + "/base/a/b.c", p.lower() + "\\base\\a\\b.c",
                 p.replace("\\", "\\\\") + "\\\\base\\\\a\\\\b.c"):
        assert x.to_inside(f"see {host} now") == "see /gfso-place/base/a/b.c now", host
    assert x.to_outside("cd /gfso-place/base && ls") == "cd C:/Users/u/work/base && ls"
    assert x.to_inside(p + "X\\y") == p + "X\\y", "a sibling that only starts like the parent is not it"
    assert x.to_inside(p + "\\basement") == p + "\\basement", "nor one that only starts like the mounted directory"
    assert x.to_outside("/gfso-placed") == "/gfso-placed"


def test_a_place_outside_its_mounts_is_refused(place, tmp_path):
    x = _ex(place, tmp_path)
    assert x._inside_cwd(str(place.parent / ".gfso-nodes-base" / "GB_proj" / "k")) == "/gfso-place/.gfso-nodes-base/GB_proj/k"
    for outside in (place.parent / "other", tmp_path, place.parent, place.parent / ".gfso-nodes-base" / "other" / "k",
                    place.parent / ".gfso-scratch-base" / "r", place.parent / ".gfso-tmp-base"):
        with pytest.raises(ValueError):
            x._inside_cwd(str(outside))


def test_a_posix_parent_maps_paths_both_ways(tmp_path, monkeypatch):
    """Linux and macOS have no drive letter: the mapping holds from any absolute parent, a POSIX one spelled exactly."""
    monkeypatch.setattr(E, "_real", PurePosixPath)
    x = ContainerExecution("e3-linux", IMAGE, None, str(tmp_path / "state"), "/home/u/work/base", "p")
    assert x.to_inside("see /home/u/work/base/a/b.c now") == "see /gfso-place/base/a/b.c now"
    assert x.to_inside('{"cwd": "/home/u/work/.gfso-nodes-base/p/k"}') == '{"cwd": "/gfso-place/.gfso-nodes-base/p/k"}'
    for other in ("/home/u/workX/y", "/mnt/home/u/work/base", "/home/U/work/base"):
        assert x.to_inside(other) == other, "a sibling, a longer path, another case: not the parent"
    assert x.to_outside("cd /gfso-place/base && ls") == "cd /home/u/work/base && ls"
    assert x._inside_cwd("/home/u/work/.gfso-nodes-base/p/k/src") == "/gfso-place/.gfso-nodes-base/p/k/src"
    w, nodes = PurePosixPath("/home/u/work"), PurePosixPath("/home/u/work/.gfso-nodes-base/p")
    assert _writable_root(w / "base" / "src", x) == w / "base"
    assert _writable_root(nodes / "k" / "src", x) == nodes / "k"
    assert _writable_root(nodes / ".gfso-scratch-k" / "k_1" / "run", x) == nodes / ".gfso-scratch-k" / "k_1"
    assert _writable_root(nodes / ".gfso-scratch-k" / "k_1" / "batch2_again" / "delivery", x) == \
        nodes / ".gfso-scratch-k" / "k_1" / "batch2_again", "a validation's batch is a root of its own"
    assert _writable_root(nodes / ".gfso-tmp" / "node-1" / "f", x) == nodes / ".gfso-tmp" / "node-1"
    with pytest.raises(ValueError):
        x._inside_cwd("/home/u/other")
    assert x.to_inside("PYTHONPATH=/home/u/work/base/src:/home/u/work/base/lib") == \
        "PYTHONPATH=/gfso-place/base/src:/gfso-place/base/lib", "each entry of a list, not the first swallowing the rest"
    for said, inside in (("cd /home/u/work/base;make", "cd /gfso-place/base;make"),
                         ("(cd /home/u/work/base)", "(cd /gfso-place/base)"),
                         ("cd /home/u/work/base&&make", "cd /gfso-place/base&&make")):
        assert x.to_inside(said) == inside, "a mounted directory's own path ends where its name does (critic over 00187de)"
    assert x.to_inside("/home/u/work/basement") == "/home/u/work/basement"


def test_a_windows_list_maps_each_entry(tmp_path, monkeypatch):
    x, p = _windows(tmp_path, monkeypatch)
    assert x.to_inside(f"PATH={p}\\base\\bin;{p}\\base\\lib") == "PATH=/gfso-place/base/bin;/gfso-place/base/lib"


@pytest.mark.parametrize("flavour, base, outside, inside, back", [
    (PurePosixPath, "/workspace", ["echo hi ", "/usr/bin/python3", "/workspaceX/a", "/"],
     "/workspace/a", "/workspace/a"),
    (PureWindowsPath, "C:\\ws", ["a C: b", "C:", "C:\\Windows\\x", "C:/wsx"], "C:\\ws\\a", "C:/ws/a")])
def test_a_root_or_a_drive_as_the_parent_maps_only_what_is_mounted(tmp_path, monkeypatch, flavour, base, outside,
                                                                  inside, back):
    """Mapped from the parent alone, a root's matched the empty string everywhere — `echo hi /gfso-place`, every
    `/usr/bin/…` sent into the container's mount (critic over d80e311)."""
    monkeypatch.setattr(E, "_real", flavour)
    x = ContainerExecution("e3-linux", IMAGE, None, str(tmp_path / "state"), base, "p")
    for text in outside:
        assert x.to_inside(text) == text
    leaf = flavour(base).name
    assert x.to_inside(inside) == f"/gfso-place/{leaf}/a" and x.to_outside(f"/gfso-place/{leaf}/a") == back


def test_a_parent_through_a_link_is_mapped_as_given_and_as_resolved(tmp_path, monkeypatch):
    """The roster names a place the way the workdir was given; the parent is resolved — a link in it left every place
    spelled as given unmapped (critic, run on Linux)."""
    monkeypatch.setattr(E, "_real", lambda p: PurePosixPath(str(p).replace("/tmp/link", "/tmp/w", 1)))
    x = ContainerExecution("e3-linux", IMAGE, None, str(tmp_path / "state"), "/tmp/link/base", "p")
    assert x.to_inside("/tmp/link/base/src/a /tmp/w/base/src/a") == "/gfso-place/base/src/a /gfso-place/base/src/a"


def test_two_projects_on_one_base_hold_disjoint_system_directories(place, tmp_path):
    """Every system directory names its project: two projects on one base share none, and a path the system named is
    read by its own project's holder (`files_at`) — a base's rounds included, now among its project's places."""
    a, b = _ex(place, tmp_path), ContainerExecution("e3-linux", IMAGE, None, str(tmp_path / "state"), str(place), "other")
    assert not {s for s, _ in a._mounts()[1:]} & {s for s, _ in b._mounts()[1:]}
    assert a.temp_root() != b.temp_root() and a._scratch_root(True) != b._scratch_root(True)
    ra, rb = scratch_of(place, a.project_name) / "root_1", scratch_of(place, b.project_name) / "root_1"
    assert ra != rb and _writable_root(rb, b) == rb
    hold_places(b.files)
    hold_places(a.files)                                 # …first in the table: it answers whatever it holds
    try:
        for path in (rb / "t.c", b.temp_of(str(place)), b._scratch_root(True) + "/x"):
            assert files_at(path) is b.files, path
        assert files_at(ra / "t.c") is a.files
    finally:
        hold_places(a.files, False)
        hold_places(b.files, False)


def test_the_container_holds_only_the_projects_own_directories_and_no_cli_state(place, tmp_path):
    """No session's CLI runs in the project's container — each runs in its place's — and the probes that do run there
    are the agents' own: the CLI state, every place's under it, is not mounted."""
    a = _ex(place, tmp_path).run_args()
    mounts = [a[i + 1] for i, v in enumerate(a) if v == "--mount"]
    assert [m.split("dst=")[1] for m in mounts] == ["/gfso-place/base,volume-subpath=.gfso-base",
                                                    "/gfso-place/.gfso-nodes-base/GB_proj"], "nothing of the host"
    assert all(m.startswith("type=volume,") for m in mounts)
    assert "-v" not in a and "--privileged" not in a and ["--cap-add", "NET_ADMIN"] == a[a.index("--cap-add"):][:2]
    assert a[a.index("--name") + 1] .startswith("gfso-e3-linux-gb-proj-")


def test_a_call_is_started_inside_its_mapped_place_with_only_what_it_sets(place, tmp_path, monkeypatch):
    ran, started = [], []
    monkeypatch.setattr(E, "run", lambda args, **kw: ran.append(args) or subprocess.CompletedProcess(
        args, 0, "true" if args[:2] == ["docker", "inspect"] else "", ""))
    monkeypatch.setattr(E.LocalExecution, "popen", lambda self, argv, **kw: started.append((argv, kw)) or _Client())
    monkeypatch.setattr(E, "_STARTED", {})
    monkeypatch.setenv("SOME_HOST_VAR", "x")
    one, two = _ex(place, tmp_path), _ex(place, tmp_path)
    env = {"SOME_HOST_VAR": "x", "CLAUDE_CODE_MAX_OUTPUT_TOKENS": "64000", "PATH": "C:\\Windows"}
    monkeypatch.setenv("PATH", "C:\\Windows")
    call = one.popen(["claude", "-p", "--system-prompt", f"work in {place}"], env=env, cwd=str(place))
    two.popen(["claude"], env=env, cwd=str(place))
    assert sum(1 for a in ran if a[:3] == ["docker", "run", "-d"]) == 1, "one container per project, whichever object asks"
    argv = started[0][0]
    assert argv[:5] == ["docker", "exec", "-i", "-w", "/gfso-place/base"]
    assert f"GFSO_CALL={call.call}" in argv and "CLAUDE_CODE_MAX_OUTPUT_TOKENS=64000" in argv
    assert not any("SOME_HOST_VAR" in a or a.startswith("PATH=") for a in argv), "the host's environment stays out"
    assert argv[-4:] == ["claude", "-p", "--system-prompt", "work in /gfso-place/base"]
    one.end(call)
    assert any(a[:2] == ["docker", "exec"] and any(str(v).startswith("gfso-e3-linux-gb-proj-") for v in a) and f"GFSO_CALL={call.call}" in a[-1] for a in ran)


class _Client:
    stdin = stdout = stderr = None
    text_mode = True
    pid, returncode = 2 ** 22 + 9, 0

    def poll(self):
        return 0

    def kill(self):
        pass


def _docker():
    if not shutil.which("docker"):
        return False
    return subprocess.run(["docker", "image", "inspect", IMAGE], capture_output=True).returncode == 0


@pytest.mark.skipif(not _docker(), reason=f"needs docker and {IMAGE}")
def test_live_an_open_way_out_reaches_out_but_not_its_gateway(place, tmp_path):
    """On Docker Engine the host is the default gateway, not Docker Desktop's network: shut too, while what it routes
    onward stays open (critic over d80e311). A port published on the gateway stands for the host's service."""
    listen = f"vol-v2a-listen-{time.time_ns()}"
    x = ContainerExecution("t", IMAGE, None, str(tmp_path / "state"), str(place), f"live{time.time_ns()}")
    subprocess.run(["docker", "run", "-d", "--rm", "--name", listen, "-p", "18765:8000", IMAGE,
                    "python3", "-m", "http.server", "8000"], capture_output=True, check=True)
    try:
        get = "curl -s -o /dev/null -w '%{http_code}' --max-time 20 "
        out = x.run(["sh", "-c", f"sleep 2; gw=$({E._GATEWAY_OF}); echo $({get}http://$gw:18765/); "
                     f"echo $({get}https://api.anthropic.com/)"], cwd=str(place), timeout=120).stdout.split()
        assert out[0] == "000" and out[1] != "000", out
    finally:
        x.stop()
        subprocess.run(["docker", "rm", "-f", listen], capture_output=True)


@pytest.mark.skipif(not _docker(), reason=f"needs docker and {IMAGE}")
def test_live_a_call_inside_is_sealed_mapped_and_ended_whole(place, tmp_path):
    env_file = tmp_path / "e.env"
    env_file.write_text("NOTHING=1\n")
    x = ContainerExecution("t", IMAGE, str(env_file), str(tmp_path / "state"), str(place), f"live{time.time_ns()}")
    try:
        (place / "in.txt").write_text("hello")
        p = x.popen(["sh", "-c", "pwd; cat in.txt; echo; cat; echo;"
                     " (timeout 3 bash -c 'echo > /dev/tcp/192.168.65.254/8000' && echo OPEN) 2>/dev/null || echo SHUT"],
                    env={}, cwd=str(place), stdin=subprocess.PIPE, stdout=subprocess.PIPE, text=True)
        p.stdin.write(f"fed {place / 'in.txt'}")
        p.stdin.close()
        out = list(p.stdout)
        p.wait(timeout=30)
        assert [line.strip() for line in out] == [f"{place.parent.as_posix()}/base", "hello",
                                                  f"fed {place.parent.as_posix()}/base/in.txt", "SHUT"]
        q = x.popen(["sh", "-c", "setsid sleep 300 & sleep 300"], env={}, cwd=str(place),
                    stdout=subprocess.PIPE, text=True)
        time.sleep(2)
        x.end(q)
        left = subprocess.run(["docker", "exec", x.container, "sh", "-c", "pgrep -c sleep || true"],
                              capture_output=True, text=True).stdout.strip()
        assert left == "1", f"the call's sleeps outlived its end: {left} (only the container's own `sleep infinity`)"
    finally:
        x.stop()


def test_each_project_keeps_its_own_cli_state(place, tmp_path):
    """Shared by an execution's projects, the CLI state let one E3 row read and append to another's conversation —
    every row's cwd is `/gfso-place/ws` (critic over d5c8f7a)."""
    a = ContainerExecution("e3-linux", IMAGE, "f", str(tmp_path / "state"), str(place), "row-a")
    b = ContainerExecution("e3-linux", IMAGE, "f", str(tmp_path / "state"), str(place), "row-b")
    assert a.state_dir() == a.own / ".gfso-state" and b.state_dir() == b.own / ".gfso-state" != a.state_dir()
    assert len({a.volume.name, a.volume.state, b.volume.name, b.volume.state}) == 4, "each in its project's own volumes"
    c = ContainerExecution("e3-linux", IMAGE, "f", str(tmp_path / "state"), str(tmp_path / "elsewhere" / "ws"), "row-a")
    assert c.volume.name != a.volume.name, "a project moved to another base mounts none of the first one's places"


@pytest.mark.skipif(not _docker(), reason=f"needs docker and {IMAGE}")
def test_live_a_container_removed_under_the_server_is_started_again_and_ends_with_it(place, tmp_path):
    env_file = tmp_path / "e.env"
    env_file.write_text("NOTHING=1\n")
    x = ContainerExecution("t", IMAGE, str(env_file), str(tmp_path / "state"), str(place), f"live{time.time_ns()}")
    try:
        assert x.run(["echo", "one"], cwd=str(place), timeout=60).stdout.strip() == "one"
        subprocess.run(["docker", "rm", "-f", x.container], capture_output=True)
        assert x.run(["echo", "two"], cwd=str(place), timeout=60).stdout.strip() == "two", "not started again"
        E.end_started()
        gone = subprocess.run(["docker", "ps", "-aq", "--filter", f"name={x.container}"], capture_output=True, text=True)
        assert not gone.stdout.strip(), "the server's exit left its container running"
    finally:
        x.stop()
