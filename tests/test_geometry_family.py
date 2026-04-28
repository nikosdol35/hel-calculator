"""Tests for the geometry-family curve module behind Plot P.

PR: feature/plot-p-geometry-family (2026-04-28).

Plot P shows peak irradiance vs engagement time at 5 reference target
approach geometries (head-on, 30°, 45°, 60°, perpendicular) plus the
user's current chain trajectory. Reference curves use a lightweight
M4+M5+M7-only path (skips M6 blooming + M8 PDE), same simplification
spirit as cn2_family / jitter_sensitivity.

Coverage:
  - Dataclass shape (5 reference angles)
  - Trajectory math: α=0° is exact head-on; α=90° has R only increasing
  - Closest-approach distance ≈ R_detect · sin(α) for each reference
  - Truncation: head-on stops at R_min; angled crossings stop at
    closest approach; α=90° caps at t_max
  - I_peak monotone-decreasing in R at fixed α (more range → wider
    spot → less peak intensity)
  - Higher α → lower I_peak peak (target never gets as close)
  - Wall-clock <1 s for full 5×30 cell sweep
  - Defensive paths: missing by_module / R_detect / engagement_geometry
"""
from __future__ import annotations

import math
import time

import pytest

from physics.geometry_family import (
    GeometryFamilyCurves,
    _REFERENCE_ANGLES_DEG,
    _T_MAX_S,
    compute_geometry_family_curves,
)
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


# ---------------------------------------------------------------------------
# Dataclass shape
# ---------------------------------------------------------------------------
def test_returns_curves_dataclass():
    """compute_geometry_family_curves returns a GeometryFamilyCurves
    with exactly five reference curves."""
    curves = compute_geometry_family_curves(_merged_result())
    assert isinstance(curves, GeometryFamilyCurves)
    assert len(curves.reference_curves) == len(_REFERENCE_ANGLES_DEG)
    # Each entry is (alpha_deg, t_axis, I_peak_axis) triplet.
    for alpha_deg, t_axis, I_axis in curves.reference_curves:
        assert isinstance(alpha_deg, float)
        assert isinstance(t_axis, tuple)
        assert isinstance(I_axis, tuple)
        assert len(t_axis) == len(I_axis)
        assert len(t_axis) >= 2
    # Reference angles are exactly the documented set.
    actual_angles = tuple(a for a, _, _ in curves.reference_curves)
    assert actual_angles == _REFERENCE_ANGLES_DEG


def test_user_trajectory_in_dataclass():
    """The chain's trajectory_t / trajectory_I_peak series flow through
    to the dataclass for the highlighted current-scenario curve."""
    curves = compute_geometry_family_curves(_merged_result())
    assert curves.current_t_axis_s is not None
    assert curves.current_I_peak_wpcm2_axis is not None
    assert len(curves.current_t_axis_s) == len(curves.current_I_peak_wpcm2_axis)
    # Chain emits ~80 trajectory samples in canonical scenarios.
    assert len(curves.current_t_axis_s) > 10


# ---------------------------------------------------------------------------
# Trajectory math correctness
# ---------------------------------------------------------------------------
def test_alpha_0_matches_head_on_formula():
    """For α=0° (head-on), R(t) = R_detect − v_tgt·t exactly. The
    last sample (closest approach) should be at R_min."""
    from physics.geometry_family import _trajectory_R_of_t
    R_detect, v_tgt = 1500.0, 20.0
    # At t = (R_detect - 100)/v_tgt = 70 s, R should be 100 m.
    t_at_R_min = (R_detect - 100.0) / v_tgt
    R_at_end = _trajectory_R_of_t(R_detect, v_tgt, 0.0, t_at_R_min)
    assert R_at_end == pytest.approx(100.0, abs=1e-6)


