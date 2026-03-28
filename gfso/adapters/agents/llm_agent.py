"""LLM agent — uses LLMProviderPort to generate responses."""
from __future__ import annotations

import logging
from typing import Optional

from gfso.core.types import (
    AgentId, Signal, DispatchPayload, SignalData, AgentPort,
    LLMProviderPort, TaskId,
)

log = logging.getLogger(__name__)


class LLMAgent(AgentPort):
    def __init__(self, llm: LLMProviderPort):
        self._llm = llm

    def dispatch(self, agent_id: AgentId, payload: DispatchPayload) -> Optional[SignalData]:
        prompt = (
            f"You are agent {agent_id}.\n"
            f"Task: {payload.task.spec.description}\n"
            f"Signal received: {payload.signal.name}\n"
            f"Current state: {payload.task.state.name}\n"
            f"Respond with one of: ACCEPT, DELIVER, CHALLENGE, BLOCK\n"
        )
        response = self._llm.complete(prompt)
        signal_name = response.strip().upper()

        try:
            signal = Signal[signal_name]
        except KeyError:
            log.warning(f"LLM agent returned invalid signal: {response}")
            return None

        return SignalData(
            signal=signal,
            task_id=payload.task.id,
            source=agent_id,
        )
