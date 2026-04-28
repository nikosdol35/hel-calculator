"""Bibliography for the HEL Calculator — primary citations + canonical
supplementary reading.

The 13 primary references match SPEC.md Appendix B exactly: every
formula in this tool traces back to one of them, and they're cited
directly in the physics-module docstrings (per CLAUDE.md §4.2 — every
implemented formula must cite its source).

The 10 supplementary references are widely-used canonical books in
laser physics, atmospheric optics, radiative transfer, and directed-
energy weapons. They are NOT required to verify any specific formula
in this tool — they are reading material for users who want to study
the field beyond what this tool implements. All ten are recognised
authoritative texts published by Cambridge / Wiley / Springer / SPIE /
Academic Press / McGraw-Hill / Dover.

The ``ALL_REFERENCES`` tuple combines both sets in display order —
13 primary first, then 10 supplementary, total 23.

Pure module — no Streamlit imports. Consumed by:
  - ``ui.outputs._render_bibliography_section`` for the on-screen Math-
    tab table
  - ``ui.math_export._render_bibliography_md`` for the Markdown export
  - ``tests.test_bibliography_section`` for the count + content asserts
"""
from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class BibliographyEntry:
    """One bibliographic record.

    Attributes:
      authors: Author surname-first form ("Andrews, L. C. & Phillips, R. L.").
      title: Book or paper title (no italics — formatting handled by
        the renderer).
      year: Publication year + edition note ("2005 (2nd ed.)" or
        "1990 — Proc. SPIE 1221, pp. 2–25").
      publisher: Publishing house or journal abbreviation.
      kind: "Cited" (in physics-module docstrings + SPEC.md Appendix B)
        or "Supplementary" (canonical reading, not used directly).
      used_for: Short topic / module reference. ≤ 6 words for table
        legibility on narrow viewports.
    """
    authors: str
    title: str
    year: str
    publisher: str
    kind: str
    used_for: str


# 13 primary references — every entry is cited in at least one physics-
# module docstring and listed in SPEC.md Appendix B. Order follows the
# rough flow of the chain: source/optics → propagation → atmosphere →
# turbulence → blooming → spot/PIB → burn-through → safety → engineering.
PRIMARY_REFERENCES: tuple[BibliographyEntry, ...] = (
    BibliographyEntry(
        authors="Andrews, L. C. & Phillips, R. L.",
        title="Laser Beam Propagation through Random Media",
        year="2005 (2nd ed.)",
        publisher="SPIE Press",
        kind="Cited",
        used_for="M4, M5, M6, M7 — propagation",
    ),
    BibliographyEntry(
        authors="Siegman, A. E.",
        title="Lasers",
        year="1986",
        publisher="University Science Books",
        kind="Cited",
        used_for="M1 beam quality; M7 Gaussian propagation",
    ),
    BibliographyEntry(
        authors="Born, M. & Wolf, E.",
        title="Principles of Optics",
        year="1999 (7th ed.)",
        publisher="Cambridge Univ. Press",
        kind="Cited",
        used_for="M7 diffraction, PIB on bucket",
    ),
    BibliographyEntry(
        authors="Gebhardt, F. G.",
        title="Twenty-five years of thermal blooming: an overview",
        year="1990 — Proc. SPIE 1221, pp. 2–25",
        publisher="SPIE",
        kind="Cited",
        used_for="M6 blooming Strehl + N_D prefactor",
    ),
    BibliographyEntry(
        authors="Gebhardt, F. G.",
        title="High-power laser propagation",
        year="1976 — Applied Optics 15(6), 1479–1493",
        publisher="OSA",
        kind="Cited",
        used_for="M6 thermal-blooming derivation",
    ),
    BibliographyEntry(
        authors="Carslaw, H. S. & Jaeger, J. C.",
        title="Conduction of Heat in Solids",
        year="1959 (2nd ed.)",
        publisher="Oxford Univ. Press",
        kind="Cited",
        used_for="M8 1-D transient PDE",
    ),
    BibliographyEntry(
        authors="Steen, W. M. & Mazumder, J.",
        title="Laser Material Processing",
        year="2010 (4th ed.)",
        publisher="Springer",
        kind="Cited",
        used_for="M8 absorptivity & failure criteria",
    ),
    BibliographyEntry(
        authors="ANSI Z136.1-2014",
        title="American National Standard for Safe Use of Lasers",
        year="2014",
        publisher="Laser Inst. of America",
        kind="Cited",
        used_for="M9 MPE, NOHD, laser class",
    ),
    BibliographyEntry(
        authors="IEC 60825-1:2014",
        title="Safety of laser products — Part 1: Equipment classification",
        year="2014",
        publisher="International Electrotechnical Commission",
        kind="Cited",
        used_for="M9 laser-class boundaries",
    ),
    BibliographyEntry(
        authors="Kruse, P. W., McGlauchlin, L. D. & McQuistan, R. B.",
        title="Elements of Infrared Technology",
        year="1962",
        publisher="Wiley",
        kind="Cited",
        used_for="M4 aerosol-extinction formula",
    ),
    BibliographyEntry(
        authors="McClatchey, R. A. et al.",
        title="Optical Properties of the Atmosphere (AFCRL-TR-72-0497)",
        year="1972",
        publisher="Air Force Cambridge Research Laboratories",
        kind="Cited",
        used_for="M4 molecular-absorption baselines (α_mol)",
    ),
    BibliographyEntry(
        authors="Hufnagel, R. E. (1974) & Valley, G. C. (1980)",
        title="Hufnagel-Valley turbulence profile (combined model)",
        year="1974 / 1980",
        publisher="OSA",
        kind="Cited",
        used_for="M5 Cn² altitude profile",
    ),
    BibliographyEntry(
        authors="Perram, G. P. et al.",
        title="An Introduction to Laser Weapon Systems",
        year="2010",
        publisher="Directed Energy Professional Society",
        kind="Cited",
        used_for="M7 spot conventions; M10 power/thermal",
    ),
)


