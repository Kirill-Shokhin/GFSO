"""FastMCP server (track-b): exposes the CORE upper API to the agent as MCP tools.

Run:  python -m gfso.mcp.server
Holds ONE Engine (SQLite-persistent) = the same CORE the UI observes — the agent's tool calls and the
UI watch one graph. Every authoring tool desugars to the closed 12-signal FSM (no bypass); the tool
docstrings (from tools.py) become the tool descriptions the agent reads.
"""
from __future__ import annotations

import asyncio
import functools
import inspect
import os
import sys
import threading
import typing
from pathlib import Path
from typing import Optional

import anyio
import uvicorn

from gfso.api.server import create_app
from gfso.delegate import default_agents, ensure_dispatcher
from gfso.engine import Engine
from gfso.runtime import ProjectRegistry
from gfso.tools import _agent_id
from gfso import tools_llm as T                   # the COMPLETE action surface (structural + LLM verbs)


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
                 "edit_accepted_risks": ("agent",), "edit_criteria": ("agent",),
                 "record_verdict": ("reviewer",),
                 # reopen re-earns a TERMINAL node under R′ (§14.3) — as load-bearing an act as any
                 # signal, and it was the one whose actor the caller still chose freely, so it
                 # landed in the audit log attributed to whatever name the model wrote.
                 "reopen": ("agent",)}


# The verbs an agent calls when it ENTERS a graph — the moment a human would want to look at it.
# The address lived only in the agent's instructions, so no tool RESULT carried it and the link was
# offered only if the model happened to remember one; here it rides back with the act itself.
from gfso import tools as _T                      # UI_LINK_VERBS / ui_link live on the verb surface
from gfso.config import HEARTBEAT_SECONDS as _HEARTBEAT, MODEL_DEFAULT, ROOT_ID, ui_enabled, ui_address
_UI_LINK_VERBS = _T.UI_LINK_VERBS                 # ONE list, both doors


def _brief(listing: dict, active: str, keep: int = 12) -> dict:
    """A project listing sized for a tool RESULT rather than for an inventory.

    An agent's context is the scarce thing here: this server holds hundreds of projects (every probe
    and every measured run leaves one), and returning all of them — plus a timestamp per project —
    spends thousands of tokens to answer "which project am I in". The trim is stated, not silent:
    `projects_total` says how many exist, and `list_projects` still returns the whole registry.
    """
    names = list(listing.get("projects") or [])
    last = listing.get("last_active") or {}
    recent = sorted(names, key=lambda n: last.get(n, 0), reverse=True)[:keep]
    if active in names and active not in recent:
        recent = [active] + recent[:keep - 1]
    return {"active": active, "projects_recent": recent, "projects_total": len(names)}


def _with_ui_link(name: str, out, project=None, ctx=None):
    """Attach the local UI address to an entry verb's result (dict results only — `project` returns
    markdown and keeps its shape). Best-effort: a link is a convenience, never a reason to fail a
    call. The UI is tab-per-project (`?project=`), so the link points at the graph just acted on."""
    if name not in _UI_LINK_VERBS or not isinstance(out, dict) or "ui" in out:
        return out
    try:
        name_ = project or out.get("active") or _SESSION_PROJECTS.get(_session_key(ctx) or 0)
        out["ui"] = _T.ui_link(name_)
    # the docstring's contract: a link is a convenience, and the verb's result is already correct
    # without it
    except Exception:
        pass
    return out


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
            # LEFT: the MCP SDK is optional AT IMPORT — this module must import without it so
            # `create_server` can raise its readable RuntimeError (and the HTTP door degrade).
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

    # ASYNC, and the body runs in a worker thread. The SDK awaits a synchronous tool INLINE on the
    # event loop, so any tool that blocks blocks the whole process: `review_decomposition` spawns a
    # `claude -p` subprocess capped at 900 seconds, and while it ran the UI stopped updating, the
    # WebSocket stalled, `/api/runtime` did not answer — which a concurrently starting session then
    # read as "the address is held by something that is not a gfso server". Two verbs had been
    # special-cased for this reason; the third was missed, and it is the one the protocol tells an
    # agent to run FIRST. A thread per call closes the class rather than the instance.
    @functools.wraps(fn)
    async def wrapper(*args, project=None, ctx=None, **kwargs):
        """Run the verb off the event loop, on the engine this session's project resolves to.

        A thread per call because a verb that blocks would otherwise stall the whole bridge, and
        the identity of pinned parameters is taken from the transport, never from the caller.
        """
        if pinned:
            for name in pinned:
                kwargs[name] = _agent_id()
        out = await anyio.to_thread.run_sync(
            functools.partial(fn, resolve(project, ctx), *args, **kwargs))
        return _with_ui_link(fn.__name__, out, project, ctx)

    wrapper.__signature__ = sig.replace(
        parameters=params, return_annotation=hints.get("return", sig.return_annotation))
    wrapper.__annotations__ = {k: v for k, v in hints.items() if k != "engine" and k not in pinned}
    if multi:
        wrapper.__annotations__["project"] = typing.Optional[str]
        if Context is not None:
            wrapper.__annotations__["ctx"] = Context
    return wrapper


