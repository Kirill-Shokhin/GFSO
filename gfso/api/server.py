"""FastAPI application — GFSO HTTP API + WebSocket + static UI."""
from __future__ import annotations

import asyncio
import contextvars
import hashlib
import inspect
import json
import os
import threading
import time
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Optional

from fastapi import FastAPI, WebSocket, WebSocketDisconnect, HTTPException, Body
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, JSONResponse

from gfso import __version__
from gfso.core.graph import DIAGNOSTIC_MEANS, Q_MEANS
from gfso.tools import PARAM_CHOICES
from gfso.core.handlers import solver_findings
from gfso.core.handlers.recommend import suggest_criteria
from gfso.core.handlers.structural import CHECK_TO_FM, FM_LABEL
from gfso.core.types import TaskId, AgentId, State
from gfso.delegate import default_agents
from gfso.runtime import data_dir
from gfso.serverctl import home as _home

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

#: How many project names `/api/projects` returns when the caller does not cap it. The whole list is
#: a DOWNLOAD, not an answer: this installation had 354 names plus a `last_active` entry for each —
#: ~19 KB, several thousand tokens — to settle "does my project exist" (measured 2026-09-01). Fifty
#: is twice the shipped picker's own window (`web/index.html` shows 25), so the picker is untouched;
#: `limit=0` lifts the cap for a caller that genuinely wants everything.
PROJECT_PAGE = 50


def _scope_namer(app, req_project):
    """ONE owner for "which project is this request about" — the `?project=` tab scope, or the
    registry's server-wide ACTIVE project when the caller named none.

    It was born inside the money total (`/api/usage`) because a person read $0.54 for a run that had
    spent $7.08 and only found out by passing the parameter. The ACTS have the same hole and it
    costs more there: the fallback is server-wide, so a `next_step` with no project returns a node
    from somebody else's graph and a typo mutates a stranger's. Two answers to "whose graph" would
    be two chances to disagree, so the acts ask this one rather than computing their own."""
    def _scope_name() -> str:
        if app.state.registry:
            return req_project.get() or app.state.registry.active
        return DEFAULT_PROJECT
    return _scope_name


def _naming_the_scope(out, project: str | None):
    """Stamp the project an act answered about onto its own body — including a REFUSAL, which is the
    body a typo produces and therefore the one that needs the scope most. Never overwrites a
    `project` the verb itself said, and says nothing when there is no graph to name."""
    if project and isinstance(out, dict) and "project" not in out:
        return {**out, "project": project}
    return out


def _projects_page(listing: dict, prefix: str, limit: int) -> dict:
    """The project list as an ANSWER rather than a download: the names matching `prefix`, capped at
    `limit`, with `last_active` narrowed to the same page. Nothing is deleted here — those DB files
    are the provenance of past measurements — the door just learned to answer a narrow question
    narrowly. `active` survives both filters: a caller that cannot see where it is standing cannot
    tell a scoped answer from an ambient one. `total` counts what MATCHED, before the cap, so a
    client can still say how many names it did not receive."""
    matched = [n for n in listing["projects"] if n.startswith(prefix)]
    page = matched[:limit] if limit > 0 else matched
    stamps = listing.get("last_active") or {}
    return {**listing, "projects": page, "total": len(matched),
            **({"last_active": {n: stamps[n] for n in page if n in stamps}} if stamps else {})}


def _build_mcp(engine: Engine):
    """MCP server + its streamable-HTTP ASGI app over the SAME Engine instance.
    Returns (mcp, asgi) or (None, None) if the MCP SDK isn't installed (it is a required dependency — reinstall the package)."""
    try:
        # LEFT: the MCP SDK is optional at RUNTIME here — this door serves HTTP with or without it,
        # and the except below is what turns a missing SDK into (None, None) instead of no server.
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


