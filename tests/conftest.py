"""Shared pytest fixtures for the HEL validation suite.

Per TESTING.md §6: canonical_inputs holds the SPEC §5.1 Panel A–F default
parameter set for a typical C-UAS engagement at 1.5 km with a 3 kW laser.
Tests that need variations make a local copy and modify (via `**fixture`
spread); the fixture itself is never mutated."""

import pytest


@pytest.fixture
def canonical_inputs():
    """SPEC §5.1 Panel A–F default parameter set."""
    return {
        # Panel A — Laser Source
        "P0": 3000, "M2": 1.2, "D": 0.10, "wavelength": 1.07e-6,
        # Panel B — Beam Director
        "eta_opt": 0.85, "sigma_jit": 10e-6,
        # Panel C — Engagement Geometry
        "H_e": 2, "R": 1500, "H_t": 200, "v_tgt": 20, "v_perp": 3,
        # Panel D — Atmosphere
        "V": 23, "RH": 0.60, "T_ambient": 300, "P_atm": 101325,
        "cn2_model": "HV_5_7", "Cn2_value": 1e-14,
        "Cn2_ground": 1.7e-14, "v_HV": 21,
        # Panel E — Aimpoint & Material
        "d_aim": 0.05, "material": "CFRP", "thickness": 0.002,
        # Panel F — System Resources & Safety
        "eta_wallplug": 0.30, "Q_cool": 15000,
        "C_thermal": 200e3, "dT_max": 30, "t_exp": 0.25,
    }
