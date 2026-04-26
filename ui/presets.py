"""Named engagement-scenario presets driving the sidebar preset dropdown.

Each preset is a dict whose keys and units match the ``user_inputs``
contract the orchestrator consumes (SI values, same dict shape the six
``ui/panels.section_*`` functions return). Selecting a preset in the
sidebar writes these values through to ``st.session_state`` under the
widget keys ``ui/panels.py`` binds to, then triggers a Streamlit rerun
so the sidebar re-renders with the new values pre-filled.

The four preset names were approved on Phase 3 PR 1 and are defined in
``ui/labels.py`` under ``PRESET_LABELS``. Underlying parameter values
are defensible reference points — not validated engagement solutions.
The user is expected to tweak any preset after selecting it.

References:
    SPEC.md §5.1 — input dict contract, sanity ranges.
    tests/conftest.py — ``canonical_inputs`` fixture, which the
        ``c_uas_short_range`` preset mirrors so the default Run Analysis
        path reproduces the canonical test case bit-for-bit.
    ui/labels.py — ``PRESET_LABELS`` (display names, stable ordering).
    ui/panels.py — session-state keys the sidebar widgets bind to.
"""

from __future__ import annotations

from typing import Any, Callable


# ---------------------------------------------------------------------------
# Preset parameter dicts.
# ---------------------------------------------------------------------------
# All values are in the SI units the orchestrator expects. The sidebar
# unit-conversion layer in ``ui/panels.py`` handles display units
# (kW, cm, µm, µrad, kJ/K, etc.); presets are stored in SI so the same
# dict shape feeds straight into ``physics/orchestrator.run_full_chain``.

_C_UAS_SHORT_RANGE: dict = {
    # Canonical SPEC §5.1 set — mirrors tests/conftest.py::canonical_inputs.
    # Represents a 3 kW laser engaging a Class-1 UAS at 1.5 km slant range.
    "P0":          3000.0,      # 3 kW
    "M2":          1.2,
    "D":           0.10,        # 10 cm
    "wavelength":  1.07e-6,     # fibre
    "eta_opt":     0.85,
    "sigma_jit":   10e-6,       # 10 µrad RMS per axis
    "H_e":         2.0,
    "R_detect":    1500.0,
    "R_min":       100.0,
    "engagement_geometry": "head_on",
    "H_t":         200.0,
    "v_tgt":       20.0,
    "V":           23.0,        # km visibility (clear)
    "RH":          0.60,
    "T_ambient":   300.0,       # K
    "P_atm":       101325.0,
    "cn2_model":   "HV_5_7",
    "Cn2_value":   1e-14,
    "Cn2_ground":  1.7e-14,
    "v_HV":        21.0,
    "d_aim":       0.05,        # 5 cm aimpoint
    "material":    "CFRP",
    "thickness":   0.002,       # 2 mm
    "backside_BC": "insulated",
    "eta_wallplug": 0.30,
    "Q_cool":       15000.0,    # W
    "C_thermal":    200e3,      # J/K
    "dT_max":       30.0,       # K
    "t_exp":        0.25,       # s (MPE-safety exposure)
}

_COUNTER_ROCKET: dict = {
    # 30 kW source engaging a small unguided rocket at 3 km. Faster
    # target (100 m/s crossing, per light-artillery ballistic regime)
    # and thicker composite casing (4 mm CFRP). Visibility reduced to
    # 15 km (light haze) because rocket engagements frequently happen
    # under less-than-clear conditions.
    "P0":          30000.0,
    "M2":          1.3,
    "D":           0.15,        # 15 cm
    "wavelength":  1.07e-6,
    "eta_opt":     0.85,
    "sigma_jit":   8e-6,        # tighter jitter on heavier mount
    "H_e":         5.0,
    "R_detect":    3000.0,
    "R_min":       200.0,
    "engagement_geometry": "head_on",
    "H_t":         500.0,
    "v_tgt":       100.0,       # typical UTM rocket terminal speed
    "V":           15.0,
    "RH":          0.55,
    "T_ambient":   295.0,
    "P_atm":       101325.0,
    "cn2_model":   "HV_5_7",
    "Cn2_value":   1e-14,
    "Cn2_ground":  1.7e-14,
    "v_HV":        21.0,
    "d_aim":       0.08,        # 8 cm aimpoint
    "material":    "CFRP",
    "thickness":   0.004,       # 4 mm casing
    "backside_BC": "insulated",
    "eta_wallplug": 0.30,
    "Q_cool":       50000.0,
    "C_thermal":    500e3,
    "dT_max":       30.0,
    "t_exp":        0.25,
}

