"""A verb that may make a project and is refused there unmakes it (`kept_if_done`) — and the door must not read the
engine it just closed: `create_task` on a name never opened answered `Cannot operate on a closed database.`, the
sqlite error leaking where the refusal's own text belonged (measured live, 2026-11-19)."""
import json

import anyio
import pytest
from mcp import types
from mcp.shared.memory import create_connected_server_and_client_session

from gfso.mcp.server import create_server
from gfso.runtime import ProjectRegistry


@pytest.mark.parametrize("client", ["claude-ai", "claude-code"])
def test_a_refused_create_task_on_a_new_name_answers_its_refusal_not_a_closed_database(monkeypatch, tmp_path, client):
    monkeypatch.setenv("GFSO_DATA_DIR", str(tmp_path))
    monkeypatch.delenv("GFSO_PROJECT", raising=False)
    reg = ProjectRegistry()

    async def go():
        async with create_connected_server_and_client_session(
                create_server(reg)._mcp_server, client_info=types.Implementation(name=client, version="1")) as c:
            return await c.call_tool("create_task", {"project": "brand_new", "title": "t"})
    r = anyio.run(go)
    text = r.content[0].text
    assert "refused" in text or "error" in text, text
    assert "closed database" not in text and "Error executing" not in text, text
