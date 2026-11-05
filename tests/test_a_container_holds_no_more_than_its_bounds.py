"""Every container the system makes is bounded in memory and processes (`config.container_limits`): unbounded, one
judge's probe held 9 GiB of the Docker VM's 19.5 and starved every project on the machine and the host (series 3,
c_compiler, 2026-10-30; the author's charter: «по ошибке могут насрать соседу и вся система полетит»). A runaway dies
as its own failure, exit 137, and the session it ran in goes on.
"""
import contextlib
import inspect
import json
import os
import re
import shutil
import subprocess
import time
from pathlib import Path
from types import SimpleNamespace

import pytest

import gfso.adapters.execution as E
import gfso.adapters.snapshots as S
import gfso.adapters.worktrees as W
import gfso.observe as O
import gfso.sessions as SS
from gfso import config as C, issuer as I, tools as T
from gfso.core.types import Criteria, Mode, Probe, TaskId
from gfso.delegate import Dispatcher
from gfso.engine.parking import USERS_WAY
from tests.support import criterion, round_over
from tests.test_delegate import _agents, _eng, _goal, _node
from tests.test_the_mode_decides_who_holds_what import _admit, _engine, _kid
from tests.test_a_session_holds_only_its_own_place import IMAGE, made, project  # noqa: F401
from tests.test_the_system_reads_a_place_where_its_agent_cannot_lead_it_out import _docker
from tests.test_a_node_works_in_its_own_place import _repo

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
    assert src.count("*_SMALL") == 5 and f'"{chr(45)}{chr(45)}memory", f"{{DOOR_MEMORY_MB}}m"' in src, \
        "the door's, the gateway's, the ceiling's maker and its reader, the disk's readers of what nodes hold and what changed"


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
    critic over the bounds). The bound comes down only once the repository is made: a 137 in the test's own `git add` of
    that file could not be told from the checkout's (CI, 2026-11-04: 137 and nothing said)."""
    name = f"gfso-kept-test-{time.time_ns()}"
    prepare = ("set -e; mkdir /tmp/w && cd /tmp/w && git init -q && git config user.email t@t && git config user.name t; "
               "head -c 200000000 /dev/urandom > big; git add big; git commit -qm d; sync")
    script = ("set -e; cd /tmp/w; echo rewritten > big; c=$(git rev-parse HEAD); t=$(git rev-parse HEAD^{tree}); "
              'python3 -I -c "$S" kept /tmp/w "$c" "$t"; echo rc=$?; git cat-file blob HEAD:big | cmp -s - big && echo restored')
    in_it = lambda body: subprocess.run(["docker", "exec", "-e", f"S={S._CHECKOUT}", name, "sh", "-c", body],
                                        capture_output=True, text=True, timeout=300)
    try:
        subprocess.run(["docker", "run", "-d", "--name", name, "--memory", "1g", "--memory-swap", "1g", IMAGE, "sleep", "600"],
                       capture_output=True, check=True)
        ready = in_it(prepare)
        assert ready.returncode == 0, ("the test's preparation", ready.returncode, ready.stderr[-300:])
        subprocess.run(["docker", "update", "--memory", "128m", "--memory-swap", "128m", name], capture_output=True, check=True)
        got = in_it(script)
    finally:
        subprocess.run(["docker", "rm", "-f", name], capture_output=True)
    assert "rc=0" in got.stdout and "restored" in got.stdout, ("the checkout", got.returncode, got.stdout[-300:], got.stderr[-300:])


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
                               "--label", f"{E.HOME}={E._home()}", "--label", f"{E.PROJECT}=p", "--label", f"{E.NODE}={node}",
                               "--cgroup-parent", f"/{group}", IMAGE, "python3", "-c", body],
                              capture_output=True, text=True).stdout.strip()
    try:
        # …the reader standing before the runaway, as with the first work of a server: started after it, it lost the race
        (watch := E.threading.Thread(target=E._watch_ceiling, args=(stop,), daemon=True)).start()
        ids.append(start("honest", honest))
        for _ in range(60):
            if subprocess.run(["docker", "exec", reader, "true"], capture_output=True).returncode == 0:
                break
            time.sleep(1)
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


def test_live_the_reader_stands_only_while_work_does(monkeypatch):
    """An idle server holds no container: the author, on a Docker wiped clean, «кто такой busybox и почему он все еще работает».
    With work the reader stands, once, whether or not the group exists yet (it was removed and made again every turn, for
    ever, on any new installation); with the last of it, it goes."""
    group = f"{E.CEILING_GROUP}/no-such-group-{os.getpid()}"
    monkeypatch.setattr(E, "CEILING_GROUP", group)
    monkeypatch.setattr(E, "CEILING_WATCH_S", 1.0)
    monkeypatch.setattr(E, "_CEILING", {"flags": ["--cgroup-parent", f"/{group}"]})
    reader, stop, work = f"{group.replace('/', '-')}-ceiling-reader", E.threading.Event(), None
    inspect = lambda: subprocess.run(["docker", "inspect", "-f", "{{.Id}}", reader], capture_output=True, text=True).stdout.strip()
    theirs = subprocess.run(["docker", "ps", "-q", "--filter", f"label={E.HOME}"], capture_output=True, text=True).stdout.strip()
    if theirs:
        pytest.skip("other work stands on this machine")
    (watch := E.threading.Thread(target=E._watch_ceiling, args=(stop,), daemon=True)).start()
    try:
        time.sleep(3)
        assert not inspect(), "a reader stands with no work on the machine"
        work = subprocess.run(["docker", "run", "-d", "--network", "none", "--label", f"{E.HOME}=h", E.CEILING_IMAGE, "sleep", "60"],
                              capture_output=True, text=True).stdout.strip()
        for _ in range(30):
            if first := inspect():
                break
            time.sleep(1)
        time.sleep(5)
        assert first and inspect() == first, "the reader was made again"
        subprocess.run(["docker", "rm", "-f", work], capture_output=True)
        work = None
        for _ in range(30):
            if not inspect():
                break
            time.sleep(1)
        assert not inspect(), "the reader outlived the work"
    finally:
        stop.set()
        watch.join(timeout=60)
        subprocess.run(["docker", "rm", "-f", reader, *([work] if work else [])], capture_output=True)


