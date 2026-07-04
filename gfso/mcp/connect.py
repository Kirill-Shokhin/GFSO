"""Lazy shared-server launcher — the stdio entry every Claude Code session points at.

`claude mcp add gfso -- python -m gfso.mcp.connect`

On session start it ENSURES the one shared gfso server is running (port closed → spawn it DETACHED,
so it outlives this session; port open → touch nothing — the second/third session just joins), then
transparently BRIDGES this session's stdio MCP traffic to the shared server's streamable-HTTP surface.
Result: any number of parallel agent sessions share ONE process — one event bus (live ticks for every
session in the UI), one dispatcher set, one registry — with zero manual server management.

Knobs (env): GFSO_SHARED_URL (default http://127.0.0.1:8000/mcp) · the spawned server inherits this
session's cwd + env (GFSO_DB_PATH etc.); its log goes to data/server.log.
"""
from __future__ import annotations

import os
import socket
import subprocess
import sys
import time
from urllib.parse import urlparse

URL = os.environ.get("GFSO_SHARED_URL", "http://127.0.0.1:8000/mcp")


def _port_open(host: str, port: int) -> bool:
    try:
        with socket.create_connection((host, port), timeout=0.5):
            return True
    except OSError:
        return False


def ensure_server(url: str = URL, wait_s: float = 25.0) -> bool:
    """Spawn the shared server DETACHED if its port is closed; wait until it answers.
    Returns True if the server is (now) up."""
    u = urlparse(url)
    host, port = u.hostname or "127.0.0.1", u.port or 8000
    if _port_open(host, port):
        return True
    os.makedirs("data", exist_ok=True)
    log = open(os.path.join("data", "server.log"), "a", encoding="utf-8")
    print(f"[gfso connect] shared server not running — starting it detached on :{port}",
          file=sys.stderr, flush=True)
    flags = 0x00000008 | 0x00000200 if os.name == "nt" else 0   # DETACHED | NEW_PROCESS_GROUP
    subprocess.Popen(
        [sys.executable, "-m", "gfso.cli", "serve", "--storage", "sqlite",
         "--db-path", os.environ.get("GFSO_DB_PATH", "data/gfso.db"),
         "--mcp", "--no-seed", "--no-browser", "--port", str(port), "--host", host],
        stdout=log, stderr=log, stdin=subprocess.DEVNULL,
        env=dict(os.environ, GFSO_AUTOEXIT="1"),   # dies by itself when the LAST session's lease expires
        creationflags=flags, start_new_session=(os.name != "nt"))
    t0 = time.monotonic()
    while time.monotonic() - t0 < wait_s:
        if _port_open(host, port):
            time.sleep(1.0)          # give the app a beat to finish mounting /mcp
            return True
        time.sleep(0.4)
    print(f"[gfso connect] server did not come up on :{port} within {wait_s}s (see data/server.log)",
          file=sys.stderr, flush=True)
    return False


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
    if not ensure_server():
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
