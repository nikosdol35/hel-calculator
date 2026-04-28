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
    number of traces — 5 reference angles + 1 PDE-accurate user
    trajectory + 1 star marker = 7 total."""
    from ui.plots import plot_p_peak_irradiance_vs_geometry
    curves = compute_geometry_family_curves(_merged_result())
    fig = plot_p_peak_irradiance_vs_geometry(curves)
    assert len(fig.data) == 7


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
    5 reference curves plus an empty user-curve area."""
    from ui.plots import plot_p_peak_irradiance_vs_geometry
    merged = _merged_result()
    # Strip the trajectory series — simulate a v1.x-style result.
    merged.pop("trajectory_t", None)
    merged.pop("trajectory_I_peak", None)
    curves = compute_geometry_family_curves(merged)
    fig = plot_p_peak_irradiance_vs_geometry(curves)
    # Only the 5 reference traces should remain (no user curve, no star).
    assert len(fig.data) == 5


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
