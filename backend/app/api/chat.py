"""Ported from jurisai/Backend/app.py (`/chat`, `get_answer`), rebuilt on
top of Sprint 3's corpus registry, Qdrant retriever, and LLMProvider.

Closes this sprint:
- D024: chunk text is formatted directly, not a raw Document repr.
- D025: a provider failure raises LLMError -> 502, never gets stored or
  returned as if it were a legal answer.
- D031: a score threshold means "I don't have that in the {act}" instead of
  always returning the top-k regardless of relevance.
- D034/D035/D036/D037/D040: corpus is resolved through the registry, chunks
  carry act/section metadata, the prompt names the act, sessions carry
  corpus + ingest_version.

Still open, Sprint 4: D014 (exception detail reaches the client), D029
(chat-persistence failure is only logged, not surfaced).
"""

import uuid

from fastapi import APIRouter, HTTPException, Request

from app.core.logging import get_logger
from app.core.rate_limit import limiter
from app.core.security import CurrentUser
from app.deps import ChatRepositoryDep, CorpusRegistryDep, LLMProviderDep, QdrantDep, SettingsDep
from app.llm.base import LLMError
from app.models.chat import ChatRequest, ChatResponse
from app.rag.prompts import build_context_block, build_system_prompt, build_user_message
from app.rag.retriever import retrieve
from app.rag.router import resolve_corpus

router = APIRouter()
logger = get_logger(__name__)


@router.post("/chat", response_model=ChatResponse)
@limiter.limit("20/minute")
async def chat(
    request: Request,
    body: ChatRequest,
    user: CurrentUser,
    qdrant: QdrantDep,
    registry: CorpusRegistryDep,
    llm: LLMProviderDep,
    chat_repo: ChatRepositoryDep,
    settings: SettingsDep,
) -> ChatResponse:
    session_id = body.session_id or ""
    if not session_id or session_id == "None":
        session_id = str(uuid.uuid4())
    query = body.query.strip()
    if not query:
        raise HTTPException(status_code=400, detail="No query provided")

    routing = resolve_corpus(
        registry, query, explicit_selection=body.corpus_mode, offence_date=body.offence_date
    )
    if routing.corpus is None:
        raise HTTPException(status_code=422, detail=routing.reason or "Could not resolve a corpus")
    corpus = routing.corpus

    chunks = retrieve(
        qdrant,
        corpus,
        query,
        k=settings.retrieval_k,
        score_threshold=settings.retrieval_score_threshold,
    )
    if not chunks:
        answer = f"I don't have that in the {corpus.act}."
        ingest_version = "n/a"
    else:
        system_prompt = build_system_prompt(corpus.act, corpus.short)
        context_block = build_context_block(chunks)
        user_message = f"Context:\n{context_block}\n\nQuestion: {build_user_message(query)}"
        try:
            answer = await llm.complete(system_prompt, user_message)
        except LLMError as e:
            logger.error("llm_provider_failed", error=str(e))
            raise HTTPException(status_code=502, detail="The answer service is unavailable") from e
        ingest_version = chunks[0].ingest_version

    try:
        chat_repo.insert_turn(
            user.id, session_id, query, answer, corpus=corpus.id, ingest_version=ingest_version
        )
    except Exception as e:
        logger.error("failed_to_store_chat", session_id=session_id, error=str(e))

    return ChatResponse(response=answer, session_id=session_id, corpus=corpus.id, act=corpus.act)