def _tool_index() -> dict:
    """The verb registry as an answer, not as knowledge a caller has to already have.

    The door is ONE generated route (`POST /api/run/{tool}`), so an OpenAPI reader sees an untyped
    passthrough and nothing else: a person arriving at this port with curl had to guess every verb
    name and every parameter from error strings, and said so (HTTP door, 2026-09-02). The registry
    already knows all of it.
    """
    out = []
    for name, fn in sorted(_tools.TOOLS.items()):
        params = [p for p in list(inspect.signature(fn).parameters.values())[1:]
                  if not p.name.startswith("_")]
        out.append({"tool": name, "post": f"/api/run/{name}",
                    "required": [p.name for p in params if p.default is inspect.Parameter.empty],
                    "optional": [p.name for p in params if p.default is not inspect.Parameter.empty],
                    "project": name not in _tools.PROJECTLESS_VERBS,
                    "what": ((fn.__doc__ or "").strip().splitlines() or [""])[0][:200],
                    # …AND THE WHOLE CONTRACT, not its first line. The catalogue truncated mid
                    # sentence, so the closed enums a verb takes (`kind`, `reason`) were discoverable
                    # only by being refused — two round trips per verb, where the refusal itself
                    # names the legal values perfectly (HTTP door, 2026-09-02).
                    # …AND THE CLOSED SETS AS DATA. A caller building against this catalogue had to
                    # parse the prose or be refused once per verb to learn them.
                    "choices": {q.name: v for q, v in
                                ((q, PARAM_CHOICES.get(name, {}).get(q.name)) for q in params)
                                if v},
                    "doc": (fn.__doc__ or "").strip()})
    return {"tools": out, "count": len(out),
            "how": "POST /api/run/<tool> with the arguments as a JSON object; `project` rides on "
                   "every verb that is about a graph."}


