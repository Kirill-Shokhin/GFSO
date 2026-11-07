"""The Claude Code provider (`ClaudeCodeProvider`) — one `claude -p` subprocess per call, started by its execution.

THE Anthropic transport (the only one): each call is a fresh process and a single-request generation —
exactly the call shape the decompose loop was calibrated on; an agent run may continue a named conversation
(`workspaces.session_key`). Its credential is the provider's (`credentials`, provider `claude`): a subscription's
token or an API key, given to the CLI's own process alone, its tools' shells scrubbed of it; with none in force, no call
runs (the host's own login is no credential the provider lists). Nothing inherited reaches the child — an inherited key silently outranked the login (measured live).
Structured output = the shared
provider-agnostic machinery (`structured.py`): appended fenced-json instruction + parse + one repair
retry — the schema is enforced by validation here, never trusted to the transport.
"""
from __future__ import annotations

import json
import logging
import math
import subprocess
import sys
import threading
import time
import uuid
from pathlib import Path
from urllib.parse import urlparse

from gfso.core.types import ExecutionPort, PlaceUnavailable
from . import credentials
from .base import RecordingProvider
from .stats import is_limit, is_unauthorized, refused_by_limit
from .structured import holds_an_object
from gfso.config import MODEL_DEFAULT, agent_trace_dir, subprocess_env
from gfso.adapters.execution import LocalExecution, scrubs

log = logging.getLogger(__name__)

#: each model's window as the CLI last reported it — a hooked session's ceiling is set before its first turn reports one
_WINDOWS: dict[str, int] = {}
#: the handover hook as this package ships it, copied beside the CLI's state where the CLI can run it (`arm`)
_HOOK = Path(__file__).with_name("handover_hook.py")


def _obj(v) -> dict:
    """A stream value as a mapping, or an empty one. The CLI's stream is not ours to type: an event whose
    `message` arrived as a string killed the whole call on `.get` (measured in two E3 runs, each time a
    ⊥ the validator never earned), so every field is read through this — never by trusting its shape."""
    return v if isinstance(v, dict) else {}


def _turn_context(ev: dict, inner: dict) -> int:
    """HOW FULL THE CONTEXT GOT on the turn this event reports: what its message was read over — fresh input,
    what it wrote to the cache and what it read from it; 0 for an event that reports no turn. The envelope only
    sums the turns, and a sum of twenty turns over one growing context says nothing about how close any of them
    came to the window."""
    turn = _obj(_obj(ev.get("message") or inner.get("message")).get("usage"))
    return sum(_count(turn.get(k)) for k in ("input_tokens", "cache_creation_input_tokens", "cache_read_input_tokens"))


def _who_ran(envelope: dict, asked: str) -> dict:
    """THE MODEL THAT RAN A SESSION, not the name it was asked by — an alias (`sonnet`) is whatever the CLI resolves
    it to that day — and that model's window: the envelope's `modelUsage` entry that cost most. With no such entry,
    `asked` — the model its turns named, else the one asked for — and no window."""
    model, use = max(((m, _obj(u)) for m, u in _obj(envelope.get("modelUsage")).items()),
                     key=lambda mu: _count(mu[1].get("costUSD")), default=(asked, {}))
    return {"model": model or asked, "context_window": _count(use.get("contextWindow")) or None}


def _summed(turns) -> dict:
    """The usage of a session's turns, summed — its totals when no result event carried them."""
    keys = ("input_tokens", "output_tokens", "cache_read_input_tokens", "cache_creation_input_tokens")
    return {k: sum(_count(t.get(k)) for t in turns) or None for k in keys}


def _ended(envelope: dict, torn: bool) -> str:
    """How a session ended: `answered`; `cut` (its stream stopped before a result); `limit` (the account's);
    `unauthorized` (the account signed out or refused);
    else the CLI's own terminal reason (`prompt_too_long` …), or `error`."""
    if torn:
        return "cut"
    if not envelope.get("is_error"):
        return "answered"
    said = f"{envelope.get('api_error') or ''} {envelope.get('result') or ''}"
    if is_limit(said):
        return "limit"
    if is_unauthorized(said):
        return "unauthorized"
    return str(envelope.get("terminal_reason") or "error")


def _lifts_at(ev: dict):
    """When the account's limit that refused this call lifts (epoch s), if the event says: the CLI's
    `rate_limit_event`, or the refused turn's `api_error_params` — `rejected` only, an `allowed` one reports every call."""
    info = _obj(ev.get("rate_limit_info")) or _obj(_obj(ev.get("api_error_params")).get("rate_limit_info"))
    return _count(info.get("resetsAt")) or None if info.get("status") == "rejected" else None


def _count(v) -> float:
    """A stream value as a number, or zero — read through like `_obj`, for the same reason."""
    return v if isinstance(v, (int, float)) and not isinstance(v, bool) else 0


def _tool_use_name(ev: dict) -> str | None:
    """The tool a stream event announces, if it announces one.

    stream-json carries tool calls as content blocks; a validator that claims "Executed: …" while
    never opening Bash is claiming something it did not do, and that is decidable HERE, structurally,
    without parsing its prose or trusting it. Measured need: 4 of 7 checkable claims in one run's
    verdicts described executions that did not match the artefact they validated.
    """
    return str(block["name"]) if (block := _tool_use(ev)) else None


def _tool_use(ev: dict) -> dict | None:
    """The tool call block a stream event announces, if it announces one (`_tool_use_name`)."""
    inner = _obj(ev.get("event"))
    content = _obj(ev.get("message")).get("content")
    for block in (ev.get("content_block"), inner.get("content_block"), ev.get("delta"), inner.get("delta"),
                  *(content if isinstance(content, list) else [])):
        if isinstance(block, dict) and block.get("type") == "tool_use" and block.get("name"):
            return block
    return None


