"""Operational-envelope sweep — 2D (R_detect × v_tgt) margin map.

PR 11 of `docs/tracker_dwell_plan_2026-04-25.md`. Plot K consumes
this module's grid output to render a compute-on-click heatmap on
the Engagement tab. The strategic view of the engagement envelope:
"for this system, against threats slower than X m/s, I'm engageable
from Y km onward."

Pure module — no Streamlit imports. The orchestrator handles the
trajectory loop; this helper only sweeps the inputs and collects
the per-cell margin.

Cost: n_R × n_v orchestrator calls. Default 10×10 = 100 cells, ~100 s
on the canonical scenario. Caller (Streamlit UI) wraps in
``@st.cache_data`` so the heatmap is computed once per session per
input set.
"""
from __future__ import annotations

import math
from dataclasses import dataclass

from physics.orchestrator import run_full_chain


@dataclass(frozen=True)
class EnvelopeGrid:
    """The output of `compute_operational_envelope`.

    Holds the (R_detect, v_tgt) sweep axes plus the per-cell engagement
    margin in percent (clamped to [-100, +200] for plotting). Cells
    where the orchestrator failed (validator-rejected, infeasible
    geometry, etc.) carry NaN. The current-scenario coordinates
    indicate the user's "you are here" reference.
    """
    R_detect_axis: tuple[float, ...]   # m, log-spaced
    v_tgt_axis: tuple[float, ...]      # m/s, linear
    margin_grid: tuple[tuple[float, ...], ...]   # row=v, col=R; %
    current_R_detect: float
    current_v_tgt: float
    n_kills: int                       # cells with margin >= 0
    n_failures: int                    # cells where the run raised


_LOG_SPAN_R_LOW_M = 100.0       # 0.1 km
_LOG_SPAN_R_HIGH_M = 30_000.0   # 30 km
_LIN_SPAN_V_LOW_MPS = 1.0
_LIN_SPAN_V_HIGH_MPS = 100.0
_MARGIN_FLOOR_PCT = -100.0
_MARGIN_CEIL_PCT = 200.0


def _log_space(low: float, high: float, n: int) -> tuple[float, ...]:
    """Logarithmic grid from low to high inclusive."""
    if n < 2:
        return (low,)
    step = (math.log(high) - math.log(low)) / (n - 1)
    return tuple(math.exp(math.log(low) + i * step) for i in range(n))


def _lin_space(low: float, high: float, n: int) -> tuple[float, ...]:
    if n < 2:
        return (low,)
    step = (high - low) / (n - 1)
    return tuple(low + i * step for i in range(n))


def _engagement_margin_pct(result: dict) -> float:
    """Compute engagement margin in percent from a v2 result dict.

    Returns NaN when the engagement is degenerate (no kill within
    window — tau_BT clamped to t_dwell — or missing keys)."""
    tau = result.get("tau_BT")
    dwell = result.get("available_dwell")
    failure_mode = result.get("failure_mode")
    if (tau is None or dwell is None
            or not math.isfinite(float(tau)) or float(tau) <= 0
            or not math.isfinite(float(dwell))):
        return math.nan
    if failure_mode == "engagement_ended_at_R_min":
        # Engagement ended without a kill; margin is -100% by
        # convention (the worst tier of the verdict bands).
        return _MARGIN_FLOOR_PCT
    m = 100.0 * (float(dwell) - float(tau)) / float(tau)
    return max(_MARGIN_FLOOR_PCT, min(_MARGIN_CEIL_PCT, m))


def compute_operational_envelope(
    base_inputs: dict,
    n_R: int = 10,
    n_v: int = 10,
    R_low_m: float = _LOG_SPAN_R_LOW_M,
    R_high_m: float = _LOG_SPAN_R_HIGH_M,
    v_low_mps: float = _LIN_SPAN_V_LOW_MPS,
    v_high_mps: float = _LIN_SPAN_V_HIGH_MPS,
) -> EnvelopeGrid:
    """Sweep R_detect (log) × v_tgt (linear) → engagement margin.

    Args:
      base_inputs: full v2 input dict. Must include ``engagement_geometry``
        (the envelope only makes sense in trajectory mode); ``R_detect``
        and ``v_tgt`` are overridden per cell.
      n_R, n_v: grid dimensions. Defaults 10×10 → 100 orchestrator
        runs. Tests pass smaller grids (3×3) so they finish in seconds.
      R_low_m / R_high_m: log-space bounds on the x-axis.
      v_low_mps / v_high_mps: linear-space bounds on the y-axis.

    Returns:
      EnvelopeGrid with the axes and the per-cell margin matrix.
      Cells where the orchestrator raises ValueError (validator-out-of-
      range, infeasible geometry, etc.) carry NaN. The current-scenario
      coordinates are the input dict's ``R_detect`` and ``v_tgt``.

    Raises:
      KeyError: when ``base_inputs`` is missing ``engagement_geometry``
        — the envelope is a v2-only feature.
    """
    if "engagement_geometry" not in base_inputs:
        raise KeyError(
            "compute_operational_envelope requires v2.0 inputs "
            "(engagement_geometry must be present)"
        )

    R_axis = _log_space(R_low_m, R_high_m, n_R)
    v_axis = _lin_space(v_low_mps, v_high_mps, n_v)

    grid: list[tuple[float, ...]] = []
    n_kills = 0
    n_failures = 0
    for v in v_axis:
        row: list[float] = []
        for R in R_axis:
            inputs = {**base_inputs, "R_detect": float(R), "v_tgt": float(v)}
            try:
                result = run_full_chain(inputs)
            except Exception:
                row.append(math.nan)
                n_failures += 1
                continue
            margin = _engagement_margin_pct(result)
            row.append(margin)
            if math.isfinite(margin) and margin >= 0:
                n_kills += 1
        grid.append(tuple(row))

    return EnvelopeGrid(
        R_detect_axis=R_axis,
        v_tgt_axis=v_axis,
        margin_grid=tuple(grid),
        current_R_detect=float(base_inputs.get("R_detect", 0.0)),
        current_v_tgt=float(base_inputs.get("v_tgt", 0.0)),
        n_kills=n_kills,
        n_failures=n_failures,
    )


__all__ = [
    "EnvelopeGrid",
    "compute_operational_envelope",
]
