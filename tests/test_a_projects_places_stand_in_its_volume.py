"""A project's own directory — its node places, its judges' rounds, its temps, its system copies, its sessions' CLI
state — is its Docker volume, on no host file system: the system reaches it through its port alone, each session's
container mounts exactly the subpaths it held before with the same rights, and nothing of the host is mounted into a
door or a gateway (the author, 2026-10-28: «изоляция значит изоляция … бесшовно и одинаково в любой системе»; measured:
a Windows host directory bind-mounted through Docker Desktop's file sharing threw I/O errors for 35 min). The base too:
the user's repository imported at the root's start, its accepted result landed back as a branch."""
import hashlib
import io
import json
import os
import sqlite3
import subprocess
import tarfile
import time
from pathlib import Path
from types import SimpleNamespace

import pytest

import gfso.adapters.door as D
import gfso.adapters.execution as E
import gfso.adapters.worktrees as W
import gfso.engine.findings as F
import gfso.workspaces as WS
from gfso.cli import _export_places
from gfso.adapters.execution import STATE_INSIDE, ContainerExecution
from gfso.core.types import PlaceUnavailable
from tests.test_a_session_holds_only_its_own_place import IMAGE, _docker, _git, lay, made, project  # noqa: F401

live = pytest.mark.skipif(not _docker(), reason=f"needs docker and {IMAGE}")


def _mounts(container: str) -> list:
    got = subprocess.run(["docker", "inspect", "-f", "{{json .Mounts}}", container], capture_output=True, text=True)
    return json.loads(got.stdout)


def _base_with_a_commit(project) -> None:
    _git(project.base, "init", "-q")
    (project.base / "b.txt").write_text("base\n")
    _git(project.base, "add", "b.txt")
    _git(project.base, "commit", "-qm", "base")


@live
def test_live_a_place_lives_its_whole_life_in_the_volume(project):
    """Made, written, read, copied for a judge, removed — and no directory under the project's own on the host."""
    _base_with_a_commit(project)
    node = project.own / "a"
    try:
        assert W.ensure(project.base, node, "gfso/p/a", project.base, execution=project)
        a = project.session(str(node))
        assert a.run(["sh", "-c", "echo work > w.txt"], cwd=str(node), timeout=120).returncode == 0
        assert project.files.read_bytes(str(node / "w.txt")) == b"work\n"
        project.files.mkdir(str(round_ := project.own / ".gfso-scratch-a" / "a_1"))
        project.copy_tree(str(node), str(round_ / "delivery"))
        judge = project.session(str(round_ / "delivery"))
        assert judge.run(["cat", "w.txt"], cwd=str(round_ / "delivery"), timeout=120).stdout == "work\n"
        project.remove_tree(str(node))
        assert not project.files.exists(str(node)) and project.files.exists(str(round_ / "delivery" / "w.txt"))
        assert not project.own.exists() and not (project.parent / ".gfso-nodes-ws").exists()
    finally:
        project.stop()


def _held(container: str) -> set:
    """(where inside, a bind's host directory or the volume's name, its subpath, read-only?) of each mount."""
    got = subprocess.run(["docker", "inspect", "-f", "{{json .HostConfig.Mounts}}", container], capture_output=True,
                         text=True)
    return {(m["Target"], m["Source"] if m["Type"] == "bind" else (m["Source"], (m.get("VolumeOptions") or {}).get(
        "Subpath")), bool(m.get("ReadOnly"))) for m in json.loads(got.stdout)}


@live
def test_live_a_sessions_container_mounts_its_own_subpaths_with_their_rights(project):
    """Exactly what `_mounts` gives, each a subpath of the volume — the whole volume nowhere, a read-only one nowhere
    writable — its CLI state at the CLI's own path too, the base the volume's, read-only: nothing of the host."""
    made(project, "a")
    a = project.session(str(project.own / "a"))
    v = project.volume.name
    try:
        a.run(["true"], cwd=str(project.own / "a"), timeout=120).check_returncode()
        sub = lambda d: (v, ".gfso-base" if d == project.base else d.relative_to(project.own).as_posix())
        want = {(a.to_inside(str(d)), sub(d), ro) for d, ro in a._mounts()}
        want |= {(at, (project.volume.state, "+a"), False) for at in (a.to_inside(str(a.state)), STATE_INSIDE)}
        held = _held(a.container)
        assert all(m[1][1] for m in held if isinstance(m[1], tuple)), "a session mounts no whole volume"
        assert held == want, "its own subpaths, with their rights"
        assert _held(project.container) == {(project.to_inside(str(project.base)), (v, ".gfso-base"), False),
                                            (project.to_inside(str(project.own)), (v, None), False)}
    finally:
        project.stop()


