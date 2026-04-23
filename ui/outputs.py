"""Five numeric output panels per SPEC §5.2.

Each ``render_panel_N`` function takes the orchestrator's merged-result
dict (plus a reference range for Panel 1) and renders the panel's
content to the active Streamlit column. All public functions return
``None``; they write to Streamlit, not to a structured object.

The caller (``ui/app.py``) merges the user input dict into the result
dict before passing it in, so entries like ``result['M2']`` and
``result['sigma_jit']`` are available without changing the ARCH §6.4
signature. Panel 1 uses this to split M1's ``theta_diff`` into the
``θ_diff_pure`` / ``θ_M²_excess`` display values and to compute the
full-angle jitter ``θ_jit = 2·σ_jit``. Fallbacks (``.get(..., 0.0)``)
keep the panels defensive if a caller passes only the module outputs.

References:
    SPEC.md §5.2 (panel contracts — Panel 1 through Panel 5).
    ARCHITECTURE.md §6.4 (public signatures; file length ~180 lines).
"""

from __future__ import annotations

import math

import streamlit as st

from ui.style import COLOR_CAUTION, COLOR_SUCCESS, COLOR_WARNING


# ---------------------------------------------------------------------------
# Panel 1 — Spot broadening & Strehl decomposition at reference range.
# ---------------------------------------------------------------------------
def render_panel_1_spot_strehl(result: dict, reference_range: float) -> None:
    """Panel 1: spot-broadening and Strehl decomposition at reference range.

    Displays the angular-error split (θ_diff_pure / θ_M²_excess / θ_turb /
    θ_jit in µrad), the Strehl decomposition (S_TB · S_opt), and the
    effective peak-irradiance ratio vs the diffraction-limited baseline
    ``S_TB · (w_diff / w_total)²``.

    Units: all angles rendered in µrad (full-angle, Siegman convention
    per SPEC §1.2); Strehl factors dimensionless, shown to 3 decimals.
    """
    st.subheader(
        f"Panel 1 — Spot & Strehl Decomposition "
        f"@ {reference_range / 1000:.2f} km"
    )

    by = result["by_module"]

    # Angular-error split. M1: theta_diff = M² · 4λ / (π·D). So
    # θ_diff_pure = theta_diff / M² (the M²=1 limit), and
    # θ_M²_excess = theta_diff − θ_diff_pure = (1 − 1/M²) · theta_diff.
    theta_diff_full = by["m1"]["theta_diff"]
    M2 = float(result.get("M2", 1.0))
    theta_diff_pure = theta_diff_full / M2 if M2 > 0 else theta_diff_full
    theta_M2_excess = theta_diff_full - theta_diff_pure

    # θ_turb and θ_jit at the reference range (full-angle).
    L = max(reference_range, 1.0)
    theta_turb = 2.0 * by["m5"]["w_turb"] / L  # w_turb is 1/e² radius
    theta_jit = 2.0 * float(result.get("sigma_jit", 0.0))  # 2·σ_jit (full angle)

    c1, c2, c3, c4 = st.columns(4)
    c1.metric("θ_diff_pure", f"{theta_diff_pure * 1e6:.2f} µrad")
    c2.metric("θ_M² excess", f"{theta_M2_excess * 1e6:.2f} µrad")
    c3.metric("θ_turb",       f"{theta_turb * 1e6:.2f} µrad")
    c4.metric("θ_jit",        f"{theta_jit * 1e6:.2f} µrad")

    # Strehl decomposition. S_opt is fixed at 1.0 in v1 (SPEC §3 M6
    # critical note — only S_TB and S_opt; turbulence enters via w_turb).
    S_TB = by["m6"]["S_TB"]
    S_opt = 1.0

    w_diff = by["m7"]["w_diff"]
    w_total = by["m7"]["w_total"]
    # Effective ratio vs diff-limited baseline.
    eff_ratio = S_TB * (w_diff ** 2) / max(w_total ** 2, 1e-30)

    c1, c2, c3 = st.columns(3)
    c1.metric("S_TB",   f"{S_TB:.3f}")
    c2.metric("S_opt",  f"{S_opt:.3f}")
    c3.metric("I_peak / I_peak,diff-lim", f"{eff_ratio:.3f}")

    st.caption(
        "Angles are **full-angle** (Siegman convention per SPEC §1.2). "
        "Effective peak ratio = S_TB · (w_diff / w_total)² — ratio to the "
        "diffraction-limited, turbulence- and blooming-free baseline."
    )


