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

from gfso.core.types import LLMProviderPort
from .structured import schema_instruction, parse_structured, RETRY_SUFFIX

log = logging.getLogger(__name__)


class HeadlessClaudeLLM(LLMProviderPort):
    def __init__(self, model: str = "sonnet", timeout: int = 900, claude_cmd: str = "claude",
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
        self._tick_every = 2.0
        if self._cmd is None:
            log.warning("claude CLI not found — headless LLM degraded to stub")

    def tag_last(self, stage: str) -> None:
        """Label the most recent call with its pipeline stage (the caller knows; the port API doesn't)."""
        if self.calls:
            self.calls[-1]["stage"] = stage

    def run_agent(self, system: str, user: str, allowed_tools: tuple[str, ...],
                  cwd: str | None = None, timeout: int | None = None) -> str:
        """Port B — the AGENT-RUNNER: one fresh headless run WITH work tools (multi-step inside one
        process), returning its final report text. Headless-by-necessity: an agent run needs a harness
        (tools/permissions/cwd), which a bare completion API can't provide — GenericLLM never covers this.
        `--dangerously-skip-permissions` is REQUIRED for non-interactivity (headless can't answer
        prompts); the safety envelope = the tool allowlist + scoped cwd (probed live 2026-07-03).
        `timeout` = a per-run process cap (e.g. deadline-derived); on expiry the process is killed and
        NO signal is forged — the FSM's timeout monitor owns escalation (one clock)."""
        return self._call(system, user, cwd=cwd, timeout=timeout,
                          tools_args=["--allowedTools", " ".join(allowed_tools),
                                      "--dangerously-skip-permissions"])

    def _call(self, system: str, user: str, tools_args: list[str] | None = None,
              cwd: str | None = None, timeout: int | None = None) -> str:
        """One fresh `claude -p` subprocess, STREAMED (stream-json + partial messages): while the model
        generates, cumulative output tokens tick to `on_tick` — real progress, never an estimate. The
        final `result` event carries the same envelope the aggregate json format did (usage,
        duration_ms, is_error, result); if it is missing, the accumulated delta text is the fallback.
        Default = a zero-tool one-shot (Port A); `tools_args`/`cwd` = an agent run (Port B)."""
        if self._cmd is None:
            return ""
        env = dict(os.environ) if self._keep_key else \
            {k: v for k, v in os.environ.items() if k not in ("ANTHROPIC_API_KEY", "ANTHROPIC_AUTH_TOKEN")}
        if self._max_thinking is not None:
            env["MAX_THINKING_TOKENS"] = str(self._max_thinking)
        args = [self._cmd, "-p", "--model", self._model, "--system-prompt", system,
                "--output-format", "stream-json", "--include-partial-messages", "--verbose",
                *(tools_args if tools_args is not None else ["--disallowedTools", "*"])]
        t0 = time.monotonic()
        cap = timeout or self._timeout
        self._est_chars = 0  # per-call char-estimate (fallback token counter while usage is absent)
        try:
            proc = subprocess.Popen(args, stdin=subprocess.PIPE, stdout=subprocess.PIPE,
                                    stderr=subprocess.DEVNULL, text=True, encoding="utf-8", env=env,
                                    cwd=cwd)

            def _feed():  # a writer thread — a large prompt would deadlock a same-thread pipe write
                try:
                    proc.stdin.write(user)
                    proc.stdin.close()
                except Exception:
                    pass
            threading.Thread(target=_feed, daemon=True).start()

            envelope, text_acc, out_tokens, last_tick = None, [], 0, t0
            for line in proc.stdout:
                if time.monotonic() - t0 > cap:
                    proc.kill()
                    log.warning("headless claude call timed out mid-stream")
                    break
                line = line.strip()
                if not line:
                    continue
                try:
                    ev = json.loads(line)
                except Exception:
                    continue
                if ev.get("type") == "result":
                    envelope = ev
                    continue
                inner = ev.get("event") or {}
                usage = inner.get("usage") or ev.get("usage") or {}
                if usage.get("output_tokens"):
                    out_tokens = usage["output_tokens"]
                delta = inner.get("delta") or {}
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
                        pass
            proc.wait(timeout=30)

            out = envelope or {}
            usage = out.get("usage") or {}
            self.calls.append({
                "duration_ms": out.get("duration_ms") or int((time.monotonic() - t0) * 1000),
                "input_tokens": usage.get("input_tokens"),
                "output_tokens": usage.get("output_tokens") or out_tokens or None,
                "cache_read_input_tokens": usage.get("cache_read_input_tokens"),
                "cache_creation_input_tokens": usage.get("cache_creation_input_tokens"),
            })
            if out.get("is_error"):
                log.warning(f"headless claude call errored: {str(out)[:300]}")
                return ""
            return out.get("result") or "".join(text_acc)
        except Exception as e:
            log.warning(f"headless claude call failed: {e}")
            return ""

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
                self._call(system, user + schema_instruction(schema) + RETRY_SUFFIX), schema)
            if parsed is not None:
                return parsed
        log.warning("headless structured call: no schema-valid json after retry")
        return {}
