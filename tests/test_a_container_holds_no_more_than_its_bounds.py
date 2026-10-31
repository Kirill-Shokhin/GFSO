"""Every container the system makes is bounded in memory and processes (`config.container_limits`): unbounded, one
judge's probe held 9 GiB of the Docker VM's 19.5 and starved every project on the machine and the host (series 3,
c_compiler, 2026-10-30; the author's charter: «по ошибке могут насрать соседу и вся система полетит»). A runaway dies
as its own failure, exit 137, and the session it ran in goes on.
"""
import inspect
import json
import os
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
        assert "container_limits()" in call or "*flags" in call or "*_SMALL" in call, src[at:at + 200]
        assert "ceiling(" in call or "/sys/fs/cgroup" in call, f"outside the installation's ceiling: {src[at:at + 200]}"
    with pytest.raises(ValueError, match="bounded"):
        E._system_run("gfso-never-started", IMAGE, ["--label", "x=y"], Path(__file__), [], Path("log"))
    assert E._SMALL == ("--memory", "256m", "--memory-swap", "256m", "--pids-limit", "256")
    assert src.count("*_SMALL") == 4, "the door's, the gateway's, the ceiling's maker and its reader: no swap past their bound"


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


def test_the_ceiling_is_a_share_of_dockers_memory_no_installation_dials(monkeypatch):
    monkeypatch.setenv("GFSO_MEMORY_CEILING", "1g")       # …a dial some installation might set: read by nothing
    assert C.memory_ceiling(16 * 2 ** 30) == 12 * 2 ** 30


def _info(driver="cgroupfs 2"):
    calls = []

    def run(args, **kw):
        calls.append(list(args))
        if args[:2] == ["docker", "info"]:
            said = f"{driver} 17179869184" if "CgroupDriver" in args[-1] else str(run.total)
            return subprocess.CompletedProcess(args, 0, said + "\n", "")
        return subprocess.CompletedProcess(args, run.rc, "", "no" if run.rc else "")
    run.rc, run.total = 0, 16 * 2 ** 30
    return run, calls


def test_no_ceiling_where_docker_takes_no_such_group_and_every_container_still_starts(monkeypatch):
    """A systemd cgroup driver takes no `/`-path parent: there the flag would refuse every start, so none is passed."""
    run, calls = _info("systemd 2")
    monkeypatch.setattr(E, "run", run)
    monkeypatch.setattr(E, "_CEILING", {})
    assert E.ceiling() == [] and (E.lay_ceiling() or True) and not any(a[:2] == ["docker", "run"] for a in calls)


def test_a_ceiling_not_written_changes_no_containers_flags_and_is_said_each_time(monkeypatch, caplog):
    """The group a container stands in is decided once: writing its limit failing — Docker busy under the very runaway
    the ceiling is for — must not restart every running container over a changed flag; and each failure is said."""
    run, calls = _info()
    monkeypatch.setattr(E, "run", run)
    monkeypatch.setattr(E, "_CEILING", {})
    monkeypatch.setattr(E, "CEILING_RELAY_S", 0.0)
    flags = E.ceiling()
    assert flags == ["--cgroup-parent", f"/{E.CEILING_GROUP}"]
    run.rc = 1
    E.lay_ceiling()
    E.lay_ceiling()
    assert E.ceiling() == flags, "a failed write moved every container's flags"
    assert sum("was not written" in r.message for r in caplog.records) == 2
    helper = next(a for a in calls if a[:2] == ["docker", "run"])
    assert E.CEILING_IMAGE in helper and helper[helper.index(E.CEILING_IMAGE) - 1] == "sh", "its own shell, pinned"
    assert "@sha256:" in E.CEILING_IMAGE


def test_the_limit_is_written_again_only_after_its_interval_of_dockers_memory_as_it_is_then(monkeypatch):
    run, calls = _info()
    monkeypatch.setattr(E, "run", run)
    monkeypatch.setattr(E, "_CEILING", {})
    E.lay_ceiling()
    E.lay_ceiling()
    writes = lambda: [a for a in calls if a[:2] == ["docker", "run"]]
    assert len(writes()) == 1 and writes()[0][-1] == str(12 * 2 ** 30)
    run.total = 8 * 2 ** 30                               # Docker given less memory, restarted under the server
    monkeypatch.setattr(E, "CEILING_RELAY_S", 0.0)
    E.lay_ceiling()
    assert writes()[-1][-1] == str(6 * 2 ** 30), "the old total written onto a smaller Docker"


def _cgroup(*script):
    return subprocess.run(["docker", "run", "--rm", "--network", "none", "--cap-drop", "ALL", "--cap-add",
                           "DAC_OVERRIDE", "--mount", "type=bind,src=/sys/fs/cgroup,dst=/cg", "-u", "0",
                           "--entrypoint", "sh", E.CEILING_IMAGE, "-c", *script], capture_output=True, text=True)


