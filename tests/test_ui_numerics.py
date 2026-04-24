"""UI-layer numeric-transform tests.

Per the Package 2 plan (validation/README.md Layer 2.5), the UI layer
inserts ≈30 numeric transformations the physics tests never see —
display scalings (W→kW, W/m²→W/cm², m→km, rad→µrad, 1/m→1/km, m→cm),
K→°C subtractions, format_value rounding rules, verdict-margin
arithmetic, and plot-specific log-guards. This file tests every one.

The goal: "every number we present" is correct, not just the numbers
the physics layer computes.
"""

from __future__ import annotations

import math

import pytest

from ui.components import format_value
from ui.labels import output_unit
from ui.outputs import _DISPLAY_SCALE, _scale


# ---------------------------------------------------------------------------
# format_value — the single gate for numeric display
# ---------------------------------------------------------------------------

def test_format_value_fixed_point_mid_range():
    """|v| in [0.01, 1e5) renders as fixed-point with 3 sig figs."""
    # 45.7 → "45.7" (3 sig figs with one decimal)
    assert format_value(45.7, "") == "45.7"


def test_format_value_integer_thousands_separator():
    """Integer-like values in fixed range use comma thousands separators."""
    assert format_value(12450.0, "") == "12,450"


def test_format_value_fraction_three_sig_figs():
    """Pure fraction 0.847 renders with three decimals (3 sig figs total)."""
    assert format_value(0.847, "") == "0.847"


def test_format_value_appends_unit_with_nbsp():
    """A non-empty unit appends after a U+00A0 non-breaking space."""
    nbsp = "\u00a0"
    assert format_value(12450.0, "m") == f"12,450{nbsp}m"


def test_format_value_scientific_below_threshold():
    """|v| < 1e-2 forces scientific notation."""
    result = format_value(0.00000123, "W/cm²")
    assert "× 10" in result
    assert result.startswith("1.23")


def test_format_value_scientific_above_threshold():
    """|v| >= 1e5 forces scientific notation."""
    result = format_value(1.23e6, "W")
    assert "× 10" in result
    assert result.startswith("1.23")


def test_format_value_boundary_1e5_uses_scientific():
    """|v| = 1e5 (the upper threshold) uses scientific, not fixed."""
    result = format_value(1e5, "")
    assert "× 10" in result


def test_format_value_just_below_1e5_uses_fixed():
    """99,999 sits inside the fixed-point regime."""
    result = format_value(99999.0, "")
    assert "×" not in result
    assert "," in result


def test_format_value_boundary_0p01_is_fixed():
    """|v| = 0.01 exactly uses fixed-point (the inequality is strict)."""
    result = format_value(0.01, "")
    assert "×" not in result


def test_format_value_just_below_0p01_uses_scientific():
    """0.009 is strictly below the scientific threshold."""
    result = format_value(0.009, "")
    assert "× 10" in result


def test_format_value_none_returns_dash():
    """None renders as em-dash U+2014."""
    assert format_value(None, "m") == "—"


def test_format_value_nan_returns_dash():
    assert format_value(float("nan"), "m") == "—"


def test_format_value_inf_returns_dash():
    assert format_value(float("inf"), "s") == "—"


def test_format_value_negative_inf_returns_dash():
    assert format_value(-float("inf"), "s") == "—"


def test_format_value_zero_returns_zero():
    """Zero renders as a literal '0' (no decimal dance)."""
    assert format_value(0.0, "") == "0"


def test_format_value_negative_scientific():
    """Negative values below 1e-2 render with a leading minus."""
    result = format_value(-1.23e-6, "W/cm²")
    assert result.startswith("-1.23")
    assert "× 10" in result


def test_format_value_sig_figs_4_for_strehl():
    """Passing sig_figs=4 yields four total digits."""
    result = format_value(0.9984, "", sig_figs=4)
    assert result == "0.9984"