async def _awaited_with_a_heartbeat(loop, ctx, label: str, step: dict, call):
    """Run a long blocking verb, and keep saying so while it runs.

    A stage that emits nothing emits nothing for as long as it takes, and a client cannot tell a
    thinking server from a dead one: an MCP session aborted `auto_decompose` at its 1800-second
    ceiling after thirty minutes of silence — and the graph HAD been changed by then, so the caller
    was left believing a no-op had happened (agent door, 2026-09-02). One model call can legitimately
    take longer than any per-message timeout, so the tick is not progress about the work; it is the
    session's evidence that the work is still there.
    """
    task = loop.run_in_executor(None, call)
    while True:
        done, _ = await asyncio.wait({task}, timeout=_HEARTBEAT)
        if done:
            return task.result()
        step["n"] += 1
        if ctx is not None:
            try:
                await ctx.report_progress(step["n"], None,
                                          f"{label} still working ({step['n'] * _HEARTBEAT}s)")
            except Exception:
                pass          # progress is presentation — never break the pipeline


def _bind_auto_decompose(engine_or_registry):  # pragma: no cover — exercised live over MCP
    """auto_decompose runs for minutes (several headless one-shots) — bind it ASYNC with an MCP Context so
    each pipeline stage streams to the client as a progress notification instead of a silent multi-minute
    wait. Presentation plumbing only: the logic stays in tools.auto_decompose (`_progress` is its
    transport-internal callback; stderr keeps logging regardless)."""
    # LEFT: the MCP SDK is optional AT IMPORT (see `_bind`) — the annotation is needed only when
    # a server is actually being built.
    from mcp.server.fastmcp import Context
    resolve = _resolver(engine_or_registry)

    async def auto_decompose(request: str, root_id: str = ROOT_ID, assignee: str = None,
                             executor: str = None,
                             depth: int = 1, model: str = MODEL_DEFAULT, fast: bool = False,
                             project: str = None, ctx: Context = None) -> dict:
        """Author or refine a verified subtree, reporting progress while the model runs.

        Minutes-long: the heartbeat below exists because a client that hears nothing for that
        long aborts a call the server is still serving.
        """
        loop = asyncio.get_running_loop()
        step = {"n": 0}

        def prog(msg: str) -> None:  # called from the executor thread
            """Push one progress line to the client from the worker thread."""
            step["n"] += 1
            if ctx is not None:
                try:
                    asyncio.run_coroutine_threadsafe(
                        ctx.report_progress(step["n"], None, f"[decompose] {msg}"), loop)
                except Exception:
                    pass  # progress is presentation — never break the pipeline

        out = await _awaited_with_a_heartbeat(loop, ctx, "[decompose]", step, functools.partial(
            T.TOOLS["auto_decompose"], resolve(project, ctx), request, root_id=root_id, assignee=assignee,
            executor=executor, depth=depth, model=model, fast=fast, _progress=prog))
        return _with_ui_link("auto_decompose", out, project, ctx)

    auto_decompose.__doc__ = T.auto_decompose.__doc__
    # `from __future__ import annotations` stringifies hints and Context is imported locally — hand the
    # SDK real types so its schema introspection can evaluate the signature.
    auto_decompose.__annotations__ = {"request": str, "root_id": str, "assignee": Optional[str],
                                      "executor": Optional[str],
                                      "depth": int, "model": str, "fast": bool,
                                      "project": Optional[str], "ctx": Context, "return": dict}
    return auto_decompose


