"""The bridge a session speaks through: what it keeps so a reconnect lands on a LIVE session."""
import socket
import threading
import time
from pathlib import Path

import anyio
import pytest
import uvicorn
from mcp import ClientSession
from mcp.server.fastmcp import FastMCP

from gfso.mcp import connect as C



def test_the_bridge_keeps_the_handshake_so_a_reconnect_has_a_live_session():
    """The reconnect existed and a whole agent-door run still died on "Session terminated".

    A reconnect opens a FRESH upstream session, and the client never sends its handshake again — it
    believes it is already initialized. So the new session was never initialized and every call
    through it failed exactly like the dead one it had just replaced (measured 2026-08-21: an entire
    run driven from the CLI mirror instead, because the agent door answered nothing for fifty
    minutes). What opens a session is kept, and replayed."""

    class _Root:
        def __init__(self, method):
            self.method = method

    class _Msg:
        def __init__(self, method):
            self.root = _Root(method)

    C._HANDSHAKE.clear()
    C._remember_handshake(_Msg("tools/call"))
    assert C._HANDSHAKE == []                      # …ordinary traffic is not a handshake
    init = _Msg("initialize")
    C._remember_handshake(init)
    C._remember_handshake(_Msg("notifications/initialized"))
    assert [m.root.method for m in C._HANDSHAKE] == ["initialize", "notifications/initialized"]
    C._remember_handshake(_Msg("initialize"))      # …a second one replaces, never appends
    assert [m.root.method for m in C._HANDSHAKE] == ["initialize"]
    C._HANDSHAKE.clear()


def test_the_bridge_reads_a_requests_id_and_bounds_its_wait():
    """Two calls of the two simplest verbs in the product ate a whole session — 30 minutes each.

    The dead-session detector fires only when the server ANSWERS; after a restart the upstream can
    instead go quiet, and the client then waits out its own idle timeout (Claude Code: 1800s) with no
    progress, no error, and no way to tell "working hard" from "will never answer". Measured on the
    agent door 2026-08-22, while the same server answered HTTP in 70 ms. The bridge now times what it
    forwards and breaks — which is the rebuild-and-replay path it already has."""
    class _Msg:
        def __init__(self, rid):
            self.message = type("M", (), {"root": type("R", (), {"id": rid})()})()

    assert C._request_id(_Msg(7)) == 7
    assert C._request_id(object()) is None                # a notification carries no id

    # …and the cap is well under any client's idle timeout: the point is a legible failure
    assert 0 < C._CALL_TIMEOUT_S <= 300


def _quick_bridge(monkeypatch):
    """The bridge's clocks, in fractions of a second."""
    monkeypatch.setattr(C, "_CALL_TIMEOUT_S", 0.3)
    monkeypatch.setattr(C, "_ALIVE_WAIT_S", 0.5)
    monkeypatch.setattr(C, "_WATCH_EVERY_S", 0.05)


def test_a_session_that_answers_nothing_breaks_the_watch(monkeypatch):
    """The silence the watch exists for stays a break: asked once, and no answer."""
    _quick_bridge(monkeypatch)
    asked = []

    async def ask():
        asked.append(1)

    async def go():
        await C._watch_unanswered({"call": time.monotonic()}, anyio, ask, {}, None)

    with pytest.raises(ConnectionError):
        anyio.run(go)
    assert len(asked) == 1


def test_a_verb_longer_than_the_watch_is_answered_once_through_the_real_bridge(monkeypatch):
    """A live session keeps its long call: the verb runs ONCE, its answer arrives, and the bridge's own question never
    reaches the client. Broken on silence, a `plan` over 180 s came back "not answered", was sent again and paid again,
    each 204 s (rehearsal, 2026-11-03); the progress said to clear it carries no id and cleared nothing."""
    _quick_bridge(monkeypatch)
    ran = []
    server = FastMCP("slow", host="127.0.0.1", port=0)

    @server.tool()
    async def slow() -> str:      # off the server's loop, as a verb of the product is (`_bind`)
        ran.append(1)
        await anyio.to_thread.run_sync(time.sleep, 1.5)
        return "done"

    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        port = s.getsockname()[1]
    web = uvicorn.Server(uvicorn.Config(server.streamable_http_app(), port=port, log_level="error"))
    threading.Thread(target=web.run, daemon=True).start()
    while not web.started:
        time.sleep(0.02)

    async def go():
        to_bridge, from_client = anyio.create_memory_object_stream(16)
        to_client, from_bridge = anyio.create_memory_object_stream(16)
        async with anyio.create_task_group() as tg:
            tg.start_soon(C._relay, f"http://127.0.0.1:{port}/mcp", from_client, to_client)
            async with ClientSession(from_bridge, to_bridge) as session:
                await session.initialize()
                out = await session.call_tool("slow")
            tg.cancel_scope.cancel()
        return out

    try:
        out = anyio.run(go)
    finally:
        web.should_exit = True
    assert out.content[0].text == "done" and not out.isError
    assert len(ran) == 1


def test_a_call_past_the_ceiling_is_answered_on_a_live_session(monkeypatch):
    """A verb that never returns on a session that answers: the wait ends with a word, under the client's own ceiling,
    the leg left standing for the rest (critic: unbounded after the question to the session was added)."""
    _quick_bridge(monkeypatch)
    monkeypatch.setattr(C, "_CALL_CEILING_S", 0.4)
    pending, alive, late = {"call": time.monotonic()}, {}, []

    async def ask():
        alive["at"] = time.monotonic()

    async def past(rid):
        late.append(rid)
        pending.pop(rid)

    async def go():
        with anyio.move_on_after(1):
            await C._watch_unanswered(pending, anyio, ask, alive, past)

    anyio.run(go)
    assert late == ["call"]


def test_the_whole_path_stands_where_the_client_does_not_cut_the_instructions():
    """Claude Code cut the server's instructions at 4096 characters ("never dec… [truncated]"): the link at the go, the
    wait and the report of the end stood past it, and no fresh agent read them (critic, measured)."""
    text = (Path(C.__file__).parent / "ORCHESTRATOR.md").read_text(encoding="utf-8")
    seen = text[:4000]
    assert text.index("## An executor on this host") < 4000
    # a heading under the cut proved nothing of its body: the host executor's `git switch` stood past it (audit, 11-07)
    # …and where it can fire: the executors are known after `set_mode`, so the check stands in the go's step
    assert seen.index("git switch -c work/<project>") > seen.index("set_mode(")
    for said in ("git switch -c work/<project>", "not in thinking", "auto_decompose(plan=path)", "next_steps(wait=600)",
                 "its `say` asks", "never ask its value in chat"):
        assert said in seen, said
