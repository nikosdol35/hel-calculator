"""Property-based / fuzz tests using hypothesis.

Per the Package 2 plan (validation/README.md Layer 2.3), these tests
verify physical-invariant properties (0 ≤ PIB ≤ 1, w_total ≥ w_diff,
etc.) across wide randomized input ranges. Single-point tests at the
canonical operating point can't catch invariant violations in corners
of the input space.

Hypothesis is run with a fixed seed (via `@settings(derandomize=True)`)
so CI runs are reproducible; locally the user can unseed by removing
the derandomize flag if they want to hunt for rare failures.

References:
  - hypothesis: https://hypothesis.readthedocs.io
  - SPEC §3 per-module invariants
"""

import math

from hypothesis import HealthCheck, given, settings
from hypothesis import strategies as st

from physics import (
    m1_laser_source,
    m3_geometry,
    m4_atmosphere,
    m6_blooming,
    m7_spot_pib,
    m9_nohd,
    m10_power_thermal,
    orchestrator,
)


# Deterministic CI runs at 50 examples per property (hypothesis' default
# profile is 100 with random seed). derandomize=True replays the same
# sequence every run. Raise HealthCheck.filter_too_much for composites
# that reject a fraction of draws (e.g. valid HEL operating points).
DERANDOMIZED = settings(
    max_examples=50,
    derandomize=True,
    suppress_health_check=[
        HealthCheck.filter_too_much,
        HealthCheck.too_slow,
        # The three orchestrator fuzz tests pull the canonical_inputs fixture
        # and overlay the hypothesis-drawn parameters. The fixture is a
        # read-only dict snapshot, not reset state — reusing it across
        # examples is safe and intentional.
        HealthCheck.function_scoped_fixture,
    ],
    deadline=None,  # some properties run the full orchestrator — be patient
)


# ---------------------------------------------------------------------------
# Hypothesis strategies for physical inputs (respect validate_range limits).
# ---------------------------------------------------------------------------

_p0 = st.floats(min_value=100.0, max_value=100_000.0, allow_nan=False)
_m2 = st.floats(min_value=1.0, max_value=10.0, allow_nan=False)
_d_aperture = st.floats(min_value=0.01, max_value=0.50, allow_nan=False)
_wavelength = st.sampled_from([1.06e-6, 1.07e-6, 1.55e-6, 2.05e-6])
_eta_opt = st.floats(min_value=0.50, max_value=0.99, allow_nan=False)
_sigma_jit = st.floats(min_value=0.0, max_value=1e-4, allow_nan=False)
_R = st.floats(min_value=100.0, max_value=50_000.0, allow_nan=False)
_v_tgt = st.floats(min_value=0.0, max_value=100.0, allow_nan=False)
_v_perp = st.floats(min_value=0.5, max_value=30.0, allow_nan=False)  # > 0 for M6
_V = st.floats(min_value=1.0, max_value=50.0, allow_nan=False)
_RH = st.floats(min_value=0.0, max_value=1.0, allow_nan=False)
_T_amb = st.floats(min_value=253.0, max_value=328.0, allow_nan=False)
_alpha_atm = st.floats(min_value=1e-6, max_value=1e-3, allow_nan=False)
_w_target = st.floats(min_value=0.005, max_value=1.0, allow_nan=False)
_tau_atm = st.floats(min_value=0.05, max_value=1.0, allow_nan=False)
_S_TB = st.floats(min_value=0.0, max_value=1.0, allow_nan=False)
_d_aim = st.floats(min_value=0.005, max_value=1.0, allow_nan=False)
_eta_wall = st.floats(min_value=0.05, max_value=0.50, allow_nan=False)
_dT_max = st.floats(min_value=5.0, max_value=80.0, allow_nan=False)
_t_engagement = st.floats(min_value=0.1, max_value=60.0, allow_nan=False)


# ---------------------------------------------------------------------------
# M4 — transmission bounds
# ---------------------------------------------------------------------------

@DERANDOMIZED
@given(V=_V, RH=_RH, T=_T_amb, lam=_wavelength, R=_R)
def test_m4_tau_in_unit_interval(V, RH, T, lam, R):
    """0 ≤ τ_atm ≤ 1 for any legal atmosphere / geometry."""
    out = m4_atmosphere.compute({
        "V": V, "RH": RH, "T_ambient": T, "wavelength": lam, "R_slant": R,
    })
    assert 0.0 <= out["tau_atm"] <= 1.0


