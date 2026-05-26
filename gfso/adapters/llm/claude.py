"""Claude API LLM provider — graceful degradation without API key."""
from __future__ import annotations

import logging
import os

from gfso.core.types import LLMProviderPort

log = logging.getLogger(__name__)


class ClaudeLLM(LLMProviderPort):
    def __init__(self, api_key: str | None = None, model: str = "claude-haiku-4-5-20251001"):
        self._model = model or "claude-haiku-4-5-20251001"
        self._client = None
        key = api_key or os.environ.get("ANTHROPIC_API_KEY")
        if key:
            try:
                import anthropic
                self._client = anthropic.Anthropic(api_key=key)
            except ImportError:
                log.warning("anthropic package not installed — LLM degraded to stub")

    def complete(self, prompt: str, context: str = "") -> str:
        if self._client is None:
            return ""
        try:
            response = self._client.messages.create(
                model=self._model,
                max_tokens=4096,
                system=context or "You are a GFSO System LLM analyzing task decompositions.",
                messages=[{"role": "user", "content": prompt}],
            )
            return response.content[0].text
        except Exception as e:
            log.warning(f"LLM call failed: {e}")
            return ""
