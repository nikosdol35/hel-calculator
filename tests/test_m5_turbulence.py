"""Validation tests for M5 turbulence per SPEC.md §3 M5.

Five cases pinned in SPEC §3 M5:
  - test_m5_r0_uniform_cn2           (2% tolerance)
  - test_m5_w_turb_5km               (2% tolerance)
  - test_m5_spherical_vs_plane_ratio (structural, 0.1% — prevents regression
                                       to plane-wave r₀ form per CLAUDE §7.1)
  - test_m5_r0_at_1500m              (2% tolerance)
  - test_m5_hv_5_7_ground_level      (2% tolerance — added SPEC v1.5; closes
                                       the HV_5_7 enum against an actual
                                       implementation, not NotImplementedError)

plus supplementary non-SPEC module-level tests (flags, input validation,
structural HV↔constant equivalence at h=0)."""

import math

import pytest

from physics import m5_turbulence


def _uniform_cn2_inputs(canonical_inputs, **overrides):
    """Helper: canonical_inputs overridden for uniform-Cn² test cases."""
    base = {
        **canonical_inputs,
        "cn2_model": "constant",
        "Cn2_value": 1e-14,
        "wavelength": 1.07e-6,
        "R_slant": 5000,
        "H_e": 0,
        "H_t": 0,
    }
    base.update(overrides)
    return base


def test_m5_r0_uniform_cn2(canonical_inputs):
    """SPEC §3 M5 'test_m5_r0_uniform_cn2'. Expected r0_sph ≈ 0.0345 m."""
    result = m5_turbulence.compute(_uniform_cn2_inputs(canonical_inputs))
    assert result["r0_sph"] == pytest.approx(0.0345, rel=0.02)


def test_m5_w_turb_5km(canonical_inputs):
    """SPEC §3 M5 'test_m5_w_turb_5km'. Expected w_turb ≈ 0.0494 m."""
    result = m5_turbulence.compute(_uniform_cn2_inputs(canonical_inputs))
    assert result["w_turb"] == pytest.approx(0.0494, rel=0.02)


def test_m5_spherical_vs_plane_ratio(canonical_inputs):
    """SPEC §3 M5 'test_m5_spherical_vs_plane_ratio'. For uniform Cn²,
    r0_sph / r0_plane = (3/8)^(-3/5) ≈ 1.801. Structural regression guard
    against accidental reversion to plane-wave r₀ form (CLAUDE §7.1)."""
    inputs = _uniform_cn2_inputs(canonical_inputs)
    result = m5_turbulence.compute(inputs)

    k = 2.0 * math.pi / inputs["wavelength"]
    L = inputs["R_slant"]
    Cn2 = inputs["Cn2_value"]
    r0_plane = (0.423 * k ** 2 * Cn2 * L) ** (-3.0 / 5.0)

    ratio = result["r0_sph"] / r0_plane
    expected_ratio = (3.0 / 8.0) ** (-3.0 / 5.0)
    assert ratio == pytest.approx(expected_ratio, rel=0.001)


def test_m5_r0_at_1500m(canonical_inputs):
    """SPEC §3 M5 'test_m5_r0_at_1500m'. Expected r0_sph ≈ 0.0711 m and
    w_turb ≈ 0.00719 m at R_slant = 1500 m."""
    inputs = _uniform_cn2_inputs(canonical_inputs, R_slant=1500)
    result = m5_turbulence.compute(inputs)
    assert result["r0_sph"] == pytest.approx(0.0711, rel=0.02)
    assert result["w_turb"] == pytest.approx(0.00719, rel=0.02)


def test_m5_flags_spherical_and_engineering_form(canonical_inputs):
    """CLAUDE §4.5 / §7.1: M5 always flags both the spherical-wave r₀
    choice and the engineering w_turb form."""
    result = m5_turbulence.compute(_uniform_cn2_inputs(canonical_inputs))
    flags = " | ".join(result["assumptions_flagged"])
    assert "spherical-wave" in flags
    assert "engineering form" in flags


