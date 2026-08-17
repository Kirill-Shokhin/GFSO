"""Lazy shared-server launcher — the stdio entry every Claude Code session points at.

`claude mcp add --scope user gfso -- gfso connect`  (a console script:
the client spawns the interpreter the package was installed into)

On session start it ENSURES the one shared gfso server is running (port closed → spawn it DETACHED,
so it outlives this session; port open → touch nothing — the second/third session just joins), then
transparently BRIDGES this session's stdio MCP traffic to the shared server's streamable-HTTP surface.
Result: any number of parallel agent sessions share ONE process — one event bus (live ticks for every
session in the UI), one dispatcher set, one registry — with zero manual server management.

Knobs (env): GFSO_SHARED_URL (default http://127.0.0.1:8000/mcp) · the spawned server inherits this
session's env (GFSO_DB_PATH etc.) but NOT its working directory — it runs in `serverctl.home()`, so
the database and `data/server.log` belong to the installation rather than to whichever directory the
agent client happened to start in.
"""
from __future__ import annotations

import os
import subprocess
import sys
import time
from urllib.parse import urlparse

URL = os.environ.get("GFSO_SHARED_URL", "http://127.0.0.1:8000/mcp")


def _port_open(host: str, port: int) -> bool:
    from gfso import serverctl                 # one probe, one answer (gfso.serverctl.port_open)
    return serverctl.port_open(host, port)


def ensure_server(url: str = URL, wait_s: float = 25.0) -> bool:
    """Spawn the shared server DETACHED if its port is closed; wait until it answers.
    Returns True if the server is (now) up.

    Every path is resolved against `serverctl.home()`, not against the current directory, and the
    child is spawned THERE. This door is the one an agent client runs, and a client picks its own
    working directory: Claude Desktop starts its servers wherever it likes, so a cwd-relative
    `data/gfso.db` put the user's graphs in a directory nobody could name — while `GFSO_HOME`, the
    variable documented for exactly that case, was read by `gfso up` alone. Measured before the fix:
    with GFSO_HOME set, the database still landed beside the caller.
    """
    from gfso import serverctl
    u = urlparse(url)
    host, port = u.hostname or "127.0.0.1", u.port or 8000
    if _port_open(host, port):
        return True
    home = serverctl.home()
    data = home / "data"
    data.mkdir(parents=True, exist_ok=True)
    log = open(data / "server.log", "a", encoding="utf-8")
    print(f"[gfso connect] shared server not running — starting it on :{port}",
          file=sys.stderr, flush=True)
    # A HIDDEN CONSOLE, not NO console — the difference is the whole class of "an empty window keeps
    # popping up". DETACHED_PROCESS left the server without a console, and on Windows a console
    # child of a console-LESS parent allocates its own console, which the default host shows as a
    # window. We answered that three times at OUR spawn sites (CREATE_NO_WINDOW in the headless
    # runner, the code verifier, the experiment layer) — but the flag is not inherited, so every
    # spawn we do NOT control re-opened the class: the claude CLI starting its stdio MCP server is
    # exactly that case. Measured with a probe over visible top-level windows: a console-less parent
    # yields 2 new visible windows for one uncontrolled grandchild (a terminal host window and a
    # pseudo-console), a hidden-console parent yields 0 — its descendants attach to the console it
    # already owns and open nothing. So the fix belongs here, once, at the root of the tree.
    si = None
    if os.name == "nt":
        si = subprocess.STARTUPINFO()
        si.dwFlags |= subprocess.STARTF_USESHOWWINDOW
        si.wShowWindow = 0                                       # SW_HIDE
        flags = 0x00000010 | 0x00000200                          # CREATE_NEW_CONSOLE | NEW_PROCESS_GROUP
    else:
        flags = 0
    subprocess.Popen(
        [sys.executable, "-m", "gfso.cli", "serve", "--storage", "sqlite",
         "--db-path", os.environ.get("GFSO_DB_PATH", str(data / "gfso.db")),
         "--no-browser", "--port", str(port), "--host", host],
        cwd=str(home),
        stdout=log, stderr=log, stdin=subprocess.DEVNULL,
        # The server outlives whoever started it: it is a background service, and the UI a person
        # left open belongs to the person, not to the agent session that happened to raise it.
        # GFSO_AUTOEXIT=1 restores the old lease-scoped lifetime for anyone who wants it.
        env=dict(os.environ, GFSO_AUTOEXIT=os.environ.get("GFSO_AUTOEXIT", "0")),
        creationflags=flags, startupinfo=si, start_new_session=(os.name != "nt"))
    t0 = time.monotonic()
    while time.monotonic() - t0 < wait_s:
        if _port_open(host, port):
            time.sleep(1.0)          # give the app a beat to finish mounting /mcp
            return True
        time.sleep(0.4)
    print(f"[gfso connect] server did not come up on :{port} within {wait_s}s "
          f"(see {data / 'server.log'})", file=sys.stderr, flush=True)
    return False