def _tool_results(ev: dict) -> list:
    """The tool results a stream event carries back to the model."""
    content = _obj(ev.get("message")).get("content")
    return [b for b in (content if isinstance(content, list) else []) if _obj(b).get("type") == "tool_result"]


def _refusal(sess: ExecutionPort, proc, ran: int) -> dict:
    """WHY A SESSION WHOSE COMMANDS RUN APART IS REFUSED (`ExecutionPort.commands_env`), as its call's record says it —
    the place's stop, as every call of the place would meet it — or {}: its CLI ran a bash beside itself — it takes no
    shell it finds wrong, and says nothing (CLI 2.1.310) — which the system's guard there refused and put on the record;
    or its commands ran (`ran`, the Bash results that were no error) and the record of `proc`'s holds none. A command
    beside the CLI could forge the stream the call is read from. {} where no record is kept."""
    if (record := sess.commands_of(proc)) is None:
        return {}
    why = ("the agent CLI did not take the system's shell (CLAUDE_CODE_SHELL): it ran its commands' shell beside "
           "itself, where they are refused" if any(r.get("beside") for r in record) else
           f"the agent CLI's commands did not come through the system's shell: {ran} ran, its record holds none"
           if ran and not any("argv" in r for r in record) else None)
    return {"ended": "unavailable", "place": sess.name, "error": why} if why else {}


def _cannot_resume(out: dict) -> bool:
    """Did the CLI refuse to go on with the conversation itself — as opposed to the round ending badly inside it? A round
    cut at its turn cap is `is_error` too (`error_max_turns`), and it is exactly the round the conversation exists to
    continue; a usage limit or an API error says nothing about the conversation either."""
    said = json.dumps(out).lower()
    return out.get("subtype") != "error_max_turns" and any(
        k in said for k in ("no conversation found", "prompt is too long", "context window", "context length"))


def _traced(trace, line: str):
    """Write the line to the agent trace, or end the trace: it is an audit aid, and losing it never costs the call."""
    if trace is None:
        return None
    try:
        trace.write(line)
        return trace
    except OSError as e:
        log.warning(f"agent trace stopped ({e})")
        return None


def _is_the_answer(result: dict, live: bool) -> bool:
    """Is this `result` event the call's answer — it carries one, or nothing the session left running can still lead
    to one? Both stream shapes are real: an executor delivered its report as the first result and, kept alive by a
    command it had left in the background, answered a later notification with a line that replaced the report
    (root.tail, AUTO haiku coreutils, 2026-10-12); and a session that ended its turn to wait for a background command
    answers "WAITING" first and its report after the notification (critic, CLI 2.1.296). First or last both misread
    one of them; what tells them apart is the answer."""
    said = result.get("result")
    return not live or (isinstance(said, str) and holds_an_object(said))


#: the variable the CLI authenticates by, per kind of credential
AUTH = credentials.CLAUDE_ENV
#: where the CLI's model answers — what a door passes to
UPSTREAM = "api.anthropic.com"
#: the name its credentials are held by in their one place (`credentials`)
PROVIDER = "claude"
#: a provider made with no credential named reads the one in force at each call's start
STORED = "stored"


def client_env(credential, scrubs: bool = True, door: tuple | None = None) -> dict:
    """A credential as the CLI's process takes it, and its tools' shells scrubbed of it where the execution can
    (`CLAUDE_CODE_SUBPROCESS_ENV_SCRUB`: the conformance battery's `env` through the tool path shows none; `scrubs`).
    Where it cannot, the tools see it — said in the log once per image (`execution.scrubs`), and the
    battery's "credential hidden" fails there. Where the execution has a `door` (`ExecutionPort.door`: its URL and
    key) the CLI holds only the door's key and calls its model through it; the door holds the credential: no process
    the CLI starts can read what it does not hold."""
    if credential and door:
        url, key = door
        host = urlparse(url).hostname
        return {"CLAUDE_CODE_SUBPROCESS_ENV_SCRUB": "0", AUTH[credential.kind]: key,
                "ANTHROPIC_BASE_URL": url, "NO_PROXY": host, "no_proxy": host}
    return {"CLAUDE_CODE_SUBPROCESS_ENV_SCRUB": "1" if scrubs else "0",
            **({AUTH[credential.kind]: credential.value} if credential else {})}


def denied(sess: ExecutionPort) -> tuple:
    """What the CLI's own writers — Edit, Write, NotebookEdit (an Edit rule covers Write) — may not touch where its
    commands run apart: its stdout, through `/proc` or `/dev`, a forged stream as a command beside it wrote; and its
    state, where the hook it runs beside itself lies. Held under `--dangerously-skip-permissions`, through a link too
    (S6 probe, CLI 2.1.310). Each path the state is mounted at — where the CLI reads it, and where its place's path maps
    (`ContainerExecution.run_args`; critic over the readers: the second was open). Its readers are not denied it: the
    CLI hands its own long outputs back through Read from there, and a link the agent makes leads Grep around any rule
    (critic over the readers, both measured)."""
    states = sorted({Path(sess.state_seen()).as_posix(), sess.to_inside(str(sess.state_dir()))})
    # …and the home the client's container runs from: a program laid on its PATH there (`~/.local/bin`) ran at the
    # client's next start, beside it (critic, live); and its `/tmp`, where a call's pid lies that its ending kills by
    return tuple(f"{t}(/{p}/**)" for t in ("Edit", "Write", "NotebookEdit")
                 for p in ("/proc", "/dev", *states, *(["/home", "/tmp"] if sess.commands_apart else [])))


def kept(execution: ExecutionPort, sid: str, what: str) -> Path:
    """What the system keeps of a conversation beside the CLI's own state — its spend so far (`spent`), its handover
    hook's state (`hook`); `forget` drops them with it."""
    return Path(execution.state_dir()) / "gfso-sessions" / f"{sid}.{what}"



