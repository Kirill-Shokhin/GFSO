"""FastMCP server (track-b): exposes the CORE upper API to the agent as MCP tools.

Requires the MCP SDK: `pip install gfso[mcp]`. Run:  python -m gfso.mcp.server
Holds ONE Engine (SQLite-persistent) = the same CORE the UI observes — the agent's tool calls and the
UI watch one graph. Every authoring tool desugars to the closed 12-signal FSM (no bypass); the tool
docstrings (from tools.py) become the tool descriptions the agent reads.
"""
from __future__ import annotations

import functools
import inspect
import os

from gfso.engine import Engine
from gfso import tools as T                       # the shared action surface (MCP + CLI both bind it)


# Session-scoped project defaults: with ONE shared server and several agent sessions in parallel,
# `use_project` must switch THAT session's default, not a global (two sessions would fight over it).
# Keyed by the MCP session object; a session that never called use_project falls back to the
# registry's active project. Stdio (one session per process) degrades to exactly the old behavior.
_SESSION_PROJECTS: dict[int, str] = {}


def _session_key(ctx) -> int | None:
    try:
        return id(ctx.request_context.session) if ctx is not None else None
    except Exception:
        return None


def _resolver(engine_or_registry):
    """One call surface over both shapes: a bare Engine (tests, single-project) or a ProjectRegistry
    (the server). resolver(project=None, ctx=None) → the engine; precedence: explicit `project`
    param → the calling SESSION's project → the registry's active."""
    if hasattr(engine_or_registry, "engine"):        # ProjectRegistry
        def _res(project=None, ctx=None):
            name = project or _SESSION_PROJECTS.get(_session_key(ctx) or 0)
            return engine_or_registry.engine(name)
        return _res
    return lambda project=None, ctx=None: engine_or_registry   # bare Engine — ignored


# Actor-identity params are PINNED on the agent's door: everything arriving over MCP IS the agent,
# so it can never sign a signal or an authoring act as someone else (the UI/HTTP door carries the
# human's explicit name; the CLI stays the unpinned dev door). Delegation params (assignee) stay
# free — NAMING an executor is legitimate; SPEAKING as one is not.
_PINNED_ACTOR = {"signal": ("source",), "revise": ("agent",),
                 "reneglect": ("agent",), "edit_criteria": ("agent",)}


def _bind(engine_or_registry, fn):
    """Wrap a tools.py function (engine, *args) as an MCP tool: drop `engine` from the signature so the
    SDK infers the schema from the remaining typed params; keep the docstring as the description.
    When a ProjectRegistry is bound, every tool additionally gains an optional trailing `project`
    param (None = the active project) — the multi-project surface lives in the BINDING layer, the
    tools stay pure (engine, *args). Actor params (_PINNED_ACTOR) are REMOVED from the schema and
    forced to the standing agent id at call time.

    Annotations are resolved to real types here: tools.py uses `from __future__ import annotations`
    (string hints), and the wrapper's globals are this module's — so the SDK's schema introspection would
    fail to eval e.g. `Optional[str]`. `get_type_hints(fn)` resolves them in tools.py's own namespace."""
    import typing
    resolve = _resolver(engine_or_registry)
    multi = hasattr(engine_or_registry, "engine")
    pinned = _PINNED_ACTOR.get(fn.__name__, ())
    hints = typing.get_type_hints(fn)
    sig = inspect.signature(fn)
    params = [
        (p.replace(annotation=hints[p.name]) if p.name in hints else p)
        for p in list(sig.parameters.values())[1:]  # drop the leading `engine`
        if not p.name.startswith("_")               # underscore params are transport-internal (e.g. _progress)
        and p.name not in pinned                    # actor identity is the door's, not the caller's claim
    ]
    Context = None
    if multi:
        try:
            from mcp.server.fastmcp import Context as _Ctx
            Context = _Ctx
        except ImportError:  # SDK absent (direct _bind unit use) — no session scoping
            pass
    if multi and "project" not in {p.name for p in params}:
        # KEYWORD_ONLY must precede a VAR_KEYWORD (e.g. `**payload`) or the signature is invalid
        var_kw = next((i for i, p in enumerate(params) if p.kind == inspect.Parameter.VAR_KEYWORD),
                      len(params))
        params.insert(var_kw, inspect.Parameter("project", inspect.Parameter.KEYWORD_ONLY,
                                                default=None, annotation=typing.Optional[str]))
        if Context is not None:  # the SDK injects ctx (Context-typed params are schema-invisible)
            params.insert(var_kw + 1, inspect.Parameter("ctx", inspect.Parameter.KEYWORD_ONLY,
                                                        default=None, annotation=Context))

    @functools.wraps(fn)
    def wrapper(*args, project=None, ctx=None, **kwargs):
        if pinned:
            from gfso.tools import _agent_id
            for name in pinned:
                kwargs[name] = _agent_id()
        return fn(resolve(project, ctx), *args, **kwargs)

    wrapper.__signature__ = sig.replace(
        parameters=params, return_annotation=hints.get("return", sig.return_annotation))
    wrapper.__annotations__ = {k: v for k, v in hints.items() if k != "engine" and k not in pinned}
    if multi:
        wrapper.__annotations__["project"] = typing.Optional[str]
        if Context is not None:
            wrapper.__annotations__["ctx"] = Context
    return wrapper


