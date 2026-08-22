"""The FORM ratchet — the machine-checkable half of `CODE_ORTHO_STANDARD.md`.

`test_layering.py` guards one edge kind (the import). `test_coupling.py` guards the other three.
This one guards the OTHER matrix: not who depends on whom, but **in how many different ways the
package does the same thing**. Every rule here was derived from a divergence found by reading, and
each one has already cost this codebase a defect or a session — none is a style preference.

How the ratchet works, and why it is EQUALITY rather than an upper bound: `BASE` records what each
number is today. The test fails when a number GROWS (a new off-diagonal element) **and** when it
SHRINKS without `BASE` being updated (a stale allowance — the same "indulgence forever" failure the
coupling allowlist guards against). So every step of the plan ends with one honest edit to `BASE`,
and the file is the progress record: no narration, just the numbers in the repository.

If a number moved because of YOUR change, lower `BASE` in the same commit. If it moved because
someone else's work landed, re-baseline first — this repository drifts by tens of lines a session.
"""
from __future__ import annotations

import ast
import io
import re
import tokenize
from collections import defaultdict
from pathlib import Path

import pytest

import os

# `GFSO_REPO` lets the file run as a DIAGNOSTIC from anywhere; installed as tests/test_form.py it
# resolves the repo from its own location. The README claimed this parameterisation before the file
# had it — a diagnostic run outside `tests/` measured an empty tree and reported everything green.
_ROOT = Path(os.environ.get("GFSO_REPO") or Path(__file__).resolve().parent.parent)
PKG = _ROOT / "gfso"
TESTS = _ROOT / "tests"
SIZE_LIMIT = 40          # statements in one function body (flattened)

# The numbers as of the last measurement. ONE edit per step, in the step's own commit.
#: The quote characters this rule is ABOUT, named once — a rule whose own literals break it
#: reads as noise, and the count it produces then includes itself.
_SINGLE = chr(39)
_TRIPLES = (chr(39) * 3, chr(34) * 3)

BASE = {
    "A1_module_without_docstring": 16,
    "A2_import_inside_a_function": 190,
    "A3_module_imported_two_ways": 4,   # this test OWNS the number; the standalone tool counts
                                        # `from X import y` spellings too and says 16 — one rule, one owner
    "A4_public_function_without_contract": 182,
    "B1_attribute_born_outside_init": 3,   # ← headless declares `last_tool_calls` (S5, 2026-08-22)
    "B3_declared_field_read_defensively": 79,   # ← `authorized_validators`, `_roster` declared (2026-08-22)
    "C2_chain_dispatch_over_constants": 1,
    "D1_swallowed_failure": 27,   # only the UNEXPLAINED ones: nine already carry their reason
    "D1_bare_except": 0,
    "E2_hand_written_log_tag": 1,
    "F_single_quoted_literals": 14,
    "F_function_over_size_limit": 15,   # ← waves 1-3 cut ten monoliths (2026-08-23)
    # C5 — the hardcode rule, and the number S4 owns. Floor is 1, NOT 0: `GFSO_L2_GATE` is read at
    # its point of enforcement DELIBERATELY (hard constraint #7 of the run sheet) — it is the switch
    # of a measured mechanism, not a setting.
    # 51 after the four path derivations moved to their owner (`gfso.config`); it read 56, and
    # 56, not the 47 this plan predicted — and the difference is the point. CM-2 unaliased
    # `import os as _os`, and eight `_os.environ` reads that this rule could not see became
    # visible. The alias was hiding them FROM THE INSTRUMENT: S4 owns 56 sites, not 47.
    "C5_env_read_outside_config": 22,    # floor 1: GFSO_L2_GATE at its enforcement point
                                         # (S4, 2026-08-22: provider/billing/storage/llm/model,
                                         #  the runtime panel and the roster path have owners)
}

