"""Every container the system makes is bounded in memory and processes (`config.container_limits`): unbounded, one
judge's probe held 9 GiB of the Docker VM's 19.5 and starved every project on the machine and the host (series 3,
c_compiler, 2026-10-30; the author's charter: «по ошибке могут насрать соседу и вся система полетит»). A runaway dies
as its own failure, exit 137, and the session it ran in goes on.
"""
import inspect
import json
import re
import subprocess
import time
from pathlib import Path
from types import SimpleNamespace

import pytest

import gfso.adapters.execution as E
import gfso.adapters.snapshots as S
from gfso import config as C
from tests.test_a_session_holds_only_its_own_place import IMAGE, made, project  # noqa: F401
from tests.test_the_system_reads_a_place_where_its_agent_cannot_lead_it_out import _docker

live = pytest.mark.skipif(not _docker(), reason=f"needs docker and {IMAGE}")


def test_the_bounds_are_the_installations_dial_with_defaults(monkeypatch):
    monkeypatch.delenv("GFSO_CONTAINER_MEMORY", raising=False)
    monkeypatch.delenv("GFSO_CONTAINER_PIDS", raising=False)
    assert C.container_limits() == ["--memory", "4g", "--memory-swap", "4g", "--pids-limit", "4096"]
    monkeypatch.setenv("GFSO_CONTAINER_MEMORY", "6g")
    monkeypatch.setenv("GFSO_CONTAINER_PIDS", "512")
    assert C.container_limits() == ["--memory", "6144m", "--memory-swap", "6144m", "--pids-limit", "512"]
    monkeypatch.setenv("GFSO_CONTAINER_MEMORY", "unbounded")
    monkeypatch.setenv("GFSO_CONTAINER_PIDS", "-1")
    assert C.container_limits() == ["--memory", "4g", "--memory-swap", "4g", "--pids-limit", "4096"], \
        "a dial that does not read bounds by the default, never by nothing"
    for unbounded_or_refused in ("0", "0g", "512", "5m"):
        monkeypatch.setenv("GFSO_CONTAINER_MEMORY", unbounded_or_refused)
        assert C.container_limits()[1] == "4g", unbounded_or_refused
    for said, read in (("64M", "64m"), ("8GB", "8192m"), ("8GiB", "8192m"), ("8gb", "8192m"), ("512mib", "512m"),
                       ("1.5g", "1536m"), ("8 g", "8192m"), ("1t", "1048576m")):
        monkeypatch.setenv("GFSO_CONTAINER_MEMORY", said)
        assert C.container_limits()[1] == read, "as Docker reads it: the dial a bound-named FAIL points to"


def test_every_docker_run_of_the_system_is_bounded():
    """Each `docker run` the execution makes carries the bounds, or flags its every caller bounds (`_system_run`: the
    door's and the gateway's, fixed and smaller)."""
    src = inspect.getsource(E)
    sites = [m.start() for m in re.finditer(r'"docker", "run"', src)]
    assert len(sites) >= 4
    for at in sites:
        call = src[at:at + 700]
        assert "container_limits()" in call or "*flags" in call, src[at:at + 200]
    with pytest.raises(ValueError, match="bounded"):
        E._system_run("gfso-never-started", IMAGE, ["--label", "x=y"], Path(__file__), [], Path("log"))
    assert E._SMALL == ("--memory", "256m", "--memory-swap", "256m", "--pids-limit", "256")
    assert src.count("*_SMALL") == 2, "the door's and the gateway's, no swap past their bound"