def _mount_acts(app, _e, _req_project, _scope_name) -> None:
    """The ACTS: the whole verb registry over HTTP, and the criteria suggester.

    A read answers about the graph; an act changes it, and they had one body between them.
    This is the door every verb is generated onto — `gfso.tools_llm.TOOLS` — which is why
    it is one mounting rather than a route each."""
    @app.get("/api/tools")
    def list_tools():
        """Every verb this door takes, with its parameters and its first line of documentation."""
        return _tool_index()

    # above; only the action/mutation surface is generated. body = the tool's kwargs as JSON.
    @app.post("/api/run/{tool}")
    def run_tool(tool: str, body: dict = Body(default={})):
        """Run one verb of the registry — `GET /api/tools` names them all — with the JSON body as
        its arguments; that body is the whole authoring surface (create, decompose, signal,
        validate).

        `project` may ride in the body or the query string; without it the scope is the server-wide
        ACTIVE project, and the answer says which graph it was about.

        STATUS CODES, said as they ARE rather than as this sentence used to claim. A call the verb
        could not be given AS WRITTEN — a malformed payload, a value of the wrong shape — is a 422
        carrying the verb's own refusal dict. A call the verb UNDERSTOOD and answered NO to is a
        **200**, with the no in the body (`accepted: false` on `signal`, `recorded: false` on
        `record_verdict`, `refused: true` elsewhere): the engine was asked a question and gave its
        answer, which is a successful call about an unsuccessful act. That is a deliberate position
        and it is defended; what was NOT true is the promise this docstring made, and four testers
        across three waves read the promise, wrote `raise_for_status()`, and were right to call the
        result a contradiction (waves 22–25). 404 is an unknown verb or an absent project, 500 a
        verb that broke.

        The practical rule for a client: branch on the BODY, never on the status. `accepted`,
        `recorded` and `refused` are the fields that carry a refusal, and every verb that can refuse
        sets one of them."""
        # `project` in the BODY as well as the query string — the third spelling of one thing. The
        # CLI takes `project=<name>`, `gfso log` takes `--project`, and this door took it only as a
        # query parameter, so a caller who put it where every other argument goes had it passed to
        # the verb as an unknown keyword and got a TypeError about the verb.
        body = dict(body or {})
        if (_in_body := body.pop("project", None)):
            _req_project.set(_in_body)      # the middleware resets its own token after the request
        fn = _tools.TOOLS.get(tool)
        if fn is None:
            raise HTTPException(404, (
                f"unknown tool '{tool}' — it is not on this door; use {_ELSEWHERE[tool]}"
                if tool in _ELSEWHERE else
                f"unknown tool '{tool}'. `GET /api/tools` lists every verb this door takes."))
        _refuse_bad_arguments(tool, fn, body)
        try:
            # A ROSTER VERB IS NOT ABOUT A GRAPH. It still needs an engine object to be dispatched
            # with, so it takes whichever one is at hand rather than refusing for a project that does
            # not exist — the roster is one server-wide file and says so.
            e: Engine = _e(create=tool in _tools.PROJECT_CREATING_VERBS
                           or tool in _tools.PROJECTLESS_VERBS)
        except KeyError as ex:
            raise HTTPException(404, f"no such project {ex.args[0]!r} — `gfso projects` lists them; "
                                     f"`create_task` or `auto_decompose` starts a new one") from None
        # WHOSE GRAPH THIS ANSWER IS ABOUT. `project` is optional here and falls back to the
        # server-wide ACTIVE project — deliberate for single-project use, and silent: measured on the
        # human door, a `next_step` with no project handed back a node from another session's graph
        # and a refused call answered about that graph too, with nothing in either body saying whose.
        # A roster verb names none, because it is about no graph (`PROJECTLESS_VERBS`).
        scope = None if tool in _tools.PROJECTLESS_VERBS else _scope_name()
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
                return JSONResponse(status_code=500 if out.get("unexpected") else 422,
                                    content=json.loads(json.dumps(_naming_the_scope(out, scope),
                                                                  default=str)))
            return _naming_the_scope(out, scope)
        except TypeError as ex:
            # A call that does not fit the verb is answered in the verb's OWN terms. Python says
            # "signal() missing 1 required positional argument: 'source'", which hands a user the
            # interpreter's view of a function they never called and no way to know that `source` is
            # who signs the signal. The door knows the signature; it can say what is missing, what
            # else the verb takes, and stay silent about the implementation. The shape refusals
            # themselves now run BEFORE the engine is resolved (`_refuse_bad_arguments`), so what
            # reaches here is a TypeError from inside the verb rather than from its signature.
            raise HTTPException(422, str(ex))
        except (ValueError, KeyError) as ex:
            raise HTTPException(422, str(ex))

    # === Per-role actions (§14.2) ===

    # === AI Suggest ===

    @app.post("/api/suggest-criteria", response_model=SuggestCriteriaResponse)
    def suggest_criteria_endpoint(req: SuggestCriteriaRequest):
        """Criteria the engine would suggest for a description — a read, it authors nothing."""
        e: Engine = _e()
        results = suggest_criteria(req.description, e._llm)
        return SuggestCriteriaResponse(
            criteria=[CriteriaIn(name=n, description=d) for n, d in results]
        )


def _mount_ledgers(app, _e, _req_project, _scope_name) -> None:
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

    @app.get("/api/metrics", response_model=MetricsOut)
    def get_metrics():
        """The five quality metrics of this project's graph — q_T, q_D, q_V, q_Dep, q_Del — beside
        `false_fail_share`, a diagnostic that is deliberately NOT part of Q (§24.5; high means
        over-strict validation). A null is ⊥: the population was empty, not a score of zero."""
        m = _e().metrics()
        return MetricsOut(**m, means={k: v for k, v in {**Q_MEANS, **DIAGNOSTIC_MEANS}.items() if k in m})

    # === Audit ===

    @app.get("/api/audit", response_model=list[AuditEntryOut])
    def get_audit(task_id: Optional[str] = None):
        """The signal trail, oldest first: what was sent, who signed it, the states it moved between
        — and the attempts the FSM REFUSED, which appear here with `rejected` set and nowhere
        else in a read. `task_id` narrows it to one node; without it, the whole project."""
        e: Engine = _e()
        tid = TaskId(task_id) if task_id else None
        return [audit_to_out(a) for a in e.audit_log(tid)]

    # === Pipeline observation history (persisted; ticks excluded at the writer) ===

    @app.get("/api/pipeline")
    def get_pipeline(limit: int = _config.PIPELINE_PAGE):
        """What the long verbs said while they ran — decomposition rounds, review, validation —
        persisted, oldest first, the last `limit` entries. Live token ticks are dropped at the
        writer, so this is the durable narrative of a run rather than the WS feed replayed."""
        return _e().pipeline_log(limit)


