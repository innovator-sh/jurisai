"""Retrieval-hit-rate eval harness (item 10). Self-contained: ingests into an
in-memory Qdrant client rather than requiring a live service, so it can run
in CI as a non-blocking report without needing docker-compose services.

Parameterised by corpus from the start — `run_eval(corpus_id, questions_path)`
takes both, so Sprint 3B adds a `bns_questions.yaml` and calls this the same
way rather than writing a second harness.
"""

from pathlib import Path
from typing import Any

import yaml
from qdrant_client import QdrantClient

from app.corpora.registry import load_registry
from app.rag.ingest import ingest_corpus
from app.rag.retriever import DEFAULT_K, DEFAULT_SCORE_THRESHOLD, retrieve


def run_eval(corpus_id: str, questions_path: Path) -> dict[str, Any]:
    registry = load_registry()
    corpus = registry.get(corpus_id)

    with open(questions_path, encoding="utf-8") as f:
        questions = yaml.safe_load(f)["questions"]

    qdrant = QdrantClient(":memory:")
    ingest_result = ingest_corpus(corpus, qdrant)

    hits = 0
    results = []
    for q in questions:
        chunks = retrieve(
            qdrant, corpus, q["query"], k=DEFAULT_K, score_threshold=DEFAULT_SCORE_THRESHOLD
        )
        retrieved_sections = [c.section for c in chunks]
        hit = q["expected_section"] in retrieved_sections
        hits += hit
        results.append(
            {
                "query": q["query"],
                "expected": q["expected_section"],
                "retrieved": retrieved_sections,
                "hit": hit,
            }
        )

    return {
        "corpus": corpus_id,
        "chunk_count": ingest_result["chunk_count"],
        "skipped_sections": ingest_result["skipped_sections"],
        "question_count": len(questions),
        "hits": hits,
        "hit_rate": hits / len(questions) if questions else 0.0,
        "results": results,
    }
