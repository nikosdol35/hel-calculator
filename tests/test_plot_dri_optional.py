"""Tests for the four optional DRI plots (PR 4 of the DRI campaign).

Covers:
    plot_dri_distance_vs_target_size
    plot_dri_atmospheric_transmission
    plot_dri_distance_vs_cn2
    plot_dri_heatmap_fov_vs_target
"""
from __future__ import annotations

from physics.dri_analyzer import (
    atmospheric_heatmap, cn2_sweep, heatmap, target_size_sweep,
)
from ui.plots import (
    plot_dri_3d_atmospheric_envelope,
    plot_dri_3d_operational_envelope,
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


# ---------------------------------------------------------------------------
# Plot DRI-8: 3D operational envelope (FOV × target size × Detection range)
# ---------------------------------------------------------------------------

def test_plot_dri_3d_operational_envelope_smoke():
    fov_grid = [1.5, 5.0, 10.0, 25.0]
    target_grid = [0.3, 1.0, 2.3, 5.0]
    grid = heatmap(
        fov_grid_deg=fov_grid,
        target_grid_m=target_grid,
        level="Detection",
        cn2=1e-14,
        **_common_kwargs(),
    )
    grid_km = [[v / 1000.0 for v in row] for row in grid]
    fig = plot_dri_3d_operational_envelope(
        fov_grid_deg=fov_grid,
        target_grid_m=target_grid,
        grid_km=grid_km,
    )
    assert len(fig.data) == 1
    assert fig.data[0].type == "surface"
    # Plotly stores Surface z as a tuple-of-tuples; check the shape.
    z = fig.data[0].z
    assert len(z) == 4 and len(z[0]) == 4


def test_plot_dri_3d_operational_envelope_log_axes():
    """Both x (FOV) and y (target dim) are on log axes — that is the
    convention the 2D heatmap uses too, and is what makes the wide
    span (0.1 — 10 m, 1.5° — 25°) read on a single chart."""
    fig = plot_dri_3d_operational_envelope(
        fov_grid_deg=[1.5, 25.0],
        target_grid_m=[0.3, 5.0],
        grid_km=[[1.0, 2.0], [3.0, 4.0]],
    )
    assert fig.layout.scene.xaxis.type == "log"
    assert fig.layout.scene.yaxis.type == "log"


def test_plot_dri_3d_operational_envelope_z_axis_zero_floor():
    """Range cannot be negative; the z-axis floor is zero."""
    fig = plot_dri_3d_operational_envelope(
        fov_grid_deg=[1.5, 25.0],
        target_grid_m=[0.3, 5.0],
        grid_km=[[1.0, 2.0], [3.0, 4.0]],
    )
    assert fig.layout.scene.zaxis.rangemode == "tozero"


def test_plot_dri_3d_operational_envelope_empty_renders_frame():
    fig = plot_dri_3d_operational_envelope(
        fov_grid_deg=None, target_grid_m=None, grid_km=None,
    )
    assert len(fig.data) == 0


def test_plot_dri_3d_operational_envelope_matches_2d_heatmap_data():
    """Same data feeds both views — the 3D z-grid must match the 2D
    z-grid cell for cell. Catches a future regression where one
    constructor inadvertently transforms the data and the two views
    disagree."""
    fov_grid = [1.5, 5.0, 10.0]
    target_grid = [0.3, 1.0, 2.3]
    grid = heatmap(
        fov_grid_deg=fov_grid,
        target_grid_m=target_grid,
        level="Detection",
        cn2=1e-14,
        **_common_kwargs(),
    )
    grid_km = [[v / 1000.0 for v in row] for row in grid]
    fig_2d = plot_dri_heatmap_fov_vs_target(
        fov_grid_deg=fov_grid, target_grid_m=target_grid, grid_km=grid_km,
    )
    fig_3d = plot_dri_3d_operational_envelope(
        fov_grid_deg=fov_grid, target_grid_m=target_grid, grid_km=grid_km,
    )
    # Both traces hold the same z grid.
    z2 = [list(row) for row in fig_2d.data[0].z]
    z3 = [list(row) for row in fig_3d.data[0].z]
    assert z2 == z3


# ---------------------------------------------------------------------------
# Plot DRI-9: 3D atmospheric envelope (Cn² × visibility × Detection range)
# ---------------------------------------------------------------------------

def _atm_grid(level="Detection"):
    cn2_grid = [1e-16, 1e-15, 1e-14, 1e-13, 5e-13]
    vis_grid = [50.0, 23.0, 10.0, 3.0, 1.0]
    common = _common_kwargs()
    common.pop("V_km")  # swept by atmospheric_heatmap
    grid = atmospheric_heatmap(
        cn2_grid=cn2_grid,
        visibility_grid=vis_grid,
        level=level,
        fov_h_deg=1.5,
        h_target=2.3,
        **common,
    )
    return cn2_grid, vis_grid, grid


def test_atmospheric_heatmap_shape():
    cn2_grid, vis_grid, grid = _atm_grid()
    assert len(grid) == 5  # rows = visibility samples
    assert all(len(row) == 5 for row in grid)  # cols = Cn² samples


def test_atmospheric_heatmap_low_visibility_clamps_range():
    """V=1 km should clamp R_final to the Koschmieder ceiling
    (~0.69 km) regardless of Cn². Catches a regression where Cn²
    interaction would somehow leak past the atmospheric clamp."""
    _, vis_grid, grid = _atm_grid()
    # Bottom row: visibility = 1 km
    bottom_row = grid[-1]  # vis_grid[-1] = 1.0
    for cell in bottom_row:
        # Range is in METERS here (no /1000). Koschmieder @ V=1km,
        # C0=0.30, C_t=0.02 → ~ 692 m.
        assert 600 < cell < 800, (
            f"V=1 km cell out of expected Koschmieder range: {cell} m"
        )


def test_atmospheric_heatmap_strong_turbulence_collapses_clear_air():
    """Top-right corner (V=50 km, Cn²=5e-13) is turbulence-limited and
    must be much smaller than the top-left (V=50, Cn²=1e-16)."""
    _, _, grid = _atm_grid()
    top_left = grid[0][0]   # V=50, Cn²=weakest
    top_right = grid[0][-1]  # V=50, Cn²=strongest
    assert top_left > top_right * 10, (
        f"Strong turbulence should collapse range by >10x at V=50km; "
        f"got {top_left/1000:.1f} km vs {top_right/1000:.1f} km"
    )


def test_plot_dri_3d_atmospheric_envelope_smoke():
    cn2_grid, vis_grid, grid = _atm_grid()
    grid_km = [[v / 1000.0 for v in row] for row in grid]
    fig = plot_dri_3d_atmospheric_envelope(
        cn2_grid=cn2_grid,
        visibility_grid=vis_grid,
        grid_km=grid_km,
    )
    assert len(fig.data) == 1
    assert fig.data[0].type == "surface"
    z = fig.data[0].z
    assert len(z) == 5 and len(z[0]) == 5


def test_plot_dri_3d_atmospheric_envelope_cn2_axis_log():
    """X axis (Cn²) is log-scaled; Y axis (visibility) is linear."""
    fig = plot_dri_3d_atmospheric_envelope(
        cn2_grid=[1e-16, 1e-13],
        visibility_grid=[10.0, 50.0],
        grid_km=[[1.0, 2.0], [3.0, 4.0]],
    )
    assert fig.layout.scene.xaxis.type == "log"
    # Visibility is best read linearly (1–60 km), not log.
    assert fig.layout.scene.yaxis.type != "log"


def test_plot_dri_3d_atmospheric_envelope_empty_renders_frame():
    fig = plot_dri_3d_atmospheric_envelope(
        cn2_grid=None, visibility_grid=None, grid_km=None,
    )
    assert len(fig.data) == 0


def test_plot_dri_3d_atmospheric_envelope_partial_empty_renders_frame():
    """Missing one of the three inputs → empty-frame fallback."""
    fig = plot_dri_3d_atmospheric_envelope(
        cn2_grid=[1e-14], visibility_grid=[23.0], grid_km=None,
    )
    assert len(fig.data) == 0