@DERANDOMIZED
@given(V=_V, RH=_RH, T=_T_amb, lam=_wavelength, R=_R)
def test_m4_alpha_atm_nonnegative(V, RH, T, lam, R):
    """α_atm ≥ 0 for any legal atmosphere (and all components ≥ 0)."""
    out = m4_atmosphere.compute({
        "V": V, "RH": RH, "T_ambient": T, "wavelength": lam, "R_slant": R,
    })
    assert out["alpha_atm"] >= 0.0
    assert out["alpha_mol_abs"] >= 0.0
    assert out["alpha_mol_scat"] >= 0.0
    assert out["alpha_aer_abs"] >= 0.0
    assert out["alpha_aer_scat"] >= 0.0


# ---------------------------------------------------------------------------
# M6 — Strehl bounds and N_D positivity
# ---------------------------------------------------------------------------

@DERANDOMIZED
@given(
    P=st.floats(min_value=100.0, max_value=100_000.0),
    w=_w_target,
    alpha=_alpha_atm,
    v_perp=_v_perp,
    R=_R,
    T=_T_amb,
)
def test_m6_strehl_in_unit_interval(P, w, alpha, v_perp, R, T):
    """0 ≤ S_TB ≤ 1 for all legal M6 inputs. This is CLAUDE §7.1
    invariant: S_TB = 1/(1+(N_D/5)²) is bounded by construction."""
    out = m6_blooming.compute({
        "P_propagating": P, "w_at_target": w, "alpha_atm": alpha,
        "v_perp": v_perp, "R_slant": R, "T_ambient": T, "P_atm": 101325.0,
    })
    assert 0.0 <= out["S_TB"] <= 1.0
    assert out["N_D"] >= 0.0
    assert out["w_bloom"] >= 0.0


# ---------------------------------------------------------------------------
# M7 — PIB in [0,1], quadrature floor, monotonicity
# ---------------------------------------------------------------------------

def _m7_inputs_draw(P_exit, tau, w0, M2, lam, L, sigma, S, w_bloom, d_aim):
    zR = math.pi * w0 ** 2 / lam
    return {
        "P_exit": P_exit, "tau_atm": tau, "w0": w0, "zR": zR, "M2": M2,
        "wavelength": lam, "R_slant": L, "sigma_jit": sigma,
        "r0_sph": math.inf, "S_TB": S, "w_bloom": w_bloom, "d_aim": d_aim,
    }


@DERANDOMIZED
@given(
    P_exit=st.floats(min_value=50.0, max_value=100_000.0),
    tau=_tau_atm,
    w0=st.floats(min_value=0.01, max_value=0.25),  # = D/2, D in [0.02,0.50]
    M2=_m2,
    lam=_wavelength,
    L=_R,
    sigma=_sigma_jit,
    S=_S_TB,
    w_bloom=st.floats(min_value=0.0, max_value=0.5),
    d_aim=_d_aim,
)
def test_m7_pib_in_unit_interval(P_exit, tau, w0, M2, lam, L, sigma, S, w_bloom, d_aim):
    """PIB_fraction ∈ [0, 1] for any legal M7 inputs."""
    out = m7_spot_pib.compute(_m7_inputs_draw(
        P_exit, tau, w0, M2, lam, L, sigma, S, w_bloom, d_aim,
    ))
    assert 0.0 <= out["PIB_fraction"] <= 1.0


@DERANDOMIZED
@given(
    P_exit=st.floats(min_value=50.0, max_value=100_000.0),
    tau=_tau_atm,
    w0=st.floats(min_value=0.01, max_value=0.25),
    M2=_m2,
    lam=_wavelength,
    L=_R,
    sigma=_sigma_jit,
    S=_S_TB,
    w_bloom=st.floats(min_value=0.0, max_value=0.5),
    d_aim=_d_aim,
)
def test_m7_w_total_is_quadrature_floor(P_exit, tau, w0, M2, lam, L, sigma, S, w_bloom, d_aim):
    """w_total ≥ w_diff, w_turb, w_jit, w_bloom — each component is a
    non-negative contribution to the quadrature (CLAUDE §7.1)."""
    out = m7_spot_pib.compute(_m7_inputs_draw(
        P_exit, tau, w0, M2, lam, L, sigma, S, w_bloom, d_aim,
    ))
    # Floating-point slack: allow a tiny 1e-12 rel margin (the quadrature
    # adds two small numbers whose round-off can go either way).
    assert out["w_total"] >= out["w_diff"] * (1.0 - 1e-12)
    assert out["w_total"] >= out["w_turb"] * (1.0 - 1e-12)
    assert out["w_total"] >= out["w_jit"] * (1.0 - 1e-12)
    assert out["w_total"] >= w_bloom * (1.0 - 1e-12)