@live
def test_live_a_runaway_dies_alone_and_its_session_goes_on(project, monkeypatch):  # noqa: F811
    monkeypatch.setenv("GFSO_CONTAINER_MEMORY", "128m")
    monkeypatch.setenv("GFSO_CONTAINER_PIDS", "128")
    made(project, "a")
    a = project.session(str(project.parent / ".gfso-nodes-ws/p/a"))
    assert a.run(["true"], cwd=str(project.base), timeout=120).returncode == 0
    for name in (a.container, project.container):
        host = json.loads(subprocess.run(["docker", "inspect", "-f", "{{json .HostConfig}}", name],
                                         capture_output=True, text=True).stdout)
        assert (host["Memory"], host["MemorySwap"], host["PidsLimit"]) == (128 * 2 ** 20, 128 * 2 ** 20, 128), name
    eat = a.run(["python3", "-c", "b = b'x' * (512 * 2 ** 20)"], cwd=str(project.base), timeout=120)
    assert eat.returncode == 137, (eat.returncode, eat.stderr)
    fork = a.run(["sh", "-c", "for i in $(seq 300); do sleep 2 & done; wait"], cwd=str(project.base), timeout=120)
    assert re.search(r"fork|unavailable", fork.stderr or "", re.I), (fork.returncode, fork.stderr[-300:])
    time.sleep(3)                                       # …what the processes' bound refused, the session's own call too
    after = a.run(["echo", "alive"], cwd=str(project.base), timeout=120)
    assert after.returncode == 0 and after.stdout.strip() == "alive", "the session's container goes on"


@pytest.mark.parametrize("rc, said", [(6, "rewritten"), (1, "Errno 6"), (137, "memory bound")])
def test_a_judges_copy_its_bound_ended_is_the_deliverys_fail_with_its_cause(rc, said, tmp_path):
    """Nothing else runs in the copy's container while its delivered files are checked: what ends it there — the
    build's rewrite (6), a socket left at a tracked path (1), a reader past its memory's bound (137) — the delivery
    made, every time it is asked; its FAIL, the cause said, never a copy to wait for again (critic over the bounds:
    read as no verdict, a delivery repeated its build on each ask and ended with a person)."""
    ran = SimpleNamespace(returncode=rc, stdout="" if rc == 137 else said, stderr="Killed")
    ex = SimpleNamespace(python="python3", session=lambda at: SimpleNamespace(run=lambda *a, **kw: ran),
                         files=SimpleNamespace(mkdir=lambda *a: None, write_files=lambda *a: None), release=lambda *a: None)
    with pytest.raises(S.BuildFailed, match=said):
        S._after_build(tmp_path, "t" * 40, "c" * 40, ex)


def test_a_reader_ended_past_the_bound_fails_the_delivery_with_its_cause():
    """The checkout's own readers: git ended by SIGKILL is the delivery's FAIL code with the bound named."""
    assert 'if r.returncode == -9:\n        bad(BAD, f"git {args[0]} reading it was {BOUND}")' in S._CHECKOUT
    assert "GFSO_CONTAINER_MEMORY" in S._CHECKOUT


@live
def test_live_a_large_file_the_build_rewrote_is_put_back_within_a_small_bound():
    """`kept` puts a delivered file back a chunk at a time, hashing what it writes: a 200 MB tracked file the build
    rewrote comes back as delivered under a 128 MiB bound (read whole, it was killed: a false FAIL blaming the build —
    critic over the bounds)."""
    name = f"gfso-kept-test-{time.time_ns()}"
    script = ("set -e; mkdir /tmp/w && cd /tmp/w && git init -q && git config user.email t@t && git config user.name t; "
              "head -c 200000000 /dev/urandom > big; git add big; git commit -qm d; "
              "echo rewritten > big; c=$(git rev-parse HEAD); t=$(git rev-parse HEAD^{tree}); "
              'python3 -I -c "$S" kept /tmp/w "$c" "$t"; echo rc=$?; git cat-file blob HEAD:big | cmp -s - big && echo restored')
    try:
        got = subprocess.run(["docker", "run", "--rm", "--name", name, "--memory", "128m", "--memory-swap", "128m",
                              "-e", f"S={S._CHECKOUT}", IMAGE, "sh", "-c", script],
                             capture_output=True, text=True, timeout=300)
    finally:
        subprocess.run(["docker", "rm", "-f", name], capture_output=True)
    assert "rc=0" in got.stdout and "restored" in got.stdout, (got.stdout[-300:], got.stderr[-300:])