@live
def test_live_a_projects_places_left_on_the_host_are_copied_in_once(tmp_path, monkeypatch):
    """A live project from before its volume keeps its places on a restart: its host directory copied in, owned by the
    image's user — its session writes there — the origin recorded; a later start copies nothing over the volume."""
    monkeypatch.setattr(E, "_SESSIONS", {})
    (base := tmp_path / "w" / "ws").mkdir(parents=True)
    (left := tmp_path / "w" / ".gfso-nodes-ws" / "p" / "a").mkdir(parents=True)
    (left / "f.txt").write_bytes(b"before\n")
    x = ContainerExecution(f"t{time.time_ns()}", IMAGE, None, str(tmp_path / "state"), str(base), "p")
    try:
        assert x.files.read_bytes(str(x.own / "a" / "f.txt")) == b"before\n"
        assert x.session(str(x.own / "a")).run(["sh", "-c", "echo after > f.txt"], cwd=str(x.own / "a"),
                                               timeout=120).returncode == 0
        assert x.volume.record[0]("volume:places") == x.volume.name and x.volume.record[0]("volume:state")
        assert (x.volume.record[0]("volume:base"), x.volume.record[0]("volume:image")) == (str(x.base), IMAGE), \
            "what an export reads the volume by, kept beside it"
        assert not left.parent.exists() and len(list(left.parent.parent.glob("p.copied-in-*"))) == 1, "consumed"
        left.mkdir(parents=True)
        (left / "f.txt").write_bytes(b"the host's leftover, changed\n")
        x.stop()
        assert x.files.read_bytes(str(x.own / "a" / "f.txt")) == b"after\n", "copied in once, never over the volume"
    finally:
        x.stop()
        x.volume.remove()


@live
def test_live_a_door_runs_with_nothing_of_the_host_mounted_and_its_log_reads_out(project):
    door, _ = project.gate.url(SimpleNamespace(kind="token", value="V"), "api.anthropic.com")
    name = next(iter(project.gate.held.values()))[0]
    try:
        assert _mounts(name) == [], "its script laid in its own memory, not mounted"
        knock = ("import urllib.request as u\ntry: u.urlopen(u.Request('http://127.0.0.1:8080/v1/x', data=b'{}', "
                 "headers={'x-api-key': 'not-its-key'}))\nexcept Exception: pass")
        subprocess.run(["docker", "exec", name, "python3", "-c", knock], capture_output=True, timeout=60)
        assert "refused: not this door's key" in project.gate.log_text()
    finally:
        project.stop()
    assert "refused: not this door's key" in project.gate.log().read_text(encoding="utf-8"), "kept past its door"


def test_a_sessions_container_is_named_and_labelled_by_its_agent_node_and_role(project):
    """«вместо сборных имён через тире сделать иерархию … видеть подгруппу именно действующих агентов» (the author,
    2026-10-28): named by node and role off the system's own names, stable per place; labelled with the agent its
    starting session names, its node, its role; grouped by role in its project's stack."""
    own = project.own
    cases = {own / "root.parser": ("executor", "root.parser"), project.base: ("executor", "root"),
             own / ".gfso-scratch-root.parser" / "r_1": ("judge", "root.parser"),
             own / ".gfso-scratch-.ws" / "r_2": ("judge", "root"), own / ".gfso-sys" / "gfso-exact-1": ("check", "gfso-exact-1")}
    for place, (role, node) in cases.items():
        s = project.session(str(place), "exec-2")
        assert (s.role, s.node, s.agent) == (role, node, "exec-2")
        assert s.container.startswith(f"{role}.{node}") and s.container == E.PlaceContainer(
            project, place).container, "stable per place"
        assert project.container not in s.container, "the project's group names the project; the name, the role first"
        labels = dict(a.split("=", 1) for a in s.run_args() if a.startswith(("gfso.", "com.docker.compose.service")))
        assert labels == {"com.docker.compose.service": role + "s", "gfso.role": role, "gfso.node": node,
                          "gfso.agent": "exec-2", "gfso.execution": project.name, "gfso.project": "p",
                          "gfso.home": E._home()}
    assert project.session(str(own / "b"), "first").agent == "first"
    assert project.session(str(own / "b"), "then").agent == "then", "the agent of whichever session starts it"
    assert E._kind_of(("r",), ()) == ("executor", "r", ())


