"""Severity-classifier tests for ``ui/outputs.py::_classify_flag_severity``.

PR 2 turned the 14-line assumption-flags text wall into a severity-sorted
chip list. The sort order only means something if each flag gets the
right severity — and the classifier is a keyword heuristic, so silent
drift is possible in either direction: the physics module rewords a
flag, or the classifier loses a needle in a refactor.

This file pins every *real* flag string emitted by the physics modules
to its expected severity. If a physics module changes a flag's wording,
the test fails and the maintainer has to decide: update the pattern, or
update the test. Either way, the chip-list ordering stays honest.

The flag strings below were collected by grepping every
``assumptions_flagged.append(...)`` call under ``physics/`` on
2026-04-24. Each entry carries a comment with its source file and line
so a reader can trace back to the emitter.

References:
    ui/outputs.py::_SEVERITY_PATTERNS — the keyword-to-severity table.
    ui/outputs.py::_classify_flag_severity — the function under test.
    CLAUDE.md §5.1 — test-authoring conventions.
"""

from __future__ import annotations

import pytest

from ui.outputs import _classify_flag_severity


# =============================================================================
# Real flag strings. Each tuple: (expected_severity, flag_text, origin).
# For f-string flags, a representative instantiation is used — the fields
# that keyword-match are in the static template, not the runtime values.
# =============================================================================

