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
    """Engagement-geometry inputs (SPEC v2.0 §3 M3 contract).

    The director is assumed to track the target; the engagement-window
    duration follows the target's threat trajectory from initial
    detection at R_detect down to the user-defined standoff range
    R_min. Two trajectory geometries supported:

      * head-on: target closes along the line of sight at v_tgt
      * lateral: target flies a perpendicular pass with closest-
        approach distance R_min at speed v_tgt
    """
    geometry_options = ("head-on closing", "lateral pass")
    geometry_keys = ("head_on", "lateral")
    initial_geometry = _initial(initial, "engagement_geometry", "head_on")
    initial_idx = 0 if initial_geometry == "head_on" else 1

    with st.sidebar.expander(SECTION_LABELS["engagement_geometry"], expanded=True):
        engagement_geometry_label = st.selectbox(
            input_label("engagement_geometry"),
            options=geometry_options,
            index=initial_idx,
            key="engagement_geometry_select",
            help=input_tooltip("engagement_geometry"),
        )
        engagement_geometry = geometry_keys[
            geometry_options.index(engagement_geometry_label)
        ]

        H_e = st.number_input(
            _labelled("H_e"),
            min_value=0.0, max_value=3000.0,
            value=float(_initial(initial, "H_e", 2.0)),
            step=1.0, key="H_e",
            help=input_tooltip("H_e"),
        )
        R_detect = st.number_input(
            _labelled("R_detect"),
            min_value=50.0, max_value=50000.0,
            value=float(_initial(initial, "R_detect", 1500.0)),
            step=50.0, key="R_detect",
            help=input_tooltip("R_detect"),
        )
        R_min = st.number_input(
            _labelled("R_min"),
            min_value=10.0, max_value=5000.0,
            value=float(_initial(initial, "R_min", 100.0)),
            step=10.0, key="R_min",
            help=input_tooltip("R_min"),
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
    return {
        "H_e": H_e,
        "R_detect": R_detect,
        "R_min": R_min,
        "H_t": H_t,
        "v_tgt": v_tgt,
        "engagement_geometry": engagement_geometry,
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
# DRI Analyzer sections — Sensor, Atmosphere, Target & Criteria.
#
# Independent of the HEL physics chain. All keys are prefixed ``dri_``
# so they cannot collide with HEL inputs. Default-collapsed expanders
# so a HEL-only user sees the same sidebar they had before.
# ---------------------------------------------------------------------------


def section_7_dri_sensor(initial: dict | None = None) -> dict:
    """DRI sensor inputs: resolution, FOVs, focal length, f-number."""
    from physics.dri_analyzer import (  # local import — keeps panels.py
        WAVELENGTH_BANDS,                # cheap to load when DRI is disabled
    )
    _ = WAVELENGTH_BANDS  # imported for downstream sections; see _atmosphere
    with st.sidebar.expander(SECTION_LABELS["dri_sensor"], expanded=False):
        n_pixels_h = st.number_input(
            _labelled("dri_n_pixels_h"),
            min_value=320, max_value=8192,
            value=int(_initial(initial, "dri_n_pixels_h", 1920)),
            step=160, key="dri_n_pixels_h",
            help=input_tooltip("dri_n_pixels_h"),
        )
        n_pixels_v = st.number_input(
            _labelled("dri_n_pixels_v"),
            min_value=240, max_value=8192,
            value=int(_initial(initial, "dri_n_pixels_v", 1080)),
            step=120, key="dri_n_pixels_v",
            help=input_tooltip("dri_n_pixels_v"),
        )
        nfov_deg = st.number_input(
            _labelled("dri_nfov_deg"),
            min_value=0.05, max_value=60.0,
            value=float(_initial(initial, "dri_nfov_deg", 1.5)),
            step=0.1, key="dri_nfov_deg",
            help=input_tooltip("dri_nfov_deg"),
        )
        wfov_deg = st.number_input(
            _labelled("dri_wfov_deg"),
            min_value=1.0, max_value=120.0,
            value=float(_initial(initial, "dri_wfov_deg", 25.0)),
            step=1.0, key="dri_wfov_deg",
            help=input_tooltip("dri_wfov_deg"),
        )
        focal_length_mm = st.number_input(
            _labelled("dri_focal_length_mm"),
            min_value=5.0, max_value=5000.0,
            value=float(_initial(initial, "dri_focal_length_mm", 200.0)),
            step=10.0, key="dri_focal_length_mm",
            help=input_tooltip("dri_focal_length_mm"),
        )
        f_number = st.number_input(
            _labelled("dri_f_number"),
            min_value=1.0, max_value=22.0,
            value=float(_initial(initial, "dri_f_number", 2.8)),
            step=0.1, key="dri_f_number",
            help=input_tooltip("dri_f_number"),
        )
    return {
        "dri_n_pixels_h": int(n_pixels_h),
        "dri_n_pixels_v": int(n_pixels_v),
        "dri_nfov_deg": float(nfov_deg),
        "dri_wfov_deg": float(wfov_deg),
        "dri_focal_length_mm": float(focal_length_mm),
        "dri_f_number": float(f_number),
    }


def section_8_dri_atmosphere(initial: dict | None = None) -> dict:
    """DRI atmosphere inputs: wavelength band, Cn² preset, visibility, C₀."""
    from physics.dri_analyzer import CN2_PRESETS, WAVELENGTH_BANDS

    band_options = list(WAVELENGTH_BANDS.keys())
    cn2_options = list(CN2_PRESETS.keys())

    initial_band = _initial(initial, "dri_band", band_options[0])
    if initial_band not in band_options:
        initial_band = band_options[0]
    initial_cn2 = _initial(initial, "dri_cn2_preset", "Moderate (canonical mid-altitude)")
    if initial_cn2 not in cn2_options:
        initial_cn2 = cn2_options[3]  # "Moderate" — index 3

    with st.sidebar.expander(SECTION_LABELS["dri_atmosphere"], expanded=False):
        band = st.selectbox(
            input_label("dri_band"),
            options=band_options,
            index=band_options.index(initial_band),
            key="dri_band",
            help=input_tooltip("dri_band"),
        )
        cn2_preset = st.selectbox(
            input_label("dri_cn2_preset"),
            options=cn2_options,
            index=cn2_options.index(initial_cn2),
            key="dri_cn2_preset",
            help=input_tooltip("dri_cn2_preset"),
        )
        visibility_km = st.number_input(
            _labelled("dri_visibility_km"),
            min_value=0.5, max_value=100.0,
            value=float(_initial(initial, "dri_visibility_km", 23.0)),
            step=1.0, key="dri_visibility_km",
            help=input_tooltip("dri_visibility_km"),
        )
        C0 = st.number_input(
            input_label("dri_C0"),
            min_value=0.05, max_value=1.00,
            value=float(_initial(initial, "dri_C0", 0.30)),
            step=0.05, key="dri_C0",
            help=input_tooltip("dri_C0"),
        )
    return {
        "dri_band": str(band),
        "dri_cn2_preset": str(cn2_preset),
        "dri_visibility_km": float(visibility_km),
        "dri_C0": float(C0),
    }


def section_9_dri_target(initial: dict | None = None) -> dict:
    """DRI target & criteria: target preset (or custom h), probability,
    Johnson cycles overrides."""
    from physics.dri_analyzer import TARGET_PRESETS

    target_options = list(TARGET_PRESETS.keys()) + ["Custom"]
    initial_target = _initial(initial, "dri_target_preset", "NATO standard")
    if initial_target not in target_options:
        initial_target = "NATO standard"

    prob_options = ("50 %", "80 %", "95 %")
    prob_to_float = {"50 %": 0.50, "80 %": 0.80, "95 %": 0.95}
    # Widget key intentionally distinct from the dict key ``dri_probability``.
    # The output dict reports probability as a float (0.50 / 0.80 / 0.95);
    # the widget shows label strings ("50 %" / "80 %" / "95 %"). Sharing the
    # same name would write a float to a session-state slot the widget reads
    # as a string-options selectbox — a ValueError on every preset apply
    # because 0.50 is not in ("50 %", "80 %", "95 %"). See the 2026-04-26
    # hotfix that renamed this key.
    _PROB_WIDGET_KEY = "_dri_probability_select"
    initial_prob_float = float(_initial(initial, "dri_probability", 0.50))
    initial_prob_label = (
        "50 %" if initial_prob_float == 0.50 else
        "80 %" if initial_prob_float == 0.80 else
        "95 %" if initial_prob_float == 0.95 else
        "50 %"
    )

    with st.sidebar.expander(SECTION_LABELS["dri_target"], expanded=False):
        target_preset = st.selectbox(
            input_label("dri_target_preset"),
            options=target_options,
            index=target_options.index(initial_target),
            key="dri_target_preset",
            help=input_tooltip("dri_target_preset"),
        )
        if target_preset == "Custom":
            target_h_m = st.number_input(
                _labelled("dri_target_h_m"),
                min_value=0.05, max_value=50.0,
                value=float(_initial(initial, "dri_target_h_m", 1.0)),
                step=0.1, key="dri_target_h_m",
                help=input_tooltip("dri_target_h_m"),
            )
        else:
            target_h_m = None  # Not used; compute() reads the preset directly.

        probability_label = st.selectbox(
            input_label("dri_probability"),
            options=prob_options,
            index=prob_options.index(initial_prob_label),
            key=_PROB_WIDGET_KEY,
            help=input_tooltip("dri_probability"),
        )
        probability = prob_to_float[probability_label]

        st.caption("Johnson cycles (N₅₀) — override defaults if needed:")
        n_cycles_D = st.number_input(
            input_label("dri_n_cycles_D"),
            min_value=0.1, max_value=30.0,
            value=float(_initial(initial, "dri_n_cycles_D", 1.0)),
            step=0.1, key="dri_n_cycles_D",
            help=input_tooltip("dri_n_cycles_D"),
        )
        n_cycles_R = st.number_input(
            input_label("dri_n_cycles_R"),
            min_value=0.1, max_value=30.0,
            value=float(_initial(initial, "dri_n_cycles_R", 4.0)),
            step=0.5, key="dri_n_cycles_R",
            help=input_tooltip("dri_n_cycles_R"),
        )
        n_cycles_I = st.number_input(
            input_label("dri_n_cycles_I"),
            min_value=0.1, max_value=30.0,
            value=float(_initial(initial, "dri_n_cycles_I", 8.0)),
            step=0.5, key="dri_n_cycles_I",
            help=input_tooltip("dri_n_cycles_I"),
        )

    out: dict = {
        "dri_target_preset": str(target_preset),
        "dri_probability": float(probability),
        "dri_n_cycles_D": float(n_cycles_D),
        "dri_n_cycles_R": float(n_cycles_R),
        "dri_n_cycles_I": float(n_cycles_I),
    }
    if target_h_m is not None:
        out["dri_target_h_m"] = float(target_h_m)
    return out


# ---------------------------------------------------------------------------
# Aggregator.
# ---------------------------------------------------------------------------


def collect_hel(initial: dict | None = None) -> dict:
    """Render the six HEL sidebar sections only and return the merged dict.

    Used by the HEL Calculator page in the multipage refactor — keeps
    the HEL sidebar uncluttered with DRI inputs. Sections 1–6:
    laser source, beam director, engagement geometry, atmosphere,
    target & aimpoint, system resources.
    """
    merged: dict = {}
    merged.update(section_1_laser_source(initial))
    merged.update(section_2_beam_director(initial))
    merged.update(section_3_engagement_geometry(initial))
    merged.update(section_4_atmosphere(initial))
    merged.update(section_5_target_aimpoint(initial))
    merged.update(section_6_system_resources(initial))
    return merged


def collect_dri(initial: dict | None = None) -> dict:
    """Render the three DRI sidebar sections only and return the merged dict.

    Used by the DRI Analyzer page in the multipage refactor — keeps
    the DRI sidebar uncluttered with HEL inputs. Sections 7–9:
    sensor, atmosphere, target & criteria.
    """
    merged: dict = {}
    merged.update(section_7_dri_sensor(initial))
    merged.update(section_8_dri_atmosphere(initial))
    merged.update(section_9_dri_target(initial))
    return merged


def collect_all(initial: dict | None = None) -> dict:
    """Render all six HEL sidebar sections plus the three DRI sections,
    returning the merged ``user_inputs`` dict.

    ``initial`` is the URL-decoded prefill dict from the page script's
    session-state latch. When ``None``, each section falls back to its
    SPEC §5.1 default. Section dicts have disjoint key spaces by
    contract (DRI inputs use the ``dri_`` prefix), so merge order does
    not lose any field.

    In the multipage refactor each page calls only the half it needs
    (``collect_hel`` / ``collect_dri``); ``collect_all`` is preserved
    as a convenience for any caller that wants the unified view.
    """
    return {
        **collect_hel(initial),
        **collect_dri(initial),
    }
