"""A part whose split is deferred on named parts says so to the page: the node's read carries the engine's deferral —
the parts it names, those whose results do not stand yet, and its reason — so the panel says "split after <producer>"
instead of only the Dep wait (ON_THE_FLY_MODE §5 item 5, ui stream 2026-11-13).

CONTROL: drop `split_after` from `/api/tasks/{id}` and the first test goes red."""
from fastapi.testclient import TestClient

from gfso.api.server import create_app
from tests.test_a_deferred_split_waits_for_the_result_it_needs import WHY, _defer, _pass, _plan


def _read(e, k):
    return TestClient(create_app(e)).get(f"/api/tasks/{k}").json()


def test_a_deferred_part_names_the_parts_its_split_waits_on_until_they_pass(monkeypatch, tmp_path):
    monkeypatch.setenv("GFSO_DATA_DIR", str(tmp_path))
    e = _plan()
    _defer(e, "root.parser")
    got = _read(e, "root.checker")["split_after"]
    assert got["producers"] == ["root.parser"] and got["waits_on"] == ["root.parser"] and got["why"] == WHY, got
    _pass(e, "root.parser")
    got = _read(e, "root.checker")["split_after"]
    assert got["producers"] == ["root.parser"] and got["waits_on"] == [], got


def test_a_part_with_no_deferral_carries_none(monkeypatch, tmp_path):
    monkeypatch.setenv("GFSO_DATA_DIR", str(tmp_path))
    e = _plan()
    assert _read(e, "root.docs")["split_after"] is None
