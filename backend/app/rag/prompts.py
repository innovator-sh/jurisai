"""Versioned prompt templates. Restructured from the legacy single f-string
(D024) into a system message (instructions), a separate context block
(retrieved chunks, labelled by corpus and citation), and the user question
last — the shape the plan calls for, and what makes prompt caching on the
context block possible once a provider that supports it is wired in.
"""

from app.corpora.registry import Corpus
from app.rag.retriever import RetrievedChunk

PROMPT_VERSION = "v1"

_SYSTEM_TEMPLATE = """You are JurisAI, a legal information assistant for Indian criminal law.

Answer ONLY using the {act} excerpts provided below. Do not use outside knowledge.
Every statement must cite its section number, e.g. "(Section 302, {short})".
If the provided excerpts do not answer the question, say so plainly rather than guessing.

This is legal information, not legal advice — always end your answer by recommending \
the user consult a qualified lawyer for their specific situation."""

_HYBRID_SYSTEM_TEMPLATE = """You are JurisAI, a legal information assistant for Indian criminal law.

The excerpts below come from more than one statute, labelled by act. {primary_short} \
({primary_act}) is the CURRENT law; {other_shorts} no longer applies to offences committed \
on or after 1 July 2024 but still governs offences committed before that date.

Answer ONLY using the excerpts provided. Do not use outside knowledge. Structure your answer as:
1. The current position under {primary_short}, with its section number.
2. The corresponding provision(s) under the earlier act(s), with their section numbers, if the \
excerpts show one — do not guess a correspondence that isn't in the excerpts.
3. If the excerpts indicate the provision was newly introduced, or its wording changed, say so \
explicitly rather than implying continuity.

Never state a section number without naming its act. If the excerpts don't answer the question, \
say so plainly rather than guessing.

This is legal information, not legal advice — always end your answer by recommending \
the user consult a qualified lawyer for their specific situation."""


def build_system_prompt(act: str, short: str) -> str:
    return _SYSTEM_TEMPLATE.format(act=act, short=short)


def build_hybrid_system_prompt(corpora: list[Corpus]) -> str:
    """`corpora` must already be primary-first (see router.py's
    `_ordered_for_hybrid`) — this doesn't re-derive which one is current."""
    primary, *others = corpora
    other_shorts = " and ".join(c.short for c in others)
    return _HYBRID_SYSTEM_TEMPLATE.format(
        primary_short=primary.short, primary_act=primary.act, other_shorts=other_shorts
    )


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