def test_alpha_90_R_strictly_increases():
    """For α=90°, R(0) = R_detect and R(t>0) > R_detect (target only
    moves away from the gun)."""
    from physics.geometry_family import _trajectory_R_of_t
    R_detect, v_tgt = 1500.0, 20.0
    R0 = _trajectory_R_of_t(R_detect, v_tgt, 90.0, 0.0)
    R1 = _trajectory_R_of_t(R_detect, v_tgt, 90.0, 1.0)
    R10 = _trajectory_R_of_t(R_detect, v_tgt, 90.0, 10.0)
    assert R0 == pytest.approx(R_detect, rel=1e-9)
    assert R1 > R0
    assert R10 > R1


def test_closest_approach_matches_R_detect_sin_alpha():
    """For α between 0° and 90°, the trajectory's closest approach
    distance equals R_detect · sin(α). Pin this for {30°, 45°, 60°}."""
    from physics.geometry_family import _trajectory_R_of_t
    R_detect, v_tgt = 1500.0, 20.0
    for alpha_deg in (30.0, 45.0, 60.0):
        # Closest approach occurs at t* = R_detect · cos(α) / v_tgt.
        alpha_rad = math.radians(alpha_deg)
        t_star = R_detect * math.cos(alpha_rad) / v_tgt
        R_close = _trajectory_R_of_t(R_detect, v_tgt, alpha_deg, t_star)
        expected = R_detect * math.sin(alpha_rad)
        assert R_close == pytest.approx(expected, rel=1e-9), (
            f"α={alpha_deg}°: expected R_close={expected:.2f} m, got {R_close:.2f} m"
        )


def test_truncation_head_on_stops_at_R_min():
    """The α=0° curve must end at the moment R(t) = R_min (canonical
    head-on engagement-end)."""
    curves = compute_geometry_family_curves(_merged_result())
    head_on = next(
        (a, t, I) for a, t, I in curves.reference_curves if a == 0.0
    )
    _, t_axis, _ = head_on
    # Canonical: (1500-100)/20 = 70 s.
    assert t_axis[-1] == pytest.approx(70.0, rel=0.01)


def test_truncation_angled_stops_at_closest_approach():
    """Angled crossings (α ≥ arcsin(R_min/R_detect)) end at the
    closest-approach time, not at R_min (which they never reach)."""
    curves = compute_geometry_family_curves(_merged_result())
    # Canonical: arcsin(100/1500) ≈ 3.8° — every reference α ≥ 30° is
    # well above this threshold and stops at closest approach.
    R_detect, v_tgt = 1500.0, 20.0
    for alpha_deg in (30.0, 45.0, 60.0):
        entry = next(
            (a, t, I) for a, t, I in curves.reference_curves if a == alpha_deg
        )
        _, t_axis, _ = entry
        expected_t_end = R_detect * math.cos(math.radians(alpha_deg)) / v_tgt
        assert t_axis[-1] == pytest.approx(expected_t_end, rel=0.01), (
            f"α={alpha_deg}°: expected t_end={expected_t_end:.2f}, "
            f"got {t_axis[-1]:.2f}"
        )


def test_truncation_perpendicular_caps_at_t_max():
    """The α=90° curve runs for the full t_max (target never closes)."""
    curves = compute_geometry_family_curves(_merged_result())
    perp = next(
        (a, t, I) for a, t, I in curves.reference_curves if a == 90.0
    )
    _, t_axis, _ = perp
    assert t_axis[-1] == pytest.approx(_T_MAX_S, rel=1e-9)


# ---------------------------------------------------------------------------
# Physics correctness
# ---------------------------------------------------------------------------
def test_I_peak_climbs_for_head_on():
    """For α=0° (head-on closing), I_peak should INCREASE over time
    as the target gets closer."""
    curves = compute_geometry_family_curves(_merged_result())
    head_on = next(
        (a, t, I) for a, t, I in curves.reference_curves if a == 0.0
    )
    _, _, I_axis = head_on
    finite = [v for v in I_axis if not math.isnan(v) and v > 0]
    assert len(finite) >= 2
    assert finite[-1] > finite[0], (
        f"head-on I_peak should rise during engagement; got "
        f"first={finite[0]:.2g} last={finite[-1]:.2g}"
    )


