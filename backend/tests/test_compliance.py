"""Sprint 6 item 4: India-only compliance (DPDP Act 2023 + CERT-In Directions
2022) -- recorded consent, self-declared role, enforced chat retention, a
180-day on-VM security log, and a production start-up guard."""

import json
import logging
from datetime import UTC, datetime
from logging.handlers import TimedRotatingFileHandler
from unittest.mock import patch

import mongomock
import pytest
from app.config import Settings
from app.core import security_log
from app.core.compliance import CONSENT_VERSION, SECURITY_LOG_RETENTION_DAYS
from app.core.security import create_access_token
from app.repositories.chat_repository import ChatRepository
from pydantic import ValidationError

from .test_auth import FAKE_CHUNKS, auth_headers, signup

PASSWORD = "correct-horse-battery"
SECRET = "test-secret-not-for-production-only-32b"


@pytest.fixture
def https_client(client):
    client.base_url = "https://testserver"
    return client


@pytest.fixture
def log_file(tmp_path):
    """Point the security-log file sink at a temp dir for one test."""
    security_log.configure_security_log(str(tmp_path))
    yield tmp_path / security_log.LOG_FILENAME
    security_log.configure_security_log("")


def _events(path) -> list[dict]:
    for h in logging.getLogger("jurisai.security").handlers:
        h.flush()
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines()]


# --- consent and role at signup --------------------------------------------


@pytest.mark.parametrize(
    "extra",
    [
        {},  # neither
        {"role": "citizen"},  # no consent
        {"role": "citizen", "consent": False},  # explicit non-consent
        {"consent": True},  # no role
        {"role": "admin", "consent": True},  # not a real role
    ],
)
def test_signup_requires_a_role_and_affirmative_consent(client, extra):
    res = client.post(
        "/api/auth/signup", json={"email": "x@example.com", "password": PASSWORD, **extra}
    )
    assert res.status_code == 422
    assert client.app.state.user_repository.collection.count_documents({}) == 0


def test_signup_records_role_and_which_consent_text_was_accepted(client):
    token = signup(client, "consent@example.com", role="police")

    doc = client.app.state.user_repository.collection.find_one({"email": "consent@example.com"})
    assert doc["role"] == "police"
    assert doc["consent_version"] == CONSENT_VERSION
    assert isinstance(doc["consent_accepted_at"], datetime)
    assert client.get("/api/auth/me", headers=auth_headers(token)).json()["role"] == "police"


def test_accounts_that_predate_roles_get_the_strictest_disclaimer(client):
    users = client.app.state.user_repository.collection
    legacy_id = str(
        users.insert_one(
            {"email": "old@example.com", "password_hash": "x", "created_at": datetime.now(UTC)}
        ).inserted_id
    )
    token = create_access_token(legacy_id, SECRET)
    assert client.get("/api/auth/me", headers=auth_headers(token)).json()["role"] == "citizen"


# --- retention ------------------------------------------------------------


def test_chat_history_expires_after_the_configured_retention(client):
    indexes = client.app.state.chat_repository.collection.index_information()
    ttl = [i for i in indexes.values() if "expireAfterSeconds" in i]
    assert len(ttl) == 1
    assert ttl[0]["key"] == [("timestamp", 1)]
    assert ttl[0]["expireAfterSeconds"] == 365 * 86400


def test_retention_period_is_configurable():
    repo = ChatRepository(mongomock.MongoClient()["t"], retention_days=30)
    ttl = [i for i in repo.collection.index_information().values() if "expireAfterSeconds" in i]
    assert ttl[0]["expireAfterSeconds"] == 30 * 86400


# --- security log (CERT-In) -----------------------------------------------


def test_security_log_rotates_daily_and_keeps_180_days(tmp_path):
    security_log.configure_security_log(str(tmp_path))
    try:
        (handler,) = logging.getLogger("jurisai.security").handlers
        assert isinstance(handler, TimedRotatingFileHandler)
        assert handler.backupCount == SECURITY_LOG_RETENTION_DAYS == 180
        assert handler.when == "MIDNIGHT"
    finally:
        security_log.configure_security_log("")


def test_security_log_with_no_directory_writes_no_file(tmp_path):
    security_log.configure_security_log(str(tmp_path))
    security_log.configure_security_log("")
    assert logging.getLogger("jurisai.security").handlers == []


