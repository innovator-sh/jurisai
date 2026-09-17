"""Funded-phase provider — the in-country (ap-south-1) inference option once
there's a budget for it. Not implemented in the MVP; see anthropic_provider.py
for the same rationale.
"""

from app.llm.base import LLMError


class BedrockProvider:
    def __init__(self, region: str = "ap-south-1", model: str = "") -> None:
        self._region = region
        self._model = model

    async def complete(self, system: str, user: str) -> str:
        raise LLMError(
            "Bedrock provider is a funded-phase stub — not implemented in the MVP. "
            "Set LLM_PROVIDER=groq or LLM_PROVIDER=mistral."
        )
