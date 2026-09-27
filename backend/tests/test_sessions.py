"""D026: renaming a session to its current title used to 404 (MongoDB's
modified_count is 0 on a no-op update) even though the session exists and
belongs to the caller."""

from unittest.mock import patch

from .test_auth import FAKE_CHUNKS, auth_headers, signup


def _create_a_session(client, token: str) -> str:
    with patch("app.api.chat.retrieve", return_value=FAKE_CHUNKS):
        response = client.post(
            "/api/chat",
            json={"query": "what is theft"},
            headers=auth_headers(token),
        )
    return response.json()["session_id"]


def test_renaming_to_the_same_title_twice_succeeds_both_times(client):
    token = signup(client, "rename-noop@example.com")
    session_id = _create_a_session(client, token)

    first = client.post(
        f"/api/rename_session/{session_id}",
        json={"title": "My case"},
        headers=auth_headers(token),
    )
    assert first.status_code == 200
    assert first.json()["success"] is True

    second = client.post(
        f"/api/rename_session/{session_id}",
        json={"title": "My case"},
        headers=auth_headers(token),
    )
    assert second.status_code == 200
    assert second.json()["success"] is True


def test_renaming_a_nonexistent_session_still_404s(client):
    token = signup(client, "rename-missing@example.com")
    response = client.post(
        "/api/rename_session/does-not-exist",
        json={"title": "x"},
        headers=auth_headers(token),
    )
    assert response.status_code == 404
