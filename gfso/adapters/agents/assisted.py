"""Assisted agent — human + System LLM suggestions."""
from __future__ import annotations

import logging
from typing import Optional

from gfso.core.types import AgentId, DispatchPayload, SignalData, AgentPort

log = logging.getLogger(__name__)


class AssistedAgent(AgentPort):
    def dispatch(self, agent_id: AgentId, payload: DispatchPayload) -> Optional[SignalData]:
        log.info(
            f"[ASSISTED {agent_id}] signal={payload.signal.name} "
            f"task={payload.task.id}"
        )
        if payload.recommendation and payload.recommendation.suggestions:
            log.info("System LLM suggestions:")
            for s in payload.recommendation.suggestions:
                log.info(f"  - {s}")
        # Human makes final decision — return None
        return None