# ---------------------------------------------------------------------------
# M9 — NOHD monotonicity and ordering
# ---------------------------------------------------------------------------

@DERANDOMIZED
@given(
    P0=_p0,
    M2=_m2,
    D=_d_aperture,
    lam=_wavelength,
    t_exp=st.floats(min_value=0.25, max_value=100.0),
)
def test_m9_nohd_ordering(P0, M2, D, lam, t_exp):
    """NOHD_gausspeak ≥ NOHD_tophat always — CLAUDE §7.1 invariant."""
    out1 = m1_laser_source.compute({
        "P0": P0, "M2": M2, "D": D, "wavelength": lam,
    })
    out9 = m9_nohd.compute({
        "P0": P0, "D": D, "theta_diff": out1["theta_diff"],
        "wavelength": lam, "t_exp": t_exp,
    })
    assert out9["NOHD_gausspeak"] >= out9["NOHD_tophat"]
    assert out9["NOHD_tophat"] >= 0.0
    assert out9["NOHD_gausspeak"] >= 0.0


@DERANDOMIZED
@given(
    P0_lo=st.floats(min_value=100.0, max_value=10_000.0),
    k=st.floats(min_value=1.01, max_value=10.0),
    M2=_m2,
    D=_d_aperture,
    lam=_wavelength,
    t_exp=st.floats(min_value=0.25, max_value=100.0),
)
def test_m9_nohd_monotone_in_power(P0_lo, k, M2, D, lam, t_exp):
    """NOHD (both forms) are monotonically non-decreasing in P0."""
    P0_hi = min(P0_lo * k, 100_000.0)
    if P0_hi <= P0_lo:
        return
    out1_lo = m1_laser_source.compute({"P0": P0_lo, "M2": M2, "D": D, "wavelength": lam})
    out1_hi = m1_laser_source.compute({"P0": P0_hi, "M2": M2, "D": D, "wavelength": lam})
    out9_lo = m9_nohd.compute({
        "P0": P0_lo, "D": D, "theta_diff": out1_lo["theta_diff"],
        "wavelength": lam, "t_exp": t_exp,
    })
    out9_hi = m9_nohd.compute({
        "P0": P0_hi, "D": D, "theta_diff": out1_hi["theta_diff"],
        "wavelength": lam, "t_exp": t_exp,
    })
    assert out9_hi["NOHD_tophat"] >= out9_lo["NOHD_tophat"] - 1e-9
    assert out9_hi["NOHD_gausspeak"] >= out9_lo["NOHD_gausspeak"] - 1e-9


# ---------------------------------------------------------------------------
# M10 — duty cycle in [0,1]; engagement_viable is bool
# ---------------------------------------------------------------------------

@DERANDOMIZED
@given(
    P0=_p0,
    eta=_eta_wall,
    Q_cool=st.floats(min_value=0.0, max_value=100_000.0),
    C=st.floats(min_value=1e3, max_value=1e6),
    dT=_dT_max,
    t_eng=_t_engagement,
)
def test_m10_duty_in_unit_interval(P0, eta, Q_cool, C, dT, t_eng):
    """duty_cycle_limit ∈ [0, 1]; engagements_per_hour ≥ 0."""
    out = m10_power_thermal.compute({
        "P0": P0, "eta_wallplug": eta, "Q_cool": Q_cool,
        "C_thermal": C, "dT_max": dT, "t_engagement": t_eng,
    })
    assert 0.0 <= out["duty_cycle_limit"] <= 1.0
    assert out["engagements_per_hour"] >= 0.0
    assert isinstance(out["engagement_viable"], bool)
    assert out["P_in"] > 0.0
    assert out["Q_waste"] >= 0.0


# ---------------------------------------------------------------------------
# M3 — dwell non-negative; R_slant = R
# ---------------------------------------------------------------------------

