"""GFSO CLI — serve the web application."""
from __future__ import annotations

import argparse
import logging
import sys
import threading
import webbrowser


def main():
    parser = argparse.ArgumentParser(prog="gfso", description="GFSO Protocol Engine")
    sub = parser.add_subparsers(dest="command")

    serve = sub.add_parser("serve", help="Start GFSO web server")
    serve.add_argument("--port", type=int, default=8000)
    serve.add_argument("--host", default="127.0.0.1")
    serve.add_argument("--storage", choices=["sqlite", "memory"], default="sqlite")
    serve.add_argument("--db-path", default="gfso.db")
    serve.add_argument("--llm", choices=["claude", "stub"], default="claude")
    serve.add_argument("--api-key", default=None)
    serve.add_argument("--model", default="claude-haiku-4-5-20251001")
    serve.add_argument("--no-browser", action="store_true")
    serve.add_argument("--mcp", action="store_true",
                       help="Also expose the MCP agent surface at /mcp over the SAME Engine (needs gfso[mcp])")
    serve.add_argument("--no-seed", action="store_true", help="Skip demo seed on empty DB")
    serve.add_argument("--reload", action="store_true", help="Auto-reload on file changes")
    serve.add_argument("--log-level", default="INFO")

    mcp = sub.add_parser("mcp", help="Start the MCP server (stdio) — also serves the live UI at :8000 over the same Engine (needs gfso[mcp])")
    mcp.add_argument("--db-path", default="data/gfso.db")
    mcp.add_argument("--llm", choices=["claude", "stub"], default="stub")
    mcp.add_argument("--model", default="claude-haiku-4-5-20251001")

    # `run` = the headless CLI mirror (drive/inspect a graph, same surface as MCP). Logic lives in gfso.driver;
    # this is only the wiring — cli.py stays the high-level launcher, not a home for low-level tool commands.
    runp = sub.add_parser("run", help="Drive/inspect a graph headless (same commands as the MCP tools)")
    runp.add_argument("args", nargs=argparse.REMAINDER, help="<tool> [args…]  (run `gfso run` alone to list)")

    args = parser.parse_args()
    if args.command is None:
        parser.print_help()
        sys.exit(1)

    if args.command == "serve":
        _serve(args)
    elif args.command == "mcp":
        _mcp(args)
    elif args.command == "run":
        from gfso.driver import run
        run(args.args)


def _mcp(args):
    import os
    os.environ["GFSO_DB_PATH"] = args.db_path
    os.environ["GFSO_LLM"] = args.llm
    os.environ["GFSO_MODEL"] = args.model
    from gfso.mcp.server import main as mcp_main
    mcp_main()


def _serve(args):
    logging.basicConfig(level=getattr(logging, args.log_level.upper()), format="%(message)s")

    # Store config in env for reload mode
    import os
    os.environ["GFSO_STORAGE"] = args.storage
    os.environ["GFSO_DB_PATH"] = args.db_path
    os.environ["GFSO_LLM"] = args.llm
    os.environ["GFSO_API_KEY"] = args.api_key or ""
    os.environ["GFSO_MODEL"] = args.model
    os.environ["GFSO_NO_SEED"] = "1" if args.no_seed else ""
    os.environ["GFSO_WITH_MCP"] = "1" if args.mcp else ""

    if not args.no_browser:
        threading.Timer(1.5, lambda: webbrowser.open(f"http://{args.host}:{args.port}")).start()

    import uvicorn
    uvicorn.run(
        "gfso.api.server:app",
        host=args.host, port=args.port,
        log_level=args.log_level.lower(),
        reload=args.reload,
        reload_dirs=["gfso"] if args.reload else None,
    )


if __name__ == "__main__":
    main()
