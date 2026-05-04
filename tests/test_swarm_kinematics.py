"""Layer 1 verification — unit tests on the new swarm-kinematics math.

Catches obvious math bugs in the slew-time regime selector, the
shortest-arc helper, and the closing-rate / time-to-leak formulas.
All test cases hand-computable so the expected values are
auditable on a calculator.

Per the plan §5 Layer 1.
"""
from __future__ import annotations

import math

import pytest

from physics.swarm_kinematics import (
    bearing_to_drone_deg,
    closing_rate_mps,
    position_at,
    range_to_bd_m,
    shortest_arc_deg,
    slew_time_s,
    time_to_leak_s,
    total_switch_time_s,
)


# ---------------------------------------------------------------------------
# Slew time — trapezoidal vs triangular regime
# ---------------------------------------------------------------------------

def test_slew_time_trapezoidal_60deg():
    """60° slew, 60 deg/s rate, 120 deg/s² accel.

    Hand-calc:
      t_accel = 60/120 = 0.5 s
      θ_accel = ½·120·0.5² = 15° per accel phase, 30° total
      Δθ - 2·θ_accel = 60 - 30 = 30° cruise distance
      t_cruise = 30/60 = 0.5 s
      Total = 2·0.5 + 0.5 = 1.5 s
    """
    assert slew_time_s(60.0, 60.0, 120.0) == pytest.approx(1.5, rel=1e-9)


def test_slew_time_triangular_10deg():
    """10° slew with same kinematics — triangular regime (10 <
    2·θ_accel = 30). Hand-calc: 2·sqrt(10/120) ≈ 0.5774 s."""
    expected = 2.0 * math.sqrt(10.0 / 120.0)
    assert slew_time_s(10.0, 60.0, 120.0) == pytest.approx(expected, rel=1e-9)


def test_slew_time_zero_delta_returns_zero():
    """No slew → no time."""
    assert slew_time_s(0.0, 60.0, 120.0) == 0.0


def test_slew_time_threshold_between_regimes():
    """At Δθ = 2·θ_accel = 30° both formulas should agree
    (continuity at the regime boundary)."""
    # θ_accel = 15° → boundary at 30°.
    triangular = 2.0 * math.sqrt(30.0 / 120.0)
    trapezoidal = slew_time_s(30.0, 60.0, 120.0)
    assert trapezoidal == pytest.approx(triangular, rel=1e-9)


def test_slew_time_rejects_bad_kinematics():
    """Non-positive rate or accel must raise ValueError."""
    with pytest.raises(ValueError):
        slew_time_s(60.0, 0.0, 120.0)
    with pytest.raises(ValueError):
        slew_time_s(60.0, 60.0, -1.0)


# ---------------------------------------------------------------------------
# Shortest-arc helper
# ---------------------------------------------------------------------------

def test_shortest_arc_basic():
    assert shortest_arc_deg(0.0, 90.0) == pytest.approx(90.0)
    assert shortest_arc_deg(0.0, 180.0) == pytest.approx(180.0)
    assert shortest_arc_deg(10.0, 30.0) == pytest.approx(20.0)


def test_shortest_arc_wraps_through_zero():
    """350° to 10° = 20° (not 340°)."""
    assert shortest_arc_deg(350.0, 10.0) == pytest.approx(20.0)
    assert shortest_arc_deg(10.0, 350.0) == pytest.approx(20.0)


def test_shortest_arc_handles_negative_bearings():
    """Bearings can be negative (atan2 returns [-180, 180])."""
    assert shortest_arc_deg(-10.0, 10.0) == pytest.approx(20.0)
    assert shortest_arc_deg(170.0, -170.0) == pytest.approx(20.0)


def test_shortest_arc_max_is_180():
    """No arc is longer than 180° (we always pick the short way)."""
    assert shortest_arc_deg(0.0, 200.0) == pytest.approx(160.0)


# ---------------------------------------------------------------------------
# Total switch time = slew + settling + reacquire
# ---------------------------------------------------------------------------

def test_total_switch_time_canonical():
    """30° switch with default kinematics: 0.5774 s slew (triangular)
    + 0.2 s settle + 0.15 s reacquire ≈ 0.93 s."""
    t = total_switch_time_s(
        bearing_from_deg=0.0,
        bearing_to_deg=30.0,
        max_rate_dps=60.0,
        max_accel_dps2=120.0,
        settling_time_s=0.2,
        reacquire_time_s=0.15,
    )
    expected = 2.0 * math.sqrt(30.0 / 120.0) + 0.2 + 0.15
    assert t == pytest.approx(expected, rel=1e-9)


