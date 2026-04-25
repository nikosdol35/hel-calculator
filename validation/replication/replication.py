"""Independent replication — Layer 5 of the validation campaign.

This file re-implements the calculator's most consequential physics
outputs from first-principles formulas using only numpy + scipy. Nothing
under physics/ is imported. The outputs are then compared to the
orchestrator's outputs at the three canonical scenarios from
tests/golden/scenarios.py; agreement target is ≤ 5% — directional
confirmation that the calculator is in the right neighborhood, not a
bit-for-bit match.

Modules replicated independently:
  M1 — Gaussian-beam divergence, Rayleigh range, exit-aperture irradiance
  M5 — spherical-wave Fried r₀ via the HV-5/7 Cn² profile and a quadrature
       integral of the (z/L)^(5/3) weighting, plus engineering w_turb
  M7 — exact-Gaussian w_diff(L), quadrature-sum spot, jitter contribution
  M8 — 1-D transient heat PDE via an independent explicit finite-difference
       scheme; surface flux + convective backside; runtime exit at T_fail
  M9 — ANSI Z136.1 piecewise MPE (Band A only, since all three scenarios
       are NIR) and top-hat NOHD

Modules deliberately NOT replicated independently (out of scope per the
campaign plan):
  M2 (P_exit = η · P0 — trivial scalar)
  M3 (slant/horizontal trig — already covered by Package 1 derivation)
  M4 (atmosphere — relies on the same McClatchey table, replication adds
      no signal; cross-check is a Package 4 HITRAN refresh path)
  M6 thermal blooming (the 4√2 prefactor and 0.3 broadening allocation
     are themselves engineering — independent replication still hits the
     same engineering choices)
  M10 (power-thermal arithmetic — covered by cross-module test in Package 2)
  M11 (validation runner — meta)

Run: python validation/replication/replication.py

Output: prints a per-scenario comparison table to stdout and writes
validation/replication/results.json with the raw numbers.
"""
from __future__ import annotations

import json
import math
import sys
from pathlib import Path

import numpy as np
from scipy.integrate import quad

# ---------------------------------------------------------------------------
# Independent M1 — Gaussian-beam closed forms
# ---------------------------------------------------------------------------
def m1_independent(P0: float, M2: float, D: float, wavelength: float) -> dict:
    """Gaussian-beam fundamentals.

    Per Siegman 1986 §17 / Born & Wolf §8:
      w₀ = D / 2                          (1/e² beam radius from aperture diameter)
      θ_diff = M² · 4·λ / (π·D)            (FULL-ANGLE 1/e² divergence,
                                            equivalent to 2·M²·λ/(π·w₀);
                                            project's convention per SPEC §3 M1)
      z_R = π · w₀² / λ                   (Rayleigh range, M²=1 form)
      I_exit = 2 · P0 / (π · w₀²)         (peak irradiance at exit aperture)
    """
    w0 = D / 2.0
    # Full-angle convention to match the project — both halves of the
    # 1/e² cone, in radians.
    theta_diff = M2 * 4.0 * wavelength / (math.pi * D)
    zR = math.pi * w0 * w0 / wavelength
    I_exit = 2.0 * P0 / (math.pi * w0 * w0)
    return {"w0": w0, "theta_diff": theta_diff, "zR": zR, "I_exit": I_exit}


# ---------------------------------------------------------------------------
# Independent M5 — HV-5/7 Cn² and spherical-wave r₀
# ---------------------------------------------------------------------------
def cn2_hv57(z: float, v_HV: float, Cn2_ground: float) -> float:
    """HV-5/7 Cn² profile, m^(-2/3), per Hufnagel 1974 + Valley 1980.

      Cn²(z) = 0.00594 · (v/27)² · (z·1e-5)^10 · exp(-z/1000)
             + 2.7e-16 · exp(-z/1500)
             + Cn2_ground · exp(-z/100)

    All three terms in m^(-2/3); z in m; v in m/s.
    """
    high_alt = 0.00594 * (v_HV / 27.0) ** 2 * (z * 1e-5) ** 10 * math.exp(-z / 1000.0)
    mid_alt = 2.7e-16 * math.exp(-z / 1500.0)
    boundary = Cn2_ground * math.exp(-z / 100.0)
    return high_alt + mid_alt + boundary


