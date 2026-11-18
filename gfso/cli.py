"""GFSO CLI — serve the web application."""
from __future__ import annotations

import argparse
import asyncio
import ctypes
import getpass
import json
import logging
import os
import runpy
import sys
import traceback
import threading
import time
import urllib.error
import urllib.parse
import urllib.request
from importlib.resources import files
from pathlib import Path

from gfso.adapters.children import bind_this_process, end_this_process, open_outside
from gfso.adapters import resources
from gfso.adapters.execution import component, end_leftovers, export_places, file_record_path, watch_ceiling, watch_disk
from gfso.adapters.netrecord import record_path, said_apart
from gfso.adapters.records import hold_the_home
from gfso.adapters.storage import person
from gfso.adapters.storage.sqlite import settings_of
from gfso.adapters.llm import credentials, headless, registry
from gfso.adapters.llm.conformance import assess, report
from gfso import __version__, serverctl, signin, witness
from gfso.config import (LOOPBACK, PERSON, UVICORN, admit_host, bind, data_dir, db_path, install_mcp_env,
                         install_serve_env, mark_the_server)
from gfso.doctor import (BY_HAND, JUST_INSTALLED, claude_cli, console_script, doctor, kept_where, setup, sign_in, sign_in_here,
                         wait_signed_in, what_for)
from gfso.examples import DEMOS, NEEDS_MODEL


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
        print(JUST_INSTALLED + "\n")          # the first line an agent reads after `pipx install gfso`
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



#: the first line of `gfso` and `gfso --help`: one command installs, and what it prints leads to everything after it


