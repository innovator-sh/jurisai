from .test_auth import auth_headers, signup


def test_healthz(client):
    response = client.get("/healthz")
    assert response.status_code == 200
    assert response.json() == {"status": "ok"}


def test_readyz(client):
    response = client.get("/readyz")
    assert response.status_code == 200


def test_chat_requires_query(client):
    token = signup(client, "smoke-chat@example.com")
    response = client.post("/api/chat", json={"query": "  "}, headers=auth_headers(token))
    assert response.status_code == 400


def test_history_starts_empty(client):
    token = signup(client, "smoke-history@example.com")
    response = client.get("/api/history", headers=auth_headers(token))
    assert response.status_code == 200
    assert response.json() == []
