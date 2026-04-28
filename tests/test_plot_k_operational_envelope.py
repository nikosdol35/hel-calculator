"""Tests for Plot K — operational-envelope heatmap (PR 11).

SPEC v2.0 §8.6 of `docs/tracker_dwell_plan_2026-04-25.md`. Plot K
renders a 2D heatmap of engagement margin across (R_detect × v_tgt)
with a "you are here" marker on the user's current scenario.

Tests use a small 3×3 grid so the compute (~9 orchestrator runs)
finishes in seconds. The default 10×10 grid would take ~100 s and
isn't appropriate for unit tests.

Coverage:
  - compute_operational_envelope returns the expected EnvelopeGrid
    structure
  - axes are log-spaced (R_detect) and linearly-spaced (v_tgt)
  - margin grid has the right shape (rows × cols)
  - cells where the orchestrator raises ValueError are NaN
  - n_kills / n_failures bookkeeping is consistent
  - non-v2 inputs raise KeyError (envelope is v2-only)
  - Plot K renders with the heatmap + the "you are here" marker
  - Plot K with None envelope falls back to empty frame
"""
from __future__ import annotations

import math

import pytest

from physics.operational_envelope import (
    EnvelopeGrid, compute_operational_envelope,
)
from tests.golden.scenarios import C_UAS_1500M


def _v2_inputs() -> dict:
    inputs = dict(C_UAS_1500M)
    inputs.pop("R")
    inputs.pop("v_perp")
    inputs.update({
        "R_detect": 1500, "R_min": 100,
        "engagement_geometry": "head_on",
    })
    return inputs


# Default sweep bounds were narrowed 2026-04-26 to R 200..12 km
# (was 100..30 km) to avoid the long-range / slow-target corner where
# M8 ran the full PDE to its 60-second timeout. Tests that don't
# care about the bounds use this fast preset instead: the entire 3×3
# grid finishes in under 30 s on the canonical CFRP / 3 kW scenario.
_FAST_KW = dict(
    R_low_m=200.0, R_high_m=2_000.0,
    v_low_mps=5.0, v_high_mps=30.0,
)


def test_compute_envelope_returns_grid_dataclass():
    env = compute_operational_envelope(_v2_inputs(), n_R=3, n_v=3, **_FAST_KW)
    assert isinstance(env, EnvelopeGrid)
    assert len(env.R_detect_axis) == 3
    assert len(env.v_tgt_axis) == 3
    assert len(env.margin_grid) == 3   # 3 rows
    assert all(len(row) == 3 for row in env.margin_grid)


def test_compute_envelope_axes_shape():
    """R-axis log-spaced, v-axis linearly-spaced."""
    env = compute_operational_envelope(
        _v2_inputs(), n_R=3, n_v=3, **_FAST_KW,
    )
    R = env.R_detect_axis
    v = env.v_tgt_axis
    # Log spacing: R[1]/R[0] == R[2]/R[1].
    assert R[1] / R[0] == pytest.approx(R[2] / R[1], rel=1e-9)
    # Linear spacing: v[1]-v[0] == v[2]-v[1].
    assert v[1] - v[0] == pytest.approx(v[2] - v[1], rel=1e-9)


def test_compute_envelope_v1_inputs_rejected():
    """The envelope is v2-only; passing a v1.x input set without
    engagement_geometry must raise KeyError."""
    # C_UAS_1500M now carries both v1.x (R, v_perp) and v2.0
    # (R_detect, R_min, engagement_geometry) keys for backward-compat;
    # explicitly drop the v2 keys so this test exercises the v1-mode
    # rejection path.
    inputs_v1 = dict(C_UAS_1500M)
    for key in ("R_detect", "R_min", "engagement_geometry"):
        inputs_v1.pop(key, None)
    with pytest.raises(KeyError, match="engagement_geometry"):
        compute_operational_envelope(inputs_v1, n_R=3, n_v=3)


def test_compute_envelope_bookkeeping_consistent():
    """n_kills + n_failures + non-kill cells = total cells."""
    env = compute_operational_envelope(_v2_inputs(), n_R=3, n_v=3, **_FAST_KW)
    total = len(env.R_detect_axis) * len(env.v_tgt_axis)
    n_finite = sum(
        1 for row in env.margin_grid for v in row if math.isfinite(v)
    )
    n_nan = sum(
        1 for row in env.margin_grid for v in row if math.isnan(v)
    )
    assert n_finite + n_nan == total
    assert env.n_failures == n_nan
    # n_kills counts margin >= 0 in finite cells.
    n_kills_check = sum(
        1 for row in env.margin_grid for v in row
        if math.isfinite(v) and v >= 0
    )
    assert env.n_kills == n_kills_check


def test_compute_envelope_current_scenario_recorded():
    """The current_R_detect / current_v_tgt fields carry the user's
    base-input values (the "you are here" coordinate)."""
    env = compute_operational_envelope(_v2_inputs(), n_R=3, n_v=3, **_FAST_KW)
    assert env.current_R_detect == 1500.0
    assert env.current_v_tgt == 20.0


def test_compute_envelope_kills_in_short_R_high_v_box():
    """Short R + slow target → high margin → finite kills. Coarse
    sanity on the canonical scenario (3 kW CFRP at 100-1000 m vs.
    1-10 m/s targets — this should be a clean kill zone)."""
    env = compute_operational_envelope(
        _v2_inputs(), n_R=3, n_v=3,
        R_low_m=200.0, R_high_m=1000.0,
        v_low_mps=1.0, v_high_mps=10.0,
    )
    # At least half the cells in this small "easy" box should be
    # green (margin >= 0).
    assert env.n_kills >= 5


