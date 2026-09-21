"""Unit tests for the two format loaders, using small synthetic text that
mimics each source's actual structure (not the real PDFs — those are
covered by the real end-to-end validation in scripts/eval.py, which is slow
and needs the real files). These exist to pin the specific bugs found while
building each parser, so a future change can't silently reintroduce them."""

from app.corpora.loaders import bns_bare_act, ipc_commentary


class TestIpcCommentaryLoader:
    def test_finds_a_genuine_heading(self):
        pages = [
            "[s 302] Punishment for murder.\n"
            "Whoever commits murder shall be punished.\nCOMMENT.—blah"
        ]
        sections, skipped = ipc_commentary.extract_sections(pages)
        assert len(sections) == 1
        assert sections[0].number == "302"
        assert sections[0].title == "Punishment for murder"
        assert "COMMENT" not in sections[0].text

    def test_footnote_quoting_superseded_law_is_not_mistaken_for_a_heading(self):
        """The exact bug found on section 375: a footnote recites old,
        repealed wording complete with its own [s N] tag, inline mid-line —
        never at the start of a line like a genuine heading."""
        pages = [
            "Prior to substitution, section 375 stood as: [s 375] Rape.—old wording here.\n"
            "[s 376] Punishment for rape.\nWhoever commits rape shall be punished.\nCOMMENT—"
        ]
        sections, _ = ipc_commentary.extract_sections(pages)
        numbers = [s.number for s in sections]
        assert "375" not in numbers  # the footnote must not register as a heading
        assert "376" in numbers

    def test_footnote_bracket_artifact_before_heading_is_tolerated(self):
        """Section 34's real heading is preceded by a footnote-number
        artifact on the same line: '170.[[s 34] Title.'"""
        pages = [
            "170.[[s 34] Acts done by several persons.\n"
            "When a criminal act is done.\nCOMMENT—"
        ]
        sections, _ = ipc_commentary.extract_sections(pages)
        assert sections[0].number == "34"

    def test_oversized_section_is_excluded_not_ingested(self):
        pages = ["[s 999] Some title.\n" + ("filler " * 2000) + "\n[s 1000] Next.\nBody.\nCOMMENT—"]
        sections, skipped = ipc_commentary.extract_sections(pages)
        assert "999" in skipped
        assert "999" not in [s.number for s in sections]

    def test_bare_repealed_marker_is_excluded_not_ingested_as_garbage(self):
        """The exact bug found on sections 216B, 226, 478, 480, 490, 492:
        a heading immediately followed by "[Repealed]"/"[Omitted]" has no
        live statute text, but _TITLE_END_RE doesn't stop there -- title
        and body consumption both ran on into unrelated footnote/next-
        chapter text (confirmed: section 490's extracted "text" turned out
        to be chapter XIX's introductory essay, not section 490's content).
        Such a heading must be skipped outright, not ingested with
        whatever text happened to follow."""
        pages = [
            "[s 490] [Repealed]\n2.[* * *].\n1. The Works of Lord Macaulay - Note P.\n"
            "2. Omitted by Act 3 of 1925.\nTHE INDIAN PENAL CODE\nCHAPTER XIX OF SOMETHING\n"
            "The authors of the Code observe some unrelated essay text here that goes on.\n"
            "[s 493] Cohabitation caused by a man.\nWhoever cohabits.\nCOMMENT—"
        ]
        sections, skipped = ipc_commentary.extract_sections(pages)
        assert "490" in skipped
        assert "490" not in [s.number for s in sections]
        assert "493" in [s.number for s in sections]


class TestBnsBareActLoader:
    SAMPLE = (
        "CHAPTER I\nPRELIMINARY\n"
        "Short title, commencement and application\n"
        "1. This Act may be called the Bharatiya Nyaya Sanhita, 2023.\n"
        "(2) It shall come into force on such date.\n"
        "Definitions.\n"
        "2. In this Sanhita, unless the context otherwise requires.\n"
        "CHAPTER II\nOF PUNISHMENTS\n"
        "Punishments.\n"
        "4. The punishments to which offenders are liable.\n"
    )

    def test_finds_sections_with_marginal_titles_before_the_number(self):
        sections, skipped = bns_bare_act.extract_sections([self.SAMPLE])
        by_num = {s.number: s for s in sections}
        assert by_num["2"].title == "Definitions"
        assert by_num["4"].title == "Punishments"

    def test_chapter_heading_is_not_swept_into_a_title(self):
        """Section 4's real marginal title is "Punishments" — the chapter
        heading "CHAPTER II \\n OF PUNISHMENTS" sits just above it and must
        not be prepended, e.g. as "OF PUNISHMENTS Punishments"."""
        sections, _ = bns_bare_act.extract_sections([self.SAMPLE])
        by_num = {s.number: s for s in sections}
        assert by_num["4"].title == "Punishments"

    def test_body_does_not_swallow_the_next_sections_title(self):
        """The exact bug found on section 2: its body was running on to
        include the next section's marginal title at the tail."""
        sections, _ = bns_bare_act.extract_sections([self.SAMPLE])
        by_num = {s.number: s for s in sections}
        assert "Punishments" not in by_num["2"].text

    def test_sub_chapter_group_heading_is_excluded_from_title(self):
        sample = (
            "1. This Act may be called the Bharatiya Nyaya Sanhita, 2023.\n"
            "Of sexual offences\n"
            "Rape.\n"
            "63. A man is said to commit rape if he.\n"
        )
        sections, _ = bns_bare_act.extract_sections([sample])
        assert sections[-1].title == "Rape"

    def test_leading_space_before_marker_is_tolerated(self):
        """A handful of real markers have a stray leading space from PDF
        extraction ('Criminal force. \\n 129. Whoever...')."""
        sample = (
            "1. This Act may be called the Bharatiya Nyaya Sanhita, 2023.\n"
            "Criminal force.\n"
            " 129. Whoever intentionally uses force.\n"
        )
        sections, _ = bns_bare_act.extract_sections([sample])
        assert any(s.number == "129" for s in sections)

    def test_missing_body_signature_raises(self):
        try:
            bns_bare_act.extract_sections(["no signature here"])
            raise AssertionError("expected ValueError")
        except ValueError:
            pass