@DERANDOMIZED
@given(
    H_e=st.floats(min_value=0.0, max_value=3000.0),
    R=st.floats(min_value=100.0, max_value=50_000.0),
    H_t=st.floats(min_value=0.0, max_value=5000.0),
    v_tgt=_v_tgt,
    v_perp=st.floats(min_value=0.0, max_value=30.0),
)
def test_m3_dwell_nonnegative(H_e, R, H_t, v_tgt, v_perp):
    """v1.x backward-compat: available_dwell ≥ 0 whenever the geometry
    is feasible (R ≥ |H_t − H_e|); infeasible → ValueError."""
    try:
        out = m3_geometry.compute({
            "H_e": H_e, "R": R, "H_t": H_t, "v_tgt": v_tgt, "v_perp": v_perp,
        })
    except ValueError:
        # Infeasible geometry is the correct failure mode; property holds.
        return
    assert out["R_slant"] == R
    assert out["R_h"] >= 0.0
    assert out["available_dwell"] >= 0.0


# ---------------------------------------------------------------------------
# M3 v2.0 — trajectory dwell ≥ 0 across both geometries (SPEC v2.0 §3 M3).
# Hypothesis fuzzes (R_detect, R_min, v_tgt, geometry) over the
# validator-accepted region; t_dwell must come out non-negative for
# every feasible draw, and a ValueError is the only legitimate failure
# mode for infeasible draws.
# ---------------------------------------------------------------------------

@DERANDOMIZED
@given(
    H_e=st.floats(min_value=0.0, max_value=3000.0),
    H_t=st.floats(min_value=0.0, max_value=5000.0),
    R_detect=st.floats(min_value=50.0, max_value=50_000.0),
    R_min=st.floats(min_value=10.0, max_value=5_000.0),
    v_tgt=st.floats(min_value=0.0, max_value=100.0),
    geometry=st.sampled_from(["head_on", "lateral"]),
)
def test_m3_v2_dwell_nonnegative(H_e, H_t, R_detect, R_min, v_tgt, geometry):
    """v2.0 trajectory dwell is non-negative for every validator-accepted
    (R_detect, R_min, v_tgt, geometry). Infeasible geometries (R_detect
    < R_min, R_detect < |H_t − H_e|, etc.) raise ValueError, which is
    the correct response."""
    try:
        out = m3_geometry.compute({
            "H_e": H_e, "H_t": H_t, "R_detect": R_detect, "R_min": R_min,
            "v_tgt": v_tgt, "engagement_geometry": geometry,
        })
    except ValueError:
        # Validator rejection is the correct failure mode; property holds.
        return
    assert out["R_slant"] == R_detect
    assert out["R_h"] >= 0.0
    assert out["available_dwell"] >= 0.0
    assert out["R_at_dwell_end"] >= 0.0


@DERANDOMIZED
@given(
    R_detect=st.floats(min_value=200.0, max_value=20_000.0),
    R_min=st.floats(min_value=10.0, max_value=2_000.0),
    v_tgt=st.floats(min_value=0.5, max_value=100.0),
    geometry=st.sampled_from(["head_on", "lateral"]),
)
def test_m3_v2_dwell_zero_only_when_R_detect_equals_R_min(
    R_detect, R_min, v_tgt, geometry,
):
    """Dwell goes to zero only at the degenerate R_detect = R_min
    boundary. For strictly R_detect > R_min and v_tgt > 0, the dwell
    is strictly positive — a regression guard against silent zero-dwell
    bugs that would make every engagement fail."""
    if R_detect <= R_min:
        return  # validator rejects; covered elsewhere
    if v_tgt < m_trajectory_module().STATIONARY_THRESHOLD_MPS:
        return  # stationary edge case has its own dwell value
    dwell = m_trajectory_module().available_dwell(
        R_detect, R_min, v_tgt, geometry,
    )
    assert dwell > 0.0


def m_trajectory_module():
    """Lazy import wrapper — keeps module-level imports clean."""
    from physics import m_trajectory
    return m_trajectory


# ---------------------------------------------------------------------------
# Orchestrator — full-chain determinism and invariants
# ---------------------------------------------------------------------------

def _chain_inputs(canonical_inputs, P0, M2, D, lam, eta_opt, sigma_jit, R, v_tgt,
                  v_perp, V, RH, d_aim):
    """Build a full chain-input dict from a canonical baseline + overrides."""
    return {
        **canonical_inputs,
        "P0": P0, "M2": M2, "D": D, "wavelength": lam, "eta_opt": eta_opt,
        "sigma_jit": sigma_jit, "R": R, "v_tgt": v_tgt, "v_perp": v_perp,
        "V": V, "RH": RH, "d_aim": d_aim,
    }


