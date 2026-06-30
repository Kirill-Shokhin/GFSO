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
from gfso import tools as _tools   # the shared action surface — the HTTP mutation surface is generated from it
from gfso.runtime import build_engine_from_env   # the ONE Engine factory (shared with MCP + CLI)

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


def create_app(engine: Engine, with_mcp: bool = False) -> FastAPI:
    mcp, mcp_asgi = _build_mcp(engine) if with_mcp else (None, None)

    lifespan = None
    if mcp is not None:
        @asynccontextmanager
        async def lifespan(_app):  # the streamable transport needs its session manager running
            async with mcp.session_manager.run():
                yield

    app = FastAPI(title="GFSO", version="0.2.0", lifespan=lifespan)
    app.state.engine = engine

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
        e: Engine = app.state.engine
        if state:
            tasks = e.tasks_by_state(State[state])
        elif assignee:
            tasks = e.tasks_by_assignee(AgentId(assignee))
        else:
            tasks = e.all_tasks()
        return [task_to_out(t) for t in tasks]

    @app.get("/api/tasks/{task_id}", response_model=TaskDetailOut)
    def get_task(task_id: str):
        e: Engine = app.state.engine
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
        e: Engine = app.state.engine
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
        e: Engine = app.state.engine
        if e.get_task(TaskId(task_id)) is None:
            raise HTTPException(404, f"task {task_id} not found")
        sigs = e.available_actions(TaskId(task_id), AgentId(role) if role else None)
        return [ActionOut(signal=s.name, role=required_role(s).name) for s in sigs]

    # === Projection (read-only critic input contract) ===

    @app.get("/api/tasks/{task_id}/projection", response_model=ProjectionOut)
    def get_projection(task_id: str):
        e: Engine = app.state.engine
        if e.get_task(TaskId(task_id)) is None:
            raise HTTPException(404, f"task {task_id} not found")
        return ProjectionOut(node_id=task_id, projection=e.project(TaskId(task_id)))

    # === L2 critic / validation (POST validate = /api/run/validate) ===

    @app.get("/api/tasks/{task_id}/critique")
    def get_critique(task_id: str):
        e: Engine = app.state.engine
        t = e.get_task(TaskId(task_id))
        if t is None:
            raise HTTPException(404, f"task {task_id} not found")
        return {"verified": t.verified, "critique": e.get_critique(TaskId(task_id))}

    # === Solver (§7.3 — deterministic, separate from LLM) ===

    @app.get("/api/tasks/{task_id}/solver", response_model=SolverOut)
    def get_solver(task_id: str):
        from gfso.core.handlers import solver_findings
        e: Engine = app.state.engine
        if e.get_task(TaskId(task_id)) is None:
            raise HTTPException(404, f"task {task_id} not found")
        ctx = e.graph.build_context(TaskId(task_id))
        return SolverOut(recommendations=[SolverItem(**f) for f in solver_findings(ctx)])

    @app.get("/api/holes")
    def get_holes(root_id: Optional[str] = None):
        """Every unmet structural check across the graph (or a subtree) — the whole-graph gap list."""
        e: Engine = app.state.engine
        return e.graph_holes(TaskId(root_id) if root_id else None)

    # === Graph ===

    @app.get("/api/graph", response_model=GraphOut)
    def get_graph():
        e: Engine = app.state.engine
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
        e: Engine = app.state.engine
        results = suggest_criteria(req.description, e._llm)
        return SuggestCriteriaResponse(
            criteria=[CriteriaIn(name=n, description=d) for n, d in results]
        )

    # === Metrics ===

    @app.get("/api/metrics", response_model=MetricsOut)
    def get_metrics():
        m = app.state.engine.metrics()
        return MetricsOut(**m)

    # === Audit ===

    @app.get("/api/audit", response_model=list[AuditEntryOut])
    def get_audit(task_id: Optional[str] = None):
        e: Engine = app.state.engine
        tid = TaskId(task_id) if task_id else None
        return [audit_to_out(a) for a in e.audit_log(tid)]

    # === WebSocket ===

    @app.websocket("/ws/events")
    async def websocket_events(websocket: WebSocket):
        await websocket.accept()
        eng: Engine = app.state.engine
        loop = asyncio.get_event_loop()
        q: asyncio.Queue = asyncio.Queue()

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

        eng.on_transition(on_transition)
        eng.on_reject(on_reject)
        try:
            while True:
                event = await q.get()
                await websocket.send_json(event)
        except WebSocketDisconnect:
            pass
        finally:
            if on_transition in eng._events._on_transition:
                eng._events._on_transition.remove(on_transition)
            if on_reject in eng._events._on_reject:
                eng._events._on_reject.remove(on_reject)

    if mcp_asgi is not None:
        app.mount("/mcp", mcp_asgi)  # agent surface, SAME Engine the UI's WebSocket observes

    return app


# Module-level app for uvicorn reload mode: `uvicorn gfso.api.server:app --reload`.
# Uses the ONE shared Engine factory with the `serve` profile (memory-default, stub LLM, demo seed). The agent
# (MCP) and the human (UI) share this one Engine — neither may bypass the protocol (validate_signals=True).
# GFSO_WITH_MCP=1 also mounts the MCP agent surface at /mcp over the SAME Engine (one process, one CORE).
app = create_app(
    build_engine_from_env(default_storage="memory", default_llm="stub", seed=not os.environ.get("GFSO_NO_SEED")),
    with_mcp=os.environ.get("GFSO_WITH_MCP") == "1",
)
