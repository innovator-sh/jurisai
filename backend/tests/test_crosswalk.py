"""Against a small synthetic CSV (not the real 380-row file) -- keeps this
fast and hermetic like the rest of the suite; the real file is exercised
end-to-end via scripts/build_crosswalk.py and manual review, not here."""

import csv
from pathlib import Path

import pytest
from app.corpora.crosswalk import load_crosswalk

FIELDNAMES = [
    "bns_section",
    "bns_title",
    "ipc_section",
    "ipc_title",
    "relation",
    "confidence",
    "source",
    "notes",
]


@pytest.fixture
def crosswalk_csv(tmp_path: Path) -> Path:
    rows = [
        {
            "bns_section": "103",
            "bns_title": "Punishment for murder",
            "ipc_section": "302",
            "ipc_title": "Punishment for murder",
            "relation": "renumbered",
            "confidence": "reviewed",
            "source": "test",
            "notes": "",
        },
        {
            "bns_section": "178",
            "bns_title": "Counterfeiting coin, Government stamps, currency-notes or bank-notes",
            "ipc_section": "231;232",
            "ipc_title": "Counterfeiting coin;Counterfeiting Indian coin",
            "relation": "merged",
            "confidence": "reviewed",
            "source": "test",
            "notes": "",
        },
        {
            "bns_section": "152",
            "bns_title": "Act endangering sovereignty, unity and integrity of India",
            "ipc_section": "",
            "ipc_title": "",
            "relation": "new",
            "confidence": "reviewed",
            "source": "test",
            "notes": "table marks this unrelated to IPC 124A",
        },
        {
            "bns_section": "",
            "bns_title": "",
            "ipc_section": "309",
            "ipc_title": "Attempt to commit suicide",
            "relation": "repealed_candidate",
            "confidence": "reviewed",
            "source": "test",
            "notes": "",
        },
    ]
    path = tmp_path / "ipc_bns.csv"
    with open(path, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=FIELDNAMES)
        writer.writeheader()
        writer.writerows(rows)
    return path


def test_from_bns_finds_a_renumbered_row(crosswalk_csv):
    crosswalk = load_crosswalk(crosswalk_csv)
    rows = crosswalk.from_bns("103")
    assert len(rows) == 1
    assert rows[0].ipc_sections == ["302"]
    assert rows[0].relation == "renumbered"


def test_from_ipc_finds_every_ipc_section_in_a_merged_row(crosswalk_csv):
    crosswalk = load_crosswalk(crosswalk_csv)
    row_via_231 = crosswalk.from_ipc("231")
    row_via_232 = crosswalk.from_ipc("232")
    assert len(row_via_231) == 1
    assert row_via_231 == row_via_232  # same underlying row, reachable both ways


def test_from_ipc_on_repealed_candidate_has_no_bns_section(crosswalk_csv):
    crosswalk = load_crosswalk(crosswalk_csv)
    rows = crosswalk.from_ipc("309")
    assert len(rows) == 1
    assert rows[0].bns_section == ""
    assert rows[0].relation == "repealed_candidate"


def test_unknown_section_returns_empty(crosswalk_csv):
    crosswalk = load_crosswalk(crosswalk_csv)
    assert crosswalk.from_bns("999") == []
    assert crosswalk.from_ipc("999") == []


def test_lookup_dispatches_by_corpus_id(crosswalk_csv):
    crosswalk = load_crosswalk(crosswalk_csv)
    assert crosswalk.lookup("bns", "103") == crosswalk.from_bns("103")
    assert crosswalk.lookup("ipc", "302") == crosswalk.from_ipc("302")


def test_lookup_on_unknown_corpus_id_returns_empty(crosswalk_csv):
    crosswalk = load_crosswalk(crosswalk_csv)
    assert crosswalk.lookup("bnss", "103") == []


def test_missing_csv_path_loads_empty(tmp_path: Path):
    crosswalk = load_crosswalk(tmp_path / "does_not_exist.csv")
    assert crosswalk.from_bns("103") == []