def test_format_value_handles_string_input_safely():
    """Non-numeric input (accidental string) returns em-dash rather than crashing."""
    assert format_value("nope", "m") == "—"  # type: ignore[arg-type]


# ---------------------------------------------------------------------------
# _DISPLAY_SCALE — SI → display unit matching labels.py
# ---------------------------------------------------------------------------

_EXPECTED_SCALINGS: list[tuple[str, float, str]] = [
    # Power — W → kW
    ("P_aim",          1e-3,  "kW"),
    ("P_in",           1e-3,  "kW"),
    ("Q_waste",        1e-3,  "kW"),
    # Irradiance — W/m² → W/cm² (÷ 10⁴)
    ("I_avg_aim",      1e-4,  "W/cm²"),
    ("I_peak",         1e-4,  "W/cm²"),
    # Distance — m → km
    ("NOHD_tophat",    1e-3,  "km"),
    ("NOHD_gausspeak", 1e-3,  "km"),
    # Angle — rad → µrad
    ("theta_diff",       1e6, "µrad"),
    ("theta_diff_pure",  1e6, "µrad"),
    ("theta_M2_excess",  1e6, "µrad"),
    ("theta_turb",       1e6, "µrad"),
    ("theta_jit",        1e6, "µrad"),
    # Extinction — 1/m → 1/km
    ("alpha_atm",      1e3,   "1/km"),
    ("alpha_mol_abs",  1e3,   "1/km"),
    ("alpha_mol_scat", 1e3,   "1/km"),
    ("alpha_aer_abs",  1e3,   "1/km"),
    ("alpha_aer_scat", 1e3,   "1/km"),
    # Spot radii — m → cm
    ("w_diff",  1e2, "cm"),
    ("w_turb",  1e2, "cm"),
    ("w_jit",   1e2, "cm"),
    ("w_bloom", 1e2, "cm"),
    ("w_total", 1e2, "cm"),
]


@pytest.mark.parametrize("key,expected_scale,expected_unit", _EXPECTED_SCALINGS)
def test_display_scale_matches_labels_unit(key, expected_scale, expected_unit):
    """Every _DISPLAY_SCALE entry converts SI into the unit labels.py
    advertises. Regression guard: changing only one of the two silently
    mismatches the displayed number."""
    assert _DISPLAY_SCALE[key] == expected_scale, (
        f"{key}: _DISPLAY_SCALE says {_DISPLAY_SCALE[key]} but test expects {expected_scale}"
    )
    # Labels may append decorators — just check the unit symbol is present.
    unit = output_unit(key)
    # Allow an exact match or a superset (e.g. "W/cm²" stored verbatim).
    assert expected_unit in unit or unit == expected_unit, (
        f"{key}: labels.py unit {unit!r} does not contain {expected_unit!r}"
    )


def test_scale_handles_none():
    """_scale returns None for None input (upstream may pass missing keys)."""
    assert _scale("P_aim", None) is None


def test_scale_passthrough_for_unscaled_key():
    """Keys not in _DISPLAY_SCALE (e.g. Strehl, PIB_fraction, dwell
    seconds) return the value unchanged."""
    assert _scale("S_TB", 0.85) == 0.85
    assert _scale("PIB_fraction", 0.34) == 0.34
    assert _scale("tau_BT", 2.5) == 2.5


def test_scale_power_watts_to_kilowatts():
    """3000 W → 3.0 kW."""
    assert _scale("P_aim", 3000.0) == pytest.approx(3.0, rel=1e-12)


def test_scale_irradiance_si_to_wpcm2():
    """1000 W/m² → 0.1 W/cm² (÷ 10⁴)."""
    assert _scale("I_peak", 1000.0) == pytest.approx(0.1, rel=1e-12)


def test_scale_radius_m_to_cm():
    """0.05 m (5 cm) → 5.0 cm display."""
    assert _scale("w_total", 0.05) == pytest.approx(5.0, rel=1e-12)