_LONG_RANGE_SURVEILLANCE: dict = {
    # 10 kW source, 10 km standoff — deterrence / dazzle / extended
    # counter-ISR use case. Slow-moving target (5 m/s drift), thin
    # polycarbonate sensor window. Atmosphere clearer (25 km) because
    # long-range paths already lose a large share of flux to extinction.
    "P0":          10000.0,
    "M2":          1.2,
    "D":           0.20,        # 20 cm (larger aperture buys divergence)
    "wavelength":  1.07e-6,
    "eta_opt":     0.85,
    "sigma_jit":   5e-6,
    "H_e":         10.0,
    "R_detect":    10000.0,
    "R_min":       500.0,
    "engagement_geometry": "lateral",
    "H_t":         1500.0,
    "v_tgt":       5.0,
    "V":           25.0,
    "RH":          0.50,
    "T_ambient":   293.0,
    "P_atm":       101325.0,
    "cn2_model":   "HV_5_7",
    "Cn2_value":   1e-14,
    "Cn2_ground":  1.7e-14,
    "v_HV":        21.0,
    "d_aim":       0.10,        # 10 cm aimpoint (sensor face)
    "material":    "polycarbonate",
    "thickness":   0.003,
    "backside_BC": "insulated",
    "eta_wallplug": 0.30,
    "Q_cool":       20000.0,
    "C_thermal":    300e3,
    "dT_max":       30.0,
    "t_exp":        0.25,
}

# Custom preset is intentionally not a dict — selecting it leaves every
# widget's current session-state value in place. ``apply_to_session_state``
# short-circuits when the preset key is ``"custom"``.
PRESET_PARAMETERS: dict[str, dict] = {
    "c_uas_short_range":       _C_UAS_SHORT_RANGE,
    "counter_rocket":          _COUNTER_ROCKET,
    "long_range_surveillance": _LONG_RANGE_SURVEILLANCE,
}


# ---------------------------------------------------------------------------
# Widget-key mapping.
# ---------------------------------------------------------------------------
# The sidebar in ``ui/panels.py`` binds every ``number_input`` /
# ``selectbox`` / ``slider`` / ``checkbox`` to a Streamlit
# ``session_state`` key. Presets are stored in SI so this mapping
# records both the display-unit key and the conversion from SI. A
# ``session_state`` write under each key is what makes the new values
# appear in the sidebar on the next rerun.

# Each entry is ``(session_state_key, convert_from_si)``.
_SI_TO_WIDGET: dict[str, tuple[str, Callable[[Any], Any]]] = {
    "P0":            ("P0_kW",          lambda v: v / 1000.0),
    "M2":            ("M2",             lambda v: v),
    "D":             ("D_cm",           lambda v: v * 100.0),
    "wavelength":    ("wavelength_um",  lambda v: v * 1e6),
    "eta_opt":       ("eta_opt",        lambda v: v),
    "sigma_jit":     ("sigma_jit_urad", lambda v: v * 1e6),
    "H_e":           ("H_e",            lambda v: v),
    "R_detect":      ("R_detect",       lambda v: v),
    "R_min":         ("R_min",          lambda v: v),
    "engagement_geometry": (
        "engagement_geometry_select",
        lambda v: "head-on closing" if v == "head_on" else "lateral pass",
    ),
    "H_t":           ("H_t",            lambda v: v),
    "v_tgt":         ("v_tgt",          lambda v: v),
    "V":             ("V_km",           lambda v: v),
    "RH":            ("RH_pct",         lambda v: v * 100.0),
    "T_ambient":     ("T_ambient_C",    lambda v: v - 273.15),
    "cn2_model":     ("cn2_model",      lambda v: v),
    "Cn2_value":     ("Cn2_value",      lambda v: v),
    "Cn2_ground":    ("Cn2_ground",     lambda v: v),
    "v_HV":          ("v_HV",           lambda v: v),
    "d_aim":         ("d_aim_cm",       lambda v: v * 100.0),
    "material":      ("material",       lambda v: v),
    "thickness":     ("thickness_mm",   lambda v: v * 1000.0),
    "backside_BC":   ("backside_BC",    lambda v: v),
    "eta_wallplug":  ("eta_wallplug",   lambda v: v),
    "Q_cool":        ("Q_cool_kW",      lambda v: v / 1000.0),
    "C_thermal":     ("C_thermal_kJK",  lambda v: v / 1000.0),
    "dT_max":        ("dT_max",         lambda v: v),
    "t_exp":         ("t_exp",          lambda v: v),
}


