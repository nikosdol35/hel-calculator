"""Engagement-scheduler for the Swarm Analyzer.

Three target-selection strategies (the orchestrator picks one for
the whole simulation; can't switch mid-run):

  * **earliest_leak_first** — pick the drone with the smallest
    time-to-leak. Tactically correct default: you go after whichever
    target is about to breach your defended zone next.
  * **closest_first** — pick the drone with the smallest current
    range. Simple, intuitive, but suboptimal when a slow distant
    drone is easier than a fast close one.
  * **easiest_kill_first** — pick the drone with the smallest
    estimated τ_BT at its current range. Maximizes "kills per
    second" but can let the most threatening one keep closing.

All three are deterministic — ties resolved by ``(t_leak, range, id)``
or ``(range, id)`` or ``(tau_estimate, id)`` lex order. Same scenario
always yields the same target choice, which makes the simulation
hashable for golden tests.

Pure module — no Streamlit imports.
"""
from __future__ import annotations

import math
from typing import Callable

from physics.swarm_kinematics import (
    closing_rate_mps,
    range_to_bd_m,
    time_to_leak_s,
)


SchedulerFn = Callable[..., int | None]


# ---------------------------------------------------------------------------
# Drone-state interface — the scheduler only cares about a tiny slice
# of each drone's state. We pass dicts (not the full SimDrone class
# from the orchestrator) so the scheduler can be tested in isolation.
# ---------------------------------------------------------------------------

def _alive_engageable(drone_states: list[dict]) -> list[dict]:
    """Drones that are currently candidates for engagement: state is
    DETECTED or ENGAGED (re-engageable). Filters out WAITING (not yet
    detected), DESTROYED, LEAKED, TIMEOUT."""
    return [
        d for d in drone_states
        if d["state"] in ("DETECTED", "ENGAGED")
    ]


# ---------------------------------------------------------------------------
# Strategy 1 — earliest-leak-first (default, tactically correct)
# ---------------------------------------------------------------------------

def pick_earliest_leak_first(
    drone_states: list[dict],
    R_min_m: float,
) -> int | None:
    """Pick the drone with the smallest time-to-leak.

    A drone with closing_rate ≤ 0 (perpendicular or receding) has
    t_leak = +∞. If ALL alive drones are receding, fall back to
    closest-first so the BD still has something to engage (the team
    can see the receding drones aren't dangerous in the playback).

    Tie-breaks: smaller range, then smaller drone_id.
    """
    candidates = _alive_engageable(drone_states)
    if not candidates:
        return None

    # Compute t_leak per drone.
    keyed: list[tuple[float, float, int, int]] = []
    for d in candidates:
        t_leak = time_to_leak_s(d["position_m"], d["velocity_mps"], R_min_m)
        rng = range_to_bd_m(d["position_m"])
        keyed.append((t_leak, rng, d["drone_id"], d["drone_id"]))

    # If all candidates have t_leak == +inf (no one is closing), fall
    # back to closest-first so the BD still acts.
    if all(math.isinf(k[0]) for k in keyed):
        return pick_closest_first(drone_states)

    # Smallest (t_leak, range, id).
    best = min(keyed)
    return best[2]


# ---------------------------------------------------------------------------
# Strategy 2 — closest-first
# ---------------------------------------------------------------------------

def pick_closest_first(drone_states: list[dict]) -> int | None:
    """Pick the drone with the smallest current range.

    Tie-break: smaller drone_id.
    """
    candidates = _alive_engageable(drone_states)
    if not candidates:
        return None
    keyed = [
        (range_to_bd_m(d["position_m"]), d["drone_id"])
        for d in candidates
    ]
    best = min(keyed)
    return best[1]


# ---------------------------------------------------------------------------
# Strategy 3 — easiest-kill-first
# ---------------------------------------------------------------------------

def pick_easiest_kill_first(
    drone_states: list[dict],
    estimate_tau_BT_s: Callable[[dict], float],
) -> int | None:
    """Pick the drone whose estimated τ_BT (lumped-mass × 0.83) at
    its current range is smallest. ``estimate_tau_BT_s(drone)``
    must return a float; the orchestrator wires this with a closure
    over the lightweight HEL chain.

    Tie-break: smaller drone_id.
    """
    candidates = _alive_engageable(drone_states)
    if not candidates:
        return None
    keyed = [(estimate_tau_BT_s(d), d["drone_id"]) for d in candidates]
    best = min(keyed)
    return best[1]


# ---------------------------------------------------------------------------
# Top-level dispatcher
# ---------------------------------------------------------------------------

def pick_target(
    strategy: str,
    drone_states: list[dict],
    R_min_m: float,
    estimate_tau_BT_s: Callable[[dict], float] | None = None,
) -> int | None:
    """Top-level dispatcher used by the orchestrator each timestep
    when BD is IDLE. Returns the drone_id of the next target, or
    None if no candidates remain (sim ends)."""
    if strategy == "earliest_leak_first":
        return pick_earliest_leak_first(drone_states, R_min_m)
    if strategy == "closest_first":
        return pick_closest_first(drone_states)
    if strategy == "easiest_kill_first":
        if estimate_tau_BT_s is None:
            raise ValueError(
                "easiest_kill_first requires estimate_tau_BT_s callback"
            )
        return pick_easiest_kill_first(drone_states, estimate_tau_BT_s)
    raise ValueError(f"unknown strategy {strategy!r}")


__all__ = [
    "pick_target",
    "pick_earliest_leak_first",
    "pick_closest_first",
    "pick_easiest_kill_first",
]
