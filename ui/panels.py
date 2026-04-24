"""The six sidebar input sections per SPEC.md §5.1 and ARCHITECTURE.md §6.3.

One function per section; each returns a dict of that section's inputs
in the SI units the physics layer expects (``ui/`` handles friendly-unit
→ SI conversion so the physics modules never see kW / cm / µm / kJ).
``collect_all`` merges the six dicts into the single ``user_inputs``
dict the orchestrator consumes.

Phase 3 PR 1 changes:
    * Emoji iconography removed — section headers are plain English only.
    * Section labels, widget labels, and tooltips now read from
      ``ui/labels.py`` (single source of truth). This module hard-codes
      defaults, ranges, and unit conversions but no user-visible prose.
    * Return-dict shape is unchanged (same keys, same SI values) so the
      orchestrator contract and all physics tests remain green.

Default-expanded sections per SPEC §5.1: Laser source (1), Engagement
geometry (3), Target & aimpoint (5) — the most frequently touched
inputs in trade-study workflows.

Plan-document improvement #4 (exposure-duration disambiguation): the
``t_exp`` tooltip explicitly states "MPE safety path only" so it is
not confused with engagement dwell.

Plan-document improvement #5 (A_λ override pattern): ``A_lambda``
exposed via a checkbox + slider pair rather than a nullable slider.
When unchecked the returned dict does NOT contain the key, so
``physics/orchestrator.py`` routes to M8's material-table default.

References:
    SPEC.md §5.1 — section contents, defaults, sanity ranges, default
        expansion state.
    ARCHITECTURE.md §6.3 — function signatures, unit-conversion
        responsibility.
    ui/labels.py — SECTION_LABELS, INPUT_LABELS (user-visible strings).
    physics/orchestrator.py — consumer contract for the returned dict.
    physics/m8_material_tables.py — ``MATERIALS`` tuple drives the
        target-material selectbox options.
"""

from __future__ import annotations

import streamlit as st

from physics.m8_material_tables import MATERIALS
from ui.labels import (
    INPUT_LABELS,
    SECTION_LABELS,
    input_label,
    input_tooltip,
)


# ---------------------------------------------------------------------------
# Small helpers.
# ---------------------------------------------------------------------------


def _initial(values: dict | None, key: str, default):
    """Return ``values[key]`` if present (URL-decoded prefill from app.py),
    otherwise fall back to the SPEC §5.1 default. Centralised so the
    URL-latch can feed every section a single dict without each one
    rewriting the same ``dict | None`` check."""
    if values is None:
        return default
    return values.get(key, default)


def _labelled(key: str) -> str:
    """Return '<label> (<unit>)' for a widget — Streamlit widgets accept
    a single string label, so we concatenate here. Falls back to just
    the label when the unit is empty."""
    entry = INPUT_LABELS[key]
    unit = entry.get("unit", "")
    label = entry["label"]
    return f"{label} ({unit})" if unit else label


# ---------------------------------------------------------------------------
# Section 1 — Laser source → M1
# ---------------------------------------------------------------------------


def section_1_laser_source(initial: dict | None = None) -> dict:
    """Laser source inputs: P0, M², D, wavelength. Feeds M1."""
    with st.sidebar.expander(SECTION_LABELS["laser_source"], expanded=True):
        P0_kW = st.number_input(
            _labelled("P0"),
            min_value=0.1, max_value=100.0,
            value=float(_initial(initial, "P0", 3000.0)) / 1000.0,
            step=0.1, key="P0_kW",
            help=input_tooltip("P0"),
        )
        M2 = st.number_input(
            input_label("M2"),
            min_value=1.0, max_value=10.0,
            value=float(_initial(initial, "M2", 1.2)),
            step=0.1, key="M2",
            help=input_tooltip("M2"),
        )
        D_cm = st.number_input(
            _labelled("D"),
            min_value=1.0, max_value=50.0,
            value=float(_initial(initial, "D", 0.10)) * 100.0,
            step=0.5, key="D_cm",
            help=input_tooltip("D"),
        )
        wavelength_um = st.number_input(
            _labelled("wavelength"),
            min_value=0.5, max_value=5.0,
            value=float(_initial(initial, "wavelength", 1.07e-6)) * 1e6,
            step=0.01, format="%.3f", key="wavelength_um",
            help=input_tooltip("wavelength"),
        )
    return {
        "P0": P0_kW * 1000.0,
        "M2": M2,
        "D": D_cm / 100.0,
        "wavelength": wavelength_um * 1e-6,
    }


