"""The FACTS about the one shared server: what is declared, what is served, and where they differ.

This module is deliberately below the binding layer — it imports nothing that spawns or stops a
process, so `gfso.api` can stamp its own code version from it without an upward edge. The act of
reconciling (spawn / stop / wait) lives with the machinery that already did it,
`gfso.mcp.connect.ensure_correct`, which composes these facts.

There is exactly ONE server, `http://127.0.0.1:8000`, and the machinery to run it already exists:
`gfso.mcp.connect.ensure_server` spawns it detached when the port is closed (every Claude session
calls it), and `POST /api/shutdown` stops it (what `gfso down` uses). Neither answers the question
that keeps biting: not "is something listening" but **is what is listening the current code with
the switches this repository declares**.

A running process holds its sources in memory, so an edited tree never reaches it; and the switches
that decide what a run measures (`GFSO_VALIDATE_INTERNAL`, `GFSO_L2_GATE`, the agent registry) are
per-process, so any restart by anyone silently changes them. Both are read off the server here and
compared with the declared state; `ensure()` starts what is down, restarts what has drifted, and
leaves a correct server alone. No port is ever an argument — a second port is what caused the
address-drift bug this file exists to make unrepeatable.
"""
from __future__ import annotations

import hashlib
import json
import os
import socket
import time
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path
from typing import Optional
from urllib.parse import urlparse

from gfso import __version__
from gfso.config import agents_path as _roster
from gfso.config import home as _config_home
from gfso.config import LOOPBACK, shared_url

def _address() -> tuple[str, int]:
    """THE address of the one server. `GFSO_SHARED_URL` is the single knob — `gfso connect`, `gfso
    down` and `gfso log` already read it, and `up` reading a hardcoded 8000 instead meant the one
    command whose whole job is reconciliation could reconcile a different server than the one the
    session was talking to."""
    u = urlparse(shared_url())
    host, port = u.hostname or LOOPBACK, u.port or 8000
    return f"http://{host}:{port}", port


BASE, PORT = _address()
ROOT = Path(__file__).resolve().parent.parent          # the tree whose gfso/*.py the fingerprint covers


def home() -> Path:
    """Where THIS installation keeps its state: the database, the server log, `data/serve.json`, the
    agent registry.

    `GFSO_HOME` wins. A source checkout — a `pyproject.toml` sitting beside the package — keeps its
    state in the tree, as it always has. An INSTALLED package's `ROOT` is site-packages, which is no
    place for a database (an upgrade deletes it, a system install refuses to write it), so the
    fallback is `~/.gfso`: ONE home per user, for the same reason there is one server.

    The current directory was the earlier fallback, and it was the wrong axis. Isolation between
    pieces of work is what PROJECTS are (`use_project`, one database file each); making the
    directory carry it as well meant a second directory got a second database that the one server
    could not serve at the same time — so yesterday's graphs were not lost but unreachable, and
    nothing said so. Every other default path in the package now resolves against this function
    (`gfso.runtime.data_dir`), including the doors that used to read the caller's cwd.
    """
    return _config_home()


def declared_path() -> Path:
    """Where the installation writes what its server should be (`data/serve.json`)."""
    return home() / "data" / "serve.json"


# The declared state of the one server. `data/serve.json` under `home()` overrides it, so the
# configuration is a fact of the installation rather than of whoever last typed a command — and
# anything experiment-specific (a named agent registry, a different validator) belongs in that file,
# not in the defaults a stranger's first install inherits.
# GFSO_VALIDATE_INTERNAL is a MEASUREMENT dial and ships OFF. With it on, every node inside one
# Del scope gets its own minutes-long validator agent — while ORCHESTRATOR.md tells the agent not to
# spend a validation on an internal node, and the canon puts the guarantee at the SEAMS (§14.5 D6).
# A run that wants every node validated says so in `data/serve.json`, which is where anything
# experiment-specific belongs.
DEFAULTS = {"GFSO_L2_GATE": "1"}


def source_fingerprint() -> str:
    """A short hash of the package's sources ON DISK — the server stamps it at import, a caller
    recomputes it, and equality is the whole meaning of "the server is current"."""
    h = hashlib.sha256()
    # Not only `*.py`. ORCHESTRATOR.md is the entire protocol an agent receives, and the
    # decompose/critic/executor/validator prompts decide what every model role is told; all are read
    # ONCE at import or at server construction. A release that fixes a prompt changes no Python,
    # produced no drift, and never reached the running server.
    watched = [p for pat in ("*.py", "*.md", "*.html", "*.css", "*.svg")
               for p in (ROOT / "gfso").rglob(pat)]
    for p in sorted(set(watched)):
        if "__pycache__" in p.parts:
            continue
        h.update(p.relative_to(ROOT).as_posix().encode())
        h.update(p.read_bytes())
    return h.hexdigest()[:12]