def test_a_judges_build_the_watch_ended_is_asked_again_not_the_deliverys_fail(monkeypatch, tmp_path):
    """The watch ends the work furthest over its share, a judge's batches among them: ended so, a build read as the
    delivery's FAIL — a neighbour pressing on the ceiling steered another node's verdict (critic B6). Its own bound, or
    its own exit, still FAILs it."""
    (box := E.ContainerExecution.__new__(E.ContainerExecution)).container = "validator.b.b_1.batch1-x"
    box.shell, box.run = lambda: "sh", lambda *a, **k: subprocess.CompletedProcess(a, 137, "", "Killed")
    ex = SimpleNamespace(session=lambda at: box, files=SimpleNamespace(exists=lambda p: False))
    monkeypatch.setattr(E, "_WATCH_ENDED", {"validator.b.b_1.batch1-x"})
    with pytest.raises(S.Uncopied, match="memory watch"):
        S._build(tmp_path, "make", ex)
    monkeypatch.setattr(E, "_WATCH_ENDED", set())
    with pytest.raises(S.BuildFailed, match="exited 137"):
        S._build(tmp_path, "make", ex)


def test_a_node_is_charged_with_what_it_added_and_never_with_the_systems_own_writes(monkeypatch):
    """One node filling Docker's disk stopped every project on the machine: a work that added more than its own bound
    pays — not the largest, not who grew by a fall a neighbour made, not the root for its children's commits the system
    carried into the base (critic: a neighbour's delivery FAILed the root's judge), and nothing it wrote beside a system
    write is forgiven with it (critic: a mark every 10 s forgave a node everything)."""
    GiB, L = 2 ** 30, E.DiskLedger()
    root, judge = ("p", "root", "executor", "s"), ("p", "root", "validator", "r1")
    works = {root: {"dirs": {("v", "base")}, "layers": {"c1": (0, 0)}}, judge: {"dirs": {("v", "round")}, "layers": {}}}

    def read(base, round_=(0, 0)):
        L.begin()
        return L.added(works, {("v", "base"): base, ("v", "round"): round_})
    assert read((80 * GiB, 10 ** 6)) == {root: (0, 0), judge: (0, 0)}, "a first reading is the baseline"
    assert read((81 * GiB, 10 ** 6))[root] == (GiB, 0), "the root's own write"
    L.writing(("v", "base"), True)                      # …a child's commit carried into the base, 15 GiB
    assert read((95 * GiB, 10 ** 6))[root] == (GiB, 0), "a directory the system writes into keeps its last charge"
    L.wrote(("v", "base"), (81 * GiB, 10 ** 6), (96 * GiB, 10 ** 6))
    L.writing(("v", "base"), False)
    assert read((97 * GiB, 10 ** 6 + 5), (GiB, 3)) == {root: (2 * GiB, 5), judge: (GiB, 3)}, \
        "the system's 15 GiB taken out, the root's own writes beside it charged, its judge's apart"
    for _ in range(6):                                  # …a mark every reading forgives nothing of the node's own
        L.writing(("v", "base"), True)
        L.wrote(("v", "base"), (0, 0), (0, 0))
        L.writing(("v", "base"), False)
    assert read((107 * GiB, 10 ** 6 + 5), (GiB, 3))[root] == (12 * GiB, 5)
    L.writing(("v", "round"), True)
    L.wrote(("v", "round"), (GiB, 3), (0, 0))           # …the system removed the judge's copy
    L.writing(("v", "round"), False)
    L.writing(("v", "round"), True)
    L.wrote(("v", "round"), (0, 0), (5 * GiB, 9))      # …and made the next
    L.writing(("v", "round"), False)
    assert read((107 * GiB, 10 ** 6 + 5), (5 * GiB, 9))[judge] == (GiB, 3), "a removal banks no credit"
    assert read((107 * GiB, 10 ** 6 + 5), (6 * GiB, 9))[judge] == (2 * GiB, 3)
    L.wrote(("v", "new"), (0, 0), (GiB, 4))            # …a directory the system made, as it left it
    works[root]["dirs"].add(("v", "new"))
    L.begin()
    assert L.added(works, {("v", "base"): (107 * GiB, 10 ** 6 + 5), ("v", "round"): (6 * GiB, 9),
                           ("v", "new"): (3 * GiB, 4)})[root] == (14 * GiB, 5), \
        "what a node writes into a directory the system made is counted from the system's hand-over"
    works[root]["layers"]["c2"] = (2 * GiB, 9)
    assert read((107 * GiB, 10 ** 6 + 5), (6 * GiB, 9))[root] == (16 * GiB, 14), \
        "a container made since the first reading: its layer counted from nothing"
    assert read((90 * GiB, 10 ** 6 + 5), (6 * GiB, 9))[root] == (4 * GiB, 14), \
        "what it deleted of what stood before is no credit against what it writes elsewhere"
    bound, running = (20 * GiB, 10 ** 6), {("p", "filler", "executor", "f"), root}
    assert E._past_bound({("p", "filler", "executor", "f"): (21 * GiB, 1), root: (3 * GiB, 5)}, running, bound) == \
        [("p", "filler", "executor", "f")]
    assert E._past_bound({root: (GiB, 2 * 10 ** 6)}, running, bound) == [root], "files count as bytes do"
    assert E._past_bound({("p", "x", "validator", "r"): (99 * GiB, 1)}, running, bound) == [], "no container of it runs"
    monkeypatch.setenv("GFSO_NODE_DISK", "5g")
    monkeypatch.setenv("GFSO_NODE_FILES", "nope")
    assert C.node_disk() == (5 * GiB, C.NODE_FILES)
    assert E._bytes("12.3MB (virtual 1.2GB)") == 12_300_000 and E._bytes("") == 0