@DERANDOMIZED
@given(
    P0=_p0, M2=_m2, D=_d_aperture, lam=_wavelength, eta_opt=_eta_opt,
    sigma_jit=st.floats(min_value=1e-7, max_value=1e-4),
    R=st.floats(min_value=500.0, max_value=20_000.0),
    v_tgt=st.floats(min_value=1.0, max_value=100.0),
    v_perp=st.floats(min_value=1.0, max_value=30.0),
    V=st.floats(min_value=5.0, max_value=50.0),
    RH=_RH,
    d_aim=st.floats(min_value=0.01, max_value=0.20),
)
def test_orchestrator_w_total_floor_fuzz(canonical_inputs, P0, M2, D, lam,
                                         eta_opt, sigma_jit, R, v_tgt, v_perp, V, RH, d_aim):
    """w_total ≥ w_diff for every full-chain run reachable from the
    canonical baseline via single-axis overrides."""
    inputs = _chain_inputs(canonical_inputs, P0, M2, D, lam, eta_opt,
                           sigma_jit, R, v_tgt, v_perp, V, RH, d_aim)
    # H_t ≤ R constraint — skip drawn cases that would be infeasible.
    if inputs["R"] < abs(inputs["H_t"] - inputs["H_e"]):
        return
    result = orchestrator.run_full_chain(inputs)
    assert result["w_total"] >= result["w_diff"] * (1.0 - 1e-10)


@DERANDOMIZED
@given(
    P0=_p0, M2=_m2, D=_d_aperture, lam=_wavelength, eta_opt=_eta_opt,
    sigma_jit=st.floats(min_value=1e-7, max_value=1e-4),
    R=st.floats(min_value=500.0, max_value=20_000.0),
    v_tgt=st.floats(min_value=1.0, max_value=100.0),
    v_perp=st.floats(min_value=1.0, max_value=30.0),
    V=st.floats(min_value=5.0, max_value=50.0),
    RH=_RH,
    d_aim=st.floats(min_value=0.01, max_value=0.20),
)
def test_orchestrator_m67_iter_bounded(canonical_inputs, P0, M2, D, lam,
                                       eta_opt, sigma_jit, R, v_tgt, v_perp, V, RH, d_aim):
    """m67_iteration_count ∈ [1, 10] always (even when it fails to
    converge, the loop respects the max_iter cap)."""
    inputs = _chain_inputs(canonical_inputs, P0, M2, D, lam, eta_opt,
                           sigma_jit, R, v_tgt, v_perp, V, RH, d_aim)
    if inputs["R"] < abs(inputs["H_t"] - inputs["H_e"]):
        return
    result = orchestrator.run_full_chain(inputs)
    assert 1 <= result["m67_iteration_count"] <= 10


@DERANDOMIZED
@given(
    P0=_p0, M2=_m2, D=_d_aperture, lam=_wavelength, eta_opt=_eta_opt,
    sigma_jit=st.floats(min_value=1e-7, max_value=1e-4),
    R=st.floats(min_value=500.0, max_value=20_000.0),
    v_tgt=st.floats(min_value=1.0, max_value=100.0),
    v_perp=st.floats(min_value=1.0, max_value=30.0),
    V=st.floats(min_value=5.0, max_value=50.0),
    RH=_RH,
    d_aim=st.floats(min_value=0.01, max_value=0.20),
)
def test_orchestrator_strehl_and_pib_bounded(canonical_inputs, P0, M2, D, lam,
                                             eta_opt, sigma_jit, R, v_tgt, v_perp, V, RH, d_aim):
    """S_TB ∈ [0,1] and PIB_fraction ∈ [0,1] for every reachable input."""
    inputs = _chain_inputs(canonical_inputs, P0, M2, D, lam, eta_opt,
                           sigma_jit, R, v_tgt, v_perp, V, RH, d_aim)
    if inputs["R"] < abs(inputs["H_t"] - inputs["H_e"]):
        return
    result = orchestrator.run_full_chain(inputs)
    assert 0.0 <= result["S_TB"] <= 1.0
    assert 0.0 <= result["PIB_fraction"] <= 1.0
    assert 0.0 <= result["tau_atm"] <= 1.0
