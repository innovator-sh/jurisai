"""Crosswalk-grounding behaviour of /api/chat — loads the real, reviewed
data/crosswalk/ipc_bns.csv (app.state.crosswalk, wired in main.py's lifespan
same as the corpus registry) rather than a fixture, so this doubles as a
sanity check that the real file still contains the well-known IPC 302 <->
BNS 103 (murder) row this test depends on."""

import json
from unittest.mock import patch

from app.llm.base import LLMError
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


def _parse_sse(text):
    """[(event_name, parsed_json_data), ...] for a text/event-stream body."""
    events = []
    for block in text.strip("\n").split("\n\n"):
        if not block:
            continue
        event_type = None
        data = None
        for line in block.split("\n"):
            if line.startswith("event:"):
                event_type = line[len("event:") :].strip()
            elif line.startswith("data:"):
                data = line[len("data:") :].strip()
        events.append((event_type, json.loads(data) if data is not None else None))
    return events


def test_chat_stream_emits_crosswalk_token_done_events_in_order(client):
    token = signup(client, "stream-ok@example.com")
    with patch("app.api.chat.retrieve", return_value=IPC_302_CHUNK):
        response = client.post(
            "/api/chat",
            json={
                "query": "what is the punishment for murder",
                "corpus_mode": "ipc",
                "stream": True,
            },
            headers=auth_headers(token),
        )
    assert response.status_code == 200
    assert response.headers["content-type"].startswith("text/event-stream")

    events = _parse_sse(response.text)
    names = [name for name, _ in events]
    assert names == ["crosswalk", "token", "token", "done"]

    crosswalk_data = events[0][1]
    assert len(crosswalk_data) == 1
    assert crosswalk_data[0]["bns_section"] == "103"

    # fake_llm's default stream yields ["a canned ", "answer"] (conftest.py)
    assert [events[1][1], events[2][1]] == ["a canned ", "answer"]

    done_data = events[3][1]
    assert done_data["persisted"] is True
    assert "session_id" in done_data


def test_chat_stream_with_no_retrieved_chunks_still_completes(client):
    token = signup(client, "stream-empty@example.com")
    with patch("app.api.chat.retrieve", return_value=[]):
        response = client.post(
            "/api/chat",
            json={"query": "irrelevant query", "corpus_mode": "ipc", "stream": True},
            headers=auth_headers(token),
        )
    assert response.status_code == 200
    events = _parse_sse(response.text)
    names = [name for name, _ in events]
    assert names == ["crosswalk", "token", "done"]
    assert events[0][1] == []  # empty crosswalk -- nothing was retrieved
    assert "I don't have that in the" in events[1][1]
    assert events[2][1]["persisted"] is True


def test_chat_stream_reports_persisted_false_when_storage_fails(client, monkeypatch):
    from app.repositories.chat_repository import ChatRepository

    def _boom(*args, **kwargs):
        raise RuntimeError("mongo write failed")

    monkeypatch.setattr(ChatRepository, "insert_turn", _boom)

    token = signup(client, "stream-persist-fail@example.com")
    with patch("app.api.chat.retrieve", return_value=IPC_302_CHUNK):
        response = client.post(
            "/api/chat",
            json={
                "query": "what is the punishment for murder",
                "corpus_mode": "ipc",
                "stream": True,
            },
            headers=auth_headers(token),
        )
    assert response.status_code == 200
    events = _parse_sse(response.text)
    done_data = events[-1][1]
    assert events[-1][0] == "done"
    assert done_data["persisted"] is False


def test_chat_stream_emits_error_event_on_llm_failure(client, fake_llm):
    async def _raising_stream(*args, **kwargs):
        raise LLMError("provider is down")
        yield ""  # pragma: no cover -- unreachable; makes this an async generator

    fake_llm.stream = _raising_stream

    token = signup(client, "stream-llm-error@example.com")
    with patch("app.api.chat.retrieve", return_value=IPC_302_CHUNK):
        response = client.post(
            "/api/chat",
            json={
                "query": "what is the punishment for murder",
                "corpus_mode": "ipc",
                "stream": True,
            },
            headers=auth_headers(token),
        )
    assert response.status_code == 200
    events = _parse_sse(response.text)
    names = [name for name, _ in events]
    assert names == ["crosswalk", "error"]  # no "done" -- the stream ends on the error
    assert events[1][1]["detail"] == "The answer service is unavailable"
