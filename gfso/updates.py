"""Whether a newer gfso is published: the line `doctor` and the user-agent's first call carry to the person.

PyPI is asked at most once a day, the answer kept in the state directory; offline, a slow index or a garbled answer says
nothing, and `GFSO_NO_UPDATE_CHECK=1` turns the asking off. Nothing about the user travels: the request is the
package's public page. Only a final release (`X.Y.Z`) is offered to a person."""
from __future__ import annotations

import json
import re
import time
import urllib.request
from typing import Callable, Optional

from gfso import __version__
from gfso.config import asks_for_releases, client_kind, data_dir

INDEX = "https://pypi.org/pypi/gfso/json"
DAY_S = 24 * 3600
MISS_S = 3600          # an unanswered index is asked again after an hour, not on every call
RELEASE = re.compile(r"\d+\.\d+\.\d+")


def _ask_index() -> Optional[str]:
    with urllib.request.urlopen(INDEX, timeout=2) as r:
        return str(json.load(r)["info"]["version"])


def _seen_today(cache, now: float) -> tuple[bool, Optional[str]]:
    """(the last answer is kept, that answer) — a day for an answer, an hour for none; a garbled cache keeps none."""
    try:
        seen = json.loads(cache.read_text(encoding="utf-8"))
        return now - float(seen["checked_at"]) < (DAY_S if seen.get("latest") else MISS_S), seen.get("latest")
    except (OSError, ValueError, KeyError, TypeError):
        return False, None


def latest(now: Callable[[], float] = time.time, ask: Callable[[], Optional[str]] = _ask_index) -> Optional[str]:
    """The newest published version, from the day's cache or the index; None when unknown."""
    if not asks_for_releases():
        return None
    cache = data_dir() / "latest_release.json"
    kept, got = _seen_today(cache, now())
    if kept:
        return got
    try:
        got = ask()
    except Exception:   # offline, a slow or garbled index: nothing is told, and nothing asked for an hour (critic:
        got = None      # a dropped route cost every use_project its 2 s timeout, the shared server's loop with it)
    try:
        cache.write_text(json.dumps({"checked_at": now(), "latest": got}), encoding="utf-8")
    except OSError:     # an unwritable home only asks again next time
        pass
    return got


def newer(**kw) -> Optional[str]:
    """What to tell the person when a newer final release is published than this one, else None."""
    v = latest(**kw)
    if not (v and RELEASE.fullmatch(v) and RELEASE.fullmatch(__version__)) or \
            tuple(map(int, v.split("."))) <= tuple(map(int, __version__.split("."))):
        return None
    restart = "Claude Desktop" if client_kind() == "chat" else "Claude Code (`/exit`, `claude -c`)"
    return (f"gfso {v} is published; this is {__version__}. Tell the person once, after the task in hand, and do not run "
            f"it yourself: the upgrade is theirs — `pipx upgrade gfso`, then `gfso setup`, then a restart of {restart}, "
            f"while no task of theirs is running")
