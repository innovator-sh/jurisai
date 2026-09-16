"""Ported from jurisai/Backend/app.py (`/chat`, `get_answer`).

Now requires auth and scopes storage by user_id (D004-D008, closed) and rate
limits per user (D015, closed). Still open, tracked for Sprint 3:
- D024: raw `Document` reprs interpolated into the prompt.
- D025: a Mistral error string gets stored and returned as if it were the
  answer, instead of a typed error.
- D029: a Mongo write failure is silently swallowed.
"""

import uuid

from fastapi import APIRouter, HTTPException, Request

from app.core.logging import get_logger
from app.core.rate_limit import limiter
from app.core.security import CurrentUser
from app.deps import ChatRepositoryDep, SettingsDep, VectorStoreDep
from app.llm.mistral_client import query_mistral
from app.models.chat import ChatRequest, ChatResponse
from app.rag.retriever import retrieve_context

router = APIRouter()
logger = get_logger(__name__)


@router.post("/chat", response_model=ChatResponse)
@limiter.limit("20/minute")
def chat(
    request: Request,
    body: ChatRequest,
    user: CurrentUser,
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
        chat_repo.insert_turn(user.id, session_id, query, response)
    except Exception as e:
        logger.error("failed_to_store_chat", session_id=session_id, error=str(e))

    return ChatResponse(response=response, session_id=session_id)