def test_a_judges_build_its_disk_bound_ended_fails_the_delivery_with_its_cause(monkeypatch, tmp_path):
    (box := E.ContainerExecution.__new__(E.ContainerExecution)).container = "validator.b.r1-x"
    box.shell, box.run = lambda: "sh", lambda *a, **k: subprocess.CompletedProcess(a, 137, "", "Killed")
    ex = SimpleNamespace(session=lambda at: box, files=SimpleNamespace(exists=lambda p: False))
    monkeypatch.setattr(E, "_DISK_ENDED", {"validator.b.r1-x": "node b's work added 30 MiB … (GFSO_NODE_DISK, GFSO_NODE_FILES)"})
    with pytest.raises(S.BuildFailed, match="ended: node b's work added .*GFSO_NODE_DISK"):
        S._build(tmp_path, "make", ex)


def _labelled(home, node, role="executor"):
    return ["--label", f"{E.HOME}={home}", "--label", f"{E.PROJECT}=p", "--label", f"{E.NODE}={node}",
            "--label", f"{E.ROLE}={role}"]


@live
def test_live_each_node_past_its_disk_bound_is_ended_wherever_it_wrote_and_none_else(monkeypatch):
    """The probe matrix: a filler in a node's temp, in its CLI state's volume, in its container's own layer, and one
    making files rather than bytes — each ended past its own bound, its layer gone; an honest node holding more than any
    filler but adding nothing, an honest node writing under its bound, and a filler of another installation, all left
    running."""
    pid = os.getpid()
    home, other, vol, state = f"critdisk{pid}", f"critdisk{pid}b", f"critdisk{pid}-v", f"critdisk{pid}-state"
    monkeypatch.setenv("GFSO_NODE_DISK", "300m")
    monkeypatch.setenv("GFSO_NODE_FILES", "3000")
    monkeypatch.setattr(E, "LAYER_STEP", 1)                 # …a layer's paths counted at every growth here
    sh = ["docker", "run", "--rm", "--network", "none", "--entrypoint", "sh"]
    grow = "i=0; while [ $i -lt 12 ]; do head -c 50000000 /dev/zero > {at}/f$i; i=$((i+1)); sleep 1; done; sleep 600"
    many = "mkdir {at}/m && cd {at}/m && i=0; while [ $i -lt 6000 ]; do : > f$i; i=$((i+1)); done; sleep 600"
    under = "head -c 100000000 /dev/zero > {at}/build; sleep 600"

    def start(h, node, mount, body, role="executor"):
        return subprocess.run(["docker", "run", "-d", "--network", "none", *_labelled(h, node, role), *mount,
                               "--entrypoint", "sh", IMAGE, "-c", body], capture_output=True, text=True,
                              check=True).stdout.strip()[:12]

    def sub(v, s):
        return ["--mount", f"type=volume,src={v},dst=/w,volume-subpath={s}"]

    gone = lambda i: subprocess.run(["docker", "inspect", i], capture_output=True).returncode != 0
    stop, ids, watch = E.threading.Event(), {}, None
    try:
        subprocess.run([*sh, "-u", "0", "-v", f"{vol}:/v", "-v", f"{state}:/s", IMAGE, "-c",
                        "mkdir -p /v/root /v/h /v/x /v/dn /v/zz /v/qq /v/j/b1 /v/j/b2 /v/.gfso-tmp/node-a /v/.gfso-tmp/node-o /v/n /s/+b && "
                        "chmod -R 777 /v /s && head -c 600000000 /dev/zero > /v/root/large"],
                       capture_output=True, check=True, timeout=300)
        ledger = E.DiskLedger()       # …each directory as the system left it when it made it (`Volume.writes`)
        for v, subs in ((vol, ["root", "h", "x", "dn", "zz", "qq", "j/b1", "j/b2", ".gfso-tmp/node-a", ".gfso-tmp/node-o", "n"]), (state, ["+b"])):
            for k, held in E._read(v, subs, IMAGE).items():
                ledger.wrote(k, (0, 0), held)
        (watch := E.threading.Thread(target=E._watch_disk, args=(stop, 2.0, home, ledger), daemon=True)).start()
        while not ledger.read:          # …its first reading made: every container below is made since, its layer new
            time.sleep(0.5)
        for h, node, mount, body in ((home, "root", sub(vol, "root"), "sleep 600"),
                                     (home, "honest", sub(vol, "h"), under.format(at="/w")),
                                     (other, "o", sub(vol, ".gfso-tmp/node-o"), grow.format(at="/w")),
                                     (home, "a", sub(vol, ".gfso-tmp/node-a"), grow.format(at="/w")),
                                     (home, "b", sub(state, "+b"), grow.format(at="/w")),
                                     (home, "c", [], grow.format(at="/tmp")),
                                     (home, "n", sub(vol, "n"), many.format(at="/w")),
                                     (home, "e", [], many.format(at="/tmp")),
                                     (home, "x", sub(vol, "x"), "mkdir /w/h && chmod 700 /w/h && "    # …hidden from a reader
                                      "head -c 400000000 /dev/zero > /w/h/big; sleep 600"),
                                     (home, "d", sub(vol, "dn"), "cd /w && mkdir x && head -c 400000000 /dev/zero > x/big"
                                      " && i=0; while [ $i -lt 40 ]; do mkdir t && mv x t/$(printf %0200d $i) && mv t x;"
                                      " i=$((i+1)); done; sleep 600"),     # …hidden past the path-length limit
                                     (home, "z", sub(vol, "zz"), "mkdir /w/l && chmod 000 /w/l && "    # …unreadable
                                      "head -c 400000000 /dev/zero > /w/big; sleep 600"),
                                     (home, "q", sub(vol, "qq"), "cd /w && mkdir x && i=0; while [ $i -lt 4200 ]; do "
                                      "mkdir t && mv x t/x && mv t x; i=$((i+1)); done; sleep 600")):     # …deeper than the system reads
            ids[node] = start(h, node, mount, body)
        for batch in ("b1", "b2"):        # …one validation's two batches, each under the bound, over it together
            ids[batch] = start(home, "j", sub(vol, f"j/{batch}"), "head -c 200000000 /dev/zero > /w/build; sleep 600", "validator")
        for _ in range(60):
            if all(gone(ids[n]) for n in "abcnexdzq"):
                break
            time.sleep(2)
        assert {n: gone(ids[n]) for n in "abcnexdzq"} == dict.fromkeys("abcnexdzq", True), "a node past its bound was not ended"
        ledger.writing((vol, "root"), True)      # …the system's own write into the root's base: a child's carried commit
        before = E._read(vol, ["root"], IMAGE)[(vol, "root")]
        subprocess.run([*sh, "-u", "0", "-v", f"{vol}:/v", IMAGE, "-c", "head -c 600000000 /dev/zero > /v/root/carried"],
                       capture_output=True, check=True, timeout=300)
        ledger.wrote((vol, "root"), before, E._read(vol, ["root"], IMAGE)[(vol, "root")])
        ledger.writing((vol, "root"), False)
        time.sleep(8)
        alive = subprocess.run(["docker", "inspect", "-f", "{{.State.Running}}", ids["root"], ids["honest"], ids["o"],
                                ids["b1"], ids["b2"]],
                               capture_output=True, text=True).stdout.split()
        assert alive == ["true"] * 5, alive
        assert E._DISK_ENDED and all("GFSO_NODE_DISK" in w or "cannot read" in w for w in E._DISK_ENDED.values()), E._DISK_ENDED
    finally:
        stop.set()
        if watch:
            watch.join(timeout=120)
        subprocess.run(["docker", "rm", "-f", *ids.values()], capture_output=True)
        subprocess.run(["docker", "volume", "rm", "-f", vol, state], capture_output=True)


