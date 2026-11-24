"""Who a call comes from: one resolver for every door, and the local person's names, sessions and tokens.

A move is signed by a name its person owns, resolved here from the call's credential and never typed by the caller
(docs/notes/SIGN_IN.md): a page session signs as any name the person owns, a token as its one name; with no credential,
on a server bound to loopback and from a process of its own OS user, a page as the person, an MCP connection as the one
name it took (`take`: its log-in, `user` among them), and any other client — an MCP connection that has taken none
too — signs nothing (`BARE`): it reads. Everything is kept hashed in gfso's state, so it
survives a restart; a process of the same OS user can read that state, and SECURITY.md says so.
"""
from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path
import secrets
import sqlite3
import re
import time
from contextlib import closing, contextmanager
from urllib.parse import urlparse

from gfso.config import (AGENT, CALLER, LEASE_HEADER, LOCAL_PERSON, LOOPBACK_NAMES, PERSON, PERSONS_NAMES, SYSTEM,
                         PRINCIPAL_RE, STANDING, Principal, agent_id, bound_beyond_loopback, caller_id, closed_launch_name,
                         data_dir, launch_token, page_auth, protected, reserved_refusal)
import psutil

from gfso.adapters.storage import person as _person
from gfso.peer import ours as peer_is_ours, relayed as peer_is_a_relay
from gfso.roster import AgentRegistry

#: the page's session cookie
COOKIE = "gfso_session"
#: how long a one-time code from `gfso ui` opens the page
CODE_S = 300
#: names no person owns: the system, and the placeholder a verb signed by when it was given no name
NOBODYS = frozenset({SYSTEM, "person"})
#: the shapes the system's roles are named in — an executor's (`exec-1`, `<project>-exec-2`, `<project>-exec`), a validator's (`val-1`,
#: `ck-val-1`, `<project>-val`), a flag taken for a name (`--assignee`): a role the roster no longer holds is still one
SYSTEM_SHAPE = re.compile(r"^-|(^|-)exec(-?\d+)?$|(^|-)val([-\d].*)?$")

_SIGN_IN = "sign in: run `gfso ui`"
_FRONT = ("this call came through a front (a name of its own, a bind past loopback, or a forwarding header), where "
          "every client arrives from this machine: a browser signs in with `gfso ui --host <front>`, a client sends "
          "its token (`gfso agent <name>`, then GFSO_TOKEN=<token>)")
_FORWARDED = ("forwarded", "x-forwarded-", "tailscale-")
_STRANGER = ("This gfso is closed to calls from outside its own user's processes: to read or to move, open a session — "
             "on its computer run `gfso ui --host <the name you reached it at>` and open the link it prints here.")
#: a call with no credential the door serves the page's empty shell alone, no data: a port forwarder's (a container's)
#: in every mode, and under `--protected` any call that is not the person's own process
STRANGER = Principal("", (), "stranger", "not this machine's user", None, _STRANGER)
#: the person's own page, admitted as this machine's user with no sign-in: it signs as his person-name — `user`, the
#: name his user-agents act as — never as an agent-name of his (`LOCAL_PERSON` is the owner, no name in a graph)
PAGE = Principal(STANDING.name, (STANDING.name,), "local-peer", "local-peer", LOCAL_PERSON)
#: a process of the person's own with no credential, no page and no name taken — a script, curl, `gfso run` from any
#: shell, an MCP connection that has not logged in: it reads, and signs nothing. The author, 2026-11-20: «только агент
#: который залогинился под именем user может писать в граф»; 11-21: «взятие имени и есть логининг агента в системе»
BARE = Principal(STANDING.name, (), "bare", "no credential", LOCAL_PERSON,
                 "a move signs as someone, and this call carries no credential: as the person, on his page (`gfso ui`) "
                 "or through an MCP connection logged in as him (`act_as('user')`); as a stream, with its token "
                 "(`gfso agent <name>`, then GFSO_TOKEN=<token>)")
#: …an MCP connection that has taken no name: it reads, and logs in by taking one (`take`)
UNTAKEN = Principal(STANDING.name, (), BARE.via, "no name taken", LOCAL_PERSON,
                    "this gfso connection has taken no name, so it reads and signs nothing: `act_as('user')` logs it in "
                    "as the person, `act_as('<name>')` as a stream of his")
