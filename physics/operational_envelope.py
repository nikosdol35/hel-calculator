"""Operational-envelope sweep — 2D (R_detect × v_tgt) margin map.

PR 11 of `docs/tracker_dwell_plan_2026-04-25.md`. Plot K consumes
this module's grid output to render a compute-on-click heatmap on
the Engagement tab. The strategic view of the engagement envelope:
"for this system, against threats slower than X m/s, I'm engageable
from Y km onward."

Pure module — no Streamlit imports. The orchestrator handles the
trajectory loop; this helper only sweeps the inputs and collects
the per-cell margin.

Cost: n_R × n_v orchestrator calls. Default 8×8 = 64 cells, ~30–90 s
on the canonical scenario. Caller (Streamlit UI) wraps in
``@st.cache_data`` so the heatmap is computed once per session per
input set.

**Cancellation contract.** The optional ``cancel_token`` argument
takes a ``threading.Event``. When set, the cell-loop checks it
between cells and raises ``concurrent.futures.CancelledError`` —
freeing the worker slot promptly when the user changes inputs or
clicks the Cancel button. Without this, ``Future.cancel()`` on a
running compute returns False (Python can't kill a running thread
without help) and the orphaned worker keeps eating CPU.

Companion sweep — ``compute_atmospheric_envelope`` — uses the same
margin definition but sweeps (Cn² × visibility) at fixed R_detect /
v_tgt. The two views (kinematic vs atmospheric) are independent
slices through the same engagement-margin field, plotted as both 2D
heatmaps and 3D surfaces on the Engagement tab.
"""
from __future__ import annotations

import concurrent.futures
import math
import threading
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