def test_only_a_projects_deletion_removes_its_volume(tmp_path, monkeypatch):
    """The volume holds the project's work: a stop, a turn of the switch and a server's sweep of leftovers keep it."""
    ran = []
    monkeypatch.setattr(E, "run", lambda args, **kw: ran.append(args) or subprocess.CompletedProcess(
        args, 0, "its-v its-state" if args[:3] == ["docker", "volume", "ls"] else "", ""))
    monkeypatch.setattr(E.shutil, "which", lambda p: "docker")
    (base := tmp_path / "ws").mkdir()
    x = ContainerExecution("e3-linux", "img", None, str(tmp_path / "state"), str(base), "p")
    x.stop()
    E.end_leftovers()
    E.end_started()
    assert not [a for a in ran if a[:2] == ["docker", "volume"] and "rm" in a]
    monkeypatch.setattr(WS, "_EXECUTIONS", {("e3-linux", "p", str(base)): x})
    WS.drop_execution("p")                                       # …by its label: no roster read
    ls = next(a for a in ran if a[:3] == ["docker", "volume", "ls"])
    assert "label=gfso.project=p" in ls and f"label=gfso.home={E._home()}" in ls
    assert ["docker", "volume", "rm", "-f", "its-v"] in ran and ["docker", "volume", "rm", "-f", "its-state"] in ran


_KNOCK = '''import sys, urllib.request as u, urllib.error as e
from concurrent.futures import ThreadPoolExecutor
def ask(key, path="/v1/messages"):
    r = u.Request("http://127.0.0.1:8080" + path, data=b'{"model":"x","messages":[]}', method="POST",
                  headers={"x-api-key": key, "content-type": "application/json"})
    try:
        return u.urlopen(r, timeout=60).status
    except e.HTTPError as x:
        return x.code
    except Exception as x:
        return repr(x)
if sys.argv[1] == "flood":
    with ThreadPoolExecutor(16) as p:
        list(p.map(lambda i: ask("not-its-key", "/" + "a" * 199), range(int(sys.argv[2]))))
else:
    print(ask(sys.argv[2]))
'''


@live
def test_live_a_flood_of_refusals_and_a_full_disk_never_cut_a_keyed_request(project, tmp_path, monkeypatch):
    """Past its cap a refusal is not written; a disk that refuses a line drops it — the request is served all the
    same: an executor flooding its project's door filled its log's memory and turned every keyed request into a 502
    (critic over 71b49ad, 80 000 keyless requests in 72 s). The cap shrunk here, so the flood is a short one."""
    small = tmp_path / "door.py"
    small.write_bytes(Path(D.__file__).read_bytes().replace(b"LOG_CAP = 20 * 2 ** 20", b"LOG_CAP = 2 ** 20"))
    monkeypatch.setattr(D, "__file__", str(small))
    monkeypatch.setattr(D, "LOG_CAP", 2 ** 20)
    _, key = project.gate.url(SimpleNamespace(kind="api", value="not-a-real-key"), "api.anthropic.com")
    name = next(iter(project.gate.held.values()))[0]
    sh = lambda *a: subprocess.run(["docker", "exec", name, *a], capture_output=True, text=True, timeout=600)
    try:
        sh("python3", "-c", _KNOCK, "flood", "4500")
        assert "the log is full" in project.gate.log_text()
        # …every block taken, and the slack of the log's last one too: a short line still fits there
        sh("sh", "-c", "dd if=/dev/zero of=/gfso-own/fill bs=64k 2>/dev/null; "
                       "while printf x >> /gfso-own/door.log 2>/dev/null; do :; done")
        got = sh("python3", "-c", _KNOCK, "keyed", key).stdout.strip()
        assert got in ("400", "401", "403", "404"), f"a keyed request after the flood got {got}, not the upstream's answer"
    finally:
        project.stop()


@live
def test_live_an_agents_links_in_a_left_place_arrive_as_links_and_its_conversations_with_them(tmp_path, monkeypatch):
    """Copied in by Linux, a link reads as a link — Docker Desktop's `docker cp` skipped all three kinds and exited 0
    (critic over 71b49ad); and each place's CLI state of before the volume comes to its new name."""
    monkeypatch.setattr(E, "_SESSIONS", {})
    (base := tmp_path / "w" / "ws").mkdir(parents=True)
    (left := tmp_path / "w" / ".gfso-nodes-ws" / "p" / "a").mkdir(parents=True)
    (left / "f.txt").write_bytes(b"x\n")
    subprocess.run(["docker", "run", "--rm", "--mount", f"type=bind,src={left},dst=/l", IMAGE, "sh", "-c",
                    "cd /l && ln -s /etc/hostname abs-file && ln -s /etc abs-dir && ln -s f.txt rel"], check=True)
    x = ContainerExecution(f"t{time.time_ns()}", IMAGE, None, str(tmp_path / "state"), str(base), "p")
    old = tmp_path / "state" / x.container
    key = lambda p: hashlib.sha1(os.path.normcase(p).encode()).hexdigest()[:12]      # …its old name
    (old / "places" / key(x.own / "a") / "projects" / "-x").mkdir(parents=True)
    (old / "places" / key(x.own / "a") / "projects" / "-x" / "s.jsonl").write_bytes(b"{}\n")
    (old / "gfso-sessions").mkdir(parents=True)
    (old / "gfso-sessions" / "t.json").write_bytes(b"[]")
    try:
        got = x.run(["sh", "-c", "for l in abs-file abs-dir rel; do readlink $l; done"], cwd=str(x.own / "a"),
                    timeout=120).stdout.split()
        assert got == ["/etc/hostname", "/etc", "f.txt"], got
        assert x.files.exists(str(x.state / "+a" / "projects" / "-x" / "s.jsonl"))
        assert x.files.exists(str(x.state / "gfso-sessions" / "t.json"))
    finally:
        x.stop()
        x.volume.remove()


