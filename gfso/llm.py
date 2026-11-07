"""THE one switch every internal LLM role goes through (`llm_factory`), and what a run spent (`session_calls`)."""
from __future__ import annotations

from gfso.adapters.llm.registry import provider_for
from gfso.adapters.llm.stats import calls_of, tag_stage
from gfso.config import MODEL_DEFAULT


def llm_factory(model: str = MODEL_DEFAULT, execution=None):
    """THE ONE switch every internal gfso LLM role goes through (decompose, validate, critic, execute, contact). `model`
    is a spec `provider/model` (`ollama/qwen3:32b`, `deepseek/deepseek-chat`); an unprefixed id is Anthropic's through
    the Claude Code CLI (`registry.provider_for`). `execution` is WHERE the provider's processes and commands run
    (`ExecutionPort`; this host when None)."""
    return provider_for(model, execution)


def session_calls(llm, stage: str) -> list:
    """A run's call records, its last call tagged with the stage that spent it — what every spawned session
    books and hands back as its `stats`, whichever runner made it."""
    tag_stage(llm, stage)
    return list(calls_of(llm))
