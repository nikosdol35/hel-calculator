"""Validation tests for M9 NOHD per SPEC.md §3 M9.

Four cases pinned in SPEC §3 M9:
  - test_m9_retinal_band_baseline  (Band A at 1.07 µm, 2% tolerance)
  - test_m9_eyesafer_band          (Band B at 1.55 µm, 5% tolerance;
                                    SPEC's '~9 m' is a rounded shorthand
                                    for the formula value 7.97 m; test
                                    pins to the formula)
  - test_m9_ratio_sqrt2            (structural: the exact algebraic
                                    invariant is on the pre-aperture
                                    form, float-tight)
  - test_m9_chronic_viewing        (Band A saturation at t_exp > 10 s)"""

import math

import pytest

from physics import m9_nohd


def _inputs(**overrides):
    """Build a neutral M9 input dict; tests override the keys they
    care about. Defaults are the SPEC §3 M9 retinal-baseline values."""
    base = {
        "P0": 1.0,
        "D": 0.001,
        "theta_diff": 1.0e-3,
        "wavelength": 1.07e-6,
        "t_exp": 0.25,
    }
    base.update(overrides)
    return base


def test_m9_retinal_band_baseline():
    """SPEC §3 M9 'test_m9_retinal_band_baseline'. Band A formula at
    1.07 µm and t_exp=0.25 s.

    Hand-check:
        MPE = 1.8e-3 · 0.25^(-1/4) · 10⁴ = 1.8e-3 · 1.4142 · 10⁴
            = 25.46 W/m²  (SPEC expects ~25.5)
        NOHD_tophat    = 1000·√(4/(π·25.46)) − 1 = 222.6 m  (~223)
        NOHD_gausspeak = 1000·√(8/(π·25.46)) − 1 = 315.2 m  (~315)
    """
    result = m9_nohd.compute(_inputs())
    assert result["MPE"] == pytest.approx(25.46, rel=0.02)
    assert result["NOHD_tophat"] == pytest.approx(222.6, rel=0.02)
    assert result["NOHD_gausspeak"] == pytest.approx(315.2, rel=0.02)
    # HEL P0 > 500 mW guarantees Class 4. This test uses P0=1 W which is
    # just above threshold but still Class 4 per SPEC §3 M9.
    assert result["laser_class"] == "Class 4"


def test_m9_eyesafer_band():
    """SPEC §3 M9 'test_m9_eyesafer_band'. Band B at 1.55 µm.

    Hand-check:
        MPE = 0.56 · 0.25^(-3/4) · 10⁴ = 0.56 · 2.8284 · 10⁴
            = 15839 W/m²  (SPEC pins this value)
        NOHD_tophat = 1000·√(4/(π·15839)) − 1 = 7.97 m

    SPEC says '~9 m'; the formula value is 7.97 m. The 1 m aperture
    correction (D/θ = 0.001/1e-3) accounts for the 12% gap — the
    formula is correct; '~9' is a rounded shorthand for the raw
    sqrt term (8.97 m). Test pins the formula value."""
    result = m9_nohd.compute(_inputs(wavelength=1.55e-6))
    assert result["MPE"] == pytest.approx(15839.0, rel=0.01)
    assert result["NOHD_tophat"] == pytest.approx(7.97, rel=0.05)
    # SPEC-stated qualitative relationship: Band B NOHD is much smaller
    # than Band A — by two orders of magnitude in MPE, ~one in NOHD.
    baseline = m9_nohd.compute(_inputs(wavelength=1.07e-6))
    assert result["NOHD_tophat"] < 0.1 * baseline["NOHD_tophat"]


def test_m9_ratio_sqrt2():
    """SPEC §3 M9 'test_m9_ratio_sqrt2'. The √2 separation between the
    Gaussian-peak and top-hat NOHD conventions comes from the sqrt(8)
    vs sqrt(4) ratio inside the range term. The aperture correction
    D/θ_diff appears identically in both, so the ratio of the RAW
    terms is exactly √2 — the invariant to test at float tolerance.

    For realistic HEL inputs (D=0.10, θ=13 µrad) the aperture term is
    large, so the ratio of the final NOHDs is only approximately √2;
    the algebraic identity is on the pre-aperture form."""
    result = m9_nohd.compute(_inputs(
        P0=3000.0, D=0.10, theta_diff=1.3e-5, wavelength=1.07e-6,
    ))
    d_over_theta = 0.10 / 1.3e-5
    raw_tophat = result["NOHD_tophat"] + d_over_theta
    raw_gausspeak = result["NOHD_gausspeak"] + d_over_theta
    assert raw_gausspeak / raw_tophat == pytest.approx(math.sqrt(2.0), rel=1e-12)

    # And the actual-NOHD ratio approaches √2 from above; the deviation
    # comes from the aperture term D/θ surviving unchanged under both
    # conventions. For these inputs D/θ = 7.7 km on a ~940 km raw range
    # → ~0.24% deviation. Assert "close to √2, within 1%" to keep this
    # as a sanity check rather than a structural redundancy.
    assert result["NOHD_gausspeak"] / result["NOHD_tophat"] == pytest.approx(
        math.sqrt(2.0), rel=1e-2
    )


