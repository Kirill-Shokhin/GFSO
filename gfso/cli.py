"""GFSO CLI — serve the web application."""
from __future__ import annotations

import argparse
import asyncio
import ctypes
import json
import logging
import os
import runpy
import sys
import threading
import time
import urllib.parse
import urllib.request
import webbrowser

from gfso import __version__, serverctl
from gfso.config import LOOPBACK, install_mcp_env, install_serve_env
from gfso import serverctl
from gfso.doctor import claude_cli, doctor, setup
from gfso.examples import DEMOS, NEEDS_MODEL
from gfso.runtime import data_dir


def main():
    """The `gfso` entry point: parse the subcommand and hand off to the verb that serves it.

    Owns one thing before dispatch — making stdout encodable, because this product's own
    vocabulary carries characters a Windows console cannot print by default.
    """
    # Once, for every subcommand. This product's own vocabulary contains characters a Windows
    # console's default code page cannot encode — "verifier ≠ executor", "·", "—" — and printing one
    # raised UnicodeEncodeError and killed the command mid-output. A tool whose help text crashes on
    # the machine it is installed on is not a diagnostic anyone can act on.
    for stream in (sys.stdout, sys.stderr):
        try:
            stream.reconfigure(encoding="utf-8", errors="replace")
        except Exception:
            pass  # a redirected stream or a non-console host: nothing to set, nothing lost
    # …AND THE CONSOLE HAS TO AGREE. Writing UTF-8 into a console still set to a legacy code page
    # renders every dash and arrow as mojibake — `вЂ"` where an em-dash belongs — through the whole
    # of this product's most-read prose (measured on the human door 2026-08-22: a tester reported it
    # as corrupted STORED data; the store was clean, the terminal was not). Asking Windows for
    # UTF-8 output costs one call and is what makes the reconfigure above visible.
    if os.name == "nt":
        try:
            ctypes.windll.kernel32.SetConsoleOutputCP(65001)
        except Exception:
            pass          # a redirected stream or a non-console host: nothing to set, nothing lost

    # ONE grammar for `project`, whichever command a person learnt first: `gfso run` takes
    # `project=<name>` and `gfso log` took only `--project <name>`, and each refused the other's
    # spelling. Translated here rather than in either parser, so both keep their own shape.
    # …EXCEPT WHERE THE SUBCOMMAND TAKES IT AS A BARE WORD. `run` and `status` pass their tail
    # through verbatim (`project=<name>` is the grammar their own help documents), so translating it
    # here turned `gfso status project=w20a` into an option neither parser has — and the error then
    # named `--project=w20a`, a flag the person never typed, sending them to look for it. The
    # translation exists for `log`, which really does take a flag (CLI door, 2026-09-02).
    _passthrough = len(sys.argv) > 1 and sys.argv[1] in ("run", "status")
    argv = [a if _passthrough or not a.startswith("project=")
            else f"--project={a.split('=', 1)[1]}"
            for a in sys.argv[1:]]
    args = build_parser().parse_args(argv)
    if args.command is None:
        build_parser().print_help()
        sys.exit(1)

    _dispatch(args)


def _add_status_parser(sub) -> None:
    """`gfso status` — the graph as a tree a person reads, which no door had."""
    stp = sub.add_parser("status", help="Show the graph as an indented tree: state and holder per "
                                        "node, then what the frontier is holding")
    stp.add_argument("args", nargs=argparse.REMAINDER,
                     help="[<root_id>] [project=<name>]")


def _add_projects_parser(sub) -> None:
    """The `projects` subcommand, built apart — the human door's answer to `list_projects`, plus the
    delete the agent door has always had and the shell had no way to reach."""
    projp = sub.add_parser("projects", help="List the project graphs this server holds, most recently "
                                            "worked in first — the human door's answer to "
                                            "`list_projects`, which only the agent door had")
    projp.add_argument("-n", type=int, default=20, help="how many to show (default 20; 0 = all)")
    projp.add_argument("--match", default="", help="substring filter")
    projp.add_argument("--delete", default="", metavar="NAME",
                       help="delete one project irreversibly (graph, audit log and DB file); needs "
                            "--yes. The agent door has had this verb; the human door had no way to "
                            "clean up after itself")
    projp.add_argument("--yes", action="store_true", help="confirm --delete")



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
    serve.add_argument("--host", default=LOOPBACK)
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

    _add_status_parser(sub)
    _add_projects_parser(sub)

    logp = sub.add_parser("log", help="The observation field in the terminal — same persisted lines "
                                      "the UI panel shows (per project)")
    logp.add_argument("--project", default=None,
                      help="project name (default: the active one); `project=<name>` also accepted, "
                           "as on `gfso run`")
    logp.add_argument("-n", type=int, default=40, help="lines to show (default 40)")
    logp.add_argument("-f", "--follow", action="store_true", help="keep polling for new lines")

    return parser


