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

import json
import os
import subprocess
import contextlib
import sys
import threading
import time
import urllib.error
import urllib.request
import uuid
from urllib.parse import urlparse

import anyio

from gfso import __version__, serverctl   # the FACTS module: what is running, what is declared
from gfso.doctor import port_state
from mcp.client.streamable_http import streamablehttp_client
from mcp.server.stdio import stdio_server
from mcp.shared.message import SessionMessage
from mcp.types import ErrorData, JSONRPCError, JSONRPCMessage

from gfso.config import (reconcile_allowed, db_path as _db_path,
                         install_spawned_server_env, spawned_server_popen_env)
from gfso.config import LOOPBACK as _LOOPBACK, shared_url

URL = shared_url()


def _port_open(host: str, port: int) -> bool:
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
    u = urlparse(url)
    host, port = u.hostname or _LOOPBACK, u.port or 8000
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
         # one derivation, in `gfso.config` (S4) — composed here by hand, this ignored GFSO_DATA_DIR
         "--db-path", str(_db_path()),
         "--no-browser", "--port", str(port), "--host", host],
        cwd=str(home),
        stdout=log, stderr=log, stdin=subprocess.DEVNULL,
        # The server outlives whoever started it: it is a background service, and the UI a person
        # left open belongs to the person, not to the agent session that happened to raise it.
        # GFSO_AUTOEXIT=1 restores the old lease-scoped lifetime for anyone who wants it.
        env=spawned_server_popen_env(),
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
    return _port_open(host, port) and serverctl.runtime() is None




def _reconcile_running(rt, env, fp, holds_lease: bool, force: bool):
    """Decide what to do about a server that IS up: leave it, or stop it so a current one can
    start. Returns (runtime|None, action, drift) — a `None` runtime means "it is gone, start
    one" — or the whole ANSWER as a dict when the decision is to leave it alone.

    Split out because `ensure_correct` answers two questions — what to do about the server
    that is there, and how to start one that is not — and the first had grown to forty
    statements of nested decisions inside the second's body.
    """
    why: list = []
    if rt is not None:
        why = serverctl.drift(rt, env, fp)
        # A restart is not free: it ends whatever the server is doing for SOMEBODY ELSE, and the
        # model subprocesses it spawned outlive it, writing into a working directory with nothing
        # left to receive their reports. So a reconcile that would interrupt other sessions REPORTS
        # instead — the drift is real and stays visible, and `gfso down` is the deliberate act.
        others = max(0, int(rt.get("sessions") or 0) - (1 if holds_lease else 0))
        busy = list(rt.get("busy") or [])
        if why and (others or busy) and not force:
            # …if that server is still there. The runtime is one HTTP read, and the decision below
            # is made from it — so a server that was exiting when it answered gets to veto its own
            # replacement with sessions that no longer exist. Measured: `gfso down` immediately
            # followed by `gfso up` left the tree stale, the reconcile declining over a session that
            # had gone with the process. Anything that ends a server between the read and the
            # decision — a crash, a kill, an operator — has the same shape, so the re-probe belongs
            # here rather than a wait belonging in `down`.
            if serverctl.runtime() is None:
                rt, why = None, []                 # it is gone; nothing of its is worth honouring
            else:
                note = (f"{others} other session(s)" if others else "") + \
                       (" and " if others and busy else "") + \
                       (f"work in flight ({', '.join(busy)})" if busy else "")
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
            # whether the server stopped is decided by `wait_closed()` below, not by this request; a
            # refused POST is just one more way of not having stopped it
            except Exception:
                pass
            if not serverctl.wait_closed():
                # It did not stop, so nothing was restarted. Reporting "restarted" here was a claim
                # about an act that did not happen — and the caller then believed it was talking to
                # current code. Whatever refused (a client on it, a stop that never arrived) leaves
                # the drift standing, which is the honest answer.
                print(f"gfso: the server did not stop ({'; '.join(why)} stands) — leaving it alone; "
                      f"the next start will be current.", file=sys.stderr, flush=True)
                return {"action": "left-alone", "drift": why, "code_version": fp}
            return None, "restarted", why
    return rt, "already-correct", why


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
    if not reconcile_allowed():
        # Asked not to touch it (a probe, a health check, a suite). Report what is there; change
        # nothing. `force=True` is a caller who said so explicitly and still means it.
        if not force:
            return {"action": "left-alone", "drift": [],
                    "why": "GFSO_NO_RECONCILE is set — reporting, not reconciling"}
    env, fp = serverctl.declared(), serverctl.source_fingerprint()
    rt, action, why = serverctl.runtime(), "already-correct", []
    _r = _reconcile_running(rt, env, fp, holds_lease, force)
    if isinstance(_r, dict):
        return _r
    rt, action, why = _r
    if rt is None:
        if foreign_holder(_LOOPBACK, serverctl.PORT):
            raise SystemExit(f"gfso: {port_state()[1]}")
        install_spawned_server_env(env)
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


