"""THE ONE PLACE a provider's credential is set and read (the author, 2026-10-28: «по регламенту факторки должно быть
только одно место для вставки токена и только там»; «единственное место провайдера должно быть в классе провайдера и
едином ендпоинте для всех»).

A credential belongs to its provider: the provider's class declares the kinds it takes (`credential_kinds`) and reads
its own from here, by its name; nothing else holds one. A key in an environment variable, a token in a container's
env-file, a launcher's default were each a second copy — which of them a call ran on depended on who started it (the
E3 rows ran on the author's own login while a second account was meant). One door writes for every provider — the CLI's
`gfso credential` and the API's `/api/credentials/{provider}`, both this module's `put`; neither ever answers with a
value, and the agent's MCP door has no such verb: a secret passed through the agent stays in its transcript.

Kinds: `token` — a subscription's long-lived token (`claude setup-token`), held by the client that calls the model;
`api` — an API key. The file is the data directory's `credentials.json`, readable by its owner alone."""
from __future__ import annotations

import json
import os
from dataclasses import dataclass
from pathlib import Path

from gfso.config import data_dir

KINDS = ("token", "api")


@dataclass(frozen=True)
class Credential:
    kind: str
    value: str


def _path() -> Path:
    return data_dir() / "credentials.json"


def _all() -> dict:
    try:
        return json.loads(_path().read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}


def get(provider: str) -> Credential | None:
    """The credential set for `provider`, or None."""
    got = _all().get(provider)
    return Credential(got["kind"], got["value"]) if isinstance(got, dict) and got.get("value") else None


def put(provider: str, kind: str, value: str | None, takes: tuple[str, ...] = KINDS) -> dict:
    """Set (`value`) or remove (None) `provider`'s credential of `kind`, which the provider must take (`takes`). Answers
    what is set now, never a value."""
    if value is not None and kind not in takes:
        raise ValueError(f"{provider!r} takes {' or '.join(takes) or 'no credential'}, not {kind!r}")
    every = _all()
    if value is None:
        every.pop(provider, None)
    else:
        every[provider] = {"kind": kind, "value": value.strip()}
    p = _path()
    p.parent.mkdir(parents=True, exist_ok=True)
    # born readable by its owner alone: a write-then-chmod leaves the new file open to everyone between the two
    with os.fdopen(os.open(p, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600), "w", encoding="utf-8") as f:
        f.write(json.dumps(every, indent=1))
    os.chmod(p, 0o600)
    return listing()


def held() -> list[str]:
    """Every value set — for this process to look for where none may be (`conformance`), never to show."""
    return [c["value"] for c in _all().values() if isinstance(c, dict) and c.get("value")]


def listing() -> dict:
    """{provider: kind} of every credential set — what the door shows."""
    return {n: c.get("kind") for n, c in _all().items() if isinstance(c, dict)}