def _dispatch(args) -> None:
    if args.command == "serve":
        _serve(args)
    elif args.command == "mcp":
        _mcp(args)
    elif args.command in ("run", "status"):
        # ONE lazy import for both: the driver pulls the whole verb registry behind it, which
        # `serve` and `up` must not pay for — and two import lines for one module is the second
        # spelling this package's own instrument counts.
        from gfso.driver import run, status
        # THE EXIT CODE CARRIES THE REFUSAL. The verbs answer rather than raise — deliberate, and
        # about the SHAPE of the answer — but every 422 came back as rc 0, so a batch of `gfso run`
        # calls reported success on the ones the engine had refused (measured 2026-08-21).
        raise SystemExit((run if args.command == "run" else status)(args.args))
    elif args.command == "connect":
        # LEFT: `gfso.mcp.connect` imports the third-party `mcp` SDK at module level, and `gfso
        # doctor` / `gfso serve` must still run on an installation where that dependency is missing.
        from gfso.mcp.connect import main as connect_main
        connect_main()
    elif args.command == "up":
        # LEFT: same optional `mcp` SDK dependency as `connect` above.
        from gfso.mcp.connect import ensure_correct
        # Non-zero when it DECLINED to reconcile: `gfso up && …` could not otherwise tell a server
        # that is now current from one left stale because somebody else is working on it.
        try:
            sys.exit(1 if ensure_correct(force=args.force)["action"] == "left-alone" else 0)
        except RuntimeError as ex:      # the server did not come up: say so, do not throw a stack
            sys.exit(f"gfso: {ex}")
    elif args.command == "down":
        _down()
    elif args.command == "projects":
        _projects(args)
    elif args.command == "log":
        _log(args)
    elif args.command == "setup":
        sys.exit(setup(desktop=args.desktop))
    elif args.command == "doctor":
        sys.exit(doctor())
    elif args.command == "demo":
        sys.exit(_demo(args.name))


def _demo(name: str | None) -> int:
    """Run one shipped example in THIS process, through runpy — they are library code, not scripts
    that exit."""
    if name not in DEMOS:
        if name is not None:
            print(f"no demo named {name!r}")
        print("demos (run `gfso demo <name>`):")
        for key, what in DEMOS.items():
            print(f"  {key:18} {what}")
        return 1 if name is not None else 0
    if name in NEEDS_MODEL:
        found, detail = claude_cli()
        if not found:
            print(f"`{name}` spawns model processes and the Claude Code CLI is not usable: {detail}")
            print("run `gfso doctor` for what to fix, or `gfso demo human_only` — it needs no model.")
            return 1
    runpy.run_module(f"gfso.examples.{name}", run_name="__main__")
    return 0


def _delete_project(name: str, confirmed: bool) -> None:
    """Delete one project through the live server — irreversible, so it is asked for twice.

    The server refuses `default` and whatever is active on its own; deleting the ground you stand on
    is the misclick that refusal exists for. The answer is a LINE: the server's payload carries the
    whole inventory (300 names and a name→timestamp map, ~15 KB), which is right for the UI and pure
    noise in a terminal that asked to delete one thing."""
    if not confirmed:
        print(f"this deletes the project '{name}' irreversibly — its graph, its audit log and its "
              f"DB file. Add --yes to confirm.")
        return
    out = serverctl.delete_project(name)
    if not out.get("error"):
        print(f"deleted '{name}' — {len(out.get('projects', ()))} project(s) left")
        return
    # The server answers a refusal as a JSON body; a person asked in words and is answered in words.
    why = out["error"]
    if why.startswith("{"):
        why = json.loads(why).get("detail", why)
    print(f"not deleted: {why}")


