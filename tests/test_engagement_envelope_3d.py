"""Tests for the 3D engagement-envelope plots and the atmospheric
envelope sweep added alongside the kinematic envelope.

Two new surfaces on the Engagement tab:
  - Plot K-3D — companion 3D view of the existing kinematic envelope
    (R_detect × v_tgt → margin). Same EnvelopeGrid, lifted into Z.
  - Plot M  — atmospheric envelope (Cn² × V → margin) at fixed
    kinematics, with both 2D heatmap and 3D surface.

Coverage:
  - compute_atmospheric_envelope returns an AtmosphericEnvelopeGrid
    with the right shape and log-spaced axes
  - both atmospheric axes are log-spaced
  - bookkeeping (n_kills + n_nan == total cells)
  - non-v2 inputs rejected with KeyError
  - turbulence-limited regime: strong Cn² collapses margin
  - extinction-limited regime: very low V collapses margin
  - 3D plot_k_operational_envelope_3d renders against a real grid
  - 3D plot_m_atmospheric_envelope / _3d render against a real grid
  - None envelope falls back to empty frame for both
  - cell-for-cell match between the 2D and 3D atmospheric figures
    (same data, two views — must agree exactly)
"""
from __future__ import annotations

import math

import pytest

from physics.operational_envelope import (
    AtmosphericEnvelopeGrid,
    compute_atmospheric_envelope,
    compute_operational_envelope,
)
from tests.golden.scenarios import C_UAS_1500M


def _v2_inputs() -> dict:
    inputs = dict(C_UAS_1500M)
    inputs.pop("R", None)
    inputs.pop("v_perp", None)
    inputs.update({
        "R_detect": 1500, "R_min": 100,
        "engagement_geometry": "head_on",
    })
    return inputs


# Atmospheric sweep is full-chain per cell (same per-cell cost as the
# kinematic envelope). Tight test bounds: Cn² 1e-16..1e-13, V 5..30 km
# — keeps every cell inside a regime the orchestrator can resolve in
# a few seconds.
_FAST_ATM_KW = dict(
    cn2_low=1.0e-16, cn2_high=1.0e-13,
    V_low_km=5.0, V_high_km=30.0,
)


# ---------------------------------------------------------------------------
# compute_atmospheric_envelope — structural tests
# ---------------------------------------------------------------------------
def test_atmospheric_envelope_returns_grid_dataclass():
    env = compute_atmospheric_envelope(
        _v2_inputs(), n_cn2=3, n_V=3, **_FAST_ATM_KW,
    )
    assert isinstance(env, AtmosphericEnvelopeGrid)
    assert len(env.cn2_axis) == 3
    assert len(env.V_km_axis) == 3
    assert len(env.margin_grid) == 3
    assert all(len(row) == 3 for row in env.margin_grid)


def test_atmospheric_envelope_axes_log_spaced():
    """Both axes are log-spaced (Cn² spans many decades, V is also
    decade-scale)."""
    env = compute_atmospheric_envelope(
        _v2_inputs(), n_cn2=3, n_V=3, **_FAST_ATM_KW,
    )
    cn2 = env.cn2_axis
    V = env.V_km_axis
    assert cn2[1] / cn2[0] == pytest.approx(cn2[2] / cn2[1], rel=1e-9)
    assert V[1] / V[0] == pytest.approx(V[2] / V[1], rel=1e-9)


def test_atmospheric_envelope_bookkeeping():
    env = compute_atmospheric_envelope(
        _v2_inputs(), n_cn2=3, n_V=3, **_FAST_ATM_KW,
    )
    total = len(env.cn2_axis) * len(env.V_km_axis)
    n_finite = sum(
        1 for row in env.margin_grid for v in row if math.isfinite(v)
    )
    n_nan = sum(
        1 for row in env.margin_grid for v in row if math.isnan(v)
    )
    assert n_finite + n_nan == total
    assert env.n_failures == n_nan
    n_kills_check = sum(
        1 for row in env.margin_grid for v in row
        if math.isfinite(v) and v >= 0
    )
    assert env.n_kills == n_kills_check


def test_atmospheric_envelope_v1_inputs_rejected():
    inputs_v1 = dict(C_UAS_1500M)
    for key in ("R_detect", "R_min", "engagement_geometry"):
        inputs_v1.pop(key, None)
    with pytest.raises(KeyError, match="engagement_geometry"):
        compute_atmospheric_envelope(inputs_v1, n_cn2=3, n_V=3)


def test_atmospheric_envelope_current_scenario_recorded():
    """current_cn2 / current_V_km carry the user's base-input values
    for the 'you are here' marker on the heatmap."""
    inputs = _v2_inputs()
    env = compute_atmospheric_envelope(
        inputs, n_cn2=3, n_V=3, **_FAST_ATM_KW,
    )
    assert env.current_cn2 == float(inputs["Cn2_value"])
    assert env.current_V_km == float(inputs["V"])


# ---------------------------------------------------------------------------
# Regime checks — does the physics behave correctly across the sweep?
# ---------------------------------------------------------------------------
def test_atmospheric_envelope_strong_cn2_drops_margin():
    """Holding V fixed, increasing Cn² broadens the spot through
    turbulence MTF and reduces the engagement margin. Compare the
    weakest-Cn² and strongest-Cn² columns of the same V row."""
    env = compute_atmospheric_envelope(
        _v2_inputs(), n_cn2=3, n_V=3,
        cn2_low=1.0e-16, cn2_high=5.0e-13,
        V_low_km=10.0, V_high_km=20.0,
    )
    # Pick a middle-V row so neither Beer-Lambert extinction nor
    # numerical clamping dominates. Compare leftmost (weakest Cn²) to
    # rightmost (strongest Cn²) cell.
    middle_row = env.margin_grid[1]
    weak_cn2 = middle_row[0]
    strong_cn2 = middle_row[-1]
    if math.isfinite(weak_cn2) and math.isfinite(strong_cn2):
        # Either the strong-Cn² cell has lower margin, or it failed
        # to close at all (margin clamped to -100%). Both verify the
        # physics direction.
        assert strong_cn2 <= weak_cn2 + 1e-6


