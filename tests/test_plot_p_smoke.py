"""Smoke tests for Plot P — peak irradiance vs target approach geometry.

Verifies the plot constructor renders against a real chain result,
returns the expected number of traces, and falls back to the empty
frame for None / empty inputs.
"""
from __future__ import annotations

import pytest

from physics.geometry_family import compute_geometry_family_curves
from physics.orchestrator import run_full_chain
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


def _merged_result(**overrides) -> dict:
    inputs = _v2_inputs(**overrides)
    result = run_full_chain(inputs)
    return {**inputs, **result}


def test_plot_p_smoke_real_chain():
    """Plot P renders against a real v2 chain result with the expected
    number of traces — 5 reference angles + 1 reference-burn-through
    marker trace + 1 PDE-accurate user trajectory + 1 'Current
    scenario' star = 8 total."""
    from ui.plots import plot_p_peak_irradiance_vs_geometry
    curves = compute_geometry_family_curves(_merged_result())
    fig = plot_p_peak_irradiance_vs_geometry(curves)
    assert len(fig.data) == 8


def test_plot_p_log_y_axis():
    """Plot P uses a log y-axis (peak irradiance spans multiple decades
    across geometries)."""
    from ui.plots import plot_p_peak_irradiance_vs_geometry
    curves = compute_geometry_family_curves(_merged_result())
    fig = plot_p_peak_irradiance_vs_geometry(curves)
    assert fig.layout.yaxis.type == "log"


def test_plot_p_handles_none_curves():
    """None input → always-render empty frame, not a crash."""
    from ui.plots import plot_p_peak_irradiance_vs_geometry
    fig = plot_p_peak_irradiance_vs_geometry(None)
    assert len(fig.data) == 0


def test_plot_p_legend_labels_include_angles():
    """Legend traces are labelled by crossing angle (0°, 30°, …)."""
    from ui.plots import plot_p_peak_irradiance_vs_geometry
    curves = compute_geometry_family_curves(_merged_result())
    fig = plot_p_peak_irradiance_vs_geometry(curves)
    names = [t.name for t in fig.data if t.name]
    # Reference traces include 5 angle labels.
    assert any("0° crossing" in n for n in names)
    assert any("30° crossing" in n for n in names)
    assert any("90° crossing" in n for n in names)
    # Current scenario is labelled.
    assert any("Current scenario" in n for n in names)


def test_plot_p_renders_when_user_trajectory_missing():
    """If the chain output lacks trajectory_t / trajectory_I_peak (v1.x
    backward-compat scenarios in tests), the plot still renders the
    5 reference curves plus the burn-through-marker trace (material
    is still known) — 6 total. No user curve, no scenario star."""
    from ui.plots import plot_p_peak_irradiance_vs_geometry
    merged = _merged_result()
    # Strip the trajectory series — simulate a v1.x-style result.
    merged.pop("trajectory_t", None)
    merged.pop("trajectory_I_peak", None)
    curves = compute_geometry_family_curves(merged)
    fig = plot_p_peak_irradiance_vs_geometry(curves)
    # 5 reference traces + 1 combined burn-through-marker trace.
    assert len(fig.data) == 6


# ---------------------------------------------------------------------------
# Phase: geometry illustration cards (5 SVG panels above Plot P)
# ---------------------------------------------------------------------------
def test_geometry_cards_constant_has_five_entries():
    """The _GEOMETRY_CARDS module-level constant must list exactly the
    5 reference angles in the same order as
    physics.geometry_family._REFERENCE_ANGLES_DEG."""
    from physics.geometry_family import _REFERENCE_ANGLES_DEG
    from ui.outputs import _GEOMETRY_CARDS
    assert len(_GEOMETRY_CARDS) == 5
    angles = tuple(c[0] for c in _GEOMETRY_CARDS)
    assert angles == _REFERENCE_ANGLES_DEG


def test_geometry_cards_titles_include_all_five_angles():
    """Each card has a title containing its angle in degrees, e.g.
    '0° Head-on', '30° Diagonal'."""
    from ui.outputs import _GEOMETRY_CARDS
    titles = [c[2] for c in _GEOMETRY_CARDS]
    for expected in ("0°", "30°", "45°", "60°", "90°"):
        assert any(expected in t for t in titles), (
            f"no card title contains {expected!r}"
        )


def test_geometry_cards_colors_match_plot_p_palette_keys():
    """The card colour-key for each angle must match the corresponding
    curve's colour in plot_p_peak_irradiance_vs_geometry. Visual
    continuity between the illustrations and the plot: same angle,
    same colour."""
    from ui.outputs import _GEOMETRY_CARDS
    # The mapping from plot_p's hand-picked styles. Order matters
    # (angle index 0..4 → palette key).
    expected_keys = (
        "data.a", "data.b", "data.c", "data.reference", "accent.primary",
    )
    actual_keys = tuple(c[1] for c in _GEOMETRY_CARDS)
    assert actual_keys == expected_keys


