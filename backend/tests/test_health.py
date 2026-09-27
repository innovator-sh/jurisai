def test_readyz_ok_when_everything_is_up(client):
    response = client.get("/readyz")
    assert response.status_code == 200
    body = response.json()
    assert body["mongo"] is True
    assert body["llm_provider"] is True


def test_readyz_reports_503_when_mongo_is_down(client, monkeypatch):
    admin_db = client.app.state.chat_repository.collection.database.client.admin

    def _boom(*args, **kwargs):
        raise ConnectionError("mongo is down")

    monkeypatch.setattr(admin_db, "command", _boom)
    response = client.get("/readyz")
    assert response.status_code == 503
    assert response.json()["mongo"] is False
