"""Sprint 6: the auth/ownership paths are held to 100% coverage. These cover
the token lifecycle that test_auth.py doesn't -- login success, refresh
rotation and reuse, logout revocation, token-type confusion, expiry, and the
repository/ownership edge cases behind them."""

from datetime import UTC, datetime, timedelta

import jwt
import pytest
from app.core.security import AUDIENCE, ISSUER, create_access_token, create_refresh_token

from .test_auth import auth_headers, signup

SECRET = "test-secret-not-for-production-only-32b"
PASSWORD = "correct-horse-battery"


@pytest.fixture
def client(client):
    """The shared client talks http://, so the (correctly) Secure refresh
    cookie would never be sent back. Production is https behind Caddy -- test
    the cookie flow the same way."""
    client.base_url = "https://testserver"
    return client


def _forged(token_type: str, ttl: timedelta, *, sub: str = "u1", secret: str = SECRET) -> str:
    now = datetime.now(UTC)
    return jwt.encode(
        {
            "sub": sub,
            "iss": ISSUER,
            "aud": AUDIENCE,
            "type": token_type,
            "jti": "forged-jti",
            "iat": now,
            "exp": now + ttl,
        },
        secret,
        algorithm="HS256",
    )


def test_login_success_returns_working_token_and_httponly_cookie(client):
    signup(client, "login-ok@example.com")
    client.cookies.clear()

    res = client.post(
        "/api/auth/login", json={"email": "login-ok@example.com", "password": PASSWORD}
    )

    assert res.status_code == 200
    token = res.json()["access_token"]
    assert client.get("/api/auth/me", headers=auth_headers(token)).status_code == 200
    set_cookie = res.headers["set-cookie"].lower()
    assert "refresh_token=" in set_cookie
    assert "httponly" in set_cookie
    assert "samesite=strict" in set_cookie


def test_login_unknown_email_gives_the_same_error_as_wrong_password(client):
    signup(client, "real@example.com")
    wrong_pw = client.post(
        "/api/auth/login", json={"email": "real@example.com", "password": "nope-nope-nope"}
    )
    unknown = client.post(
        "/api/auth/login", json={"email": "ghost@example.com", "password": PASSWORD}
    )
    assert wrong_pw.status_code == unknown.status_code == 401
    # request_id is per-request noise; everything else must be identical so the
    # response doesn't reveal which half (email or password) was wrong.
    assert {k: v for k, v in wrong_pw.json().items() if k != "request_id"} == {
        k: v for k, v in unknown.json().items() if k != "request_id"
    }


def test_refresh_issues_new_access_token_and_rotates_the_cookie(client):
    signup(client, "refresh@example.com")
    old_cookie = client.cookies.get("refresh_token")

    res = client.post("/api/auth/refresh")

    assert res.status_code == 200
    assert (
        client.get("/api/auth/me", headers=auth_headers(res.json()["access_token"])).status_code
        == 200
    )
    assert client.cookies.get("refresh_token") != old_cookie


def test_a_used_refresh_token_cannot_be_replayed(client):
    """Rotation makes each refresh token single-use -- a stolen, already-used
    one must be dead."""
    signup(client, "replay@example.com")
    stolen = client.cookies.get("refresh_token")
    assert client.post("/api/auth/refresh").status_code == 200

    client.cookies.clear()
    client.cookies.set("refresh_token", stolen)
    assert client.post("/api/auth/refresh").status_code == 401


def test_refresh_without_a_cookie_is_rejected(client):
    assert client.post("/api/auth/refresh").status_code == 401


def test_refresh_with_a_garbage_cookie_is_rejected(client):
    client.cookies.set("refresh_token", "not-a-jwt")
    assert client.post("/api/auth/refresh").status_code == 401


def test_refresh_with_a_validly_signed_but_unknown_jti_is_rejected(client):
    """Signature checks out, but the server never issued it (or purged it)."""
    client.cookies.set("refresh_token", _forged("refresh", timedelta(days=1)))
    assert client.post("/api/auth/refresh").status_code == 401


def test_an_access_token_cannot_be_used_as_a_refresh_token(client):
    token = signup(client, "confusion@example.com")
    client.cookies.clear()
    client.cookies.set("refresh_token", token)
    res = client.post("/api/auth/refresh")
    assert res.status_code == 401


def test_a_refresh_token_cannot_be_used_as_an_access_token(client):
    signup(client, "confusion2@example.com")
    refresh = client.cookies.get("refresh_token")
    assert client.get("/api/auth/me", headers=auth_headers(refresh)).status_code == 401


def test_expired_and_wrongly_signed_tokens_are_rejected(client):
    expired = _forged("access", timedelta(seconds=-5))
    wrong_key = _forged("access", timedelta(minutes=5), secret="a-different-secret-of-32-bytes!!!")
    assert client.get("/api/auth/me", headers=auth_headers(expired)).status_code == 401
    assert client.get("/api/auth/me", headers=auth_headers(wrong_key)).status_code == 401