@live
def test_live_the_systems_containers_are_bounded_in_their_sum(monkeypatch):
    """Two containers each under its own bound, together over the ceiling: the kernel ends one, as it ends a runaway
    over its own bound — so a delivery that runs away in every batch of its validation stays inside the ceiling. In a
    group of the test's own under the machine's, which it removes."""
    group = f"{E.CEILING_GROUP}/live-test-{os.getpid()}"
    monkeypatch.setattr(E, "CEILING_GROUP", group)
    monkeypatch.setattr(E, "memory_ceiling", lambda total: 300 * 2 ** 20)
    monkeypatch.setattr(E, "_CEILING", {})
    flags, ids = E.ceiling(), []
    if not flags:
        pytest.skip("Docker's cgroups take no such group here (not cgroupfs v2)")
    try:
        E.lay_ceiling()
        assert flags == ["--cgroup-parent", f"/{group}"]
        assert _cgroup(f"cat /cg/{group}/memory.max").stdout.strip() == str(300 * 2 ** 20)
        eat = "python3 -c \"import time; b = b'x' * (200 * 2 ** 20); time.sleep(4)\""
        ids = [subprocess.run(["docker", "run", "-d", "--network", "none", "--memory", "256m", "--memory-swap", "256m",
                               *flags, IMAGE, "sh", "-c", eat], capture_output=True, text=True).stdout.strip()
               for _ in range(2)]
        codes = [subprocess.run(["docker", "wait", i], capture_output=True, text=True).stdout.strip() for i in ids]
        assert sorted(codes) == ["0", "137"], codes
    finally:
        subprocess.run(["docker", "rm", "-f", *ids], capture_output=True)
        _cgroup(f"rmdir /cg/{group}")


ID = lambda c: c * 64
MiB = 2 ** 20


def test_near_the_ceiling_the_work_furthest_over_its_share_is_ended_whatever_containers_it_runs_in():
    """The kernel at the group's max ends its largest process — an honest one beside a runaway spread thin (measured).
    Per container the same failed one level up (critic r2); so the unit is the node's work, every container of it, its
    share the ceiling over the works that hold anything (critic r3), and what counts is what no reclaim gives back: an
    honest writer's page cache fired the watch on its neighbour, a memfd runaway hid in the cache (critic r3)."""
    units = {ID("a"): "h|p|honest", ID("b"): "h|p|runaway", ID("c"): "h|p|runaway", ID("d"): "h|p|runaway",
             ID("e"): "h|p|idle"}
    row = lambda i, held, file=0, shmem=0: f"{i} {held + file - shmem} {file} {shmem}"
    read = lambda *rows: "\n".join(["1000000000", *rows])
    spread = read(row(".", 900 * MiB), row(ID("a"), 300 * MiB), *(row(ID(c), 200 * MiB) for c in "bcd"),
                  row(ID("e"), 1 * MiB))
    assert sorted(E._over_share(spread, lambda ids: units)) == [ID("b"), ID("c"), ID("d")]
    cache = read(row(".", 650 * MiB, file=500 * MiB), row(ID("a"), 650 * MiB), row(ID("b"), 0, file=500 * MiB))
    assert E._over_share(cache, lambda ids: units) == [], "page cache is given back: the kernel ends nobody, nor the watch"
    memfd = read(row(".", 900 * MiB, file=600 * MiB, shmem=600 * MiB), row(ID("a"), 300 * MiB),
                 row(ID("b"), 600 * MiB, file=600 * MiB, shmem=600 * MiB))
    assert E._over_share(memfd, lambda ids: units) == [ID("b")], "a memfd is memory, not cache"
    alone = read(row(".", 900 * MiB), row(ID("a"), 899 * MiB), *(row(ID(c), 1 * MiB) for c in "e"))
    assert E._over_share(alone, lambda ids: units) == [], "an honest heavy work beside idle ones holds the ceiling whole"
    assert E._over_share(read(row(".", 849 * MiB), row(ID("b"), 849 * MiB)), lambda ids: units) == [], "below 85%"
    assert E._over_share(read(row(".", 900 * MiB), "suite 900 0 0", row(ID("a"), 10 * MiB)), lambda ids: {}) == []
    assert E._over_share("max\n. 9 0 0", lambda ids: {}) == [] and E._over_share("", lambda ids: {}) == []


