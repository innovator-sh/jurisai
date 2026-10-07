"""The `LLMProvider` protocol — every LLM call in the app goes through this,
never a provider SDK directly from route code. `LLM_PROVIDER` in config
picks the implementation; swapping providers is a config change, not a
route change.
"""

from collections.abc import AsyncIterator
from typing import Protocol


class LLMError(Exception):
    """Raised on a provider failure. Replaces the legacy behaviour (D025) of
    returning an error *string* that then got persisted and shown to the
    user as if it were a legal answer — callers must handle this as a
    typed error, not text to display."""


class LLMProvider(Protocol):
    async def complete(self, system: str, user: str) -> str: ...

    def stream(self, system: str, user: str) -> AsyncIterator[str]:
        """Yields the answer incrementally (Sprint 5's SSE chat). Each
        provider only retries *opening* the stream (a retryable error before
        any token has reached the caller) — once a chunk has been yielded,
        retrying would silently duplicate partial output, so a failure past
        that point raises LLMError and ends the stream instead."""
        ...
