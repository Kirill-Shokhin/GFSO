"""The COUPLING ratchet — four kinds of edge, one guard, numbers that may not grow.

`tests/test_layering.py` guards ONE kind of edge: the import. Three other kinds carry as much
coupling and are invisible to it, which is why the package has 55 private reach-ins, 6 monkey
patches, 72 duck-typed attribute names and a path-built dependency from L2 into the binding layer
that the existing binding test was written to forbid.

Four kinds, one guard:
  I   import              — already covered by test_layering.py; not repeated here
  II  path to a foreign area's files  — `Path(__file__).parent / "mcp" / "prompts"`
  III shared vocabulary   — a literal or dict key that two modules must agree on
  IV  private reach       — `foo._bar` on a foreign object; assignment of a private attr onto one;
                            `getattr`/`hasattr` with a literal name

The guard is an ALLOWLIST that shrinks. Every entry is a known off-diagonal element with a home
block; the test fails if an entry disappears from the code (stale allowance) OR if a new edge
appears that is not allowed. Both directions matter: a shrinking list with no ratchet is decoration.
"""
from __future__ import annotations

import ast
from pathlib import Path

import pytest

import os
PKG = Path(os.environ.get("GFSO_REPO", Path(__file__).resolve().parents[1])) / "gfso"

AREA_DIRS = {"mcp", "core", "engine", "adapters", "decompose", "critic", "api", "web", "examples"}

# ── Kind IV: private reach-ins across an object boundary ────────────────────────────────────────
# Every entry is (module, attr). Remove an entry when its block lands; the test fails if an entry
# is still listed once the code no longer produces it, so the list cannot rot into permission.
ALLOWED_PRIVATE: set[tuple[str, str]] = {
    # block 1 removes all of these: Graph becomes a complete facade
    ("gfso.core.graph.metrics", "_storage"), ("gfso.core.graph.mutations", "_storage"),
    ("gfso.engine.loop", "_storage"), ("gfso.engine.validation", "_storage"),
    ("gfso.engine", "_storage"), ("gfso.critic.runner", "_storage"),
    ("gfso.runtime", "_storage"), ("gfso.api.server", "_storage"),
    ("gfso.critic.runner", "_graph"), ("gfso.delegate", "_graph"),
    ("gfso.runtime", "_graph"), ("gfso.tools_llm", "_graph"), ("gfso.api.server", "_graph"),
    # block 1: EventBus gains an unsubscribe
    ("gfso.api.server", "_events"), ("gfso.api.server", "_on_transition"),
    ("gfso.api.server", "_on_reject"), ("gfso.api.server", "_on_info"),
    ("gfso.engine", "_on_transition"), ("gfso.engine", "_on_reject"),
    # block 1: Engine gains quiesce()
    ("gfso.decompose", "_dispatch_quiesce"), ("gfso.decompose.build", "_dispatch_quiesce"),
    ("gfso.decompose.build", "_recompute_checks"),
    # block 1: the gate publishes a query surface
    ("gfso.critic.runner", "_llm"), ("gfso.api.server", "_llm"),
    # block 6: sqlite's own codecs, inside its own module (benign; kept visible on purpose)
    ("gfso.adapters.storage.sqlite", "_accepted_risks_to_json"),
    ("gfso.adapters.storage.sqlite", "_accepted_risks_from_json"),
    # binding wiring that has no better home yet
    ("gfso.api.server", "_on_create"), ("gfso.api.server", "_exit"),
    ("gfso.runtime", "_NAME_RE"),
    # Added by the door-fixing stream on 2026-08-20/21 and recorded here rather than quietly
    # tolerated: each is a channel the dispatcher opened into the engine because the engine has no
    # public surface for it. S8 removes them by publishing that surface; until then the ratchet
    # holds the count so a ninth cannot arrive unnoticed.
    ("gfso.delegate", "_roster"),                  # S8: who is registered, published downward
    ("gfso.delegate", "_dispatch_wake"),           # S8: the quiesce-end poke
    ("gfso.delegate", "_validation_parked"),       # S8: nodes automatic validation gave up on
}

