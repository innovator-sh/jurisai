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

_ENTRY_RE = re.compile(r"(\d+[A-Z]{0,2})\.\s*(?!\d)")
_SUBITEM_RE = re.compile(r"(\d+[A-Z]{0,2})\((?:[a-z]|\d+)\)")
_SPECIAL_WORDS = ("New Section", "New Sub-Section", "Deleted")
_SPECIAL_RE = re.compile(r"\b(" + "|".join(_SPECIAL_WORDS) + r")\b")
# A row's own title sometimes cross-references another section in prose,
# e.g. BNS s341's title reads "...forgery punishable under section 338." --
# that "338" is a self-reference, not a real table-column entry, and the
# word "section" immediately before it is what tells the two apart: a real
# entry is always a bare "N. Title", never "section N.".
_SECTION_PREFIX_RE = re.compile(r"\bsection\s*$", re.IGNORECASE)


def _tokenize(table_text: str) -> tuple[list[tuple[str | None, str, bool, int, str]], str]:
    """Flattens the table into a stream of (section_number_or_None, trailing
    content, is_ipc_side, start_pos, kind) tokens, plus the flattened text
    itself (needed by _group_rows for the "section N" self-reference check,
    which has to look back from a token's own position). `kind` is "entry",
    "subitem", or the literal matched special word ("Deleted", "New
    Section", "New Sub-Section") -- callers needing to know what preceded a
    token look at the previous token's `kind`, not a separate flag per
    marker. A None-number token's own trailing content is whatever text
    follows before the next boundary, not the marker word itself.

    Multi-mapping rows (one BNS section corresponding to several IPC
    sections, e.g. BNS s 1 absorbing IPC ss 1-5) list each IPC reference
    after a bracketed sub-item marker: "1(4) 3. Punishment...". Subitem
    tokens carry their own leading number (e.g. "1" in "1(4)") with empty
    content -- _group_rows uses that number only to resync against the BNS
    sequence when a row's real "N. Title" header is missing entirely (BNS s
    319's table row skips straight to "319(1) 416." with no "319. Cheating
    by personation" header of its own). The bare number immediately
    following a subitem marker is flagged is_ipc_side=True -- this is what
    lets _group_rows tell a genuine BNS row header apart from an IPC-column
    reference whose number coincidentally matches an upcoming BNS section
    number (the exact bug that corrupted BNS ss 4/5/8/10/12: IPC ss 2-5,
    tabulated under BNS s 1's sub-items, were misread as BNS s 2/3/4/5
    headers because both sides are small sequential integers early in the
    document)."""
    flat = re.sub(r"\s+", " ", table_text)
    boundaries: list[tuple[int, int, str | None, str]] = []
    for m in _ENTRY_RE.finditer(flat):
        boundaries.append((m.start(), m.end(), m.group(1), "entry"))
    for m in _SUBITEM_RE.finditer(flat):
        boundaries.append((m.start(), m.end(), m.group(1), "subitem"))
    for m in _SPECIAL_RE.finditer(flat):
        boundaries.append((m.start(), m.end(), None, m.group(1)))
    boundaries.sort(key=lambda b: b[0])

    tokens = []
    prev_kind = None
    for idx, (start, end, number, kind) in enumerate(boundaries):
        content_end = boundaries[idx + 1][0] if idx + 1 < len(boundaries) else len(flat)
        is_ipc_side = prev_kind == "subitem"
        content = "" if kind == "subitem" else flat[end:content_end].strip()
        tokens.append((number, content, is_ipc_side, start, kind))
        prev_kind = kind
    return tokens, flat


