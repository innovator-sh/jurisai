"""The corpus registry — the single source of truth for which statutes exist.

No route, prompt, or retriever should ever hardcode a corpus id like "ipc" or
"bns"; everything resolves through `Corpus` objects loaded here from
`definitions.yaml`. Adding BNSS or BSA later is a YAML entry, not a code change.
"""

from dataclasses import dataclass
from datetime import date
from pathlib import Path
from typing import Any

import yaml

DEFINITIONS_PATH = Path(__file__).parent / "definitions.yaml"


@dataclass(frozen=True)
class Corpus:
    id: str
    act: str
    short: str
    jurisdiction: str
    in_force_from: date
    in_force_to: date | None
    source: str
    collection: str
    enabled: bool
    superseded_by: str | None = None
    supersedes: str | None = None

    def covers(self, offence_date: date) -> bool:
        if offence_date < self.in_force_from:
            return False
        return self.in_force_to is None or offence_date <= self.in_force_to


class CorpusRegistry:
    def __init__(self, corpora: list[Corpus]) -> None:
        self._by_id = {c.id: c for c in corpora}

    def get(self, corpus_id: str) -> Corpus:
        try:
            return self._by_id[corpus_id]
        except KeyError as e:
            raise KeyError(f"Unknown corpus id: {corpus_id!r}") from e

    def all(self) -> list[Corpus]:
        return list(self._by_id.values())

    def enabled(self) -> list[Corpus]:
        return [c for c in self._by_id.values() if c.enabled]

    def for_offence_date(self, offence_date: date) -> Corpus | None:
        """The enabled corpus whose in-force window covers this date, if any."""
        for corpus in self.enabled():
            if corpus.covers(offence_date):
                return corpus
        return None


def _parse_corpus(raw: dict[str, Any]) -> Corpus:
    return Corpus(
        id=raw["id"],
        act=raw["act"],
        short=raw["short"],
        jurisdiction=raw["jurisdiction"],
        in_force_from=raw["in_force_from"],
        in_force_to=raw.get("in_force_to"),
        source=raw["source"],
        collection=raw["collection"],
        enabled=raw["enabled"],
        superseded_by=raw.get("superseded_by"),
        supersedes=raw.get("supersedes"),
    )


def load_registry(path: Path = DEFINITIONS_PATH) -> CorpusRegistry:
    with open(path, encoding="utf-8") as f:
        raw = yaml.safe_load(f)
    corpora = [_parse_corpus(c) for c in raw["corpora"]]
    return CorpusRegistry(corpora)
