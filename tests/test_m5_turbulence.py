"""Validation tests for M5 turbulence per SPEC.md §3 M5.

Four cases pinned in SPEC §3 M5:
  - test_m5_r0_uniform_cn2          (2% tolerance)
  - test_m5_w_turb_5km              (2% tolerance)
  - test_m5_spherical_vs_plane_ratio (structural, 0.1% — prevents regression
                                       to plane-wave r₀ form per CLAUDE §7.1)
  - test_m5_r0_at_1500m             (2% tolerance)"""

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
    """SPEC §3 M5 enumerates 'HV_5_7' but this commit ships only 'constant';
    the unimplemented branch must raise NotImplementedError (not silently
    fall through)."""
    inputs = _uniform_cn2_inputs(canonical_inputs, cn2_model="HV_5_7")
    with pytest.raises(NotImplementedError, match="HV_5_7"):
        m5_turbulence.compute(inputs)


def test_m5_out_of_range_Cn2_raises(canonical_inputs):
    """Input validation: Cn2_value below SPEC §3 M5 range raises ValueError."""
    inputs = _uniform_cn2_inputs(canonical_inputs, Cn2_value=1e-20)
    with pytest.raises(ValueError, match="Cn2_value"):
        m5_turbulence.compute(inputs)
