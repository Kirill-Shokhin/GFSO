"""A bridge whose server is gone answers every call, and goes on once the server is back — it never leaves.

Reproduced 2026-11-14 through the product's own bridge: `gfso down` under a live bridge, `gfso up` a minute later,
then six calls of six unanswered at 60 s each — `list_agents`, `register_agent`, `unregister_agent` (the hang a console
met on 11-11). The bridge had given up at its first failure because the server was not answering yet, and returned out
of the client's stdio, which deadlocks against a client still holding the pipe: the process stayed, reading nothing.
"""
import contextlib
import functools
import io
import json
import time

import anyio
import pytest
from mcp.shared.message import SessionMessage
from mcp.types import JSONRPCMessage, JSONRPCNotification, JSONRPCRequest

import gfso.mcp.connect as C


def _request(rid):
    return SessionMessage(JSONRPCMessage(JSONRPCRequest(jsonrpc="2.0", id=rid, method="tools/call", params={})))


def _run(answers_after: int, monkeypatch, send, close: bool):
    """Drive `_answer_while_down` with the server down for `answers_after` looks; returns (its result, replies)."""
    looks = iter([None] * answers_after + [{"code_version": "x"}] * 100)
    monkeypatch.setattr(C.serverctl, "runtime", lambda timeout=3.0: next(looks))
    monkeypatch.setattr(C, "_RECONNECT_WAIT_S", 0.01)

    async def go():
        to_bridge, client_read = anyio.create_memory_object_stream(10)
        client_write, from_bridge = anyio.create_memory_object_stream(10)
        for m in send:
            await to_bridge.send(m)
        if close:
            await to_bridge.aclose()
        with anyio.fail_after(10):
            ended = await C._answer_while_down(client_read, client_write)
        await client_write.aclose()
        return ended, [m async for m in from_bridge]
    return anyio.run(go)


def test_every_call_while_down_is_answered_and_the_bridge_goes_on_when_the_server_is_back(monkeypatch):
    note = SessionMessage(JSONRPCMessage(JSONRPCNotification(jsonrpc="2.0", method="notifications/initialized")))
    ended, replies = _run(3, monkeypatch, [_request(7), note, _request("x")], close=False)
    assert ended is False, "the server came back: the bridge reconnects, the client's session goes on"
    assert [r.message.root.id for r in replies] == [7, "x"], "each request answered by its own id; a notification not"
    assert all("not answering" in r.message.root.error.message for r in replies)


def test_the_client_ending_its_session_ends_the_wait(monkeypatch):
    ended, replies = _run(10 ** 6, monkeypatch, [_request(1)], close=True)
    assert ended is True and [r.message.root.id for r in replies] == [1]


def test_a_call_read_when_the_server_returns_is_answered_not_dropped(monkeypatch):
    """The server's return cancels the wait; a cancel while a reply waits on a slow client stdout lost the call it had
    already read — not answered, not left for the next leg (critic: id 5 of 10 lost with a 20 ms writer)."""
    looks = iter([None] * 3 + [{"code_version": "x"}] * 100)
    monkeypatch.setattr(C.serverctl, "runtime", lambda timeout=3.0: next(looks))
    monkeypatch.setattr(C, "_RECONNECT_WAIT_S", 0.03)

    async def go():
        to_bridge, client_read = anyio.create_memory_object_stream(20)
        client_write, from_bridge = anyio.create_memory_object_stream(0)
        answered = []

        async def slow_stdout():
            async for m in from_bridge:
                answered.append(m.message.root.id)
                await anyio.sleep(0.02)
        for i in range(1, 11):
            await to_bridge.send(_request(i))
        async with anyio.create_task_group() as tg:
            tg.start_soon(slow_stdout)
            with anyio.fail_after(10):
                await C._answer_while_down(client_read, client_write)
            await client_write.aclose()
        left = []
        while True:
            try:
                left.append(client_read.receive_nowait().message.root.id)
            except anyio.WouldBlock:
                return answered, left
    answered, left = anyio.run(go)
    assert sorted(answered + left) == list(range(1, 11)), (answered, left)


async def _dead_relay(*_a, **_k):
    raise ConnectionError("Session terminated")


def test_the_bridge_on_real_stdio_ends_once_its_client_closes_it(monkeypatch):
    """Through the SDK's own stdio server: its stdout task ends only with the write stream, so a bridge that never closed
    it outlived its client, holding the lease that keeps the shared server up (critic: alive after 20 s)."""
    line = json.dumps({"jsonrpc": "2.0", "id": 9, "method": "tools/list"}) + "\n"
    out = io.StringIO()
    monkeypatch.setattr(C, "stdio_server", functools.partial(
        C.stdio_server, stdin=anyio.wrap_file(io.StringIO(line)), stdout=anyio.wrap_file(out)))
    monkeypatch.setattr(C, "_relay", _dead_relay)
    monkeypatch.setattr(C.serverctl, "runtime", lambda timeout=3.0: None)

    async def go():
        with anyio.fail_after(10):
            await C._bridge("http://127.0.0.1:9/mcp")
    anyio.run(go)
    assert '"id":9' in out.getvalue() and "gfso up" in out.getvalue()


def test_a_leg_ends_with_its_clients_side(monkeypatch):
    """The client closing its stdio ends the relay: its other tasks waited on a server that had nothing to say."""

    @contextlib.asynccontextmanager
    async def silent_server(url, headers=None, terminate_on_close=True):
        to_server, _sink = anyio.create_memory_object_stream(10)
        _never, from_server = anyio.create_memory_object_stream(10)
        yield from_server, to_server, None

    async def quiet(*_a):
        return None
    monkeypatch.setattr(C, "streamablehttp_client", silent_server)
    monkeypatch.setattr(C, "_replay_handshake", quiet)

    async def go():
        to_bridge, client_read = anyio.create_memory_object_stream(5)
        client_write, _from_bridge = anyio.create_memory_object_stream(5)
        await to_bridge.aclose()
        with anyio.fail_after(10):
            await C._relay("http://127.0.0.1:9/mcp", client_read, client_write)
    anyio.run(go)


def test_a_reconnect_whose_handshake_is_never_answered_breaks_the_leg(monkeypatch):
    """A server that takes the session and never answers the replayed handshake held the bridge, reading nothing."""

    @contextlib.asynccontextmanager
    async def mute_server(url, headers=None, terminate_on_close=True):
        to_server, _sink = anyio.create_memory_object_stream(10)
        _never, from_server = anyio.create_memory_object_stream(10)
        yield from_server, to_server, None

    async def forever(*_a):
        await anyio.sleep_forever()
    monkeypatch.setattr(C, "streamablehttp_client", mute_server)
    monkeypatch.setattr(C, "_replay_handshake", forever)
    monkeypatch.setattr(C, "_ALIVE_WAIT_S", 0.2)

    async def go():
        _to_bridge, client_read = anyio.create_memory_object_stream(5)
        client_write, _from_bridge = anyio.create_memory_object_stream(5)
        with anyio.fail_after(10):
            await C._relay("http://127.0.0.1:9/mcp", client_read, client_write)
    began = time.monotonic()
    with pytest.raises(TimeoutError):
        anyio.run(go)
    assert time.monotonic() - began < 5, "broken by its own bound, not by the test's"
