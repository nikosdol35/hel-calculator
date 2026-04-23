"""The six input panels (A–F) per SPEC.md §5.1 and ARCHITECTURE.md §6.3.

One function per panel; each returns a dict of that panel's inputs in the
SI units the physics layer expects (``ui/`` handles friendly-unit → SI
conversion so the physics modules never see kW/cm/µm/kJ). ``collect_all``
merges the six dicts into the single ``user_inputs`` dict the orchestrator
consumes.

All panels render as ``st.expander`` widgets in the sidebar. Default
expansion state per SPEC §5.1: A, C, E expanded; B, D, F collapsed —
rationale: panels A, C, E are the most frequently touched inputs in
trade-study workflows.

Plan-document improvement #4 (exposure-duration disambiguation):
    Panel F's ``t_exp`` label explicitly states "laser exposure time,
    M9 MPE safety path only" so it is not confused with the engagement
    dwell used elsewhere in the tool. No SPEC edit required — this is
    a UI-only label clarification per CLAUDE §3 step 1.

Plan-document improvement #5 (A_λ override pattern):
    Panel E exposes ``A_lambda`` via a checkbox + slider pair rather
    than a nullable slider. When the checkbox is unchecked the returned
    dict does NOT contain the key, which matches exactly what the
    orchestrator expects (``physics/orchestrator.py`` line ~258 passes
    ``A_lambda`` only when ``u.get("A_lambda") is not None``); M8 then
    falls back to its material-table default and flags the
    default-lookup assumption. With the checkbox on, the slider value
    passes through. No SPEC edit required — SPEC §5.1 Panel E already
    described this as "from table / user override 0.05–0.99"; the
    UI pattern here implements that intent.

References:
    SPEC.md §5.1 — panel contents, defaults, sanity ranges, iconography,
        default expansion state.
    ARCHITECTURE.md §6.3 — function signatures (``panel_a_*`` … ``panel_f_*``
        plus ``collect_all``), unit-conversion responsibility.
    physics/orchestrator.py — consumer contract for the returned dict.
    physics/m8_material_tables.py — ``MATERIALS`` tuple drives Panel E's
        material selectbox options.
"""

from __future__ import annotations

import streamlit as st

from physics.m8_material_tables import MATERIALS


# ---------------------------------------------------------------------------
# Small helpers.
# ---------------------------------------------------------------------------


def _initial(values: dict | None, key: str, default):
    """Return ``values[key]`` if present (URL-decoded prefill from app.py)
    otherwise fall back to the SPEC §5.1 default. Centralised so the slice-4
    URL-latch can feed the panels a single dict without every panel
    rewriting the same ``dict | None`` check."""
    if values is None:
        return default
    return values.get(key, default)


# ---------------------------------------------------------------------------
# Panel A — Laser Source → M1
# ---------------------------------------------------------------------------


def panel_a_laser_source(initial: dict | None = None) -> dict:
    """SPEC §5.1 Panel A: P0, M², D, wavelength. Icon 🔦."""
    with st.sidebar.expander("🔦 A — Laser Source", expanded=True):
        P0_kW = st.number_input(
            "Output power (kW)",
            min_value=0.1, max_value=100.0,
            value=float(_initial(initial, "P0", 3000.0)) / 1000.0,
            step=0.1, key="P0_kW",
        )
        M2 = st.number_input(
            "Beam quality M²",
            min_value=1.0, max_value=10.0,
            value=float(_initial(initial, "M2", 1.2)),
            step=0.1, key="M2",
        )
        D_cm = st.number_input(
            "Exit aperture diameter (cm)",
            min_value=1.0, max_value=50.0,
            value=float(_initial(initial, "D", 0.10)) * 100.0,
            step=0.5, key="D_cm",
        )
        wavelength_um = st.number_input(
            "Wavelength (µm)",
            min_value=0.5, max_value=5.0,
            value=float(_initial(initial, "wavelength", 1.07e-6)) * 1e6,
            step=0.01, format="%.3f", key="wavelength_um",
        )
    return {
        "P0": P0_kW * 1000.0,
        "M2": M2,
        "D": D_cm / 100.0,
        "wavelength": wavelength_um * 1e-6,
    }


# ---------------------------------------------------------------------------
# Panel B — Beam Director → M2 (+ jitter into M7)
# ---------------------------------------------------------------------------


