"""Numeric output sections per SPEC §5.2 (Phase 3 PR 2 rewrite).

Each ``render_section_N`` function takes the orchestrator's merged-result
dict (plus a reference range for the spot-and-Strehl section) and
renders that section's content to the active Streamlit column. All
public functions return ``None``; they write to Streamlit, not to a
structured object.

The caller (``ui/app.py``) merges the user-input dict into the result
dict before passing it in, so entries like ``result['M2']`` and
``result['sigma_jit']`` are available without changing the ARCH §6.4
signature. The spot-and-Strehl section uses this to split the
diffraction angle into its ideal-Gaussian and beam-quality-excess
components, and to compute the full-angle pointing jitter
``θ_jit = 2 · σ_jit``. Fallbacks (``.get(..., 0.0)``) keep the
sections defensive if a caller passes only the module outputs.

**PR 2 changes versus PR 1:**

* Every output cell is now a ``metric_card`` from ``ui/components.py``
  instead of ``st.metric``. Cards sit on the 12-column alignment grid
  (via ``st.columns(...)``) and render their numeric values through
  ``format_value`` — so the "3 sig figs, comma thousands-separator,
  scientific notation outside [0.01, 1e5), non-breaking-space before
  unit" rule applies uniformly, with no per-call format strings.
* The verdict banner is a ``status_chip`` (hue + Lucide icon + text).
* ``render_panel_4_assumptions`` emits a severity-sorted chip list
  instead of a bullet wall. Each flag is classified into
  ``ok | warn | error | info`` by a lightweight keyword heuristic and
  ordered error → warn → info → ok so the most important flag reads
  first.

PR 3 then splits these render functions across tabs (Overview /
Engagement / Target effects / Safety / Atmosphere / Diagnostics). PR 2
keeps the single-scroll page so the diff stays isolated to components
and formatting.

References:
    SPEC.md §5.2 (section contracts).
    SPEC.md §5.3 items 8–11 (numeric-display, verdict chip, flag severity).
    ARCHITECTURE.md §6.4 (public signatures) and §6.9 (ui/components.py).
    ui/labels.py — OUTPUT_LABELS, VERDICT_TEMPLATES (user-visible strings).
    ui/components.py — metric_card, status_chip, format_value.
"""

from __future__ import annotations

import math

import streamlit as st

from ui.components import (
    format_value,
    metric_card,
    section_header,
    status_chip,
)
from ui.labels import (
    VERDICT_TEMPLATES,
    output_label,
    output_tooltip,
    output_unit,
)


# =============================================================================
# Unit-scaling helper: orchestrator returns SI; labels.py declares display units
# =============================================================================
# The orchestrator emits SI units (W, W/m², m, rad, 1/m). ``ui/labels.py``
# declares the DISPLAY unit for each output key (kW, W/cm², km, µrad, 1/km).
# The scale factors below convert SI → display unit and match what the
# metric_card gets handed. All scaling lives in one dict so a future change
# of display convention happens in one place.

_DISPLAY_SCALE: dict[str, float] = {
    # Power — SI W → display kW
    "P_aim":        1e-3,
    "P_in":         1e-3,
    "Q_waste":      1e-3,
    # Irradiance — SI W/m² → display W/cm²
    "I_avg_aim":    1e-4,
    "I_peak":       1e-4,
    # Distance — SI m → display km
    "NOHD_tophat":    1e-3,
    "NOHD_gausspeak": 1e-3,
    # Angle — SI rad → display µrad
    "theta_diff":       1e6,
    "theta_diff_pure":  1e6,
    "theta_M2_excess":  1e6,
    "theta_turb":       1e6,
    "theta_jit":        1e6,
    # Extinction — SI 1/m → display 1/km
    "alpha_atm":       1e3,
    "alpha_mol_abs":   1e3,
    "alpha_mol_scat":  1e3,
    "alpha_aer_abs":   1e3,
    "alpha_aer_scat":  1e3,
    # Spot radii — SI m → display cm
    "w_diff":   1e2,
    "w_turb":   1e2,
    "w_jit":    1e2,
    "w_bloom":  1e2,
    "w_total":  1e2,
    # Time (s), Margin (%), dimensionless ratios — pass-through (scale=1.0).
}


def _scale(key: str, value: float | None) -> float | None:
    """Scale a SI orchestrator value to the display unit declared in labels.py."""
    if value is None:
        return None
    return value * _DISPLAY_SCALE.get(key, 1.0)


