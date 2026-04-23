"""Validation tests for M4 atmospheric attenuation per SPEC.md §3 M4.

Three cases pinned in SPEC §3:
  - test_m4_aerosol_clear     (Kruse @ V=23 km, 5% tol)
  - test_m4_aerosol_hazy      (Kruse @ V=5 km,  5% tol)
  - test_m4_wavelength_interpolation (exact match to log-space linear)

Per TESTING.md §6, the two Kruse aerosol cases share identical
arrange/act/assert structure and are collapsed with `parametrize`."""

import math

import pytest

from physics import m4_atmosphere


@pytest.mark.parametrize(
    "V, RH, wavelength_um, expected_alpha_aer_per_km",
    [
        pytest.param(23, 0.60, 1.07, 0.0716, id="m4_clear"),
        pytest.param( 5, 0.60, 1.07, 0.366,  id="m4_hazy"),
    ],
)
def test_m4_aerosol_kruse(
    V, RH, wavelength_um, expected_alpha_aer_per_km, canonical_inputs
):
    """SPEC §3 M4 Kruse aerosol validation: α_aer_total within 5%."""
    inputs = {
        **canonical_inputs,
        "V": V, "RH": RH, "T_ambient": 300,
        "wavelength": wavelength_um * 1e-6,
        "R_slant": 5000,
    }
    result = m4_atmosphere.compute(inputs)
    alpha_aer_total_per_km = (
        (result["alpha_aer_abs"] + result["alpha_aer_scat"]) * 1000.0
    )
    assert alpha_aer_total_per_km == pytest.approx(
        expected_alpha_aer_per_km, rel=0.05
    )


def test_m4_aerosol_clear_atm_and_tau(canonical_inputs):
    """SPEC §3 M4 'test_m4_aerosol_clear' full outputs: α_atm ≈ 0.137 1/km
    and τ_atm ≈ exp(-0.685) ≈ 0.504, both within 5%."""
    inputs = {
        **canonical_inputs,
        "V": 23, "RH": 0.60, "T_ambient": 300,
        "wavelength": 1.07e-6, "R_slant": 5000,
    }
    result = m4_atmosphere.compute(inputs)
    alpha_atm_per_km = result["alpha_atm"] * 1000.0
    assert alpha_atm_per_km == pytest.approx(0.137, rel=0.05)
    assert result["tau_atm"] == pytest.approx(math.exp(-0.685), rel=0.05)


def test_m4_wavelength_interpolation(canonical_inputs):
    """SPEC §3 M4 'test_m4_wavelength_interpolation'. A wavelength between
    the tabulated 1.07 and 1.55 µm points (here 1.30 µm) must produce the
    log-space linear interpolate and carry the 'wavelength interpolated'
    flag. Tolerance: exact match (floating-point)."""
    inputs = {
        **canonical_inputs,
        "V": 23, "RH": 0.60, "T_ambient": 300,
        "wavelength": 1.30e-6, "R_slant": 5000,
    }
    result = m4_atmosphere.compute(inputs)

    assert any("interpolated" in flag for flag in result["assumptions_flagged"])

    log_x = math.log(1.30e-6)
    log_x1, log_x2 = math.log(1.07e-6), math.log(1.55e-6)
    log_y1, log_y2 = math.log(0.065), math.log(0.190)
    t = (log_x - log_x1) / (log_x2 - log_x1)
    expected_per_km = math.exp(log_y1 + t * (log_y2 - log_y1))

    actual_per_km = result["alpha_mol_abs"] * 1000.0
    assert actual_per_km == pytest.approx(expected_per_km, rel=1e-9)


def test_m4_flags_sea_level_and_placeholder_tables(canonical_inputs):
    """CLAUDE §4.5 + SPEC §10.1: M4 always flags both the sea-level slant-path
    simplification and the HIGH UNCERTAINTY placeholder α_mol tables."""
    inputs = {
        **canonical_inputs,
        "V": 23, "RH": 0.60, "T_ambient": 300,
        "wavelength": 1.07e-6, "R_slant": 5000,
    }
    result = m4_atmosphere.compute(inputs)
    flags = " | ".join(result["assumptions_flagged"])
    assert "SPEC §10.1" in flags
    assert "sea-level" in flags


def test_m4_out_of_range_V_raises(canonical_inputs):
    """Input validation: V below SPEC §3 M4 valid range raises ValueError."""
    inputs = {**canonical_inputs, "V": 0.1, "R_slant": 5000}
    with pytest.raises(ValueError, match="V"):
        m4_atmosphere.compute(inputs)
