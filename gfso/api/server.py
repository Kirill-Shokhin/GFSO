"""FastAPI application — GFSO HTTP API + WebSocket + static UI."""
from __future__ import annotations

import asyncio
import uuid
from pathlib import Path
from typing import Optional

from fastapi import FastAPI, WebSocket, WebSocketDisconnect, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse

from gfso.core.types import TaskId, AgentId, Signal, State, CriterionMapping
from gfso.engine import Engine

from .models import (
    CreateTaskRequest, SendSignalRequest, DecomposeRequest,
    TaskOut, TaskDetailOut, CheckResultOut, RecommendationOut,
    GraphOut, GraphNode, GraphEdge, MetricsOut, AuditEntryOut,
    SuggestCriteriaRequest, SuggestCriteriaResponse, CriteriaIn,
    spec_in_to_spec, task_to_out, audit_to_out, signal_request_to_data,
)

WEB_DIR = Path(__file__).parent.parent / "web"


def create_app(engine: Engine) -> FastAPI:
    app = FastAPI(title="GFSO", version="0.2.0")
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

    # === Task CRUD ===

    @app.post("/api/tasks", response_model=TaskOut, status_code=201)
    def create_task(req: CreateTaskRequest):
        e: Engine = app.state.engine
        task_id = TaskId(req.task_id or str(uuid.uuid4())[:8])
        spec = spec_in_to_spec(req.spec)
        e.assign_task(
            task_id, spec, AgentId(req.assignee),
            parent_id=TaskId(req.parent_id) if req.parent_id else None,
            max_iterations=req.max_iterations,
        )
        e.wait_idle()
        task = e.get_task(task_id)
        return task_to_out(task)

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

    # === Signals ===

    @app.post("/api/tasks/{task_id}/signal", response_model=AuditEntryOut)
    def send_signal(task_id: str, req: SendSignalRequest):
        e: Engine = app.state.engine
        data = signal_request_to_data(task_id, req)
        entry = e.send_signal_sync(data, timeout=5.0)
        if entry is None:
            raise HTTPException(504, "signal processing timed out")
        return audit_to_out(entry)

    @app.post("/api/tasks/{task_id}/decompose", response_model=list[TaskOut])
    def decompose_task(task_id: str, req: DecomposeRequest):
        e: Engine = app.state.engine
        children_specs = []
        for c in req.children:
            cid = TaskId(c.task_id or str(uuid.uuid4())[:8])
            spec = spec_in_to_spec(c.spec)
            children_specs.append((cid, spec, AgentId(c.assignee)))
        mappings = [CriterionMapping(m.criterion_name, TaskId(m.child_id)) for m in req.criterion_mappings] or None
        tasks = e.decompose_task(TaskId(task_id), children_specs, mappings)
        return [task_to_out(t) for t in tasks]

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
                id=t.id, label=t.spec.description[:40],
                state=t.state.name, assignee=t.assignee,
                parent_id=t.parent_id, has_children=has_children,
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

    return app


def _create_engine_from_env() -> Engine:
    """Create engine from environment variables (for uvicorn reload mode)."""
    import os
    storage_type = os.environ.get("GFSO_STORAGE", "memory")
    if storage_type == "sqlite":
        from gfso.adapters.storage.sqlite import SqliteStorage
        storage = SqliteStorage(os.environ.get("GFSO_DB_PATH", "gfso.db"))
    else:
        from gfso.adapters.storage.memory import MemoryStorage
        storage = MemoryStorage()

    llm_type = os.environ.get("GFSO_LLM", "stub")
    if llm_type == "claude":
        from gfso.adapters.llm.claude import ClaudeLLM
        llm = ClaudeLLM(
            api_key=os.environ.get("GFSO_API_KEY") or None,
            model=os.environ.get("GFSO_MODEL", "claude-haiku-4-5-20251001"),
        )
    else:
        from gfso.adapters.llm.stub import StubLLM
        llm = StubLLM()

    from gfso.adapters.agents.human import HumanAgent

    # Seed with stub LLM for fast startup, then switch to real LLM
    needs_seed = not os.environ.get("GFSO_NO_SEED")
    engine = Engine(storage=storage, agents=HumanAgent(), llm=None, validate_signals=False)
    engine.start()

    if needs_seed and not engine.all_tasks():
        from gfso.demo import seed_demo
        seed_demo(engine)

    engine._llm = llm

    return engine


# Module-level app for uvicorn reload mode: `uvicorn gfso.api.server:app --reload`
app = create_app(_create_engine_from_env())
