"""THE ONE PLACE a provider's credentials are set and read (the author, 2026-10-28: «по регламенту факторки должно быть
только одно место для вставки токена и только там»; «у нас только одно единственное место провайдеров … то что внутри
провайдера можно делать несколько или даже много разных токенов - это ок … все это в любом случае должно заворачиваться в
один канал в систему»).

A credential belongs to its provider: the provider's class declares the kinds it takes (`credential_kinds`) and reads
its own from here, by its name; nothing else holds one. A key in an environment variable, a token in a container's
env-file, a launcher's default were each a second copy — which of them a call ran on depended on who started it. One
door writes for every provider — the CLI's `gfso credential` and the API's `/api/credentials/{provider}`, both this
module's acts; neither ever answers with a value, and the agent's MCP door has no such verb: a secret passed through the
agent stays in its transcript.

A provider holds a LIST of named credentials, each of its kind — `token`, a subscription's long-lived token (`claude
setup-token`); `api`, an API key — one ACTIVE pointer and an ORDER. Every call reads the credential in force at its
start (`current`), so moving the pointer (`use`) sends every new call to the new one while calls in flight finish on
theirs. A call its credential's limit refused marks it spent until the limit lifts (`spend`) and moves the pointer to
the next one in the order that is not: the project stops only when every one is spent. The file is the data
directory's `credentials.json`, readable by its owner alone."""
from __future__ import annotations

import json
import os
import threading
import time
from contextlib import contextmanager
from dataclasses import dataclass
from pathlib import Path

from gfso.config import LIMIT_RETRY_S, data_dir

KINDS = ("token", "api")
#: the variable a Claude client authenticates by, per kind — read by the provider and by a harness starting the CLI itself
CLAUDE_ENV = {"token": "CLAUDE_CODE_OAUTH_TOKEN", "api": "ANTHROPIC_API_KEY"}
_LOCK = threading.Lock()
#: how many times a read or a rename is tried again past the instant another process holds the file (10 ms apart)
_TRIES = 200
#: a lock older than this was left by a process that died holding it
_STALE_S = 15


@dataclass(frozen=True)
class Credential:
    kind: str
    value: str


def where() -> Path:
    """Where the provider's one place lives — for a refusal to name it."""
    return data_dir() / "credentials.json"


def _read(path: Path | None = None) -> dict:
    """The store as it stands; none yet — empty. A store that is there and does not read RAISES: read as "nothing set",
    a call ran on the host's login and a change wrote the whole store back near-empty (critic, two processes)."""
    p = path or where()
    for left in range(_TRIES, -1, -1):
        try:
            text = p.read_text(encoding="utf-8")
        except FileNotFoundError:
            return {}
        except PermissionError:            # Windows: the instant another writer renames a new one over it
            if not left:
                raise
            time.sleep(0.01)
            continue
        try:
            return normal(json.loads(text))
        except ValueError as e:
            raise ValueError(f"{p} does not read ({e}): fix or remove it, then set the credentials again") from e


def normal(raw: dict) -> dict:
    """Every provider as {active, order, held: {name: {kind, value}}, spent: {name: until}} — the shape before this one,
    one `{kind, value}` per provider and a second account as `provider@name`, read into it; one value held under two
    names is one credential, under the named one."""
    out: dict = {}
    for key, got in sorted(raw.items(), key=lambda kv: "@" not in kv[0]):       # the named ones first
        if not isinstance(got, dict):
            continue
        provider, _, name = key.partition("@")
        p = out.setdefault(provider, {"active": None, "order": [], "held": {}, "spent": {}})
        if "held" in got:
            p.update({k: got.get(k) or p[k] for k in ("active", "order", "held", "spent")})
            continue
        if not got.get("value"):
            continue
        same = next((n for n, c in p["held"].items() if c["value"] == got["value"]), None)
        n = same or name or got["kind"]
        p["held"][n] = {"kind": got["kind"], "value": got["value"]}
        p["order"] += [] if n in p["order"] else [n]
        if not name:
            p["active"] = n                    # the flat entry was the one in force
    for p in out.values():
        _settle(p)
    return {k: v for k, v in out.items() if v["held"]}


def _settle(p: dict) -> None:
    """The order over what is held, and an active one among them."""
    p["order"] = [n for n in p["order"] if n in p["held"]] + [n for n in p["held"] if n not in p["order"]]
    p["active"] = p["active"] if p["active"] in p["held"] else (p["order"] or [None])[0]


def _write(every: dict) -> None:
    p = where()
    p.parent.mkdir(parents=True, exist_ok=True)
    # …whole or not at all: rewritten in place, a call starting mid-write read it empty and ran on the host's login
    # (critic: 520 of 10 653 reads under one writer) — a new file, then one rename over the old
    tmp = p.with_name(f".{p.name}.{os.getpid()}.{threading.get_ident()}")
    # born readable by its owner alone: a write-then-chmod leaves the new file open to everyone between the two
    with os.fdopen(os.open(tmp, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600), "w", encoding="utf-8") as f:
        f.write(json.dumps(every, indent=1))
    os.chmod(tmp, 0o600)
    for left in range(_TRIES, -1, -1):
        try:
            return os.replace(tmp, p)
        except PermissionError:            # Windows: a reader holds the old one open for an instant
            if not left:
                raise
            time.sleep(0.01)


def _live(p: dict, name: str, now: float) -> bool:
    return (p["spent"].get(name) or 0) <= now


def in_force(p: dict, now: float | None = None) -> str | None:
    """The name a call starts on: the active one, or past it in the order the first not spent; all spent — the active."""
    now = time.time() if now is None else now
    order = p["order"]
    if not order:
        return None
    at = order.index(p["active"]) if p["active"] in order else 0
    return next((n for n in order[at:] + order[:at] if _live(p, n, now)), p["active"])


