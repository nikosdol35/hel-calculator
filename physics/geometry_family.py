"""Family of peak-irradiance vs engagement-time curves at varying
target approach geometries.

Plot P consumes this module's output to overlay 5 reference crossing
geometries (head-on, 30°, 45°, 60°, perpendicular) plus the user's
current scenario, so the operator sees how robust the engagement is
to changing target approach angles.

Pure module — no Streamlit imports.

**Lightweight compute path** — same simplification spirit as
``physics.cn2_family`` and ``physics.jitter_sensitivity``:

  1. **M1** (laser geometry: w0, zR) — read from chain output.
  2. **M2** (beam-director power: P_exit) — read from chain output.
  3. **M4** (atmospheric transmission: tau_atm) — runs per (R) cell.
  4. **M5** (turbulence: r0_sph) — runs per (R) cell.
  5. **M7** (spot / PIB / I_peak) — runs per (R) cell with
     ``S_TB = 1.0`` and ``w_bloom = 0`` (skip M6 blooming).

Per-cell cost: ~5 ms. Total for 5 reference angles × 30 trajectory
samples = ~750 ms.

**Why bypass the chain's geometry restriction?** The chain's
``m_trajectory.py`` only supports ``"head_on"`` and ``"lateral"``;
adding 30°/60°/45° crossing angles would require extending the
SPEC v2.0 contract (touches m_trajectory + m3_geometry +
orchestrator + multiple validators). Plot P is a visualization-
layer comparative diagnostic — it synthesises straight-line
trajectories at arbitrary angles directly here, without disturbing
the chain.

The user's current-scenario curve is taken DIRECTLY from the chain's
``trajectory_t`` / ``trajectory_I_peak`` time-series (PDE-accurate
per the orchestrator's full M4-M8 path). Reference curves use the
lightweight path above. They may differ by ~10-20 % in absolute
level — the plot's caption discloses this.
"""
from __future__ import annotations

import math
from dataclasses import dataclass

from physics import m4_atmosphere, m5_turbulence, m7_spot_pib


# Reference crossing angles in degrees. α=0° matches chain's "head_on";
# α=90° is pure perpendicular crossing (target velocity perpendicular
# to LOS at detection — never closes).
_REFERENCE_ANGLES_DEG: tuple[float, ...] = (0.0, 30.0, 45.0, 60.0, 90.0)

# Default trajectory sampling.
_DEFAULT_N_SAMPLES: int = 30
# Global safety cap on engagement duration. The α=90° degenerate case
# (target moves perpendicular at detection — only moves away) needs a
# bound so the curve doesn't run forever; everything else is bounded
# by the trajectory math (R_min crossing or closest-approach turnaround).
# 180 s comfortably accommodates head-on engagements at canonical-class
# closing speeds (v_tgt = 10-30 m/s, R_detect = 1.5-3 km → t_close in
# the 50-300 s range) while still bounding α=90° to a finite duration.
_T_MAX_S: float = 180.0


@dataclass(frozen=True)
class GeometryFamilyCurves:
    """Output of `compute_geometry_family_curves`.

    One reference curve per angle in ``_REFERENCE_ANGLES_DEG`` plus
    an optional current-scenario curve from the chain's actual
    trajectory output. Each reference curve is a tuple of
    (t_axis_s, I_peak_axis_wpcm2) lists of equal length; the
    user's curve uses chain time series and may be a different
    length.

    Attributes:
      reference_curves: tuple of (alpha_deg, t_axis, I_peak_axis)
        triplets, in ``_REFERENCE_ANGLES_DEG`` order.
      current_t_axis_s: chain's trajectory_t (None if missing).
      current_I_peak_wpcm2_axis: chain's trajectory_I_peak in
        W/cm² (None if missing). Already converted from W/m² SI.
      current_R_at_kill_km: where the chain says the engagement
        closes (None for fly-by trajectories).
    """
    reference_curves: tuple[tuple[float, tuple[float, ...], tuple[float, ...]], ...]
    current_t_axis_s: tuple[float, ...] | None
    current_I_peak_wpcm2_axis: tuple[float, ...] | None
    current_R_at_kill_km: float | None


# ---------------------------------------------------------------------------
# Trajectory math (synthetic, doesn't touch the chain)
# ---------------------------------------------------------------------------

def _trajectory_R_of_t(
    R_detect_m: float, v_tgt_mps: float, alpha_deg: float, t_s: float,
) -> float:
    """Slant range R(t) for a straight-line trajectory at crossing
    angle α (degrees from LOS at detection).

    Coordinate system: gun at origin. Target initially at (R_detect, 0).
    Target velocity vector at angle α from the LOS direction:
      vx = -v_tgt · cos(α)   (closing component along LOS)
      vy =  v_tgt · sin(α)   (cross-track component)

    Position(t) = (R_detect - v·cos(α)·t, v·sin(α)·t)
    R(t) = sqrt(x(t)² + y(t)²)

    α = 0°: pure head-on → R(t) = R_detect - v·t
    α = 90°: target moves perpendicular at detection → R only increases.
    """
    alpha_rad = math.radians(alpha_deg)
    x = R_detect_m - v_tgt_mps * math.cos(alpha_rad) * t_s
    y = v_tgt_mps * math.sin(alpha_rad) * t_s
    return math.sqrt(x * x + y * y)


