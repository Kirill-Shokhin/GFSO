"""A call inside a project's container runs where its place is, sees container paths, and gives host paths back.

One server runs every project's work isolated by EXECUTION, never by a second server (the author, 2026-10-25: «разве не
должно быть так что сервер один а исполнение все равно изолировано?»). The container holds the base's parent's four
directories of the project at `/gfso-place`; a path crossing the boundary is mapped both ways, a place outside them is
refused, the host's network is shut (Docker Desktop forwards 192.168.65.254 to the host's loopback, :8000 included), and a
call is ended inside, its own group and whatever left it — killing the `docker exec` client leaves them running (probes
P1, P8: docs/notes/ONE_SERVER_PROBES.md).
"""
import shutil
import subprocess
import time

import pytest

import gfso.adapters.execution as E
from gfso.adapters.execution import ContainerExecution

IMAGE = "e3-linux-agent:2"


@pytest.fixture
def place(tmp_path):
    base = tmp_path / "work" / "base"
    base.mkdir(parents=True)
    return base


def _ex(base, tmp_path, env_file="envf"):
    return ContainerExecution("e3-linux", IMAGE, str(env_file), str(tmp_path / "state"), str(base), "GB proj")


def test_a_path_is_mapped_both_ways_in_any_spelling(place, tmp_path):
    x = _ex(place, tmp_path)
    p = str(place.parent)
    for host in (p + "\\base\\a\\b.c", p.replace("\\", "/") + "/base/a/b.c", p.lower() + "\\base\\a\\b.c",
                 p.replace("\\", "\\\\") + "\\\\base\\\\a\\\\b.c"):
        assert x.to_inside(f"see {host} now") == "see /gfso-place/base/a/b.c now", host
    assert x.to_outside("cd /gfso-place/base && ls") == f"cd {place.parent.as_posix()}/base && ls"
    assert x.to_inside(p + "X\\y") == p + "X\\y", "a sibling that only starts like the parent is not it"
    assert x.to_outside("/gfso-placed") == "/gfso-placed"


def test_a_place_outside_the_four_mounts_is_refused(place, tmp_path):
    x = _ex(place, tmp_path)
    assert x.inside_cwd(str(place.parent / ".gfso-nodes-base" / "p" / "k")) == "/gfso-place/.gfso-nodes-base/p/k"
    for outside in (place.parent / "other", tmp_path, place.parent):
        with pytest.raises(ValueError):
            x.inside_cwd(str(outside))


def test_the_container_holds_only_the_projects_four_directories_and_its_state(place, tmp_path):
    a = _ex(place, tmp_path).run_args()
    mounts = [a[i + 1] for i, v in enumerate(a) if v == "--mount"]
    assert [m.split("dst=")[1] for m in mounts] == ["/gfso-place/base", "/gfso-place/.gfso-nodes-base",
                                                     "/gfso-place/.gfso-scratch-base", "/gfso-place/.gfso-tmp-base",
                                                     "/home/agent/.claude"]
    assert "-v" not in a and "--privileged" not in a and ["--cap-add", "NET_ADMIN"] == a[a.index("--cap-add"):][:2]
    assert a[a.index("--name") + 1] == "gfso-e3-linux-gb-proj"


def test_a_call_is_started_inside_its_mapped_place_with_only_what_it_sets(place, tmp_path, monkeypatch):
    ran, started = [], []
    monkeypatch.setattr(E, "run", lambda args, **kw: ran.append(args) or subprocess.CompletedProcess(args, 0, b"", b""))
    monkeypatch.setattr(E.LocalExecution, "popen", lambda self, argv, **kw: started.append((argv, kw)) or _Client())
    monkeypatch.setattr(E, "_STARTED", set())
    monkeypatch.setenv("SOME_HOST_VAR", "x")
    one, two = _ex(place, tmp_path), _ex(place, tmp_path)
    env = {"SOME_HOST_VAR": "x", "CLAUDE_CODE_MAX_OUTPUT_TOKENS": "64000", "PATH": "C:\\Windows"}
    monkeypatch.setenv("PATH", "C:\\Windows")
    call = one.popen(["claude", "-p", "--system-prompt", f"work in {place}"], env=env, cwd=str(place))
    two.popen(["claude"], env=env, cwd=str(place))
    assert sum(1 for a in ran if a[:2] == ["docker", "run"]) == 1, "one container per project, whichever object asks"
    argv = started[0][0]
    assert argv[:5] == ["docker", "exec", "-i", "-w", "/gfso-place/base"]
    assert f"GFSO_CALL={call.call}" in argv and "CLAUDE_CODE_MAX_OUTPUT_TOKENS=64000" in argv
    assert not any("SOME_HOST_VAR" in a or a.startswith("PATH=") for a in argv), "the host's environment stays out"
    assert argv[-4:] == ["claude", "-p", "--system-prompt", "work in /gfso-place/base"]
    one.end(call)
    assert any(a[:3] == ["docker", "exec", "gfso-e3-linux-gb-proj"] and f"GFSO_CALL={call.call}" in a[-1] for a in ran)


class _Client:
    stdin = stdout = None
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
