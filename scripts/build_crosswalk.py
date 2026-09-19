#!/usr/bin/env python
"""Builds a DRAFT IPC<->BNS crosswalk from NCRB's official "Corresponding
Section Table" (embedded in the same PDF as the BNS bare-act text).

This produces a starting point for human review, NOT reviewed data. Per the
plan: "It is never LLM-generated at query time — a hallucinated section
mapping in a legal tool is the highest-severity failure this product can
have" and "human-review every row before committing." Every row this script
writes has confidence=unreviewed; nothing here is loaded by the app until
a human has gone through it and the confidence column is updated by hand
(see corpora/crosswalk.py, which refuses to load anything else).

What this script does NOT attempt, and why:
- BNS sections 2 (Definitions) and 3 (General explanations) are excluded.
  Their entries in the table are bracketed sub-clauses ("2(1)", "2(2)", ...)
  with no period, which don't fit this table's otherwise-consistent
  "N. Title." row format and corrupted row-boundary detection when
  included. They're term definitions, not offences, and out of scope for
  what the crosswalk is actually for (section-to-section offence mapping).
- The table's "Deleted" marker (meaning an IPC provision has no BNS
  successor) isn't parsed directly — some instances weren't reliably
  distinguishable from surrounding noise in testing. Instead, `relation:
  repealed` is inferred indirectly and more robustly: any IPC section
  extracted by the IPC loader that never appears in ANY row's mapped
  section list is flagged as a repeal candidate. This can't distinguish a
  genuine repeal from this script simply missing a row — that ambiguity is
  exactly why a human reviews every row rather than trusting either signal
  alone.
- Titles are NOT taken from this table's text. The two-column layout
  interleaves cells inconsistently (sometimes same line, sometimes
  wrapped), and cleaning that up reliably for 350+ rows wasn't achieved in
  testing. Instead, each row's title is looked up from the already-
  validated `ipc_commentary`/`bns_bare_act` loaders — the same parsers
  that build the actual retrieval index — so a title here is only ever as
  good as data already proven correct elsewhere, never a second, unverified
  source of truth.
"""

import csv
import re
import sys
from collections import Counter
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent / "backend"))

from app.corpora.loaders import bns_bare_act, ipc_commentary  # noqa: E402
from pypdf import PdfReader  # noqa: E402

TABLE_START_PAGE = 19
TABLE_END_PAGE = 73  # bns_bare_act.BODY_START_SIGNATURE lands here
EXCLUDED_BNS_SECTIONS = {"2", "3"}  # definitions / general explanations -- see module docstring
LOOKAHEAD = 6  # how far ahead to search when resyncing after a missed match

_ENTRY_RE = re.compile(r"(\d+[A-Z]{0,2})\.\s+")
_SPECIAL_WORDS = ("New Section", "New Sub-Section", "Deleted")
_SPECIAL_RE = re.compile(r"\b(" + "|".join(_SPECIAL_WORDS) + r")\b")


def _tokenize(table_text: str) -> list[tuple[str | None, str]]:
    """Flattens the table into a stream of (section_number_or_None, trailing
    content) tokens. A None-number token marks a special word ("New
    Section", "Deleted") at that position -- its own trailing content is
    whatever text follows before the next boundary, not the marker word
    itself (callers checking for a specific marker should track boundary
    identity, not this token's content)."""
    flat = re.sub(r"\s+", " ", table_text)
    boundaries: list[tuple[int, int, str | None]] = []
    for m in _ENTRY_RE.finditer(flat):
        boundaries.append((m.start(), m.end(), m.group(1)))
    for m in _SPECIAL_RE.finditer(flat):
        boundaries.append((m.start(), m.end(), None))
    boundaries.sort(key=lambda b: b[0])

    tokens = []
    for idx, (_, end, number) in enumerate(boundaries):
        content_end = boundaries[idx + 1][0] if idx + 1 < len(boundaries) else len(flat)
        tokens.append((number, flat[end:content_end].strip()))
    return tokens


def _group_rows(
    tokens: list[tuple[str | None, str]], bns_sequence: list[str]
) -> list[tuple[str, list[str]]]:
    """Groups the token stream into (bns_number, [ipc_numbers]) rows,
    resyncing against the known BNS section sequence when a match is found
    further ahead than immediately next -- without this, one missed match
    anywhere in the document silently corrupts every row after it."""
    rows: list[tuple[str, list[str]]] = []
    current_bns: str | None = None
    current_ipc: list[str] = []
    skip_current = False
    seq_idx = 0

    for number, _ in tokens:
        is_new_row = False
        if number is not None and seq_idx < len(bns_sequence):
            window = bns_sequence[seq_idx : seq_idx + LOOKAHEAD]
            if number in window:
                seq_idx += window.index(number)
                is_new_row = True

        if is_new_row:
            if current_bns is not None and not skip_current:
                rows.append((current_bns, current_ipc))
            current_bns = number
            current_ipc = []
            skip_current = number in EXCLUDED_BNS_SECTIONS
            seq_idx += 1
        elif number is not None:
            current_ipc.append(number)

    if current_bns is not None and not skip_current:
        rows.append((current_bns, current_ipc))
    return rows


