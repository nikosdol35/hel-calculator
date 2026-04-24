"""Tabbed result renderers per SPEC §5.2 (Phase 3 PR 3 rewrite).

Each ``render_tab_<name>`` function takes the orchestrator's merged-result
dict (plus a reference range where relevant, and an optional range-sweep
sample list for the Engagement tab) and renders that tab's content to
the active Streamlit surface. ``ui/app.py`` calls these six functions
inside the six ``st.tabs(...)`` panes in reading order:

    Overview → Engagement → Target effects → Safety → Atmosphere → Diagnostics

The renderers return ``None``; they write to Streamlit, not to a structured
object. The caller merges ``user_inputs`` into the result dict before
passing it in so entries like ``result['M2']`` and ``result['sigma_jit']``
are available without changing the ARCH §6.4 signature.

**PR 3 changes versus PR 2:**

* Single-scroll five-section layout (``render_panel_1`` … ``render_panel_5``
  + ``render_all``) is replaced by six tab renderers. The tab IA matches
  the plan's reading order: Overview answers "can I engage?" in one glance;
  Engagement carries the spot-and-Strehl decomposition and the three
  range-sweep plots; Safety holds both NOHD conventions + laser class;
  Atmosphere holds the extinction breakdown; Diagnostics holds the
  severity-sorted flag list and convergence status.
* ``render_panel_*`` names removed — no test or external caller referenced
  them; ``render_all`` is likewise gone now that ``app.py`` drives each
  tab directly.
* The severity classifier (``_SEVERITY_PATTERNS``, ``_classify_flag_severity``)
  is preserved byte-for-byte — ``tests/test_outputs_severity.py`` pins it.

References:
    SPEC.md §5.2 — per-tab contract (what reads on each tab).
    SPEC.md §5.3 items 8–11 — numeric-display, verdict chip, flag severity.
    ARCHITECTURE.md §6.4 — public signatures.
    ARCHITECTURE.md §6.9 — ui/components.py helpers.
    ui/labels.py — OUTPUT_LABELS, VERDICT_TEMPLATES, ADVISORY (all user copy).
    ui/components.py — metric_card, status_chip, section_header, format_value.
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
    ADVISORY,
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
# Verdict chip — shared between Overview and the flag classifier
# =============================================================================

def _verdict_chip(result: dict) -> None:
    """Render the three-tier verdict chip (ENGAGEABLE / MARGINAL / NOT ENGAGEABLE).

    Thresholds per SPEC §5.2 Overview verdict:

      * τ_BT ≤ 0      → ``ok``    — "ENGAGEABLE — instantaneous"
      * dwell ≤ 0     → ``error`` — "NOT ENGAGEABLE — no dwell available"
      * margin ≥ 30%  → ``ok``    — "ENGAGEABLE — {margin}% margin"
      * 0 ≤ m < 30%   → ``warn``  — "MARGINAL — {margin}% margin"
      * margin < 0    → ``error`` — "NOT ENGAGEABLE — exceeds dwell by {shortfall}%"
    """
    by = result["by_module"]
    tau_bt = by["m8"].get("tau_BT")
    dwell = by["m3"].get("available_dwell")

    if tau_bt is None or tau_bt <= 0.0:
        status_chip(VERDICT_TEMPLATES["instant"], "ok")
        return
    if dwell is None or dwell <= 0.0:
        status_chip(VERDICT_TEMPLATES["no_dwell"], "error")
        return

    margin = (dwell - tau_bt) / tau_bt
    if margin >= 0.30:
        status_chip(VERDICT_TEMPLATES["ok"].format(margin=margin * 100), "ok")
    elif margin >= 0.0:
        status_chip(VERDICT_TEMPLATES["warn"].format(margin=margin * 100), "warn")
    else:
        status_chip(
            VERDICT_TEMPLATES["error"].format(shortfall=abs(margin) * 100),
            "error",
        )


# =============================================================================
# Overview tab — verdict + six top-line KPIs + compute headroom
# =============================================================================

def render_tab_overview(result: dict) -> None:
    """Render the Overview tab.

    Reads in one glance: engagement verdict first, then the six KPIs that
    answer "can I engage this target with this system?" — power in the
    aimpoint, peak irradiance, burn-through time, available dwell, wall-
    plug input power, waste heat. Two secondary compute-headroom cards
    (sustain time, engagements per hour) sit below the primary row so the
    same tab carries the "can I engage repeatedly?" read.
    """
    section_header("Engagement verdict")
    _verdict_chip(result)

    st.write("")  # small vertical spacer

    by = result["by_module"]
    p_aim = by["m7"]["P_aim"]
    i_peak = by["m7"]["I_peak"]
    tau_bt = by["m8"].get("tau_BT")
    dwell = by["m3"].get("available_dwell")
    p_in = by["m10"]["P_in"]
    q_waste = by["m10"]["Q_waste"]

    section_header("Engagement summary")
    c1, c2, c3 = st.columns(3)
    with c1: _card("P_aim",   p_aim)
    with c2: _card("I_peak",  i_peak)
    with c3: _card("tau_BT",  tau_bt)

    c1, c2, c3 = st.columns(3)
    with c1: _card("available_dwell", dwell)
    with c2: _card("P_in",    p_in)
    with c3: _card("Q_waste", q_waste)

    # --- Secondary row: compute headroom ------------------------------------
    t_sustain = by["m10"]["t_sustain"]
    eng_per_hr = by["m10"]["engagements_per_hour"]

    section_header("Compute headroom")
    c1, c2 = st.columns(2)
    with c1:
        if math.isfinite(t_sustain):
            _card("t_sustain", t_sustain, size="md")
        else:
            metric_card(
                output_label("t_sustain"),
                "∞ thermally unlimited",
                unit="",
                tooltip=output_tooltip("t_sustain"),
                size="md",
            )
    with c2:
        _card("engagements_per_hour", eng_per_hr, size="md")


# =============================================================================
# Engagement tab — spot-and-Strehl decomposition + range-sweep plots
# =============================================================================

def render_tab_engagement(
    result: dict,
    reference_range: float,
    *,
    sweep: list[dict] | None = None,
) -> None:
    """Render the Engagement tab.

    Two-part content:

    1. **Spot & Strehl at the reference range** — angular-error split
       (ideal-Gaussian diffraction, M² excess, turbulence, jitter) and
       Strehl decomposition (S_TB · S_opt), plus the effective peak-
       irradiance ratio vs the diffraction-limited baseline.
    2. **Range-sweep plots** (when ``sweep`` is supplied) — on-target
       performance, time-to-burn-through, beam-diameter breakdown.

    The sweep argument is optional so the renderer stays usable in
    unit-test harnesses that do not materialise a sweep.

    Args:
        result: Merged orchestrator result dict.
        reference_range: The slant-range (m) at which the spot-and-Strehl
            split is evaluated. Drives the section header caption and
            the full-angle turbulence conversion.
        sweep: Optional list of merged-result dicts, one per slant-range
            sample, with a ``"range"`` key added per sample. When
            present, the three range-sweep plots render below the
            spot/Strehl section.
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

    # --- Range-sweep plots --------------------------------------------------
    if sweep is None:
        return

    # Import the plots module locally — keeps the unit-test import surface
    # of ui/outputs.py light (tests that only exercise the severity
    # classifier do not need plotly loaded).
    from ui import plots

    section_header("Range-sweep plots")
    try:
        st.plotly_chart(
            plots.plot_a_on_target_performance(sweep),
            use_container_width=True,
        )
        st.plotly_chart(
            plots.plot_b_time_to_burnthrough(sweep),
            use_container_width=True,
        )
        st.plotly_chart(
            plots.plot_c_beam_diameter_breakdown(sweep),
            use_container_width=True,
        )
    except ValueError as exc:
        st.warning(
            f"Range-sweep skipped ({exc}); single-point results above are valid."
        )


