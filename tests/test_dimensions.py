"""Dimensional-scaling tests for the HEL physics modules.

Per the Package 2 plan (validation/README.md Layer 2.1), each module has
formulas whose scaling in each input is predicted by first principles.
Scaling a single input by k and checking the output scales by the correct
power of k catches off-by-k, off-by-k², missing-factor, and wrong-unit
errors that numerical validation at one operating point misses.

These tests are deliberately narrow — they check *scaling*, not absolute
values (SPEC §3 validation cases already pin absolute values). Tolerances
are tight (0.1%–1%) because the scaling is exact in closed form for every
case below; residual error comes from finite-precision arithmetic and
(for M7 diffraction) a small `1+(M²L/zR)²` correction that we control by
choosing L ≫ zR.

References:
  - CLAUDE §7.1 immutable formulas
  - SPEC §3 per-module equations
"""

import math

import pytest

from physics import (
    m1_laser_source,
    m2_beam_director,
    m3_geometry,
    m4_atmosphere,
    m5_turbulence,
    m6_blooming,
    m7_spot_pib,
    m9_nohd,
    m10_power_thermal,
)


# ---------------------------------------------------------------------------
# M1 — Laser Source (exact closed form; tolerance 0.1%)
# ---------------------------------------------------------------------------

def test_m1_theta_diff_linear_in_wavelength(canonical_inputs):
    """θ_diff = M²·4λ/(πD) → 2λ must give 2·θ_diff exactly."""
    base = m1_laser_source.compute(canonical_inputs)
    inputs = {**canonical_inputs, "wavelength": 2.0 * canonical_inputs["wavelength"]}
    # 2 × λ stays inside [0.5e-6, 5.0e-6] at canonical λ=1.07 µm.
    scaled = m1_laser_source.compute(inputs)
    assert scaled["theta_diff"] == pytest.approx(2.0 * base["theta_diff"], rel=1e-6)


def test_m1_theta_diff_inverse_in_aperture(canonical_inputs):
    """θ_diff ∝ 1/D → 2·D must give 0.5·θ_diff exactly."""
    base = m1_laser_source.compute(canonical_inputs)
    inputs = {**canonical_inputs, "D": 2.0 * canonical_inputs["D"]}
    scaled = m1_laser_source.compute(inputs)
    assert scaled["theta_diff"] == pytest.approx(0.5 * base["theta_diff"], rel=1e-6)


def test_m1_rayleigh_range_quadratic_in_aperture(canonical_inputs):
    """zR = π·(D/2)²/λ → 2·D must give 4·zR exactly."""
    base = m1_laser_source.compute(canonical_inputs)
    inputs = {**canonical_inputs, "D": 2.0 * canonical_inputs["D"]}
    scaled = m1_laser_source.compute(inputs)
    assert scaled["zR"] == pytest.approx(4.0 * base["zR"], rel=1e-6)


def test_m1_exit_irradiance_quadratic_inverse_in_aperture(canonical_inputs):
    """I_exit = 2P/(π·(D/2)²) → 2·D must give 0.25·I_exit exactly."""
    base = m1_laser_source.compute(canonical_inputs)
    inputs = {**canonical_inputs, "D": 2.0 * canonical_inputs["D"]}
    scaled = m1_laser_source.compute(inputs)
    assert scaled["I_exit"] == pytest.approx(0.25 * base["I_exit"], rel=1e-6)


def test_m1_exit_irradiance_linear_in_power(canonical_inputs):
    """I_exit ∝ P0 → 2·P0 must give 2·I_exit exactly."""
    base = m1_laser_source.compute(canonical_inputs)
    # 2 × 3000 W = 6000 W stays inside [100, 100_000].
    inputs = {**canonical_inputs, "P0": 2.0 * canonical_inputs["P0"]}
    scaled = m1_laser_source.compute(inputs)
    assert scaled["I_exit"] == pytest.approx(2.0 * base["I_exit"], rel=1e-6)


# ---------------------------------------------------------------------------
# M2 — Beam Director (trivial but verified)
# ---------------------------------------------------------------------------