def test_I_peak_falls_for_perpendicular():
    """For α=90° (perpendicular crossing), the target only gets
    farther, so I_peak should DECREASE over time."""
    curves = compute_geometry_family_curves(_merged_result())
    perp = next(
        (a, t, I) for a, t, I in curves.reference_curves if a == 90.0
    )
    _, _, I_axis = perp
    finite = [v for v in I_axis if not math.isnan(v) and v > 0]
    assert len(finite) >= 2
    assert finite[-1] < finite[0], (
        f"perpendicular I_peak should fall during engagement; got "
        f"first={finite[0]:.2g} last={finite[-1]:.2g}"
    )


def test_higher_alpha_lower_max_I_peak():
    """As α grows, the target gets less close → maximum I_peak should
    decrease across the family."""
    curves = compute_geometry_family_curves(_merged_result())
    max_per_angle = []
    for alpha_deg, _, I_axis in curves.reference_curves:
        finite = [v for v in I_axis if not math.isnan(v) and v > 0]
        max_per_angle.append((alpha_deg, max(finite) if finite else 0.0))
    # Pull α=0° max and α=60° max for the comparison.
    max_0 = next(m for a, m in max_per_angle if a == 0.0)
    max_60 = next(m for a, m in max_per_angle if a == 60.0)
    assert max_0 > max_60, (
        f"head-on peak ({max_0:.2g}) should exceed 60° peak ({max_60:.2g})"
    )


# ---------------------------------------------------------------------------
# Performance
# ---------------------------------------------------------------------------
def test_runs_well_under_one_second():
    """Wall-clock budget guard. ~150 cells of M4+M5+M7 should finish
    in ~750 ms; even with overhead, well under 1 s on local hardware.
    Busts if someone reintroduces M6 or M8 PDE per cell."""
    result = _merged_result()
    t0 = time.monotonic()
    compute_geometry_family_curves(result)
    elapsed = time.monotonic() - t0
    assert elapsed < 1.0, (
        f"sweep took {elapsed * 1000:.0f} ms — should be <1 s. Did "
        f"someone reintroduce M6 / M8 / full chain per cell?"
    )


# ---------------------------------------------------------------------------
# Defensive paths
# ---------------------------------------------------------------------------
def test_v1_inputs_rejected():
    """Plot P is v2-only (uses by_module + R_detect). Missing
    engagement_geometry → KeyError."""
    inputs = dict(C_UAS_1500M)
    for key in ("R_detect", "R_min", "engagement_geometry"):
        inputs.pop(key, None)
    result = run_full_chain(inputs)
    merged = {**inputs, **result}
    with pytest.raises(KeyError, match="v2.0"):
        compute_geometry_family_curves(merged)


def test_missing_by_module_rejected():
    """Without by_module (chain hasn't run), KeyError so the render
    pipeline can fall back gracefully."""
    inputs = _v2_inputs()
    with pytest.raises(KeyError, match="by_module"):
        compute_geometry_family_curves(inputs)


def test_missing_material_does_not_crash():
    """I_peak doesn't depend on material (unlike τ_BT), so a missing
    material should still produce valid curves. Same behaviour as
    cn2_family — verify it works."""
    merged = _merged_result()
    merged["material"] = "definitely_not_a_real_material"
    curves = compute_geometry_family_curves(merged)
    assert len(curves.reference_curves) == len(_REFERENCE_ANGLES_DEG)
    # All reference curves still produce values.
    for _, _, I_axis in curves.reference_curves:
        finite = [v for v in I_axis if not math.isnan(v) and v > 0]
        assert len(finite) >= 2


def test_constants_locked():
    """Reference angles are part of the contract; bumping them
    silently would shift the entire plot story."""
    assert _REFERENCE_ANGLES_DEG == (0.0, 30.0, 45.0, 60.0, 90.0)
    assert _T_MAX_S > 60.0  # At least handles canonical 70 s head-on.
