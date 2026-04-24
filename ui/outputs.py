"""Numeric output sections per SPEC §5.2.

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

Phase 3 PR 1: all user-visible strings now route through
``ui/labels.py``. Internal citations (``SPEC §…``, module tags like
``M6``, "Panel N" chrome) have been removed from user-facing copy —
they survive in docstrings and comments for maintainer reference.
Tabbed layout (PR 3) will split these render functions across tabs;
for now the single-scroll page is preserved so PR 1 remains
isolated to theme + labels.

References:
    SPEC.md §5.2 (section contracts).
    ARCHITECTURE.md §6.4 (public signatures).
    ui/labels.py — OUTPUT_LABELS, VERDICT_TEMPLATES (user-visible strings).
    ui/theme.py — palette tokens (COLOR_SUCCESS, COLOR_WARNING, COLOR_CAUTION).
"""

from __future__ import annotations

import math

import streamlit as st

from ui.labels import (
    VERDICT_TEMPLATES,
    output_label,
    output_unit,
)
from ui.theme import COLOR_CAUTION, COLOR_SUCCESS, COLOR_WARNING


# ---------------------------------------------------------------------------
# Small formatting helper.
# ---------------------------------------------------------------------------


def _with_unit(value_str: str, key: str) -> str:
    """Return ``'<value> <unit>'`` — unit pulled from labels.py. Non-breaking
    space between value and unit per the voice-and-tone rules (every number
    ships with its unit)."""
    unit = output_unit(key)
    return f"{value_str} {unit}" if unit else value_str


# ---------------------------------------------------------------------------
# Section 1 — Spot broadening & Strehl decomposition at reference range.
# ---------------------------------------------------------------------------
def render_panel_1_spot_strehl(result: dict, reference_range: float) -> None:
    """Angular-error split + Strehl decomposition at the reference range.

    Displays the angular components (ideal-Gaussian diffraction, M²
    excess, turbulence broadening, jitter) in µrad full-angle (Siegman
    convention), the Strehl decomposition (thermal-blooming × optical),
    and the effective peak-irradiance ratio vs the diffraction-limited
    baseline ``S_TB · (w_diff / w_total)²``.
    """
    st.subheader(
        f"Spot & Strehl decomposition — reference range {reference_range / 1000:.2f} km"
    )

    by = result["by_module"]

    # Angular-error split. The diffraction-module output is the full
    # beam-quality-inflated divergence; dividing by M² recovers the
    # M²=1 limit, and the difference is the excess broadening.
    theta_diff_full = by["m1"]["theta_diff"]
    M2 = float(result.get("M2", 1.0))
    theta_diff_pure = theta_diff_full / M2 if M2 > 0 else theta_diff_full
    theta_M2_excess = theta_diff_full - theta_diff_pure

    # Full-angle turbulence and jitter broadening at the reference range.
    L = max(reference_range, 1.0)
    theta_turb = 2.0 * by["m5"]["w_turb"] / L  # w_turb is the 1/e² radius
    theta_jit = 2.0 * float(result.get("sigma_jit", 0.0))  # 2·σ_jit (full-angle)

    c1, c2, c3, c4 = st.columns(4)
    c1.metric(output_label("theta_diff_pure"), _with_unit(f"{theta_diff_pure * 1e6:.2f}", "theta_diff_pure"))
    c2.metric(output_label("theta_M2_excess"), _with_unit(f"{theta_M2_excess * 1e6:.2f}", "theta_M2_excess"))
    c3.metric(output_label("theta_turb"),      _with_unit(f"{theta_turb      * 1e6:.2f}", "theta_turb"))
    c4.metric(output_label("theta_jit"),       _with_unit(f"{theta_jit       * 1e6:.2f}", "theta_jit"))

    # Strehl decomposition. The optical Strehl is fixed at 1.0 in v1;
    # atmospheric turbulence enters via w_turb (not as a Strehl factor).
    S_TB = by["m6"]["S_TB"]
    S_opt = 1.0

    w_diff = by["m7"]["w_diff"]
    w_total = by["m7"]["w_total"]
    # Effective peak ratio vs diffraction-limited, turbulence- and
    # blooming-free baseline.
    eff_ratio = S_TB * (w_diff ** 2) / max(w_total ** 2, 1e-30)

    c1, c2, c3 = st.columns(3)
    c1.metric(output_label("S_TB"),  f"{S_TB:.3f}")
    c2.metric(output_label("S_opt"), f"{S_opt:.3f}")
    c3.metric("Peak vs diffraction limit", f"{eff_ratio:.3f}")

    st.caption(
        "Angles are full-angle (Siegman convention). The peak-vs-diffraction-limit "
        "ratio is S_TB · (w_diff / w_total)² — a direct comparison against "
        "the turbulence- and blooming-free baseline."
    )