def test_a_carry_marks_both_temps_its_bundle_passes_through_as_the_systems(tmp_path, monkeypatch):
    """The bundle a carry makes lies in the source's temp, then in the target's — each a node's own mounted directory: a
    reading inside the carry charged them with it (engineering, signing the JOINT). Both are the system's writes."""
    seen, held = [], W._held
    monkeypatch.setattr(W, "_held", lambda ex, p: (seen.append(str(p)), held(ex, p))[1])
    base = _repo(tmp_path / "ws")
    W.ensure(base, tmp_path / "place", "gfso/p/a", base)
    (tmp_path / "place" / "a.py").write_text("x = 1\n")
    W.commit_all(base, tmp_path / "place", "d", "e", branch="gfso/p/a")
    temp = E.LocalExecution().temp_of(str(tmp_path / "place"))
    assert seen.count(str(temp)) == 2, ("the source's temp and the target's, each marked", seen)
    assert str(base) in seen and str(tmp_path / "place") in seen


def test_the_systems_writes_into_one_directory_are_measured_once_and_an_unread_one_is_unknown(monkeypatch):
    """A write nested in another (a bring's carry) or beside it (two joins into one parent) measured twice banked
    credit, and a reading that failed was taken for an empty directory and charged a node with its whole place (critic):
    one measurement per span of the system's writes, and an unread side is unknown — the charge stands, the baseline is
    taken again at the next reading."""
    held, reads = {"now": (10, 1)}, []

    def read(vol, subs, image=None):
        reads.append(subs[0])
        if held["now"] is None:
            raise OSError("not read")
        return {(vol, subs[0]): held["now"]}
    L, v = E.DiskLedger(), E.Volume.__new__(E.Volume)
    v.image = None
    monkeypatch.setattr(E, "_LEDGER", L)
    monkeypatch.setattr(E, "_read", read)
    monkeypatch.setattr(E.Volume, "mount", lambda self, root, ro, dst: ["--mount", f"type=volume,src=vol,dst={dst},"
                                                                              f"volume-subpath={root}"])
    L.wrote(("vol", "p"), (0, 0), (10, 1))
    with v.writes("p"):
        with v.writes("p"):                              # …nested
            held["now"] = (30, 2)
    assert reads == ["p", "p"] and L.system[("vol", "p")] == (20, 1), (reads, L.system)
    other = v.writes("p")                                # …held open: a collected one would end its span
    t = E.threading.Thread(target=other.__enter__)
    with v.writes("p"):                                  # …and beside another, from another thread
        t.start()
        t.join()
        held["now"] = (50, 3)
    assert len(reads) == 3 and L.busy == {("vol", "p"): 1}, "the other's span still open: measured when it ends"
    L.busy.clear()
    held["now"] = None                                   # …a reading that does not finish
    with v.writes("p"):
        pass
    assert ("vol", "p") in L.lost and L.busy == {}
    works = {("p", "n", "executor", "s"): {"dirs": {("vol", "p")}, "layers": {}}}
    L.charged[("vol", "p")] = (5, 0)
    L.begin()
    assert L.added(works, {("vol", "p"): (99, 9)})[("p", "n", "executor", "s")] == (5, 0), \
        "the charge stands across a write that was not measured"
    L.begin()
    assert L.added(works, {("vol", "p"): (101, 9)})[("p", "n", "executor", "s")] == (7, 0)