def test_total_switch_time_uses_shortest_arc():
    """Switch from 350° to 10° should use 20° arc, not 340°."""
    t_short = total_switch_time_s(350.0, 10.0, 60.0, 120.0, 0.0, 0.0)
    t_long_calc = slew_time_s(340.0, 60.0, 120.0)
    assert t_short < t_long_calc


# ---------------------------------------------------------------------------
# Position / range / bearing
# ---------------------------------------------------------------------------

def test_position_at_constant_velocity():
    pos = position_at((1000.0, 0.0), (-30.0, 0.0), 5.0)
    assert pos == pytest.approx((850.0, 0.0))


def test_range_to_bd_basic():
    assert range_to_bd_m((1000.0, 0.0)) == pytest.approx(1000.0)
    assert range_to_bd_m((300.0, 400.0)) == pytest.approx(500.0)


def test_bearing_to_drone_axes():
    assert bearing_to_drone_deg((1.0, 0.0)) == pytest.approx(0.0)
    assert bearing_to_drone_deg((0.0, 1.0)) == pytest.approx(90.0)
    assert bearing_to_drone_deg((-1.0, 0.0)) == pytest.approx(180.0)
    assert bearing_to_drone_deg((0.0, -1.0)) == pytest.approx(-90.0)


# ---------------------------------------------------------------------------
# Closing rate
# ---------------------------------------------------------------------------

def test_closing_rate_head_on_at_30mps():
    """Drone at (1 km, 0) heading (-30, 0) m/s → +30 m/s closing."""
    assert closing_rate_mps((1000.0, 0.0), (-30.0, 0.0)) == pytest.approx(30.0)


def test_closing_rate_perpendicular_is_zero():
    """Drone at (1 km, 0) moving (0, 30) m/s — pure cross-track,
    closing rate = 0 (range is at its instantaneous minimum)."""
    assert closing_rate_mps((1000.0, 0.0), (0.0, 30.0)) == pytest.approx(0.0, abs=1e-9)


def test_closing_rate_receding_is_negative():
    """Drone at (1 km, 0) moving (+30, 0) m/s → -30 m/s closing
    (range is growing)."""
    assert closing_rate_mps((1000.0, 0.0), (30.0, 0.0)) == pytest.approx(-30.0)


def test_closing_rate_zero_range_returns_zero():
    """Drone exactly at BD origin → guard against division-by-zero."""
    assert closing_rate_mps((0.0, 0.0), (10.0, 0.0)) == 0.0


# ---------------------------------------------------------------------------
# Time-to-leak
# ---------------------------------------------------------------------------

def test_time_to_leak_basic():
    """3 km drone at +30 m/s closing, R_min 100 m → (3000-100)/30 ≈ 96.67 s."""
    t = time_to_leak_s((3000.0, 0.0), (-30.0, 0.0), 100.0)
    assert t == pytest.approx(96.667, rel=1e-3)


def test_time_to_leak_perpendicular_is_inf():
    """Pure perpendicular motion never leaks."""
    assert time_to_leak_s((1000.0, 0.0), (0.0, 30.0), 100.0) == float("inf")


def test_time_to_leak_receding_is_inf():
    """Receding drone never leaks via this trajectory."""
    assert time_to_leak_s((1000.0, 0.0), (30.0, 0.0), 100.0) == float("inf")


def test_time_to_leak_already_inside_R_min_is_zero():
    """Drone already inside R_min gets 0 (sim will mark LEAK on
    the very next step)."""
    assert time_to_leak_s((50.0, 0.0), (-10.0, 0.0), 100.0) == 0.0


# ---------------------------------------------------------------------------
# Layer 6 — hand-calculable cross-check (operator's "trust handle")
# ---------------------------------------------------------------------------
def test_layer6_handcalc_slew_time_matches_textbook():
    """A 90° slew at 60 deg/s rate / 120 deg/s² accel:
       t_accel = 0.5 s, θ_accel = 15°, cruise = 60°, t_cruise = 1.0 s
       Total slew = 2·0.5 + 1.0 = 2.0 s
    Operator can verify on a piece of paper. If this test ever fails
    the slew-kinematics module itself has a bug."""
    assert slew_time_s(90.0, 60.0, 120.0) == pytest.approx(2.0, rel=1e-9)
