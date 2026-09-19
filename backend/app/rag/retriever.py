"""Corpus-scoped Qdrant retrieval with a score threshold — replaces the
Chroma-based retriever that always returned the top-3 chunks regardless of
relevance (D031) and had no way to scope a query to one corpus (D035).
"""

from dataclasses import dataclass

from qdrant_client import QdrantClient
from qdrant_client.models import FieldCondition, Filter, MatchValue

from app.corpora.registry import Corpus
from app.rag.embeddings import embed_query

DEFAULT_SCORE_THRESHOLD = 0.5
DEFAULT_K = 3


@dataclass(frozen=True)
class RetrievedChunk:
    text: str
    act: str
    section: str
    section_title: str
    page: int
    score: float
    ingest_version: str


def retrieve(
    qdrant: QdrantClient,
    corpus: Corpus,
    query: str,
    *,
    k: int = DEFAULT_K,
    score_threshold: float = DEFAULT_SCORE_THRESHOLD,
) -> list[RetrievedChunk]:
    vector = embed_query(query)
    results = qdrant.query_points(
        collection_name=corpus.collection,
        query=vector,
        query_filter=Filter(
            must=[FieldCondition(key="corpus", match=MatchValue(value=corpus.id))]
        ),
        limit=k,
        score_threshold=score_threshold,
    ).points
    return [
        RetrievedChunk(
            text=p.payload["text"],
            act=p.payload["act"],
            section=p.payload["section"],
            section_title=p.payload["section_title"],
            page=p.payload["page"],
            score=p.score,
            ingest_version=p.payload["ingest_version"],
        )
        for p in results
        if p.payload is not None
    ]