# ---------------------------------------------------------------------------
# Section 2 — Engagement summary with three-tier verdict.
# ---------------------------------------------------------------------------
def render_panel_2_engagement(result: dict) -> None:
    """Engagement summary with a three-tier verdict chip + margin.

    Verdict thresholds:
      - margin ≥ 30%    → "ENGAGEABLE"        (success)
      - 0 ≤ margin < 30% → "MARGINAL"         (warning)
      - margin < 0       → "NOT ENGAGEABLE"   (error, quotes shortfall)
      - τ_BT ≤ 0         → "ENGAGEABLE — instantaneous"
      - dwell ≤ 0        → "NOT ENGAGEABLE — no dwell available"
    """
    st.subheader("Engagement summary")

    by = result["by_module"]
    P_aim = by["m7"]["P_aim"]
    I_avg_aim = by["m7"]["I_avg_aim"]
    I_peak = by["m7"]["I_peak"]
    tau_BT = by["m8"].get("tau_BT")
    dwell = by["m3"].get("available_dwell")

    c1, c2, c3 = st.columns(3)
    c1.metric(output_label("P_aim"),     _with_unit(f"{P_aim / 1000:.2f}",     "P_aim"))
    c2.metric(output_label("I_avg_aim"), _with_unit(f"{I_avg_aim / 1e4:.1f}",  "I_avg_aim"))
    c3.metric(output_label("I_peak"),    _with_unit(f"{I_peak / 1e4:.1f}",     "I_peak"))

    c1, c2 = st.columns(2)
    tau_str = _with_unit(f"{tau_BT:.2f}", "tau_BT") if tau_BT is not None else "—"
    dwell_str = _with_unit(f"{dwell:.2f}", "available_dwell") if dwell is not None else "—"
    c1.metric(output_label("tau_BT"),         tau_str)
    c2.metric(output_label("available_dwell"), dwell_str)

    # Verdict.
    if tau_BT is None or tau_BT <= 0.0:
        _render_verdict(VERDICT_TEMPLATES["instant"], COLOR_SUCCESS)
        return
    if dwell is None or dwell <= 0.0:
        _render_verdict(VERDICT_TEMPLATES["no_dwell"], COLOR_CAUTION)
        return

    margin = (dwell - tau_BT) / tau_BT
    if margin >= 0.30:
        _render_verdict(
            VERDICT_TEMPLATES["ok"].format(margin=margin * 100),
            COLOR_SUCCESS,
        )
    elif margin >= 0.0:
        _render_verdict(
            VERDICT_TEMPLATES["warn"].format(margin=margin * 100),
            COLOR_WARNING,
        )
    else:
        _render_verdict(
            VERDICT_TEMPLATES["error"].format(shortfall=abs(margin) * 100),
            COLOR_CAUTION,
        )


def _render_verdict(text: str, color: str) -> None:
    """Render a colored verdict banner (inline HTML for a colored pill).

    PR 2 replaces this with ``status_chip`` from ``ui/components.py``;
    kept as a minimal inline renderer during PR 1 so the verdict still
    displays while the rest of the design system lands.
    """
    st.markdown(
        f"<div style='padding:12px;border-radius:6px;background:{color};"
        f"color:white;font-weight:600;font-size:18px;text-align:center;"
        f"margin-top:8px;margin-bottom:8px'>{text}</div>",
        unsafe_allow_html=True,
    )


