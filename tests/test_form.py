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
import builtins
import io
import re
import symtable
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
    "G1_name_never_bound": 0,
    "G2_unreachable_after_jump": 0,
    # 0: every package and module says what it owns — the first thing a stranger reads
    "A1_module_without_docstring": 0,
    # 188: `llm_factory` moved to the import section — it was imported inside two functions
    # and USED inside a third, which is how the evidence instrument died with a NameError
    # 187: `contextvars` is imported where every other stdlib module in this file is — it was read
    #      inside the app factory, one line above its only use (2026-09-02)
    # 16: every import whose timing is not load-bearing now sits in its module's import block; the
    #     sixteen that stay say why on the line above (optional `mcp`/`uvicorn` behind their own
    #     except, the zero-dependency core cut, and the two real cycles) (2026-09-02)
    # 16 IS THE FLOOR, not a debt (2026-09-03, checked site by site). S18 wrote "→0" before the
    # constraints were known: an optional SDK (`mcp`, `uvicorn`) hoisted would break the very
    # commands that must run WITHOUT it — `gfso doctor` and `gfso serve` on an install missing
    # it; `serverctl` hoisted into `tools.py` puts the transport inside the zero-dependency
    # core cut; and three are real import cycles. Every one of the sixteen carries its reason
    # on the line above it, which is the actual rule — a late import is a decision or a defect,
    # and the difference is whether it is written down.
    # 17 (2026-09-03): splitting the project verbs gave the destructive one its own
    # mounting, and the optional-SDK import is a per-function constraint — the same
    # reason, spelled where it binds. A floor that RISES with a legitimate split is the
    # instrument working, not drifting.
    "A2_import_inside_a_function": 17,
    "A3_module_imported_two_ways": 1,   # this test OWNS the number; the standalone tool counts
                                        # `from X import y` spellings too and says 16 — one rule, one owner
    # 181: `/api/projects` gained one — the filter it now takes needs saying (2026-09-02)
    # 116: the ports now CARRY the contracts (22 written), and an implementation of an
    # abstract method inherits the one it implements instead of repeating it 50 times
    # 33: the HTTP door's route handlers now say what they ANSWER — an undocumented handler is an
    # empty OpenAPI description, and a person driving this port with curl recovered the verbs and
    # their parameters from error strings instead (2026-09-02)
    "A4_public_function_without_contract": 0,
    "B1_attribute_born_outside_init": 3,   # ← headless declares `last_tool_calls` (S5, 2026-08-22)
    # 52 (2026-09-03): S7 removed the defensive reads of DECLARED fields, and B3 fell with it —
    # the two rules were counting the same habit from two angles. What remains is the legitimate
    # duck-typing of PORTS, which is why this number's floor was never zero.
    # 53: `_why` asks an exception whether it HAS `.exceptions` — a group does, a plain
    # one does not, and a default over an attribute that genuinely may be absent is the
    # legitimate case this number's floor exists for.
    "B3_declared_field_read_defensively": 53,   # ← `authorized_validators`, `_roster` declared (2026-08-22)
    "C2_chain_dispatch_over_constants": 1,
    "D1_swallowed_failure": 1,   # only the UNEXPLAINED ones: every other swallow now says what
                                 # it gives up, or logs instead of losing it (2026-09-02)
    "D1_bare_except": 0,
    "E2_hand_written_log_tag": 1,
    # 9, not 14: a literal single-quoted because its own body holds a double quote is not a
    # style choice at all (`_forced`) — the rule stopped counting the language, 2026-09-02
    "F_single_quoted_literals": 9,
    # 10: the biggest is 48 statements now — it was 272 when the ratchet was installed
    # 0 (2026-09-03): the last three were each within four statements of the ceiling, and each one
    # was hiding a second owner rather than a long body. `_frontier` asked three questions at once —
    # does this node's PLAN gate its children (§13.4), is it waiting on work already in flight, what
    # step does it offer — and the first two are now their own methods. `_dispatch_steps` wrote the
    # rule "say a refusal once, keyed by what it is about" out by hand five times, and seven sites
    # across `delegate.py` did; `_say_once` owns it. `signal` sent the signal AND authored the whole
    # reply; what an accepted signal owes its sender is a different question from how one is sent.
    "F_function_over_size_limit": 0,
    # C5 — the hardcode rule, and the number S4 owns. Floor is 1, NOT 0: `GFSO_L2_GATE` is read at
    # its point of enforcement DELIBERATELY (hard constraint #7 of the run sheet) — it is the switch
    # of a measured mechanism, not a setting.
    # 51 after the four path derivations moved to their owner (`gfso.config`); it read 56, and
    # 56, not the 47 this plan predicted — and the difference is the point. CM-2 unaliased
    # `import os as _os`, and eight `_os.environ` reads that this rule could not see became
    # visible. The alias was hiding them FROM THE INSTRUMENT: S4 owns 56 sites, not 47.
    # 21: choosing the project is `config.select_project` now — two doors were writing the
    # variable by hand, which is how a setting acquires a second owner and then a second meaning
    # 5 (2026-09-03): the environment a CHILD gets is one question, and it was answered in four
    # places — `serve`, the MCP door, the bridge's spawn, the model runner. `gfso.config` owns
    # it now (`install_serve_env` / `install_mcp_env` / `install_spawned_server_env` /
    # `spawned_server_popen_env` / `subprocess_env`). What is left is the declared floor plus
    # four DIAGNOSTIC reads in `doctor`, whose job is to report what the environment says —
    # including `APPDATA`, which is the OS's variable and not this product's configuration.
    "C5_env_read_outside_config": 5,     # floor 1: GFSO_L2_GATE at its enforcement point
                                         # (S4, 2026-08-22: provider/billing/storage/llm/model,
                                         #  the runtime panel and the roster path have owners)
}