def _card(
    key: str,
    value: float | int | str | None,
    *,
    override_label: str | None = None,
    flag_est: bool = False,
    size: str = "lg",
    sig_figs: int = 3,
) -> None:
    """Thin wrapper around ``metric_card`` that fills label/unit/tooltip from
    ``ui/labels.py`` by output key and scales the value into display units.

    String values (material names, failure modes, laser class) pass through
    without scaling or unit appending. Numeric values route through
    ``_DISPLAY_SCALE`` and ``format_value``.
    """
    label = override_label if override_label is not None else output_label(key)
    unit = output_unit(key)
    tooltip = output_tooltip(key) or None

    scaled = value if isinstance(value, str) else _scale(key, value)

    metric_card(
        label,
        scaled,
        unit=unit if not isinstance(value, str) else "",
        tooltip=tooltip,
        flag_est=flag_est,
        size=size,
        sig_figs=sig_figs,
    )


# =============================================================================
# Section 1 — Spot broadening & Strehl decomposition at reference range.
# =============================================================================
def render_panel_1_spot_strehl(result: dict, reference_range: float) -> None:
    """Angular-error split + Strehl decomposition at the reference range.

    Displays the angular components (ideal-Gaussian diffraction, M²
    excess, turbulence broadening, jitter) in µrad full-angle (Siegman
    convention), the Strehl decomposition (thermal-blooming × optical),
    and the effective peak-irradiance ratio vs the diffraction-limited
    baseline ``S_TB · (w_diff / w_total)²``.
    """
    section_header(
        f"Spot & Strehl decomposition — reference range "
        f"{reference_range / 1000:.2f} km"
    )

    by = result["by_module"]

    # Angular-error split. The diffraction-module output is the full
    # beam-quality-inflated divergence; dividing by M² recovers the
    # M²=1 limit, and the difference is the excess broadening.
    theta_diff_full = by["m1"]["theta_diff"]
    m2_bq = float(result.get("M2", 1.0))
    theta_diff_pure = theta_diff_full / m2_bq if m2_bq > 0 else theta_diff_full
    theta_M2_excess = theta_diff_full - theta_diff_pure

    # Full-angle turbulence and jitter broadening at the reference range.
    path = max(reference_range, 1.0)
    theta_turb = 2.0 * by["m5"]["w_turb"] / path  # w_turb is the 1/e² radius
    theta_jit = 2.0 * float(result.get("sigma_jit", 0.0))  # 2·σ_jit

    c1, c2, c3, c4 = st.columns(4)
    with c1: _card("theta_diff_pure", theta_diff_pure)
    with c2: _card("theta_M2_excess", theta_M2_excess)
    with c3: _card("theta_turb",      theta_turb)
    with c4: _card("theta_jit",       theta_jit)

    # Strehl decomposition. The optical Strehl is fixed at 1.0 in v1;
    # atmospheric turbulence enters via w_turb (not as a Strehl factor).
    s_tb = by["m6"]["S_TB"]
    s_opt = 1.0

    w_diff = by["m7"]["w_diff"]
    w_total = by["m7"]["w_total"]
    # Effective peak ratio vs diffraction-limited, turbulence- and
    # blooming-free baseline.
    eff_ratio = s_tb * (w_diff ** 2) / max(w_total ** 2, 1e-30)

    c1, c2, c3 = st.columns(3)
    with c1: _card("S_TB",  s_tb,  sig_figs=4)
    with c2: _card("S_opt", s_opt, sig_figs=4)
    with c3:
        metric_card(
            "Peak vs diffraction limit",
            eff_ratio,
            unit="",
            tooltip=(
                "Effective peak-irradiance ratio against the diffraction-"
                "limited, turbulence- and blooming-free baseline."
            ),
            sig_figs=4,
        )

    st.caption(
        "Angles are full-angle (Siegman convention). The peak-vs-diffraction-"
        "limit ratio is S_TB · (w_diff / w_total)² — a direct comparison "
        "against the turbulence- and blooming-free baseline."
    )


