"""2D drone trajectory math + beam-director slew kinematics.

Two pure-math layers consumed by the swarm orchestrator:

  * **Drone trajectories** — straight-line constant-velocity in 2D
    with the BD at the origin. ``position_at(t)``, ``range_at(t)``,
    ``bearing_at(t)``, ``closing_rate(t)``, ``time_to_leak(t)``.
  * **BD slew time** — trapezoidal/triangular regime selector with
    shortest-arc azimuth slew. Standard textbook treatment per
    Hilkert (2008), *Inertially Stabilized Platform Technology*.

Both layers are pure numeric functions — easy to test in isolation
(see ``tests/test_swarm_kinematics.py``).
"""
from __future__ import annotations

import math


# ---------------------------------------------------------------------------
# Drone trajectory math (2D, BD at origin)
# ---------------------------------------------------------------------------

def position_at(
    initial_position_m: tuple[float, float],
    velocity_mps: tuple[float, float],
    t_s: float,
) -> tuple[float, float]:
    """Drone position at time t. Straight-line constant-velocity."""
    x0, y0 = initial_position_m
    vx, vy = velocity_mps
    return (x0 + vx * t_s, y0 + vy * t_s)


def range_to_bd_m(position_m: tuple[float, float]) -> float:
    """Slant range from BD (origin) to drone in metres."""
    x, y = position_m
    return math.sqrt(x * x + y * y)


def bearing_to_drone_deg(position_m: tuple[float, float]) -> float:
    """Bearing from BD (origin) to drone, in degrees [-180, 180].

    Coordinate convention: 0° along +x (east), 90° along +y (north).
    Matches Plotly's natural azimuth orientation for the playback
    map. The BD slews in this same azimuth frame.
    """
    x, y = position_m
    return math.degrees(math.atan2(y, x))


def closing_rate_mps(
    position_m: tuple[float, float],
    velocity_mps: tuple[float, float],
) -> float:
    """Instantaneous range-closing rate (m/s, positive when range
    is shrinking). The component of the drone's velocity vector
    projected onto the drone-to-BD direction.

    Formula: -1/r · (x·vx + y·vy). If r → 0 (drone exactly at BD),
    return 0 to avoid division-by-zero (drone has already leaked).
    """
    r = range_to_bd_m(position_m)
    if r <= 0:
        return 0.0
    x, y = position_m
    vx, vy = velocity_mps
    return -(x * vx + y * vy) / r


def time_to_leak_s(
    position_m: tuple[float, float],
    velocity_mps: tuple[float, float],
    R_min_m: float,
) -> float:
    """Time until the drone's range crosses ``R_min`` from outside.

    Returns +∞ when:
      - the drone is moving perpendicular or away (closing_rate ≤ 0)
      - the drone is already inside R_min (already-leaked drones
        are handled by the simulation loop, not this function)

    Otherwise: ``(range - R_min) / closing_rate`` — the linearization
    is exact along a straight-line constant-velocity trajectory in
    the limit where the drone is heading directly at the BD; for
    other angles it's a slight under-estimate (the drone will reach
    closest approach before R_min crossing if it's offset). Acceptable
    for scheduler tie-breaking (the scheduler runs every timestep
    so the estimate refreshes continuously).
    """
    r = range_to_bd_m(position_m)
    if r <= R_min_m:
        return 0.0  # already inside; sim will mark LEAK on next step
    closing = closing_rate_mps(position_m, velocity_mps)
    if closing <= 0:
        return float("inf")
    return (r - R_min_m) / closing


# ---------------------------------------------------------------------------
# Beam-director slew time (azimuth-only, 2D)
# ---------------------------------------------------------------------------

def shortest_arc_deg(bearing_from_deg: float, bearing_to_deg: float) -> float:
    """Smallest angular distance (degrees, always non-negative)
    between two bearings. Picks the shorter direction around the
    circle: e.g. 350° → 10° is 20°, not 340°.
    """
    diff = (bearing_to_deg - bearing_from_deg) % 360.0
    if diff > 180.0:
        diff = 360.0 - diff
    return diff


def slew_time_s(
    delta_theta_deg: float,
    max_rate_dps: float,
    max_accel_dps2: float,
) -> float:
    """Time to slew through ``delta_theta_deg`` under a trapezoidal
    velocity profile (or triangular if Δθ is small enough to never
    reach max rate). Pure kinematics — no settling or reacquire time
    here; ``total_switch_time_s`` adds those.

    Trapezoidal regime (large slew):
      t_accel = max_rate / max_accel
      θ_accel = ½ · max_accel · t_accel²    (one accel phase)
      θ_cruise = Δθ - 2·θ_accel
      t_cruise = θ_cruise / max_rate
      t_total = 2·t_accel + t_cruise

    Triangular regime (Δθ < 2·θ_accel — slew finishes accelerating
    + decelerating, never reaches max rate):
      t_total = 2·sqrt(Δθ / max_accel)

    Source: Hilkert 2008 §3.2. Handles the Δθ ≈ 0 case (returns 0).
    """
    if delta_theta_deg <= 0:
        return 0.0
    if max_rate_dps <= 0 or max_accel_dps2 <= 0:
        raise ValueError("max_rate and max_accel must be positive")

    t_accel = max_rate_dps / max_accel_dps2
    theta_accel = 0.5 * max_accel_dps2 * t_accel * t_accel

    if delta_theta_deg < 2.0 * theta_accel:
        # Triangular: never reaches max rate.
        return 2.0 * math.sqrt(delta_theta_deg / max_accel_dps2)
    # Trapezoidal: accel → cruise at max rate → decel.
    cruise_theta = delta_theta_deg - 2.0 * theta_accel
    t_cruise = cruise_theta / max_rate_dps
    return 2.0 * t_accel + t_cruise


def total_switch_time_s(
    bearing_from_deg: float,
    bearing_to_deg: float,
    max_rate_dps: float,
    max_accel_dps2: float,
    settling_time_s: float,
    reacquire_time_s: float,
) -> float:
    """Full target-to-target switch time: shortest-arc slew +
    settling + reacquire. This is the value the orchestrator uses to
    book "BD blackout" while moving from one target to the next."""
    delta = shortest_arc_deg(bearing_from_deg, bearing_to_deg)
    t_slew = slew_time_s(delta, max_rate_dps, max_accel_dps2)
    return t_slew + settling_time_s + reacquire_time_s


__all__ = [
    "position_at",
    "range_to_bd_m",
    "bearing_to_drone_deg",
    "closing_rate_mps",
    "time_to_leak_s",
    "shortest_arc_deg",
    "slew_time_s",
    "total_switch_time_s",
]
