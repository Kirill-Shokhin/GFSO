"""Every runtime asset matches a declared package-data glob — and the globs DECIDE what ships.

The `gfso` package is not pure Python: modules read files that sit beside them — the UI stylesheet
and icon, the decompose/critic/executor/validator prompts, and `gfso/mcp/ORCHESTRATOR.md`, which is
delivered to an agent as the MCP server's instructions. Drop one from the globs and the wheel is
built without it: the UI comes up unstyled, `auto_decompose` raises at import, and the MCP server
hands an agent session an EMPTY protocol while reporting healthy tools.

*(A correction worth keeping, because it nearly demoted this file: an earlier measurement here
concluded the globs were decorative — that removing `*.css` changed nothing about the artifact. That
measurement was taken in a working tree carrying a stale `gfso.egg-info/SOURCES.txt`, which
setuptools reuses; from a clean export the stylesheet vanishes exactly as it should. The lesson is
the project's own: a build cache is part of the apparatus, and a measurement taken through one is a
measurement of the cache.)*

This file checks the declaration against the tree, which is fast and runs everywhere.
`tests/test_distribution.py` checks the ARTIFACT — it builds from a clean copy, opens the wheel and
the sdist, installs the wheel into a fresh environment and drives it from a directory that is not
this repository. Both of its planted defects were shown to turn it red.
"""
import fnmatch
import pathlib
import tomllib

ROOT = pathlib.Path(__file__).parent.parent
PKG = ROOT / "gfso"


def _package_data_globs() -> list[str]:
    with open(ROOT / "pyproject.toml", "rb") as f:
        declared = tomllib.load(f)["tool"]["setuptools"]["package-data"]
    return [pat for patterns in declared.values() for pat in patterns]


def _runtime_assets() -> list[str]:
    return sorted(p.relative_to(PKG).as_posix() for p in PKG.rglob("*")
                  if p.is_file() and p.suffix != ".py" and "__pycache__" not in p.parts)


def _covered(rel: str, globs: list[str]) -> bool:
    """package-data patterns are relative to the OWNING package's directory, and a package may be at
    any depth — so a path counts as covered when some suffix of it matches some declared pattern."""
    parts = rel.split("/")
    return any(fnmatch.fnmatch("/".join(parts[i:]), pat)
               for i in range(len(parts)) for pat in globs)


def test_every_runtime_asset_is_declared_package_data():
    globs = _package_data_globs()
    missed = [rel for rel in _runtime_assets() if not _covered(rel, globs)]
    assert not missed, (f"these files are read at runtime but no package-data glob {globs} carries "
                        f"them into the wheel: {missed}")


def test_the_assets_the_product_cannot_run_without_are_present():
    """A named floor: renaming or losing one of these breaks a door, and the glob test above would
    stay green because it only asks whether what EXISTS is shipped."""
    required = ("web/index.html", "web/gfso.css", "web/tokens.css", "web/icon.svg",
                "mcp/ORCHESTRATOR.md", "mcp/prompts/executor.md", "mcp/prompts/validator.md",
                "decompose/prompts/search.md", "decompose/prompts/audit.md",
                "critic/prompts/atomicity.md", "critic/prompts/checker.md")
    assert not [r for r in required if not (PKG / r).exists()]