# ---------------------------------------------------------------------------
# Panel 2 — Engagement summary with three-tier verdict.
# ---------------------------------------------------------------------------
def render_panel_2_engagement(result: dict) -> None:
    """Panel 2: engagement summary with traffic-light verdict + margin.

    Three-tier verdict per SPEC §5.2 Panel 2:
      - margin ≥ 30%  → "ENGAGEABLE"       (green, COLOR_SUCCESS)
      - 0% ≤ margin < 30% → "MARGINAL"      (amber, COLOR_WARNING)
      - margin < 0%   → "NOT ENGAGEABLE"   (red,   COLOR_CAUTION)
      - τ_BT ≤ 0      → "ENGAGEABLE — instantaneous"
      - dwell ≤ 0     → "NOT ENGAGEABLE — no dwell available"
    """
    st.subheader("Panel 2 — Engagement Summary")

    by = result["by_module"]
    P_aim = by["m7"]["P_aim"]
    I_avg_aim = by["m7"]["I_avg_aim"]
    I_peak = by["m7"]["I_peak"]
    tau_BT = by["m8"].get("tau_BT")
    dwell = by["m3"].get("available_dwell")

    c1, c2, c3 = st.columns(3)
    c1.metric("P_aim",     f"{P_aim / 1000:.2f} kW")
    c2.metric("I_avg_aim", f"{I_avg_aim / 1e4:.1f} W/cm²")
    c3.metric("I_peak",    f"{I_peak / 1e4:.1f} W/cm²")

    c1, c2 = st.columns(2)
    c1.metric("τ_BT",            f"{tau_BT:.2f} s" if tau_BT is not None else "—")
    c2.metric("Available dwell", f"{dwell:.2f} s" if dwell is not None else "—")

    # Verdict — edge cases per SPEC §5.2 Panel 2.
    if tau_BT is None or tau_BT <= 0.0:
        _render_verdict("ENGAGEABLE — instantaneous", COLOR_SUCCESS)
        return
    if dwell is None or dwell <= 0.0:
        _render_verdict("NOT ENGAGEABLE — no dwell available", COLOR_CAUTION)
        return

    margin = (dwell - tau_BT) / tau_BT
    if margin >= 0.30:
        _render_verdict(f"ENGAGEABLE — {margin * 100:.0f}% margin", COLOR_SUCCESS)
    elif margin >= 0.0:
        _render_verdict(f"MARGINAL — {margin * 100:.0f}% margin", COLOR_WARNING)
    else:
        _render_verdict(
            f"NOT ENGAGEABLE — exceeds dwell by {abs(margin) * 100:.0f}%",
            COLOR_CAUTION,
        )


def _render_verdict(text: str, color: str) -> None:
    """Render a colored verdict banner (inline HTML for a colored pill)."""
    st.markdown(
        f"<div style='padding:12px;border-radius:6px;background:{color};"
        f"color:white;font-weight:600;font-size:18px;text-align:center;"
        f"margin-top:8px;margin-bottom:8px'>{text}</div>",
        unsafe_allow_html=True,
    )