def _mount_plan_reads(app, _e) -> None:
    """What a reader asks about a DECOMPOSITION: its projection, its review, its checks,
    its holes — as against the nodes and the graph, which are the other kind of read."""
    @app.get("/api/tasks/{task_id}/projection", response_model=ProjectionOut)
    def get_projection(task_id: str):
        """The node's decomposition as the markdown a critic reads: goal, children with their
        criteria and coverage, dependency seams, ACCEPTED_RISKS, the structural checks already
        run. A read about the PLAN, not about the work — nothing here says whether anything was
        executed."""
        e: Engine = _e()
        if e.get_task(TaskId(task_id)) is None:
            raise HTTPException(404, f"task {task_id} not found")
        return ProjectionOut(node_id=task_id, projection=e.project(TaskId(task_id)))

    # === L2 critic / validation (POST /api/run/review_decomposition) ===

    @app.get("/api/tasks/{task_id}/critique")
    def get_critique(task_id: str):
        """The Level-2 review of this node's plan as stored: `verified` is whether the plan
        currently carries the gate, `critique` the checker's findings. A null critique means no
        review has run — not a review that found nothing; the two are the same colour to anything
        that reads only the findings."""
        e: Engine = _e()
        t = e.get_task(TaskId(task_id))
        if t is None:
            raise HTTPException(404, f"task {task_id} not found")
        return {"verified": t.verified, "critique": e.get_critique(TaskId(task_id))}

    # === Solver (§15.3 — deterministic, separate from LLM) ===

    @app.get("/api/tasks/{task_id}/solver", response_model=SolverOut)
    def get_solver(task_id: str):
        """The DETERMINISTIC half of plan review (§15.3): the structural checks this node fails
        right now, one finding each, computed without a model call. Empty means every applicable
        check passed — unlike `critique`, where empty can also mean nobody looked."""
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


def _named(tool: str, p) -> str:
    """A parameter as the door should print it — with its CHOICES when the set is closed.

    `revise` takes a `reason`, the hint read "(it also takes reason)", and the field looks like free
    text — so a caller wrote a sentence and was refused by an enum they had no way to know existed
    (HTTP door, wave 26, 2026-09-06). The words are already owned once, in `gfso.tools.PARAM_CHOICES`,
    which this door already imports for its schema; the defect was only that the REFUSAL did not use
    what the schema knows. A second table here would have been the same defect in a new place.
    """
    choices = PARAM_CHOICES.get(tool, {}).get(p.name)
    return f"{p.name}: {'|'.join(choices)}" if choices else p.name

def _refuse_bad_arguments(tool: str, fn, body: dict) -> None:
    """Refuse a call the verb cannot take — BEFORE anything is created for it.

    This check already existed, in the TypeError handler around the call, which meant it ran after
    the engine had been resolved and the project brought into existence. Measured 2026-09-02: a
    malformed `create_task` answered 422 and left the project behind, so a caller getting the payload
    wrong three times accumulated three projects — the same mechanism that had put 315 of them on
    this installation. A check that runs after the side effect is not a guard.
    """
    sig = inspect.signature(fn)
    params = [p for p in list(sig.parameters.values())[1:] if not p.name.startswith("_")]
    required = [p.name for p in params if p.default is inspect.Parameter.empty]
    if missing := [n for n in required if n not in (body or {})]:
        optional = [p.name for p in params if p.default is not inspect.Parameter.empty]
        raise HTTPException(422, f"{tool} needs {', '.join(missing)}"
                                 + (f" (it also takes {', '.join(_named(tool, p) for p in params if p.default is not inspect.Parameter.empty)})"
                                    if optional else ""))
    if unknown := [k for k in (body or {}) if k not in {p.name for p in params}]:
        raise HTTPException(422, f"{tool} does not take {', '.join(unknown)} — it takes "
                                 f"{', '.join(p.name for p in params)}")


