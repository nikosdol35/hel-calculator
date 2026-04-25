"""Tests for the DRI FOV-sweep plot constructor (PR 3 of the DRI campaign).

Smoke + structural checks against the always-render frame contract:
- the plot returns a valid go.Figure for any sweep
- empty / None sweep falls back to the empty frame
- trace count and types are stable across all three D / R / I levels
"""
from __future__ import annotations

from physics.dri_analyzer import fov_sweep
from ui.plots import plot_dri_distance_vs_fov


# ---------------------------------------------------------------------------
# Common sweep-builder so tests share a reasonable input set.
# ---------------------------------------------------------------------------

def _v_sweep(level: str, n_points: int = 12) -> list[dict]:
    return fov_sweep(
        level=level,
        fov_low_deg=1.5,
        fov_high_deg=25.0,
        n_points=n_points,
        h_target=2.3,
        n_pixels_h=1920,
        band="Visible",
        cn2=1e-14,
        V_km=23.0,
        f_mm=200.0,
        f_number=2.8,
        C0=0.30,
        probability=0.50,
    )


# ---------------------------------------------------------------------------
# Smoke tests
# ---------------------------------------------------------------------------

def test_plot_dri_fov_smoke_detection():
    """Detection FOV-sweep plot renders 3 traces (final + geom + atm)."""
    sweep = _v_sweep("Detection")
    fig = plot_dri_distance_vs_fov(sweep, level="Detection", nfov_deg=1.5)
    assert len(fig.data) == 3
    names = [t.name for t in fig.data]
    assert "Detection range (final)" in names
    assert "Geometric limit (Johnson)" in names
    assert "Atmospheric ceiling (Koschmieder)" in names


def test_plot_dri_fov_smoke_recognition():
    """Recognition FOV-sweep plot renders cleanly."""
    sweep = _v_sweep("Recognition")
    fig = plot_dri_distance_vs_fov(sweep, level="Recognition", nfov_deg=1.5)
    assert len(fig.data) == 3
    assert "Recognition range (final)" in [t.name for t in fig.data]


def test_plot_dri_fov_smoke_identification():
    """Identification FOV-sweep plot renders cleanly."""
    sweep = _v_sweep("Identification")
    fig = plot_dri_distance_vs_fov(sweep, level="Identification", nfov_deg=1.5)
    assert len(fig.data) == 3
    assert "Identification range (final)" in [t.name for t in fig.data]


# ---------------------------------------------------------------------------
# Empty / None sweep fallback
# ---------------------------------------------------------------------------

def test_plot_dri_fov_none_sweep_renders_empty_frame():
    fig = plot_dri_distance_vs_fov(None, level="Detection", nfov_deg=1.5)
    assert len(fig.data) == 0


def test_plot_dri_fov_empty_list_renders_empty_frame():
    fig = plot_dri_distance_vs_fov([], level="Detection", nfov_deg=1.5)
    assert len(fig.data) == 0


# ---------------------------------------------------------------------------
# Layout checks
# ---------------------------------------------------------------------------

def test_plot_dri_fov_y_axis_starts_at_zero():
    """Range cannot be negative; the y-axis starts at zero."""
    sweep = _v_sweep("Detection")
    fig = plot_dri_distance_vs_fov(sweep, level="Detection", nfov_deg=1.5)
    assert fig.layout.yaxis.rangemode == "tozero"


def test_plot_dri_fov_nfov_marker_present():
    """When nfov_deg is supplied, a vertical line at NFOV is drawn."""
    sweep = _v_sweep("Detection")
    fig = plot_dri_distance_vs_fov(sweep, level="Detection", nfov_deg=1.5)
    # add_vline appends to fig.layout.shapes.
    assert len(fig.layout.shapes or []) >= 1


def test_plot_dri_fov_omits_marker_when_nfov_none():
    """No vertical reference when nfov_deg is None."""
    sweep = _v_sweep("Detection")
    fig = plot_dri_distance_vs_fov(sweep, level="Detection", nfov_deg=None)
    assert len(fig.layout.shapes or []) == 0


# ---------------------------------------------------------------------------
# Numerical sanity (curve endpoint matches single-point compute)
# ---------------------------------------------------------------------------

def test_plot_dri_fov_first_point_at_nfov():
    """Sweep first entry's fov_deg == NFOV (low end) by construction."""
    sweep = _v_sweep("Detection")
    assert sweep[0]["fov_deg"] == 1.5


def test_plot_dri_fov_curve_decreases_with_wider_fov():
    """Wider FOV → shorter geometric range. Plot data reflects this."""
    sweep = _v_sweep("Detection")
    fig = plot_dri_distance_vs_fov(sweep, level="Detection", nfov_deg=1.5)
    # The first trace is the 'final' curve. Its y-values should
    # generally decrease as FOV increases (atmosphere may flatten the
    # tail when geometry-limited shrinks below R_atm).
    final_trace = fig.data[0]
    ys = list(final_trace.y)
    # NFOV value > WFOV value (with at most floating-point slack).
    assert ys[0] > ys[-1] - 1e-6
