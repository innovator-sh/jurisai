from dataclasses import dataclass


@dataclass(frozen=True)
class RawSection:
    """The common shape every loader produces, regardless of source format —
    `rag/chunking.py`'s `chunk_sections()` only ever sees this, never a
    format's raw markup."""

    number: str
    title: str
    text: str
    page: int
