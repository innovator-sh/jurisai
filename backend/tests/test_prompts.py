from app.corpora.crosswalk import Crosswalk, CrosswalkRow
from app.rag.prompts import build_crosswalk_block, collect_crosswalk_facts
from app.rag.retriever import RetrievedChunk

MERGED_ROW = CrosswalkRow(
    bns_section="178",
    bns_title="Counterfeiting coin, Government stamps, currency-notes or bank-notes",
    ipc_sections=["231", "232"],
    ipc_titles=["Counterfeiting coin", "Counterfeiting Indian coin"],
    relation="merged",
    confidence="reviewed",
    source="test",
    notes="",
)
RENUMBERED_ROW = CrosswalkRow(
    bns_section="103",
    bns_title="Punishment for murder",
    ipc_sections=["302"],
    ipc_titles=["Punishment for murder"],
    relation="renumbered",
    confidence="reviewed",
    source="test",
    notes="",
)
NEW_ROW = CrosswalkRow(
    bns_section="152",
    bns_title="Act endangering sovereignty, unity and integrity of India",
    ipc_sections=[],
    ipc_titles=[],
    relation="new",
    confidence="reviewed",
    source="test",
    notes="table marks this unrelated to IPC 124A",
)
REPEALED_ROW = CrosswalkRow(
    bns_section="",
    bns_title="",
    ipc_sections=["309"],
    ipc_titles=["Attempt to commit suicide"],
    relation="repealed_candidate",
    confidence="reviewed",
    source="test",
    notes="",
)


def _chunk(section: str) -> RetrievedChunk:
    return RetrievedChunk(
        text="...",
        act="Indian Penal Code, 1860",
        section=section,
        section_title="...",
        page=1,
        score=0.9,
        ingest_version="test",
    )


def test_build_crosswalk_block_renders_merged_row():
    text = build_crosswalk_block([MERGED_ROW])
    assert "BNS 178 <-> IPC 231, 232 (merged)" in text
    assert "Counterfeiting coin, Government stamps" in text


def test_build_crosswalk_block_renders_new_row():
    text = build_crosswalk_block([NEW_ROW])
    assert "BNS 152 is a NEW provision with no IPC predecessor" in text


def test_build_crosswalk_block_renders_repealed_candidate_row():
    text = build_crosswalk_block([REPEALED_ROW])
    assert "IPC 309 has no established BNS successor (repealed_candidate)" in text


def test_build_crosswalk_block_appends_notes_when_present():
    text = build_crosswalk_block([NEW_ROW])
    assert "(note: table marks this unrelated to IPC 124A)" in text


def test_build_crosswalk_block_empty_list():
    expected = "(No verified correspondence found for the retrieved sections.)"
    assert build_crosswalk_block([]) == expected


def test_collect_crosswalk_facts_dedupes_a_merged_row_reached_from_two_ipc_sections():
    crosswalk = Crosswalk([MERGED_ROW])
    chunks_by_corpus = {"ipc": [_chunk("231"), _chunk("232")]}
    facts = collect_crosswalk_facts(crosswalk, chunks_by_corpus)
    assert facts == [MERGED_ROW]


def test_collect_crosswalk_facts_across_both_corpora():
    crosswalk = Crosswalk([MERGED_ROW, RENUMBERED_ROW])
    chunks_by_corpus = {
        "ipc": [_chunk("231")],
        "bns": [_chunk("103")],
    }
    facts = collect_crosswalk_facts(crosswalk, chunks_by_corpus)
    assert len(facts) == 2
    assert MERGED_ROW in facts
    assert RENUMBERED_ROW in facts


def test_collect_crosswalk_facts_empty_when_nothing_matches():
    crosswalk = Crosswalk([MERGED_ROW])
    chunks_by_corpus = {"ipc": [_chunk("999")]}
    assert collect_crosswalk_facts(crosswalk, chunks_by_corpus) == []