def foreign_holder(host: str, port: int) -> bool:
    """True when the port is open and whatever holds it is NOT a gfso server.

    An open port was taken for a running server everywhere in this file, so the one case that
    actually happens on a stranger's machine — something else already on :8000 — produced the worst
    possible outcome: `ensure_server` spawned nothing and returned success, and the caller then
    waited out its whole retry budget before announcing a server that was never started.
    """
    from gfso import serverctl
    return _port_open(host, port) and serverctl.runtime() is None


def ensure_correct(verbose: bool = True, holds_lease: bool = False, force: bool = False) -> dict:
    """Make THE one server correct and current — start, restart, or leave alone. Idempotent.

    `ensure_server` above answers "is the port open", which is not the question that keeps costing
    runs. A process holds its code in memory, so an edited tree never reaches it; and the switches
    that decide what a run measures (GFSO_VALIDATE_INTERNAL, GFSO_L2_GATE, the agent registry) are
    per-process, so any restart by anyone silently changes them — a run once sat 25 minutes waiting
    on a verdict that could not come, because a restart had dropped one variable.

    So: read what the server says about itself (`/api/runtime`), compare with what the repository
    declares (`gfso.serverctl`), and reconcile. Stop is the same graceful `/api/shutdown` that
    `gfso down` uses; start is `ensure_server` above. No port is an argument anywhere: there is one
    server, and multi-project mode is the isolation boundary.
    """
    import json
    import urllib.error
    import urllib.request
    from gfso import serverctl

    env, fp = serverctl.declared(), serverctl.source_fingerprint()
    rt, action, why = serverctl.runtime(), "already-correct", []
    if rt is not None:
        why = serverctl.drift(rt, env, fp)
        # A restart is not free: it ends whatever the server is doing for SOMEBODY ELSE, and the
        # model subprocesses it spawned outlive it, writing into a working directory with nothing
        # left to receive their reports. So a reconcile that would interrupt other sessions REPORTS
        # instead — the drift is real and stays visible, and `gfso down` is the deliberate act.
        others = max(0, int(rt.get("sessions") or 0) - (1 if holds_lease else 0))
        busy = list(rt.get("busy") or [])
        if why and (others or busy) and not force:
            note = (f"{others} other session(s)" if others else "") +                    (" and " if others and busy else "") +                    (f"work in flight ({', '.join(busy)})" if busy else "")
            print(f"gfso: the server is not current ({'; '.join(why)}), and {note} — leaving it "
                  f"alone. `gfso down` when it is safe, and the next command starts a current one.",
                  file=sys.stderr, flush=True)
            return {"action": "left-alone", "drift": why, "code_version": fp}
        # (`gfso up` turns "left-alone" into a non-zero exit — a caller chaining on it must be able
        # to tell a reconciled server from one it was asked to leave.)
        if why:
            # UNFORCED, and that is the whole point: `force` overrides the server's own refusal to
            # stop while clients are working (§/api/shutdown), so sending it on a ROUTINE staleness
            # reconcile made the last line of defence decorative — a stale tree could end a run that
            # had paid for hours. A new declaration applies to the NEXT start; only a deliberate act
            # (`gfso down`, an explicit force) may end work in flight. A 409 here is the correct
            # answer, not an error: somebody is on it.
            stop = {"force": True} if force else {}
            try:                                   # the graceful path; the server exits itself
                urllib.request.urlopen(urllib.request.Request(
                    f"{serverctl.BASE}/api/shutdown", data=json.dumps(stop).encode(), method="POST",
                    headers={"Content-Type": "application/json"}), timeout=3).read()
            except urllib.error.HTTPError as ex:
                if ex.code == 409:
                    print(f"gfso: the server is not current ({'; '.join(why)}) but clients are "
                          f"working on it — leaving it alone; the next start will be current.",
                          file=sys.stderr, flush=True)
                    return {"action": "left-alone", "drift": why, "code_version": fp}
            except Exception:
                pass
            for _ in range(40):
                if not _port_open("127.0.0.1", serverctl.PORT):
                    break
                time.sleep(0.5)
            if _port_open("127.0.0.1", serverctl.PORT):
                # It did not stop, so nothing was restarted. Reporting "restarted" here was a claim
                # about an act that did not happen — and the caller then believed it was talking to
                # current code. Whatever refused (a client on it, a stop that never arrived) leaves
                # the drift standing, which is the honest answer.
                print(f"gfso: the server did not stop ({'; '.join(why)} stands) — leaving it alone; "
                      f"the next start will be current.", file=sys.stderr, flush=True)
                return {"action": "left-alone", "drift": why, "code_version": fp}
            rt, action = None, "restarted"
    if rt is None:
        if foreign_holder("127.0.0.1", serverctl.PORT):
            from gfso.doctor import port_state
            raise SystemExit(f"gfso: {port_state()[1]}")
        os.environ.update(env)                     # the spawn inherits THIS process's environment
        os.environ["GFSO_AUTOEXIT"] = "0"          # THE server stays up until it is stale or stopped
        prior = os.getcwd()
        # The home is CREATED here, not assumed: on a first install `~/.gfso` does not exist yet, and
        # `chdir` into it raised FileNotFoundError before anything was spawned — so `gfso setup` died
        # with a traceback instead of the report it exists to print, and `gfso connect` exited, which
        # an agent client shows as a session with no gfso tools at all. Invisible from a source
        # checkout, where the home is the repository and always exists.
        (serverctl.home() / "data").mkdir(parents=True, exist_ok=True)
        try:
            os.chdir(serverctl.home())             # db/log paths are relative to the working tree
            # Spawning is FLAKY on Windows: the port a just-stopped server held can still be in the
            # kernel's hands when the replacement tries to bind, and the replacement then dies
            # unseen. Observed live — `up` reported "did not come up", the identical command a
            # moment later started it, and in between an unattended run lost its engine. One attempt
            # is a coin toss; three, spaced, is a start.
            for attempt in range(3):
                if ensure_server(f"{serverctl.BASE}/mcp"):
                    break
                if verbose and attempt < 2:
                    print(f"gfso: the server did not come up (attempt {attempt + 1}/3) — retrying")
                time.sleep(2)
            else:
                raise RuntimeError(f"the shared server did not come up in three attempts — see "
                                   f"{serverctl.home() / 'data' / 'server.log'}")
        finally:
            os.chdir(prior)
        action = "restarted" if action == "restarted" else "started"
        for _ in range(30):                        # /api/runtime lags the open port by a beat
            if serverctl.runtime() is not None:
                break
            time.sleep(1)
    if verbose:
        # The HOME is printed, not assumed: it decides where the database, the log and the agent
        # registry live, and it differs between a source checkout and an installed package.
        print(f"gfso server {serverctl.BASE}: {action}"
              + (f" ({'; '.join(why)})" if why else "")
              + f" · code {fp} · home {serverctl.home()}")
    return {"action": action, "drift": why, "code_version": fp}


