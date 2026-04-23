"""Validation tests for M7 spot size and power-in-the-bucket per
SPEC.md §3 M7.

Four cases pinned in SPEC §3 M7:
  - test_m7_pure_diffraction_5km     (2% tolerance)
  - test_m7_diff_plus_turb_5km       (2% tolerance)
  - test_m7_typical_c_uas_1500m      (2% tolerance; near-field
                                      regression guard against far-field
                                      asymptote — plan v0.6 bug)
  - test_m7_convention_consistency   (structural; guards against w vs σ
                                      convention mixing — plan v0.3/v0.4
                                      bugs)"""

import math

import pytest

from physics import m7_spot_pib


def _ideal_5km_inputs():
    """Reproduces SPEC §3 M7 Case-1/Case-2 baseline (P_exit=2550 W,
    w0=0.05, zR=7340, 5 km, λ=1.07 µm). Case 1 overrides r0_sph=inf;
    Case 2 overrides r0_sph=0.0345."""
    return {
        "P_exit": 2550.0,
        "tau_atm": 1.0,
        "w0": 0.05,
        "zR": 7340.0,
        "M2": 1.0,
        "wavelength": 1.07e-6,
        "R_slant": 5000.0,
        "sigma_jit": 0.0,
        "r0_sph": math.inf,
        "S_TB": 1.0,
        "w_bloom": 0.0,
        "d_aim": 0.05,
    }


def test_m7_pure_diffraction_5km():
    """SPEC §3 M7 'test_m7_pure_diffraction_5km'. Pure exact-Gaussian
    diffraction at 5 km with all other contributions zero. Hand-check:
    w_diff = 0.05·√(1 + (5000/7340)²) = 0.0605 m; d_spot = 0.1210 m;
    PIB = 1 - exp(-2·0.025²/0.0605²) = 0.2894."""
    result = m7_spot_pib.compute(_ideal_5km_inputs())
    assert result["w_diff"] == pytest.approx(0.0605, rel=0.02)
    assert result["d_spot"] == pytest.approx(0.1210, rel=0.02)
    assert result["PIB_fraction"] == pytest.approx(0.289, rel=0.02)


def test_m7_diff_plus_turb_5km():
    """SPEC §3 M7 'test_m7_diff_plus_turb_5km'. Case 1 with r0_sph
    replaced by the M5 uniform-Cn² result at 5 km (0.0345 m). Hand-check:
    w_turb ≈ 0.0494 m, w_total ≈ 0.0781 m, PIB ≈ 0.185."""
    inputs = _ideal_5km_inputs()
    inputs["r0_sph"] = 0.0345
    result = m7_spot_pib.compute(inputs)
    assert result["w_turb"] == pytest.approx(0.0494, rel=0.02)
    assert result["w_total"] == pytest.approx(0.0781, rel=0.02)
    assert result["PIB_fraction"] == pytest.approx(0.185, rel=0.02)


def test_m7_typical_c_uas_1500m():
    """SPEC §3 M7 'test_m7_typical_c_uas_1500m' — THE NEAR-FIELD
    REGRESSION TEST. Guards against reversion to the far-field
    asymptote w_diff = M²·λ·L/(π·w₀), which at 1500 m would return
    w_diff ≈ 1.02 cm (a 5× under-prediction of spot size). The EXACT
    Gaussian formula returns w_diff ≈ 5.10 cm. Plan v0.6 bug."""
    inputs = {
        "P_exit": 1000.0,
        "tau_atm": 1.0,
        "w0": 0.05,
        "zR": 7340.0,
        "M2": 1.0,
        "wavelength": 1.07e-6,
        "R_slant": 1500.0,
        "sigma_jit": 0.0,
        "r0_sph": 0.0711,
        "S_TB": 1.0,
        "w_bloom": 0.0,
        "d_aim": 0.05,
    }
    result = m7_spot_pib.compute(inputs)

    # Exact-Gaussian value (correct):
    assert result["w_diff"] == pytest.approx(0.0510, rel=0.02)

    # Explicit assertion that we are NOT producing the far-field value:
    k = 2.0 * math.pi / inputs["wavelength"]
    w_diff_farfield = inputs["M2"] * inputs["wavelength"] * inputs["R_slant"] / (
        math.pi * inputs["w0"]
    )
    assert w_diff_farfield == pytest.approx(0.0102, rel=0.02)  # hand-check
    # 5× separation — trivially distinguishable at 2% tolerance.
    assert abs(result["w_diff"] - w_diff_farfield) / result["w_diff"] > 0.5

    assert result["PIB_fraction"] == pytest.approx(0.376, rel=0.02)


