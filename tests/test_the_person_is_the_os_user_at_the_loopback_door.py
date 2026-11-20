"""On a server bound to loopback the person is whoever the OS says owns the other end of the call's connection: a
process of the server's own OS user. His page moves with no sign-in step; another OS user of the machine, or a peer whose
owner the OS will not name, is served nothing — no move, no read, no socket — unless it carries a credential this
installation issued (a front run as the system, as `tailscale serve` is). `--protected` (`page_auth` `key`) asks the
page's sign-in as well; a front and a bind past loopback answer as before. Another OS user's call is shown here by the
door's lookup made to answer "someone else": one OS user runs this suite."""
import asyncio
import contextlib
import json
import socket
from pathlib import Path
import threading
import time
import urllib.request

import psutil
import pytest
import uvicorn
from starlette.testclient import TestClient
from starlette.websockets import WebSocketDisconnect

import gfso
from gfso import cli, config, peer, serverctl, signin
from gfso.adapters.llm.stub import StubLLM
from gfso.api.server import _OPEN_SENDS, create_app
from gfso.config import CALLER
from gfso.mcp.server import create_server
from gfso.runtime import ProjectRegistry
from gfso.core.types import Signal, TaskId
from tests.support import criterion, make_engine

SPEC = {"description": "node", "criteria": [criterion("k", "keep")]}
LOOPBACK = "http://127.0.0.1:8000"
PAGE = {"Origin": LOOPBACK, "Sec-Fetch-Site": "same-origin"}
REFUSED = {"refused": True, "page_auth": "key", "error": signin._STRANGER}


def _a_reader(c, e) -> None:
    """Reads the graph, moves nothing: what a call no process of the person's makes is served with no credential."""
    assert c.get("/api/graph").status_code == 200
    out = c.post("/api/run/create_task", json={"task_id": "n", "spec": SPEC}).json()
    assert out.get("refused") and "front" in out["error"] and e.graph.get_task(TaskId("n")) is None, out


def _a_relay(monkeypatch):
    monkeypatch.setattr(signin, "peer_is_a_relay", lambda peer, server: True, raising=False)


@pytest.fixture
def door():
    e = make_engine(llm=StubLLM(), validate_signals=True)
    e.start()
    yield e, create_app(e)
    e.stop()


def _client(app, base=LOOPBACK, **headers) -> TestClient:
    c = TestClient(app, base_url=base, headers=headers)
    c.cookies.clear()
    return c


def _someone_else(monkeypatch):
    monkeypatch.setattr(signin, "peer_is_ours", lambda peer, server: False, raising=False)


@pytest.mark.parametrize("headers", [{}, PAGE], ids=["a client", "a page"])
def test_a_call_no_process_of_the_persons_makes_reads_and_moves_nothing_by_default(door, monkeypatch, headers):
    """A phone through `tailscale serve`, a device on the LAN, another account of this machine: the graph is open to
    read, a move needs a name (the author, 2026-11-16: «чтение графа - вообще по канону может быть во многих случаях
    публичной базой»; «ходы пускай и будут со входом»)."""
    e, app = door
    _someone_else(monkeypatch)
    _a_reader(_client(app, **headers), e)


@pytest.mark.parametrize("headers", [{}, PAGE], ids=["a client", "a page"])
def test_protected_or_a_port_forwarders_call_reads_nothing_and_moves_nothing(door, monkeypatch, headers):
    for closed in ("protected", "relay"):
        with monkeypatch.context() as m:
            m.setattr(signin, "peer_is_ours", lambda peer, server: False, raising=False)
            if closed == "protected":
                m.setenv("GFSO_PAGE_AUTH", "key")
            else:
                m.setattr(signin, "peer_is_a_relay", lambda peer, server: True, raising=False)
            e, app = door
            c = _client(app, **headers)
            assert c.post("/api/run/create_task", json={"task_id": "n", "spec": SPEC}).json()["error"] == signin._STRANGER
            assert e.graph.get_task(TaskId("n")) is None
            for read in ("/api/graph", "/api/whoami", "/api/runtime", "/mcp"):
                out = c.get(read)
                assert out.status_code == 403 and out.json()["error"] == signin._STRANGER, (closed, read)
            with pytest.raises(WebSocketDisconnect) as gone:
                with c.websocket_connect("/ws/events"):
                    pass
            assert gone.value.code == 4403


