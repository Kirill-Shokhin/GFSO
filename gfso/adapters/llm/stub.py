"""Stub LLM provider for testing."""
from gfso.core.types import LLMProviderPort


class StubLLM(LLMProviderPort):
    def complete(self, prompt: str, context: str = "") -> str:
        return ""
