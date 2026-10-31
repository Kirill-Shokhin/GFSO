"""A provider over a chat API: the wire (`ChatWire`, one required method) and the provider built on it (`ChatProvider`).

A WIRE answers one turn of a conversation — the messages so far and the tools on offer in, the reply out: its text, the
tool calls it asks for, what the turn cost, how it finished. That is all a vendor's API is to this system; everything
else — one-shot answers, structured answers, agent runs with work tools (`toolloop.ToolLoop`) — is built once on top of
it. A wire DECLARES what it reports beyond the required (`tools`, `reports_cache`, `reports_cost`, `context_window`);
what it does not report stays None in the call record, never 0.

The transcript is OpenAI-shaped (`role`, `content`, `tool_calls`, `tool_call_id`): the shape most chat APIs speak. A
wire of another shape translates at its own boundary.
"""
from __future__ import annotations

import http.client
import json
import logging
import re
import socket
import time
import urllib.error
import urllib.request
from dataclasses import dataclass, field
from typing import Optional

from gfso.core.types import ExecutionPort
from gfso.adapters.execution import LocalExecution
from .base import RecordingProvider, record
from .toolloop import ToolLoop, transcript_path

log = logging.getLogger(__name__)

#: how a turn's finish reads as the call record's `ended` — the one word the engine reads (`Engine.record_llm_usage`)
ENDED = {"stop": "answered", "tools": "answered", "length": "answered", "limit": "limit", "context": "prompt_too_long",
         "unavailable": "unavailable", "unauthorized": "unauthorized", "cut": "cut", "error": "error"}
#: …and as its `stop_reason`, where it has one (a cut at the output limit is asked again shorter: `base`)
STOP = {"length": "max_tokens", "stop": "end_turn", "tools": "tool_use"}
#: THE WIRE WAITS OUT WHAT PASSES BY ITSELF, as the CLI does inside itself: a busy server (5xx), a per-minute rate
#: limit (429 with a short or no Retry-After), a dropped connection — each turn asked again after these many seconds,
#: then given up as `cut` (5xx, connection) or `limit` (429). A cheap API's "busy" and a local server reloading its model
#: ended a run that had done the work, its conversation dropped (critic over the factory, 2026-10-27).
RETRY_DELAYS_S = (2, 8, 30)
#: a Retry-After past this is a limit to stop the project for, not to wait out inside one call
RETRY_AFTER_MAX_S = 60
#: how a 400's body names an overflowed window — a bad parameter's own "maximum" must not read as one
CONTEXT_OVERFLOW = ("context length", "context_length", "context window", "maximum context", "prompt is too long",
                    "too many tokens", "reduce the length", "context size", "exceed_context_size")   # llama.cpp's


#: a reasoning model's inline thinking — closed, or left open to the end of a cut reply
THINKING = re.compile(r"<think>.*?(</think>|$)", re.S)


def is_address(place: str) -> bool:
    """Is this place a model server's address (a stop a chat call made), rather than an execution's name?"""
    return str(place or "").startswith(("http://", "https://"))


def answers(address: str, timeout: float = 5) -> Optional[str]:
    """Why the model server at `address` does not answer now, or None where it does — any HTTP status below 500 is a
    server that answers (a refused key is the account's question, not the place's)."""
    try:
        with urllib.request.urlopen(urllib.request.Request(address.rstrip("/") + "/models"), timeout=timeout):
            return None
    except urllib.error.HTTPError as e:
        return None if e.code < 500 else f"{address}: HTTP {e.code}"
    except (OSError, ValueError) as e:
        return f"{address}: {e}"