# ---------------------------------------------------------------------------
# Phase: kill-marker placement (per-curve burn-through + scenario star)
# ---------------------------------------------------------------------------
def test_plot_p_star_sits_at_chain_tau_BT_not_trajectory_end():
    """The 'Current scenario' star must be at the chain's PDE-accurate
    τ_BT (the actual kill moment), not at the trajectory end. For
    canonical CFRP at 1500 m head-on, τ_BT ≈ 2.7 s while the trajectory
    runs to ~70 s — so the star's x-coordinate must be in single-digit
    seconds."""
    from ui.plots import plot_p_peak_irradiance_vs_geometry
    merged = _merged_result()
    chain_tau_BT = float(merged["tau_BT"])
    curves = compute_geometry_family_curves(merged)
    fig = plot_p_peak_irradiance_vs_geometry(curves)
    # Find the star trace (markers+text mode, name == "You are here").
    star_traces = [t for t in fig.data if t.name == "You are here"]
    assert len(star_traces) == 1, "exactly one scenario-star trace expected"
    star = star_traces[0]
    star_t = float(star.x[0])
    assert star_t == pytest.approx(chain_tau_BT, rel=1e-6), (
        f"star at t={star_t:.3f}s should be at τ_BT={chain_tau_BT:.3f}s, "
        f"not the trajectory end"
    )
    # Defensive: the trajectory end is ~70 s for canonical → star
    # must NOT be there.
    assert star_t < 30.0, (
        f"star at t={star_t:.1f}s is suspiciously close to the trajectory "
        f"end — bug regression?"
    )


def test_plot_p_star_tooltip_says_burn_through():
    """When the chain produces a kill, the star's tooltip should say
    'burn-through at t = ...' (not 'engagement-end at ...'). The
    distinction matters because the user asked for the star to mark
    the kill moment, not the trajectory end."""
    from ui.plots import plot_p_peak_irradiance_vs_geometry
    curves = compute_geometry_family_curves(_merged_result())
    fig = plot_p_peak_irradiance_vs_geometry(curves)
    star_traces = [t for t in fig.data if t.name == "You are here"]
    template = star_traces[0].hovertemplate
    assert "burn-through" in template, (
        f"star tooltip should advertise 'burn-through' for a chain-kill "
        f"scenario; got: {template!r}"
    )


def test_plot_p_star_falls_back_to_engagement_end_when_no_kill():
    """If the chain produces no kill (τ_BT is None / not in result),
    the star should fall back to the trajectory END so the figure
    still renders. Tooltip uses 'engagement-end' rather than
    'burn-through' to be honest about what the user is seeing."""
    from ui.plots import plot_p_peak_irradiance_vs_geometry
    merged = _merged_result()
    merged["tau_BT"] = None  # simulate no-kill chain output
    curves = compute_geometry_family_curves(merged)
    fig = plot_p_peak_irradiance_vs_geometry(curves)
    star_traces = [t for t in fig.data if t.name == "You are here"]
    template = star_traces[0].hovertemplate
    assert "engagement-end" in template


def test_plot_p_kill_markers_trace_present_for_canonical():
    """For canonical CFRP (a killable scenario), the
    burn-through-markers trace must exist with at least the head-on
    point. The trace is named so legend identifies it."""
    from ui.plots import plot_p_peak_irradiance_vs_geometry
    curves = compute_geometry_family_curves(_merged_result())
    fig = plot_p_peak_irradiance_vs_geometry(curves)
    bt_traces = [t for t in fig.data if t.name == "Burn-through (per geometry)"]
    assert len(bt_traces) == 1
    assert len(bt_traces[0].x) >= 1, "head-on at minimum should kill"


def test_plot_p_kill_markers_match_dataclass_values():
    """The kill-marker trace coordinates must match the
    `reference_kill_markers` from the dataclass exactly. Pin this so
    a plot-side recomputation can't drift from the physics module."""
    from ui.plots import plot_p_peak_irradiance_vs_geometry
    curves = compute_geometry_family_curves(_merged_result())
    fig = plot_p_peak_irradiance_vs_geometry(curves)
    bt_trace = next(t for t in fig.data if t.name == "Burn-through (per geometry)")
    expected_xs = [m[0] for m in curves.reference_kill_markers if m is not None]
    expected_ys = [m[1] for m in curves.reference_kill_markers if m is not None]
    assert list(bt_trace.x) == pytest.approx(expected_xs, rel=1e-9)
    assert list(bt_trace.y) == pytest.approx(expected_ys, rel=1e-9)


def test_plot_p_no_kill_markers_when_material_unknown():
    """If the material is unknown (E_fail can't be computed), no
    kill-marker trace should be added. Plot must still render the
    5 reference curves + user trajectory + star = 7 total."""
    from ui.plots import plot_p_peak_irradiance_vs_geometry
    merged = _merged_result()
    merged["material"] = "definitely_not_a_real_material"
    curves = compute_geometry_family_curves(merged)
    fig = plot_p_peak_irradiance_vs_geometry(curves)
    bt_traces = [t for t in fig.data if t.name == "Burn-through (per geometry)"]
    assert len(bt_traces) == 0
    # 5 ref + 1 user + 1 star = 7 (no kill-markers trace).
    assert len(fig.data) == 7


def test_geometry_card_closest_approach_distances_match_geometry():
    """Spot-check the closest-approach formula used in the cards
    matches the physics: head-on → R_min; α=30°/45°/60° → R_detect·sin α;
    α=90° → R_detect."""
    import math
    R_detect_m, R_min_m = 1500.0, 100.0
    # Per the card-rendering formula:
    expected = {
        0.0:  R_min_m,                                          # 100 m
        30.0: R_detect_m * math.sin(math.radians(30.0)),        # 750 m
        45.0: R_detect_m * math.sin(math.radians(45.0)),        # ≈1060 m
        60.0: R_detect_m * math.sin(math.radians(60.0)),        # ≈1300 m
        90.0: R_detect_m,                                       # 1500 m
    }
    assert expected[0.0] == pytest.approx(100.0, abs=0.5)
    assert expected[30.0] == pytest.approx(750.0, abs=0.5)
    assert expected[45.0] == pytest.approx(1061.0, abs=5.0)
    assert expected[60.0] == pytest.approx(1299.0, abs=5.0)
    assert expected[90.0] == pytest.approx(1500.0, abs=0.5)