# How many times a dropped bridge is rebuilt before giving up, and how long to wait between
# attempts. Small and bounded: this covers a server restart (seconds), not an outage.
_RECONNECTS = 5
_RECONNECT_WAIT_S = 2.0


#: How long a forwarded call may go unanswered before the bridge calls the upstream gone. Well under
#: any client's own idle timeout (Claude Code waits 1800s), because the point is to fail legibly
#: rather than to outlast a slow verb: the long ones (`auto_decompose`, `validate_result`) stream
#: progress, which arrives as traffic and clears the pending entry.
_CALL_TIMEOUT_S = 180.0


def _request_id(msg):
    """The JSON-RPC id of a request or its reply, or None for a notification.

    Read straight off the declared fields (`SessionMessage.message.root.id`) — a notification simply
    has no `id`, which is what the AttributeError means here."""
    try:
        return msg.message.root.id
    except AttributeError:
        return None


async def _watch_unanswered(pending: dict, anyio) -> None:
    """A CALL THAT WILL NEVER BE ANSWERED MUST NOT LOOK LIKE A SLOW ONE.

    The dead-session detector fires only when the server ANSWERS. After a restart the upstream can
    instead go quiet: the request leaves, nothing comes back, and the client waits out its own idle
    timeout — thirty minutes per call, measured on the agent door 2026-08-22, where two calls of the
    two simplest verbs in the product ate an entire session while the same server was answering HTTP
    in 70 ms. Breaking the connection is what triggers the bridge's rebuild-and-replay path."""
    while True:
        await anyio.sleep(5)
        oldest = min(pending.values(), default=None)
        if oldest is not None and time.monotonic() - oldest > _CALL_TIMEOUT_S:
            raise ConnectionError(
                f"the shared server has not answered a call in {_CALL_TIMEOUT_S:.0f}s — rebuilding "
                f"the bridge (a server restart orphans the session it was talking to)")


def _is_dead_session(msg) -> bool:
    """Does this reply say the server has forgotten our session? (a restart, not a network fault)"""
    try:
        root = getattr(msg, "message", msg)
        err = getattr(getattr(root, "root", root), "error", None)
        text = str(getattr(err, "message", "") or "")
        return "session" in text.lower() and ("terminated" in text.lower()
                                              or "not found" in text.lower())
    except Exception:
        return False


#: The client's own `initialize` request, kept from the first time it was seen. A reconnect opens a
#: FRESH upstream session, and the client will never send its handshake again — it believes it is
#: already initialized — so a bridge that reconnects without replaying this is a bridge whose new
#: session is uninitialized: every later call fails exactly like the dead one it just replaced.
#: Measured 2026-08-21: the reconnect loop existed, a whole agent-door run still died with
#: "Session terminated" on every call.
_HANDSHAKE: list = []


async def _answer_the_orphans(client_write, pending: dict, why: str) -> int:
    """Reply to every call that was in flight when the upstream leg broke.

    Rebuilding the bridge does not re-answer what was already sent: the request id is gone with the
    old session, so the CLIENT goes on waiting for it until its own ceiling — thirty minutes for one
    `get_review` that had in fact already succeeded (agent door, 2026-09-02, reproduced here by
    restarting the server under a live bridge). The healing was real and invisible; what the user
    saw was a free read that never returned. A JSON-RPC error carrying the same id ends the wait at
    the moment the break is known, and says what to do about it.
    """
    answered = 0
    for rid in list(pending):
        try:
            await client_write.send(SessionMessage(JSONRPCMessage(JSONRPCError(
                jsonrpc="2.0", id=rid,
                error=ErrorData(code=-32001, message=why)))))
            answered += 1
        except Exception:
            break                     # the stdio leg is gone too; nothing left to answer to
        finally:
            pending.pop(rid, None)
    return answered