def m5_independent(
    L: float,
    wavelength: float,
    v_HV: float,
    Cn2_ground: float,
    H_e: float,
    H_t: float,
) -> dict:
    """Spherical-wave Fried coherence length and engineering w_turb.

    Per Andrews & Phillips 2005 §6.5 + CLAUDE §7.1 invariants:
      r₀_sph = (0.423 · k² · ∫₀^L Cn²(z(s)) · (s/L)^(5/3) ds)^(-3/5)
      w_turb = 2L / (k · r₀_sph)

    Path parameterization: s ∈ [0, L] is along the slant; altitude on the
    path linearly interpolates from H_e (at s=0) to H_t (at s=L). Cn²
    samples the altitude, not the path coordinate.
    """
    k = 2.0 * math.pi / wavelength

    def integrand(s: float) -> float:
        # Linear altitude interpolation along the slant path.
        z = H_e + (H_t - H_e) * (s / L)
        return cn2_hv57(z, v_HV, Cn2_ground) * (s / L) ** (5.0 / 3.0)

    # quad with adaptive limits; the (s/L)^(5/3) factor vanishes at s=0 so
    # the integral is well-behaved. The project's `Cn2_integrated` output
    # IS this weighted integral (SPEC §3 M5 outputs table) — not the bare
    # profile integral. Match the project key here.
    Cn2_integrated, _err = quad(integrand, 0.0, L, limit=200)

    r0_sph = (0.423 * k * k * Cn2_integrated) ** (-3.0 / 5.0)
    w_turb = 2.0 * L / (k * r0_sph)
    return {
        "Cn2_integrated": Cn2_integrated,
        "r0_sph": r0_sph,
        "w_turb": w_turb,
    }


# ---------------------------------------------------------------------------
# Independent M7 — exact-Gaussian spot and quadrature-sum total
# ---------------------------------------------------------------------------
def m7_independent(
    P_exit: float,
    tau_atm: float,
    S_TB: float,
    L: float,
    M2: float,
    w0: float,
    zR: float,
    sigma_jit: float,
    w_turb: float,
    w_bloom: float = 0.0,
) -> dict:
    """Exact-Gaussian propagation + quadrature-sum spot.

    Per CLAUDE §7.1 invariants (re-stated, not imported):
      w_diff(L) = w₀ · sqrt(1 + (M² · L / z_R)²)
      w_jit    = 2 · σ_jit · L                                   (per-axis σ)
      w_total² = w_diff² + w_turb² + w_jit² + w_bloom²
      I_peak   = 2 · P_exit · τ_atm · S_TB / (π · w_total²)
                                          (Strehl on numerator; S_total
                                           = S_TB·S_opt and S_opt=1 in v1
                                           per SPEC §3 M7)

    M2/M4/M6 outputs (P_exit, tau_atm, S_TB) are taken from the
    orchestrator since this layer does not replicate those modules.
    """
    w_diff = w0 * math.sqrt(1.0 + (M2 * L / zR) ** 2)
    w_jit = 2.0 * sigma_jit * L
    w_total = math.sqrt(w_diff ** 2 + w_turb ** 2 + w_jit ** 2 + w_bloom ** 2)
    I_peak = 2.0 * P_exit * tau_atm * S_TB / (math.pi * w_total ** 2)
    return {
        "w_diff": w_diff,
        "w_jit": w_jit,
        "w_total": w_total,
        "I_peak": I_peak,
    }


