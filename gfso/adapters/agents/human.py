"""Human agent — dispatches via logging, returns None (async human response)."""
from __future__ import annotations

import logging
from typing import Optional

from gfso.core.types import AgentId, DispatchPayload, SignalData, AgentPort

log = logging.getLogger(__name__)


class HumanAgent(AgentPort):
    def dispatch(self, agent_id: AgentId, payload: DispatchPayload) -> Optional[SignalData]:
        log.info(
            f"[HUMAN {agent_id}] signal={payload.signal.name} "
            f"task={payload.task.id} state={payload.task.state.name}"
        )
        if payload.check_results:
            for r in payload.check_results:
                status = "PASS" if r.passed else ("SKIP" if r.skipped else "FAIL")
                log.info(f"  {r.check_name}: {status} {r.details}")
        if payload.recommendation and payload.recommendation.suggestions:
            for s in payload.recommendation.suggestions:
                log.info(f"  suggestion: {s}")
        # Human responds asynchronously via API — return None
        return None