def test_m2_p_exit_linear_in_power(canonical_inputs):
    """P_exit = η·P0 → 2·P0 must give 2·P_exit exactly."""
    m2_inputs = {"P0": canonical_inputs["P0"], "eta_opt": canonical_inputs["eta_opt"]}
    base = m2_beam_director.compute(m2_inputs)
    scaled = m2_beam_director.compute({**m2_inputs, "P0": 2.0 * m2_inputs["P0"]})
    assert scaled["P_exit"] == pytest.approx(2.0 * base["P_exit"], rel=1e-9)


def test_m2_p_exit_linear_in_eta(canonical_inputs):
    """P_exit = η·P0 — doubling η (0.45→0.90, both in [0.50, 0.99]? use 0.5→0.99)."""
    m2_inputs = {"P0": canonical_inputs["P0"], "eta_opt": 0.50}
    base = m2_beam_director.compute(m2_inputs)
    # Scale η by 99/50 = 1.98; output should scale identically.
    eta2 = 0.99
    scaled = m2_beam_director.compute({**m2_inputs, "eta_opt": eta2})
    assert scaled["P_exit"] == pytest.approx((eta2 / 0.50) * base["P_exit"], rel=1e-9)


# ---------------------------------------------------------------------------
# M3 — Engagement Geometry (Euclidean; exact)
# ---------------------------------------------------------------------------

def test_m3_slant_linear_in_range_flat_geometry(canonical_inputs):
    """R_slant = R exactly; 2·R doubles R_slant (flat case H_e=H_t)."""
    base_inputs = {**canonical_inputs, "H_e": 100.0, "H_t": 100.0, "R": 1000.0}
    base = m3_geometry.compute(base_inputs)
    scaled = m3_geometry.compute({**base_inputs, "R": 2000.0})
    assert scaled["R_slant"] == pytest.approx(2.0 * base["R_slant"], rel=1e-9)


def test_m3_horizontal_linear_in_range_flat_geometry(canonical_inputs):
    """R_h = sqrt(R² − ΔH²) → at ΔH=0, 2·R gives 2·R_h."""
    base_inputs = {**canonical_inputs, "H_e": 100.0, "H_t": 100.0, "R": 1000.0}
    base = m3_geometry.compute(base_inputs)
    scaled = m3_geometry.compute({**base_inputs, "R": 2000.0})
    assert scaled["R_h"] == pytest.approx(2.0 * base["R_h"], rel=1e-9)


def test_m3_dwell_inverse_in_target_speed(canonical_inputs):
    """available_dwell = 2R·tan(FOV/2)/v_tgt → 2·v_tgt halves dwell."""
    base = m3_geometry.compute(canonical_inputs)
    scaled = m3_geometry.compute({**canonical_inputs, "v_tgt": 2.0 * canonical_inputs["v_tgt"]})
    assert scaled["available_dwell"] == pytest.approx(
        0.5 * base["available_dwell"], rel=1e-9,
    )


def test_m3_dwell_linear_in_range(canonical_inputs):
    """available_dwell = 2R·tan(FOV/2)/v_tgt → 2·R doubles dwell."""
    base = m3_geometry.compute(canonical_inputs)
    scaled = m3_geometry.compute({**canonical_inputs, "R": 2.0 * canonical_inputs["R"]})
    assert scaled["available_dwell"] == pytest.approx(
        2.0 * base["available_dwell"], rel=1e-9,
    )


# ---------------------------------------------------------------------------
# M4 — Atmospheric Attenuation
# ---------------------------------------------------------------------------

def test_m4_aerosol_inverse_in_visibility_kruse_plateau(canonical_inputs):
    """In the Kruse plateau (6 ≤ V ≤ 50 km), q=1.3 is constant, so
    α_aer ∝ 1/V exactly. V → V/2 doubles the aerosol extinction."""
    m4_inputs = {
        "V": 20.0, "RH": canonical_inputs["RH"],
        "T_ambient": canonical_inputs["T_ambient"],
        "wavelength": canonical_inputs["wavelength"],
        "R_slant": canonical_inputs["R"],
    }
    base = m4_atmosphere.compute(m4_inputs)
    scaled = m4_atmosphere.compute({**m4_inputs, "V": 10.0})
    # Aerosol total = aer_abs + aer_scat; both halves scale together.
    base_aer = base["alpha_aer_abs"] + base["alpha_aer_scat"]
    scaled_aer = scaled["alpha_aer_abs"] + scaled["alpha_aer_scat"]
    assert scaled_aer == pytest.approx(2.0 * base_aer, rel=1e-6)