# =============================================================================
# Section 2 — Engagement summary with three-tier verdict chip.
# =============================================================================
def render_panel_2_engagement(result: dict) -> None:
    """Engagement summary with a three-tier verdict chip + margin.

    Verdict thresholds (SPEC §5.2 Overview verdict):
      * margin ≥ 30%    → ``ok``    chip — "ENGAGEABLE — {margin}% margin"
      * 0 ≤ margin < 30% → ``warn`` chip — "MARGINAL — {margin}% margin"
      * margin < 0      → ``error`` chip — "NOT ENGAGEABLE — exceeds dwell by {shortfall}%"
      * τ_BT ≤ 0        → ``ok``    chip — "ENGAGEABLE — instantaneous"
      * dwell ≤ 0       → ``error`` chip — "NOT ENGAGEABLE — no dwell available"
    """
    section_header("Engagement summary")

    by = result["by_module"]
    p_aim = by["m7"]["P_aim"]
    i_avg = by["m7"]["I_avg_aim"]
    i_peak = by["m7"]["I_peak"]
    tau_bt = by["m8"].get("tau_BT")
    dwell = by["m3"].get("available_dwell")

    c1, c2, c3 = st.columns(3)
    with c1: _card("P_aim",     p_aim)
    with c2: _card("I_avg_aim", i_avg)
    with c3: _card("I_peak",    i_peak)

    c1, c2 = st.columns(2)
    with c1: _card("tau_BT",          tau_bt)
    with c2: _card("available_dwell", dwell)

    # --- Verdict chip ----------------------------------------------------
    st.write("")  # small vertical spacer
    if tau_bt is None or tau_bt <= 0.0:
        status_chip(VERDICT_TEMPLATES["instant"], "ok")
        return
    if dwell is None or dwell <= 0.0:
        status_chip(VERDICT_TEMPLATES["no_dwell"], "error")
        return

    margin = (dwell - tau_bt) / tau_bt
    if margin >= 0.30:
        status_chip(
            VERDICT_TEMPLATES["ok"].format(margin=margin * 100),
            "ok",
        )
    elif margin >= 0.0:
        status_chip(
            VERDICT_TEMPLATES["warn"].format(margin=margin * 100),
            "warn",
        )
    else:
        status_chip(
            VERDICT_TEMPLATES["error"].format(shortfall=abs(margin) * 100),
            "error",
        )


# =============================================================================
# Section 3 — System feasibility (power, thermal, safety).
# =============================================================================
def render_panel_3_feasibility(result: dict) -> None:
    """System feasibility: input power, waste heat, engagement count, NOHD.

    The Nominal Ocular Hazard Distance is reported in BOTH the top-hat
    and Gaussian-peak conventions (per the v1 safety contract); the
    user cites whichever is appropriate for the specific safety case.
    """
    section_header("System feasibility")

    by = result["by_module"]
    p_in = by["m10"]["P_in"]
    q_waste = by["m10"]["Q_waste"]
    t_sustain = by["m10"]["t_sustain"]
    eng_per_hr = by["m10"]["engagements_per_hour"]

    c1, c2, c3, c4 = st.columns(4)
    with c1: _card("P_in",    p_in)
    with c2: _card("Q_waste", q_waste)
    with c3:
        if math.isfinite(t_sustain):
            _card("t_sustain", t_sustain)
        else:
            # Display-string override: "∞" with the thermally-unlimited
            # clarification. format_value emits "—" for non-finite numbers
            # by design, so we pass the string directly.
            metric_card(
                output_label("t_sustain"),
                "∞ thermally unlimited",
                unit="",
                tooltip=output_tooltip("t_sustain"),
            )
    with c4: _card("engagements_per_hour", eng_per_hr)

    nohd_th = by["m9"].get("NOHD_tophat", 0.0)
    nohd_gp = by["m9"].get("NOHD_gausspeak", 0.0)
    laser_class = by["m9"].get("laser_class", "—")

    c1, c2, c3 = st.columns(3)
    with c1: _card("NOHD_tophat",    nohd_th)
    with c2: _card("NOHD_gausspeak", nohd_gp)
    with c3: _card("laser_class",    laser_class)

    st.caption(
        "Both Nominal Ocular Hazard Distance conventions are reported — "
        "cite whichever is appropriate for the specific safety case. "
        "The Gaussian-peak value is the more conservative of the two."
    )


# =============================================================================
# Section 4 — Severity-sorted assumption-flag chip list.
# =============================================================================
# PR 2 replaces PR 1's bullet wall with a severity-sorted chip list. The
# severity of each flag is inferred from keyword patterns matching the
# physics modules' existing flag strings (no new fields added to
# ``assumptions_flagged`` — the list is still raw strings). Ordering is
# error → warn → info → ok so the most important flag reads first.

# Keyword → severity. Checked case-insensitively; first match wins. Order
# matters: more-specific patterns appear before general ones. All physics
# flag strings trace back to ``assumptions_flagged.append(...)`` calls in
# the physics modules.
_SEVERITY_PATTERNS: tuple[tuple[str, str], ...] = (
    # --- error: the calculation failed, the engagement is not viable ------
    ("not viable",               "error"),
    ("not engageable",           "error"),
    ("reached timeout",          "error"),  # M8: "simulation reached 60 s timeout…"
    ("infeasible",               "error"),
    ("no feasible",              "error"),
    # --- warn: a model is outside its strict validity range, or a high-
    #          uncertainty literature default is in play -------------------
    ("high uncertainty",         "warn"),
    ("reduced confidence",       "warn"),
    ("outside tabulated",        "warn"),
    ("outside validated",        "warn"),
    ("outside the validity",     "warn"),
    ("outside stated validity",  "warn"),  # M6: "N_D = … > 30: … outside stated validity range"
    ("did not converge",         "warn"),  # orchestrator: M6↔M7 loop non-convergence
    ("deferred to v2",           "warn"),  # M9: "MPE for λ > 4 µm deferred to v2…"
    ("best-effort",              "warn"),  # M9: "t_exp < 18 µs … best-effort limit"
    ("extrapolated",             "warn"),
    ("extrapolation",            "warn"),
    ("clamped",                  "warn"),
    ("default",                  "warn"),
    # --- info: an explicit modelling choice the user should know about ----
    ("assumed",                  "info"),
    ("1-d transient",            "info"),
    ("1d transient",             "info"),
    ("sea-level",                "info"),
    ("hv-",                      "info"),
    ("conv+rad",                 "info"),
    ("convective",               "info"),
)