def test_m9_chronic_viewing():
    """SPEC §3 M9 'test_m9_chronic_viewing'. Band A MPE saturates at
    the chronic limit 1.0e-3 W/cm² = 10 W/m² for t_exp > 10 s."""
    result = m9_nohd.compute(_inputs(t_exp=100.0))
    assert result["MPE"] == pytest.approx(10.0, rel=0.02)


def test_m9_flags_convention_always():
    """CLAUDE §4.5 always-on: the NOHD convention choice is pinned in
    CLAUDE §7.1 as immutable and must be surfaced every call."""
    result = m9_nohd.compute(_inputs())
    flags = " | ".join(result["assumptions_flagged"])
    assert "top-hat" in flags
    assert "Gaussian-peak" in flags


def test_m9_flags_mpe_uncertainty_always():
    """CLAUDE §4.5 + SPEC §10.3: the ANSI MPE values are flagged as
    requiring cross-check against the revision in force at release,
    and the no-C_A design choice is disclosed."""
    result = m9_nohd.compute(_inputs())
    flags = " | ".join(result["assumptions_flagged"])
    assert "§10.3" in flags
    assert "C_A" in flags


def test_m9_flags_reduced_confidence_off_validated_set():
    """ARCH §4.3: wavelength outside {1.06, 1.07, 1.55, 2.05 µm}
    triggers the reduced-confidence flag."""
    result = m9_nohd.compute(_inputs(wavelength=1.30e-6))
    flags = " | ".join(result["assumptions_flagged"])
    assert "reduced confidence" in flags


def test_m9_flags_no_reduced_confidence_on_validated_wavelength():
    """Conversely: a wavelength in the validated set must NOT fire
    the reduced-confidence flag."""
    result = m9_nohd.compute(_inputs(wavelength=2.05e-6))
    flags = " | ".join(result["assumptions_flagged"])
    assert "reduced confidence" not in flags


def test_m9_hel_geometry_class4():
    """Realistic HEL geometry (from M1 validation case 2): P0=3 kW
    gives Class 4 and a kilometre-scale NOHD."""
    result = m9_nohd.compute(_inputs(
        P0=3000.0, D=0.10, theta_diff=1.63e-5, wavelength=1.07e-6,
    ))
    assert result["laser_class"] == "Class 4"
    # Kilometre-scale NOHD for an HEL at moderate beam quality:
    # (1/1.63e-5) · √(4·3000/(π·25.46)) − 0.10/1.63e-5
    # = 61350 · 12.24 − 6135 ≈ 744 km raw − 6 km aperture ≈ 738 km.
    assert result["NOHD_tophat"] > 100_000.0
    assert result["NOHD_gausspeak"] > result["NOHD_tophat"]


def test_m9_band_b_chronic_limit():
    """Band B (eye-safer) also has a chronic plateau at 0.1 W/cm²
    = 1000 W/m² for t_exp > 10 s."""
    result = m9_nohd.compute(_inputs(wavelength=1.55e-6, t_exp=100.0))
    assert result["MPE"] == pytest.approx(1000.0, rel=0.02)


def test_m9_zero_theta_diff_raises():
    """Input validation: θ_diff ≤ 0 would divide by zero in the NOHD
    range term — must raise."""
    with pytest.raises(ValueError, match="theta_diff"):
        m9_nohd.compute(_inputs(theta_diff=0.0))


def test_m9_out_of_range_t_exp_raises():
    """Input validation: t_exp outside Panel F sanity range [0.25, 100]
    raises."""
    with pytest.raises(ValueError, match="t_exp"):
        m9_nohd.compute(_inputs(t_exp=0.1))
    with pytest.raises(ValueError, match="t_exp"):
        m9_nohd.compute(_inputs(t_exp=200.0))


def test_m9_below_band_a_raises():
    """Input validation: wavelength below Band A (< 0.4 µm UV) is
    outside v1 scope and raises — no placeholder fallback."""
    with pytest.raises(ValueError, match="wavelength"):
        m9_nohd.compute(_inputs(wavelength=0.300e-6))


def test_m9_low_power_classification():
    """Class 4 threshold is 500 mW per SPEC §3 M9. Below that, the
    classification walks down through 3B / 3R / 1M / 1. These branches
    are unused for HEL but are present to keep the classifier honest
    and the safety-case context correct for unit tests."""
    # Just above 500 mW → Class 4.
    assert m9_nohd.compute(_inputs(P0=0.51))["laser_class"] == "Class 4"
    # Between 5 mW and 500 mW → Class 3B.
    assert m9_nohd.compute(_inputs(P0=0.1))["laser_class"] == "Class 3B"
    # Between 1 mW and 5 mW → Class 3R.
    assert m9_nohd.compute(_inputs(P0=0.002))["laser_class"] == "Class 3R"