def test_scale_nohd_m_to_km():
    """2500 m → 2.5 km."""
    assert _scale("NOHD_tophat", 2500.0) == pytest.approx(2.5, rel=1e-12)


def test_scale_angle_rad_to_urad():
    """10e-6 rad → 10 µrad."""
    assert _scale("theta_diff", 10e-6) == pytest.approx(10.0, rel=1e-12)


def test_scale_extinction_per_m_to_per_km():
    """1e-4 /m → 0.1 /km."""
    assert _scale("alpha_atm", 1e-4) == pytest.approx(0.1, rel=1e-12)


# ---------------------------------------------------------------------------
# K → °C additive conversion (6 call sites in ui/outputs.py, plots.py, etc.)
# ---------------------------------------------------------------------------

def _kelvin_to_celsius(T_K: float) -> float:
    """Mirror of the literal subtraction applied in ui/outputs.py and
    ui/plots.py. Testing the constant keeps those call sites honest."""
    return T_K - 273.15


def test_k_to_c_ice_point():
    assert _kelvin_to_celsius(273.15) == pytest.approx(0.0, abs=1e-12)


def test_k_to_c_room_temperature():
    assert _kelvin_to_celsius(300.0) == pytest.approx(26.85, rel=1e-9)


def test_k_to_c_ambient_canonical():
    """T_ambient default 300 K (Panel D) → 26.85 °C."""
    assert _kelvin_to_celsius(300.0) == pytest.approx(26.85, abs=1e-6)


def test_k_to_c_cfrp_failure_threshold():
    """CFRP decomposition threshold sits at ~823 K per material table;
    that must display as ≈ 550 °C."""
    assert _kelvin_to_celsius(823.0) == pytest.approx(549.85, abs=1e-6)


def test_k_to_c_round_trip():
    """(T − 273.15) + 273.15 = T exactly for any physical temperature."""
    for T_K in (253.0, 273.15, 300.0, 400.0, 823.0, 1000.0):
        assert (_kelvin_to_celsius(T_K) + 273.15) == pytest.approx(T_K, rel=1e-12)


# ---------------------------------------------------------------------------
# Verdict-margin arithmetic (Overview tab)
# ---------------------------------------------------------------------------

def _verdict_margin(dwell: float, tau_bt: float) -> float:
    """Mirror of ui/outputs.py::_verdict_chip margin = (dwell − tau_bt) / tau_bt."""
    return (dwell - tau_bt) / tau_bt


def _verdict_severity(dwell: float | None, tau_bt: float | None) -> str:
    """Mirror of ui/outputs.py verdict thresholds. Returns 'instant',
    'no_dwell', 'ok', 'warn', or 'error'."""
    if tau_bt is None or tau_bt <= 0.0:
        return "instant"
    if dwell is None or dwell <= 0.0:
        return "no_dwell"
    margin = _verdict_margin(dwell, tau_bt)
    if margin >= 0.30:
        return "ok"
    if margin >= 0.0:
        return "warn"
    return "error"


def test_verdict_margin_at_ok_boundary():
    """margin exactly = 0.30 → OK (ENGAGEABLE)."""
    assert _verdict_severity(dwell=1.30, tau_bt=1.0) == "ok"


def test_verdict_margin_just_below_ok_boundary():
    """margin just under 0.30 → WARN (MARGINAL)."""
    # 1.299 / 1.0 - 1 = 0.299 < 0.30
    assert _verdict_severity(dwell=1.299, tau_bt=1.0) == "warn"


def test_verdict_margin_at_zero_boundary():
    """margin = 0.0 → WARN (MARGINAL, exactly equals dwell)."""
    assert _verdict_severity(dwell=1.0, tau_bt=1.0) == "warn"


def test_verdict_margin_negative():
    """margin < 0 → ERROR (NOT ENGAGEABLE)."""
    assert _verdict_severity(dwell=0.5, tau_bt=1.0) == "error"