# 10 supplementary references — canonical books in the surrounding
# fields, useful for users who want to study the physics deeper. Each
# title independently verified via a 2026-04-28 web search against the
# publisher catalogues (Springer, Wiley, Cambridge, SPIE, Dover,
# Academic Press / Elsevier, McGraw-Hill).
SUPPLEMENTARY_REFERENCES: tuple[BibliographyEntry, ...] = (
    BibliographyEntry(
        authors="Zohuri, B.",
        title="Directed Energy Weapons: Physics of High Energy Lasers (HEL)",
        year="2016",
        publisher="Springer",
        kind="Supplementary",
        used_for="Full HEL system text — companion to Perram",
    ),
    BibliographyEntry(
        authors="Saleh, B. E. A. & Teich, M. C.",
        title="Fundamentals of Photonics",
        year="2019 (3rd ed.)",
        publisher="Wiley",
        kind="Supplementary",
        used_for="Foundational laser & photonics",
    ),
    BibliographyEntry(
        authors="Tatarski, V. I.",
        title="Wave Propagation in a Turbulent Medium",
        year="1961 (Dover reprint 2016)",
        publisher="Dover",
        kind="Supplementary",
        used_for="Foundational turbulence theory",
    ),
    BibliographyEntry(
        authors="Ishimaru, A.",
        title="Wave Propagation and Scattering in Random Media",
        year="1978 / IEEE reprint 1997",
        publisher="Academic Press / IEEE Press",
        kind="Supplementary",
        used_for="Random-media scattering theory",
    ),
    BibliographyEntry(
        authors="Goodman, J. W.",
        title="Statistical Optics",
        year="2015 (2nd ed.)",
        publisher="Wiley",
        kind="Supplementary",
        used_for="Probability basis for turbulence statistics",
    ),
    BibliographyEntry(
        authors="Goodman, J. W.",
        title="Introduction to Fourier Optics",
        year="2017 (4th ed.)",
        publisher="Macmillan Learning",
        kind="Supplementary",
        used_for="Beam diffraction & propagation foundations",
    ),
    BibliographyEntry(
        authors="Modest, M. F.",
        title="Radiative Heat Transfer",
        year="2021 (4th ed.)",
        publisher="Academic Press",
        kind="Supplementary",
        used_for="M8 absorptivity & blackbody emission deeper",
    ),
    BibliographyEntry(
        authors="Smith, W. J.",
        title="Modern Optical Engineering",
        year="2007 (4th ed.)",
        publisher="SPIE Press",
        kind="Supplementary",
        used_for="Optical-system design",
    ),
    BibliographyEntry(
        authors="Thomas, G. E. & Stamnes, K.",
        title="Radiative Transfer in the Atmosphere and Ocean",
        year="2017 (2nd ed.)",
        publisher="Cambridge Univ. Press",
        kind="Supplementary",
        used_for="M4 atmospheric absorption deeper",
    ),
    BibliographyEntry(
        authors="Bass, M. et al. (eds.)",
        title="Handbook of Optics (5 vols.)",
        year="2009 (3rd ed.)",
        publisher="McGraw-Hill",
        kind="Supplementary",
        used_for="Encyclopedic optics reference",
    ),
)


# Combined display order — primary first, supplementary second.
ALL_REFERENCES: tuple[BibliographyEntry, ...] = (
    PRIMARY_REFERENCES + SUPPLEMENTARY_REFERENCES
)


__all__ = [
    "BibliographyEntry",
    "PRIMARY_REFERENCES",
    "SUPPLEMENTARY_REFERENCES",
    "ALL_REFERENCES",
]
