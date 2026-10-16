"""Router precedence, proven against a synthetic registry first, then
against the real one now that Sprint 3B has enabled both ipc and bns."""

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
    loader="ipc_commentary",
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
    loader="bns_bare_act",
    enabled=True,
    supersedes="ipc",
)


@pytest.fixture
def both_enabled() -> CorpusRegistry:
    return CorpusRegistry([IPC, BNS])


def test_explicit_selection_wins(both_enabled):
    result = resolve_corpus(both_enabled, "what is theft", explicit_selection="bns")
    assert [c.id for c in result.corpora] == ["bns"]


def test_offence_date_before_bns_routes_to_ipc(both_enabled):
    result = resolve_corpus(both_enabled, "what is theft", offence_date=date(2023, 5, 1))
    assert [c.id for c in result.corpora] == ["ipc"]


def test_offence_date_after_cutover_routes_to_bns(both_enabled):
    result = resolve_corpus(both_enabled, "what is theft", offence_date=date(2025, 1, 1))
    assert [c.id for c in result.corpora] == ["bns"]


def test_citation_in_query_pins_corpus(both_enabled):
    result = resolve_corpus(both_enabled, "what is section 302 ipc")
    assert [c.id for c in result.corpora] == ["ipc"]


def test_bare_section_number_falls_through_to_hybrid_default(both_enabled):
    """'section 302' with no act named must not be silently assigned to one
    corpus — that's the whole point of requiring an explicit citation. With
    two corpora enabled, no date, and no recognised citation, this is
    exactly the default case: hybrid, primary (superseding) corpus first."""
    result = resolve_corpus(both_enabled, "what is section 302")
    assert result.is_hybrid
    assert [c.id for c in result.corpora] == ["bns", "ipc"]


def test_default_with_two_enabled_corpora_is_hybrid_bns_first(both_enabled):
    result = resolve_corpus(both_enabled, "what is theft")
    assert result.needs_clarification is False
    assert result.is_hybrid
    assert [c.id for c in result.corpora] == ["bns", "ipc"]


def test_unrecognised_explicit_selection_falls_through_to_hybrid(both_enabled):
    result = resolve_corpus(both_enabled, "what is theft", explicit_selection="bnss")
    assert result.is_hybrid


# --- Against the real registry, now that Sprint 3B has enabled bns too ---


def test_real_registry_explicit_selection_reaches_bns():
    registry = load_registry()
    result = resolve_corpus(registry, "what is theft", explicit_selection="bns")
    assert [c.id for c in result.corpora] == ["bns"]


def test_real_registry_offence_date_routes_correctly_both_ways():
    registry = load_registry()
    pre_cutover = resolve_corpus(registry, "what is theft", offence_date=date(2023, 5, 1))
    assert [c.id for c in pre_cutover.corpora] == ["ipc"]
    post_cutover = resolve_corpus(registry, "what is theft", offence_date=date(2025, 1, 1))
    assert [c.id for c in post_cutover.corpora] == ["bns"]


def test_real_registry_bare_query_defaults_to_hybrid_bns_first():
    """This is the real-registry version of the same rule tested above
    against the synthetic fixture — both corpora really are enabled now."""
    registry = load_registry()
    result = resolve_corpus(registry, "what is theft")
    assert result.is_hybrid
    assert [c.id for c in result.corpora] == ["bns", "ipc"]


def test_citation_routing_works_for_a_corpus_the_router_has_never_heard_of():
    """Onboarding a corpus is a definitions.yaml entry + a loader -- the router
    must not need to know the new act's name (it used to hard-code ipc|bns)."""
    bnss = Corpus(
        id="bnss",
        act="Bharatiya Nagarik Suraksha Sanhita, 2023",
        short="BNSS",
        jurisdiction="IN",
        in_force_from=date(2024, 7, 1),
        in_force_to=None,
        source="data/bnss",
        collection="jurisai_bnss",
        loader="bnss_bare_act",
        enabled=True,
    )
    registry = CorpusRegistry([IPC, BNS, bnss])

    result = resolve_corpus(registry, "what does section 438 BNSS say about anticipatory bail")
    assert [c.id for c in result.corpora] == ["bnss"]

    # "bns" is a prefix of "bnss": the longer name must win, not be shadowed.
    result = resolve_corpus(registry, "what is section 103 bns")
    assert [c.id for c in result.corpora] == ["bns"]


def test_a_citation_naming_a_disabled_corpus_does_not_pin_it():
    disabled_bns = Corpus(**{**BNS.__dict__, "enabled": False})
    registry = CorpusRegistry([IPC, disabled_bns])
    result = resolve_corpus(registry, "what is section 103 bns")
    assert [c.id for c in result.corpora] == ["ipc"]
