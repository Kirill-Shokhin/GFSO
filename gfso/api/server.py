"""FastAPI application — GFSO HTTP API + WebSocket + static UI."""
from __future__ import annotations

import asyncio
import json
import os
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Optional

from fastapi import FastAPI, WebSocket, WebSocketDisconnect, HTTPException, Body
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse

from gfso import __version__
from gfso.core.types import TaskId, AgentId, State

# Stamped ONCE, when this process imports its code — not recomputed per request, because the point
# is to report what is LOADED, not what is on disk now. `gfso up` compares the two and restarts on
# a difference, which is how "is the server current" stops being a question anyone has to ask.
from gfso import serverctl as _serverctl
try:
    from gfso.serverctl import source_fingerprint as _sfp
    _CODE_VERSION = _sfp()
except Exception:                                    # never let a diagnostic field break the server
    _CODE_VERSION = "unknown"
from gfso.core.protocol.validation import required_role
from gfso.engine.validation import l2_gate_on as _l2_gate_on
from gfso.tools_llm import validate_internal_on as _validate_internal_on
from gfso import config as _config
from gfso.config import LOOPBACK as _LOOPBACK, DEFAULT_PROJECT
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
    Returns (mcp, asgi) or (None, None) if the MCP SDK isn't installed (it is a required dependency — reinstall the package)."""
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


def _mount_acts(app, _e, _req_project) -> None:
    """The ACTS: the whole verb registry over HTTP, and the criteria suggester.

    A read answers about the graph; an act changes it, and they had one body between them.
    This is the door every verb is generated onto — `gfso.tools_llm.TOOLS` — which is why
    it is one mounting rather than a route each."""
    # above; only the action/mutation surface is generated. body = the tool's kwargs as JSON.
    @app.post("/api/run/{tool}")
    def run_tool(tool: str, body: dict = Body(default={})):
        # `project` in the BODY as well as the query string — the third spelling of one thing. The
        # CLI takes `project=<name>`, `gfso log` takes `--project`, and this door took it only as a
        # query parameter, so a caller who put it where every other argument goes had it passed to
        # the verb as an unknown keyword and got a TypeError about the verb.
        body = dict(body or {})
        if (_in_body := body.pop("project", None)):
            _req_project.set(_in_body)      # the middleware resets its own token after the request
        fn = _tools.TOOLS.get(tool)
        if fn is None:
            raise HTTPException(404, f"unknown tool '{tool}'")
        try:
            # A ROSTER VERB IS NOT ABOUT A GRAPH. It still needs an engine object to be dispatched
            # with, so it takes whichever one is at hand rather than refusing for a project that does
            # not exist — the roster is one server-wide file and says so.
            e: Engine = _e(create=tool in _tools.PROJECT_CREATING_VERBS
                           or tool in _tools.PROJECTLESS_VERBS)
        except KeyError as ex:
            raise HTTPException(404, f"no such project {ex.args[0]!r} — `gfso projects` lists them; "
                                     f"`create_task` or `auto_decompose` starts a new one") from None
        try:
            out = fn(e, **body)
            # A REFUSAL KEEPS ITS STATUS AND ITS SHAPE. The verbs answer rather than raise (one
            # wrapper over the registry, `tools_llm._answering`) so that the MCP and CLI doors get
            # structure instead of an exception — but HTTP has a status code for "I understood you
            # and will not do it", and dropping to 200 would have made every refusal look like a
            # success to anything reading the code alone. The BODY is the verb's own dict either way,
            # which is what the caller reads: the old path re-encoded a JSON error message inside a
            # JSON envelope, and a person got quoted braces to unpick.
            # A STATUS CODE AND AN EXIT CODE ANSWER DIFFERENT QUESTIONS, and this door keeps the
            # HTTP one: 4xx is "this call could not be processed as given" (a shape refusal, an
            # unknown key), while an engine that processed the call and answered "no" is a 200 whose
            # BODY carries the answer. The CLI's exit code is about the ACT — `tools.is_refusal` —
            # and the two differing here is correct, not a drift (the typed-records register read it
            # as one; the distinction is the reason this branch tests `refused`, not `error`).
            if isinstance(out, dict) and (out.get("refused") or out.get("unexpected")):
                from fastapi.responses import JSONResponse
                return JSONResponse(status_code=500 if out.get("unexpected") else 422,
                                    content=json.loads(json.dumps(out, default=str)))
            return out
        except TypeError as ex:
            # A call that does not fit the verb is answered in the verb's OWN terms. Python says
            # "signal() missing 1 required positional argument: 'source'", which hands a user the
            # interpreter's view of a function they never called and no way to know that `source` is
            # who signs the signal. The door knows the signature; it can say what is missing, what
            # else the verb takes, and stay silent about the implementation.
            import inspect
            sig = inspect.signature(fn)
            params = [p for p in list(sig.parameters.values())[1:] if not p.name.startswith("_")]
            required = [p.name for p in params if p.default is inspect.Parameter.empty]
            missing = [n for n in required if n not in (body or {})]
            if missing:
                optional = [p.name for p in params if p.default is not inspect.Parameter.empty]
                raise HTTPException(422, f"{tool} needs {', '.join(missing)}"
                                         + (f" (it also takes {', '.join(optional)})" if optional else ""))
            unknown = [k for k in (body or {}) if k not in {p.name for p in params}]
            if unknown:
                raise HTTPException(422, f"{tool} does not take {', '.join(unknown)} — it takes "
                                         f"{', '.join(p.name for p in params)}")
            raise HTTPException(422, str(ex))
        except (ValueError, KeyError) as ex:
            raise HTTPException(422, str(ex))

    # === Per-role actions (§14.2) ===

    # === AI Suggest ===

    @app.post("/api/suggest-criteria", response_model=SuggestCriteriaResponse)
    def suggest_criteria_endpoint(req: SuggestCriteriaRequest):
        from gfso.core.handlers.recommend import suggest_criteria
        e: Engine = _e()
        results = suggest_criteria(req.description, e._llm)
        return SuggestCriteriaResponse(
            criteria=[CriteriaIn(name=n, description=d) for n, d in results]
        )


