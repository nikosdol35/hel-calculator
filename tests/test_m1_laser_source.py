"""Validation tests for M1 laser source per SPEC.md §3 M1.

Two cases pinned in SPEC §3: test_m1_divergence (closed-form arithmetic,
0.1% tolerance) and test_m1_rayleigh_range (first-principles, 1% tolerance)."""

import pytest

from physics import m1_laser_source


def test_m1_divergence(canonical_inputs):
    """SPEC §3 M1 'test_m1_divergence'. Expected theta_diff ≈ 13.547 µrad."""
    inputs = {
        **canonical_inputs,
        "P0": 1000, "M2": 1.0, "D": 0.10, "wavelength": 1.064e-6,
    }
    result = m1_laser_source.compute(inputs)
    assert result["theta_diff"] == pytest.approx(13.547e-6, rel=1e-3)


def test_m1_rayleigh_range(canonical_inputs):
    """SPEC §3 M1 'test_m1_rayleigh_range'. Expected w0=0.05 m; zR ≈ 7340 m."""
    inputs = {
        **canonical_inputs,
        "P0": 3000, "M2": 1.2, "D": 0.10, "wavelength": 1.07e-6,
    }
    result = m1_laser_source.compute(inputs)
    assert result["w0"] == pytest.approx(0.05, rel=0.01)
    assert result["zR"] == pytest.approx(7340.0, rel=0.01)


def test_m1_out_of_range_P0_raises():
    """Input validation: P0 below the SPEC §3 M1 valid range raises ValueError."""
    with pytest.raises(ValueError, match="P0"):
        m1_laser_source.compute({"P0": 50, "M2": 1.2, "D": 0.10, "wavelength": 1.07e-6})


def test_m1_wavelength_outside_validated_set_flags(canonical_inputs):
    """Assumption flag: wavelength not in {1.06, 1.07, 1.55, 2.05 µm} triggers
    a reduced-confidence entry in assumptions_flagged (SPEC §3 M1, SPEC §1.6)."""
    inputs = {**canonical_inputs, "wavelength": 1.30e-6}
    result = m1_laser_source.compute(inputs)
    assert any("wavelength outside validated set" in flag
               for flag in result["assumptions_flagged"])
