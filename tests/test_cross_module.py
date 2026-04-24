"""Cross-module consistency tests.

Two or more modules independently compute values that must agree — either
by identity (e.g. M2 P_exit = η·P0) or by physical equivalence
(e.g. M7 w_diff(L) in the far field equals M1 θ_diff·L/2). Per the
Package 2 plan (validation/README.md Layer 2.2), these tests guard
against cross-module formula drift that single-module tests cannot see.

Tolerances are tight (≤1%) because the relationships are either exact
or differ only by the '1+(M²L/zR)²' correction that we control by
choosing L ≫ zR."""

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
    orchestrator,
)


# ---------------------------------------------------------------------------
# M1 ↔ M7 — diffraction consistency
# ---------------------------------------------------------------------------

def test_m7_w_diff_matches_m1_gaussian_propagation(canonical_inputs):
    """M7 implements w_diff = w₀·√(1+(M²·L/zR)²) — the exact Gaussian.
    Feed M1's w₀, zR, M² into M7 directly and recompute w_diff from the
    first-principles Gaussian propagation law; they must agree to ≤ 0.5 %."""
    out1 = m1_laser_source.compute({
        "P0": canonical_inputs["P0"], "M2": canonical_inputs["M2"],
        "D": canonical_inputs["D"], "wavelength": canonical_inputs["wavelength"],
    })
    L = canonical_inputs["R"]
    w0 = out1["w0"]
    zR = out1["zR"]
    M2 = canonical_inputs["M2"]
    expected_w_diff = w0 * math.sqrt(1.0 + (M2 * L / zR) ** 2)

    out7 = m7_spot_pib.compute({
        "P_exit": 1000.0, "tau_atm": 1.0, "w0": w0, "zR": zR, "M2": M2,
        "wavelength": canonical_inputs["wavelength"], "R_slant": L,
        "sigma_jit": 0.0, "r0_sph": math.inf, "S_TB": 1.0,
        "w_bloom": 0.0, "d_aim": canonical_inputs["d_aim"],
    })
    assert out7["w_diff"] == pytest.approx(expected_w_diff, rel=1e-9)


def test_m1_theta_diff_matches_m7_far_field_asymptote(canonical_inputs):
    """In the far field (L ≫ zR), the exact Gaussian spot radius w_diff
    approaches the asymptote w₀·(M²L/zR) = M²·λ·L/(π·D/2) = (θ_diff/2)·L
    (since θ_diff = M²·4λ/(π·D) is the full-angle divergence).
    At L = 50 km with canonical inputs (zR ≈ 7340 m), M²L/zR ≈ 8.2 giving
    a residual '1+' correction of ~0.7 % — inside a 1 % tolerance."""
    out1 = m1_laser_source.compute({
        "P0": canonical_inputs["P0"], "M2": canonical_inputs["M2"],
        "D": canonical_inputs["D"], "wavelength": canonical_inputs["wavelength"],
    })
    L = 50000.0
    out7 = m7_spot_pib.compute({
        "P_exit": 1000.0, "tau_atm": 1.0, "w0": out1["w0"], "zR": out1["zR"],
        "M2": canonical_inputs["M2"],
        "wavelength": canonical_inputs["wavelength"], "R_slant": L,
        "sigma_jit": 0.0, "r0_sph": math.inf, "S_TB": 1.0,
        "w_bloom": 0.0, "d_aim": canonical_inputs["d_aim"],
    })
    # θ_diff is a full angle, so half-angle·L is the 1/e² radius asymptote.
    expected_w_asymptote = (out1["theta_diff"] / 2.0) * L
    assert out7["w_diff"] == pytest.approx(expected_w_asymptote, rel=0.01)


# ---------------------------------------------------------------------------
# M2 — identity (trivial but regressable)
# ---------------------------------------------------------------------------

def test_m2_p_exit_equals_eta_times_p0(canonical_inputs):
    """P_exit = η_opt · P0 exactly."""
    out = m2_beam_director.compute({
        "P0": canonical_inputs["P0"], "eta_opt": canonical_inputs["eta_opt"],
    })
    assert out["P_exit"] == pytest.approx(
        canonical_inputs["P0"] * canonical_inputs["eta_opt"], rel=1e-12,
    )


# ---------------------------------------------------------------------------
# M4 — Beer-Lambert identity τ = exp(-α·R)
# ---------------------------------------------------------------------------

def test_m4_tau_equals_beer_lambert(canonical_inputs):
    """τ_atm must equal exp(-α_atm · R_slant) to machine precision."""
    out = m4_atmosphere.compute({
        "V": canonical_inputs["V"], "RH": canonical_inputs["RH"],
        "T_ambient": canonical_inputs["T_ambient"],
        "wavelength": canonical_inputs["wavelength"],
        "R_slant": canonical_inputs["R"],
    })
    assert out["tau_atm"] == pytest.approx(
        math.exp(-out["alpha_atm"] * canonical_inputs["R"]), rel=1e-12,
    )


