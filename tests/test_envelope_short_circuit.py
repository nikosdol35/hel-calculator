"""Tests for the dwell-window short-circuit on engagement-envelope sweeps.

User-reported 2026-04-27 bug: a 6×6 = 36-cell envelope sweep on
Streamlit Cloud took 9+ minutes on the canonical 3 kW scenario.

Root cause discovered via timing measurement: cells with very long
dwell windows (e.g. 12 km @ 1 m/s = 11 900 s engagement) cause
M8's PDE to integrate step-by-step in simulated time at ~24:1
wall-clock ratio. A single 12 km × 1 m/s cell took 326 seconds
of wall-clock on local hardware — 80% of the user's 9-minute
total compute came from ~5 such cells.

Fix: the closed-form ``_cell_skipped_for_envelope`` guard skips
cells with simulated dwell > 300 s before running the M8 PDE.
Skipped cells are marked NaN (gray on the heatmap) and counted
under ``n_failures``. Typical C-UAS engagements close in 5–90 s,
so this guard is effectively invisible for normal scenarios — it
only fires on the operationally-unusual long-dwell corner that
dominates Cloud compute time.

Coverage:
  - Skip on R ≤ R_min (no dwell window)
  - Skip on dwell > 300 s
  - No skip on dwell ≤ 300 s (typical C-UAS engagements)
  - Defer (no skip) on degenerate v_tgt
  - Operational envelope: long-dwell corner cells become NaN
  - Operational envelope: total compute time bounded
  - Atmospheric envelope: kinematics-out-of-budget → all-NaN
"""
from __future__ import annotations

import math
import time

from physics.operational_envelope import (
    _cell_skipped_for_envelope,
    _ENVELOPE_MAX_DWELL_S,
    compute_atmospheric_envelope,
    compute_operational_envelope,
)
from tests.golden.scenarios import C_UAS_1500M


def _v2_inputs(**overrides) -> dict:
    inputs = dict(C_UAS_1500M)
    inputs.pop("R", None)
    inputs.pop("v_perp", None)
    inputs.update({
        "R_detect": 1500, "R_min": 100,
        "engagement_geometry": "head_on",
    })
    inputs.update(overrides)
    return inputs


# ---------------------------------------------------------------------------
# Direct unit tests on the helper
# ---------------------------------------------------------------------------
def test_skipped_when_R_below_R_min():
    """R ≤ R_min → no dwell window → skipped immediately."""
    inputs = _v2_inputs(R_min=100)
    assert _cell_skipped_for_envelope(
        R_m=50.0, v_tgt_mps=10.0, base_inputs=inputs,
    ) is True
    assert _cell_skipped_for_envelope(
        R_m=100.0, v_tgt_mps=10.0, base_inputs=inputs,
    ) is True


def test_skipped_when_dwell_exceeds_cap():
    """Cells with simulated dwell > 300 s are skipped to keep
    envelope compute time bounded. The 12 km × 1 m/s corner has
    dwell = 11 900 s — easily over the cap."""
    inputs = _v2_inputs(R_min=100)
    assert _cell_skipped_for_envelope(
        R_m=12_000.0, v_tgt_mps=1.0, base_inputs=inputs,
    ) is True
    # Dwell = (5000 - 100) / 10 = 490 s — still over cap
    assert _cell_skipped_for_envelope(
        R_m=5000.0, v_tgt_mps=10.0, base_inputs=inputs,
    ) is True


def test_not_skipped_within_normal_engagements():
    """Typical C-UAS engagements close in 5–90 s. None should
    be skipped by the dwell guard."""
    inputs = _v2_inputs(R_min=100)
    # 1.5 km × 20 m/s = 70 s dwell — typical C-UAS scenario
    assert _cell_skipped_for_envelope(
        R_m=1500.0, v_tgt_mps=20.0, base_inputs=inputs,
    ) is False
    # 5 km × 30 m/s = 163 s dwell — still under cap
    assert _cell_skipped_for_envelope(
        R_m=5000.0, v_tgt_mps=30.0, base_inputs=inputs,
    ) is False
    # 12 km × 100 m/s = 119 s dwell — under cap (fast target!)
    assert _cell_skipped_for_envelope(
        R_m=12_000.0, v_tgt_mps=100.0, base_inputs=inputs,
    ) is False


def test_defers_on_degenerate_velocity():
    """v ≤ 0 → defer to the chain (which raises). Not the
    short-circuit's job to validate inputs."""
    inputs = _v2_inputs(R_min=100)
    assert _cell_skipped_for_envelope(
        R_m=1500.0, v_tgt_mps=0.0, base_inputs=inputs,
    ) is False
    assert _cell_skipped_for_envelope(
        R_m=1500.0, v_tgt_mps=-5.0, base_inputs=inputs,
    ) is False


