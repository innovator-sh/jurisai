"""Loads `data/crosswalk/ipc_bns.csv` for bidirectional IPC<->BNS lookup.

This module trusts whatever the CSV says — it does not re-derive or verify
mappings. The CSV itself is the reviewed artefact: `scripts/build_crosswalk.py`
produces a draft with every row marked `confidence=unreviewed`; a human
updates that column row-by-row during review (see that script's docstring
for exactly what it does and doesn't verify). Nothing here decides whether
a row is trustworthy — it's a lookup table, not a review gate.
"""

import csv
from dataclasses import dataclass
from pathlib import Path

DEFAULT_CSV_PATH = Path(__file__).parent.parent.parent.parent / "data" / "crosswalk" / "ipc_bns.csv"


@dataclass(frozen=True)
class CrosswalkRow:
    bns_section: str
    bns_title: str
    ipc_sections: list[str]  # empty for a "new" BNS section with no IPC ancestor
    ipc_titles: list[str]
    relation: str  # new | renumbered | merged | repealed_candidate | ...
    confidence: str  # "unreviewed" until a human updates it
    source: str
    notes: str


class Crosswalk:
    def __init__(self, rows: list[CrosswalkRow]) -> None:
        self._by_bns: dict[str, list[CrosswalkRow]] = {}
        self._by_ipc: dict[str, list[CrosswalkRow]] = {}
        for row in rows:
            if row.bns_section:
                self._by_bns.setdefault(row.bns_section, []).append(row)
            for ipc_section in row.ipc_sections:
                self._by_ipc.setdefault(ipc_section, []).append(row)

    def from_bns(self, section: str) -> list[CrosswalkRow]:
        return self._by_bns.get(section, [])

    def from_ipc(self, section: str) -> list[CrosswalkRow]:
        return self._by_ipc.get(section, [])

    def lookup(self, corpus_id: str, section: str) -> list[CrosswalkRow]:
        """corpus_id is one of the two ids this crosswalk is inherently
        about -- this module's whole purpose is the ipc<->bns mapping, so
        (unlike route code, which never names a corpus literally -- see
        corpora/registry.py) it's the one legitimate place for those two
        literals to live."""
        if corpus_id == "ipc":
            return self.from_ipc(section)
        if corpus_id == "bns":
            return self.from_bns(section)
        return []


def load_crosswalk(path: Path = DEFAULT_CSV_PATH) -> Crosswalk:
    if not path.exists():
        return Crosswalk([])
    rows = []
    with open(path, encoding="utf-8") as f:
        for raw in csv.DictReader(f):
            rows.append(
                CrosswalkRow(
                    bns_section=raw["bns_section"],
                    bns_title=raw["bns_title"],
                    ipc_sections=[s for s in raw["ipc_section"].split(";") if s],
                    ipc_titles=[t for t in raw["ipc_title"].split(";") if t],
                    relation=raw["relation"],
                    confidence=raw["confidence"],
                    source=raw["source"],
                    notes=raw["notes"],
                )
            )
    return Crosswalk(rows)