def panel_b_beam_director(initial: dict | None = None) -> dict:
    """SPEC §5.1 Panel B: η_opt, σ_jit (per-axis 1-σ RMS). Icon 🎯."""
    with st.sidebar.expander("🎯 B — Beam Director", expanded=False):
        eta_opt = st.number_input(
            "Optical transmission",
            min_value=0.50, max_value=0.99,
            value=float(_initial(initial, "eta_opt", 0.85)),
            step=0.01, key="eta_opt",
        )
        sigma_jit_urad = st.number_input(
            "Pointing jitter — per-axis 1-σ RMS (µrad)",
            min_value=0.1, max_value=1000.0,
            value=float(_initial(initial, "sigma_jit", 10e-6)) * 1e6,
            step=0.5, key="sigma_jit_urad",
            help="Per-axis (azimuth or elevation) 1-σ angular RMS, the "
                 "standard PTU/EO datasheet convention. Entering a 2-D "
                 "radial RMS value would double-count — see SPEC §1.",
        )
    return {
        "eta_opt": eta_opt,
        "sigma_jit": sigma_jit_urad * 1e-6,
    }


# ---------------------------------------------------------------------------
# Panel C — Engagement Geometry → M3
# ---------------------------------------------------------------------------


def panel_c_geometry(initial: dict | None = None) -> dict:
    """SPEC §5.1 Panel C: H_e, R, H_t, v_tgt, v_perp. Icon 📐."""
    with st.sidebar.expander("📐 C — Engagement Geometry", expanded=True):
        H_e = st.number_input(
            "Emplacement altitude AGL (m)",
            min_value=0.0, max_value=3000.0,
            value=float(_initial(initial, "H_e", 2.0)),
            step=1.0, key="H_e",
        )
        R = st.number_input(
            "Slant range to target (m)",
            min_value=50.0, max_value=50000.0,
            value=float(_initial(initial, "R", 1500.0)),
            step=50.0, key="R",
        )
        H_t = st.number_input(
            "Target altitude AGL (m)",
            min_value=0.0, max_value=5000.0,
            value=float(_initial(initial, "H_t", 200.0)),
            step=10.0, key="H_t",
        )
        v_tgt = st.number_input(
            "Target velocity (m/s)",
            min_value=0.0, max_value=100.0,
            value=float(_initial(initial, "v_tgt", 20.0)),
            step=1.0, key="v_tgt",
        )
        v_perp = st.number_input(
            "Crosswind, perpendicular to path (m/s)",
            min_value=0.0, max_value=30.0,
            value=float(_initial(initial, "v_perp", 3.0)),
            step=0.5, key="v_perp",
        )
    return {
        "H_e": H_e, "R": R, "H_t": H_t,
        "v_tgt": v_tgt, "v_perp": v_perp,
    }


# ---------------------------------------------------------------------------
# Panel D — Atmosphere → M4, M5
# ---------------------------------------------------------------------------

_CN2_MODEL_OPTIONS = ("HV_5_7", "constant", "HV_day", "HV_night")