def test_atmospheric_envelope_low_visibility_drops_margin():
    """Holding Cn² fixed, very low V (heavy fog) cuts on-target
    irradiance via Beer-Lambert and reduces the engagement margin."""
    env = compute_atmospheric_envelope(
        _v2_inputs(), n_cn2=3, n_V=3,
        cn2_low=1.0e-15, cn2_high=1.0e-14,
        V_low_km=0.5, V_high_km=30.0,
    )
    # Same middle-Cn² column across the V axis.
    low_V = env.margin_grid[0][1]   # row=0 → V_low_km
    high_V = env.margin_grid[-1][1]  # row=last → V_high_km
    if math.isfinite(low_V) and math.isfinite(high_V):
        assert low_V <= high_V + 1e-6


# ---------------------------------------------------------------------------
# Plot smoke tests
# ---------------------------------------------------------------------------
def test_plot_k_3d_smoke():
    from ui.plots import plot_k_operational_envelope_3d
    env = compute_operational_envelope(
        _v2_inputs(), n_R=3, n_v=3,
        R_low_m=200.0, R_high_m=2_000.0,
        v_low_mps=5.0, v_high_mps=30.0,
    )
    fig = plot_k_operational_envelope_3d(env)
    assert len(fig.data) == 1
    assert fig.data[0].type == "surface"
    # 3D scene is configured.
    assert fig.layout.scene.xaxis.type == "log"


def test_plot_k_3d_none_envelope_renders_empty_frame():
    from ui.plots import plot_k_operational_envelope_3d
    fig = plot_k_operational_envelope_3d(None)
    assert len(fig.data) == 0


def test_plot_m_2d_smoke():
    from ui.plots import plot_m_atmospheric_envelope
    env = compute_atmospheric_envelope(
        _v2_inputs(), n_cn2=3, n_V=3, **_FAST_ATM_KW,
    )
    fig = plot_m_atmospheric_envelope(env)
    # Heatmap + "you are here" scatter.
    assert len(fig.data) == 2
    assert fig.data[0].type == "heatmap"
    assert fig.data[1].type == "scatter"
    # Both axes are log.
    assert fig.layout.xaxis.type == "log"
    assert fig.layout.yaxis.type == "log"


def test_plot_m_3d_smoke():
    from ui.plots import plot_m_atmospheric_envelope_3d
    env = compute_atmospheric_envelope(
        _v2_inputs(), n_cn2=3, n_V=3, **_FAST_ATM_KW,
    )
    fig = plot_m_atmospheric_envelope_3d(env)
    assert len(fig.data) == 1
    assert fig.data[0].type == "surface"
    assert fig.layout.scene.xaxis.type == "log"
    assert fig.layout.scene.yaxis.type == "log"


def test_plot_m_none_envelope_renders_empty_frame():
    from ui.plots import (
        plot_m_atmospheric_envelope, plot_m_atmospheric_envelope_3d,
    )
    assert len(plot_m_atmospheric_envelope(None).data) == 0
    assert len(plot_m_atmospheric_envelope_3d(None).data) == 0


def test_plot_m_2d_and_3d_share_data():
    """The 2D heatmap and the 3D surface are two views of the same
    AtmosphericEnvelopeGrid — they must encode the same z-grid
    cell-for-cell."""
    from ui.plots import (
        plot_m_atmospheric_envelope, plot_m_atmospheric_envelope_3d,
    )
    env = compute_atmospheric_envelope(
        _v2_inputs(), n_cn2=3, n_V=3, **_FAST_ATM_KW,
    )
    fig_2d = plot_m_atmospheric_envelope(env)
    fig_3d = plot_m_atmospheric_envelope_3d(env)
    z_2d = fig_2d.data[0].z
    z_3d = fig_3d.data[0].z
    assert len(z_2d) == len(z_3d)
    for row_2d, row_3d in zip(z_2d, z_3d):
        assert len(row_2d) == len(row_3d)
        for a, b in zip(row_2d, row_3d):
            if math.isnan(a):
                assert math.isnan(b)
            else:
                assert a == pytest.approx(b, rel=1e-12)


def test_plot_k_2d_and_3d_share_data():
    """Same cell-for-cell agreement test for the kinematic envelope's
    2D heatmap and 3D surface — they share an EnvelopeGrid."""
    from ui.plots import (
        plot_k_operational_envelope, plot_k_operational_envelope_3d,
    )
    env = compute_operational_envelope(
        _v2_inputs(), n_R=3, n_v=3,
        R_low_m=200.0, R_high_m=2_000.0,
        v_low_mps=5.0, v_high_mps=30.0,
    )
    fig_2d = plot_k_operational_envelope(env)
    fig_3d = plot_k_operational_envelope_3d(env)
    z_2d = fig_2d.data[0].z
    z_3d = fig_3d.data[0].z
    assert len(z_2d) == len(z_3d)
    for row_2d, row_3d in zip(z_2d, z_3d):
        assert len(row_2d) == len(row_3d)
        for a, b in zip(row_2d, row_3d):
            if math.isnan(a):
                assert math.isnan(b)
            else:
                assert a == pytest.approx(b, rel=1e-12)