def test_m4_alpha_atm_is_sum_of_components(canonical_inputs):
    """α_atm = α_mol_abs + α_mol_scat + α_aer_abs + α_aer_scat exactly."""
    out = m4_atmosphere.compute({
        "V": canonical_inputs["V"], "RH": canonical_inputs["RH"],
        "T_ambient": canonical_inputs["T_ambient"],
        "wavelength": canonical_inputs["wavelength"],
        "R_slant": canonical_inputs["R"],
    })
    components_sum = (
        out["alpha_mol_abs"] + out["alpha_mol_scat"]
        + out["alpha_aer_abs"] + out["alpha_aer_scat"]
    )
    assert out["alpha_atm"] == pytest.approx(components_sum, rel=1e-12)


# ---------------------------------------------------------------------------
# M3 — Pythagorean identity R² = R_h² + ΔH²
# ---------------------------------------------------------------------------

def test_m3_pythagorean_identity(canonical_inputs):
    """R² = R_h² + (H_t − H_e)² to machine precision."""
    out = m3_geometry.compute(canonical_inputs)
    dh = canonical_inputs["H_t"] - canonical_inputs["H_e"]
    R = canonical_inputs["R"]
    assert R ** 2 == pytest.approx(out["R_h"] ** 2 + dh ** 2, rel=1e-12)


def test_m3_r_slant_equals_r(canonical_inputs):
    """In v1, R_slant = R exactly (SPEC §3 M3)."""
    out = m3_geometry.compute(canonical_inputs)
    assert out["R_slant"] == pytest.approx(canonical_inputs["R"], rel=1e-12)


# ---------------------------------------------------------------------------
# M7 — quadrature identity
# ---------------------------------------------------------------------------

def test_m7_w_total_quadrature_exact(canonical_inputs):
    """w_total² = w_diff² + w_turb² + w_jit² + w_bloom² — CLAUDE §7.1
    invariant. Turbulence enters via w_turb (never as a Strehl factor)."""
    out7 = m7_spot_pib.compute({
        "P_exit": 1000.0, "tau_atm": 0.9, "w0": 0.05,
        "zR": math.pi * 0.05 ** 2 / 1.07e-6,
        "M2": 1.2, "wavelength": 1.07e-6, "R_slant": 2000.0,
        "sigma_jit": 10e-6, "r0_sph": 0.05, "S_TB": 0.8,
        "w_bloom": 0.015, "d_aim": 0.05,
    })
    sq = (
        out7["w_diff"] ** 2 + out7["w_turb"] ** 2
        + out7["w_jit"] ** 2 + 0.015 ** 2
    )
    assert out7["w_total"] ** 2 == pytest.approx(sq, rel=1e-12)


# ---------------------------------------------------------------------------
# M9 — NOHD ordering (CLAUDE §7.1 invariant)
# ---------------------------------------------------------------------------

def test_m9_gausspeak_always_exceeds_tophat(canonical_inputs):
    """NOHD_gausspeak > NOHD_tophat always (factor √2 on the pre-aperture
    term; same aperture subtract). This is a CLAUDE §7.1 invariant."""
    # Exercise across three scenarios.
    for P0 in (500.0, 3000.0, 30000.0):
        for lam in (1.07e-6, 1.55e-6, 2.05e-6):
            out1 = m1_laser_source.compute({
                "P0": P0, "M2": 1.2, "D": canonical_inputs["D"], "wavelength": lam,
            })
            out9 = m9_nohd.compute({
                "P0": P0, "D": canonical_inputs["D"],
                "theta_diff": out1["theta_diff"], "wavelength": lam,
                "t_exp": 0.25,
            })
            assert out9["NOHD_gausspeak"] > out9["NOHD_tophat"]


# ---------------------------------------------------------------------------
# M10 — identity Q_waste = P_in − P0
# ---------------------------------------------------------------------------

def test_m10_q_waste_identity(canonical_inputs):
    """Q_waste = P_in − P0 = P0·(1/η − 1) exactly."""
    out = m10_power_thermal.compute({
        "P0": canonical_inputs["P0"],
        "eta_wallplug": canonical_inputs["eta_wallplug"],
        "Q_cool": canonical_inputs["Q_cool"],
        "C_thermal": canonical_inputs["C_thermal"],
        "dT_max": canonical_inputs["dT_max"],
        "t_engagement": 5.0,
    })
    P0 = canonical_inputs["P0"]
    eta = canonical_inputs["eta_wallplug"]
    assert out["Q_waste"] == pytest.approx(P0 * (1.0 / eta - 1.0), rel=1e-12)
    assert out["P_in"] == pytest.approx(P0 / eta, rel=1e-12)
    assert out["Q_waste"] == pytest.approx(out["P_in"] - P0, rel=1e-12)