# ---------------------------------------------------------------------------
# Section 3 — System feasibility (power, thermal, safety).
# ---------------------------------------------------------------------------
def render_panel_3_feasibility(result: dict) -> None:
    """System feasibility: input power, waste heat, engagement count, NOHD.

    The Nominal Ocular Hazard Distance is reported in BOTH the top-hat
    and Gaussian-peak conventions (per the v1 safety contract); the
    user cites whichever is appropriate for the specific safety case.
    """
    st.subheader("System feasibility")

    by = result["by_module"]
    P_in = by["m10"]["P_in"]
    Q_waste = by["m10"]["Q_waste"]
    t_sustain = by["m10"]["t_sustain"]
    engagements_per_hour = by["m10"]["engagements_per_hour"]

    c1, c2, c3, c4 = st.columns(4)
    c1.metric(output_label("P_in"),    _with_unit(f"{P_in / 1000:.1f}",    "P_in"))
    c2.metric(output_label("Q_waste"), _with_unit(f"{Q_waste / 1000:.1f}", "Q_waste"))
    if math.isfinite(t_sustain):
        c3.metric(output_label("t_sustain"), _with_unit(f"{t_sustain:.1f}", "t_sustain"))
    else:
        c3.metric(output_label("t_sustain"), "∞ (thermally unlimited)")
    c4.metric(output_label("engagements_per_hour"), f"{engagements_per_hour:.1f}")

    NOHD_th = by["m9"].get("NOHD_tophat", 0.0)
    NOHD_gp = by["m9"].get("NOHD_gausspeak", 0.0)
    laser_class = by["m9"].get("laser_class", "—")

    c1, c2, c3 = st.columns(3)
    c1.metric(output_label("NOHD_tophat"),    _with_unit(f"{NOHD_th / 1000:.2f}", "NOHD_tophat"))
    c2.metric(output_label("NOHD_gausspeak"), _with_unit(f"{NOHD_gp / 1000:.2f}", "NOHD_gausspeak"))
    c3.metric(output_label("laser_class"),    laser_class)
    st.caption(
        "Both Nominal Ocular Hazard Distance conventions are reported — "
        "cite whichever is appropriate for the specific safety case. "
        "The Gaussian-peak value is the more conservative of the two."
    )


# ---------------------------------------------------------------------------
# Section 4 — Always-visible assumptions roll-up.
# ---------------------------------------------------------------------------
def render_panel_4_assumptions(result: dict) -> None:
    """Always-visible list of every module's flagged assumptions.

    Showing the user exactly what defaults and approximations feed into
    the displayed numbers is a hard contract — this section cannot be
    collapsed. PR 2 replaces the bullet list with a severity-sorted
    chip list; PR 1 keeps the bullet list intact so the content is
    preserved while the design system lands.
    """
    st.subheader("Assumptions & flags")
    flags = result.get("assumptions_flagged", [])
    if not flags:
        st.info("No assumption flags raised for this input set.")
        return
    st.markdown("\n".join(f"- {f}" for f in flags))


# ---------------------------------------------------------------------------
# Section 5 — Atmospheric extinction breakdown.
# ---------------------------------------------------------------------------
def render_panel_5_atmosphere_breakdown(result: dict) -> None:
    """Atmospheric extinction decomposition into molecular + aerosol
    absorption and scattering. Shown in 1/km and as a percentage share
    of the total."""
    st.subheader("Atmospheric extinction breakdown")
    by = result["by_module"]

    components = (
        (output_label("alpha_mol_abs"),  by["m4"]["alpha_mol_abs"]),
        (output_label("alpha_mol_scat"), by["m4"]["alpha_mol_scat"]),
        (output_label("alpha_aer_abs"),  by["m4"]["alpha_aer_abs"]),
        (output_label("alpha_aer_scat"), by["m4"]["alpha_aer_scat"]),
    )
    total = by["m4"]["alpha_atm"]

    if total <= 0:
        st.info("Total extinction is zero — vacuum or negligible path extinction.")
        return

    rows = [
        {
            "Component": label,
            "α (1/km)":  f"{value * 1000:.4f}",
            "Share":     f"{value / total * 100:.1f}%",
        }
        for label, value in components
    ]
    rows.append({
        "Component": output_label("alpha_atm"),
        "α (1/km)":  f"{total * 1000:.4f}",
        "Share":     "100.0%",
    })
    st.table(rows)


# ---------------------------------------------------------------------------
# Aggregate renderer.
# ---------------------------------------------------------------------------
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