# The second root. `tests/` is 47 % of the package's python and the suite is the first thing an
# outside engineer reads, so it is in scope FOR FORM (the run sheet's own decision on `tests/`) — but only for the rules that
# mean the same thing there. Deliberately NOT applied to tests: C2 (a chain in a test is a table
# nobody reads twice), F_size (a scenario test is legitimately long), A4 (the test NAME is its
# contract in this suite), E2 (no logging). T1/T2 are what step S19 actually removes.
BASE_TESTS = {
    "G1_name_never_bound": 0,
    "G2_unreachable_after_jump": 0,
    "A1_module_without_docstring": 0,
    # 4: every test import whose timing is not load-bearing now sits in its module's import
    #    block; the four that stay say why on the line (two self-imports, one behind a
    #    sys.path insert, one behind `pytest.importorskip`)
    # 245: the wave-18 tests hoisted theirs, and this file stopped importing inside its own rule
    "A2_import_inside_a_function": 4,
    "B1_attribute_born_outside_init": 0,
    "D1_swallowed_failure": 2,
    "F_single_quoted_literals": 3,
    # 1 — the floor: the ONE construction site is `tests/support.py`, which owns it (S19, 2026-09-02)
    "T1_engine_built_by_hand": 1,
    # 1 — the acceptance-embeddability suite keeps its own, deliberately: it plays a FOREIGN
    # host and must need nothing from this repository's test kit
    "T2_spec_helper_redefined": 1,
}

# Rules that are already at their target and must STAY there (a floor, not a ratchet step).
AT_TARGET = {"D1_bare_except", "G1_name_never_bound", "G2_unreachable_after_jump"}


def _modules(root: Path) -> list[tuple[str, Path]]:
    return [(".".join(p.relative_to(root.parent).with_suffix("").parts), p)
            for p in sorted(root.rglob("*.py")) if "__pycache__" not in p.parts]


def _stmts(node: ast.AST) -> int:
    """How much this function DOES — its docstring not counted among it.

    A docstring is an `ast.stmt`, so the size rule was charging a function for being documented: two
    functions sitting exactly at the ceiling could not be given one without tripping it, and an agent
    documenting the API door correctly refused to (2026-09-02). A rule that makes the codebase worse
    at the margin is measuring the wrong thing.
    """
    doc = 1 if ast.get_docstring(node) is not None else 0
    return sum(1 for n in ast.walk(node) if isinstance(n, ast.stmt)) - 1 - doc


