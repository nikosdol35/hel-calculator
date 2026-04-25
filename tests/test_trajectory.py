"""Tests for `physics/m_trajectory.py` — closed-form R(t) and t_dwell.

PR 2 of `docs/tracker_dwell_plan_2026-04-25.md`. Pure-math module
with no orchestrator coupling; the tests run against the closed
forms directly. SPEC v2.0 §3 M3.

Coverage:
  - validator behaviour (R_detect ≥ R_min, geometry enum, sign checks)
  - head-on closed forms (R(t), t_dwell)
  - lateral closed forms (R(t), t_dwell)
  - stationary degenerate case (v_tgt < 0.1 m/s → constant R, dwell = 60 s)
  - R(0) = R_detect for both geometries
  - R(t_dwell) = R_min for both geometries
"""
from __future__ import annotations

import math

import pytest


# ---------------------------------------------------------------------------
# Validator
# ---------------------------------------------------------------------------

def test_validator_accepts_canonical_head_on():
    from physics.m_trajectory import validate_trajectory_inputs
    # Should not raise.
    validate_trajectory_inputs(
        R_detect=1500.0, R_min=100.0, v_tgt=20.0,
        engagement_geometry="head_on",
    )


def test_validator_accepts_canonical_lateral():
    from physics.m_trajectory import validate_trajectory_inputs
    validate_trajectory_inputs(
        R_detect=1500.0, R_min=100.0, v_tgt=20.0,
        engagement_geometry="lateral",
    )


def test_validator_rejects_R_detect_below_R_min():
    """SPEC v2.0 §3 M3: R_detect must be ≥ R_min for both geometries."""
    from physics.m_trajectory import validate_trajectory_inputs
    with pytest.raises(ValueError, match="R_detect"):
        validate_trajectory_inputs(
            R_detect=50.0, R_min=100.0, v_tgt=20.0,
            engagement_geometry="head_on",
        )


def test_validator_rejects_unknown_geometry():
    from physics.m_trajectory import validate_trajectory_inputs
    with pytest.raises(ValueError, match="engagement_geometry"):
        validate_trajectory_inputs(
            R_detect=1500.0, R_min=100.0, v_tgt=20.0,
            engagement_geometry="diving",  # not in {head_on, lateral}
        )


def test_validator_rejects_negative_v_tgt():
    from physics.m_trajectory import validate_trajectory_inputs
    with pytest.raises(ValueError, match="v_tgt"):
        validate_trajectory_inputs(
            R_detect=1500.0, R_min=100.0, v_tgt=-5.0,
            engagement_geometry="head_on",
        )


def test_validator_rejects_zero_R_detect():
    from physics.m_trajectory import validate_trajectory_inputs
    with pytest.raises(ValueError, match="R_detect"):
        validate_trajectory_inputs(
            R_detect=0.0, R_min=100.0, v_tgt=20.0,
            engagement_geometry="head_on",
        )


# ---------------------------------------------------------------------------
# Head-on geometry
# ---------------------------------------------------------------------------

def test_head_on_dwell_canonical():
    """t_dwell = (R_detect − R_min) / v_tgt.

    Canonical: R_detect=1500, R_min=100, v_tgt=20 → 70 s."""
    from physics.m_trajectory import available_dwell
    t = available_dwell(1500.0, 100.0, 20.0, "head_on")
    assert t == pytest.approx(70.0, rel=1e-12)


def test_head_on_R_at_t_zero_is_R_detect():
    """R(0) = R_detect by definition."""
    from physics.m_trajectory import trajectory_R_of_t
    R = trajectory_R_of_t(1500.0, 100.0, 20.0, "head_on")
    assert R(0.0) == pytest.approx(1500.0, rel=1e-12)


def test_head_on_R_at_t_dwell_is_R_min():
    """R(t_dwell) = R_min by construction."""
    from physics.m_trajectory import available_dwell, trajectory_R_of_t
    R = trajectory_R_of_t(1500.0, 100.0, 20.0, "head_on")
    t_dwell = available_dwell(1500.0, 100.0, 20.0, "head_on")
    assert R(t_dwell) == pytest.approx(100.0, rel=1e-12)


def test_head_on_R_linear_in_time():
    """R(t) = R_detect − v_tgt · t — strictly linear closure."""
    from physics.m_trajectory import trajectory_R_of_t
    R = trajectory_R_of_t(1500.0, 100.0, 20.0, "head_on")
    # At halfway through dwell (35 s): R = 1500 − 20·35 = 800.
    assert R(35.0) == pytest.approx(800.0, rel=1e-12)


def test_head_on_dwell_scales_with_velocity():
    """Doubling v_tgt halves t_dwell."""
    from physics.m_trajectory import available_dwell
    t1 = available_dwell(1500.0, 100.0, 20.0, "head_on")
    t2 = available_dwell(1500.0, 100.0, 40.0, "head_on")
    assert t2 == pytest.approx(t1 / 2.0, rel=1e-12)


# ---------------------------------------------------------------------------
# Lateral geometry
# ---------------------------------------------------------------------------

def test_lateral_dwell_canonical():
    """t_dwell = √(R_detect² − R_min²) / v_tgt.

    Canonical: R_detect=1500, R_min=100, v_tgt=20 →
    √(2_250_000 − 10_000) / 20 = √2_240_000 / 20 ≈ 1496.66 / 20 ≈ 74.83 s."""
    from physics.m_trajectory import available_dwell
    t = available_dwell(1500.0, 100.0, 20.0, "lateral")
    expected = math.sqrt(1500.0**2 - 100.0**2) / 20.0
    assert t == pytest.approx(expected, rel=1e-12)


