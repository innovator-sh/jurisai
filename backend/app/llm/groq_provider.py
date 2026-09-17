"""MVP default provider — free tier, fastest of the no-cost options.
Streaming isn't wired in yet: no route consumes SSE until Sprint 5 rebuilds
the frontend, so `complete()` is all this needs today; `stream()` lands on
the protocol when something actually calls it.
"""

import groq
from tenacity import retry, retry_if_exception_type, stop_after_attempt, wait_exponential

from app.llm.base import LLMError

DEFAULT_MODEL = "llama-3.3-70b-versatile"
TIMEOUT_SECONDS = 15.0

_RETRYABLE = (groq.RateLimitError, groq.APIConnectionError, groq.InternalServerError)


class GroqProvider:
    def __init__(self, api_key: str, model: str = DEFAULT_MODEL) -> None:
        self._client = groq.AsyncGroq(api_key=api_key, timeout=TIMEOUT_SECONDS)
        self._model = model

    @retry(
        retry=retry_if_exception_type(_RETRYABLE),
        stop=stop_after_attempt(3),
        wait=wait_exponential(multiplier=1, min=1, max=8),
        reraise=True,
    )
    async def _create(self, system: str, user: str) -> str:
        # Retryable groq.* exceptions must propagate here uncaught, or
        # tenacity never sees them to decide whether to retry.
        response = await self._client.chat.completions.create(
            model=self._model,
            messages=[
                {"role": "system", "content": system},
                {"role": "user", "content": user},
            ],
            max_tokens=1024,
            temperature=0.3,
        )
        content = response.choices[0].message.content
        if not content:
            raise LLMError("Groq returned an empty response")
        return content

    async def complete(self, system: str, user: str) -> str:
        try:
            return await self._create(system, user)
        except groq.GroqError as e:
            raise LLMError(f"Groq request failed: {e}") from e