def test_auth_lifecycle_is_logged_without_secrets_or_pii(https_client, log_file):
    client = https_client
    signup(client, "audit@example.com", role="lawyer")
    client.post(
        "/api/auth/signup",
        json={
            "email": "audit@example.com",
            "password": PASSWORD,
            "role": "citizen",
            "consent": True,
        },
    )
    client.post("/api/auth/login", json={"email": "audit@example.com", "password": "wrong-one!"})
    login = client.post(
        "/api/auth/login", json={"email": "audit@example.com", "password": PASSWORD}
    )
    token = login.json()["access_token"]
    stolen = client.cookies.get("refresh_token")
    client.post("/api/auth/refresh")
    client.cookies.clear()
    client.cookies.set("refresh_token", stolen)
    client.post("/api/auth/refresh")  # replay of an already-rotated token
    client.post("/api/auth/logout")
    client.post("/api/auth/delete_account", json={"password": "nope"}, headers=auth_headers(token))
    client.post(
        "/api/auth/delete_account", json={"password": PASSWORD}, headers=auth_headers(token)
    )

    events = _events(log_file)
    names = [e["event"] for e in events]
    for expected in (
        "signup",
        "login_failed",
        "login_success",
        "token_refresh",
        "refresh_rejected",
        "account_delete_rejected",
        "account_deleted",
        "signup_rejected_duplicate",
    ):
        assert expected in names, f"{expected} missing from {names}"

    assert all({"ts", "event", "request_id", "ip"} <= e.keys() for e in events)
    assert next(e for e in events if e["event"] == "signup")["role"] == "lawyer"

    raw = log_file.read_text(encoding="utf-8")
    for secret in (PASSWORD, "wrong-one!", token, stolen, "audit@example.com"):
        assert secret not in raw, f"{secret[:12]!r} leaked into the security log"


def test_rate_limit_trips_are_logged(https_client, log_file):
    client = https_client
    token = signup(client, "burst2@example.com")
    with patch("app.api.chat.retrieve", return_value=FAKE_CHUNKS):
        for i in range(25):
            client.post("/api/chat", json={"query": f"q{i}"}, headers=auth_headers(token))

    limited = [e for e in _events(log_file) if e["event"] == "rate_limited"]
    assert limited
    assert limited[0]["path"] == "/api/chat"


def test_chat_text_never_reaches_the_security_log(https_client, log_file):
    client = https_client
    token = signup(client, "noquery@example.com")
    with patch("app.api.chat.retrieve", return_value=FAKE_CHUNKS):
        client.post(
            "/api/chat",
            json={"query": "my private fact pattern xyzzy"},
            headers=auth_headers(token),
        )
    assert "xyzzy" not in log_file.read_text(encoding="utf-8")


def test_email_fingerprint_is_stable_case_insensitive_and_not_the_address():
    a = security_log.email_fingerprint("User@Example.com ")
    assert a == security_log.email_fingerprint("user@example.com")
    assert "example" not in a and len(a) == 16


# --- production start-up guard ---------------------------------------------


def _prod_kwargs(**overrides):
    base = {
        "mongo_uri": "mongodb://test/x",
        "jwt_secret_key": "x" * 32,
        "groq_api_key": "test-key",
        "environment": "production",
        "grievance_officer_name": "A. Officer",
        "grievance_officer_email": "grievance@example.in",
        "grievance_officer_address": "1 Example Road, Pune, India",
        "security_log_dir": "/var/log/jurisai",
    }
    base.update(overrides)
    return base


def test_production_starts_when_compliance_settings_are_present():
    assert Settings(_env_file=None, **_prod_kwargs()).environment == "production"  # type: ignore[call-arg]


@pytest.mark.parametrize(
    "missing",
    [
        "grievance_officer_name",
        "grievance_officer_email",
        "grievance_officer_address",
        "security_log_dir",
    ],
)
def test_production_refuses_to_start_without_each_compliance_setting(missing):
    with pytest.raises(ValidationError, match=missing.upper()):
        Settings(_env_file=None, **_prod_kwargs(**{missing: ""}))  # type: ignore[call-arg]


def test_development_does_not_require_compliance_settings():
    kwargs = _prod_kwargs(environment="development")
    for k in ("grievance_officer_name", "grievance_officer_email", "grievance_officer_address"):
        kwargs[k] = ""
    kwargs["security_log_dir"] = ""
    assert Settings(_env_file=None, **kwargs).environment == "development"  # type: ignore[call-arg]
