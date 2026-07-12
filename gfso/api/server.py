"""FastAPI application — GFSO HTTP API + WebSocket + static UI."""
from __future__ import annotations

import asyncio
import os
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Optional

from fastapi import FastAPI, WebSocket, WebSocketDisconnect, HTTPException, Body
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse

from gfso.core.types import TaskId, AgentId, State
from gfso.core.protocol.validation import required_role
from gfso.engine import Engine
from gfso import tools_llm as _tools  # the COMPLETE action surface (structural + LLM) — the HTTP mutation surface is generated from it

from .models import (
    TaskOut, TaskDetailOut, CheckResultOut, RecommendationOut,
    GraphOut, GraphNode, GraphEdge, MetricsOut, AuditEntryOut,
    SuggestCriteriaRequest, SuggestCriteriaResponse, CriteriaIn,
    ActionOut, SolverItem, SolverOut, ProjectionOut,
    task_to_out, audit_to_out,
)

WEB_DIR = Path(__file__).parent.parent / "web"


def _build_mcp(engine: Engine):
    """MCP server + its streamable-HTTP ASGI app over the SAME Engine instance.
    Returns (mcp, asgi) or (None, None) if the MCP SDK isn't installed (`pip install gfso[mcp]`)."""
    try:
        from gfso.mcp.server import create_server
        mcp = create_server(engine)  # raises RuntimeError if the SDK is absent
    except (RuntimeError, ImportError):
        return None, None
    # the streamable app routes internally at settings.streamable_http_path (default "/mcp"); set it to "/"
    # so mounting the sub-app at "/mcp" yields exactly "/mcp" (not "/mcp/mcp").
    mcp.settings.streamable_http_path = "/"
    return mcp, mcp.streamable_http_app()


def _start_reaper(app, grace: float = 12.0, interval: float = 3.0) -> None:
    """Self-shutdown loop: once ANY lease has existed, zero live leases for `grace` seconds ⟹ the
    last Claude session is gone → exit (the next session's connect.py respawns a fresh server)."""
    import threading, time

    def _loop():
        had_any = False
        while True:
            time.sleep(interval)
            now = time.monotonic()
            live = [k for k, ts in list(app.state.leases.items()) if now - ts <= grace]
            for k in list(app.state.leases):
                if k not in live:
                    app.state.leases.pop(k, None)
            if live:
                had_any = True
            elif had_any:
                print("[gfso] last session gone — shutting down", flush=True)
                app.state.exit_fn()
                return
    threading.Thread(target=_loop, daemon=True).start()