def _bind_auto_decompose(engine_or_registry):  # pragma: no cover — exercised live over MCP
    """auto_decompose runs for minutes (several headless one-shots) — bind it ASYNC with an MCP Context so
    each pipeline stage streams to the client as a progress notification instead of a silent multi-minute
    wait. Presentation plumbing only: the logic stays in tools.auto_decompose (`_progress` is its
    transport-internal callback; stderr keeps logging regardless)."""
    import asyncio
    from typing import Optional
    from mcp.server.fastmcp import Context
    resolve = _resolver(engine_or_registry)

    async def auto_decompose(request: str, root_id: str = "root", assignee: str = None,
                             depth: int = 1, model: str = "sonnet", fast: bool = False,
                             project: str = None, ctx: Context = None) -> dict:
        loop = asyncio.get_running_loop()
        step = {"n": 0}

        def prog(msg: str) -> None:  # called from the executor thread
            step["n"] += 1
            if ctx is not None:
                try:
                    asyncio.run_coroutine_threadsafe(
                        ctx.report_progress(step["n"], None, f"[decompose] {msg}"), loop)
                except Exception:
                    pass  # progress is presentation — never break the pipeline

        return await loop.run_in_executor(None, functools.partial(
            T.auto_decompose, resolve(project, ctx), request, root_id=root_id, assignee=assignee,
            depth=depth, model=model, fast=fast, _progress=prog))

    auto_decompose.__doc__ = T.auto_decompose.__doc__
    # `from __future__ import annotations` stringifies hints and Context is imported locally — hand the
    # SDK real types so its schema introspection can evaluate the signature.
    auto_decompose.__annotations__ = {"request": str, "root_id": str, "assignee": Optional[str],
                                      "depth": int, "model": str, "fast": bool,
                                      "project": Optional[str], "ctx": Context, "return": dict}
    return auto_decompose


