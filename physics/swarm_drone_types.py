"""Drone-type presets for the Swarm Analyzer.

Three preset threat types covering the common drone-swarm threat
spectrum: a small commercial quad-copter, a mini fixed-wing UAV, and
a Group-1 kamikaze (Shahed-class small). All three preset materials
(``polycarbonate``, ``GFRP``, ``CFRP``) are entries in
``physics/m8_material_tables.MATERIAL_PROPERTIES`` already, so the
HEL chain handles them with no SPEC change.

Each preset carries:
  - ``mass_kg`` — for kinetic-energy / loitering-munition reasoning
    (informational; not used in the v1 simulation)
  - ``material`` — key into ``m8_material_tables``; drives ρ, c_p, k,
    T_fail in the burn-through math
  - ``thickness_m`` — front-face shell thickness driving E_fail
  - ``speed_mps_default`` / ``speed_envelope`` — typical operating
    envelope for the drone class
  - ``color`` — palette-aligned hex used by the playback animation

The preset library is closed (no custom-drone editor in v1, per the
plan §9). v2 will add custom-type support.

Sources:
  - Commercial quad geometry / mass: DJI Mavic / Phantom datasheets
  - Mini fixed-wing: small loitering-munition class (~3-5 kg)
  - Group-1 kamikaze: open-source Shahed-class reporting (Sandia
    SAND2024-class), small variant ~5-10 kg
"""
from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class DroneType:
    """One drone-class preset.

    All numeric values are in SI (kg, m, m/s). ``color`` is a hex
    string aligned with the app palette so the animated playback's
    drone dots match the corresponding curves elsewhere in the tool.
    """
    key: str
    label: str
    mass_kg: float
    material: str            # key into m8_material_tables.MATERIAL_PROPERTIES
    thickness_m: float
    speed_mps_default: float
    speed_envelope_mps: tuple[float, float]
    color_hex: str
    a_lambda_hint: float | None = None  # optional override; None → use M8 default


COMMERCIAL_QUAD = DroneType(
    key="commercial_quad",
    label="Commercial quad (DJI-class)",
    mass_kg=1.5,
    material="polycarbonate",
    thickness_m=0.001,             # 1 mm body shell
    speed_mps_default=18.0,
    speed_envelope_mps=(10.0, 25.0),
    color_hex="#F5A623",            # amber, palette data.a
)

MINI_FIXED_WING = DroneType(
    key="mini_fixed_wing",
    label="Mini fixed-wing UAV",
    mass_kg=4.0,
    material="GFRP",
    thickness_m=0.0015,
    speed_mps_default=30.0,
    speed_envelope_mps=(20.0, 45.0),
    color_hex="#2EA8A0",            # teal, palette data.b
)

GROUP1_KAMIKAZE = DroneType(
    key="group1_kamikaze",
    label="Group-1 kamikaze (Shahed-class small)",
    mass_kg=8.0,
    material="CFRP",
    thickness_m=0.002,
    speed_mps_default=45.0,
    speed_envelope_mps=(30.0, 60.0),
    color_hex="#9B7AC9",            # purple, palette data.c
)


DRONE_TYPES: dict[str, DroneType] = {
    COMMERCIAL_QUAD.key: COMMERCIAL_QUAD,
    MINI_FIXED_WING.key: MINI_FIXED_WING,
    GROUP1_KAMIKAZE.key: GROUP1_KAMIKAZE,
}


def get_drone_type(key: str) -> DroneType:
    """Look up a preset by key. Raises ``KeyError`` with a clear
    message listing the available keys when the lookup fails — better
    UX than the default dict KeyError."""
    if key not in DRONE_TYPES:
        raise KeyError(
            f"Unknown drone type {key!r}. Available presets: "
            f"{sorted(DRONE_TYPES.keys())}."
        )
    return DRONE_TYPES[key]


__all__ = [
    "DroneType",
    "COMMERCIAL_QUAD",
    "MINI_FIXED_WING",
    "GROUP1_KAMIKAZE",
    "DRONE_TYPES",
    "get_drone_type",
]