def _measure(root: Path) -> tuple[dict[str, int], dict[str, list[str]]]:
    counts: dict[str, int] = defaultdict(int)
    where: dict[str, list[str]] = defaultdict(list)
    import_forms: dict[str, set[str]] = defaultdict(set)

    def hit(rule: str, addr: str) -> None:
        counts[rule] += 1
        where[rule].append(addr)

    #: Names DECLARED on a port with a contract written on the declaration — abstract or optional.
    #: An implementation of one of these is documented by the port it implements; the optional half
    #: matters as much as the abstract one, since that is where a default no-op states what a
    #: storage that does not override it gives up.
    _port_contracts = {fn.name
                       for _m, _p in _modules(root)
                       for cls in ast.walk(ast.parse(_p.read_text(encoding="utf-8-sig")))
                       if isinstance(cls, ast.ClassDef) and cls.name.endswith("Port")
                       for fn in cls.body
                       if isinstance(fn, (ast.FunctionDef, ast.AsyncFunctionDef))
                       and ast.get_docstring(fn)}

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

        # G1/G2 — THE RESIDUE OF A CUT. Splitting a monolith moves a block into a new function, and
        # two things survive the move silently: a name the block read from the old enclosing scope
        # (Python compiles it as a global load, so nothing complains until that branch runs — this is
        # how `/api/usage` answered 500 on every real server for a week while the suite stayed green),
        # and a statement stranded after the `return`/`continue` the block used to end on. Both are
        # invisible to every other instrument here, and both were live in this repository.
        for _fn_name, _free in _free_names(src):
            hit("G1_name_never_bound", f"{path.name}: {_fn_name}() -> {_free}")
        for _line, _after in _unreachable(tree):
            hit("G2_unreachable_after_jump", f"{path.name}:{_line} after {_after}")

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
            if not fn.name.startswith("_") and ast.get_docstring(fn) is None                     and fn.name not in _port_contracts:
                # …AND AN IMPLEMENTATION INHERITS THE CONTRACT IT IMPLEMENTS. The abstract method
                # carries what the operation promises; repeating it on every adapter is the
                # duplication this whole instrument exists to count, and it would have meant fifty
                # copies of two dozen sentences across the two storage adapters alone. What the rule
                # is about is a public function whose behaviour is stated NOWHERE (2026-09-02).
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
                    if _q[:3] not in _TRIPLES and _q[:1] == _SINGLE and not _forced(_q):
                        hit("F_single_quoted_literals", f"{path.name}:{tok.start[0]}")
                    continue
                if _FEND is not None and tok.type == _FEND:
                    _in_fstring = max(0, _in_fstring - 1)
                    continue
                if tok.type != tokenize.STRING or _in_fstring:
                    continue
                q = tok.string[len(re.match(r"^[A-Za-z]*", tok.string).group(0)):]
                if q[:3] not in _TRIPLES and q[:1] == _SINGLE and not _forced(q):
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


def _forced(quoted: str) -> bool:
    """Is this literal single-quoted because its BODY carries a double quote?

    Measured 2026-09-02: 32 of the 35 single-quoted literals in `tests/` are JSON payloads
    (`'{"verdict": "atomic"}'`). Rewriting them in double quotes would only add escaping, so a rule
    that counted them was measuring the LANGUAGE, not a divergence — the same error as the regex
    that counted apostrophes in English prose. The style rule is about the quote an author was FREE
    to choose.
    """
    return chr(34) in quoted[1:-1]


def _free_names(src: str) -> list[tuple[str, str]]:
    """Names a nested scope reads that nothing binds — locally, in an enclosing function, at module
    level, or in builtins. Python compiles such a read as a global load, so it raises only when its
    branch runs: exactly how a closure variable lost during an extraction stays invisible."""
    try:
        st = symtable.symtable(src, "m.py", "exec")
    except SyntaxError:
        return []
    # MODULE-LEVEL bindings only. Counting every import in the file — wherever it stood — is what
    # made the first version of this rule false-green: `tools_llm.validate_result` used
    # `llm_factory`, which two OTHER functions import locally, and the live call died with a raw
    # NameError on the HTTP door while this rule stayed at zero (found by a tester, 2026-09-02).
    # A function-level import binds inside THAT function, and the walk below already carries it.
    known = {sym.get_name() for sym in st.get_symbols()} | set(dir(builtins))
    # module globals symtable omits, plus `__class__` — the implicit cell a method gets from a
    # zero-argument `super()`, bound by the interpreter and by nothing in the source
    known |= {"__file__", "__name__", "__doc__", "__package__", "__class__"}
    out: list[tuple[str, str]] = []

    def walk(table, enclosing: set[str]) -> None:
        for child in table.get_children():
            bound = {sym.get_name() for sym in child.get_symbols()
                     if sym.is_assigned() or sym.is_parameter() or sym.is_imported()}
            scope = enclosing | bound
            out.extend((child.get_name(), sym.get_name()) for sym in child.get_symbols()
                       if sym.is_referenced() and sym.get_name() not in scope
                       and sym.get_name() not in known)
            walk(child, scope)

    walk(st, set())
    return out


def _unreachable(tree: ast.AST) -> list[tuple[int, str]]:
    """Statements stranded after a return/continue/break/raise in the same block."""
    jumps = (ast.Return, ast.Continue, ast.Break, ast.Raise)
    out: list[tuple[int, str]] = []
    for n in ast.walk(tree):
        for field in ("body", "orelse", "finalbody"):
            body = getattr(n, field, None)
            if not isinstance(body, list):
                continue
            for i, st in enumerate(body[:-1]):
                if isinstance(st, jumps):
                    out.append((body[i + 1].lineno, type(st).__name__))
                    break
    return out


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