def _engine_for(registry, bound: Engine, project: Optional[str], create: bool) -> Engine:
    """Resolve a request's engine: the ?project= scope through the registry, or the single bound one.

    A read may not author a graph, so an unknown name comes back as a refusal rather than as an
    empty graph under that name — which reads as the caller's own work having vanished.
    """
    if not registry:
        return bound
    try:
        return registry.engine(project, create=create)
    except KeyError as unknown:
        raise _no_such_project(unknown.args[0])


#: Verbs that exist on ANOTHER door, and where they are on this one. A bare "unknown tool" for a verb
#: a caller has genuinely seen elsewhere reads as "this product cannot do that" — measured on the HTTP
#: door 2026-09-02, where `delete_project` is on the MCP roster and 404s here, while the capability
#: sits one route away. These verbs are session-scoped by nature (they refuse to delete or switch the
#: ground the CALLER stands on, which needs a session), so they belong to that binding; what is owed
#: is not the verb but the sentence that stops the search.
_ELSEWHERE = {
    "delete_project": "DELETE /api/projects/{name}",
    "use_project": "POST /api/projects/use  {\"name\": \"…\"} — or just pass ?project= per call, "
                   "which is what this door scopes on",
}


def _no_such_project(name: str) -> HTTPException:
    """The refusal for a project this server does not have — named, with where the real list is.

    A read may not author a graph, so a mistyped name has to come back as a refusal rather than as
    an empty graph under that name, which reads as the caller's own work having vanished.
    """
    return HTTPException(
        404, f"no project named '{name}' on this server. A read does not create one — check the "
             f"name against `GET /api/projects`, or author it with a verb that builds a graph "
             f"(`create_task`, `auto_decompose`).")


def _graph_for_drawing(e: Engine) -> GraphOut:
    """The project shaped for a picture: nodes with state and Del, parent edges, Dep edges.

    Shaping, not mounting — it sat inside the read that serves it, which is why the
    function that registers the reads was the size of the reads themselves.
    """
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
            closure=e.closure_of(t.id),
        ))
        if t.parent_id:
            edges.append(GraphEdge(source=t.parent_id, target=t.id, type="parent-child"))
    for dep in e.get_dependencies():
        edges.append(GraphEdge(source=dep.from_id, target=dep.to_id, type="dependency", discovered=dep.discovered))
    return GraphOut(nodes=nodes, edges=edges)


def _mount_reads(app, _e, _req_project, _scope_name) -> None:
    """Every READ of a graph: nodes, checks, review, holes, metrics, the two ledgers.

    `create_app` answered six different questions in one body of 270 statements — pages,
    reads, acts, projects, lifecycle, events — so its own shape was invisible and a reader
    after one of them walked the other five. Each is its own mounting now; `create_app` is
    the assembly, and the routes it registers are unchanged.
    """

    @app.get("/api/tasks", response_model=list[TaskOut])
    def list_tasks(state: Optional[str] = None, assignee: Optional[str] = None):
        """The project's nodes, flat: all of them, or those in one `state` (a State name, e.g.
        `EXECUTING`) or held by one `assignee`. `state` wins when both are given. Summary shape —
        criteria, checks, audit and children come from the per-node read."""
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
        """One node with everything that hangs off it: its structural checks, the stored
        recommendation, its full audit trail, its direct children. The read the UI's detail panel
        is built from; an unknown id is a 404, never an empty body."""
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
            closure=e.closure_of(TaskId(task_id)),
            checks=[CheckResultOut.of(c) for c in checks],
            recommendation=RecommendationOut(suggestions=list(rec.suggestions)) if rec else None,
            audit=[audit_to_out(a) for a in audit],
            children=[task_to_out(c) for c in children],
        )

    # === Unified authoring surface: every gfso tool over HTTP (the SAME gfso.tools.TOOLS that MCP + CLI bind) ===
    # Adding an authoring verb = ONE Engine method + ONE gfso.tools entry → it appears HERE, on MCP, and on the
    # CLI with zero per-adapter edits (no duplicate route to keep in sync). Reads keep their bespoke typed routes
    _mount_acts(app, _e, _req_project, _scope_name)

    # === Metrics ===

    _mount_ledgers(app, _e, _req_project, _scope_name)


    @app.get("/api/tasks/{task_id}/actions", response_model=list[ActionOut])
    def get_actions(task_id: str, role: Optional[str] = None):
        """Which signals this node admits in the state it is in — narrowed, when `role` is given, to
        the ones that role may send (executor = the node's assignee, issuer = its parent's).
        Empty is an answer, not a gap: a settled node admits nothing. System signals (TIMEOUT)
        are never offered."""
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
        """The whole project shaped for drawing: every node with its state and Del, parent-child
        edges, and dependency edges — `discovered` marking the ones execution found rather than
        the plan declaring. `has_children` separates a leaf from a node whose children merely are
        not drawn yet."""
        return _graph_for_drawing(_e())

