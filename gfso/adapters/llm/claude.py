"""Claude API LLM provider — stub."""
from gfso.core.types import LLMProviderPort


class ClaudeLLM(LLMProviderPort):
    def __init__(self, api_key: str):
        raise NotImplementedError("Claude LLM provider not yet implemented")

    def complete(self, prompt: str, context: str = "") -> str:
        raise NotImplementedError