def _mount_ledgers(app, _e) -> None:
    """What the RUN cost and what it did: usage, metrics, the audit and pipeline logs.

    A different read from "what does this node look like" — these are about the run rather
    than the graph, and they share a scope (the project whose money and history is being
    asked about)."""
    @app.get("/api/check_map")
    def get_check_map():
        """The canon's CHECK → failure-mode routing (§13.4) and the FM names (§12.6), served so the
        UI renders the product's table instead of a copy of it — the copy drifted (CHECK-6 shown as
        FM-1 where the canon routes it to FM-7). Guarded against the canon in
        `tests/test_canon_check_map.py`."""
        from gfso.core.handlers.structural import CHECK_TO_FM, FM_LABEL
        return {"check_to_fm": CHECK_TO_FM, "fm_label": FM_LABEL}

    @app.get("/api/usage")
    def get_usage(detail: bool = False):
        """What this project's graph COST in model calls: totals, a per-ROLE split (decomposer /
        l2_review / validator / executor), and the calls themselves with `detail=true`.

        `costed_calls` is carried beside `cost_usd` on purpose: a transport that reports no price
        contributes zero, and a money total that cannot tell "free" from "not reported" is the same
        ⊥-as-zero error the metrics refuse elsewhere."""
        e: Engine = _e()
        out = e.usage_totals()
        # WHICH PROJECT THIS IS ABOUT. Without `?project=` the scope falls back to the registry's
        # ACTIVE project — which is server-wide, so it can easily be somebody else's — and the answer
        # was a plausible small number with nothing saying whose. Measured on the human door
        # 2026-08-21: a person read $0.54 for a run that had spent $7.08, and only found out by
        # passing the parameter. A money total has to name its scope.
        out["project"] = _scope_name()
        if detail:
            out["calls"] = e._graph._storage.get_usage()
        return out

    def _scope_name() -> str:
        """The project this request is answering about — the `?project=` tab scope, or the
        registry's server-wide ACTIVE project when the caller named none."""
        if app.state.registry:
            return _req_project.get() or app.state.registry.active
        return DEFAULT_PROJECT

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
    def get_pipeline(limit: int = _config.PIPELINE_PAGE):
        return _e().pipeline_log(limit)


