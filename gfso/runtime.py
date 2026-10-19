"""Shared CORE construction — the ONE Engine that every interface mirror (HTTP API · MCP · CLI) derives from.

The Engine is the single surface; HTTP API, MCP and CLI are three equivalent wrappers over it (and the UI is a
browser client of the HTTP mirror). Keeping the factory here means the mirrors don't each re-invent it.
"""
from __future__ import annotations

import logging
import os
import re
import sys

from gfso.engine import Engine
from gfso.core.graph.model import root_of
from gfso.adapters.agents.human import HumanAgent
from gfso.adapters.llm.stub import StubLLM
from gfso.adapters.storage.memory import MemoryStorage
from gfso.adapters.storage.sqlite import SqliteStorage, peek_root
from gfso.demo import seed_demo
from gfso import config as _config
from gfso.config import (data_dir as _config_data_dir, active_project,
                         remember_active_project, DEFAULT_PROJECT)
from gfso.llm import llm_factory

log = logging.getLogger(__name__)


def data_dir():
    """THE state directory: `GFSO_DATA_DIR` if set, else `data/` under the installation's home.

    Anchored on `serverctl.home()` rather than on the current directory, because every default path
    in this package used to resolve against wherever the caller happened to stand — so `gfso run`
    from one directory and the server started from another read different databases, silently, and
    the user's graphs went missing rather than erroring.
    """
    return _config_data_dir()


def build_engine_from_env(*, validate_signals: bool = True, default_storage: str = "sqlite",
                          default_llm: str = "none", seed: bool = False,
                          db_path: str | None = None) -> Engine:
    """The ONE Engine factory for every entry point. Reads the environment:
    `GFSO_STORAGE` (sqlite|memory, default `default_storage`) · `GFSO_DB_PATH` (sqlite path) ·
    `GFSO_LLM` (llm|stub|none, default `default_llm`; `llm` = the real provider via `llm_factory`,
    `GFSO_MODEL` selects its model). Headless entry points (MCP, CLI) take the defaults (sqlite,
    no llm, no seed); `gfso serve` passes default_storage='memory', default_llm='stub'; seeding is opt-in (`--seed`).
    `db_path` overrides the sqlite file (the ProjectRegistry's per-project isolation).
    Returns a STARTED engine."""
    if _config.storage_kind(default_storage) == "sqlite":
        storage = SqliteStorage(str(db_path or _config.db_path()))
    else:
        storage = MemoryStorage()

    llm_kind = _config.llm_kind(default_llm)
    if llm_kind in ("llm", "claude"):   # "claude" = the legacy alias for the real-provider path
        llm = llm_factory(model=_config.engine_model())
    elif llm_kind == "stub":
        llm = StubLLM()
    else:
        llm = None

    engine = Engine(storage, HumanAgent(), llm=llm, validate_signals=validate_signals)
    engine.start()
    if seed and not engine.all_tasks():
        seed_demo(engine)
    return engine