#: where an MCP client's bridge reaches the server: the door a lease logs in at
MCP_PATH = "/mcp"
#: a stdio server's own lease, its connection's for the life of its process: it logs in by it as a bridge does by its own
PROCESS_LEASE = "stdio-" + secrets.token_hex(16)



def _hash(raw: str) -> str:
    return hashlib.sha256(raw.encode()).hexdigest()


def _state() -> Path:
    """The sign-in state's file, in a directory of its own: beside the graphs it was read as one, and `signin` stood in
    the project list with its delete offered (ui). A file an earlier build left there moves once, with its journal."""
    path, old = data_dir() / "signin" / "state.db", data_dir() / "signin.db"
    if old.exists() and not path.exists():
        path.parent.mkdir(parents=True, exist_ok=True)
        for tail in ("", "-wal", "-shm"):
            if Path(f"{old}{tail}").exists():
                os.replace(f"{old}{tail}", f"{path}{tail}")
    return path


@contextmanager
def _db():
    """The state file, made on first use, when the names already in this machine's graphs become the local person's."""
    path = _state()
    fresh = not path.exists()
    path.parent.mkdir(parents=True, exist_ok=True)
    with closing(sqlite3.connect(path, timeout=10, isolation_level=None)) as db:
        yield _made(db, fresh)


def _held(query: str, *args) -> list:
    """What the state holds for a read, and nothing made for it: a lookup on a machine that never issued anything
    leaves no file behind (a read writes nothing)."""
    if not _state().exists():
        return []
    with _db() as db:
        return db.execute(query, args).fetchall()


def _made(db, fresh: bool):
    db.executescript("""
        CREATE TABLE IF NOT EXISTS names (name TEXT PRIMARY KEY, person TEXT NOT NULL);
        CREATE TABLE IF NOT EXISTS sessions (hash TEXT PRIMARY KEY, person TEXT NOT NULL, made REAL NOT NULL,
                                             host TEXT);
        CREATE TABLE IF NOT EXISTS tokens (hash TEXT PRIMARY KEY, id TEXT NOT NULL, person TEXT NOT NULL,
                                           name TEXT NOT NULL, made REAL NOT NULL);
        CREATE TABLE IF NOT EXISTS codes (hash TEXT PRIMARY KEY, person TEXT NOT NULL, until REAL NOT NULL);
        CREATE TABLE IF NOT EXISTS marks (key TEXT PRIMARY KEY, value TEXT NOT NULL);
        CREATE TABLE IF NOT EXISTS holds (lease TEXT PRIMARY KEY, name TEXT NOT NULL, person TEXT NOT NULL,
                                          via TEXT NOT NULL, since REAL NOT NULL, lost REAL);
    """)
    if "host" not in {r[1] for r in db.execute("PRAGMA table_info(sessions)")}:
        db.execute("ALTER TABLE sessions ADD COLUMN host TEXT")
        # …and the sessions from before go: their cookie reached every port of 127.0.0.1, another account's too
        db.execute("DELETE FROM sessions")
    if fresh:
        db.executemany("INSERT OR IGNORE INTO names VALUES (?, ?)", [(n, LOCAL_PERSON) for n in _names_in_the_graphs()])
    return db


def _systems() -> dict:
    """The roster's names by kind: `external` a person's, every other kind the system's (an executor, a validator)."""
    return {a: c.get("kind") for a, c in AgentRegistry().list().items()}


def systems_name(name: str, systems: dict | None = None) -> str | None:
    """Why `name` is the system's and no person's to sign as (§10.1: one signs only a role one holds), or None: a name
    nobody owns, a role on the roster now, or a role's shape — a person never signs as a system role."""
    if name in NOBODYS:
        return "the system"
    if (kind := (_systems() if systems is None else systems).get(name)):
        return None if kind == "external" else kind     # …a person's on the roster, whatever its name's shape
    return "a system role's name" if SYSTEM_SHAPE.search(name) else None


