"""Builds one corpus's Qdrant collection from its source PDF(s).

Replaces the legacy import-time ingestion entirely (D017) — this runs as a
standalone CLI (`scripts/ingest.py --corpus ipc`), never as part of app
startup. The app connects to an existing collection and fails readiness if
a declared, enabled corpus's collection is missing, rather than building
the index itself on every restart.
"""

import argparse
import sys
import time
from pathlib import Path

from pypdf import PdfReader
from qdrant_client import QdrantClient
from qdrant_client.models import Distance, PointStruct, VectorParams

from app.core.logging import get_logger
from app.corpora.loaders import bns_bare_act, ipc_commentary
from app.corpora.registry import Corpus, load_registry
from app.rag.chunking import chunk_sections
from app.rag.embeddings import VECTOR_SIZE, embed_texts

logger = get_logger(__name__)

# Dispatched by the registry's `loader` field — see corpora/definitions.yaml
# and corpora/loaders/__init__.py for why each corpus needs its own.
LOADERS = {
    "ipc_commentary": ipc_commentary.extract_sections,
    "bns_bare_act": bns_bare_act.extract_sections,
}


def _load_pdf_pages(pdf_path: Path) -> list[str]:
    reader = PdfReader(str(pdf_path))
    return [page.extract_text() for page in reader.pages]


def ingest_corpus(corpus: Corpus, qdrant: QdrantClient) -> dict[str, object]:
    source_dir = Path(corpus.source)
    pdfs = sorted(source_dir.glob("*.pdf"))
    if not pdfs:
        raise FileNotFoundError(f"No PDFs found in {source_dir} for corpus {corpus.id!r}")

    try:
        extract_sections = LOADERS[corpus.loader]
    except KeyError as e:
        raise ValueError(
            f"Corpus {corpus.id!r} declares loader {corpus.loader!r}, which isn't "
            f"registered in rag/ingest.py's LOADERS dict"
        ) from e

    ingest_version = time.strftime("%Y%m%dT%H%M%SZ", time.gmtime())
    all_chunks = []
    total_skipped: list[str] = []
    for pdf_path in pdfs:
        logger.info("parsing_pdf", path=str(pdf_path))
        pages = _load_pdf_pages(pdf_path)
        sections, skipped = extract_sections(pages)
        total_skipped.extend(skipped)
        chunks = chunk_sections(
            sections,
            corpus=corpus.id,
            act=corpus.act,
            source_doc=pdf_path.name,
            ingest_version=ingest_version,
        )
        all_chunks.extend(chunks)

    if not all_chunks:
        raise ValueError(f"No chunks produced for corpus {corpus.id!r} — refusing to index empty")

    logger.info("embedding_chunks", count=len(all_chunks))
    vectors = embed_texts([c.text for c in all_chunks])

    if qdrant.collection_exists(corpus.collection):
        qdrant.delete_collection(corpus.collection)
    qdrant.create_collection(
        corpus.collection,
        vectors_config=VectorParams(size=VECTOR_SIZE, distance=Distance.COSINE),
    )

    points = [
        PointStruct(
            id=i,
            vector=vector,
            payload={
                "text": chunk.text,
                "corpus": chunk.corpus,
                "act": chunk.act,
                "section": chunk.section,
                "section_title": chunk.section_title,
                "page": chunk.page,
                "in_force_from": corpus.in_force_from.isoformat(),
                "in_force_to": corpus.in_force_to.isoformat() if corpus.in_force_to else None,
                "source_doc": chunk.source_doc,
                "ingest_version": chunk.ingest_version,
            },
        )
        for i, (chunk, vector) in enumerate(zip(all_chunks, vectors, strict=True))
    ]
    qdrant.upsert(corpus.collection, points=points)

    logger.info(
        "ingest_complete",
        corpus=corpus.id,
        chunks=len(points),
        skipped_sections=total_skipped,
        ingest_version=ingest_version,
    )
    return {
        "corpus": corpus.id,
        "chunk_count": len(points),
        "skipped_sections": total_skipped,
        "ingest_version": ingest_version,
    }


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Build a corpus's Qdrant index from its source PDF(s)."
    )
    parser.add_argument("--corpus", required=True, help="Corpus id from corpora/definitions.yaml")
    parser.add_argument("--qdrant-url", default="http://localhost:6333")
    args = parser.parse_args()

    registry = load_registry()
    try:
        corpus = registry.get(args.corpus)
    except KeyError as e:
        print(f"error: {e}", file=sys.stderr)
        sys.exit(1)

    qdrant = QdrantClient(url=args.qdrant_url)
    result = ingest_corpus(corpus, qdrant)
    print(f"Ingested {result['chunk_count']} chunks for corpus '{result['corpus']}'.")
    if result["skipped_sections"]:
        print(
            f"Skipped (parser low-confidence, see corpora/loaders/): "
            f"{result['skipped_sections']}"
        )


if __name__ == "__main__":
    main()
