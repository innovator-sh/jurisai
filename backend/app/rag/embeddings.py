"""Direct sentence-transformers usage — no LangChain wrapper.

Still `multi-qa-mpnet-base-dot-v1` (English-only dense embeddings). The
BGE-M3 hybrid dense+sparse swap (D056, D057 — multilingual + exact
section-number lexical matching) is a deliberately separate, larger piece
of work: it needs a ~2GB model download, the `FlagEmbedding` package for
its sparse output, and Qdrant's sparse-vector API, none of which this
sprint's time budget covers testing properly. Tracked open, not silently
dropped.
"""

from functools import lru_cache

from sentence_transformers import SentenceTransformer

MODEL_NAME = "multi-qa-mpnet-base-dot-v1"
VECTOR_SIZE = 768


@lru_cache(maxsize=1)
def get_embedder() -> SentenceTransformer:
    return SentenceTransformer(MODEL_NAME)


def embed_texts(texts: list[str]) -> list[list[float]]:
    embeddings = get_embedder().encode(texts, show_progress_bar=False)
    return [e.tolist() for e in embeddings]


def embed_query(text: str) -> list[float]:
    return embed_texts([text])[0]