# The second root. `tests/` is 47 % of the package's python and the suite is the first thing an
# outside engineer reads, so it is in scope FOR FORM (the run sheet's own decision on `tests/`) — but only for the rules that
# mean the same thing there. Deliberately NOT applied to tests: C2 (a chain in a test is a table
# nobody reads twice), F_size (a scenario test is legitimately long), A4 (the test NAME is its
# contract in this suite), E2 (no logging). T1/T2 are what step S19 actually removes.
BASE_TESTS = {
    "A1_module_without_docstring": 1,
    "A2_import_inside_a_function": 266,
    "B1_attribute_born_outside_init": 0,
    "D1_swallowed_failure": 4,
    "F_single_quoted_literals": 36,
    "T1_engine_built_by_hand": 54,        # ← all five re-snapped at S1
    "T2_spec_helper_redefined": 6,
}

# Rules that are already at their target and must STAY there (a floor, not a ratchet step).
AT_TARGET = {"D1_bare_except"}


def _modules(root: Path) -> list[tuple[str, Path]]:
    return [(".".join(p.relative_to(root.parent).with_suffix("").parts), p)
            for p in sorted(root.rglob("*.py")) if "__pycache__" not in p.parts]


def _stmts(node: ast.AST) -> int:
    return sum(1 for n in ast.walk(node) if isinstance(n, ast.stmt)) - 1


