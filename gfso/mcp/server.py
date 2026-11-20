"""FastMCP server (track-b): exposes the CORE upper API to the agent as MCP tools.

Run:  python -m gfso.mcp.server
Holds ONE Engine (SQLite-persistent) = the same CORE the UI observes — the agent's tool calls and the
UI watch one graph. Every authoring tool desugars to the closed 12-signal FSM (no bypass); the tool
docstrings (from tools.py) become the tool descriptions the agent reads.
"""
from __future__ import annotations

import asyncio
import contextvars
import functools
import inspect
import json
import typing
import weakref
from typing import Optional

import anyio
try:            # LEFT: the MCP SDK is optional AT IMPORT (see `_bind`)
    import mcp.server.lowlevel.server as _lowlevel
    from mcp import types as _types
    from mcp.server.session import ServerSession as _ServerSession
except ImportError:  # pragma: no cover
    _lowlevel = None

from gfso import updates
from gfso.config import (CALLER, CLIENT, CLIENT_HEADER, CLIENT_KINDS, DEFAULT_PROJECT, LEASE_HEADER, PERSONS_NAMES,
                         STANDING, agent_id, caller_id, client_kind, how_it_is_waited, ONE_CALL, ROOT_ID, project_by_env)
from gfso.engine import Engine
from gfso.engine.moves import SIGNERS
from gfso import signin
from gfso.runtime import ProjectRegistry
from gfso.mcp import protocol as _PROTOCOL
from gfso.tools import _agent_id
from gfso import tools_llm as T                   # the COMPLETE action surface (structural + LLM verbs)


# Session-scoped project defaults: with ONE shared server and several agent sessions in parallel,
# `use_project` must switch THAT session's default, not a global (two sessions would fight over it).
# Keyed by the MCP session object; a session that never called use_project falls back to the
# registry's active project. Stdio (one session per process) degrades to exactly the old behavior.
# KEYED BY THE SESSION OBJECT, held WEAKLY — never by `id()`. CPython reuses an address once the
# object behind it is collected, and the SDK drops the transport when a session ends, so successive
# sessions (same type, same size — the likeliest reuse candidate) could land on one key: a session
# that had never called `use_project` inherited another session's project and its verbs wrote into
# THAT graph, silently, with the registry reporting a different active project in the same second.
# A weak key dies with its session, so the entry cannot outlive the object and be re-found by an
# address. (What this does NOT fix: a bridge rebuild makes a genuinely NEW session, whose mapping is
# gone — `gfso/mcp/connect.py` replays only the `initialize` handshake, not `use_project`.)
class _SessionProjects:
    """A mapping from SESSION OBJECT to project name that no address can be re-found by.

    Weak where the session allows it, so the entry dies with the session; strong where it does not
    (a few objects refuse a weak reference), which keeps the session itself alive and therefore its
    address unre-usable. Either way the invariant is the one that matters: an entry can never be
    reached by a session that is not the one that made it.
    """

    def __init__(self):
        self._weak, self._strong = weakref.WeakKeyDictionary(), {}

    def _side(self, key):
        return self._weak if key in self._weak else (self._strong if key in self._strong else None)

    def get(self, key, default=None):
        """This session's project, or `default` — never another session's."""
        side = self._side(key)
        return default if side is None else side[key]

    def __contains__(self, key):
        return self._side(key) is not None

    def __getitem__(self, key):
        return self._side(key)[key]

    def __setitem__(self, key, value):
        try:
            self._weak[key] = value
        except TypeError:
            self._strong[key] = value

    def __delitem__(self, key):
        del self._side(key)[key]

    def items(self):
        """Every (session, project) pair, for the sweep that drops a deleted project's sessions."""
        return [*self._weak.items(), *self._strong.items()]


_SESSION_PROJECTS = _SessionProjects()


def _session_key(ctx):
    """The session OBJECT — the key `_SESSION_PROJECTS` is keyed by, or None outside a session."""
    try:
        return ctx.request_context.session if ctx is not None else None
    except Exception:
        return None


def _entered(reg, name: str, ctx) -> None:
    """The calling session stands in project `name` from now on, every verb defaulting to it — `use_project`'s act, and a
    `set_mode` naming its project: the setup of a small task in one call (e2e5 G_3). No session: the server's active."""
    if (key := _session_key(ctx)) is not None:
        _SESSION_PROJECTS[key] = name
    else:
        reg.use(name)


def _the_setup_entered(reg, name: str, ctx, out):
    """A `set_mode` naming its project, recorded: the session enters it (`_entered`), the answer naming it `active` as
    `use_project`'s does, so it says the page's link too (`_link_and_say`)."""
    if not isinstance(out, dict) or _T.is_refusal(out):
        return out
    _entered(reg, name, ctx)
    return {**out, "active": name}


