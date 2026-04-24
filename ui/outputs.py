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

    # Always render all three frames — when sweep is None/empty, each
    # constructor returns a frame-only figure with a centered advisory
    # (SPEC §5.3 item 10: no silent plot skip on infeasible geometry).
    # An ``explanation(..., variant="plot")`` sits under each chart so
    # a non-specialist viewer reads what the curves mean in two sentences.
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
        plots.plot_c_beam_diameter_breakdown(sweep),
        use_container_width=True,
        config=PLOTLY_MODEBAR_CONFIG,
    )
    explanation(EXPLANATIONS["plot_c_intro"], variant="plot")


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
