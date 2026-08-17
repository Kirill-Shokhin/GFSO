"""GFSO CLI — serve the web application."""
from __future__ import annotations

import argparse
import logging
import sys
import threading
import webbrowser

from gfso import __version__, serverctl


def main():
    # Once, for every subcommand. This product's own vocabulary contains characters a Windows
    # console's default code page cannot encode — "verifier ≠ executor", "·", "—" — and printing one
    # raised UnicodeEncodeError and killed the command mid-output. A tool whose help text crashes on
    # the machine it is installed on is not a diagnostic anyone can act on.
    for stream in (sys.stdout, sys.stderr):
        try:
            stream.reconfigure(encoding="utf-8", errors="replace")
        except Exception:
            pass

    args = build_parser().parse_args()
    if args.command is None:
        build_parser().print_help()
        sys.exit(1)

    _dispatch(args)


def build_parser() -> argparse.ArgumentParser:
    """THE command line, as an object. Separated from `main` so that it can be ASKED whether a
    command line is valid without running it — `gfso.mcp.connect` builds a `gfso serve …` argv for
    the process it spawns, and nothing could check the two agreed. They stopped agreeing: a flag
    renamed here left the launcher passing a spelling `serve` no longer had, so every start died
    instantly with a usage message into `server.log` while the launcher reported only a timeout."""
    parser = argparse.ArgumentParser(prog="gfso", description="GFSO Protocol Engine")
    parser.add_argument("--version", action="version", version=f"gfso {__version__}")
    sub = parser.add_subparsers(dest="command")

    serve = sub.add_parser("serve", help="Run the server IN THIS PROCESS (the primitive; `gfso up` "
                                        "is the everyday command — it decides whether to start or "
                                        "restart and calls this). Comes up with the declared switches.")
    # THE address, from the one place that computes it (`GFSO_SHARED_URL` is its single knob):
    # a literal here meant `serve` could bind a port that `up`/`down`/`log` were not talking to.
    serve.add_argument("--port", type=int, default=serverctl.PORT)
    serve.add_argument("--host", default="127.0.0.1")
    serve.add_argument("--storage", choices=["sqlite", "memory"], default="sqlite")
    # None, not "data/gfso.db": a relative default resolves against the caller's directory, so this
    # one command put the DEFAULT project's database beside whoever typed it while its named
    # projects still lived in the installation's home — a split brain inside one process, and a UI
    # showing an empty (or freshly seeded demo) graph instead of the user's work.
    serve.add_argument("--db-path", default=None)
    serve.add_argument("--llm", choices=["claude", "stub"], default="claude")
    serve.add_argument("--model", default="claude-haiku-4-5-20251001")
    serve.add_argument("--no-browser", action="store_true")
    # The agent door is mounted by DEFAULT. Hand-started, this command used to hold the one address
    # with no /mcp: every probe answered, `up` called it correct, and every agent session got a 404
    # from a server that looked healthy to everything except the agent.
    serve.add_argument("--no-mcp", action="store_true",
                       help="Do NOT expose the MCP agent surface at /mcp (it is on by default)")
    # Seeding is OPT-IN. It used to happen unless `--no-seed` was passed, which no human passes:
    # typing `gfso serve` wrote a demo graph into the user's own empty database, and the UI then
    # showed a toy task tree where their work should have been.
    serve.add_argument("--seed", action="store_true",
                       help="Write the demo graph into an empty database (off by default)")
    # Kept as a hidden alias: a long-lived bridge holding OLDER code still passes `--no-seed`, and
    # an unknown flag means the server does not start at all — the stale-client failure this
    # codebase has already paid for once.
    serve.add_argument("--no-seed", action="store_true", help=argparse.SUPPRESS)
    serve.add_argument("--reload", action="store_true", help="Auto-reload on file changes")
    serve.add_argument("--log-level", default="INFO")

    mcp = sub.add_parser("mcp", help="Start a STANDALONE stdio MCP server in THIS process (its own "
                                     f"Engine; it also raises the UI on :{serverctl.PORT} itself, and both die "
                                     "with the session). `gfso connect` — the bridge to the one "
                                     "shared server — is what an agent client should point at.")
    mcp.add_argument("--db-path", default=None)   # None → the installation's home, like every door
    mcp.add_argument("--llm", choices=["claude", "stub"], default="stub")
    mcp.add_argument("--model", default="claude-haiku-4-5-20251001")

    # `run` = the headless CLI mirror (drive/inspect a graph, same surface as MCP). Logic lives in gfso.driver;
    # this is only the wiring — cli.py stays the high-level launcher, not a home for low-level tool commands.
    runp = sub.add_parser("run", help="Drive/inspect a graph headless (same commands as the MCP tools)")
    runp.add_argument("args", nargs=argparse.REMAINDER, help="<tool> [args…]  (run `gfso run` alone to list)")

    # The MCP door an agent client is registered against: `claude mcp add --scope user gfso -- gfso connect`.
    # It is a console script, so the client spawns the interpreter the package was installed into —
    # `python -m gfso.mcp.connect` only works when whatever `python` resolves to happens to be that
    # same environment, which for a client started outside the venv it usually is not.
    sub.add_parser("connect", help="MCP stdio door: ensure the one shared server is up, then bridge "
                                   "this session's stdio to it (what an agent client runs)")

    upp = sub.add_parser("up", help=f"Make THE shared server ({serverctl.BASE}) correct and current: "
                                    "start it if down, restart it if it serves stale code or the "
                                    "wrong switches, leave it alone otherwise. Idempotent — there "
                                    "is only ever one server.")
    upp.add_argument("--force", action="store_true",
                     help="Restart even when other sessions are connected or work is in flight. "
                          "Without this, a stale server with someone else on it is reported and "
                          "left alone: restarting ends their run, and the model subprocesses it "
                          "spawned outlive it.")

    sub.add_parser("down", help="Stop the shared server (code update: the next session reconnect "
                                "auto-spawns a fresh one)")

    setupp = sub.add_parser("setup", help="One command after installing: register the agent door "
                                          "with Claude Code, bring the server up, open the UI, and "
                                          "report what it found. Idempotent — safe to re-run.")
    setupp.add_argument("--desktop", action="store_true",
                        help="Also write the entry into Claude Desktop's claude_desktop_config.json "
                             "(a backup is kept; restart Desktop afterwards). Without this flag the "
                             "block is printed for you to paste — another application's config is "
                             "not edited unless you ask for it by name.")

    sub.add_parser("doctor", help="What this installation is and whether it can work: version, "
                                  "where state lives, who holds the port, whether the Claude Code "
                                  "CLI answers. Paste its output into a bug report.")

    demo = sub.add_parser("demo", help="Run a shipped example (no name lists them). `human_only` "
                                       "shows the gate refusing a self-signed PASS, with no AI.")
    demo.add_argument("name", nargs="?", default=None)

    logp = sub.add_parser("log", help="The observation field in the terminal — same persisted lines "
                                      "the UI panel shows (per project)")
    logp.add_argument("--project", default=None, help="project name (default: the active one)")
    logp.add_argument("-n", type=int, default=40, help="lines to show (default 40)")
    logp.add_argument("-f", "--follow", action="store_true", help="keep polling for new lines")

    return parser