async def _relay(url: str) -> None:
    """Transparent bidirectional JSON-RPC pump: this session's stdio ↔ the shared server's HTTP."""
    import anyio
    from mcp.server.stdio import stdio_server
    from mcp.client.streamable_http import streamablehttp_client

    async def pump(src, dst):
        async with src, dst:
            async for msg in src:
                await dst.send(msg)

    async with stdio_server() as (client_read, client_write):          # Claude Code side
        async with streamablehttp_client(url, terminate_on_close=True) as (srv_read, srv_write, _sid):
            async with anyio.create_task_group() as tg:
                tg.start_soon(pump, client_read, srv_write)            # session → shared server
                tg.start_soon(pump, srv_read, client_write)            # shared server → session


def _heartbeat(url: str, lease_id: str, stop) -> None:
    """Hold this session's LEASE on the shared server (every ~4s). The server self-exits once the
    last lease expires — the whole lifecycle mirrors the sessions with zero manual management."""
    import json as _json
    import urllib.request
    u = urlparse(url)
    api = f"http://{u.hostname}:{u.port or 8000}/api/lease"
    while not stop.is_set():
        try:
            urllib.request.urlopen(urllib.request.Request(
                api, data=_json.dumps({"id": lease_id}).encode(),
                headers={"Content-Type": "application/json"}, method="POST"), timeout=3).read()
        except Exception:
            pass                      # server briefly down/restarting — the bridge will notice itself
        stop.wait(4.0)
    try:                              # fast shutdown path: drop the lease on clean exit
        urllib.request.urlopen(urllib.request.Request(f"{api}/{lease_id}", method="DELETE"),
                               timeout=2).read()
    except Exception:
        pass