def _names_in_the_graphs() -> set:
    """Every party named in this machine's graphs — a node's Del, a root's issuer, a signer in the log — that is not the
    system's, so every party there keeps a mover when the sign-in comes."""
    found = set()
    for f in data_dir().glob("*.db"):
        try:
            with closing(sqlite3.connect(f"file:{f}?mode=ro", uri=True, timeout=2)) as g:
                for q in ("SELECT assignee FROM tasks", "SELECT value FROM settings WHERE key LIKE 'issuer:%'",
                          "SELECT DISTINCT source FROM audit_log"):
                    try:
                        found |= {str(r[0]) for r in g.execute(q) if r[0]}
                    except sqlite3.Error:
                        pass          # a graph from before that table: nothing named there
        except sqlite3.Error:
            continue                  # not a graph: nothing named in it
    systems = _systems()
    return {n for n in found if PRINCIPAL_RE.match(n) and n not in PERSONS_NAMES and not systems_name(n, systems)}


def ready() -> None:
    """The state made where it is not yet — on a server's first start, when the names in this machine's graphs become
    the local person's."""
    with _db():
        pass


def _state_pending(db) -> dict:
    """What the person's rename would write in the sign-in state: rows per field, empty where it ran."""
    if db.execute("SELECT 1 FROM marks WHERE key = ?", (_person.MARK,)).fetchone():
        return {}
    return {f"{t}.name": n for t in ("names", "tokens")
            if (n := db.execute(f"SELECT COUNT(*) FROM {t} WHERE name = ?", (_person.OLD,)).fetchone()[0])}


def rename_the_person() -> dict:
    """The person's name of before 0.4.0, `agent`, written `user` in every graph of this home and in the sign-in state,
    once (`adapters.storage.person`): {database: rows per field written, or {"refused": why} for a graph left as it
    is}. Refused whole (`TwoParties`) before anything is written where the sign-in state, which every project shares,
    names `user` as another party: a role on the roster, a token, a name another person owns. A conflict or a failed
    write inside ONE graph refuses that graph alone — it stays unopened, its reason said — and the others go on: the
    server stopped whole on one graph's `user`, and crashed on one it could not write (critic over 2b8e97f)."""
    graphs, refused = {}, {}
    for f in sorted(data_dir().glob("*.db")):
        try:
            with closing(sqlite3.connect(f, timeout=10)) as g:
                if (n := _person.pending(g)):
                    if (why := _person.refusal(g, f"graph {f.name}")):
                        refused[f.name] = {"refused": why}
                    else:
                        graphs[f] = n
        except sqlite3.DatabaseError:
            continue                  # not a graph: no party in it
    state, held = {}, []
    if _state().exists():
        with _db() as db:
            state = _state_pending(db)
            if db.execute("SELECT 1 FROM tokens WHERE name = ? AND person != ?", (PERSON, LOCAL_PERSON)).fetchone():
                held.append(f"a token for `{PERSON}`, another person's")   # …his own is his log-in (`issue`)
            if db.execute("SELECT 1 FROM names WHERE name = ? AND person != ?", (PERSON, LOCAL_PERSON)).fetchone():
                held.append(f"the name `{PERSON}`, another person's")
    if not (graphs or state):
        return refused
    if PERSON in _systems():
        held.append(f"the role `{PERSON}` on the roster")
    if held:
        raise _person.TwoParties(_person.merge_refusal(", ".join(held)))
    out = dict(refused)
    for f in graphs:
        try:
            with closing(sqlite3.connect(f, timeout=10)) as g:
                if (n := _person.rename(g)):
                    out[f.name] = n
        except (sqlite3.DatabaseError, _person.TwoParties) as ex:   # read-only, locked past its timeout, raced
            out[f.name] = {"refused": f"not rewritten ({ex}); the graph opens once it can be written"}
    if state:
        with _db() as db:
            db.execute("DELETE FROM names WHERE name = ? AND EXISTS (SELECT 1 FROM names WHERE name = ?)",
                       (_person.OLD, PERSON))
            for t in ("names", "tokens"):
                db.execute(f"UPDATE {t} SET name = ? WHERE name = ?", (PERSON, _person.OLD))
            db.execute("INSERT OR REPLACE INTO marks VALUES (?, ?)", (_person.MARK, _person.record(state)))
        out[str(_state().relative_to(data_dir()))] = state
    return out