def test_m7_convention_consistency():
    """SPEC §3 M7 'test_m7_convention_consistency'. The w-convention
    PIB formula 1 − exp(−2R²/w²) and the σ-convention form
    1 − exp(−R²/(2σ²)) with σ = w/2 are algebraically identical.
    Likewise I_peak = 2P/(π·w²) = P/(2π·σ²). Verifying both at
    floating-point tolerance guards against silently wiring the wrong
    constant factor (plan v0.3/v0.4 bugs)."""
    inputs = _ideal_5km_inputs()
    inputs["r0_sph"] = 0.0345
    inputs["sigma_jit"] = 5e-6
    inputs["S_TB"] = 0.8
    result = m7_spot_pib.compute(inputs)

    w = result["w_total"]
    sigma = w / 2.0
    R = inputs["d_aim"] / 2.0

    pib_w = 1.0 - math.exp(-2.0 * R ** 2 / w ** 2)
    pib_sigma = 1.0 - math.exp(-R ** 2 / (2.0 * sigma ** 2))
    assert pib_w == pytest.approx(pib_sigma, rel=1e-12)
    assert result["PIB_fraction"] == pytest.approx(pib_w, rel=1e-12)

    P_delivered = inputs["P_exit"] * inputs["tau_atm"] * inputs["S_TB"]
    ipeak_w = 2.0 * P_delivered / (math.pi * w ** 2)
    ipeak_sigma = P_delivered / (2.0 * math.pi * sigma ** 2)
    assert ipeak_w == pytest.approx(ipeak_sigma, rel=1e-12)
    assert result["I_peak"] == pytest.approx(ipeak_w, rel=1e-12)


def test_m7_quadrature_independence():
    """Structural: w_total must satisfy w_total² = sum of squares of
    the four contributions. Regression guard against accidental linear
    addition (would overweight every term)."""
    inputs = _ideal_5km_inputs()
    inputs["r0_sph"] = 0.0345
    inputs["sigma_jit"] = 5e-6
    inputs["w_bloom"] = 0.02
    result = m7_spot_pib.compute(inputs)
    expected = math.sqrt(
        result["w_diff"] ** 2 + result["w_turb"] ** 2
        + result["w_jit"] ** 2 + inputs["w_bloom"] ** 2
    )
    assert result["w_total"] == pytest.approx(expected, rel=1e-12)


def test_m7_no_double_count_turbulence():
    """Structural: turbulence must enter ONLY via w_turb, never as a
    Strehl factor on top. Compare I_peak from {S_TB=1, r0_sph=finite}
    against I_peak from {S_TB=1, r0_sph=inf}: the only difference must
    come through w_total (i.e. the quadrature), not through a hidden
    turbulence-Strehl multiplier. Plan v0.4 bug."""
    base = _ideal_5km_inputs()
    with_turb = {**base, "r0_sph": 0.0345}
    without_turb = {**base, "r0_sph": math.inf}

    r_with = m7_spot_pib.compute(with_turb)
    r_without = m7_spot_pib.compute(without_turb)

    # If turbulence were being applied as a Strehl factor as well as
    # through w_turb, the ratio of I_peak values would differ from the
    # inverse ratio of w_total² values. Check they match exactly.
    expected_ratio = r_without["w_total"] ** 2 / r_with["w_total"] ** 2
    actual_ratio = r_with["I_peak"] / r_without["I_peak"]
    assert actual_ratio == pytest.approx(expected_ratio, rel=1e-12)


def test_m7_flags_convention_always():
    """CLAUDE §7.1: M7 always flags the spot-size / Strehl convention
    so the ledger records the choice explicitly."""
    result = m7_spot_pib.compute(_ideal_5km_inputs())
    flags = " | ".join(result["assumptions_flagged"])
    assert "long-term" in flags
    assert "S_opt=1" in flags


def test_m7_flags_blooming_limited_regime():
    """Conditional flag: when w_bloom > w_diff the engagement is
    blooming-limited and the 0.3 SPEC §10.4 HIGH UNCERTAINTY factor
    governs viability."""
    inputs = _ideal_5km_inputs()
    inputs["w_bloom"] = 0.20  # ≫ w_diff ≈ 0.06
    result = m7_spot_pib.compute(inputs)
    flags = " | ".join(result["assumptions_flagged"])
    assert "blooming-limited" in flags


def test_m7_zero_w0_raises():
    """Input validation: w0 ≤ 0 raises ValueError (would divide by
    zero in I_peak)."""
    inputs = _ideal_5km_inputs()
    inputs["w0"] = 0.0
    with pytest.raises(ValueError, match="w0"):
        m7_spot_pib.compute(inputs)


def test_m7_out_of_range_S_TB_raises():
    """Input validation: S_TB outside [0,1] raises ValueError."""
    inputs = _ideal_5km_inputs()
    inputs["S_TB"] = 1.5
    with pytest.raises(ValueError, match="S_TB"):
        m7_spot_pib.compute(inputs)