def panel_d_atmosphere(initial: dict | None = None) -> dict:
    """SPEC §5.1 Panel D: V, RH, T_ambient, cn2_model, Cn2_value /
    Cn2_ground, v_HV. Icon 🌫️.

    ``Cn2_value`` is shown when cn2_model == 'constant'; ``Cn2_ground`` and
    ``v_HV`` are shown for the HV profiles. Both keys are still returned in
    the output dict (falling back to SPEC defaults) so M5's input
    validation sees the full required-keys set regardless of which model is
    selected.
    """
    with st.sidebar.expander("🌫️ D — Atmosphere", expanded=False):
        V = st.number_input(
            "Visibility (km)",
            min_value=0.5, max_value=50.0,
            value=float(_initial(initial, "V", 23.0)),
            step=0.5, key="V_km",
        )
        RH_pct = st.number_input(
            "Relative humidity (%)",
            min_value=0.0, max_value=100.0,
            value=float(_initial(initial, "RH", 0.60)) * 100.0,
            step=1.0, key="RH_pct",
        )
        T_ambient_C = st.number_input(
            "Ambient temperature (°C)",
            min_value=-20.0, max_value=55.0,
            value=float(_initial(initial, "T_ambient", 300.0)) - 273.15,
            step=1.0, key="T_ambient_C",
        )
        cn2_default = str(_initial(initial, "cn2_model", "HV_5_7"))
        cn2_index = (
            _CN2_MODEL_OPTIONS.index(cn2_default)
            if cn2_default in _CN2_MODEL_OPTIONS else 0
        )
        cn2_model = st.selectbox(
            "Cn² model", _CN2_MODEL_OPTIONS, index=cn2_index, key="cn2_model",
            help="'HV_day' / 'HV_night' are enumerated but not yet "
                 "implemented in M5; selecting them raises a clear error.",
        )
        if cn2_model == "constant":
            Cn2_value = st.number_input(
                "Cn² value (m^-2/3)",
                min_value=1e-17, max_value=1e-12,
                value=float(_initial(initial, "Cn2_value", 1e-14)),
                format="%.2e", key="Cn2_value",
            )
            Cn2_ground = float(_initial(initial, "Cn2_ground", 1.7e-14))
            v_HV = float(_initial(initial, "v_HV", 21.0))
        else:
            Cn2_ground = st.number_input(
                "Ground Cn² (m^-2/3)",
                min_value=1e-16, max_value=1e-12,
                value=float(_initial(initial, "Cn2_ground", 1.7e-14)),
                format="%.2e", key="Cn2_ground",
            )
            v_HV = st.number_input(
                "HV wind speed (m/s)",
                min_value=0.0, max_value=60.0,
                value=float(_initial(initial, "v_HV", 21.0)),
                step=1.0, key="v_HV",
            )
            Cn2_value = float(_initial(initial, "Cn2_value", 1e-14))

    return {
        "V": V,
        "RH": RH_pct / 100.0,
        "T_ambient": T_ambient_C + 273.15,
        "P_atm": 101325.0,  # SPEC §3 M6 default (sea level); not user-editable in v1
        "cn2_model": cn2_model,
        "Cn2_value": Cn2_value,
        "Cn2_ground": Cn2_ground,
        "v_HV": v_HV,
    }


# ---------------------------------------------------------------------------
# Panel E — Aimpoint & Material → M7, M8
# ---------------------------------------------------------------------------

_BACKSIDE_BC_OPTIONS = ("insulated", "convective")


def panel_e_aimpoint_material(initial: dict | None = None) -> dict:
    """SPEC §5.1 Panel E: d_aim, material, thickness, A_lambda (override
    via checkbox+slider — improvement #5), backside_BC. Icon 🛡️.

    A_lambda handling (improvement #5): the override defaults to OFF so
    first-time users get the material-table default (with its SPEC §10.2
    HIGH UNCERTAINTY flag surfacing in Panel 4). Toggling the checkbox
    reveals the slider; when toggled off the returned dict omits the
    ``A_lambda`` key entirely (so the orchestrator's
    ``u.get("A_lambda") is not None`` gate routes to the table lookup).
    """
    with st.sidebar.expander("🛡️ E — Aimpoint & Material", expanded=True):
        d_aim_cm = st.number_input(
            "Aimpoint diameter (cm)",
            min_value=0.5, max_value=30.0,
            value=float(_initial(initial, "d_aim", 0.05)) * 100.0,
            step=0.5, key="d_aim_cm",
        )
        mat_default = str(_initial(initial, "material", "CFRP"))
        mat_index = MATERIALS.index(mat_default) if mat_default in MATERIALS else 0
        material = st.selectbox(
            "Material", MATERIALS, index=mat_index, key="material",
        )
        thickness_mm = st.number_input(
            "Thickness (mm)",
            min_value=0.1, max_value=20.0,
            value=float(_initial(initial, "thickness", 0.002)) * 1000.0,
            step=0.1, key="thickness_mm",
        )

        # Improvement #5: checkbox + slider pair. Default OFF so the
        # material-table lookup (with its SPEC §10.2 HIGH UNCERTAINTY
        # flag) fires unless the user has a measured value.
        override_default = _initial(initial, "A_lambda", None) is not None
        override_A = st.checkbox(
            "Override default A_λ absorptivity",
            value=override_default,
            help="Default uses the SPEC §3 M8 material-table A_λ (flagged "
                 "HIGH UNCERTAINTY). Tick this only if you have a measured "
                 "or program-specific value.",
            key="_A_lambda_override",
        )
        if override_A:
            A_lambda = st.slider(
                "A_λ absorptivity",
                min_value=0.05, max_value=0.99,
                value=float(_initial(initial, "A_lambda", 0.85)),
                step=0.01, key="A_lambda",
            )
        else:
            A_lambda = None

        bc_default = str(_initial(initial, "backside_BC", "insulated"))
        bc_index = (
            _BACKSIDE_BC_OPTIONS.index(bc_default)
            if bc_default in _BACKSIDE_BC_OPTIONS else 0
        )
        backside_BC = st.selectbox(
            "Backside BC", _BACKSIDE_BC_OPTIONS, index=bc_index,
            key="backside_BC",
            help="'insulated' (conservative) or 'convective' (uses ambient "
                 "air as the cold sink — SPEC §10.6 HIGH UNCERTAINTY).",
        )

    out: dict = {
        "d_aim": d_aim_cm / 100.0,
        "material": material,
        "thickness": thickness_mm / 1000.0,
        "backside_BC": backside_BC,
    }
    if A_lambda is not None:
        out["A_lambda"] = A_lambda
    return out