def _mount_plan_reads(app, _e) -> None:
    """What a reader asks about a DECOMPOSITION: its projection, its review, its checks,
    its holes — as against the nodes and the graph, which are the other kind of read."""
    @app.get("/api/tasks/{task_id}/projection", response_model=ProjectionOut)
    def get_projection(task_id: str):
        e: Engine = _e()
        if e.get_task(TaskId(task_id)) is None:
            raise HTTPException(404, f"task {task_id} not found")
        return ProjectionOut(node_id=task_id, projection=e.project(TaskId(task_id)))

    # === L2 critic / validation (POST /api/run/review_decomposition) ===

    @app.get("/api/tasks/{task_id}/critique")
    def get_critique(task_id: str):
        e: Engine = _e()
        t = e.get_task(TaskId(task_id))
        if t is None:
            raise HTTPException(404, f"task {task_id} not found")
        return {"verified": t.verified, "critique": e.get_critique(TaskId(task_id))}

    # === Solver (§15.3 — deterministic, separate from LLM) ===

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


def _mount_reads(app, _e, _req_project) -> None:
    """Every READ of a graph: nodes, checks, review, holes, metrics, the two ledgers.

    `create_app` answered six different questions in one body of 270 statements — pages,
    reads, acts, projects, lifecycle, events — so its own shape was invisible and a reader
    after one of them walked the other five. Each is its own mounting now; `create_app` is
    the assembly, and the routes it registers are unchanged.
    """

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
            checks=[CheckResultOut.of(c) for c in checks],
            recommendation=RecommendationOut(suggestions=list(rec.suggestions)) if rec else None,
            audit=[audit_to_out(a) for a in audit],
            children=[task_to_out(c) for c in children],
        )

    # === Unified authoring surface: every gfso tool over HTTP (the SAME gfso.tools.TOOLS that MCP + CLI bind) ===
    # Adding an authoring verb = ONE Engine method + ONE gfso.tools entry → it appears HERE, on MCP, and on the
    # CLI with zero per-adapter edits (no duplicate route to keep in sync). Reads keep their bespoke typed routes
    _mount_acts(app, _e, _req_project)

    # === Metrics ===

    _mount_ledgers(app, _e)


    @app.get("/api/tasks/{task_id}/actions", response_model=list[ActionOut])
    def get_actions(task_id: str, role: Optional[str] = None):
        e: Engine = _e()
        if e.get_task(TaskId(task_id)) is None:
            raise HTTPException(404, f"task {task_id} not found")
        sigs = e.available_actions(TaskId(task_id), AgentId(role) if role else None)
        return [ActionOut(signal=s.name, role=required_role(s).name) for s in sigs]

    # === Projection (read-only critic input contract) ===

    _mount_plan_reads(app, _e)

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
                id=t.id, label=(t.spec.name or t.spec.description[:_config.LABEL_CHARS]),
                state=t.state.name, assignee=t.assignee,
                parent_id=t.parent_id, has_children=has_children,
                done_reason=t.done_reason.name if t.done_reason else None,
            ))
            if t.parent_id:
                edges.append(GraphEdge(source=t.parent_id, target=t.id, type="parent-child"))
        for dep in e.get_dependencies():
            edges.append(GraphEdge(source=dep.from_id, target=dep.to_id, type="dependency", discovered=dep.discovered))
        return GraphOut(nodes=nodes, edges=edges)

def _mount_pages(app) -> None:
    """The page and its assets — the human door's own surface.

    `create_app` answered six different questions in one body of 270 statements — pages,
    reads, acts, projects, lifecycle, events — so its own shape was invisible and a reader
    after one of them walked the other five. Each is its own mounting now; `create_app` is
    the assembly, and the routes it registers are unchanged.
    """

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


def _mount_events(app) -> None:
    """The live WS feed — every write, pushed to whoever is watching.

    One of the six questions `create_app` used to answer in a single body of 270
    statements; the routes it registers are unchanged.
    """
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