def _bind_validate_result(engine_or_registry):  # pragma: no cover — exercised live over MCP
    """validate_result spawns a tool-using validator agent (minutes when it runs real test suites) — same
    async + progress-notification binding as auto_decompose, for the same MCP-timeout reason."""
    # LEFT: the MCP SDK is optional AT IMPORT (see `_bind`).
    from mcp.server.fastmcp import Context
    resolve = _resolver(engine_or_registry)

    async def validate_result(task_id: str, deliverable: str = None, model: str = MODEL_DEFAULT,
                            workdir: str = None, project: str = None, ctx: Context = None) -> dict:
        """Run the independent validator over a delivery and record the verdict it produces.

        Minutes-long for the same reason as the decomposition verb above; the verdict it records
        is the instrument's, never the caller's.
        """
        loop = asyncio.get_running_loop()
        step = {"n": 0}

        def prog(msg: str) -> None:  # called from the executor thread
            """Push one progress line to the client from the worker thread."""
            step["n"] += 1
            if ctx is not None:
                try:
                    asyncio.run_coroutine_threadsafe(
                        ctx.report_progress(step["n"], None, f"[validate_result] {msg}"), loop)
                except Exception:
                    pass  # progress is presentation — never break the pipeline

        return await _awaited_with_a_heartbeat(loop, ctx, "[validate_result]", step, functools.partial(
            T.TOOLS["validate_result"], resolve(project, ctx), task_id, deliverable=deliverable, model=model,
            workdir=workdir, _progress=prog))

    validate_result.__doc__ = T.validate_result.__doc__
    validate_result.__annotations__ = {"task_id": str, "deliverable": Optional[str], "model": str,
                                     "workdir": Optional[str], "project": Optional[str],
                                     "ctx": Context, "return": dict}
    return validate_result


def _mount_project_delete(server, reg) -> None:
    """The one DESTRUCTIVE project verb, mounted apart from the reads.

    It carries a rule the other two do not: it refuses to delete the ground the CALLER
    stands on, which is why it needs the session at all. Kept separate so that rule is not
    read as incidental to listing and switching.
    """
    # LEFT: the MCP SDK is optional AT IMPORT (see `_bind`).
    from mcp.server.fastmcp import Context as _Ctx

    def delete_project(name: str = "", project: str = "", ctx: _Ctx = None) -> dict:
        """Delete a NAMED project irreversibly (its graph, audit log and DB file). Refused for
        `default`, for the server's active project and for YOUR SESSION's current project —
        switch away first (`use_project`): deleting the ground you stand on is the misclick
        this refusal exists for.

        Takes `project=` like every other verb; `name=` is the older spelling and still works."""
        name = name or project
        if not name:
            return {"error": "delete_project needs the project: delete_project(project='…')"}
        key = _session_key(ctx)
        if key is not None and _SESSION_PROJECTS.get(key) == name:
            raise ValueError(f"{name!r} is your session's current project — use_project away first")
        out = reg.delete(name)
        for k, v in list(_SESSION_PROJECTS.items()):   # sessions pointing at the dead project
            if v == name:                              # fall back to the registry's active
                del _SESSION_PROJECTS[k]
        return out

    delete_project.__annotations__ = {"name": str, "project": str, "ctx": _Ctx,
                                      "return": dict}
    server.add_tool(delete_project, name="delete_project",
                    description=(delete_project.__doc__ or "").strip())


