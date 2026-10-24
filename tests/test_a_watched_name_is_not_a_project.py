"""Opening the page on a name that is no project must not make it one. The live feed (`/ws/events`)
read its project with the registry's default `create=True`, so a tab opened on a mistyped or not-yet-
existing name left an empty project behind on the shared server — two appeared in one UI session
(2026-10-24) — while every HTTP read of the same name answered 404 and created nothing."""
import os

from fastapi.testclient import TestClient
from starlette.websockets import WebSocketDisconnect

from gfso.api.server import create_app
from gfso.runtime import ProjectRegistry


def test_the_live_feed_on_an_unknown_name_closes_and_creates_nothing(monkeypatch, tmp_path):
    monkeypatch.setenv("GFSO_DATA_DIR", str(tmp_path))
    monkeypatch.delenv("GFSO_PROJECT", raising=False)
    monkeypatch.setenv("GFSO_STORAGE", "memory")
    reg = ProjectRegistry()
    client = TestClient(create_app(reg.engine(), registry=reg))
    try:
        with client.websocket_connect("/ws/events?project=no-such-goal"):
            pass                           # connecting is all a tab does before it waits
    except WebSocketDisconnect as closed:
        assert closed.code == 4404
    assert not os.path.exists(tmp_path / "no-such-goal.db"), "watching a name created the project"
    assert client.get("/api/graph?project=no-such-goal").status_code == 404
