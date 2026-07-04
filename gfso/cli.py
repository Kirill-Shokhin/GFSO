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
    serve.add_argument("--db-path", default="data/gfso.db")
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

    sub.add_parser("down", help="Stop the shared server (code update: the next session reconnect "
                                "auto-spawns a fresh one)")

    logp = sub.add_parser("log", help="The observation field in the terminal — same persisted lines "
                                      "the UI panel shows (per project)")
    logp.add_argument("--project", default=None, help="project name (default: the active one)")
    logp.add_argument("-n", type=int, default=40, help="lines to show (default 40)")
    logp.add_argument("-f", "--follow", action="store_true", help="keep polling for new lines")

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
    elif args.command == "down":
        _down()
    elif args.command == "log":
        _log(args)


def _log(args):
    """Terminal mirror of the UI observation panel: the persisted pipeline lines of one project."""
    import json as _json
    import os
    import time
    import urllib.parse
    import urllib.request
    from urllib.parse import urlparse
    u = urlparse(os.environ.get("GFSO_SHARED_URL", "http://127.0.0.1:8000/mcp"))
    base = f"http://{u.hostname}:{u.port or 8000}/api/pipeline?limit={max(args.n, 1)}"
    if args.project:
        base += "&project=" + urllib.parse.quote(args.project)
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass
    last: list = []
    while True:
        try:
            rows = _json.loads(urllib.request.urlopen(base, timeout=5).read())
        except Exception as e:
            print(f"no server answering ({type(e).__name__})")
            return
        printed = {(x["ts"], x["message"]) for x in last}
        for r in rows:
            if not args.follow or (r["ts"], r["message"]) not in printed:
                print(f"{r['ts']} [{r['source']}] {r['message']}")
        if not args.follow:
            return
        last = rows
        time.sleep(2)


def _down():
    import json as _json
    import os
    import urllib.request
    from urllib.parse import urlparse
    u = urlparse(os.environ.get("GFSO_SHARED_URL", "http://127.0.0.1:8000/mcp"))
    api = f"http://{u.hostname}:{u.port or 8000}/api/shutdown"
    try:
        out = urllib.request.urlopen(urllib.request.Request(api, data=b"{}", method="POST",
                                     headers={"Content-Type": "application/json"}), timeout=3).read()
        print(f"server stopping: {_json.loads(out)}")
    except Exception as e:
        print(f"no server answering at {api} ({type(e).__name__}) — nothing to stop")


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