def _t_engagement_end(
    R_detect_m: float, R_min_m: float, v_tgt_mps: float, alpha_deg: float,
) -> float:
    """Engagement-end time for a given crossing angle.

    Per the plan §3.2, each reference curve runs from t=0 until the
    EARLIEST of:
      1. R(t) reaches R_min                       — engagement-end
      2. R(t) reaches its closest approach        — target turns away
      3. t_max global cap                         — α=90° degenerate
    """
    if v_tgt_mps <= 0.0:
        return _T_MAX_S
    alpha_rad = math.radians(alpha_deg)
    # Closest approach occurs at t* = R_detect · cos(α) / v.
    # For α ≥ 90° this is non-positive (target only moves away).
    # Use a small epsilon to catch α = 90° exactly (cos π/2 isn't
    # exactly 0 in IEEE 754; we treat anything within 1e-9 of zero as
    # "no closing").
    cos_a = math.cos(alpha_rad)
    sin_a = math.sin(alpha_rad)
    if cos_a <= 1.0e-9:
        # α ≥ 90° (within float tolerance): no closing. Cap at t_max.
        return _T_MAX_S
    t_closest = R_detect_m * cos_a / v_tgt_mps
    R_closest = R_detect_m * sin_a
    if R_closest <= R_min_m:
        # Trajectory passes inside R_min — solve for t when R(t) = R_min.
        # x(t)² + y(t)² = R_min²
        # (R_d - v·c·t)² + (v·s·t)² = R_min²
        # Expand: R_d² - 2·R_d·v·c·t + v²·c²·t² + v²·s²·t² = R_min²
        # v²·t² - 2·R_d·v·c·t + (R_d² - R_min²) = 0
        a = v_tgt_mps * v_tgt_mps
        b = -2.0 * R_detect_m * v_tgt_mps * cos_a
        c = R_detect_m * R_detect_m - R_min_m * R_min_m
        disc = b * b - 4.0 * a * c
        if disc < 0.0:
            # Numerically shouldn't happen (we know R_closest ≤ R_min);
            # defensive fallback to closest-approach time.
            return min(t_closest, _T_MAX_S)
        # The smaller root is the first crossing of R = R_min (entry).
        t_enter = (-b - math.sqrt(disc)) / (2.0 * a)
        return min(max(t_enter, 0.0), _T_MAX_S)
    # α large enough that trajectory misses R_min — stop at closest approach.
    return min(t_closest, _T_MAX_S)


# ---------------------------------------------------------------------------
# Per-cell M4+M5+M7 compute (lightweight, ~5 ms)
# ---------------------------------------------------------------------------

def _compute_I_peak_wpcm2_at_R(
    base_inputs: dict, R_m: float, w0: float, zR: float, P_exit: float,
) -> float | None:
    """Compute I_peak (W/cm²) at one slant range using M4+M5+M7 only.

    Returns None if any module rejects the inputs (out-of-range or bad
    combination) — caller treats this as a missing data point. Same
    pattern as ``cn2_family._compute_one_cell``.
    """
    if R_m <= 0.0:
        return None
    try:
        m4_out = m4_atmosphere.compute({
            "wavelength": base_inputs["wavelength"],
            "R_slant": R_m,
            "V": base_inputs["V"],
            "RH": base_inputs["RH"],
            "T_ambient": base_inputs["T_ambient"],
            "P_atm": base_inputs["P_atm"],
            "H_e": base_inputs.get("H_e", 2.0),
            "H_t": base_inputs.get("H_t", 200.0),
        })
        m5_out = m5_turbulence.compute({
            "cn2_model": base_inputs["cn2_model"],
            "Cn2_value": base_inputs.get("Cn2_value", 1.0e-14),
            "Cn2_ground": base_inputs.get("Cn2_ground", 1.7e-14),
            "v_HV": base_inputs.get("v_HV", 21.0),
            "wavelength": base_inputs["wavelength"],
            "R_slant": R_m,
            "H_e": base_inputs.get("H_e", 2.0),
            "H_t": base_inputs.get("H_t", 200.0),
        })
        m7_out = m7_spot_pib.compute({
            "P_exit": P_exit,
            "tau_atm": m4_out["tau_atm"],
            "w0": w0,
            "zR": zR,
            "M2": base_inputs["M2"],
            "wavelength": base_inputs["wavelength"],
            "R_slant": R_m,
            "sigma_jit": base_inputs["sigma_jit"],
            "r0_sph": m5_out["r0_sph"],
            "S_TB": 1.0,
            "w_bloom": 0.0,
            "d_aim": base_inputs["d_aim"],
        })
    except (ValueError, KeyError):
        return None
    # I_peak from M7 is in W/m²; convert to W/cm² for display.
    return float(m7_out.get("I_peak", 0.0)) * 1.0e-4