@pytest.mark.parametrize("closed", ["protected", "relay"])
def test_a_closed_call_is_served_the_pages_shell_and_refused_every_api(door, monkeypatch, closed):
    """The shell holds no data and is what says why: the page, its styles, its icon, its modules — and no route of
    the API. A port forwarder's call (a container reaching this loopback) is closed in every mode."""
    if closed == "protected":
        monkeypatch.setenv("GFSO_PAGE_AUTH", "key")
    else:
        _a_relay(monkeypatch)
    auth = "key" if closed == "protected" else "local-peer"
    _someone_else(monkeypatch)
    c = _client(door[1], **PAGE)
    for shell in ("/", "/tokens.css", "/gfso.css", "/icon.svg"):
        assert c.get(shell).status_code == 200, shell
    module = next(p.name for p in (Path(gfso.__file__).parent / "web" / "js").glob("*.js"))
    assert c.get(f"/js/{module}").status_code == 200
    out = c.get("/signin", params={"code": "never-minted"}, follow_redirects=False)     # …it trades a minted code alone
    assert out.status_code in (303, 403) and "set-cookie" not in out.headers
    out = c.get("/api/projects")
    assert (out.status_code, out.json()) == (403, {**REFUSED, "page_auth": auth})


def test_a_credential_this_installation_never_issued_names_no_one(door, monkeypatch):
    """What lets a call no process of the person's makes MOVE is a credential this installation holds, never one it
    does not: with a forged one it is a reader, as with none."""
    e, app = door
    _someone_else(monkeypatch)
    c = _client(app, **PAGE)
    c.cookies.set(signin.COOKIE, "never-issued")
    _a_reader(c, e)
    _a_reader(_client(app, Authorization="Bearer gfso_never-issued"), e)


def test_a_front_run_as_another_os_user_is_served_on_the_credential_it_carries(door, monkeypatch):
    """`tailscale serve` runs as the system: a session opened through it, or a client's token, is served as before."""
    e, app = door
    _someone_else(monkeypatch)
    _, token = signin.issue("engineering")
    c = _client(app, Authorization=f"Bearer {token}", **{"X-Forwarded-For": "100.64.0.7"})
    assert c.get("/api/whoami").json()["signs_as"] == ["engineering"]
    assert c.post("/api/run/create_task", json={"task_id": "n", "spec": SPEC, "assignee": "engineering"}).status_code == 200


@pytest.mark.parametrize("relay", ["com.docker.backend.exe", "com.docker.backend", "vpnkit", "com.docker.proxy"])
def test_a_connection_a_port_forwarder_relays_is_not_ours(monkeypatch, relay):
    """Measured: a container's call to host.docker.internal arrives held by com.docker.backend.exe, the person's own
    process — so any container on this machine's Docker, another account's in docker-users included, was the person.
    A forwarder carries whatever client it relays, as a front does: its owner says nothing of who asks."""
    s = socket.create_server(("127.0.0.1", 0))
    c = socket.create_connection(s.getsockname())
    a, at = s.accept()
    try:
        assert peer.ours(at, s.getsockname())
        monkeypatch.setattr(psutil.Process, "name", lambda self: relay)
        assert not peer.ours(at, s.getsockname()), f"a connection {relay} relays was taken for the person's"
    finally:
        for x in (a, c, s):
            x.close()


def test_an_owner_the_os_will_not_name_is_not_ours(monkeypatch):
    s = socket.create_server(("127.0.0.1", 0))
    c = socket.create_connection(s.getsockname())
    a, at = s.accept()
    try:
        assert peer.ours(at, s.getsockname()), "this process's own connection is its user's"
        assert not peer.ours(("127.0.0.1", 1), s.getsockname()), "a connection the OS does not hold is no one's"
        assert not peer.ours(None, s.getsockname())

        def refused(self, *a, **k):
            raise psutil.AccessDenied(self.pid)
        monkeypatch.setattr(psutil.Process, "username", refused)
        monkeypatch.setattr(psutil.Process, "uids", refused, raising=False)       # …POSIX's owner
        assert not peer.ours(at, s.getsockname()), "an owner the OS will not name was taken for ours"
    finally:
        for x in (a, c, s):
            x.close()


