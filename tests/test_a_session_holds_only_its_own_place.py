"""A session runs in a container of its own place: it writes its place alone, reads the base, and never sees another
node's place nor the system's own checks — so it cannot soil a neighbour's work, already accepted or not, nor read it
(the author, 2026-10-27: «по ошибке могут насрать соседу … агенты могут подглядывать»). The system's own commands stay
in the project's container. A validation's run — an issuer's contact with a node too — writes its own round of the
node's scratch and reads the earlier ones, whose probes its standing findings name.

Each node holds its own temp. Not held yet: see `PlaceContainer` — the CLI's state is shared, a root's judges write
the base.
"""
import os
import shutil
import subprocess
import time
from pathlib import Path
from types import SimpleNamespace

import pytest

import gfso.adapters.execution as E
import gfso.workspaces as WS
from gfso.adapters.execution import ContainerExecution, PlaceContainer
from gfso.issuer import CONTACT_ROUND, _contact_place

IMAGE = "e3-linux-agent:2"


@pytest.fixture
def project(tmp_path, monkeypatch):
    monkeypatch.setattr(E, "_SESSIONS", {})
    monkeypatch.setattr(E, "_SWITCH", {})
    base = tmp_path / "work" / "ws"
    for d in ("ws", ".gfso-nodes-ws/p/a", ".gfso-nodes-ws/p/b", ".gfso-scratch-ws", ".gfso-tmp-ws"):
        (tmp_path / "work" / d).mkdir(parents=True, exist_ok=True)
    (tmp_path / "e.env").write_text("NOTHING=1\n")
    return ContainerExecution("t", IMAGE, str(tmp_path / "e.env"), str(tmp_path / "state"), str(base),
                              f"sess{time.time_ns()}")


def test_a_session_writes_its_place_and_reads_the_base(project):
    work = project.parent
    a = project.session(str(work / ".gfso-nodes-ws/p/a"))
    assert isinstance(a, PlaceContainer) and a.rw == work / ".gfso-nodes-ws/p/a"
    assert a._mounts() == [(project.base, True), (work / ".gfso-nodes-ws/p/a", False),
                           (work / ".gfso-nodes-ws/p/.gfso-scratch-a", True), (Path(a.temp_root()), False)],         "its validations' rounds read-only: they hold the probes its standing findings re-run"
    assert project.session(str(work / ".gfso-nodes-ws/p/a/src")) is a, "one container per place"
    assert project.session(str(work / ".gfso-nodes-ws/p/b")) is not a
    with pytest.raises(ValueError):
        a._inside_cwd(str(work / ".gfso-nodes-ws/p/b"))
    root = project.session(str(project.base))
    assert root._mounts() == [(project.base, False), (work / ".gfso-scratch-ws", False), (Path(root.temp_root()), False)]


@pytest.mark.parametrize("scratch", [".gfso-scratch-ws", ".gfso-nodes-ws/p/.gfso-scratch-a"])
def test_a_validation_writes_its_round_and_reads_the_earlier_ones(project, scratch):
    """The scratch stands beside the place validated — the base's, or a node clone's (`tools_llm`)."""
    scratch = project.parent / scratch
    v = project.session(str(scratch / "root_1700000000" / "run" / "delivery"))
    assert v.rw == scratch / "root_1700000000"
    assert v._mounts() == [(project.base, True), (scratch, True), (scratch / "root_1700000000", False),
                           (Path(v.temp_root()), False)]


def test_the_systems_commands_stay_in_the_projects_container(project):
    assert project.session(str(project.parent / ".gfso-nodes-ws/p/a")).container != project.container
    assert project._mounts() == [(project.parent / m, False) for m in project.mounts]


def test_a_place_going_takes_its_session_with_it(project, monkeypatch):
    ran = []
    monkeypatch.setattr(E, "run", lambda args, **kw: ran.append(args) or subprocess.CompletedProcess(args, 0, "", ""))
    monkeypatch.setattr(ContainerExecution, "run", lambda self, args, **kw: subprocess.CompletedProcess(args, 0, "", ""))
    a = project.session(str(project.parent / ".gfso-nodes-ws/p/a"))
    b = project.session(str(project.parent / ".gfso-nodes-ws/p/b"))
    project.remove_tree(str(project.parent / ".gfso-nodes-ws/p/a"))
    assert ["docker", "rm", "-f", a.container] in ran and ["docker", "rm", "-f", b.container] not in ran
    project.stop()
    assert ["docker", "rm", "-f", b.container] in ran and E._SESSIONS == {}


def _docker():
    return bool(shutil.which("docker")) and subprocess.run(["docker", "image", "inspect", IMAGE],
                                                           capture_output=True).returncode == 0


