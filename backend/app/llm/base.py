"""The `LLMProvider` protocol — every LLM call in the app goes through this,
never a provider SDK directly from route code. `LLM_PROVIDER` in config
picks the implementation; swapping providers is a config change, not a
route change.
"""

from typing import Protocol


class LLMError(Exception):
    """Raised on a provider failure. Replaces the legacy behaviour (D025) of
    returning an error *string* that then got persisted and shown to the
    user as if it were a legal answer — callers must handle this as a
    typed error, not text to display."""


class LLMProvider(Protocol):
    async def complete(self, system: str, user: str) -> str: ...