# Sort order: lower number = higher priority (rendered first).
_SEVERITY_ORDER: dict[str, int] = {"error": 0, "warn": 1, "info": 2, "ok": 3}


def _classify_flag_severity(flag: str) -> str:
    """Return the severity of a single assumption-flag string.

    Uses a keyword heuristic against ``_SEVERITY_PATTERNS``; first match
    wins. Unmatched flags fall back to ``"info"`` — the calmest tier —
    because a flag that exists by virtue of being in the list is worth
    surfacing, just not with escalated visual weight.
    """
    lowered = flag.lower()
    for needle, severity in _SEVERITY_PATTERNS:
        if needle in lowered:
            return severity
    return "info"


def render_panel_4_assumptions(result: dict) -> None:
    """Always-visible, severity-sorted chip list of flagged assumptions.

    Showing the user exactly what defaults and approximations feed into
    the displayed numbers is a hard contract — this section cannot be
    collapsed. The chip list orders ``error → warn → info`` so the most
    important flags read first, and each chip carries hue + Lucide icon
    + text (color-blind triple-encoded per the design system).
    """
    section_header("Assumptions & flags")
    flags = result.get("assumptions_flagged", [])
    if not flags:
        st.info("No assumption flags raised for this input set.")
        return

    # Classify and stable-sort. ``sorted(..., key=...)`` is stable, so flags
    # of the same severity retain the order the physics modules appended
    # them — useful when two related flags want to read together.
    classified = [(flag, _classify_flag_severity(flag)) for flag in flags]
    classified.sort(key=lambda pair: _SEVERITY_ORDER[pair[1]])

    for flag, severity in classified:
        status_chip(flag, severity)


# =============================================================================
# Section 5 — Atmospheric extinction breakdown.
# =============================================================================
def render_panel_5_atmosphere_breakdown(result: dict) -> None:
    """Atmospheric extinction decomposition into molecular + aerosol
    absorption and scattering.

    Shown as a table with each component's α (1/km, three significant
    figures, scientific notation below 0.01) and its percentage share of
    the total. PR 5 replaces the table with a horizontal stacked-bar
    plot; this PR keeps the tabular view so the data is present while
    the plot library lands.
    """
    section_header("Atmospheric extinction breakdown")
    by = result["by_module"]

    components = (
        ("alpha_mol_abs",  by["m4"]["alpha_mol_abs"]),
        ("alpha_mol_scat", by["m4"]["alpha_mol_scat"]),
        ("alpha_aer_abs",  by["m4"]["alpha_aer_abs"]),
        ("alpha_aer_scat", by["m4"]["alpha_aer_scat"]),
    )
    total_si = by["m4"]["alpha_atm"]

    if total_si <= 0:
        st.info("Total extinction is zero — vacuum or negligible path extinction.")
        return

    # Build display rows. ``format_value`` handles the scientific-notation
    # switch at |α| < 0.01/km automatically; share is a plain percentage.
    rows = [
        {
            "Component": output_label(key),
            "α (1/km)":  format_value(_scale(key, value), unit=""),
            "Share":     f"{value / total_si * 100:.1f}%",
        }
        for key, value in components
    ]
    rows.append({
        "Component": output_label("alpha_atm"),
        "α (1/km)":  format_value(_scale("alpha_atm", total_si), unit=""),
        "Share":     "100.0%",
    })
    st.table(rows)


# =============================================================================
# Aggregate renderer.
# =============================================================================
def render_all(result: dict, reference_range: float) -> None:
    """Render all five sections in top-to-bottom reading order.

    PR 3 replaces this single-scroll layout with a tabbed container
    (Overview / Engagement / Target effects / Safety / Atmosphere /
    Diagnostics). Until then, the five sections render in order.
    """
    render_panel_1_spot_strehl(result, reference_range)
    render_panel_2_engagement(result)
    render_panel_3_feasibility(result)
    render_panel_4_assumptions(result)
    render_panel_5_atmosphere_breakdown(result)