def _mount_pages(app) -> None:
    """The page and its assets — the human door's own surface.

    `create_app` answered six different questions in one body of 270 statements — pages,
    reads, acts, projects, lifecycle, events — so its own shape was invisible and a reader
    after one of them walked the other five. Each is its own mounting now; `create_app` is
    the assembly, and the routes it registers are unchanged.
    """

    @app.get("/")
    async def index():
        """The human door itself: the single page, which drives this same API and watches
        `/ws/events`."""
        return FileResponse(WEB_DIR / "index.html")

    @app.get("/tokens.css")
    async def tokens_css():
        """The brand tokens — palette, type scale, fonts — that the UI's stylesheet is written
        against. The single source of truth for colour: `gfso.css` requires this loaded first."""
        return FileResponse(WEB_DIR / "tokens.css", media_type="text/css")

    @app.get("/gfso.css")
    async def gfso_css():
        """The UI's own styles, expressed entirely in the tokens above, so recolouring the product
        is an edit to `tokens.css` and never to this."""
        return FileResponse(WEB_DIR / "gfso.css", media_type="text/css")

    @app.get("/icon.svg")
    async def icon_svg():
        """The page's icon, served from this origin like every other asset — the door depends on no
        external host."""
        return FileResponse(WEB_DIR / "icon.svg", media_type="image/svg+xml")