def _mount_projects(app, _e) -> None:
    """Which graph a caller stands in: list, switch, delete.

    One of the six questions `create_app` used to answer in a single body of 270
    statements; the routes it registers are unchanged.
    """
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

    @app.delete("/api/projects/{name}")
    def delete_project(name: str):
        reg = app.state.registry
        if reg is None:
            raise HTTPException(400, "single-project server (no registry)")
        try:
            return reg.delete(name)   # refuses default + the active project (switch first)
        except ValueError as ex:
            raise HTTPException(422, str(ex))

def _mount_runtime(app, _e, _live_leases) -> None:
    """What THIS process is serving: its roster, a node's verdict, and the runtime panel.

    The panel is the measurement arm's only preflight — code fingerprint, switches, roster
    content — and it belongs with the roster it reports, not with the lease machinery that
    keeps the process alive."""
    @app.get("/api/agents")
    def get_agents():
        # …and SAY that `project=` selects nothing here: the roster is one server-wide file, and a
        # caller who passed the parameter every other verb takes got other projects' roles back with
        # no way to tell an ignored argument from a shared registry (measured 2026-08-22).
        from gfso.delegate import default_agents
        return {"agents": default_agents().list(),
                "scope": "server-wide: this roster is shared by every session and project of the "
                         "one server. `project=` selects the GRAPH, never the roster."}

    @app.get("/api/tasks/{task_id}/verdict")
    def get_task_verdict(task_id: str):
        """The stored independent verdict for the node's current delivery, evidence included.

        `record_exec_verdict` persists the per-criterion evidence precisely so the trail shows WHAT
        was verified and not merely the answer (Thm 11) — but nothing could read it back, so a
        contested FAIL was auditable only by reading the server's log. Read-only, and deliberately
        NOT in the agent tool surface: the executor already learns which criteria failed through
        the FAIL signal, and handing it the validator's reasoning would change what a run measures.
        """
        # ONE SHAPE, WHICHEVER DOOR ASKS. This returned the raw record while `get_verdict` — the
        # verb the CLI and the agent door use — answers with state, currency, the delivery it judged
        # and the refused reports beside it. A caller moving between the two crashed on `KeyError:
        # 'state'` (measured on the human door 2026-08-22: "same fact, two schemas").
        e: Engine = _e()
        if e.get_task(TaskId(task_id)) is None:
            raise HTTPException(404, f"task {task_id} not found")
        return _tools.TOOLS["get_verdict"](e, task_id)

    def _hash_registry_file() -> str:
        import hashlib as _h, os as _os
        path = str(_config.agents_path())
        try:
            return _h.sha256(open(path, "rb").read()).hexdigest()[:12] if path else ""
        except OSError:
            return "missing"

    # Stamped ONCE, at startup, for the same reason `code_version` is: the question is what this
    # PROCESS loaded, not what is on disk now. Read per request it answered with the file's current
    # hash, so the caller compared the file against itself — a comparison that cannot fail, while
    # the defect it was written for (an edited registry that reaches nothing until a restart) went
    # on happening. The roster really is a process singleton, loaded once.
    _AGENTS_VERSION = _hash_registry_file()

    def _agents_fingerprint() -> str:
        """Hash of the agent registry AS LOADED BY THIS PROCESS."""
        return _AGENTS_VERSION

    @app.get("/api/runtime")
    def get_runtime():
        """The switches that are PROCESS-scoped, so a client can see what this server actually does.

        Both change behaviour a caller would otherwise have to infer from silence: with
        `validate_internal` off, a node inside one Del scope self-verifies (§14.5 D6) and no
        independent verdict ever arrives — indistinguishable, from the outside, from a validator
        that is merely slow; with the L2 gate off, execution starts on an unreviewed plan (the
        canon's EXPLORE branch, §13.5). They are set per PROCESS, so a restart can silently drop
        one — which is exactly how a measurement run stalled for 25 minutes waiting on a verdict
        that was never going to come.
        """
        import os
        from gfso.runtime import data_dir
        from gfso.serverctl import home as _home
        return {"version": __version__,   # the RELEASE; `code_version` below is the source hash
                # WHERE this process keeps state, and WHETHER the agent door is mounted. Both were
                # invisible, and both are ways the live server can differ from the installation
                # asking about it: a second install serves another database, and a hand-started
                # `gfso serve` holds the address with no /mcp — an agent session then 404s while
                # every diagnostic reported a healthy server.
                "home": str(_home()),
                "data_dir": str(data_dir()),
                # Who else is on this server, and is it working. A reconcile that restarts the one
                # server without asking either question ends someone else's run mid-flight — and a
                # killed process does not take its `claude` children with it, so they go on writing
                # into a working directory with nobody left to receive the report.
                "sessions": len(_live_leases()),
                # SERVER-WIDE, and said so: this counts the long verbs running in THIS process for
                # every session and project, so a reader saw `review_decomposition` beside their own
                # idle graph and read it as theirs (measured 2026-08-21).
                "busy": sorted(_tools.INFLIGHT),
                "busy_note": ("long-running verbs in flight on this server across ALL sessions and "
                              "projects — not necessarily yours"),
                "with_mcp": _config.with_mcp(),
                "autoexit": _config.autoexit(),
                # THE EFFECTIVE VALUES, read from the code that obeys them — not from the
                # environment as this panel happens to see it. This is the measurement arm's only
                # preflight: it refuses to start when `l2_gate` is false, so a declared `true` over a
                # mechanism that is not running would let a run measure stalling instead of
                # acceptance, and nothing would say so. Asking the enforcement point makes the two
                # inseparable by construction.
                "validate_internal": _validate_internal_on(),
                "l2_gate": _l2_gate_on(),
                # What CODE is actually serving: a running process holds its sources in memory, so an
                # edited tree does not reach it and nothing about the port or the health check says so.
                # Stamped once at startup — comparing it with the tree's is the whole staleness test.
                "code_version": _CODE_VERSION,
                "agents_path": str(_config.agents_path()),
                # …and the CONTENT the process actually loaded. The registry is read once, at
                # startup, so editing the file changes nothing until a restart — and `gfso up`
                # reported "already-correct" while the live server still held the previous
                # validators. The path alone cannot see that; a fingerprint of what was loaded can.
                "agents_version": _agents_fingerprint()}


