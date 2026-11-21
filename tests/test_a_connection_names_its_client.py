"""A connection is one client, and which one is read off what it said at `initialize`, never assumed: Claude Code says
`claude-code` (its own handshake, recorded 2026-11-15: clientInfo `claude-code` 2.1.325, capabilities `roots`,
`elicitation`); what Claude Desktop says is read in the server's log the first time it connects."""
import json

import anyio
from mcp import ClientSession, types
from mcp.client.streamable_http import streamablehttp_client
from mcp.server.fastmcp import Context, FastMCP
import mcp.server.lowlevel.server as lowlevel
from mcp.shared.memory import create_client_server_memory_streams, create_connected_server_and_client_session

from gfso import config, doctor, tools_llm as TL
from gfso.adapters.llm import credentials
from gfso.mcp import protocol as P
from gfso.mcp import connect as C
from gfso.mcp.server import create_server
from gfso.runtime import ProjectRegistry
from tests.support import make_engine
from tests.test_a_connection_signs_as_its_principal import _serve


def test_the_server_log_says_the_client_once_per_session(capsys):
    e = make_engine()
    e.start()

    async def main():
        async with create_connected_server_and_client_session(
                create_server(e)._mcp_server, client_info=types.Implementation(name="claude-code", version="2.1.325")) as c:
            await c.list_tools()
            await c.call_tool("next_steps", {})
    try:
        anyio.run(main)
    finally:
        e.stop()
    said = [ln for ln in capsys.readouterr().out.splitlines() if "a client connected" in ln]
    assert said == ["[gfso] a client connected: claude-code 2.1.325, declaring {}"], said


def _kind_by_memory(name):
    """The kind a call of a session whose client named itself `name` is served under, on an in-memory session."""
    e = make_engine()
    srv = create_server(e)
    srv.add_tool(lambda: config.client_kind(), name="kind")

    async def main():
        async with create_connected_server_and_client_session(
                srv._mcp_server, client_info=types.Implementation(name=name, version="1")) as c:
            return (await c.call_tool("kind", {})).content[0].text
    try:
        return anyio.run(main)
    finally:
        e.stop()


def test_the_kind_is_the_clients_name_read_and_chat_for_any_other():
    assert [_kind_by_memory(n) for n in ("claude-code", "claude-ai", "mcp")] == ["code", "chat", "chat"]
    assert config.client_kind() is None, "outside a connection no kind is served"


def test_the_bridges_header_names_the_kind_over_the_clients_name_and_a_kind_unknown_is_refused():
    e = make_engine()
    srv = create_server(e)
    srv.add_tool(lambda: config.client_kind(), name="kind")
    srv.settings.streamable_http_path = "/mcp"
    web, url = _serve(srv.streamable_http_app())

    async def go(kind):
        async with streamablehttp_client(url, headers={config.CLIENT_HEADER: kind}) as (r, w, _), \
                ClientSession(r, w, client_info=types.Implementation(name="claude-code", version="1")) as s:
            await s.initialize()
            out = await s.call_tool("kind", {})
        return out.isError, out.content[0].text
    try:
        assert anyio.run(go, "chat") == (False, "chat")
        err, text = anyio.run(go, "terminal")
    finally:
        web.should_exit = True
        e.stop()
    assert err and "client kind 'terminal'" in text, text


def test_the_bridge_says_the_kind_its_entry_was_launched_with(monkeypatch):
    seen = []
    srv = FastMCP("echo", host="127.0.0.1", port=0)

    @srv.tool()
    async def who(ctx: Context) -> str:
        seen.append(ctx.request_context.request.headers.get(config.CLIENT_HEADER))
        return "ok"
    web, url = _serve(srv.streamable_http_app())
    monkeypatch.delenv("GFSO_AGENT_ID", raising=False)
    monkeypatch.setenv("GFSO_CLIENT", "chat")

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
    assert seen == ["chat"]


def test_the_desktop_entry_names_its_kind():
    assert doctor.desktop_entry()["env"]["GFSO_CLIENT"] == "chat"


def test_no_verb_holds_a_call_for_the_wait():
    async def main():
        async with create_connected_server_and_client_session(create_server(make_engine())._mcp_server) as c:
            return {t.name: t.inputSchema["properties"] for t in (await c.list_tools()).tools}
    listed = anyio.run(main)
    assert "wait" not in listed["next_steps"] and "wait" not in str(listed)
    assert not any(n == "wait" or "wait_for" in n for n in listed)