def _mount_events(app) -> None:
    """The live WS feed — every write, pushed to whoever is watching.

    One of the six questions `create_app` used to answer in a single body of 270
    statements; the routes it registers are unchanged.
    """
    # === WebSocket ===

    @app.websocket("/ws/events")
    async def websocket_events(websocket: WebSocket):
        """Live push of every write the engine makes to the graph this socket named (`?project=`,
        the same tab scope the HTTP calls carry — the middleware covers HTTP only, so it is read
        here by hand): `transition` for an accepted signal, `reject` for a refused one,
        `pipeline` for what a running verb reports. The callbacks are unregistered on disconnect,
        so a dropped tab leaves nothing subscribed."""
        await websocket.accept()
        # the tab's project rides the WS url too (middleware covers HTTP only)
        proj = websocket.query_params.get("project") or None
        eng: Engine = app.state.registry.engine(proj) if app.state.registry else app.state.engine
        loop = asyncio.get_event_loop()
        app.state.loop = loop
        q: asyncio.Queue = asyncio.Queue()
        app.state.ws_clients.add(q)          # join the global broadcast set (project-list events)

        def on_transition(tid, old, new, sig):
            """An accepted signal as the frame the page redraws from: the node, both states, and
            what moved it."""
            loop.call_soon_threadsafe(q.put_nowait, {
                "type": "transition", "task_id": str(tid),
                "old_state": old.name, "new_state": new.name, "signal": sig.name,
            })

        def on_reject(tid, sig, state):
            """A signal the FSM refused — pushed as an event of its own, because the state that
            refused it is the whole answer to why nothing happened, and a watcher would otherwise
            see only silence."""
            loop.call_soon_threadsafe(q.put_nowait, {
                "type": "reject", "task_id": str(tid),
                "signal": sig.name, "state": state.name,
            })

        def on_info(source, message):
            """What a running verb reports about its own progress, tagged with the stage that said
            it. Not a graph change: nothing here means the graph moved."""
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
    def get_projects(prefix: str = "", limit: int = PROJECT_PAGE):
        """The projects a caller can stand in — filtered, because the full list is a download
        (`_projects_page` carries the measurement and the meaning of `total`)."""
        reg = app.state.registry
        return _projects_page(reg.list() if reg else
                              {"active": DEFAULT_PROJECT, "projects": [DEFAULT_PROJECT]},
                              prefix, limit)

    @app.post("/api/projects/use")
    def use_project(body: dict = Body(...)):
        """Move the SERVER-WIDE active project — the fallback scope of every call that names no
        `?project=`, so this changes what other sessions on this server get too, and a tab that
        passes the parameter is unaffected. Creates the project on first use; answers with the
        registry listing. 400 on a single-project server, 422 on a name the registry refuses."""
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
        """Destroy a project irreversibly: its engine is stopped and its database file removed with
        the whole history in it. Refused for `default` and for the ACTIVE project — switch away
        first; deleting the ground you stand on is the misclick that refusal exists for."""
        reg = app.state.registry
        if reg is None:
            raise HTTPException(400, "single-project server (no registry)")
        try:
            return reg.delete(name)   # refuses default + the active project (switch first)
        except ValueError as ex:
            raise HTTPException(422, str(ex))

def _mount_runtime(app, _e, _live_leases, _scope_name) -> None:
    """What THIS process is serving: its roster, a node's verdict, and the runtime panel.

    The panel is the measurement arm's only preflight — code fingerprint, switches, roster
    content — and it belongs with the roster it reports, not with the lease machinery that
    keeps the process alive."""
    @app.get("/api/agents")
    def get_agents():
        """The delegation roster: the executor roles registered on this server and what each may be
        given. SERVER-WIDE — one file shared by every session and project, which is why the
        answer carries its own `scope` line and why `project=` selects nothing here. Registration
        is a verb, not this read."""
        # …and SAY that `project=` selects nothing here: the roster is one server-wide file, and a
        # caller who passed the parameter every other verb takes got other projects' roles back with
        # no way to tell an ignored argument from a shared registry (measured 2026-08-22).
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
        # …and the scope rides with it, because ONE SHAPE means one shape: the verb's answer over
        # `/api/run` now names the graph it read, and a read door that dropped that would be the
        # same two-schemas defect this endpoint exists to have closed.
        return _naming_the_scope(_tools.TOOLS["get_verdict"](e, task_id), _scope_name())

    def _hash_registry_file() -> str:
        path = str(_config.agents_path())
        try:
            return hashlib.sha256(open(path, "rb").read()).hexdigest()[:12] if path else ""
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
                # …AND HOW MUCH OF ONE VERDICT RUNS AT ONCE. Acceptance is 65-70% of a run's spend on
                # every measurement taken, and this dial is what decides how much of it happens in
                # parallel — so a cost measured without it recorded is a cost measured against an
                # unknown setting. Read from the owner, like the two switches above.
                "validation_batch": _config.validation_batch(),
                # …AND WHO THIS DOOR'S CALLER IS BY DEFAULT. The page shipped a box reading `pm` — an
                # id registered nowhere — so a person's first Pass/Fail was signed as a stranger and
                # refused, correctly and uselessly (read as a user, 2026-09-02). The identity the
                # frontier computes `mine` against is the one a surface should offer.
                "agent_id": _config.agent_id(),
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


