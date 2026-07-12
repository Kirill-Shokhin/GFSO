"""THE cut line of the gfso-core distribution — the single source the build and the tests share.

gfso-core = the zero-dependency closure GOVERNED BY THE CANON: the protocol standard (core/),
the reference runtime over it (engine/: process_signal, audit, timeout monitor), the structural
action surface (tools.py), and the neutral stdlib adapters (storage, human agent, stub LLM).
Everything above — the author's product (decompose/critic/delegate, LLM adapters, transports,
UI, runtime DI) — ships as the `gfso` distribution and depends on this one.

The line is where THREE independent boundaries coincide (that is what makes it ONE seam):
governance (below changes ⟺ the canon changes), dependencies (below = pure stdlib), and the
mechanically-enforced layer gate (tests/test_layering.py: every crossing edge points down).
tests/test_core_dist.py proves the closure continuously; publication is a later flip
(packaging/build_core.py builds the wheel from this manifest today).
"""
from __future__ import annotations

import pathlib

# Whole subpackages (every .py under them ships)
CORE_PACKAGES = (
    "gfso/core",
    "gfso/engine",
)

# Individual modules/files
CORE_FILES = (
    "gfso/__init__.py",
    "gfso/tools.py",
    "gfso/adapters/__init__.py",
    "gfso/adapters/storage/__init__.py",
    "gfso/adapters/storage/memory.py",
    "gfso/adapters/storage/sqlite.py",
    "gfso/adapters/agents/__init__.py",
    "gfso/adapters/agents/human.py",
    "gfso/adapters/llm/__init__.py",
    "gfso/adapters/llm/stub.py",
)


def core_paths(root: pathlib.Path) -> list[pathlib.Path]:
    """Every file of the core distribution, as paths under `root` (the repo root)."""
    out = [root / f for f in CORE_FILES]
    for pkg in CORE_PACKAGES:
        out.extend(sorted((root / pkg).rglob("*.py")))
    return out


def covered_module_prefixes() -> set[str]:
    """gfso-import prefixes (two dotted segments) the manifest covers — the closure boundary."""
    return {"gfso.core", "gfso.engine", "gfso.tools", "gfso.adapters"}