def test_m4_molecular_absorption_linear_in_rh(canonical_inputs):
    """α_mol_abs ∝ RH / _RH_BASELINE → 2·RH doubles α_mol_abs."""
    m4_inputs = {
        "V": canonical_inputs["V"], "RH": 0.30,
        "T_ambient": canonical_inputs["T_ambient"],
        "wavelength": canonical_inputs["wavelength"],
        "R_slant": canonical_inputs["R"],
    }
    base = m4_atmosphere.compute(m4_inputs)
    scaled = m4_atmosphere.compute({**m4_inputs, "RH": 0.60})
    assert scaled["alpha_mol_abs"] == pytest.approx(2.0 * base["alpha_mol_abs"], rel=1e-6)


def test_m4_molecular_scattering_independent_of_rh(canonical_inputs):
    """α_mol_scat must NOT depend on RH — regression guard against a past bug."""
    m4_inputs = {
        "V": canonical_inputs["V"], "RH": 0.20,
        "T_ambient": canonical_inputs["T_ambient"],
        "wavelength": canonical_inputs["wavelength"],
        "R_slant": canonical_inputs["R"],
    }
    base = m4_atmosphere.compute(m4_inputs)
    other = m4_atmosphere.compute({**m4_inputs, "RH": 0.80})
    assert base["alpha_mol_scat"] == pytest.approx(other["alpha_mol_scat"], rel=1e-12)


def test_m4_tau_squared_when_r_doubles(canonical_inputs):
    """τ = exp(-α·R); α is R-independent, so 2·R gives τ_new = τ_old²."""
    m4_inputs = {
        "V": canonical_inputs["V"], "RH": canonical_inputs["RH"],
        "T_ambient": canonical_inputs["T_ambient"],
        "wavelength": canonical_inputs["wavelength"],
        "R_slant": 1000.0,
    }
    base = m4_atmosphere.compute(m4_inputs)
    scaled = m4_atmosphere.compute({**m4_inputs, "R_slant": 2000.0})
    assert scaled["tau_atm"] == pytest.approx(base["tau_atm"] ** 2, rel=1e-6)


# ---------------------------------------------------------------------------
# M5 — Turbulence (constant-Cn² regime — closed form)
# ---------------------------------------------------------------------------

def _m5_constant_inputs(canonical_inputs, Cn2_value=1e-15):
    return {
        "cn2_model": "constant",
        "Cn2_value": Cn2_value,
        "Cn2_ground": canonical_inputs["Cn2_ground"],
        "v_HV": canonical_inputs["v_HV"],
        "wavelength": canonical_inputs["wavelength"],
        "R_slant": canonical_inputs["R"],
        "H_e": canonical_inputs["H_e"],
        "H_t": canonical_inputs["H_t"],
    }


def test_m5_cn2_integrated_linear_in_cn2_value(canonical_inputs):
    """Constant model: ∫ = Cn²·L·3/8 → 2·Cn² doubles the integral."""
    m5_inputs = _m5_constant_inputs(canonical_inputs, Cn2_value=1e-15)
    base = m5_turbulence.compute(m5_inputs)
    scaled = m5_turbulence.compute({**m5_inputs, "Cn2_value": 2e-15})
    assert scaled["Cn2_integrated"] == pytest.approx(
        2.0 * base["Cn2_integrated"], rel=1e-9,
    )


def test_m5_r0_scales_as_cn2_to_minus_three_fifths(canonical_inputs):
    """r0_sph ∝ (Cn²·L·3/8)^(-3/5) → 2·Cn² gives r0·2^(-3/5)."""
    m5_inputs = _m5_constant_inputs(canonical_inputs, Cn2_value=1e-15)
    base = m5_turbulence.compute(m5_inputs)
    scaled = m5_turbulence.compute({**m5_inputs, "Cn2_value": 2e-15})
    assert scaled["r0_sph"] == pytest.approx(
        base["r0_sph"] * 2.0 ** (-3.0 / 5.0), rel=1e-6,
    )


def test_m5_w_turb_scales_as_cn2_to_three_fifths(canonical_inputs):
    """w_turb = 2L/(k·r0) ∝ r0⁻¹ ∝ Cn²^(3/5) → 2·Cn² gives 2^(3/5)·w_turb."""
    m5_inputs = _m5_constant_inputs(canonical_inputs, Cn2_value=1e-15)
    base = m5_turbulence.compute(m5_inputs)
    scaled = m5_turbulence.compute({**m5_inputs, "Cn2_value": 2e-15})
    assert scaled["w_turb"] == pytest.approx(
        base["w_turb"] * 2.0 ** (3.0 / 5.0), rel=1e-6,
    )