@live
def test_live_a_volume_lost_under_its_record_stops_the_place_and_is_never_refilled(tmp_path, monkeypatch):
    """The project's record says its volume was made: the volume gone, the place is down with that reason — refilled
    from the host's stale copy, the project would go on over work it already did (critic over 71b49ad)."""
    monkeypatch.setattr(E, "_SESSIONS", {})
    (base := tmp_path / "w" / "ws").mkdir(parents=True)
    (left := tmp_path / "w" / ".gfso-nodes-ws" / "p" / "a").mkdir(parents=True)
    (left / "f.txt").write_bytes(b"stale\n")
    kept = {}
    x = ContainerExecution(f"t{time.time_ns()}", IMAGE, None, str(tmp_path / "state"), str(base), "p")
    x.volume.record = (kept.get, kept.__setitem__)
    try:
        x.files.write_bytes(str(x.own / "a" / "f.txt"), b"work\n")
        assert kept["volume:places"] == x.volume.name
        x.stop()
        x.volume.remove()
        with pytest.raises(PlaceUnavailable, match="its volume .* is gone"):
            x.files.read_bytes(str(x.own / "a" / "f.txt"))
    finally:
        x.stop()
        x.volume.remove()


@live
def test_live_a_copy_in_cut_by_its_time_leaves_no_copy_running_and_the_next_start_makes_it_whole(tmp_path,
                                                                                                    monkeypatch):
    """Its own container gone with the cut, nothing recorded; the next start empties what it half wrote and copies
    whole — the orphan of a cut copy raced the retry and wrote over it (critic over 6202d19)."""
    monkeypatch.setattr(E, "_SESSIONS", {})
    (base := tmp_path / "w" / "ws").mkdir(parents=True)
    (left := tmp_path / "w" / ".gfso-nodes-ws" / "p" / "a").mkdir(parents=True)
    for i in range(300):
        (left / f"f{i}").write_bytes(b"x")
    x = ContainerExecution(f"t{time.time_ns()}", IMAGE, None, str(tmp_path / "state"), str(base), "p")
    one = f"{x.volume.name}-bring-in"
    x.volume.copy_time = 0.2
    try:
        with pytest.raises(RuntimeError):
            x.start()
        assert not subprocess.run(["docker", "ps", "-aq", "--filter", f"name={one}"], capture_output=True,
                                  text=True).stdout.split(), "the cut copy's container goes with the cut"
        assert x.volume.record[0]("volume:places") is None and left.is_dir(), "nothing recorded, nothing consumed"
        x.volume.copy_time = 1800
        got = x.run(["sh", "-c", "ls | wc -l"], cwd=str(x.own / "a"), timeout=120).stdout.strip()
        assert got == "300" and x.volume.record[0]("volume:places")
    finally:
        x.stop()
        x.volume.remove()


def _fresh(tmp_path, base, record: dict, name: str = "", project: str = "p") -> ContainerExecution:
    """A server's view of the project, its own record in hand — as `workspaces.execution_of` holds it."""
    E._STARTED.clear()
    E._SESSIONS.clear()
    x = ContainerExecution(name or f"t{tmp_path.name[-12:]}", IMAGE, None, str(tmp_path / "state"), str(base), project)
    x.volume.record = (record.get, record.__setitem__)
    return x


def _volume_stands(v: str) -> bool:
    return subprocess.run(["docker", "volume", "inspect", v], capture_output=True).returncode == 0


