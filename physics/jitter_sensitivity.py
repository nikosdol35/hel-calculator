"""Jitter-sensitivity sweep — τ_BT vs σ_jit at fixed kinematics.

Plot N consumes this module's curve to show how the burn-through time
scales with pointing jitter, with the user's current scenario marked
as the 'you are here' star.

Pure module — no Streamlit imports.

**v3.2 (2026-04-27):** the sweep covers the full operational envelope
**1 µrad → 500 mrad on a log axis** (5.7 decades, 25 cells). Earlier
revisions tried linear with various ranges (0–50 µrad, 0–200 µrad,
dynamic expansion) but each broke a different scenario: low-jitter
showed only the green zone, high-jitter pushed the star off-chart.
Fixed log range plus colored feasibility zones gives the user a
consistent at-a-glance read regardless of σ_jit, and Plotly's
mouse-zoom lets them drill into any decade.

Two deliberate simplifications keep the sweep fast (~ms total instead
of ~minutes):

  1. **Lumped-mass τ_BT** instead of M8 PDE. The PDE per cell would
     cost 1-3 s. Lumped-mass:
         τ_BT_lumped = E_fail_jpcm2 / I_avg_aim_wpcm2
     Times an empirical 0.83 correction matching the PDE/lumped ratio
     measured during the closing-physics review (canonical scenario
     killed at 80 J/cm² vs lumped E_fail of 96 J/cm² → ratio 0.833).

  2. **Skip M6 blooming** (set w_bloom = 0 and S_TB = 1.0 in the
     sweep). M6↔M7 fixed-point would cost ~30-50 ms per cell.
     Blooming is a second-order effect that doesn't change the curve
     shape: it shifts the floor by a few percent at low σ_jit and is
     irrelevant at high σ_jit (PIB → 0 anyway).

Both simplifications are disclosed in the plot caption. The user's
actual scenario uses the full chain's PDE-accurate τ_BT for the
'you are here' star, so the headline metric and the star agree
even though they sit on slightly different curves.

Cost: ~20 closed-form arithmetic evaluations ≈ 30 µs total. The render
function calls this module directly (no Streamlit cache) — the cost
is imperceptible compared to the rest of the page render, and going
through the cache helper introduced a contract bug in v2 (chain
outputs were dropped before reaching this function, leaving every
cell at I_avg = 0 and triggering the all-no-kill fallback).
"""
from __future__ import annotations

import math
from dataclasses import dataclass


# Lumped-mass surface flux below which radiation losses outpace
# absorption — the surface can never reach T_fail no matter how long
# you wait. Same threshold Plot J uses to define its "useful zone."
_USEFUL_FLUX_THRESHOLD_WPCM2 = 1.0


# Empirical correction factor relating lumped-mass τ_BT to the PDE-
# accurate τ_BT. Measured during the closing-physics review (commit
# c62b3c7): canonical CFRP scenario kills at 80 J/cm² absorbed vs
# lumped-mass E_fail of 96 J/cm² → PDE/lumped ratio = 0.833. The PDE
# kills earlier than lumped-mass because the front face heats faster
# than the bulk does. Applied as τ_BT_curve = ratio × τ_BT_lumped to
# keep the curve within ~5 % of PDE-accurate values for typical
# materials.
_LUMPED_TO_PDE_RATIO = 0.83


@dataclass(frozen=True)
class JitterSensitivityCurve:
    """Output of `compute_jitter_sensitivity`.

    Holds the (σ_jit, τ_BT) sweep plus the user's "you are here"
    coordinate (which uses the chain's PDE-accurate τ_BT, not the
    lumped-mass approximation used for the curve).
    """
    sigma_jit_axis_urad: tuple[float, ...]    # log-spaced (v3.2, 2026-04-27)
    tau_BT_axis_s: tuple[float, ...]          # NaN in no-kill cells
    no_kill_mask: tuple[bool, ...]            # True where I_avg < threshold
    available_dwell_s: float
    kill_threshold_urad: float | None         # σ_jit where curve == dwell
    no_kill_threshold_urad: float | None      # smallest σ_jit at which I_avg < threshold
    current_sigma_jit_urad: float             # for the star
    current_tau_BT_s: float                   # PDE-accurate; from the chain


def _log_space(low: float, high: float, n: int) -> tuple[float, ...]:
    """Log-spaced grid of n points from low to high (inclusive).
    Both endpoints must be > 0."""
    if n < 2:
        return (low,)
    step = (math.log(high) - math.log(low)) / (n - 1)
    return tuple(math.exp(math.log(low) + i * step) for i in range(n))