@contextlib.contextmanager
def _served(app):
    """`app` on a real socket, run as every server of this package is (`config.UVICORN`): its port."""
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        port = s.getsockname()[1]
    web = uvicorn.Server(uvicorn.Config(app, port=port, log_level="error", **config.UVICORN))
    run = threading.Thread(target=web.run, daemon=True)
    run.start()
    try:
        while not web.started:
            time.sleep(0.02)
        yield port
    finally:
        web.should_exit = True
        run.join(10)


def _ask(port, path, headers=None, **k):
    return json.loads(urllib.request.urlopen(urllib.request.Request(
        f"http://127.0.0.1:{port}{path}", headers={"Origin": f"http://127.0.0.1:{port}",
                                                 "Content-Type": "application/json", **(headers or {})}, **k),
        timeout=10).read())


def test_a_real_loopback_call_of_this_user_is_the_person_with_nothing_to_sign_in(door, monkeypatch):
    """The OS's own answer through a real server on a real socket: this process is this machine's user."""
    monkeypatch.delenv("GFSO_PAGE_AUTH", raising=False)
    monkeypatch.setattr(signin, "peer_is_ours", peer.ours)
    with _served(door[1]) as port:
        assert _ask(port, "/api/whoami")["kind"] == "person"
        _ask(port, "/api/run/create_task", method="POST", data=json.dumps({"task_id": "n", "spec": SPEC}).encode())
        assert door[0].graph.get_task(TaskId("n")) is not None


def test_the_owner_is_asked_of_the_real_socket_whatever_a_forwarding_header_says(door, monkeypatch):
    """uvicorn takes `X-Forwarded-For` for the client from 127.0.0.1 by default: the OS was then asked of a socket that
    is not there, and a same-user front's call read as another account's."""
    asked = []
    monkeypatch.setattr(signin, "peer_is_ours", lambda peer_, server: asked.append(peer_) or peer.ours(peer_, server))
    with _served(door[1]) as port:
        out = _ask(port, "/api/whoami", {"X-Forwarded-For": "100.64.0.7"})
    assert asked and asked[0][0] == "127.0.0.1", asked
    assert out["signs_as"] == [] and "front" in out["lift"], out


def test_the_persons_page_moves_with_no_cookie_by_default(door, monkeypatch):
    monkeypatch.delenv("GFSO_PAGE_AUTH", raising=False)
    e, app = door
    signin.issue("engineering")                                     # …an agent's name of his: the page signs not as it
    c = _client(app, **PAGE)
    assert c.get("/api/whoami").json() == {"name": "user", "kind": "person", "how": "local-peer", "signs_as": ["user"]}
    c.post("/api/run/create_task", json={"task_id": "n", "spec": SPEC})
    assert c.post("/api/run/signal", json={"task_id": "n", "signal": "ACCEPT"}).json()["accepted"]   # its Del, his
    out = c.post("/api/run/signal", json={"task_id": "n", "signal": "ACCEPT", "source": "engineering"}).json()
    assert out.get("refused") and "signs only as user" in out["error"], out
    e.wait_idle()
    assert [(str(a.source), a.via) for a in e.audit_log(TaskId("n")) if a.signal == Signal.ACCEPT] == [
        ("user", "local-peer")]
    with c.websocket_connect("ws://127.0.0.1:8000/ws/events"):
        pass


@pytest.mark.parametrize("headers", [{"Origin": "https://stranger.example"}, {"Sec-Fetch-Site": "cross-site"}])
def test_a_page_of_another_site_is_still_refused(door, headers):
    e, app = door
    c = _client(app, **headers)
    assert c.post("/api/run/create_task", json={"task_id": "n", "spec": SPEC}).status_code == 403
    assert e.graph.get_task(TaskId("n")) is None