@live
def test_live_a_lost_volume_stays_lost_whoever_asks_the_storage(tmp_path):
    """F1 (critic over 28c8064): the storage probe's own mount made a lost volume again, empty, at every tick of the
    monitor — the place no longer read as lost, and the project ran on nothing."""
    (base := tmp_path / "ws").mkdir()
    kept: dict = {}
    x = _fresh(tmp_path, base, kept)
    try:
        x.files.mkdir(str(x.own / "a"))
        x.files.write_bytes(str(x.own / "a" / "w"), b"WORK")
        x.stop()
        x.volume.remove()
        x = _fresh(tmp_path, base, kept)
        assert "is gone" in (x.unavailable(storage=True) or "") and "is gone" in (x.unavailable(storage=True) or "")
        assert not _volume_stands(x.volume.name) and not _volume_stands(x.volume.state), "made again by the probe"
        with pytest.raises(PlaceUnavailable, match="is gone"):
            x.start()
        y = _fresh(tmp_path, base, {}, "u" + x.name)                         # …never made: not lost, and the probe
        assert y.unavailable(storage=True) is None and not _volume_stands(y.volume.name)   # makes nothing of it
    finally:
        x.stop()
        x.volume.remove()


@live
def test_live_two_installations_on_one_machine_hold_a_volume_each(tmp_path, monkeypatch):
    """F2: one execution, project and base under two state homes — B's first start emptied A's volume."""
    (base := tmp_path / "ws").mkdir()
    monkeypatch.setenv("GFSO_DATA_DIR", str(tmp_path / "home-a"))
    a = _fresh(tmp_path, base, {})
    xs = [a]
    try:
        a.files.mkdir(str(a.own / "a"))
        a.files.write_bytes(str(a.own / "a" / "w"), b"A-WORK")
        a.stop()
        monkeypatch.setenv("GFSO_DATA_DIR", str(tmp_path / "home-b"))
        xs.append(b := _fresh(tmp_path, base, {}))
        assert b.files.read_bytes(str(b.own / "a" / "w")) is None, "B reads nothing of A's"
        b.stop()
        monkeypatch.setenv("GFSO_DATA_DIR", str(tmp_path / "home-a"))
        a2 = _fresh(tmp_path, base, {"volume:places": a.volume.name, "volume:state": a.volume.state})
        xs.append(a2)
        assert a2.files.read_bytes(str(a2.own / "a" / "w")) == b"A-WORK", "A's work survives B's start"
    finally:
        for x in xs:
            x.stop()
            x.volume.remove()


@live
def test_live_a_project_whose_volumes_its_record_names_otherwise_is_down_never_started_empty(tmp_path, monkeypatch):
    """F3 and its sequel (critics over 28c8064 and f5d93ba): the project's execution declared on another base, under
    another name, or its state home moved with its settings — the record names other volumes than this execution
    would mount. Started on new, empty ones, the project would run on nothing while its work stood elsewhere: it is
    down, both names said, until the operator declares it back or removes the record (then it starts afresh)."""
    (base := tmp_path / "ws").mkdir()
    (other := tmp_path / "other" / "ws2").mkdir(parents=True)
    kept: dict = {}
    xs = [_fresh(tmp_path, base, kept)]
    try:
        xs[0].files.mkdir(str(xs[0].own / "a"))
        xs[0].stop()
        moved = lambda: (monkeypatch.setenv("GFSO_DATA_DIR", str(tmp_path / "moved")), base)[1]
        for name, at in (("", lambda: other), ("v" + xs[0].name, lambda: base), ("", moved)):
            xs.append(y := _fresh(tmp_path, at(), kept, name))
            with pytest.raises(PlaceUnavailable, match=f"in the volume {xs[0].volume.name}, and this execution would "
                                                       f"mount {y.volume.name}"):
                y.files.mkdir(str(y.own / "a"))
            assert not _volume_stands(y.volume.name), "no volume made of a record that names another"
        for k in [k for k in kept if k.startswith("volume:")]:
            del kept[k]
        xs.append(y := _fresh(tmp_path, other, kept))
        y.files.mkdir(str(y.own / "a"))                           # …the record removed: started on new volumes
    finally:
        for x in xs:
            x.stop()
            x.volume.remove()


@live
def test_live_a_place_and_a_round_carried_in_stand_by_the_record_once_their_host_copy_is_gone(tmp_path):
    """n5 (critic over f5d93ba): a place and a round from before the record of places made was kept fell back on the
    host's directory — gone once the copy-in consumed it, the node's place read as never made and its validations
    ran in the base. The copy-in records what it carries; once the volume is recorded, the host is never asked."""
    (base := tmp_path / "ws").mkdir()
    (tmp_path / ".gfso-nodes-ws" / "p" / "a").mkdir(parents=True)
    (tmp_path / ".gfso-nodes-ws" / "p" / ".gfso-scratch-a" / "r1").mkdir(parents=True)
    graph = SimpleNamespace(d={})
    graph.setting, graph.store_setting = graph.d.get, graph.d.__setitem__
    engine = SimpleNamespace(graph=graph)
    x = _fresh(tmp_path, base, graph.d)
    x.volume.carried = lambda dirs: WS._carried(engine, dirs)
    try:
        assert x.files.is_dir(str(a := x.own / "a")) and not (tmp_path / ".gfso-nodes-ws" / "p").exists()
        r1 = str(x.own / ".gfso-scratch-a" / "r1")
        assert WS.made(engine, str(a)) and F.round_stands(graph)((r1, ".gfso-scratch-a/r1"))
        assert not WS.made(engine, str(x.own / "b")), "the host is not asked once the volume is recorded"
    finally:
        x.stop()
        x.volume.remove()


