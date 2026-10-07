"""Funded-phase provider — the in-country (ap-south-1) inference option once
there's a budget for it. Not implemented in the MVP; see anthropic_provider.py
for the same rationale.
"""

from collections.abc import AsyncIterator

from app.llm.base import LLMError

_NOT_IMPLEMENTED = (
    "Bedrock provider is a funded-phase stub — not implemented in the MVP. "
    "Set LLM_PROVIDER=groq or LLM_PROVIDER=mistral."
)


class BedrockProvider:
    def __init__(self, region: str = "ap-south-1", model: str = "") -> None:
        self._region = region
        self._model = model

    async def complete(self, system: str, user: str) -> str:
        raise LLMError(_NOT_IMPLEMENTED)

    async def stream(self, system: str, user: str) -> AsyncIterator[str]:
        raise LLMError(_NOT_IMPLEMENTED)
        yield ""  # pragma: no cover -- unreachable; makes this an async generator