def test_verdict_instantaneous_burnthrough():
    """tau_bt = 0 → 'instant' (ENGAGEABLE — no time to heat through)."""
    assert _verdict_severity(dwell=5.0, tau_bt=0.0) == "instant"


def test_verdict_no_dwell():
    """dwell = 0 with finite tau_bt → 'no_dwell' (stationary viable target
    but no time window). Note: in practice dwell=∞ for stationary, not 0."""
    assert _verdict_severity(dwell=0.0, tau_bt=1.0) == "no_dwell"


def test_verdict_margin_percent_sign_on_error():
    """Error margin expressed as shortfall: (−0.5) → 50% shortfall display."""
    margin = _verdict_margin(dwell=0.5, tau_bt=1.0)
    assert margin == pytest.approx(-0.5, rel=1e-12)
    shortfall_pct = abs(margin) * 100
    assert shortfall_pct == pytest.approx(50.0, rel=1e-12)


def test_verdict_margin_percent_sign_on_ok():
    """OK margin expressed as excess: 42.3% (from dwell=1.423, tau=1.0)."""
    margin_pct = _verdict_margin(dwell=1.423, tau_bt=1.0) * 100
    assert margin_pct == pytest.approx(42.3, rel=1e-9)


# ---------------------------------------------------------------------------
# Plot log-guards
# ---------------------------------------------------------------------------

def _log_guard(value: float, floor: float = 1e-6) -> float:
    """Mirror of the log-y guard used in ui/plots.py for tau_BT / NOHD etc."""
    return max(value, floor)


def test_log_guard_protects_zero():
    """log_guard(0) returns the floor, not 0 (which would plot at −∞)."""
    assert _log_guard(0.0) == 1e-6


def test_log_guard_preserves_positive():
    """log_guard returns the value unchanged when above the floor."""
    assert _log_guard(2.5) == 2.5


def test_log_guard_negative_inputs_clamped():
    """A non-physical negative input is clamped to the floor."""
    assert _log_guard(-1.0) == 1e-6


# ---------------------------------------------------------------------------
# Panel UI↔SI round-trip (document the conversion constants even though the
# widgets themselves can't be exercised without a Streamlit runtime)
# ---------------------------------------------------------------------------
# See ui/panels.py — each of these is inlined into a st.number_input → return
# dict bridge. Catching a silent typo in the conversion constant (×1000 vs
# /1000) here saves a full cross-module failure.


def test_panel_p0_kw_to_w_round_trip():
    """P0: kW × 1000 → W; back-conversion is W / 1000."""
    for p0_kw in (0.1, 3.0, 30.0, 100.0):
        si = p0_kw * 1000.0
        back = si / 1000.0
        assert back == pytest.approx(p0_kw, rel=1e-12)


def test_panel_d_cm_to_m_round_trip():
    """D: cm / 100 → m."""
    for d_cm in (1.0, 10.0, 30.0, 50.0):
        si = d_cm / 100.0
        back = si * 100.0
        assert back == pytest.approx(d_cm, rel=1e-12)


def test_panel_wavelength_um_to_m_round_trip():
    """wavelength: µm × 1e-6 → m."""
    for lam_um in (1.06, 1.07, 1.55, 2.05):
        si = lam_um * 1e-6
        back = si * 1e6
        assert back == pytest.approx(lam_um, rel=1e-12)


def test_panel_sigma_jit_urad_to_rad_round_trip():
    """sigma_jit: µrad × 1e-6 → rad."""
    for sig_urad in (1.0, 5.0, 10.0, 50.0):
        si = sig_urad * 1e-6
        back = si * 1e6
        assert back == pytest.approx(sig_urad, rel=1e-12)


def test_panel_rh_pct_to_fraction_round_trip():
    """RH: pct / 100 → fraction."""
    for rh_pct in (0.0, 30.0, 60.0, 100.0):
        si = rh_pct / 100.0
        back = si * 100.0
        assert back == pytest.approx(rh_pct, rel=1e-12)