# ---------------------------------------------------------------------------
# M6 — Thermal Blooming (N_D closed form)
# ---------------------------------------------------------------------------

def _m6_inputs(canonical_inputs, P=1000.0, w=0.05, v_perp=3.0, alpha_atm=1e-4):
    return {
        "P_propagating": P,
        "w_at_target": w,
        "alpha_atm": alpha_atm,
        "v_perp": v_perp,
        "R_slant": canonical_inputs["R"],
        "T_ambient": canonical_inputs["T_ambient"],
        "P_atm": canonical_inputs["P_atm"],
    }


def test_m6_nd_linear_in_power(canonical_inputs):
    """N_D ∝ P → 2·P doubles N_D."""
    m6_inputs = _m6_inputs(canonical_inputs)
    base = m6_blooming.compute(m6_inputs)
    scaled = m6_blooming.compute({**m6_inputs, "P_propagating": 2.0 * m6_inputs["P_propagating"]})
    assert scaled["N_D"] == pytest.approx(2.0 * base["N_D"], rel=1e-9)


def test_m6_nd_inverse_in_crosswind(canonical_inputs):
    """N_D ∝ 1/v_perp → 2·v_perp halves N_D."""
    m6_inputs = _m6_inputs(canonical_inputs)
    base = m6_blooming.compute(m6_inputs)
    scaled = m6_blooming.compute({**m6_inputs, "v_perp": 2.0 * m6_inputs["v_perp"]})
    assert scaled["N_D"] == pytest.approx(0.5 * base["N_D"], rel=1e-9)


def test_m6_nd_linear_in_alpha(canonical_inputs):
    """N_D ∝ α_atm → 2·α doubles N_D."""
    m6_inputs = _m6_inputs(canonical_inputs)
    base = m6_blooming.compute(m6_inputs)
    scaled = m6_blooming.compute({**m6_inputs, "alpha_atm": 2.0 * m6_inputs["alpha_atm"]})
    assert scaled["N_D"] == pytest.approx(2.0 * base["N_D"], rel=1e-9)


def test_m6_nd_cubic_inverse_in_spot_radius(canonical_inputs):
    """N_D ∝ 1/w³ → 2·w gives N_D/8."""
    m6_inputs = _m6_inputs(canonical_inputs)
    base = m6_blooming.compute(m6_inputs)
    scaled = m6_blooming.compute({**m6_inputs, "w_at_target": 2.0 * m6_inputs["w_at_target"]})
    assert scaled["N_D"] == pytest.approx(base["N_D"] / 8.0, rel=1e-9)


def test_m6_nd_quadratic_in_range(canonical_inputs):
    """N_D ∝ R² → 2·R quadruples N_D."""
    m6_inputs = _m6_inputs(canonical_inputs)
    base = m6_blooming.compute(m6_inputs)
    scaled = m6_blooming.compute({**m6_inputs, "R_slant": 2.0 * m6_inputs["R_slant"]})
    assert scaled["N_D"] == pytest.approx(4.0 * base["N_D"], rel=1e-9)


# ---------------------------------------------------------------------------
# M7 — Spot and PIB
# ---------------------------------------------------------------------------

def _m7_inputs(canonical_inputs, **overrides):
    """Minimal M7 inputs; defaults yield a far-field diffraction regime."""
    # Canonical w0 = D/2 = 0.05 m; zR = π·w0²/λ ≈ 7340 m at λ=1.07 µm.
    # For far-field tests we set L = 50 km (max) so M²L/zR ≫ 1.
    defaults = {
        "P_exit": 2550.0,
        "tau_atm": 0.9,
        "w0": 0.05,
        "zR": math.pi * 0.05 ** 2 / 1.07e-6,
        "M2": 1.2,
        "wavelength": 1.07e-6,
        "R_slant": 50000.0,
        "sigma_jit": 10e-6,
        "r0_sph": 0.10,
        "S_TB": 1.0,
        "w_bloom": 0.0,
        "d_aim": 0.05,
    }
    defaults.update(overrides)
    return defaults


