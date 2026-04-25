"""End-to-end worked example for the math tab.

A single canonical engagement walked through every formula in
dependency order, with concrete numbers at each step. The reader
sees how the inputs (3 kW, 1 km, 1.07 µm, CFRP) become the headline
outputs (tau_BT, NOHD, etc.) — and can check any number against the
formulas they read on the per-metric rows above.

Per the plan:
  - Static content (always the same scenario regardless of user
    inputs) — this is a teaching artifact, not the user's analysis.
    Their live values are in the per-metric "Value" column above.
  - The scenario uses the c_uas_short_range preset with R = 1000 m
    rather than the golden c_uas_1500m, per the user's choice on
    2026-04-25.

The walkthrough is computed live (via run_full_chain on the static
scenario inputs) so the values stay in sync with the underlying
physics implementation; if a future refactor changes a formula the
worked example updates automatically with the rest of the tool.
Cached at module level so it runs at most once per session.
"""
from __future__ import annotations

from dataclasses import dataclass, field


# Worked-example scenario — c_uas preset, head-on engagement
# starting at R_detect = 1500 m, closing to R_min = 100 m at v_tgt =
# 20 m/s (= 70 s engagement window). SPEC v2.0 §3 M3 trajectory model.
WORKED_EXAMPLE_INPUTS: dict = {
    # Panel A — Laser source
    "P0": 3000, "M2": 1.2, "D": 0.10, "wavelength": 1.07e-6,
    # Panel B — Beam director
    "eta_opt": 0.85, "sigma_jit": 10e-6,
    # Panel C — Engagement geometry (SPEC v2.0 trajectory contract —
    # head-on closing from 1.5 km to 100 m at 20 m/s)
    "H_e": 2, "R_detect": 1500, "R_min": 100, "H_t": 200,
    "v_tgt": 20, "engagement_geometry": "head_on",
    # Panel D — Atmosphere
    "V": 23, "RH": 0.60, "T_ambient": 300, "P_atm": 101325,
    "cn2_model": "HV_5_7", "Cn2_value": 1e-14,
    "Cn2_ground": 1.7e-14, "v_HV": 21,
    # Panel E — Aimpoint & material
    "d_aim": 0.05, "material": "CFRP", "thickness": 0.002,
    # Panel F — System resources & safety
    "eta_wallplug": 0.30, "Q_cool": 15000,
    "C_thermal": 200e3, "dT_max": 30, "t_exp": 0.25,
}


@dataclass(frozen=True)
class WalkthroughStep:
    """One numbered step in the worked example.

    The renderer formats each step as: a heading with the metric's
    display name + symbol; a one-line "given" telling the reader
    which upstream values feed this formula; the formula in LaTeX;
    the computed value; and a one-line "what this tells us" hook
    into the next step in the chain.
    """
    step_number: int
    metric_keys: tuple[str, ...]   # which MATH_CONTENT keys this step covers
    section_title: str             # heading, e.g. "1. Beam at the laser exit"
    given: str                     # "Given P0 = 3 kW, M² = 1.2, D = 10 cm, λ = 1.07 µm"
    narrative: str                 # 2-3 sentences explaining what this step does