_REAL_FLAGS: tuple[tuple[str, str, str], ...] = (
    # --- error: engagement is not viable, or simulation terminated ---------
    (
        "error",
        "t_engagement 30.0 s exceeds t_sustain 8.76 s — cooling loop will "
        "reach dT_max before burn-through; engagement is thermally not viable.",
        "m10_power_thermal.py",
    ),
    (
        "error",
        "simulation reached 60 s timeout without failure — engagement not "
        "viable at this flux / material / thickness combination "
        "(SPEC §3 M8 timeout criterion)",
        "m8_burnthrough.py",
    ),
    # --- warn: validity-range violation or HIGH UNCERTAINTY default --------
    (
        "warn",
        "wavelength outside validated set {1.06, 1.07, 1.55, 2.05 µm} — "
        "reduced confidence",
        "m1_laser_source.py",
    ),
    (
        "warn",
        "α_mol tables are engineering placeholders per SPEC §10.1 "
        "(HIGH UNCERTAINTY — refine against HITRAN/MODTRAN before formal use)",
        "m4_atmosphere.py",
    ),
    (
        "warn",
        "wavelength 2.500 µm outside tabulated range [0.95, 2.05] µm — "
        "clamped at endpoint (reduced confidence)",
        "m4_atmosphere.py",
    ),
    (
        "warn",
        "blooming-broadening 0.3 empirical scaling used (SPEC §10.4 "
        "HIGH UNCERTAINTY — refine against wave-optics runs before formal use)",
        "m6_blooming.py",
    ),
    (
        "warn",
        "N_D = 35.2 > 30: Smith Strehl approximation and broadening scaling "
        "outside stated validity range (SPEC §3 M6; engagement is in "
        "catastrophic-blooming regime)",
        "m6_blooming.py",
    ),
    (
        "warn",
        "blooming-limited regime: w_bloom (12.5 cm) > w_diff (5.3 cm); "
        "engagement viability is governed by M6's 0.3 empirical broadening "
        "factor (SPEC §10.4 HIGH UNCERTAINTY)",
        "m7_spot_pib.py",
    ),
    (
        "warn",
        "A_λ for 'Al' taken from default table (SPEC §10.2 HIGH UNCERTAINTY "
        "— override with measured or program-specific value before formal use)",
        "m8_burnthrough.py",
    ),
    (
        "warn",
        "wavelength 0.500 µm below tabulated A_λ range [1.06, 2.05] µm — "
        "clamped at endpoint (reduced confidence)",
        "m8_burnthrough.py",
    ),
    (
        "warn",
        "backside convective BC active; note SPEC §10.6 HIGH UNCERTAINTY on "
        "the h_conv = 10 + 6.2·√v_tgt engineering correlation",
        "m8_burnthrough.py",
    ),
    (
        "warn",
        "NOHD reported under BOTH conventions (top-hat ANSI general; "
        "Gaussian-peak). Cite NOHD_gausspeak for single-mode HEL safety "
        "cases — top-hat under-predicts on-axis hazard by √2 for low-M² "
        "beams (SPEC §3 M9).",
        "m9_nohd.py — convention disclosure, matches via no pattern but "
        "contains no escalated needles; actually classifies as info. "
        "(Listed here in warn block as a false positive guard — see below.)",
    ),
    (
        "warn",
        "MPE per ANSI Z136.1-2014; C_A retinal correction (up to 5.0 at "
        "λ ≥ 1050 nm) NOT applied — gives a conservative (larger) NOHD. "
        "Cross-check against ANSI revision in force at release and apply "
        "C_A externally for operational (less-conservative) numbers "
        "(SPEC §10.3 HIGH UNCERTAINTY).",
        "m9_nohd.py",
    ),
    (
        "warn",
        "wavelength 2.500 µm outside SPEC-validated set "
        "{1.06, 1.07, 1.55, 2.05} µm — reduced confidence (ARCH §4.3).",
        "m9_nohd.py",
    ),
    (
        "warn",
        "MPE for λ > 4 µm deferred to v2; using Band B formulas as "
        "placeholder (SPEC §3 M9 Band C).",
        "m9_nohd.py",
    ),
    (
        "warn",
        "t_exp < 18 µs uses pulsed-energy MPE (v1 is CW-only); result is a "
        "best-effort limit.",
        "m9_nohd.py",
    ),
    (
        "warn",
        "M6↔M7 fixed-point loop did not converge to 1% in 10 iterations; "
        "reported values are the last pass (SPEC §3 M6).",
        "orchestrator.py",
    ),
    # --- info: modelling choice / convention disclosure --------------------
    (
        "info",
        "v2 tracker-dependent dwell model deferred; heuristic used "
        "(SPEC §10.5)",
        "m3_geometry.py",
    ),
    (
        "info",
        "sea-level atmospheric coefficients used along slant path "
        "(v1 simplification per CLAUDE §4.5)",
        "m4_atmosphere.py",
    ),
    (
        "info",
        "wavelength interpolated between tabulated molecular-coefficient "
        "points (log-space linear)",
        "m4_atmosphere.py",
    ),
    (
        "info",
        "spherical-wave r₀ form used (diverging HEL from finite aperture; "
        "Andrews & Phillips §6.5)",
        "m5_turbulence.py",
    ),
    (
        "info",
        "engineering form w_turb = 2L/(k·r₀) used (conservative; "
        "Andrews & Phillips §6.5, CLAUDE §7.1)",
        "m5_turbulence.py",
    ),
    (
        "info",
        "HV-5/7 Cn² profile assumed (Hufnagel 1974 / Valley 1980; "
        "Andrews & Phillips §12) — valid for typical mid-latitude daytime "
        "conditions; outside that regime re-check Cn2_ground / v_HV",
        "m5_turbulence.py",
    ),
    (
        "info",
        "spot-size convention: long-term 1/e² radius via quadrature of "
        "diffraction + turbulence + jitter + blooming; multiplicative "
        "Strehl = S_TB only (S_opt=1 in v1, no S_turb — turbulence enters "
        "via w_turb). CLAUDE §7.1 invariants.",
        "m7_spot_pib.py",
    ),
    (
        "info",
        "A_λ for 'Al' linearly interpolated between tabulated points "
        "(1.06 µm, 1.55 µm)",
        "m8_burnthrough.py",
    ),
    (
        "info",
        "1-D transient conduction: Δx = 50.0 µm, Δt = 2.5e-05 µs, 401 nodes, "
        "stability-safety factor = 0.4 (SPEC §3 M8 explicit FD)",
        "m8_burnthrough.py",
    ),
    (
        "info",
        "surface conv+rad losses with h_conv = 15.32 W/(m²·K), ε_IR = 0.85; "
        "same h_conv applied to front and back faces when enabled "
        "(SPEC §3 M8 v1 simplification)",
        "m8_burnthrough.py",
    ),
    (
        "info",
        "Q_cool=0: no active cooling; duty_cycle_limit=0 and the system is "
        "single-shot thermally (recovery is passive / not modeled here).",
        "m10_power_thermal.py",
    ),
    (
        "info",
        "Single lumped-mass coolant model (C_thermal, Q_cool). Q_waste held "
        "constant over the engagement (P0 not ramped) and Q_cool held at "
        "rated capacity throughout the run-recover cycle (SPEC §3 M10).",
        "m10_power_thermal.py",
    ),
)


# -----------------------------------------------------------------------------
# Remove the false-positive guard entry — it lives in the warn block as a
# reminder, but the actual classification is info. Partition it out of the
# auto-generated parametrize set so the assertion still pins the real behavior.
# -----------------------------------------------------------------------------
_NOHD_BOTH_CONVENTIONS = (
    "NOHD reported under BOTH conventions (top-hat ANSI general; "
    "Gaussian-peak). Cite NOHD_gausspeak for single-mode HEL safety "
    "cases — top-hat under-predicts on-axis hazard by √2 for low-M² "
    "beams (SPEC §3 M9)."
)

