"""CLI driver — the headless graph-driving commands behind `gfso run`. Kept OUT of `cli.py` (the launcher):
`cli.py` wires the `run` subcommand, the low-level per-tool dispatch lives here.

It binds the SAME shared action surface as MCP (`gfso.tools.TOOLS`), so the CLI has full parity with MCP by
construction — add a tool and it appears here for free, no per-command upkeep. Each invocation runs one tool and prints JSON. When the one shared server is up the call goes THROUGH it
(`/api/run/<tool>`), so there is a single engine, a single writer and a single sequencer over the log — and the
write appears live in the UI. With no server up it opens the database directly, which is the same surface and
the only one available.

    gfso run                                   # list commands
    gfso run auto_decompose "<request>"        # build the graph
    gfso run next_step                          # the forcing-point: the next directive
    gfso run signal <task> ACCEPT human         # ACCEPT / DELIVER (result=...) / PASS / FAIL / ...
    gfso run list_holes | get_graph | get_task <id> | project <id>
    gfso run next_step project=<name>          # a named project (routed to the server's registry)
"""
from __future__ import annotations

import sys
import os
import json
import typing
import threading
import inspect
import textwrap
from pathlib import Path
import urllib.error
import urllib.request
from urllib.parse import quote

from gfso.runtime import build_engine_from_env
from gfso import tools as _T     # the verb surface: UI_LINK_VERBS / ui_link live there
from gfso.config import agent_id, narrate, select_project
from gfso import serverctl
from gfso import tools_llm as T  # the COMPLETE registry (structural + LLM verbs)


def _coerce(v: str):
    """A JSON literal ({…}/[…]/number/true) is parsed; `@file` reads one; anything else is a string.

    `@file.json` is the shape a person reaches for when a criteria list is longer than a shell line,
    and it was passed through as the literal string "@file.json" — which arrived inside the verb as
    a Python TypeError about string indices (measured on the human door 2026-08-21). Reading the file
    is what they meant; a missing one is refused in words rather than as a traceback."""
    if not isinstance(v, str):
        return v
    if v.startswith("@") and len(v) > 1:
        path = Path(v[1:])
        if not path.exists():
            raise ValueError(f"no such file: {path} (an argument starting with `@` reads a file — "
                             f"`@criteria.json` passes what that file holds)")
        text = path.read_text(encoding="utf-8").strip()
        # A FILE THAT DOES NOT PARSE IS AN ERROR ABOUT THAT FILE. The generic path below falls back
        # to "then it is a string", which is right for a value typed on the command line and wrong
        # for one read out of a file the caller wrote as JSON: the string then arrived inside the
        # verb and came back as `string indices must be integers` — a Python message about a value
        # whose origin nothing named (wave 26, 2026-09-06).
        if text[:1] in "{[":
            try:
                return json.loads(text)
            except (ValueError, json.JSONDecodeError) as ex:
                raise ValueError(f"{path} does not parse as JSON: {ex}. The file begins with "
                                 f"{text[:1]!r}, so it was read as JSON — fix the file, or pass the "
                                 f"value inline if it was meant to be text.") from None
        return _coerce(text)
    try:
        return json.loads(v) if (v[:1] in "{[" or v.lstrip("-").replace(".", "", 1).isdigit()) else v
    except (ValueError, json.JSONDecodeError):
        return v


def _typed(v: str, param):
    """A positional argument, read as the parameter's own type — int/float/bool, else as written."""
    if param is None:
        return _coerce(v) if v[:1] in "{[@" else v
    ann = str(param.annotation).lower()
    if _wants_list(param):
        return _as_list(v)
    if "int" in ann and v.lstrip("-").isdigit():
        return int(v)
    if "float" in ann:
        try:
            return float(v)
        except ValueError:
            return v
    if "bool" in ann:
        return v.strip().lower() in ("1", "true", "yes", "on")
    return _coerce(v) if v[:1] in "{[@" else v


