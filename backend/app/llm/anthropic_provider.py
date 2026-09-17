"""Funded-phase provider — not implemented in the MVP (no paid API budget).
Exists to prove the LLMProvider protocol generalizes beyond the two free
providers; wiring this up is a config change plus filling in `complete()`
with the `anthropic` SDK, not a redesign.
"""

from app.llm.base import LLMError


class AnthropicProvider:
    def __init__(self, api_key: str, model: str = "claude-sonnet-5") -> None:
        self._api_key = api_key
        self._model = model

    async def complete(self, system: str, user: str) -> str:
        raise LLMError(
            "Anthropic provider is a funded-phase stub — not implemented in the MVP. "
            "Set LLM_PROVIDER=groq or LLM_PROVIDER=mistral."
        )