async def _replay_handshake(srv_write, srv_read) -> None:
    """Re-do the client's handshake on a freshly opened upstream session, silently.

    Its reply belongs to nobody: the client asked once, long ago, and already has an answer. So the
    reply is READ here and dropped, rather than forwarded into a session that would not know what to
    do with a second one."""
    if not _HANDSHAKE:
        return
    await srv_write.send(_HANDSHAKE[0])
    with contextlib.suppress(Exception):
        await srv_read.receive()          # the new session's initialize result — ours, not the client's
    for note in _HANDSHAKE[1:]:
        await srv_write.send(note)


def _remember_handshake(msg) -> None:
    """Keep the client→server messages that OPEN a session: `initialize` and its notification."""
    try:
        root = getattr(getattr(msg, "message", msg), "root", None)
        method = str(getattr(root, "method", "") or "")
    except Exception:
        return
    if method == "initialize":
        _HANDSHAKE[:] = [msg]
    elif method == "notifications/initialized" and _HANDSHAKE:
        _HANDSHAKE.append(msg)


async def _relay(url: str, client_read, client_write) -> None:
    """One HTTP leg for a stdio pair the CALLER owns: this session's stdio ↔ the shared server.

    The client's side is passed IN and is never opened or closed here. It used to be opened
    inside this function, so every rebuild tore it down and re-acquired it — and the teardown
    DEADLOCKS: `stdio_server().__aexit__` waits for its stdin reader, and stdin never closes
    because the client is still holding the pipe open waiting for the reply that the restart
    interrupted. Measured 2026-09-03 on a controlled bench (call, restart the server under
    the bridge, call): the HTTP leg closed cleanly — the SDK logged its session-termination
    404 — and then nothing, no reconnect line, no exit line, while the heartbeat thread kept
    the lease alive so the process looked healthy from every side but the one that mattered.
    The client waited out its own idle ceiling: thirty minutes, on the FIRST call a stranger
    makes. The stdio side belongs to the client and never needs rebuilding.
    """
    pending: dict = {}          # request id → when it went upstream, for the watchdog below

    async def pump(src, dst, watch_for_dead_session: bool = False):
        """Forward every message from one leg to the other until a leg closes.

        `watch_for_dead_session` marks the SERVER→session direction, the only one where a reply
        can say the server has forgotten us — which is a break to act on, not a message to pass.
        """
        # NOT `async with src, dst` — a pump does not OWN the streams it moves messages
        # between, and closing them is what made the rebuild impossible: the first break
        # closed the CLIENT's side on the way out, so every later attempt died
        # `ClosedResourceError` before it could reach the server (bench, 2026-09-03 —
        # attempt 1 reported the real cause, attempts 2-5 reported attempt 1's damage).
        # The owners close them: `stdio_server` the client side, `streamablehttp_client`
        # the server side, and the point of the rebuild is that only the second is remade.
        async for msg in src:
            if not watch_for_dead_session:
                _remember_handshake(msg)
                if (_rid := _request_id(msg)) is not None:
                    pending[_rid] = time.monotonic()
            else:
                # …AND NOT FOR THE ONE THAT DISCOVERED THE DEATH. The reply carrying
                # `Session terminated` has the id of the call that provoked it, and popping it
                # here — before the raise below — took that call OUT of `pending`, so
                # `_answer_the_orphans` found nobody to answer and the caller waited out its
                # own ceiling for the one request the bridge KNEW was dead. Measured on the
                # bench 2026-09-03: the rebuild succeeded, the handshake replayed, and the
                # call that triggered all of it was never answered.
                if not _is_dead_session(msg):
                    pending.pop(_request_id(msg), None)
            # A RESTARTED SERVER DOES NOT BREAK THE PIPE — it answers. Its new process knows
            # nothing of this session id, so every call comes back as a normal JSON-RPC error
            # reading `Session terminated`, the transport stays perfectly healthy, and the
            # retry loop below never fires because nothing raised. Measured 2026-08-20: an
            # agent's whole progon ran through a bridge in exactly this state — the tool list
            # was there, not one tool worked, and it finished only by writing itself a private
            # HTTP client. A person would have stopped. So the dead session is DETECTED here,
            # in the one place it is visible, and turned into the break that triggers a rebuild.
            if watch_for_dead_session and _is_dead_session(msg):
                raise ConnectionError("the shared server no longer knows this session")
            await dst.send(msg)

    try:
        async with streamablehttp_client(url, terminate_on_close=True) as (srv_read, srv_write, _sid):
            await _replay_handshake(srv_write, srv_read)   # …on a reconnect; a no-op the first time
            async with anyio.create_task_group() as tg:
                tg.start_soon(pump, client_read, srv_write)            # session → shared server
                tg.start_soon(pump, srv_read, client_write, True)      # shared server → session
                tg.start_soon(_watch_unanswered, pending, anyio)
    except BaseException:
        # …and NOBODY IS LEFT WAITING ON THE LEG THAT JUST BROKE.
        # WHAT THE BRIDGE KNOWS IS THAT THE CONNECTION BROKE. It does NOT know whether the call
        # reached the server, and it said it did not — "no work of yours was lost by it; send it
        # again". Measured on the agent door (wave 26, 2026-09-06): three times in one run, and
        # wrong in both directions. Once the `auto_decompose` HAD run and built the whole subtree;
        # obeying the advice bought a second refine round (~$0.30–0.70). Twice a `validate_result`
        # HAD started, and the resend was suppressed as a duplicate with its `model=opus` silently
        # dropped. A claim about the far side of a broken connection is exactly the claim that
        # cannot be made from this side; what CAN be said is where to look.
        n = await _answer_the_orphans(
            client_write, pending,
            "the shared server restarted and this bridge is rebuilding, so this call was not "
            "answered. Whether it RAN on the server is not knowable from here — it may have "
            "completed, may have started, or may never have arrived. Check before you resend: "
            "`get_graph` / `get_task` for an authoring call, `get_verdict` for a validation, "
            "`usage` for whether it was billed. Resending a call that did run costs a second one.")
        if n:
            print(f"[gfso connect] {n} call(s) in flight were ended rather than left waiting",
                  file=sys.stderr, flush=True)
        raise