# Duck-typed PRIVATE names — `getattr(obj, "_x", …)`. Same edge, different syntax, so it needs its
# own list: the attribute walker cannot see it.
ALLOWED_DUCK_PRIVATE: set[tuple[str, str]] = {
    ("gfso.decompose", "_dispatch_quiesce"), ("gfso.decompose", "_dispatch_wake"),
    ("gfso.decompose.build", "_dispatch_quiesce"), ("gfso.decompose.build", "_dispatch_wake"),
    ("gfso.delegate", "_dispatch_quiesce"), ("gfso.delegate", "_project_name"),
    ("gfso.delegate", "_owner_live"), ("gfso.runtime", "_on_create"),
    ("gfso.critic.runner", "_model"), ("gfso.critic.runner", "_critique_log_path"),
    ("gfso.tools_llm", "_model"),
    ("gfso.adapters.llm.headless", "_est_chars"),
    # …and the duck-typed spelling of the same three channels (see the note above; S8 owns them).
    ("gfso.engine", "_validation_parked"), ("gfso.examples.autonomous_org", "_validation_parked"),
}

# ── Kind IV bis: a private attribute WRITTEN onto a foreign object ──────────────────────────────
ALLOWED_PATCH: set[tuple[str, str]] = {
    ("gfso.api.server", "_on_create"), ("gfso.runtime", "_NAME_RE"),
    ("gfso.decompose", "_dispatch_quiesce"), ("gfso.decompose.build", "_dispatch_quiesce"),
}

# ── Kind IV ter: duck-typed protocol (getattr/hasattr with a literal name) ──────────────────────
# Fields DECLARED on a dataclass must never be read through getattr — that hides schema drift.
DECLARED_TASK_FIELDS = {"iteration", "reopens", "revisions", "state_entered_at", "verified",
                        "spec", "deadline", "assignee", "done_reason", "max_iterations"}

# ── Kind II: a module may only build paths inside its OWN area ──────────────────────────────────
ALLOWED_PATH: set[tuple[str, str]] = {
    ("gfso.delegate", "mcp"), ("gfso.tools_llm", "mcp"),      # block 4 moves the prompts
    ("gfso.api.server", "web"), # doctor is binding: allowed by design
}

# ── Kind III: literals two or more modules must agree on ────────────────────────────────────────
# After block 0 these live in core.vocabulary / product.config and nowhere else.
OWNED_ELSEWHERE = {"PASS", "FAIL", "sonnet", "haiku", "127.0.0.1", "gfso.db", "agents.json",
                   "default", "root", "agent"}
# The owners of shared words. `gfso.core.types.enums` exists today; `gfso.config` is the ONE module
# S4 creates (top-level, in the manner of runtime.py / serverctl.py / driver.py — no rename, no new
# package). The earlier spelling here named `gfso.core.vocabulary` and `gfso.product.config`, which
# belong to a renamed layout the plan dropped: the arbiter was pointing at modules that do not and
# will not exist, so the literal rule could never reach zero.
VOCAB_MODULES = {"gfso.core.types.enums", "gfso.config"}


def _modules():
    for f in sorted(PKG.rglob("*.py")):
        if "__pycache__" in f.parts:
            continue
        parts = list(f.relative_to(PKG.parent).with_suffix("").parts)
        if parts[-1] == "__init__":
            parts = parts[:-1]
        yield ".".join(parts), f


def _tree(f: Path):
    return ast.parse(f.read_text(encoding="utf-8-sig"))


def _root_name(node) -> str:
    while isinstance(node, (ast.Attribute, ast.Subscript, ast.Call)):
        node = node.value if not isinstance(node, ast.Call) else node.func
    return node.id if isinstance(node, ast.Name) else ""


