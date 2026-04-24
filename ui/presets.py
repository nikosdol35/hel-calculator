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
    "R":           1500.0,
    "H_t":         200.0,
    "v_tgt":       20.0,
    "v_perp":      3.0,
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
    "R":           3000.0,
    "H_t":         500.0,
    "v_tgt":       100.0,       # typical UTM rocket terminal speed
    "v_perp":      15.0,
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
    "R":           10000.0,
    "H_t":         1500.0,
    "v_tgt":       5.0,
    "v_perp":      1.0,
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
_SI_TO_WIDGET: dict[str, tuple[str, object]] = {
    "P0":            ("P0_kW",          lambda v: v / 1000.0),
    "M2":            ("M2",             lambda v: v),
    "D":             ("D_cm",           lambda v: v * 100.0),
    "wavelength":    ("wavelength_um",  lambda v: v * 1e6),
    "eta_opt":       ("eta_opt",        lambda v: v),
    "sigma_jit":     ("sigma_jit_urad", lambda v: v * 1e6),
    "H_e":           ("H_e",            lambda v: v),
    "R":             ("R",              lambda v: v),
    "H_t":           ("H_t",            lambda v: v),
    "v_tgt":         ("v_tgt",          lambda v: v),
    "v_perp":        ("v_perp",         lambda v: v),
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


__all__ = [
    "PRESET_PARAMETERS",
    "apply_to_session_state",
]