def names_of(person: str) -> tuple:
    """Every name `person` owns, the standing agent first: locally his (the user's agent acts for him)."""
    systems = _systems()        # …read now: a name the roster gave the system since is his no more
    own = sorted(r[0] for r in _held("SELECT name FROM names WHERE person = ?", person))
    return (agent_id(), *[n for n in own if n not in PERSONS_NAMES and not systems_name(n, systems)])


def own(name: str, person: str = LOCAL_PERSON) -> None:
    """`name` becomes `person`'s: a name a person registered (`register_agent`, a person's kind) or was issued. The
    person's own names are refused: they are his already, and no agent-name of his is born under them."""
    if (why := reserved_refusal(name)):
        raise ValueError(why)
    if PRINCIPAL_RE.match(name) and name not in NOBODYS:
        with _db() as db:
            db.execute("INSERT OR IGNORE INTO names VALUES (?, ?)", (name, person))


def issue(name: str, person: str = LOCAL_PERSON) -> tuple[str, str]:
    """A token for `name`, which becomes `person`'s: (its id, the token) — his own name's (`PERSON`) too, which a
    connection logs in by under `--protected`. Refused for a name no person may own — the system's roles (an
    executor's, a validator's) and the names nobody owns."""
    if not PRINCIPAL_RE.match(name or ""):
        raise ValueError(f"{name!r} is not a name a role can be held by: letters, digits, `.`, `_`, `-`, up to 64")
    if name != PERSON and (why := reserved_refusal(name)):
        raise ValueError(why)
    if (kind := systems_name(name)):
        raise ValueError(f"{name!r} is the system's ({kind}): a person signs as a name of his own")
    if name != PERSON:
        own(name, person)
    raw, tid = "gfso_" + secrets.token_urlsafe(32), "tok-" + secrets.token_hex(4)
    with _db() as db:
        db.execute("INSERT INTO tokens VALUES (?, ?, ?, ?, ?)", (_hash(raw), tid, person, name, time.time()))
    return tid, raw


def revoke(name: str) -> int:
    """Every token for `name` revoked; how many were."""
    with _db() as db:
        return db.execute("DELETE FROM tokens WHERE name = ?", (name,)).rowcount


def code(person: str = LOCAL_PERSON) -> str:
    """A one-time code that opens a page session for `person`, good for `CODE_S`."""
    raw = secrets.token_urlsafe(24)
    with _db() as db:
        db.execute("DELETE FROM codes WHERE until < ?", (time.time(),))
        db.execute("INSERT INTO codes VALUES (?, ?, ?)", (_hash(raw), person, time.time() + CODE_S))
    return raw


def redeem(raw: str, host: str = "") -> str | None:
    """The session a one-time code opens at `host` (the name the page asked, kept with it), the code spent; None for a
    code spent, expired or never written."""
    with _db() as db:
        row = db.execute("DELETE FROM codes WHERE hash = ? AND until >= ? RETURNING person",
                         (_hash(raw or ""), time.time())).fetchone()
        if row is None:
            return None
        session = secrets.token_urlsafe(32)
        db.execute("INSERT INTO sessions (hash, person, made, host) VALUES (?, ?, ?, ?)",
                   (_hash(session), row[0], time.time(), host.lower()))
    return session


def sign_out(session: str) -> None:
    """The page session ended."""
    with _db() as db:
        db.execute("DELETE FROM sessions WHERE hash = ?", (_hash(session or ""),))


#: the credential of a connection whose holding was refused (`held`): it signs as no one, whatever name it reads as
REFUSED = "none"


def _refused(lift: str) -> Principal:
    return Principal(agent_id(), (), REFUSED, "not signed in", None, lift)


def by_token(raw: str) -> Principal:
    """The principal a token stands for, or a refusal naming how to get one."""
    row = next(iter(_held("SELECT id, person, name FROM tokens WHERE hash = ?", _hash(raw))), None)
    if row is None:
        return _refused("this token is not one this installation holds (revoked, or another home's): "
                        "`gfso agent <name>` issues one")
    if (kind := systems_name(row[2])):
        return _refused(f"this token is for {row[2]!r}, now the system's ({kind}): a person signs as a name of his own")
    return Principal(row[2], (row[2],), row[0], f"token for {row[2]}", row[1])