# The 10-step chain. Each step covers one or two adjacent metrics
# from the same module so the reader sees logical groups (the four
# M1 outputs together, the four atmosphere components together,
# etc.) rather than 41 separate steps.
WALKTHROUGH_STEPS: tuple[WalkthroughStep, ...] = (
    WalkthroughStep(
        step_number=1,
        metric_keys=("theta_diff", "w0", "zR", "I_exit"),
        section_title="1 · Beam at the laser exit (M1)",
        given=(
            "Given P0 = 3 kW, M² = 1.2, D = 10 cm, λ = 1.07 µm. "
            "Aperture fills uniformly."
        ),
        narrative=(
            "Closed-form Gaussian-beam quantities. The launch radius is "
            "half the aperture diameter; the divergence inflates by M² "
            "above the diffraction-limited floor; the Rayleigh range "
            "tells us where pure diffraction takes over from "
            "near-collimated propagation; and the exit irradiance is "
            "the on-axis Gaussian peak, twice the spatial average."
        ),
    ),
    WalkthroughStep(
        step_number=2,
        metric_keys=("P_exit",),
        section_title="2 · Optical-train transmission (M2)",
        given="Given P0 = 3 kW, η_opt = 0.85.",
        narrative=(
            "Multiplicative loss across the optical train. Everything "
            "downstream uses P_exit, not P0, so optical efficiency "
            "directly scales the energy actually pointed at the target."
        ),
    ),
    WalkthroughStep(
        step_number=3,
        metric_keys=("R_slant", "R_h", "elevation_angle",
                     "available_dwell"),
        section_title="3 · Engagement geometry (M3)",
        given=(
            "Given R = 1000 m, H_e = 2 m, H_t = 200 m, "
            "v_tgt = 20 m/s. Default FOV = 5°."
        ),
        narrative=(
            "Pythagorean decomposition of the slant range into a "
            "horizontal component and an elevation angle. The dwell "
            "window is the time the target stays inside a 5°-FOV "
            "engagement basket at v_tgt — the available budget the "
            "burn-through time has to fit inside."
        ),
    ),
    WalkthroughStep(
        step_number=4,
        metric_keys=("alpha_mol_abs", "alpha_mol_scat",
                     "alpha_aer_abs", "alpha_aer_scat",
                     "alpha_atm", "tau_atm"),
        section_title="4 · Atmospheric transmission (M4)",
        given=(
            "Given λ = 1.07 µm, V = 23 km, RH = 60 %, "
            "R_slant = 1000 m."
        ),
        narrative=(
            "The four α components are looked up (molecular) or "
            "computed via the Kruse formula (aerosol), summed, and "
            "fed through the Beer–Lambert law to give τ_atm — the "
            "fraction of the beam's power that survives the trip "
            "to the target."
        ),
    ),
    WalkthroughStep(
        step_number=5,
        metric_keys=("Cn2_integrated", "r0_sph", "w_turb"),
        section_title="5 · Atmospheric turbulence (M5)",
        given=(
            "Given HV-5/7 Cn² profile (Cn2_ground = 1.7×10⁻¹⁴ "
            "m⁻²/³, v_HV = 21 m/s), λ = 1.07 µm, R_slant = 1000 m, "
            "altitudes H_e → H_t."
        ),
        narrative=(
            "scipy.integrate.quad evaluates the path-integral of "
            "Cn²·(z/L)^(5/3) along the slant; the Fried parameter is "
            "then a 0.423·k²·∫ to the −3/5 power; w_turb is the "
            "engineering long-term-average broadening that goes into "
            "the M7 quadrature sum."
        ),
    ),
    WalkthroughStep(
        step_number=6,
        metric_keys=("N_D", "S_TB", "w_bloom",
                     "w_diff", "w_jit", "w_total"),
        section_title="6 · Blooming and spot size — fixed-point loop (M6 ↔ M7)",
        given=(
            "Iterate M6 (blooming uses w_total) ↔ M7 (w_total uses "
            "w_bloom) until |Δw_total/w_total| < 1 %. Cap at 10 "
            "iterations."
        ),
        narrative=(
            "Each pass: (a) M6 computes the Gebhardt distortion "
            "number from the current spot, (b) M6 turns N_D into a "
            "blooming Strehl S_TB and a broadening w_bloom, (c) M7 "
            "quadrature-sums w_diff, w_turb, w_jit, and the new "
            "w_bloom into a fresh w_total. Convergence is typically "
            "2–4 passes; this run's iteration count is shown on the "
            "math tab."
        ),
    ),
    WalkthroughStep(
        step_number=7,
        metric_keys=("d_spot", "I_peak", "PIB_fraction",
                     "P_aim", "I_avg_aim"),
        section_title="7 · On-target intensities (M7 closed forms)",
        given="Given the converged w_total, P_exit, τ_atm, S_TB.",
        narrative=(
            "The peak irradiance is the Gaussian on-axis value at "
            "w_total, scaled by S_TB to capture how blooming dims "
            "the peak. PIB is the closed-form Gaussian fraction "
            "inside the aimpoint disk; multiplying it by "
            "P_exit·τ_atm·S_TB gives the actual wattage delivered "
            "into the bucket (P_aim), and dividing by the bucket "
            "area gives the average irradiance the burn-through "
            "model uses."
        ),
    ),
    WalkthroughStep(
        step_number=8,
        metric_keys=("tau_BT", "T_surface_peak", "E_delivered",
                     "failure_mode"),
        section_title="8 · Burn-through (M8 — explicit-FD heat solver)",
        given=(
            "Given I_avg_aim, CFRP material properties (ρ = 1600 "
            "kg/m³, c_p = 1000 J/(kg·K), k = 7 W/(m·K), "
            "T_fail = 600 K), thickness = 2 mm, "
            "T_amb = 300 K, A_λ = 0.85 (CFRP at 1.07 µm)."
        ),
        narrative=(
            "Explicit finite-difference integration of the 1-D heat "
            "PDE from t = 0 forward, with the absorbed flux at the "
            "front face and a convective backside BC. tau_BT is the "
            "first time the front-face temperature crosses 600 K — "
            "for CFRP that's the decomposition threshold."
        ),
    ),
    WalkthroughStep(
        step_number=9,
        metric_keys=("MPE", "NOHD_tophat", "NOHD_gausspeak",
                     "laser_class"),
        section_title="9 · Eye-safety budget (M9 — ANSI Z136.1)",
        given=(
            "Given P0 = 3 kW, θ_diff (full-angle), λ = 1.07 µm, "
            "t_exp = 0.25 s, D = 10 cm."
        ),
        narrative=(
            "Band A piecewise MPE at t = 0.25 s; conservative no-C_A "
            "convention. NOHD is computed under both top-hat and "
            "Gaussian-peak conventions with the D/θ aperture "
            "correction subtracted. P0 = 3 kW puts this firmly in "
            "Class 4."
        ),
    ),
    WalkthroughStep(
        step_number=10,
        metric_keys=("P_in", "Q_waste", "t_sustain",
                     "duty_cycle_limit", "engagements_per_hour",
                     "engagement_viable"),
        section_title="10 · Power and thermal resources (M10)",
        given=(
            "Given P0 = 3 kW, η_wallplug = 0.30, Q_cool = 15 kW, "
            "C_thermal = 200 kJ/K, dT_max = 30 K, "
            "t_engagement = tau_BT."
        ),
        narrative=(
            "Wall-plug input is P0/η; waste heat is the difference. "
            "If waste heat ≤ cooling capacity the system runs "
            "indefinitely; otherwise the lumped-mass coolant loop "
            "saturates after t_sustain. engagement_viable is True "
            "when tau_BT fits inside that window."
        ),
    ),
)