def build_parser() -> argparse.ArgumentParser:
    """THE command line, as an object. Separated from `main` so that it can be ASKED whether a
    command line is valid without running it — `gfso.mcp.connect` builds a `gfso serve …` argv for
    the process it spawns, and nothing could check the two agreed. They stopped agreeing: a flag
    renamed here left the launcher passing a spelling `serve` no longer had, so every start died
    instantly with a usage message into `server.log` while the launcher reported only a timeout."""
    parser = argparse.ArgumentParser(prog="gfso", description=JUST_INSTALLED + "\n\nGFSO Protocol Engine",
                                     formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--version", action="version", version=f"gfso {__version__}")
    sub = parser.add_subparsers(dest="command")
    # …FIRST, for the one reading this right after `pipx install gfso`: pipx says nothing of what comes next, and
    # `setup` stood seventh of sixteen (a tester on a clean install, 2026-11-13)
    setupp = sub.add_parser("setup", help="One command after installing: register the agent door "
                                          "with Claude Code, bring the server up, open the UI, and "
                                          "report what it found. Idempotent — safe to re-run.")
    setupp.add_argument("--desktop", action="store_true",
                        help="Also write the entry into Claude Desktop's claude_desktop_config.json "
                             "(a backup is kept; restart Desktop afterwards). Only if the person names Desktop: another application's config is "
                             "not edited unless you ask for it by name.")
    _add_protected(setupp)


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
    runp = sub.add_parser("run", help="Drive/inspect a graph headless (same commands as the MCP tools). " + BY_HAND)
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
    _add_protected(upp)

    sub.add_parser("down", help="Stop the shared server (code update: the next session reconnect "
                                "auto-spawns a fresh one)")

    sub.add_parser("doctor", help="What this installation is and whether it can work: version, "
                                  "where state lives, who holds the port, whether the Claude Code "
                                  "CLI answers. Paste its output into a bug report.")

    _add_provider_parser(sub)

    demo = sub.add_parser("demo", help="Run a shipped example (no name lists them). `human_only` "
                                       "shows the gate refusing a self-signed PASS, with no AI.")
    demo.add_argument("name", nargs="?", default=None)

    _add_status_parser(sub)
    _add_projects_parser(sub)
    _add_sign_in_parsers(sub)

    _add_watch_parsers(sub)

    return parser



def _add_protected(p) -> None:
    p.add_argument("--protected", action=argparse.BooleanOptionalAction, default=None,
                   help="the page signs in with `gfso ui` as well as coming from a process of your OS user; kept in "
                        "data/serve.json for every later start (`--no-protected`: back to no sign-in, the default)")


def _protected(args) -> None:
    """`--protected` / `--no-protected` declared for the installation (`config.page_auth`); neither keeps what it is."""
    if args.protected is not None:
        serverctl.declare("GFSO_PAGE_AUTH", "key" if args.protected else "local-peer")


def _add_sign_in_parsers(sub) -> None:
    """Who you are on the page and at a console: the page opened signed in, and a name's token issued."""
    uip = sub.add_parser("ui", help="Open the page signed in: a one-time code opens a session there, which signs your "
                                    "moves as any name you own. Never handed to an agent: the page link an agent gives "
                                    "you reads, and a move asks you to sign in here.")
    uip.add_argument("project", nargs="?", default=None, help="open that project's page, not the list of them")
    uip.add_argument("--host", default=None, help="a front this server is reached through (`tailscale serve`, "
                                                  "`GFSO_ALLOWED_HOSTS`), opened there; it must keep the Host header")
    agp = sub.add_parser("agent", help="Issue a token for a name you own (`engineering`, a console's name) and print the "
                                       "console's launch line: the console signs as that name. Refused for the system's "
                                       "names (an executor's, a validator's).")
    agp.add_argument("name")
    agp.add_argument("--revoke", action="store_true", help="revoke every token for the name")
    sub.add_parser("migrate", help="Write the person as `user` where a database of this home from before 0.4.0 says "
                                   "`agent`: once, recorded in each database it rewrote. `serve` does it at its start.")


def _ui(args) -> int:
    """Open the page on a one-time code written to this installation's state; the server spends it and sets the session.
    The code is said to no one: the browser opens on it."""
    if (rt := serverctl.runtime()) is None:
        print(f"no server answering at {serverctl.BASE} — `gfso up` first, then `gfso ui`")
        return 2
    base = (args.host if "://" in args.host else f"https://{args.host}") if args.host else serverctl.BASE
    if not args.host and serverctl.page_auth_in_force(rt) == "local-peer":
        # …no session to open: here the page is the person as it is, and a loopback cookie reaches every port of it
        open_outside(serverctl.ui_link(args.project))
        print(f"the page opens at {serverctl.ui_link(args.project)}")
        return 0
    back = f"&next={urllib.parse.quote('/?project=' + args.project, safe='')}" if args.project else ""
    link = f"{base.rstrip('/')}/signin?code={urllib.parse.quote(signin.code())}{back}"
    if args.host:
        # …a front's name is for another device (a phone through `tailscale serve`): opened here, this browser spent the
        # code and the device had no way in (critic) — the link is said, for the device to open
        print(f"open this on the device that reaches {base.rstrip('/')}/ — good for {signin.CODE_S // 60} minutes, once:\n"
              f"{link}")
        return 0
    open_outside(link)
    print(f"the page opens signed in at {base.rstrip('/')}/ (its code is good for {signin.CODE_S // 60} minutes, once)")
    return 0


def _agent(args) -> int:
    """Issue `args.name` a token, or revoke its tokens; the token is printed once, in the launch line."""
    if args.revoke:
        print(f"{signin.revoke(args.name)} token(s) for {args.name} revoked")
        return 0
    try:
        tid, token = signin.issue(args.name)
    except ValueError as ex:
        print(f"gfso agent: {ex}", file=sys.stderr)
        return 2
    print(f"a token for {args.name} ({tid}), shown this once. Launch the console that signs as {args.name} with it:",
          f"  GFSO_TOKEN={token} claude              # bash, zsh",
          f"  $env:GFSO_TOKEN='{token}'; claude     # PowerShell",
          f"`gfso agent {args.name} --revoke` revokes it.", sep="\n")
    return 0


def _migrate(args) -> int:
    """The person's rename (`signin.rename_the_person`) run on this home, what it wrote said per database."""
    try:
        done = signin.rename_the_person()
    except person.TwoParties as ex:
        print(f"gfso migrate: {ex}", file=sys.stderr)
        return 2
    refused = {db: r["refused"] for db, r in done.items() if "refused" in r}
    for db, rows in done.items():
        if db not in refused:
            print(f"{db}: " + ", ".join(f"{k} {n}" for k, n in sorted(rows.items())))
    for db, why in refused.items():
        print(f"gfso migrate: {db} left as it is — {why}", file=sys.stderr)
    n = len(done) - len(refused)
    print(f"the person is written `{PERSON}` in {n} database(s) rewritten now" if n else
          f"nothing rewritten now in {data_dir()}")
    return 1 if refused else 0


def _add_watch_parsers(sub) -> None:
    """The ways to watch without driving: a run's log, a wait that ends when the run needs you, and the witness of a
    console's writes."""
    logp = sub.add_parser("log", help="The log in the terminal — same persisted lines "
                                      "the UI panel shows (per project)")
    logp.add_argument("--project", default=None,
                      help="project name (default: the active one); `project=<name>` also accepted, "
                           "as on `gfso run`")
    logp.add_argument("-n", type=int, default=40, help="lines to show (default 40)")
    logp.add_argument("-f", "--follow", action="store_true", help="keep polling for new lines")

    waitp = sub.add_parser("wait", help="Wait for a project's run to need you — run it in the background: it asks only "
                                        "the live server and exits when the root is settled, a move is yours, or the run "
                                        "stopped")
    waitp.add_argument("--project", default=None, help="project name (default: the active one); `project=<name>` too")
    waitp.add_argument("--hours", type=float, default=24.0, help="give up after this long (default 24)")

    witp = sub.add_parser("witness", help="A Claude Code hook: a tool call that changed this repository's working tree "
                                          "while no node of the project is at work in it is recorded in the project "
                                          "and told to the agent; it never blocks. Installed only when you ask, in "
                                          "this repository alone. Without a flag: one hook run (the event on stdin).")
    witp.add_argument("project")
    how = witp.add_mutually_exclusive_group()
    how.add_argument("--install", action="store_true",
                     help="write it into .claude/settings.local.json at the top of the worktree you run it in "
                          "(a linked worktree's own top, where its console starts), kept out of git; a node is at "
                          "work in the repository whichever of its worktrees it was taken in")
    how.add_argument("--remove", action="store_true", help="take it out, your other hooks kept")


def _add_provider_parser(sub) -> None:
    """`gfso provider-check` — the conformance battery on one provider (`adapters/llm/conformance.py`)."""
    provp = sub.add_parser("provider-check", help="Whether a model provider can run on gfso and in which roles: a "
                                                  "battery of small real calls (a completion, a structured answer, "
                                                  "a tool round trip in a place of its own). `--list` names the "
                                                  "providers a model spec may start with.")
    provp.add_argument("spec", nargs="?", default=None, help="a model spec, e.g. ollama/qwen3:32b or deepseek/deepseek-chat")
    provp.add_argument("--list", action="store_true")
    credp = sub.add_parser("credential", help="Set a model provider's credential in its one place — read from stdin, never "
                                              "an argument, never printed back. No provider: what is set, by kind.")
    credp.add_argument("provider", nargs="?", default=None, help="claude, deepseek, openai, … (`provider-check --list`)")
    credp.add_argument("--kind", choices=("token", "api"), default=None,
                       help="token = a subscription's (`claude setup-token`); api = an API key. Default: what it takes")
    credp.add_argument("--name", default=None, help="which of the provider's credentials (default: its kind) — a "
                                                    "provider holds several, e.g. two accounts' tokens and keys")
    credp.add_argument("--use", metavar="NAME", default=None, help="move the pointer: every new call runs on NAME, "
                                                                   "calls in flight finish on theirs")
    credp.add_argument("--order", metavar="A,B,…", default=None, help="the order the pointer moves in when a limit "
                                                                      "refuses the one in force")
    credp.add_argument("--remove", action="store_true", help="remove NAME (`--name`), else every credential of it")
    credp.add_argument("--sign-in", action="store_true", help="claude only: open a window where the person signs in "
                                                              "(`claude setup-token`) and pastes the token at gfso's "
                                                              "hidden prompt; returns at once, never sees it")
    credp.add_argument("--wait", action="store_true", help="claude only: block up to about 100 s until a credential is "
                                                           "held; exit 0 when it is, non-zero (run again) when not")
    credp.add_argument("--sign-in-here", action="store_true", help=argparse.SUPPRESS)  # the window's own side
    netp = sub.add_parser("network", help="Where the record lies of what a project's sessions reached by network, under every switch.")
    netp.add_argument("project")
    expp = sub.add_parser("export-places", help="Write a project's places — kept in its execution's volume, on no host "
                                                "directory — under DIR/<project>, each node's clone readable without "
                                                "the base or the volume")
    expp.add_argument("project")
    expp.add_argument("dir")

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
            # …AND IT SAYS WHY, which it did not. `gfso up` exited 1 in total silence: the
            # branch a caller hits most (`GFSO_NO_RECONCILE`) returned without printing anything at
            # all, and the exit code was the whole of the answer — read, on this repository's own
            # server, as "another session is connected" when it was nothing of the sort.
            # The repair is in `connect.ensure_correct`, not here: every outcome now narrates
            # through one owner (`_left_alone`, plus the verbose summary) AND carries the sentence
            # in what it RETURNS, so a caller that is not a terminal can read it too. A print here
            # as well was tried and removed — `verbose` already emits the identical line, so the
            # door said everything twice and the drift three times, and silencing `verbose` to stop
            # that also swallowed the "did not come up, retrying" progress lines.
            _protected(args)
            _out = ensure_correct(force=args.force)
            sys.exit(1 if _out["action"] == "left-alone" else 0)
        except RuntimeError as ex:      # the server did not come up: say so, do not throw a stack
            sys.exit(f"gfso: {ex}")
    elif args.command == "down":
        _down()
    elif args.command == "projects":
        _projects(args)
    elif args.command == "log":
        _log(args)
    elif args.command in _EXITS:
        sys.exit(_EXITS[args.command](args))
    elif args.command == "setup":
        _protected(args)
        sys.exit(setup(desktop=args.desktop))
    elif args.command == "doctor":
        sys.exit(doctor())
    elif args.command == "demo":
        sys.exit(_demo(args.name))
    elif args.command == "network":
        print(record_path(args.project))
        print(*said_apart(args.project), sep="\n")
        print(f"what changed in its sessions' directories: {file_record_path(args.project)}")


def _export_places(args) -> int:
    """`gfso export-places PROJECT DIR`: the project's places out of the volume its own record names; non-zero where
    it has none or nothing was exported."""
    if (record := settings_of(str(db_path(args.project)))) is None:
        print(f"{args.project}: no project of the name in {data_dir()}", file=sys.stderr)
        return 1
    try:
        for n in export_places(args.project, record, args.dir):
            print(f"{args.project}: {n}", file=sys.stderr)
    except (OSError, LookupError, ValueError) as e:
        print(f"{args.project}: {e}", file=sys.stderr)
        return 1
    print(f"{args.project}: its places are under {os.path.join(args.dir, component(args.project))}")
    return 0


def _provider_check(args) -> int:
    """`gfso provider-check SPEC`: the conformance battery on one provider; non-zero when it can hold no role."""
    if args.list or not args.spec:
        for n in registry.names():
            p = registry.preset(n)
            print(f"{n:12} {p.base_url if p else ('Claude Code CLI' if n == 'claude' else 'plugin')}"
                  + (f"  key: gfso credential {n}" if p and p.keyed else "") + (f"  ({p.note})" if p and p.note else ""))
        return 0
    # the report case under the executor's own system prompt, as a real executor reads it
    found = assess(registry.provider_for(args.spec),
                   files("gfso.mcp").joinpath("prompts", "executor.md").read_text(encoding="utf-8"))
    print(report(args.spec, found))
    return 0 if found["roles"] else 1


def _credential(args) -> int:
    """`gfso credential PROVIDER` — the door every provider's credential is set by (`registry.set_credential`)."""
    if not args.provider:
        print(json.dumps(credentials.listing()))
        return 0
    try:
        if args.use or args.order:
            print(json.dumps(credentials.use(args.provider, args.use) if args.use
                             else credentials.order(args.provider, [n.strip() for n in args.order.split(",") if n.strip()])))
            return 0
        kind = args.kind or (registry.takes(args.provider) or ("api",))[0]
        if args.sign_in or args.sign_in_here or args.wait:
            if args.provider != headless.PROVIDER:
                raise ValueError("--sign-in is the claude subscription's: `gfso credential claude --sign-in`")
            if args.wait:
                if not wait_signed_in(args.provider):
                    sys.exit("gfso: not yet, no credential is held: run `gfso credential claude --wait` again")
                print("A credential is held (its value is never shown): the sign-in is done, go on.")
                return 0
            if args.sign_in_here:
                return sign_in_here()
            if not sign_in(console_script()):
                sys.exit("gfso: no window to open here: the person runs `claude setup-token` in their own terminal, "
                         "then `gfso credential claude` and pastes the token at its hidden prompt; `gfso credential claude --wait` sees it")
            print("A window is open: the person signs in there and pastes the token; it never passes the chat. Run "
                  "`gfso credential claude --wait` now, again if it says not yet, rather than waiting for them to say it "
                  "is done. " + what_for() + " " + kept_where())
            return 0
        value = None if args.remove else (getpass.getpass(f"{args.provider} {kind}: ") if sys.stdin.isatty()
                                          else sys.stdin.read()).strip()
        if value == "":
            sys.exit("gfso: no credential on stdin")
        print(json.dumps(registry.set_credential(args.provider, kind, value, args.name)))
        if value:
            print(registry.shown(value), file=sys.stderr)
    except ValueError as ex:                   # no such provider, or a kind it does not take
        sys.exit(f"gfso: {ex}")
    return 0


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
    # THE TOTAL IS THE SERVER'S, not the length of the page it sent. The endpoint pages (a full list
    # was 19KB), so this printed "50 project(s)" on an installation holding a hundred — a count that
    # answers "how many did you send me" while reading as "how much do I have".
    total = out.get("total") if not args.match else len(names)
    total = len(names) if total is None else total
    print(f"{total} project(s), most recently worked in first"
          + (f" (showing {len(shown)})" if len(shown) < total else "") + ":")
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
                # a follower read through a pipe (`| grep --line-buffered`) gets each event as it lands
                print(f"{r['ts']} [{r['source']}] {r['message']}", flush=args.follow)
        if not args.follow:
            return
        last = rows
        time.sleep(2)


def _wait(args) -> int:
    """Monitoring, not work: the agent that gave the go runs this in the background and stays free for the person,
    woken when it exits — a `next_steps(wait=600)` once held over MCP kept the client's session busy for ten minutes a
    call. It asks ONLY the live server: a run lives there, and the local path `gfso run` falls back to would build an
    engine of its own here, with no container and no branch (11-09). The transport of the server's one wait (`POST
    /api/wait`), whose `needs_you` decides. Exit 0: the run needs its customer; 2: no server answering, or the wait
    refused; 3: still running at `--hours`."""
    url = f"{serverctl.BASE}/api/wait"
    ask = json.dumps({"project": args.project} if args.project else {}).encode()
    end = time.monotonic() + args.hours * 3600
    while time.monotonic() < end:
        try:
            req = urllib.request.Request(url, data=ask, method="POST",
                                         headers={"Content-Type": "application/json", **signin.credential_header()})
            out = json.loads(urllib.request.urlopen(req, timeout=900).read() or b"null") or {}
        except urllib.error.HTTPError as e:      # the server answered: the call was wrong, not the server down
            print(f"the server refused the wait ({e.code}): {e.read().decode('utf-8', 'replace')[:300]}", flush=True)
            return 2
        except Exception as e:
            print(f"no server answering ({type(e).__name__}) — nothing was waited on; the run, if any, is on the "
                  f"server: `gfso up`, then wait again", flush=True)
            return 2
        if why := out.get("needs_you"):
            print(f"{why} — read it with `next_steps` and `get_verdict` over MCP; the page: "
                  f"{serverctl.ui_link(args.project)}", flush=True)
            for s in [s for s in out.get("steps") or () if s.get("mine") and not s.get("optional")][:3]:
                print(f"- {s.get('task_id')}: {s.get('directive', '')[:400]}", flush=True)
            return 0
    print(f"still running after {args.hours:g} h — wait again", flush=True)
    return 3


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
    bind_this_process()          # the stdio server spawns `claude` children too
    install_mcp_env(db_path=args.db_path, llm=args.llm, model=args.model, declared=serverctl.declared())
    # LEFT: `gfso.mcp.stdio` needs the optional `mcp` SDK, and importing it raises the whole HTTP
    # stack (fastapi + uvicorn + `gfso.api.server`) that the other subcommands do not pay for.
    from gfso.mcp.stdio import main as mcp_main
    mcp_main()


def _serve(args):
    logging.basicConfig(level=getattr(logging, args.log_level.upper()), format="%(message)s")
    # …a second `serve` typed by hand ended every project's work before it failed to bind (critic, read), and wrote a gap
    if serverctl.port_open(LOOPBACK if args.host in ("0.0.0.0", "::") else args.host, args.port):
        sys.exit(f"gfso serve: {args.host}:{args.port} is already served, and its work goes on: `gfso down` first.")
    # …and on another port it ended this home's containers all the same (`end_leftovers`): one server to a home
    if not hold_the_home(data_dir()):
        sys.exit(f"gfso serve: a server of {data_dir()} is running, and its work goes on: `gfso down` first.")
    # The server's descendants — executors, validators, their probes — die with it, however it ends.
    bind_this_process()
    end_leftovers()              # …and the project containers of the server that stood here before
    watch_ceiling()              # …and who pays when every installation's containers together reach the ceiling
    watch_disk()                 # …and who pays when Docker's disk fills
    resources.watch()            # …and what it holds in Docker read on its own schedule, so a page gets it at once
    # …and its projects that stood stay stopped until their Start; a reload worker inherits it, a stdio MCP process not
    mark_the_server()

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

    admit_host(args.host)            # the page this opens is served under that name
    bind(args.host)                  # …and past loopback no Host header vouches for a local caller
    try:
        done = signin.rename_the_person()   # …and the person written `user` where a graph from before 0.4.0 says `agent`
    except person.TwoParties as ex:
        sys.exit(f"gfso serve: {ex}")      # the sign-in state names `user` as another party: every project shares it
    for db, r in done.items():
        if "refused" in r:                 # one graph's conflict or failed write refuses that graph alone
            print(f"gfso serve: {db} is not opened — {r['refused']}", file=sys.stderr)
    signin.ready()                   # …and every party already in the graphs keeps a mover
    if not args.no_browser:
        threading.Timer(1.5, lambda: open_outside(f"http://{args.host}:{args.port}")).start()

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
            timeout_graceful_shutdown=_GRACE_S, **UVICORN,
        )
        loop = asyncio.SelectorEventLoop()
        asyncio.set_event_loop(loop)
        try:
            loop.run_until_complete(uvicorn.Server(config).serve())
        finally:
            loop.close()
            _end_with_the_children()

    try:
        uvicorn.run(
            "gfso.api.server:app",
            host=args.host, port=args.port,
            log_level=args.log_level.lower(),
            reload=args.reload,
            reload_dirs=["gfso"] if args.reload else None,
            timeout_graceful_shutdown=_GRACE_S, **UVICORN,
        )
    finally:
        _end_with_the_children()