def _dropped_by_the_api(calls: list) -> bool:
    """The last of these calls errored on the API's side — not refused by a limit, not cut at its turn cap. Such a
    one-shot is asked once more: with no tools it changes nothing, and its "" was read as an answer — a plan's search
    that ended in "API Error: JSON Parse error" was folded as "no findings" (gb-coreutils-tnrqbl588, 2026-10-31). The
    caller passes the call's OWN record: readings run in parallel on one provider (critic)."""
    last = next((c for c in reversed(calls) if isinstance(c, dict)), None)
    return bool(last and last.get("error") and not refused_by_limit(calls) and last.get("stop_reason") != "max_turns"
                and not last.get("refused"))


def _once_more(one_shot: bool, call, last_record) -> str:
    """`call()`, and once more where it was a tool-less one-shot the API dropped (`_dropped_by_the_api`)."""
    text = call()
    if one_shot and not text and _dropped_by_the_api([last_record()]):
        log.warning("headless claude one-shot ended in an API error — asked once more")
        text = call()
    return text


class _Hooks:
    """THE HANDOVER HOOK of one execution's CLI (`budget.hooked`): the script copied beside the CLI's state, a session's
    state written there before it runs and read back after, and the flags that let the CLI run it."""

    #: what the system arms a session with (`budget.hooked`) — the rest of its state is the hook's readings
    ARMS = ("budget", "ceiling", "reopen", "boundary")

    def __init__(self, execution: ExecutionPort):
        self._exec, self._at, self.armed = execution, {}, set()

    def where(self, sid: str | None) -> ExecutionPort:
        """The execution the conversation `sid` runs in (`ExecutionPort.session`), once a call or an arming named its
        place: a session in its own place keeps its CLI state there — the others' conversations and the system's notes
        on them out of its reach."""
        return self._at.get(sid, self._exec)

    def place(self, sid: str | None, cwd: str | None, agent: str | None = None) -> None:
        """The conversation `sid` runs in the session of `cwd` from now on, as `agent`'s."""
        if sid and cwd:
            self._at[sid] = self._exec.session(cwd, agent)


    def arm(self, sid: str, state: dict) -> None:
        """The hook armed for the conversation `sid`: the script where the CLI runs it, the session's line, ceiling and
        checked-point request where it reads them — one write where its session runs."""
        f = kept(ex := self.where(sid), sid, "hook")
        ex.files.write_files(str(f.parent), {_HOOK.name: _HOOK.read_bytes(), f.name: json.dumps(state).encode()})
        self.armed.add(sid)

    def across(self, sid: str, forget) -> None:
        """`forget` the conversation `sid` and arm the hook again for the cold run that replaces it: as armed, its
        readings gone."""
        armed = self.state(sid) if sid in self.armed else None
        forget(sid)
        if armed is not None:
            self.arm(sid, {**{k: armed[k] for k in self.ARMS if k in armed}, "resumed": False})

    def state(self, sid: str) -> dict:
        """What the hook left of the session `sid` — `{}` where it left nothing readable."""
        try:
            return json.loads((ex := self.where(sid)).files.read_text(str(kept(ex, sid, "hook"))) or "")
        except (OSError, ValueError):
            return {}

    def settings(self, sid: str | None, denied: tuple = ()) -> str:
        """The settings a call carries over the operator's: no language, no hook but the system's own handover hook on a
        conversation it armed one for, and the CLI's own writers kept off what `denied` names."""
        deny = {"permissions": {"deny": list(denied)}} if denied else {}
        if sid not in self.armed:
            return json.dumps({"disableAllHooks": True, "language": "", "autoMemoryEnabled": False, **deny})
        # …on this host the server's own interpreter: `python3` on a Windows PATH is the Store's stub, which runs nothing
        py = Path(sys.executable if isinstance(self.where(sid), LocalExecution) else "python3").as_posix()
        at = f"{Path(self.where(sid).state_seen()).as_posix()}/gfso-sessions/{_HOOK.name}"
        # …and no auto-memory: with no setting source loaded the CLI still read the operator's MEMORY.md (probed, CLI
        # 2.1.311: "# Memory index" quoted); in a container it would carry one session's notes to the next outside the log
        return json.dumps({"language": "", "autoMemoryEnabled": False, "hooks": {"PostToolUse": [
            {"matcher": "*", "hooks": [{"type": "command", "command": f'"{py}" "{at}"'}]}]}, **deny})

    def clean(self, sid: str | None) -> list[str]:
        """What keeps the operator and the repository out of the call: no setting source loaded — the person's and the
        project's CLAUDE.md, skills and hooks stay out (probed on CLI 2.1.311, haiku 5.5: neither CLAUDE.md read, no skill
        listed, the handover hook's word reached the model). Not `--safe-mode`: under it the CLI still read the cwd's
        `.claude/settings.json`, and a delivered `apiKeyHelper` ran beside a judge's client and forged its verdict
        (critic, live)."""
        return ["--setting-sources", ""]


_SET_TOKEN = f"run `claude setup-token`, then `gfso credential {PROVIDER}`"
#: what lifts a refusal, by the kind refused — `claude login` lifts none: no call runs on a login, only on the store
_REFUSED = {"token": f"{PROVIDER}'s token was refused: {_SET_TOKEN} (`claude login` cannot help: no call runs outside "
                     f"the credential store)",
            "api": f"{PROVIDER}'s API key was refused: set a working one with `gfso credential {PROVIDER} --kind api`"}


