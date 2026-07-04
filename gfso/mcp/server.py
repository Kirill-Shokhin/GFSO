"""FastMCP server (track-b): exposes the CORE upper API to the agent as MCP tools.

Requires the MCP SDK: `pip install gfso[mcp]`. Run:  python -m gfso.mcp.server
Holds ONE Engine (SQLite-persistent) = the same CORE the UI observes — the agent's tool calls and the
UI watch one graph. Every authoring tool desugars to the closed 12-signal FSM (no bypass); the tool
docstrings (from tools.py) become the tool descriptions the agent reads.
"""
from __future__ import annotations

import functools
import inspect
import os

from gfso.engine import Engine
from gfso.runtime import build_engine_from_env   # shared CORE factory (also used by the CLI mirror)
from gfso import tools as T                       # the shared action surface (MCP + CLI both bind it)


def _bind(engine: Engine, fn):
    """Wrap a tools.py function (engine, *args) as an MCP tool: drop `engine` from the signature so the
    SDK infers the schema from the remaining typed params; keep the docstring as the description.

    Annotations are resolved to real types here: tools.py uses `from __future__ import annotations`
    (string hints), and the wrapper's globals are this module's — so the SDK's schema introspection would
    fail to eval e.g. `Optional[str]`. `get_type_hints(fn)` resolves them in tools.py's own namespace."""
    import typing
    hints = typing.get_type_hints(fn)
    sig = inspect.signature(fn)
    params = [
        (p.replace(annotation=hints[p.name]) if p.name in hints else p)
        for p in list(sig.parameters.values())[1:]  # drop the leading `engine`
        if not p.name.startswith("_")               # underscore params are transport-internal (e.g. _progress)
    ]

    @functools.wraps(fn)
    def wrapper(*args, **kwargs):
        return fn(engine, *args, **kwargs)

    wrapper.__signature__ = sig.replace(
        parameters=params, return_annotation=hints.get("return", sig.return_annotation))
    wrapper.__annotations__ = {k: v for k, v in hints.items() if k != "engine"}
    return wrapper


def _bind_auto_decompose(engine: Engine):  # pragma: no cover — exercised live over MCP
    """auto_decompose runs for minutes (several headless one-shots) — bind it ASYNC with an MCP Context so
    each pipeline stage streams to the client as a progress notification instead of a silent multi-minute
    wait. Presentation plumbing only: the logic stays in tools.auto_decompose (`_progress` is its
    transport-internal callback; stderr keeps logging regardless)."""
    import asyncio
    from mcp.server.fastmcp import Context

    async def auto_decompose(request: str, root_id: str = "root", assignee: str = "human",
                             depth: int = 1, model: str = "sonnet", ctx: Context = None) -> dict:
        loop = asyncio.get_running_loop()
        step = {"n": 0}

        def prog(msg: str) -> None:  # called from the executor thread
            step["n"] += 1
            if ctx is not None:
                try:
                    asyncio.run_coroutine_threadsafe(
                        ctx.report_progress(step["n"], None, f"[decompose] {msg}"), loop)
                except Exception:
                    pass  # progress is presentation — never break the pipeline

        return await loop.run_in_executor(None, functools.partial(
            T.auto_decompose, engine, request, root_id=root_id, assignee=assignee,
            depth=depth, model=model, _progress=prog))

    auto_decompose.__doc__ = T.auto_decompose.__doc__
    # `from __future__ import annotations` stringifies hints and Context is imported locally — hand the
    # SDK real types so its schema introspection can evaluate the signature.
    auto_decompose.__annotations__ = {"request": str, "root_id": str, "assignee": str,
                                      "depth": int, "model": str, "ctx": Context, "return": dict}
    return auto_decompose


def create_server(engine: Engine):
    """Register every tools.py function on a FastMCP server. Raises if the MCP SDK is absent."""
    try:
        from mcp.server.fastmcp import FastMCP
    except ImportError as e:  # pragma: no cover
        raise RuntimeError("MCP SDK not installed — run `pip install gfso[mcp]`") from e
    server = FastMCP("gfso")
    for name, fn in T.TOOLS.items():
        if name == "auto_decompose":  # long-running: async + MCP progress notifications
            server.add_tool(_bind_auto_decompose(engine), name=name,
                            description=(fn.__doc__ or "").strip())
            continue
        server.add_tool(_bind(engine, fn), name=name, description=(fn.__doc__ or "").strip())
    return server


def _serve_ui(engine: Engine, host: str, port: int) -> None:  # pragma: no cover
    """Serve the HTTP + UI + WebSocket over the SAME Engine in a daemon thread, so the human watches the
    agent's MCP mutations LIVE. All logging → stderr: stdout is the MCP stdio channel and MUST stay clean
    (a stray print would corrupt the JSON-RPC stream)."""
    import sys, threading, uvicorn
    from gfso.api.server import create_app
    app = create_app(engine)  # with_mcp=False — the MCP surface is this stdio process; the app is UI-only
    config = uvicorn.Config(app, host=host, port=port, log_level="warning",
                            access_log=False, log_config=None)  # log_config=None → root logger (stderr)
    threading.Thread(target=uvicorn.Server(config).run, daemon=True).start()
    print(f"[gfso mcp] UI live at http://{host}:{port}", file=sys.stderr)


def main() -> None:  # pragma: no cover
    engine = build_engine_from_env()
    if os.environ.get("GFSO_MCP_UI", "1") != "0":
        try:
            _serve_ui(engine, os.environ.get("GFSO_UI_HOST", "127.0.0.1"),
                      int(os.environ.get("GFSO_UI_PORT", "8000")))
        except Exception as e:
            import sys
            print(f"[gfso mcp] UI not started ({e}) — MCP tools still work", file=sys.stderr)
    create_server(engine).run()  # blocks on the stdio MCP loop


if __name__ == "__main__":  # pragma: no cover
    main()
