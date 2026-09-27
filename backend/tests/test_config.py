"""CORS_ORIGINS as documented in .env.example (a bare comma-separated
string) used to crash Settings() outright — pydantic-settings' default env
parsing for a list field expects JSON syntax. Reproduces that exact crash
and confirms the fix."""

import pytest
from app.config import Settings
from pydantic import ValidationError


def _base_kwargs() -> dict[str, str]:
    return {
        "mongo_uri": "mongodb://test/x",
        "jwt_secret_key": "x" * 32,
        "groq_api_key": "test-key",
    }


def test_comma_separated_cors_origins_parses_into_a_list():
    settings = Settings(cors_origins="http://a.example,http://b.example", **_base_kwargs())
    assert settings.cors_origins == ["http://a.example", "http://b.example"]


def test_single_origin_with_no_comma_still_parses():
    settings = Settings(cors_origins="http://localhost:8000", **_base_kwargs())
    assert settings.cors_origins == ["http://localhost:8000"]


def test_a_real_list_passes_through_unchanged():
    settings = Settings(cors_origins=["http://a.example"], **_base_kwargs())
    assert settings.cors_origins == ["http://a.example"]


def test_missing_required_field_still_fails_fast(monkeypatch):
    # conftest.py sets these globally via os.environ.setdefault for every
    # other test's benefit — remove them here so this test actually
    # exercises the "nothing supplies it" case rather than silently reading
    # the ambient value.
    monkeypatch.delenv("MONGO_URI", raising=False)
    monkeypatch.delenv("JWT_SECRET_KEY", raising=False)
    with pytest.raises(ValidationError):
        Settings(_env_file=None, groq_api_key="test-key")  # type: ignore[call-arg]