def main() -> None:  # pragma: no cover — exercised live as the MCP entry
    import threading
    import uuid
    import anyio
    from urllib.parse import urlparse as _up
    _u = _up(URL)
    if foreign_holder(_u.hostname or "127.0.0.1", _u.port or 8000):
        from gfso.doctor import port_state
        print(f"[gfso connect] {port_state()[1]}", file=sys.stderr, flush=True)
        sys.exit(1)
    # RECONCILE, not merely "is the port open" — which is all this door used to ask. After
    # `pip install -U gfso` the next session bridged into the process from before the upgrade and
    # went on doing so indefinitely: the server no longer exits by itself, and nothing here compared
    # what it was serving. The upgrade appeared to change nothing, which with a public version line
    # is the defect that voids every other one.
    #
    # verbose=False is load-bearing: stdout IS the JSON-RPC channel of this stdio server, so a
    # status line printed onto it corrupts the session. Everything goes to stderr.
    try:
        result = ensure_correct(verbose=False, holds_lease=False)
        if result["drift"]:
            print(f"[gfso connect] server reconciled ({'; '.join(result['drift'])})",
                  file=sys.stderr, flush=True)
    except SystemExit:
        raise
    except Exception as ex:
        print(f"[gfso connect] could not make the server correct: {ex}",
              file=sys.stderr, flush=True)
        sys.exit(1)
    stop = threading.Event()
    hb = threading.Thread(target=_heartbeat, args=(URL, uuid.uuid4().hex[:12], stop), daemon=True)
    hb.start()
    try:
        anyio.run(_relay, URL)
    except (KeyboardInterrupt, Exception) as e:  # session end / server gone — exit quietly
        print(f"[gfso connect] bridge closed: {type(e).__name__}", file=sys.stderr, flush=True)
    finally:
        stop.set()
        hb.join(3.0)                  # let the heartbeat thread fire its lease-drop


if __name__ == "__main__":  # pragma: no cover
    main()
