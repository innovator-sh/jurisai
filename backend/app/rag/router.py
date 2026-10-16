"""Resolves which corpus/corpora a question should be answered from.

Implements the plan's full precedence — explicit selection, offence date,
citation, default-hybrid. `RoutingResult.corpora` holds one entry for a
single-corpus answer, or more than one for hybrid (retrieve from every
enabled corpus, primary-corpus-first — see `_ordered_for_hybrid`).
`needs_clarification=True` with an empty `corpora` list is the "the answer
genuinely differs and guessing would be wrong" case, not a fallback for
anything routine.
"""

import re
from dataclasses import dataclass, field
from datetime import date

from app.corpora.registry import Corpus, CorpusRegistry


def _citation_pattern(corpora: list[Corpus]) -> re.Pattern[str]:
    """"section 302 ipc" -> the corpus whose short name follows the number.
    Built from the registry, not hard-coded, so onboarding a new corpus (e.g.
    "section 438 bnss") needs no router change -- the same rule as everywhere
    else that a corpus id comes from definitions.yaml only."""
    shorts = sorted({c.short.lower() for c in corpora}, key=len, reverse=True)
    return re.compile(
        r"\bsection\s+\d+[a-z]*\s*(" + "|".join(re.escape(s) for s in shorts) + r")\b",
        re.IGNORECASE,
    )


@dataclass(frozen=True)
class RoutingResult:
    corpora: list[Corpus] = field(default_factory=list)
    needs_clarification: bool = False
    reason: str = ""

    @property
    def is_hybrid(self) -> bool:
        return len(self.corpora) > 1


def _ordered_for_hybrid(enabled: list[Corpus]) -> list[Corpus]:
    """Current law first — the plan's answer contract wants "current
    position under BNS, [then] the corresponding IPC provision", not an
    arbitrary or alphabetical order. A corpus with `supersedes` set is, by
    definition, the current one; this generalises to any future pair
    without naming "bns"/"ipc" here."""
    return sorted(enabled, key=lambda c: c.supersedes is None)


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
        return RoutingResult(corpora=[registry.get(explicit_selection)])

    # 2. Offence date — the registry's in-force window decides.
    if offence_date is not None:
        corpus = registry.for_offence_date(offence_date)
        if corpus is not None:
            return RoutingResult(corpora=[corpus])
        return RoutingResult(
            needs_clarification=True,
            reason=f"No enabled corpus covers an offence date of {offence_date.isoformat()}.",
        )

    # 3. Explicit citation in the query pins the corpus ("section 302 ipc").
    by_short = {c.short.lower(): c for c in enabled}
    if by_short:
        citation_match = _citation_pattern(enabled).search(query)
        if citation_match:
            return RoutingResult(corpora=[by_short[citation_match.group(1).lower()]])

    # 4. Default: hybrid across every enabled corpus. With only one enabled,
    # this collapses to a single-corpus result.
    if len(enabled) == 0:
        return RoutingResult(needs_clarification=True, reason="No corpus is enabled.")
    return RoutingResult(corpora=_ordered_for_hybrid(enabled))