class ProjectRegistry:
    """Multi-project CORE: {project name → Engine}, one SQLite FILE per project (physical isolation IS
    the guarantee — a Dep edge across projects is not even representable; project boundary =
    Dep-closure boundary). A project = one GRAPH (a forest, many roots OK — Dep⊂T×T is
    canon-unrestricted, cross-root Dep is real). The DEFAULT project is the env-configured engine
    (GFSO_DB_PATH / gfso.db) — every existing call keeps working unchanged; named projects live at
    `GFSO_DATA_DIR/<name>.db`. One server process owns the registry (engine-per-process, unchanged)."""
    _NAME_RE = None  # compiled lazily

    def __init__(self, **engine_kwargs):
        self._kw = engine_kwargs
        self._dir = str(data_dir())
        self._engines: dict[str, Engine] = {}
        self._active = active_project()
        ProjectRegistry._NAME_RE = re.compile(r"^[A-Za-z0-9_-]{1,64}$")

    @property
    def active(self) -> str:
        """The project this process is pointed at right now."""
        return self._active

    def engine(self, project: str | None = None, create: bool = True) -> Engine:
        """The project's engine, created lazily; None/'' → the ACTIVE project.

        `create=False` REFUSES an unknown name instead of making one. A read used to create the
        project it was reading: `get_task root project=beta` on a name that did not exist answered
        "unknown task" and left a `beta.db` behind, so every typo became a permanent project — this
        installation had accumulated 315 of them (measured 2026-08-21). Only the verbs that AUTHOR
        create."""
        name = project or self._active
        if not self._NAME_RE.match(name):
            raise ValueError(f"bad project name {name!r} (allowed: [A-Za-z0-9_-], ≤64)")
        if (name not in self._engines and not create
                and name != DEFAULT_PROJECT
                and not os.path.exists(os.path.join(self._dir, f"{name}.db"))):
            raise KeyError(name)
        if name not in self._engines:
            kw = dict(self._kw)
            if name != "default":
                kw["db_path"] = os.path.join(self._dir, f"{name}.db")
                kw["seed"] = False
            self._engines[name] = build_engine_from_env(**kw)
            self._engines[name].project_name = name    # per-project instruments key off it
            self._engines[name]._project_name = name    # (the older spelling, still read downstream)
            try:  # delegation autostart rides with the engine (works under every entry point)
                # LEFT: import cycle gfso.runtime ↔ gfso.delegate (delegate → gfso.tools_llm →
                # gfso.runtime), so delegation is reached from here only at call time.
                from gfso.delegate import ensure_dispatcher
                ensure_dispatcher(self._engines[name])
            except Exception as ex:
                # Swallowed, this left a project that never auto-executes and never auto-validates
                # anything for the life of the process — indistinguishable, from outside, from an
                # executor that is merely slow.
                # stderr: stdout is `gfso mcp`'s JSON-RPC channel
                print(f"gfso: delegation dispatcher failed to start for project {name!r} ({ex}) — "
                      f"nothing will be dispatched or auto-validated there",
                      file=sys.stderr, flush=True)
            cb = getattr(self, "_on_create", None)   # notify listeners (e.g. UI project list) that a project appeared
            if cb:
                try:
                    cb(name)
                # a listener refresh is presentation — a UI that misses one project appearing must
                # not break the door that created it
                except Exception:
                    pass
        return self._engines[name]

    def use(self, name: str) -> Engine:
        """Switch the ACTIVE project (creates it on first use). Every interface consulting the registry
        (MCP verbs' default, UI) follows — one shared registry per server process, and the choice is
        REMEMBERED: a restart used to put every session that had not re-chosen back into `default`
        without saying so (MCP door, wave 26, 2026-09-06)."""
        eng = self.engine(name)   # validates + creates
        self._active = name
        remember_active_project(name)
        return eng

    def delete(self, name: str) -> dict:
        """Delete a NAMED project irreversibly: stop its engine (+its dispatcher), close the SQLite
        connection (Windows holds the file lock until then — observed live), remove `<name>.db`
        (+wal/shm). Refused: `default` (the env-configured engine owns no per-project file) and the
        ACTIVE project (switch away first — deleting the ground you stand on is the misclick this
        refusal exists for). A registry operation, not a graph signal: a project's log dies with
        the project by definition (cross-project provenance was never representable)."""
        if not self._NAME_RE.match(name):
            raise ValueError(f"bad project name {name!r} (allowed: [A-Za-z0-9_-], ≤64)")
        if name == "default":
            raise ValueError("the default project cannot be deleted")
        if name == self._active:
            raise ValueError(f"{name!r} is the ACTIVE project — switch away first (use_project)")
        eng = self._engines.pop(name, None)
        if eng is not None:
            try:
                # LEFT: import cycle gfso.runtime ↔ gfso.delegate (see `engine` above).
                from gfso.delegate import _DISPATCHERS
                d = _DISPATCHERS.pop(id(eng), None)
                if d:
                    d.stop()
            # A stop that raises must not leave the project HALF-deleted — the files go next.
            # …BUT IT IS NOT NOTHING: the dispatcher is out of the registry and may still be running,
            # polling a database that is deleted three lines below. Nothing owns it any more, so this
            # is the last place that can say so — and a poll against a removed file is what a reader
            # of the log will otherwise be trying to explain (found while naming the swallowed
            # failures, 2026-09-02).
            except Exception as _ex:
                log.warning(f"the dispatcher of {name!r} did not stop ({_ex}); it is unregistered and "
                            f"may still be polling a database this call is about to delete")
            eng.stop()
            close = getattr(eng._graph._storage, "close", None)
            if close:
                close()
        base = os.path.join(self._dir, f"{name}.db")
        for suffix in ("", "-wal", "-shm"):
            try:
                os.remove(base + suffix)
            # -wal/-shm exist only if SQLite made them; their absence is the normal case, not a
            # failure
            except FileNotFoundError:
                pass
        cb = getattr(self, "_on_create", None)   # registry-list listeners (UI) refresh on delete too
        if cb:
            try:
                cb(name)
            # a listener refresh is presentation — a UI that misses one deletion must not break the
            # door that performed it
            except Exception:
                pass
        return self.list()

    def list(self) -> dict:
        """{active, projects}: every .db in GFSO_DATA_DIR + the loaded ones (default always present)."""
        names = {"default", *self._engines.keys()}
        try:
            names |= {f[:-3] for f in os.listdir(self._dir)
                      if f.endswith(".db") and self._NAME_RE.match(f[:-3])}
        # a data dir that cannot be listed holds no stored projects, and the loaded names above
        # already say so
        except OSError:
            pass
        names.discard("gfso")  # the default project's own file — not a separate project
        # …ordered by when each was last WORKED IN, newest first. Alphabetical order made the picker
        # useless the moment the installation had a history: the project someone is actually on sat
        # somewhere in the middle of hundreds of names from finished runs and probes (measured: 271
        # entries, the live one 69th). Recency is the fact a picker needs, and the database's own
        # mtime already carries it — nothing new to track, and nothing has to be deleted to make the
        # list readable (those files are the provenance of past measurements).
        def _touched(name: str) -> float:
            for candidate in (f"{name}.db", "gfso.db" if name == "default" else f"{name}.db"):
                base = os.path.join(self._dir, candidate)
                try:
                    stamp = os.path.getmtime(base)
                except OSError:
                    continue
                # …OR ITS WAL, where a WAL-mode database's writes land until a checkpoint: the file
                # alone kept the stamp of its last checkpoint, so `ui-link-probe`, written at 16:43,
                # was listed as 09-07 beneath a hundred finished probes (2026-09-24). An EMPTY WAL
                # is not a write — a read-only open creates one — so it does not count.
                try:
                    if os.path.getsize(base + "-wal"):
                        stamp = max(stamp, os.path.getmtime(base + "-wal"))
                except OSError:      # no WAL: everything is in the file, and its stamp is the answer
                    pass
                return stamp
            return 0.0

        by_recency = sorted(names, key=lambda n: (-_touched(n), n))
        return {"active": self._active, "projects": by_recency,
                # The raw stamps too, so a client can group or age them without a second call.
                "last_active": {n: round(_touched(n), 0) for n in by_recency}}

    def roots(self, names) -> dict:
        """{name: {state, done_reason} | None} — each named project's root, None before it has one.

        A loaded project answers from its engine; any other is PEEKED at on disk, because building
        its engine would start its dispatcher, and looking at a list must not set a graph running."""
        def _root(name: str):
            eng = self._engines.get(name)
            if eng is not None:
                r = root_of(eng.all_tasks())
                return r and (r.state, r.done_reason)
            return peek_root(str(_config.db_path()) if name == DEFAULT_PROJECT
                             else os.path.join(self._dir, f"{name}.db"))
        return {n: (st := _root(n)) and {"state": st[0].name, "done_reason": st[1] and st[1].name}
                for n in names}
