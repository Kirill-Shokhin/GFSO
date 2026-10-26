"""What every provider shares, whatever its transport: the call records it keeps and the structured answer it gives.

A provider's own work is ONE method — `_call(system, user)`, a zero-tool answer, appending its call record to `calls`.
The rest is the same for all of them, so it lives once: the stage a call is labelled with, the live-tick hooks, the tools
the last agent run reached for, and the schema-valid answer with its one repair retry (`structured.py` — no transport is
trusted to enforce a schema).
"""
from __future__ import annotations

import logging

from gfso.core.types import LLMProviderPort
from .stats import refused_by_limit
from .structured import parse_structured, retry_suffix, schema_instruction, RETRY_SHORTER

log = logging.getLogger(__name__)

#: The keys of one call's record — the neutral shape the ledger stores (`Engine.record_llm_usage`). A provider fills
#: what its transport reports; what it does not report stays None, never 0.
RECORD = ("duration_ms", "input_tokens", "output_tokens", "cache_read_input_tokens", "cache_creation_input_tokens",
          "cost_usd", "model", "context_window", "peak_context", "turns", "transport_torn", "ended", "limit_resets_at",
          "resumed", "stop_reason", "error")


def record(**fields) -> dict:
    """One call's record: every key of `RECORD`, None where the transport said nothing."""
    unknown = set(fields) - set(RECORD) - {"stage", "parse_failed", "place"}
    if unknown:
        raise TypeError(f"not a call record field: {', '.join(sorted(unknown))}")
    return {k: fields.get(k) for k in RECORD} | {k: v for k, v in fields.items() if k not in RECORD}


class RecordingProvider(LLMProviderPort):
    """A provider that records its calls. Subclasses implement `_call` and, to hold agent roles, `run_agent`."""

    def __init__(self, model: str):
        self._model = model
        self.calls: list[dict] = []       # one `record` per call, in completion order
        self.last_tool_calls: dict[str, int] = {}   # the tools the LAST agent run reached for, by name
        self.last_peak_context = 0
        self.on_tick = None               # optional: live progress lines (`on_tick(msg)`)
        self.stage_hint = ""

    def begin_run(self) -> None:
        """A new call starts: what the last one reached for and how full it got are its own, not this one's."""
        self.last_tool_calls, self.last_peak_context = {}, 0

    def note_peak(self, tokens: int) -> None:
        """How full the context got on a turn of the call being read — the fullest one is the call's peak."""
        self.last_peak_context = max(self.last_peak_context, tokens or 0)

    def note_tool(self, name: str) -> None:
        """The run reached for a work tool — counted by its name (the invariants read the shell's)."""
        self.last_tool_calls[name] = self.last_tool_calls.get(name, 0) + 1

    def tag_last(self, stage: str) -> None:
        """Label the most recent call with its pipeline stage (the caller knows; the port does not)."""
        if self.calls:
            self.calls[-1]["stage"] = stage

    def _call(self, system: str, user: str) -> str:
        raise NotImplementedError

    def complete(self, prompt: str, context: str = "") -> str:
        return self._call(context or "You are a GFSO System LLM analyzing task decompositions.", prompt)

    def complete_structured(self, system: str, user: str, schema: dict) -> dict:
        """The port's structured contract: a dict satisfying `schema`'s required keys, {} on failure."""
        text = self._call(system, user + schema_instruction(schema))
        parsed = parse_structured(text, schema)
        if parsed is not None:
            return parsed
        if refused_by_limit(self.calls[-1:]):
            return {}                          # nothing ran: no reply to have failed parsing, nothing to retry
        if self.calls:
            self.calls[-1]["parse_failed"] = True  # keep the wasted attempt visible in stats
        if text:  # one repair retry with the failure fed back
            cut = bool(self.calls) and self.calls[-1].get("stop_reason") == "max_tokens"
            parsed = parse_structured(self._call(system, user + schema_instruction(schema)
                                                 + (RETRY_SHORTER if cut else retry_suffix(text, schema))), schema)
            if parsed is not None:
                return parsed
        log.warning(f"{type(self).__name__} structured call: no schema-valid json after retry")
        return {}
