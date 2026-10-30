"""An open page learns that a process of the server started or ended, and that a call's spend was booked, the moment it
happens — pushed on its live feed — instead of re-reading `/api/runtime` every 5 s and the ledger every 30 s, intervals
nothing justified (the author, 2026-10-25: «где то 5 секунд где то 30 … а как ты обоснуешь что это оптимальное»)."""
from fastapi.testclient import TestClient

from gfso import inflight
from gfso.adapters import resources as R
from gfso.api.server import create_app
from gfso.runtime import ProjectRegistry


def _client(monkeypatch, tmp_path):
    monkeypatch.setenv("GFSO_DATA_DIR", str(tmp_path))
    monkeypatch.delenv("GFSO_PROJECT", raising=False)
    monkeypatch.setenv("GFSO_STORAGE", "memory")
    reg = ProjectRegistry()
    return reg.engine(), TestClient(create_app(reg.engine(), registry=reg))


def test_a_process_starting_and_ending_reaches_the_open_page(monkeypatch, tmp_path):
    eng, client = _client(monkeypatch, tmp_path)
    with client.websocket_connect("/ws/events") as ws:
        with inflight._inflight("validate_result", eng, "r1"):
            started = ws.receive_json()
            assert started["type"] == "inflight"
            assert [(w["verb"], w["task_id"]) for w in started["in_flight"]] == [("validate_result", "r1")]
        ended = ws.receive_json()
        assert ended == {"type": "inflight", "in_flight": []}
    assert not inflight.LISTENERS, "a closed page left its listener behind"


def test_a_booked_call_reaches_the_open_page(monkeypatch, tmp_path):
    eng, client = _client(monkeypatch, tmp_path)
    with client.websocket_connect("/ws/events") as ws:
        eng.record_llm_usage("executor", [{"model": "m", "input_tokens": 1, "output_tokens": 1}], node_id="r1")
        said = ws.receive_json()
        assert said["type"] == "pipeline" and said["source"] == "usage"
    assert all(p["source"] != "usage" for p in eng.pipeline_log()), "the push is not a line of the run's history"


def test_a_new_reading_of_docker_reaches_the_open_page(monkeypatch, tmp_path):
    """The author: «интерфейс не должен тригерить новый опрос … отобразить текущее число» — the server's poller tells
    each open page the reading it stored, the body `GET /api/resources` answers."""
    monkeypatch.setattr(R, "_read", {})
    monkeypatch.setattr(R, "watch", lambda: None)
    monkeypatch.setattr(R, "_docker", lambda *a: [])
    _, client = _client(monkeypatch, tmp_path)
    live = R.Live(spawn=lambda argv: type("P", (), {"stdout": (), "poll": lambda s: None, "kill": lambda s: None, "wait": lambda s: 0})())
    with client.websocket_connect("/ws/events") as ws:
        live.tick()
        said = ws.receive_json()
        assert said["type"] == "resources" and said["read_at"]["containers"] and "projects" in said
    assert not R.LISTENERS, "a closed page left its listener behind"
