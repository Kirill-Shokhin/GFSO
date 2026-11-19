"""A console already running takes a stream's name over its own gfso connection (`act_as`), no relaunch: the stream is a
name the person opened and assigned, never a console or a session (DEV_GRAPH_AND_TEAM §1). The connection is its
bridge's lease, so the name outlives a `/clear` and a rebuilt leg; one live connection holds a name (Del unique, §2.6);
the taking is recorded with who, which name and when, and every move after it carries the connection (Thm 11)."""
import json
import uuid

import anyio
import pytest
from mcp import ClientSession
from mcp.client.streamable_http import streamablehttp_client

from gfso import config, signin
from gfso.core.types import Signal, TaskId
from tests.test_a_connection_signs_as_its_principal import HUMAN, door  # noqa: F401 — the fixture


def _lease():
    return uuid.uuid4().hex


async def _call(url, lease, verb, args):
    async with streamablehttp_client(url, headers={config.CLIENT_HEADER: "code", config.LEASE_HEADER: lease}) as (r, w, _), \
            ClientSession(r, w) as s:
        await s.initialize()
        out = await s.call_tool(verb, args)
    text = "".join(getattr(c, "text", "") for c in out.content)
    try:
        return json.loads(text)
    except ValueError:
        return {"raw": text}


@pytest.fixture
def go(door):
    e, url = door
    return e, lambda lease, verb, **a: anyio.run(_call, url, lease, verb, a)


def _stream(e, go, name):
    """A node the person assigns to `name`: the stream he opens."""
    out = go(_lease(), "create_task", task_id=f"{name}-root", spec={"description": "a stream", "criteria": [HUMAN]},
             assignee=name)
    e.wait_idle()
    assert e.graph.get_task(TaskId(f"{name}-root")) is not None, out


def test_a_running_console_takes_the_stream_it_was_assigned_and_keeps_it(go):
    e, go = go
    _stream(e, go, "eng1")
    one = _lease()
    assert go(one, "act_as")["name"] == "user"
    took = go(one, "act_as", name="eng1")
    assert took["name"] == "eng1" and took["signs_as"] == ["eng1"], took
    # …a fresh MCP session on the same bridge — a `/clear`, a rebuilt leg — is still the stream
    assert go(one, "act_as")["name"] == "eng1"
    go(one, "signal", task_id="eng1-root", signal="ACCEPT")
    e.wait_idle()
    accepted = [a for a in e.audit_log(TaskId("eng1-root")) if a.signal == Signal.ACCEPT and not a.rejected]
    assert [str(a.source) for a in accepted] == ["eng1"] and accepted[0].via.startswith("as:"), accepted
    # …recorded: who took which name when (Thm 11)
    assert signin._held("SELECT name, person, via FROM holds WHERE lease = ?", signin._hash(one)) == \
        [("eng1", "local", "claim")]


def test_a_second_connection_is_refused_the_name_a_live_one_holds(go, monkeypatch):
    e, go = go
    _stream(e, go, "eng2")
    one, two = _lease(), _lease()
    monkeypatch.setattr(signin, "LIVE_LEASES", lambda: [one, two])
    assert go(one, "act_as", name="eng2")["name"] == "eng2"
    out = go(two, "act_as", name="eng2")
    assert out.get("refused") and "held by another connection" in out["error"] and "§2.6" in out["error"], out
    assert go(two, "act_as")["name"] == "user"


def test_a_name_whose_holder_is_gone_passes_and_the_old_connection_signs_as_no_one(go, monkeypatch):
    e, go = go
    _stream(e, go, "eng3")
    one, two = _lease(), _lease()
    assert go(one, "act_as", name="eng3")["name"] == "eng3"
    monkeypatch.setattr(signin, "LIVE_LEASES", lambda: [two])          # …its bridge's lease lapsed
    assert go(two, "act_as", name="eng3")["name"] == "eng3"
    back = go(one, "act_as")
    assert back["kind"] == "none" and "another connection took it" in back["lift"], back    # never the person


def test_one_connection_holds_one_name_for_its_life(go):
    e, go = go
    _stream(e, go, "eng4")
    signin.issue("ui4")                 # …a name issued to him is his to take as well
    one = _lease()
    assert go(one, "act_as", name="eng4")["name"] == "eng4"
    out = go(one, "act_as", name="ui4")
    assert out.get("refused") and "one connection holds one name" in out["error"], out
    assert go(_lease(), "act_as", name="ui4")["name"] == "ui4"


@pytest.mark.parametrize("name, why", [("nobody-assigned-me", "not a name of yours"), ("user", "reserved"),
                                       ("x-exec-1", "the system's")])
def test_a_name_the_person_did_not_issue_is_refused(go, name, why):
    _, go = go
    out = go(_lease(), "act_as", name=name)
    assert out.get("refused") and why in out["error"], out


def test_under_protected_the_claim_is_refused_and_the_names_token_takes_it(go, monkeypatch):
    e, go = go
    _stream(e, go, "eng5")
    monkeypatch.setenv("GFSO_PAGE_AUTH", "key")
    one = _lease()
    out = go(one, "act_as", name="eng5")
    assert out.get("refused") and "--protected" in out["error"], out
    out = go(one, "act_as", name="eng5", token=signin.issue("other5")[1])
    assert out.get("refused") and "does not sign as `eng5`" in out["error"], out
    assert go(one, "act_as", name="eng5", token=signin.issue("eng5")[1])["name"] == "eng5"


def test_the_bridge_names_its_lease_on_every_leg(monkeypatch):
    """The relay sends this process's lease, so a rebuilt leg is the same connection."""
    from gfso.mcp import connect as C
    from tests import test_a_connection_signs_as_its_principal as P
    from mcp.server.fastmcp import Context, FastMCP
    seen = []
    srv = FastMCP("echo", host="127.0.0.1", port=0)

    @srv.tool()
    async def who(ctx: Context) -> str:
        seen.append(ctx.request_context.request.headers.get(config.LEASE_HEADER))
        return "ok"
    web, url = P._serve(srv.streamable_http_app())

    async def once():
        to_bridge, from_client = anyio.create_memory_object_stream(16)
        to_client, from_bridge = anyio.create_memory_object_stream(16)
        async with anyio.create_task_group() as tg:
            tg.start_soon(C._relay, url, from_client, to_client)
            async with ClientSession(from_bridge, to_bridge) as session:
                await session.initialize()
                await session.call_tool("who")
            tg.cancel_scope.cancel()
    try:
        anyio.run(once)
        anyio.run(once)
    finally:
        web.should_exit = True
    assert seen == [C.LEASE, C.LEASE] and len(C.LEASE) == 32