def _measure(root: Path) -> tuple[dict[str, int], dict[str, list[str]]]:
    counts: dict[str, int] = defaultdict(int)
    where: dict[str, list[str]] = defaultdict(list)
    import_forms: dict[str, set[str]] = defaultdict(set)

    def hit(rule: str, addr: str) -> None:
        counts[rule] += 1
        where[rule].append(addr)

    for mod, path in _modules(root):
        src = path.read_text(encoding="utf-8-sig")
        tree = ast.parse(src)
        try:
            comment_lines = {t.start[0] for t in tokenize.generate_tokens(io.StringIO(src).readline)
                             if t.type == tokenize.COMMENT}
        except (tokenize.TokenError, IndentationError):
            comment_lines = set()

        # An import is "inside a function" only when a FUNCTION encloses it: a module-level `try:`
        # or `if TYPE_CHECKING:` is still the import section (the first version of this rule
        # reported `api/server.py`'s guarded fingerprint import, which is not a defect).
        in_fn = {n.lineno
                 for fn in ast.walk(tree) if isinstance(fn, (ast.FunctionDef, ast.AsyncFunctionDef))
                 for n in ast.walk(fn) if isinstance(n, (ast.Import, ast.ImportFrom))}
        # A chain is ONE construct: without this an eight-branch dispatch reports eight defects.
        chain_tail = {sub.lineno for n in ast.walk(tree) if isinstance(n, ast.If)
                      for sub in n.orelse if isinstance(sub, ast.If)}

        if ast.get_docstring(tree) is None:
            hit("A1_module_without_docstring", f"{mod}")

        for n in ast.walk(tree):
            if isinstance(n, (ast.Import, ast.ImportFrom)):
                if n.lineno in in_fn:
                    hit("A2_import_inside_a_function", f"{path.name}:{n.lineno}")
                for a in n.names:
                    if isinstance(n, ast.Import):
                        import_forms[a.name.split(".")[0]].add(
                            f"import {a.name}" + (f" as {a.asname}" if a.asname else ""))
            if isinstance(n, ast.Call) and isinstance(n.func, ast.Name) \
                    and n.func.id in ("getattr", "hasattr") and len(n.args) >= 2 \
                    and isinstance(n.args[1], ast.Constant) and isinstance(n.args[1].value, str)                     and not n.args[1].value.startswith("__"):
                # A dunder is the language's own protocol, not a neighbour's field. test_coupling
                # excludes them; this rule did not — one notion, two spellings, inside the pair of
                # instruments whose whole job is to forbid exactly that.
                hit("B3_declared_field_read_defensively", f"{path.name}:{n.lineno} {n.args[1].value}")
            if isinstance(n, ast.Call) and isinstance(n.func, ast.Attribute) \
                    and n.func.attr in ("info", "warning", "error", "debug") \
                    and isinstance(n.func.value, ast.Name) and n.func.value.id in ("log", "logger", "logging") \
                    and n.args and re.search(r"^f?['\"]\[[A-Za-z_]", ast.unparse(n.args[0])):
                hit("E2_hand_written_log_tag", f"{path.name}:{n.lineno}")
            if isinstance(n, ast.If) and n.lineno not in chain_tail and _chain_target(n):
                hit("C2_chain_dispatch_over_constants", f"{path.name}:{n.lineno}")
            # C5 — a read of the environment outside the one module that owns configuration.
            if isinstance(n, ast.Attribute) and n.attr == "environ"                     and isinstance(n.value, ast.Name) and n.value.id == "os"                     and mod not in ("gfso.config",):
                hit("C5_env_read_outside_config", f"{path.name}:{n.lineno}")
            if isinstance(n, ast.Call) and isinstance(n.func, ast.Attribute)                     and n.func.attr == "getenv" and mod not in ("gfso.config",):
                hit("C5_env_read_outside_config", f"{path.name}:{n.lineno}")
            # T1/T2 — what S19 removes: an engine built by hand instead of by the shared factory,
            # and the `_spec` helper redefined per file with drifting signatures.
            if isinstance(n, ast.Call) and isinstance(n.func, ast.Name) and n.func.id == "Engine":
                hit("T1_engine_built_by_hand", f"{path.name}:{n.lineno}")
            if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef)) and n.name == "_spec":
                hit("T2_spec_helper_redefined", f"{path.name}:{n.lineno}")
            if isinstance(n, ast.ExceptHandler):
                # The rule the STANDARD states is "swallow only WITH a reason written beside it" —
                # so the number must fall when the reason is written. Counting every `except: pass`
                # made the sanctioned repair invisible to the ratchet (a comment changes no AST),
                # leaving only "delete the handler" as a way to move the number. Comments are a
                # TOKEN-level fact, so they are collected per line above and consulted here.
                if len(n.body) == 1 and isinstance(n.body[0], ast.Pass)                         and not (comment_lines & {n.lineno - 1, n.lineno, n.body[0].lineno}):
                    hit("D1_swallowed_failure", f"{path.name}:{n.lineno}")
                if n.type is None:
                    hit("D1_bare_except", f"{path.name}:{n.lineno}")

        for cls in [c for c in ast.walk(tree) if isinstance(c, ast.ClassDef)]:
            init = next((f for f in cls.body
                         if isinstance(f, ast.FunctionDef) and f.name == "__init__"), None)
            declared = {n.attr for n in (ast.walk(init) if init is not None else ())
                        if isinstance(n, ast.Attribute) and isinstance(n.value, ast.Name)
                        and n.value.id == "self" and isinstance(n.ctx, ast.Store)}
            for fn in [f for f in cls.body
                       if isinstance(f, ast.FunctionDef) and f.name != "__init__"]:
                for n in ast.walk(fn):
                    if isinstance(n, ast.Attribute) and isinstance(n.value, ast.Name) \
                            and n.value.id == "self" and isinstance(n.ctx, ast.Store) \
                            and n.attr not in declared:
                        hit("B1_attribute_born_outside_init", f"{path.name}:{n.lineno} {cls.name}.{n.attr}")

        for fn in [f for f in ast.walk(tree) if isinstance(f, (ast.FunctionDef, ast.AsyncFunctionDef))]:
            if _stmts(fn) > SIZE_LIMIT:
                hit("F_function_over_size_limit", f"{path.name}:{fn.lineno} {fn.name} ({_stmts(fn)})")
            if not fn.name.startswith("_") and ast.get_docstring(fn) is None:
                hit("A4_public_function_without_contract", f"{path.name}:{fn.lineno} {fn.name}")

        # Quote style is measured on TOKENS, never by a regex over the source: a regex counts
        # apostrophes in English prose ("the executor's id") and reported four times the real number.
        try:
            # …AND THE MEASUREMENT MUST NOT DEPEND ON THE INTERPRETER. Since PEP 701 (3.12) an
            # f-string is tokenized in pieces, so every literal inside a replacement field becomes a
            # STRING token of its own: the same tree counted 14 on 3.11 and 248 on 3.13, and CI —
            # which runs the newer one — read that as a flood of new defects. A rule about the
            # quote style of a WRITTEN literal skips what lives inside an f-string, on every version.
            _FSTART = getattr(tokenize, "FSTRING_START", None)
            _FEND = getattr(tokenize, "FSTRING_END", None)
            _in_fstring = 0
            for tok in tokenize.generate_tokens(io.StringIO(src).readline):
                if _FSTART is not None and tok.type == _FSTART:
                    _in_fstring += 1
                    # the OUTER quote is one the author wrote, so it is measured like any other;
                    # what is skipped below is only what lives INSIDE the replacement fields
                    _q = tok.string[len(re.match(r"^[A-Za-z]*", tok.string).group(0)):]
                    if _q[:3] not in _TRIPLES and _q[:1] == _SINGLE:
                        hit("F_single_quoted_literals", f"{path.name}:{tok.start[0]}")
                    continue
                if _FEND is not None and tok.type == _FEND:
                    _in_fstring = max(0, _in_fstring - 1)
                    continue
                if tok.type != tokenize.STRING or _in_fstring:
                    continue
                q = tok.string[len(re.match(r"^[A-Za-z]*", tok.string).group(0)):]
                if q[:3] not in _TRIPLES and q[:1] == _SINGLE:
                    hit("F_single_quoted_literals", f"{path.name}:{tok.start[0]}")
        except (tokenize.TokenError, IndentationError):
            pass

    for base, forms in import_forms.items():
        if len(forms) > 1:
            hit("A3_module_imported_two_ways", f"{base}: {sorted(forms)}")
    return dict(counts), dict(where)