def _heartbeat(url: str, lease_id: str, stop) -> None:
    """Hold this session's LEASE on the shared server (every ~4s). The server self-exits once the
    last lease expires — the whole lifecycle mirrors the sessions with zero manual management."""
    u = urlparse(url)
    api = f"http://{u.hostname}:{u.port or 8000}/api/lease"
    while not stop.is_set():
        try:
            urllib.request.urlopen(urllib.request.Request(
                api, data=json.dumps({"id": lease_id}).encode(),
                headers={"Content-Type": "application/json"}, method="POST"), timeout=3).read()
        except Exception:
            pass                      # server briefly down/restarting — the bridge will notice itself
        stop.wait(4.0)
    try:                              # fast shutdown path: drop the lease on clean exit
        urllib.request.urlopen(urllib.request.Request(f"{api}/{lease_id}", method="DELETE"),
                               timeout=2).read()
    except Exception:
        pass  # the lease expires on its own within seconds — this is the fast path, not the mechanism


USAGE = """gfso.mcp.connect — the MCP bridge: one stdio session in, one HTTP session out.

This is not a command you run by hand. It speaks JSON-RPC over stdin/stdout, so an MCP client
starts it and talks to it; started from a terminal it will sit waiting for a request that never
comes. Point a client at it:

    "gfso": { "command": "python", "args": ["-m", "gfso.mcp.connect"] }

It reconciles the one server (127.0.0.1:8000 unless GFSO_SHARED_URL says otherwise) before
bridging, so an upgraded install is not silently served by the process from before the upgrade.

  -h, --help   this text
  --version    the version this bridge belongs to

To look at the graph WITHOUT a client: `gfso status`, `gfso log`, or the page at the server's URL.
"""


def _argv_answer(argv) -> str | None:
    """The text this bridge owes a person who ran it by hand — or None, meaning go and bridge.

    `main` never looked at argv, so `--help` fell through into the stdio server and blocked on a
    stdin that would never carry a request: the FIRST command a new user types against the
    documented entry point hung forever with no output (measured on the MCP door 2026-09-02). A
    door that cannot say what it is is indistinguishable from a dead one.

    Pure, and answered BEFORE any server contact, so it is instant and changes nothing.
    """
    args = [a for a in (argv or [])[1:] if a.strip()]
    if not args:
        return None
    if set(args) & {"-h", "--help", "help"}:
        return USAGE
    if "--version" in args:
        return f"gfso {__version__} (MCP bridge)"
    return f"gfso.mcp.connect takes no arguments (got {' '.join(args)}).\n\n{USAGE}"


