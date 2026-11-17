"""Whether the other end of a loopback connection is a process of this server's own OS user.

On a server bound to loopback that is the person locally (SECURITY.md): another OS user of this machine reaches the
port but cannot own a socket of ours; a container reaches it only through a port forwarder (`relayed`). Asked per request,
never remembered by port: an ephemeral port freed by a closed connection can be taken by another user's process.
"""
from __future__ import annotations

import os
import sys

import psutil


def _at(host: str, port: int) -> tuple:
    """An address as the OS table spells it: an IPv4 peer on a dual-stack socket arrives as `::ffff:a.b.c.d`."""
    return (host.removeprefix("::ffff:").lower(), port)


#: port forwarders that hold, as the user's own process, a connection made by whatever client they relay: Docker
#: Desktop's (measured: a container's call to host.docker.internal arrives held by com.docker.backend.exe), so any
#: container on the machine's engine — another account's in docker-users too — would be the person; read as a front
RELAYS = frozenset({"com.docker.backend", "com.docker.proxy", "vpnkit", "vpnkit-bridge", "docker-proxy"})


def _mine(p: psutil.Process) -> bool:
    if p.name().lower().removesuffix(".exe") in RELAYS:
        return False
    if os.name == "nt":
        return p.username() == psutil.Process().username()
    return p.uids().real == os.getuid()


def relayed(peer, server) -> bool:
    """Whether the connection's other end is held by a port forwarder (`RELAYS`): on this machine that is how a container
    reaches the host's loopback (Docker Desktop's backend, `docker-proxy`), so what it carries may be any container's
    code — an executor's included — and is served nothing without a credential. An owner the OS will not name is not
    taken for one: a front run by the system (`tailscale serve`) is refused the owner lookup the same way."""
    if not peer or not server:
        return False
    want = (_at(*peer), _at(*server))
    try:
        pid = next((c.pid for c in psutil.net_connections("tcp")
                    if c.raddr and (_at(*c.laddr), _at(*c.raddr)) == want), None)
        return bool(pid) and psutil.Process(pid).name().lower().removesuffix(".exe") in RELAYS
    except psutil.Error:
        return False


def ours(peer, server) -> bool:
    """Whether `peer` — (host, port) of the connection's client end, ASGI's `scope["client"]` — is held by a process of
    this server's user, `server` being the connection's other end (`scope["server"]`). An owner the OS will not name
    is not ours. macOS shows every process's sockets only to root, so there the user's own processes are searched."""
    if not peer or not server:
        return False
    want = (_at(*peer), _at(*server))
    hit = lambda c: c.raddr and (_at(*c.laddr), _at(*c.raddr)) == want
    try:
        if sys.platform == "darwin":
            me = os.getuid()
            for p in psutil.process_iter():
                try:
                    if p.uids().real == me and any(hit(c) for c in p.net_connections("tcp")):
                        return _mine(p)
                except psutil.Error:
                    continue
            return False
        pid = next((c.pid for c in psutil.net_connections("tcp") if hit(c)), None)
        return bool(pid) and _mine(psutil.Process(pid))
    except psutil.Error:
        return False