def by_session(raw: str, at: str, ours: bool) -> Principal | None:
    """The principal a page session stands for where it is shown `at` a name, `ours` whether the connection is this
    server's user's — None for a session not held, or not good where it is shown: one opened at a front's name counts at
    that very name alone; one opened at a loopback name (or before names were kept) only at a loopback name and from a
    peer of ours — its cookie reaches every port of the name, another account's server too, and a front of the person's
    relays what it is given."""
    row = next(iter(_held("SELECT person, host FROM sessions WHERE hash = ?", _hash(raw))), None)
    opened = row and (row[1] or "").lower()
    if row is None or (at != opened if opened and opened not in LOOPBACK_NAMES
                       else not (ours and at in LOOPBACK_NAMES)):
        return None
    return Principal(agent_id(), names_of(row[0]), "session", "signed in", row[0])


def _a_reader() -> Principal:
    """What a call no process of the person's makes, with no credential, is served: the graph to read and no move (the
    author, 2026-11-16: «чтение графа - вообще по канону может быть во многих случаях публичной базой. это и есть
    прозрачность»; «ходы пускай и будут со входом») — a phone through `tailscale serve`, a device on the LAN, another
    account alike; under `--protected` nothing, the page's shell alone."""
    return STRANGER if protected() else _refused(_FRONT)


def principal_of(conn) -> Principal:
    """Who a request comes from (its `headers`, `cookies`, `client` and `scope`): its bearer token or its page session
    where either names someone; else, on a server bound to loopback, the OS says whether the connection's other end is a
    process of this server's user (`peer.ours`): if so, asking a loopback name with nothing a front adds, a browser is
    the person's page (`page_auth`: `local-peer`, or `key`, where it signs in); a connection's lease the name it took
    (`held`), `user` among them; one that took none at the MCP door `UNTAKEN`, any other client `BARE` — both read
    only. A port forwarder's connection (a container's) is `STRANGER`, the page's shell alone. Every other call — a front's,
    the LAN's, another account's — is a reader (`_a_reader`): a front's every client arrives from this machine, so
    loopback says nothing there."""
    h = conn.headers
    auth, cookie = h.get("authorization") or "", conn.cookies.get(COOKIE)
    host = (urlparse("//" + (h.get("host") or "")).hostname or "").lower()
    bearer = auth[7:].strip() if auth.lower().startswith("bearer ") else None
    local = not bound_beyond_loopback()
    mine = peer_is_ours(conn.client, conn.scope.get("server"))
    ours = not local or mine      # …past a loopback bind every peer is a client of the network, no OS user's
    # …one session rule on every path (`by_session`): a front of the person's own user relayed a loopback cookie
    # another account had lured off a port of 127.0.0.1 (critic)
    fronted = any(k.lower().startswith(_FORWARDED) for k in h.keys())
    # …a front that rewrites the Host to its upstream carried a loopback session as the person: what came through a
    # front is no loopback call of ours, whatever Host it names (critic)
    p = by_token(bearer) if bearer is not None else cookie and by_session(cookie, host, mine and not fronted)
    if p and p.signs_as:
        return p
    if not mine and peer_is_a_relay(conn.client, conn.scope.get("server")):
        return STRANGER           # …a container's way to this machine's ports, an executor's code included (critic)
    if not ours or not local or host not in LOOPBACK_NAMES or fronted:
        return _a_reader()
    if p:
        return p                  # …a credential that names no one, from the person's own process: its refusal said
    if h.get("origin") or h.get("sec-fetch-site"):
        return _refused(_SIGN_IN) if page_auth() == "key" else PAGE
    lease = h.get(LEASE_HEADER)
    at_mcp = any(str(conn.scope.get(k) or "").startswith(MCP_PATH) for k in ("root_path", "path"))
    return held(lease) or (UNTAKEN if lease and at_mcp else BARE)


