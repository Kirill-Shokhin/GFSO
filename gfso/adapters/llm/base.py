"""What every provider shares, whatever its transport: the call records it keeps and the structured answer it gives.

A provider's own work is ONE method — `_call(system, user)`, a zero-tool answer, appending its call record to `calls`.
The rest is the same for all of them, so it lives once: the stage a call is labelled with, the live-tick hooks, the tools
the last agent run reached for, and the schema-valid answer with its one repair retry (`structured.py` — no transport is
trusted to enforce a schema).
"""
from __future__ import annotations

import logging
import re
import time

from gfso.core.types import LLMProviderPort
from . import budget
from .stats import refused_by_limit
from .structured import parse_structured, retry_suffix, schema_instruction, RETRY_SHORTER

log = logging.getLogger(__name__)

#: The keys of one call's record — the neutral shape the ledger stores (`Engine.record_llm_usage`). A provider fills
#: what its transport reports; what it does not report stays None, never 0.
RECORD = ("duration_ms", "input_tokens", "output_tokens", "cache_read_input_tokens", "cache_creation_input_tokens",
          "cost_usd", "model", "context_window", "peak_context", "turns", "transport_torn", "ended", "limit_resets_at",
          "resumed", "stop_reason", "error", "at", "credential")


def record(**fields) -> dict:
    """One call's record: every key of `RECORD`, None where the transport said nothing."""
    unknown = set(fields) - set(RECORD) - {"stage", "parse_failed", "place"}
    if unknown:
        raise TypeError(f"not a call record field: {', '.join(sorted(unknown))}")
    # …`at`: when the call ended, stamped as it is booked — the ledger read the drain's moment, one for every round of a
    # run drained together, so a run's rounds and handovers lay on top of each other in time (ui stream, 2026-10-27)
    return {k: fields.get(k) for k in RECORD} | {"at": fields.get("at") or time.time()}         | {k: v for k, v in fields.items() if k not in RECORD}


class RecordingProvider(LLMProviderPort):
    """A provider that records its calls. Subclasses implement `_call` and, to hold agent roles, `agent_round`."""
    #: the resource's context budget in tokens (`budget.run`), None = its sessions hand over at the ceiling alone
    context_budget: int | None = None
    #: is the run a WORK session — one whose context the system hands over (`budget.run`)? An executor's, set by the
    #: frame that spawns it; a validator's or a consent's run is one round, as before
    budgeted = False
    #: turns per round between two readings of the budget — as finely as the provider can stop a run and continue it
    budget_step = 8
    #: can the provider read its session's context after each tool call from inside the run (`budget.hooked`, `arm`)?
    #: Else the budget reads it between rounds
    handover_hook = False

    def __init__(self, model: str):
        self._model = model
        self.calls: list[dict] = []       # one `record` per call, in completion order
        self.last_tool_calls: dict[str, int] = {}   # the tools the LAST agent run reached for, by name
        self.last_peak_context = 0
        self.on_tick = None               # optional: live progress lines (`on_tick(msg)`)
        self.stage_hint = ""
        self.resume_fallback = None       # what a lost conversation reopens on, set while a budget runs (`budget.run`)
        self.machine_state = None         # optional: the place's state as the system reads it, for a reopen (`budget.run`)
        self.reads_as_report = None       # optional: does an answer parse as the role's report (`budget._as_note`)

    @property
    def agent(self) -> str | None:
        """Who the calls work as — the name the stage carries (`<node> <role>(<agent>)`), None where it names none: what
        an isolated place shows its session's container as (`ExecutionPort.session`)."""
        return (m := re.search(r"\(([^()]+)\)", self.stage_hint or "")) and m.group(1)

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

    def run_agent(self, system: str, user: str, allowed_tools: tuple[str, ...], cwd: str | None = None,
                  timeout: int | None = None, max_turns: int | None = None, session: str | None = None) -> str:
        """The port's agent run — a work session's under its ceiling and the resource's budget (`budget.run`)."""
        if not self.budgeted:
            return self.agent_round(system, user, allowed_tools, cwd, timeout, max_turns, session)
        return (budget.hooked if self.handover_hook else budget.run)(self, system, user, allowed_tools, cwd, timeout,
                                                                     max_turns, session)

    def agent_round(self, system, user, allowed_tools, cwd, timeout, max_turns, session) -> str:
        """One round of an agent run, the transport's own."""
        return LLMProviderPort.run_agent(self, system, user, allowed_tools, cwd, timeout, max_turns, session)

    def arm(self, sid: str, state: dict, cwd: str | None = None) -> None:
        """The handover hook armed for the conversation `sid` where its session will run (`cwd`), with the state it
        reads (`handover_hook`)."""
        raise NotImplementedError

    def window(self) -> int | None:
        """The model's context window as last reported, None before any call reported one."""
        return None

    def close_session(self, system: str, prompt: str, allowed_tools, cwd, timeout, session) -> str:
        """The session's last answer — what it hands the next one (`budget.CLOSE`), its conversation continued under
        the same tools so its cached prefix holds."""
        return self.agent_round(system, prompt, allowed_tools, cwd, timeout, budget.CLOSE_TURNS, session)

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
