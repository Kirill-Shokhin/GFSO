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
import inspect
import urllib.error
import urllib.request
from urllib.parse import quote

from gfso.runtime import build_engine_from_env
from gfso import tools_llm as T  # the COMPLETE registry (structural + LLM verbs)


def _coerce(v: str):
    """A JSON literal ({…}/[…]/number/true) is parsed; anything else stays a plain string."""
    if not isinstance(v, str):
        return v
    try:
        return json.loads(v) if (v[:1] in "{[" or v.lstrip("-").replace(".", "", 1).isdigit()) else v
    except (ValueError, json.JSONDecodeError):
        return v


def run(argv: list[str]) -> None:
    try:  # graph/LLM text carries →/≈/±; keep stdout from crashing on a non-UTF-8 console
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass

    if not argv or argv[0] in ("-h", "--help", "help"):
        print("gfso run — headless graph commands (the SAME surface as the MCP tools):")
        for name, fn in T.TOOLS.items():
            ps = [p for p in list(inspect.signature(fn).parameters)[1:]  # drop the leading `engine`
                  if not p.startswith("_")]                  # underscore params are transport-internal
            print(f"  {name} {' '.join('<' + p + '>' for p in ps)}")
        return

    name, rest = argv[0], argv[1:]
    fn = T.TOOLS.get(name)
    if fn is None:
        print(json.dumps({"error": f"unknown command '{name}'", "commands": list(T.TOOLS)}, ensure_ascii=False))
        return

    params = set(inspect.signature(fn).parameters)
    # `project=` is not a tool parameter — it selects WHICH graph the verb runs against, and belongs
    # to the door rather than to the verb. Taken out before the split below, or it would fall
    # through as a positional and be dropped without a word.
    project = next((a.split("=", 1)[1] for a in rest if a.startswith("project=")), None)
    rest = [a for a in rest if not a.startswith("project=")]
    pos, kw = [], {}
    for a in rest:                                # `key=value` (a real param) → kwarg; else positional
        if "=" in a and a.split("=", 1)[0] in params:
            k, v = a.split("=", 1)
            kw[k] = _coerce(v)
        else:
            pos.append(_coerce(a) if a[:1] in "{[" else a)

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
    print(json.dumps(out, default=str, ensure_ascii=False))


def _through_server(name, fn, pos: list, kw: dict, project: str | None):
    """Run the verb on the live server over `/api/run/<tool>`; None when no server answers.

    The HTTP door takes keyword arguments only, so the positionals are named here off the same
    signature the CLI already reads — one surface, two spellings of the same call.
    """
    from gfso import serverctl
    if serverctl.runtime() is None:
        return None
    names = [p for p in list(inspect.signature(fn).parameters)[1:] if not p.startswith("_")]
    body = dict(zip(names, pos))
    body.update(kw)
    url = f"{serverctl.BASE}/api/run/{name}" + (f"?project={quote(project)}" if project else "")
    req = urllib.request.Request(url, data=json.dumps(body, default=str).encode(),
                                 headers={"Content-Type": "application/json"}, method="POST")
    try:
        with urllib.request.urlopen(req, timeout=1800) as r:
            return json.loads(r.read() or b"null")
    except urllib.error.HTTPError as ex:
        return {"error": ex.read().decode("utf-8", "replace")[:2000], "status": ex.code}
