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

Sprint 5: `body.stream=true` switches to an SSE response (`_stream_chat`)
instead of the single ChatResponse JSON body, for the rebuilt frontend's
streamed chat UI. Retrieval, corpus routing, and crosswalk-grounding stay
identical between the two paths — only how the answer and its metadata
reach the client differs. Three SSE event types, in order: `crosswalk`
(known before generation, from retrieval), `token` (one per chunk from
llm.stream()), `done` (after the Mongo write, carrying the same
session_id/persisted info ChatResponse.persisted already carries). A
provider failure mid-stream can't become an HTTPException (headers are
already sent), so it becomes an `error` event instead.
"""

import json
import uuid
from collections.abc import AsyncIterator

from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import StreamingResponse

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
from app.llm.base import LLMError, LLMProvider
from app.models.chat import ChatRequest, ChatResponse, CrosswalkFact
from app.rag.prompts import (
    build_context_block,
    build_crosswalk_block,
    build_hybrid_context,
    build_hybrid_system_prompt,
    build_reformulation_prompt,
    build_system_prompt,
    build_user_message,
    collect_crosswalk_facts,
)
from app.rag.retriever import RetrievedChunk, retrieve
from app.rag.router import resolve_corpus
from app.repositories.chat_repository import ChatRepository

router = APIRouter()
logger = get_logger(__name__)


def _sse(event: str, data: str) -> str:
    return f"event: {event}\ndata: {data}\n\n"


async def _reformulate_for_retrieval(llm: LLMProvider, query: str) -> str | None:
    """Fallback only -- called once, only when the first retrieval pass
    across every routed corpus comes back empty. A free-text narrative
    ("he said his sister needed eye surgery...") embeds poorly against
    formal statute text; rewritten into legal-concept terms it retrieves
    correctly (confirmed directly against the real index: ~0.50/wrong
    section on the raw narrative vs. ~0.69/correct section reformulated).
    Never raises -- a reformulation failure just means the original
    "I don't have that" behaviour stands, not a broken request."""
    system, user = build_reformulation_prompt(query)
    try:
        result = await llm.complete(system, user)
    except LLMError as e:
        logger.warning("query_reformulation_failed", error=str(e))
        return None
    result = result.strip()
    return result or None


async def _stream_chat(
    *,
    llm: LLMProvider,
    chat_repo: ChatRepository,
    user_id: str,
    session_id: str,
    query: str,
    crosswalk_facts: list[CrosswalkFact],
    system_prompt: str,
    user_message: str,
    has_chunks: bool,
    no_answer: str,
    response_corpus_id: str,
    ingest_version: str,
) -> AsyncIterator[str]:
    yield _sse("crosswalk", json.dumps([f.model_dump() for f in crosswalk_facts]))

    answer_parts: list[str] = []
    if not has_chunks:
        answer_parts.append(no_answer)
        yield _sse("token", json.dumps(no_answer))
    else:
        try:
            async for chunk in llm.stream(system_prompt, user_message):
                answer_parts.append(chunk)
                yield _sse("token", json.dumps(chunk))
        except LLMError as e:
            logger.error("llm_provider_failed", error=str(e))
            yield _sse("error", json.dumps({"detail": "The answer service is unavailable"}))
            return

    answer = "".join(answer_parts)
    persisted = True
    try:
        chat_repo.insert_turn(
            user_id,
            session_id,
            query,
            answer,
            corpus=response_corpus_id,
            ingest_version=ingest_version,
        )
    except Exception as e:
        logger.error("failed_to_store_chat", session_id=session_id, error=str(e))
        persisted = False

    yield _sse("done", json.dumps({"session_id": session_id, "persisted": persisted}))


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
) -> ChatResponse | StreamingResponse:
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

    def _retrieve_all(q: str) -> dict[str, list[RetrievedChunk]]:
        return {
            c.id: retrieve(
                qdrant,
                c,
                q,
                k=settings.retrieval_k,
                score_threshold=settings.retrieval_score_threshold,
            )
            for c in routing.corpora
        }

    chunks_by_corpus = _retrieve_all(query)
    all_chunks = [ch for chunks in chunks_by_corpus.values() for ch in chunks]

    if not all_chunks:
        # A fact-pattern narrative embeds poorly against formal statute
        # text (D066) -- retry once against a retrieval-only rewrite before
        # giving up. Never shown to the user, never used for the answer.
        reformulated = await _reformulate_for_retrieval(llm, query)
        if reformulated:
            chunks_by_corpus = _retrieve_all(reformulated)
            all_chunks = [ch for chunks in chunks_by_corpus.values() for ch in chunks]

    acts = [c.act for c in routing.corpora]
    response_corpus_id = "hybrid" if routing.is_hybrid else routing.corpora[0].id
    no_answer = f"I don't have that in the {' or '.join(acts)}."
    ingest_version = all_chunks[0].ingest_version if all_chunks else "n/a"

    crosswalk_facts: list[CrosswalkFact] = []
    system_prompt = ""
    user_message = ""
    if all_chunks:
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

    if body.stream:
        return StreamingResponse(
            _stream_chat(
                llm=llm,
                chat_repo=chat_repo,
                user_id=user.id,
                session_id=session_id,
                query=query,
                crosswalk_facts=crosswalk_facts,
                system_prompt=system_prompt,
                user_message=user_message,
                has_chunks=bool(all_chunks),
                no_answer=no_answer,
                response_corpus_id=response_corpus_id,
                ingest_version=ingest_version,
            ),
            media_type="text/event-stream",
        )

    if not all_chunks:
        answer = no_answer
    else:
        try:
            answer = await llm.complete(system_prompt, user_message)
        except LLMError as e:
            logger.error("llm_provider_failed", error=str(e))
            raise HTTPException(status_code=502, detail="The answer service is unavailable") from e

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