# ---------------------------------------------------------------------------
# Section 2 — Beam director → M2 (+ jitter into M7)
# ---------------------------------------------------------------------------


def section_2_beam_director(initial: dict | None = None) -> dict:
    """Beam-director inputs: optical transmission, pointing jitter. Feeds M2 + M7."""
    with st.sidebar.expander(SECTION_LABELS["beam_director"], expanded=False):
        eta_opt = st.number_input(
            input_label("eta_opt"),
            min_value=0.50, max_value=0.99,
            value=float(_initial(initial, "eta_opt", 0.85)),
            step=0.01, key="eta_opt",
            help=input_tooltip("eta_opt"),
        )
        sigma_jit_urad = st.number_input(
            _labelled("sigma_jit"),
            min_value=0.1, max_value=1000.0,
            value=float(_initial(initial, "sigma_jit", 10e-6)) * 1e6,
            step=0.5, key="sigma_jit_urad",
            help=input_tooltip("sigma_jit"),
        )
    return {
        "eta_opt": eta_opt,
        "sigma_jit": sigma_jit_urad * 1e-6,
    }


# ---------------------------------------------------------------------------
# Section 3 — Engagement geometry → M3
# ---------------------------------------------------------------------------


def section_3_engagement_geometry(initial: dict | None = None) -> dict:
    """Engagement-geometry inputs: altitudes, range, target + wind speed."""
    with st.sidebar.expander(SECTION_LABELS["engagement_geometry"], expanded=True):
        H_e = st.number_input(
            _labelled("H_e"),
            min_value=0.0, max_value=3000.0,
            value=float(_initial(initial, "H_e", 2.0)),
            step=1.0, key="H_e",
            help=input_tooltip("H_e"),
        )
        R = st.number_input(
            _labelled("R"),
            min_value=50.0, max_value=50000.0,
            value=float(_initial(initial, "R", 1500.0)),
            step=50.0, key="R",
            help=input_tooltip("R"),
        )
        H_t = st.number_input(
            _labelled("H_t"),
            min_value=0.0, max_value=5000.0,
            value=float(_initial(initial, "H_t", 200.0)),
            step=10.0, key="H_t",
            help=input_tooltip("H_t"),
        )
        v_tgt = st.number_input(
            _labelled("v_tgt"),
            min_value=0.0, max_value=100.0,
            value=float(_initial(initial, "v_tgt", 20.0)),
            step=1.0, key="v_tgt",
            help=input_tooltip("v_tgt"),
        )
        v_perp = st.number_input(
            _labelled("v_perp"),
            min_value=0.0, max_value=30.0,
            value=float(_initial(initial, "v_perp", 3.0)),
            step=0.5, key="v_perp",
            help=input_tooltip("v_perp"),
        )
    return {
        "H_e": H_e, "R": R, "H_t": H_t,
        "v_tgt": v_tgt, "v_perp": v_perp,
    }


# ---------------------------------------------------------------------------
# Section 4 — Atmosphere → M4, M5
# ---------------------------------------------------------------------------

# Only the two models that physics/m5_turbulence.py actually implements
# are exposed in the UI. SPEC §3 M5 enumerates "HV_day", "HV_night", and
# "custom" as valid ``cn2_model`` values, but their compute branches
# raise NotImplementedError pending their own SPEC validation cases
# (see tests/test_m5_turbulence.py::test_m5_hv_day_not_implemented).
# Exposing them in the selectbox would route the user into a traceback;
# surface only the implemented pair until the other branches land.
_CN2_MODEL_OPTIONS = ("HV_5_7", "constant")