def _mount_project_verbs(server, reg) -> None:
    """The three verbs that are about WHICH graph a session stands in, not about a graph.

    Registered only when a registry is present, and kept apart from `create_server` because
    they answer a different question from every other verb — and because the assembly of a
    server should read as an assembly.
    """
    # LEFT: the MCP SDK is optional AT IMPORT (see `_bind`).
    from mcp.server.fastmcp import Context as _Ctx

    def use_project(name: str = "", project: str = "", ctx: _Ctx = None) -> dict:
        """Switch YOUR SESSION's project (a separate GRAPH in its own DB file; created on first
        use). Several agent sessions share this server — each holds its own current project, so
        switching never affects the others; all your verbs default to it (`project` on any verb
        overrides per-call). A Dep across projects is not representable — if two goals need a Dep
        edge, they belong in ONE project.

        Takes `name` or `project` — every OTHER verb spells it `project`, and this one alone
        wanted `name`, which cost a caller a failed call for no reason anyone could infer."""
        name = name or project
        if not name:
            return {"error": "use_project needs the project's name: use_project(project='…') "
                             "(or `name=`, the older spelling — both work)"}
        reg.engine(name)                              # validates the name + creates lazily
        key = _session_key(ctx)
        if key is not None:
            _SESSION_PROJECTS[key] = name
        else:                                         # no session (bare transport) → global active
            reg.use(name)
        # Switching projects answers "which one am I in now", so it returns that and a short
        # recent list — not the whole registry. Measured on this server: 270 projects plus a
        # full last-active map, several thousand tokens of noise into the caller's context on
        # every switch, for a one-line action. The count is kept so the trim is visible rather
        # than silent, and `list_projects` remains the verb for the full inventory.
        return _with_ui_link("use_project", _brief(reg.list(), name))

    def list_projects(limit: int = 25, match: str = "", ctx: _Ctx = None) -> dict:
        """{active, projects, total}: the isolated project graphs this server owns (one DB file
        each), MOST RECENTLY WORKED IN FIRST; `active` = YOUR session's current project.
        `limit` (default 25, 0 = all) and `match` (substring) trim it.

        The full list used to come back whole, with a name→timestamp map beside it: measured
        2026-08-20, ~300 ids and ~15KB into a caller's context for a question that wanted a
        handful of recent names. An installation with a history has hundreds of finished runs
        and probes in it, and none of them are deleted — they are the provenance of past
        measurements — so the answer trims instead."""
        out = reg.list()
        key = _session_key(ctx)
        if key is not None and key in _SESSION_PROJECTS:
            out["active"] = _SESSION_PROJECTS[key]
        names = [n for n in out["projects"] if not match or match in n]
        out["total"] = len(names)
        if limit and len(names) > limit:
            out["note"] = (f"{len(names)} projects; showing the {limit} most recently worked in. "
                           f"`limit=0` for all, `match=<substring>` to filter.")
            names = names[:limit]
        out["projects"] = names
        out["last_active"] = {n: out["last_active"][n] for n in names if n in out["last_active"]}
        return out

    use_project.__annotations__ = {"name": str, "project": str, "ctx": _Ctx, "return": dict}
    list_projects.__annotations__ = {"limit": int, "match": str, "ctx": _Ctx, "return": dict}
    server.add_tool(use_project, name="use_project", description=(use_project.__doc__ or "").strip())
    server.add_tool(list_projects, name="list_projects", description=(list_projects.__doc__ or "").strip())
    _mount_project_delete(server, reg)


def create_server(engine_or_registry):
    """Register every tools.py function on a FastMCP server (a bare Engine or a ProjectRegistry —
    with a registry every tool gains the optional `project` param + the use_project/list_projects
    verbs). Raises if the MCP SDK is absent."""
    try:
        # LEFT: the MCP SDK is optional AT IMPORT — this except is what turns its absence into the
        # message below instead of an ImportError on `import gfso.mcp.server`.
        from mcp.server.fastmcp import FastMCP
    except ImportError as e:  # pragma: no cover
        raise RuntimeError("MCP SDK not installed — reinstall the package: `pip install gfso`") from e
    # The user-agent's protocol travels as the server's INSTRUCTIONS (delivered at initialize) — the
    # agent starts knowing WHAT GFSO is and HOW to drive it, not just 25 bare tool schemas. One source
    # of truth: gfso/mcp/ORCHESTRATOR.md.
    #
    # Read UNGUARDED. A swallowed OSError here handed the agent an empty protocol on any install
    # whose wheel lacked the file, and the server looked healthy from every angle — 32 tools, clean
    # initialize, instructions "". tests/test_packaging.py keeps the file in the distribution; if it
    # is ever missing, a traceback is the correct outcome.
    protocol = (Path(__file__).parent / "ORCHESTRATOR.md").read_text(encoding="utf-8")
    server = FastMCP("gfso", instructions=protocol)
    # NOTE: the two bindings below call `T.TOOLS[...]`, not the module functions — the registry
    # entries are the ones wrapped to announce themselves in INFLIGHT. Bound to the bare functions,
    # `/api/runtime` reported `busy: []` throughout a decomposition or a validator run, which is
    # exactly the window in which another session's reconcile must not restart the server.
    long_running = {"auto_decompose": _bind_auto_decompose, "validate_result": _bind_validate_result}
    for name, fn in T.TOOLS.items():
        if name in long_running:  # minutes-long: async + MCP progress notifications
            server.add_tool(long_running[name](engine_or_registry), name=name,
                            description=(fn.__doc__ or "").strip())
            continue
        server.add_tool(_bind(engine_or_registry, fn), name=name, description=(fn.__doc__ or "").strip())
    if hasattr(engine_or_registry, "use"):    # ProjectRegistry → the project verbs
        _mount_project_verbs(server, engine_or_registry)
    _add_agent_verbs(server, engine_or_registry)
    return server