def _wants_list(param) -> bool:
    """Does this verb parameter take a LIST, and ONLY a list? (read off the signature, never the name)

    A parameter that takes either shape — `Union[str, list]`, which `dispute_finding.criterion` is —
    must not have a bare value split on commas: almost every Level-2 finding key contains one
    ("conflict: writer, queue", "undecided: the goal requires X, not Y"), so the split made most
    findings unaddressable from this door and the caller was told their own key "is not an open
    Level-2 finding". A stranger found the workaround (`criterion=@file`) and reported the door as
    effectively closed for disputes (CLI door, wave 25, 2026-09-05).
    A caller who means several still writes JSON, which is what a script sends anyway.
    """
    if param is None:
        return False
    ann = param.annotation
    # RESOLVED HERE, not by the caller. `tools.py` carries `from __future__ import annotations`, so a
    # signature read straight off it hands out STRINGS — and a rule that answers False for every
    # string is a rule that silently un-lists every parameter for anyone who did not know to resolve
    # first. The door does resolve; the suite called it raw and caught exactly that (2026-09-05).
    if isinstance(ann, str):
        try:
            ann = eval(ann, {**vars(typing), "list": list, "dict": dict, "str": str,  # noqa: S307
                             "int": int, "float": float, "bool": bool, "None": None})
        except Exception:
            return "list" in ann.lower() and "str" not in ann.lower()   # degraded, and only here
    if typing.get_origin(ann) is list or ann is list:
        return True                # `list[dict]` and bare `list` — a list and nothing else
    args = typing.get_args(ann)
    if args:                       # a union — ask its MEMBERS, never its printed form
        # `Optional[list]` is (list, NoneType) and still means a list; `Union[str, list]` also admits
        # a plain string, and there a bare value is that string. Read off the type, because the
        # printed form is a text and reading a rule off a text is how this repository has measured
        # itself wrong before.
        _members = [a for a in args if a is not type(None)]
        if any(a is str for a in _members):
            return False
        return any(a is list or typing.get_origin(a) is list for a in _members)
    return False


def _as_list(v: str) -> list:
    """A bare word where a list is expected is ONE item — not a bag of characters.

    `failed_criteria=exact_duplicate_grouping` arrived as a plain string, the engine iterated it,
    and the node came back failed on twenty-four one-letter "criteria" (`- e`, `- x`, `- a`, …).
    Measured 2026-08-20 on the human door: a person driving from the CLI could not fail a node by
    its criterion name AT ALL — every attempt shredded the name. JSON (`["a","b"]`) still works and
    is what a script should send; this is for the human typing the obvious thing.
    """
    if v[:1] in "{[" or v.startswith("@"):    # …and `@file`, for a value longer than a shell line
        out = _coerce(v)
        return out if isinstance(out, list) else [out]
    return [s.strip() for s in v.split(",") if s.strip()]


