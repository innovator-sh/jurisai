"""Versioned prompt templates. Restructured from the legacy single f-string
(D024) into a system message (instructions), a separate context block
(retrieved chunks, labelled by corpus and citation), and the user question
last — the shape the plan calls for, and what makes prompt caching on the
context block possible once a provider that supports it is wired in.
"""

from app.corpora.crosswalk import Crosswalk, CrosswalkRow
from app.corpora.registry import Corpus
from app.rag.retriever import RetrievedChunk

PROMPT_VERSION = "v1"

_SYSTEM_TEMPLATE = """You are JurisAI, a legal information assistant for Indian criminal law.

Answer ONLY using the {act} excerpts provided below. Do not use outside knowledge.
Every statement must cite its section number, e.g. "(Section 302, {short})".
If the provided excerpts do not answer the question, say so plainly rather than guessing.
For any cross-reference to another act's section, use only the VERIFIED
CORRESPONDENCE section below — never infer one from the excerpts alone.

This is legal information, not legal advice — always end your answer by recommending \
the user consult a qualified lawyer for their specific situation."""

_HYBRID_SYSTEM_TEMPLATE = """You are JurisAI, a legal information assistant for Indian criminal law.

The excerpts below come from more than one statute, labelled by act. {primary_short} \
({primary_act}) is the CURRENT law; {other_shorts} no longer applies to offences committed \
on or after 1 July 2024 but still governs offences committed before that date.

Answer ONLY using the excerpts provided. Do not use outside knowledge. Structure your answer as:
1. The current position under {primary_short}, with its section number.
2. The corresponding provision(s) under the earlier act(s), with their section numbers, using
ONLY the VERIFIED CORRESPONDENCE section below — never infer or guess a correspondence from
the excerpts themselves.
3. If the VERIFIED CORRESPONDENCE section states a provision is new, or has no successor, say
so explicitly rather than implying continuity.

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


def collect_crosswalk_facts(
    crosswalk: Crosswalk, chunks_by_corpus: dict[str, list[RetrievedChunk]]
) -> list[CrosswalkRow]:
    """One entry per distinct crosswalk row touched by anything actually
    retrieved this turn, deduped — the same row is reachable from every IPC
    section in a merged group (e.g. BNS 178 is `lookup`-able from both IPC
    231 and IPC 232), and would otherwise repeat in the prompt."""
    seen: dict[tuple[str, tuple[str, ...]], CrosswalkRow] = {}
    for corpus_id, chunks in chunks_by_corpus.items():
        sections = {c.section for c in chunks}
        for section in sections:
            for row in crosswalk.lookup(corpus_id, section):
                key = (row.bns_section, tuple(row.ipc_sections))
                seen.setdefault(key, row)
    return list(seen.values())


def build_crosswalk_block(rows: list[CrosswalkRow]) -> str:
    if not rows:
        return "(No verified correspondence found for the retrieved sections.)"
    lines = []
    for row in rows:
        if row.bns_section and row.ipc_sections:
            ipc_list = ", ".join(row.ipc_sections)
            line = (
                f"BNS {row.bns_section} <-> IPC {ipc_list} "
                f"({row.relation}) -- {row.bns_title}"
            )
        elif row.bns_section:
            line = (
                f"BNS {row.bns_section} is a NEW provision with no IPC "
                f"predecessor -- {row.bns_title}"
            )
        else:
            ipc_list = ", ".join(row.ipc_sections)
            ipc_title_list = ", ".join(row.ipc_titles)
            line = (
                f"IPC {ipc_list} has no established BNS successor "
                f"({row.relation}) -- {ipc_title_list}"
            )
        if row.notes:
            line += f" (note: {row.notes})"
        lines.append(line)
    return "\n".join(lines)
