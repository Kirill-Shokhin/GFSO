"""GenericLLM — THE non-Anthropic extension point (OpenAI-compatible HTTP, incl. local models).

This is the ONE clearly-named endpoint an external user plugs a foreign provider into ("на свой
страх и риск"): everything internal to gfso takes its adapter from `runtime.llm_factory()`, so
switching the WHOLE system here is `GFSO_PROVIDER=generic` + `GFSO_GENERIC_BASE_URL/MODEL[/API_KEY]`
— and switching back to the Anthropic harness is removing that env. No prompt or schema changes on
either side: schema enforcement is ours (`structured.py`), any text-returning provider serves it.

Status: architecturally complete, NOT live-tested against a real provider (we don't run one) —
the code path mirrors the headless adapter 1:1 (same port, same stats shape, same structured
machinery + one repair retry). Frozen prompts are calibrated on Claude: before trusting another
provider's OUTPUT, re-run the frozen T01 judge protocol (runs/v2_t01/).
"""
from __future__ import annotations

import json
import logging
import time
import urllib.request

from gfso.core.types import LLMProviderPort
from .structured import schema_instruction, parse_structured, RETRY_SUFFIX

log = logging.getLogger(__name__)


class GenericLLM(LLMProviderPort):
    def __init__(self, base_url: str, model: str, api_key: str | None = None, timeout: int = 600):
        self._url = base_url.rstrip("/") + "/chat/completions"
        self._model = model
        self._key = api_key
        self._timeout = timeout
        self.calls: list[dict] = []   # same stats shape as the headless adapter

    def tag_last(self, stage: str) -> None:
        if self.calls:
            self.calls[-1]["stage"] = stage

    def _call(self, system: str, user: str) -> str:
        body = json.dumps({"model": self._model,
                           "messages": [{"role": "system", "content": system},
                                        {"role": "user", "content": user}]}).encode("utf-8")
        req = urllib.request.Request(self._url, data=body, method="POST",
                                     headers={"Content-Type": "application/json",
                                              **({"Authorization": f"Bearer {self._key}"} if self._key else {})})
        t0 = time.monotonic()
        try:
            with urllib.request.urlopen(req, timeout=self._timeout) as resp:
                out = json.loads(resp.read().decode("utf-8"))
            usage = out.get("usage") or {}
            self.calls.append({
                "duration_ms": int((time.monotonic() - t0) * 1000),
                "input_tokens": usage.get("prompt_tokens"),
                "output_tokens": usage.get("completion_tokens"),
                "cache_read_input_tokens": None, "cache_creation_input_tokens": None,
                # An OpenAI-compatible endpoint prices per provider, not per response: no cost field
                # exists here, and inventing one from a token count would be a made-up number in a
                # column that must be measured. None = not reported, never 0.0.
                "cost_usd": None, "model": self._model,
            })
            return ((out.get("choices") or [{}])[0].get("message") or {}).get("content") or ""
        except Exception as e:
            log.warning(f"generic llm call failed: {e}")
            return ""

    def complete(self, prompt: str, context: str = "") -> str:
        return self._call(context or "You are a GFSO System LLM analyzing task decompositions.", prompt)

    def complete_structured(self, system: str, user: str, schema: dict) -> dict:
        text = self._call(system, user + schema_instruction(schema))
        parsed = parse_structured(text, schema)
        if parsed is not None:
            return parsed
        if self.calls:
            self.calls[-1]["parse_failed"] = True
        if text:
            parsed = parse_structured(self._call(system, user + schema_instruction(schema) + RETRY_SUFFIX), schema)
            if parsed is not None:
                return parsed
        log.warning("generic structured call: no schema-valid json after retry")
        return {}
