"""What this installation holds in Docker is read by the labels the system sets at every making (`execution.identity`):
per project and node, with a number Docker did not give left None; a server's sweep of leftovers removes its own
installation's containers alone."""
import json
import threading
import time
import subprocess

import pytest
from fastapi.testclient import TestClient

from gfso.adapters import execution as E, resources as R
from gfso.api.server import create_app
from gfso.runtime import ProjectRegistry
from gfso.adapters.execution import ContainerExecution


def _ps(i, name, home, project="", role="", node="", agent="", service="", state="running"):
    return "\t".join((i, name, state, home, project, role, node, agent, service))


@pytest.fixture
def docker(monkeypatch):
    """Docker as the view asks it, answered from `said` — the cache emptied before and after."""
    said, asked = {}, []
    monkeypatch.setattr(R, "_read", {})
    monkeypatch.setattr(R, "watch", lambda: None)              # …the poller is the server's, not a test's
    monkeypatch.setattr(R, "_docker", lambda *a: asked.append(a) or said.get(a[0], []))
    return said, asked


def _held(*a):
    """The reading as a page gets it, after the poller's turn (`resources.refresh`)."""
    R.refresh()
    return R.held(*a)


def test_a_page_never_asks_docker_it_gets_the_last_reading(docker, monkeypatch):
    """The author: «интерфейс должен подгружать то что есть в бэке а не что то тригерить самим чтением»."""
    _, asked = docker
    monkeypatch.setattr(R, "watch", lambda: None)
    got = R.held(set())
    assert not asked and got["read_at"] == {"containers": None, "stats": None, "disk": None}, "a read asked Docker"
    R.refresh()
    n = len(asked)
    assert R.held(set())["read_at"]["containers"] and len(asked) == n, "the stored reading, at once"


class _Proc:
    """A stream of Docker's stood in for: running, saying nothing."""
    stdout = ()

    def poll(self):
        return None

    def kill(self):
        pass

    def wait(self):
        return 0


def _streams():
    return R.Live(spawn=lambda argv: _Proc())


def test_docker_tells_what_changed_the_server_reads_that_and_tells_the_open_page(docker, monkeypatch):
    """The author: «это же сам докер должен отдавать … обновления от него вообще хуком можно сделать»."""
    said, asked = docker
    told = []
    monkeypatch.setattr(R, "LISTENERS", [lambda: told.append(R.held(set())["read_at"]["containers"])])
    live = _streams()
    live.tick()
    assert live.procs and len(told) == 1 and told[0], "the first reading, pushed"
    n = len(asked)
    live.tick()
    assert len(asked) == n and len(told) == 1, "no event, no read; nothing new, nothing pushed"
    live.events(iter([f"container\tab\t{E._home()}\n"]))
    live.tick()
    assert [a[0] for a in asked[n:]] == ["ps"] and len(told) == 2, "a container's event: its list read again, told"
    live.stats(iter(["\x1b[Hab\t1.5%\t10MiB / 4GiB\t3\x1b[K\n", "\x1b[Hab\t2.0%\t11MiB / 4GiB\t3\x1b[K\n"]))
    assert R._read["stats"][1] == {"ab": (1.5, 10 * 2 ** 20, 3)} and R._read["stats"][2] is False, \
        "a frame per home of the cursor; the stream's end said as a read not fresh"


def test_an_idle_server_keeps_no_stream_of_docker(docker, monkeypatch):
    monkeypatch.setattr(R, "LISTENERS", [])
    live = _streams()
    live.tick()
    assert live.procs, "nothing read yet: the streams start"
    monkeypatch.setattr(R, "_asked", [float("-inf")])
    live.tick()
    assert not live.procs, "nobody reads: Docker is asked nothing"
    monkeypatch.setattr(R, "LISTENERS", [lambda: None])
    live.tick()
    assert live.procs, "an open page keeps them"


def test_sizes_read_as_docker_prints_them():
    assert R.size("13.6MB") == 13_600_000 and R.size("752KiB") == 752 * 1024 and R.size("1.5GiB") == 3 * 2 ** 29
    assert R.size("0B") == 0 and R.size("N/A") is None and R.size("") is None and R.size("7 parsecs") is None