def _parse_args(name: str, fn, rest: list) -> tuple[list, dict, dict | None]:
    """The command line as this verb's arguments: `key=value`, positionals in signature order,
    `@file` for a payload that does not fit a shell line, JSON where the verb wants an object.

    `run` decides WHICH verb runs and where its answer goes; reading the words into arguments is
    its own job, and it was sixty statements of one body away from the decision."""
    # RESOLVED, because `tools.py` carries `from __future__ import annotations` and hands this door
    # STRINGS. The old rule read the printed form (`"list" in str(ann)`) and got the right answer for
    # the wrong reason; anything sharper than a substring test needs the real objects.
    _sig = inspect.signature(fn)
    try:
        _hints = typing.get_type_hints(fn)
    except Exception:
        _hints = {}
    sig = {n: (p.replace(annotation=_hints[n]) if n in _hints else p)
           for n, p in _sig.parameters.items()}
    params = set(sig)
    pos, kw = [], {}
    for a in rest:                                # `key=value` (a real param) → kwarg; else positional
        if "=" in a and a.split("=", 1)[0] in params:
            k, v = a.split("=", 1)
            try:
                kw[k] = _as_list(v) if _wants_list(sig.get(k)) else _coerce(v)
            except ValueError as ex:              # an unreadable `@file` is a sentence, not a stack
                # …RETURNED IN THIS FUNCTION'S OWN SHAPE. It printed the sentence and returned `1`
                # out of a function whose contract is a triple, so the caller unpacked an int and
                # the door answered with a TypeError traceback ABOVE the sentence — every
                # unreadable `@file`, including a missing one, has done that (found 2026-09-06 by
                # making a broken JSON file say which file it was).
                return [], {}, {"error": f"{k}: {ex}"}
        elif "=" in a and a.split("=", 1)[0].isidentifier():
            # A `key=value` whose key is not a parameter used to fall through as a POSITIONAL
            # argument — so a typo did not fail, it silently filled the next slot with the literal
            # text `assigne=kirill`. Measured 2026-08-20: three typos in a row produced no warning
            # of any kind, and there was no way to tell "the parameter does not exist" from "the
            # parameter did not work". Refused by name, with the ones that do exist.
            k = a.split("=", 1)[0]
            return [], {}, {"error": f"{name} has no parameter '{k}' — it takes: "
                                     f"{', '.join(p for p in params if not p.startswith('_') and p != 'engine')}"
                                     f" (plus `project=` on any verb)"}
        elif a.startswith("-") and not a.lstrip("-").isdigit() and a.strip("-"):
            # THE OTHER GRAMMAR A PERSON TRIES. This door reads `key=value`; the flag spelling is
            # what most CLIs take, and it fell straight through as POSITIONAL DATA — measured here
            # 2026-09-05: `create_task root '{…}' --assignee me` produced a node whose assignee was
            # the literal string "--assignee" and whose PARENT was "me", both silently, and the node
            # then waited forever for signals from a party that does not exist. The `key=value` typo
            # rule above already refuses by name for exactly this reason; a flag is the same mistake
            # in the other notation, so it gets the same answer.
            _k = a.split("=", 1)[0].lstrip("-")
            _known = _k in params
            _takes = ", ".join(p for p in params if not p.startswith("_") and p != "engine")
            return [], {}, {
                "error": (f"this door reads `key=value`, not flags: write `{_k}=<value>` instead "
                          f"of `{a}`." if _known else
                          f"this door reads `key=value`, not flags, and `{_k}` is not a parameter "
                          f"of {name} — it takes: {_takes} (plus `project=` on any verb)."),
                "refused": True}
        else:
            # …AND TYPED BY THE SIGNATURE. A positional filling an `int` slot arrived as the STRING
            # "1", and the verb compared it with a number: `'>' not supported between instances of
            # 'str' and 'int'`, a traceback naming no argument, on the very form the door's own
            # usage line prints (measured on the human door 2026-08-22, ~10 minutes at the start of
            # a run). The named form worked because coercion happened there; the positional form is
            # the same call.
            _p = list(sig.values())[len(pos) + 1] if len(pos) + 1 < len(sig) else None
            pos.append(_typed(a, _p))
    return pos, kw, None


def _params(fn) -> list[str]:
    """A verb's caller-facing parameters: the leading `engine` and the transport-internal
    underscore ones are not things anybody types."""
    return [p for p in list(inspect.signature(fn).parameters)[1:] if not p.startswith("_")]


#: Parameters that name WHO is acting. A verb carrying one of these gets the identity block below:
#: the door's invitation to name yourself is true, and it was read as an invitation to invent a
#: name. Measured on the human door 2026-09-01: `next_step` answered `"assignee": "agent",
#: "mine": true`, the tester signed a signal `source=w18c-human`, and the FSM refused them from
#: their own graph. The refusal is the protocol working; the help that never said what their id
#: WAS is the defect.
#: The identity word itself is `gfso.config`'s to spell (one owner per shared literal), so the
#: parameter named for it is read off that accessor instead of respelled here.
_WHO_PARAMS = frozenset({"source", "assignee", "new_assignee", agent_id.__name__.removesuffix("_id")})