# ---------------------------------------------------------------------------
# Public API.
# ---------------------------------------------------------------------------


def apply_to_session_state(session_state, preset_key: str) -> bool:
    """Write a preset's values into Streamlit session-state.

    ``session_state`` is ``st.session_state`` from the caller (we accept
    it as a parameter so this module does not import ``streamlit`` at
    the top level — keeps the module cheaply importable from tests).

    Returns ``True`` if the session-state was actually written to
    (i.e. the preset is one of the three pre-built scenarios); returns
    ``False`` for ``"custom"`` (the widget values are left alone so the
    user keeps whatever they last edited).

    The ``A_lambda`` override is reset to off by every preset — none of
    the pre-built scenarios pin an override value, so the orchestrator
    routes to the M8 material-table default (surfacing any HIGH-
    UNCERTAINTY flag on the Diagnostics tab).
    """
    if preset_key == "custom":
        return False
    preset = PRESET_PARAMETERS.get(preset_key)
    if preset is None:
        return False

    for si_key, value in preset.items():
        mapping = _SI_TO_WIDGET.get(si_key)
        if mapping is None:
            continue
        widget_key, convert = mapping
        session_state[widget_key] = convert(value)

    # A_λ override: force off so the material-table default applies.
    session_state["_A_lambda_override"] = False
    # Drop any pinned override value so the sidebar slider does not
    # re-appear pre-filled on the next rerun.
    session_state.pop("A_lambda", None)
    return True


# ---------------------------------------------------------------------------
# DRI Analyzer sensor presets (multipage PR 2, 2026-04-26).
# ---------------------------------------------------------------------------
# Independent of the HEL preset registry above. Each preset is a dict
# whose keys match the DRI input session-state keys exactly — DRI inputs
# are already in display units (deg, mm, px) so no SI → display
# conversion layer is needed; the values written to session_state ARE
# the widget values directly.

_EO_DAYTIME_SURVEILLANCE: dict = {
    # Mid-tier security camera with a long-zoom lens. Daylight, clear
    # weather, person-class target.
    "dri_n_pixels_h": 1920, "dri_n_pixels_v": 1080,
    "dri_nfov_deg":   1.5,  "dri_wfov_deg":   25.0,
    "dri_focal_length_mm": 200.0, "dri_f_number": 2.8,
    "dri_band":       "Visible",
    "dri_cn2_preset": "Moderate (canonical mid-altitude)",
    "dri_visibility_km": 23.0, "dri_C0": 0.30,
    "dri_target_preset": "Person standing",
    "dri_probability": 0.50,
    "dri_n_cycles_D": 1.0, "dri_n_cycles_R": 4.0, "dri_n_cycles_I": 8.0,
}

_EO_LONG_RANGE_SURVEILLANCE: dict = {
    # 4K sensor on a 600 mm telephoto. Counter-vehicle / overwatch
    # configuration with a sub-degree NFOV.
    "dri_n_pixels_h": 3840, "dri_n_pixels_v": 2160,
    "dri_nfov_deg":   0.5,  "dri_wfov_deg":   10.0,
    "dri_focal_length_mm": 600.0, "dri_f_number": 4.0,
    "dri_band":       "Visible",
    "dri_cn2_preset": "Moderate (canonical mid-altitude)",
    "dri_visibility_km": 30.0, "dri_C0": 0.30,
    "dri_target_preset": "Car / sedan",
    "dri_probability": 0.50,
    "dri_n_cycles_D": 1.0, "dri_n_cycles_R": 4.0, "dri_n_cycles_I": 8.0,
}

_SWIR_NIGHT_VISION: dict = {
    # SWIR (1.55 µm) sensor, eye-safe NIR illuminator-assisted. Lower
    # contrast, dawn / overcast turbulence regime.
    "dri_n_pixels_h": 1280, "dri_n_pixels_v": 1024,
    "dri_nfov_deg":   2.0,  "dri_wfov_deg":   20.0,
    "dri_focal_length_mm": 150.0, "dri_f_number": 2.8,
    "dri_band":       "SWIR",
    "dri_cn2_preset": "Weak (overcast / dawn)",
    "dri_visibility_km": 15.0, "dri_C0": 0.40,
    "dri_target_preset": "Person standing",
    "dri_probability": 0.50,
    "dri_n_cycles_D": 1.0, "dri_n_cycles_R": 4.0, "dri_n_cycles_I": 8.0,
}