def test_protected_the_page_needs_a_session_and_its_connection_both(door, monkeypatch):
    monkeypatch.setenv("GFSO_PAGE_AUTH", "key")
    e, app = door
    c = _client(app, **PAGE)
    out = c.post("/api/run/create_task", json={"task_id": "n", "spec": SPEC}).json()
    assert out.get("refused") and "sign in: run `gfso ui`" in out["error"], out
    assert c.get("/api/runtime").json()["page_auth"] == "key"
    c.cookies.set(signin.COOKIE, signin.redeem(signin.code()))
    assert c.post("/api/run/create_task", json={"task_id": "n", "spec": SPEC}).status_code == 200
    assert c.get("/api/whoami").json()["how"] == "signed in"
    _someone_else(monkeypatch)
    assert _client(app, **PAGE).get("/api/graph").status_code == 403


def test_the_default_is_said_at_the_door(door, monkeypatch):
    monkeypatch.delenv("GFSO_PAGE_AUTH", raising=False)
    assert _client(door[1]).get("/api/runtime").json()["page_auth"] == "local-peer"


@pytest.mark.parametrize("base, headers", [
    ("http://testserver", {}),                              # a front's name
    ("http://front.example:8000", {"Origin": "http://front.example:8000", "Sec-Fetch-Site": "same-origin"}),  # …its page
    (LOOPBACK, {"X-Forwarded-For": "100.64.0.7"}),          # a front that rewrote Host
    (LOOPBACK, {"Tailscale-User-Login": "a@b", **PAGE}),
])
def test_a_front_with_no_credential_is_refused_as_before(door, monkeypatch, base, headers):
    """…though the front runs as the person's own user (Caddy, cloudflared, `ngrok http`): its peer is his, its every
    client is not."""
    _, app = door
    monkeypatch.setattr(signin, "peer_is_ours", lambda peer, server: True, raising=False)
    monkeypatch.setenv("GFSO_ALLOWED_HOSTS", "testserver,front.example")
    out = _client(app, base, **headers).post("/api/run/create_task", json={"task_id": "n", "spec": SPEC}).json()
    assert out.get("refused") and "front" in out["error"], out


def test_past_a_loopback_bind_a_front_answers_as_before(door, monkeypatch):
    _, app = door
    monkeypatch.setenv("GFSO_BIND", "0.0.0.0")
    asked = []
    monkeypatch.setattr(signin, "peer_is_ours", lambda *a: asked.append(a) or False, raising=False)
    c = _client(app, **PAGE)
    out = c.post("/api/run/create_task", json={"task_id": "n", "spec": SPEC}).json()
    assert out.get("refused") and "front" in out["error"], out
    assert c.get("/api/graph").status_code == 200        # …the OS asked only for what a session needs


def test_protected_is_the_installations_word_and_a_server_without_it_has_drifted(tmp_path, monkeypatch):
    monkeypatch.setenv("GFSO_HOME", str(tmp_path))
    monkeypatch.delenv("GFSO_PAGE_AUTH", raising=False)
    for argv in (["up", "--protected"], ["setup", "--protected"]):
        assert cli.build_parser().parse_args(argv).protected is True
    cli._protected(cli.build_parser().parse_args(["up", "--protected"]))
    assert serverctl.declared()["GFSO_PAGE_AUTH"] == "key"
    said = lambda rt: [d for d in serverctl.drift(rt, serverctl.declared(), "") if "page_auth" in d]
    assert said({"page_auth": "local-peer"}) and not said({"page_auth": "key"})
    cli._protected(cli.build_parser().parse_args(["up"]))               # …neither flag: the word stands
    assert serverctl.declared()["GFSO_PAGE_AUTH"] == "key"
    cli._protected(cli.build_parser().parse_args(["up", "--no-protected"]))
    assert serverctl.declared()["GFSO_PAGE_AUTH"] == "local-peer"


@pytest.mark.parametrize("auth", ["local-peer", "key"])
@pytest.mark.parametrize("at", ["", "127.0.0.1", "localhost"])
def test_a_loopback_session_replayed_from_a_peer_not_ours_moves_nothing_in_either_mode(door, monkeypatch, auth, at):
    """A loopback cookie is port-blind (RFC 6265 §8.5): another account's server on 127.0.0.1 receives the person's —
    replayed, it names no one: a reader by default, nothing at all under `--protected`."""
    monkeypatch.setenv("GFSO_PAGE_AUTH", auth)
    session = signin.redeem(signin.code(), at)
    _someone_else(monkeypatch)
    c = _client(door[1], **PAGE)
    c.cookies.set(signin.COOKIE, session)
    if auth == "key":
        out = c.get("/api/graph")
        assert (out.status_code, out.json()) == (403, REFUSED)
        assert c.post("/api/run/create_task", json={"task_id": "n", "spec": SPEC}).status_code == 403
    else:
        _a_reader(c, door[0])