#: Verb-specific worked examples. The docstrings are shared with the agent door and say what a
#: verb MEANS; a shape you have to guess is a fact about typing it here.
_HELP_EXAMPLES = {
    "edit_criteria": """example — `criteria` is a LIST OF OBJECTS, one per criterion:

  gfso run edit_criteria task_id=D2 criteria='[{"name": "handles_empty_input",
    "description": "given an empty input file, exits 0 and writes nothing"}]'

  `name` is the identifier the protocol refers to the criterion by (`signal … FAIL
  failed_criteria=handles_empty_input`); `description` is the decidable test. A list too long
  for one shell line goes in a file: `criteria=@criteria.json`.

THIS REPLACES THE CONTRACT. The set you pass becomes the whole set — every criterion you do
not name is dropped. Read what is there first (`gfso run get_task <id>`) and include what you
mean to keep. One exception, and it is deliberate: the `dep__<producer>` criteria that carry
the node's dependency edges are carried over unless you name one yourself, so hand-writing the
list cannot silently sever what this node WAITS FOR — cutting an edge stays explicit
(`remove_dependency`).""",
}


def _print_listing() -> None:
    """The command listing — the first thing anyone at this door reads, and therefore where the
    argument every verb takes has to be visible.

    `project=` was on the per-command `--help` and on none of the thirty listed names, while the
    rule for a server holding more than one graph is to pass it explicitly (measured on the human
    door 2026-09-01)."""
    print("gfso run — headless graph commands (the SAME surface as the MCP tools).")
    print("`gfso run <command> --help` prints what it DOES and the shape of every argument —")
    print("the names below are not the shapes: a nested one wants an object, not a word.")
    print("`project=<name>` rides on EVERY command and names the graph it runs against; without "
          "it\nthe verb runs against the server's active project, whichever that currently is.\n")
    for name, fn in T.TOOLS.items():
        print(f"  {name} {' '.join('<' + p + '>' for p in _params(fn))} [project=<name>]")


def _print_verb_help(name: str, fn) -> None:
    """One verb: what it DOES (its docstring, the same description every door shows), then what
    only this door can say — who the caller is here, and the shapes that had to be guessed."""
    print(f"gfso run {name} " + " ".join(f"<{p}>" for p in _params(fn)) + " [project=<name>]\n")
    print(textwrap.dedent(fn.__doc__ or "(no description)").strip())
    if (who := [p for p in _params(fn) if p in _WHO_PARAMS]):
        me = agent_id()
        print(f"\nYOUR ID AT THIS DOOR IS `{me}`. That is the literal name the engine knows this "
              f"terminal by, and\nthe name `auto_decompose` writes into every node it builds for "
              f"you — so a node reported as\n`\"mine\": true` has Del=`{me}`, and `{who[0]}={me}` "
              f"is what this verb wants for such a node.\nNaming yourself something else is real, "
              f"and it is for a node you actually gave to that name\n(`create_task "
              f"assignee=<name>`, `reassign`): the FSM checks the node's Del, not who typed.")
    if name in _HELP_EXAMPLES:
        print("\n" + _HELP_EXAMPLES[name])


#: How each state renders in the tree a person reads. Module level because the renderer that reads
#: it is: a table defined inside one function and read from another is a name nothing binds, which
#: the FORM ratchet counts and which is a real bug waiting for the day the two move apart.
_MARK = {"DONE": "[x]", "ABANDONED": "[-]", "ESCALATED": "[!]", "BLOCKED": "[b]",
         "VALIDATING": "[?]", "REWORKING": "[r]", "EXECUTING": "[>]"}


