"""MVP alternate provider — matches what the legacy app used, kept as a
config-swappable fallback behind the same protocol as Groq.
"""

from mistralai.client import Mistral
from mistralai.client.errors import SDKError
from tenacity import retry, retry_if_exception, stop_after_attempt, wait_exponential

from app.llm.base import LLMError

DEFAULT_MODEL = "mistral-small-latest"
TIMEOUT_MS = 15_000


def _is_retryable(exc: BaseException) -> bool:
    status = getattr(exc, "status_code", None)
    return isinstance(exc, SDKError) and (status == 429 or (status is not None and status >= 500))


class MistralProvider:
    def __init__(self, api_key: str, model: str = DEFAULT_MODEL) -> None:
        self._client = Mistral(api_key=api_key)
        self._model = model

    @retry(
        retry=retry_if_exception(_is_retryable),
        stop=stop_after_attempt(3),
        wait=wait_exponential(multiplier=1, min=1, max=8),
        reraise=True,
    )
    async def _create(self, system: str, user: str) -> str:
        response = await self._client.chat.complete_async(
            model=self._model,
            messages=[  # type: ignore[arg-type]  # dicts are accepted at runtime (TypedDict union)
                {"role": "system", "content": system},
                {"role": "user", "content": user},
            ],
            max_tokens=1024,
            temperature=0.3,
            timeout_ms=TIMEOUT_MS,
        )
        message = response.choices[0].message if response.choices else None
        content = message.content if message else None
        if not content or not isinstance(content, str):
            raise LLMError("Mistral returned an empty or non-text response")
        return content

    async def complete(self, system: str, user: str) -> str:
        try:
            return await self._create(system, user)
        except SDKError as e:
            raise LLMError(f"Mistral request failed: {e}") from e