def test_a_project_is_read_per_node_by_its_labels_and_a_missing_number_stays_none(docker):
    said, _ = docker
    h = E._home()
    said["ps"] = [_ps("a1", "executor.root.x-1", h, "p", "executor", "root.x", "exec-2", "executors"),
                  _ps("a2", "judge.root.x.r_1-2", h, "p", "judge", "root.x", "val", "judges"),
                  _ps("a3", "gfso-e-p", h, "p", "system", "", "", "system"),
                  _ps("a4", "door-3", h, "p", "", "", "", "door"),
                  _ps("b1", "executor.root-4", "otherhome", "p", "executor", "root"),
                  _ps("c1", "gfso-e-old", "", "", "system")]
    said["stats"] = ["a1\t12.5%\t200MiB / 19GiB\t9", "a2\t0.00%\t1MiB / 19GiB\t2", "a3\t1.0%\t2MiB / 19GiB\t2",
                     "c1\t3.0%\t4MiB / 19GiB\t2"]                   # …a4 not running: no numbers
    said["system"] = [json.dumps({"Volumes": [
        {"Name": "gfso-e-p-k-v", "Labels": f"gfso.execution=e,gfso.home={h},gfso.project=p", "Size": "1MB"},
        {"Name": "gfso-e-p-k-state", "Labels": f"gfso.execution=e,gfso.home={h},gfso.project=p", "Size": "N/A"},
        {"Name": "gfso-e-gone-k-v", "Labels": f"gfso.execution=e,gfso.home={h},gfso.project=gone", "Size": "3MB"},
        {"Name": "theirs-v", "Labels": "gfso.home=otherhome,gfso.project=p", "Size": "9GB"}]})]
    said["info"] = ["24 20973101056"]
    got = _held({"p"})
    assert got["read"] == {"containers": True, "stats": True, "disk": True}
    assert got["machine"] == {"cpus": 24, "memory_bytes": 20973101056}
    assert [p["project"] for p in got["projects"]] == ["gone", "p"], "another installation's holds are not ours"
    gone, p = got["projects"]
    assert gone["known"] is False and gone["disk_bytes"] == 3_000_000 and gone["containers"]["standing"] == 0
    assert p["known"] is True and p["disk_bytes"] == 1_000_000 and p["disk_counted"] == "1/2", "N/A is not 0"
    assert p["containers"] == {"standing": 4, "running": 4, "busy": 1, "busy_counted": "3/4"}
    assert {k: v["busy"] for k, v in p["by_role"].items()} == {"door": None, "executor": 1, "judge": 0, "system": 0}
    [node] = p["nodes"]
    assert node["node"] == "root.x" and node["memory_bytes"] == 201 * 2 ** 20 and node["cpu_percent"] == 12.5
    assert {c["agent_id"] for c in node["containers"]} == {"exec-2", "val"}
    assert {c["name"] for c in p["system"]} == {"gfso-e-p", "door-3"}
    door = next(c for c in p["system"] if c["role"] == "door")
    assert door["busy"] is None and door["memory_bytes"] is None, "a number Docker did not give stays None"
    assert p["memory_bytes_counted"] == "3/4"
    assert got["older_build"]["containers"] == 1 and got["older_build"]["memory_bytes"] == 4 * 2 ** 20


def test_docker_is_asked_once_while_a_reading_stands(docker):
    _, asked = docker
    _held(set())
    _held(set())
    assert sum(a[0] == "stats" for a in asked) == 1 and sum(a[0] == "system" for a in asked) == 1


def test_every_container_the_system_starts_carries_its_installation_and_project(tmp_path):
    (base := tmp_path / "ws").mkdir()
    x = ContainerExecution("e3-linux", "img", None, str(tmp_path / "state"), str(base), "a project")
    mine = {f"gfso.execution=e3-linux", "gfso.project=a_project", f"gfso.home={E._home()}"}
    s = x.session(str(x.own / "root.n"), "exec")
    for args in (x.run_args(), s.run_args(), x.way.gateway_args()[0]):
        assert mine <= set(args), args
    assert x.volume.labels == E.identity("e3-linux", "a_project")


