"""Sprint 6 item 2: load-check /api/chat concurrency with a stubbed provider.

The legacy app made a blocking LLM call inside the request handler, so N
concurrent users were answered one at a time. These tests fire N simultaneous
chats at the real route (real auth, routing, prompt building, persistence;
only the LLM and the vector search are stubbed) and assert wall time is
nowhere near N x per-call latency.

Two separate things can serialize requests, so each gets its own test:
  * the LLM call (awaited -- must overlap), and
  * retrieval (embedding + a Qdrant query: blocking work that must not run on
    the event loop).
"""

import asyncio
import time
from unittest.mock import MagicMock, patch

import httpx
import mongomock
import pytest
from app.rag.retriever import RetrievedChunk

N = 20
LLM_LATENCY = 0.4  # seconds each stubbed LLM call takes
RETRIEVAL_LATENCY = 0.05  # seconds of *blocking* work per stubbed retrieval

CHUNK = RetrievedChunk(
    text="Whoever commits theft shall be punished...",
    act="Indian Penal Code, 1860",
    section="379",
    section_title="Punishment for theft",
    page=1409,
    score=0.7,
    ingest_version="test",
)


@pytest.fixture
async def app_client(fake_llm):
    fake_qdrant = MagicMock()
    fake_qdrant.collection_exists.return_value = True
    with (
        patch("app.main.MongoClient", return_value=mongomock.MongoClient()),
        patch("app.main.QdrantClient", return_value=fake_qdrant),
        patch("app.main.build_llm_provider", return_value=fake_llm),
    ):
        from app.main import app

        async with app.router.lifespan_context(app):
            transport = httpx.ASGITransport(app=app)
            async with httpx.AsyncClient(transport=transport, base_url="https://testserver") as c:
                yield c


async def _signup_many(client: httpx.AsyncClient, n: int) -> list[dict[str, str]]:
    headers = []
    for i in range(n):
        res = await client.post(
            "/api/auth/signup",
            json={
                "email": f"load{i}@example.com",
                "password": "correct-horse-battery",
                "role": "lawyer",
                "consent": True,
            },
        )
        assert res.status_code == 201, res.text
        headers.append({"Authorization": f"Bearer {res.json()['access_token']}"})
    return headers


async def _fire(client: httpx.AsyncClient, headers: list[dict[str, str]]) -> float:
    """N simultaneous chats, one per user (distinct users so the per-user rate
    limit isn't what's being measured). Returns wall-clock seconds."""
    start = time.perf_counter()
    responses = await asyncio.gather(
        *[
            client.post("/api/chat", json={"query": f"what is theft {i}?"}, headers=h)
            for i, h in enumerate(headers)
        ]
    )
    elapsed = time.perf_counter() - start
    print(f"{len(headers)} concurrent chats in {elapsed:.2f}s")
    assert [r.status_code for r in responses] == [200] * len(headers), [
        r.text for r in responses if r.status_code != 200
    ][:1]
    return elapsed


async def test_concurrent_chats_overlap_on_the_llm_call(app_client, fake_llm):
    async def slow_complete(*_a, **_kw):
        await asyncio.sleep(LLM_LATENCY)
        return "a canned answer"

    fake_llm.complete.side_effect = slow_complete
    headers = await _signup_many(app_client, N)

    with patch("app.api.chat.retrieve", return_value=[CHUNK]):
        elapsed = await _fire(app_client, headers)

    serial = N * LLM_LATENCY
    # Fully serialized would be 8s; allow generous headroom for CI jitter.
    assert elapsed < serial / 3, f"{elapsed:.2f}s for {N} chats (serial would be {serial:.1f}s)"


async def test_blocking_retrieval_does_not_serialize_concurrent_chats(app_client, fake_llm):
    """retrieve() embeds the query and calls Qdrant synchronously. Run directly
    on the event loop it would stall every other request for its duration."""

    async def slow_complete(*_a, **_kw):
        await asyncio.sleep(LLM_LATENCY)
        return "a canned answer"

    def blocking_retrieve(*_a, **_kw):
        time.sleep(RETRIEVAL_LATENCY)  # deliberately blocking, like embed + Qdrant IO
        return [CHUNK]

    fake_llm.complete.side_effect = slow_complete
    headers = await _signup_many(app_client, N)

    with patch("app.api.chat.retrieve", side_effect=blocking_retrieve):
        elapsed = await _fire(app_client, headers)

    # On the loop: ~N*0.05 = 1.0s of serialized retrieval stacked on the 0.4s LLM
    # overlap. Off the loop: the 20 retrievals overlap in worker threads.
    budget = LLM_LATENCY + (N * RETRIEVAL_LATENCY) / 2
    assert elapsed < budget, f"{elapsed:.2f}s (budget {budget:.2f}s) -- retrieval blocks the loop"