# =============================================================================
# Target effects tab — burn-through + target properties context
# =============================================================================

def render_tab_target_effects(result: dict) -> None:
    """Render the Target effects tab.

    Shows the burn-through outcome (``τ_BT`` and the material context that
    drives it — material name, thickness, absorbance, back-side BC) so the
    user can reason about what changes if they pick a different material
    or aimpoint. Temperature-vs-time and material-comparison plots are
    PR 5 scope.
    """
    section_header("Burn-through outcome")

    by = result["by_module"]
    tau_bt = by["m8"].get("tau_BT")
    dwell = by["m3"].get("available_dwell")

    c1, c2 = st.columns(2)
    with c1: _card("tau_BT", tau_bt)
    with c2: _card("available_dwell", dwell)

    # Advisory when burn-through is not reached in the available dwell.
    if tau_bt is not None and dwell is not None and tau_bt > dwell > 0.0:
        st.warning(ADVISORY["no_burnthrough"])

    # --- Target context -----------------------------------------------------
    # Pull user-input values the app merged into ``result``. Defaults guard
    # the unit-test / missing-key paths without crashing the page.
    section_header("Target context")
    material = str(result.get("material", "—"))
    thickness = result.get("thickness")  # m
    a_lambda = by["m8"].get("A_lambda")
    a_lambda_flagged = bool(by["m8"].get("A_lambda_flagged", False))
    backside_bc = str(result.get("backside_BC", "—"))

    c1, c2, c3, c4 = st.columns(4)
    with c1:
        metric_card("Target material", material, unit="", size="md")
    with c2:
        # Display thickness in mm regardless of orchestrator's SI m.
        thickness_mm = thickness * 1000.0 if thickness is not None else None
        metric_card(
            "Target thickness",
            thickness_mm,
            unit="mm",
            size="md",
        )
    with c3:
        metric_card(
            "Absorbance A_λ",
            a_lambda,
            unit="",
            flag_est=a_lambda_flagged,
            size="md",
            sig_figs=3,
        )
    with c4:
        metric_card(
            "Back-side condition",
            backside_bc,
            unit="",
            size="md",
        )

    st.caption(
        "Temperature-vs-time and material-comparison plots arrive in a "
        "future release."
    )