# The numbers as of the last measurement (2026-08-20, loc 12 475). ONE edit per step, in that
# step's own commit — the ratchet is EQUALITY, so a base left above reality is an allowance that
# never expires, exactly like a stale allowlist entry.
# Measured 2026-08-20 20:5x on a tree the E3 stream was editing live — these WILL differ by the
# time the plan runs. S1 re-snaps them: run the file once, read "X -> Y" and set Y.
BASE_COUNT = {"private_reach": 2,   # ← `issuer_of` published (2026-08-22)
              "monkey_patch": 0, "foreign_path": 0,
              "duck_private": 0,
              # 2 (2026-09-03, S7): a `getattr` with a default over a DECLARED field says the
              # field might be absent — a false statement about the type, and the reason this
              # rule exists. The generation triple (iteration/reopens/revisions) was read that
              # way in six places, each with its own defaults; `generation_of_task` owns it.
              # The two left guard a task that really can be None, and say so as a None check.
              "getattr_declared": 2,
              # The SIZE of each allowlist is itself a number. Without it a step that publishes an
              # operation and deletes 21 reach-ins moves nothing the ratchet can see: every one of
              # those sites is ALLOWED, so `found` stays empty before and after (measured — the
              # first version of this file made the whole weeding step invisible to §5.3).
              # HARD numbers, not len(...) of the list itself. Computed from the list, the base
              # moved with every deletion and compared a thing to itself: deleting two entries left
              # the test green (measured). That is the third time in one session the same defect —
              # a guard whose own bookkeeping makes it blind — appeared inside these instruments.
              "allowed_private": 32,
              "allowed_duck": 14,
              "allowed_path": 3,
              "allowed_patch": 4}


def _stale(kind: str, stale: set) -> None:
    """An allowance for something that no longer occurs is an indulgence that never expires."""
    assert not stale, (f"{kind}: the allowlist is stale — these no longer occur in the code, "
                       f"delete the entries so the guard keeps ratcheting: {sorted(stale)}")


def test_allowlists_have_not_grown():
    """The allowlists only SHRINK. Their size is the progress record of the weeding steps."""
    for name, current in (("allowed_private", len(ALLOWED_PRIVATE)),
                          ("allowed_duck", len(ALLOWED_DUCK_PRIVATE)),
                          ("allowed_path", len(ALLOWED_PATH)),
                          ("allowed_patch", len(ALLOWED_PATCH))):
        if current != BASE_COUNT[name]:
            pytest.fail(f"{name}: {BASE_COUNT[name]} -> {current} · "
                        + ("lower BASE_COUNT in this commit" if current < BASE_COUNT[name]
                           else "an allowlist may not grow — publish the operation instead"))
# `sonnet` on the MCP door is not a stray literal: `mcp/server.py` declares it as the default IN
# THE SCHEMA THE AGENT SEES, and the tiers of the doors are deliberately different (CRITIQUE К-7).
# Its floor is therefore 1, NOT 0 and not 3: this rule counts MODULES (one `break` per file), and
# all three signatures live in `mcp/server.py` — one module. "Floor 3" counted signatures with a
# rule that counts modules.
BASE_LITERAL = {# 2 and 1: V's two values are `Verdict`, a StrEnum whose members ARE those byte
                # strings — so records, reports, signals and the JSON schema the validator answers
                # in all carry the same word without spelling it. What is left: the enum itself,
                # and one example that types the PASS a person types.
                "PASS": 2, "FAIL": 1,
                # 0: the default model tier is `gfso.config.MODEL_DEFAULT` (a VOCAB module, so the
                # owner itself does not count) and every door — MCP signature, decomposer, roster,
                # runtime factory, the examples — asks it. Nine spellings were nine places to
                # answer differently about which model this product runs on by default.
                "sonnet": 0,
                # 0: the tier an engine built from the environment runs on is
                # `gfso.config.engine_model()` — it was spelled in the factory that reads the
                # environment, which is the module S4 exists to empty (2026-08-22).
                "haiku": 0,
                # 1: the loopback address is `gfso.config.LOOPBACK` and every door asks it. One
                # server has one address, and six spellings were five chances to disagree.
                # 0: the loopback address is `gfso.config.LOOPBACK` (a VOCAB module, so the owner
                # itself does not count) and every door asks it.
                "127.0.0.1": 0,
                # 2: the default root id is `gfso.config.ROOT_ID`; what is left is the two examples
                # that name their own root in prose (the MCP door asked the owner instead of
                # spelling its own default).
                "root": 2,
                # 2, not 4: the roster and the database file are derived in `gfso.config` now, and
                # the two remaining spellings are that owner and the doctor line that reports it.
                "agents.json": 2, "gfso.db": 1,
                # 2: the single-project `/api/projects` answer asked `gfso.config.DEFAULT_PROJECT`
                # instead of spelling the name a third time (2026-09-02)
                "default": 2,
                # 1: the agent's standing identity is `gfso.config.agent_id()`; what is left is the
                # example that names its own actor in prose.
                "agent": 1}


