"""Per-format section extractors. Each loader takes a list of page texts
(pypdf's page order) and returns `(sections, skipped_section_numbers)`.

Different statutes are typeset completely differently — this package exists
because BNS proved that isn't a hypothetical: the IPC source is an annotated
commentary edition needing a `[s N]` heading parser, while BNS's official
bare-act text uses plain `N. Whoever...` markers with no case-law
interleaved. Neither loader works on the other's document; see each
module's docstring for what its source actually looks like and what
testing against it caught.
"""

from app.corpora.loaders.base import RawSection

__all__ = ["RawSection"]
