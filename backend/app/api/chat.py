"""Ported from jurisai/Backend/app.py (`/chat`, `get_answer`), rebuilt on
top of the corpus registry, Qdrant retriever, LLMProvider, and — as of
Sprint 3B — hybrid retrieval across both ipc and bns.

Closes from Sprint 3: D024, D025, D031, D034/D035/D036/D037/D040 (see that
sprint's docs/decisions.md entry). Sprint 3B additionally wires the router's
hybrid default (previously unreachable — Sprint 3 only ever had one corpus
enabled) into an actual multi-corpus retrieval + answer contract.

D014 closed Sprint 4 (core/errors.py's global handlers, not a per-route fix
— this route never built its own error response to begin with).
D029 closed: a persistence failure still doesn't fail the request (the LLM
call already succeeded — that answer shouldn't be wasted for a Mongo write
error) or get folded into the answer text, but ChatResponse.persisted now
tells the caller honestly whether the turn was actually saved.
"""

import uuid

from fastapi import APIRouter, HTTPException, Request

from app.core.logging import get_logger
from app.core.rate_limit import limiter
from app.core.security import CurrentUser
from app.deps import (
    ChatRepositoryDep,
    CorpusRegistryDep,
    CrosswalkDep,
    LLMProviderDep,
    QdrantDep,
    SettingsDep,
)
from app.llm.base import LLMError
from app.models.chat import ChatRequest, ChatResponse, CrosswalkFact
from app.rag.prompts import (
    build_context_block,
    build_crosswalk_block,
    build_hybrid_context,
    build_hybrid_system_prompt,
    build_system_prompt,
    build_user_message,
    collect_crosswalk_facts,
)
from app.rag.retriever import RetrievedChunk, retrieve
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
    crosswalk: CrosswalkDep,
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
    if not routing.corpora:
        raise HTTPException(status_code=422, detail=routing.reason or "Could not resolve a corpus")

    chunks_by_corpus: dict[str, list[RetrievedChunk]] = {
        c.id: retrieve(
            qdrant,
            c,
            query,
            k=settings.retrieval_k,
            score_threshold=settings.retrieval_score_threshold,
        )
        for c in routing.corpora
    }
    all_chunks = [ch for chunks in chunks_by_corpus.values() for ch in chunks]
    acts = [c.act for c in routing.corpora]
    response_corpus_id = "hybrid" if routing.is_hybrid else routing.corpora[0].id

    crosswalk_facts: list[CrosswalkFact] = []
    if not all_chunks:
        answer = f"I don't have that in the {' or '.join(acts)}."
        ingest_version = "n/a"
    else:
        crosswalk_rows = collect_crosswalk_facts(crosswalk, chunks_by_corpus)
        crosswalk_facts = [
            CrosswalkFact(
                bns_section=r.bns_section,
                bns_title=r.bns_title,
                ipc_sections=r.ipc_sections,
                ipc_titles=r.ipc_titles,
                relation=r.relation,
                notes=r.notes,
            )
            for r in crosswalk_rows
        ]
        crosswalk_block = build_crosswalk_block(crosswalk_rows)
        if routing.is_hybrid:
            system_prompt = build_hybrid_system_prompt(routing.corpora)
            context_block = build_hybrid_context(chunks_by_corpus)
        else:
            corpus = routing.corpora[0]
            system_prompt = build_system_prompt(corpus.act, corpus.short)
            context_block = build_context_block(all_chunks)
        user_message = (
            f"Context:\n{context_block}\n\n"
            f"VERIFIED CORRESPONDENCE (human-reviewed):\n{crosswalk_block}\n\n"
            f"Question: {build_user_message(query)}"
        )
        try:
            answer = await llm.complete(system_prompt, user_message)
        except LLMError as e:
            logger.error("llm_provider_failed", error=str(e))
            raise HTTPException(status_code=502, detail="The answer service is unavailable") from e
        ingest_version = all_chunks[0].ingest_version

    persisted = True
    try:
        chat_repo.insert_turn(
            user.id,
            session_id,
            query,
            answer,
            corpus=response_corpus_id,
            ingest_version=ingest_version,
        )
    except Exception as e:
        logger.error("failed_to_store_chat", session_id=session_id, error=str(e))
        persisted = False

    return ChatResponse(
        response=answer,
        session_id=session_id,
        corpus=response_corpus_id,
        acts=acts,
        crosswalk=crosswalk_facts,
        persisted=persisted,
    )