@dataclass
class Turn:
    """One answered turn: the reply and the bookkeeping of the call that made it.

    `finish`: `stop` (it answered), `tools` (it asks for tool calls), `length` (cut at the output limit), `limit` (the
    account's or the server's rate limit), `context` (the conversation outgrew the window), `unavailable` (nothing
    answered at the address), `unauthorized` (the key was refused), `cut` (the connection or the time ran out
    mid-answer), `error`."""
    text: str = ""
    tool_calls: list = field(default_factory=list)     # [{"id", "name", "arguments": dict}]
    finish: str = "stop"
    input_tokens: Optional[int] = None                 # fresh input, the cached part excluded
    output_tokens: Optional[int] = None
    cache_read: Optional[int] = None
    cache_write: Optional[int] = None
    cost_usd: Optional[float] = None
    model: str = ""                                    # the model that answered, as the API names it
    prompt_tokens: Optional[int] = None                # how full the context was on this turn
    resets_at: Optional[float] = None                  # when a limit that refused the turn lifts (epoch s)
    error: Optional[str] = None
    raw_assistant: dict = field(default_factory=dict)  # the reply as the transcript keeps it

    @property
    def failed(self) -> bool:
        """Did the turn give no reply to go on with?"""
        return ENDED[self.finish] not in ("answered",)

    @property
    def ended(self) -> str:
        """How a call that ended on this turn ended, in the record's word."""
        return ENDED[self.finish]

    @property
    def stop_reason(self) -> Optional[str]:
        """Why the reply stopped, in the record's word, where it says."""
        return STOP.get(self.finish)


class ChatWire:
    """The one class a vendor's chat API is written as. REQUIRED: `turn`. Declared, optional: the attributes below."""
    #: can it carry tool calls (function calling)? Required for the agent roles — executor, validator, contact.
    tools: bool = False
    #: does its usage split the cached part of the input out? (else cache read / write stay None)
    reports_cache: bool = False
    #: does a response carry its cost? (else cost comes from a declared tariff, or stays None)
    reports_cost: bool = False
    #: the model's window in tokens where known — the agent loop keeps its transcript under it
    context_window: Optional[int] = None
    #: where it answers — named in a record when nothing answers there
    address: str = ""

    def turn(self, messages: list, tools: list | None = None, timeout: float = 900) -> Turn:
        """One turn: `messages` (OpenAI-shaped) and the tools on offer (name, description, JSON-schema parameters) in,
        the reply out. Never raises for what the API answered: a refusal, a limit or a dead address is the Turn's
        `finish`."""
        raise NotImplementedError

    def discover_window(self) -> Optional[int]:
        """The window the server gives this model where it says (kept as `context_window`); a wire that cannot ask: None."""
        return None


#: a tariff in dollars per million tokens: (input, output, cached input)
Tariff = tuple


def _priced(t: Turn, tariff: Optional[Tariff]) -> Optional[float]:
    """The turn's cost from a DECLARED tariff — never guessed: no tariff, no number."""
    if not tariff or t.input_tokens is None or t.output_tokens is None:
        return None
    i, o, c = (tuple(tariff) + (None,))[:3]
    return (t.input_tokens * i + t.output_tokens * o + (t.cache_read or 0) * (c if c is not None else i)) / 1e6