def _bind_validate_node(engine_or_registry):  # pragma: no cover — exercised live over MCP
    """validate_node spawns a tool-using validator agent (minutes when it runs real test suites) — same
    async + progress-notification binding as auto_decompose, for the same MCP-timeout reason."""
    import asyncio
    from typing import Optional
    from mcp.server.fastmcp import Context
    resolve = _resolver(engine_or_registry)

    async def validate_node(task_id: str, deliverable: str = None, model: str = "sonnet",
                            workdir: str = None, project: str = None, ctx: Context = None) -> dict:
        loop = asyncio.get_running_loop()
        step = {"n": 0}

        def prog(msg: str) -> None:  # called from the executor thread
            step["n"] += 1
            if ctx is not None:
                try:
                    asyncio.run_coroutine_threadsafe(
                        ctx.report_progress(step["n"], None, f"[validate_node] {msg}"), loop)
                except Exception:
                    pass  # progress is presentation — never break the pipeline

        return await loop.run_in_executor(None, functools.partial(
            T.validate_node, resolve(project, ctx), task_id, deliverable=deliverable, model=model,
            workdir=workdir, _progress=prog))

    validate_node.__doc__ = T.validate_node.__doc__
    validate_node.__annotations__ = {"task_id": str, "deliverable": Optional[str], "model": str,
                                     "workdir": Optional[str], "project": Optional[str],
                                     "ctx": Context, "return": dict}
    return validate_node


def create_server(engine_or_registry):
    """Register every tools.py function on a FastMCP server (a bare Engine or a ProjectRegistry —
    with a registry every tool gains the optional `project` param + the use_project/list_projects
    verbs). Raises if the MCP SDK is absent."""
    try:
        from mcp.server.fastmcp import FastMCP
    except ImportError as e:  # pragma: no cover
        raise RuntimeError("MCP SDK not installed — run `pip install gfso[mcp]`") from e
    # The user-agent's protocol travels as the server's INSTRUCTIONS (delivered at initialize) — the
    # agent starts knowing WHAT GFSO is and HOW to drive it, not just 25 bare tool schemas. One source
    # of truth: gfso/mcp/ORCHESTRATOR.md.
    from pathlib import Path
    try:
        protocol = (Path(__file__).parent / "ORCHESTRATOR.md").read_text(encoding="utf-8")
    except OSError:  # pragma: no cover
        protocol = ""
    server = FastMCP("gfso", instructions=protocol)
    long_running = {"auto_decompose": _bind_auto_decompose, "validate_node": _bind_validate_node}
    for name, fn in T.TOOLS.items():
        if name in long_running:  # minutes-long: async + MCP progress notifications
            server.add_tool(long_running[name](engine_or_registry), name=name,
                            description=(fn.__doc__ or "").strip())
            continue
        server.add_tool(_bind(engine_or_registry, fn), name=name, description=(fn.__doc__ or "").strip())
    if hasattr(engine_or_registry, "use"):    # ProjectRegistry → the project verbs
        reg = engine_or_registry
        from mcp.server.fastmcp import Context as _Ctx

        def use_project(name: str, ctx: _Ctx = None) -> dict:
            """Switch YOUR SESSION's project (a separate GRAPH in its own DB file; created on first
            use). Several agent sessions share this server — each holds its own current project, so
            switching never affects the others; all your verbs default to it (`project` on any verb
            overrides per-call). A Dep across projects is not representable — if two goals need a Dep
            edge, they belong in ONE project."""
            reg.engine(name)                              # validates the name + creates lazily
            key = _session_key(ctx)
            if key is not None:
                _SESSION_PROJECTS[key] = name
            else:                                         # no session (bare transport) → global active
                reg.use(name)
            return {**reg.list(), "active": name}

        def list_projects(ctx: _Ctx = None) -> dict:
            """{active, projects}: the isolated project graphs this server owns (one DB file each);
            `active` = YOUR session's current project."""
            out = reg.list()
            key = _session_key(ctx)
            if key is not None and key in _SESSION_PROJECTS:
                out["active"] = _SESSION_PROJECTS[key]
            return out

        use_project.__annotations__ = {"name": str, "ctx": _Ctx, "return": dict}
        list_projects.__annotations__ = {"ctx": _Ctx, "return": dict}
        server.add_tool(use_project, name="use_project", description=(use_project.__doc__ or "").strip())
        server.add_tool(list_projects, name="list_projects", description=(list_projects.__doc__ or "").strip())
    _add_agent_verbs(server, engine_or_registry)
    return server