@dataclass(frozen=True)
class ComputedWalkthrough:
    """The fully computed worked example: scenario inputs, every
    orchestrator output (merged with inputs), and the static
    walkthrough steps. The renderer pairs each step with the
    metric values from the orchestrator result."""
    inputs: dict
    result: dict          # merged orchestrator result + user inputs
    steps: tuple[WalkthroughStep, ...] = field(
        default_factory=lambda: WALKTHROUGH_STEPS,
    )


def compute_worked_example() -> ComputedWalkthrough:
    """Run the full chain on the worked-example scenario and return
    the merged result. Pure function — same inputs every time."""
    # Local import keeps this module free of physics-layer references
    # at import time (the math tab shouldn't pay for the orchestrator
    # import unless the worked-example section actually renders).
    from physics.orchestrator import run_full_chain

    res = run_full_chain(WORKED_EXAMPLE_INPUTS)
    merged = {**WORKED_EXAMPLE_INPUTS, **res}
    return ComputedWalkthrough(
        inputs=WORKED_EXAMPLE_INPUTS, result=merged,
    )


__all__ = [
    "WORKED_EXAMPLE_INPUTS",
    "WALKTHROUGH_STEPS",
    "ComputedWalkthrough",
    "WalkthroughStep",
    "compute_worked_example",
]
