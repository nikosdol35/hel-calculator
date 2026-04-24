"""Canonical engagement scenarios for golden-output regression.

Per the Package 2 plan (validation/README.md Layer 2.4), four scenarios
are pinned to guard against silent numeric drift in any of the 46
orchestrator output keys. The scenarios cover the main SPEC §5.1 preset
archetypes plus one infeasible-geometry case that must raise.

Each scenario is a complete SI-unit dict suitable for passing straight to
`orchestrator.run_full_chain()`. The expected outputs for each scenario
live in `<name>.json` and are seeded once via the test_golden.py update
mode. See that file's module docstring for the bootstrap procedure.
"""

# ---------------------------------------------------------------------------
# 1. C-UAS short-range — 3 kW / 1.5 km / 1.07 µm / CFRP (Panel 1 preset)
# ---------------------------------------------------------------------------
C_UAS_1500M = {
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


# ---------------------------------------------------------------------------
# 2. Counter-rocket — 30 kW / 3 km / 1.07 µm / CFRP
# ---------------------------------------------------------------------------
COUNTER_ROCKET_3000M = {
    "P0": 30000, "M2": 1.3, "D": 0.30, "wavelength": 1.07e-6,
    "eta_opt": 0.80, "sigma_jit": 5e-6,
    "H_e": 10, "R": 3000, "H_t": 1000, "v_tgt": 80, "v_perp": 5,
    "V": 23, "RH": 0.60, "T_ambient": 298, "P_atm": 101325,
    "cn2_model": "HV_5_7", "Cn2_value": 1e-14,
    "Cn2_ground": 1.7e-14, "v_HV": 21,
    "d_aim": 0.10, "material": "CFRP", "thickness": 0.003,
    "eta_wallplug": 0.25, "Q_cool": 100000,
    "C_thermal": 500e3, "dT_max": 25, "t_exp": 1.0,
}


# ---------------------------------------------------------------------------
# 3. Long-range surveillance — 10 kW / 8 km / 1.55 µm / polycarbonate
# ---------------------------------------------------------------------------
LONG_RANGE_8000M = {
    "P0": 10000, "M2": 1.5, "D": 0.25, "wavelength": 1.55e-6,
    "eta_opt": 0.85, "sigma_jit": 8e-6,
    "H_e": 100, "R": 8000, "H_t": 2000, "v_tgt": 50, "v_perp": 10,
    "V": 30, "RH": 0.50, "T_ambient": 290, "P_atm": 101325,
    "cn2_model": "HV_5_7", "Cn2_value": 1e-14,
    "Cn2_ground": 1.7e-14, "v_HV": 21,
    "d_aim": 0.15, "material": "polycarbonate", "thickness": 0.004,
    "eta_wallplug": 0.30, "Q_cool": 30000,
    "C_thermal": 250e3, "dT_max": 30, "t_exp": 2.0,
}


# ---------------------------------------------------------------------------
# 4. Infeasible geometry — R < |H_t − H_e|; must raise ValueError
# ---------------------------------------------------------------------------
INFEASIBLE = {
    **C_UAS_1500M,
    "R": 1000, "H_e": 0, "H_t": 5000,  # 5000 m altitude delta > 1000 m slant
}


SCENARIOS = {
    "c_uas_1500m": C_UAS_1500M,
    "counter_rocket_3000m": COUNTER_ROCKET_3000M,
    "long_range_8000m": LONG_RANGE_8000M,
}
