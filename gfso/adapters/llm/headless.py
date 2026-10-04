"""Headless Claude Code LLM provider — one-shot `claude -p` subprocess calls.

THE Anthropic transport (the only one): each call is a fresh, stateless, single-request generation —
exactly the call shape the decompose loop was calibrated on. BOTH billing modes ride the same
transport: by default ANTHROPIC_API_KEY / ANTHROPIC_AUTH_TOKEN are STRIPPED from the child env
(subscription via the claude.ai login — the key would silently outrank it, measured live);
`keep_api_key=True` keeps them ⟹ the same CLI bills the API per token. Structured output = the shared
provider-agnostic machinery (`structured.py`): appended fenced-json instruction + parse + one repair
retry — the schema is enforced by validation here, never trusted to the transport.
"""
from __future__ import annotations

import json
import logging
import os
import shutil
import subprocess
import threading
import time
import uuid
from pathlib import Path

from gfso.core.types import LLMProviderPort
from .structured import holds_an_object, schema_instruction, parse_structured, RETRY_SHORTER, RETRY_SUFFIX
from gfso.config import MODEL_DEFAULT, agent_trace_dir, subprocess_env
from gfso.adapters.children import adopt, kill_tree, release, spawn_kw

log = logging.getLogger(__name__)


def _obj(v) -> dict:
    """A stream value as a mapping, or an empty one. The CLI's stream is not ours to type: an event whose
    `message` arrived as a string killed the whole call on `.get` (measured in two E3 runs, each time a
    ⊥ the validator never earned), so every field is read through this — never by trusting its shape."""
    return v if isinstance(v, dict) else {}


def _tool_use_name(ev: dict) -> str | None:
    """The tool a stream event announces, if it announces one.

    stream-json carries tool calls as content blocks; a validator that claims "Executed: …" while
    never opening Bash is claiming something it did not do, and that is decidable HERE, structurally,
    without parsing its prose or trusting it. Measured need: 4 of 7 checkable claims in one run's
    verdicts described executions that did not match the artefact they validated.
    """
    inner = _obj(ev.get("event"))
    for block in (ev.get("content_block"), inner.get("content_block"), ev.get("delta"), inner.get("delta")):
        if isinstance(block, dict) and block.get("type") == "tool_use" and block.get("name"):
            return str(block["name"])
    content = _obj(ev.get("message")).get("content")
    for block in (content if isinstance(content, list) else []):
        if isinstance(block, dict) and block.get("type") == "tool_use" and block.get("name"):
            return str(block["name"])
    return None


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