def test_m7_w_jit_linear_in_sigma(canonical_inputs):
    """w_jit = 2·σ·L → 2·σ doubles w_jit exactly."""
    m7_inputs = _m7_inputs(canonical_inputs, sigma_jit=5e-6)
    base = m7_spot_pib.compute(m7_inputs)
    scaled = m7_spot_pib.compute({**m7_inputs, "sigma_jit": 10e-6})
    assert scaled["w_jit"] == pytest.approx(2.0 * base["w_jit"], rel=1e-9)


def test_m7_w_jit_linear_in_range(canonical_inputs):
    """w_jit = 2·σ·L → 2·L doubles w_jit exactly."""
    m7_inputs = _m7_inputs(canonical_inputs, R_slant=1500.0)
    base = m7_spot_pib.compute(m7_inputs)
    scaled = m7_spot_pib.compute({**m7_inputs, "R_slant": 3000.0})
    assert scaled["w_jit"] == pytest.approx(2.0 * base["w_jit"], rel=1e-9)


def test_m7_w_turb_inverse_in_r0(canonical_inputs):
    """w_turb = 2L/(k·r₀) → 2·r₀ halves w_turb."""
    m7_inputs = _m7_inputs(canonical_inputs, r0_sph=0.10)
    base = m7_spot_pib.compute(m7_inputs)
    scaled = m7_spot_pib.compute({**m7_inputs, "r0_sph": 0.20})
    assert scaled["w_turb"] == pytest.approx(0.5 * base["w_turb"], rel=1e-9)


def test_m7_w_diff_linear_in_range_far_field(canonical_inputs):
    """Exact: w_diff = w₀·√(1+(M²L/zR)²). In the far field (L ≫ zR) the
    '1+' correction is small and 2·L doubles w_diff to within a small
    residual determined by (zR/(M²L))². At canonical w₀=0.05 m, λ=1.07 µm,
    zR ≈ 7340 m; L=50 km gives M²L/zR ≈ 8.17, residual ~1%."""
    m7_inputs = _m7_inputs(canonical_inputs, R_slant=25000.0)
    base = m7_spot_pib.compute(m7_inputs)
    scaled = m7_spot_pib.compute({**m7_inputs, "R_slant": 50000.0})
    # Expected ratio closed form:
    zR = m7_inputs["zR"]
    M2 = m7_inputs["M2"]
    ratio_theory = math.sqrt(
        (1.0 + (M2 * 50000.0 / zR) ** 2) / (1.0 + (M2 * 25000.0 / zR) ** 2)
    )
    assert scaled["w_diff"] / base["w_diff"] == pytest.approx(ratio_theory, rel=1e-9)
    # And that theoretical ratio is close to 2.0 in the far field:
    assert ratio_theory == pytest.approx(2.0, rel=0.02)


def test_m7_pib_exponent_uses_radius(canonical_inputs):
    """PIB = 1 − exp(−2·R_aim²/w²) where R_aim = d_aim/2. Regression guard
    against ever using d_aim in the exponent instead of R_aim. The
    signature: at w=d_aim/2, PIB = 1 − exp(−2·(1/4)·d²/(d²/4)) = 1 − exp(−2)
    if we use d_aim, but the correct PIB with R_aim is
    1 − exp(−2·(d_aim/2)²/(d_aim/2)²) = 1 − exp(−2) = 0.8647.
    Cleaner check: tune d_aim and w such that the expected PIB is known."""
    # Set w_total so that 2·R_aim²/w² = 1 → PIB = 1 − e⁻¹ ≈ 0.6321.
    # Requires w² = 2·R_aim² → w = √2 · R_aim = √2 · d_aim/2.
    # Achieve this by setting turbulence/jitter high so w_total is dominated
    # by a controllable term: disable r0 (= inf) and set sigma_jit to
    # force w_jit = 2·σ·L. Pick L = 1000 m, d_aim = 0.01 m → R_aim = 0.005.
    # Need w ≈ √2 · 0.005 = 7.07e-3 m from w_jit alone (w_diff negligible).
    # w_jit = 2·σ·L → σ = 7.07e-3 / (2·1000) = 3.54e-6 rad.
    # But w_diff contributes; choose D large and L/zR small so w_diff ≈ w₀.
    # Simpler: just assert monotonic + factor-of-2 in the exponent via a
    # pair of cases that would disagree by a full order of magnitude if
    # the exponent factor were wrong.
    m7_inputs = _m7_inputs(
        canonical_inputs,
        R_slant=1000.0,
        sigma_jit=0.0,
        r0_sph=math.inf,
        w_bloom=0.0,
        d_aim=0.01,
    )
    result = m7_spot_pib.compute(m7_inputs)
    # Closed form: PIB = 1 − exp(−2·R_aim²/w_total²). R_aim = 0.005 m.
    w_total = result["w_total"]
    expected_pib = 1.0 - math.exp(-2.0 * (0.005 ** 2) / (w_total ** 2))
    assert result["PIB_fraction"] == pytest.approx(expected_pib, rel=1e-9)


