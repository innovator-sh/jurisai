"""Resolves which corpus a question should be answered from.

Implements the plan's full precedence — explicit selection, offence date,
citation, default-hybrid — against whatever corpora are enabled in the
registry. Today only `ipc` is enabled, so every path collapses to it; the
seam and the precedence logic itself are what's under test here, proven
against a registry with both corpora so the logic generalizes correctly
once Sprint 3B flips `bns` on. See the plan's "Query routing" section.
"""

import re
from dataclasses import dataclass
from datetime import date

from app.corpora.registry import Corpus, CorpusRegistry

_CITATION_RE = re.compile(r"\bsection\s+\d+[a-z]*\s*(ipc|bns)\b", re.IGNORECASE)


@dataclass(frozen=True)
class RoutingResult:
    corpus: Corpus | None
    needs_clarification: bool = False
    reason: str = ""


def resolve_corpus(
    registry: CorpusRegistry,
    query: str,
    *,
    explicit_selection: str | None = None,
    offence_date: date | None = None,
) -> RoutingResult:
    enabled = registry.enabled()
    enabled_ids = {c.id for c in enabled}

    # 1. Explicit user selection wins outright.
    if explicit_selection and explicit_selection in enabled_ids:
        return RoutingResult(corpus=registry.get(explicit_selection))

    # 2. Offence date — the registry's in-force window decides.
    if offence_date is not None:
        corpus = registry.for_offence_date(offence_date)
        if corpus is not None:
            return RoutingResult(corpus=corpus)
        return RoutingResult(
            corpus=None,
            needs_clarification=True,
            reason=f"No enabled corpus covers an offence date of {offence_date.isoformat()}.",
        )

    # 3. Explicit citation in the query pins the corpus ("section 302 ipc").
    citation_match = _CITATION_RE.search(query)
    if citation_match:
        cited_id = citation_match.group(1).lower()
        if cited_id in enabled_ids:
            return RoutingResult(corpus=registry.get(cited_id))

    # 4. Default: hybrid across every enabled corpus. With only one enabled,
    # this collapses to it; ambiguity is only real once a second corpus is on.
    if len(enabled) == 1:
        return RoutingResult(corpus=enabled[0])
    if len(enabled) > 1:
        return RoutingResult(
            corpus=None,
            needs_clarification=True,
            reason="Multiple corpora are enabled and no offence date or citation was given.",
        )
    return RoutingResult(corpus=None, needs_clarification=True, reason="No corpus is enabled.")
