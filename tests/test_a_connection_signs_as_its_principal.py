"""Over MCP each connection signs as the principal its credential carries: the token its console was launched with.
The server signed every call by ITS environment: a bridge launched as `engineering` created a node as engineering and
then had its ACCEPT signed `agent` and refused (measured 2026-11-13). The canon's record of a decision names its author
(Thm 11), and only the role's holder moves it (§10.1)."""
import asyncio
import json
import os
import socket
import threading
import time
import uuid

import anyio
import pytest
import uvicorn
from mcp import ClientSession
from mcp.client.streamable_http import streamablehttp_client
from mcp.server.fastmcp import Context, FastMCP

from gfso import config, signin
from gfso.adapters.llm.stub import StubLLM
from gfso.core.types import Signal, TaskId
from gfso.mcp import connect as C
from gfso.mcp import server as MS
from tests.support import make_engine

HUMAN = {"name": "accepted", "description": "the author accepts it",
         "check": [{"behaviour": "the result holds", "command": "the author reads the result", "expect": "he accepts it"}]}


def _serve(app):
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        port = s.getsockname()[1]
    web = uvicorn.Server(uvicorn.Config(app, port=port, log_level="error"))
    threading.Thread(target=web.run, daemon=True).start()
    while not web.started:
        time.sleep(0.02)
    return web, f"http://127.0.0.1:{port}/mcp"


#: a token per name, issued once for the suite's person: a console of that name
_TOKENS: dict = {}


def bearer(name) -> dict:
    """The header a console launched with `name`'s token sends; `None` the person's own, launched with his (`gfso agent
    user`) — a bridge's lease alone, having taken no name, reads and signs nothing."""
    name = name or config.PERSON
    if name not in _TOKENS:
        _TOKENS[name] = signin.issue(name)[1]
    return {"Authorization": f"Bearer {_TOKENS[name]}"}


async def _call(url, name, verb, args):
    # …as a client with hands: `in_chat` is refused to a chat one, which is not what this asks
    named = {config.CLIENT_HEADER: "code", **bearer(name)}
    async with streamablehttp_client(url, headers=named) as (r, w, _), \
            ClientSession(r, w) as s:
        await s.initialize()
        out = await s.call_tool(verb, args)
    text = "".join(getattr(c, "text", "") for c in out.content)
    return out.isError, text


@pytest.fixture
def door():
    e = make_engine(llm=StubLLM(), validate_signals=True)
    e.start()
    srv = MS.create_server(e)
    srv.settings.streamable_http_path = "/mcp"
    web, url = _serve(srv.streamable_http_app())
    yield e, url
    web.should_exit = True
    e.stop()


def test_each_connection_signs_its_own_moves_not_anothers(door):
    """Through the bridge, each connection by its own token."""
    e, url = door
    go = lambda name, verb, **a: anyio.run(_call, url, name, verb, a)
    err, text = go("engineering", "create_task", task_id="n1", spec={"description": "a stream", "criteria": [HUMAN]},
                   assignee="engineering")
    assert not err, text
    e.wait_idle()
    # a second connection, and the standing agent, cannot sign the first one's consent
    for other in ("mallory", None):
        err, text = go(other, "signal", task_id="n1", signal="ACCEPT")
        e.wait_idle()
        assert str(e.graph.get_task(TaskId("n1")).state).endswith("OFFERED"), (other, text)
    err, text = go("engineering", "signal", task_id="n1", signal="ACCEPT")
    e.wait_idle()
    assert not err and str(e.graph.get_task(TaskId("n1")).state).endswith("EXECUTING"), text
    signed = [(str(a.source), a.rejected) for a in e.audit_log(TaskId("n1")) if a.signal == Signal.ACCEPT]
    assert signed == [("mallory", True), ("user", True), ("engineering", False)], signed


def test_a_token_this_installation_does_not_hold_is_refused_not_read_as_the_standing_agent(door):
    e, url = door
    err, text = anyio.run(_call, url, None, "create_task", {"task_id": "n1", "spec": {"description": "x", "criteria": [HUMAN]}})
    _TOKENS["forged"] = "gfso_forged"
    err, text = anyio.run(_call, url, "forged", "signal", {"task_id": "n1", "signal": "ACCEPT"})
    assert "signed by no one" in text and "not one this installation holds" in text, text


def test_the_bridge_sends_the_token_its_console_was_launched_with(monkeypatch):
    """The relay carries `GFSO_TOKEN` of its own launch as the credential every request of its connection bears."""
    seen = []
    srv = FastMCP("echo", host="127.0.0.1", port=0)

    @srv.tool()
    async def who(ctx: Context) -> str:
        seen.append(ctx.request_context.request.headers.get("authorization"))
        return "ok"
    web, url = _serve(srv.streamable_http_app())
    monkeypatch.setenv(config.TOKEN_ENV, "gfso_t")

    async def go():
        to_bridge, from_client = anyio.create_memory_object_stream(16)
        to_client, from_bridge = anyio.create_memory_object_stream(16)
        async with anyio.create_task_group() as tg:
            tg.start_soon(C._relay, url, from_client, to_client)
            async with ClientSession(from_bridge, to_bridge) as session:
                await session.initialize()
                await session.call_tool("who")
            tg.cancel_scope.cancel()
    try:
        anyio.run(go)
    finally:
        web.should_exit = True
    assert seen == ["Bearer gfso_t"]


def test_a_long_verb_runs_under_its_callers_principal():
    """The long path runs in an executor, which copies no context by itself: the caller's name must travel with it."""
    async def go():
        token = config.CALLER.set(config.STANDING.signing("engineering"))
        try:
            return await MS._awaited_with_a_heartbeat(asyncio.get_running_loop(), None, "x", {"n": 0}, config.caller_id)
        finally:
            config.CALLER.reset(token)
    assert asyncio.run(go()) == "engineering"
    assert config.caller_id() == config.agent_id()


def test_a_named_connection_is_refused_in_a_project_with_a_mode_not_decided_as_a_stranger(door):
    """A mode reads the standing agent as the user's own: a named connection's root went to the system (critic)."""
    e, url = door
    err, text = anyio.run(_call, url, "engineering", "set_mode", {"mode": "solo", "perform": "in_chat"})
    assert "connection acts as 'engineering'" in text and e.mode() is None, text
    anyio.run(_call, url, None, "register_agent", {"agent_id": "val", "kind": "llm-validator", "workdir": "."})
    err, text = anyio.run(_call, url, None, "set_mode", {"mode": "solo", "perform": "in_chat"})
    assert e.mode() is not None, text
    err, text = anyio.run(_call, url, "engineering", "create_task",
                          {"task_id": "n2", "spec": {"description": "x", "criteria": [HUMAN]}})
    assert "connection acts as 'engineering'" in text and e.graph.get_task(TaskId("n2")) is None, text


def test_a_named_connection_cannot_register_the_standing_identity(door):
    _, url = door
    err, text = anyio.run(_call, url, "engineering", "register_agent",
                          {"agent_id": "user", "kind": "llm-validator", "workdir": "."})
    assert "STANDING identity" in text, text


def test_a_server_a_console_raises_takes_no_credential_of_it(monkeypatch):
    monkeypatch.setenv(config.TOKEN_ENV, "gfso_t")
    assert config.TOKEN_ENV not in config.spawned_server_popen_env()
