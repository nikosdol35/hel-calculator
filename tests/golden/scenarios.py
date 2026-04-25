"""Canonical engagement scenarios for golden-output regression.

Per the Package 2 plan (validation/README.md Layer 2.4), three scenarios
are pinned to guard against silent numeric drift across the orchestrator
output dict. The scenarios cover the main SPEC §5.1 preset archetypes
plus one infeasible-geometry case that must raise.

**SPEC v2.0 — tracker-supported dwell.** Each scenario carries the v2.0
trajectory-mode keys (``R_detect``, ``R_min``, ``engagement_geometry``)
plus the legacy v1.x ``R`` and ``v_perp`` keys. The orchestrator
dispatches on the presence of ``engagement_geometry``: leaving it in
makes the scenario a v2 trajectory engagement (the default state — and
what the goldens are seeded against), and tests that need a v1.x
single-point engagement can drop the v2 keys explicitly. PR 12 of
``docs/tracker_dwell_plan_2026-04-25.md`` re-seeded the
``<scenario>.json`` golden files under the v2 contract; see
``test_golden.py`` for the bootstrap procedure.

Each scenario is a complete SI-unit dict suitable for passing straight to
``orchestrator.run_full_chain()``. The infeasible case uses ``R_detect``
< ``|H_t − H_e|`` to trigger the M3 v2.0 validator's ValueError.
"""

# ---------------------------------------------------------------------------
# 1. C-UAS short-range — 3 kW / detect at 1.5 km / 1.07 µm / CFRP /
#    head-on closure at 20 m/s down to 100 m standoff (Panel 1 preset).
# ---------------------------------------------------------------------------
C_UAS_1500M = {
    # Panel A — Laser Source
    "P0": 3000, "M2": 1.2, "D": 0.10, "wavelength": 1.07e-6,
    # Panel B — Beam Director
    "eta_opt": 0.85, "sigma_jit": 10e-6,
    # Panel C — Engagement Geometry. v2.0 keys drive the orchestrator;
    # the v1.x R / v_perp are kept so legacy callers and tests that
    # explicitly drop the v2 keys still get a complete v1 dict.
    "H_e": 2, "H_t": 200, "v_tgt": 20,
    "R": 1500, "v_perp": 3,                        # v1.x backward-compat
    "R_detect": 1500, "R_min": 100,                # v2.0 trajectory contract
    "engagement_geometry": "head_on",
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
# 2. Counter-rocket — 30 kW / detect at 3 km / 1.07 µm / CFRP /
#    head-on closure at 80 m/s down to 100 m standoff.
# ---------------------------------------------------------------------------
COUNTER_ROCKET_3000M = {
    "P0": 30000, "M2": 1.3, "D": 0.30, "wavelength": 1.07e-6,
    "eta_opt": 0.80, "sigma_jit": 5e-6,
    "H_e": 10, "H_t": 1000, "v_tgt": 80,
    "R": 3000, "v_perp": 5,                        # v1.x backward-compat
    "R_detect": 3000, "R_min": 100, "engagement_geometry": "head_on",
    "V": 23, "RH": 0.60, "T_ambient": 298, "P_atm": 101325,
    "cn2_model": "HV_5_7", "Cn2_value": 1e-14,
    "Cn2_ground": 1.7e-14, "v_HV": 21,
    "d_aim": 0.10, "material": "CFRP", "thickness": 0.003,
    "eta_wallplug": 0.25, "Q_cool": 100000,
    "C_thermal": 500e3, "dT_max": 25, "t_exp": 1.0,
}


# ---------------------------------------------------------------------------
# 3. Long-range surveillance — 10 kW / detect at 8 km / 1.55 µm /
#    polycarbonate / lateral pass at 50 m/s with 500 m closest approach.
#    Demonstrates the lateral-geometry path through the orchestrator.
# ---------------------------------------------------------------------------
LONG_RANGE_8000M = {
    "P0": 10000, "M2": 1.5, "D": 0.25, "wavelength": 1.55e-6,
    "eta_opt": 0.85, "sigma_jit": 8e-6,
    "H_e": 100, "H_t": 2000, "v_tgt": 50,
    "R": 8000, "v_perp": 10,                       # v1.x backward-compat
    "R_detect": 8000, "R_min": 500, "engagement_geometry": "lateral",
    "V": 30, "RH": 0.50, "T_ambient": 290, "P_atm": 101325,
    "cn2_model": "HV_5_7", "Cn2_value": 1e-14,
    "Cn2_ground": 1.7e-14, "v_HV": 21,
    "d_aim": 0.15, "material": "polycarbonate", "thickness": 0.004,
    "eta_wallplug": 0.30, "Q_cool": 30000,
    "C_thermal": 250e3, "dT_max": 30, "t_exp": 2.0,
}


# ---------------------------------------------------------------------------
# 4. Infeasible geometry — R_detect < |H_t − H_e|; must raise ValueError.
#    Triggers the M3 v2.0 path's altitude-vs-slant feasibility check.
# ---------------------------------------------------------------------------
INFEASIBLE = {
    **C_UAS_1500M,
    "R": 1000, "R_detect": 1000, "H_e": 0, "H_t": 5000,
    # 5000 m altitude delta exceeds 1000 m slant → M3 raises in both
    # v1.x and v2.0 modes.
}


SCENARIOS = {
    "c_uas_1500m": C_UAS_1500M,
    "counter_rocket_3000m": COUNTER_ROCKET_3000M,
    "long_range_8000m": LONG_RANGE_8000M,
}