#: the server's live bridge leases, raw (`/api/lease`), handed down by the server that holds them; None, or None from
#: it (a server up less than one lease grace, its bridges not yet beaten), not known — every other connection's holding
#: then counts as live
LIVE_LEASES = None


def _when(t: float) -> str:
    return time.strftime("%Y-%m-%d %H:%M:%S", time.localtime(t))


def held(lease: str | None) -> Principal | None:
    """The name the connection of bridge lease `lease` took (`take`), as its principal; None where it took none. A
    holding lost to another connection, made by a claim under `--protected`, or of a name no longer its person's is
    refused, never read as the person: the console was a stream's, and its moves are not his."""
    row = next(iter(_held("SELECT name, person, via, since, lost FROM holds WHERE lease = ?", _hash(lease))), None) \
        if lease else None
    if row is None:
        return None
    name, person, via, since, lost = row
    if lost:
        return _refused(f"this connection took `{name}` at {_when(since)}, and another connection took it at "
                        f"{_when(lost)} while this one was silent: log in again (`act_as('{name}')`, or another name), "
                        f"or out (`act_as('')`)")
    if via == "claim" and protected():
        return _refused(f"under --protected a name is taken with its own credential: `act_as('{name}', token=…)`, "
                        f"the token `gfso agent {name}` prints")
    if (kind := systems_name(name)) or (via != "claim" and not _held("SELECT 1 FROM tokens WHERE id = ?", via)):
        what = f"now the system's ({kind})" if kind else "no longer issued: its token was revoked"
        return _refused(f"`{name}` is {what}: this connection signs as nothing. Log it in under a name of yours "
                        f"(`act_as('user')`, `act_as('<name>')`), or out (`act_as('')`)")
    return Principal(name, (name,), f"as:{_hash(lease)[:12]}", f"acting as {name} since {_when(since)}", person)


def holds(lease: str | None) -> str | None:
    """The name the connection of `lease` took, whatever its holding reads as now; None where it took none."""
    return next(iter(_held("SELECT name FROM holds WHERE lease = ?", _hash(lease))), (None,))[0] if lease else None


def live_holding(lease: str | None) -> str | None:
    """The name the connection of `lease` holds still — None where it took none, or another connection took it since
    (lost): what it owes is that connection's now."""
    return next(iter(_held("SELECT name FROM holds WHERE lease = ? AND lost IS NULL", _hash(lease))),
                (None,))[0] if lease else None