def _dispatch(args) -> None:
    if args.command == "serve":
        _serve(args)
    elif args.command == "mcp":
        _mcp(args)
    elif args.command == "run":
        from gfso.driver import run
        run(args.args)
    elif args.command == "connect":
        from gfso.mcp.connect import main as connect_main
        connect_main()
    elif args.command == "up":
        from gfso.mcp.connect import ensure_correct
        # Non-zero when it DECLINED to reconcile: `gfso up && …` could not otherwise tell a server
        # that is now current from one left stale because somebody else is working on it.
        try:
            sys.exit(1 if ensure_correct(force=args.force)["action"] == "left-alone" else 0)
        except RuntimeError as ex:      # the server did not come up: say so, do not throw a stack
            sys.exit(f"gfso: {ex}")
    elif args.command == "down":
        _down()
    elif args.command == "log":
        _log(args)
    elif args.command == "setup":
        from gfso.doctor import setup
        sys.exit(setup(desktop=args.desktop))
    elif args.command == "doctor":
        from gfso.doctor import doctor
        sys.exit(doctor())
    elif args.command == "demo":
        sys.exit(_demo(args.name))


def _demo(name: str | None) -> int:
    """Run one shipped example in THIS process, through runpy — they are library code, not scripts
    that exit."""
    import runpy
    from gfso.examples import DEMOS, NEEDS_MODEL
    if name not in DEMOS:
        if name is not None:
            print(f"no demo named {name!r}")
        print("demos (run `gfso demo <name>`):")
        for key, what in DEMOS.items():
            print(f"  {key:18} {what}")
        return 1 if name is not None else 0
    if name in NEEDS_MODEL:
        from gfso.doctor import claude_cli
        found, detail = claude_cli()
        if not found:
            print(f"`{name}` spawns model processes and the Claude Code CLI is not usable: {detail}")
            print("run `gfso doctor` for what to fix, or `gfso demo human_only` — it needs no model.")
            return 1
    runpy.run_module(f"gfso.examples.{name}", run_name="__main__")
    return 0