#: each case of the matrix: what the honest work runs, what the other runs in how many containers, and what must end
#: (a work's name) — the watch never ends what the kernel would spare, and ends a runaway before the kernel chooses
_GROW = "import time; xs = []\nwhile True: xs.append(bytearray(b'x' * 5 * 2 ** 20)); time.sleep(0.5)"
_MEMFD = ("import os, time; f = os.memfd_create('m')\nwhile True: os.write(f, b'x' * 5 * 2 ** 20); time.sleep(0.5)")
_HOLD = lambda mib: f"import time; b = b'x' * {mib} * 2 ** 20; time.sleep(40)"   # one allocation, all touched
_WRITE = ("import os, time\nwith open('/tmp/big', 'wb') as f:\n for _ in range(200): f.write(b'x' * 5 * 2 ** 20); "
          "f.flush(); os.fsync(f.fileno()); time.sleep(0.05)\ntime.sleep(10)")
MATRIX = {
    "anon runaway spread over three containers": (_HOLD(250), _GROW, 3, "runaway"),
    "memfd runaway": (_HOLD(250), _MEMFD, 1, "runaway"),
    "an honest writer's page cache": (_HOLD(300), _WRITE, 1, None),
    "an honest heavy work beside idle ones": (_HOLD(480), "import time; time.sleep(40)", 4, None),
}


@live
@pytest.mark.parametrize("case", list(MATRIX))
def test_live_near_the_ceiling_the_watch_ends_only_the_runaway(monkeypatch, case):
    honest, other, n, ended = MATRIX[case]
    group = f"{E.CEILING_GROUP}/watch-test-{os.getpid()}"
    monkeypatch.setattr(E, "CEILING_GROUP", group)
    monkeypatch.setattr(E, "CEILING_WATCH_S", 1.0)
    monkeypatch.setattr(E, "_CEILING", {"flags": ["--cgroup-parent", f"/{group}"]})
    reader, ids, stop = f"{group.replace('/', '-')}-ceiling-reader", [], E.threading.Event()
    if _cgroup(f"mkdir -p /cg/{group} && echo 600M > /cg/{group}/memory.max && "
               f"echo 0 > /cg/{group}/memory.swap.max").returncode:
        pytest.skip("Docker's cgroups take no such group here")

    def start(node, body):
        return subprocess.run(["docker", "run", "-d", "--network", "none", "--memory", "1g", "--memory-swap", "1g",
                               "--label", f"{E.HOME}=h", "--label", f"{E.PROJECT}=p", "--label", f"{E.NODE}={node}",
                               "--cgroup-parent", f"/{group}", IMAGE, "python3", "-c", body],
                              capture_output=True, text=True).stdout.strip()
    try:
        # …the watch up first, its reader standing, as for a server's life: started after the runaway, it lost the race
        (watch := E.threading.Thread(target=E._watch_ceiling, args=(stop,), daemon=True)).start()
        for _ in range(60):
            if subprocess.run(["docker", "exec", reader, "true"], capture_output=True).returncode == 0:
                break
            time.sleep(1)
        ids.append(start("honest", honest))
        time.sleep(3)
        ids += [start("runaway" if ended else f"other{k}", other) for k in range(n)]
        codes = [subprocess.run(["docker", "wait", i], capture_output=True, text=True, timeout=180).stdout.strip()
                 for i in ids]
        events = dict(x.split() for x in _cgroup(f"cat /cg/{group}/memory.events").stdout.splitlines() if x.strip())
        assert codes[0] == "0", f"the honest work was ended: {codes}, {events}"
        assert codes[1:] == (["137"] * n if ended else ["0"] * n), (codes, events)
        assert events["oom_kill"] == "0", f"the kernel chose, not the watch: {events}"
    finally:
        stop.set()
        watch.join(timeout=60)                  # …its turn ended: else it made its reader again after the removal
        subprocess.run(["docker", "rm", "-f", *ids, reader], capture_output=True)
        _cgroup(f"rmdir /cg/{group}")


def test_a_judges_build_the_watch_ended_is_asked_again_not_the_deliverys_fail(monkeypatch, tmp_path):
    """The watch ends the work furthest over its share, a judge's batches among them: ended so, a build read as the
    delivery's FAIL — a neighbour pressing on the ceiling steered another node's verdict (critic B6). Its own bound, or
    its own exit, still FAILs it."""
    (box := E.ContainerExecution.__new__(E.ContainerExecution)).container = "judge.b.b_1.batch1-x"
    box.shell, box.run = lambda: "sh", lambda *a, **k: subprocess.CompletedProcess(a, 137, "", "Killed")
    ex = SimpleNamespace(session=lambda at: box, files=SimpleNamespace(exists=lambda p: False))
    monkeypatch.setattr(E, "_WATCH_ENDED", {"judge.b.b_1.batch1-x"})
    with pytest.raises(S.Uncopied, match="memory watch"):
        S._build(tmp_path, "make", ex)
    monkeypatch.setattr(E, "_WATCH_ENDED", set())
    with pytest.raises(S.BuildFailed, match="exited 137"):
        S._build(tmp_path, "make", ex)