# A stop means stop, the way `/api/shutdown` already does it. uvicorn waits for open requests with
# no bound by default, and a long verb's request is open for as long as its paid `claude` child runs,
# so a Ctrl-C or SIGTERM waited out every call; then the interpreter joined the worker threads
# blocked on those children, and on Windows the job never closed because the process never ended.
_GRACE_S = 5


def _end_with_the_children():
    """Exit at once, children first — keeping a failed start's traceback and exit code (called from a
    `finally`, so an exception may be on its way out)."""
    exc = sys.exc_info()[1]
    code = 0 if exc is None or isinstance(exc, KeyboardInterrupt) else (
        (exc.code if isinstance(exc.code, int) else 1) if isinstance(exc, SystemExit) else 1)
    if code and not isinstance(exc, SystemExit):
        traceback.print_exc()
    end_this_process(code)


def _witness(args) -> int:
    """The witness hook run (`gfso.witness`), or written into this repository's own settings file."""
    if not (args.install or args.remove):
        sys.argv[1:] = [args.project]
        witness.main()
    if (top := witness.git(os.getcwd(), "rev-parse", "--show-toplevel")) is None:
        print("gfso witness: not in a git repository — run it at the repository it watches", file=sys.stderr)
        return 2
    print(witness.install(Path(top.strip()), args.project, remove=args.remove))
    return 0


#: the commands that are one function of their arguments, exiting with what it returns
_EXITS = {"wait": _wait, "ui": _ui, "agent": _agent, "provider-check": _provider_check, "credential": _credential,
          "export-places": _export_places, "migrate": _migrate, "witness": _witness}


if __name__ == "__main__":
    main()