def _replies(monkeypatch, tmp_path, name, *verbs):
    """What a session whose client named itself `name` is answered, verb by verb, in project p1 stopped after its entry."""
    monkeypatch.setenv("GFSO_DATA_DIR", str(tmp_path))
    monkeypatch.setenv("GFSO_STORAGE", "memory")
    monkeypatch.delenv("GFSO_PROJECT", raising=False)
    reg = ProjectRegistry()

    async def go():
        async with create_connected_server_and_client_session(
                create_server(reg)._mcp_server, client_info=types.Implementation(name=name, version="1")) as c:
            await c.call_tool("act_as", {"name": "user"})      # …the person's agent, logged in as him
            await c.call_tool("use_project", {"project": "p1"})
            reg.engine("p1").pause("user", "held")
            return [json.loads((await c.call_tool(v, {})).content[0].text) for v in verbs]
    try:
        return anyio.run(go)
    finally:
        reg.engine("p1").stop()


def test_a_chat_clients_next_call_carries_the_runs_news_once(monkeypatch, tmp_path):
    """Nothing wakes a chat client and none of its calls is held: it learns at its next call, whatever the call is."""
    first, second = _replies(monkeypatch, tmp_path, "claude-ai", "tech_reports", "tech_reports")
    assert first["news"] == "the run is stopped" and "news" not in second, (first, second)


def test_a_client_that_read_it_or_has_a_wake_is_not_told_it_again(monkeypatch, tmp_path):
    read, after = _replies(monkeypatch, tmp_path, "claude-ai", "next_steps", "tech_reports")
    assert "news" not in read and "news" not in after
    (code,) = _replies(monkeypatch, tmp_path, "claude-code", "tech_reports")
    assert "news" not in code


async def _initialized(name):
    """The InitializeResult a client naming itself `name` is answered with, on a session of its own."""
    srv = create_server(make_engine())._mcp_server
    async with create_client_server_memory_streams() as (client, server):
        async with anyio.create_task_group() as tg:
            tg.start_soon(lambda: srv.run(server[0], server[1], srv.create_initialization_options()))
            async with ClientSession(client[0], client[1], client_info=types.Implementation(name=name, version="1")) as s:
                out = await s.initialize()
            tg.cancel_scope.cancel()
    return out


def test_each_kind_is_served_its_own_instructions_at_initialize():
    """The SDK's private seam (`ServerSession._received_request`, `_init_options`, the lowlevel server building its
    sessions by name): an SDK that moves either fails here, not in a client's first minute."""
    assert anyio.run(_initialized, "claude-code").instructions == P.BY_KIND["code"]
    assert lowlevel.ServerSession.__name__ == "KindSession", "the door's server installs its session class"
    assert anyio.run(_initialized, "claude-ai").instructions == P.BY_KIND["chat"] != P.BY_KIND["code"]


def test_the_header_names_the_kind_of_the_instructions_too():
    e = make_engine()
    srv = create_server(e)
    srv.settings.streamable_http_path = "/mcp"
    web, url = _serve(srv.streamable_http_app())

    async def go():
        async with streamablehttp_client(url, headers={config.CLIENT_HEADER: "chat"}) as (r, w, _), \
                ClientSession(r, w, client_info=types.Implementation(name="claude-code", version="1")) as s:
            return (await s.initialize()).instructions
    try:
        assert anyio.run(go) == P.BY_KIND["chat"]
    finally:
        web.should_exit = True
        e.stop()


def test_a_chat_client_is_refused_the_work_by_its_own_tools_and_told_who_runs_a_command():
    """A chat client has only the gfso verbs: `in_chat` had it do the work by tools it lacks."""
    e = make_engine()
    token = config.CLIENT.set("chat")
    try:
        out = TL.TOOLS["set_mode"](e, mode="solo", perform="in_chat")
        assert out.get("refused") and "only the gfso verbs" in out["error"], out
        assert config.for_the_hands("gfso log") == "the person runs `gfso log` in a terminal"
    finally:
        config.CLIENT.reset(token)
        e.stop()
    assert config.for_the_hands("gfso log") == "run `gfso log`"


def test_the_machine_s_step_is_served_done_where_nothing_of_it_is_missing(monkeypatch):
    """After a client's restart for a credential step 1 still read «once: `gfso doctor`», and it ran doctor a second time
    over a state that had changed (s23g4): the server reads the credential and the execution at the connection."""
    monkeypatch.setattr(credentials, "held", lambda: ["claude"])
    monkeypatch.setattr(P, "executions", lambda: {"default": {}})
    ready = anyio.run(_initialized, "claude-code").instructions
    assert "is set up" in ready and "`gfso doctor`. No Docker" not in ready and "2. **The repository.**" in ready
    monkeypatch.setattr(credentials, "held", lambda: [])
    assert anyio.run(_initialized, "claude-code").instructions == P.BY_KIND["code"], "a missing credential: as written"