def test_a_session_opened_at_a_fronts_name_is_served_from_a_peer_not_ours_at_that_name_only(door, monkeypatch):
    monkeypatch.setenv("GFSO_ALLOWED_HOSTS", "testserver,front.example")
    _someone_else(monkeypatch)
    front = _client(door[1], "http://front.example", **{"X-Forwarded-For": "100.64.0.7"})
    out = front.get("/signin", params={"code": signin.code()}, follow_redirects=False)
    assert out.status_code == 303 and signin.COOKIE in out.headers["set-cookie"]
    session = out.cookies[signin.COOKIE]
    front.cookies.set(signin.COOKIE, session)
    assert front.get("/api/whoami").json()["how"] == "signed in"
    loop = _client(door[1], **PAGE)
    loop.cookies.set(signin.COOKIE, session)
    who = loop.get("/api/whoami").json()
    assert not who.get("signs_as") and who.get("how") != "signed in", "a front's session shown at a loopback name"


@pytest.mark.parametrize("opened_at", ["127.0.0.1", None])
def test_a_loopback_session_relayed_by_the_persons_own_front_is_not_the_person(door, monkeypatch, opened_at):
    """The critic's case: a loopback cookie another account lured off 127.0.0.1:<p> (or one from before names were
    kept), shown through a front the person runs as himself — the peer his, the Host the front's — is no session."""
    monkeypatch.setenv("GFSO_PAGE_AUTH", "key")
    monkeypatch.setenv("GFSO_ALLOWED_HOSTS", "testserver,front.example")
    session = signin.redeem(signin.code(), "127.0.0.1")
    if opened_at is None:
        with signin._db() as db:
            db.execute("UPDATE sessions SET host = NULL")
    front = _client(door[1], "http://front.example", **{"X-Forwarded-For": "100.64.0.7"})
    front.cookies.set(signin.COOKIE, session)
    assert front.get("/api/whoami").json().get("how") != "signed in"
    out = front.post("/api/run/create_task", json={"task_id": "n", "spec": SPEC})
    assert out.status_code != 200 and "refused" in out.text, out.text          # …the front's refusal: no session
    assert door[0].graph.get_task(TaskId("n")) is None
    loop = _client(door[1], **PAGE)
    loop.cookies.set(signin.COOKIE, session)
    assert loop.get("/api/whoami").json()["how"] == "signed in", "the same session at its own name, from his peer"


def test_by_default_a_loopback_sign_in_opens_the_page_and_sets_no_cookie(door, monkeypatch):
    monkeypatch.delenv("GFSO_PAGE_AUTH", raising=False)
    out = _client(door[1], **PAGE).get("/signin", params={"code": signin.code(), "next": "/?project=p"},
                                         follow_redirects=False)
    assert (out.status_code, out.headers["location"]) == (303, "/?project=p") and "set-cookie" not in out.headers


def test_protected_the_persons_peer_with_a_loopback_session_is_served_and_without_one_asked_to_sign_in(door, monkeypatch):
    monkeypatch.setenv("GFSO_PAGE_AUTH", "key")
    c = _client(door[1], **PAGE)
    assert c.get("/api/whoami").json()["lift"] == "sign in: run `gfso ui`"
    out = c.get("/signin", params={"code": signin.code()}, follow_redirects=False)
    c.cookies.set(signin.COOKIE, out.cookies[signin.COOKIE])
    assert c.get("/api/whoami").json()["how"] == "signed in"