def _git(cwd, *args):
    subprocess.run(["git", "-c", "user.name=t", "-c", "user.email=t@t", *args], cwd=cwd, check=True,
                   capture_output=True)


@pytest.mark.skipif(not _docker(), reason=f"needs docker and {IMAGE}")
def test_live_a_session_sees_its_place_alone(project):
    work = project.parent
    _git(project.base, "init", "-q")
    (project.base / "b.txt").write_text("base\n")
    _git(project.base, "add", "b.txt")
    _git(project.base, "commit", "-qm", "base")
    for n in ("a", "b"):
        node = work / ".gfso-nodes-ws/p" / n
        shutil.rmtree(node)
        _git(node.parent, "clone", "-q", "--shared", str(project.base), n)
        (node / ".git/objects/info/alternates").write_bytes(b"../../../../../ws/.git/objects\n")   # LF: git reads a CR
    (work / ".gfso-nodes-ws/p/b/secret.txt").write_text("b's work\n")
    a = project.session(str(work / ".gfso-nodes-ws/p/a"))
    probe = ("echo x > a.c && git add a.c && git -c user.name=t -c user.email=t@t commit -qm work && echo COMMITTED; "
             "ls /gfso-place/.gfso-nodes-ws/p/b/secret.txt 2>/dev/null && echo SAW-B; "
             "touch /gfso-place/ws/x 2>/dev/null && echo WROTE-BASE; "
             "git -C /gfso-place/ws update-ref refs/heads/x HEAD 2>/dev/null && echo MOVED-A-BASE-REF; "
             "cat /gfso-place/ws/b.txt; true")
    try:
        got = a.run(["bash", "-c", probe], cwd=str(work / ".gfso-nodes-ws/p/a"), timeout=120).stdout.split()
        assert got == ["COMMITTED", "base"], got
        assert (work / ".gfso-nodes-ws/p/a/a.c").exists(), "the session's work stands in its place on the host"
        sys_view = project.run(["ls", str(work / ".gfso-nodes-ws/p/b")], cwd=str(project.base), timeout=60).stdout
        assert "secret.txt" in sys_view, "the system's own commands still see every place"
    finally:
        project.stop()


@pytest.mark.skipif(not _docker(), reason=f"needs docker and {IMAGE}")
def test_live_a_validation_writes_its_round_alone_and_its_call_ends_where_it_runs(project):
    scratch = project.parent / ".gfso-scratch-ws"
    (scratch / "root_1/run").mkdir(parents=True)
    (scratch / "root_1/run/probe.sh").write_text("echo earlier\n")
    (scratch / "root_2/run/delivery").mkdir(parents=True)
    v = project.session(str(scratch / "root_2/run/delivery"))
    probe = ("echo r > ../mine.txt && echo WROTE-ITS-ROUND; cat /gfso-place/.gfso-scratch-ws/root_1/run/probe.sh; "
             "touch /gfso-place/.gfso-scratch-ws/root_1/run/x 2>/dev/null && echo WROTE-AN-EARLIER-ROUND; true")
    try:
        got = v.run(["bash", "-c", probe], cwd=str(scratch / "root_2/run/delivery"), timeout=120).stdout.split()
        assert got == ["WROTE-ITS-ROUND", "echo", "earlier"], got
        q = v.popen(["sh", "-c", "setsid sleep 300 & sleep 300"], env={}, cwd=str(scratch / "root_2/run/delivery"),
                    stdout=subprocess.PIPE, text=True)
        time.sleep(2)
        project.end(q)                                   # ended through the project's execution, as headless does
        left = subprocess.run(["docker", "exec", v.container, "sh", "-c", "pgrep -c sleep || true"],
                              capture_output=True, text=True).stdout.strip()
        assert left == "1", f"the call's sleeps outlived its end: {left} (only the container's own `sleep infinity`)"
    finally:
        project.stop()


def test_the_systems_own_checks_stand_where_no_session_reaches(project):
    """The system's exact checks and observations: in the temp every session holds, a session could change what a
    check runs on (critic over the session slice)."""
    with project.scratch("gfso-exact-", system=True) as d:
        assert Path(d).parent == project.parent / ".gfso-sys-ws"
        a = project.session(str(project.parent / ".gfso-nodes-ws/p/a"))
        assert not any(src.is_relative_to(project.parent / ".gfso-sys-ws") for src, _ in a._mounts())