def test_lateral_R_at_t_zero_is_R_detect():
    from physics.m_trajectory import trajectory_R_of_t
    R = trajectory_R_of_t(1500.0, 100.0, 20.0, "lateral")
    assert R(0.0) == pytest.approx(1500.0, rel=1e-12)


def test_lateral_R_at_t_dwell_is_R_min():
    """R(t_dwell) = R_min — closest approach by definition."""
    from physics.m_trajectory import available_dwell, trajectory_R_of_t
    R = trajectory_R_of_t(1500.0, 100.0, 20.0, "lateral")
    t_dwell = available_dwell(1500.0, 100.0, 20.0, "lateral")
    assert R(t_dwell) == pytest.approx(100.0, rel=1e-9)


def test_lateral_R_monotonically_decreasing():
    """For inbound lateral motion, R(t) decreases monotonically from
    R_detect to R_min over [0, t_dwell]."""
    from physics.m_trajectory import available_dwell, trajectory_R_of_t
    R = trajectory_R_of_t(1500.0, 100.0, 20.0, "lateral")
    t_dwell = available_dwell(1500.0, 100.0, 20.0, "lateral")
    samples = [R(t_dwell * frac) for frac in (0.0, 0.25, 0.5, 0.75, 1.0)]
    for prev, curr in zip(samples, samples[1:]):
        assert curr <= prev + 1e-9


def test_lateral_dwell_longer_than_head_on_for_same_inputs():
    """Lateral pass takes longer than head-on closure for the same
    detection / standoff / velocity (the trajectory is the slant
    distance, not the axial component)."""
    from physics.m_trajectory import available_dwell
    t_head = available_dwell(1500.0, 100.0, 20.0, "head_on")
    t_lat = available_dwell(1500.0, 100.0, 20.0, "lateral")
    assert t_lat > t_head


# ---------------------------------------------------------------------------
# Stationary edge case
# ---------------------------------------------------------------------------

def test_is_stationary_threshold():
    from physics.m_trajectory import (
        STATIONARY_THRESHOLD_MPS, is_stationary,
    )
    assert is_stationary(0.0)
    assert is_stationary(STATIONARY_THRESHOLD_MPS - 1e-6)
    assert not is_stationary(STATIONARY_THRESHOLD_MPS)
    assert not is_stationary(10.0)


def test_stationary_dwell_returns_timeout():
    """v_tgt = 0 → dwell clamps to STATIONARY_DWELL_S (60 s)."""
    from physics.m_trajectory import (
        STATIONARY_DWELL_S, available_dwell,
    )
    t = available_dwell(500.0, 100.0, 0.0, "head_on")
    assert t == STATIONARY_DWELL_S


def test_stationary_R_constant():
    """Stationary R(t) is the constant R_detect for any t."""
    from physics.m_trajectory import trajectory_R_of_t
    R = trajectory_R_of_t(500.0, 100.0, 0.05, "head_on")
    assert R(0.0) == pytest.approx(500.0)
    assert R(30.0) == pytest.approx(500.0)
    assert R(120.0) == pytest.approx(500.0)


def test_stationary_dwell_is_geometry_independent():
    """For a stationary target the dwell window is the same in either
    geometry — both reduce to a constant-R single-point analysis."""
    from physics.m_trajectory import available_dwell
    t_h = available_dwell(500.0, 100.0, 0.0, "head_on")
    t_l = available_dwell(500.0, 100.0, 0.0, "lateral")
    assert t_h == t_l


# ---------------------------------------------------------------------------
# R_at_dwell_end helper
# ---------------------------------------------------------------------------

def test_R_at_dwell_end_moving_target():
    """For a moving target, the engagement ends at R_min for both
    geometries by construction."""
    from physics.m_trajectory import R_at_dwell_end
    assert R_at_dwell_end(R_min=100.0, v_tgt=20.0) == 100.0
    assert R_at_dwell_end(R_min=50.0, v_tgt=5.0) == 50.0


def test_R_at_dwell_end_stationary_returns_R_detect():
    """Stationary target — engagement runs at constant R, so the
    'end' range is the same as the start (R_detect)."""
    from physics.m_trajectory import R_at_dwell_end
    assert R_at_dwell_end(R_min=100.0, v_tgt=0.0, R_detect=500.0) == 500.0


def test_R_at_dwell_end_stationary_without_R_detect_raises():
    """The stationary case is unrepresentable without the initial
    range — caller must supply R_detect."""
    from physics.m_trajectory import R_at_dwell_end
    with pytest.raises(ValueError, match="R_detect"):
        R_at_dwell_end(R_min=100.0, v_tgt=0.0)


# ---------------------------------------------------------------------------
# Sanity: dwell formulas converge at R_min → R_detect (corner case)
# ---------------------------------------------------------------------------

def test_dwell_zero_when_R_detect_equals_R_min():
    """At the engagement-end boundary the dwell window collapses to 0
    seconds. The validator rejects this in practice (R_detect = R_min
    is degenerate), but the formulas themselves should produce 0
    rather than a NaN — important for edge-case robustness inside
    sweep loops."""
    from physics.m_trajectory import available_dwell
    t_h = available_dwell(100.0, 100.0, 20.0, "head_on")
    t_l = available_dwell(100.0, 100.0, 20.0, "lateral")
    assert t_h == 0.0
    assert t_l == 0.0


def test_export_surface():
    """Public symbols match the module-level __all__ tuple."""
    from physics import m_trajectory
    expected = {
        "EngagementGeometry", "STATIONARY_THRESHOLD_MPS",
        "STATIONARY_DWELL_S", "available_dwell", "is_stationary",
        "R_at_dwell_end", "trajectory_R_of_t",
        "validate_trajectory_inputs",
    }
    assert set(m_trajectory.__all__) == expected
