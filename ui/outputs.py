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

import csv
import io
import math
from typing import Literal

import streamlit as st

from ui.components import (
    explanation,
    metric_card,
    section_header,
    status_chip,
)
from ui.labels import (
    ADVISORY,
    EXPLANATIONS,
    MATERIAL_DISPLAY_NAMES,
    VERDICT_TEMPLATES,
    output_label,
    output_tooltip,
    output_unit,
    verdict_explanation,
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
    # SPEC v2.0 §3 M3 — engagement-end slant range, displayed in km
    "R_at_dwell_end": 1e-3,
    # SPEC v2.0 §3 M8 — kill range, displayed in km
    "R_at_kill":      1e-3,
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
    size: Literal["lg", "md"] = "lg",
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
# CSV snapshot — Overview-tab export of the numeric result set
# =============================================================================
# One row per metric, four columns (Label, Value, Unit, Flag). Values are
# the display-unit numbers the user sees on screen (matches ``format_value``
# output on the metric cards), so the CSV pastes directly into a report
# or spreadsheet without a follow-up SI-to-display conversion step.
#
# ``_CSV_METRIC_KEYS`` is the curated ordered list — not every key in
# ``by_module`` is worth exporting. The ordering matches the app's
# reading order (Overview → Engagement → Target → Safety → Atmosphere)
# so someone scanning the CSV top-to-bottom sees the same story.

_CSV_METRIC_KEYS: tuple[tuple[str, str], ...] = (
    # (submodule_key, output_key). Overview hero row first.
    ("m7",  "P_aim"),
    ("m7",  "I_peak"),
    ("m7",  "I_avg_aim"),
    ("m7",  "PIB"),
    ("m8",  "tau_BT"),
    ("m8",  "T_surface_peak"),
    ("m3",  "available_dwell"),
    ("m10", "P_in"),
    ("m10", "Q_waste"),
    ("m10", "t_sustain"),
    ("m10", "engagements_per_hour"),
    # Strehl + spot breakdown.
    ("m7",  "S_TB"),
    ("m7",  "S_opt"),
    ("m7",  "S_total"),
    ("m7",  "w_total"),
    ("m7",  "w_diff"),
    ("m7",  "w_turb"),
    ("m7",  "w_jit"),
    ("m7",  "w_bloom"),
    # Safety + atmosphere.
    ("m9",  "NOHD_tophat"),
    ("m9",  "NOHD_gausspeak"),
    ("m4",  "alpha_atm"),
    ("m4",  "alpha_mol_abs"),
    ("m4",  "alpha_mol_scat"),
    ("m4",  "alpha_aer_abs"),
    ("m4",  "alpha_aer_scat"),
)


def _csv_value_for(scaled: float | int | str | None) -> str:
    """Stringify a scaled value for CSV output.

    Numeric values render with six significant figures (engineers want
    more precision in the data file than the on-screen card shows).
    Non-finite or ``None`` renders as an empty cell so the CSV stays
    spreadsheet-compatible.
    """
    if scaled is None:
        return ""
    if isinstance(scaled, str):
        return scaled
    try:
        fval = float(scaled)
    except (TypeError, ValueError):
        return ""
    if not math.isfinite(fval):
        return ""
    return f"{fval:.6g}"


def _build_csv_snapshot(result: dict) -> str:
    """Assemble the Overview-tab CSV snapshot as a single string.

    Four columns: Label, Value, Unit, Flag. One row per metric in
    ``_CSV_METRIC_KEYS`` that is present in the result dict, preceded
    by a verdict row and followed by one row per entry in
    ``assumptions_flagged``. Uses ``csv.writer`` so embedded commas /
    quotes in flag strings are escaped correctly.
    """
    buf = io.StringIO()
    writer = csv.writer(buf, lineterminator="\n")
    writer.writerow(("Label", "Value", "Unit", "Flag"))

    # Verdict summary row (reproduces the Overview chip).
    by = result.get("by_module", {})
    tau_bt = by.get("m8", {}).get("tau_BT")
    dwell = by.get("m3", {}).get("available_dwell")
    verdict_text: str
    if tau_bt is None or (isinstance(tau_bt, (int, float)) and tau_bt <= 0.0):
        verdict_text = "Engageable (instantaneous)"
    elif dwell is None or (isinstance(dwell, (int, float)) and dwell <= 0.0):
        verdict_text = "Not engageable (no dwell)"
    else:
        margin = (dwell - tau_bt) / tau_bt
        if margin >= 0.30:
            verdict_text = f"Engageable ({margin * 100:.0f}% margin)"
        elif margin >= 0.0:
            verdict_text = f"Marginal ({margin * 100:.0f}% margin)"
        else:
            verdict_text = f"Not engageable (exceeds dwell by {abs(margin) * 100:.0f}%)"
    writer.writerow(("Engagement verdict", verdict_text, "", ""))

    # Per-metric rows.
    for module_key, output_key in _CSV_METRIC_KEYS:
        module = by.get(module_key, {})
        if output_key not in module:
            continue
        # Defense-in-depth: skip any output key without a user-facing label
        # entry. Prevents a future _CSV_METRIC_KEYS / OUTPUT_LABELS drift
        # from crashing the Overview tab (and, because st.tabs() renders
        # every tab body on every rerun, the whole app).
        try:
            label = output_label(output_key)
            unit = output_unit(output_key)
        except KeyError:
            continue
        raw = module[output_key]
        scaled = raw if isinstance(raw, str) else _scale(output_key, raw)
        # T_surface_peak is the only additive-offset conversion in the app
        # (kelvin → celsius). ``_DISPLAY_SCALE`` is multiplicative only,
        # so this special case lives here rather than polluting the scale
        # table with a non-scalar entry.
        if output_key == "T_surface_peak" and isinstance(scaled, (int, float)):
            scaled = float(scaled) - 273.15
        if isinstance(raw, str):
            unit = ""
        writer.writerow((label, _csv_value_for(scaled), unit, ""))

    # Assumption-flag rows.
    flags = result.get("assumptions_flagged", [])
    for flag in flags:
        writer.writerow(("Assumption flag", "", "", str(flag)))

    return buf.getvalue()


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

    # Plain-language explanation right under the chip — tells a non-specialist
    # reader *why* the engagement is (or is not) feasible, quoting the two
    # time values the verdict compares. ``verdict_explanation`` in labels.py
    # mirrors the branching in ``_verdict_chip`` so the prose and chip always
    # agree on which tier applies.
    explanation(verdict_explanation(result))

    by = result["by_module"]
    p_aim = by["m7"]["P_aim"]
    i_peak = by["m7"]["I_peak"]
    tau_bt = by["m8"].get("tau_BT")
    dwell = by["m3"].get("available_dwell")
    p_in = by["m10"]["P_in"]
    q_waste = by["m10"]["Q_waste"]

    section_header("Engagement summary")
    explanation(EXPLANATIONS["overview_summary"])
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
    explanation(EXPLANATIONS["overview_headroom"])
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

    # --- Hero chart: dwell vs burn-through ----------------------------------
    # Local imports keep the unit-test import surface of ui/outputs.py light.
    from ui import plots
    from ui.theme import PLOTLY_MODEBAR_CONFIG

    section_header("Engagement margin")
    st.plotly_chart(
        plots.plot_overview_dwell_vs_burnthrough(dwell, tau_bt),
        use_container_width=True,
        config=PLOTLY_MODEBAR_CONFIG,
    )
    explanation(EXPLANATIONS["overview_margin_plot"], variant="plot")

    # --- CSV snapshot export ----------------------------------------------
    # A small footer button that hands the user a four-column CSV of the
    # on-screen numeric result set so it can drop straight into a report
    # or spreadsheet. Kept at the bottom of the Overview tab so it is the
    # last thing in the default reading order — the engineer has already
    # seen the verdict and the KPIs by the time they reach it.
    from ui.labels import BUTTON_LABELS  # local import — single use.

    st.download_button(
        label=BUTTON_LABELS["export_csv"],
        data=_build_csv_snapshot(result),
        file_name="hel-analysis-snapshot.csv",
        mime="text/csv",
        key="_overview_csv_download",
        help=(
            "Download the on-screen numeric result set as a CSV — one row "
            "per metric (Label, Value, Unit, Flag), followed by any "
            "active assumption flags. Pastes straight into a spreadsheet."
        ),
    )


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
    explanation(EXPLANATIONS["engagement_spot_strehl"])

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
    # Import the plots module and the modebar config locally — keeps the
    # unit-test import surface of ui/outputs.py light (tests that only
    # exercise the severity classifier do not need plotly loaded).
    from ui import plots
    from ui.theme import PLOTLY_MODEBAR_CONFIG

    section_header("Range-sweep plots")

    # Log / linear toggle for the wide-dynamic-range peak-irradiance panel.
    # A visible radio is more engineer-legible than burying the choice in
    # the Plotly modebar. When ``sweep`` is None the radio still renders
    # (so the control stays put across feasible / infeasible states) but
    # the plot below is the frame-with-advisory form.
    scale_choice = st.radio(
        "Peak-irradiance axis scale",
        options=("linear", "log"),
        horizontal=True,
        index=0,
        key="_plot_a_scale",
    )
    log_y = scale_choice == "log"

    # Always render every frame — when sweep is None/empty, each
    # constructor returns a frame-only figure with a centered advisory
    # (SPEC §5.3 item 10: no silent plot skip on infeasible geometry).
    # An ``explanation(..., variant="plot")`` sits under each chart so
    # a non-specialist viewer reads what the curves mean in two sentences.
    #
    # Reading order: a verdict-shaped go/no-go (G) above the diagnostic
    # stack; on-target performance (A) and time budget (B) next; the
    # margin reframing of B (E) immediately after; then the broadening
    # diagnostics (C → D).
    d_aim_si = result.get("d_aim")
    st.plotly_chart(
        plots.plot_g_spot_vs_bucket(sweep, d_aim=d_aim_si),
        use_container_width=True,
        config=PLOTLY_MODEBAR_CONFIG,
    )
    explanation(EXPLANATIONS["plot_g_intro"], variant="plot")
    st.plotly_chart(
        plots.plot_a_on_target_performance(sweep, log_y=log_y),
        use_container_width=True,
        config=PLOTLY_MODEBAR_CONFIG,
    )
    explanation(EXPLANATIONS["plot_a_intro"], variant="plot")
    st.plotly_chart(
        plots.plot_b_time_to_burnthrough(sweep),
        use_container_width=True,
        config=PLOTLY_MODEBAR_CONFIG,
    )
    explanation(EXPLANATIONS["plot_b_intro"], variant="plot")
    st.plotly_chart(
        plots.plot_e_engagement_margin_vs_range(
            sweep, reference_range=reference_range,
        ),
        use_container_width=True,
        config=PLOTLY_MODEBAR_CONFIG,
    )
    explanation(EXPLANATIONS["plot_e_intro"], variant="plot")
    st.plotly_chart(
        plots.plot_c_beam_diameter_breakdown(sweep),
        use_container_width=True,
        config=PLOTLY_MODEBAR_CONFIG,
    )
    explanation(EXPLANATIONS["plot_c_intro"], variant="plot")
    st.plotly_chart(
        plots.plot_d_blooming_distortion_number(
            sweep, reference_range=reference_range,
        ),
        use_container_width=True,
        config=PLOTLY_MODEBAR_CONFIG,
    )
    explanation(EXPLANATIONS["plot_d_intro"], variant="plot")


# =============================================================================
# Target effects tab — burn-through + target properties context
# =============================================================================

def render_tab_target_effects(result: dict) -> None:
    """Render the Target effects tab.

    Shows the burn-through outcome (``τ_BT`` and the material context that
    drives it — material name, thickness, absorbance, back-side BC), a
    simplified temperature envelope, and a burn-through-comparison bar
    across the seven v1 materials at the current reference-range flux.
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
        metric_card(
            "Target material",
            MATERIAL_DISPLAY_NAMES.get(material, material),
            unit="",
            size="md",
        )
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

    # --- Plots: temperature envelope + material comparison -------------------
    from ui import plots
    from ui.theme import PLOTLY_MODEBAR_CONFIG

    section_header("Temperature envelope")
    # Assemble °C endpoints. Orchestrator carries T_ambient in K through
    # the merged inputs, and m8 reports T_surface_peak in K; material
    # T_fail lives in physics.m8_material_tables. The plot constructor
    # is unit-neutral and expects °C for readable axis numbers.
    t_amb_k = result.get("T_ambient")
    t_peak_k = by["m8"].get("T_surface_peak")
    t_fail_k = _material_t_fail(material)
    t_amb_c = (t_amb_k - 273.15) if t_amb_k is not None else None
    t_peak_c = (t_peak_k - 273.15) if t_peak_k is not None else None
    t_fail_c = (t_fail_k - 273.15) if t_fail_k is not None else None

    st.plotly_chart(
        plots.plot_target_temperature_envelope(
            t_amb_c=t_amb_c,
            t_peak_c=t_peak_c,
            t_fail_c=t_fail_c,
            tau_bt=tau_bt,
            dwell=dwell,
        ),
        use_container_width=True,
        config=PLOTLY_MODEBAR_CONFIG,
    )
    st.caption(ADVISORY["temperature_schematic"])

    section_header("Burn-through across v1 materials")
    material_tau = _compute_material_comparison(result)
    st.plotly_chart(
        plots.plot_target_material_comparison(
            material_tau_bt=material_tau,
            material_labels=MATERIAL_DISPLAY_NAMES,
            current_material=material,
            dwell=dwell,
        ),
        use_container_width=True,
        config=PLOTLY_MODEBAR_CONFIG,
    )
    st.caption(
        "Each bar shows time-to-burn-through for that material under the "
        "same reference-range flux, thickness, wavelength, and back-side "
        "boundary. Bars to the left of the dwell marker are engageable."
    )


# -----------------------------------------------------------------------------
# Material-comparison helper — calls m8 per material, cached.
# -----------------------------------------------------------------------------

def _material_t_fail(material: str) -> float | None:
    """Look up the failure temperature (K) for a v1 material name."""
    # Lazy import: keeps outputs.py unit-test import surface clean.
    from physics.m8_material_tables import MATERIAL_PROPERTIES
    props = MATERIAL_PROPERTIES.get(material)
    if props is None:
        return None
    t_fail = props.get("T_fail")
    return float(t_fail) if t_fail is not None else None


def _compute_material_comparison(result: dict) -> dict[str, float] | None:
    """Return {material_name: tau_BT_seconds} for every v1 material.

    Calls ``m8_burnthrough.compute`` once per material, keeping every
    non-material input identical to the current analysis (flux,
    thickness, wavelength, back-side boundary, target velocity, ambient
    temperature). Entries that hit the internal timeout keep their
    sentinel value so the plot constructor can render them as
    "no burn-through" bars.

    Wrapped through a ``@st.cache_data`` bridge so the 7-call cost is
    amortised across reruns at the same inputs.
    """
    from physics.m8_material_tables import MATERIALS

    # Build a hashable key from just the inputs m8 reads.
    i_aim = result.get("by_module", {}).get("m7", {}).get("I_avg_aim")
    if i_aim is None or not math.isfinite(i_aim):
        return None
    thickness = result.get("thickness")
    wavelength = result.get("wavelength")
    backside_bc = result.get("backside_BC", "insulated")
    v_tgt = result.get("v_tgt")
    t_amb = result.get("T_ambient")
    a_lambda = result.get("A_lambda")

    if thickness is None or wavelength is None or v_tgt is None or t_amb is None:
        return None

    # mypy: the None guard above narrows the four fields; the casts below
    # are float(...) on values already known to be non-None numeric inputs.
    key = (
        float(i_aim), float(thickness), float(wavelength),
        str(backside_bc), float(v_tgt), float(t_amb),
        None if a_lambda is None else float(a_lambda),
        tuple(MATERIALS),
    )
    return _material_comparison_cached(key)


@st.cache_data(max_entries=32, show_spinner=False)
def _material_comparison_cached(key: tuple) -> dict[str, float]:
    """Cached worker: evaluates m8 once per v1 material for one frozen key."""
    from physics import m8_burnthrough
    from physics.m8_material_tables import MATERIALS

    (
        i_aim, thickness, wavelength, backside_bc,
        v_tgt, t_amb, a_lambda, _materials_tuple,
    ) = key

    out: dict[str, float] = {}
    for material in MATERIALS:
        inputs = {
            "I_aim":       i_aim,
            "material":    material,
            "thickness":   thickness,
            "wavelength":  wavelength,
            "backside_BC": backside_bc,
            "v_tgt":       v_tgt,
            "T_ambient":   t_amb,
        }
        if a_lambda is not None:
            inputs["A_lambda"] = a_lambda
        try:
            result = m8_burnthrough.compute(inputs)
            tau = float(result.get("tau_BT", math.nan))
            # no_failure_before_timeout → report as NaN so the plot's
            # timeout-bar branch renders it at the right edge.
            mode = result.get("failure_mode", "")
            if mode == "no_failure_before_timeout":
                tau = math.nan
            out[material] = tau
        except ValueError:
            # Bad input for this material (e.g. thickness outside range);
            # surface as NaN rather than crashing the whole chart.
            out[material] = math.nan
    return out


# =============================================================================
# Safety tab — both NOHD conventions + laser class
# =============================================================================

def render_tab_safety(result: dict) -> None:
    """Render the Safety tab.

    Both Nominal Ocular Hazard Distance conventions (top-hat and Gaussian-
    peak) sit side-by-side; the user cites whichever is appropriate for
    the specific safety case. Laser class reads as a plain-string card.
    A hazard-zone schematic below the cards shows the three zones on a
    single range axis — inside the Gaussian-peak NOHD (hazardous under
    both conventions), between the two NOHD values (transition zone),
    and beyond the top-hat NOHD (safe under both).
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

    # --- Hazard-zone schematic ---------------------------------------------
    from ui import plots
    from ui.theme import PLOTLY_MODEBAR_CONFIG

    section_header("Hazard zones")
    st.plotly_chart(
        plots.plot_safety_nohd_zones(
            nohd_tophat=nohd_th,
            nohd_gausspeak=nohd_gp,
        ),
        use_container_width=True,
        config=PLOTLY_MODEBAR_CONFIG,
    )


# =============================================================================
# Atmosphere tab — extinction breakdown
# =============================================================================

def render_tab_atmosphere(
    result: dict,
    *,
    sweep: list[dict] | None = None,
) -> None:
    """Render the Atmosphere tab.

    Two-part content:

    1. **Extinction breakdown** — horizontal stacked bar splitting the
       total extinction coefficient into its four physical components
       (molecular absorption, molecular scattering, aerosol absorption,
       aerosol scattering). Each segment is annotated with its share of
       the total in the hover text.
    2. **Transmission vs slant range** — line chart of τ_atm(L) across
       the orchestrator's range sweep, with a 1/e horizontal reference
       to read the characteristic attenuation length at a glance.

    The sweep argument is optional so the renderer stays usable in
    unit-test harnesses that do not materialise a sweep; when absent
    the second plot renders a frame with the infeasibility advisory
    per SPEC §5.3 item 10.
    """
    from ui import plots
    from ui.theme import PLOTLY_MODEBAR_CONFIG

    by = result["by_module"]
    alpha_mol_abs = by["m4"]["alpha_mol_abs"]
    alpha_mol_scat = by["m4"]["alpha_mol_scat"]
    alpha_aer_abs = by["m4"]["alpha_aer_abs"]
    alpha_aer_scat = by["m4"]["alpha_aer_scat"]
    total_si = by["m4"]["alpha_atm"]

    # --- Headline cards: total extinction + reference-range transmission ---
    section_header("Atmospheric summary")
    c1, c2 = st.columns(2)
    with c1: _card("alpha_atm", total_si)
    with c2: _card("tau_atm", by["m4"].get("tau_atm"), sig_figs=4)

    # --- Extinction breakdown (stacked bar) --------------------------------
    section_header("Extinction breakdown")
    st.plotly_chart(
        plots.plot_atmosphere_extinction_breakdown(
            alpha_mol_abs_si=alpha_mol_abs,
            alpha_mol_scat_si=alpha_mol_scat,
            alpha_aer_abs_si=alpha_aer_abs,
            alpha_aer_scat_si=alpha_aer_scat,
        ),
        use_container_width=True,
        config=PLOTLY_MODEBAR_CONFIG,
    )
    if total_si <= 0:
        st.info(ADVISORY["vacuum_path"])

    # --- Transmission vs range ---------------------------------------------
    section_header("Transmission vs slant range")
    st.plotly_chart(
        plots.plot_atmosphere_transmission_vs_range(sweep),
        use_container_width=True,
        config=PLOTLY_MODEBAR_CONFIG,
    )


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


def _classify_flag_severity(flag: str) -> Literal["ok", "warn", "error", "info"]:
    """Return the severity of a single assumption-flag string.

    Uses a keyword heuristic against ``_SEVERITY_PATTERNS``; first match
    wins. Unmatched flags fall back to ``"info"`` — the calmest tier —
    because a flag that exists by virtue of being in the list is worth
    surfacing, just not with escalated visual weight.
    """
    lowered = flag.lower()
    for needle, severity in _SEVERITY_PATTERNS:
        if needle in lowered:
            # _SEVERITY_PATTERNS entries are hand-curated to match the
            # Literal["ok","warn","error","info"] alphabet; the tuple-of-str
            # annotation is kept for readability, and the cast here tells
            # mypy the invariant is maintained.
            return severity  # type: ignore[return-value]
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


# =============================================================================
# How it's calculated tab — math, formulas, traceable values
# =============================================================================
# Per docs/math_tab_plan_2026-04-25.md. PR 1 ships the skeleton + glossary +
# M1/M2/M3 entries (9 metrics). PRs 2-3 fill out the remaining 32 numeric
# entries plus the 4 categorical verdicts; PR 4 adds constants + worked
# example; PR 5 adds Markdown export.
#
# Architecture: module sections are anchored markdown headers (NOT
# st.expander) because per-metric Full views nest a single st.expander
# inside, and Streamlit forbids nested expanders.

_MATH_VIEW_KEY = "_math_view_mode"
_MATH_SEARCH_KEY = "_math_search"
_MATH_SENSITIVITY_KEY = "_math_sensitivity_enabled"


@st.cache_data(max_entries=128, show_spinner=False)
def _perturbed_run(
    frozen_inputs: tuple, input_key: str, sign: int
) -> dict:
    """Run the orchestrator with one user input perturbed by ±10 %.

    Cached on (frozen_inputs, input_key, sign). With ~22 numeric inputs
    × 2 signs there are at most 44 cache entries per (frozen_inputs,)
    bucket; subsequent re-renders of the math tab in the same session
    pull from cache.

    Returns the merged-result dict in the same shape ui/app.py builds:
    user_inputs ⊕ orchestrator_result. On any validator-bound failure
    the perturbed run returns an empty dict so the sensitivity helper
    can skip that input.
    """
    from physics.orchestrator import run_full_chain

    base = dict(frozen_inputs)
    val = base.get(input_key)
    if val is None or isinstance(val, (str, bool)):
        return {}
    try:
        new_val = float(val) * (1.0 + sign * 0.10)
    except (TypeError, ValueError):
        return {}
    if new_val < 0:
        new_val = 0.0
    perturbed = {**base, input_key: new_val}
    try:
        result = run_full_chain(perturbed)
    except Exception:
        # Perturbation pushed an input outside validator bounds; signal
        # "no data" rather than propagating.
        return {}
    return {**perturbed, **result}


def _format_value_for_math_tab(key: str, value: float | int | str | None,
                                unit: str) -> str:
    """Render a value cell for the math tab (Simple-view value column).

    Reuses the existing _scale / format_value chain so the math tab and
    the metric cards can never disagree on what number is displayed.
    """
    from ui.components import format_value
    if value is None:
        return "—"
    if isinstance(value, str):
        return value
    if isinstance(value, bool):
        return "yes" if value else "no"
    scaled = _scale(key, float(value))
    return format_value(scaled, unit)


def _substitute_formula_values(entry, result: dict) -> str | None:
    """Build the 'with current values' substituted-formula string for the
    Full view. Returns None when substitution doesn't make sense
    (categorical metrics, solver-based metrics)."""
    from ui.math_content import MetricEntry
    if not isinstance(entry, MetricEntry):
        return None
    if entry.is_categorical or entry.is_solver_based:
        return None
    if entry.formula_text is None:
        return None
    # PR 1: render a simple "with values" line by listing each input + its
    # SI numeric value. PR 2 adds proper symbolic substitution into the
    # LaTeX expression.
    parts = []
    for dep in entry.formula_dependencies:
        v = result.get(dep)
        if v is None or isinstance(v, (str, bool)):
            parts.append(f"{dep} = (n/a)")
        else:
            parts.append(f"{dep} = {float(v):.4g}")
    for inp in entry.sensitivity_inputs:
        v = result.get(inp)
        if v is None or isinstance(v, (str, bool)):
            continue
        parts.append(f"{inp} = {float(v):.4g}")
    if not parts:
        return None
    return " · ".join(parts)


def _render_provenance_badges(entry) -> None:
    """Render the trust/origin badges next to a metric in Full view."""
    from ui.math_content import ProvenanceFlag
    if not entry.provenance:
        return
    chips: list[str] = []
    for flag in entry.provenance:
        if flag is ProvenanceFlag.CLAUDE_71_INVARIANT:
            chips.append(":material/verified: Audit-pinned formula")
        elif flag is ProvenanceFlag.HIGH_UNCERTAINTY:
            chips.append(":material/warning: HIGH UNCERTAINTY value")
        elif flag is ProvenanceFlag.REPLICATED:
            chips.append(":material/science: Independently replicated")
    if chips:
        st.caption(" · ".join(chips))


def _frozen_inputs_for_sensitivity(result: dict) -> tuple | None:
    """Build a hashable frozen-inputs tuple from the merged result so it
    can key the perturbation cache. The merged dict is what
    render_tab_math receives — it carries the user inputs as well as the
    orchestrator output. Returns None when the dict doesn't look like a
    real merged result (e.g. infeasible-geometry stub)."""
    user_input_keys = (
        "P0", "M2", "D", "wavelength", "eta_opt", "sigma_jit",
        "H_e", "R", "H_t", "v_tgt", "v_perp",
        "V", "RH", "T_ambient", "P_atm",
        "cn2_model", "Cn2_value", "Cn2_ground", "v_HV",
        "d_aim", "material", "thickness",
        "eta_wallplug", "Q_cool", "C_thermal", "dT_max", "t_exp",
        "backside_BC",
    )
    items = []
    for k in user_input_keys:
        v = result.get(k)
        if v is None:
            return None
        # Normalise to hashable types only.
        if isinstance(v, (int, float, str, bool)):
            items.append((k, v))
        else:
            return None
    return tuple(items)


def _render_sensitivity_bar(entry, result: dict) -> None:
    """Render the inline sensitivity line for one metric in Full view.

    Computes the ±10 % response of the metric to each user input in
    ``entry.sensitivity_inputs`` via the cached perturbation runner.
    Displays the top-3 most influential inputs as a single line.

    Skipped silently for metrics with no ``sensitivity_inputs``
    (categorical / verdict outputs)."""
    if not entry.sensitivity_inputs:
        return
    frozen = _frozen_inputs_for_sensitivity(result)
    if frozen is None:
        return

    from ui.sensitivity import (
        compute_sensitivity_for_metric, format_sensitivity_line,
    )

    def runner(input_key: str, sign: int) -> dict:
        return _perturbed_run(frozen, input_key, sign)

    sens = compute_sensitivity_for_metric(
        metric_key=entry.key,
        sensitivity_inputs=entry.sensitivity_inputs,
        base_result=result,
        base_inputs=dict(frozen),
        perturbation_runner=runner,
    )
    line = format_sensitivity_line(sens)
    st.caption(line)


def _render_metric_row(entry, result: dict, *, view_mode: str) -> None:
    """Render one metric (one row). Layout per plan §3:

    Simple view:
       1. Bold display name + symbol + (unit) on the left, value on the
          right of the same row.
       2. LaTeX formula below.
       3. "What it means" plain-language sentence below.

    Full view (when expander opens):
       4. Substituted formula with this run's input values.
       5. Citation, code reference, derivation link.
       6. Depends-on intermediates list.
       7. Provenance badges (audit-pinned / HIGH UNCERTAINTY / replicated).
       8. Assumptions list.

    Categorical and solver-based metrics skip the LaTeX block and use
    prose-style formula content instead.
    """
    # Display unit comes from the same source the per-tab metric cards
    # use — eliminates any chance of math tab vs card disagreement.
    display_unit = output_unit(entry.key)
    si_value = result.get(entry.key)
    rendered_value = _format_value_for_math_tab(
        entry.key, si_value, display_unit,
    )

    # Row header — display name + value side by side.
    h1, h2 = st.columns([3, 1])
    with h1:
        unit_suffix = f" · {display_unit}" if display_unit else ""
        st.markdown(
            f"**{entry.display_name}** · `{entry.key}`{unit_suffix}"
        )
    with h2:
        st.markdown(
            f"<div style='text-align:right; font-variant-numeric: "
            f"tabular-nums; font-weight:600;'>{rendered_value}</div>",
            unsafe_allow_html=True,
        )

    # Iteration banner (for M6↔M7 post-iteration values).
    if entry.is_iterated:
        iter_count = result.get("m67_iteration_count")
        iter_text = (
            f"this run: {int(iter_count)} iterations"
            if isinstance(iter_count, (int, float))
            else "iteration count unknown"
        )
        st.caption(
            f"Computed via the blooming–focusing self-consistency "
            f"iteration ({iter_text} to 1 % tolerance)."
        )

    # Formula block.
    if entry.is_categorical:
        # Verdict / classification — render the prose rule as a
        # mono-spaced code block rather than LaTeX. The plan §6.3
        # mockup shows this layout; it reads as "this is a rule, not
        # an equation".
        st.caption("Categorical (verdict) output — set by the rule below.")
        if entry.formula_text:
            st.code(entry.formula_text, language="text")
    elif entry.is_solver_based:
        # Multi-line formula (PDE + boundary conditions + stop rule).
        # Render the LaTeX header line if present, then the full
        # text recipe in a code block.
        if entry.formula_latex is not None:
            st.latex(entry.formula_latex)
        if entry.formula_text:
            st.code(entry.formula_text, language="text")
    elif entry.formula_latex is not None:
        st.latex(entry.formula_latex)

    # "What it means" plain-language one-liner.
    if entry.explanation_short:
        st.markdown(entry.explanation_short)

    # Full-view expander.
    if view_mode == "Full":
        with st.expander("Show full derivation", expanded=False):
            # Substituted formula with this run's values.
            sub = _substitute_formula_values(entry, result)
            if sub:
                st.markdown(f"**With this run's values:** {sub}")

            # Expert explanation.
            if entry.explanation_full:
                st.markdown(f"**Why this formula:** {entry.explanation_full}")

            # Citation chain.
            if entry.citation:
                st.markdown(f"**Citation:** {entry.citation}")
            if entry.code_ref:
                st.markdown(f"**Implemented at:** `{entry.code_ref}`")
            if entry.derivation_link:
                st.markdown(f"**Full derivation:** `{entry.derivation_link}`")

            # Symbolic dependency chain.
            if entry.formula_dependencies:
                deps = ", ".join(f"`{d}`" for d in entry.formula_dependencies)
                st.markdown(f"**Depends on:** {deps}")

            # Provenance badges.
            _render_provenance_badges(entry)

            # Assumptions.
            if entry.assumptions:
                st.markdown("**Assumptions:**")
                for a in entry.assumptions:
                    st.markdown(f"- {a}")

            # Sensitivity bar — ±10 % response to each user input.
            # Computed only in Full view to avoid the perturbation runs
            # on every page render. Cached at the perturbation level so
            # multiple metrics sharing inputs share cache entries.
            if not entry.is_categorical:
                _render_sensitivity_bar(entry, result)


def _matches_search(entry, query: str) -> bool:
    """Filter helper — returns True when the user's free-text query matches
    any of the metric's searchable fields. Case-insensitive substring
    match across display_name, key, formula_text, explanation_short."""
    if not query:
        return True
    q = query.lower().strip()
    haystack = " ".join((
        entry.display_name,
        entry.key,
        entry.formula_text or "",
        entry.explanation_short or "",
        entry.explanation_full or "",
    )).lower()
    return q in haystack


def render_tab_math(result: dict) -> None:
    """Render the "How it's calculated" tab.

    Sections:
      1. Header + explanation
      2. View-mode toggle (Simple / Full)
      3. Search filter
      4. Quick-jump navigation
      5. Glossary expander (top-level)
      6. Per-module sections (anchored markdown headers; PR 1 ships M1-M3)
      7. (Stubs for PR 2-5 — empty in PR 1.)

    The user's current run feeds every "Value" cell so the math tab and
    the per-tab metric cards can never disagree on a number.
    """
    from ui.glossary import GLOSSARY
    from ui.math_content import MATH_CONTENT, MODULE_ORDER, MODULE_TITLES

    section_header("How it's calculated")
    explanation(EXPLANATIONS["math_intro"])

    # --- View mode + search ----------------------------------------------
    c1, c2 = st.columns([1, 3])
    with c1:
        view_mode = st.radio(
            "View",
            options=("Simple", "Full"),
            horizontal=True,
            index=0,
            key=_MATH_VIEW_KEY,
            help=(
                "Simple shows formula, value, and a one-sentence "
                "explanation. Full adds substituted values, citations, "
                "code references, and assumptions."
            ),
        )
    with c2:
        search_query = st.text_input(
            "Search",
            placeholder="Filter by metric name, symbol, or term…",
            key=_MATH_SEARCH_KEY,
        )

    # --- Quick-jump --------------------------------------------------------
    quick_targets: list[str] = ["[Glossary](#glossary)"]
    for module_id in MODULE_ORDER:
        # Only list modules that actually have entries in MATH_CONTENT.
        if any(e.module == module_id for e in MATH_CONTENT.values()):
            anchor = module_id.lower()
            quick_targets.append(f"[{module_id}](#{anchor})")
    quick_targets.append("[Constants & sources](#constants)")
    quick_targets.append("[Worked example](#worked-example)")
    st.markdown(" · ".join(quick_targets))

    # --- Glossary ---------------------------------------------------------
    st.markdown("<a id='glossary'></a>", unsafe_allow_html=True)
    with st.expander(f"Glossary ({len(GLOSSARY)} terms)", expanded=False):
        st.caption(
            "Concept-level definitions. Each entry explains the *concept* "
            "(what is 'diffraction'? what is 'Strehl'?) — separate from "
            "the per-metric 'What it means' below, which explains what "
            "that specific number tells you about the engagement."
        )
        for term, definition in GLOSSARY.items():
            st.markdown(f"**{term}** — {definition}")

    # --- Per-module sections ----------------------------------------------
    for module_id in MODULE_ORDER:
        module_entries = [
            e for e in MATH_CONTENT.values() if e.module == module_id
        ]
        if not module_entries:
            continue
        # Filter by search.
        visible = [e for e in module_entries if _matches_search(e, search_query)]
        if not visible:
            continue

        anchor = module_id.lower()
        st.markdown(f"<a id='{anchor}'></a>", unsafe_allow_html=True)
        st.markdown(f"### {module_id} — {MODULE_TITLES[module_id]}")

        for entry in visible:
            _render_metric_row(entry, result, view_mode=view_mode)
            st.divider()

    # --- Constants & sources section --------------------------------------
    _render_constants_section()

    # --- Worked example ---------------------------------------------------
    _render_worked_example()

    # --- Markdown export --------------------------------------------------
    _render_markdown_export(result)


@st.cache_data(max_entries=4, show_spinner=False)
def _cached_worked_example() -> dict:
    """Compute and cache the worked-example chain once per session.

    The worked example is a static teaching artifact (always at the
    canonical c_uas-1km scenario); recomputing on every rerun is
    wasteful. Returns the same merged-result dict shape as
    ``run_full_chain``."""
    from ui.worked_example import compute_worked_example
    walkthrough = compute_worked_example()
    return walkthrough.result


def _render_constants_section() -> None:
    """Render the constants & sources tables in their own anchored
    section, one expander per module group. The data lives in
    ``ui/constants_table.py`` (mirror of validation/constants_audit.md)."""
    from ui.constants_table import CONSTANTS_BY_MODULE, total_constant_count

    st.markdown("<a id='constants'></a>", unsafe_allow_html=True)
    st.markdown("### Constants & physical sources")
    st.caption(
        f"Every hard-coded numeric in the physics modules — "
        f"{total_constant_count()} explicit entries plus the multi-cell "
        f"data tables (α_mol, A_λ, material properties). Each value "
        f"traces to its primary literature source. HIGH UNCERTAINTY "
        f"badges flag entries currently held as engineering defaults."
    )

    for group_title, entries in CONSTANTS_BY_MODULE.items():
        with st.expander(f"{group_title} ({len(entries)})", expanded=False):
            # Build a Markdown table (Streamlit's st.dataframe is
            # heavier and styles less consistently with the rest of
            # the math tab; for ~10 rows per group, a plain table is
            # adequate).
            st.markdown(
                "| Name | Value | Units | Source | Verdict | Code |\n"
                "|---|---|---|---|---|---|"
            )
            for c in entries:
                # Escape pipes so they don't break Markdown table
                # rendering. The constants_table.py text never uses
                # multi-line strings so no \n handling is needed.
                cells = [
                    c.name.replace("|", "\\|"),
                    c.value.replace("|", "\\|"),
                    c.units.replace("|", "\\|") if c.units else "—",
                    c.source.replace("|", "\\|"),
                    c.verdict.replace("|", "\\|"),
                    f"`{c.code_ref}`",
                ]
                st.markdown("| " + " | ".join(cells) + " |")


def _render_markdown_export(result: dict) -> None:
    """Render the bottom-of-tab Download-as-Markdown button.

    The export carries the full math-tab content — glossary, every
    per-metric row with the user's current values, the constants
    roster, and the static worked example — as a self-contained
    Markdown file. Engineers download and attach to trade-study
    deliverables. The export is computed lazily inside
    ``st.download_button``: the bytes are generated only when the
    user clicks, so opening the math tab itself doesn't pay the
    rendering cost.
    """
    from ui.math_export import to_markdown

    st.divider()
    st.markdown("### Download")
    st.caption(
        "Export the entire math tab as a self-contained Markdown "
        "document — every formula, every value at your current "
        "inputs, every citation and assumption. Opens cleanly in any "
        "Markdown viewer."
    )

    md_bytes = to_markdown(result, include_full=True).encode("utf-8")
    st.download_button(
        label="Download as Markdown",
        data=md_bytes,
        file_name="hel-math-tab.md",
        mime="text/markdown",
        help=(
            "Self-contained .md file — formulas as LaTeX math blocks, "
            "values from your current run, no external assets."
        ),
    )


def _render_worked_example() -> None:
    """Render the end-to-end walkthrough at the c_uas-1km worked
    example. Static scenario (NOT the user's current run) — the
    purpose is to show the full dependency chain in concrete numbers
    so a junior engineer can see how the formulas fit together."""
    from ui.labels import output_unit
    from ui.math_content import MATH_CONTENT
    from ui.worked_example import WALKTHROUGH_STEPS

    st.markdown("<a id='worked-example'></a>", unsafe_allow_html=True)
    st.markdown("### Worked example — c_uas at 1 km")
    st.caption(
        "End-to-end walk-through of the full dependency chain at a "
        "fixed reference scenario (3 kW · 1 km · 1.07 µm · CFRP · "
        "0.25 s exposure). This section's values do NOT follow your "
        "sidebar inputs — it's a teaching artifact so you can see "
        "how the 41 numeric metrics fit together. Your live values "
        "are in the per-metric rows above."
    )

    try:
        result = _cached_worked_example()
    except Exception as exc:  # pragma: no cover — defensive
        st.warning(
            f"Worked example could not be computed: {exc!s}. The "
            "static scenario should always be valid; if you see this, "
            "report it as a bug."
        )
        return

    for step in WALKTHROUGH_STEPS:
        st.markdown(f"#### {step.section_title}")
        st.markdown(f"*Given:* {step.given}")
        st.markdown(step.narrative)

        # Render each metric in the step as a small "key = value"
        # line so the reader sees the concrete output.
        lines: list[str] = []
        for key in step.metric_keys:
            entry = MATH_CONTENT.get(key)
            if entry is None:
                continue
            si_value = result.get(key)
            unit = output_unit(key)
            rendered = _format_value_for_math_tab(key, si_value, unit)
            lines.append(
                f"- **{entry.display_name}** "
                f"(`{key}`): {rendered}"
            )
        if lines:
            st.markdown("\n".join(lines))