def _e_fail_jpm2(material: str, thickness_m: float, T_amb_k: float) -> float | None:
    """Lumped-mass failure-fluence requirement (J/m²) for the user's
    target material + thickness. Returns None if the material is
    missing from the table or thickness is degenerate.

    E_fail = ρ · c_p · thickness · (T_fail − T_ambient)
    """
    if not thickness_m or thickness_m <= 0:
        return None
    try:
        from physics.m8_material_tables import MATERIAL_PROPERTIES
        if material not in MATERIAL_PROPERTIES:
            return None
        props = MATERIAL_PROPERTIES[material]
        delta_T = float(props["T_fail"]) - float(T_amb_k)
        if delta_T <= 0:
            return None
        return (
            float(props["rho"]) * float(props["c_p"])
            * float(thickness_m) * delta_T
        )
    except Exception:
        return None


def compute_jitter_sensitivity(
    base_inputs: dict,
    n_points: int = 25,
    sigma_jit_low_rad: float = 1.0e-6,        # 1 µrad
    sigma_jit_high_rad: float = 0.5,          # 500 mrad
) -> JitterSensitivityCurve:
    """Sweep σ_jit at the user's R_detect, return the τ_BT curve.

    Args:
      base_inputs: merged orchestrator-result dict (the same shape
        passed to ``render_tab_engagement``). Must include the v2.0
        trajectory key ``engagement_geometry`` and the chain outputs
        (``by_module``, ``tau_BT``, ``available_dwell``).
      n_points: grid points (default 25, log-spaced).
      sigma_jit_low_rad / sigma_jit_high_rad: sweep bounds (default
        1 µrad → 500 mrad).

    Returns:
      JitterSensitivityCurve with the curve + user's "you are here"
      coordinates.

    Raises:
      KeyError: when ``base_inputs`` is missing the v2.0 trajectory
        keys (this plot is v2-only).
    """
    if "engagement_geometry" not in base_inputs:
        raise KeyError(
            "compute_jitter_sensitivity requires v2.0 inputs "
            "(engagement_geometry must be present)"
        )

    # Pull the chain's M7 spot-size + M4 atmospheric + M1 power values
    # — all independent of σ_jit, so they're constants across the sweep.
    by = base_inputs.get("by_module") or {}
    m7 = by.get("m7", {})
    m4 = by.get("m4", {})
    m2_out = by.get("m2", {})

    w_diff = float(m7.get("w_diff", 0.0))
    w_turb = float(m7.get("w_turb", 0.0))
    # Skip blooming (set w_bloom = 0, S_TB = 1.0). See module docstring.
    w_bloom_squared = 0.0

    tau_atm = float(m7.get("tau_atm") or m4.get("tau_atm", 0.0))
    P_exit = float(m2_out.get("P_exit", 0.0))

    R_slant_m = float(base_inputs.get("R_detect") or base_inputs.get("R", 0.0))
    d_aim = float(base_inputs.get("d_aim", 0.05))
    R_aim = d_aim / 2.0

    # Material → E_fail. None when material is unknown / missing —
    # then the whole curve is no-kill and the plot renders as the
    # always-render frame.
    E_fail_jpm2 = _e_fail_jpm2(
        base_inputs.get("material"),
        base_inputs.get("thickness"),
        base_inputs.get("T_ambient", 293.0),
    )

    # Bucket-area term shows up in I_avg. Pre-compute.
    bucket_area_m2 = math.pi * R_aim * R_aim if R_aim > 0 else 0.0

    # Available dwell (constant across the sweep — depends only on R
    # and v_tgt). Read from the chain.
    available_dwell_s = float(
        by.get("m3", {}).get("available_dwell")
        or base_inputs.get("available_dwell", 0.0)
    )

    # User's chain-accurate τ_BT for the "you are here" star.
    current_tau_BT_s = float(base_inputs.get("tau_BT") or 0.0)
    current_sigma_jit_rad = float(base_inputs.get("sigma_jit", 0.0))

    # ── Sweep loop ─────────────────────────────────────────────────
    # Fixed log-spaced range covers the full operational envelope;
    # the user's σ_jit always falls within it, so the star is
    # always on-chart. Plotly's mouse-zoom lets the user drill into
    # specific decades.
    sigma_axis_rad = _log_space(
        sigma_jit_low_rad, sigma_jit_high_rad, n_points,
    )
    tau_BT_axis: list[float] = []
    no_kill_mask: list[bool] = []

    for sigma_jit_rad in sigma_axis_rad:
        # M7 spot-broadening with the new σ_jit (skip M6 blooming).
        w_jit = 2.0 * sigma_jit_rad * R_slant_m
        w_total_squared = (
            w_diff * w_diff
            + w_turb * w_turb
            + w_jit * w_jit
            + w_bloom_squared
        )
        if w_total_squared <= 0 or bucket_area_m2 <= 0:
            tau_BT_axis.append(float("nan"))
            no_kill_mask.append(True)
            continue

        # PIB on the bucket. Use the standard Gaussian-on-disk formula.
        try:
            pib_exponent = -2.0 * R_aim * R_aim / w_total_squared
            PIB = 1.0 - math.exp(pib_exponent)
        except (OverflowError, ValueError):
            PIB = 0.0

        # In-bucket power → bucket-averaged irradiance.
        # S_TB = 1 (skip M6); P_aim = P_exit · τ_atm · PIB.
        P_aim_w = P_exit * tau_atm * PIB
        I_avg_aim_wpm2 = P_aim_w / bucket_area_m2 if bucket_area_m2 > 0 else 0.0
        I_avg_aim_wpcm2 = I_avg_aim_wpm2 * 1.0e-4   # W/m² → W/cm²

        # No-kill regime: surface can't reach T_fail when radiation
        # losses outpace absorption. Same threshold as Plot J.
        if (E_fail_jpm2 is None
                or I_avg_aim_wpcm2 < _USEFUL_FLUX_THRESHOLD_WPCM2):
            tau_BT_axis.append(float("nan"))
            no_kill_mask.append(True)
            continue

        # Lumped-mass τ_BT with empirical PDE correction factor.
        tau_BT_lumped_s = E_fail_jpm2 / I_avg_aim_wpm2
        tau_BT_s = _LUMPED_TO_PDE_RATIO * tau_BT_lumped_s
        tau_BT_axis.append(tau_BT_s)
        no_kill_mask.append(False)

    # Threshold-detection helpers. Both are linear interpolations
    # between adjacent sweep cells.

    def _interp_log_x(x_lo: float, x_hi: float,
                      y_lo: float, y_hi: float, y_target: float) -> float:
        """Linear interp on log(x) for fixed y_target between (x_lo,
        y_lo) and (x_hi, y_hi). Used because the x-axis is log."""
        if y_hi == y_lo:
            return x_lo
        t = (y_target - y_lo) / (y_hi - y_lo)
        log_lo = math.log(x_lo)
        log_hi = math.log(x_hi)
        return math.exp(log_lo + t * (log_hi - log_lo))

    # No-kill threshold: smallest σ_jit at which the cell is no_kill.
    # When found, every σ_jit ≥ this value falls in the greyed region.
    no_kill_threshold_rad: float | None = None
    for i, is_no_kill in enumerate(no_kill_mask):
        if is_no_kill:
            no_kill_threshold_rad = sigma_axis_rad[i]
            break

    # Kill threshold: the boundary between feasible (τ_BT ≤ dwell)
    # and infeasible. Two ways infeasibility can kick in as σ_jit
    # grows: (a) τ_BT exceeds available_dwell, or (b) I_avg drops
    # below the no-kill threshold. Whichever comes first IS the
    # kill threshold. Annotation in the plot reads "Kill threshold:
    # σ_jit ≤ X µrad" — anything beyond X is infeasible.
    kill_threshold_rad: float | None = None
    if available_dwell_s > 0:
        for i in range(1, n_points):
            tau_lo = tau_BT_axis[i - 1]
            tau_hi = tau_BT_axis[i]
            # Case (a): adjacent finite cells where curve crosses dwell.
            if (not math.isnan(tau_lo) and not math.isnan(tau_hi)
                    and tau_lo <= available_dwell_s < tau_hi):
                kill_threshold_rad = _interp_log_x(
                    sigma_axis_rad[i - 1], sigma_axis_rad[i],
                    tau_lo, tau_hi, available_dwell_s,
                )
                break
            # Case (b): finite cell → no-kill cell. Threshold is
            # somewhere in this interval; with the lumped-mass model
            # we don't know exactly where, so use the no-kill
            # boundary as a lower-bound proxy.
            if not math.isnan(tau_lo) and math.isnan(tau_hi):
                kill_threshold_rad = sigma_axis_rad[i]
                break

    # If the curve never crossed dwell AND no_kill never engaged,
    # the kill threshold is undefined (engagement closes for every
    # σ_jit in the swept range — typical for a very high-power
    # scenario at close range). kill_threshold_rad stays None.

    # Convert all σ_jit values to µrad for the dataclass (display unit).
    rad_to_urad = 1.0e6
    return JitterSensitivityCurve(
        sigma_jit_axis_urad=tuple(s * rad_to_urad for s in sigma_axis_rad),
        tau_BT_axis_s=tuple(tau_BT_axis),
        no_kill_mask=tuple(no_kill_mask),
        available_dwell_s=available_dwell_s,
        kill_threshold_urad=(
            kill_threshold_rad * rad_to_urad
            if kill_threshold_rad is not None else None
        ),
        no_kill_threshold_urad=(
            no_kill_threshold_rad * rad_to_urad
            if no_kill_threshold_rad is not None else None
        ),
        current_sigma_jit_urad=current_sigma_jit_rad * rad_to_urad,
        current_tau_BT_s=current_tau_BT_s,
    )


__all__ = [
    "JitterSensitivityCurve",
    "compute_jitter_sensitivity",
]