def _projects(args):
    """The project graphs this server holds — the human door's answer to a question only the agent
    door could ask. A person driving from the shell had no way to see what they had already made
    (measured 2026-08-21: `list_projects` and `use_project` exist on MCP alone), and `project=` is
    useless if you cannot remember the name."""
    if args.delete:
        _delete_project(args.delete, args.yes)
        return
    out = serverctl.projects()
    if out is None:
        print("no server is up — `gfso up` starts the one server, and the projects live in it")
        return
    names = [n for n in out.get("projects", []) if not args.match or args.match in n]
    shown = names if not args.n else names[:args.n]
    active = out.get("active")
    print(f"{len(names)} project(s), most recently worked in first"
          + (f" (showing {len(shown)})" if len(shown) < len(names) else "") + ":")
    for n in shown:
        print(f"  {'*' if n == active else ' '} {n}")
    print("\n  * = the server's active project. Every `gfso run` verb takes `project=<name>`; "
          "the name is the isolation boundary, not a port or a directory.")


def _log(args):
    """Terminal mirror of the UI observation panel: the persisted pipeline lines of one project."""
    base = f"{serverctl.BASE}/api/pipeline?limit={max(args.n, 1)}"
    if args.project:
        base += "&project=" + urllib.parse.quote(args.project)
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    # the same as `main`: a stream that refuses has nothing to reconfigure — the strip still prints,
    # with replacements
    except Exception:
        pass
    last: list = []
    while True:
        try:
            rows = json.loads(urllib.request.urlopen(base, timeout=5).read())
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
    api = f"{serverctl.BASE}/api/shutdown"
    try:
        # `down` is the deliberate stop — it means it even if sessions are on the server. The
        # server refuses an unforced stop while clients are working, which is what keeps a routine
        # reconcile from taking down someone's run.
        out = urllib.request.urlopen(urllib.request.Request(
            api, data=b'{"force": true}', method="POST",
            headers={"Content-Type": "application/json"}), timeout=3).read()
        print(f"server stopping: {json.loads(out)}")
        # …and WAIT for it to be gone, on the same wait the reconciler already uses. Returning
        # before the port is free makes `down` a request rather than a fact, and the command is
        # named for the fact.
        if not serverctl.wait_closed():
            print(f"warning: {serverctl.BASE} still answering — it did not exit on request")
    except Exception as e:
        print(f"no server answering at {api} ({type(e).__name__}) — nothing to stop")


def _mcp(args):
    install_mcp_env(db_path=args.db_path, llm=args.llm, model=args.model)
    # LEFT: `gfso.mcp.server` needs the optional `mcp` SDK, and importing it raises the whole HTTP
    # stack (fastapi + uvicorn + `gfso.api.server`) that the other subcommands do not pay for.
    from gfso.mcp.server import main as mcp_main
    mcp_main()


def _serve(args):
    logging.basicConfig(level=getattr(logging, args.log_level.upper()), format="%(message)s")

    # Store config in env for reload mode
    # Whatever raises the server — `gfso up`, a session's connect.py, or this command typed by hand
    # — it comes up with the switches this repository DECLARES. They are per-process and decide what
    # a run measures (a same-Del node self-verifies with GFSO_VALIDATE_INTERNAL off, so no
    # independent verdict ever arrives), and a hand-typed `serve` used to silently drop them: one
    # run waited 25 minutes for a verdict that could not come. An explicitly exported value still
    # wins — arm G⁻ sets GFSO_L2_GATE=0 deliberately — so this fills gaps, it does not override.
    install_serve_env(
        serverctl.declared(), storage=args.storage, db_path=args.db_path, llm=args.llm,
        model=args.model, seed=args.seed, with_mcp=not args.no_mcp,
        on_declaration_error=lambda ex: print(
            f"gfso: could not read the declared server config ({ex})"))

    if not args.no_browser:
        threading.Timer(1.5, lambda: webbrowser.open(f"http://{args.host}:{args.port}")).start()

    try:
        # LEFT: the except below is what turns a missing `uvicorn` into the line under it; hoisted,
        # the whole CLI would die on an ImportError instead.
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