class _Credentials:
    """WHICH CREDENTIAL A CALL RUNS ON, apart from how it runs: the one given, or its provider's in force at the call's
    start (`credentials.current`); refused by that one's limit or sign-in, it is marked spent, the pointer moves to the
    next in the order and the call runs again there — its refused attempt booked as `moved`, which stops nothing. Only
    with every one spent does the refusal stand, and the project stops until the first of them lifts
    (docs/notes/PROJECT_CLOCK.md, case 10). Every record a call makes names the credential it ran on (`_booked`)."""

    credential_kinds = tuple(AUTH)
    #: the credential each thread's call runs on, and its last record — a thread runs one call at a time
    _mine = threading.local()

    def _on_credentials(self, run) -> str:
        """`run(credential)` — one attempt of the call — until it is not refused or nothing is left to move to."""
        while True:
            try:
                name, cred = self._in_force()
            except (OSError, ValueError) as e:
                return self._no_store(e)
            self._mine.name, self._mine.kind, self._mine.last = name, cred.kind, None
            text = run(cred)
            # …THIS thread's last record, on the credential it ran on: one provider serves parallel calls (`parallel_safe`),
            # and a cold resume inside the attempt ran a call of its own, which may have moved on (critic)
            last = self._mine.last or {}
            name = last.get("credential")
            # …settled already where a cold resume's own call ran it to the end (critic: spent twice, shorter)
            if last.get("_settled") or not (name and last.get("ended") in ("limit", "unauthorized")):
                return text
            try:
                nxt = credentials.spend(PROVIDER, name, last.get("limit_resets_at"))
            except (OSError, ValueError) as e:
                log.warning(f"the credential store took no mark of {name}'s refusal: {e}")
                return text                    # the refusal stands as it is: the project stops on it, as before
            if nxt is None:
                last.update(_settled=True, limit_resets_at=credentials.lifts(PROVIDER) or last.get("limit_resets_at"))
                return text
            # …words that name no limit: the attempt is no refusal of the call, which runs on (`refused_by_limit`)
            last.update(ended="moved", limit_resets_at=None, error=f"{last['ended']} on {name}: moved to {nxt}")

    def _in_force(self) -> tuple:
        """(name, credential) a call starts on: the one given, or the provider's in force now."""
        if self._credential is None:
            # …None once meant the host's login: the same fallback no credential list declares, by another door
            raise ValueError("a provider made with no credential runs on no one's: name one, or leave it to the "
                             f"provider's store ({credentials.where()})")
        if self._credential is not STORED:
            return None, self._credential
        if (got := credentials.current(PROVIDER)) is None:
            # …NO CALL OUTSIDE ITS PROVIDER: with nothing in force in the one place, the CLI ran on whatever login its host
            # held — a fallback no credential list declared, and a bench whose home held no store spent a subscription
            # half a wave while the provider's API key stood unused (2026-11-01). A fallback is an entry of the list.
            raise ValueError(f"no credential of {PROVIDER!r} is in force in {credentials.where()}: {_SET_TOKEN}; no call "
                             f"runs outside its provider")
        return got

    def _no_store(self, e: Exception) -> str:
        """THE STORE DOES NOT READ: no call can say which credential it runs on — not the node's failure, and not the
        host's login either. Booked as a refused sign-in, so the project stops until a person mends it, no node is
        parked (critic: it was one retry, then parked)."""
        self._mine.name = None
        self._booked({"duration_ms": 0, "model": self._model, "ended": "unauthorized", "error": str(e)[:300],
                      "remedy": str(e), "transport_torn": False, "resumed": False, "at": time.time()})
        return ""

    def _booked(self, rec: dict) -> None:
        """One call's record, naming the credential this thread's call ran on."""
        rec["credential"] = self._mine.name
        if rec.get("ended") == "unauthorized" and "remedy" not in rec:   # …`_no_store`'s has one, on a thread with no `kind` yet
            rec["remedy"] = _REFUSED[self._mine.kind]
        self._mine.last = rec
        self._book(rec)