_MWIR_THERMAL_IMAGER: dict = {
    # 640x512 MWIR cooled-array thermal imager. Tuned for small-UAS
    # (Group-1) detection — the canonical C-UAS thermal use case.
    "dri_n_pixels_h": 640,  "dri_n_pixels_v": 512,
    "dri_nfov_deg":   2.0,  "dri_wfov_deg":   18.0,
    "dri_focal_length_mm": 100.0, "dri_f_number": 4.0,
    "dri_band":       "MWIR",
    "dri_cn2_preset": "Moderate (canonical mid-altitude)",
    "dri_visibility_km": 23.0, "dri_C0": 0.50,
    "dri_target_preset": "DJI Mavic 4 (Group-1 UAS)",
    "dri_probability": 0.50,
    "dri_n_cycles_D": 1.0, "dri_n_cycles_R": 4.0, "dri_n_cycles_I": 8.0,
}

_LWIR_THERMAL_IMAGER: dict = {
    # 640x480 LWIR uncooled microbolometer. Wider WFOV, person-class
    # target — common ground-surveillance / vehicle-mounted scope.
    "dri_n_pixels_h": 640,  "dri_n_pixels_v": 480,
    "dri_nfov_deg":   2.5,  "dri_wfov_deg":   24.0,
    "dri_focal_length_mm": 75.0, "dri_f_number": 1.4,
    "dri_band":       "LWIR",
    "dri_cn2_preset": "Moderate (canonical mid-altitude)",
    "dri_visibility_km": 23.0, "dri_C0": 0.50,
    "dri_target_preset": "Person standing",
    "dri_probability": 0.50,
    "dri_n_cycles_D": 1.0, "dri_n_cycles_R": 4.0, "dri_n_cycles_I": 8.0,
}

DRI_PRESET_PARAMETERS: dict[str, dict] = {
    "eo_daytime_surveillance":    _EO_DAYTIME_SURVEILLANCE,
    "eo_long_range_surveillance": _EO_LONG_RANGE_SURVEILLANCE,
    "swir_night_vision":          _SWIR_NIGHT_VISION,
    "mwir_thermal_imager":        _MWIR_THERMAL_IMAGER,
    "lwir_thermal_imager":        _LWIR_THERMAL_IMAGER,
}


#: Translation map: dict-key ``dri_probability`` (float in [0, 1]) to the
#: label string the selectbox widget actually stores in session_state.
#: The widget's session-state key (``_dri_probability_select`` in
#: ``ui/panels.py::section_9_dri_target``) is intentionally distinct from
#: the dict key ``dri_probability`` so the float and the label cannot
#: collide. See the 2026-04-26 hotfix that introduced this split.
_DRI_PROB_FLOAT_TO_LABEL: dict[float, str] = {
    0.50: "50 %",
    0.80: "80 %",
    0.95: "95 %",
}
_DRI_PROB_WIDGET_KEY: str = "_dri_probability_select"


def apply_dri_preset_to_session_state(session_state, preset_key: str) -> bool:
    """Mirror of ``apply_to_session_state`` for DRI presets.

    DRI inputs are already in display units (deg, mm, px) so this
    function writes preset values straight into ``session_state``
    without the SI → widget unit-conversion layer that the HEL preset
    pathway uses. Returns ``True`` when a known preset is applied,
    ``False`` for the ``"custom"`` sentinel (or any unknown key) so
    the caller can keep the user's current widget edits.

    Special case: ``dri_probability`` in the preset is a float (0.50 /
    0.80 / 0.95), but the corresponding widget is a string-options
    selectbox. We additionally write the label form to the widget's
    actual session-state key so the widget renders the new value
    rather than choking on a float-vs-string options mismatch.
    """
    if preset_key == "custom":
        return False
    preset = DRI_PRESET_PARAMETERS.get(preset_key)
    if preset is None:
        return False
    for widget_key, value in preset.items():
        session_state[widget_key] = value
    # Translation step: keep the float in session_state[dri_probability]
    # for any future caller that reads it directly, AND write the label
    # form to the widget's actual key so the selectbox picks up the new
    # value when the page re-renders.
    prob_float = preset.get("dri_probability")
    if prob_float is not None and prob_float in _DRI_PROB_FLOAT_TO_LABEL:
        session_state[_DRI_PROB_WIDGET_KEY] = (
            _DRI_PROB_FLOAT_TO_LABEL[prob_float]
        )
    return True


__all__ = [
    "PRESET_PARAMETERS",
    "DRI_PRESET_PARAMETERS",
    "apply_to_session_state",
    "apply_dri_preset_to_session_state",
]