def _chain_target(node: ast.If) -> str | None:
    """The name an if/elif chain keeps comparing against constants, if it is one."""
    names, depth, cur = [], 0, node
    while cur is not None:
        t = cur.test
        if isinstance(t, ast.Compare) and len(t.ops) == 1 and isinstance(t.ops[0], (ast.Eq, ast.In)) \
                and isinstance(t.left, (ast.Name, ast.Attribute)):
            names.append(ast.unparse(t.left))
            depth += 1
        else:
            return None
        cur = cur.orelse[0] if len(cur.orelse) == 1 and isinstance(cur.orelse[0], ast.If) else None
    return names[0] if depth >= 3 and len(set(names)) == 1 else None


COUNTS, WHERE = _measure(PKG)
COUNTS_T, WHERE_T = _measure(TESTS)


def _ratchet(rule: str, now: int, base: int, sample: str, where: str) -> None:
    if now > base:
        pytest.fail(f"{where} {rule}: {base} -> {now}. A new off-diagonal element of the FORM "
                    f"matrix (CODE_ORTHO_STANDARD.md). First sites: {sample}")
    if now < base and rule not in AT_TARGET:
        pytest.fail(f"{where} {rule}: {base} -> {now}. Good - now lower the base to {now} in this "
                    f"same commit. A base left above reality is an allowance that never expires.")


@pytest.mark.parametrize("rule", sorted(BASE))
def test_form_ratchet(rule: str) -> None:
    _ratchet(rule, COUNTS.get(rule, 0), BASE[rule], " | ".join(WHERE.get(rule, [])[:8]), "gfso/")


@pytest.mark.parametrize("rule", sorted(BASE_TESTS))
def test_form_ratchet_tests(rule: str) -> None:
    """The second root (run sheet 4.3): the suite is the code an outside engineer reads first."""
    _ratchet(rule, COUNTS_T.get(rule, 0), BASE_TESTS[rule],
             " | ".join(WHERE_T.get(rule, [])[:8]), "tests/")
