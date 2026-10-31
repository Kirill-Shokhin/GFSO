"""The plan as an artifact of its own — a `.gfso` text the customer reads whole before any project exists.

What the file holds is the canon's authority-free plane {T, D, Dep, V} with the split's register (§2.8, §9.2) and the
goal it answers; nothing in it names who executes (Del enters at the go, §10.4). Three parts sit apart from the plan
because they are not the plan: the executor-relative fit marks (κ is a property of the actor, §3.7), the Level-2
review the system ran over it, and the customer's notes with their answers. The checks' input files are machinery:
each is written once under its content hash at the end, the plan naming it by that hash.

TOML, because a plan is configuration handed between parties — stdlib reads it (`tomllib`), every editor shows it, and
the emitter below is the only writer the format needs. `parse(render(x)) == x` is the format's whole contract.
"""
from __future__ import annotations

import hashlib
import json
import re
import tomllib

FORMAT = "gfso-plan/1"
_FIT = ("volume", "fits_one_session")
_BARE = re.compile(r"^[A-Za-z0-9_-]+$")


def render(goal: str, spec: dict, review: dict | None = None, notes: list | None = None,
           executor: str = "") -> str:
    """The plan file for `spec` (the `extract_spec` shape) answering `goal`."""
    plan, inputs = _hoist(spec)
    fit = {"executor": executor, **{f"whole_{k}": plan.pop(f"whole_{k}") for k in _FIT if f"whole_{k}" in plan},
           "parts": [{"id": s["id"], **{k: s.pop(k) for k in _FIT if k in s}} for s in plan.get("subtasks", ())]}
    doc = {"format": FORMAT, "goal": goal, "plan": plan, "fit": fit, "review": review or {},
           "notes": list(notes or ()), "inputs": inputs}
    return _emit(doc)


def parse(text: str) -> dict:
    """{goal, spec, review, notes, executor} back from a plan file — the spec exactly as `render` was given it."""
    doc = tomllib.loads(text)
    if doc.get("format") != FORMAT:
        raise ValueError(f"not a {FORMAT} file (format = {doc.get('format')!r})")
    fit, inputs = doc.get("fit", {}), doc.get("inputs", {})
    spec = _lower(doc.get("plan", {}), inputs)
    marks = {p["id"]: p for p in fit.get("parts", ())}
    for s in spec.get("subtasks", ()):
        s.update({k: marks[s["id"]][k] for k in _FIT if k in marks.get(s["id"], {})})
    spec.update({f"whole_{k}": fit[f"whole_{k}"] for k in _FIT if f"whole_{k}" in fit})
    return {"goal": doc.get("goal", ""), "spec": spec, "review": doc.get("review", {}),
            "notes": doc.get("notes", []), "executor": fit.get("executor", "")}


def _hoist(spec: dict) -> tuple[dict, dict]:
    """A deep copy of `spec` whose checks name their input files by content hash, and the files by that hash."""
    plan, inputs = json.loads(json.dumps(spec)), {}
    for c in _criteria(plan):
        for p in c.get("check") or ():
            if isinstance(p.get("inputs"), dict):
                for name, body in p["inputs"].items():
                    h = "sha256-" + hashlib.sha256(json.dumps(body).encode()).hexdigest()[:16]
                    inputs[h] = body
                    p["inputs"][name] = h
    return plan, inputs


def _lower(plan: dict, inputs: dict) -> dict:
    spec = json.loads(json.dumps(plan))
    for c in _criteria(spec):
        for p in c.get("check") or ():
            if isinstance(p.get("inputs"), dict):
                p["inputs"] = {n: inputs[h] for n, h in p["inputs"].items()}
    return spec


def _criteria(spec: dict):
    yield from spec.get("root_criteria") or ()
    for s in spec.get("subtasks") or ():
        yield from s.get("criteria") or ()


# --- the writer: TOML for nested tables, arrays of tables, strings, numbers, booleans (no null: a None is left out) ---

def _emit(doc: dict) -> str:
    out: list[str] = []
    _table(doc, [], out)
    return "\n".join(out).lstrip("\n") + "\n"


def _table(d: dict, path: list[str], out: list[str]) -> None:
    subs = []
    for k, v in d.items():
        if v is None:
            continue
        if isinstance(v, dict) or (isinstance(v, list) and v and all(isinstance(x, dict) for x in v)):
            subs.append((k, v))
        else:
            out.append(f"{_key(k)} = {_value(v)}")
    for k, v in subs:
        p = path + [_key(k)]
        if isinstance(v, dict):
            out.append(f"\n[{'.'.join(p)}]")
            _table(v, p, out)
        else:
            for item in v:
                out.append(f"\n[[{'.'.join(p)}]]")
                _table(item, p, out)


def _key(k) -> str:
    return k if _BARE.match(str(k)) else json.dumps(str(k), ensure_ascii=False)


def _value(v) -> str:
    if isinstance(v, bool):
        return "true" if v else "false"
    if isinstance(v, (int, float)):
        return json.dumps(v)
    if isinstance(v, str):
        return _string(v)
    if isinstance(v, list):
        if any(isinstance(x, dict) for x in v):      # a list mixing tables and values has no TOML table form
            return "[" + ", ".join(_inline(x) for x in v) + "]"
        return "[" + ", ".join(_value(x) for x in v) + "]"
    raise TypeError(f"no TOML form for {type(v).__name__}")


def _inline(v) -> str:
    if isinstance(v, dict):
        return "{" + ", ".join(f"{_key(k)} = {_inline(x)}" for k, x in v.items() if x is not None) + "}"
    return _value(v)


def _string(s: str) -> str:
    """A multi-line literal where the text reads as written; else a basic string (JSON's escapes are TOML's)."""
    if "\n" in s and "'''" not in s and not s.endswith("'") \
            and not any(ord(ch) < 32 and ch not in "\n\t" or ord(ch) == 127 for ch in s):
        return "'''\n" + s + "'''"
    return json.dumps(s, ensure_ascii=False).replace("\x7f", "\\u007f")   # JSON leaves DEL bare, TOML refuses it
