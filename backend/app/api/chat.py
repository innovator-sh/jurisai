"""Ported from jurisai/Backend/app.py (`/chat`, `get_answer`), relocated only.

Preserved as-is, all tracked as open issues for later sprints:
- D024: raw `Document` reprs interpolated into the prompt (Sprint 3).
- D025: a Mistral error string gets stored and returned as if it were the
  answer, instead of a typed error (Sprint 3).
- D029: a Mongo write failure is silently swallowed (Sprint 3).
- D015: no rate limiting on this route (Sprint 2).
- No auth, no ownership on session_id (D004-D008, Sprint 2).
"""

import uuid

from fastapi import APIRouter, HTTPException

from app.core.logging import get_logger
from app.deps import ChatRepositoryDep, SettingsDep, VectorStoreDep
from app.llm.mistral_client import query_mistral
from app.models.chat import ChatRequest, ChatResponse
from app.rag.retriever import retrieve_context

router = APIRouter()
logger = get_logger(__name__)


@router.post("/chat", response_model=ChatResponse)
def chat(
    body: ChatRequest,
    vector_store: VectorStoreDep,
    chat_repo: ChatRepositoryDep,
    settings: SettingsDep,
) -> ChatResponse:
    session_id = body.session_id or ""
    if not session_id or session_id == "None":
        session_id = str(uuid.uuid4())
    query = body.query.strip()
    if not query:
        raise HTTPException(status_code=400, detail="No query provided")

    context = retrieve_context(vector_store, query, k=3)
    formatted_query = f"Based on the following legal documents: {context}\nAnswer this: {query}"
    response = query_mistral(formatted_query, settings.mistral_api_key)

    try:
        chat_repo.insert_turn(session_id, query, response)
    except Exception as e:
        logger.error("failed_to_store_chat", session_id=session_id, error=str(e))

    return ChatResponse(response=response, session_id=session_id)