def _how_a_node_reads(state: str, closure: dict | None) -> tuple:
    """The mark and the sentence for ONE node — how it closed, not only that it did.

    Three kinds a bare `[x]` used to hide: a PASS its own current verdict contradicts, a closure by
    hand OVER an instrument that said otherwise, and a closure on a person's word where no instrument
    spoke. The last keeps its tick — it is the documented solo path (§14.5's degenerate case) — and
    the first two do not. Module level rather than nested, because a nested body counts toward its
    enclosing function and the size rule is measuring the tree, not the indentation.

    READ FROM THE NODE, not out of the completion answer. These three facts used to be scraped from
    `next_steps`, which reports them only on the branch where a graph is COMPLETE — so the marks
    vanished exactly while a project still had work in it, which is when someone is looking (CLI and
    fresh-install doors reported it independently, wave 26, 2026-09-06). The node carries its own
    closure now (`Engine.closure_of`), so the tree says the same thing at every moment of a run.
    """
    cl = closure or {}
    if cl.get("refuted"):
        return "[X]", "   <- PASS CONTRADICTED by its own current verdict (get_verdict)"
    if cl.get("overruled"):
        return "[!]", "   <- closed BY HAND over an instrument's opposite verdict (get_verdict)"
    if cl.get("by_hand"):
        return (_MARK.get(state, "[ ]"),
                "   <- closed on a verdict ASSERTED BY HAND, not an instrument's (get_verdict)")
    return _MARK.get(state, "[ ]"), ""


def status(argv: list[str]) -> int:
    """The graph as a person reads it: one line per node, indented by depth.

    `get_graph` answers with the whole object, unindented, and a tester asking "which nodes are done
    and which are still validating" ended up regexing ids and states out of the raw text with a
    throwaway one-liner — the one moment in a whole run where they came closest to opening the source
    (CLI door, 2026-09-02). The data was always there; what was missing was a shape a person reads.
    """
    project = next((a.split("=", 1)[1] for a in argv
                    if a.startswith("project=") or a.startswith("--project=")), None)
    # …AND A ROOT ID IS A WORD, not any leftover token. `gfso status -- project=x` took `--` for an id
    # and printed a phantom node rather than refusing it (CLI door, 2026-09-02): a tree that invents a
    # row is worse than one that says the id is unknown.
    root = next((a for a in argv if "=" not in a and not a.startswith("-")), None)
    actor = next((a.split("=", 1)[1] for a in argv
                  if a.startswith("actor=") or a.startswith("--actor=")), None)
    g = run_verb("get_graph", project=project)
    if not isinstance(g, dict) or g.get("error"):
        print(json.dumps(g, ensure_ascii=False))
        return 1
    nodes = {str(n.get("id")): n for n in (g.get("nodes") or ())}
    kids: dict = {}
    for n in nodes.values():
        kids.setdefault(str(n.get("parent_id") or ""), []).append(str(n.get("id")))
    if root and root not in nodes:
        print(json.dumps({"error": f"no node {root!r} in this project",
                          "roots": sorted(kids.get("", []))}, ensure_ascii=False))
        return 1
    roots = [root] if root else sorted(kids.get("", []))
    # A GREEN THAT IS NOT GREEN MUST NOT RENDER AS `[x]`. A node can stand at PASS while its own
    # current verdict says FAIL, and this tree — the thing a person actually looks at to answer "is
    # it done" — printed it identically to an evidence-backed one (CLI door, 2026-09-02).
    # SCOPED WHERE THE TREE IS SCOPED, AND ASKED AS WHOEVER IS ASKING. `status <root>` printed that
    # root's subtree and then counted the whole project underneath it, and put the whole project's
    # frontier under the same heading; and `actor=` — which every other frontier verb takes — was
    # dropped, so a person driving their own graph read "0 step(s) for you" beside a step that was
    # theirs (CLI and fresh-install doors, wave 26, 2026-09-06).
    nxt = run_verb("next_steps", project=project, root_id=root, actor=actor)

    shown: list = []

    def _line(nid: str, depth: int) -> None:
        n = nodes.get(nid) or {}
        state = str(n.get("state") or "?")
        shown.append(n)
        mark, why = _how_a_node_reads(state, n.get("closure"))
        print(f"{'  ' * depth}{mark} {nid}  {state}  ({str(n.get('assignee') or '-')})"
              + (f"  {n.get('name')}" if n.get("name") else "") + why)
        for k in sorted(kids.get(nid, [])):
            _line(k, depth + 1)

    for r in roots:
        _line(r, 0)
    counts: dict = {}
    for n in shown:
        counts[str(n.get("state"))] = counts.get(str(n.get("state")), 0) + 1
    print("\n" + " · ".join(f"{k} {v}" for k, v in sorted(counts.items()))
          + f" · {len(shown)} nodes"
          + (f" under {root}" if root else " total"))
    if isinstance(nxt, dict):
        if nxt.get("refuted_passes"):
            print(f"frontier: NOT COMPLETE — {nxt['directive']}")
        elif nxt.get("complete"):
            print("frontier: COMPLETE — the root is DONE/PASS")
        else:
            mine = [s for s in (nxt.get("steps") or ()) if s.get("mine")]
            print(f"frontier: {len(mine)} step(s) for you"
                  + (f", first: {mine[0].get('action')} {mine[0].get('task_id')}" if mine else "")
                  + f" · {len(nxt.get('in_flight') or ())} in flight"
                  + f" · {len(nxt.get('waiting') or ())} waiting")
    return 0