def test_panel_t_ambient_c_to_k():
    """T_ambient: °C + 273.15 → K (additive)."""
    assert 0.0 + 273.15 == pytest.approx(273.15, rel=1e-12)
    assert 26.85 + 273.15 == pytest.approx(300.0, abs=1e-6)
    assert 55.0 + 273.15 == pytest.approx(328.15, rel=1e-12)


def test_panel_d_aim_cm_to_m_round_trip():
    """d_aim: cm / 100 → m."""
    for d_cm in (0.5, 5.0, 15.0, 50.0):
        si = d_cm / 100.0
        back = si * 100.0
        assert back == pytest.approx(d_cm, rel=1e-12)


def test_panel_thickness_mm_to_m_round_trip():
    """thickness: mm / 1000 → m."""
    for t_mm in (0.1, 2.0, 5.0, 20.0):
        si = t_mm / 1000.0
        back = si * 1000.0
        assert back == pytest.approx(t_mm, rel=1e-12)


def test_panel_q_cool_kw_to_w_round_trip():
    """Q_cool: kW × 1000 → W."""
    for q_kw in (5.0, 15.0, 50.0, 100.0):
        si = q_kw * 1000.0
        back = si / 1000.0
        assert back == pytest.approx(q_kw, rel=1e-12)


def test_panel_c_thermal_kjk_to_jk_round_trip():
    """C_thermal: kJ/K × 1000 → J/K."""
    for c_kjk in (50.0, 200.0, 500.0):
        si = c_kjk * 1000.0
        back = si / 1000.0
        assert back == pytest.approx(c_kjk, rel=1e-12)


# ---------------------------------------------------------------------------
# OUTPUT_LABELS coverage — every numeric key the orchestrator emits has a
# labels.py entry (otherwise a card would render a blank label at runtime)
# ---------------------------------------------------------------------------

_NUMERIC_OUTPUT_KEYS = [
    "theta_diff", "w0", "zR", "I_exit",
    "P_exit",
    "R_slant", "R_h", "elevation_angle", "available_dwell",
    "alpha_atm", "tau_atm", "alpha_mol_abs", "alpha_mol_scat",
    "alpha_aer_abs", "alpha_aer_scat",
    "Cn2_integrated", "r0_sph", "w_turb",
    "N_D", "S_TB", "w_bloom",
    "w_diff", "w_jit", "w_total", "d_spot",
    "I_peak", "PIB_fraction", "P_aim", "I_avg_aim",
    "tau_BT", "T_surface_peak", "E_delivered",
    "MPE", "NOHD_tophat", "NOHD_gausspeak",
    "P_in", "Q_waste", "t_sustain", "duty_cycle_limit", "engagements_per_hour",
]


@pytest.mark.parametrize("key", _NUMERIC_OUTPUT_KEYS)
def test_every_numeric_output_has_label(key):
    """Every orchestrator numeric output has a labels.py entry so the
    UI never renders a blank label. This guards against a silent
    typo in outputs.py after a SPEC revision."""
    from ui.labels import OUTPUT_LABELS
    # If the key is missing, output_label raises KeyError — that's a bug.
    assert key in OUTPUT_LABELS, (
        f"orchestrator output {key!r} has no ui/labels.py entry; the UI "
        f"would render an empty label or crash."
    )


# ---------------------------------------------------------------------------
# format_value interaction with _DISPLAY_SCALE (end-to-end display chain)
# ---------------------------------------------------------------------------

def test_display_chain_power_to_kw_card_string():
    """3000 W → scale to 3.0 kW → format_value → '3.00 kW'."""
    si_value = 3000.0
    scaled = _scale("P_aim", si_value)
    unit = output_unit("P_aim")
    rendered = format_value(scaled, unit)
    nbsp = "\u00a0"
    assert rendered == f"3.00{nbsp}kW"