# ---------------------------------------------------------------------------
# Independent M8 — 1-D transient heat solver (independent FD code)
# ---------------------------------------------------------------------------
# Material table — same SPEC values; copied locally to keep replication
# independent of physics/m8_material_tables.py.
_MAT_PROPS = {
    "anodized_Al":    {"rho": 2700.0, "c_p":  900.0, "k": 200.0, "T_fail": 933.0,
                       "L_f": 397_000.0, "mode": "melt"},
    "CFRP":           {"rho": 1600.0, "c_p": 1000.0, "k":   7.0, "T_fail": 600.0,
                       "L_f": None,     "mode": "decomposition"},
    "GFRP":           {"rho": 1900.0, "c_p":  800.0, "k":   0.4, "T_fail": 600.0,
                       "L_f": None,     "mode": "decomposition"},
    "polycarbonate":  {"rho": 1200.0, "c_p": 1200.0, "k":   0.2, "T_fail": 700.0,
                       "L_f": None,     "mode": "decomposition"},
    "ABS":            {"rho": 1050.0, "c_p": 1400.0, "k":  0.17, "T_fail": 670.0,
                       "L_f": None,     "mode": "decomposition"},
    "EPP_foam":       {"rho":   30.0, "c_p": 1900.0, "k":  0.04, "T_fail": 620.0,
                       "L_f": None,     "mode": "decomposition"},
    "LiPo":           {"rho": 1800.0, "c_p": 1000.0, "k":   0.5, "T_fail": 420.0,
                       "L_f": None,     "mode": "vent"},
}

_A_LAMBDA = {
    "anodized_Al":    (0.30, 0.30, 0.25, 0.20),
    "CFRP":           (0.85, 0.85, 0.85, 0.85),
    "GFRP":           (0.40, 0.40, 0.45, 0.55),
    "polycarbonate":  (0.10, 0.10, 0.30, 0.60),
    "ABS":            (0.70, 0.70, 0.75, 0.85),
    "EPP_foam":       (0.50, 0.50, 0.55, 0.70),
    "LiPo":           (0.30, 0.30, 0.35, 0.45),
}
_LAMBDA_NODES = (1.06e-6, 1.07e-6, 1.55e-6, 2.05e-6)


def _lookup_a_lambda(material: str, wavelength: float) -> float:
    """Linear interpolation A_λ table; clamp at endpoints."""
    nodes = _LAMBDA_NODES
    table = _A_LAMBDA[material]
    if wavelength <= nodes[0]:
        return table[0]
    if wavelength >= nodes[-1]:
        return table[-1]
    for i in range(len(nodes) - 1):
        if nodes[i] <= wavelength <= nodes[i + 1]:
            t = (wavelength - nodes[i]) / (nodes[i + 1] - nodes[i])
            return table[i] + t * (table[i + 1] - table[i])
    return table[-1]