def _mount_lifecycle(app, _e, engine) -> None:
    """The server's own life: leases, shutdown, the roster and what this process is serving.

    One of the six questions `create_app` used to answer in a single body of 270
    statements; the routes it registers are unchanged.
    """
    app.state.leases = {}
    app.state.exit_fn = (lambda: os._exit(0))

    LEASE_GRACE = 12.0

    def _live_leases() -> list[str]:
        """Leases that have heartbeated recently. Expiry belongs HERE, not in the reaper.

        The reaper was the only thing that ever pruned this dict, and it is opt-in now — so a
        session that ended without dropping its lease (a killed client; the drop rides a daemon
        thread) left an entry that never expired. Everything downstream reads `sessions` to decide
        whether a reconcile would interrupt somebody, so one stale entry made every later upgrade
        decline to take effect, permanently and silently.
        """
        import time
        now = time.monotonic()
        for k, ts in list(app.state.leases.items()):
            if now - ts > LEASE_GRACE:
                app.state.leases.pop(k, None)
        return list(app.state.leases)

    @app.post("/api/lease")
    def renew_lease(body: dict = Body(...)):
        import time
        app.state.leases[str(body.get("id", "?"))] = time.monotonic()
        return {"ok": True, "sessions": len(_live_leases())}

    @app.delete("/api/lease/{lease_id}")
    def drop_lease(lease_id: str):
        app.state.leases.pop(lease_id, None)
        return {"ok": True, "sessions": len(_live_leases())}

    # A registered executor role may name the lease it belongs to, and then it is only dispatchable
    # while that lease lives. The leases are here; the dispatcher is a layer below and must not
    # import this module, so the answer is handed down as a function. Same expiry as everything else
    # reads — one liveness computation, not a second one that can disagree with the 409 above.
    try:
        from gfso.delegate import default_agents
        default_agents().set_owner_liveness(lambda client: client in _live_leases())
    except Exception:                       # a liveness probe is an improvement, never a boot blocker
        pass

    @app.post("/api/shutdown")
    def shutdown(body: dict = Body(default={})):
        """Stop the server — unless someone is using it, and then only when asked to mean it.

        The rule lives HERE, not in the reconciler, because a client holds its own code in memory:
        an older `gfso up` still on a long-lived session bridge kept restarting a drifted server
        under a run that had paid for hours of work, and no fix in the client could reach it. The
        server is the one party that cannot be out of date about itself.

        `gfso down` and a deliberate restart pass `force`; a routine reconcile does not, and gets
        told who is on it. A newly declared state applies to the NEXT start.
        """
        import threading
        # ONE definition of "someone is on it": `_live_leases()` also prunes, so a killed client
        # cannot hold the server hostage forever. Two windows here meant two answers to the same
        # question — the endpoint said 90s while everything else said 12.
        live = _live_leases()
        if live and not body.get("force"):
            raise HTTPException(409, f"{len(live)} client(s) are working on this server "
                                     f"({', '.join(sorted(live)[:4])}) — not stopping. Pass "
                                     f"force=true (that is what `gfso down` does) to mean it.")
        threading.Timer(0.3, app.state.exit_fn).start()   # answer first, then exit
        return {"ok": True, "bye": True}

    if _config.autoexit():     # opt-in, see above
        _start_reaper(app)

    # === Delegation roster (read view; registration = the MCP verb) ===

    _mount_runtime(app, _e, _live_leases)