def section_4_atmosphere(initial: dict | None = None) -> dict:
    """Atmosphere inputs: visibility, humidity, temperature, Cn² profile.

    ``Cn2_value`` is shown when the turbulence profile is 'constant';
    ``Cn2_ground`` and ``v_HV`` are shown for the HV profiles. Both
    groups of keys are returned regardless (falling back to SPEC
    defaults) so M5's input validation always sees the full required
    key-set.
    """
    with st.sidebar.expander(SECTION_LABELS["atmosphere"], expanded=False):
        V = st.number_input(
            _labelled("V"),
            min_value=0.5, max_value=50.0,
            value=float(_initial(initial, "V", 23.0)),
            step=0.5, key="V_km",
            help=input_tooltip("V"),
        )
        RH_pct = st.number_input(
            _labelled("RH"),
            min_value=0.0, max_value=100.0,
            value=float(_initial(initial, "RH", 0.60)) * 100.0,
            step=1.0, key="RH_pct",
            help=input_tooltip("RH"),
        )
        T_ambient_C = st.number_input(
            _labelled("T_ambient"),
            min_value=-20.0, max_value=55.0,
            value=float(_initial(initial, "T_ambient", 300.0)) - 273.15,
            step=1.0, key="T_ambient_C",
            help=input_tooltip("T_ambient"),
        )
        cn2_default = str(_initial(initial, "cn2_model", "HV_5_7"))
        cn2_index = (
            _CN2_MODEL_OPTIONS.index(cn2_default)
            if cn2_default in _CN2_MODEL_OPTIONS else 0
        )
        cn2_model = st.selectbox(
            input_label("cn2_model"),
            _CN2_MODEL_OPTIONS, index=cn2_index, key="cn2_model",
            help=input_tooltip("cn2_model"),
        )
        if cn2_model == "constant":
            Cn2_value = st.number_input(
                _labelled("Cn2_value"),
                min_value=1e-17, max_value=1e-12,
                value=float(_initial(initial, "Cn2_value", 1e-14)),
                format="%.2e", key="Cn2_value",
                help=input_tooltip("Cn2_value"),
            )
            Cn2_ground = float(_initial(initial, "Cn2_ground", 1.7e-14))
            v_HV = float(_initial(initial, "v_HV", 21.0))
        else:
            Cn2_ground = st.number_input(
                _labelled("Cn2_ground"),
                min_value=1e-16, max_value=1e-12,
                value=float(_initial(initial, "Cn2_ground", 1.7e-14)),
                format="%.2e", key="Cn2_ground",
                help=input_tooltip("Cn2_ground"),
            )
            v_HV = st.number_input(
                _labelled("v_HV"),
                min_value=0.0, max_value=60.0,
                value=float(_initial(initial, "v_HV", 21.0)),
                step=1.0, key="v_HV",
                help=input_tooltip("v_HV"),
            )
            Cn2_value = float(_initial(initial, "Cn2_value", 1e-14))

    return {
        "V": V,
        "RH": RH_pct / 100.0,
        "T_ambient": T_ambient_C + 273.15,
        # P_atm default per SPEC §3 M6; not user-editable in v1.
        "P_atm": 101325.0,
        "cn2_model": cn2_model,
        "Cn2_value": Cn2_value,
        "Cn2_ground": Cn2_ground,
        "v_HV": v_HV,
    }


# ---------------------------------------------------------------------------
# Section 5 — Target & aimpoint → M7, M8
# ---------------------------------------------------------------------------

_BACKSIDE_BC_OPTIONS = ("insulated", "convective")


