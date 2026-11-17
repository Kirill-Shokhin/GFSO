"""A node a live party works itself over the MCP door is seen worked while that party is connected. A person or the user's
own console runs no process of the server, so `in_flight` never named its work and the page guessed (the author,
2026-11-14: «иначе как инчат должен быть видим как процесс?»). Presence is a property of a live connection, never of
an identity: it opens on a move that leaves the node at work in the mover's hands and closes when the node leaves work or
the mover's last lease is gone."""
import asyncio
import time

import anyio
import pytest
from fastapi.testclient import TestClient

from gfso import config, presence, signin
from gfso import tools as T
from gfso.adapters.llm.stub import StubLLM
from gfso.api.server import create_app, _expiring, _pushed
from tests.support import make_engine
from tests.test_a_connection_signs_as_its_principal import HUMAN, _call, bearer, door  # noqa: F401 — the door fixture

SPEC = {"description": "a stream", "criteria": [HUMAN]}


@pytest.fixture(autouse=True)
def nothing_worked(monkeypatch):
    monkeypatch.setattr(presence, "WORKING", {})


def _seen():
    return [(w["task_id"], w["principal"]) for w in presence.working()]


def _at_work(e, principal, tid="n1"):
    T.create_task(e, tid, SPEC, assignee=principal)
    assert T.signal(e, tid, "ACCEPT", source=principal)["accepted"]


def test_a_move_by_a_named_party_opens_its_work_once(door):
    e, url = door
    go = lambda name, verb, **a: anyio.run(_call, url, name, verb, a)
    go("engineering", "create_task", task_id="n1", spec=SPEC, assignee="engineering")
    assert _seen() == [], "an offered node is not at work"
    go("engineering", "signal", task_id="n1", signal="ACCEPT")
    [w] = presence.working()
    assert (w["project"], w["task_id"], w["principal"], w["via"]) == (config.DEFAULT_PROJECT, "n1", "engineering", "mcp")
    go("engineering", "get_task", task_id="n1")
    assert presence.working() == [w], "a second move refreshes, never duplicates"


@pytest.mark.parametrize("leave", [{"signal": "DELIVER", "result": "done"}, {"signal": "BLOCK", "reason": "waits"}])
def test_the_work_closes_when_the_node_leaves_work(door, leave):
    e, url = door
    go = lambda name, verb, **a: anyio.run(_call, url, name, verb, a)
    go("engineering", "create_task", task_id="n1", spec=SPEC, assignee="engineering")
    go("engineering", "signal", task_id="n1", signal="ACCEPT")
    assert _seen() == [("n1", "engineering")]
    err, text = go("engineering", "signal", task_id="n1", **leave)
    e.wait_idle()
    assert not err and _seen() == [], text


def test_a_refused_move_and_a_node_held_by_another_open_nothing(door):
    e, url = door
    go = lambda name, verb, **a: anyio.run(_call, url, name, verb, a)
    go("engineering", "create_task", task_id="n1", spec=SPEC, assignee="engineering")
    go("mallory", "signal", task_id="n1", signal="ACCEPT")
    assert _seen() == [], "a refused move opened work"
    go("engineering", "signal", task_id="n1", signal="ACCEPT")
    go("mallory", "get_task", task_id="n1")
    assert _seen() == [("n1", "engineering")], "a node held by another opened work for its reader"


def test_the_standing_agent_is_seen_under_its_identity(door):
    e, url = door
    go = lambda name, verb, **a: anyio.run(_call, url, name, verb, a)
    go(None, "create_task", task_id="n1", spec=SPEC)
    go(None, "signal", task_id="n1", signal="ACCEPT")
    assert _seen() == [("n1", config.agent_id())]


@pytest.fixture
def server(monkeypatch):
    e = make_engine(llm=StubLLM(), validate_signals=True)
    e.start()
    yield e, TestClient(create_app(e))
    e.stop()


def test_the_work_closes_with_the_partys_last_lease_and_not_with_anothers(server):
    e, client = server
    for lease, who in (("a", "engineering"), ("b", "engineering"), ("c", "mallory")):
        client.post("/api/lease", json={"id": lease}, headers=bearer(who))
    _at_work(e, "engineering")
    presence.moved(e, "n1", "engineering")
    client.delete("/api/lease/a")
    assert _seen() == [("n1", "engineering")], "a party with a lease left is still alive"
    client.delete("/api/lease/b")
    assert _seen() == [], "another party's lease kept it"


def test_an_expired_lease_closes_the_work_without_a_read(server):
    e, client = server
    client.post("/api/lease", json={"id": "a"})            # no token: the standing agent
    _at_work(e, config.agent_id())
    presence.moved(e, "n1", config.agent_id())
    client.app.state.leases["a"] = time.monotonic() - 60

    async def a_while():
        with pytest.raises(asyncio.TimeoutError):
            await asyncio.wait_for(_expiring(client.app, every=0.01), 0.2)
    asyncio.run(a_while())
    assert _seen() == []


def test_the_runtime_and_the_page_carry_the_work(server):
    e, client = server
    _at_work(e, "engineering")
    with client.websocket_connect("/ws/events") as ws:
        presence.moved(e, "n1", "engineering")
        said = ws.receive_json()
        while said["type"] != "working":
            said = ws.receive_json()
        assert [w["task_id"] for w in said["working"]] == ["n1"]
    assert [w["principal"] for w in client.get("/api/runtime").json()["working"]] == ["engineering"]
    assert presence.LISTENERS == [], "a closed page left its listener behind"


