"""An orphan's volumes are removed by the id its project's record made and its volumes carry — never by its name: a held
project under any spelling of it, a record that does not read, a data dir that does not list, a volume with no id and
a volume a container mounts are each left standing, the cause said (the author, 2026-10-29: «правильный бек»; two
removals by name matched held projects, critics over 4d4aeed, 8f6dfae)."""
import json
import re
import subprocess
import time

import pytest
from fastapi.testclient import TestClient

import gfso.runtime as RT
from gfso.adapters import execution as E, resources as R
from gfso.api.server import create_app
from gfso.core.types import PROJECT_ID
from gfso.runtime import ProjectRegistry
from tests.test_a_session_holds_only_its_own_place import IMAGE, _docker, project  # noqa: F401

live = pytest.mark.skipif(not _docker(), reason=f"needs docker and {IMAGE}")
DEAD = "d" * 32


def _docker_out(*args) -> str:
    return subprocess.run(["docker", *args], capture_output=True, text=True).stdout


@pytest.fixture
def home(tmp_path, monkeypatch):
    """An installation of its own (its data dir, its home), its server, and the volumes and containers this test made
    — recorded by name and removed by those names alone."""
    monkeypatch.setenv("GFSO_DATA_DIR", str(tmp_path))
    monkeypatch.setattr(R, "_read", {})
    reg = ProjectRegistry()
    made = {"volumes": [], "containers": []}

    def volume(project, pid=None) -> str:
        name = f"gfso-orphan-test-{time.time_ns()}"
        labels = {E.HOME: E.installation(), E.PROJECT: project, **({E.ID: pid} if pid else {})}
        subprocess.run(["docker", "volume", "create", *[a for k, v in labels.items() for a in ("--label", f"{k}={v}")],
                        name], check=True, capture_output=True)
        made["volumes"].append(name)
        return name

    def mounting(v) -> None:
        made["containers"].append(_docker_out("create", "--mount", f"type=volume,src={v},dst=/v", IMAGE, "true").strip())

    c = TestClient(create_app(reg.engine(), registry=reg), base_url="http://127.0.0.1:8000")
    yield reg, c, volume, mounting
    for eng in reg._engines.values():
        eng.stop()
    if made["containers"]:
        subprocess.run(["docker", "rm", "-f", *made["containers"]], capture_output=True)
    for v in made["volumes"]:
        subprocess.run(["docker", "volume", "rm", "-f", v], capture_output=True)


def _standing(*names) -> set:
    return set(names) & set(_docker_out("volume", "ls", "-q").split())


def test_a_projects_record_makes_its_id_once_and_keeps_it(tmp_path, monkeypatch):
    monkeypatch.setenv("GFSO_DATA_DIR", str(tmp_path))
    reg = ProjectRegistry()
    reg.engine("p").stop()
    first = dict(ProjectRegistry().ids())["p"]
    assert re.fullmatch(r"[0-9a-f]{32}", first or "")
    reg2 = ProjectRegistry()
    reg2.engine("p").stop()
    assert dict(reg2.ids())["p"] == first, "made once: a reopening keeps it"


@live
def test_live_a_volume_is_made_with_its_projects_id(project):  # noqa: F811
    record = {PROJECT_ID: "ab" * 16}
    project.volume.record = (record.get, record.__setitem__)
    assert project.run(["true"], cwd=str(project.base), timeout=120).returncode == 0
    for v in (project.volume.name, project.volume.state):
        assert json.loads(_docker_out("volume", "inspect", "-f", "{{json .Labels}}", v))[E.ID] == "ab" * 16


@live
def test_live_a_true_orphans_volumes_go_by_their_names_and_a_held_projects_stand(home):
    reg, c, volume, _ = home
    held = volume("p", reg.engine("p").graph.setting(PROJECT_ID))
    gone = [volume("gone", DEAD), volume("gone", DEAD)]
    assert {v["name"]: v["project_id"] for p in c.get("/api/resources").json()["projects"] for v in p["volumes"]}[
        gone[0]] == DEAD
    got = c.delete(f"/api/resources/orphans/{DEAD}")
    assert got.status_code == 200 and sorted(got.json()["removed"]) == sorted(gone) and got.json()["refused"] == {}
    assert _standing(held, *gone) == {held}
    assert c.delete(f"/api/resources/orphans/{reg.engine('p').graph.setting(PROJECT_ID)}").status_code == 409
    assert _standing(held) == {held}