def _resolver(engine_or_registry):
    """One call surface over both shapes: a bare Engine (tests, single-project) or a ProjectRegistry
    (the server). resolver(project=None, ctx=None) → the engine; precedence: explicit `project`
    param → the calling SESSION's project → the registry's active."""
    if hasattr(engine_or_registry, "engine"):        # ProjectRegistry
        def _res(project=None, ctx=None, create=True):
            key = _session_key(ctx)
            name = project or (_SESSION_PROJECTS.get(key) if key is not None else None)
            # A SESSION THAT NAMES NO PROJECT WHERE THE FALLBACK IS `default` AND OTHER PROJECTS EXIST is asked which: an
            # AUTO customer told its project by name called `get_graph` and `auto_decompose` without it, was answered
            # "No mode set" from the empty default, and its plan was built where nothing executes
            # (GB_sql_database_tmwpw7028, 2026-10-15). A project switched to stands (it survives a restart); `default`
            # is chosen per session, or by `GFSO_PROJECT` — read off a remembered file it latched the hole open.
            if not name and engine_or_registry.active == DEFAULT_PROJECT and not project_by_env() and (
                    others := [p for p in engine_or_registry.list()["projects"] if p != DEFAULT_PROJECT]):
                raise ValueError(f"this session names no project, and this server holds {len(others)} besides "
                                 f"`default`: {', '.join(others[:10])} — name yours with `use_project` (`default` "
                                 f"included), or pass `project=`")
            return engine_or_registry.engine(name, create=create)
        return _res
    return lambda project=None, ctx=None, create=True: engine_or_registry   # bare Engine — ignored


# THE SIGNER ARGUMENTS ARE NOT IN THIS DOOR'S SCHEMA: a connection signs as its credential's name (`moves.SIGNERS`, the
# table every door reads; `tools_llm._signed` fills them), so a name the model saw is no argument it can type here.
# Delegation params (assignee) stay free — NAMING an executor is legitimate; SPEAKING as one is not.


# The verbs an agent calls when it ENTERS a graph — the moment a human would want to look at it.
# The address lived only in the agent's instructions, so no tool RESULT carried it and the link was
# offered only if the model happened to remember one; here it rides back with the act itself.
from gfso import tools as _T
from gfso.serverctl import UI_LINK_VERBS as _UI_LINK_VERBS, open_the_page, ui_link as _ui_link   # ONE list, both doors
from gfso.workspaces import LANDED
from gfso.adapters.netrecord import said_apart
from gfso.config import HEARTBEAT_SECONDS as _HEARTBEAT


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


#: What a verb's listing declares for an answer that holds a plan's whole text (`tools_llm.PLAN_TEXT_MAX`, escaped as
#: JSON): Claude Code saves a longer result than 50,000 characters to a file, unless the tool declares its own, up to
#: 500,000, which then holds in place of its token cap (docs: code.claude.com/docs/en/mcp, "Raise the limit for a specific
#: tool", "Scope") — and a plan past 47,000 was read from outside the person's folder, four prompts (M3, M4, 2026-11-05).
ANSWER_ROOM = {verb: {"anthropic/maxResultSizeChars": 500_000} for verb in ("plan", "refine_plan")}


def _link_for_them(link: str) -> str:
    """The link said so it is written: told to write it, a client wrote it after the go, bare, or as "at the link in the
    panel", believing the person sees what a tool answers (five clients, 2026-11-05); told "in your own text", M8 wrote it in
    thinking at the start and not at the go (11-07); the scheme and the branch said with it sank it in one long line (the
    author, 11-09: «ссылка норм если не утонет в этой длинной подписи»). The author: «в обязательном порядке
    ссылку … чтобы пользователь просто тыкнул в чате»."""
    return f"The person does not see this tool's answer: write this link in your reply's text now, on a line of its own with nothing else on it, not in thinking: {link} — then, on other lines: "


def _with_ui_link(name: str, out, project=None, engine=None):
    """Attach the local UI address to an entry verb's result (dict results only — `project` returns
    markdown and keeps its shape). Best-effort: a link is a convenience, never a reason to fail a
    call. The UI is tab-per-project (`?project=`), so the link points at the graph just acted on.
    The go and the end also say what the person is told: left to the instructions read at the start, a fresh client
    told them neither (run B, 2026-11-04). What is said stands first: last in a long answer, it went unsaid."""
    if not isinstance(out, dict):
        return out
    _link_and_say(name, out, project, engine)
    return {"say": out.pop("say"), **out} if "say" in out else out


