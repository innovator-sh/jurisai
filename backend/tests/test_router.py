"""Router precedence, proven against a registry with BOTH corpora enabled —
the real production registry only has ipc enabled today (bns declared but
unbuilt), so these tests are what actually exercises rules 1-4 in the plan's
routing precedence rather than asserting them by fiat."""

from datetime import date

import pytest
from app.corpora.registry import Corpus, CorpusRegistry, load_registry
from app.rag.router import resolve_corpus

IPC = Corpus(
    id="ipc",
    act="Indian Penal Code, 1860",
    short="IPC",
    jurisdiction="IN",
    in_force_from=date(1862, 1, 1),
    in_force_to=date(2024, 6, 30),
    source="data/ipc",
    collection="jurisai_ipc",
    enabled=True,
    superseded_by="bns",
)
BNS = Corpus(
    id="bns",
    act="Bharatiya Nyaya Sanhita, 2023",
    short="BNS",
    jurisdiction="IN",
    in_force_from=date(2024, 7, 1),
    in_force_to=None,
    source="data/bns",
    collection="jurisai_bns",
    enabled=True,
    supersedes="ipc",
)


@pytest.fixture
def both_enabled() -> CorpusRegistry:
    return CorpusRegistry([IPC, BNS])


def test_explicit_selection_wins(both_enabled):
    result = resolve_corpus(both_enabled, "what is theft", explicit_selection="bns")
    assert result.corpus.id == "bns"


def test_offence_date_before_bns_routes_to_ipc(both_enabled):
    result = resolve_corpus(both_enabled, "what is theft", offence_date=date(2023, 5, 1))
    assert result.corpus.id == "ipc"


def test_offence_date_after_cutover_routes_to_bns(both_enabled):
    result = resolve_corpus(both_enabled, "what is theft", offence_date=date(2025, 1, 1))
    assert result.corpus.id == "bns"


def test_citation_in_query_pins_corpus(both_enabled):
    result = resolve_corpus(both_enabled, "what is section 302 ipc")
    assert result.corpus.id == "ipc"


def test_bare_section_number_does_not_guess_a_corpus(both_enabled):
    """'section 302' with no act named must not be silently assigned to one
    corpus — that's the whole point of requiring an explicit citation. With
    two corpora enabled this falls through to needing clarification, not a
    guess (hybrid retrieval across both is Sprint 3B's job)."""
    result = resolve_corpus(both_enabled, "what is section 302")
    assert result.corpus is None
    assert result.needs_clarification is True


def test_default_with_two_enabled_corpora_needs_clarification(both_enabled):
    result = resolve_corpus(both_enabled, "what is theft")
    assert result.needs_clarification is True
    assert result.corpus is None


def test_real_registry_resolves_to_ipc_when_ipc_is_the_right_answer():
    """Sprint 3 exit criteria: bns is declared but unbuilt, so any request
    that *should* legitimately land on ipc does — a bare query, or an
    explicit 'bns' selection that isn't enabled yet, both fall through to it."""
    registry = load_registry()
    for kwargs in [{}, {"explicit_selection": "bns"}]:
        result = resolve_corpus(registry, "what is theft", **kwargs)
        assert result.corpus is not None
        assert result.corpus.id == "ipc"


def test_real_registry_refuses_ipc_for_a_post_cutover_offence_date():
    """An offence date after 1 Jul 2024 is genuinely not IPC's to answer —
    with bns not yet enabled, the router must ask rather than silently
    apply superseded law, even though "for now it always resolves to ipc"
    describes the default case, not this one."""
    registry = load_registry()
    result = resolve_corpus(registry, "what is theft", offence_date=date(2025, 1, 1))
    assert result.corpus is None
    assert result.needs_clarification is True