class OpenAIWire(ChatWire):
    """The OpenAI-compatible `/chat/completions` with function calling — what Ollama, LM Studio, vLLM, the llama.cpp
    server, DeepSeek, Qwen's compatible mode, OpenRouter, Groq, Together, Mistral, Gemini's compatible endpoint and
    OpenAI itself speak."""
    tools = True
    reports_cache = True       # where the server reports it: `prompt_tokens_details.cached_tokens`, DeepSeek's hit count

    def __init__(self, base_url: str, model: str, api_key: Optional[str] = None, *, max_tokens: Optional[int] = None,
                 context_window: Optional[int] = None, tariff: Optional[Tariff] = None, extra: Optional[dict] = None):
        self.address = base_url.rstrip("/")
        self._model, self._key, self._max_tokens, self._tariff = model, api_key, max_tokens, tariff
        self.context_window = context_window
        self.reports_cost = tariff is not None
        self.missing_key: Optional[str] = None   # the variable a key was asked of and not found (`registry`)
        self._extra = dict(extra or {})          # body fields a server wants beyond the standard ones

    def _get(self, url: str, body: Optional[dict] = None, timeout: float = 10) -> dict:
        req = urllib.request.Request(url, data=json.dumps(body).encode("utf-8") if body is not None else None,
                                     method="POST" if body is not None else "GET",
                                     headers={"Content-Type": "application/json",
                                              **({"Authorization": f"Bearer {self._key}"} if self._key else {})})
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            return json.loads(resp.read().decode("utf-8"))

    def discover_window(self) -> Optional[int]:
        """The window the SERVER gives this model, where it says — a local server truncates past it silently (Ollama's
        `/v1` ignores `num_ctx`), so the declared one is not enough: Ollama's loaded context (`/api/ps`) or its model's
        `num_ctx` (`/api/show`), vLLM's `max_model_len`, the llama.cpp server's `n_ctx`. Kept as the wire's window."""
        root = self.address[:-3] if self.address.endswith("/v1") else self.address
        reads = ((f"{root}/api/ps", None, lambda d: next((m.get("context_length") for m in d.get("models") or []
                                                          if str(m.get("name", "")).startswith(self._model)), None)),
                 (f"{root}/api/show", {"model": self._model}, _num_ctx),
                 (f"{self.address}/models", None, lambda d: next((m.get("max_model_len") for m in d.get("data") or []
                                                                  if m.get("id") == self._model), None)),
                 (f"{root}/props", None, lambda d: (d.get("default_generation_settings") or {}).get("n_ctx")))
        for url, body, pick in reads:
            try:
                n = pick(self._get(url, body))
            except (OSError, ValueError, AttributeError, TypeError):
                continue                       # this server does not speak that dialect: the next one asks
            if isinstance(n, int) and n > 0:
                self.context_window = n
                return n
        return None

    def _post(self, body: dict, timeout: float) -> dict:
        req = urllib.request.Request(self.address + "/chat/completions", data=json.dumps(body).encode("utf-8"),
                                     method="POST", headers={"Content-Type": "application/json",
                                                             **({"Authorization": f"Bearer {self._key}"}
                                                                if self._key else {})})
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            return json.loads(resp.read().decode("utf-8"))

    def turn(self, messages: list, tools: list | None = None, timeout: float = 900) -> Turn:
        """`ChatWire.turn` over HTTP, what passes by itself waited out (`RETRY_DELAYS_S`); each failure that stays
        named as the Turn's finish."""
        t0 = time.monotonic()
        for delay in (*RETRY_DELAYS_S, None):
            t = self._once(messages, tools, max(1.0, timeout - (time.monotonic() - t0)))
            passes = (t.finish == "cut" or str(t.error).startswith("HTTP 5")
                      or t.finish == "limit" and str(t.error).startswith("rate_limit")
                      and (t.resets_at is None or t.resets_at - time.time() <= RETRY_AFTER_MAX_S))
            if not passes or delay is None or time.monotonic() - t0 + delay >= timeout:
                return Turn(**{**t.__dict__, "finish": "cut"}) if t.error and t.error.startswith("HTTP 5") else t
            time.sleep(max(delay, (t.resets_at or 0) - time.time()))
        return t

    def _once(self, messages: list, tools: list | None, timeout: float) -> Turn:
        body = {"model": self._model, "messages": messages, **self._extra}
        if tools:
            body["tools"] = [{"type": "function", "function": t} for t in tools]
        if self._max_tokens:
            body["max_tokens"] = self._max_tokens
        if self.missing_key:                       # nothing to send it with: the account's question, as a refused key
            return Turn(finish="unauthorized", error=f"unauthorized: no API key — {self.missing_key}", model=self._model)
        try:
            out = self._post(body, timeout)
        except urllib.error.HTTPError as e:
            return self._refused(e)
        except (socket.timeout, TimeoutError) as e:
            return Turn(finish="cut", error=f"timeout: {e}", model=self._model)
        except urllib.error.URLError as e:
            if isinstance(e.reason, ConnectionRefusedError) or isinstance(e.reason, socket.gaierror):
                return Turn(finish="unavailable", error=f"{self.address}: {e.reason}", model=self._model)
            return Turn(finish="cut", error=f"connection: {e.reason}", model=self._model)
        except ConnectionRefusedError as e:        # nothing listens there: the server is down
            return Turn(finish="unavailable", error=f"{self.address}: {e}", model=self._model)
        except (OSError, http.client.HTTPException) as e:   # dropped, reset, a body cut short: the turn was cut
            return Turn(finish="cut", error=f"connection: {type(e).__name__}: {e}", model=self._model)
        except ValueError as e:                    # a body that is not JSON
            return Turn(finish="error", error=f"unreadable response: {e}", model=self._model)
        return self._read(out)

    def _refused(self, e: urllib.error.HTTPError) -> Turn:
        try:
            said = e.read().decode("utf-8", "replace")[:400]
        except OSError:
            said = ""                              # the refusal's body is a courtesy; its status is the answer
        if e.code == 429:
            wait = e.headers.get("Retry-After") if e.headers else None
            try:
                lifts = time.time() + float(wait) if wait else None
            except ValueError:
                lifts = None                       # an HTTP date, not seconds: the limit's own probe finds the lift
            return Turn(finish="limit", error=f"rate_limit: HTTP 429 {said}", resets_at=lifts, model=self._model)
        if e.code == 402:                          # out of credit: the account's, lifted by a person (`spend limit`)
            return Turn(finish="limit", error=f"spend limit: HTTP 402 {said}", model=self._model)
        if e.code in (401, 403):
            return Turn(finish="unauthorized", error=f"unauthorized: HTTP {e.code} {said}", model=self._model)
        low = said.lower()
        if e.code == 413 or e.code == 400 and any(k in low for k in CONTEXT_OVERFLOW):
            return Turn(finish="context", error=f"prompt_too_long: HTTP {e.code} {said}", model=self._model)
        return Turn(finish="error", error=f"HTTP {e.code} {said}", model=self._model)

    def _read(self, out: dict) -> Turn:
        choice = ((out.get("choices") or [{}])[0]) if isinstance(out, dict) else {}
        msg = choice.get("message") or {}
        usage = out.get("usage") or {}
        prompt = usage.get("prompt_tokens")
        cached = (usage.get("prompt_tokens_details") or {}).get("cached_tokens")
        if cached is None:
            cached = usage.get("prompt_cache_hit_tokens")          # DeepSeek
        calls = [_tool_call(c, i) for i, c in enumerate(msg.get("tool_calls") or [])]
        # a reasoning model's thinking, where the server leaves it inline: a draft verdict inside it won the parse over
        # the final one (critic over the chat path — a path to a false PASS on the validator)
        content = THINKING.sub("", msg.get("content") or "").strip()
        finish = {"length": "length", "tool_calls": "tools", "function_call": "tools"}.get(
            choice.get("finish_reason"), "tools" if calls else "stop")
        t = Turn(text=content, tool_calls=calls, finish=finish, model=out.get("model") or self._model,
                 input_tokens=None if prompt is None else prompt - (cached or 0),
                 output_tokens=usage.get("completion_tokens"), cache_read=cached, prompt_tokens=prompt,
                 raw_assistant={"role": "assistant", "content": content,
                                **({"tool_calls": msg["tool_calls"]} if msg.get("tool_calls") else {})})
        t.cost_usd = usage.get("cost") if isinstance(usage.get("cost"), (int, float)) else _priced(t, self._tariff)
        return t


