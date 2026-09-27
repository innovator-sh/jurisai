"""Global exception handlers (core/errors.py) — every error response shares
one shape and never contains a raw exception string (D014). Adds a
throwaway route to the already-running app via the `client` fixture rather
than a real one, since every real route already goes through the same
global handlers — this isolates the handler behaviour itself."""

from app.core.request_id import REQUEST_ID_HEADER


def test_http_exception_is_wrapped_with_request_id(client):
    # /api/session/<id> on an unauthenticated request 401s via HTTPException.
    response = client.get("/api/session/does-not-exist")
    assert response.status_code == 401
    body = response.json()
    assert body["error"] == "Missing bearer token"
    assert body["request_id"]
    assert "detail" not in body


def test_unhandled_exception_never_leaks_exception_text(client, monkeypatch):
    from app.repositories.chat_repository import ChatRepository

    def _boom(*args, **kwargs):
        raise RuntimeError("super secret internal detail")

    monkeypatch.setattr(ChatRepository, "get_history", _boom)

    from .test_auth import auth_headers, signup

    token = signup(client, "errors-boom@example.com")
    response = client.get("/api/history", headers=auth_headers(token))
    assert response.status_code == 500
    body = response.json()
    assert body["error"] == "Internal server error"
    assert "super secret internal detail" not in response.text
    assert body["request_id"]


def test_every_response_carries_a_request_id_header(client):
    response = client.get("/healthz")
    assert response.headers[REQUEST_ID_HEADER]


def test_security_headers_present_on_every_response(client):
    response = client.get("/healthz")
    assert response.headers["X-Content-Type-Options"] == "nosniff"
    assert response.headers["X-Frame-Options"] == "DENY"
    assert "Content-Security-Policy" in response.headers
    assert "Strict-Transport-Security" in response.headers


def test_unknown_field_in_request_body_is_rejected(client):
    from .test_auth import auth_headers, signup

    token = signup(client, "extra-field@example.com")
    response = client.post(
        "/api/chat",
        json={"query": "what is theft", "some_unexpected_field": "x"},
        headers=auth_headers(token),
    )
    assert response.status_code == 422