def test_an_issuers_contact_is_a_round_of_the_nodes_own_scratch(project):
    """It reads the probes the node's standing findings name in the earlier rounds and writes only its own; a root's,
    with no copy, lays its inputs in the temp its session holds (critic 2 over the session slice: moved to the system's
    scratch, a root's contact could not read its inputs nor a node's run its findings)."""
    node = project.parent / ".gfso-nodes-ws/p/a"
    with _contact_place(str(node), project) as d:
        assert Path(d).parent == node.parent / ".gfso-scratch-a"
        c = project.session(d + "/place")
        assert c.rw == Path(d) and (node.parent / ".gfso-scratch-a", True) in c._mounts()
    with _contact_place(str(project.base), project) as d:
        assert Path(d).parent == Path(project.temp_of(str(project.base)))
        assert any(Path(d).is_relative_to(src) for src, _ in project.session(str(project.base))._mounts())


def test_a_session_whose_directory_is_gone_is_stopped_and_one_started_by_its_project_stays_tracked(project, monkeypatch):
    ran = []
    monkeypatch.setattr(E, "run", lambda args, **kw: ran.append(args) or subprocess.CompletedProcess(
        args, 0, "true" if args[:2] == ["docker", "inspect"] else "", ""))
    monkeypatch.setattr(E, "_STARTED", {})
    with project.scratch("gfso-noplace-") as d:
        gone = project.session(d)
    project.session(str(project.parent / ".gfso-nodes-ws/p/a"))
    assert ["docker", "rm", "-f", gone.container] in ran and gone.container not in {s.container for s in E._SESSIONS.values()}
    b = project.session(str(project.parent / ".gfso-nodes-ws/p/b"))
    b.start()                                            # its project's container starts first, stopping its sessions
    assert E._SESSIONS[(project.container, os.path.normcase(b.rw))] is b


SYSTEMS_OWN = {"issuer/__init__.py": ("gfso-derive-",), "observe.py": ("gfso-observe-",),
               "tools_llm.py": ("gfso-exact-",)}


def test_the_systems_own_copies_and_checks_take_the_systems_scratch():
    """The issuer's copy of a node and the system's checks: in the temp every session holds, a session could read a
    neighbour's delivery or change what a check runs on."""
    gfso = Path(__file__).resolve().parents[1] / "gfso"
    for f, prefixes in SYSTEMS_OWN.items():
        text = (gfso / f).read_text(encoding="utf-8")
        for p in prefixes:
            assert f'.scratch("{p}", system=True)' in text and f'.scratch("{p}")' not in text, (f, p)


@pytest.mark.skipif(not _docker(), reason=f"needs docker and {IMAGE}")
def test_live_an_issuers_contact_reads_its_inputs_and_the_nodes_earlier_probes(project):
    node = project.parent / ".gfso-nodes-ws/p/a"
    (node.parent / ".gfso-scratch-a/a_1/run").mkdir(parents=True)
    (node.parent / ".gfso-scratch-a/a_1/run/probe.sh").write_text("echo probed\n")
    try:
        with _contact_place(str(node), project) as d:
            (Path(d) / "place").mkdir()
            (Path(d) / "in.txt").write_text("node-input\n")
            got = project.session(d + "/place").run(
                ["bash", "-c", "cat ../in.txt; bash /gfso-place/.gfso-nodes-ws/p/.gfso-scratch-a/a_1/run/probe.sh; "
                               "touch /gfso-place/.gfso-nodes-ws/p/.gfso-scratch-a/a_1/x 2>/dev/null && echo WROTE; true"],
                cwd=d + "/place", timeout=120).stdout.split()
            assert got == ["node-input", "probed"], got
        with _contact_place(str(project.base), project) as d:
            (Path(d) / "in.txt").write_text("root-input\n")
            got = project.session(str(project.base)).run(["cat", str(Path(d) / "in.txt")], cwd=str(project.base),
                                                         timeout=120).stdout.split()
            assert got == ["root-input"], got
    finally:
        project.stop()


@pytest.mark.skipif(not _docker(), reason=f"needs docker and {IMAGE}")
def test_live_an_executor_reads_its_findings_probes_and_cannot_rewrite_them(project):
    node = project.parent / ".gfso-nodes-ws/p/a"
    (node.parent / ".gfso-scratch-a/a_1").mkdir(parents=True)
    (node.parent / ".gfso-scratch-a/a_1/probe.sh").write_text("echo probed\n")
    probe = ("bash /gfso-place/.gfso-nodes-ws/p/.gfso-scratch-a/a_1/probe.sh; "
             "echo 'echo forged' > /gfso-place/.gfso-nodes-ws/p/.gfso-scratch-a/a_1/probe.sh 2>/dev/null && echo REWROTE; true")
    try:
        got = project.session(str(node)).run(["bash", "-c", probe], cwd=str(node), timeout=120).stdout.split()
        assert got == ["probed"], got
    finally:
        project.stop()