def test_a_removed_copy_takes_off_only_what_the_system_put_there(monkeypatch):
    """Each exact check copies the built delivery into the system's scratch, writes there, and the copy is removed:
    booked as the measured removal, every check was charged with the outputs of all the checks before it (critic: 30
    checks of 1 GiB → 30 GiB on a directory back at its baseline). What the system put there comes off, and what the
    check wrote leaves what the directory holds by itself."""
    GiB, held = 2 ** 30, {"now": (0, 0)}
    L, v = E.DiskLedger(), E.Volume.__new__(E.Volume)
    v.image = None
    monkeypatch.setattr(E, "_LEDGER", L)
    monkeypatch.setattr(E, "_read", lambda vol, subs, image=None: {(vol, subs[0]): held["now"]})
    monkeypatch.setattr(E.Volume, "mount", lambda self, root, ro, dst: ["--mount", f"type=volume,src=vol,dst={dst},"
                                                                              f"volume-subpath={root}"])
    works = {("p", "x", "check", "c"): {"dirs": {("vol", "sys")}, "layers": {}}}
    L.wrote(("vol", "sys"), (0, 0), (0, 0))
    for i in range(30):
        with v.writes(E.Path("sys"), E.Path("sys") / f"run{i}"):
            held["now"] = (GiB, 1)                       # …the copy
        held["now"] = (2 * GiB, 2)                       # …what the check wrote
        L.begin()
        assert L.added(works, {("vol", "sys"): held["now"]})[("p", "x", "check", "c")] == (GiB, 1)
        with v.writes(E.Path("sys"), E.Path("sys") / f"run{i}", removing=True):
            held["now"] = (0, 0)
        L.begin()
        assert L.added(works, {("vol", "sys"): held["now"]})[("p", "x", "check", "c")] == (0, 0), i


def test_a_directory_that_outruns_its_reading_time_again_and_again_ends_its_work(monkeypatch):
    """Unread, a directory's charge stood frozen below the bound for good, and a node that kept its directory slow to
    walk kept it so (critic): read past its time `DISK_SLOW_READS` times in a row, its work is ended for it; one good
    reading between starts the count again, and a reader that cannot read at all (no GNU find there) is no such count."""
    said = {"out": "T 0 /v/p"}
    monkeypatch.setattr(E, "run", lambda *a, **k: subprocess.CompletedProcess(a, 0, said["out"], ""))
    monkeypatch.setattr(E, "_SLOW", {})
    for n in (1, 2):
        assert E._read("vol", ["p", "q"]) == {} and E._SLOW == {("vol", "p"): n}
    said["out"] = "4096 1 /v/p"
    assert E._read("vol", ["p", "q"]) == {("vol", "p"): (4096, 1)} and E._SLOW == {}
    said["out"] = "N 0 /v/p"
    E._read("vol", ["p", "q"])
    assert E._SLOW == {}, "a reader that cannot read at all is no slowness of the node's"


def test_a_directory_whose_walk_keeps_failing_ends_its_work_as_a_slow_one_does(monkeypatch):
    """A failed walk froze the charge as an outrun one did, with no count: on the Linux runner a node's nest answered
    "could not read" at every reading of the wait and stayed running, past any bound it wrote to."""
    said = {"out": "U 0 /v/p"}
    monkeypatch.setattr(E, "run", lambda *a, **k: subprocess.CompletedProcess(a, 0, said["out"], ""))
    monkeypatch.setattr(E, "_SLOW", {})
    for n in (1, 2, 3):
        assert E._read("vol", ["p", "q"]) == {} and E._SLOW == {("vol", "p"): n}
    assert E._SLOW[("vol", "p")] >= E.DISK_SLOW_READS, "the count the watch ends a work at"
    said["out"] = "4096 1 /v/p"
    assert E._read("vol", ["p", "q"]) == {("vol", "p"): (4096, 1)} and E._SLOW == {}, "one good reading starts it again"


@pytest.mark.skipif(not shutil.which("sh"), reason="the reader's script is a POSIX shell's")
@pytest.mark.parametrize("find, said", [("exit 1", "N"),                                       # …no GNU find at all
                                        ('case "$*" in *-maxdepth*) exit 0;; esac; exit 1', "U")])  # …its walk failed
def test_the_reader_tells_a_find_that_cannot_read_from_a_walk_that_failed(tmp_path, find, said):
    """Told apart, or an image with no GNU find would have every node in it ended as unreadable."""
    (tmp_path / "bin").mkdir()
    (tmp_path / "bin" / "find").write_text(f"#!/bin/sh\n{find}\n", newline="\n")
    (tmp_path / "bin" / "find").chmod(0o755)
    (tmp_path / "d").mkdir()
    got = subprocess.run(["sh", "-c", 'PATH="./bin:$PATH"; ' + E._HELD, "sh", "4097", "5", "d"], cwd=tmp_path,
                         capture_output=True, text=True)
    assert got.stdout.split() == [said, "0", "d"], got.stdout + got.stderr


@pytest.mark.skipif(not shutil.which("sh"), reason="the reader's script is a POSIX shell's")
@pytest.mark.parametrize("error, said", [("No such file or directory", "8192"),   # …a parallel build's temp: no stop
                                         ("Permission denied", "U"), ("File name too long", "U")])  # …a walk that failed