def create_app(engine: Engine, with_mcp: bool = False, registry=None) -> FastAPI:
    mcp, mcp_asgi = _build_mcp(registry or engine) if with_mcp else (None, None)

    lifespan = None
    if mcp is not None:
        @asynccontextmanager
        async def lifespan(_app):  # the streamable transport needs its session manager running
            async with mcp.session_manager.run():
                yield

    app = FastAPI(title="GFSO", version="0.2.0", lifespan=lifespan)
    app.state.engine = engine
    app.state.registry = registry
    app.state.ws_clients = set()      # one asyncio.Queue per live WS — for GLOBAL broadcasts (project list)
    app.state.loop = None
    if registry is not None:
        # A new project is a REGISTRY event, not a per-project transition — so it rides no single WS. Push it
        # to EVERY connected client (event-driven, no poll): each refreshes its project list on receipt.
        def _broadcast_projects(_name=None):
            loop = app.state.loop
            if loop is None:
                return
            for q in list(app.state.ws_clients):
                loop.call_soon_threadsafe(q.put_nowait, {"type": "projects"})
        registry._on_create = _broadcast_projects

    # Per-TAB project view: every request may carry ?project=<name> (the UI appends its tab's project
    # to all /api calls and the WS url) — two browser tabs can watch two projects simultaneously.
    import contextvars
    _req_project: contextvars.ContextVar = contextvars.ContextVar("gfso_project", default=None)

    @app.middleware("http")
    async def _project_scope(request, call_next):
        token = _req_project.set(request.query_params.get("project") or None)
        try:
            return await call_next(request)
        finally:
            _req_project.reset(token)

    def _e() -> Engine:
        """The request-time engine: the ?project= tab scope → the registry's ACTIVE project → the
        single bound engine."""
        if app.state.registry:
            return app.state.registry.engine(_req_project.get())
        return app.state.engine

    app.add_middleware(
        CORSMiddleware,
        allow_origins=["*"], allow_methods=["*"], allow_headers=["*"],
    )

    # === Static UI ===

    @app.get("/")
    async def index():
        return FileResponse(WEB_DIR / "index.html")

    @app.get("/tokens.css")
    async def tokens_css():
        return FileResponse(WEB_DIR / "tokens.css", media_type="text/css")

    @app.get("/gfso.css")
    async def gfso_css():
        return FileResponse(WEB_DIR / "gfso.css", media_type="text/css")

    @app.get("/icon.svg")
    async def icon_svg():
        return FileResponse(WEB_DIR / "icon.svg", media_type="image/svg+xml")

    # === Task CRUD (create/mutate = /api/run/<tool>; reads stay bespoke) ===

    @app.get("/api/tasks", response_model=list[TaskOut])
    def list_tasks(state: Optional[str] = None, assignee: Optional[str] = None):
        e: Engine = _e()
        if state:
            tasks = e.tasks_by_state(State[state])
        elif assignee:
            tasks = e.tasks_by_assignee(AgentId(assignee))
        else:
            tasks = e.all_tasks()
        return [task_to_out(t) for t in tasks]

    @app.get("/api/tasks/{task_id}", response_model=TaskDetailOut)
    def get_task(task_id: str):
        e: Engine = _e()
        t = e.get_task(TaskId(task_id))
        if t is None:
            raise HTTPException(404, f"task {task_id} not found")
        checks = e.get_checks(TaskId(task_id))
        rec = e.graph._storage.get_recommendation(TaskId(task_id))
        audit = e.audit_log(TaskId(task_id))
        children = e.get_children(TaskId(task_id))
        out = task_to_out(t)
        return TaskDetailOut(
            **out.model_dump(),
            checks=[CheckResultOut(check_name=c.check_name, passed=c.passed, details=c.details, skipped=c.skipped) for c in checks],
            recommendation=RecommendationOut(suggestions=list(rec.suggestions)) if rec else None,
            audit=[audit_to_out(a) for a in audit],
            children=[task_to_out(c) for c in children],
        )

    # === Unified authoring surface: every gfso tool over HTTP (the SAME gfso.tools.TOOLS that MCP + CLI bind) ===
    # Adding an authoring verb = ONE Engine method + ONE gfso.tools entry → it appears HERE, on MCP, and on the
    # CLI with zero per-adapter edits (no duplicate route to keep in sync). Reads keep their bespoke typed routes
    # above; only the action/mutation surface is generated. body = the tool's kwargs as JSON.
    @app.post("/api/run/{tool}")
    def run_tool(tool: str, body: dict = Body(default={})):
        e: Engine = _e()
        fn = _tools.TOOLS.get(tool)
        if fn is None:
            raise HTTPException(404, f"unknown tool '{tool}'")
        try:
            return fn(e, **(body or {}))
        except (ValueError, TypeError, KeyError) as ex:
            raise HTTPException(422, str(ex))

    # === Per-role actions (§6.2) ===

    @app.get("/api/tasks/{task_id}/actions", response_model=list[ActionOut])
    def get_actions(task_id: str, role: Optional[str] = None):
        e: Engine = _e()
        if e.get_task(TaskId(task_id)) is None:
            raise HTTPException(404, f"task {task_id} not found")
        sigs = e.available_actions(TaskId(task_id), AgentId(role) if role else None)
        return [ActionOut(signal=s.name, role=required_role(s).name) for s in sigs]

    # === Projection (read-only critic input contract) ===

    @app.get("/api/tasks/{task_id}/projection", response_model=ProjectionOut)
    def get_projection(task_id: str):
        e: Engine = _e()
        if e.get_task(TaskId(task_id)) is None:
            raise HTTPException(404, f"task {task_id} not found")
        return ProjectionOut(node_id=task_id, projection=e.project(TaskId(task_id)))

    # === L2 critic / validation (POST validate = /api/run/validate) ===

    @app.get("/api/tasks/{task_id}/critique")
    def get_critique(task_id: str):
        e: Engine = _e()
        t = e.get_task(TaskId(task_id))
        if t is None:
            raise HTTPException(404, f"task {task_id} not found")
        return {"verified": t.verified, "critique": e.get_critique(TaskId(task_id))}

    # === Solver (§7.3 — deterministic, separate from LLM) ===

    @app.get("/api/tasks/{task_id}/solver", response_model=SolverOut)
    def get_solver(task_id: str):
        from gfso.core.handlers import solver_findings
        e: Engine = _e()
        if e.get_task(TaskId(task_id)) is None:
            raise HTTPException(404, f"task {task_id} not found")
        ctx = e.graph.build_context(TaskId(task_id))
        return SolverOut(recommendations=[SolverItem(**f) for f in solver_findings(ctx)])

    @app.get("/api/holes")
    def get_holes(root_id: Optional[str] = None):
        """Every unmet structural check across the graph (or a subtree) — the whole-graph gap list."""
        e: Engine = _e()
        return e.graph_holes(TaskId(root_id) if root_id else None)

    # === Graph ===

    @app.get("/api/graph", response_model=GraphOut)
    def get_graph():
        e: Engine = _e()
        all_tasks = e.all_tasks()
        nodes = []
        edges = []
        children_set = set()
        for t in all_tasks:
            if t.parent_id:
                children_set.add(t.parent_id)
        for t in all_tasks:
            has_children = t.id in children_set or bool(e.get_children(t.id))
            nodes.append(GraphNode(
                id=t.id, label=(t.spec.name or t.spec.description[:40]),
                state=t.state.name, assignee=t.assignee,
                parent_id=t.parent_id, has_children=has_children,
                done_reason=t.done_reason.name if t.done_reason else None,
            ))
            if t.parent_id:
                edges.append(GraphEdge(source=t.parent_id, target=t.id, type="parent-child"))
        for dep in e.get_dependencies():
            edges.append(GraphEdge(source=dep.from_id, target=dep.to_id, type="dependency", discovered=dep.discovered))
        return GraphOut(nodes=nodes, edges=edges)

    # === AI Suggest ===

    @app.post("/api/suggest-criteria", response_model=SuggestCriteriaResponse)
    def suggest_criteria_endpoint(req: SuggestCriteriaRequest):
        from gfso.core.handlers.recommend import suggest_criteria
        e: Engine = _e()
        results = suggest_criteria(req.description, e._llm)
        return SuggestCriteriaResponse(
            criteria=[CriteriaIn(name=n, description=d) for n, d in results]
        )

    # === Metrics ===

    @app.get("/api/metrics", response_model=MetricsOut)
    def get_metrics():
        m = _e().metrics()
        return MetricsOut(**m)

    # === Audit ===

    @app.get("/api/audit", response_model=list[AuditEntryOut])
    def get_audit(task_id: Optional[str] = None):
        e: Engine = _e()
        tid = TaskId(task_id) if task_id else None
        return [audit_to_out(a) for a in e.audit_log(tid)]

    # === Pipeline observation history (persisted; ticks excluded at the writer) ===

    @app.get("/api/pipeline")
    def get_pipeline(limit: int = 500):
        return _e().pipeline_log(limit)

    # === Lifecycle: session leases + self-shutdown (the shared-server automation) ===
    # Every connect.py bridge (one per Claude session) heartbeats a lease; when the LAST lease
    # expires the server exits itself (only under GFSO_AUTOEXIT=1 — how connect.py spawns it;
    # a manually run `gfso serve` never self-terminates). `gfso down` → POST /api/shutdown for
    # code updates: the next session reconnect auto-spawns a fresh server.
    app.state.leases = {}
    app.state.exit_fn = (lambda: os._exit(0))

    @app.post("/api/lease")
    def renew_lease(body: dict = Body(...)):
        import time as _t
        app.state.leases[str(body.get("id", "?"))] = _t.monotonic()
        return {"ok": True, "sessions": len(app.state.leases)}

    @app.delete("/api/lease/{lease_id}")
    def drop_lease(lease_id: str):
        app.state.leases.pop(lease_id, None)
        return {"ok": True, "sessions": len(app.state.leases)}

    @app.post("/api/shutdown")
    def shutdown():
        import threading as _th
        _th.Timer(0.3, app.state.exit_fn).start()   # answer first, then exit
        return {"ok": True, "bye": True}

    if os.environ.get("GFSO_AUTOEXIT") == "1":
        _start_reaper(app)

    # === Delegation roster (read view; registration = the MCP verb) ===

    @app.get("/api/agents")
    def get_agents():
        from gfso.delegate import AgentRegistry
        return AgentRegistry().list()

    # === Projects (multi-project registry; single-project servers report just "default") ===

    @app.get("/api/projects")
    def get_projects():
        reg = app.state.registry
        return reg.list() if reg else {"active": "default", "projects": ["default"]}

    @app.post("/api/projects/use")
    def use_project(body: dict = Body(...)):
        reg = app.state.registry
        if reg is None:
            raise HTTPException(400, "single-project server (no registry)")
        try:
            reg.use(body["name"])
        except (KeyError, ValueError) as ex:
            raise HTTPException(422, str(ex))
        return reg.list()

    # === WebSocket ===

    @app.websocket("/ws/events")
    async def websocket_events(websocket: WebSocket):
        await websocket.accept()
        # the tab's project rides the WS url too (middleware covers HTTP only)
        proj = websocket.query_params.get("project") or None
        eng: Engine = app.state.registry.engine(proj) if app.state.registry else app.state.engine
        loop = asyncio.get_event_loop()
        app.state.loop = loop
        q: asyncio.Queue = asyncio.Queue()
        app.state.ws_clients.add(q)          # join the global broadcast set (project-list events)

        def on_transition(tid, old, new, sig):
            loop.call_soon_threadsafe(q.put_nowait, {
                "type": "transition", "task_id": str(tid),
                "old_state": old.name, "new_state": new.name, "signal": sig.name,
            })

        def on_reject(tid, sig, state):
            loop.call_soon_threadsafe(q.put_nowait, {
                "type": "reject", "task_id": str(tid),
                "signal": sig.name, "state": state.name,
            })

        def on_info(source, message):
            loop.call_soon_threadsafe(q.put_nowait, {
                "type": "pipeline", "source": source, "msg": message,
            })

        eng.on_transition(on_transition)
        eng.on_reject(on_reject)
        eng.on_info(on_info)
        try:
            while True:
                event = await q.get()
                await websocket.send_json(event)
        except WebSocketDisconnect:
            pass
        finally:
            app.state.ws_clients.discard(q)
            if on_transition in eng._events._on_transition:
                eng._events._on_transition.remove(on_transition)
            if on_reject in eng._events._on_reject:
                eng._events._on_reject.remove(on_reject)
            if on_info in eng._events._on_info:
                eng._events._on_info.remove(on_info)

    if mcp_asgi is not None:
        app.mount("/mcp", mcp_asgi)  # agent surface, SAME Engine the UI's WebSocket observes

    return app


# Module-level app for `gfso serve` / uvicorn: the SHARED-SERVER entry point — ONE process owns the
# CORE; the human's UI, the WebSocket, and (GFSO_WITH_MCP=1) the MCP agent surface at /mcp all observe
# the SAME engines, so live events (token ticks, active processes) reach every client. This is the
# recommended shape when several agent sessions work in parallel: point their MCP config at
# http://127.0.0.1:8000/mcp instead of spawning a stdio server per session (a second stdio process
# shares the DB file but NOT the event bus — its live ticks are invisible to the UI).
from gfso.runtime import ProjectRegistry as _PR
_registry = _PR(default_storage="memory", default_llm="stub",
                seed=not os.environ.get("GFSO_NO_SEED"))
app = create_app(_registry.engine(), with_mcp=os.environ.get("GFSO_WITH_MCP") == "1",
                 registry=_registry)