@live
def test_live_an_unlabelled_volume_under_the_projects_name_is_never_its_places(tmp_path):
    """n2/n3 (critic over f5d93ba): a volume made outside the system, or by Docker between the asking and the run,
    under the project's name, stood in for its places."""
    (base := tmp_path / "ws").mkdir()
    kept: dict = {}
    x = _fresh(tmp_path, base, kept)
    try:
        subprocess.run(["docker", "volume", "create", x.volume.name], capture_output=True, check=True)
        with pytest.raises(PlaceUnavailable, match="not this installation's making"):
            x.files.mkdir(str(x.own / "a"))
        assert not kept, "nothing recorded"
    finally:
        x.stop()
        x.volume.remove()


@live
def test_live_a_source_the_host_would_not_move_aside_is_moved_at_the_next_start(tmp_path):
    """n4 (critic over f5d93ba): a file held open kept the host's directory from its rename after the record was
    written, and nothing tried again — a project made again under the name refilled from it."""
    (base := tmp_path / "ws").mkdir()
    (left := tmp_path / ".gfso-nodes-ws" / "p" / "a").mkdir(parents=True)
    (left / "f.txt").write_bytes(b"x")
    kept: dict = {}
    x = _fresh(tmp_path, base, kept)
    try:
        with open(left / "f.txt", "rb"):
            x.files.mkdir(str(x.own / "a"))
            held = (tmp_path / ".gfso-nodes-ws" / "p").exists()
        assert kept.get("volume:places") and held, "recorded, and the open file kept the host's copy in place"
        x = _fresh(tmp_path, base, kept)
        x.files.mkdir(str(x.own / "a"))
        assert not (tmp_path / ".gfso-nodes-ws" / "p").exists(), "moved aside at the next start"
    finally:
        x.stop()
        x.volume.remove()


@live
def test_live_a_projects_places_export_to_the_host_whole_its_clones_free_of_the_base(tmp_path):
    """What the E3 harness grades offline: each node's clone reads with the base and the volume gone."""
    (base := tmp_path / "ws").mkdir()
    _git(base, "init", "-q")
    (base / "b.txt").write_text("base\n")
    _git(base, "add", "b.txt")
    _git(base, "commit", "-qm", "base")
    x = _fresh(tmp_path, base, {})
    out = tmp_path / "out" / ".gfso-nodes-ws"
    try:
        assert W.ensure(base, x.own / "a", "gfso/p/a", base, execution=x)
        x.session(str(x.own / "a")).run(["sh", "-c", "echo w > w.txt && ln -s w.txt l"], cwd=str(x.own / "a"),
                                        timeout=120).check_returncode()
        W.commit_all(base, x.own / "a", "work", "agent", x)
        _export(x, out)
        assert x.files.exists(str(x.own / "a" / ".git" / "objects" / "info" / "alternates")), "the place untouched"
    finally:
        x.stop()
        x.volume.remove()
    clone = out / "p" / "a"
    assert (clone / "w.txt").read_text() == "w\n" and not (clone / ".git/objects/info/alternates").exists()
    base.rename(tmp_path / "the-base-gone")
    for cmd in (["log", "--oneline"], ["cat-file", "-p", "HEAD^{tree}"]):
        r = subprocess.run(["git", "-c", f"safe.directory={clone.as_posix()}", *cmd], cwd=clone, capture_output=True,
                           text=True)
        assert r.returncode == 0 and r.stdout.strip(), (cmd, r.stderr)


def _export(x, out) -> list:
    """`gfso export-places` over the project's record as the server kept it — the dict `_fresh` hands its volume."""
    return E.export_places("p", x.volume.record[0].__self__, str(out))


def _two_clones(tmp_path):
    """A project of two node clones, `a` and `b`, each with a commit of its own."""
    (base := tmp_path / "ws").mkdir()
    _git(base, "init", "-q")
    (base / "b.txt").write_text("base\n")
    _git(base, "add", "b.txt")
    _git(base, "commit", "-qm", "base")
    x = _fresh(tmp_path, base, {})
    for n in ("a", "b"):
        assert W.ensure(base, x.own / n, f"gfso/p/{n}", base, execution=x)
        x.session(str(x.own / n)).run(["sh", "-c", f"echo honest > {n}.txt"], cwd=str(x.own / n), timeout=120)
        W.commit_all(base, x.own / n, "work", "agent", x)
    return x