class ClaudeCodeProvider(_Credentials, RecordingProvider):
    """Anthropic's models through the Claude Code CLI: this class builds every `claude -p` invocation and reads its
    stream; WHERE the process runs is its execution's (`ExecutionPort`, this host by default)."""
    #: each call is its own `claude -p` process, so independent readings may run at once (`stats.readings`)
    parallel_safe = True
    runs_agents = True
    #: the CLI runs a hook after each tool call, so a session's context is read and handed over inside its one process
    handover_hook = True

    def __init__(self, model: str = MODEL_DEFAULT, timeout: int = 900, claude_cmd: str = "claude",
                 max_thinking_tokens: int | None = None, execution: ExecutionPort | None = None,
                 credential=STORED):
        super().__init__(model)
        self._timeout = timeout
        self._exec = execution or LocalExecution()
        self._cmd = self._exec.which(claude_cmd)
        # Latency lever: per-call wall time is dominated by OUTPUT tokens, and thinking tokens bill into
        # output. Caps the child CLI's thinking budget (MAX_THINKING_TOKENS env); None = CLI default.
        self._max_thinking = max_thinking_tokens
        # `credentials.Credential` given (None is refused at the call: no host login); by default the provider's one in force at each
        # call's start (`credentials.current`), so a moved pointer reaches every new call and none in flight
        self._credential = credential
        self.last_model = ""          # the model its turns name — what a cut session ran on
        self.last_turns: dict = {}    # each turn's own usage, by message id — what a cut session spent
        self._turn_id = ""            # the message whose closing `message_delta` is still to come
        self.last_lift = None         # when the account's limit that refused the call being read lifts (`_lifts_at`)
        self.hooks = _Hooks(self._exec)  # the handover hook of this execution's CLI (`arm`), and where each runs
        # Live ticks are REAL (stream-json + partial messages: actual output tokens so far), never an estimate.
        self._tick_every = 2.0
        if self._cmd is None:
            log.warning("claude CLI not found — headless LLM degraded to stub")

    @property
    def execution(self) -> ExecutionPort:
        """Where its processes run."""
        return self._exec

    def _transcripts(self, sid: str) -> bool:
        """Does the CLI keep the conversation — `<its state dir>/projects/<its cwd, encoded>/<id>.jsonl`?"""
        at = Path((ex := self.hooks.where(sid)).state_dir()) / "projects"
        return any(ex.files.exists(str(at / d / f"{sid}.jsonl")) for d in ex.files.listdir(str(at)))

    def forget(self, session: str) -> None:
        """Drop a conversation's transcript: the work it served is settled, or it would not resume — and what this
        execution keeps of it beside the CLI's state, whichever provider kept it (a chat run's transcript too: the
        workspaces forget a project's conversations through one provider)."""
        # …wherever its session kept it: a place's state lies under its project's (`PlaceContainer`), and a server
        # that restarted no longer knows which place a conversation ran in — two levels: never the whole home
        self._exec.files.remove_matching(str(self._exec.state_dir()), [
            f"{at}{p}" for at in ("", "*/") for p in (f"projects/*/{session}.jsonl", f"gfso-sessions/{session}.*")])
        self.hooks.armed.discard(session)

    def _own_cost(self, sid: str | None, total, resumed: bool):
        """THE ROUND'S OWN COST: on `--resume` the CLI's `total_cost_usd` is the whole conversation's, so a continued
        round of one turn booked $1.64, its predecessor's $1.60 again (GB_sql_database_tnildb300, 4 rounds, +$5.86).
        Less what the conversation had cost when the round before it was cut; None stays None."""
        if not (resumed and sid and isinstance(total, (int, float))):
            return total
        try:
            before = float((ex := self.hooks.where(sid)).files.read_text(str(kept(ex, sid, "spent"))) or "")
        except (OSError, ValueError):
            return total                   # nothing kept (a conversation from before this was kept): as the CLI said
        return max(0.0, total - before)

    def _session_args(self, sid: str | None) -> list[str]:
        """A call naming no conversation SAVES none: each would otherwise land in the operator's session history for
        its directory (measured on one install: 10 459 internal transcripts beside 18 of the person's own, and `claude
        --resume` took over three minutes to list them). A named one lives under its node's own place, not the
        person's."""
        if not sid:
            return ["--no-session-persistence"]
        return ["--resume", sid] if self._transcripts(sid) else ["--session-id", sid]

    def window(self) -> int | None:
        """The model's window as the CLI last reported it, or None before any call did."""
        return _WINDOWS.get(self._model)

    def arm(self, sid: str, state: dict, cwd: str | None = None) -> None:
        """The handover hook armed for `sid` (`_Hooks.arm`) where its session will run (`cwd`), told whether the
        conversation continues an earlier run."""
        self.hooks.place(sid, cwd, self.agent)
        self.hooks.arm(sid, {**state, "resumed": bool(self._transcripts(sid))})

    def _never_started(self, e: PlaceUnavailable, resumed: bool) -> str:
        """NOTHING STARTED: read as an empty answer, a dead Docker daemon was redialled as a cut call four times, then
        parked the node as an unreadable report (GB_sql_database_tnij0m952). Recorded as its own ending, so booking it
        stops the project (`Engine.record_llm_usage`); no answer."""
        self._booked({"duration_ms": 0, "model": self._model, "ended": "unavailable", "place": e.place,
                           "error": str(e), "transport_torn": False, "resumed": resumed, "at": time.time()})
        return ""

    def _after_the_round(self, sid: str | None, out: dict, mine: list) -> None:
        """ONLY A ROUND CUT AT ITS TURN CAP IS CONTINUED: the next round of any other starts with a clean context, each
        agent's own (the author, 2026-09-27: «агенты … с чистым контекстом дешево»). Measured continuing every round
        (GB_sql_database_tn9nii608): a disputing executor repeated its challenge out of the conversation every 24 s, 40
        calls, each one's input 16k tokens longer."""
        if mine and mine[-1].get("context_window"):
            _WINDOWS[self._model] = mine[-1]["context_window"]
        # …and one its handover hook stopped at the ceiling: its note is asked for by that conversation (`budget.hooked`);
        # the hook's word is the round's, on its record
        hook = self.hooks.state(sid) if sid in self.hooks.armed else None
        if hook is not None and mine:
            mine[-1]["hook"] = hook
        if sid and out.get("subtype") != "error_max_turns" and not (hook or {}).get("stopped"):
            self.forget(sid)
        elif sid and isinstance(out.get("total_cost_usd"), (int, float)):
            (ex := self.hooks.where(sid)).files.write_bytes(str(kept(ex, sid, "spent")),
                                                            str(out["total_cost_usd"]).encode())

    def agent_round(self, system: str, user: str, allowed_tools: tuple[str, ...],
                     cwd: str | None = None, timeout: int | None = None,
                     max_turns: int | None = None, session: str | None = None) -> str:
        """Port B — the AGENT-RUNNER: one headless run WITH work tools (multi-step inside one
        process), returning its final report text. Headless-by-necessity: an agent run needs a harness
        (tools/permissions/cwd); a chat API gets one from the system's own loop (`toolloop.ToolLoop`).
        `--dangerously-skip-permissions` is REQUIRED for non-interactivity (headless can't answer
        prompts); the safety envelope = the tool allowlist + scoped cwd (probed live 2026-07-03).
        `timeout` = a per-run process cap (e.g. deadline-derived); on expiry the process is killed and
        NO signal is forged — the FSM's timeout monitor owns escalation (one clock)."""
        # A run with NO cwd inherits the SERVER's, which is the state home (`~/.gfso`) — a directory
        # holding the databases and containing none of the user's work. An agent with write and
        # shell tools loose in there is both useless and unsafe, and it fails in the worst possible
        # way: a validator reports on artifacts it cannot see, so the verdict is wrong rather than
        # absent. Whoever spawns an agent names its directory.
        if not cwd:
            raise ValueError(
                "an agent run needs a working directory: without one it would run where the server "
                "stands (the gfso state home), which holds none of the work being validated. Pass "
                "`workdir` — to validate_result, or in the agent's registration.")
        # `max_turns` is a term of the AGENT's contract, not of the transport: how many steps one
        # run may take before it stops. It exists so a delegated executor can be given the same
        # envelope as an agent driven from outside — without it, two runs of "the same" agent differ
        # in a way nothing records, and a comparison between them measures the difference.
        # THE ALLOWLIST APPROVES; `--tools` IS WHAT LOADS. With the approval list alone every run carried
        # the schemas of all ~28 built-in tools, re-read on every call: 58% of a validator's cached input
        # (2026-09-27), and a read-only validator holding Write and Edit.
        loaded = ",".join(dict.fromkeys(t.split("(", 1)[0].strip() for t in allowed_tools))
        if session:                                      # a named conversation's CLI state is its place's from here on
            self.hooks.place(session, cwd, self.agent)
        return self._call(system, user, cwd=cwd, timeout=timeout, session=session,
                          tools_args=["--tools", loaded,
                                      "--allowedTools", " ".join(allowed_tools),
                                      "--dangerously-skip-permissions"]
                                     + (["--max-turns", str(max_turns)] if max_turns else []))

    def _read_stream(self, proc, t0: float, cap: float):
        """Read the CLI's event stream: usage, deltas, tool names, and the ticks a caller sees.

        The subprocess is one concern (build the argv, spawn it, wait, account for the call);
        reading what it streams is another, and it is where the live progress comes from —
        real output tokens, never an estimate. Returns (envelope, text, out_tokens)."""
        envelope, text_acc, out_tokens, last_tick = None, [], 0, t0
        self.begin_run()
        self.last_model, self.last_turns, self._turn_id, self.last_lift = "", {}, "", None
        # WHAT AN AGENT RUN DID, KEPT WHEN ASKED (`GFSO_AGENT_TRACE_DIR`): each call's raw stream, one
        # file per call. `--no-session-persistence` keeps these runs out of the operator's history, which
        # also left no record of what a delegated executor or validator actually ran — an audit that reads
        # the tool calls (a leak check, a claim of execution) had nothing to read.
        trace = None
        if (tdir := agent_trace_dir()):
            try:
                Path(tdir).mkdir(parents=True, exist_ok=True)
                trace = open(Path(tdir) / f"{time.strftime('%Y%m%dT%H%M%S')}-{uuid.uuid4().hex[:8]}"
                             f"-{''.join(c if c.isalnum() else '_' for c in (self.stage_hint or 'call'))[-60:]}.jsonl",
                             "w", encoding="utf-8", buffering=1)   # line by line: a killed server keeps the tail
            except OSError as e:
                log.warning(f"agent trace not kept ({e})")
        # THE CAP FIRES WHETHER OR NOT THE CHILD SPEAKS. It was checked only as a line arrived, so a child that
        # goes silent holds the read past any cap, and only the node's state bound ends the wait around it (a root
        # validation stood 340 minutes with no answer across a sleep of the machine, AUTO json_parser, 2026-09-28).
        timer = threading.Timer(max(0.0, cap - (time.monotonic() - t0)), self._exec.end, args=(proc,))
        timer.daemon = True
        # …and no cap, none: a timer over an unbounded wait overflowed in its own thread (OverflowError, time_t)
        timer.start() if math.isfinite(cap) else None
        try:
            return self._read_lines(proc, t0, cap, envelope, text_acc, out_tokens, last_tick, trace)
        finally:
            timer.cancel()
            if trace is not None:
                try:
                    trace.close()
                except OSError:                # a failed flush of an audit aid never replaces the answer
                    pass

    def _observe(self, ev: dict, inner: dict) -> None:
        """What one event says about the session itself: a tool it called, how full its context got."""
        self.note_peak(_turn_context(ev, inner))
        self.last_lift = _lifts_at(ev) or self.last_lift
        msg = _obj(ev.get("message") or inner.get("message"))
        self._note_turn(msg, inner)
        named = msg.get("model")
        if isinstance(named, str) and named and not named.startswith("<"):   # `<synthetic>`: the CLI's own refusal
            self.last_model = named
        self.note_tools(_tool_use(ev), _tool_results(ev))

    def _note_turn(self, msg: dict, inner: dict) -> None:
        """A turn's own usage, by message id. What it was read over arrives with the message; its output arrives
        in the `message_delta` that closes it, which names no message — kept under the message last started (the
        message's own usage carries a token or so of output: summed alone it was 0.36% of the real output)."""
        if msg.get("id"):
            self._turn_id = msg["id"]
            if (u := dict(_obj(msg.get("usage")))):
                u["output_tokens"] = max(_count(u.get("output_tokens")),
                                         _count(self.last_turns.get(msg["id"], {}).get("output_tokens")))
                self.last_turns[msg["id"]] = u
        if inner.get("type") == "message_delta" and self._turn_id in self.last_turns:
            t = self.last_turns[self._turn_id]
            t["output_tokens"] = max(_count(t.get("output_tokens")), _count(_obj(inner.get("usage")).get("output_tokens")))

    def _read_lines(self, proc, t0, cap, envelope, text_acc, out_tokens, last_tick, trace):
        live = False      # a background task of the session is still running (`background_tasks_changed`)
        for line in proc.stdout:
            trace = _traced(trace, line)
            if time.monotonic() - t0 > cap:
                self._exec.end(proc)
                log.warning("headless claude call timed out mid-stream")
                break
            line = line.strip()
            if not line:
                continue
            try:
                ev = _obj(json.loads(line))
            except Exception:
                continue
            live = bool(ev.get("tasks")) if ev.get("subtype") == "background_tasks_changed" else live
            if ev.get("type") == "result":
                envelope = ev
                if _is_the_answer(ev, live):
                    break
                continue
            inner = _obj(ev.get("event"))
            self._observe(ev, inner)
            usage = _obj(inner.get("usage")) or _obj(ev.get("usage"))
            if isinstance(usage.get("output_tokens"), int):
                out_tokens = usage["output_tokens"]
            delta = _obj(inner.get("delta"))
            if isinstance(delta.get("text"), str):
                text_acc.append(delta["text"])
            chunk = delta.get("text") or delta.get("thinking")  # thinking streams tokens too
            if isinstance(chunk, str):
                est_chars = getattr(self, "_est_chars", 0) + len(chunk)
                self._est_chars = est_chars
            now = time.monotonic()
            if self.on_tick is not None and now - last_tick >= self._tick_every:
                last_tick = now
                tok = out_tokens or (getattr(self, "_est_chars", 0) // 4)
                try:
                    self.on_tick(f"{self.stage_hint or 'generating'}: {tok} tokens · {now - t0:.0f}s")
                except Exception:
                    pass  # a token tick is presentation — never break the generation it is reporting on

        return envelope, text_acc, out_tokens

    def _call(self, system: str, user: str, tools_args: list[str] | None = None,
              cwd: str | None = None, timeout: int | None = None, session: str | None = None) -> str:
        """One fresh `claude -p` subprocess, STREAMED (stream-json + partial messages): while the model
        generates, cumulative output tokens tick to `on_tick` — real progress, never an estimate. The
        final `result` event carries the same envelope the aggregate json format did (usage,
        duration_ms, is_error, result); if it is missing, the accumulated delta text is the fallback.
        Default = a zero-tool one-shot (Port A); `tools_args`/`cwd` = an agent run (Port B). On the credential `_Credentials` gives it."""
        if self._cmd is None:
            return ""
        # …and a call naming no place runs in an empty one of its own, never where the server stands: there the plan's
        # author took the state home for the work's directory, pinned `cd <home> && …` on every probe of a plan, and a
        # validator following one removed the project's own database (GB_sql_database_tmzgc0724, 2026-10-16)
        if not cwd:
            with self._exec.scratch("gfso-noplace-") as empty:
                return self._call(system, user, tools_args, empty, timeout, session)
        return _once_more(tools_args is None, lambda: self._on_credentials(
            lambda cred: self._attempt(cred, system, user, tools_args, cwd, timeout, session)), lambda: self._mine.last)

    def _attempt(self, credential, system: str, user: str, tools_args, cwd: str, timeout, session) -> str:
        try:
            resuming = self._session_args(session)      # …read where its session keeps it: a dead place stops first
        except PlaceUnavailable as e:
            return self._never_started(e, False)
        # in the session's own place (`ExecutionPort.session`): it writes there alone and sees no other node's
        sess = self._exec.session(cwd, self.agent).client()
        args = [self._cmd, "-p", "--model", self._model, "--system-prompt", system,
                # The CLI inherits the USER's MCP configuration, and this installation registers its
                # own door there — so every internal call (decompose, the Level-2 review, the
                # validator) started the gfso stdio bridge as a child, each in its own console
                # window: the empty windows are that bridge, not the model. Two reasons to pin it
                # shut rather than hide the window: this layer's calls need no gfso tools at all,
                # and a VALIDATOR holding them could sign the graph it is validating (§10.3). With
                # --strict-mcp-config and no --mcp-config, no MCP server is started.
                "--strict-mcp-config",
                # The same fact one layer over: the CLI also inherits the user's HOOKS, and a hook
                # written for a person's interactive console has no business inside an internal
                # call of this product. Measured live: a session-lifecycle hook fires in this child
                # and injects its own instructions into the run — so a run's context stops being
                # the run's. Worse for the Stop event, where a hook may REFUSE the child's exit and
                # buy extra generation rounds on a paid call, for a stop nobody was waiting on.
                # Neither is the operator's mistake; a child of ours is ours to keep clean.
                # …and the operator's LANGUAGE. `language` in the person's settings survives
                # --safe-mode and arrives as "Always respond in <x>": measured, an issuer on an
                # English goal wrote its justifications into the graph in Russian and in German.
                # The empty value removes the instruction (probed 2026-09-25: the child reports
                # none); the call's own prompt then decides, as it does for every other rule.
                # …and where its commands run apart, its own writers off its stdout and its state (`denied`)
                "--settings", self.hooks.settings(session, denied(sess) if sess.commands_apart else ()),
                # …AND THE OPERATOR'S OWN INSTRUCTIONS. Hooks and MCP were shut, and the call still
                # loaded the person's CLAUDE.md: probed 2026-09-24, an internal call listed the
                # operator's working-mode and coding rules among its instructions — so an executor or
                # a validator of this product ran under whatever its user had written for themselves.
                # No setting source drops CLAUDE.md, skills, plugins, hooks and MCP and keeps auth — and, unlike
                # `--safe-mode`, the cwd's `.claude/settings.json`, which a delivered tree carries (`_Hooks.clean`).
                *self.hooks.clean(session),
                *resuming,
                "--output-format", "stream-json", "--include-partial-messages", "--verbose",
                *(tools_args if tools_args is not None else ["--disallowedTools", "*"])]
        t0 = time.monotonic()
        cap = timeout or self._timeout
        self._est_chars = 0  # per-call char-estimate (fallback token counter while usage is absent)
        proc, out, n0 = None, {}, len(self.calls)
        try:
            # …its door first, where the execution keeps one: a place down there is the call's own ending (critic 3)
            door = sess.door(credential, UPSTREAM) if credential else None
            env = {**subprocess_env(credential=client_env(credential, door is None and scrubs(self._exec), door)),
                   **({"MAX_THINKING_TOKENS": str(self._max_thinking)} if self._max_thinking is not None else {}),
                   **sess.commands_env()}
            proc = sess.popen(args, env=env, cwd=cwd, stdin=subprocess.PIPE, stdout=subprocess.PIPE,
                              stderr=subprocess.DEVNULL, text=True, encoding="utf-8")

            def _feed():  # a writer thread — a large prompt would deadlock a same-thread pipe write
                try:
                    proc.stdin.write(user)
                    proc.stdin.close()
                except Exception as e:
                    log.warning(f"headless claude call: the prompt was never written to the child ({e})")
            threading.Thread(target=_feed, daemon=True).start()

            envelope, text_acc, out_tokens = self._read_stream(proc, t0, cap)
            if envelope is None:               # answered: whatever still runs is ended below (`kill_tree`)
                proc.wait(timeout=30)

            out = envelope or {}
            # A STREAM CUT BEFORE ITS RESULT kept no totals, and its tokens were recorded as the last tick's
            # output alone: its turns' own usage, once per message, is what it spent (input and cache as the
            # message carries them, output as its `message_delta` does — together they reproduce the envelope)
            usage = _obj(out.get("usage")) if envelope is not None else _summed(self.last_turns.values())
            self._booked({
                "at": time.time(),
                # …the process's own life, measured here: the CLI's figure is its last result's, and a command that
                # outlived it (a `make` past its Bash timeout) kept the process 12 minutes the ledger did not see (ui)
                "duration_ms": int((time.monotonic() - t0) * 1000),
                "input_tokens": usage.get("input_tokens"),
                "output_tokens": usage.get("output_tokens") or out_tokens or None,
                "cache_read_input_tokens": usage.get("cache_read_input_tokens"),
                "cache_creation_input_tokens": usage.get("cache_creation_input_tokens"),
                # The envelope has carried the cost all along and nothing read it: the tokens were
                # recorded, the dollars were dropped, and "what did this graph cost" stayed a
                # question the system could not answer about itself.
                "cost_usd": self._own_cost(session, out.get("total_cost_usd"), "--resume" in args),
                **_who_ran(out, self.last_model or self._model),   # the model that ran it and its window
                "peak_context": self.last_peak_context or None,
                "turns": _count(out.get("num_turns")) or None,
                # THE STREAM ENDED WITHOUT ITS RESULT EVENT — the call was cut, not answered.
                # Only this layer can see the difference: upstream all that survives is a short
                # answer at zero cost, and zero cost is a fact about the money and about nothing
                # else. A validator whose call was cut looks exactly like a validator whose report came back
                # thin, and the two want opposite handling — a bigger model repairs a thin report
                # and does nothing at all for a severed pipe. Measured 2026-09-06: one such call ran
                # 15 minutes, produced 232 tokens and $0.00, was read as a weak report, escalated to
                # a tier three times the price, and spent the node's last attempt; the run
                # (`database_engine`) ended on it.
                "transport_torn": envelope is None,
                # WHY A SESSION GAVE NO ANSWER, kept with it: a context grown past the window and an account
                # limit both come back as zero tokens at zero cost, and only this layer can tell them apart
                "ended": _ended(out, envelope is None),
                # …and when the limit that refused it lifts: the system stops the project until then (`Engine.pause`)
                "limit_resets_at": _lifts_at(out) or self.last_lift,
                # whether it CONTINUED a conversation (`--resume`, a round cut at its turn cap) rather than opening
                # a context of its own: real contexts are the calls that did not
                "resumed": "--resume" in args,
                # a round cut at its turn cap, in the record's one word for it (`budget.cut_at_turn_cap`)
                "stop_reason": "max_turns" if out.get("subtype") == "error_max_turns" else out.get("stop_reason"),
                # …and WHY a call that errored ended: read as "did not parse", 38 re-issues of a root whose packet no
                # longer fit the model's window answered a bug no executor could fix (GB_sql_database_tmxu0n436)
                # …with the envelope's own `api_error`: an account's limit came back as "api_error: You've hit your
                # session limit", which no reader took for a limit, and its sessions were parked as unreadable
                # reports (GB_c_compiler_tncfs1160, 2026-10-23)
                "error": (f"{out.get('terminal_reason') or 'error'}: "
                          + (f"{out['api_error']}: " if out.get("api_error") else "")
                          + str(out.get("result") or "")[:160]
                          if out.get("is_error") else None),
                # …and its commands as the system ran them: a CLI that ran them beside itself is refused, its answer
                # unread (`_refusal`)
                **(refused := _refusal(sess, proc, self.last_shell_ran)),
            })
            if refused or out.get("is_error"):
                log.warning(f"headless claude call {'refused' if refused else 'errored'}: "
                            f"{refused.get('error') or str(out)[:300]}")
                if refused or not (session and "--resume" in args and _cannot_resume(out)):
                    return ""
            else:
                return (out.get("result") if isinstance(out.get("result"), str) else "") or "".join(text_acc)
        except PlaceUnavailable as e:
            return self._never_started(e, "--resume" in args)
        except Exception as e:
            log.warning(f"headless claude call failed: {e}", exc_info=True)   # the cause was once only inferred
            return ""
        finally:
            # A call that ended in an exception — `wait` timing out after the stream closed was one —
            # used to leave its child running until the server itself died.
            if proc is not None:           # the child's own shells too, on every path
                self._exec.end(proc)
            # …a round what stops the project refused never ran: the conversation it would continue is kept
            if not refused_by_limit(self.calls[n0:]):
                self._after_the_round(session, out, self.calls[n0:])
        # Reached only by a conversation the CLI could not take up (gone, outgrown its window): that is not the round's
        # failure, so the round runs cold — after the first process is gone, which otherwise rewrote the transcript
        # just forgotten and sent the "cold" retry back to `--resume` (critic, live on CLI 2.1.306)
        # …on what the run reopens on (`resume_fallback`): a budget's "continue the task" means nothing without its history;
        # and still armed: forgotten with the conversation, the hook left the cold run without a ceiling and the provider
        # was sent back to rounds for good (critic over the hook path)
        return self.hooks.across(session, self.forget) or self._call(system, self.resume_fallback or user, tools_args,
                                                                     cwd, timeout, session)