def test_each_node_holds_its_own_temp_and_its_validations_share_it(project):
    """What the system lays for a node's sessions — inputs, long lists — stands where only that node's sessions reach
    (critic 3 over the session slice: the temp every session held carried every node's, read and written)."""
    work = project.parent
    a, b = project.session(str(work / ".gfso-nodes-ws/p/a")), project.session(str(work / ".gfso-nodes-ws/p/b"))
    assert a.temp_root() != b.temp_root() and Path(a.temp_root()).parent == work / ".gfso-tmp-ws"
    assert not any(Path(b.temp_root()).is_relative_to(src) or src == work / ".gfso-tmp-ws" for src, _ in a._mounts())
    round_of_a = project.session(str(work / ".gfso-nodes-ws/p/.gfso-scratch-a/a_1/run/delivery"))
    assert round_of_a.temp_root() == a.temp_root() == project.temp_of(str(work / ".gfso-nodes-ws/p/a"))


def test_what_the_system_lays_for_a_session_goes_to_its_nodes_temp():
    """Inputs and long lists are laid in the temp of the node they are for, not the temp every node once held."""
    gfso = Path(__file__).resolve().parents[1] / "gfso"
    packets = (gfso / "packets.py").read_text(encoding="utf-8")
    assert "temp_root()" not in packets and packets.count("node_temp(engine,") == 2 and "temp_of(workdir)" in packets
    assert "ex.temp_of(where)" in (gfso / "issuer/__init__.py").read_text(encoding="utf-8")


@pytest.mark.skipif(not _docker(), reason=f"needs docker and {IMAGE}")
def test_live_a_node_reads_its_own_temp_and_not_its_neighbours(project):
    work = project.parent
    a, b = project.session(str(work / ".gfso-nodes-ws/p/a")), project.session(str(work / ".gfso-nodes-ws/p/b"))
    (Path(a.temp_root()) / "mine.md").write_text("a-list\n")
    (Path(b.temp_root()) / "theirs.md").write_text("b-list\n")
    probe = (f"cat {a.to_inside(str(Path(a.temp_root()) / 'mine.md'))}; "
             f"cat {a.to_inside(str(Path(b.temp_root()) / 'theirs.md'))} 2>/dev/null && echo SAW-B; "
             f"ls {a.to_inside(str(work / '.gfso-tmp-ws'))} 2>/dev/null | grep -c node- ; true")
    try:
        got = a.run(["bash", "-c", probe], cwd=str(work / ".gfso-nodes-ws/p/a"), timeout=120).stdout.split()
        assert got[:1] == ["a-list"] and "SAW-B" not in got, got
        assert got[1:] in ([], ["0"], ["1"]), f"the temp's other nodes are listed: {got}"
    finally:
        project.stop()


def test_the_temp_laid_for_a_node_is_the_one_its_session_holds_now(project, monkeypatch):
    """A parent's consent runs before its executor made its place, in the roster's workdir: what is laid for it goes
    to the temp that session holds, and once the place stands, to the place's (critic over the node temps)."""
    place = project.parent / ".gfso-nodes-ws/p/a"
    task = SimpleNamespace(id="a", assignee="exec")
    monkeypatch.setattr(WS, "execution_of", lambda engine, agents=None: project)
    monkeypatch.setattr(WS, "performer", lambda engine, agents, who: (who, {"workdir": str(project.base)}))
    monkeypatch.setattr(WS, "node_workspace", lambda engine, agents, tid: None)
    before = WS.node_temp(SimpleNamespace(), task)
    assert before == project.temp_of(str(project.base)) == project.session(str(project.base)).temp_root()
    monkeypatch.setattr(WS, "node_workspace", lambda engine, agents, tid: str(place))
    assert WS.node_temp(SimpleNamespace(), task) == project.session(str(place)).temp_root() != before
    with project.scratch("gfso-conformance-") as d:
        assert project.temp_of(d) == str(Path(d).resolve()), "a directory lent to one call is its own temp"


def test_the_rounds_rotation_leaves_a_running_contact_alone(project):
    """A contact runs among the node's validation rounds; the rotation that keeps the newest twenty must not take it
    from under its session (critic over the S4 seam)."""

    with _contact_place(str(project.parent / ".gfso-nodes-ws/p/a"), project) as d:
        assert Path(d).name.startswith(CONTACT_ROUND)
    rotation = (Path(__file__).resolve().parents[1] / "gfso/tools_llm.py").read_text(encoding="utf-8")
    assert "if not d.name.startswith(_CONTACT)" in rotation