@live
def test_live_an_export_runs_nothing_an_agent_wrote_and_carries_none_of_it(tmp_path):
    """F1/F5 (critic over 247e374): the export's git ran a's `core.fsmonitor` as root and it forged b's exported
    clone; and an exported clone carried its agent's config and hooks to the host. An export is inert."""
    x = _two_clones(tmp_path)
    out = tmp_path / "out"
    a = x.own / "a"
    try:
        x.files.write_bytes(str(a / ".git" / "fsm.sh"), b"#!/bin/sh\ntouch /tmp/x/RAN; echo forged > /tmp/x/b/b.txt\n")
        x.files.write_bytes(str(a / ".git" / "hooks" / "post-checkout"), b"#!/bin/sh\ntouch /tmp/x/HOOK\n")
        x.session(str(a)).run(["sh", "-c", "chmod +x .git/fsm.sh .git/hooks/post-checkout && "
                                           "git config core.fsmonitor /tmp/x/a/.git/fsm.sh"],   # …the export's copy
                    cwd=str(a), timeout=120)
        _export(x, out)
    finally:
        x.stop()
        x.volume.remove()
    got = out / "p"
    assert not (got / "RAN").exists() and (got / "b" / "b.txt").read_text() == "honest\n"
    config = (got / "a" / ".git" / "config").read_text()
    assert "fsmonitor" not in config and not (got / "a" / ".git" / "hooks").exists(), config


@live
def test_live_a_clone_that_does_not_repack_is_exported_as_it_stands_and_named(tmp_path):
    """F2: one clone whose repack failed exited the whole export with nothing written."""
    x = _two_clones(tmp_path)
    out = tmp_path / "out"
    try:
        x.files.write_bytes(str(x.own / "a" / ".git" / "refs" / "heads" / "broken"), b"1" * 40 + b"\n")
        assert _export(x, out), "what could not be done is said"
    finally:
        x.stop()
        x.volume.remove()
    notes = (out / ".gfso-export-notes").read_text(encoding="utf-8")
    assert "a: not repacked" in notes and (out / "p" / "a" / ".git" / "objects" / "info" / "alternates").exists()
    assert not (out / "p" / "b" / ".git" / "objects" / "info" / "alternates").exists(), "the rest made whole"


def test_an_entry_the_host_refuses_or_a_link_out_of_the_export_is_said_and_the_rest_written(tmp_path):
    """F3/F4: two names one on a case-blind disk stopped the extraction part-way; a link was made to lead out."""
    buf = io.BytesIO()
    with tarfile.open(fileobj=buf, mode="w") as t:
        def add(name, data=None, link=None):
            i = tarfile.TarInfo(name)
            if link is not None:
                i.type, i.linkname = tarfile.SYMTYPE, link
            elif data is None:
                i.type = tarfile.DIRTYPE
            else:
                i.size = len(data)
            t.addfile(i, io.BytesIO(data) if data else None)
        add("./a/A", b"file")
        add("./a/a")
        add("./a/a/x", b"under a dir of the same name")
        add("./a/abs", link="/etc/passwd")
        add("./a/up", link="../../../outside")
        add("./a/in", link="A")
        add("./z/last", b"written")
    notes = E._untar(buf.getvalue(), tmp_path / "out")
    assert (tmp_path / "out" / "z" / "last").read_bytes() == b"written", "the rest written"
    for link, target in (("abs", "/etc/passwd"), ("up", "../../../outside")):
        p = tmp_path / "out" / "a" / link
        assert not p.is_symlink() and p.read_text() == target and any(link in n for n in notes)
    assert not (tmp_path / "outside").exists()


@live
def test_live_a_lost_state_volume_is_the_place_down_and_a_project_made_again_inherits_nothing(tmp_path):
    """F5: the CLI state's volume lost under its record — the place down with that reason, no volume made of it. F4:
    a project deleted and made again under its name — the host's leftover and its old CLI state, consumed by the first
    copy-in, do not come in again."""
    (base := tmp_path / "ws").mkdir()
    (left := tmp_path / ".gfso-nodes-ws" / "p" / "a").mkdir(parents=True)
    (left / "old.txt").write_bytes(b"OLD-WORK\n")
    kept: dict = {}
    x = _fresh(tmp_path, base, kept)
    try:
        assert x.files.read_bytes(str(x.own / "a" / "old.txt")) == b"OLD-WORK\n"
        x.stop()
        subprocess.run(["docker", "volume", "rm", x.volume.state], capture_output=True, check=True)
        x = _fresh(tmp_path, base, kept)
        with pytest.raises(PlaceUnavailable, match=f"its volume {x.volume.state} is gone"):
            x.files.read_bytes(str(x.own / "a" / "old.txt"))
        assert not _volume_stands(x.volume.state), "no volume made of a lost one"
        x.stop()
        WS.drop_execution("p")
        assert not _volume_stands(x.volume.name)
        x = _fresh(tmp_path, base, {})                               # …made again: its record went with its db
        assert x.files.read_bytes(str(x.own / "a" / "old.txt")) is None, "a project made again inherits nothing"
    finally:
        x.stop()
        x.volume.remove()