def _mount_lifecycle(app, _e, engine, _scope_name) -> None:
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
        now = time.monotonic()
        for k, ts in list(app.state.leases.items()):
            if now - ts > LEASE_GRACE:
                app.state.leases.pop(k, None)
        return list(app.state.leases)

    @app.post("/api/lease")
    def renew_lease(body: dict = Body(...)):
        """Heartbeat one session's claim on this process (`id` in the body), good for about twelve
        seconds. Everything that could interrupt somebody — `/api/shutdown`, the reaper, a
        reconcile — counts these leases, so a client that stops calling is what makes the server
        free to restart."""
        app.state.leases[str(body.get("id", "?"))] = time.monotonic()
        return {"ok": True, "sessions": len(_live_leases())}

    @app.delete("/api/lease/{lease_id}")
    def drop_lease(lease_id: str):
        """Give up a session's claim now instead of waiting out its expiry, so the next reconcile is
        not told the server is busy by a client that has already gone. Unknown ids are `ok`: this
        says the lease is not held, not that it once was."""
        app.state.leases.pop(lease_id, None)
        return {"ok": True, "sessions": len(_live_leases())}

    # A registered executor role may name the lease it belongs to, and then it is only dispatchable
    # while that lease lives. The leases are here; the dispatcher is a layer below and must not
    # import this module, so the answer is handed down as a function. Same expiry as everything else
    # reads — one liveness computation, not a second one that can disagree with the 409 above.
    try:
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

    _mount_runtime(app, _e, _live_leases, _scope_name)


def create_app(engine: Engine, with_mcp: bool = False, registry=None) -> FastAPI:
    """Assemble the HTTP door: the pages, the reads, the acts, the ledgers, the lifecycle, the events.

    An assembly and nothing else — every route lives in one of the mountings below, so this function
    reads as the list of questions this door answers. `registry` turns on multi-project mode, which is
    the isolation boundary: one port, one server, a graph per project.
    """
    mcp, mcp_asgi = _build_mcp(registry or engine) if with_mcp else (None, None)

    lifespan = None
    if mcp is not None:
        @asynccontextmanager
        async def lifespan(_app):  # the streamable transport needs its session manager running
            """Hold the MCP session manager open for as long as the sub-app is mounted."""
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
    _req_project: contextvars.ContextVar = contextvars.ContextVar("gfso_project", default=None)

    @app.middleware("http")
    async def _project_scope(request, call_next):
        token = _req_project.set(request.query_params.get("project") or None)
        try:
            return await call_next(request)
        finally:
            _req_project.reset(token)

    def _e(create: bool = False) -> Engine:
        """The request-time engine: the ?project= tab scope → the registry's ACTIVE project → the
        single bound engine. A read may not author a graph, so this REFUSES an unknown project by
        default and only the verbs that author pass `create=True`.

        The registry has owned that rule since 315 projects accumulated out of typos, but every read
        on this door called this with the old permissive default, so the rule protected the agent
        door alone. Measured 2026-09-02: `GET /api/graph?project=<typo>` answered 200 with an empty
        graph and left the project behind — which reads, to the person who made the typo, exactly
        like their work having vanished. An unknown project is now a 404 that says so.
        """
        return _engine_for(app.state.registry, app.state.engine, _req_project.get(), create)

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
    # ONE owner for "whose graph is this about", built here and handed down: the acts stamp it on
    # their answers, the ledgers scope their totals by it, and two of them would be two chances to
    # disagree about which project a caller is standing in.
    _scope_name = _scope_namer(app, _req_project)
    _mount_reads(app, _e, _req_project, _scope_name)

    # === Lifecycle: session leases + self-shutdown (the shared-server automation) ===
    # Every connect.py bridge (one per Claude session) heartbeats a lease. Under GFSO_AUTOEXIT=1 the
    # server exits itself once the LAST lease expires — which is now OPT-IN, and used to be what a
    # session-spawned server did. As a product default it was wrong twice over: the UI a person left
    # open kept showing the last graph it had seen, with no indication that the process behind it was
    # gone (the page only retries its socket), and an in-flight delegated executor was orphaned
    # rather than stopped. The server is a background service now: it stays until `gfso down`.
    _mount_lifecycle(app, _e, engine, _scope_name)

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
