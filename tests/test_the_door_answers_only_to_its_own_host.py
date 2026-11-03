"""The server has no login, so what keeps a stranger's web page off it is the browser's same-origin rule — and a
name whose DNS is re-pointed at 127.0.0.1 makes the stranger's page same-origin. The door therefore refuses a
Host it does not own, and a socket a browser opened from a page that is not this server's (2026-10-27)."""
import re
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from starlette.websockets import WebSocketDisconnect

from gfso import config
from gfso.api.server import create_app
from gfso.runtime import ProjectRegistry


@pytest.fixture
def client(monkeypatch, tmp_path):
    monkeypatch.setenv("GFSO_DATA_DIR", str(tmp_path))
    monkeypatch.delenv("GFSO_PROJECT", raising=False)
    monkeypatch.setenv("GFSO_STORAGE", "memory")
    reg = ProjectRegistry()
    return TestClient(create_app(reg.engine(), registry=reg))


@pytest.mark.parametrize("host", ["127.0.0.1:8000", "localhost:8000", "[::1]:8000", "testserver"])
def test_its_own_names_are_answered(client, host):
    assert client.get("/api/tools", headers={"host": host}).status_code == 200


def test_what_the_door_answers_holds_the_page_s_policy(client):
    """Escaping alone stood between what agents write and a script on a page holding every verb (a critic, read); in a real
    browser a planted handler and script ran with no policy and neither runs with this one."""
    h = client.get("/", headers={"host": "127.0.0.1:8000"}).headers
    policy = h["content-security-policy"]
    assert "script-src 'self' https://unpkg.com;" in policy and "object-src 'none'" in policy and "'unsafe-eval'" not in policy
    assert "frame-ancestors 'none'" in policy and h["x-content-type-options"] == "nosniff"


@pytest.mark.parametrize("host", ["rebind.example:8000", "127.0.0.1.rebind.example", ""])
def test_a_foreign_host_is_refused_before_any_verb(client, host):
    r = client.post("/api/run/create_task", headers={"host": host}, json={"task_id": "x"})
    assert r.status_code == 403


def test_a_socket_from_a_foreign_page_is_closed(client):
    with pytest.raises(WebSocketDisconnect) as e:
        with client.websocket_connect("/ws/events", headers={"origin": "https://stranger.example"}):
            pass
    assert e.value.code == 4403


@pytest.mark.parametrize("origin", [None, "http://127.0.0.1:8000"])
def test_a_socket_from_its_own_page_or_no_page_opens(client, origin):
    headers = {"origin": origin} if origin else {}
    with client.websocket_connect("/ws/events", headers=headers):
        pass


def test_every_script_the_page_fetches_from_elsewhere_carries_its_hash():
    """The page can drive every verb, so code a CDN serves in place of the pinned file must not run in it."""
    page = (Path(__file__).resolve().parents[1] / "gfso" / "web" / "index.html").read_text(encoding="utf-8")
    remote = re.findall(r"<script[^>]*\bsrc=\"https?://[^>]*>", page)
    assert remote and all('integrity="sha384-' in t and 'crossorigin="anonymous"' in t for t in remote)


def test_a_foreign_page_writes_nothing_even_with_a_body_no_preflight_stops(client):
    r = client.post("/api/shutdown", headers={"origin": "https://stranger.example"})
    assert r.status_code == 403


def test_a_foreign_page_may_still_load_a_read_and_its_own_page_may_write(client):
    assert client.get("/api/tools", headers={"origin": "https://stranger.example"}).status_code == 200
    r = client.post("/api/run/create_task", headers={"host": "127.0.0.1:9000", "origin": "http://127.0.0.1:9000"},
                    json={"task_id": "x"})
    assert r.status_code != 403


def test_a_socket_from_its_own_page_on_another_port_opens(client):
    with client.websocket_connect("/ws/events", headers={"host": "127.0.0.1:9000", "origin": "http://127.0.0.1:9000"}):
        pass


@pytest.mark.parametrize("site", ["cross-site", "same-site"])
def test_nothing_a_browser_marks_as_from_another_site_is_served(client, site):
    """An image tag sends no Origin; a read with `?project=` wakes that project's engine and its clock."""
    assert client.get("/api/tools", headers={"sec-fetch-site": site}).status_code == 403


@pytest.mark.parametrize("site", ["same-origin", "none"])
def test_its_own_page_and_a_typed_address_are_served(client, site):
    assert client.get("/api/tools", headers={"sec-fetch-site": site}).status_code == 200


def test_the_name_a_server_is_started_on_is_answered(client, monkeypatch):
    monkeypatch.setenv("GFSO_ALLOWED_HOSTS", "testserver")
    config.admit_host("box.lan")
    assert client.get("/api/tools", headers={"host": "box.lan:8000"}).status_code == 200


def test_its_own_name_served_over_tls_in_front_may_write_and_a_stranger_may_not(client, monkeypatch):
    """`tailscale serve` hands the page over https under the name the server answers to; the page is its own."""
    monkeypatch.setenv("GFSO_ALLOWED_HOSTS", "kir.tail.ts.net")
    own = {"host": "kir.tail.ts.net", "origin": "https://kir.tail.ts.net"}
    assert client.post("/api/run/create_task", headers=own, json={"task_id": "x"}).status_code != 403
    stranger = {**own, "origin": "https://stranger.example"}
    assert client.post("/api/run/create_task", headers=stranger, json={"task_id": "x"}).status_code == 403