def declared() -> dict:
    """The declared configuration: the shipped defaults, with `data/serve.json` over them.

    A fact of the INSTALLATION rather than of whoever last typed a command — which is what lets
    `gfso up` decide whether a running server is the right one instead of merely a live one."""
    # The registry path is derived from `home()` rather than frozen at import: it must be ABSOLUTE
    # (the server is spawned detached and every reader compares the same string) and it must follow
    # the installation, not the package's own location.
    # …through the owner, not composed by hand: this spelling ignored GFSO_DATA_DIR, so a moved
    # state directory took the graphs with it and left the roster where it had been (D-1).
    env = dict(DEFAULTS, GFSO_AGENTS_PATH=str(_roster()))
    path = declared_path()
    if path.exists():
        try:
            env.update({k: str(v) for k, v in json.loads(
                path.read_text(encoding="utf-8")).items()})
        except Exception as ex:
            print(f"gfso: {path.name} unreadable ({ex}) — using defaults")
    return env


def port_open(host: str = LOOPBACK, port: Optional[int] = None, timeout: float = 0.5) -> bool:
    """Is anything listening? THE one socket probe — a fact, so it lives with the other facts.

    It was implemented twice, and the copies answered for different callers: a test could neutralize
    one while the other still opened a real socket, so the case it was written for passed only when
    an unrelated server happened to be running on the machine.
    """
    try:
        with socket.create_connection((host, PORT if port is None else port), timeout=timeout):
            return True
    except OSError:
        return False


def wait_closed(timeout: float = 20.0, host: str = LOOPBACK) -> bool:
    """Block until nothing is listening; True if the port closed within `timeout`.

    A stop is asynchronous — the server answers the request and then exits — so every caller that
    must know it is GONE waits for the socket. The reconciler waited; `gfso down` did not, and
    `down` followed by `up` raced the exit: the next command read the runtime of a dying process,
    saw a session that was leaving with it, and declined to restart. Written twice, the two waits
    would drift the way the socket probe already did once (that is why `port_open` says "THE one").
    """
    deadline = time.monotonic() + timeout
    while port_open(host):
        if time.monotonic() >= deadline:
            return False
        time.sleep(0.25)
    return True


def projects(timeout: float = 10.0) -> Optional[dict]:
    """{active, projects, last_active} from the live server; None when nothing answers.

    Here rather than in the CLI because this module already owns the one server's address and the
    HTTP to it — a door that hand-rolls its own request is a second place that has to know both."""
    try:
        with urllib.request.urlopen(f"{BASE}/api/projects", timeout=timeout) as r:
            return json.loads(r.read() or b"null")
    except Exception:
        return None


def delete_project(name: str, timeout: float = 30.0) -> dict:
    """Delete one project irreversibly through the live server; the server refuses the ones it must
    (`default`, and whatever is active). Here for the same reason `projects()` is: this module owns
    the one server's address and the HTTP to it."""
    req = urllib.request.Request(f"{BASE}/api/projects/{urllib.parse.quote(name)}", method="DELETE")
    try:
        with urllib.request.urlopen(req, timeout=timeout) as r:
            return json.loads(r.read() or b"{}")
    except urllib.error.HTTPError as ex:
        return {"error": (ex.read() or b"").decode("utf-8", "replace")[:400] or str(ex)}
    except Exception as ex:
        return {"error": f"no server answered: {ex}"}


def runtime(timeout: float = 3.0) -> Optional[dict]:
    """What the live server says about itself; None when nothing answers."""
    try:
        with urllib.request.urlopen(f"{BASE}/api/runtime", timeout=timeout) as r:
            return json.loads(r.read() or b"null")
    except Exception:
        return None


def drift(rt: dict, env: dict, fingerprint: str) -> list[str]:
    """Why the live server is not the declared one — empty means it is."""
    out = []
    if rt.get("version") not in (None, __version__):
        out.append(f"version {rt.get('version')} != installed {__version__}")
    if rt.get("code_version") != fingerprint:
        out.append(f"code {rt.get('code_version') or 'pre-versioning'} != tree {fingerprint}")
    # A server without the agent door is the failure that looked healthiest: `gfso serve` typed by
    # hand mounts no /mcp, so it answered every probe while every agent session got a 404.
    if rt.get("with_mcp") is False:
        out.append("no agent door mounted (started with --no-mcp)")
    if "home" in rt and Path(rt["home"]) != home():
        out.append(f"state home {rt['home']} != {home()}")
    for key, field in (("GFSO_VALIDATE_INTERNAL", "validate_internal"), ("GFSO_L2_GATE", "l2_gate")):
        want = str(env.get(key, "")) not in ("", "0")
        if bool(rt.get(field)) != want:
            out.append(f"{field}={bool(rt.get(field))} != {want}")
    if (rt.get("agents_path") or "") != env.get("GFSO_AGENTS_PATH", ""):
        out.append("agent registry differs")
    # …and its CONTENT, not just its path. The registry is loaded once at startup, so an edited
    # file reaches nothing until a restart — measured: switching the validator's model left the
    # live server serving the old one while `up` reported "already-correct".
    want = agents_fingerprint(env.get("GFSO_AGENTS_PATH", ""))
    if "agents_version" in rt and rt.get("agents_version") != want:
        out.append(f"agent registry content {rt.get('agents_version') or 'unknown'} != file {want}")
    return out


def agents_fingerprint(path: str) -> str:
    """A stamp over the roster FILE, so a reconcile can tell "the same roster" from "a roster with
    the same path" — a run measured against another registry is a different measurement."""
    if not path:
        return ""
    try:
        return hashlib.sha256(open(path, "rb").read()).hexdigest()[:12]
    except OSError:
        return "missing"