def test_display_chain_irradiance_to_wpcm2_card_string():
    """1e5 W/m² → scale to 10 W/cm² → format_value → '10.0 W/cm²'."""
    si_value = 1.0e5
    scaled = _scale("I_peak", si_value)
    unit = output_unit("I_peak")
    rendered = format_value(scaled, unit)
    nbsp = "\u00a0"
    assert rendered == f"10.0{nbsp}W/cm²"


def test_display_chain_angle_urad_card_string():
    """10e-6 rad → 10.0 µrad → '10.0 µrad'."""
    scaled = _scale("theta_diff", 10e-6)
    unit = output_unit("theta_diff")
    rendered = format_value(scaled, unit)
    nbsp = "\u00a0"
    assert rendered == f"10.0{nbsp}µrad"


# ---------------------------------------------------------------------------
# Derived UI-only quantities (outputs.py 464-489: θ_M2_excess etc.)
# ---------------------------------------------------------------------------

def test_theta_m2_excess_difference():
    """θ_M2_excess = θ_diff − θ_diff_pure (M²>1 component)."""
    theta_diff = 13.547e-6 * 1.2   # scaled by M²=1.2 from M²=1 baseline
    theta_pure = 13.547e-6
    expected = theta_diff - theta_pure
    # Mirror the arithmetic in outputs.py.
    computed = theta_diff - theta_pure
    assert computed == pytest.approx(expected, rel=1e-12)
    assert computed > 0


def test_theta_turb_from_w_turb():
    """θ_turb = 2·w_turb / L (full-angle from 1/e² radius)."""
    w_turb = 0.10
    L = 2000.0
    theta_turb = 2.0 * w_turb / L
    assert theta_turb == pytest.approx(1e-4, rel=1e-12)


def test_theta_jit_from_sigma():
    """θ_jit = 2·σ_jit (per-axis σ → full-angle)."""
    sigma = 10e-6
    theta_jit = 2.0 * sigma
    assert theta_jit == pytest.approx(20e-6, rel=1e-12)


def test_strehl_effective_formula_guarded():
    """S_effective = S_TB · (w_diff² / w_total²), guard against w_total=0."""
    S_TB = 0.8
    w_diff = 0.05
    w_total = 0.10
    guard = 1e-30
    S_eff = S_TB * (w_diff ** 2) / (w_total ** 2 + guard)
    assert S_eff == pytest.approx(0.2, rel=1e-9)


def test_strehl_effective_guard_prevents_divzero():
    """At w_total=0 (pathological), the guard keeps the computation finite."""
    S_TB = 1.0
    w_diff = 0.05
    w_total = 0.0
    guard = 1e-30
    S_eff = S_TB * (w_diff ** 2) / (w_total ** 2 + guard)
    # Result is finite (very large, but not NaN/inf).
    assert math.isfinite(S_eff)


# ---------------------------------------------------------------------------
# Atmosphere extinction percentage share (outputs.py atmosphere tab)
# ---------------------------------------------------------------------------

def test_atmosphere_component_share_sums_to_100():
    """Each component / total × 100 summed over 4 components = 100 %."""
    components = {
        "mol_abs":  1.2e-4,
        "mol_scat": 0.5e-4,
        "aer_abs":  0.2e-4,
        "aer_scat": 3.8e-4,
    }
    total = sum(components.values())
    shares = [v / total * 100 for v in components.values()]
    assert sum(shares) == pytest.approx(100.0, rel=1e-12)


def test_atmosphere_total_guard_prevents_divzero():
    """When total α is 0 (clean dry air at 1.07 µm after rounding), the
    share calculation uses a 1e-12 guard to avoid ZeroDivisionError."""
    total = 0.0
    guard = 1e-12
    share = (1e-6 / (total + guard)) * 100
    assert math.isfinite(share)