def current(provider: str, every: dict | None = None) -> tuple[str, Credential] | None:
    """(name, credential) a call of `provider` starts on now, or None — none set."""
    p = (every if every is not None else _read()).get(provider)
    if not p or (name := in_force(p)) is None:
        return None
    c = p["held"][name]
    return name, Credential(c["kind"], c["value"])


def get(provider: str) -> Credential | None:
    """The credential a call of `provider` starts on now, or None."""
    got = current(provider)
    return got[1] if got else None


@contextmanager
def _locked():
    """One writer at a time across PROCESSES — the person's `gfso credential` beside the server's `spend` — not only
    threads: a read-act-write of one lost the other's change, the pointer a person just moved included (critic)."""
    lock = where().with_name(".credentials.lock")
    lock.parent.mkdir(parents=True, exist_ok=True)
    with _LOCK:
        t0 = time.time()
        while True:
            try:
                os.close(os.open(lock, os.O_CREAT | os.O_EXCL | os.O_WRONLY))
                break
            except (FileExistsError, PermissionError):   # Windows: the last holder's delete still pending (critic)
                try:
                    age = time.time() - lock.stat().st_mtime
                except FileNotFoundError:
                    continue                   # released meanwhile: try again at once
                if age > _STALE_S:
                    lock.unlink(missing_ok=True)
                    continue
                if time.time() - t0 > 2 * _STALE_S:
                    raise TimeoutError(f"{lock} is held: another process is changing the credentials")
                time.sleep(0.01)
        try:
            yield
        finally:
            lock.unlink(missing_ok=True)


def _change(act) -> dict:
    with _locked():
        every = _read()
        act(every)
        _write(every)
    return listing()


def put(provider: str, kind: str, value: str | None, takes: tuple[str, ...] = KINDS, name: str | None = None) -> dict:
    """Set (`value`) or remove (None) `provider`'s credential `name` (default: its kind) of `kind`, which the provider
    must take (`takes`); without `name`, a removal removes them all. The first one set is the active one. Answers what
    is set now, never a value."""
    if value is not None and kind not in takes:
        raise ValueError(f"{provider!r} takes {' or '.join(takes) or 'no credential'}, not {kind!r}")

    def _act(every):
        if value is None:
            if name is None:
                every.pop(provider, None)
            elif (p := every.get(provider)) is not None:
                p["held"].pop(name, None)
                p["spent"].pop(name, None)
                _settle(p)
                if not p["held"]:
                    every.pop(provider)
            return
        p = every.setdefault(provider, {"active": None, "order": [], "held": {}, "spent": {}})
        n = name or kind
        p["held"][n] = {"kind": kind, "value": value.strip()}
        p["spent"].pop(n, None)
        p["order"] += [] if n in p["order"] else [n]
        p["active"] = p["active"] or n
    return _change(_act)


def _named(every: dict, provider: str, names) -> dict:
    p = every.get(provider)
    if not p:
        raise ValueError(f"no credential is set for {provider!r}")
    if unknown := [n for n in names if n not in p["held"]]:
        raise ValueError(f"{provider!r} holds {', '.join(p['held'])}, not {', '.join(unknown)}")
    return p


def use(provider: str, name: str) -> dict:
    """Move `provider`'s pointer to `name`: every call starting from now runs on it, those in flight finish on theirs."""
    def _act(every):
        p = _named(every, provider, [name])
        p["active"] = name
        p["spent"].pop(name, None)         # a person's choice: tried at once, its limit says again if it stands
    return _change(_act)


def order(provider: str, names: list[str]) -> dict:
    """The order `provider`'s pointer moves in when a limit refuses the one in force: `names`, then the rest held."""
    def _act(every):
        p = _named(every, provider, names)
        p["order"] = list(dict.fromkeys(names)) + [n for n in p["order"] if n not in names]
    return _change(_act)


def spend(provider: str, name: str, until: float | None = None) -> str | None:
    """`name`'s limit refused a call: spent until `until` (else `LIMIT_RETRY_S` from now), and the pointer, where it still
    stands on `name`, moved to the next one in the order not spent. Answers the one the call runs on next, or None —
    every one is spent, and the limit stops the project. A pointer moved away meanwhile (a person's `use`, another
    call's move) stays where it is, and `name` removed meanwhile is marked nothing (critic)."""
    moved: list = []

    def _act(every):
        p = every.get(provider)
        if not p:
            return
        now = time.time()
        if name in p["held"]:
            p["spent"][name] = until if until and until > now else now + LIMIT_RETRY_S
        nxt = in_force({**p, "active": name if p["active"] == name else p["active"]}, now)
        if nxt and nxt != name and _live(p, nxt, now):
            p["active"] = nxt if p["active"] == name else p["active"]
            moved.append(nxt)
    _change(_act)
    return moved[0] if moved else None


def lifts(provider: str) -> float | None:
    """When the first of `provider`'s spent credentials lifts, or None — none spent."""
    return min((_read().get(provider) or {}).get("spent", {}).values(), default=None)


def held() -> list[str]:
    """Every value set — for this process to look for where none may be (`conformance`), never to show."""
    return [c["value"] for p in _read().values() for c in p["held"].values()]


def listing() -> dict:
    """{provider: {active, in_force, order, held: {name: kind}, spent: {name: until}}} — what the door shows, no value."""
    now = time.time()
    return {k: {"active": p["active"], "in_force": in_force(p, now), "order": p["order"],
                "held": {n: c["kind"] for n, c in p["held"].items()},
                **({"spent": spent} if (spent := {n: u for n, u in p["spent"].items() if u > now}) else {})}
            for k, p in _read().items()}
