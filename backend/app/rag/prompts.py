"""Versioned prompt templates. Restructured from the legacy single f-string
(D024) into a system message (instructions), a separate context block
(retrieved chunks, labelled by corpus and citation), and the user question
last — the shape the plan calls for, and what makes prompt caching on the
context block possible once a provider that supports it is wired in.

`build_hybrid_context` exists now so Sprint 3B (BNS) has a seam to land in;
today it's only ever called with one corpus's chunks.
"""

from app.rag.retriever import RetrievedChunk

PROMPT_VERSION = "v1"

_SYSTEM_TEMPLATE = """You are JurisAI, a legal information assistant for Indian criminal law.

Answer ONLY using the {act} excerpts provided below. Do not use outside knowledge.
Every statement must cite its section number, e.g. "(Section 302, {short})".
If the provided excerpts do not answer the question, say so plainly rather than guessing.

This is legal information, not legal advice — always end your answer by recommending \
the user consult a qualified lawyer for their specific situation."""


def build_system_prompt(act: str, short: str) -> str:
    return _SYSTEM_TEMPLATE.format(act=act, short=short)


def build_context_block(chunks: list[RetrievedChunk]) -> str:
    if not chunks:
        return "(No relevant sections found.)"
    parts = []
    for c in chunks:
        parts.append(f"[Section {c.section} — {c.section_title}, page {c.page}]\n{c.text}")
    return "\n\n".join(parts)


def build_hybrid_context(chunks_by_corpus: dict[str, list[RetrievedChunk]]) -> str:
    """Sprint 3B seam — labels each block by corpus once more than one is live."""
    parts = []
    for corpus_id, chunks in chunks_by_corpus.items():
        parts.append(f"=== {corpus_id.upper()} ===\n{build_context_block(chunks)}")
    return "\n\n".join(parts)


def build_user_message(query: str) -> str:
    return query.strip()
