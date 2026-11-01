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
    if bad := form(doc):
        raise ValueError(f"the {FORMAT} file is malformed: " + "; ".join(bad))
    fit, inputs = doc.get("fit", {}), doc.get("inputs", {})
    spec = _lower(doc.get("plan", {}), inputs)
    marks = {p["id"]: p for p in fit.get("parts", ())}
    for s in spec.get("subtasks", ()):
        s.update({k: marks[s["id"]][k] for k in _FIT if k in marks.get(s["id"], {})})
    spec.update({f"whole_{k}": fit[f"whole_{k}"] for k in _FIT if f"whole_{k}" in fit})
    return {"goal": doc.get("goal", ""), "spec": spec, "review": doc.get("review", {}),
            "notes": doc.get("notes", []), "executor": fit.get("executor", "")}


def _named(rows, where, *keys) -> list[str]:
    """Each row of `rows` that lacks one of `keys`, said by its place in the file."""
    return [f"{where}[{i}].{k}: missing" for i, r in enumerate(rows or ()) for k in keys if not r.get(k)]


def _known(v, domain, where, what) -> list[str]:
    """`v`, where given, names one of `domain` — else said with what the file does have."""
    return [f"{where}: {v!r} is no {what} (have: {', '.join(map(str, domain)) or 'none'})"] if (
        v is not None and v not in domain) else []


_SECTIONS = ("format", "goal", "plan", "fit", "review", "notes", "inputs")
#: what the build reads of [plan] (`build_graph_live`) and of [fit] (`parse`)
_PLAN = ("name", "root_criteria", "subtasks", "mappings", "deps", "accepted_risks", "denial", "scope")
_FIT_KEYS = ("executor", "parts", *(f"whole_{k}" for k in _FIT))
#: what the build reads of each row below them — a field it does not read is a slip, built silently without this
_ROWS = {"part": ("id", "name", "description", "criteria", "writes", "runs"),
         "criterion": ("name", "description", "check", "depends_on"),
         "probe": ("behaviour", "command", "expect", "exact", "inputs"),
         "dep": ("from", "to", "glue", "reads"), "mapping": ("criterion", "child_id"), "scope": ("item", "why_out"),
         "risk": ("item", "predictability", "justification", "invalidation_condition", "invalidation", "p", "impact",
                  "component", "denial"),
         "fit part": ("id", *_FIT)}


def _slip(where: str, kind: str, row) -> list[str]:
    """Each field of one `kind` row at `where` the build does not read, said by its place."""
    return [f"{where}.{k}: no field of a {kind} (have: {', '.join(_ROWS[kind])})"
            for k in (row if isinstance(row, dict) else ()) if k not in _ROWS[kind]]


def _slips(where: str, kind: str, rows) -> list[str]:
    """`_slip` over a list of rows at `where`, each by its index."""
    return [x for i, r in enumerate(rows or ()) for x in _slip(f"{where}[{i}]", kind, r)]


def _unread(doc: dict) -> list[str]:
    """Every section, table field and row field of a plan file the build does not read — a misspelled `[fits]`,
    `[[plan.mapping]]` or `expcet` was dropped silently, a check built expecting nothing — and an `exact` that is no
    true/false (`exact = "true"` built a check no system runs)."""
    plan, fit = doc.get("plan"), doc.get("fit")
    out = [f"{k}: no section of a {FORMAT} file (have: {', '.join(_SECTIONS)})" for k in doc if k not in _SECTIONS]
    for where, table, known in (("plan", plan, _PLAN), ("fit", fit, _FIT_KEYS)):
        out += [f"{where}.{k}: no field of [{where}] (have: {', '.join(known)})"
                for k in (table if isinstance(table, dict) else ()) if k not in known]
    out += _slips("fit.parts", "fit part", fit.get("parts") if isinstance(fit, dict) else ())
    if not isinstance(plan, dict):
        return out
    out += _slips("plan.subtasks", "part", plan.get("subtasks"))
    crits = [(f"plan.root_criteria[{j}]", c) for j, c in enumerate(plan.get("root_criteria") or ())] + [
        (f"plan.subtasks[{i}].criteria[{j}]", c) for i, s in enumerate(plan.get("subtasks") or ())
        for j, c in enumerate(s.get("criteria") or ())]
    for where, c in crits:
        out += _slip(where, "criterion", c)
        out += _slips(f"{where}.check", "probe", c.get("check"))
        out += [f"{where}.check[{n}].exact: {q['exact']!r} is no true/false" for n, q in enumerate(c.get("check") or ())
                if isinstance(q, dict) and "exact" in q and not isinstance(q["exact"], bool)]
    for name, kind in (("deps", "dep"), ("mappings", "mapping"), ("scope", "scope"), ("accepted_risks", "risk")):
        out += _slips(f"plan.{name}", kind, plan.get(name))
    return out