def _a_project_on_disk(tmp_path, monkeypatch, record: dict) -> None:
    """A server's data dir holding project `p`'s own file with `record` its settings, and the caller's roster and
    declarations naming no execution of it — as `python -m gfso.cli` is typed with PYTHONPATH alone."""
    (data := tmp_path / "data").mkdir()
    (tmp_path / "roster.json").write_text("{}")
    for k, v in (("GFSO_DATA_DIR", data), ("GFSO_AGENTS_PATH", tmp_path / "roster.json"),
                 ("GFSO_EXECUTIONS_PATH", tmp_path / "none.json")):
        monkeypatch.setenv(k, str(v))
    with sqlite3.connect(data / "p.db") as c:
        c.execute("CREATE TABLE settings (key TEXT PRIMARY KEY, value TEXT)")
        c.executemany("INSERT INTO settings VALUES (?, ?)", record.items())
    c.close()


def _exported(tmp_path, capsys) -> tuple:
    rc = _export_places(SimpleNamespace(project="p", dir=str(tmp_path / "out")))
    return rc, capsys.readouterr().err


@pytest.mark.parametrize("legacy", [False, True], ids=["base recorded", "recorded before its base was kept"])
def test_export_places_exports_the_volume_the_projects_own_record_names_whatever_the_callers_roster(
        tmp_path, monkeypatch, capsys, legacy):
    """Measured on a live project: with no roster of its execution in the caller's environment the verb said "its
    places stand on this host already" of a project whose places were in a volume. The system's record decides."""
    base = tmp_path / "w" / "ws"
    monkeypatch.setenv("GFSO_DATA_DIR", str(tmp_path / "data"))       # …the volume's name carries this home
    v = E.Volume(E.container_name("ex", "p"), "ex", base.parent / ".gfso-nodes-ws" / "p", base, "p")
    record = {"volume:places": v.name, "volume:state": v.state, "volume:image": "img:1",
              **({f"place-made:{base.parent / '.gfso-nodes-ws' / 'p' / 'root'}": "1"} if legacy else
                 {"volume:base": str(base)})}
    _a_project_on_disk(tmp_path, monkeypatch, record)
    monkeypatch.setattr(E.Volume, "_labels", staticmethod(lambda n: {E.LABEL: "ex", "gfso.home": E._home()}))
    got = []
    monkeypatch.setattr(E.Volume, "export", lambda self, *a: got.append((self.name, *a)) or [])
    assert _exported(tmp_path, capsys)[0] == 0
    assert got == [(v.name, "img:1", tmp_path / "out" / "p")], "the volume of the base the record names"


def test_export_places_of_a_recorded_volume_that_is_gone_is_said_and_fails(tmp_path, monkeypatch, capsys):
    _a_project_on_disk(tmp_path, monkeypatch, {"volume:places": "gone-v", "volume:base": str(tmp_path / "ws")})
    monkeypatch.setattr(E.Volume, "_labels", staticmethod(lambda n: None))
    rc, err = _exported(tmp_path, capsys)
    assert rc == 1 and "its volume gone-v is gone" in err


@pytest.mark.parametrize("record", [None, {"mode": "solo"}], ids=["no project file", "no volume recorded"])
def test_export_places_with_nothing_recorded_fails_and_says_why(tmp_path, monkeypatch, capsys, record):
    if record is None:
        monkeypatch.setenv("GFSO_DATA_DIR", str(tmp_path / "empty"))
    else:
        _a_project_on_disk(tmp_path, monkeypatch, record)
    rc, err = _exported(tmp_path, capsys)
    assert rc == 1 and ("no project of the name" if record is None else "names no volume") in err


def test_two_projects_name_the_same_place_apart_and_their_doors_and_gateways_too(tmp_path):
    """Short names, the project's left to its group (the author, 2026-10-29): still none shared on the machine."""
    xs = [E.ContainerExecution("e", IMAGE, None, str(tmp_path / "state"), str(tmp_path / "w" / "ws"), p)
          for p in ("p", "q")]
    names = [x.session(str(x.own / "root.a"), None).container for x in xs]
    assert names[0].startswith("executor.root.a-") and names[0] != names[1]
    assert E.gateway_of(xs[0].container) != E.gateway_of(xs[1].container)