def test_no_new_private_reach():
    """A private attribute of a FOREIGN object is a dependency the import graph cannot show."""
    found, stale = [], set(ALLOWED_PRIVATE)
    for mod, f in _modules():
        for n in ast.walk(_tree(f)):
            if not isinstance(n, ast.Attribute):
                continue
            a = n.attr
            if not (a.startswith("_") and not a.startswith("__")):
                continue
            root = _root_name(n)
            # `self._graph._storage` starts at self and still reaches into a FOREIGN object's
            # private at the second hop. Counting only the root missed every such chain — the
            # engine's own nine reaches into Graph among them.
            hops = ast.unparse(n).count("._")
            if root in ("self", "cls", "") and hops < 2:
                continue
            key = (mod, a)
            stale.discard(key)
            if key not in ALLOWED_PRIVATE:
                found.append(f"{f.name}:{n.lineno} {mod} reaches {a}")
    _stale("private_reach", stale)
    if len(found) != BASE_COUNT["private_reach"]:
        pytest.fail(f"private_reach: {BASE_COUNT['private_reach']} -> {len(found)} · "
                    + ("lower BASE_COUNT in this commit" if len(found) < BASE_COUNT["private_reach"]
                       else "new: " + " | ".join(found[:6])))


def test_no_new_monkey_patch():
    """Writing a private attribute onto someone else's object is an undeclared contract."""
    found, stale = [], set(ALLOWED_PATCH)
    for mod, f in _modules():
        for n in ast.walk(_tree(f)):
            if not isinstance(n, ast.Assign):
                continue
            for t in n.targets:
                if (isinstance(t, ast.Attribute) and t.attr.startswith("_")
                        and not t.attr.startswith("__") and _root_name(t) not in ("self", "cls", "")):
                    stale.discard((mod, t.attr))
                    if (mod, t.attr) not in ALLOWED_PATCH:
                        found.append(f"{f.name}:{n.lineno} {mod} writes {t.attr}")
    _stale("monkey_patch", stale)
    if len(found) != BASE_COUNT["monkey_patch"]:
        pytest.fail(f"monkey_patch: {BASE_COUNT['monkey_patch']} -> {len(found)} · "
                    + ("lower BASE_COUNT in this commit" if len(found) < BASE_COUNT["monkey_patch"]
                       else "new: " + " | ".join(found[:6])))


def test_declared_fields_are_not_read_through_getattr():
    """`getattr(task, "iteration", 0)` on a dataclass field hides drift and defeats the type."""
    found = []
    for mod, f in _modules():
        for n in ast.walk(_tree(f)):
            fn = n.func if isinstance(n, ast.Call) else None
            name = fn.id if isinstance(fn, ast.Name) else ""
            if name in ("getattr", "hasattr") and len(n.args) >= 2 \
                    and isinstance(n.args[1], ast.Constant) \
                    and n.args[1].value in DECLARED_TASK_FIELDS:
                found.append(f"{f.name}:{n.lineno} {mod} getattr({n.args[1].value!r})")
    if len(found) != BASE_COUNT["getattr_declared"]:
        pytest.fail(f"getattr_declared: {BASE_COUNT['getattr_declared']} -> {len(found)} · "
                    + ("lower BASE_COUNT in this commit" if len(found) < BASE_COUNT["getattr_declared"]
                       else "new: " + " | ".join(found[:6])))