# ---------------------------------------------------------------------------
# Orchestrator-level cross-checks
# ---------------------------------------------------------------------------

def test_orchestrator_w_total_at_least_each_component(canonical_inputs):
    """Orchestrator result: w_total ≥ w_diff, w_turb, w_jit individually
    (each is a non-negative contribution to the quadrature)."""
    result = orchestrator.run_full_chain(canonical_inputs)
    assert result["w_total"] >= result["w_diff"] - 1e-12
    assert result["w_total"] >= result["w_turb"] - 1e-12
    assert result["w_total"] >= result["w_jit"] - 1e-12


def test_orchestrator_pib_in_unit_interval(canonical_inputs):
    """PIB_fraction ∈ [0, 1] always."""
    result = orchestrator.run_full_chain(canonical_inputs)
    assert 0.0 <= result["PIB_fraction"] <= 1.0


def test_orchestrator_strehl_and_transmission_in_unit_interval(canonical_inputs):
    """S_TB ∈ [0,1], tau_atm ∈ [0,1] after the full chain."""
    result = orchestrator.run_full_chain(canonical_inputs)
    assert 0.0 <= result["S_TB"] <= 1.0
    assert 0.0 <= result["tau_atm"] <= 1.0


def test_orchestrator_flags_deduplicated(canonical_inputs):
    """assumptions_flagged is de-duplicated while preserving first-seen
    order (SPEC §3 orchestration contract)."""
    result = orchestrator.run_full_chain(canonical_inputs)
    flags = result["assumptions_flagged"]
    assert len(flags) == len(set(flags)), (
        "assumptions_flagged contains duplicates after orchestrator merge"
    )


def test_orchestrator_m67_converges_for_canonical(canonical_inputs):
    """Canonical scenario converges within 10 iterations at 1 % tol."""
    result = orchestrator.run_full_chain(canonical_inputs)
    assert result["m67_converged"] is True
    assert 1 <= result["m67_iteration_count"] <= 10


def test_orchestrator_m67_self_consistency_after_convergence(canonical_inputs):
    """After convergence, plugging w_total back into M6 reproduces S_TB
    within 0.5 %. This verifies the fixed-point actually settled on a
    self-consistent pair, not just that Δw fell under 1 %."""
    result = orchestrator.run_full_chain(canonical_inputs)
    # Re-run M6 one more time with the converged w_total.
    out6_recheck = m6_blooming.compute({
        "P_propagating": result["P_exit"],
        "w_at_target": result["w_total"],
        "alpha_atm": result["alpha_atm"],
        "v_perp": canonical_inputs["v_perp"],
        "R_slant": result["R_slant"],
        "T_ambient": canonical_inputs["T_ambient"],
        "P_atm": canonical_inputs["P_atm"],
    })
    assert out6_recheck["S_TB"] == pytest.approx(result["S_TB"], rel=5e-3)


def test_orchestrator_infeasible_geometry_raises(canonical_inputs):
    """If R < |H_t − H_e| the chain must raise before M4 runs — M3's
    _validate_inputs rejects the geometry."""
    bad = {**canonical_inputs, "H_e": 0, "H_t": 5000, "R": 1000}
    with pytest.raises(ValueError):
        orchestrator.run_full_chain(bad)


def test_orchestrator_determinism(canonical_inputs):
    """Same inputs → same outputs. No random state leaks into the chain."""
    r1 = orchestrator.run_full_chain(canonical_inputs)
    r2 = orchestrator.run_full_chain(canonical_inputs)
    # Numeric outputs must match exactly across repeated calls.
    for key in ("theta_diff", "w0", "zR", "I_exit", "P_exit",
                "R_slant", "alpha_atm", "tau_atm", "r0_sph", "w_turb",
                "N_D", "S_TB", "w_bloom", "w_total", "I_peak",
                "PIB_fraction", "P_aim", "I_avg_aim", "tau_BT",
                "T_surface_peak", "NOHD_tophat", "NOHD_gausspeak",
                "P_in", "Q_waste"):
        if key in r1:
            assert r1[key] == r2[key], f"Non-deterministic output for {key}"


def test_orchestrator_by_module_namespace_populated(canonical_inputs):
    """by_module exposes every module's output dict under keys m1..m10."""
    result = orchestrator.run_full_chain(canonical_inputs)
    by_mod = result["by_module"]
    assert set(by_mod.keys()) == {
        "m1", "m2", "m3", "m4", "m5", "m6", "m7", "m8", "m9", "m10",
    }
    # Spot-check that a namespaced value matches the flat-merged value.
    assert by_mod["m1"]["theta_diff"] == result["theta_diff"]
    assert by_mod["m7"]["w_total"] == result["w_total"]
    assert by_mod["m9"]["NOHD_tophat"] == result["NOHD_tophat"]
