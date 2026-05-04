"""Tests for the swarm scenario data model + JSON round-trip.

Layer 4b in the plan: scenario JSON serialization must be lossless
so golden scenarios stored as JSON can be deserialized identically
across runs / refactors.
"""
from __future__ import annotations

import pytest

from physics.swarm_scenario import (
    BDKinematics,
    Drone,
    SCENARIO_SCHEMA_VERSION,
    SwarmScenario,
)


def _hel_inputs_canonical() -> dict:
    """A minimal-but-valid HEL inputs dict (matches what the orchestrator
    passes through to the lightweight chain). Mirrors the canonical
    tests/golden/scenarios.C_UAS_1500M values."""
    return {
        "wavelength": 1.07e-6,
        "P0": 5000.0,
        "M2": 1.2,
        "D": 0.10,
        "sigma_jit": 1.0e-5,
        "eta_opt": 0.85,
        "V": 23.0,
        "RH": 50.0,
        "T_ambient": 300.0,
        "P_atm": 101325.0,
        "cn2_model": "constant",
        "Cn2_value": 1.7e-14,
        "Cn2_ground": 1.7e-14,
        "v_HV": 21.0,
        "d_aim": 0.05,
    }


def _canonical_scenario() -> SwarmScenario:
    return SwarmScenario(
        drones=(
            Drone(0, "commercial_quad", (1500.0, 0.0), (-18.0, 0.0)),
            Drone(1, "mini_fixed_wing", (1200.0, 800.0), (-25.0, -15.0)),
            Drone(2, "group1_kamikaze", (2000.0, -500.0), (-40.0, 5.0)),
        ),
        bd_kinematics=BDKinematics(),
        hel_inputs=_hel_inputs_canonical(),
    )


# ---------------------------------------------------------------------------
# Drone validation
# ---------------------------------------------------------------------------

def test_drone_rejects_unknown_type():
    """Drone __post_init__ must reject unknown drone-type keys."""
    with pytest.raises(ValueError, match="unknown drone_type_key"):
        Drone(0, "fictional_drone", (1000.0, 0.0), (-10.0, 0.0))


def test_drone_position_must_be_2tuple():
    with pytest.raises(ValueError, match="2-tuples"):
        Drone(0, "commercial_quad", (1000.0,), (-10.0, 0.0))


def test_drone_initial_range_property():
    d = Drone(0, "commercial_quad", (300.0, 400.0), (-5.0, -5.0))
    assert d.initial_range_m == pytest.approx(500.0)


def test_drone_speed_property():
    d = Drone(0, "commercial_quad", (1000.0, 0.0), (-3.0, 4.0))
    assert d.speed_mps == pytest.approx(5.0)


# ---------------------------------------------------------------------------
# BDKinematics validation
# ---------------------------------------------------------------------------

def test_bd_kinematics_rejects_zero_rate():
    with pytest.raises(ValueError, match="positive"):
        BDKinematics(max_slew_rate_dps=0.0)


def test_bd_kinematics_rejects_negative_settling():
    with pytest.raises(ValueError, match="non-negative"):
        BDKinematics(settling_time_s=-0.1)


def test_bd_kinematics_default_values_match_plan():
    """Plan §1 specifies generic defaults (60 deg/s, 120 deg/s²,
    0.2 s settle, 0.15 s reacquire)."""
    bd = BDKinematics()
    assert bd.max_slew_rate_dps == 60.0
    assert bd.max_slew_accel_dps2 == 120.0
    assert bd.settling_time_s == 0.2
    assert bd.reacquire_time_s == 0.15


# ---------------------------------------------------------------------------
# SwarmScenario validation
# ---------------------------------------------------------------------------

def test_scenario_rejects_unknown_strategy():
    with pytest.raises(ValueError, match="unknown strategy"):
        SwarmScenario(
            drones=(),
            bd_kinematics=BDKinematics(),
            hel_inputs=_hel_inputs_canonical(),
            strategy="random_pick",
        )


def test_scenario_rejects_R_detect_le_R_min():
    with pytest.raises(ValueError, match="greater than R_min"):
        SwarmScenario(
            drones=(),
            bd_kinematics=BDKinematics(),
            hel_inputs=_hel_inputs_canonical(),
            R_min_m=500.0,
            R_detect_max_m=400.0,
        )


def test_scenario_rejects_duplicate_drone_ids():
    with pytest.raises(ValueError, match="unique"):
        SwarmScenario(
            drones=(
                Drone(0, "commercial_quad", (1000.0, 0.0), (-10.0, 0.0)),
                Drone(0, "commercial_quad", (1100.0, 0.0), (-10.0, 0.0)),
            ),
            bd_kinematics=BDKinematics(),
            hel_inputs=_hel_inputs_canonical(),
        )


# ---------------------------------------------------------------------------
# JSON round-trip (Layer 4b)
# ---------------------------------------------------------------------------

def test_scenario_json_round_trip():
    """Save → load → identical Python object."""
    s1 = _canonical_scenario()
    blob = s1.to_json()
    s2 = SwarmScenario.from_json(blob)
    assert s1 == s2


def test_scenario_json_includes_schema_version():
    """The on-disk format is versioned so future migrations are
    safe."""
    blob = _canonical_scenario().to_json()
    assert f'"version": "{SCENARIO_SCHEMA_VERSION}"' in blob


def test_bad_json_invalid_syntax():
    """Malformed JSON → ValueError, not crash."""
    with pytest.raises(ValueError, match="invalid JSON"):
        SwarmScenario.from_json("{not valid json")


def test_bad_json_wrong_schema_version():
    blob = '{"version": "999", "drones": [], "bd_kinematics": {}, "hel_inputs": {}}'
    with pytest.raises(ValueError, match="unsupported scenario schema"):
        SwarmScenario.from_json(blob)


def test_bad_json_unknown_drone_type():
    s = _canonical_scenario()
    bad = s.to_json().replace("commercial_quad", "fictional_drone")
    with pytest.raises(ValueError, match="missing or malformed"):
        SwarmScenario.from_json(bad)


def test_scenario_json_is_stable_across_calls():
    """Same scenario serializes to bit-identical JSON twice in a
    row (sort_keys=True). Important for golden tests that compare
    JSON byte-for-byte."""
    s = _canonical_scenario()
    assert s.to_json() == s.to_json()