def form(doc: dict) -> list[str]:
    """What is wrong with the SHAPE of a plan file, each as `<field>: <problem>` — a person editing it by hand learns it
    here, not when the build drops a mapping onto a part that is not there or dies on a missing key. Names only what the
    build would lose or fail on; whether the plan is any good is the review's."""
    plan, inputs, out = doc.get("plan"), doc.get("inputs", {}), []
    out += _unread(doc)
    if not str(doc.get("goal") or "").strip():
        out.append("goal: missing or empty — the plan answers a goal")
    if not isinstance(plan, dict):
        return out + ["plan: missing — the [plan] table holds the criteria and the split"]
    parts = plan.get("subtasks") or []
    ids = [s.get("id") for s in parts]
    roots = [c.get("name") for c in plan.get("root_criteria") or ()]
    if not roots:
        out.append("plan.root_criteria: none — a goal with no criterion cannot fail")

    named, known = (lambda *a: out.extend(_named(*a))), (lambda *a: out.extend(_known(*a)))

    named(plan.get("root_criteria"), "plan.root_criteria", "name")
    named(parts, "plan.subtasks", "id")
    named(plan.get("scope"), "plan.scope", "item")
    twice = lambda xs: sorted({x for x in xs if x and xs.count(x) > 1}, key=str)     # noqa: E731
    out += [f"plan.subtasks: id {i!r} appears twice" for i in twice(ids)]
    # …a mapping names its criterion: two of one name are one criterion to the build, the other's checks unread
    out += [f"plan.root_criteria: name {n!r} appears twice" for n in twice(roots)]
    for i, s in enumerate(parts):
        named(s.get("criteria"), f"plan.subtasks[{i}].criteria", "name")
        out += [f"plan.subtasks[{i}].criteria: name {n!r} appears twice"
                for n in twice([c.get("name") for c in s.get("criteria") or ()])]
        for j, c in enumerate(s.get("criteria") or ()):
            known(c.get("depends_on"), ids, f"plan.subtasks[{i}].criteria[{j}].depends_on", "part")
    named(plan.get("mappings"), "plan.mappings", "criterion", "child_id")
    named(plan.get("deps"), "plan.deps", "from", "to")
    for i, m in enumerate(plan.get("mappings") or ()):
        known(m.get("criterion"), roots, f"plan.mappings[{i}].criterion", "root criterion")
        known(m.get("child_id"), ids, f"plan.mappings[{i}].child_id", "part")
    for i, d in enumerate(plan.get("deps") or ()):
        known(d.get("from"), ids, f"plan.deps[{i}].from", "part")
        known(d.get("to"), ids, f"plan.deps[{i}].to", "part")
    for i, m in enumerate(doc.get("fit", {}).get("parts") or ()):
        known(m.get("id"), ids, f"fit.parts[{i}].id", "part")
    for c in _criteria(plan):
        for k, p in enumerate(c.get("check") or ()):
            for name, h in (p.get("inputs") or {}).items() if isinstance(p.get("inputs"), dict) else ():
                if h not in inputs:
                    out.append(f"check {c.get('name')!r}[{k}].inputs.{name}: {h!r} has no file under [inputs]")
    return out


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