def test_a_file_gone_during_the_walk_is_a_reading_and_any_other_failure_is_not(tmp_path, error, said):
    """A critic's churn answered `U` in 29% of its readings, and three in a row end a node: an honest build's vanishing
    temp files must not, while a nest that fails the walk must."""
    (tmp_path / "bin").mkdir()
    (tmp_path / "bin" / "find").write_text(
        '#!/bin/sh\ncase "$*" in *-maxdepth*|*-mindepth*) exit 0;; esac\n'
        f"echo '1 1 8'; echo '2 1 8'; echo \"find: 'x': {error}\" >&2; exit 1\n", newline="\n")
    (tmp_path / "bin" / "find").chmod(0o755)
    (tmp_path / "d").mkdir()
    got = subprocess.run(["sh", "-c", 'PATH="./bin:$PATH"; ' + E._HELD, "sh", "4097", "5", "d"], cwd=tmp_path,
                         capture_output=True, text=True)
    assert got.stdout.split()[0] == said, got.stdout + got.stderr
    if said != "U":
        assert got.stdout.split() == ["8192", "2", "d"], "no error line is read as an entry"


@pytest.mark.skipif(not shutil.which("sh"), reason="the reader's script is a POSIX shell's")
def test_the_reader_reads_a_real_tree_and_finds_a_real_nest(tmp_path):
    """The script itself, under the real `find`: every test above it feeds `_read` the script's answer."""
    (tmp_path / "d" / "a" / "b").mkdir(parents=True)
    (tmp_path / "d" / "a" / "b" / "f").write_bytes(b"x" * 5000)

    def read(depth):
        return subprocess.run(["sh", "-c", E._HELD, "sh", str(depth), "5", "d"], cwd=tmp_path, capture_output=True,
                              text=True).stdout.split()
    assert read(3) == ["D", "0", "d"], "a nest as deep as the bound"
    held = read(4097)
    assert held[0].isdigit() and held[1:] == ["4", "d"], held          # …three directories and the file, read whole


def test_a_whole_volume_outrun_counts_for_each_of_its_directories_and_a_nest_read_whole_is_cleared(monkeypatch):
    """Each directory outrunning its time alone was counted, but a volume outrun as a whole left every charge frozen
    with no count (critic); and a place once found too deep stayed so after its nest was gone (critic)."""
    def late(*a, **k):
        raise subprocess.TimeoutExpired("docker", 1)
    monkeypatch.setattr(E, "_SLOW", {})
    monkeypatch.setattr(E, "_TOO_DEEP", {("vol", "p")})
    monkeypatch.setattr(E, "_read", late)
    works = {("p", "n", "executor", "s"): {"dirs": {("vol", "p"), ("vol", "q")}, "layers": {}, "image": None}}
    assert E._disk_read(works) == {} and E._SLOW == {("vol", "p"): 1, ("vol", "q"): 1}
    monkeypatch.undo()
    monkeypatch.setattr(E, "_SLOW", {})
    monkeypatch.setattr(E, "_TOO_DEEP", {("vol", "p")})
    monkeypatch.setattr(E, "run", lambda *a, **k: subprocess.CompletedProcess(a, 0, "4096 1 /v/p", ""))
    E._read("vol", ["p"])
    assert E._TOO_DEEP == set()


def test_an_executor_ended_past_its_disk_bound_is_said_once_by_its_place(monkeypatch):
    """The executor's path saw only a cut: the watch's cause is read there by the session's place, every container of
    it, and taken off once said — the place's next session runs in containers of the same names."""
    (box := E.ContainerExecution.__new__(E.ContainerExecution)).container = "executor.a-f40103"
    monkeypatch.setattr(E, "_DISK_ENDED", {"executor.a-f40103-client": "past", "executor.a-f40103-client-commands":
                                           "past", "executor.a-f40103x": "a neighbour's", "validator.a.r1-x": "its judge's"})
    assert E.ended_past_disk(box) == "past"
    assert E.ended_past_disk(box) is None, "said once: an older end is not the place's next session's"
    assert set(E._DISK_ENDED) == {"executor.a-f40103x", "validator.a.r1-x"}, "no other place's cause taken with it"
    assert E.ended_past_disk(SimpleNamespace(container="executor.a-f40103x")) is None, "a host session: none"


def test_a_node_whose_executor_its_disk_bound_ended_is_parked_at_once_with_its_cause_and_the_move_that_lifts_it(
        tmp_path):
    """Its next session in the same place is ended again within seconds: four redials and a retry were spent on that,
    then the node parked as «stopped twice without a signal» with `revise` and `reassign` offered — each a session in
    the same place, ended again. Parked at once, the cause said to the issuer, CANCEL offered; the control, a cut with
    no such cause, is still redialled."""
    why = "the directories of its place hold 21000 MiB and 3 files its work added, past its bound (GFSO_NODE_DISK, …)"
    for past in (why, None):
        e = _eng()
        agents = _agents(tmp_path, ("exec-1", "llm-executor"))
        tries, said = [], []
        e.emit_info = lambda src, msg, _s=said: _s.append(msg)
        d = Dispatcher(e, agents, poll=30, runner=lambda en, tid, ex, ag, _p=past: tries.append(1) or
                       {"task_id": str(tid), "status": "unparsed", "cut": True, "past_disk": _p})
        _goal(e, assignee="agent")
        _node(e, "n1", assignee="exec-1", parent="goal")
        d.dispatch_once()
        round_over(d, "n1", lambda: len(tries) >= 1)
        parked = "n1" in e.parking.parked_executions()
        assert parked == bool(past), (past, said)
        if past:
            assert any(why in m and "PARKED" in m for m in said) and not any("redialled" in m for m in said), said
            step = next(s for s in T.next_steps(e, actor="agent")["steps"] if s["task_id"] == "n1")
            assert step["mine"] and why in step["directive"] and "CANCEL" in step["directive"]
            assert "revise(" not in step["directive"] and "reassign(" not in step["directive"], step["directive"]
            T.revise(e, "n1", agent="agent", max_iterations=5)
            assert "n1" not in e.parking.parked_executions(), "a new version lifts the park, as any park"
        else:
            assert any("redialled" in m for m in said), said
        e.stop()