def test_a_servers_sweep_removes_its_own_installations_containers_alone(monkeypatch):
    ran = []
    out = f"mine {E._home()}\ntheirs 0badc0de\nold\n"
    monkeypatch.setattr(E, "run", lambda args, **kw: ran.append(args) or subprocess.CompletedProcess(
        args, 0, out if args[:2] == ["docker", "ps"] else "", ""))
    monkeypatch.setattr(E.shutil, "which", lambda p: "docker")
    monkeypatch.setattr(E, "_keep_logs", lambda ids: None)
    E.end_leftovers()
    assert ["docker", "rm", "-f", "mine", "old"] in [a[:5] for a in ran if a[:2] == ["docker", "rm"]]
    assert not [a for a in ran if "theirs" in a], "another installation's running container is not ours to end"
    prune = next(a for a in ran if a[:3] == ["docker", "network", "prune"])
    assert f"label=gfso.home={E._home()}" in prune


def test_a_door_its_server_running_is_never_busy_a_stopped_container_holds_nothing_and_the_keeper_is_the_systems(
        docker):
    said, _ = docker
    h = E._home()
    said["ps"] = [_ps("d", "door-1", h, "p", "", "", "", "door"),
                  _ps("s", "system.state-2", h, "p", "system", "state", "", "systems"),
                  _ps("x", "executor.n-3", h, "p", "executor", "n", "", "executors", state="exited")]
    said["stats"] = ["d	0.16%	20MiB / 19GiB	3", "s	0.00%	1MiB / 19GiB	2"]
    said["system"] = [json.dumps({"Volumes": []})]
    [p] = _held({"p"})["projects"]
    door = next(c for c in p["system"] if c["role"] == "door")
    assert door["busy"] is None, "a door's own server is its work, not a call (measured idle at 3 PIDs)"
    assert {c["name"] for c in p["system"]} == {"door-1", "system.state-2"} and [n["node"] for n in p["nodes"]] == ["n"]
    stopped = p["nodes"][0]["containers"][0]
    assert stopped["busy"] is False and stopped["memory_bytes"] == 0 and p["memory_bytes_counted"] == "3/3"
    assert p["containers"] == {"standing": 3, "running": 2, "busy": 0, "busy_counted": "2/3"}


def test_a_read_docker_did_not_answer_is_said_and_the_one_before_it_serves(docker, monkeypatch):
    said, _ = docker
    h = E._home()
    said["ps"] = [_ps("a", "executor.n-1", h, "p", "executor", "n")]
    said["stats"] = []
    said["system"] = [json.dumps({"Volumes": []})]
    first = _held(set())
    assert first["read"] == {"containers": True, "stats": True, "disk": True}
    taken = first["read_at"]
    assert all(isinstance(t, float) and abs(t - time.time()) < 60 for t in taken.values()), taken
    monkeypatch.setattr(R, "_docker", lambda *a: None)                # …the daemon gone
    monkeypatch.setattr(R, "FRESH", -1.0)
    monkeypatch.setattr(R, "DISK_FRESH", -1.0)
    got = _held(set())
    assert got["read"] == {"containers": False, "stats": False, "disk": False}
    assert got["projects"][0]["containers"]["standing"] == 1, "the reading before it, said as not fresh"
    assert got["read_at"] == taken, "a kept reading keeps the time it was taken, not the failed read's"
    R._read.clear()
    said["system"] = [json.dumps({"Volumes": [
        {"Name": "v", "Labels": f"gfso.home={h},gfso.project=p,gfso.project_id={'a' * 32}", "Size": "1MB"}]})]
    monkeypatch.setattr(R, "_docker", lambda *a: said.get(a[0]) if a[0] == "system" else None)
    got = _held(set())
    assert got["read"]["containers"] is False and got["projects"][0]["containers"] is None, "never listed: no 0"
    assert got["projects"][0]["project_ids"] == ["a" * 32], "the id DELETE /api/resources/orphans/{id} takes"
    assert got["read_at"]["containers"] is None and isinstance(got["read_at"]["disk"], float)


