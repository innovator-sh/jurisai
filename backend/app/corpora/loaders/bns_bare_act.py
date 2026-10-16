"""Loader for the official BNS bare-act text (NCRB's published PDF, chosen over the
MHA Gazette copy). Unlike the IPC source, this is a genuine bare-act: no
case-law commentary interleaved, no footnote-quoted superseded text, no
"COMMENT" boundary to search for. That structural difference is exactly why
this is its own loader rather than a variant of `ipc_commentary.py` — the
two documents aren't different dialects of the same format, they're
different formats entirely (confirmed: running the IPC loader's `[s N]`
parser against this PDF finds zero sections).

Three things found by testing against known sections (63, 103, 303, 318,
...) before trusting this parser, matching all 358 of BNS's official
section count with zero duplicates once fixed:

1. Section markers are plain `N. Whoever...` at a line start — no bracket
   tag. But the marginal title for a section sits on its own line
   *immediately before* the number, not inline with the body and not only
   in the arrangement-of-sections index — e.g. "Punishment for murder.\n
   103.(1) Whoever commits murder...". A handful of these marker lines
   have a single stray leading space ("Criminal force. \n 129. Whoever...")
   — a PDF-extraction artifact, not a real second offset convention — so
   the line-start pattern tolerates one leading space/tab.
2. Titles can wrap across two lines, same failure mode as the IPC loader.
   Because the title sits *before* its own number (not after, like IPC),
   this parser walks the gap between two consecutive markers backward from
   the end: a line joins the title only while the line further back does
   NOT end in terminal punctuation ('.', ':', ';') — that punctuation marks
   the end of the *previous* section's body, not a title continuation. The
   same walk also determines exactly how many trailing characters to trim
   off the *previous* section's body, which otherwise would run on to
   include this title (confirmed by inspection: section 2's body was
   swallowing "General explanations." — section 3's title — at its tail).
3. Chapter headings ("CHAPTER II", all-caps) and sub-chapter group
   headings ("Of Theft", "Of sexual offences", Title Case) sit between
   sections too and must not be swept into a title. Missing the Title Case
   form initially produced titles like "Of sexual offences Rape." for
   section 63 — fixed by also treating a line matching `^Of [\\w ,]+$` as
   a boundary, not just all-caps lines.
"""

import re

from app.corpora.loaders.base import RawSection

BODY_START_SIGNATURE = "This Act may be called the Bharatiya Nyaya Sanhita"
# Optional single leading space/tab — see point 1 above.
_SECTION_RE = re.compile(r"(?m)^[ \t]?(\d+[A-Z]?)\.\s?")
_CHAPTER_GROUP_RE = re.compile(r"^Of [a-zA-Z ,]{3,80}$")


def _is_heading_marker(line: str) -> bool:
    if len(line) > 2 and line.upper() == line:
        return True  # "CHAPTER II", "OF PUNISHMENTS"
    return bool(_CHAPTER_GROUP_RE.match(line))  # "Of Theft", "Of sexual offences"


def _title_from_gap(gap_text: str) -> tuple[str, int]:
    """`gap_text` is everything between the end of one section's marker and
    the start of the next — i.e. [previous section's body tail] + [this
    section's title, 1+ lines]. Returns (title, chars_consumed_from_the_end)
    so the caller can trim the previous section's body to exclude it."""
    lines = gap_text.split("\n")
    i = len(lines) - 1
    while i >= 0 and lines[i].strip() == "":
        i -= 1
    if i < 0:
        return "", 0
    first = lines[i].strip()
    if _is_heading_marker(first):
        return "", 0
    title_lines = [first]
    j = i - 1
    while j >= 0:
        line = lines[j].strip()
        if not line or _is_heading_marker(line) or line.endswith((".", ":", ";")):
            break
        title_lines.insert(0, line)
        j -= 1
    consumed = len("\n".join(lines[j + 1 :]))
    return " ".join(title_lines), consumed


def extract_sections(pages: list[str]) -> tuple[list[RawSection], list[str]]:
    full_text = ""
    page_at_offset: list[tuple[int, int]] = []
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

    signature_idx = full_text.find(BODY_START_SIGNATURE)
    if signature_idx == -1:
        raise ValueError(
            "Could not find the real Act body (looked for a distinctive phrase "
            "from section 1) — this source's layout may have changed."
        )
    # The nearest preceding numbered marker to the signature is section 1's
    # own heading — robust against exactly how many characters precede the
    # signature on that line, unlike a fixed backward offset.
    preamble_matches = list(_SECTION_RE.finditer(full_text[: signature_idx + 50]))
    if not preamble_matches:
        raise ValueError("Found the body signature but no preceding section-1 marker")
    body_offset = preamble_matches[-1].start()
    body = full_text[body_offset:]

    matches = list(_SECTION_RE.finditer(body))
    raw_segments = [
        body[m.end() : (matches[k + 1].start() if k + 1 < len(matches) else len(body))]
        for k, m in enumerate(matches)
    ]

    sections = []
    skipped: list[str] = []
    for k, m in enumerate(matches):
        number = m.group(1)
        raw = raw_segments[k]

        if k + 1 < len(matches):
            _, consumed = _title_from_gap(raw)
            text = raw[: len(raw) - consumed].strip()
        else:
            text = raw.strip()

        if k == 0:
            title = "Short title, commencement and application"
        else:
            title, _ = _title_from_gap(raw_segments[k - 1])

        if not text or not title:
            skipped.append(number)
            continue

        sections.append(
            RawSection(
                number=number,
                title=title.rstrip(".").strip(),
                text=re.sub(r"[ \t]+", " ", text).strip(),
                page=page_for_offset(body_offset + m.start()),
            )
        )

    return sections, sorted(set(skipped))