def m8_independent(
    I_avg_aim: float,
    material: str,
    thickness: float,
    wavelength: float,
    T_ambient: float,
    v_tgt: float,
    t_max: float = 60.0,
) -> dict:
    """Independent explicit-FD 1-D heat solver.

    Boundary conditions:
      Front face (x=0): -k ∂T/∂x = q_in, with
                         q_in = A_λ · I_avg_aim − ε · σ · (T⁴ − T_amb⁴)
      Back face (x=L):  -k ∂T/∂x = h · (T − T_amb), with
                         h = 10 + 6.2·sqrt(v_tgt)
      ε = 0.85; σ = Stefan-Boltzmann; failure at T_surface ≥ T_fail.

    Returns dict with tau_BT (s) and T_peak_K. tau_BT is the time the
    front face first reaches T_fail; if t_max elapses without failure,
    returns inf.
    """
    props = _MAT_PROPS[material]
    rho, cp, k = props["rho"], props["c_p"], props["k"]
    T_fail = props["T_fail"]
    A_lam = _lookup_a_lambda(material, wavelength)
    eps = 0.85
    sigma = 5.670374419e-8
    h_back = 10.0 + 6.2 * math.sqrt(max(v_tgt, 0.0))

    # Spatial grid — same nominal dx as the project (50 µm), with
    # min 21 nodes. Independent choice of N_min = 21 to satisfy the
    # explicit-FD CFL with safety; chosen identically to project for a
    # like-for-like comparison.
    N = max(21, int(math.ceil(thickness / 5.0e-5)) + 1)
    dx = thickness / (N - 1)
    alpha = k / (rho * cp)
    # CFL: dt < dx²/(2α); use 0.4 safety.
    dt = 0.4 * dx * dx / (2.0 * alpha)
    n_steps = int(math.ceil(t_max / dt))

    T = np.full(N, T_ambient, dtype=np.float64)
    t = 0.0
    tau_BT = math.inf
    T_peak = T_ambient

    q_abs = A_lam * I_avg_aim
    for _ in range(n_steps):
        # Interior: explicit central-difference.
        T_new = T.copy()
        T_new[1:-1] = T[1:-1] + alpha * dt / (dx * dx) * (T[2:] - 2.0 * T[1:-1] + T[:-2])

        # Front face (x=0): ghost-node Neumann.
        # BC: -k · ∂T/∂x = q_in_eff (heat flowing INTO the slab in +x direction).
        # 2nd-order central: ∂T/∂x|_{x=0} ≈ (T[1] − T_ghost) / (2·dx).
        #     → T_ghost = T[1] + 2·dx·q_in_eff/k    (ghost is HOTTER than T[1])
        q_in_eff = q_abs - eps * sigma * (T[0] ** 4 - T_ambient ** 4)
        T_ghost_front = T[1] + 2.0 * dx * q_in_eff / k
        T_new[0] = T[0] + alpha * dt / (dx * dx) * (T[1] - 2.0 * T[0] + T_ghost_front)

        # Back face (x=L): convective BC -k(T_g - T_{N-2})/(2dx) = h·(T_{N-1}-T_amb)
        # → T_g = T_{N-2} - 2·dx·h·(T[N-1]-T_amb)/k. Central-diff at i=N-1.
        q_back = h_back * (T[-1] - T_ambient)
        T_ghost_back = T[-2] - 2.0 * dx * q_back / k
        T_new[-1] = T[-1] + alpha * dt / (dx * dx) * (T[-2] - 2.0 * T[-1] + T_ghost_back)

        T = T_new
        t += dt
        if T[0] > T_peak:
            T_peak = T[0]
        if T[0] >= T_fail and tau_BT == math.inf:
            tau_BT = t
            break

    return {"tau_BT": tau_BT, "T_peak_K": float(T_peak), "A_lambda_used": A_lam}


# ---------------------------------------------------------------------------
# Independent M9 — ANSI Z136.1 piecewise Band A MPE + top-hat NOHD
# ---------------------------------------------------------------------------
def mpe_wpm2(wavelength: float, t_exp: float) -> float:
    """ANSI Z136.1-2014 piecewise retinal MPE. No C_A applied (conservative
    per SPEC §10.3 disposition). Returns W/m².

    Band A (400–1400 nm) and Band B (1400–4000 nm) are distinguished. v1.12
    pulsed-regime constant 5e-7 J/cm² used (matches Package 3 paired SPEC +
    code edit).
    """
    BAND_A_HI = 1.4e-6
    if wavelength < BAND_A_HI:
        # Band A
        if t_exp < 18e-6:
            return (5.0e-7 / t_exp) * 1.0e4   # W/cm² → W/m²
        if t_exp <= 10.0:
            return 1.8e-3 * (t_exp ** (-0.25)) * 1.0e4
        return 1.0e-3 * 1.0e4   # chronic
    # Band B
    if t_exp <= 10.0:
        return 0.56 * (t_exp ** (-0.75)) * 1.0e4
    return 0.1 * 1.0e4   # chronic