def test_m7_i_peak_linear_in_power(canonical_inputs):
    """I_peak = 2·P·τ·S/(π·w²). At fixed geometry and S, I_peak ∝ P_exit."""
    m7_inputs = _m7_inputs(canonical_inputs, P_exit=1000.0)
    base = m7_spot_pib.compute(m7_inputs)
    scaled = m7_spot_pib.compute({**m7_inputs, "P_exit": 2000.0})
    assert scaled["I_peak"] == pytest.approx(2.0 * base["I_peak"], rel=1e-9)


def test_m7_i_peak_linear_in_tau(canonical_inputs):
    """I_peak ∝ τ_atm → 2·τ doubles I_peak (while τ ≤ 1)."""
    m7_inputs = _m7_inputs(canonical_inputs, tau_atm=0.4)
    base = m7_spot_pib.compute(m7_inputs)
    scaled = m7_spot_pib.compute({**m7_inputs, "tau_atm": 0.8})
    assert scaled["I_peak"] == pytest.approx(2.0 * base["I_peak"], rel=1e-9)


def test_m7_i_peak_linear_in_strehl(canonical_inputs):
    """I_peak ∝ S_total = S_TB (S_opt=1 in v1). Doubling S_TB doubles I_peak."""
    m7_inputs = _m7_inputs(canonical_inputs, S_TB=0.25)
    base = m7_spot_pib.compute(m7_inputs)
    scaled = m7_spot_pib.compute({**m7_inputs, "S_TB": 0.50})
    assert scaled["I_peak"] == pytest.approx(2.0 * base["I_peak"], rel=1e-9)


def test_m7_quadrature_identity(canonical_inputs):
    """w_total² = w_diff² + w_turb² + w_jit² + w_bloom² exactly."""
    m7_inputs = _m7_inputs(canonical_inputs, w_bloom=0.02)
    r = m7_spot_pib.compute(m7_inputs)
    expected_sq = r["w_diff"] ** 2 + r["w_turb"] ** 2 + r["w_jit"] ** 2 + m7_inputs["w_bloom"] ** 2
    assert r["w_total"] ** 2 == pytest.approx(expected_sq, rel=1e-12)


def test_m7_d_spot_is_twice_w_total(canonical_inputs):
    """d_spot = 2·w_total by definition."""
    m7_inputs = _m7_inputs(canonical_inputs)
    r = m7_spot_pib.compute(m7_inputs)
    assert r["d_spot"] == pytest.approx(2.0 * r["w_total"], rel=1e-12)


# ---------------------------------------------------------------------------
# M9 — NOHD / MPE
# ---------------------------------------------------------------------------

def _m9_inputs(canonical_inputs, P0=3000.0, theta=1e-5, t_exp=0.25):
    return {
        "P0": P0,
        "D": canonical_inputs["D"],
        "theta_diff": theta,
        "wavelength": canonical_inputs["wavelength"],
        "t_exp": t_exp,
    }


def test_m9_nohd_pre_aperture_term_sqrt_in_power(canonical_inputs):
    """Pre-aperture NOHD term = (1/θ)·√(4P/(πMPE)) scales as √P. The
    aperture correction (D/θ) is P-independent, so adding D/θ back to the
    reported NOHD recovers the exact sqrt scaling."""
    m9_inputs = _m9_inputs(canonical_inputs, P0=3000.0)
    base = m9_nohd.compute(m9_inputs)
    scaled = m9_nohd.compute({**m9_inputs, "P0": 6000.0})
    aperture_corr = m9_inputs["D"] / m9_inputs["theta_diff"]
    base_pre = base["NOHD_tophat"] + aperture_corr
    scaled_pre = scaled["NOHD_tophat"] + aperture_corr
    assert scaled_pre == pytest.approx(math.sqrt(2.0) * base_pre, rel=1e-9)