def test_under_auto_a_node_its_disk_bound_ended_is_asked_with_its_cause_and_cancel_alone():
    """The machine issuer read its own «parked» question — «twice ended without any signal», `reassign` offered — and
    never the cause, so it could reassign into the same place, ended again (engineering over the JOINT). The cause in
    its question and `cancel` its one move; at an AUTO root, where cancelling is the user's, the run waits for the user,
    told why; the control, a park with no cause, keeps its question and moves."""
    why = "the directories of its place hold 21000 MiB and 3 files its work added, past its bound (GFSO_NODE_DISK, …)"
    e = _engine(Mode.AUTO)
    T.TOOLS["create_task"](e, "root", {"description": "the goal", "criteria": [criterion("g", "G holds")]})
    _admit(e, "root", _kid("root.part", ["g"], criterion("k", "K holds")))
    root, part = e.graph.get_task(TaskId("root")), e.graph.get_task(TaskId("root.part"))
    e.parking.park_execution(part.id)
    assert I.moves_for(e, part, "parked") == ("reassign", "cancel")
    assert "twice ended without any signal" in I.issuer_context(e, part.id, "parked")
    e.parking.park_execution(part.id, why)
    assert I.moves_for(e, part, "parked") == ("cancel",)
    asked = I.issuer_context(e, part.id, "parked")
    assert why in asked and "is ended again" in asked and "twice ended" not in asked, asked
    e.parking.park_execution(root.id, why)
    assert I.moves_for(e, root, "parked") == ()
    out = I.settle(e, None, root.id, "parked", str(e.graph.issuer_of(root.id)), None)
    assert out["status"] == "users" and why in out["why"] and "start_project" in out["why"], out
    assert e.paused(), "the run waits for the user"


def test_laying_a_checks_inputs_spends_none_of_the_observations_time(monkeypatch, tmp_path):
    """Laying each check's inputs is the system's own write, measured twice for the disk's watch (~0.5–1.5 s): counted in
    the observation's budget, it left a rich contract's later checks unrun, the judge's word deciding them — as the copy
    did, which is already not counted."""
    monkeypatch.setattr(O, "materialize_inputs", lambda *a: (time.sleep(0.4), {})[1])
    monkeypatch.setattr(O, "_run", lambda *a: {"rc": 0, "out": "ok", "stdout": "ok", "stderr": ""})
    monkeypatch.setattr(O, "ended_by_watch", lambda ex: False)
    ex = SimpleNamespace(shell=lambda: "sh", release=lambda tree: None, copy_tree=lambda a, b: None,
                         system_writes=lambda p, **k: contextlib.nullcontext(), files=None, remove_tree=lambda p: None,
                         scratch=lambda *a, **k: contextlib.nullcontext(str(tmp_path)),
                         session=lambda p: None)
    c = Criteria(name="c", check=tuple(Probe(behaviour=f"b{i}", command=f"echo {i}", expect="ok") for i in range(5)))
    rows = O.run_checks(ex, [("k", c, p) for p in c.check], str(tmp_path), str(tmp_path), 1.5)
    assert [r.get("note") for _, r in rows] == [None] * 5, rows


def test_a_place_is_past_its_bound_by_its_own_directories_now_never_by_its_layer_nor_an_end_remembered(monkeypatch):
    """What parks a node is its place's directories — they outlive its sessions — holding more than its bound by the
    ledger as it stands: a container's own layer goes with it, and a session ended for what its layer held left the next
    one free (critic: parked at once with cancel alone, a node a retry would carry was thrown away); an end never read
    named an ordinary cut later (critic) — the record now, not the event, decides."""
    GiB = 2 ** 30
    ex = E.PlaceContainer.__new__(E.PlaceContainer)
    ex._mounts = lambda: [(Path("place"), False), (Path("base"), True), (Path("temp"), False)]
    ex.state, ex.volume = Path("state"), SimpleNamespace(key=lambda d: ("v", d.name))
    monkeypatch.setattr(E, "_LEDGER", L := E.DiskLedger())
    monkeypatch.setattr(E, "_DISK_ENDED", {})
    monkeypatch.setenv("GFSO_NODE_DISK", "20g")
    L.charged = {("v", "base"): (99 * GiB, 0), "c1": (99 * GiB, 0), ("v", "place"): (12 * GiB, 0),
                 ("v", "temp"): (5 * GiB, 0), ("v", "state"): (2 * GiB, 0)}
    assert E.place_past_disk(ex) is None, "a read-only directory and a container's layer are no part of the place's"
    L.charged[("v", "temp")] = (7 * GiB, 0)
    assert "21504 MiB" in (E.place_past_disk(ex) or ""), "its writable directories and its CLI state, summed"
    assert E.place_past_disk(SimpleNamespace()) is None, "a host session: none"


def test_the_issuers_step_at_a_root_its_disk_bound_parked_says_cancelling_abandons_the_goal():
    """A root has no parent: «its parent's split can issue the work anew» offered a CANCEL that abandons the goal
    (critic). Its step says so, and the user's own way — a restart counts the place again."""
    why = "the directories of its place hold 21000 MiB and 3 files its work added, past its bound"
    e = _engine(Mode.SOLO)
    T.TOOLS["create_task"](e, "root", {"description": "the goal", "criteria": [criterion("g", "G holds")]})
    _admit(e, "root", _kid("root.part", ["g"], criterion("k", "K holds")))
    for node, says in (("root", "abandons the goal"), ("root.part", "its parent's split can issue")):
        e.parking.park_execution(TaskId(node), why)
        step = next(s for s in T.next_steps(e, actor="agent")["steps"] if s["task_id"] == node)
        assert why in step["directive"] and says in step["directive"] and "restart" in step["directive"], step


