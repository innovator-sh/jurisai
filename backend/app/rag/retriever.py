"""Ported from jurisai/Backend/app.py (`get_answer`'s retrieval step), relocated
only. Deliberately still returns raw `Document` objects, not formatted text —
the caller interpolates them the same way legacy did. That's D024 (raw repr
reaching the prompt), tracked open for Sprint 3 along with the rest of the
prompt-construction rework; fixing it here would bundle an answer-quality
change into a sprint that's supposed to be a pure structural move.
No score threshold, no corpus scoping, fixed k=3 — also open, also Sprint 3.
"""

from langchain_community.vectorstores import Chroma
from langchain_core.documents import Document


def retrieve_context(vector_store: Chroma, query: str, k: int = 3) -> list[Document]:
    return vector_store.similarity_search(query, k=k)
