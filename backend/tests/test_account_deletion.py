"""D059 (DPDP): account deletion must actually purge chat history and
revoke access, not just soft-flag the account."""

from unittest.mock import patch

from .test_auth import FAKE_CHUNKS, auth_headers, signup


def test_wrong_password_is_rejected_and_deletes_nothing(client):
    token = signup(client, "keep-me@example.com", password="correct-horse-battery")

    response = client.post(
        "/api/auth/delete_account",
        json={"password": "wrong-password"},
        headers=auth_headers(token),
    )
    assert response.status_code == 401

    # Account must still exist and work normally afterward.
    me = client.get("/api/auth/me", headers=auth_headers(token))
    assert me.status_code == 200
    assert me.json()["email"] == "keep-me@example.com"


def test_correct_password_deletes_the_account(client):
    token = signup(client, "delete-me@example.com", password="correct-horse-battery")

    response = client.post(
        "/api/auth/delete_account",
        json={"password": "correct-horse-battery"},
        headers=auth_headers(token),
    )
    assert response.status_code == 200
    assert response.json()["success"] is True


def test_deleted_accounts_access_token_is_rejected_immediately(client):
    """Access tokens are stateless JWTs with no blacklist -- this only works
    because current_user re-fetches the user from the DB on every request,
    so a deleted user 401s well before the token's natural 15-minute expiry."""
    token = signup(client, "revoked-immediately@example.com", password="correct-horse-battery")
    client.post(
        "/api/auth/delete_account",
        json={"password": "correct-horse-battery"},
        headers=auth_headers(token),
    )
    me = client.get("/api/auth/me", headers=auth_headers(token))
    assert me.status_code == 401


def test_deletion_purges_chat_history(client):
    token = signup(client, "purge-history@example.com", password="correct-horse-battery")
    user_id = client.get("/api/auth/me", headers=auth_headers(token)).json()["id"]

    with patch("app.api.chat.retrieve", return_value=FAKE_CHUNKS):
        client.post("/api/chat", json={"query": "what is theft"}, headers=auth_headers(token))

    from app.main import app

    chat_repo = app.state.chat_repository
    assert chat_repo.collection.count_documents({"user_id": user_id}) == 1

    client.post(
        "/api/auth/delete_account",
        json={"password": "correct-horse-battery"},
        headers=auth_headers(token),
    )

    assert chat_repo.collection.count_documents({"user_id": user_id}) == 0
    assert app.state.user_repository.get_by_email("purge-history@example.com") is None


def test_deletion_revokes_the_refresh_cookie(client):
    token = signup(client, "revoke-refresh@example.com", password="correct-horse-battery")
    response = client.post(
        "/api/auth/delete_account",
        json={"password": "correct-horse-battery"},
        headers=auth_headers(token),
    )
    # The refresh cookie should be cleared in the response.
    set_cookie = response.headers.get("set-cookie", "")
    assert "refresh_token=" in set_cookie


def test_deletion_purges_stored_refresh_tokens(client):
    token = signup(client, "purge-refresh@example.com", password="correct-horse-battery")

    from app.main import app

    user_id = client.get("/api/auth/me", headers=auth_headers(token)).json()["id"]
    refresh_repo = app.state.refresh_token_repository
    assert refresh_repo.collection.count_documents({"user_id": user_id}) >= 1

    client.post(
        "/api/auth/delete_account",
        json={"password": "correct-horse-battery"},
        headers=auth_headers(token),
    )
    assert refresh_repo.collection.count_documents({"user_id": user_id}) == 0
