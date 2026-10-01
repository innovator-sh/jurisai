"""`LLMProvider.stream()` (Sprint 5, SSE chat) for the two MVP providers.
Mocks each provider's SDK client directly (no real network call) -- mirrors
how `complete()` is exercised in practice, just for the streaming path,
which had no test coverage at all before this (no provider-level tests
existed for `complete()` either, confirmed by grep before writing these)."""

from types import SimpleNamespace

import groq
import httpx
import pytest
from app.llm.base import LLMError
from app.llm.groq_provider import GroqProvider
from app.llm.mistral_provider import MistralProvider
from mistralai.client.errors import SDKError


class _FakeAsyncStream:
    """Minimal async-iterable standing in for an SDK's streaming response."""

    def __init__(self, items):
        self._items = items

    def __aiter__(self):
        return self._gen()

    async def _gen(self):
        for item in self._items:
            yield item


def _groq_chunk(content):
    return SimpleNamespace(choices=[SimpleNamespace(delta=SimpleNamespace(content=content))])


async def test_groq_stream_yields_each_chunks_content(monkeypatch):
    provider = GroqProvider(api_key="test-unused")
    chunks = _FakeAsyncStream(
        [_groq_chunk("Whoever "), _groq_chunk(None), _groq_chunk("commits murder")]
    )

    async def _fake_create(*args, **kwargs):
        return chunks

    monkeypatch.setattr(provider._client.chat.completions, "create", _fake_create)

    received = [c async for c in provider.stream("system", "user")]
    assert received == ["Whoever ", "commits murder"]


async def test_groq_stream_wraps_connection_failure_as_llm_error(monkeypatch):
    provider = GroqProvider(api_key="test-unused")

    async def _fake_create(*args, **kwargs):
        raise groq.GroqError("boom")

    monkeypatch.setattr(provider._client.chat.completions, "create", _fake_create)

    with pytest.raises(LLMError):
        async for _ in provider.stream("system", "user"):
            pass


def _mistral_event(content):
    choice = SimpleNamespace(delta=SimpleNamespace(content=content))
    return SimpleNamespace(data=SimpleNamespace(choices=[choice]))


async def test_mistral_stream_yields_each_events_content(monkeypatch):
    provider = MistralProvider(api_key="test-unused")
    events = _FakeAsyncStream(
        [_mistral_event("Whoever "), _mistral_event(None), _mistral_event("commits murder")]
    )

    async def _fake_stream_async(*args, **kwargs):
        return events

    monkeypatch.setattr(provider._client.chat, "stream_async", _fake_stream_async)

    received = [c async for c in provider.stream("system", "user")]
    assert received == ["Whoever ", "commits murder"]


async def test_mistral_stream_wraps_sdk_failure_as_llm_error(monkeypatch):
    provider = MistralProvider(api_key="test-unused")
    response = httpx.Response(400, request=httpx.Request("POST", "http://x"))

    async def _fake_stream_async(*args, **kwargs):
        raise SDKError("bad request", response)

    monkeypatch.setattr(provider._client.chat, "stream_async", _fake_stream_async)

    with pytest.raises(LLMError):
        async for _ in provider.stream("system", "user"):
            pass
