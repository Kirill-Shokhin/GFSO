"""Shared CORE construction — the ONE Engine that every interface mirror (HTTP API · MCP · CLI) derives from.

The Engine is the single surface; HTTP API, MCP and CLI are three equivalent wrappers over it (and the UI is a
browser client of the HTTP mirror). Keeping the factory here means the mirrors don't each re-invent it.
"""
from __future__ import annotations

import os

from gfso.engine import Engine
from gfso.adapters.agents.human import HumanAgent


def llm_factory(model: str = "sonnet"):
    """THE ONE switch every internal gfso LLM role goes through (decompose, validate, critic, future
    validate_node/delegate one-shots). Two env knobs, whole-system semantics (no per-role mixing):

    - `GFSO_PROVIDER` = anthropic (default) | generic
        anthropic → the headless `claude -p` transport (the ONLY Anthropic path);
        generic   → `GenericLLM` at `GFSO_GENERIC_BASE_URL` (OpenAI-compatible; local models /
                    other vendors, external users' own risk; `GFSO_GENERIC_MODEL`,
                    `GFSO_GENERIC_API_KEY` optional).
    - `GFSO_BILLING` = subscription (default) | api  — Anthropic only: `api` keeps
        ANTHROPIC_API_KEY in the child env (per-token billing on the same transport, measured);
        `subscription` strips it (claude.ai login).

    Flipping the whole system to a foreign provider and seamlessly back IS these two variables."""
    if os.environ.get("GFSO_PROVIDER", "anthropic") == "generic":
        from gfso.adapters.llm.generic import GenericLLM
        return GenericLLM(base_url=os.environ["GFSO_GENERIC_BASE_URL"],
                          model=os.environ.get("GFSO_GENERIC_MODEL", model),
                          api_key=os.environ.get("GFSO_GENERIC_API_KEY"))
    from gfso.adapters.llm.headless import HeadlessClaudeLLM
    return HeadlessClaudeLLM(model=model,
                             keep_api_key=os.environ.get("GFSO_BILLING", "subscription") == "api")


def build_engine_from_env(*, validate_signals: bool = True, default_storage: str = "sqlite",
                          default_llm: str = "none", seed: bool = False,
                          db_path: str | None = None) -> Engine:
    """The ONE Engine factory for every entry point. Reads the environment:
    `GFSO_STORAGE` (sqlite|memory, default `default_storage`) · `GFSO_DB_PATH` (sqlite path) ·
    `GFSO_LLM` (llm|stub|none, default `default_llm`; `llm` = the real provider via `llm_factory`,
    `GFSO_MODEL` selects its model). Headless entry points (MCP, CLI) take the defaults (sqlite,
    no llm, no seed); `gfso serve` passes default_storage='memory', default_llm='stub', seed=True.
    `db_path` overrides the sqlite file (the ProjectRegistry's per-project isolation).
    Returns a STARTED engine."""
    if os.environ.get("GFSO_STORAGE", default_storage) == "sqlite":
        from gfso.adapters.storage.sqlite import SqliteStorage
        storage = SqliteStorage(db_path or os.environ.get("GFSO_DB_PATH", "data/gfso.db"))
    else:
        from gfso.adapters.storage.memory import MemoryStorage
        storage = MemoryStorage()

    llm_kind = os.environ.get("GFSO_LLM", default_llm)
    if llm_kind in ("llm", "claude"):   # "claude" = the legacy alias for the real-provider path
        llm = llm_factory(model=os.environ.get("GFSO_MODEL", "haiku"))
    elif llm_kind == "stub":
        from gfso.adapters.llm.stub import StubLLM
        llm = StubLLM()
    else:
        llm = None

    engine = Engine(storage, HumanAgent(), llm=llm, validate_signals=validate_signals)
    engine.start()
    if seed and not engine.all_tasks():
        from gfso.demo import seed_demo
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
        import re
        self._kw = engine_kwargs
        self._dir = os.environ.get("GFSO_DATA_DIR", "data")
        self._engines: dict[str, Engine] = {}
        self._active = os.environ.get("GFSO_PROJECT", "default")
        ProjectRegistry._NAME_RE = re.compile(r"^[A-Za-z0-9_-]{1,64}$")

    @property
    def active(self) -> str:
        return self._active

    def engine(self, project: str | None = None) -> Engine:
        """The project's engine, created lazily; None/'' → the ACTIVE project."""
        name = project or self._active
        if not self._NAME_RE.match(name):
            raise ValueError(f"bad project name {name!r} (allowed: [A-Za-z0-9_-], ≤64)")
        if name not in self._engines:
            kw = dict(self._kw)
            if name != "default":
                kw["db_path"] = os.path.join(self._dir, f"{name}.db")
                kw["seed"] = False
            self._engines[name] = build_engine_from_env(**kw)
            try:  # delegation autostart rides with the engine (works under every entry point)
                from gfso.delegate import ensure_dispatcher
                ensure_dispatcher(self._engines[name])
            except Exception:
                pass
            cb = getattr(self, "_on_create", None)   # notify listeners (e.g. UI project list) that a project appeared
            if cb:
                try:
                    cb(name)
                except Exception:
                    pass
        return self._engines[name]

    def use(self, name: str) -> Engine:
        """Switch the ACTIVE project (creates it on first use). Every interface consulting the registry
        (MCP verbs' default, UI) follows — one shared registry per server process."""
        eng = self.engine(name)   # validates + creates
        self._active = name
        return eng

    def list(self) -> dict:
        """{active, projects}: every .db in GFSO_DATA_DIR + the loaded ones (default always present)."""
        names = {"default", *self._engines.keys()}
        try:
            names |= {f[:-3] for f in os.listdir(self._dir)
                      if f.endswith(".db") and self._NAME_RE.match(f[:-3])}
        except OSError:
            pass
        names.discard("gfso")  # the default project's own file — not a separate project
        return {"active": self._active, "projects": sorted(names)}
