"""Retry wrapper for Anthropic API: handles 429/529/503 + connection errors."""
from __future__ import annotations

import logging
import time

from anthropic import APIStatusError, APIConnectionError

log = logging.getLogger(__name__)


class RetryClient:
    """Wraps Anthropic client. Retries with exponential backoff on transient errors."""

    def __init__(self, client, max_attempts: int = 8, base_delay: float = 5.0, max_delay: float = 120.0):
        self._c = client
        self._max_attempts = max_attempts
        self._base_delay = base_delay
        self._max_delay = max_delay
        self.messages = self

    def create(self, **kwargs):
        delay = self._base_delay
        for attempt in range(self._max_attempts):
            try:
                return self._c.messages.create(**kwargs)
            except (APIConnectionError, APIStatusError) as e:
                code = getattr(e, "status_code", "conn")
                retryable = isinstance(e, APIConnectionError) or code in (429, 529, 503)
                if retryable and attempt < self._max_attempts - 1:
                    log.warning(f"[retry] {code} attempt {attempt+1}/{self._max_attempts}, sleeping {delay}s")
                    time.sleep(delay)
                    delay = min(delay * 2, self._max_delay)
                else:
                    raise
