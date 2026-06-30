"""Shared CORE construction — the ONE Engine that every interface mirror (HTTP API · MCP · CLI) derives from.

The Engine is the single surface; HTTP API, MCP and CLI are three equivalent wrappers over it (and the UI is a
browser client of the HTTP mirror). Keeping the factory here means the mirrors don't each re-invent it.
"""
from __future__ import annotations

import os

from gfso.engine import Engine
from gfso.adapters.agents.human import HumanAgent


def build_engine_from_env(*, validate_signals: bool = True, default_storage: str = "sqlite",
                          default_llm: str = "none", seed: bool = False) -> Engine:
    """The ONE Engine factory for every entry point. Reads the environment:
    `GFSO_STORAGE` (sqlite|memory, default `default_storage`) · `GFSO_DB_PATH` (sqlite path) ·
    `GFSO_LLM` (claude|stub|none, default `default_llm`; `GFSO_MODEL`/`GFSO_API_KEY` for claude).
    Headless entry points (MCP, CLI) take the defaults (sqlite, no llm, no seed); `gfso serve` passes
    default_storage='memory', default_llm='stub', seed=True. Returns a STARTED engine."""
    if os.environ.get("GFSO_STORAGE", default_storage) == "sqlite":
        from gfso.adapters.storage.sqlite import SqliteStorage
        storage = SqliteStorage(os.environ.get("GFSO_DB_PATH", "data/gfso.db"))
    else:
        from gfso.adapters.storage.memory import MemoryStorage
        storage = MemoryStorage()

    llm_kind = os.environ.get("GFSO_LLM", default_llm)
    if llm_kind == "claude":
        from gfso.adapters.llm.claude import ClaudeLLM
        llm = ClaudeLLM(api_key=os.environ.get("GFSO_API_KEY") or None,
                        model=os.environ.get("GFSO_MODEL", "claude-haiku-4-5-20251001"))
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