# =============================================================================
# Safety tab — both NOHD conventions + laser class
# =============================================================================

def render_tab_safety(result: dict) -> None:
    """Render the Safety tab.

    Both Nominal Ocular Hazard Distance conventions (top-hat and Gaussian-
    peak) sit side-by-side; the user cites whichever is appropriate for
    the specific safety case. Laser class reads as a plain-string card.
    The hazard-zone cross-section schematic is PR 5 scope.
    """
    section_header("Nominal Ocular Hazard Distance")

    by = result["by_module"]
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
# Atmosphere tab — extinction breakdown
# =============================================================================

def render_tab_atmosphere(result: dict) -> None:
    """Render the Atmosphere tab.

    Shows the total extinction coefficient split into its four contributing
    components (molecular absorption, molecular scattering, aerosol
    absorption, aerosol scattering) with per-component percentage share.
    PR 5 replaces the tabular view with a horizontal stacked-bar plot.
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
        st.info(ADVISORY["vacuum_path"])
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
# Diagnostics tab — severity-sorted assumption chips + convergence status
# =============================================================================
# The severity classifier below is pinned by ``tests/test_outputs_severity.py``
# and must not change without updating the pinning test. Each keyword maps to
# one of ``error | warn | info | ok``; first-match-wins; unmatched flags fall
# back to ``info`` — the calmest tier — because the flag is in the list by
# virtue of a physics module appending it, and that alone is worth surfacing.

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


def render_tab_diagnostics(result: dict) -> None:
    """Render the Diagnostics tab.

    Two sections:

    1. **Assumption flags** — always-visible, severity-sorted chip list.
       Showing the user exactly what defaults and approximations feed
       into the displayed numbers is a hard contract; this section cannot
       be collapsed. Chips are ordered ``error → warn → info → ok`` so
       the most important read first.
    2. **Convergence status** — the M6↔M7 blooming–focusing loop
       iteration count and converged flag, as a small card + caption.
    """
    section_header("Assumptions & flags")
    flags = result.get("assumptions_flagged", [])
    if not flags:
        st.info("No assumption flags raised for this input set.")
    else:
        # Classify and stable-sort. ``sorted(..., key=...)`` is stable, so
        # flags of the same severity retain the order the physics modules
        # appended them — useful when two related flags want to read
        # together.
        classified = [(flag, _classify_flag_severity(flag)) for flag in flags]
        classified.sort(key=lambda pair: _SEVERITY_ORDER[pair[1]])

        for flag, severity in classified:
            status_chip(flag, severity)

    # --- Convergence status --------------------------------------------------
    st.write("")  # spacer
    section_header("Convergence status")
    iter_count = result.get("m67_iteration_count")
    converged = result.get("m67_converged")

    c1, c2 = st.columns(2)
    with c1:
        metric_card(
            "Loop iterations",
            iter_count,
            unit="",
            tooltip="Blooming–focusing self-consistency loop iteration count.",
            size="md",
        )
    with c2:
        metric_card(
            "Converged",
            "yes" if converged else "no",
            unit="",
            tooltip="Whether the blooming–focusing loop reached its tolerance.",
            size="md",
        )
