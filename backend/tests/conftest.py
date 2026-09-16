"""Test fixtures keep the smoke test hermetic: no real Mongo connection and no
~400MB embedding-model download, even though production startup (correctly,
per D017, open until Sprint 3) still does both for real."""

import os
from unittest.mock import MagicMock, patch

import mongomock
import pytest
from fastapi.testclient import TestClient

# Required settings need *a* value to construct, even though the mocks below
# mean nothing ever actually calls out with them. Set before any `app.*`
# import, so tests don't depend on a real .env existing.
os.environ.setdefault("MONGO_URI", "mongodb://test-unused/jurisai")
os.environ.setdefault("MISTRAL_API_KEY", "test-unused-key")


@pytest.fixture
def client():
    with (
        patch("app.main.MongoClient", return_value=mongomock.MongoClient()),
        patch("app.main.build_or_load_vector_store", return_value=MagicMock()),
    ):
        from app.main import app

        with TestClient(app) as test_client:
            yield test_client