def run_verb(name: str, project: str | None = None, *pos, **kw):
    """Call one verb the way `run` does — through the live server when there is one, else locally.

    THE one place that answers "how does this door reach the engine", so a caller that wants an
    ANSWER rather than a printed line does not build an argv and parse the output back (`status` is
    the first such caller) — and so the project-selection rule is not written twice.
    """
    fn = T.TOOLS[name]
    out = _through_server(name, fn, list(pos), kw, project)
    if out is None:
        out = _locally(fn, project, list(pos), kw)
    return out


def _locally(fn, project: str | None, pos: list, kw: dict):
    """Run the verb in this process — the path with no server up.

    With no server the direct path is the only one there is, and it is correct: the second-writer
    problem it used to create exists only when a server is also holding the file.
    """
    if project:
        select_project(project)
    engine = build_engine_from_env()
    out = fn(engine, *pos, **kw)
    engine.wait_idle()
    return out


def run(argv: list[str]) -> int:
    """Run one CLI verb from `argv` and return its exit code.

    The exit code is about the ACT, not the transport: a verb the engine understood and refused
    is a non-zero exit with the refusal in the body.
    """
    try:  # graph/LLM text carries →/≈/±; keep stdout from crashing on a non-UTF-8 console
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass  # a stream that refuses is one with nothing to reconfigure — the run itself is unaffected

    if not argv or argv[0] in ("-h", "--help", "help"):
        _print_listing()
        return 0

    name, rest = argv[0], argv[1:]
    fn = T.TOOLS.get(name)
    # `gfso run <verb> --help` — WHAT THE VERB IS, not just the shape of its call. The listing prints
    # parameter names and nothing else, so a person could see that `record_verdict` takes `observed`
    # and had to read the source to learn what belongs in it. The docstring is where every door's
    # description already comes from; this is the human door finally reading it out.
    if fn is not None and any(a in ("-h", "--help", "help") for a in rest):
        _print_verb_help(name, fn)
        return 0
    if fn is None:
        # A VERB THAT EXISTS SOMEWHERE ELSE IS NOT AN UNKNOWN VERB. The MCP door carries the
        # project-lifecycle verbs (they are about WHICH graph a session stands in, not about a
        # graph), and a person who learnt them there was answered "unknown command" with a list of
        # thirty others to search (measured on the human door 2026-08-22). Say the door.
        _elsewhere = {"delete_project": "gfso projects --delete <name> --yes",
                      "list_projects": "gfso projects",
                      "use_project": "gfso run <verb> project=<name> (the CLI carries the project per call)"}
        if name in _elsewhere:
            print(json.dumps({"error": f"'{name}' is not a graph verb — on this door it is: "
                                       f"{_elsewhere[name]}", "use": _elsewhere[name]}, ensure_ascii=False))
            return 1
        print(json.dumps({"error": f"unknown command '{name}'", "commands": list(T.TOOLS)}, ensure_ascii=False))
        return 1

    params = set(inspect.signature(fn).parameters)
    # `project=` is not a tool parameter — it selects WHICH graph the verb runs against, and belongs
    # to the door rather than to the verb. Taken out before the split below, or it would fall
    # through as a positional and be dropped without a word.
    # Both spellings, because the two CLI commands had two grammars: `gfso run … project=<name>` and
    # `gfso log --project <name>`, and a person who learnt one was refused by the other with no hint
    # that the other existed.
    project = next((a.split("=", 1)[1] for a in rest
                    if a.startswith("project=") or a.startswith("--project=")), None)
    if project is None and "--project" in rest:
        _i = rest.index("--project")
        project = rest[_i + 1] if _i + 1 < len(rest) else None
        rest = rest[:_i] + rest[_i + 2:]
    rest = [a for a in rest if not (a.startswith("project=") or a.startswith("--project="))]
    pos, kw, _bad = _parse_args(name, fn, rest)
    if _bad is not None:                      # a parameter this verb does not have: refused by name
        print(json.dumps(_bad, ensure_ascii=False))
        return 1

    # THROUGH THE RUNNING SERVER when there is one. This used to open the database directly,
    # always, and that is a second writer against a file whose single-sequencer property is what
    # the log's guarantees rest on: Inv-7 gives one non-branching history, and §14.3 requires the
    # consumption check and the edge it authorizes to be ONE log-serialized step. Two engines over
    # one file are two sequencers, and the interleaving that breaks it is exactly the one nobody
    # would reproduce on purpose. It also meant a CLI write appeared in the UI only on a reload, and
    # reached neither the dispatcher's queue nor the observation panel.
    #
    # With no server up, the direct path is still correct — and it is the only one there is.
    out = _through_server(name, fn, pos, kw, project)
    if out is None:
        out = _locally(fn, project, pos, kw)
    # …and tell the caller where to LOOK. The agent door attaches this and the human door did not,
    # so the person the UI exists for was the one never given its address.
    if name in _T.UI_LINK_VERBS and isinstance(out, dict) and "ui" not in out:
        try:
            out["ui"] = _T.ui_link(project or out.get("active"))
        # the link is attached to a result already produced — never a reason to fail the call that
        # produced it
        except Exception:
            pass
    _emit(out)
    # A REFUSAL IS NOT A SUCCESS, and a script has only the exit code to read it by. Every 422 came
    # back as rc 0, so a batch of `gfso run` calls reported success on the ones the engine had
    # refused, and the person only noticed because they happened to be printing bodies (measured on
    # the human door 2026-08-21). The verbs answer rather than raise — that is deliberate, and it is
    # about the SHAPE of the answer, not about pretending the act happened.
    return 1 if T.is_refusal(out) else 0


