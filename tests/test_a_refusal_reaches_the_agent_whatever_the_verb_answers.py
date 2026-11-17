"""Every verb may answer a refusal (`{"error": …, "refused": true}`); over MCP the SDK validates the answer against
the verb's declared type, and a refused `decompose` (declared a list) reached the agent as a pydantic error with the
refusal's own text cut away (2026-11-13)."""
import anyio
from mcp.server.fastmcp import FastMCP
from mcp.shared.memory import create_connected_server_and_client_session

from gfso import tools_llm as TL
from gfso.mcp.server import _bind
from tests.support import make_engine


def test_a_refused_decompose_says_why_over_mcp():
    e = make_engine()
    e.start()
    srv = FastMCP("p")
    srv.add_tool(_bind(e, TL.TOOLS["decompose"]), name="decompose")
    got = {}

    async def main():
        async with create_connected_server_and_client_session(srv._mcp_server, raise_exceptions=False) as c:
            r = await c.call_tool("decompose", {"parent_id": "no-such-node", "children": []})
            got["text"] = "".join(getattr(x, "text", "") for x in r.content)
    try:
        anyio.run(main)
    finally:
        e.stop()
    assert "validation error" not in got["text"] and ("error" in got["text"] or "refused" in got["text"]), got["text"][:300]