def _group_rows(
    tokens: list[tuple[str | None, str, bool, int, str]], flat: str, bns_sequence: list[str]
) -> tuple[list[tuple[str, list[str]]], set[str]]:
    """Groups the token stream into (bns_number, [ipc_numbers]) rows,
    resyncing against the known BNS section sequence when a match is found
    further ahead than immediately next -- without this, one missed match
    anywhere in the document silently corrupts every row after it.

    A number flagged is_ipc_side by _tokenize is never treated as a BNS row
    boundary, even if it coincidentally equals an upcoming BNS section
    number -- it is always appended to the currently open row instead.

    A subitem token (e.g. the "319" in "319(1)") is normally just a marker
    for the entry that follows it and contributes nothing itself -- but a
    few BNS rows (s 319 "Cheating by personation" is the confirmed case)
    have no "N. Title" header of their own at all; the table jumps straight
    to "319(1) 416. Cheating by personation. 319(2) 419. ...". Without
    resyncing on the subitem's own number too, that whole row -- and every
    IPC number under it -- would silently vanish. This only fires when the
    subitem's number differs from the currently open row and matches the
    next expected BNS section, so it can't misfire on the ordinary case of
    a subitem continuing the row it already belongs to (e.g. "70(2)" while
    s 70 is already open).

    A number immediately following a "Deleted" marker is dropped, not
    appended to whatever row happens to be open -- the table uses this
    inline ("Deleted 124A. Sedition 152. Acts endangering...") to state
    that a specific IPC section has NO Bns successor, which previously got
    misread as an IPC-side reference of the row open just before it (BNS s
    151 wrongly absorbed IPC s 124A this way). Dropping it here lets
    build_draft's ordinary "never referenced anywhere" repeal-candidate
    inference catch it correctly instead.

    A number that would otherwise be appended as IPC-side content (never
    one that matches as a genuine new BNS row) is dropped if it's a prose
    self-reference like "...forgery punishable under section 338." -- BNS
    s341's actual bug. The check runs here, after the row-boundary decision,
    not in _tokenize, because doing it unconditionally there also silently
    dropped genuine BNS row headers that happened to be preceded by the
    word "section" in the PRECEDING row's trailing prose (confirmed: 9 BNS
    sections vanished from the output this way when first tried).

    Also returns the set of IPC numbers seen under an EXCLUDED_BNS_SECTIONS
    row (s 2 Definitions, s 3 General explanations). Those rows are dropped
    from the output because they're term definitions, not offences -- but
    the IPC numbers they reference are real, in-scope correspondences, not
    unmapped ones. Without tracking them separately, build_draft's repeal-
    candidate check (based on "never appears in any row") would wrongly
    flag every IPC definitions-chapter section (6, 7, 33, 46, 47, ...) as a
    possible repeal, since dropping s 2/s 3's rows also silently dropped
    the fact that those sections *were* accounted for."""
    rows: list[tuple[str, list[str]]] = []
    excluded_ipc_refs: set[str] = set()
    current_bns: str | None = None
    current_ipc: list[str] = []
    skip_current = False
    seq_idx = 0
    prev_kind: str | None = None

    for number, _, is_ipc_side, start, kind in tokens:
        is_new_row = False
        if (
            kind in ("entry", "subitem")
            and number is not None
            and number != current_bns
            and seq_idx < len(bns_sequence)
        ):
            window = bns_sequence[seq_idx : seq_idx + LOOKAHEAD]
            if kind == "entry" and not is_ipc_side and number in window:
                seq_idx += window.index(number)
                is_new_row = True
            elif kind == "subitem" and number in window:
                seq_idx += window.index(number)
                is_new_row = True

        if is_new_row:
            if current_bns is not None:
                if skip_current:
                    excluded_ipc_refs.update(current_ipc)
                else:
                    rows.append((current_bns, current_ipc))
            current_bns = number
            current_ipc = []
            skip_current = number in EXCLUDED_BNS_SECTIONS
            seq_idx += 1
        elif (
            kind == "entry"
            and number is not None
            and prev_kind != "Deleted"
            and not _SECTION_PREFIX_RE.search(flat, 0, start)
        ):
            current_ipc.append(number)

        prev_kind = kind

    if current_bns is not None:
        if skip_current:
            excluded_ipc_refs.update(current_ipc)
        else:
            rows.append((current_bns, current_ipc))
    return rows, excluded_ipc_refs


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
    # ';' is this CSV's multi-value delimiter (ipc_section/ipc_title can list
    # several numbers for a merged row) -- a title that happens to contain a
    # literal ';' (confirmed: IPC s158's raw source text has one) would
    # silently misalign ipc_section against ipc_title on read. Scrubbed once
    # here rather than at every join site below.
    bns_titles = {s.number: s.title.replace(";", ",") for s in bns_sections}
    ipc_titles = {s.number: s.title.replace(";", ",") for s in ipc_sections}
    bns_sequence = [s.number for s in bns_sections]

    table_text = "\n".join(bns_pages[TABLE_START_PAGE:TABLE_END_PAGE])
    tokens, flat = _tokenize(table_text)
    rows, excluded_ipc_refs = _group_rows(tokens, flat, bns_sequence)

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
    # any row's mapping, AND aren't accounted for by an excluded BNS s 2/s 3
    # (Definitions / General explanations) row -- those are real, in-scope
    # correspondences, just not offence-to-offence ones. Indirect and
    # imperfect -- see module docstring.
    all_ipc_numbers = set(ipc_titles)
    repeal_candidates = sorted(
        all_ipc_numbers - referenced_ipc - excluded_ipc_refs, key=lambda n: (len(n), n)
    )
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