def _emit(out) -> None:
    """JSON for a script, READABLE text for a person at a terminal.

    The directives this door hands out are prose — several sentences with newlines in them — and
    JSON escapes every one, so the human door printed its most important field as a single line of
    backslash-n. A pipe or a redirect still gets exact JSON (`gfso run … | jq` keeps working); only
    an interactive terminal gets the rendering.
    """
    if not (isinstance(out, (dict, list)) and sys.stdout.isatty()):
        print(json.dumps(out, default=str, ensure_ascii=False))
        return
    # NOTHING IS AN ANSWER, and it has to look like one. An empty list rendered as an empty screen:
    # measured 2026-08-21, a person ran `list_holes` twice because they could not tell "no holes"
    # from a call that had failed silently.
    print(_render(out) if out else "(empty — the verb answered, and the answer is nothing)")


def _render(v, indent: str = "") -> str:
    """One value as indented lines; multi-line strings become blocks instead of escapes."""
    nl = "\n"
    if isinstance(v, dict):
        parts = []
        for k, val in v.items():
            if isinstance(val, str) and nl in val:
                body = nl.join(indent + "    " + ln for ln in val.splitlines())
                parts.append(f"{indent}{k}:" + nl + body)
            elif isinstance(val, (dict, list)) and val:
                parts.append(f"{indent}{k}:" + nl + _render(val, indent + "  "))
            else:
                parts.append(f"{indent}{k}: {json.dumps(val, default=str, ensure_ascii=False)}")
        return nl.join(parts)
    if isinstance(v, list):
        return nl.join(_render(x, indent + "  ") if isinstance(x, (dict, list))
                       else f"{indent}- {json.dumps(x, default=str, ensure_ascii=False)}"
                       for x in v)
    return f"{indent}{v}"