def test_by_default_gfso_ui_opens_the_page_and_mints_no_session(monkeypatch):
    monkeypatch.setattr(serverctl, "runtime", lambda *a, **k: {"page_auth": "local-peer"})
    opened = []
    monkeypatch.setattr(cli, "open_outside", opened.append)
    minted = []
    monkeypatch.setattr(signin, "code", lambda *a: minted.append(1) or "x")
    assert cli._ui(cli.build_parser().parse_args(["ui", "p"])) == 0
    assert opened == [serverctl.ui_link("p")] and not minted


@pytest.mark.parametrize("origin", ["http://127.0.0.1:8080", "http://[::1]:8000", "http://localhost:8000"])
def test_a_page_of_another_loopback_name_or_port_opens_no_socket_of_the_persons(door, origin):
    """The critic's case: another account's page on 127.0.0.1:8080 or [::1]:<port>, opened in the person's own
    browser, asked his socket — its peer his, a browser sending no Sec-Fetch-Site on a socket's handshake — and was
    pushed his live data. The page's origin is the very one the request asked."""
    c = _client(door[1], Origin=origin)
    with pytest.raises(WebSocketDisconnect):
        with c.websocket_connect("ws://127.0.0.1:8000/ws/events?projects=1") as ws:
            ws.receive_json()
    with _client(door[1], Origin=LOOPBACK).websocket_connect("ws://127.0.0.1:8000/ws/events?projects=1"):
        pass                                                         # …its own origin, at its own name


@pytest.mark.parametrize("name", ["localhost", "[::1]"])
def test_a_loopback_name_of_an_address_the_server_does_not_hold_is_not_its_page(door, name):
    """The critic's case: the server holds 127.0.0.1:8000 alone; another account binds [::1]:8000, serves its page at
    http://localhost:8000, then lets go — the browser falls back to 127.0.0.1 and the page, same-origin by name, read
    and moved as the person. A name is the page's only where the server holds every address it names."""
    c = _client(door[1], Host=f"{name}:8000", Origin=f"http://{name}:8000", **{"Sec-Fetch-Site": "same-origin"})
    assert c.post("/api/run/create_task", json={"task_id": "n", "spec": SPEC, "assignee": "user"}).status_code != 200
    assert c.get("/api/projects").status_code != 200


def test_a_page_on_another_port_of_the_machine_reads_nothing_back(door):
    """The critic's case: a browser that sends no Sec-Fetch-Site, on a page at 127.0.0.1:8080 any account can bind,
    read every project — the door let the read through and CORS echoed that origin, a dev static host's leftover."""
    r = _client(door[1], Origin="http://127.0.0.1:8080").get("/api/projects")
    assert r.headers.get("access-control-allow-origin") is None, r.headers


def test_a_loopback_session_through_a_front_that_rewrites_the_host_is_no_session(door, monkeypatch):
    """The critic's case: ngrok --host-header=rewrite, cloudflared httpHostHeader, Caddy header_up Host — the peer
    the person's front, the Host 127.0.0.1 — carried a lured loopback cookie as the person."""
    monkeypatch.setenv("GFSO_PAGE_AUTH", "key")
    session = signin.redeem(signin.code(), "127.0.0.1")
    front = _client(door[1], **{"X-Forwarded-For": "100.64.0.7", "X-Forwarded-Host": "front.example"})
    front.cookies.set(signin.COOKIE, session)
    assert front.get("/api/whoami").json().get("how") != "signed in"
    out = front.post("/api/run/create_task", json={"task_id": "n", "spec": SPEC})
    assert out.status_code != 200 and door[0].graph.get_task(TaskId("n")) is None, out.text


def test_gfso_ui_at_a_fronts_name_says_the_link_for_the_device_and_spends_nothing_here(monkeypatch, capsys):
    """The phone through `tailscale serve`: opened in this machine's browser, the code was spent here and the device
    had no way in (critic). The link is said; nothing opens it on this machine."""
    monkeypatch.setattr(serverctl, "runtime", lambda *a, **k: {"page_auth": "key"})   # …a server answering (CI runs none)
    opened = []
    monkeypatch.setattr(cli, "open_outside", opened.append)
    monkeypatch.setattr(signin, "code", lambda *a: "c0de")
    assert cli._ui(cli.build_parser().parse_args(["ui", "p", "--host", "pc.tail.ts.net"])) == 0
    said = capsys.readouterr().out
    assert not opened and "https://pc.tail.ts.net/signin?code=c0de" in said, said