def take(lease: str | None, name: str, token: str = "", issued: bool = False) -> Principal:
    """The connection of lease `lease` logs in as `name` — the person's own (`PERSON`) or a stream's — from now until
    its bridge ends or it logs out (`let_go`): the holding kept in the sign-in state, so it outlives a `/clear` and a
    server restart, and recorded with its person, its credential and its time (Thm 11). Locally by default the person's
    own connection may take his name, or a name he owns or issued (`issued`: a node he assigned to it): his OS user is
    him already. Under `--protected` the name's own token is required. Taking another name re-logs the connection in
    under it; one name is held by one live connection (§2.6). ValueError says why not."""
    if not lease:
        raise ValueError("this connection names no bridge lease: a console takes a name through `gfso connect`")
    if bound_beyond_loopback():
        raise ValueError("past loopback every call carries its own credential: launch the console with the name's "
                         f"token (`gfso agent {name}`, then GFSO_TOKEN=<token>)")
    if not PRINCIPAL_RE.match(name or "") or (name != PERSON and (why := reserved_refusal(name))):
        raise ValueError(why if name and PRINCIPAL_RE.match(name) else f"{name!r} is not a name")
    if (kind := systems_name(name)):
        raise ValueError(f"{name!r} is the system's ({kind}): a person's connection acts as a name of his own")
    if token:
        if (by := by_token(token)).signs_as != (name,):
            raise ValueError(f"this token does not sign as `{name}`: " + (by.lift or f"it signs as `{by.name}`"))
        via = by.via
    elif protected():
        raise ValueError(f"under --protected a name is taken with its own credential: `act_as('{name}', token=…)`, "
                         f"the token `gfso agent {name}` prints at your shell")
    elif name == PERSON:
        via = "claim"
    elif name in names_of(LOCAL_PERSON) or issued:
        via = "claim"
        own(name)
    else:
        raise ValueError(f"`{name}` is not a name of yours: assign it a node first (its Del is yours to set, §10.1), "
                         f"or issue it (`gfso agent {name}`)")
    h, now = _hash(lease), time.time()
    with _db() as db:
        mine = db.execute("SELECT name FROM holds WHERE lease = ?", (h,)).fetchone()
        seen = LIVE_LEASES() if LIVE_LEASES is not None else None
        live = None if seen is None else {_hash(x) for x in seen}
        for other, since in db.execute("SELECT lease, since FROM holds WHERE name = ? AND lost IS NULL AND lease != ?",
                                       (name, h)).fetchall():
            # …a connection recorded under its console is alive while its process is — a bridge's and a stdio
            # server's alike, whatever the server's own list of leases knows; one unrecorded, by that list
            if (alive := _recorded_alive(other)) or (alive is None and (live is None or other in live)):
                raise ValueError(f"`{name}` is held by another connection since {_when(since)} (as:{other[:12]}): Del "
                                 f"names one accountable party (§2.6), so one console holds a name at a time. Work in "
                                 f"that console, or close it: the name frees when its bridge ends")
            db.execute("UPDATE holds SET lost = ? WHERE lease = ?", (now, other))
        if mine is None:
            db.execute("INSERT INTO holds VALUES (?, ?, ?, ?, ?, NULL)", (h, name, LOCAL_PERSON, via, now))
        elif mine[0] != name:           # …a re-log-in under another name: its own time, the old holding ended
            db.execute("UPDATE holds SET name = ?, via = ?, since = ?, lost = NULL WHERE lease = ?", (name, via, now, h))
        elif token:
            db.execute("UPDATE holds SET via = ? WHERE lease = ?", (via, h))   # …a claim, now with its token
    print(f"[gfso] connection as:{h[:12]} acts as `{name}` ({via}), for {LOCAL_PERSON}", flush=True)
    return held(lease)


def let_go(lease: str | None) -> None:
    """The connection of `lease` logs out: the name it took is free, and it reads and signs nothing until it takes one."""
    if lease:
        with _db() as db:
            if db.execute("DELETE FROM holds WHERE lease = ?", (_hash(lease),)).rowcount:
                print(f"[gfso] connection as:{_hash(lease)[:12]} logged out", flush=True)


def local_principal(mcp: bool = False) -> Principal:
    """Who a call with no server between comes from — the CLI's own path, a stdio server (`mcp`): the token in
    `GFSO_TOKEN`, else the name this console's bridge took; else, over MCP, the name the stdio server's own connection
    took (`PROCESS_LEASE`), none a connection that reads (`UNTAKEN`); and from the CLI a reader (`BARE`), as at the
    server's door: any shell runs it."""
    if (refused := launch_refusal()) is not None:
        return _refused(refused)
    raw = launch_token()
    return by_token(raw) if raw else held(console_lease()) or (held(PROCESS_LEASE) or UNTAKEN if mcp else BARE)


def launch_refusal() -> str | None:
    """What a console launched under the closed `GFSO_AGENT_ID` and no token runs instead, said at every client door
    (the bridge, the CLI, `gfso wait`, a stdio server): a name is signed by its token now, and taking the console for
    the standing agent would sign its moves as someone it was not launched as."""
    if (name := closed_launch_name()) and not launch_token():
        return (f"GFSO_AGENT_ID names a console no more: launch this console without it, and take the name in it — "
                f"`act_as('{name}')` over its gfso connection — or launch it with the token `gfso agent {name}` prints "
                f"(GFSO_TOKEN=<token>).")
    return None


def credential_header() -> dict:
    """The header a client's token rides in to the server (`GFSO_TOKEN`, set at its launch outside the agent), else its
    console's bridge lease: the name that connection took signs; none, the client reads (`BARE`). A console launched the
    closed way stops here (`launch_refusal`)."""
    if (refused := launch_refusal()) is not None:
        raise SystemExit(f"gfso: {refused}")
    if (t := launch_token()):
        return {"Authorization": f"Bearer {t}"}
    return {LEASE_HEADER: lease} if (lease := console_lease()) else {}


