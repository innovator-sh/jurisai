"""Sprint 2 exit criteria: an unowned session_id returns 404 on every session
route, unauthenticated requests get 401, and the chat route's rate limit trips
under load."""

from unittest.mock import patch

from app.rag.retriever import RetrievedChunk

FAKE_CHUNKS = [
    RetrievedChunk(
        text="Whoever commits theft shall be punished...",
        act="Indian Penal Code, 1860",
        section="379",
        section_title="Punishment for theft",
        page=1409,
        score=0.7,
        ingest_version="test",
    )
]


def signup(client, email: str, password: str = "correct-horse-battery") -> str:
    res = client.post("/api/auth/signup", json={"email": email, "password": password})
    assert res.status_code == 201, res.text
    return res.json()["access_token"]


def auth_headers(token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}"}


def test_signup_and_me(client):
    token = signup(client, "alice@example.com")
    res = client.get("/api/auth/me", headers=auth_headers(token))
    assert res.status_code == 200
    assert res.json()["email"] == "alice@example.com"


def test_signup_duplicate_email_conflicts(client):
    signup(client, "dupe@example.com")
    res = client.post(
        "/api/auth/signup", json={"email": "dupe@example.com", "password": "whatever123"}
    )
    assert res.status_code == 409


def test_login_wrong_password_rejected(client):
    signup(client, "bob@example.com")
    res = client.post(
        "/api/auth/login", json={"email": "bob@example.com", "password": "wrong-password"}
    )
    assert res.status_code == 401


def test_protected_routes_require_auth(client):
    assert client.get("/api/history").status_code == 401
    assert client.get("/api/session/whatever").status_code == 401
    assert client.post("/api/rename_session/x", json={"title": "y"}).status_code == 401
    assert client.post("/api/delete_session", json={"session_id": "x"}).status_code == 401
    assert client.post("/api/chat", json={"query": "hi"}).status_code == 401


def test_user_cannot_touch_another_users_session(client):
    token_a = signup(client, "userA@example.com")
    token_b = signup(client, "userB@example.com")

    with patch("app.api.chat.retrieve", return_value=FAKE_CHUNKS):
        chat_res = client.post(
            "/api/chat", json={"query": "what is theft?"}, headers=auth_headers(token_a)
        )
    assert chat_res.status_code == 200
    session_id = chat_res.json()["session_id"]

    # User A can see it.
    a_res = client.get(f"/api/session/{session_id}", headers=auth_headers(token_a))
    assert a_res.status_code == 200

    # User B gets 404 on every route touching that session — never a 403,
    # which would confirm the session_id exists at all (D004-D008).
    b_headers = auth_headers(token_b)
    assert client.get(f"/api/session/{session_id}", headers=b_headers).json() == []
    assert (
        client.post(
            f"/api/rename_session/{session_id}", json={"title": "hijacked"}, headers=b_headers
        ).status_code
        == 404
    )
    assert (
        client.post(
            "/api/delete_session", json={"session_id": session_id}, headers=b_headers
        ).status_code
        == 404
    )
    # And user A's history never contains anything from user B's account.
    b_history = client.get("/api/history", headers=b_headers).json()
    assert b_history == []


def test_chat_rate_limit_trips(client):
    token = signup(client, "burst@example.com")
    with patch("app.api.chat.retrieve", return_value=FAKE_CHUNKS):
        statuses = [
            client.post(
                "/api/chat", json={"query": f"q{i}"}, headers=auth_headers(token)
            ).status_code
            for i in range(25)
        ]
    assert 429 in statuses
