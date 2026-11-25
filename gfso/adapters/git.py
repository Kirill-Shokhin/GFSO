"""THE SYSTEM'S GIT, SPELLED ONCE: every git it runs on this host is built here (`run`), and every script that runs git
elsewhere renders its flags from here (`sh`) — a copy spelled by hand lost `core.fsmonitor=false` in one script while
its neighbours kept it, and a repository's config ran there.

Two profiles, one question each answers: whose config the call reads.
* APART (the default) — the system's own git over a repository an agent writes: no config but the repository's
  (`NO_CONFIG`: the system's and the user's are not the agent's to read, and an image's `safe.directory` goes with
  them), no hook, no fsmonitor. Depth, not the bound — a repository's config still names filters, drivers, commands,
  and a denylist leaks by class. Its owner is not asked (`safe.directory=*`): nothing of a stranger's config runs
  hooked or monitored. Long paths taken where the platform bounds them (Git for Windows): a judge's copy deep in a
  project's places wrote no pack ("Filename too long") and read as the delivery's own fault.
* PLAIN — the user's own git over their own repository, as their console reads it: their config (under APART their
  CRLF checkout read as changed). Never `safe.directory=*`: with their config honoured, a repository another owner
  holds would run its fsmonitor and hooks as them — the class that check exists for.
Both (`EVERY`): no replace refs — an object they stand in for is not the one a checkout without them reads, and a
landing that read through them and wrote past them moved a branch to a commit it never checked —; no lazy fetch — an
object a partial clone lacks is the user's network, reached with their credentials, from no thread of the system's —;
no prompt.
"""
from __future__ import annotations

import shlex
import shutil
from pathlib import Path

from gfso.adapters import children
from gfso.config import subprocess_env
from gfso.places import same_place

APART = ("-c", "safe.directory=*", "-c", "core.hooksPath=/dev/null", "-c", "core.fsmonitor=false", "-c", "core.longpaths=true")
NO_CONFIG = {"GIT_CONFIG_NOSYSTEM": "1", "GIT_CONFIG_GLOBAL": "/dev/null"}
EVERY = {"GIT_NO_REPLACE_OBJECTS": "1", "GIT_NO_LAZY_FETCH": "1", "GIT_TERMINAL_PROMPT": "0"}
#: a fetch of what an agent made: every object checked as git takes it — the pack was made where an agent writes
FSCK = ("-c", "fetch.fsckObjects=true", "-c", "transfer.fsckObjects=true")
#: a wait past this is a hung git, not a slow one: a checkout of a large tree takes minutes
SLOW = 600


def argv(*args, plain: bool = False) -> list:
    """The command line of one git call under its profile."""
    return ["git", *(() if plain else APART), *args]


def env(extra: dict | None = None, plain: bool = False) -> dict:
    """The environment of one git call under its profile — `extra` never undoes a profile's own."""
    return subprocess_env(extra={**(extra or {}), **EVERY, **({} if plain else NO_CONFIG)})


def run(cwd, *args, plain: bool = False, extra: dict | None = None, input=None, text: bool = True,
        timeout: float = SLOW):
    """One git call on this host in `cwd` (None: the process's): text out, or bytes where `text` is False."""
    return children.run(argv(*args, plain=plain), timeout=timeout, cwd=None if cwd is None else str(cwd), input=input,
                        env=env(extra, plain), **({"text": True, "encoding": "utf-8", "errors": "replace"} if text else {}))


def sh(*flags) -> str:
    """APART as a shell script's words — its environment and flags before `git`, `flags` after them — for a script
    that runs git where the system's git cannot be called (`execution._EXPORT`, `_IMPORT`)."""
    return " ".join([*(f"{k}={v}" for k, v in {**EVERY, **NO_CONFIG}.items()), "git", *map(shlex.quote, (*APART, *flags))])


def is_top(base, plain: bool = False) -> bool:
    """Is `base` the top of a git work tree with a commit to branch from? Compared as places (`same_place`), not as
    text: git names the top by its target, so a base reached through a junction or spelled by its 8.3 short name read
    as another directory, and the user's own repository was refused as no top."""
    if not (shutil.which("git") and Path(base).is_dir()):
        return False
    got = run(base, "rev-parse", "--show-toplevel", "--verify", "HEAD", plain=plain)
    top = got.stdout.splitlines()[:1] if got.returncode == 0 else []
    return bool(top) and same_place(top[0], base)