def test_past_a_loopback_bind_a_loopback_session_counts_only_from_the_persons_own_socket(door, monkeypatch):
    """The critic's case: bound to 0.0.0.0, `ours` read true for every peer, so a lured loopback cookie replayed from
    another account's socket, or from the LAN with Host 127.0.0.1, was the person."""
    monkeypatch.setenv("GFSO_BIND", "0.0.0.0")
    session = signin.redeem(signin.code(), "127.0.0.1")
    _someone_else(monkeypatch)
    c = _client(door[1], **PAGE)
    c.cookies.set(signin.COOKIE, session)
    assert c.get("/api/whoami").json().get("how") != "signed in"
    c.post("/api/run/create_task", json={"task_id": "n", "spec": SPEC})
    assert door[0].graph.get_task(TaskId("n")) is None


def test_past_a_loopback_bind_the_persons_page_signs_in_at_a_loopback_name(door, monkeypatch):
    """The critic's case: past a loopback bind the no-step shortcut skipped the cookie while the door refused every
    loopback call as a front — the person's page could never move. There the page always signs in."""
    monkeypatch.setenv("GFSO_BIND", "0.0.0.0")
    monkeypatch.delenv("GFSO_PAGE_AUTH", raising=False)
    assert config.page_auth() == "key"
    c = _client(door[1], **PAGE)
    out = c.get("/signin", params={"code": signin.code()}, follow_redirects=False)
    assert out.status_code == 303 and signin.COOKIE in out.headers.get("set-cookie", "")
    c.cookies.set(signin.COOKIE, out.cookies[signin.COOKIE])
    assert c.get("/api/whoami").json()["how"] == "signed in"


def test_a_reader_deletes_and_makes_no_project_over_mcp(monkeypatch, tmp_path):
    """The critic's case: the project verbs mounted beside the tools passed no signing, so a reader through a front
    deleted a project. A reader may still step its own session onto a project that exists — that is reading."""
    pytest.importorskip("mcp")
    monkeypatch.setenv("GFSO_DATA_DIR", str(tmp_path))
    monkeypatch.setenv("GFSO_DB_PATH", str(tmp_path / "gfso_default.db"))
    monkeypatch.delenv("GFSO_STORAGE", raising=False)
    monkeypatch.delenv("GFSO_PROJECT", raising=False)
    reg = ProjectRegistry()
    reg.engine("victim")
    server = create_server(reg)
    reader = signin._refused(signin._FRONT)
    monkeypatch.setattr(signin, "local_principal", lambda mcp=False: reader)   # the door resolves each call's own caller
    token = CALLER.set(reader)
    try:
        for verb, args in (("delete_project", {"project": "victim"}), ("use_project", {"project": "fresh"})):
            try:
                asyncio.run(server.call_tool(verb, args))
            except Exception as ex:                    # the SDK raises or returns the refusal: either is a refusal
                assert "signed by no one" in str(ex), ex
    finally:
        CALLER.reset(token)
    assert (tmp_path / "victim.db").exists() and not reg.exists("fresh")
    for e in list(reg._engines.values()):
        e.stop()


def test_a_reader_spends_no_model_call(door, monkeypatch):
    e, app = door
    _someone_else(monkeypatch)
    out = _client(app, **PAGE).post("/api/suggest-criteria", json={"description": "anything"})
    assert out.status_code == 403 and "signed by no one" in out.text, out.text


def test_past_a_loopback_bind_a_port_forwarders_call_is_still_served_nothing(door, monkeypatch):
    _, app = door
    monkeypatch.setenv("GFSO_BIND", "0.0.0.0")
    monkeypatch.setattr(signin, "peer_is_ours", lambda peer, server: False, raising=False)
    _a_relay(monkeypatch)
    out = _client(app, **PAGE).get("/api/graph")
    assert out.status_code == 403 and out.json()["error"] == signin._STRANGER