def create_app(engine: Engine, with_mcp: bool = False, registry=None) -> FastAPI:
    mcp, mcp_asgi = _build_mcp(registry or engine) if with_mcp else (None, None)

    lifespan = None
    if mcp is not None:
        @asynccontextmanager
        async def lifespan(_app):  # the streamable transport needs its session manager running
            async with mcp.session_manager.run():
                yield

    app = FastAPI(title="GFSO", version=__version__, lifespan=lifespan)
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

    def _e(create: bool = True) -> Engine:
        """The request-time engine: the ?project= tab scope → the registry's ACTIVE project → the
        single bound engine. `create=False` refuses a project that does not exist rather than
        making one — a read may not author a graph."""
        if app.state.registry:
            return app.state.registry.engine(_req_project.get(), create=create)
        return app.state.engine

    # LOOPBACK ONLY. The shipped UI is served from this same origin, so a wildcard bought nothing —
    # and it cost everything: this server has no authentication (SECURITY.md), and `/api/run/{tool}`
    # exposes the whole tool registry, including a `signal` whose source the caller chooses and a
    # `validate_result` that spawns a model with shell access in a directory the caller names. With
    # `*`, any page the user happened to have open in a browser could drive that chain.
    app.add_middleware(
        CORSMiddleware,
        # The one server's own port comes from `serverctl` (whose single knob is GFSO_SHARED_URL) —
        # a literal 8000 here allowed the page and its API to disagree about which server they are.
        # 8080 stays for a UI served from a dev static host beside it.
        allow_origins=[f"http://{h}:{p}" for h in (_LOOPBACK, "localhost")
                       for p in dict.fromkeys((_serverctl.PORT, 8080))],
        allow_methods=["*"], allow_headers=["*"],
    )

    # === Static UI ===
    _mount_pages(app)

    # === Task CRUD (create/mutate = /api/run/<tool>; reads stay bespoke) ===
    _mount_reads(app, _e, _req_project)

    # === Lifecycle: session leases + self-shutdown (the shared-server automation) ===
    # Every connect.py bridge (one per Claude session) heartbeats a lease. Under GFSO_AUTOEXIT=1 the
    # server exits itself once the LAST lease expires — which is now OPT-IN, and used to be what a
    # session-spawned server did. As a product default it was wrong twice over: the UI a person left
    # open kept showing the last graph it had seen, with no indication that the process behind it was
    # gone (the page only retries its socket), and an in-flight delegated executor was orphaned
    # rather than stopped. The server is a background service now: it stays until `gfso down`.
    _mount_lifecycle(app, _e, engine)

    _mount_projects(app, _e)

    _mount_events(app)

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
                # Seeding is OPT-IN here too. Importing this module — which the release smoke test
                # and any introspection tool does — used to build an engine AND write a demo graph.
                seed=_config.seed_demo())
app = create_app(_registry.engine(), with_mcp=_config.with_mcp(),
                 registry=_registry)