def _log(args):
    """Terminal mirror of the UI observation panel: the persisted pipeline lines of one project."""
    import json as _json
    import os
    import time
    import urllib.parse
    import urllib.request
    base = f"{serverctl.BASE}/api/pipeline?limit={max(args.n, 1)}"
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
    api = f"{serverctl.BASE}/api/shutdown"
    try:
        # `down` is the deliberate stop — it means it even if sessions are on the server. The
        # server refuses an unforced stop while clients are working, which is what keeps a routine
        # reconcile from taking down someone's run.
        out = urllib.request.urlopen(urllib.request.Request(
            api, data=b'{"force": true}', method="POST",
            headers={"Content-Type": "application/json"}), timeout=3).read()
        print(f"server stopping: {_json.loads(out)}")
    except Exception as e:
        print(f"no server answering at {api} ({type(e).__name__}) — nothing to stop")


def _mcp(args):
    import os
    from gfso.runtime import data_dir
    os.environ["GFSO_DB_PATH"] = args.db_path or str(data_dir() / "gfso.db")
    os.environ["GFSO_LLM"] = args.llm
    os.environ["GFSO_MODEL"] = args.model
    from gfso.mcp.server import main as mcp_main
    mcp_main()


def _serve(args):
    logging.basicConfig(level=getattr(logging, args.log_level.upper()), format="%(message)s")

    # Store config in env for reload mode
    import os

    # Whatever raises the server — `gfso up`, a session's connect.py, or this command typed by hand
    # — it comes up with the switches this repository DECLARES. They are per-process and decide what
    # a run measures (a same-Del node self-verifies with GFSO_VALIDATE_INTERNAL off, so no
    # independent verdict ever arrives), and a hand-typed `serve` used to silently drop them: one
    # run waited 25 minutes for a verdict that could not come. An explicitly exported value still
    # wins — arm G⁻ sets GFSO_L2_GATE=0 deliberately — so this fills gaps, it does not override.
    try:
        from gfso.serverctl import declared
        for key, value in declared().items():
            os.environ.setdefault(key, value)
    except Exception as ex:                       # never let the declaration stop the server
        print(f"gfso: could not read the declared server config ({ex})")
    from gfso.runtime import data_dir
    os.environ["GFSO_STORAGE"] = args.storage
    os.environ["GFSO_DB_PATH"] = args.db_path or str(data_dir() / "gfso.db")
    os.environ["GFSO_LLM"] = args.llm
    os.environ["GFSO_MODEL"] = args.model
    os.environ["GFSO_SEED"] = "1" if args.seed else ""   # the name the app actually reads
    os.environ["GFSO_WITH_MCP"] = "" if args.no_mcp else "1"

    if not args.no_browser:
        threading.Timer(1.5, lambda: webbrowser.open(f"http://{args.host}:{args.port}")).start()

    try:
        import uvicorn
    except ImportError:
        sys.exit("uvicorn is missing from this environment — reinstall: pip install gfso")

    # Windows: run on the SELECTOR loop, and install it OURSELVES.
    #
    # The default proactor loop dies on the accept path when a client vanishes mid-request — which a
    # headless agent's MCP bridge does every time its process ends. `WinError 64` propagates out of
    # `accept_coro`, the accept loop stops, and the process stays ALIVE while answering nothing:
    # every later call gets "connection refused" from a server that is still running. Observed
    # live three times, each killing a multi-hour run minutes after the agent's first tool session.
    #
    # Setting the event-loop POLICY does not help: uvicorn 0.42 picks the loop class itself
    # (`uvicorn.loops.asyncio.asyncio_loop_factory` returns `ProactorEventLoop` on win32) and
    # ignores the policy. So the loop is created here and uvicorn is told to touch nothing
    # (`loop="none"`). Verified by the absence of `IocpProactor` in the server's traceback.
    if sys.platform == "win32":
        import asyncio
        config = uvicorn.Config(
            "gfso.api.server:app",
            host=args.host, port=args.port,
            log_level=args.log_level.lower(),
            loop="none",
            reload=args.reload,
            reload_dirs=["gfso"] if args.reload else None,
        )
        loop = asyncio.SelectorEventLoop()
        asyncio.set_event_loop(loop)
        try:
            loop.run_until_complete(uvicorn.Server(config).serve())
        finally:
            loop.close()
        return

    uvicorn.run(
        "gfso.api.server:app",
        host=args.host, port=args.port,
        log_level=args.log_level.lower(),
        reload=args.reload,
        reload_dirs=["gfso"] if args.reload else None,
    )


if __name__ == "__main__":
    main()