def test_docker_not_installed_is_no_answer_not_an_error(monkeypatch):
    def gone(*a, **kw):
        raise FileNotFoundError("docker")
    monkeypatch.setattr(R, "run", gone)
    assert R._docker("ps") is None
    monkeypatch.setattr(R, "run", lambda *a, **kw: (_ for _ in ()).throw(subprocess.TimeoutExpired("docker", 20)))
    assert R._docker("ps") is None


def test_any_spelling_of_a_held_project_is_known_and_no_removal_takes_a_name(tmp_path, monkeypatch):
    """An orphan named by its project's NAME matched a held project under another spelling (critics over 4d4aeed,
    8f6dfae, run): removal takes an id alone (`resources.remove_orphan`), and a name is no id."""
    monkeypatch.setenv("GFSO_DATA_DIR", str(tmp_path))
    (tmp_path / "Alpha.db").write_bytes(b"")
    monkeypatch.setattr(R, "_read", {})
    monkeypatch.setattr(R, "_docker", lambda *a: [json.dumps({"Volumes": [
        {"Name": "v", "Labels": f"gfso.home={E._home()},gfso.project=alpha", "Size": "1MB"}]})] if a[0] == "system"
        else [])
    reg = ProjectRegistry()
    c = TestClient(create_app(reg.engine(), registry=reg), base_url="http://127.0.0.1:8000")
    monkeypatch.setattr(R, "watch", lambda: None)              # …the server's reading, taken by the test's own turn
    R.refresh()
    assert [(p["project"], p["known"]) for p in c.get("/api/resources").json()["projects"]] == [("alpha", True)]
    assert c.delete("/api/resources/orphans/alpha").status_code == 404


def test_a_reader_never_waits_on_docker_while_the_server_reads_it(docker, monkeypatch):
    """The lock guards the store, not Docker's answer: a page waited 8.8 s behind a slow `system df` (critic)."""

    gate = threading.Event()
    monkeypatch.setattr(R, "_docker", lambda *a: gate.wait(10) and [])
    reading = threading.Thread(target=R.refresh, daemon=True)
    reading.start()
    t0 = time.perf_counter()
    R.held(set())
    assert time.perf_counter() - t0 < 1.0, "a read of the reading waited on Docker"
    gate.set()
    reading.join(10)


def test_this_installations_volume_is_heard_by_its_name_and_no_one_elses_event_is(docker):
    """A volume's event carries no label (Docker 29, live): filtered by the label, none was ever heard, and a dropped
    project's volumes stood in the view up to a minute (critic). Another program's, or another home's, reads nothing."""
    live, h = _streams(), E._home()
    live.events(iter([f"volume\tgfso-e-p-{h}-abc123-v\t\n"]))
    assert live.stale == {"ps", "volumes"}
    live.stale = set()
    live.events(iter(["volume\ttheirs\t\n", f"volume\tgfso-e-p-otherhom-abc123-v\t\n", "container\tab\totherhom\n",
                      "container\tab\t\n"]))
    assert live.stale == set()


def test_a_stream_dying_at_once_is_tried_again_ever_later_up_to_a_minute(docker, monkeypatch):
    """Its lifetime decides, not the wait it then stood: measured so, the wait fell back to 1 s once it reached 16
    (critic, simulated)."""
    clock = [1000.0]
    monkeypatch.setattr(R.time, "perf_counter", lambda: clock[0])
    monkeypatch.setattr(R, "LISTENERS", [lambda: None])
    dead = type("D", (_Proc,), {"poll": lambda s: 1})
    live, starts = R.Live(spawn=lambda argv: dead()), []
    for _ in range(600):
        n = len(live.procs) and live.started
        live.tick()
        if live.started != n:
            starts.append(clock[0])
        clock[0] += 1.0
    gaps = [b - a for a, b in zip(starts, starts[1:])]
    assert max(gaps) == 60 and gaps[-1] == 60, gaps
