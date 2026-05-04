"""Layer 2 verification — scheduler correctness + tie-breaking.

The plan §5 Layer 2: pin the three target-selection strategies and
their deterministic tie-breaking rules. Same scenario must always
yield the same target choice — hashed scenarios → identical
simulations → reliable golden tests.
"""
from __future__ import annotations

import pytest

from physics.swarm_scheduler import (
    pick_closest_first,
    pick_earliest_leak_first,
    pick_easiest_kill_first,
    pick_target,
)


def _drone_state(
    drone_id: int,
    pos: tuple[float, float],
    vel: tuple[float, float],
    state: str = "DETECTED",
) -> dict:
    """Minimal drone-state dict the scheduler needs."""
    return {
        "drone_id": drone_id,
        "position_m": pos,
        "velocity_mps": vel,
        "state": state,
    }


# ---------------------------------------------------------------------------
# Earliest-leak-first
# ---------------------------------------------------------------------------

def test_earliest_leak_picks_smallest_t_leak():
    """3 drones at 1/2/3 km, all closing at 30 m/s — drone @ 1 km
    has the smallest t_leak."""
    drones = [
        _drone_state(0, (2000.0, 0.0), (-30.0, 0.0)),
        _drone_state(1, (1000.0, 0.0), (-30.0, 0.0)),
        _drone_state(2, (3000.0, 0.0), (-30.0, 0.0)),
    ]
    assert pick_earliest_leak_first(drones, R_min_m=100.0) == 1


def test_earliest_leak_prioritises_fast_closer():
    """Drone A: 1 km @ 10 m/s closing → t_leak ≈ 90 s.
    Drone B: 2 km @ 100 m/s closing → t_leak ≈ 19 s.
    B should be picked even though A is closer."""
    drones = [
        _drone_state(0, (1000.0, 0.0), (-10.0, 0.0)),
        _drone_state(1, (2000.0, 0.0), (-100.0, 0.0)),
    ]
    assert pick_earliest_leak_first(drones, R_min_m=100.0) == 1


def test_earliest_leak_falls_back_to_closest_when_all_receding():
    """If every drone is moving away, the scheduler should still
    return SOMETHING (smallest current range) so the BD acts and the
    team can SEE in the playback that the receding drones aren't
    dangerous."""
    drones = [
        _drone_state(0, (1000.0, 0.0), (30.0, 0.0)),    # receding
        _drone_state(1, (500.0, 0.0), (30.0, 0.0)),     # closer, also receding
    ]
    assert pick_earliest_leak_first(drones, R_min_m=100.0) == 1


def test_earliest_leak_skips_destroyed_and_leaked():
    """DESTROYED / LEAKED drones aren't candidates."""
    drones = [
        _drone_state(0, (500.0, 0.0), (-30.0, 0.0), state="DESTROYED"),
        _drone_state(1, (1000.0, 0.0), (-30.0, 0.0), state="LEAKED"),
        _drone_state(2, (1500.0, 0.0), (-30.0, 0.0), state="DETECTED"),
    ]
    assert pick_earliest_leak_first(drones, R_min_m=100.0) == 2


def test_earliest_leak_skips_waiting_drones():
    """Drones in WAITING state (not yet inside R_detect_max) are
    not candidates either."""
    drones = [
        _drone_state(0, (500.0, 0.0), (-30.0, 0.0), state="WAITING"),
        _drone_state(1, (1500.0, 0.0), (-30.0, 0.0), state="DETECTED"),
    ]
    assert pick_earliest_leak_first(drones, R_min_m=100.0) == 1


def test_earliest_leak_returns_none_when_no_candidates():
    """All drones DESTROYED → scheduler returns None → sim ends."""
    drones = [
        _drone_state(0, (500.0, 0.0), (-30.0, 0.0), state="DESTROYED"),
    ]
    assert pick_earliest_leak_first(drones, R_min_m=100.0) is None


# ---------------------------------------------------------------------------
# Closest-first
# ---------------------------------------------------------------------------

def test_closest_first_ignores_closing_rate():
    """A close-but-receding drone is still 'closest'."""
    drones = [
        _drone_state(0, (500.0, 0.0), (30.0, 0.0)),     # close, receding
        _drone_state(1, (2000.0, 0.0), (-30.0, 0.0)),   # far, closing
    ]
    assert pick_closest_first(drones) == 0


# ---------------------------------------------------------------------------
# Easiest-kill-first
# ---------------------------------------------------------------------------

def test_easiest_kill_first_uses_estimate():
    """The strategy is parameterized by an estimate_tau_BT_s callback.
    The orchestrator wires it; here we test with a fake closure."""
    drones = [
        _drone_state(0, (1000.0, 0.0), (-30.0, 0.0)),
        _drone_state(1, (1000.0, 0.0), (-30.0, 0.0)),
        _drone_state(2, (1000.0, 0.0), (-30.0, 0.0)),
    ]
    # Fake estimator: drone_id 1 has the smallest τ_BT.
    fake_tau = {0: 5.0, 1: 2.0, 2: 4.0}
    pick = pick_easiest_kill_first(
        drones, estimate_tau_BT_s=lambda d: fake_tau[d["drone_id"]]
    )
    assert pick == 1


# ---------------------------------------------------------------------------
# Tie-breaking — determinism
# ---------------------------------------------------------------------------

def test_tie_break_smallest_id_wins():
    """Two drones with identical (t_leak, range) — smaller id wins."""
    drones = [
        _drone_state(5, (1000.0, 0.0), (-30.0, 0.0)),
        _drone_state(2, (1000.0, 0.0), (-30.0, 0.0)),
    ]
    assert pick_earliest_leak_first(drones, R_min_m=100.0) == 2


def test_tie_break_is_consistent_across_calls():
    """Identical inputs → identical output every call (no random
    ordering creeping in via dict iteration)."""
    drones = [
        _drone_state(7, (1000.0, 0.0), (-30.0, 0.0)),
        _drone_state(3, (1000.0, 0.0), (-30.0, 0.0)),
    ]
    picks = [pick_earliest_leak_first(drones, 100.0) for _ in range(20)]
    assert all(p == 3 for p in picks)


# ---------------------------------------------------------------------------
# Top-level dispatcher
# ---------------------------------------------------------------------------

def test_pick_target_dispatches_to_right_strategy():
    drones = [
        _drone_state(0, (500.0, 0.0), (30.0, 0.0)),     # close, receding
        _drone_state(1, (2000.0, 0.0), (-30.0, 0.0)),   # far, closing
    ]
    # earliest_leak: closing drone wins (#1).
    assert pick_target("earliest_leak_first", drones, 100.0) == 1
    # closest_first: closer drone wins (#0).
    assert pick_target("closest_first", drones, 100.0) == 0


def test_pick_target_unknown_strategy_raises():
    with pytest.raises(ValueError, match="unknown strategy"):
        pick_target("magic_strategy", [], 100.0)


def test_easiest_kill_first_requires_estimator():
    with pytest.raises(ValueError, match="requires estimate_tau_BT_s"):
        pick_target("easiest_kill_first", [], 100.0)