# ---------------------------------------------------------------------------
# Panel 3 — System feasibility (power, thermal, safety).
# ---------------------------------------------------------------------------
def render_panel_3_feasibility(result: dict) -> None:
    """Panel 3: system feasibility — power, cooling, engagement count, NOHD.

    NOHD is reported in BOTH top-hat and Gaussian-peak conventions per
    SPEC §3 M9 critical note; users cite the one appropriate for their
    safety case.
    """
    st.subheader("Panel 3 — System Feasibility")

    by = result["by_module"]
    P_in = by["m10"]["P_in"]
    Q_waste = by["m10"]["Q_waste"]
    t_sustain = by["m10"]["t_sustain"]
    engagements_per_hour = by["m10"]["engagements_per_hour"]

    c1, c2, c3, c4 = st.columns(4)
    c1.metric("P_in",      f"{P_in / 1000:.1f} kW")
    c2.metric("Q_waste",   f"{Q_waste / 1000:.1f} kW")
    if math.isfinite(t_sustain):
        c3.metric("t_sustain", f"{t_sustain:.1f} s")
    else:
        c3.metric("t_sustain", "∞ (thermally unlimited)")
    c4.metric("Eng/hr",    f"{engagements_per_hour:.1f}")

    NOHD_th = by["m9"].get("NOHD_tophat", 0.0)
    NOHD_gp = by["m9"].get("NOHD_gausspeak", 0.0)
    laser_class = by["m9"].get("laser_class", "—")

    c1, c2, c3 = st.columns(3)
    c1.metric("NOHD (top-hat)",    f"{NOHD_th / 1000:.2f} km")
    c2.metric("NOHD (Gauss-peak)", f"{NOHD_gp / 1000:.2f} km")
    c3.metric("Laser class",       laser_class)
    st.caption(
        "NOHD is reported in BOTH conventions per SPEC §3 M9 — cite the "
        "one appropriate for the specific safety case."
    )


# ---------------------------------------------------------------------------
# Panel 4 — Always-visible assumptions roll-up.
# ---------------------------------------------------------------------------
def render_panel_4_assumptions(result: dict) -> None:
    """Panel 4: always-visible list of every module's flagged assumptions.

    Per SPEC §5.3 item 4, this panel cannot be collapsed — showing the
    user exactly what defaults and approximations feed into the displayed
    numbers.
    """
    st.subheader("Panel 4 — Assumptions & Flags")
    flags = result.get("assumptions_flagged", [])
    if not flags:
        st.info("No assumption flags raised for this input set.")
        return
    st.markdown("\n".join(f"- {f}" for f in flags))


# ---------------------------------------------------------------------------
# Panel 5 — Atmospheric extinction α breakdown.
# ---------------------------------------------------------------------------
def render_panel_5_atmosphere_breakdown(result: dict) -> None:
    """Panel 5: α_atm decomposition into molecular + aerosol absorption /
    scattering (per SPEC §5.2 Panel 5). Shown in 1/km and as a percentage
    share of the total."""
    st.subheader("Panel 5 — Atmospheric Extinction Breakdown")
    by = result["by_module"]

    components = (
        ("α_mol_abs  (molecular absorption)",  by["m4"]["alpha_mol_abs"]),
        ("α_mol_scat (molecular scattering)",  by["m4"]["alpha_mol_scat"]),
        ("α_aer_abs  (aerosol absorption)",    by["m4"]["alpha_aer_abs"]),
        ("α_aer_scat (aerosol scattering)",    by["m4"]["alpha_aer_scat"]),
    )
    total = by["m4"]["alpha_atm"]

    if total <= 0:
        st.info("α_atm = 0 (vacuum or negligible path extinction).")
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
        "Component": "TOTAL α_atm",
        "α (1/km)":  f"{total * 1000:.4f}",
        "Share":     "100.0%",
    })
    st.table(rows)


# ---------------------------------------------------------------------------
# Aggregate renderer.
# ---------------------------------------------------------------------------
def render_all(result: dict, reference_range: float) -> None:
    """Render all five panels in SPEC §5.2 top-to-bottom order."""
    render_panel_1_spot_strehl(result, reference_range)
    render_panel_2_engagement(result)
    render_panel_3_feasibility(result)
    render_panel_4_assumptions(result)
    render_panel_5_atmosphere_breakdown(result)