@live
def test_live_a_held_project_under_another_spelling_is_never_removable(home):
    """`Alpha` held: volumes labelled `alpha` carrying its id are held by the id; those carrying another id (a project
    made again under the old name took the old one's volumes) are held by the name a held project mounts them by. A
    record renamed (`Beta.db` holds the id of volumes labelled `gamma`, a name nothing holds): held by the id alone."""
    reg, c, volume, _ = home
    alpha = reg.engine("Alpha").graph.setting(PROJECT_ID)
    by_id, by_name = volume("alpha", alpha), volume("alpha", DEAD)
    assert c.delete(f"/api/resources/orphans/{alpha}").status_code == 409
    got = c.delete(f"/api/resources/orphans/{DEAD}").json()
    assert got["removed"] == [] and "held under that name" in got["refused"][by_name]
    assert _standing(by_id, by_name) == {by_id, by_name}
    beta = reg.engine("Beta").graph.setting(PROJECT_ID)
    renamed = volume("gamma", beta)
    assert c.delete(f"/api/resources/orphans/{beta}").status_code == 409 and _standing(renamed) == {renamed}


@live
def test_live_a_record_that_does_not_read_or_a_dir_that_does_not_list_removes_nothing(home, tmp_path, monkeypatch):
    reg, c, volume, _ = home
    orphan = volume("gone", DEAD)
    (tmp_path / "broken.db").write_bytes(b"not a database, " * 64)
    got = c.delete(f"/api/resources/orphans/{DEAD}")
    assert got.status_code == 409 and "broken.db" in got.json()["detail"] and _standing(orphan) == {orphan}
    (tmp_path / "broken.db").unlink()
    listdir = RT.os.listdir

    def denied(p):
        if str(p) == str(tmp_path):
            raise PermissionError(13, "Access is denied", str(p))
        return listdir(p)
    monkeypatch.setattr(RT.os, "listdir", denied)
    got = c.delete(f"/api/resources/orphans/{DEAD}")
    assert got.status_code == 409 and "denied" in got.json()["detail"] and _standing(orphan) == {orphan}
    monkeypatch.setattr(RT.os, "listdir", listdir)
    assert c.delete(f"/api/resources/orphans/{DEAD}").json()["removed"] == [orphan], "the refusal was the cause"


@live
def test_live_a_volume_with_no_id_is_never_removed(home):
    _, c, volume, _ = home
    bare, orphan = volume("gone"), volume("gone", DEAD)
    assert c.delete(f"/api/resources/orphans/{DEAD}").json()["removed"] == [orphan]
    assert _standing(bare) == {bare}
    [row] = [p for p in c.get("/api/resources").json()["projects"] if p["project"] == "gone"]
    assert [(v["name"], v["project_id"]) for v in row["volumes"]] == [(bare, None)]


@live
def test_live_a_volume_any_container_mounts_is_not_removed(home):
    _, c, volume, mounting = home
    used, free = volume("gone", DEAD), volume("gone", DEAD)
    mounting(used)                                                   # …created, never started
    got = c.delete(f"/api/resources/orphans/{DEAD}").json()
    assert got["removed"] == [free] and "mounted by" in got["refused"][used] and _standing(used, free) == {used}


@live
def test_live_a_project_opened_under_the_volumes_name_while_removing_keeps_them(home):
    """The registry is read again before each volume: `gamma` opened after the act's first look (critic over the act, a
    hook opening it mid-loop) mounts its volumes by name, and they stand."""
    _, _, volume, _ = home
    orphan = volume("gamma", DEAD)
    reads = iter([[], [("gamma", "e" * 32)]])
    got = R.remove_orphan(DEAD, lambda: next(reads))
    assert got["removed"] == [] and "held under that name" in got["refused"][orphan] and _standing(orphan) == {orphan}
