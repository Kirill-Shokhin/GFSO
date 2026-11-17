"""A call its client cancels while the verb runs ends as cancelled, and the session keeps serving: the verb's worker
thread shielded the await, the wrapper returned as if answered, the SDK answered a second time and its assertion
("Request already responded to") ended the whole session — every call in flight lost, the bridge saying the server
restarted (a tester's run, 2026-11-13; reproduced here before the fix)."""
import time

import anyio
import mcp.types as t
from mcp.server.fastmcp import FastMCP
from mcp.shared.memory import create_connected_server_and_client_session

from gfso.mcp.server import _bind
from tests.support import make_engine


def slow_verb(engine) -> dict:
    """Sleeps past the client's cancel."""
    time.sleep(0.6)
    return {"late": True}


def quick_verb(engine) -> dict:
    """Answers at once."""
    return {"ok": True}


def test_a_cancelled_call_ends_and_the_next_call_is_served():
    e = make_engine()
    srv = FastMCP("p")
    srv.add_tool(_bind(e, slow_verb), name="slow")
    srv.add_tool(_bind(e, quick_verb), name="quick")
    got = {}

    async def main():
        async with create_connected_server_and_client_session(srv._mcp_server, raise_exceptions=False) as c:
            async def call_slow():
                try:
                    await c.send_request(t.ClientRequest(t.CallToolRequest(
                        params=t.CallToolRequestParams(name="slow", arguments={}))), t.CallToolResult)
                except Exception as ex:
                    got["slow"] = str(ex)
            async with anyio.create_task_group() as tg:
                tg.start_soon(call_slow)
                await anyio.sleep(0.2)
                await c.send_notification(t.ClientNotification(t.CancelledNotification(
                    params=t.CancelledNotificationParams(requestId=c._request_id - 1, reason="moved"))))
                await anyio.sleep(0.8)
            with anyio.fail_after(5):
                got["quick"] = (await c.call_tool("quick", {})).content[0].text
    try:
        anyio.run(main)
    finally:
        e.stop()
    assert "cancelled" in got.get("slow", "") and '"ok": true' in got.get("quick", "")
