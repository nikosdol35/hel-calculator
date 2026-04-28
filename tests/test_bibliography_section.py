"""Tests for the Math-tab Bibliography section (added 2026-04-28).

Verifies that ``ui.bibliography`` enumerates exactly:
  - 13 primary references (matching SPEC.md Appendix B)
  - 10 supplementary canonical books
  - 23 total

Plus pins the canonical authors (so a future refactor can't silently
drop a citation), checks every entry has the required dataclass fields
populated, and verifies the Markdown export includes a Bibliography
section.
"""
from __future__ import annotations

from ui.bibliography import (
    ALL_REFERENCES,
    PRIMARY_REFERENCES,
    SUPPLEMENTARY_REFERENCES,
    BibliographyEntry,
)


def test_thirteen_primary_references():
    """SPEC.md Appendix B has 13 primary works — pin the count."""
    assert len(PRIMARY_REFERENCES) == 13
    authors = " | ".join(e.authors for e in PRIMARY_REFERENCES)
    for needle in ("Andrews", "Siegman", "Born", "Gebhardt", "Carslaw",
                   "Steen", "ANSI Z136.1", "IEC 60825-1", "Kruse",
                   "McClatchey", "Hufnagel", "Perram"):
        assert needle in authors, f"missing primary reference: {needle}"


def test_gebhardt_appears_twice_in_primary():
    """Gebhardt has TWO works cited (1976 paper + 1990 SPIE overview)
    — both physics-critical for M6 blooming. Drop one and we lose
    SPEC §10.4 citation provenance."""
    gebhardt_count = sum(
        1 for e in PRIMARY_REFERENCES if "Gebhardt" in e.authors
    )
    assert gebhardt_count == 2


def test_ten_supplementary_references():
    """10 canonical books verified via 2026-04-28 publisher-catalogue
    web search (Springer / Wiley / Cambridge / SPIE / Dover /
    Academic Press / McGraw-Hill)."""
    assert len(SUPPLEMENTARY_REFERENCES) == 10
    authors = " | ".join(e.authors for e in SUPPLEMENTARY_REFERENCES)
    for needle in ("Zohuri", "Saleh", "Tatarski", "Ishimaru",
                   "Goodman", "Modest", "Smith", "Thomas", "Bass"):
        assert needle in authors, f"missing supplementary: {needle}"


def test_goodman_appears_twice_in_supplementary():
    """Goodman authored two relevant canonical texts (Statistical
    Optics + Introduction to Fourier Optics) — both apply to
    different parts of the chain."""
    goodman_count = sum(
        1 for e in SUPPLEMENTARY_REFERENCES if "Goodman" in e.authors
    )
    assert goodman_count == 2


def test_total_twenty_three():
    assert len(ALL_REFERENCES) == 23
    assert ALL_REFERENCES == PRIMARY_REFERENCES + SUPPLEMENTARY_REFERENCES


def test_each_entry_has_required_fields():
    """Every BibliographyEntry must be fully populated — no empty
    cells in the rendered table."""
    for e in ALL_REFERENCES:
        assert isinstance(e, BibliographyEntry)
        assert e.authors and e.title and e.year and e.publisher
        assert e.kind in ("Cited", "Supplementary")
        assert e.used_for


def test_kind_partition_matches_group_lists():
    """All PRIMARY_REFERENCES entries report kind='Cited';
    all SUPPLEMENTARY_REFERENCES report kind='Supplementary'."""
    for e in PRIMARY_REFERENCES:
        assert e.kind == "Cited"
    for e in SUPPLEMENTARY_REFERENCES:
        assert e.kind == "Supplementary"


def test_used_for_under_six_words_or_so():
    """Where-used cells render in a Markdown-table column on
    narrow viewports. Keep them short (≤ 8 words) so the table
    stays legible on mobile."""
    for e in ALL_REFERENCES:
        word_count = len(e.used_for.split())
        assert word_count <= 8, (
            f"'used_for' too long for {e.authors!r}: "
            f"{word_count} words ({e.used_for!r})"
        )


def test_markdown_export_includes_bibliography_section():
    """The Markdown download must mirror the on-screen Bibliography
    section so users who export the math tab get the references."""
    from ui.math_export import to_markdown
    # Minimal stub result — the bibliography section doesn't depend
    # on the user's input values, so we only need a dict that doesn't
    # crash the exporter's metric rows.
    from physics.orchestrator import run_full_chain
    from tests.golden.scenarios import C_UAS_1500M
    result = run_full_chain(dict(C_UAS_1500M))
    md = to_markdown(result, include_full=False)
    assert "## Bibliography & references" in md
    # At least 3 well-known authors appear in the export.
    for needle in ("Andrews", "Zohuri", "Tatarski"):
        assert needle in md, f"missing {needle} in Markdown export"