#: what a bridge is launched through, never the console itself: the bridge's own interpreter and launchers, and a
#: shell a client may start it by
_LAUNCHERS = frozenset({"gfso", "python", "python3", "pythonw", "py", "uv", "uvx", "pipx", "cmd", "sh", "bash", "zsh",
                        "powershell", "pwsh", "conhost"})


def _consoles() -> Path:
    return data_dir() / "consoles"


def _console_of(proc: psutil.Process) -> psutil.Process | None:
    """The console a bridge runs under: its nearest ancestor that is no launcher of it (the MCP client, Claude Code)."""
    return next((a for a in proc.parents() if a.name().lower().removesuffix(".exe") not in _LAUNCHERS), None)


def _stamp(proc: psutil.Process) -> list:
    """A process as a record names it: its pid and start time, so a reused pid is not it."""
    return [proc.pid, round(proc.create_time(), 3)]


def _alive(stamp) -> bool:
    try:
        return _stamp(psutil.Process(stamp[0])) == list(stamp)
    except psutil.Error:
        return False


def record_console(lease: str, bridge: psutil.Process | None = None, console: psutil.Process | None = None) -> None:
    """This bridge's lease written under its console's process and its own: a `gfso` call from that console's shell
    finds it (`console_lease`) and signs as the name its connection took — one console is one Del (§2.6), its shell
    and its MCP connection alike."""
    try:
        bridge = bridge or psutil.Process()
        if (console := console or _console_of(bridge)) is None:
            return
        _consoles().mkdir(parents=True, exist_ok=True)
        (_consoles() / f"{_hash(lease)[:16]}.json").write_text(
            json.dumps({"console": _stamp(console), "bridge": _stamp(bridge), "lease": lease}), encoding="utf-8")
    except (psutil.Error, OSError):
        pass                      # …no console found: its shell signs as it did, by its own credential


def _recorded_alive(hashed: str) -> bool | None:
    """Is the connection whose lease hashes to `hashed` alive by its own process — its console record's bridge
    (`record_console`)? None where it is recorded under no console."""
    try:
        bridge = json.loads((_consoles() / f"{hashed[:16]}.json").read_text(encoding="utf-8"))["bridge"]
    except (OSError, ValueError, KeyError, TypeError):
        return None
    return _alive(bridge)


def forget_console(lease: str) -> None:
    """The bridge's record, gone with it."""
    (_consoles() / f"{_hash(lease)[:16]}.json").unlink(missing_ok=True)


def console_lease() -> str | None:
    """The lease of the live bridge whose console is this process's NEAREST such ancestor (`record_console`) — a console
    started from another's shell is its own — or None: outside every console, or detached from it (a chain that no
    longer reaches the console). A record whose bridge is gone (killed past its own cleanup) is dropped as it is read."""
    if not _consoles().is_dir():
        return None
    by_console = {}
    for f in _consoles().glob("*.json"):
        try:
            r = json.loads(f.read_text(encoding="utf-8"))
            if not _alive(r["bridge"]):
                f.unlink(missing_ok=True)
                continue
            by_console[tuple(r["console"])] = r["lease"]
        except (OSError, ValueError, KeyError, TypeError):
            continue
    try:
        return next((by_console[s] for a in psutil.Process().parents() if (s := tuple(_stamp(a))) in by_console), None)
    except psutil.Error:
        return None


def whoami(project: str | None = None) -> dict:
    """The principal of the call being served, as the page and a client read it: `name` its default signer, `kind` a
    person signed in or an agent acting for him, `how` its credential, `signs_as` every name it may sign as. Asked about
    a project, the way to sign in opens that project's page (`gfso ui <project>`)."""
    p = CALLER.get() or STANDING
    lift = f"sign in: run `gfso ui {project}`" if project and p.lift == _SIGN_IN else p.lift
    # …`agent` the kind: the standing agent, or a console acting for the person under a name of his
    return {"name": caller_id(), "kind": "person" if p.a_page else AGENT if p.signs_as else "none",
            "how": p.how, "signs_as": list(p.signs_as), **({"lift": lift} if lift else {})}