def section_5_target_aimpoint(initial: dict | None = None) -> dict:
    """Target / aimpoint inputs: aimpoint size, material, thickness, A_λ, BC.

    A_λ handling (plan improvement #5): override defaults to OFF so the
    first-time path uses the tabulated HIGH-UNCERTAINTY default (surfaced
    on the Diagnostics tab). Toggling the checkbox reveals the slider;
    when toggled off the returned dict omits ``A_lambda`` entirely so
    the orchestrator routes to the material-table lookup.
    """
    with st.sidebar.expander(SECTION_LABELS["target_aimpoint"], expanded=True):
        d_aim_cm = st.number_input(
            _labelled("d_aim"),
            min_value=0.5, max_value=30.0,
            value=float(_initial(initial, "d_aim", 0.05)) * 100.0,
            step=0.5, key="d_aim_cm",
            help=input_tooltip("d_aim"),
        )
        mat_default = str(_initial(initial, "material", "CFRP"))
        mat_index = MATERIALS.index(mat_default) if mat_default in MATERIALS else 0
        material = st.selectbox(
            input_label("material"),
            MATERIALS, index=mat_index, key="material",
            help=input_tooltip("material"),
        )
        thickness_mm = st.number_input(
            _labelled("thickness"),
            min_value=0.1, max_value=20.0,
            value=float(_initial(initial, "thickness", 0.002)) * 1000.0,
            step=0.1, key="thickness_mm",
            help=input_tooltip("thickness"),
        )

        override_default = _initial(initial, "A_lambda", None) is not None
        override_A = st.checkbox(
            input_label("A_lambda"),
            value=override_default,
            help=input_tooltip("A_lambda"),
            key="_A_lambda_override",
        )
        if override_A:
            A_lambda = st.slider(
                input_label("A_lambda"),
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
            input_label("backside_BC"),
            _BACKSIDE_BC_OPTIONS, index=bc_index,
            key="backside_BC",
            help=input_tooltip("backside_BC"),
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
# Section 6 — System resources → M9, M10
# ---------------------------------------------------------------------------


def section_6_system_resources(initial: dict | None = None) -> dict:
    """System-resource inputs: wall-plug, cooling, exposure duration."""
    with st.sidebar.expander(SECTION_LABELS["system_resources"], expanded=False):
        eta_wallplug = st.number_input(
            input_label("eta_wallplug"),
            min_value=0.05, max_value=0.50,
            value=float(_initial(initial, "eta_wallplug", 0.30)),
            step=0.01, key="eta_wallplug",
            help=input_tooltip("eta_wallplug"),
        )
        Q_cool_kW = st.number_input(
            _labelled("Q_cool"),
            min_value=0.0, max_value=500.0,
            value=float(_initial(initial, "Q_cool", 15000.0)) / 1000.0,
            step=1.0, key="Q_cool_kW",
            help=input_tooltip("Q_cool"),
        )
        C_thermal_kJK = st.number_input(
            _labelled("C_thermal"),
            min_value=10.0, max_value=5000.0,
            value=float(_initial(initial, "C_thermal", 200e3)) / 1000.0,
            step=10.0, key="C_thermal_kJK",
            help=input_tooltip("C_thermal"),
        )
        dT_max = st.number_input(
            _labelled("dT_max"),
            min_value=5.0, max_value=80.0,
            value=float(_initial(initial, "dT_max", 30.0)),
            step=1.0, key="dT_max",
            help=input_tooltip("dT_max"),
        )
        t_exp = st.number_input(
            _labelled("t_exp"),
            min_value=0.25, max_value=100.0,
            value=float(_initial(initial, "t_exp", 0.25)),
            step=0.25, key="t_exp",
            help=input_tooltip("t_exp"),
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
    """Render all six sidebar sections and return the merged ``user_inputs`` dict.

    ``initial`` is the URL-decoded prefill dict from ``ui/app.py``'s
    session-state latch. When ``None``, each section falls back to its
    SPEC §5.1 default. Section dicts have disjoint key spaces by
    contract, so merge order does not lose any field.
    """
    merged: dict = {}
    merged.update(section_1_laser_source(initial))
    merged.update(section_2_beam_director(initial))
    merged.update(section_3_engagement_geometry(initial))
    merged.update(section_4_atmosphere(initial))
    merged.update(section_5_target_aimpoint(initial))
    merged.update(section_6_system_resources(initial))
    return merged