def _add_agent_verbs(server, engine_or_registry) -> None:
    """The delegation roster: register_agent / list_agents + the autostart dispatchers. Delegation is
    NOT a verb — the issuer's only act is setting Del (assignee) to a registered llm-executor; the
    dispatcher picks the node up from the frontier, spawns the executor, wraps its signals, and
    auto-validates the delivery with the registered llm-validator (verdict auto-signals; an unparsed
    verdict escalates)."""
    resolve = _resolver(engine_or_registry)
    # ProjectRegistry engines attach their dispatchers at creation (runtime); a BARE engine
    # (tests / single-project embedding) gets one here.
    if not hasattr(engine_or_registry, "engine"):
        ensure_dispatcher(engine_or_registry, default_agents())

    def register_agent(agent_id: str, kind: str, model: str = MODEL_DEFAULT,
                       workdir: str = None, validator: str = None,
                       oracle_map: str = None, max_turns: int = None,
                       client: str = None, project: str = None, ctx=None) -> dict:
        """Register a non-human participant — the shared verb, presented on this door."""
        return T.TOOLS["register_agent"](
            resolve(project, ctx), agent_id, kind, model=model, workdir=workdir,
            validator=validator, oracle_map=oracle_map, max_turns=max_turns, client=client)

    def list_agents(project: str = None, match: str = "", limit: int = 25, ctx=None) -> dict:
        """The delegation roster — the shared verb, presented on this door."""
        return T.TOOLS["list_agents"](resolve(project, ctx), match=match, limit=limit)

    # One implementation, four doors: the verbs live in the shared registry (`gfso.tools_llm`) and
    # this binding only presents them. They used to live HERE and nowhere else, so a person on the
    # CLI or the HTTP API could not register a role at all — while the log told them to reassign
    # work to one (measured 2026-08-21).
    register_agent.__doc__ = T.TOOLS["register_agent"].__doc__ or T.register_agent.__doc__
    list_agents.__doc__ = T.list_agents.__doc__
    register_agent.__annotations__ = {"agent_id": str, "kind": str, "model": str,
                                      "workdir": Optional[str], "validator": Optional[str],
                                      "oracle_map": Optional[str], "max_turns": Optional[int],
                                      "client": Optional[str], "project": Optional[str],
                                      "return": dict}
    list_agents.__annotations__ = {"project": Optional[str], "match": str, "limit": int,
                                   "return": dict}
    server.add_tool(register_agent, name="register_agent", description=(register_agent.__doc__ or "").strip())
    server.add_tool(list_agents, name="list_agents", description=(list_agents.__doc__ or "").strip())


def _serve_ui(registry, host: str, port: int) -> None:  # pragma: no cover
    """Serve the HTTP + UI + WebSocket over the SAME registry in a daemon thread, so the human watches the
    agent's MCP mutations LIVE (and follows use_project switches). All logging → stderr: stdout is the MCP
    stdio channel and MUST stay clean (a stray print would corrupt the JSON-RPC stream)."""
    # with_mcp=False — the MCP surface is this stdio process; the app is UI-only
    app = create_app(registry.engine(), registry=registry)
    config = uvicorn.Config(app, host=host, port=port, log_level="warning",
                            access_log=False, log_config=None)  # log_config=None → root logger (stderr)
    threading.Thread(target=uvicorn.Server(config).run, daemon=True).start()
    print(f"[gfso mcp] UI live at http://{host}:{port}", file=sys.stderr)


def main() -> None:  # pragma: no cover
    """Serve the MCP surface over stdio against this installation's project registry."""
    registry = ProjectRegistry()
    registry.engine()  # materialize the default project up front
    if ui_enabled():
        try:
            _serve_ui(registry, *ui_address())
        except Exception as e:
            print(f"[gfso mcp] UI not started ({e}) — MCP tools still work", file=sys.stderr)
    create_server(registry).run()  # blocks on the stdio MCP loop


if __name__ == "__main__":  # pragma: no cover
    main()
