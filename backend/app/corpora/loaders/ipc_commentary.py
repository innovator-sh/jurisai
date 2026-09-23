"""Loader for the IPC source: an annotated commentary edition (~1870 pages:
statute text interleaved with case law, footnotes, and cross-references
under `[s <N>]` markers) — not a bare-act text. Several things follow from
that, each found by testing this parser against known sections (302, 379,
420, 375, 34, ...) before trusting it — see docs/decisions.md for the full
list:

1. A genuine section heading is a `[s N] Title.` line that STARTS a line of
   its own — sometimes preceded by a footnote-number artifact like
   "170.[" (e.g. section 34's actual heading). The same `[s N]` marker also
   turns up inline mid-paragraph inside footnotes quoting superseded text
   (a footnote on section 375 recites the pre-2013 wording verbatim,
   complete with its own `[s 375]` tag) — those are never at a line start,
   which is what tells a real heading apart from a footnote quoting old law.
   Getting this wrong means citing repealed text as current law.
2. A title can wrap across two lines in the source (e.g. section 149's
   heading is "Every member of unlawful assembly guilty of offence
   committed in\\nprosecution of common object."). The title is accumulated
   line-by-line until a line ends in "." — stopping at end-of-line
   unconditionally truncated titles and corrupted the body text with a
   leftover title fragment.
3. Only the statute text itself — between the heading and the first
   "COMMENT" marker — is ingested. The commentary and case citations that
   follow are legal opinion, not law, and conflating them with the
   authoritative text is exactly the kind of correctness bug a legal tool
   cannot ship with.
4. A handful of sections (107, 108, 109, 121, 375, 376, 464 — heavily
   amended, subsection-lettered provisions) don't have a detectable
   "COMMENT" boundary or a matching next heading in this format, so
   extraction runs on and swallows a neighbouring section's text (confirmed
   by inspection: content that is actually section 376 turned up labelled
   as 375). Spot-checking confirmed everything else — including other long
   sections like 300 (murder) and 499 (defamation, correctly ending at its
   real "Tenth Exception") — extracts cleanly. Given that, sections whose
   raw block exceeds `MAX_RAW_SECTION_CHARS` are excluded rather than
   ingested with unverified, likely-mislabelled content: there's a clean
   gap in the length distribution between the longest confirmed-correct
   section (8,637 chars) and the shortest confirmed-contaminated one
   (13,058 chars), so the threshold sits in that gap. This is the same
   principle Sprint 3's retrieval threshold applies at query time — no
   chunk is better than a wrong one — just applied at ingest time instead.
   `scripts/ingest.py` prints which sections were skipped.
5. A section whose heading is immediately followed by a bare "[Repealed]"
   or "[Omitted]" (10 sections found this way: 13, 15, 16, 138A, 216B,
   226, 478, 480, 490, 492) has no live statute text at all -- that
   bracket IS the IPC's own way of saying so. `_TITLE_END_RE` doesn't
   treat the bracket as a title terminator, so title/body consumption
   both ran on past it into whatever unrelated footnote, case citation, or
   even next-chapter introductory essay happened to contain the next
   '.'/em-dash -- confirmed by inspection: section 490's extracted "text"
   turned out to be chapter XIX's introductory prose, not section 490's
   content (which has none, repealed in 1925). These are detected before
   title/body consumption runs and skipped outright, the same as case 4.
6. A footnote-number artifact can share its bracket with the heading
   marker itself instead of using its own separate one: section 4's real
   heading is "45.[s 4]" (one bracket total), not "45.[[s 4]" (two
   brackets, section 34's pattern) or a bare "[s 4]". The original regex
   only handled the other two forms, so this variant matched nothing at
   all -- not even caught by the MAX_RAW_SECTION_CHARS or bare-repealed-
   marker exclusions, just silently absent with no signal anywhere. Found
   by grepping the full text for every "N.[s M]" occurrence and checking
   which M never turned up in extract_sections's own output at all: 17
   sections were missing this way, including s4 (extraterritorial
   jurisdiction), the obscenity cluster (292-295A), and several sexual-
   offence provisions (366A, 366B, 376AB, 376C, 376E) -- a much bigger,
   previously-unknown gap than case 4's 7 sections.
7. A footnote-number artifact isn't always digits -- some pages use
   asterisks instead ("Forged **[document or electronic record]" on
   section 470, "***[" on 471). `_FOOTNOTE_BRACKET_RE` only stripped the
   digit form, so the asterisks leaked into the cleaned title verbatim.
8. The heading marker isn't always followed by a plain space before the
   title -- section 228A's is "416.[s 228A]-- Disclosure of..." (an
   em-dash with no space at all between the bracket and it), which the
   original `\]\s+` requirement couldn't match, silently dropping the
   section the same way case 6 did.

Known remaining gap, not yet fixed: a handful of definitions-chapter
sections (confirmed: 17) use a bracketed, unpunctuated single-word title
("21.[s 17] \"Government\"") with no terminator before the body sentence
starts on the next line -- unlike sibling definitions (33, 46, 47, ...)
whose quoted term IS followed by a period. `_consume_title` has nothing to
stop at, so it runs into the body and grabs an inline footnote number as
its accidental terminator, which -- unlike the title-only cosmetic
artifacts on 292/293/294A -- also truncates section 17's actual retrievable
text (its opening definition sentence ends up misclassified as the title
and lost). Needs a dedicated fix, not a quick patch, since the ambiguity is
title-vs-body itself, not the token pattern.
"""

