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
import threading
import inspect
from pathlib import Path
import urllib.error
import urllib.request
from urllib.parse import quote

from gfso.runtime import build_engine_from_env
from gfso import tools as _T     # the verb surface: UI_LINK_VERBS / ui_link live there
from gfso.config import narrate
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
        return _coerce(path.read_text(encoding="utf-8").strip())
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
    """Does this verb parameter take a LIST? (read off the signature, never guessed from the name)"""
    if param is None:
        return False
    ann = param.annotation
    return "list" in str(ann).lower()


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
    sig = inspect.signature(fn).parameters
    params = set(sig)
    pos, kw = [], {}
    for a in rest:                                # `key=value` (a real param) → kwarg; else positional
        if "=" in a and a.split("=", 1)[0] in params:
            k, v = a.split("=", 1)
            try:
                kw[k] = _as_list(v) if _wants_list(sig.get(k)) else _coerce(v)
            except ValueError as ex:              # an unreadable `@file` is a sentence, not a stack
                print(json.dumps({"error": f"{k}: {ex}"}, ensure_ascii=False))
                return 1
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


def run(argv: list[str]) -> int:
    try:  # graph/LLM text carries →/≈/±; keep stdout from crashing on a non-UTF-8 console
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass

    if not argv or argv[0] in ("-h", "--help", "help"):
        print("gfso run — headless graph commands (the SAME surface as the MCP tools).")
        print("`gfso run <command> --help` prints what it DOES and the shape of every argument —")
        print("the names below are not the shapes: a nested one wants an object, not a word." + "\n")
        for name, fn in T.TOOLS.items():
            ps = [p for p in list(inspect.signature(fn).parameters)[1:]  # drop the leading `engine`
                  if not p.startswith("_")]                  # underscore params are transport-internal
            print(f"  {name} {' '.join('<' + p + '>' for p in ps)}")
        return 0

    name, rest = argv[0], argv[1:]
    fn = T.TOOLS.get(name)
    # `gfso run <verb> --help` — WHAT THE VERB IS, not just the shape of its call. The listing prints
    # parameter names and nothing else, so a person could see that `record_verdict` takes `observed`
    # and had to read the source to learn what belongs in it. The docstring is where every door's
    # description already comes from; this is the human door finally reading it out.
    if fn is not None and any(a in ("-h", "--help", "help") for a in rest):
        import textwrap
        ps = [p for p in list(inspect.signature(fn).parameters)[1:] if not p.startswith("_")]
        print(f"gfso run {name} " + " ".join(f"<{p}>" for p in ps) + " [project=<name>]\n")
        print(textwrap.dedent(fn.__doc__ or "(no description)").strip())
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
        if project:
            os.environ["GFSO_PROJECT"] = project
        engine = build_engine_from_env()
        out = fn(engine, *pos, **kw)
        engine.wait_idle()
    # …and tell the caller where to LOOK. The agent door attaches this and the human door did not,
    # so the person the UI exists for was the one never given its address.
    if name in _T.UI_LINK_VERBS and isinstance(out, dict) and "ui" not in out:
        try:
            out["ui"] = _T.ui_link(project or out.get("active"))
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