# ---------------------------------------------------------------------------
# Panel F — System Resources & Safety → M9, M10
# ---------------------------------------------------------------------------


def panel_f_resources_safety(initial: dict | None = None) -> dict:
    """SPEC §5.1 Panel F: η_wallplug, Q_cool, C_thermal, ΔT_max, t_exp.
    Icon ⚙️.

    The ``t_exp`` label explicitly names the MPE safety path
    (improvement #4) so it is not confused with engagement dwell or M10
    runtime — those quantities live elsewhere in the tool.
    """
    with st.sidebar.expander("⚙️ F — System Resources & Safety", expanded=False):
        eta_wallplug = st.number_input(
            "Wall-plug efficiency",
            min_value=0.05, max_value=0.50,
            value=float(_initial(initial, "eta_wallplug", 0.30)),
            step=0.01, key="eta_wallplug",
        )
        Q_cool_kW = st.number_input(
            "Cooling capacity (kW)",
            min_value=0.0, max_value=500.0,
            value=float(_initial(initial, "Q_cool", 15000.0)) / 1000.0,
            step=1.0, key="Q_cool_kW",
        )
        C_thermal_kJK = st.number_input(
            "Coolant thermal mass (kJ/K)",
            min_value=10.0, max_value=5000.0,
            value=float(_initial(initial, "C_thermal", 200e3)) / 1000.0,
            step=10.0, key="C_thermal_kJK",
        )
        dT_max = st.number_input(
            "Max coolant ΔT (K)",
            min_value=5.0, max_value=80.0,
            value=float(_initial(initial, "dT_max", 30.0)),
            step=1.0, key="dT_max",
        )
        t_exp = st.number_input(
            "Laser exposure duration — MPE safety path only (s)",
            min_value=0.25, max_value=100.0,
            value=float(_initial(initial, "t_exp", 0.25)),
            step=0.25, key="t_exp",
            help="Drives M9 ANSI Z136.1 MPE calculation only. This is NOT "
                 "the engagement dwell or M10 runtime — Plot B derives "
                 "dwell from target response per SPEC §3 M8.",
        )
    return {
        "eta_wallplug": eta_wallplug,
        "Q_cool": Q_cool_kW * 1000.0,
        "C_thermal": C_thermal_kJK * 1000.0,
        "dT_max": dT_max,
        "t_exp": t_exp,
    }


# ---------------------------------------------------------------------------
# Aggregator.
# ---------------------------------------------------------------------------


def collect_all(initial: dict | None = None) -> dict:
    """Render all six panels and return the merged ``user_inputs`` dict.

    ``initial`` is the URL-decoded prefill dict from ``ui/app.py``'s
    session-state latch (slice 4 / improvement #1). When None, each
    panel falls back to its SPEC §5.1 default. Later keys do not
    overwrite earlier ones because panel dicts have disjoint key
    spaces by SPEC §5.1.
    """
    merged: dict = {}
    merged.update(panel_a_laser_source(initial))
    merged.update(panel_b_beam_director(initial))
    merged.update(panel_c_geometry(initial))
    merged.update(panel_d_atmosphere(initial))
    merged.update(panel_e_aimpoint_material(initial))
    merged.update(panel_f_resources_safety(initial))
    return merged