import re
import unicodedata

from app.corpora.loaders.base import RawSection

# A genuine heading starts a line, optionally preceded by a footnote-number
# artifact, which can appear two ways: with its own bracket ("170.[[s 34]",
# two brackets total) or sharing the heading's own bracket ("45.[s 4]", one
# bracket total -- the two forms coexist in this source). Digits-only class
# after "s " deliberately excludes "[s 302.1]" (sub-commentary headings
# within a section's own annotation, not real section boundaries).
_HEADING_RE = re.compile(r"^(?:\d+\.\[?)?\[s (\d+[A-Z]{0,3})\]\s*[.—�]?\s*", re.MULTILINE)
_COMMENT_RE = re.compile(r"^COMMENT\b", re.MULTILINE)
# A footnote-number artifact prefixing bracketed text, either digit-based
# ("196.[imprisonment...]") or asterisk-based ("**[document...]" -- seen on
# sections 470/471, apparently used when no footnote number was assigned).
_FOOTNOTE_BRACKET_RE = re.compile(r"(?:\d+\.|\*+)\[")
# A title ends at the first '.', em-dash, or PDF-font-decode replacement
# character (some pages render an em-dash as U+FFFD instead of '—') —
# wherever it falls, not necessarily at end-of-line. Some sections (e.g.
# "Rape.—A man is said to...") pack the title and the start of the body on
# one visual line with no line break between them at all.
_TITLE_END_RE = re.compile(r"[.—�]")
# A heading immediately followed by one of these has no live statute text
# -- see module docstring point 5. Checked before title/body consumption,
# not as a _TITLE_END_RE terminator, because the real problem isn't where
# the title ends -- it's that there's no body to bound at all.
_DEAD_SECTION_RE = re.compile(r"^\s*\[(Repealed|Omitted)\]", re.IGNORECASE)

MAX_RAW_SECTION_CHARS = 10_000


def _clean(text: str) -> str:
    text = unicodedata.normalize("NFKC", text)  # 'ﬁne' -> 'fine', etc.
    text = _FOOTNOTE_BRACKET_RE.sub("", text)  # "196.[imprisonment...]" -> "imprisonment...]"
    text = text.replace("]", "")  # strip the now-unmatched closing brackets
    text = re.sub(r"[ \t]+", " ", text).strip()
    # A leading '.', '"', or the title terminator itself is a leftover from
    # where _consume_title cut the title off mid-line (e.g. body starting
    # '".\nThe words "movable property"...' after a title like '"Movable
    # property'). Cosmetic only — the statute text itself is unaffected.
    return text.lstrip(".—�\" ").strip()


def _consume_title(full_text: str, start: int) -> tuple[str, int]:
    """The title runs from `start` to the first '.'/em-dash — which may be on
    a later line if the title itself wraps (e.g. section 149's heading spans
    two lines with no terminator on the first), or partway through the same
    line as the body if there's no line break at all (e.g. section 375's
    "Rape.—A man is said to..." packs title and body onto one visual line).
    Returns (title, offset where the body starts)."""
    match = _TITLE_END_RE.search(full_text, start)
    if match is None:
        return full_text[start:].strip(), len(full_text)
    title = full_text[start : match.start() + 1].replace("\n", " ").strip()
    return title, match.end()


def extract_sections(pages: list[str]) -> tuple[list[RawSection], list[str]]:
    """`pages` is page text in order, 0-indexed matching pypdf's page numbers.
    Returns (sections, skipped_section_numbers) — see the module docstring
    for why some sections are excluded rather than ingested."""
    full_text = ""
    page_at_offset: list[tuple[int, int]] = []  # (char offset, page number)
    for i, page_text in enumerate(pages):
        page_at_offset.append((len(full_text), i))
        full_text += page_text + "\n"

    def page_for_offset(offset: int) -> int:
        page = 0
        for start, page_no in page_at_offset:
            if start > offset:
                break
            page = page_no
        return page

    headings = list(_HEADING_RE.finditer(full_text))
    sections = []
    skipped = []
    for idx, match in enumerate(headings):
        number = match.group(1)
        if _DEAD_SECTION_RE.match(full_text[match.end() : match.end() + 30]):
            skipped.append(number)
            continue
        title, body_start = _consume_title(full_text, match.end())
        body_end = headings[idx + 1].start() if idx + 1 < len(headings) else len(full_text)
        block = full_text[body_start:body_end]

        comment_match = _COMMENT_RE.search(block)
        statute_text = block[: comment_match.start()] if comment_match else block

        if len(statute_text) > MAX_RAW_SECTION_CHARS:
            skipped.append(number)
            continue

        cleaned = _clean(statute_text)
        if not cleaned:
            continue  # a heading with no statute body (e.g. a repealed/reserved section)
        sections.append(
            RawSection(
                number=number,
                title=_clean(title).rstrip(".—�").strip(),
                text=cleaned,
                page=page_for_offset(match.start()),
            )
        )
    return _deduplicate(sections), sorted(set(skipped))


def _deduplicate(sections: list[RawSection]) -> list[RawSection]:
    """A handful of sections (amendment-related ones like 120B, 153A) are
    printed twice in the source, verified byte-identical where checked.
    Keeps the longest text seen per section number."""
    best: dict[str, RawSection] = {}
    for section in sections:
        current = best.get(section.number)
        if current is None or len(section.text) > len(current.text):
            best[section.number] = section
    return list(best.values())
