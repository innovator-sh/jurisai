"""Test fixtures keep the smoke test hermetic: no real Mongo, Qdrant, or LLM
provider network calls, and no ~400MB embedding-model download — even
though production startup does all of that for real."""

import os
from unittest.mock import AsyncMock, MagicMock, patch

import mongomock
import pytest
from fastapi.testclient import TestClient

# Required settings need *a* value to construct, even though the mocks below
# mean nothing ever actually calls out with them. Set before any `app.*`
# import, so tests don't depend on a real .env existing.
os.environ.setdefault("MONGO_URI", "mongodb://test-unused/jurisai")
os.environ.setdefault("GROQ_API_KEY", "test-unused-key")
os.environ.setdefault("JWT_SECRET_KEY", "test-secret-not-for-production-only-32b")


@pytest.fixture
def fake_llm():
    """The object returned by build_llm_provider() in tests. Override its
    `.complete` return value per-test: `fake_llm.complete.return_value = ...`."""
    provider = MagicMock()
    provider.complete = AsyncMock(return_value="a canned answer")
    return provider


@pytest.fixture
def client(fake_llm):
    fake_qdrant = MagicMock()
    fake_qdrant.collection_exists.return_value = True

    with (
        patch("app.main.MongoClient", return_value=mongomock.MongoClient()),
        patch("app.main.QdrantClient", return_value=fake_qdrant),
        patch("app.main.build_llm_provider", return_value=fake_llm),
    ):
        from app.main import app

        # raise_server_exceptions=False: production never lets an unhandled
        # exception escape as a Python traceback — core/errors.py's global
        # handler always turns it into a real 500 response — so tests should
        # see that same response, not a raised exception TestClient would
        # otherwise re-raise by default even with a handler registered.
        with TestClient(app, raise_server_exceptions=False) as test_client:
            yield test_client