def _link_and_say(name: str, out: dict, project, engine) -> None:
    """What the person is told, only where it is so: the end by where the result landed (a part's `complete`, a run with
    no container, a base with no git say otherwise or nothing), the go only where it built work no one holds."""
    # …a session that hid where it went was read only by whoever ran `gfso network` (critic): at the end it is told, a link
    # that cannot be made or not
    if engine is not None and (name == "stop_project" or (name == "next_steps" and out.get("complete"))) and (said := said_apart(engine.project_name)):
        out["the_records_say"] = said
        out["say"] = "Tell them what the system's own records say of this run: `the_records_say`."
    try:
        link = _ui_link(project or out.get("active"))
    # the docstring's contract: a link is a convenience, and the verb's result is already correct without it
    except Exception:
        return
    landed = engine.graph.setting(LANDED) if engine is not None and name == "next_steps" and out.get("complete") else None
    if landed:
        where = json.loads(landed)
        # …the program seen working first (the author: the person wants to see it run); read first all the same, for what
        # runs here was written by the agents
        out["say"] = ("Before anything else: read what the result runs (the agents wrote it, and it runs on this machine); "
                      "if it does only what the task asked, run it on a small example and show the person its output first; "
                      "if not, do not run it and say why. Then write to them: the root's verdict (`get_verdict(\"root\")`), " + (
            f"the branch `{where['branch']}` with their own untouched, {link}, and the one command that shows the result "
            "(`git worktree add`: a checkout refuses over uncommitted files); a next task starts from their HEAD: merge "
            "first to build on this." if where.get("branch") else f"where the result lies, `{where.get('path')}`, and {link}."))
        if "the_records_say" in out:
            out["say"] += " Tell them too what the system's own records say of this run: `the_records_say`."
        if said_of := [str(t.id) for t in engine.all_tasks()
                       if engine.checks_no_longer_run(t.id) or engine.findings_not_reproduced(t.id)]:
            more = f" and {len(said_of) - 5} more" if len(said_of) > 5 else ""
            out["say"] += (f" And what its PASS did not re-run: `get_verdict` of {', '.join(said_of[:5])}{more}, its "
                           "`checks_no_longer_run` and `findings_not_reproduced`.")
    if name == "set_mode" and out.get("active") and "ui" not in out:
        # …the setup in one call enters the project, so it says the link `use_project` would have said
        out["ui"] = link
        out["say"] = (f"{_link_for_them(link)}it shows the plan, its checks and each verdict; only what is committed "
                      f"enters." + (f" {out['say']}" if out.get("say") else ""))
        return
    if name not in _UI_LINK_VERBS or "ui" in out:
        return
    out["ui"] = link
    if name == "use_project" and not out.get("mode"):
        out["say"] = (f"{_link_for_them(link)}it shows the work; the scheme is `auto`, every "
                      "role on claude-haiku-5-5, the most tested and cheap, say if another suits; only what is committed "
                      f"enters; their branch is not touched and the result comes as branch "
                      f"`gfso/{out.get('active') or '<project>'}/accepted`.")
    if name == "auto_decompose" and out.get("root_id") and not out.get("error") and engine is not None             and (engine.mode() or {}).get("mode") == "auto":
        if (opened := open_the_page(project or out.get("active"))) is not False:
            out["page_opened"] = opened
        out["say"] = (_the_go_says(out) + f"{_link_for_them(link)}it runs unattended, they can watch there"
                      + (" (it is open in their browser now)" if out.get("page_opened") is True else "") + ", "
                      "you report the end. "
                      + (f"And one more line: the plan goes with {len(out['open_at_the_go'])} criterion(s) its review "
                         "left open (`open_at_the_go`) — the root's checks still decide the result, but a failure there "
                         "will not point to a part. " if out.get("open_at_the_go") else "")
                      + "These lines go to the person BEFORE any other call. " + how_it_is_waited(engine.project_name))
    elif name == "auto_decompose" and "goal_as_given" in out:
        out["say"] = _the_go_says(out) + "These lines go to the person BEFORE any other call." + (
            f" {out['say']}" if out.get("say") else "")     # …the go's own say (a chat's branch, its parts) kept


def _the_go_says(out: dict) -> str:
    """What the go's answer records of the start (`tools_llm.recorded_at_the_go`), said first: where the work runs and
    what of their repository it lacks were the client's to say off a roster it skipped, and the goal its own paraphrase."""
    return ((T.ON_HOST if out.get("runs_on_host") else "")
            + (f"Name what the agents' copy lacks (`not_imported`): {'; '.join(out['not_imported'])}. "
               if out.get("not_imported") else "")
            + ("Quote the goal the work is held to, verbatim (`goal_as_given`). " if out.get("goal_as_given") else ""))


