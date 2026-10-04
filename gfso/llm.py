"""THE one switch every internal LLM role goes through (`llm_factory`), and what a run spent (`session_calls`)."""
from __future__ import annotations

from gfso.adapters.llm.generic import GenericLLM
from gfso.adapters.llm.headless import HeadlessClaudeLLM
from gfso.adapters.llm.stats import calls_of, tag_stage
from gfso import config as _config
from gfso.config import MODEL_DEFAULT


def llm_factory(model: str = MODEL_DEFAULT):
    """THE ONE switch every internal gfso LLM role goes through (decompose, validate, critic, future
    validate_result/delegate one-shots). Two env knobs, whole-system semantics (no per-role mixing):

    - `GFSO_PROVIDER` = anthropic (default) | generic
        anthropic → the headless `claude -p` transport (the ONLY Anthropic path);
        generic   → `GenericLLM` at `GFSO_GENERIC_BASE_URL` (OpenAI-compatible; local models /
                    other vendors, external users' own risk; `GFSO_GENERIC_MODEL`,
                    `GFSO_GENERIC_API_KEY` optional).
    - `GFSO_BILLING` = subscription (default) | api  — Anthropic only: `api` keeps
        ANTHROPIC_API_KEY in the child env (per-token billing on the same transport, measured);
        `subscription` strips it (claude.ai login).

    Flipping the whole system to a foreign provider and seamlessly back IS these two variables."""
    if _config.provider() == "generic":
        _g = _config.generic_provider()
        if not _g["base_url"]:
            raise ValueError("GFSO_PROVIDER=generic needs GFSO_GENERIC_BASE_URL — the OpenAI-compatible "
                             "endpoint to talk to")
        return GenericLLM(base_url=_g["base_url"], model=_g["model"] or model, api_key=_g["api_key"])
    return HeadlessClaudeLLM(model=model, keep_api_key=_config.api_billing())


def session_calls(llm, stage: str) -> list:
    """A run's call records, its last call tagged with the stage that spent it — what every spawned session
    books and hands back as its `stats`, whichever runner made it."""
    tag_stage(llm, stage)
    return list(calls_of(llm))