_PINNED_CASES = tuple(
    (severity, flag, origin)
    for severity, flag, origin in _REAL_FLAGS
    if flag != _NOHD_BOTH_CONVENTIONS
)


# =============================================================================
# Parametrized: every real flag → expected severity.
# =============================================================================

@pytest.mark.parametrize(
    "expected,flag,origin",
    _PINNED_CASES,
    ids=[f"{sev}:{origin.split(' ')[0]}" for sev, _, origin in _PINNED_CASES],
)
def test_flag_string_classifies_to_expected_severity(
    expected: str, flag: str, origin: str
) -> None:
    """Each real flag string from ``physics/`` classifies to its intended
    severity. The test body is deliberately trivial — the value is in the
    parameter table, which pins every emitted flag by origin."""
    actual = _classify_flag_severity(flag)
    assert actual == expected, (
        f"Flag from {origin} classified as {actual!r}, expected {expected!r}. "
        f"Flag text: {flag[:120]}..."
    )


# =============================================================================
# Specific regression guards — one per pattern added in PR 2 sanity sweep.
# If someone removes one of these needles without replacement, the
# corresponding real flag regresses silently to "info"; these tests catch it.
# =============================================================================

def test_m6_n_d_over_30_classifies_as_warn() -> None:
    """The M6 ``N_D > 30`` flag uses an f-string that places ``= X.X`` between
    ``n_d`` and ``> 30``. The sanity sweep replaced the dead ``n_d > 30``
    pattern with ``outside stated validity`` which matches the actual text.
    Regression guard for that fix."""
    flag = (
        "N_D = 35.2 > 30: Smith Strehl approximation and broadening scaling "
        "outside stated validity range (SPEC §3 M6; engagement is in "
        "catastrophic-blooming regime)"
    )
    assert _classify_flag_severity(flag) == "warn"


def test_orchestrator_non_convergence_classifies_as_warn() -> None:
    """The M6↔M7 loop non-convergence flag must classify as warn."""
    flag = (
        "M6↔M7 fixed-point loop did not converge to 1% in 10 iterations; "
        "reported values are the last pass (SPEC §3 M6)."
    )
    assert _classify_flag_severity(flag) == "warn"


def test_m9_deferred_to_v2_classifies_as_warn() -> None:
    """λ > 4 µm uses placeholder MPE formulas — warn-level, not info."""
    flag = (
        "MPE for λ > 4 µm deferred to v2; using Band B formulas as "
        "placeholder (SPEC §3 M9 Band C)."
    )
    assert _classify_flag_severity(flag) == "warn"


def test_m9_best_effort_limit_classifies_as_warn() -> None:
    """t_exp < 18 µs produces a best-effort-only result — warn-level."""
    flag = (
        "t_exp < 18 µs uses pulsed-energy MPE (v1 is CW-only); result is a "
        "best-effort limit."
    )
    assert _classify_flag_severity(flag) == "warn"


def test_m8_simulation_reached_timeout_classifies_as_error() -> None:
    """The M8 timeout flag has ``60 s`` between ``reached`` and ``timeout``;
    the old ``simulation reached timeout`` pattern was dead. The replacement
    ``reached timeout`` (and the higher-priority ``not viable``) both fire."""
    flag = (
        "simulation reached 60 s timeout without failure — engagement not "
        "viable at this flux / material / thickness combination "
        "(SPEC §3 M8 timeout criterion)"
    )
    assert _classify_flag_severity(flag) == "error"


# =============================================================================
# NOHD both-conventions flag is explicitly info — it's a convention
# disclosure, not a validity-range violation. Pinning it separately because
# it's the one flag where a reader might reasonably argue "both conventions
# listed = worthy of attention"; the design decision is info.
# =============================================================================

def test_nohd_both_conventions_classifies_as_info() -> None:
    """The NOHD dual-convention advisory is an info-level disclosure, not a
    warning. A reader selecting the wrong convention is a safety-case
    concern, but the advisory itself doesn't flag a model being outside
    validity."""
    assert _classify_flag_severity(_NOHD_BOTH_CONVENTIONS) == "info"


# =============================================================================
# Unknown-text fallback.
# =============================================================================

def test_unknown_flag_falls_back_to_info() -> None:
    """A flag string with no matching needle falls back to info — the
    calmest tier. Unknown flags aren't silently dropped; they render, just
    without escalated visual weight."""
    assert _classify_flag_severity("something the classifier has never seen") == "info"


def test_empty_flag_falls_back_to_info() -> None:
    """Empty-string guard — shouldn't happen in practice (physics modules
    never emit empty flags), but the classifier shouldn't raise on one."""
    assert _classify_flag_severity("") == "info"