def test_where_only_the_user_lifts_a_place_past_its_bound_no_system_move_is_offered_and_their_way_is_said():
    """At an AUTO root the step offered CANCEL «made without you» while the machine issuer, offered nothing, stopped the
    run telling the user to restart — two texts at odds (critic); a part of the user's own plan was cancelled with «only
    the user re-plans it», the restart never named (critic). Both are the user's: one predicate, one sentence."""
    why = "the directories of its place hold 21000 MiB and 3 files its work added, past its bound"
    e = _engine(Mode.AUTO)
    T.TOOLS["create_task"](e, "root", {"description": "the goal", "criteria": [criterion("g", "G holds")]})
    _admit(e, "root", _kid("root.part", ["g"], criterion("k", "K holds")))
    root, part = e.graph.get_task(TaskId("root")), e.graph.get_task(TaskId("root.part"))
    e.parking.park_execution(root.id, why)
    step = next(s for s in T.next_steps(e, actor="agent")["steps"] if s["task_id"] == "root")
    assert USERS_WAY in step["directive"] and "CANCEL" not in step["directive"], step["directive"]
    e.parking.park_execution(part.id, why)
    assert I.moves_for(e, part, "parked") == ("cancel",), "below the root of the system's own plan: cancel"
    e.give_users_plan(root.id)
    assert I.moves_for(e, part, "parked") == (), "a part of the plan the user handed in is not the system's to cut"
    out = I.settle(e, None, part.id, "parked", str(e.graph.issuer_of(part.id)), None)
    assert out["status"] == "users" and USERS_WAY in out["why"], out


def test_a_plain_park_whose_last_end_was_the_disks_watch_says_it_and_keeps_its_moves(tmp_path, monkeypatch):
    """A place just under its bound: each session ended after what little the place leaves, each a plain cut, the node
    parked «stopped twice» with the cause lost (critic). The plain park keeps its moves — a narrower contract may fit
    what is left — and says what ended it; an end nobody read is cleared when a session starts (critic)."""
    e = _eng()
    agents = _agents(tmp_path, ("exec-1", "llm-executor"))
    tries = []
    d = Dispatcher(e, agents, poll=30, runner=lambda en, tid, ex, ag: tries.append(1) or
                   {"task_id": str(tid), "status": "unparsed", "past_disk": None, "disk_ended": "LAST-END"})
    _goal(e, assignee="agent")
    _node(e, "n1", assignee="exec-1", parent="goal")
    for want in (1, 2):
        d.dispatch_once()
        round_over(d, "n1", lambda: len(tries) >= want)
    assert "n1" in e.parking.parked_executions()
    step = next(s for s in T.next_steps(e, actor="agent")["steps"] if s["task_id"] == "n1")
    assert "STOPPED WITHOUT A SIGNAL" in step["directive"] and "ended by the disk's watch: LAST-END" in step["directive"]
    assert "revise(" in step["directive"], "its moves kept"
    e.stop()
    (box := E.PlaceContainer.__new__(E.PlaceContainer)).container = "executor.n1-ab"
    monkeypatch.setattr(E, "_DISK_ENDED", {"executor.n1-ab-client": "OLD"})
    monkeypatch.setattr(SS, "execution_of", lambda engine, agents=None: SimpleNamespace(session=lambda cwd: box))
    SS._fresh_disk(None, None, "/w")
    assert not E._DISK_ENDED, "an unread end is not the next session's"


def test_a_parents_consent_in_a_place_past_its_bound_parks_it_at_once_with_the_cause(tmp_path):
    """A revised parent consents in its own place: past its bound there, the consent was ended twice and the node
    parked with no cause, `revise` offered again (critic) — parked at once with it, as its executor's round is."""
    why = "the directories of its place hold 21000 MiB and 3 files its work added, past its bound"
    for past in (why, None):
        e = _eng()
        d = Dispatcher(e, _agents(tmp_path, ("exec-1", "llm-executor")), poll=30, runner=lambda *a: None,
                       consent_runner=lambda *a, _p=past: {"status": "unparsed", "past_disk": _p})
        _goal(e, assignee="agent")
        _node(e, "n1", assignee="exec-1", parent="goal")
        d._consent_guarded(TaskId("n1"), "exec-1")
        assert ("n1" in e.parking.parked_executions()) == bool(past), past
        assert e.parking.execution_park_reason(e.graph.get_task(TaskId("n1"))) == past
        e.stop()


def test_a_node_past_its_disk_bound_whose_contracts_ran_out_is_told_to_cancel_not_to_write_another(monkeypatch):
    """Its contracts spent, the machine issuer was told «a next contract that changes what failed, or cancel» — a next
    contract runs in the same place and is ended again; cancelling is its one move (critic)."""
    e = _engine(Mode.AUTO)
    T.TOOLS["create_task"](e, "root", {"description": "the goal", "criteria": [criterion("g", "G holds")]})
    _admit(e, "root", _kid("root.part", ["g"], criterion("k", "K holds")))
    part, told = e.graph.get_task(TaskId("root.part")), []
    monkeypatch.setattr(I, "extensions_spent", lambda *a: True)
    monkeypatch.setattr(I, "issuer_turn", lambda *a, refusal="", **k: told.append(refusal) or {"status": "applied"})
    for why, says in (("past its bound", "no next contract runs there: `cancel`"), (None, "Decide: a next contract")):
        e.parking.park_execution(part.id, why)
        I.settle(e, None, part.id, "parked", str(e.graph.issuer_of(part.id)), None)
        assert says in told[-1], told[-1]