def test_an_engine_made_again_under_the_project_closes_what_the_old_one_held():
    """A reopen makes a new engine for the same project: the old one's entry closed by none of the new engine's
    transitions, and a node out of work stayed seen worked (critic)."""
    old, new = make_engine(), make_engine()
    for e in (old, new):
        e.start()
        _at_work(e, "engineering")
    presence.moved(old, "n1", "engineering")
    assert T.signal(new, "n1", "BLOCK", source="engineering", reason="waits")["accepted"]
    presence.moved(new, "n1", "engineering")         # the delivering party's own move, read on the new engine
    assert _seen() == []


def test_a_lease_naming_no_party_keeps_the_count_whole(server):
    """A principal that is no name a role can be held by is the standing agent: a dict there broke every lease count
    and ended expiry for the server's life (critic)."""
    _, client = server
    assert client.post("/api/lease", json={"id": "x", "principal": {"k": 1}}).status_code == 200
    assert client.post("/api/lease", json={"id": "y", "principal": "engineering"}).json()["sessions"] == 2
    assert client.app.state.lease_holders["x"] == config.agent_id()


def test_a_move_from_an_open_page_is_seen_worked_while_a_page_stays_open(server):
    """The same act read the same whichever door it came through: a person moving their node from the page got
    «Accepted» and never «In progress», presence opening only on an MCP move (JOINT in-work, 2026-11-15). Its life is
    the person's open pages, as a bridge's is its leases. CONTROL: drop `_page_moved` from `run_tool` and it fails."""
    e, client = server
    signin.issue("alice")
    T.create_task(e, "n1", SPEC, assignee="alice")
    client.cookies.set(signin.COOKIE, signin.redeem(signin.code()))
    ws = "ws://127.0.0.1:8000/ws/events"     # …the page's own name: a session counts where it was opened, and the test
    #   client's socket asks `testserver` unless told
    with client.websocket_connect(ws), client.websocket_connect(ws):
        assert client.post("/api/run/signal", json={"task_id": "n1", "signal": "ACCEPT"}).json()["accepted"]
        [w] = presence.working()
        assert (w["principal"], w["via"]) == ("alice", "page")
    with client.websocket_connect(ws):                    # …a reload: the next page opens within the grace
        client.app.state.live_leases()
        assert _seen() == [("n1", "alice")], "a reload ended the work for good (critic)"
    client.app.state.live_leases()
    assert _seen() == [("n1", "alice")], "the last page's grace is a bridge's: not yet"
    client.app.state.closed["local"] -= 60
    client.app.state.live_leases()
    assert _seen() == [], "the person's last page closed a grace ago and the work stayed seen"


def test_a_page_move_with_no_page_open_opens_nothing(server):
    """A session's call with none of its pages open would be seen worked with nothing to end it."""
    e, client = server
    signin.issue("alice")
    T.create_task(e, "n1", SPEC, assignee="alice")
    client.cookies.set(signin.COOKIE, signin.redeem(signin.code()))
    assert client.post("/api/run/signal", json={"task_id": "n1", "signal": "ACCEPT"}).json()["accepted"]
    assert _seen() == []


def test_a_closed_page_is_read_as_it_closes_not_at_the_next_frame():
    """A closed tab stayed seen at work until a frame was sent to it, up to a minute (critic, uvicorn measured): the
    socket is read, and its close ends the push. CONTROL: drop the reader from `server._pushed` and this hangs."""

    class Closed:
        sent = []

        async def receive(self):
            return {"type": "websocket.disconnect"}

        async def send_json(self, e):
            self.sent.append(e)

    async def run():
        await asyncio.wait_for(_pushed(Closed(), asyncio.Queue()), 2)
    asyncio.run(run())


def test_a_page_and_a_console_on_one_node_each_end_by_their_own_door(server):
    """One key for both doors let the page's close end the console's work, and the reverse (critic)."""
    e, _ = server
    _at_work(e, "engineering")
    presence.moved(e, "n1", "engineering", via="page", person="local")
    presence.moved(e, "n1", "engineering")
    presence.page_gone("local")
    assert [(w["principal"], w["via"]) for w in presence.working()] == [("engineering", "mcp")]


@pytest.mark.parametrize("asked, lands", [("/?project=p", "/?project=p"), ("//evil.example/x", "/"),
                                          ("https://evil.example/", "/"), (r"/\evil.example", "/"),
                                          ("/	/evil.example", "/%09/evil.example")])
def test_a_sign_in_comes_back_to_its_page_and_never_off_it(server, asked, lands):
    _, client = server
    out = client.get("/signin", params={"code": signin.code(), "next": asked}, follow_redirects=False)
    assert out.status_code == 303 and out.headers["location"] == lands


def test_the_way_to_sign_in_names_the_page_it_is_asked_from(server, monkeypatch):
    """A page with no session, where the page signs in (`--protected`), shows the server's sentence as it is: asked
    about a project, it opens that project."""
    monkeypatch.setenv("GFSO_PAGE_AUTH", "key")
    _, client = server
    client.cookies.clear()
    said = lambda **q: client.get("/api/whoami", params=q, headers={"Sec-Fetch-Site": "same-origin"}).json()["lift"]
    assert said(project="p1") == "sign in: run `gfso ui p1`" and said() == "sign in: run `gfso ui`"
