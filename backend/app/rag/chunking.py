"""Format-agnostic chunk sub-splitting. Every loader in `corpora/loaders/`
produces the same `RawSection` shape regardless of source format; this is
the one place that turns those into `Chunk`s, so both corpora share one
chunking strategy from day one (per-format differences live entirely in
the loaders, not here).
"""

from dataclasses import dataclass

from app.corpora.loaders.base import RawSection

MAX_CHUNK_CHARS = 1500


@dataclass(frozen=True)
class Chunk:
    text: str
    corpus: str
    act: str
    section: str
    section_title: str
    page: int
    source_doc: str
    ingest_version: str


def chunk_sections(
    sections: list[RawSection], *, corpus: str, act: str, source_doc: str, ingest_version: str
) -> list[Chunk]:
    """One chunk per section where it fits; long sections are sub-split with
    the heading repeated in each part, per the plan's chunking design."""
    chunks = []
    for section in sections:
        if len(section.text) <= MAX_CHUNK_CHARS:
            parts = [section.text]
        else:
            parts = [
                section.text[i : i + MAX_CHUNK_CHARS]
                for i in range(0, len(section.text), MAX_CHUNK_CHARS)
            ]
        for part in parts:
            heading = f"Section {section.number} — {section.title}. "
            chunks.append(
                Chunk(
                    text=heading + part,
                    corpus=corpus,
                    act=act,
                    section=section.number,
                    section_title=section.title,
                    page=section.page,
                    source_doc=source_doc,
                    ingest_version=ingest_version,
                )
            )
    return chunks