def _unread_go(name: str, engine, kwargs) -> Optional[dict]:
    """The go under `auto` is a plan file the customer read: a request making a new root would plan and run in one
    call, nobody reading the plan (the author: «пока заказчик не убедится… запускать нельзя»). Refused at this door
    only, lifted by the customer's own `plan` first; the harnesses that plan and run in one call do not come through it."""
    if name != "auto_decompose" or kwargs.get("plan") is not None or kwargs.get("spec") is not None:
        return None
    root = kwargs.get("root_id") or ROOT_ID
    if (engine.mode() or {}).get("mode") != "auto" or any(str(t.id) == root for t in engine.all_tasks()):
        return None
    return {"error": "under `auto` the go is a plan the customer read: call `plan(request)`, read its `text` whole, "
                     "then `auto_decompose(plan=path)`; a second goal, in a fresh project (`use_project`)", "refused": "the plan unread"}


def _the_call(engine_or_registry, resolve, fn, project, ctx, args, kwargs) -> tuple:
    """(the engine a verb runs on, its call there) — or (the answer, None) where the door answers itself. The project is
    made only by a verb that may make it, as on the HTTP door (a read made the project it read, one per typo), and a
    refusal, the door's or the verb's, leaves none it made: a refused `set_mode` made one."""
    try:
        engine, made = resolve(project, ctx, create=False), False
    except KeyError as unknown:
        if not _T.may_make_a_project(fn.__name__):
            return {"error": f"no such project {unknown.args[0]!r} — `list_projects` names them; `use_project` makes "
                             f"a new one", "refused": True}, None
        engine, made = resolve(project, ctx), True
    except ValueError as e:              # whose graph this call is about is not settled: said, not raised
        return {"error": str(e)}, None
    no = _unread_go(fn.__name__, engine, kwargs) or _named_under_a_mode(fn.__name__, engine, kwargs)
    call = (lambda **_: no) if no else functools.partial(fn, engine, *args, **kwargs)
    if made:
        call = functools.partial(engine_or_registry.kept_if_done, made, engine, call)
    return (call(), None) if no else (engine, call)


def _with_refusal(ret):
    """A verb's answer type that admits its refusal: every verb may answer `{"error": …, "refused": true}`
    (`tools_llm._answering`), and the SDK validates the answer against the declared type — a refused `decompose`
    (declared a list) reached the agent as a pydantic error with the refusal's text cut away (2026-11-13)."""
    return ret if ret in (dict, inspect.Signature.empty) else typing.Union[ret, dict]


def _sdk_context():
    """The SDK's `Context` type, or None where the SDK is absent (direct `_bind` unit use): no session scoping."""
    try:
        # LEFT: the MCP SDK is optional AT IMPORT — this module must import without it so
        # `create_server` can raise its readable RuntimeError (and the HTTP door degrade).
        from mcp.server.fastmcp import Context
        return Context
    except ImportError:
        return None