def test_m9_nohd_pre_aperture_term_inverse_in_theta(canonical_inputs):
    """Pre-aperture term = (1/θ)·√(4P/πMPE) − 0 → scales as 1/θ. Add back
    aperture correction (which also scales as 1/θ) → reported NOHD itself
    scales as 1/θ."""
    m9_inputs = _m9_inputs(canonical_inputs, theta=1e-5)
    base = m9_nohd.compute(m9_inputs)
    scaled = m9_nohd.compute({**m9_inputs, "theta_diff": 2e-5})
    assert scaled["NOHD_tophat"] == pytest.approx(0.5 * base["NOHD_tophat"], rel=1e-9)
    assert scaled["NOHD_gausspeak"] == pytest.approx(0.5 * base["NOHD_gausspeak"], rel=1e-9)


def test_m9_nohd_gausspeak_vs_tophat_sqrt2_ratio(canonical_inputs):
    """NOHD_gausspeak_pre / NOHD_tophat_pre = √(8/4) = √2 exactly (both
    pre-aperture-correction). Test via the pre-aperture form."""
    m9_inputs = _m9_inputs(canonical_inputs)
    r = m9_nohd.compute(m9_inputs)
    aperture_corr = m9_inputs["D"] / m9_inputs["theta_diff"]
    ratio = (r["NOHD_gausspeak"] + aperture_corr) / (r["NOHD_tophat"] + aperture_corr)
    assert ratio == pytest.approx(math.sqrt(2.0), rel=1e-9)


def test_m9_mpe_band_a_chronic_constant(canonical_inputs):
    """In Band A chronic regime (t > 10 s), MPE = 1 mW/cm² = 10 W/m²
    independent of t_exp. Check two different t_exp values give same MPE."""
    m9_inputs = _m9_inputs(canonical_inputs, t_exp=15.0)
    r1 = m9_nohd.compute(m9_inputs)
    r2 = m9_nohd.compute({**m9_inputs, "t_exp": 50.0})
    assert r1["MPE"] == pytest.approx(r2["MPE"], rel=1e-12)
    assert r1["MPE"] == pytest.approx(10.0, rel=1e-9)  # 1e-3 W/cm² → 10 W/m²


# ---------------------------------------------------------------------------
# M10 — Power and Thermal Budget
# ---------------------------------------------------------------------------

def _m10_inputs(canonical_inputs, P0=3000.0):
    return {
        "P0": P0,
        "eta_wallplug": canonical_inputs["eta_wallplug"],
        "Q_cool": canonical_inputs["Q_cool"],
        "C_thermal": canonical_inputs["C_thermal"],
        "dT_max": canonical_inputs["dT_max"],
        "t_engagement": 5.0,
    }


def test_m10_p_in_linear_in_p0(canonical_inputs):
    """P_in = P0/η → 2·P0 doubles P_in at fixed η."""
    m10_inputs = _m10_inputs(canonical_inputs, P0=3000.0)
    base = m10_power_thermal.compute(m10_inputs)
    scaled = m10_power_thermal.compute({**m10_inputs, "P0": 6000.0})
    assert scaled["P_in"] == pytest.approx(2.0 * base["P_in"], rel=1e-12)


def test_m10_q_waste_linear_in_p0_at_fixed_eta(canonical_inputs):
    """Q_waste = P0·(1/η − 1) → 2·P0 doubles Q_waste at fixed η."""
    m10_inputs = _m10_inputs(canonical_inputs, P0=3000.0)
    base = m10_power_thermal.compute(m10_inputs)
    scaled = m10_power_thermal.compute({**m10_inputs, "P0": 6000.0})
    assert scaled["Q_waste"] == pytest.approx(2.0 * base["Q_waste"], rel=1e-12)


def test_m10_q_waste_vs_p_in_identity(canonical_inputs):
    """Q_waste must equal P_in − P0 exactly."""
    m10_inputs = _m10_inputs(canonical_inputs, P0=3000.0)
    r = m10_power_thermal.compute(m10_inputs)
    assert r["Q_waste"] == pytest.approx(r["P_in"] - m10_inputs["P0"], rel=1e-12)