def _classify_relation(ipc_numbers: list[str]) -> str:
    if not ipc_numbers:
        return "new"
    if len(ipc_numbers) > 1:
        return "merged"
    return "renumbered"


def build_draft() -> None:
    bns_pdf = Path(__file__).parent.parent / "data" / "bns" / "bns-data.pdf"
    ipc_pdf = Path(__file__).parent.parent / "data" / "ipc" / "ipc-data.pdf"

    bns_pages = [p.extract_text() or "" for p in PdfReader(bns_pdf).pages]
    ipc_pages = [p.extract_text() or "" for p in PdfReader(ipc_pdf).pages]

    bns_sections, _ = bns_bare_act.extract_sections(bns_pages)
    ipc_sections, _ = ipc_commentary.extract_sections(ipc_pages)
    bns_titles = {s.number: s.title for s in bns_sections}
    ipc_titles = {s.number: s.title for s in ipc_sections}
    bns_sequence = [s.number for s in bns_sections]

    table_text = "\n".join(bns_pages[TABLE_START_PAGE:TABLE_END_PAGE])
    tokens = _tokenize(table_text)
    rows = _group_rows(tokens, bns_sequence)

    referenced_ipc: set[str] = set()
    csv_rows = []
    for bns_num, ipc_nums in rows:
        relation = _classify_relation(ipc_nums)
        referenced_ipc.update(ipc_nums)
        csv_rows.append(
            {
                "bns_section": bns_num,
                "bns_title": bns_titles.get(bns_num, ""),
                "ipc_section": ";".join(ipc_nums),
                "ipc_title": ";".join(ipc_titles.get(n, "") for n in ipc_nums),
                "relation": relation,
                "confidence": "unreviewed",
                "source": "NCRB Corresponding Section Table (data/bns/bns-data.pdf)",
                "notes": "",
            }
        )

    # Repeal candidates: IPC sections the loader found that never appear in
    # any row's mapping. Indirect and imperfect -- see module docstring.
    all_ipc_numbers = set(ipc_titles)
    repeal_candidates = sorted(all_ipc_numbers - referenced_ipc, key=lambda n: (len(n), n))
    for ipc_num in repeal_candidates:
        csv_rows.append(
            {
                "bns_section": "",
                "bns_title": "",
                "ipc_section": ipc_num,
                "ipc_title": ipc_titles[ipc_num],
                "relation": "repealed_candidate",
                "confidence": "unreviewed",
                "source": "inferred: not referenced by any parsed crosswalk row",
                "notes": (
                    "Could be a genuine repeal, or a row this script's parser "
                    "missed -- verify against the source table directly."
                ),
            }
        )

    out_path = Path(__file__).parent.parent / "data" / "crosswalk" / "ipc_bns.csv"
    out_path.parent.mkdir(parents=True, exist_ok=True)
    with open(out_path, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(
            f,
            fieldnames=[
                "bns_section",
                "bns_title",
                "ipc_section",
                "ipc_title",
                "relation",
                "confidence",
                "source",
                "notes",
            ],
        )
        writer.writeheader()
        writer.writerows(csv_rows)

    mapped = {r[0] for r in rows}
    missing_bns = sorted(
        set(bns_sequence) - EXCLUDED_BNS_SECTIONS - mapped, key=lambda n: (len(n), n)
    )
    relation_counts = Counter(r["relation"] for r in csv_rows)
    expected_count = len(bns_sequence) - len(EXCLUDED_BNS_SECTIONS)

    print(f"Wrote {len(csv_rows)} rows to {out_path}")
    print(
        f"BNS sections mapped: {len(rows)} of {expected_count} "
        f"(excluding {sorted(EXCLUDED_BNS_SECTIONS)})"
    )
    print(f"BNS sections the parser never matched a row for: {missing_bns}")
    print(f"Relation counts: {dict(relation_counts)}")
    print("\nEVERY ROW IS confidence=unreviewed. See the module docstring for exactly")
    print("what this script does and doesn't verify. Human review required before use.")


if __name__ == "__main__":
    build_draft()
