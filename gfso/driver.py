"""CLI driver — the headless graph-driving commands behind `gfso run`. Kept OUT of `cli.py` (the launcher):
`cli.py` wires the `run` subcommand, the low-level per-tool dispatch lives here.

It binds the SAME shared action surface as MCP (`gfso.tools.TOOLS`), so the CLI has full parity with MCP by
construction — add a tool and it appears here for free, no per-command upkeep. Each invocation loads the CORE
from GFSO_DB_PATH, runs one tool, prints JSON, persists (state lives in SQLite, so a sequence of commands drives
the graph exactly as MCP calls would). The only thing a persistent MCP process adds is LIVE UI mirroring (WS) —
a lifecycle difference, not a capability one.

    gfso run                                   # list commands
    gfso run auto_decompose "<request>"        # build the graph
    gfso run next_step                          # the forcing-point: the next directive
    gfso run signal <task> ACCEPT human         # ACCEPT / DELIVER (result=...) / PASS / FAIL / ...
    gfso run list_holes | get_graph | get_task <id> | project <id>
"""
from __future__ import annotations

import sys
import json
import inspect

from gfso.runtime import build_engine_from_env
from gfso import tools as T


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
    pos, kw = [], {}
    for a in rest:                                # `key=value` (a real param) → kwarg; else positional
        if "=" in a and a.split("=", 1)[0] in params:
            k, v = a.split("=", 1)
            kw[k] = _coerce(v)
        else:
            pos.append(_coerce(a) if a[:1] in "{[" else a)

    engine = build_engine_from_env()
    out = fn(engine, *pos, **kw)
    engine.wait_idle()
    print(json.dumps(out, default=str, ensure_ascii=False))