@pytest.mark.parametrize("path,body", [
    ("/api/lease", {"id": "L-owner"}), ("/api/wait", {}), ("/api/shutdown", {}),
    ("/api/run/probe_inputs", {"task_id": "root"}), ("/api/run/create_task", {"task_id": "n", "spec": SPEC}),
])
def test_a_reader_changes_nothing_through_a_route_that_writes(door, monkeypatch, path, body):
    """The critic's cases (three rounds): routes counted as reads that changed state — a lease that kept a departed
    owner's executor spawning, a wait that marked plans told, `probe_inputs`' files. The verbs are refused at the one
    door every transport is built on (`tools_llm._signed`: no name, reads only); the HTTP-only routes by `_a_move`."""
    e, app = door
    _someone_else(monkeypatch)
    out = _client(app, **PAGE).post(path, json=body)
    assert out.status_code in (403, 422) and "signed by no one" in out.text, (path, out.text)
    assert e.graph.get_task(TaskId("n")) is None


def test_every_route_that_writes_is_a_move_and_one_added_later_too(door, monkeypatch):
    """The HTTP-only routes held the reader rule one by one, so a route added later would have been open (critic,
    2026-11-16): it is held for the whole app now, every route but a GET and the named reads (`_OPEN_SENDS`) a move.
    CONTROL: drop the app's `dependencies=[Depends(_a_move)]` and both halves go red."""
    _, app = door

    @app.post("/api/added-later")
    def _added_later():
        return {"wrote": True}

    _someone_else(monkeypatch)
    c = _client(app, **PAGE)
    writes = [(m, r.path) for r in app.routes for m in sorted(getattr(r, "methods", None) or ())
              if m not in ("GET", "HEAD", "OPTIONS") and r.path not in _OPEN_SENDS]
    assert ("POST", "/api/added-later") in writes and len(writes) >= 10, writes
    for m, path in writes:
        out = c.request(m, path.replace("{", "x").replace("}", ""), json={})
        assert out.status_code == 403 and "signed by no one" in out.text, (m, path, out.status_code, out.text[:200])


def test_which_credentials_the_person_holds_is_read_only_by_a_signed_call(door, monkeypatch):
    """What was opened is the graph; the credentials' names and kinds are the person's own setup (critic, 2026-11-16).
    CONTROL: drop "/api/credentials" from `_OWN_READS` and the first assertion goes red."""
    _, app = door
    assert _client(app, **PAGE).get("/api/credentials").status_code == 200, "the person's own page reads it"
    _someone_else(monkeypatch)
    out = _client(app, **PAGE).get("/api/credentials")
    assert out.status_code == 403 and "signed by no one" in out.text, out.text


@pytest.mark.parametrize("verb", ["list_agents", "canon"])
def test_a_projectless_read_makes_no_project(monkeypatch, verb, tmp_path):
    """A projectless read naming a project that does not exist made one per call (critic): on both doors only a verb
    that may make a project (`tools.MAKES_A_PROJECT`) makes one."""
    monkeypatch.setenv("GFSO_DATA_DIR", str(tmp_path))
    monkeypatch.setenv("GFSO_DB_PATH", str(tmp_path / "gfso_default.db"))
    monkeypatch.delenv("GFSO_STORAGE", raising=False)
    monkeypatch.delenv("GFSO_PROJECT", raising=False)
    reg = ProjectRegistry()
    _someone_else(monkeypatch)
    _client(create_app(reg.engine(), registry=reg), **PAGE).post(f"/api/run/{verb}?project=made-by-reader", json={})
    assert not reg.exists("made-by-reader") and not (tmp_path / "made-by-reader.db").exists()
    for e in list(reg._engines.values()):
        e.stop()


def test_a_reader_is_served_every_read_the_page_makes(door, monkeypatch):
    e, app = door
    _someone_else(monkeypatch)
    c = _client(app, **PAGE)
    for path in ("/api/whoami", "/api/runtime", "/api/projects?limit=0", "/api/graph?next=0", "/api/tasks",
                 "/api/audit", "/api/pipeline?limit=20", "/api/metrics"):
        assert c.get(path).status_code == 200, path
    for path, body in (("/api/run/tech_reports", {}), ("/api/run/next_steps", {}), ("/api/verdicts", [])):
        assert c.post(path, json=body).status_code == 200, path
    # the events socket is served to a reader too; the test client's socket closes 4403 for the
    # person's own process as well, so it is judged live, not here