def m9_independent(
    P0: float, theta_full: float, D: float, t_exp: float, wavelength: float
) -> dict:
    """ANSI NOHD top-hat AND Gaussian-peak conventions per SPEC §3 M9.

    range_tophat    = (1/θ)·√(4·P0/(π·MPE))
    range_gausspeak = (1/θ)·√(8·P0/(π·MPE))
    aperture_correction = D / θ                  (beam fills aperture at distance D/θ)
    NOHD            = max(0, range − aperture_correction)

    Project's `theta_diff` is already full-angle (M²·4λ/(π·D)) per
    SPEC §3 M1, so pass it in directly. MPE dispatch on wavelength
    handles the 1.4 µm Band A→B boundary.
    """
    mpe = mpe_wpm2(wavelength, t_exp)
    inv_theta = 1.0 / theta_full
    range_tophat = inv_theta * math.sqrt(4.0 * P0 / (math.pi * mpe))
    range_gausspeak = inv_theta * math.sqrt(8.0 * P0 / (math.pi * mpe))
    aperture_corr = D * inv_theta
    return {
        "MPE": mpe,
        "NOHD_tophat": max(0.0, range_tophat - aperture_corr),
        "NOHD_gausspeak": max(0.0, range_gausspeak - aperture_corr),
    }


# ---------------------------------------------------------------------------
# Comparison driver
# ---------------------------------------------------------------------------
def _rel_err(actual: float, expected: float) -> float:
    """Signed relative error in percent. Robust to zero/inf."""
    if not math.isfinite(actual) or not math.isfinite(expected):
        return math.nan
    if expected == 0.0:
        return math.nan if actual != 0.0 else 0.0
    return 100.0 * (actual - expected) / expected


def replicate_scenario(name: str, scen: dict, golden_path: Path) -> dict:
    """Run independent implementations for a scenario; load golden and
    compare. Returns a dict suitable for the report table."""
    with open(golden_path) as f:
        golden = json.load(f)

    out_m1 = m1_independent(scen["P0"], scen["M2"], scen["D"], scen["wavelength"])
    out_m5 = m5_independent(
        L=golden["R_slant"],   # use orchestrator's slant for an apples-to-apples M5
        wavelength=scen["wavelength"],
        v_HV=scen["v_HV"],
        Cn2_ground=scen["Cn2_ground"],
        H_e=scen["H_e"],
        H_t=scen["H_t"],
    )
    # M2/M4/M6 outputs come from the orchestrator (those modules are
    # not part of Layer 5 replication scope). This isolates the M5/M7
    # replication from those upstream modules.
    out_m7 = m7_independent(
        P_exit=golden["P_exit"],
        tau_atm=golden["tau_atm"],
        S_TB=golden["S_TB"],
        L=golden["R_slant"],
        M2=scen["M2"],
        w0=out_m1["w0"],
        zR=out_m1["zR"],
        sigma_jit=scen["sigma_jit"],
        w_turb=out_m5["w_turb"],
        w_bloom=golden["w_bloom"],
    )
    out_m8 = m8_independent(
        I_avg_aim=golden["I_avg_aim"],
        material=scen["material"],
        thickness=scen["thickness"],
        wavelength=scen["wavelength"],
        T_ambient=scen["T_ambient"],
        v_tgt=scen["v_tgt"],
    )
    out_m9 = m9_independent(
        P0=scen["P0"],
        theta_full=out_m1["theta_diff"],
        D=scen["D"],
        t_exp=scen["t_exp"],
        wavelength=scen["wavelength"],
    )

    # Build comparison table.
    rows = []
    pairs = [
        ("M1", "theta_diff",     out_m1["theta_diff"],     golden["theta_diff"]),
        ("M1", "w0",             out_m1["w0"],             golden["w0"]),
        ("M1", "zR",             out_m1["zR"],             golden["zR"]),
        ("M1", "I_exit",         out_m1["I_exit"],         golden["I_exit"]),
        ("M5", "Cn2_integrated", out_m5["Cn2_integrated"], golden["Cn2_integrated"]),
        ("M5", "r0_sph",         out_m5["r0_sph"],         golden["r0_sph"]),
        ("M5", "w_turb",         out_m5["w_turb"],         golden["w_turb"]),
        ("M7", "w_diff",         out_m7["w_diff"],         golden["w_diff"]),
        ("M7", "w_jit",          out_m7["w_jit"],          golden["w_jit"]),
        ("M7", "w_total",        out_m7["w_total"],        golden["w_total"]),
        ("M7", "I_peak",         out_m7["I_peak"],         golden["I_peak"]),
        ("M8", "tau_BT",         out_m8["tau_BT"],         golden["tau_BT"]),
        ("M9", "MPE",            out_m9["MPE"],            golden["MPE"]),
        ("M9", "NOHD_tophat",    out_m9["NOHD_tophat"],    golden["NOHD_tophat"]),
        ("M9", "NOHD_gausspeak", out_m9["NOHD_gausspeak"], golden["NOHD_gausspeak"]),
    ]
    for module, key, actual, expected in pairs:
        # M8 special case: project caps tau_BT at 60s timeout sentinel
        # while independent code returns inf for the same condition.
        # Both indicate "no burn-through within simulation window" —
        # verdict-level agreement.
        if (key == "tau_BT"
                and not math.isfinite(actual)
                and expected >= 59.99):
            rows.append({
                "module": module,
                "key": key,
                "independent": "no failure within 60s",
                "calculator": "no failure within 60s",
                "rel_err_pct": 0.0,
                "verdict_match": True,
            })
            continue
        rows.append({
            "module": module,
            "key": key,
            "independent": actual,
            "calculator": expected,
            "rel_err_pct": _rel_err(actual, expected),
        })
    return {"scenario": name, "rows": rows}


