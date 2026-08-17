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
import ast
import pathlib

import gfso

ROOT = pathlib.Path(gfso.__file__).parent

# module prefix → allowed gfso-internal import prefixes (first two dotted segments)
RULES = {
    "gfso.core": {"gfso.core"},
    "gfso.engine": {"gfso.core", "gfso.engine"},
    "gfso.tools": {"gfso.core", "gfso.engine"},
    "gfso.adapters": {"gfso.core", "gfso.adapters"},
}

# gfso.doctor is binding: it reports on the doors, and `setup` drives them (it imports gfso.mcp).
BINDING = {"gfso.mcp", "gfso.api", "gfso.web", "gfso.cli", "gfso.driver", "gfso.main", "gfso.doctor"}


def _imports(py: pathlib.Path) -> set[str]:
    tree = ast.parse(py.read_text(encoding="utf-8-sig"))
    out = set()
    for n in ast.walk(tree):
        if isinstance(n, ast.Import):
            out |= {a.name for a in n.names if a.name.startswith("gfso")}
        elif isinstance(n, ast.ImportFrom) and n.module and n.module.startswith("gfso"):
            out.add(n.module)
    return {".".join(i.split(".")[:2]) for i in out}


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