def test_envelope_max_dwell_is_300s():
    """Lock the cap to 300 s. Bumping this changes the user-visible
    behaviour (more / fewer cells render) and the compute-time
    budget on Streamlit Cloud."""
    assert _ENVELOPE_MAX_DWELL_S == 300.0


# ---------------------------------------------------------------------------
# Integration tests on the operational envelope
# ---------------------------------------------------------------------------
def test_operational_envelope_corner_cells_marked_nan():
    """A 4×4 sweep on the canonical scenario should mark long-dwell
    corner cells as NaN via the dwell guard (rather than running
    the full M8 PDE for ~5 minutes per cell)."""
    env = compute_operational_envelope(
        _v2_inputs(), n_R=4, n_v=4,
    )
    # Some cells should be NaN (corner cells with dwell > 300 s).
    nan_count = sum(
        1 for row in env.margin_grid for v in row
        if isinstance(v, float) and math.isnan(v)
    )
    assert nan_count >= 1, (
        f"expected ≥1 cells skipped via dwell guard; got "
        f"nan_count={nan_count}. Did the guard fire?"
    )
    # And those NaN cells should be reflected in n_failures.
    assert env.n_failures >= nan_count


def test_operational_envelope_short_circuit_cuts_compute_time():
    """A 4×4 sweep with the dwell guard live should finish well
    under 60 s on local hardware. Without the guard, the long-dwell
    corner alone would push it past 5 minutes."""
    t0 = time.monotonic()
    env = compute_operational_envelope(
        _v2_inputs(), n_R=4, n_v=4,
    )
    elapsed = time.monotonic() - t0
    assert elapsed < 60.0, (
        f"4×4 envelope took {elapsed:.0f}s on canonical scenario; "
        f"dwell guard should keep it under 60 s. Did the guard "
        f"regress, or did per-cell M8 cost change?"
    )
    # Sanity: at least one cell should have closed (not all NaN).
    finite_count = sum(
        1 for row in env.margin_grid for v in row
        if isinstance(v, float) and math.isfinite(v)
    )
    assert finite_count >= 4


def test_operational_envelope_close_range_unaffected():
    """Close-range, slow-target, high-velocity cells (where the
    chain definitely closes the engagement) should NOT be skipped.
    Regression guard against accidental over-skipping."""
    env = compute_operational_envelope(
        _v2_inputs(), n_R=3, n_v=3,
        R_low_m=200.0, R_high_m=1500.0,
        v_low_mps=10.0, v_high_mps=30.0,
    )
    nan_count = sum(
        1 for row in env.margin_grid for v in row
        if isinstance(v, float) and math.isnan(v)
    )
    assert nan_count == 0, (
        f"dwell guard incorrectly skipped close-range cells: "
        f"{env.margin_grid!r}"
    )


# ---------------------------------------------------------------------------
# Atmospheric envelope: kinematics-based all-or-nothing skip
# ---------------------------------------------------------------------------
def test_atmospheric_envelope_skips_when_kinematics_out_of_budget():
    """If the user's R_detect / v_tgt itself has dwell > 300 s,
    no atmospheric variation can change that — the entire heatmap
    is NaN."""
    # 12 km × 1 m/s = 11 900 s dwell — out of envelope.
    inputs = _v2_inputs(R_detect=12_000, v_tgt=1.0)
    env = compute_atmospheric_envelope(
        inputs, n_cn2=3, n_V=3,
        cn2_low=1e-16, cn2_high=1e-13,
        V_low_km=5.0, V_high_km=30.0,
    )
    all_nan = all(
        isinstance(v, float) and math.isnan(v)
        for row in env.margin_grid for v in row
    )
    assert all_nan, (
        f"expected all-NaN atmospheric heatmap when kinematics "
        f"are out of budget; got {env.margin_grid!r}"
    )
    assert env.n_failures == 9  # 3 × 3 = 9 cells


def test_atmospheric_envelope_runs_when_kinematics_in_budget():
    """The atmospheric heatmap renders normally when kinematics
    are within the dwell budget."""
    # 1.5 km × 20 m/s = 70 s dwell — well under cap.
    inputs = _v2_inputs(R_detect=1500, v_tgt=20.0)
    env = compute_atmospheric_envelope(
        inputs, n_cn2=3, n_V=3,
        cn2_low=1e-16, cn2_high=1e-13,
        V_low_km=5.0, V_high_km=30.0,
    )
    finite_count = sum(
        1 for row in env.margin_grid for v in row
        if isinstance(v, float) and math.isfinite(v)
    )
    assert finite_count == 9