def _add_agent_verbs(server, engine_or_registry) -> None:
    """The delegation roster: register_agent / list_agents + the autostart dispatchers. Delegation is
    NOT a verb — the issuer's only act is setting Del (assignee) to a registered llm-executor; the
    dispatcher picks the node up from the frontier, spawns the executor, wraps its signals, and
    auto-validates the delivery with the registered llm-validator (verdict auto-signals; an unparsed
    verdict escalates)."""
    from typing import Optional
    from gfso.delegate import default_agents, ensure_dispatcher
    agents = default_agents()
    # ProjectRegistry engines attach their dispatchers at creation (runtime); a BARE engine
    # (tests / single-project embedding) gets one here.
    if not hasattr(engine_or_registry, "engine"):
        ensure_dispatcher(engine_or_registry, agents)

    def register_agent(agent_id: str, kind: str, model: str = "sonnet",
                       workdir: str = None, validator: str = None) -> dict:
        """Register a NON-human participant (humans need no registration — an unregistered Del = human,
        the system stays passive). kind: `llm-executor` (nodes assigned to this id AUTOSTART: headless
        executor with work tools in `workdir`, its report wrapped into ACCEPT/DELIVER/BLOCK/CHALLENGE) ·
        `llm-validator` (the auto-validation instrument fired on EVERY delivery — delegated or
        self-executed; its verdict auto-signals PASS/FAIL) · `external` (a system that sends its own
        signals; nothing spawns). `validator` on an executor entry = a per-executor instrument override
        (else the first registered llm-validator serves everyone). To delegate work after this: just
        assign/reassign nodes to the registered id."""
        return agents.register(agent_id, kind, model=model, workdir=workdir, validator=validator)

    def list_agents() -> dict:
        """The delegation roster {agent_id → kind/model/workdir}. Unlisted ids = humans."""
        return agents.list()

    register_agent.__annotations__ = {"agent_id": str, "kind": str, "model": str,
                                      "workdir": Optional[str], "validator": Optional[str],
                                      "return": dict}
    list_agents.__annotations__ = {"return": dict}
    server.add_tool(register_agent, name="register_agent", description=(register_agent.__doc__ or "").strip())
    server.add_tool(list_agents, name="list_agents", description=(list_agents.__doc__ or "").strip())


def _serve_ui(registry, host: str, port: int) -> None:  # pragma: no cover
    """Serve the HTTP + UI + WebSocket over the SAME registry in a daemon thread, so the human watches the
    agent's MCP mutations LIVE (and follows use_project switches). All logging → stderr: stdout is the MCP
    stdio channel and MUST stay clean (a stray print would corrupt the JSON-RPC stream)."""
    import sys, threading, uvicorn
    from gfso.api.server import create_app
    # with_mcp=False — the MCP surface is this stdio process; the app is UI-only
    app = create_app(registry.engine(), registry=registry)
    config = uvicorn.Config(app, host=host, port=port, log_level="warning",
                            access_log=False, log_config=None)  # log_config=None → root logger (stderr)
    threading.Thread(target=uvicorn.Server(config).run, daemon=True).start()
    print(f"[gfso mcp] UI live at http://{host}:{port}", file=sys.stderr)


def main() -> None:  # pragma: no cover
    from gfso.runtime import ProjectRegistry
    registry = ProjectRegistry()
    registry.engine()  # materialize the default project up front
    if os.environ.get("GFSO_MCP_UI", "1") != "0":
        try:
            _serve_ui(registry, os.environ.get("GFSO_UI_HOST", "127.0.0.1"),
                      int(os.environ.get("GFSO_UI_PORT", "8000")))
        except Exception as e:
            import sys
            print(f"[gfso mcp] UI not started ({e}) — MCP tools still work", file=sys.stderr)
    create_server(registry).run()  # blocks on the stdio MCP loop


if __name__ == "__main__":  # pragma: no cover
    main()