def _why(e: BaseException) -> str:
    """The reason inside an exception, unwrapping the groups anyio raises.

    `ExceptionGroup` is the shape a task group failure arrives in, and printing its class name told
    a reader nothing at all — five reconnect lines that each said `ExceptionGroup` and nothing about
    what had actually gone wrong (bench, 2026-09-03).
    """
    seen, cur = [], e
    while True:
        subs = getattr(cur, "exceptions", None)
        if not subs:
            break
        cur = subs[0]
        seen.append(type(cur).__name__)
    tail = str(cur).strip().splitlines()[0][:120] if str(cur).strip() else ""
    return f"{type(cur).__name__}{': ' + tail if tail else ''}"


async def _bridge(url: str) -> None:
    """Own the client's stdio ONCE, and rebuild only the HTTP leg under it.

    The retry loop used to live outside `anyio.run`, so each attempt re-entered `_relay` and with it
    `stdio_server()` — and tearing that down deadlocks against a client still holding the pipe. The
    client's side is opened here, once, and outlives every rebuild; what is rebuilt is the leg that
    actually broke.
    """
    async with stdio_server() as (client_read, client_write):          # Claude Code side
        for attempt in range(_RECONNECTS + 1):
            try:
                await _relay(url, client_read, client_write)
                return                              # stdio closed = the client ended the session
            except Exception as e:
                if attempt >= _RECONNECTS or serverctl.runtime() is None:
                    print(f"[gfso connect] bridge closed ({_why(e)}) and the shared server "
                          f"is not answering — run `gfso up` and reconnect this session.",
                          file=sys.stderr, flush=True)
                    return
                print(f"[gfso connect] the shared server dropped this bridge ({_why(e)}) "
                      f"but is answering again — reconnecting ({attempt + 1}/{_RECONNECTS})",
                      file=sys.stderr, flush=True)
                await anyio.sleep(_RECONNECT_WAIT_S)


def main(argv: list | None = None) -> None:  # pragma: no cover — exercised live as the MCP entry
    """Answer an argv question, or bridge this session's stdio to the one shared server.

    Reconciles the server before bridging, so an upgraded install is not silently served by
    the process from before the upgrade, and rebuilds the leg when a restart drops it.
    """
    # ARGV IS PASSED IN, never read from the global. Reading `sys.argv` here made this answer to
    # whatever happened to be on the command line of whoever called it: `gfso connect` would have
    # seen its own subcommand as an unknown argument and refused to start — breaking the documented
    # entry point in the course of fixing it — and the suite's two bridge tests, which call `main()`
    # directly, got pytest's arguments. Only the `__main__` block below has a command line to read.
    if argv is not None and (said := _argv_answer(argv)) is not None:
        # stdout, not stderr: a person asked a question and this is the answer to it.
        print(said)
        sys.exit(0 if set(argv[1:]) & {"-h", "--help", "help", "--version"} else 2)
    _u = urlparse(URL)
    if foreign_holder(_u.hostname or _LOOPBACK, _u.port or 8000):
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
    # RECONNECT, don't die. The HTTP leg breaks whenever the shared server restarts — an upgrade, a
    # deliberate `up --force`, a crash — and this used to end the bridge process. The client does not
    # respawn it, so the session loses its gfso tools permanently: measured 2026-08-20, an agent's
    # very first call after a server restart returned `Session terminated` and every call after it
    # did too, while the server itself was up and serving others. Its own workaround was to write a
    # private HTTP client; a person would simply have stopped.
    # Retrying is bounded and quiet: if the server is genuinely gone the probe fails and we exit as
    # before, and the exit line now says what happened rather than naming an exception class.
    try:
        anyio.run(_bridge, URL)
    except KeyboardInterrupt:
        pass                      # Ctrl-C ends the bridge deliberately; the `finally`
                                  # below still drops the lease, so nothing is left held
    except Exception as e:
        # The stdio side is opened ONCE now, outside the rebuild loop — so a failure to open
        # it at all (no readable stdin, which is what a test harness hands us) escapes past
        # `_bridge` instead of being retried. The old shape caught it because the loop wrapped
        # the whole thing; this says the same sentence in the one place that can still say it.
        print(f"[gfso connect] bridge closed ({_why(e)}) and the shared server "
              f"is not answering — run `gfso up` and reconnect this session.",
              file=sys.stderr, flush=True)
    finally:
        stop.set()
        hb.join(3.0)                  # let the heartbeat thread fire its lease-drop


if __name__ == "__main__":  # pragma: no cover
    main(sys.argv)
