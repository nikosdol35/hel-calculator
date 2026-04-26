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


# ---------------------------------------------------------------------------
# Cache-wrapper regression — atmospheric envelope must inject fov_h_deg.
# ---------------------------------------------------------------------------

# Canonical user_inputs the DRI page produces from a fresh sidebar render
# at default values. Used to reproduce the cache-wrapper kwarg flow without
# importing the page module (which would execute Streamlit widget calls
# under bare-mode pytest).
_CANONICAL_DRI_BASE = {
    "dri_n_pixels_h": 1920, "dri_n_pixels_v": 1080,
    "dri_nfov_deg": 1.5, "dri_wfov_deg": 25.0,
    "dri_focal_length_mm": 200.0, "dri_f_number": 2.8,
    "dri_band": "Visible",
    "dri_cn2_preset": "Moderate (canonical mid-altitude)",
    "dri_visibility_km": 23.0, "dri_C0": 0.30,
    "dri_target_preset": "NATO standard",
    "dri_probability": 0.50,
    "dri_n_cycles_D": 1.0, "dri_n_cycles_R": 4.0, "dri_n_cycles_I": 8.0,
}


def _resolve_dri_kwargs_like_page(base: dict, level: str) -> dict:
    """Mirror of ``ui.tools.dri_analyzer._resolve_dri_kwargs``. Inlined
    here so the test doesn't import the page module (which would
    trigger Streamlit widget calls in bare-mode pytest)."""
    from physics.dri_analyzer import CN2_PRESETS, target_critical_dim
    target_preset = base["dri_target_preset"]
    if target_preset == "Custom":
        h_target = float(base.get("dri_target_h_m", 1.0))
    else:
        h_target = target_critical_dim(target_preset)
    cn2 = CN2_PRESETS[base["dri_cn2_preset"]]
    n_cycles_50 = float(base[{
        "Detection": "dri_n_cycles_D",
        "Recognition": "dri_n_cycles_R",
        "Identification": "dri_n_cycles_I",
    }[level]])
    return dict(
        h_target=h_target,
        n_pixels_h=int(base["dri_n_pixels_h"]),
        band=base["dri_band"],
        cn2=cn2,
        V_km=float(base["dri_visibility_km"]),
        f_mm=float(base["dri_focal_length_mm"]),
        f_number=float(base["dri_f_number"]),
        C0=float(base.get("dri_C0", 0.30)),
        probability=float(base.get("dri_probability", 0.50)),
        n_cycles_50=n_cycles_50,
    )


def test_atmospheric_heatmap_cache_wrapper_injects_fov():
    """**Regression for the 2026-04-26 hotfix.**

    ``run_dri_atmospheric_heatmap_cached`` builds its kwargs from
    ``_resolve_dri_kwargs``, which intentionally does NOT carry
    ``fov_h_deg`` (every other helper sweeps FOV per evaluation).
    The atmospheric envelope holds FOV constant at NFOV, so the
    wrapper must explicitly inject ``fov_h_deg=base["dri_nfov_deg"]``.
    Forgetting this injection produced a runtime
    ``TypeError: dri_range() missing 1 required keyword-only argument:
    'fov_h_deg'`` on the live deploy.
    """
    base = _CANONICAL_DRI_BASE
    kwargs = _resolve_dri_kwargs_like_page(base, "Detection")
    kwargs.pop("cn2")
    kwargs.pop("V_km")

    # Reproduce the wrapper's call exactly.
    grid = atmospheric_heatmap(
        cn2_grid=[1e-15, 1e-14, 1e-13],
        visibility_grid=[10.0, 23.0, 50.0],
        level="Detection",
        fov_h_deg=float(base["dri_nfov_deg"]),
        **kwargs,
    )
    assert len(grid) == 3 and all(len(row) == 3 for row in grid)
    # Centre cell (V=23 km, Cn²=1e-14, NATO target, NFOV=1.5°,
    # Visible band) reproduces the canonical Detection range —
    # ~11 km. Pinned numerically.
    centre = grid[1][1] / 1000.0
    assert 9.0 <= centre <= 13.0, (
        f"Atmospheric-heatmap centre cell at the canonical scenario "
        f"should match the Detection-range headline (~11 km); got "
        f"{centre:.2f} km. Likely a kwarg leak (missing fov_h_deg, "
        f"missing target, etc.)."
    )


def test_atmospheric_heatmap_without_fov_raises_typeerror():
    """Defensive: confirms that the underlying ``atmospheric_heatmap``
    DOES require ``fov_h_deg`` — i.e. that the regression-guard test
    above is testing a real failure mode and not a vacuous one."""
    import pytest
    base = _CANONICAL_DRI_BASE
    kwargs = _resolve_dri_kwargs_like_page(base, "Detection")
    kwargs.pop("cn2")
    kwargs.pop("V_km")
    with pytest.raises(TypeError, match="fov_h_deg"):
        atmospheric_heatmap(
            cn2_grid=[1e-14], visibility_grid=[23.0],
            level="Detection",
            **kwargs,  # no fov_h_deg — should raise
        )


def test_dri_atmospheric_heatmap_runner_passes_fov_to_kernel():
    """Pin-the-source check: the page-level cache wrapper
    ``run_dri_atmospheric_heatmap_cached`` MUST call the kernel with
    ``fov_h_deg=...``. Catches a refactor that silently drops the
    injection (which is exactly how the live-deploy bug came in).

    Approach: locate the function via AST, walk the function body
    for an ``atmospheric_heatmap`` call, and confirm one of its
    keyword args is ``fov_h_deg``. Avoids fragile regex matching
    over multi-line arg lists with nested parens.
    """
    import ast
    from pathlib import Path

    src = (Path(__file__).resolve().parent.parent
           / "ui" / "tools" / "dri_analyzer.py").read_text(encoding="utf-8")
    tree = ast.parse(src)

    func = next(
        (node for node in ast.walk(tree)
         if isinstance(node, ast.FunctionDef)
         and node.name == "run_dri_atmospheric_heatmap_cached"),
        None,
    )
    assert func is not None, (
        "Could not locate run_dri_atmospheric_heatmap_cached in "
        "ui/tools/dri_analyzer.py — this regression guard is now stale."
    )

    fov_kw_seen = False
    for node in ast.walk(func):
        if (isinstance(node, ast.Call)
                and isinstance(node.func, ast.Attribute)
                and node.func.attr == "atmospheric_heatmap"):
            kw_names = {kw.arg for kw in node.keywords}
            if "fov_h_deg" in kw_names:
                fov_kw_seen = True
                break
    assert fov_kw_seen, (
        "run_dri_atmospheric_heatmap_cached must pass fov_h_deg= "
        "explicitly to atmospheric_heatmap (the kernel iterates "
        "Cn²/V_km but FOV is fixed at NFOV)."
    )