class HeadlessClaudeLLM(LLMProviderPort):
    #: each call is its own `claude -p` process, so independent readings may run at once (`stats.readings`)
    parallel_safe = True

    def __init__(self, model: str = MODEL_DEFAULT, timeout: int = 900, claude_cmd: str = "claude",
                 max_thinking_tokens: int | None = None, keep_api_key: bool = False):
        self._model = model
        self._timeout = timeout
        self._cmd = shutil.which(claude_cmd)
        # Latency lever: per-call wall time is dominated by OUTPUT tokens, and thinking tokens bill into
        # output. Caps the child CLI's thinking budget (MAX_THINKING_TOKENS env); None = CLI default.
        self._max_thinking = max_thinking_tokens
        self._keep_key = keep_api_key  # True = api billing (key kept in child env); False = subscription
        self.calls: list[dict] = []   # per-call stats: {stage?, duration_ms, input/output/cache tokens}
        # Live ticks: the CLI streams (stream-json + partial messages), so generation progress is REAL
        # (actual output tokens so far), not an estimate. The caller wires `on_tick(msg)` and may set
        # `stage_hint` before each call; both are optional presentation.
        self.on_tick = None
        self.stage_hint = ""
        # Which work tools the LAST run reached for — a field of this object, not of one call inside
        # it: the verdict record carries it, and a client whose run never started (or whose result is
        # merged from concurrent siblings) still has to answer the question.
        self.last_tool_calls: dict[str, int] = {}
        self._tick_every = 2.0
        if self._cmd is None:
            log.warning("claude CLI not found — headless LLM degraded to stub")

    def tag_last(self, stage: str) -> None:
        """Label the most recent call with its pipeline stage (the caller knows; the port API doesn't)."""
        if self.calls:
            self.calls[-1]["stage"] = stage

    def run_agent(self, system: str, user: str, allowed_tools: tuple[str, ...],
                  cwd: str | None = None, timeout: int | None = None,
                  max_turns: int | None = None) -> str:
        """Port B — the AGENT-RUNNER: one fresh headless run WITH work tools (multi-step inside one
        process), returning its final report text. Headless-by-necessity: an agent run needs a harness
        (tools/permissions/cwd), which a bare completion API can't provide — GenericLLM never covers this.
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
        return self._call(system, user, cwd=cwd, timeout=timeout,
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
        self.last_tool_calls = {}
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
        timer = threading.Timer(max(0.0, cap - (time.monotonic() - t0)), kill_tree, args=(proc,))
        timer.daemon = True
        timer.start()
        try:
            return self._read_lines(proc, t0, cap, envelope, text_acc, out_tokens, last_tick, trace)
        finally:
            timer.cancel()
            if trace is not None:
                try:
                    trace.close()
                except OSError:                # a failed flush of an audit aid never replaces the answer
                    pass

    def _read_lines(self, proc, t0, cap, envelope, text_acc, out_tokens, last_tick, trace):
        live = False      # a background task of the session is still running (`background_tasks_changed`)
        for line in proc.stdout:
            trace = _traced(trace, line)
            if time.monotonic() - t0 > cap:
                kill_tree(proc)
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
            if (tname := _tool_use_name(ev)):
                self.last_tool_calls[tname] = self.last_tool_calls.get(tname, 0) + 1
            inner = _obj(ev.get("event"))
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
              cwd: str | None = None, timeout: int | None = None) -> str:
        """One fresh `claude -p` subprocess, STREAMED (stream-json + partial messages): while the model
        generates, cumulative output tokens tick to `on_tick` — real progress, never an estimate. The
        final `result` event carries the same envelope the aggregate json format did (usage,
        duration_ms, is_error, result); if it is missing, the accumulated delta text is the fallback.
        Default = a zero-tool one-shot (Port A); `tools_args`/`cwd` = an agent run (Port B)."""
        if self._cmd is None:
            return ""
        env = subprocess_env(keep_key=self._keep_key)
        if self._max_thinking is not None:
            env["MAX_THINKING_TOKENS"] = str(self._max_thinking)
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
                "--settings", '{"disableAllHooks": true, "language": ""}',
                # …AND THE OPERATOR'S OWN INSTRUCTIONS. Hooks and MCP were shut, and the call still
                # loaded the person's CLAUDE.md: probed 2026-09-24, an internal call listed the
                # operator's working-mode and coding rules among its instructions — so an executor or
                # a validator of this product ran under whatever its user had written for themselves.
                # `--safe-mode` drops CLAUDE.md, skills, plugins, hooks and MCP and keeps auth (probed:
                # none of those instructions reached the call; tools and the system prompt work).
                "--safe-mode",
                # And the reverse direction: each call used to SAVE its transcript into the
                # operator's session history for this directory. Measured on one install: 10 459
                # internal transcripts beside 18 of the person's own, and `claude --resume` took
                # over three minutes to list them. Nothing reads them; the envelope comes off stdout.
                "--no-session-persistence",
                "--output-format", "stream-json", "--include-partial-messages", "--verbose",
                *(tools_args if tools_args is not None else ["--disallowedTools", "*"])]
        t0 = time.monotonic()
        cap = timeout or self._timeout
        self._est_chars = 0  # per-call char-estimate (fallback token counter while usage is absent)
        # Windows: a console child ALLOCATES ITS OWN console when the parent has none (the shared
        # server is spawned detached) — every agent run popped an empty `claude` window on top of
        # the user's screen, accidentally closable (= killing the run). CREATE_NO_WINDOW suppresses
        # the console entirely; all real I/O rides the pipes and is unaffected.
        no_window = {"creationflags": subprocess.CREATE_NO_WINDOW} if os.name == "nt" else {}
        proc = None
        try:
            proc = adopt(subprocess.Popen(args, stdin=subprocess.PIPE, stdout=subprocess.PIPE,
                                          stderr=subprocess.DEVNULL, text=True, encoding="utf-8",
                                          env=env, cwd=cwd, **no_window, **spawn_kw()))

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
            usage = _obj(out.get("usage"))
            self.calls.append({
                "duration_ms": out.get("duration_ms") or int((time.monotonic() - t0) * 1000),
                "input_tokens": usage.get("input_tokens"),
                "output_tokens": usage.get("output_tokens") or out_tokens or None,
                "cache_read_input_tokens": usage.get("cache_read_input_tokens"),
                "cache_creation_input_tokens": usage.get("cache_creation_input_tokens"),
                # The envelope has carried the cost all along and nothing read it: the tokens were
                # recorded, the dollars were dropped, and "what did this graph cost" stayed a
                # question the system could not answer about itself.
                "cost_usd": out.get("total_cost_usd"),
                "model": self._model,
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
                "stop_reason": out.get("stop_reason"),
            })
            if out.get("is_error"):
                log.warning(f"headless claude call errored: {str(out)[:300]}")
                return ""
            return (out.get("result") if isinstance(out.get("result"), str) else "") or "".join(text_acc)
        except Exception as e:
            log.warning(f"headless claude call failed: {e}", exc_info=True)   # the cause was once only inferred
            return ""
        finally:
            # A call that ended in an exception — `wait` timing out after the stream closed was one —
            # used to leave its child running until the server itself died.
            if proc is not None:           # the child's own shells too, on every path
                kill_tree(proc)
                release(proc)

    def complete(self, prompt: str, context: str = "") -> str:
        return self._call(context or "You are a GFSO System LLM analyzing task decompositions.", prompt)

    def complete_structured(self, system: str, user: str, schema: dict) -> dict:
        """The port's structured contract: a dict satisfying `schema`'s required keys, {} on failure."""
        text = self._call(system, user + schema_instruction(schema))
        parsed = parse_structured(text, schema)
        if parsed is not None:
            return parsed
        if self.calls:
            self.calls[-1]["parse_failed"] = True  # keep the wasted attempt visible in stats
        if text:  # one repair retry with the failure fed back
            parsed = parse_structured(
                self._call(system, user + schema_instruction(schema)
                           + (RETRY_SHORTER if self.calls and self.calls[-1].get("stop_reason") == "max_tokens"
                              else RETRY_SUFFIX)), schema)
            if parsed is not None:
                return parsed
        log.warning("headless structured call: no schema-valid json after retry")
        return {}