def test_no_path_into_a_foreign_area():
    """`Path(__file__).parent / "mcp" / "prompts"` is an import the layer gate cannot see."""
    found, stale = [], set(ALLOWED_PATH)
    for mod, f in _modules():
        for n in ast.walk(_tree(f)):
            if not (isinstance(n, ast.BinOp) and isinstance(n.op, ast.Div)):
                continue
            segs, cur = [], n
            while isinstance(cur, ast.BinOp) and isinstance(cur.op, ast.Div):
                if isinstance(cur.right, ast.Constant) and isinstance(cur.right.value, str):
                    segs.append(cur.right.value)
                cur = cur.left
            for hit in {s for s in segs} & AREA_DIRS:
                if hit in mod.split("."):
                    continue                       # its own area — fine
                key = (mod, hit)
                stale.discard(key)
                if key not in ALLOWED_PATH:
                    found.append(f"{f.name}:{n.lineno} {mod} -> {hit}/")
    _stale("foreign_path", stale)
    if len(found) != BASE_COUNT["foreign_path"]:
        pytest.fail(f"foreign_path: {BASE_COUNT['foreign_path']} -> {len(found)} · "
                    + ("lower BASE_COUNT in this commit" if len(found) < BASE_COUNT["foreign_path"]
                       else "new: " + " | ".join(found[:6])))


@pytest.mark.parametrize("literal", sorted(OWNED_ELSEWHERE))
def test_shared_literal_has_one_owner(literal):
    """A literal two modules must agree on belongs to the vocabulary, not to both of them."""
    owners = []
    for mod, f in _modules():
        if mod in VOCAB_MODULES:
            continue
        for n in ast.walk(_tree(f)):
            if isinstance(n, ast.Constant) and n.value == literal:
                owners.append(f"{f.name}:{n.lineno}")
                break
    base = BASE_LITERAL.get(literal, 1)
    if len(owners) != base:
        pytest.fail(f"{literal!r}: spelled in {base} modules -> {len(owners)}. "
                    + ("lower BASE_LITERAL in this commit" if len(owners) < base
                       else f"a new spelling: {owners}"))


def test_no_new_duck_typed_private():
    """`getattr(engine, "_dispatch_quiesce", 0)` is the same edge as `engine._dispatch_quiesce`,
    written so the attribute walker cannot see it. It gets its own ratchet."""
    found, stale = [], set(ALLOWED_DUCK_PRIVATE)
    for mod, f in _modules():
        for n in ast.walk(_tree(f)):
            fn = n.func if isinstance(n, ast.Call) else None
            name = fn.id if isinstance(fn, ast.Name) else ""
            if name not in ("getattr", "hasattr") or len(n.args) < 2:
                continue
            arg = n.args[1]
            # A DUNDER is not a private reach: `getattr(fn, "__name__", "?")` reads the language's
            # own protocol, not a neighbour's internals. The private-attribute rule above already
            # excludes them (`not a.startswith("__")`); this one did not, so one notion had two
            # spellings — exactly the defect this file exists to catch, inside this file.
            if not (isinstance(arg, ast.Constant) and isinstance(arg.value, str)
                    and arg.value.startswith("_") and not arg.value.startswith("__")):
                continue
            key = (mod, arg.value)
            stale.discard(key)
            if key not in ALLOWED_DUCK_PRIVATE:
                found.append(f"{f.name}:{n.lineno} {mod} duck-types {arg.value}")
    _stale("duck_private", stale)
    if len(found) != BASE_COUNT["duck_private"]:
        pytest.fail(f"duck_private: {BASE_COUNT['duck_private']} -> {len(found)} · "
                    + ("lower BASE_COUNT in this commit" if len(found) < BASE_COUNT["duck_private"]
                       else "new: " + " | ".join(found[:6])))