# ---------------------------------------------------------------------------
# Public entry point
# ---------------------------------------------------------------------------

def compute_geometry_family_curves(
    base_inputs: dict,
    angles_deg: tuple[float, ...] | None = None,
    n_samples: int = _DEFAULT_N_SAMPLES,
) -> GeometryFamilyCurves:
    """Compute peak irradiance vs engagement time for a family of
    target approach angles.

    Args:
      base_inputs: merged orchestrator-result dict (the same shape
        passed to ``render_tab_*``). Must include the v2.0 trajectory
        key ``engagement_geometry`` and ``by_module`` (so we can read
        M1/M2 outputs without re-running them).
      angles_deg: tuple of crossing angles in degrees. Defaults to
        ``_REFERENCE_ANGLES_DEG``.
      n_samples: trajectory sampling density (default 30).

    Returns:
      GeometryFamilyCurves with reference-curve list + the user's
      chain trajectory (or None when not available).

    Raises:
      KeyError: when ``base_inputs`` is missing the v2.0 trajectory
        keys or the chain output (``by_module``) — chain hasn't run.
    """
    if "engagement_geometry" not in base_inputs:
        raise KeyError(
            "compute_geometry_family_curves requires v2.0 inputs "
            "(engagement_geometry must be present)"
        )
    by = base_inputs.get("by_module") or {}
    m1 = by.get("m1", {})
    m2 = by.get("m2", {})
    if not m1 or not m2:
        raise KeyError(
            "compute_geometry_family_curves requires by_module['m1'] "
            "and by_module['m2'] (chain output)"
        )

    w0 = float(m1.get("w0") or 0.0)
    zR = float(m1.get("zR") or 0.0)
    P_exit = float(m2.get("P_exit") or 0.0)
    if w0 <= 0 or zR <= 0 or P_exit <= 0:
        raise KeyError("invalid M1/M2 outputs in by_module")

    R_detect_m = float(base_inputs.get("R_detect") or base_inputs.get("R", 0.0))
    R_min_m = float(base_inputs.get("R_min", 100.0))
    v_tgt_mps = float(base_inputs.get("v_tgt", 0.0))
    if R_detect_m <= 0:
        raise KeyError("R_detect must be > 0")

    levels = angles_deg if angles_deg is not None else _REFERENCE_ANGLES_DEG

    # Build each reference curve.
    reference_curves: list[tuple[float, tuple[float, ...], tuple[float, ...]]] = []
    for alpha_deg in levels:
        t_end = _t_engagement_end(R_detect_m, R_min_m, v_tgt_mps, alpha_deg)
        if n_samples < 2:
            sample_times = (0.0,)
        else:
            step = t_end / (n_samples - 1) if n_samples > 1 else 0.0
            sample_times = tuple(step * i for i in range(n_samples))
        I_peak_axis: list[float] = []
        for t_s in sample_times:
            R = _trajectory_R_of_t(R_detect_m, v_tgt_mps, alpha_deg, t_s)
            I_peak = _compute_I_peak_wpcm2_at_R(
                base_inputs, R, w0, zR, P_exit,
            )
            I_peak_axis.append(I_peak if I_peak is not None else float("nan"))
        reference_curves.append(
            (float(alpha_deg), sample_times, tuple(I_peak_axis))
        )

    # User's current-scenario curve from the chain's trajectory output.
    current_t_axis = base_inputs.get("trajectory_t")
    current_I_peak_wpm2 = base_inputs.get("trajectory_I_peak")
    current_t_tup: tuple[float, ...] | None = None
    current_I_tup: tuple[float, ...] | None = None
    if current_t_axis and current_I_peak_wpm2:
        try:
            current_t_tup = tuple(float(t) for t in current_t_axis)
            # Convert chain's W/m² SI to W/cm² for display.
            current_I_tup = tuple(float(v) * 1.0e-4 for v in current_I_peak_wpm2)
        except (TypeError, ValueError):
            current_t_tup = None
            current_I_tup = None

    R_at_kill = base_inputs.get("R_at_kill")
    current_R_at_kill_km: float | None = None
    if R_at_kill is not None and isinstance(R_at_kill, (int, float)):
        try:
            v = float(R_at_kill)
            if math.isfinite(v) and v > 0:
                current_R_at_kill_km = v / 1000.0
        except (TypeError, ValueError):
            current_R_at_kill_km = None

    return GeometryFamilyCurves(
        reference_curves=tuple(reference_curves),
        current_t_axis_s=current_t_tup,
        current_I_peak_wpcm2_axis=current_I_tup,
        current_R_at_kill_km=current_R_at_kill_km,
    )


__all__ = [
    "GeometryFamilyCurves",
    "compute_geometry_family_curves",
    "_REFERENCE_ANGLES_DEG",
    "_T_MAX_S",
]