def _bind(engine_or_registry, fn):
    """Wrap a tools.py function (engine, *args) as an MCP tool: drop `engine` from the signature so the
    SDK infers the schema from the remaining typed params; keep the docstring as the description.
    When a ProjectRegistry is bound, every tool additionally gains an optional trailing `project`
    param (None = the active project) — the multi-project surface lives in the BINDING layer, the
    tools stay pure (engine, *args). Signer params (`moves.SIGNERS`) are REMOVED from the schema: the call's
    credential signs it.

    Annotations are resolved to real types here: tools.py uses `from __future__ import annotations`
    (string hints), and the wrapper's globals are this module's — so the SDK's schema introspection would
    fail to eval e.g. `Optional[str]`. `get_type_hints(fn)` resolves them in tools.py's own namespace."""
    resolve = _resolver(engine_or_registry)
    multi = hasattr(engine_or_registry, "engine")
    pinned = SIGNERS.get(fn.__name__, ())
    # A verb that takes `_progress` runs for minutes (a decomposition, a validator run): it streams its stages and a
    # heartbeat to the client. It was bound by two hand-written wrappers whose signatures drifted from the verbs —
    # `validate_result` lost `validator`, `auto_decompose` lost `max_iterations` (ortho audit, D-F15); the schema
    # comes from the verb here like every other's.
    long = "_progress" in inspect.signature(fn).parameters
    hints = typing.get_type_hints(fn)
    sig = inspect.signature(fn)
    params = [
        (p.replace(annotation=hints[p.name]) if p.name in hints else p)
        for p in list(sig.parameters.values())[1:]  # drop the leading `engine`
        if not p.name.startswith("_")               # underscore params are transport-internal (e.g. _progress)
        and p.name not in pinned                    # actor identity is the door's, not the caller's claim
    ]
    Context = _sdk_context() if multi or long else None
    # KEYWORD_ONLY must precede a VAR_KEYWORD (e.g. `**payload`) or the signature is invalid
    var_kw = next((i for i, p in enumerate(params) if p.kind == inspect.Parameter.VAR_KEYWORD), len(params))
    if multi and "project" not in {p.name for p in params}:
        params.insert(var_kw, inspect.Parameter("project", inspect.Parameter.KEYWORD_ONLY,
                                                default=None, annotation=typing.Optional[str]))
        var_kw += 1
    if (multi or long) and Context is not None:  # the SDK injects ctx (Context-typed params are schema-invisible)
        params.insert(var_kw, inspect.Parameter("ctx", inspect.Parameter.KEYWORD_ONLY,
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

        A thread per call because a verb that blocks would otherwise stall the whole bridge.
        """
        ONE_CALL.set(object())     # …this call's own: its reply and its news read one walk of an unwritten graph
        engine, call = _the_call(engine_or_registry, resolve, fn, project, ctx, args, kwargs)
        if call is None:
            return engine
        out = await (_with_progress(ctx, f"[{fn.__name__}]", call) if long else anyio.to_thread.run_sync(call))
        # …A CALL ITS CLIENT CALLED OFF ENDS HERE. The worker thread shields the await from cancellation, so a call the
        # client cancelled while the verb ran (Claude Code does, moving a long call to the background) returned as
        # if answered; the SDK, its cancel already answered, answered again and its assertion ended the WHOLE session:
        # every call in flight lost, the bridge reporting a restart that never was (a tester's run, 2026-11-13). The
        # checkpoint delivers the cancellation, which the SDK treats as the duplicate it suppresses.
        await anyio.lowlevel.checkpoint()
        if multi and project and fn.__name__ == "set_mode":
            out = _the_setup_entered(engine_or_registry, engine.project_name, ctx, out)
        out = _with_ui_link(fn.__name__, out, project or engine.project_name, engine)
        if multi and not engine_or_registry.exists(engine.project_name):
            return out             # …a refused call unmade the project it made (`kept_if_done`): its engine is closed, no news to read
        # …and the news read off the loop too: it reads the frontier under the storage's lock, as a verb does
        out = await anyio.to_thread.run_sync(contextvars.copy_context().run, _with_news, ctx, fn.__name__, out, engine)
        return _frontier_for_an_agent(out) if fn.__name__ == "next_steps" else out

    wrapper.__signature__ = sig.replace(parameters=params,
                                        return_annotation=_with_refusal(hints.get("return", sig.return_annotation)))
    wrapper.__annotations__ = {k: _with_refusal(v) if k == "return" else v for k, v in hints.items()
                               if k != "engine" and k not in pinned}
    if multi:
        wrapper.__annotations__["project"] = typing.Optional[str]
    if (multi or long) and Context is not None:
        wrapper.__annotations__["ctx"] = Context
    return wrapper


#: what each session of a chat client was last told its run needs of it, by session: the news rides once
_TOLD = _SessionProjects()


def _with_news(ctx, name: str, out, engine):
    """A chat client's reply carries what its run needs of its customer (`needs_its_customer`), once, since its session
    was last told: no call of a chat client is held and nothing wakes it, so it learns at its next call, whatever it is."""
    if client_kind() != "chat" or not isinstance(out, dict) or (key := _session_key(ctx)) is None:
        return out
    if (p := CALLER.get()) is not None and not p.signs_as:
        return out                 # …a reader is no customer: its read marks no plan told (critic over open reading)
    seen = out if name == "next_steps" else T.next_steps(engine)
    why = T.needs_its_customer(seen)
    told, _TOLD[key] = _TOLD.get(key), (engine.project_name, why)
    if not why or told == (engine.project_name, why):
        return out
    T.said_a_plan(engine.project_name, seen)       # …a plan said once is no news again: the run's own news comes next
    return out if name == "next_steps" else {**out, "news": why}


def _frontier_for_an_agent(out):
    """The frontier as an agent's client can read it: each offer by id and name under its holder, and a reason several waits
    share said once under `why`. Each offer a step and each reason in every wait, the development graph's frontier was
    145,696 characters, past a tool result (2026-11-20); the page reads the whole frontier at its own door."""
    if not isinstance(out, dict):
        return out
    offers, steps = {}, []
    for s in out.get("steps") or ():
        if _T.is_offer(s):
            offers.setdefault(s.get("performed_by") or "", {})[s["task_id"]] = s.get("name")
        else:
            steps.append(s)
    if offers:
        out = {**out, "steps": steps, "offers": offers,
               "offers_are": "an offer is its holder's to take (ACCEPT when its work starts, or CHALLENGE); "
                             "`get_task(<id>)` holds its contract"}
    whys = [w.get("why") for w in out.get("waiting") or ()]
    shared = sorted({y for y in whys if y and whys.count(y) > 1}, key=whys.index)
    if shared:
        keys = {y: f"why-{i}" for i, y in enumerate(shared, 1)}
        out = {**out, "why": {k: y for y, k in keys.items()},
               "waiting": [{**w, "why": keys[w["why"]]} if w.get("why") in keys else w for w in out["waiting"]]}
    return out


async def _with_progress(ctx, label: str, call):
    """Run a minutes-long verb that takes `_progress`: each stage it reports goes to the client, and a heartbeat
    between them (`_awaited_with_a_heartbeat`)."""
    loop, step = asyncio.get_running_loop(), {"n": 0}

    def prog(msg: str) -> None:  # called from the worker thread
        """Push one stage line to the client."""
        step["n"] += 1
        if ctx is not None:
            try:
                asyncio.run_coroutine_threadsafe(ctx.report_progress(step["n"], None, f"{label} {msg}"), loop)
            except Exception:
                pass  # progress is presentation — never break the pipeline
    return await _awaited_with_a_heartbeat(loop, ctx, label, step, functools.partial(call, _progress=prog))


async def _awaited_with_a_heartbeat(loop, ctx, label: str, step: dict, call):
    """Run a long blocking verb, and keep saying so while it runs.

    A stage that emits nothing emits nothing for as long as it takes, and a client cannot tell a
    thinking server from a dead one: an MCP session aborted `auto_decompose` at its 1800-second
    ceiling after thirty minutes of silence — and the graph HAD been changed by then, so the caller
    was left believing a no-op had happened (agent door, 2026-09-02). One model call can legitimately
    take longer than any per-message timeout, so the tick is not progress about the work; it is the
    session's evidence that the work is still there.
    """
    task = loop.run_in_executor(None, contextvars.copy_context().run, call)   # the caller's principal travels with it
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


def _a_move_here(what: str) -> None:
    """A project verb mounted beside the tools (`_mount_project_*`) is outside the signing every tool passes
    (`tools_llm._signed`): what it changes is refused here to a call no credential signs — a reader through a front
    or the LAN reads, and deletes or makes nothing (critic over the open-read change: a reader deleted a project)."""
    if (p := CALLER.get()) is not None and not p.signs_as:
        raise ValueError(f"{what} is a move, and this call is signed by no one: {p.lift}")


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
        this refusal exists for. Refused too while any node is issued and not ended, stopped or not: CANCEL its
        root and let the cancel settle first (§12.6) — under AUTO once the person has changed its mode from their page.

        Takes `project=` like every other verb; `name=` is the older spelling and still works."""
        name = name or project
        if not name:
            return {"error": "delete_project needs the project: delete_project(project='…')"}
        _a_move_here("deleting a project")
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


def _protocol(section: str = "") -> dict:
    """THE REST OF THE PROTOCOL your instructions stop short of — the modes, the loop, the workforce, a host executor, a
    second goal — for when the person asks for one: no `section`, the headings; `section='modes'` the section whose
    heading names it."""
    return _PROTOCOL.reference(section)


def _issued_by_the_person(engine, name: str) -> bool:
    """Whether a node of `engine`'s graph is held by `name` and its Del was the person's to set (§10.1): issued by him,
    or a root self-assigned to it — made at a door, every caller of which is the person locally; the system's roles
    split, they make no root."""
    g = engine.graph
    return any(str(t.assignee) == name and (str(i := g.issuer_of(t.id)) in PERSONS_NAMES
                                            or (g.get_parent(t.id) is None and str(i) == name))
               for t in g.all_tasks())


def _act_as(resolve, _Ctx):
    """The door's `act_as` over `resolve` (`_resolver`), its context typed `_Ctx`: a verb of the connection, not of a
    graph."""

    def act_as(name: str = "", token: str = "", project: str = "", ctx: _Ctx = None) -> dict:
        """WHO THIS CONNECTION SIGNS AS, and the door to take a stream's name in a console already running. No `name`:
        `{name, kind, how, signs_as}` of this connection. With `name` — a stream you opened (a node you assigned to
        it) or a name issued to you — this connection signs as that name alone from now until its gfso connection
        ends: `/clear` keeps it, and it never goes back to the person nor takes another. One live connection holds a
        name at a time. Under `gfso up --protected` pass `token`, the one `gfso agent <name>` prints at your shell."""
        if name:
            try:
                req = ctx.request_context.request
            except (ValueError, LookupError, AttributeError):
                req = None
            lease = req.headers.get(LEASE_HEADER) if req is not None else None
            p = CALLER.get()
            # …its own holding the name's token mends (a claim, under `--protected` since): that call reaches `take`
            # …and a bridge that signs nothing yet (under `--protected`) asks `take`, which wants the name's token
            if p is not None and not p.signs_as and not (p.via == signin.BARE.via or token and signin.holds(lease) == name):
                return {"refused": True, "error": f"this connection signs as no one: {p.lift}"}
            if p is not None and p.signs_as and p.via != STANDING.via and not p.via.startswith("as:"):
                return {"refused": True, "error": f"this connection signs as `{p.name}` by its {p.how}: a console "
                        f"launched with a credential keeps it; take `{name}` in a console launched without one"}
            try:
                engine = resolve(project or None, ctx, create=False)
            except Exception:           # …no project here: the names issued to him alone
                engine = None
            try:
                CALLER.set(signin.take(lease, name, token, engine is not None and _issued_by_the_person(engine, name)))
            except ValueError as ex:
                return {"refused": True, "error": str(ex)}
        return signin.whoami()
    act_as.__annotations__ = {"name": str, "token": str, "project": str, "ctx": _Ctx, "return": dict}
    return act_as


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
        if (key := _session_key(ctx)) is None or not reg.exists(name):   # the server's active one, or a new one
            _a_move_here("making a project or switching the server's active one")
        reg.engine(name)                              # validates the name + creates lazily
        _entered(reg, name, ctx)
        # Switching projects answers "which one am I in now", so it returns that and a short
        # recent list — not the whole registry. Measured on this server: 270 projects plus a
        # full last-active map, several thousand tokens of noise into the caller's context on
        # every switch, for a one-line action. The count is kept so the trim is visible rather
        # than silent, and `list_projects` remains the verb for the full inventory.
        out = _brief(reg.list(), name)
        try:   # where the graph stands and what it waits on — entering a project is a move like a signal
            e = reg.engine(name)
            out["mode"] = e.mode()
            out.update(_T.next_for(e, _agent_id(), entering=True))
        except Exception:   # gives up only the hint; the switch stands
            pass
        # …and a newer gfso, said where every task begins: nothing else would ever tell the person
        if newer := updates.newer():
            out["newer_gfso"] = newer
        return _with_ui_link("use_project", out)

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


def _named_under_a_mode(verb: str, engine, kwargs: dict) -> Optional[dict]:
    """A connection named other than the standing agent, refused in a project with a mode, or making one: a mode reads
    the standing agent as the user's own (who holds what, whose disputes the system answers), so its calls were
    decided as a stranger's — its own root offered to the system, its consent not its move (critic). Until the user's
    agent is a project's own, a named connection works in a project without a mode."""
    who = caller_id()
    if who == agent_id() or not (engine.mode() or (verb == "set_mode" and kwargs.get("mode"))):
        return None
    return {"refused": True, "error": f"this connection acts as {who!r}, and a project with a mode (solo, semi, auto) "
            f"is held by this server's standing agent {agent_id()!r}: a named connection works in a project without "
            f"a mode. Use such a project, or connect without a name."}


#: the client kind a client's own name at `initialize` stands for; a name not here is `chat`: told it holds nothing, a
#: client loses nothing (the person is told what to run), told it has a shell or a wake it lacks, it acts on neither
_KIND_OF_NAME = {"claude-code": "code"}


def _kind(request, params) -> str:
    """A connection's client kind: its bridge's header (`GFSO_CLIENT` of the door's entry), else what its client's name at
    `initialize` stands for, else `chat`. A header naming no kind is refused, never read as another."""
    said = request.headers.get(CLIENT_HEADER) if request is not None else None
    if said is not None and said not in CLIENT_KINDS:
        raise ValueError(f"this connection names its client kind {said[:40]!r}: not one of {', '.join(CLIENT_KINDS)}")
    return said or _KIND_OF_NAME.get(params.clientInfo.name if params is not None else "", "chat")


def client_kind_of(ctx) -> str:
    """The client kind of the connection a call came on (`_kind`)."""
    try:
        req = ctx.request_context.request
    except (ValueError, LookupError, AttributeError):        # stdio, or no request
        req = None
    session = _session_key(ctx)
    return _kind(req, session.client_params if session is not None else None)


def _serve_instructions_by_kind() -> None:
    """Each session is answered at `initialize` with its client kind's instructions (`protocol.BY_KIND`). The protocol
    carries instructions in the InitializeResult alone, and the SDK answers it from the session's own options, built for
    that session before the request comes (`ServerSession._received_request`, `_init_options`): a session class of its
    own, set where the SDK's lowlevel server builds its sessions by name, replaces this server's text there and no other
    server's. Private ground: `tests/test_a_connection_names_its_client.py` fails on an SDK that no longer reads it."""
    if _lowlevel.ServerSession is not _ServerSession:
        return

    class KindSession(_ServerSession):
        """A session served its client kind's instructions."""

        async def _received_request(self, responder):
            match responder.request.root:
                case _types.InitializeRequest(params=params) if self._init_options.instructions in _PROTOCOL.BY_KIND.values():
                    meta = responder.message_metadata
                    try:
                        kind = _kind(meta.request_context if meta is not None else None, params)
                    except ValueError:      # …its every call refuses the header; the text it reads meanwhile is chat's
                        kind = "chat"
                    self._init_options.instructions = _PROTOCOL.served(kind)
            return await super()._received_request(responder)
    _lowlevel.ServerSession = KindSession


def _principal_of(ctx):
    """Who this call's connection comes from (`signin.principal_of`): over HTTP its request's credential; over stdio, with
    no request, this process's own (`signin.local_principal`)."""
    try:
        req = ctx.request_context.request
    except (ValueError, LookupError, AttributeError):        # stdio, or no request: one process, one credential
        req = None
    return signin.principal_of(req) if req is not None else signin.local_principal(mcp=True)


#: the sessions whose client has been said in the server's log, held weakly: an entry dies with its session
_MET: "weakref.WeakSet" = weakref.WeakSet()


def _met(ctx) -> None:
    """The client a session's `initialize` named and the capabilities it declared, said once in the server's log: what
    Claude Desktop or another client sends is read there, never assumed (the client kind, `client_kind`)."""
    session = _session_key(ctx)
    if session is None or session in _MET or session.client_params is None:
        return
    _MET.add(session)
    params = session.client_params
    info = params.clientInfo
    print(f"[gfso] a client connected: {info.name} {info.version}, declaring "
          f"{json.dumps(params.capabilities.model_dump(exclude_none=True))}", flush=True)


def create_server(engine_or_registry):
    """Register every tools.py function on a FastMCP server (a bare Engine or a ProjectRegistry —
    with a registry every tool gains the optional `project` param + the use_project/list_projects
    verbs). Raises if the MCP SDK is absent."""
    try:
        # LEFT: the MCP SDK is optional AT IMPORT — this except is what turns its absence into the
        # message below instead of an ImportError on `import gfso.mcp.server`.
        from mcp.server.fastmcp import Context, FastMCP
    except ImportError as e:  # pragma: no cover
        raise RuntimeError("MCP SDK not installed — reinstall the package: `pip install gfso`") from e
    # The user-agent's protocol travels as the server's INSTRUCTIONS (delivered at initialize), by the client's kind
    # (`gfso.mcp.protocol`): the agent starts knowing WHAT GFSO is and HOW to drive it with what its client has.
    _serve_instructions_by_kind()

    class _Door(FastMCP):
        """Every call is signed by ITS connection's principal: a server serving several consoles signed them all by its
        own environment, so `engineering`'s ACCEPT landed as `agent` and was refused (measured 2026-11-13). The name is
        its credential's — the token its console was launched with, else the standing agent (`signin.principal_of`)."""

        async def list_tools(self):
            """The listing a client asks for right after `initialize`: where its session is first seen."""
            _met(self.get_context())
            return await super().list_tools()

        async def call_tool(self, name, arguments):
            """The verb, served under its connection's principal and client kind for that call alone."""
            _met(ctx := self.get_context())
            token, kind = CALLER.set(_principal_of(ctx)), CLIENT.set(client_kind_of(ctx))
            try:
                return await super().call_tool(name, arguments)
            finally:
                CALLER.reset(token)
                CLIENT.reset(kind)
    server = _Door("gfso", instructions=_PROTOCOL.BY_KIND["chat"])
    # Bound from `T.TOOLS[...]`, not the module functions — the registry entries are the ones wrapped to announce
    # themselves in INFLIGHT; bound to the bare functions, `/api/runtime` reported `busy: []` through a decomposition.
    for name, fn in T.TOOLS.items():
        server.add_tool(_bind(engine_or_registry, fn), name=name, description=(fn.__doc__ or "").strip(),
                        meta=ANSWER_ROOM.get(name))
    server.add_tool(_protocol, name="protocol", description=(_protocol.__doc__ or "").strip())   # the door's own text
    act_as = _act_as(_resolver(engine_or_registry), Context)
    server.add_tool(act_as, name="act_as", description=(act_as.__doc__ or "").strip())
    if hasattr(engine_or_registry, "use"):    # ProjectRegistry → the project verbs
        _mount_project_verbs(server, engine_or_registry)
    return server