def test_a_token_for_a_user_that_no_longer_exists_is_rejected(client):
    ghost = create_access_token("507f1f77bcf86cd799439011", SECRET)  # valid ObjectId, no such user
    assert client.get("/api/auth/me", headers=auth_headers(ghost)).status_code == 401


def test_a_token_whose_subject_is_not_an_object_id_is_rejected(client):
    bad_sub = create_access_token("not-an-object-id", SECRET)
    assert client.get("/api/auth/me", headers=auth_headers(bad_sub)).status_code == 401


def test_logout_revokes_the_refresh_token(client):
    signup(client, "logout@example.com")
    cookie = client.cookies.get("refresh_token")

    assert client.post("/api/auth/logout").json() == {"success": True}

    client.cookies.set("refresh_token", cookie)  # replay the pre-logout cookie
    assert client.post("/api/auth/refresh").status_code == 401


@pytest.mark.parametrize("cookie", [None, "garbage"])
def test_logout_always_succeeds_even_without_a_usable_session(client, cookie):
    if cookie:
        client.cookies.set("refresh_token", cookie)
    assert client.post("/api/auth/logout").status_code == 200


def test_refresh_token_helper_returns_the_jti_it_embedded():
    token, jti = create_refresh_token("u1", SECRET)
    assert jwt.decode(token, SECRET, algorithms=["HS256"], audience=AUDIENCE)["jti"] == jti


# --- ownership / repository edge cases ------------------------------------


def test_renaming_a_session_to_blank_is_a_400(client):
    token = signup(client, "blank@example.com")
    res = client.post(
        "/api/rename_session/anything", json={"title": "   "}, headers=auth_headers(token)
    )
    assert res.status_code == 400


def test_deleting_a_nonexistent_session_is_a_404(client):
    token = signup(client, "nodelete@example.com")
    res = client.post(
        "/api/delete_session", json={"session_id": "does-not-exist"}, headers=auth_headers(token)
    )
    assert res.status_code == 404


def test_a_malformed_bearer_token_is_a_clean_401(client):
    """Garbage in the Authorization header must 401, not 500."""
    res = client.get("/api/history", headers={"Authorization": "Bearer %%%not.a.jwt"})
    assert res.status_code == 401


def test_owner_can_delete_their_own_session(client):
    from unittest.mock import patch

    from .test_auth import FAKE_CHUNKS

    token = signup(client, "owner-delete@example.com")
    with patch("app.api.chat.retrieve", return_value=FAKE_CHUNKS):
        session_id = client.post(
            "/api/chat", json={"query": "what is theft?"}, headers=auth_headers(token)
        ).json()["session_id"]

    res = client.post(
        "/api/delete_session", json={"session_id": session_id}, headers=auth_headers(token)
    )

    assert res.status_code == 200
    assert client.get(f"/api/session/{session_id}", headers=auth_headers(token)).json() == []
    assert client.get("/api/history", headers=auth_headers(token)).json() == []


def test_history_titles_fall_back_to_the_query_truncated_at_50_chars(client):
    from unittest.mock import patch

    from .test_auth import FAKE_CHUNKS

    token = signup(client, "titles@example.com")
    long_query = "what is the punishment for theft of a motor vehicle at night? " * 2
    with patch("app.api.chat.retrieve", return_value=FAKE_CHUNKS):
        client.post("/api/chat", json={"query": "short one"}, headers=auth_headers(token))
        client.post("/api/chat", json={"query": long_query}, headers=auth_headers(token))

    titles = {h["title"] for h in client.get("/api/history", headers=auth_headers(token)).json()}

    assert "short one" in titles
    assert long_query[:50] + "..." in titles


def _request(headers: dict[str, str]):
    from starlette.requests import Request

    scope = {
        "type": "http",
        "headers": [(k.lower().encode(), v.encode()) for k, v in headers.items()],
        "client": ("203.0.113.9", 1234),
    }
    return Request(scope)


def test_rate_limit_key_is_per_user_when_a_token_is_present():
    from app.core.rate_limit import user_or_ip_key

    token = create_access_token("507f1f77bcf86cd799439011", SECRET)
    assert user_or_ip_key(_request({"Authorization": f"Bearer {token}"})) == (
        "user:507f1f77bcf86cd799439011"
    )


@pytest.mark.parametrize(
    "headers",
    [{}, {"Authorization": "Bearer %%%not.a.jwt"}, {"Authorization": "Basic abc"}],
)
def test_rate_limit_key_falls_back_to_ip_without_a_usable_token(headers):
    """Unreachable over HTTP today (slowapi runs inside the route, after the
    auth dependency), so exercise the defensive fallback directly."""
    from app.core.rate_limit import user_or_ip_key

    assert user_or_ip_key(_request(headers)) == "ip:203.0.113.9"


def test_user_repository_ignores_malformed_ids():
    import mongomock
    from app.repositories.user_repository import UserRepository

    repo = UserRepository(mongomock.MongoClient()["t"])
    assert repo.get_by_id("not-an-object-id") is None
    assert repo.delete("not-an-object-id") is False
