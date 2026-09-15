def test_healthz(client):
    response = client.get("/healthz")
    assert response.status_code == 200
    assert response.json() == {"status": "ok"}


def test_readyz(client):
    response = client.get("/readyz")
    assert response.status_code == 200


def test_chat_requires_query(client):
    response = client.post("/api/chat", json={"query": "  "})
    assert response.status_code == 400


def test_history_starts_empty(client):
    response = client.get("/api/history")
    assert response.status_code == 200
    assert response.json() == []