#: The verbs that spawn a model and run for MINUTES. The door blocks on them with nothing on screen:
#: measured on the agent door 2026-08-21, three and a half minutes of silence with no way to tell a
#: working call from a hung one, on a server that was also serving someone else's run. The engine
#: already narrates itself into the observation field; this door just was not listening.
_LONG_VERBS = frozenset({"auto_decompose", "review_decomposition", "validate_result"})


def _narrate(project: str | None, stop) -> None:
    """Mirror the project's observation lines to STDERR while a long verb runs.

    stderr, not stdout: stdout is this door's JSON, and a progress line printed into it corrupts the
    answer for anything parsing it."""
    seen = None
    while not stop.is_set():
        try:
            url = f"{serverctl.BASE}/api/pipeline?limit=5" + (f"&project={quote(project)}" if project else "")
            with urllib.request.urlopen(url, timeout=5) as r:
                rows = json.loads(r.read() or b"[]")
            for row in rows:
                key = (row.get("ts"), row.get("message"))
                if seen is None or key > seen:
                    print(f"  … {row.get('message', '')}", file=sys.stderr, flush=True)
            if rows:
                seen = max((row.get("ts"), row.get("message")) for row in rows)
        except Exception:
            pass                       # narration is presentation — never break the call it watches
        stop.wait(3.0)


def _through_server(name, fn, pos: list, kw: dict, project: str | None):
    """Run the verb on the live server over `/api/run/<tool>`; None when no server answers.

    The HTTP door takes keyword arguments only, so the positionals are named here off the same
    signature the CLI already reads — one surface, two spellings of the same call.
    """
    if serverctl.runtime() is None:
        return None
    names = [p for p in list(inspect.signature(fn).parameters)[1:] if not p.startswith("_")]
    body = dict(zip(names, pos))
    body.update(kw)
    url = f"{serverctl.BASE}/api/run/{name}" + (f"?project={quote(project)}" if project else "")
    req = urllib.request.Request(url, data=json.dumps(body, default=str).encode(),
                                 headers={"Content-Type": "application/json"}, method="POST")
    stop, narrator = threading.Event(), None
    if name in _LONG_VERBS and narrate():
        narrator = threading.Thread(target=_narrate, args=(project, stop), daemon=True)
        narrator.start()
    try:
        with urllib.request.urlopen(req, timeout=1800) as r:
            return json.loads(r.read() or b"null")
    except urllib.error.HTTPError as ex:
        # The body is already the verb's own JSON — carried as a STRING it arrived double-escaped
        # (`{"error": "{\"detail\":\"signal needs source …\"}"}`) and a person unpicked quoted
        # braces to read one sentence. Unwrap it when it parses; keep the text when it does not.
        raw = ex.read().decode("utf-8", "replace")[:4000]
        try:
            body = json.loads(raw)
        except (ValueError, json.JSONDecodeError):
            return {"error": raw, "status": ex.code}
        if isinstance(body, dict):
            return {**({"error": body["detail"]} if isinstance(body.get("detail"), str) else body),
                    "status": ex.code}
        return {"error": body, "status": ex.code}
    finally:
        stop.set()
        if narrator is not None:
            narrator.join(1.0)
