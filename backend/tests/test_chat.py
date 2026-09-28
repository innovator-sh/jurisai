"""Crosswalk-grounding behaviour of /api/chat — loads the real, reviewed
data/crosswalk/ipc_bns.csv (app.state.crosswalk, wired in main.py's lifespan
same as the corpus registry) rather than a fixture, so this doubles as a
sanity check that the real file still contains the well-known IPC 302 <->
BNS 103 (murder) row this test depends on."""

from unittest.mock import patch

from app.rag.retriever import RetrievedChunk

from .test_auth import auth_headers, signup

IPC_302_CHUNK = [
    RetrievedChunk(
        text="Whoever commits murder shall be punished with death, or imprisonment for life...",
        act="Indian Penal Code, 1860",
        section="302",
        section_title="Punishment for murder",
        page=100,
        score=0.9,
        ingest_version="test",
    )
]


def test_chat_response_includes_verified_crosswalk_fact(client):
    token = signup(client, "crosswalk-chat@example.com")
    with patch("app.api.chat.retrieve", return_value=IPC_302_CHUNK):
        response = client.post(
            "/api/chat",
            json={"query": "what is the punishment for murder", "corpus_mode": "ipc"},
            headers=auth_headers(token),
        )
    assert response.status_code == 200
    body = response.json()
    assert len(body["crosswalk"]) == 1
    fact = body["crosswalk"][0]
    assert fact["bns_section"] == "103"
    assert fact["ipc_sections"] == ["302"]
    assert fact["relation"] == "renumbered"


def test_chat_prompt_sent_to_llm_includes_crosswalk_block(client, fake_llm):
    token = signup(client, "crosswalk-prompt@example.com")
    with patch("app.api.chat.retrieve", return_value=IPC_302_CHUNK):
        client.post(
            "/api/chat",
            json={"query": "what is the punishment for murder", "corpus_mode": "ipc"},
            headers=auth_headers(token),
        )
    user_message = fake_llm.complete.call_args.args[1]
    assert "VERIFIED CORRESPONDENCE" in user_message
    assert "BNS 103 <-> IPC 302 (renumbered)" in user_message


def test_chat_with_no_retrieved_chunks_has_empty_crosswalk(client):
    token = signup(client, "crosswalk-empty@example.com")
    with patch("app.api.chat.retrieve", return_value=[]):
        response = client.post(
            "/api/chat",
            json={"query": "irrelevant query", "corpus_mode": "ipc"},
            headers=auth_headers(token),
        )
    assert response.status_code == 200
    assert response.json()["crosswalk"] == []


def test_chat_response_reports_persisted_true_on_success(client):
    token = signup(client, "persisted-ok@example.com")
    with patch("app.api.chat.retrieve", return_value=IPC_302_CHUNK):
        response = client.post(
            "/api/chat",
            json={"query": "what is the punishment for murder", "corpus_mode": "ipc"},
            headers=auth_headers(token),
        )
    assert response.status_code == 200
    assert response.json()["persisted"] is True


def test_chat_still_returns_the_answer_when_persistence_fails(client, monkeypatch):
    """D029: a Mongo write failure after a successful LLM call must not
    waste that answer or fail the request -- it's still returned, just
    honestly flagged as unsaved via persisted=False."""
    from app.repositories.chat_repository import ChatRepository

    def _boom(*args, **kwargs):
        raise RuntimeError("mongo write failed")

    monkeypatch.setattr(ChatRepository, "insert_turn", _boom)

    token = signup(client, "persisted-fail@example.com")
    with patch("app.api.chat.retrieve", return_value=IPC_302_CHUNK):
        response = client.post(
            "/api/chat",
            json={"query": "what is the punishment for murder", "corpus_mode": "ipc"},
            headers=auth_headers(token),
        )
    assert response.status_code == 200
    body = response.json()
    assert body["persisted"] is False
    assert body["response"] == "a canned answer"  # the LLM's answer still came through