def test_plot_k_smoke():
    """Plot K renders against a real envelope grid.

    Trace layout (post-2026-04-28 visual fix):
      0. Gray underlay heatmap (covers full grid extent)
      1. Coloured margin heatmap (NaN cells render transparent →
         reveal the gray underlay)
      2. "You are here" scatter marker
    """
    from ui.plots import plot_k_operational_envelope
    env = compute_operational_envelope(_v2_inputs(), n_R=3, n_v=3, **_FAST_KW)
    fig = plot_k_operational_envelope(env)
    # 2 heatmaps + 1 scatter marker.
    assert len(fig.data) == 3
    assert fig.data[0].type == "heatmap"  # gray underlay
    assert fig.data[1].type == "heatmap"  # coloured margin layer
    assert fig.data[2].type == "scatter"  # "you are here" star
    # X-axis is log.
    assert fig.layout.xaxis.type == "log"


def test_plot_k_none_envelope_renders_empty_frame():
    from ui.plots import plot_k_operational_envelope
    fig = plot_k_operational_envelope(None)
    assert len(fig.data) == 0


# ---------------------------------------------------------------------------
# Phase: visual fixes (2026-04-28)
# ---------------------------------------------------------------------------
def test_plot_k_underlay_is_gray_and_hides_colorbar():
    """The gray underlay heatmap (trace 0) must hide its colorbar
    (showscale=False) and ignore hover, so it doesn't compete with
    the coloured layer for visual attention."""
    from ui.plots import plot_k_operational_envelope
    env = compute_operational_envelope(_v2_inputs(), n_R=3, n_v=3, **_FAST_KW)
    fig = plot_k_operational_envelope(env)
    underlay = fig.data[0]
    assert underlay.showscale is False
    assert underlay.hoverinfo == "skip"


def test_plot_k_x_axis_uses_explicit_tickvals():
    """Pre-fix, ``update_xaxes(type='log')`` alone caused Plotly to
    render TWO overlapping tick rows (auto + log-decade). After
    setting ``tickmode='array'`` with explicit tickvals, only one
    tick row appears."""
    from ui.plots import plot_k_operational_envelope
    env = compute_operational_envelope(_v2_inputs(), n_R=3, n_v=3, **_FAST_KW)
    fig = plot_k_operational_envelope(env)
    assert fig.layout.xaxis.tickmode == "array"
    # At least 2 tickvals (≥ 1 decade visible).
    assert len(fig.layout.xaxis.tickvals or ()) >= 2


def test_plot_k_caption_explains_gray_cells():
    """A short annotation under the plot tells the user the gray
    cells are skipped (dwell > 5 min) rather than render bugs."""
    from ui.plots import plot_k_operational_envelope
    env = compute_operational_envelope(_v2_inputs(), n_R=3, n_v=3, **_FAST_KW)
    fig = plot_k_operational_envelope(env)
    annot_texts = [a.text for a in (fig.layout.annotations or [])]
    # Caption must mention BOTH the visual cue ("Gray cells") and the
    # cutoff threshold ("5 min") so the user understands what they're
    # looking at and why.
    combined = " ".join(annot_texts)
    assert "Gray cells" in combined and "5 min" in combined, (
        f"caption should explain gray cells + 5 min cutoff; "
        f"annotations={annot_texts}"
    )


def test_plot_k_skipped_cells_have_helpful_hover():
    """NaN cells now read 'Skipped — engagement window > 5 min' in
    the hover instead of the misleading default 'margin null%'."""
    from ui.plots import plot_k_operational_envelope
    env = compute_operational_envelope(_v2_inputs(), n_R=3, n_v=3, **_FAST_KW)
    fig = plot_k_operational_envelope(env)
    # Trace 1 is the colored heatmap (trace 0 is the gray underlay).
    coloured = fig.data[1]
    assert coloured.customdata is not None, (
        "colored heatmap must carry customdata for per-cell hover text"
    )
    # Every cell's customdata is either the margin readout or the
    # skipped-cell explanation — never anything else.
    flat = [cell for row in coloured.customdata for cell in row]
    for cell_text in flat:
        assert ("margin" in cell_text) or ("Skipped" in cell_text), (
            f"unexpected hover text: {cell_text!r}"
        )


def test_plot_k_cells_have_no_gap():
    """Both heatmap layers use xgap=ygap=0 so adjacent coloured cells
    abut without thin gray gridlines between them."""
    from ui.plots import plot_k_operational_envelope
    env = compute_operational_envelope(_v2_inputs(), n_R=3, n_v=3, **_FAST_KW)
    fig = plot_k_operational_envelope(env)
    for trace in fig.data[:2]:  # both heatmaps
        assert (trace.xgap or 0) == 0
        assert (trace.ygap or 0) == 0


def test_default_bounds_locked_to_200m_12km():
    """Pin the production default bounds — narrowed 2026-04-26 from
    the original 100 m..30 km. Re-widening them silently would put the
    long-range / slow-target M8-timeout corner back into the grid and
    blow the typical compute time from ~90 s to ~30 min."""
    from physics.operational_envelope import (
        _LOG_SPAN_R_LOW_M, _LOG_SPAN_R_HIGH_M,
    )
    assert _LOG_SPAN_R_LOW_M == 200.0
    assert _LOG_SPAN_R_HIGH_M == 12_000.0


def test_default_bounds_used_when_no_kwargs():
    """A grid built without explicit R bounds should respect the
    locked defaults — first cell at 200 m, last cell at 12 km."""
    env = compute_operational_envelope(_v2_inputs(), n_R=3, n_v=3,
                                       v_low_mps=5.0, v_high_mps=30.0)
    assert env.R_detect_axis[0] == pytest.approx(200.0, rel=1e-9)
    assert env.R_detect_axis[-1] == pytest.approx(12_000.0, rel=1e-9)