def test_m5_unsupported_cn2_model_raises(canonical_inputs):
    """SPEC §3 M5 enumerates 'HV_day' but only 'constant' and 'HV_5_7' are
    implemented as of SPEC v1.5; the unimplemented branch must raise
    NotImplementedError (not silently fall through).

    (This test previously used 'HV_5_7'; SPEC v1.5 implements HV_5_7 with
    a dedicated validation case, so the coverage moves to the next
    enumerated-but-unimplemented model.)"""
    inputs = _uniform_cn2_inputs(canonical_inputs, cn2_model="HV_day")
    with pytest.raises(NotImplementedError, match="HV_day"):
        m5_turbulence.compute(inputs)


def test_m5_out_of_range_Cn2_raises(canonical_inputs):
    """Input validation: Cn2_value below SPEC §3 M5 range raises ValueError."""
    inputs = _uniform_cn2_inputs(canonical_inputs, Cn2_value=1e-20)
    with pytest.raises(ValueError, match="Cn2_value"):
        m5_turbulence.compute(inputs)


# --- SPEC §3 M5.5: HV_5_7 ground-level slant (SPEC v1.5) ---------------------


def _hv_5_7_inputs(canonical_inputs, **overrides):
    """Helper: canonical_inputs pinned to the SPEC §3 M5.5 HV_5_7 case
    (Cn2_ground=1.7e-14, v_HV=21, λ=1.07 µm, R_slant=5 km, H_e=H_t=0)."""
    base = {
        **canonical_inputs,
        "cn2_model": "HV_5_7",
        "Cn2_ground": 1.7e-14,
        "v_HV": 21,
        "wavelength": 1.07e-6,
        "R_slant": 5000,
        "H_e": 0,
        "H_t": 0,
    }
    base.update(overrides)
    return base


def test_m5_hv_5_7_ground_level(canonical_inputs):
    """SPEC §3 M5 'test_m5_hv_5_7_ground_level'. With H_e=H_t=0 the HV-5/7
    profile reduces analytically to Cn²(0) = Cn2_ground + 2.7e-16 =
    1.727e-14 m^(-2/3), so r0_sph ≈ 0.0249 m and w_turb ≈ 0.0685 m.

    Tolerance: 2% (matches SPEC §3 M5 first-principles tolerance)."""
    result = m5_turbulence.compute(_hv_5_7_inputs(canonical_inputs))
    assert result["r0_sph"] == pytest.approx(0.0249, rel=0.02)
    assert result["w_turb"] == pytest.approx(0.0685, rel=0.02)


def test_m5_hv_5_7_flags_hv_profile(canonical_inputs):
    """CLAUDE §4.5: HV_5_7 must flag the profile choice so Panel 4 can
    surface the assumption to the operator (matches what the 'constant'
    branch does for the spherical/engineering choices)."""
    result = m5_turbulence.compute(_hv_5_7_inputs(canonical_inputs))
    flags = " | ".join(result["assumptions_flagged"])
    assert "HV-5/7" in flags


def test_m5_hv_5_7_matches_constant_at_ground(canonical_inputs):
    """Structural regression guard: HV_5_7 at H_e=H_t=0 must equal
    'constant' with Cn2_value = Cn2_ground + 2.7e-16 to within 0.1%.
    Catches regression to plane-wave integration, wrong profile-summation
    order, or an integrator that drifts past the 2% SPEC tolerance.

    SPEC §3 M5 v1.5 validation-case rationale."""
    hv_inputs = _hv_5_7_inputs(canonical_inputs)
    const_inputs = _uniform_cn2_inputs(
        canonical_inputs,
        Cn2_value=hv_inputs["Cn2_ground"] + 2.7e-16,
        R_slant=hv_inputs["R_slant"],
        wavelength=hv_inputs["wavelength"],
    )
    hv = m5_turbulence.compute(hv_inputs)
    const = m5_turbulence.compute(const_inputs)
    assert hv["r0_sph"] == pytest.approx(const["r0_sph"], rel=0.001)
    assert hv["w_turb"] == pytest.approx(const["w_turb"], rel=0.001)
    assert hv["Cn2_integrated"] == pytest.approx(const["Cn2_integrated"], rel=0.001)