def main() -> int:
    repo_root = Path(__file__).resolve().parent.parent.parent
    golden_dir = repo_root / "tests" / "golden"
    sys.path.insert(0, str(repo_root))
    # Import only the scenario dicts — no physics module.
    from tests.golden.scenarios import SCENARIOS  # noqa: E402

    results = []
    for name, scen in SCENARIOS.items():
        golden_file = golden_dir / f"{name}.json"
        results.append(replicate_scenario(name, scen, golden_file))

    # Print summary to stdout.
    for scenario in results:
        print(f"\n=== Scenario: {scenario['scenario']} ===")
        print(f"{'Module':<8}{'Key':<18}{'Independent':>22}{'Calculator':>22}{'rel err %':>10}")
        print("-" * 80)
        for row in scenario["rows"]:
            ind = row["independent"]
            cal = row["calculator"]
            err = row["rel_err_pct"]
            if isinstance(ind, str):
                ind_s = ind
            elif math.isfinite(ind):
                ind_s = f"{ind:.4g}"
            else:
                ind_s = str(ind)
            if isinstance(cal, str):
                cal_s = cal
            elif math.isfinite(cal):
                cal_s = f"{cal:.4g}"
            else:
                cal_s = str(cal)
            if math.isfinite(err):
                err_s = f"{err:+.2f}"
            else:
                err_s = "n/a"
            print(f"{row['module']:<8}{row['key']:<18}{ind_s:>22}{cal_s:>22}{err_s:>10}")

    # Worst-case across all rows × scenarios.
    abs_errs = [
        abs(r["rel_err_pct"]) for s in results for r in s["rows"]
        if math.isfinite(r["rel_err_pct"])
    ]
    if abs_errs:
        print(f"\nWorst |rel err|: {max(abs_errs):.2f}% across "
              f"{sum(len(s['rows']) for s in results)} comparisons.")

    out_path = Path(__file__).parent / "results.json"
    with open(out_path, "w") as f:
        json.dump(results, f, indent=2)
    print(f"\nWrote {out_path}.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
