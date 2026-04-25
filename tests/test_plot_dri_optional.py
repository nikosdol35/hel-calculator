"""Tests for the four optional DRI plots (PR 4 of the DRI campaign).

Covers:
    plot_dri_distance_vs_target_size
    plot_dri_atmospheric_transmission
    plot_dri_distance_vs_cn2
    plot_dri_heatmap_fov_vs_target
"""
from __future__ import annotations

from physics.dri_analyzer import (
    cn2_sweep, heatmap, target_size_sweep,
)
from ui.plots import (
    plot_dri_atmospheric_transmission,
    plot_dri_distance_vs_cn2,
    plot_dri_distance_vs_target_size,
    plot_dri_heatmap_fov_vs_target,
)


# ---------------------------------------------------------------------------
# Common kwargs
# ---------------------------------------------------------------------------

def _common_kwargs():
    return dict(
        n_pixels_h=1920,
        band="Visible",
        V_km=23.0,
        f_mm=200.0,
        f_number=2.8,
        C0=0.30,
        probability=0.50,
    )


# ---------------------------------------------------------------------------
# Plot DRI-4: distance vs target size
# ---------------------------------------------------------------------------

def _target_size_sweeps():
    sizes = [0.2, 0.5, 1.0, 2.3, 5.0]
    base = dict(fov_h_deg=1.5, cn2=1e-14, **_common_kwargs())
    sw_d = target_size_sweep(level="Detection", sizes_m=sizes, **base)
    sw_r = target_size_sweep(level="Recognition", sizes_m=sizes, **base)
    sw_i = target_size_sweep(level="Identification", sizes_m=sizes, **base)
    return sw_d, sw_r, sw_i


def test_plot_dri_target_size_smoke():
    sw_d, sw_r, sw_i = _target_size_sweeps()
    fig = plot_dri_distance_vs_target_size(sw_d, sw_r, sw_i)
    assert len(fig.data) == 3
    names = [t.name for t in fig.data]
    assert "Detection" in names
    assert "Recognition" in names
    assert "Identification" in names


def test_plot_dri_target_size_log_x_axis():
    sw_d, sw_r, sw_i = _target_size_sweeps()
    fig = plot_dri_distance_vs_target_size(sw_d, sw_r, sw_i)
    assert fig.layout.xaxis.type == "log"


def test_plot_dri_target_size_empty_renders_frame():
    fig = plot_dri_distance_vs_target_size(None, None, None)
    assert len(fig.data) == 0


def test_plot_dri_target_size_partial_empty_renders_frame():
    """If any one sweep is empty, the empty-frame fallback triggers."""
    sw_d, sw_r, sw_i = _target_size_sweeps()
    fig = plot_dri_distance_vs_target_size(sw_d, sw_r, [])
    assert len(fig.data) == 0


# ---------------------------------------------------------------------------
# Plot DRI-5: atmospheric transmission vs range
# ---------------------------------------------------------------------------

def test_plot_dri_atmospheric_transmission_smoke():
    fig = plot_dri_atmospheric_transmission(alpha_per_km=0.17, R_max_km=30.0)
    assert len(fig.data) == 1
    # Y-axis range pinned [0, 1].
    assert fig.layout.yaxis.range[0] == 0.0
    assert fig.layout.yaxis.range[1] == 1.0


def test_plot_dri_atmospheric_transmission_starts_at_one():
    """At R=0, τ = exp(0) = 1."""
    fig = plot_dri_atmospheric_transmission(alpha_per_km=0.17, R_max_km=10.0)
    ys = list(fig.data[0].y)
    assert abs(ys[0] - 1.0) < 1e-9


def test_plot_dri_atmospheric_transmission_decays_monotonically():
    """τ(R) is monotonically decreasing."""
    fig = plot_dri_atmospheric_transmission(alpha_per_km=0.17, R_max_km=20.0)
    ys = list(fig.data[0].y)
    for a, b in zip(ys, ys[1:]):
        assert b <= a + 1e-9


def test_plot_dri_atmospheric_transmission_zero_alpha_renders_frame():
    """α = 0 → vacuum advisory frame."""
    fig = plot_dri_atmospheric_transmission(alpha_per_km=0.0, R_max_km=10.0)
    assert len(fig.data) == 0


def test_plot_dri_atmospheric_transmission_none_alpha_renders_frame():
    fig = plot_dri_atmospheric_transmission(alpha_per_km=None, R_max_km=10.0)
    assert len(fig.data) == 0


def test_plot_dri_atmospheric_transmission_one_over_e_reference_present():
    """A horizontal line at 1/e is added as a layout shape."""
    fig = plot_dri_atmospheric_transmission(alpha_per_km=0.17, R_max_km=30.0)
    # add_hline appends to fig.layout.shapes.
    assert len(fig.layout.shapes or []) >= 1


# ---------------------------------------------------------------------------
# Plot DRI-6: distance vs Cn²
# ---------------------------------------------------------------------------

def _cn2_sweeps():
    base = dict(fov_h_deg=1.5, h_target=2.3, **_common_kwargs())
    sw_d = cn2_sweep(level="Detection", **base)
    sw_r = cn2_sweep(level="Recognition", **base)
    sw_i = cn2_sweep(level="Identification", **base)
    return sw_d, sw_r, sw_i


def test_plot_dri_cn2_smoke():
    sw_d, sw_r, sw_i = _cn2_sweeps()
    fig = plot_dri_distance_vs_cn2(sw_d, sw_r, sw_i)
    assert len(fig.data) == 3


def test_plot_dri_cn2_log_x_axis():
    sw_d, sw_r, sw_i = _cn2_sweeps()
    fig = plot_dri_distance_vs_cn2(sw_d, sw_r, sw_i)
    assert fig.layout.xaxis.type == "log"


def test_plot_dri_cn2_empty_renders_frame():
    fig = plot_dri_distance_vs_cn2(None, None, None)
    assert len(fig.data) == 0


# ---------------------------------------------------------------------------
# Plot DRI-7: heatmap
# ---------------------------------------------------------------------------

def test_plot_dri_heatmap_smoke():
    fov_grid = [1.5, 5.0, 10.0, 25.0]
    target_grid = [0.3, 1.0, 2.3]
    grid = heatmap(
        fov_grid_deg=fov_grid,
        target_grid_m=target_grid,
        level="Detection",
        cn2=1e-14,
        **_common_kwargs(),
    )
    grid_km = [[v / 1000.0 for v in row] for row in grid]
    fig = plot_dri_heatmap_fov_vs_target(
        fov_grid_deg=fov_grid,
        target_grid_m=target_grid,
        grid_km=grid_km,
    )
    assert len(fig.data) == 1
    assert fig.data[0].type == "heatmap"


def test_plot_dri_heatmap_axes_log():
    fig = plot_dri_heatmap_fov_vs_target(
        fov_grid_deg=[1.5, 25.0],
        target_grid_m=[0.3, 5.0],
        grid_km=[[1.0, 2.0], [3.0, 4.0]],
    )
    assert fig.layout.xaxis.type == "log"
    assert fig.layout.yaxis.type == "log"


def test_plot_dri_heatmap_empty_renders_frame():
    fig = plot_dri_heatmap_fov_vs_target(
        fov_grid_deg=None, target_grid_m=None, grid_km=None,
    )
    assert len(fig.data) == 0