# Sweep bounds — tightened 2026-04-26 from the original 100 m..30 km
# down to 200 m..12 km. The wider bounds included a long-range / slow-
# target corner where the engagement could not close, so M8 ran the
# full PDE to its 60 s timeout for ~30 cells of the 100-cell grid →
# 30 min worst case. The new bounds keep the grid in C-UAS-relevant
# territory (200 m is just below typical R_min; 12 km covers every
# realistic short-range engagement) while keeping the typical
# compute under ~90 s on a 3 kW CFRP scenario.
_LOG_SPAN_R_LOW_M = 200.0       # 0.2 km
_LOG_SPAN_R_HIGH_M = 12_000.0   # 12 km
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
    n_R: int = 8,
    n_v: int = 8,
    R_low_m: float = _LOG_SPAN_R_LOW_M,
    R_high_m: float = _LOG_SPAN_R_HIGH_M,
    v_low_mps: float = _LIN_SPAN_V_LOW_MPS,
    v_high_mps: float = _LIN_SPAN_V_HIGH_MPS,
    cancel_token: threading.Event | None = None,
) -> EnvelopeGrid:
    """Sweep R_detect (log) × v_tgt (linear) → engagement margin.

    Args:
      base_inputs: full v2 input dict. Must include ``engagement_geometry``
        (the envelope only makes sense in trajectory mode); ``R_detect``
        and ``v_tgt`` are overridden per cell.
      n_R, n_v: grid dimensions. Defaults 8×8 → 64 orchestrator runs
        (was 10×10 = 100; reduced 2026-04-26 because the corner
        cells dominated total compute time and 64 cells is plenty
        of resolution for a heatmap). Tests pass smaller grids
        (3×3) so they finish in seconds.
      R_low_m / R_high_m: log-space bounds on the x-axis.
      v_low_mps / v_high_mps: linear-space bounds on the y-axis.
      cancel_token: optional ``threading.Event`` checked between
        cells. When set, the loop raises
        ``concurrent.futures.CancelledError`` immediately, freeing
        the worker slot. Without this, an in-flight worker can't
        be stopped by ``Future.cancel()`` (Python's ThreadPool
        cancel semantics return False on running tasks).

    Returns:
      EnvelopeGrid with the axes and the per-cell margin matrix.
      Cells where the orchestrator raises ValueError (validator-out-of-
      range, infeasible geometry, etc.) carry NaN. The current-scenario
      coordinates are the input dict's ``R_detect`` and ``v_tgt``.

    Raises:
      KeyError: when ``base_inputs`` is missing ``engagement_geometry``
        — the envelope is a v2-only feature.
      concurrent.futures.CancelledError: when ``cancel_token`` is set
        between cells.
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
        if cancel_token is not None and cancel_token.is_set():
            raise concurrent.futures.CancelledError(
                "operational-envelope compute cancelled mid-sweep"
            )
        row: list[float] = []
        for R in R_axis:
            if cancel_token is not None and cancel_token.is_set():
                raise concurrent.futures.CancelledError(
                    "operational-envelope compute cancelled mid-sweep"
                )
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


@dataclass(frozen=True)
class AtmosphericEnvelopeGrid:
    """The output of ``compute_atmospheric_envelope``.

    Holds the (Cn², V_km) sweep axes plus the per-cell engagement
    margin in percent (clamped to [-100, +200] for plotting). Cells
    where the orchestrator failed (validator-rejected, etc.) carry
    NaN. The current-scenario coordinates indicate the user's
    "you are here" reference.
    """
    cn2_axis: tuple[float, ...]        # m^(−2/3), log-spaced
    V_km_axis: tuple[float, ...]       # km, log-spaced (vis spans ~0.5..50 km)
    margin_grid: tuple[tuple[float, ...], ...]   # row=V, col=Cn²; %
    current_cn2: float
    current_V_km: float
    n_kills: int                       # cells with margin >= 0
    n_failures: int                    # cells where the run raised


_LOG_SPAN_CN2_LOW = 1.0e-16
_LOG_SPAN_CN2_HIGH = 5.0e-13
_LOG_SPAN_V_LOW_KM = 0.5
_LOG_SPAN_V_HIGH_KM = 50.0


def compute_atmospheric_envelope(
    base_inputs: dict,
    n_cn2: int = 8,
    n_V: int = 8,
    cn2_low: float = _LOG_SPAN_CN2_LOW,
    cn2_high: float = _LOG_SPAN_CN2_HIGH,
    V_low_km: float = _LOG_SPAN_V_LOW_KM,
    V_high_km: float = _LOG_SPAN_V_HIGH_KM,
    cancel_token: threading.Event | None = None,
) -> AtmosphericEnvelopeGrid:
    """Sweep Cn² (log) × V (log) → engagement margin.

    Args:
      base_inputs: full v2 input dict. Must include ``engagement_geometry``;
        ``Cn2_value`` and ``V`` are overridden per cell. The
        orchestrator runs the whole chain per cell — same trajectory
        loop the kinematic envelope uses, just with different
        atmosphere inputs.
      n_cn2, n_V: grid dimensions. Defaults 8×8 → 64 orchestrator
        runs (was 10×10; reduced 2026-04-26 to match the kinematic
        envelope and keep typical compute under ~90 s). Tests pass
        smaller grids (3×3) so they finish in seconds.
      cn2_low / cn2_high: log-space bounds on the x-axis (m^(-2/3)).
      V_low_km / V_high_km: log-space bounds on the y-axis.
      cancel_token: optional ``threading.Event`` checked between
        cells; same contract as ``compute_operational_envelope``.

    Returns:
      AtmosphericEnvelopeGrid with the axes and per-cell margin matrix.
      Cells where the orchestrator raises ValueError carry NaN. The
      ``current_cn2`` / ``current_V_km`` coordinates are the user's
      input values for the "you are here" overlay.

    Raises:
      KeyError: when ``base_inputs`` is missing ``engagement_geometry``
        — the envelope is a v2-only feature.
      concurrent.futures.CancelledError: when ``cancel_token`` is set
        between cells.

    Implementation note: when ``cn2_model == 'HV_5_7'`` the v2 chain
    derives turbulence from ``Cn2_ground`` rather than ``Cn2_value``.
    To make the sweep meaningful regardless of the user's mode we
    flip ``cn2_model`` to ``'constant'`` for every cell — the per-cell
    ``Cn2_value`` then drives M5 directly and the sweep maps a clean
    Cn² → margin response.
    """
    if "engagement_geometry" not in base_inputs:
        raise KeyError(
            "compute_atmospheric_envelope requires v2.0 inputs "
            "(engagement_geometry must be present)"
        )

    cn2_axis = _log_space(cn2_low, cn2_high, n_cn2)
    V_axis = _log_space(V_low_km, V_high_km, n_V)

    grid: list[tuple[float, ...]] = []
    n_kills = 0
    n_failures = 0
    for V_km in V_axis:
        if cancel_token is not None and cancel_token.is_set():
            raise concurrent.futures.CancelledError(
                "atmospheric-envelope compute cancelled mid-sweep"
            )
        row: list[float] = []
        for cn2 in cn2_axis:
            if cancel_token is not None and cancel_token.is_set():
                raise concurrent.futures.CancelledError(
                    "atmospheric-envelope compute cancelled mid-sweep"
                )
            inputs = {
                **base_inputs,
                "V": float(V_km),
                "Cn2_value": float(cn2),
                "cn2_model": "constant",   # see docstring note
            }
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

    return AtmosphericEnvelopeGrid(
        cn2_axis=cn2_axis,
        V_km_axis=V_axis,
        margin_grid=tuple(grid),
        current_cn2=float(base_inputs.get("Cn2_value", 0.0)),
        current_V_km=float(base_inputs.get("V", 0.0)),
        n_kills=n_kills,
        n_failures=n_failures,
    )


__all__ = [
    "AtmosphericEnvelopeGrid",
    "EnvelopeGrid",
    "compute_atmospheric_envelope",
    "compute_operational_envelope",
]
