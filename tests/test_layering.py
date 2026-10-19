"""The layering GATE — the dependency matrix of architecture.md enforced mechanically.

Rules are checked over the AST (module- AND function-level imports both count: a lazy
`from gfso.critic import …` inside a method is still a layer edge). A violation is a red
test, not a narrated convention — invariants are rejected by the machine, not by review.

Layer map (§3A audit / architecture.md):
  L0  gfso.core       → itself only (the embeddable protocol standard; zero upward imports)
  L1  gfso.engine     → core only (the framework over the standard)
      gfso.tools      → core + engine only (the STRUCTURAL action surface; the LLM verbs
                        live in gfso.tools_llm — L2, free to pull decompose/delegate/runtime)
  L3  gfso.adapters   → core + adapters only (port implementations)
  Binding (mcp/api/web/cli/driver/main) is the ONLY place allowed to import binding.
"""
import pathlib

import gfso
from tests.support import imports_of, module_reached

ROOT = pathlib.Path(gfso.__file__).parent

# module prefix → allowed gfso-internal import prefixes (first two dotted segments)
# `gfso.config` is admissible EVERYWHERE: it is the settings vocabulary — one module, no gfso
# imports at all (os and pathlib), read at call time. A layer rule exists so a lower layer cannot
# reach into a higher one; a leaf that answers "where does this product keep its data, which model
# does it run by default" inverts nothing. Without this row every layer keeps its own spelling of
# those answers, which is the defect the config owner exists to remove.
# `gfso.places` is the same kind of leaf — where a path is, asked without waiting on a file server — and
# `docs/architecture.md` says so; the gate admitted only `gfso.config`, so the document and the gate disagreed about
# one module (sync audit, D-F17). A leaf stays one: `test_the_leaves_import_no_gfso` holds them to it.
_LEAVES = {"gfso.config", "gfso.places"}
RULES = {
    "gfso.core": {"gfso.core"} | _LEAVES,
    "gfso.engine": {"gfso.core", "gfso.engine"} | _LEAVES,
    "gfso.tools": {"gfso.core", "gfso.engine"} | _LEAVES,
    "gfso.adapters": {"gfso.core", "gfso.adapters"} | _LEAVES,
}

# gfso.doctor is binding: it reports on the doors, and `setup` drives them (it imports gfso.mcp).
BINDING = {"gfso.mcp", "gfso.api", "gfso.web", "gfso.cli", "gfso.driver", "gfso.main", "gfso.doctor"}


def _imports(py: pathlib.Path) -> set[str]:
    """Every gfso module this file imports, resolved (`support.imports_of`), cut to its first two segments."""
    return {".".join(module_reached(ROOT.parent, m, n).split(".")[:2])
            for _, m, n in imports_of(py, ROOT.parent) if m.startswith("gfso")}


def _modules():
    for py in ROOT.rglob("*.py"):
        rel = py.relative_to(ROOT.parent).with_suffix("")
        yield ".".join(rel.parts), py


def test_layer_rules():
    violations = []
    for mod, py in _modules():
        for prefix, allowed in RULES.items():
            if mod == prefix or mod.startswith(prefix + "."):
                bad = _imports(py) - allowed - {mod.rsplit(".", 1)[0], "gfso"}
                if bad:
                    violations.append(f"{mod} imports {sorted(bad)} (allowed: {sorted(allowed)})")
    assert not violations, "layer violations:\n" + "\n".join(violations)


def test_binding_imported_only_by_binding():
    """mcp/api/web/cli/driver are the outermost shell: nothing below them may import them."""
    violations = []
    for mod, py in _modules():
        top2 = ".".join(mod.split(".")[:2])
        if top2 in BINDING or mod == "gfso.main":
            continue
        bad = _imports(py) & BINDING
        if bad:
            violations.append(f"{mod} imports binding layer {sorted(bad)}")
    assert not violations, "binding-layer violations:\n" + "\n".join(violations)


def test_the_leaves_import_no_gfso():
    """What every layer may import must itself import nothing of gfso, or the admission is a back door upward."""
    bad = {mod: sorted(_imports(py) - {"gfso"}) for mod, py in _modules() if mod in _LEAVES and _imports(py) - {"gfso"}}
    assert not bad, f"a leaf imports gfso modules: {bad}"