def _num_ctx(show: dict) -> Optional[int]:
    """Ollama's `/api/show`: the model's own `num_ctx` parameter where its model file sets one — the window it runs at."""
    for line in str(show.get("parameters") or "").splitlines():
        k, _, v = line.partition(" ")
        if k == "num_ctx" and v.strip().isdigit():
            return int(v.strip())
    return None


def _tool_call(c: dict, i: int) -> dict:
    """One tool call of a reply, its arguments parsed — or kept as text the loop reports back, never dropped."""
    fn = c.get("function") or {}
    args = fn.get("arguments")
    if isinstance(args, str):
        try:
            args = json.loads(args or "{}")
        except ValueError:
            args = {"__unparsed__": args}
    return {"id": c.get("id") or f"call_{i}", "name": fn.get("name") or "",
            "arguments": args if isinstance(args, dict) else {"__unparsed__": args}}


def _total(turns: list, k: str):
    vals = [getattr(t, k) for t in turns if getattr(t, k) is not None]
    return sum(vals) if vals else None


class ChatProvider(RecordingProvider):
    """A provider of every role over one chat wire: one-shots by a turn without tools, agent runs by the tool loop."""
    parallel_safe = True       # each call is its own HTTP request
    budget_step = 4            # the loop is ours: a round is stopped and continued at no cost but its turns

    def __init__(self, wire: ChatWire, model: str, execution: ExecutionPort | None = None, timeout: int = 900):
        super().__init__(model)
        self.wire, self.execution, self._timeout = wire, execution or LocalExecution(), timeout
        self.runs_agents = wire.tools
        self._window_asked = False         # the server asked once for the window it gives (`discover_window`)

    def book(self, turns: list, t0: float, *, ended: str, resumed: bool = False, stop_reason=None, error=None,
             place: Optional[str] = None) -> dict:
        """One call's record from the turns it took — summed, the fullest turn its peak."""
        last = turns[-1] if turns else Turn()
        rec = record(duration_ms=int((time.monotonic() - t0) * 1000), input_tokens=_total(turns, "input_tokens"),
                     output_tokens=_total(turns, "output_tokens"), cache_read_input_tokens=_total(turns, "cache_read"),
                     cache_creation_input_tokens=_total(turns, "cache_write"), cost_usd=_total(turns, "cost_usd"),
                     model=last.model or self._model, context_window=self.wire.context_window,
                     peak_context=max((t.prompt_tokens or 0 for t in turns), default=0) or None,
                     turns=len(turns) or None, transport_torn=ended == "cut", ended=ended,
                     limit_resets_at=last.resets_at, resumed=resumed, stop_reason=stop_reason, error=error)
        if ended == "unavailable":
            rec["place"] = place or self.wire.address
        self._book(rec)
        return rec

    def _call(self, system: str, user: str) -> str:
        t0 = time.monotonic()
        t = self.wire.turn([{"role": "system", "content": system}, {"role": "user", "content": user}],
                           timeout=self._timeout)
        self.book([t], t0, ended=t.ended, stop_reason=t.stop_reason, error=t.error)
        if t.failed:
            log.warning(f"{self.wire.address} call ended {t.finish}: {t.error}")
            return ""
        return t.text

    def agent_round(self, system: str, user: str, allowed_tools: tuple[str, ...], cwd: Optional[str] = None,
                     timeout: Optional[int] = None, max_turns: Optional[int] = None,
                     session: Optional[str] = None) -> str:
        """One round of an agent run through the system's own tool loop."""
        if not self.runs_agents:
            return super().agent_round(system, user, allowed_tools, cwd, timeout, max_turns, session)
        if not cwd:
            raise ValueError("an agent run needs a working directory: without one it would run where the server "
                             "stands (the gfso state home), which holds none of the work. Pass `workdir`.")
        if not (self._window_asked or self.wire.context_window):
            self._window_asked = True
            self.wire.discover_window()
        return ToolLoop(self).run(system, user, allowed_tools, cwd, timeout or self._timeout, max_turns, session)

    def forget(self, session: str) -> None:
        """Drop a conversation kept between rounds."""
        t = transcript_path(self.execution, session)
        self.execution.files.remove_matching(str(t.parent), [t.name])
