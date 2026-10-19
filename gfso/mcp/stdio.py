"""The MCP door over stdio, with the UI beside it — the one module that composes both doors.

It lived in `gfso.mcp.server`, which made the MCP surface import the HTTP door (`create_app`) while the HTTP door
imports the MCP surface to mount it — two doors each composing the other, an import knot (ortho audit, D-F14). The
surfaces stay leaves; the process that serves both is assembled here.
"""
from __future__ import annotations

import sys
import threading

import uvicorn

from gfso.api.server import create_app
from gfso.config import ui_address, ui_enabled
from gfso.mcp.server import create_server
from gfso.runtime import ProjectRegistry


def _serve_ui(registry, host: str, port: int) -> None:  # pragma: no cover
    """Serve the HTTP + UI + WebSocket over the SAME registry in a daemon thread, so the human watches the
    agent's MCP mutations LIVE (and follows use_project switches). All logging → stderr: stdout is the MCP
    stdio channel and MUST stay clean (a stray print would corrupt the JSON-RPC stream)."""
    # with_mcp=False — the MCP surface is this stdio process; the app is UI-only
    app = create_app(registry.engine(), registry=registry)
    config = uvicorn.Config(app, host=host, port=port, log_level="warning",
                            access_log=False, log_config=None)  # log_config=None → root logger (stderr)
    threading.Thread(target=uvicorn.Server(config).run, daemon=True).start()
    print(f"[gfso mcp] UI live at http://{host}:{port}", file=sys.stderr)


def main() -> None:  # pragma: no cover
    """Serve the MCP surface over stdio against this installation's project registry."""
    registry = ProjectRegistry()
    registry.engine()  # materialize the default project up front
    if ui_enabled():
        try:
            _serve_ui(registry, *ui_address())
        except Exception as e:
            print(f"[gfso mcp] UI not started ({e}) — MCP tools still work", file=sys.stderr)
    create_server(registry).run()  # blocks on the stdio MCP loop


if __name__ == "__main__":  # pragma: no cover
    main()
