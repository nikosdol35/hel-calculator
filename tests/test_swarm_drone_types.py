"""Tests for the swarm-drone-type preset library.

Verifies the three presets pin the right material keys (so the HEL
chain's M8 material table can resolve them), have non-degenerate
numeric values, and the lookup helper raises clean errors for bad
keys.
"""
from __future__ import annotations

import pytest

from physics.m8_material_tables import MATERIAL_PROPERTIES
from physics.swarm_drone_types import (
    COMMERCIAL_QUAD,
    DRONE_TYPES,
    GROUP1_KAMIKAZE,
    MINI_FIXED_WING,
    DroneType,
    get_drone_type,
)


def test_three_presets_in_library():
    """The plan §1 / §3.7 specifies exactly three presets for v1."""
    assert len(DRONE_TYPES) == 3
    assert set(DRONE_TYPES.keys()) == {
        "commercial_quad", "mini_fixed_wing", "group1_kamikaze",
    }


def test_each_preset_material_in_m8_table():
    """Every drone preset's material must resolve in the M8 material
    table — otherwise the HEL chain can't compute E_fail."""
    for drone_type in DRONE_TYPES.values():
        assert drone_type.material in MATERIAL_PROPERTIES, (
            f"drone {drone_type.key!r} references unknown material "
            f"{drone_type.material!r}"
        )


def test_preset_numeric_fields_positive():
    """Sanity: mass, thickness, speed, speed-envelope all positive
    and reasonable. Catches typos like a mass of -1.5."""
    for d in DRONE_TYPES.values():
        assert d.mass_kg > 0
        assert d.thickness_m > 0
        assert d.speed_mps_default > 0
        lo, hi = d.speed_envelope_mps
        assert lo > 0 and hi > lo
        assert lo <= d.speed_mps_default <= hi


def test_get_drone_type_known_key_returns_preset():
    """Lookup helper resolves all three keys."""
    assert get_drone_type("commercial_quad") is COMMERCIAL_QUAD
    assert get_drone_type("mini_fixed_wing") is MINI_FIXED_WING
    assert get_drone_type("group1_kamikaze") is GROUP1_KAMIKAZE


def test_get_drone_type_bad_key_raises_with_helpful_message():
    """Unknown key → KeyError listing the available presets."""
    with pytest.raises(KeyError, match="Unknown drone type"):
        get_drone_type("not_a_real_drone")


def test_preset_color_hex_is_valid():
    """Color must be a #RRGGBB hex string (Plotly + the app palette
    both accept this format)."""
    for d in DRONE_TYPES.values():
        assert d.color_hex.startswith("#")
        assert len(d.color_hex) == 7
        # Accept hex chars only.
        int(d.color_hex[1:], 16)


def test_dronetype_is_frozen():
    """DroneType instances must be immutable (we hash them inside
    the LRU-cached lightweight chain calls)."""
    with pytest.raises(Exception):
        COMMERCIAL_QUAD.mass_kg = 99.0
