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
    # DRI Analyzer — distances SI m → display km
    "dri_R_detection_m":      1e-3,
    "dri_R_recognition_m":    1e-3,
    "dri_R_identification_m": 1e-3,
    "dri_R_atm_m":            1e-3,
    # DRI Analyzer — angles SI rad → display µrad
    "dri_ifov_pixel_rad": 1e6,
    "dri_theta_diff_rad": 1e6,
    "dri_theta_turb_rad": 1e6,
    "dri_ifov_eff_rad":   1e6,
    # Time (s), Margin (%), dimensionless ratios — pass-through (scale=1.0).
}


# ---------------------------------------------------------------------------
# SI units for raw user-input keys (Phase A.1, 2026-04-28).
# INPUT_LABELS already carries each input's *display* unit (e.g. "kW",
# "µrad"), but the substituted-formula block in the math-tab Full view
# shows raw SI values from the chain's `result` dict so the formula stays
# self-consistent. This dict labels each input with its SI unit so the
# reader sees `P0 = 3000 W — Laser output power` instead of just
# `P0 = 3000`. Hand-curated; the test suite covers a representative slice.
# Empty string = dimensionless.
# ---------------------------------------------------------------------------

_INPUT_SI_UNITS: dict[str, str] = {
    # Section 1 — Laser source / M1
    "P0":         "W",
    "M2":         "",
    "D":          "m",
    "wavelength": "m",
    # Section 2 — Beam director / M2 + jitter
    "eta_opt":    "",
    "sigma_jit":  "rad",
    # Section 3 — Engagement geometry / M3
    "H_e":        "m",
    "H_t":        "m",
    "v_tgt":      "m/s",
    "v_perp":     "m/s",
    "R":          "m",
    "R_detect":   "m",
    "R_min":      "m",
    "engagement_geometry": "",     # categorical
    # Section 4 — Atmosphere / M4
    "V":          "km",            # visibility — chain stores it in km
    "RH":         "",              # fraction
    "T_ambient":  "K",
    "P_atm":      "Pa",
    # Section 4b — Turbulence / M5
    "cn2_model":  "",              # categorical
    "Cn2_value":  "m^(-2/3)",
    "Cn2_ground": "m^(-2/3)",
    "v_HV":       "m/s",
    # Section 5 — Aimpoint / target / M7+M8
    "d_aim":      "m",
    "material":   "",              # categorical
    "thickness":  "m",
    # Section 6 — System resources / M10
    "eta_wallplug": "",
    "Q_cool":     "W",
    "C_thermal":  "J/K",
    "dT_max":     "K",
    "t_exp":      "s",
    "backside_BC": "",             # categorical
    # SPEC v2.0 / safety-table inputs / M9
    "A_lambda":   "",              # absorption fraction
}


def _scale(key: str, value: float | None) -> float | None:
    """Scale a SI orchestrator value to the display unit declared in labels.py."""
    if value is None:
        return None
    return value * _DISPLAY_SCALE.get(key, 1.0)


def _build_formula_details_html(key: str, result: dict | None) -> str | None:
    """Build the click-to-expand <details> HTML block that shows a
    metric's formula + substituted values inside its card (Phase C,
    2026-04-28).

    Returns None when:
      - the key has no MATH_CONTENT entry (most input-only keys)
      - the result dict isn't available (chain hasn't run)
      - the entry is categorical (failure_mode, laser_class) — no
        meaningful formula to substitute into

    Why a <details>/<summary> disclosure widget rather than a hover
    popover: the previous tooltip implementation tried hover popovers
    and ran into overlap problems with neighbouring cards (see comment
    in ui/components.py:330). Native HTML disclosure is mobile-
    friendly, doesn't overlap, and requires no JavaScript. Users see a
    small "▸ Show formula" toggle below the metric value; clicking
    expands inline. Same UX intent as the user's "hover to see
    formula" request, but more robust.
    """
    if result is None:
        return None
    from ui.math_content import MATH_CONTENT

    entry = MATH_CONTENT.get(key)
    if entry is None or entry.is_categorical:
        return None

    # The formula text — prefer the ASCII formula_text (single line).
    # Fallback to formula_latex with a code-block render if no ASCII.
    formula_line = entry.formula_text or entry.formula_latex or ""
    if not formula_line:
        return None

    # Reuse the Phase A.1 substituted-values builder. Use compact=True
    # so the popover lists ONLY the formula's literal variables — not
    # the upstream user inputs from sensitivity_inputs. Phase C.1
    # (2026-04-28) fix: previously the popover listed every entry's
    # full sensitivity-input set (e.g. for S_TB it showed P0, eta_opt,
    # T_ambient, P_atm, RH even though they're not in S_TB's formula),
    # which confused readers. Math tab's Full view still uses the
    # non-compact form for the deeper-context view.
    sub_md = _substitute_formula_values(entry, result, compact=True)
    sub_html = ""
    if sub_md:
        # Convert markdown bullet list to HTML <ul>. Each line starts
        # with "- " — strip the marker and wrap in <li>.
        items: list[str] = []
        for line in sub_md.splitlines():
            if line.startswith("- "):
                # Strip "- " and convert **key** → <strong>key</strong>,
                # *label* → <em>label</em>. Cheap manual conversion to
                # avoid pulling in a markdown lib.
                inner = line[2:]
                inner = _md_emphasis_to_html(inner)
                items.append(f"<li>{inner}</li>")
        if items:
            sub_html = "<ul class='hel-card-formula-values'>" + "".join(items) + "</ul>"

    # Escape the formula text for HTML safety (formula_text may contain
    # < > & symbols that we want rendered literally inside <code>).
    formula_escaped = (
        formula_line.replace("&", "&amp;")
        .replace("<", "&lt;")
        .replace(">", "&gt;")
    )

    return (
        "<details class='hel-card-formula'>"
        "<summary>Show formula</summary>"
        f"<div class='hel-card-formula-body'>"
        f"<code class='hel-card-formula-code'>{formula_escaped}</code>"
        f"{sub_html}"
        "</div>"
        "</details>"
    )


def _md_emphasis_to_html(text: str) -> str:
    """Convert a small subset of inline markdown to HTML.

    Supports **bold** → <strong>, *italic* → <em>. Used when re-using
    the Markdown bullets from `_substitute_formula_values()` inside
    the metric-card formula popover (which is rendered as raw HTML,
    not Streamlit markdown). Keeps the conversion local — no external
    markdown dependency for a 2-pattern need.
    """
    import re
    # **bold** → <strong>bold</strong>
    out = re.sub(r"\*\*([^*]+)\*\*", r"<strong>\1</strong>", text)
    # *italic* → <em>italic</em>
    out = re.sub(r"\*([^*]+)\*", r"<em>\1</em>", out)
    return out


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

    Phase C (2026-04-28): when the chain's merged result is available
    in ``st.session_state["_current_result"]`` AND the key has a
    ``MATH_CONTENT`` entry, an inline "▸ Show formula" disclosure is
    appended to the card showing the formula + substituted values.
    The chain's result is set once per page render in
    ``ui/tools/hel_calculator.py`` so callers don't need to thread it
    through.
    """
    label = override_label if override_label is not None else output_label(key)
    unit = output_unit(key)
    tooltip = output_tooltip(key) or None

    scaled = value if isinstance(value, str) else _scale(key, value)

    # Phase C — build the optional formula-details HTML block. Reads
    # the current run's result dict from session_state (set once at
    # the top of the page render). Falls back to None when the chain
    # hasn't run yet, the key has no MATH_CONTENT entry, or the entry
    # is categorical.
    current_result = st.session_state.get("_current_result")
    formula_details_html = _build_formula_details_html(key, current_result)

    metric_card(
        label,
        scaled,
        unit=unit if not isinstance(value, str) else "",
        tooltip=tooltip,
        flag_est=flag_est,
        size=size,
        sig_figs=sig_figs,
        formula_details_html=formula_details_html,
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

    Reads in one glance: engagement verdict first, then the four headline
    KPIs that answer "can I engage this target with this system?" — power
    in the aimpoint, peak irradiance, burn-through time, available dwell.
    Wall-plug input power, waste heat, sustain time, and engagements-per-
    hour are still computed by M10 (the math tab consumes them) but are
    intentionally not shown in this tab — they belong to a "can I engage
    repeatedly?" question that v1's audience doesn't reach for from the
    front page (hidden 2026-04-27 per user request).
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

    section_header("Engagement summary")
    explanation(EXPLANATIONS["overview_summary"])
    # Single row of four headline metrics. Was 3+3 with two cards
    # (P_in, Q_waste) plus a separate "Compute headroom" section
    # below; consolidated 2026-04-27 to the four numbers users
    # actually consult on the Overview tab.
    c1, c2, c3, c4 = st.columns(4)
    with c1: _card("P_aim",           p_aim)
    with c2: _card("I_peak",          i_peak)
    with c3: _card("tau_BT",          tau_bt)
    with c4: _card("available_dwell", dwell)

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
    # Section intro removed 2026-04-27 per user request — the per-card
    # inline tooltips already explain each metric, so a separate intro
    # paragraph above is redundant. EXPLANATIONS["engagement_spot_strehl"]
    # kept in labels.py as an orphan key for possible future use.

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
    # Phase C.1 (2026-04-28): route through _card so the metric picks up
    # its OUTPUT_LABELS + MATH_CONTENT entries (label, tooltip, formula
    # popover). Stash the value into result so the substituted-formula
    # block can find it, even though the metric itself isn't a chain
    # output (it's UI-computed). Belt-and-braces: also push it into
    # session_state for any downstream lookup.
    result["peak_irradiance_ratio"] = eff_ratio
    if "_current_result" in st.session_state:
        st.session_state["_current_result"]["peak_irradiance_ratio"] = eff_ratio
    with c3: _card("peak_irradiance_ratio", eff_ratio, sig_figs=4)

    # Footer caption removed 2026-04-27 per user request — the same
    # information is already in the inline tooltips on the seven cards
    # above (peak-vs-diffraction-limit ratio, Strehl decompositions,
    # angular-error sources). Repeating it as a paragraph below was
    # redundant.

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
    # SPEC v2.0 §8.3 — Plot H (engagement-profile timeline) sits
    # at the top of the tab as the headline visualisation. Falls
    # back to the empty-frame advisory when the result lacks the
    # trajectory series (v1.x mode).
    if "trajectory_t_pde" in result:
        st.plotly_chart(
            plots.plot_h_engagement_profile(result),
            use_container_width=True,
            config=PLOTLY_MODEBAR_CONFIG,
        )
        explanation(EXPLANATIONS["plot_h_intro"], variant="plot")
        # 2026-04-28: Plot I (outcome-map vs R_detect) hidden per user
        # request — Plot B (time-to-burn-through) now occupies this
        # slot and tells the same engagement-closure story more
        # directly. Plot I's constructor remains in ui/plots.py for
        # any future use; only the render call is removed here.
        st.plotly_chart(
            plots.plot_b_time_to_burnthrough(sweep),
            use_container_width=True,
            config=PLOTLY_MODEBAR_CONFIG,
        )
        explanation(EXPLANATIONS["plot_b_intro"], variant="plot")
        # SPEC v2.0 §8.5 — Plot J (cumulative-energy diagnostic).
        st.plotly_chart(
            plots.plot_j_cumulative_energy_diagnostic(result),
            use_container_width=True,
            config=PLOTLY_MODEBAR_CONFIG,
        )
        explanation(EXPLANATIONS["plot_j_intro"], variant="plot")

        # SPEC v2.0 §8.6 — Plot K (operational envelope heatmap).
        # Compute-on-click per the user's PR-4-stage decision: the
        # full 10×10 grid is ~100 orchestrator runs (~100 s on first
        # click). Cached at the @st.cache_data layer — subsequent
        # renders are instant for the same input set. The 3D
        # companion view is rendered inside the same render-block
        # (single cache, two figures).
        _render_operational_envelope_plot(result)
        # Plot M — atmospheric envelope (Cn² × V at fixed kinematics).
        # Same compute-on-click pattern; orthogonal slice through the
        # margin field.
        _render_atmospheric_envelope_plot(result)
    st.plotly_chart(
        plots.plot_g_spot_vs_bucket(
            sweep, d_aim=d_aim_si,
            reference_range=reference_range,
            current_w_total_m=result.get("w_total"),
        ),
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
    # Plot O — Peak irradiance vs detection range, family of Cn² curves.
    # Sibling diagnostic to Plot A: same axes, but with 5 reference
    # atmospheres + the user's actual scenario highlighted. Lightweight
    # M4+M5+M7-only compute path keeps it sub-second.
    _render_cn2_family_plot(result)
    # 2026-04-28: Plot B was promoted UP into Plot I's slot (above);
    # Plot E (burn-through time vs dwell window) hidden per user
    # request — it duplicated Plot B's engagement-closure story.
    # Both plot constructors remain in ui/plots.py for future use.
    # 2026-04-28: Plot C' (spot tightening through trajectory) and the
    # v1 fallback (beam-diameter breakdown) hidden per user request —
    # the spot-vs-bucket plot already conveys the key insight.
    # Plot constructors remain in ``ui.plots`` for any future use.
    st.plotly_chart(
        plots.plot_d_blooming_distortion_number(
            sweep, reference_range=reference_range,
        ),
        use_container_width=True,
        config=PLOTLY_MODEBAR_CONFIG,
    )
    explanation(EXPLANATIONS["plot_d_intro"], variant="plot")

    # --- Jitter target visualizer (last on the tab) ----------------------------
    # SPEC §5.2.1 — Plotly Frames animation showing the laser spot
    # wandering on the target plane due to jitter, with a persistent
    # fluence heat map. Loops continuously. Illustrative; consumes
    # M5/M7/M8 outputs but adds no new physics. Placed at the end of
    # the tab because it's a deep-dive diagnostic — users land on the
    # Engagement tab to see the headline results first (Plot H, the
    # range-sweep panels, and so on); the visualizer is for users who
    # want to study how σ_jit shapes the heat distribution.
    if "trajectory_t_pde" in result:
        _render_jitter_animation(result)
        # Plot N — Burn-through time vs Jitter (SPEC §5.2.2). Sits
        # right under the visualizer at the absolute bottom of the
        # engagement tab. Renders inline (no Compute button) because
        # the lumped-mass sweep is sub-second.
        _render_jitter_sensitivity(result)


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
# Geometry tab — peak irradiance for varying target approach angles
# (Plot P, 2026-04-28). Sibling of Plot O (Cn² family) on the
# visualization layer; doesn't touch the chain.
# =============================================================================

# The 5 reference geometries shown both in the illustration cards
# (above the plot) AND in Plot P's curves. Kept in lockstep with
# physics/geometry_family._REFERENCE_ANGLES_DEG.
#
# Each entry: (alpha_deg, palette_color_key, title, description_line2).
_GEOMETRY_CARDS: tuple[tuple[float, str, str, str], ...] = (
    (0.0,  "data.a",
     "0° Head-on",       "Target heads straight at the beam director."),
    (30.0, "data.b",
     "30° Diagonal",     "Mostly closing, some cross-track motion."),
    (45.0, "data.c",
     "45° Diagonal",     "Half closing, half cross-track."),
    (60.0, "data.reference",
     "60° Wide crossing", "Mostly cross-track, barely closing."),
    (90.0, "accent.primary",
     "90° Perpendicular", "Pure fly-by; the target never closes."),
)


def _render_geometry_diagrams(
    palette: dict, R_detect_m: float, R_min_m: float,
) -> None:
    """Render the row of 5 SVG illustration cards above Plot P.

    Each card is a small top-down diagram:
      - gun (filled circle) at the left, anchored on a horizontal
        line-of-sight axis;
      - target (open circle) at the right;
      - velocity vector arrow originating at the target, pointing in
        its α-angled direction (length identical across all cards
        so the eye reads only the rotation difference).

    Arrow colour matches the angle's curve in Plot P so the reader
    can connect "this scenario looks like this" to "this scenario
    produces this curve".

    Closest-approach distance per card is computed from the actual
    chain inputs:
      - 0° → R_min (engagement-end at gun's minimum range)
      - α ∈ (0°, 90°) → R_detect · sin(α) (trajectory's closest pass)
      - 90° → R_detect (target never gets closer than detection)
    """
    cards_html: list[str] = []
    for alpha_deg, color_key, title, line2 in _GEOMETRY_CARDS:
        arrow_color = palette.get(color_key, palette["fg.secondary"])
        # Velocity arrow geometry — see plan §4. Beam director (20,55),
        # Target (110,55) on a 140×90 viewBox. Arrow length 25 px from
        # the target's circle EDGE (radius 5). SVG y-axis points DOWN
        # so subtracting sin α makes the arrow point "up" (away from
        # the beam director) on screen.
        gun_x, gun_y = 20.0, 55.0
        tgt_x, tgt_y = 110.0, 55.0
        target_radius = 5.0
        arrow_length = 25.0   # the visible arrow shaft length
        alpha_rad = math.radians(alpha_deg)
        cos_a = math.cos(alpha_rad)
        sin_a = math.sin(alpha_rad)
        # Arrow START — outside the target circle, at the edge in the
        # velocity direction. Looks like the arrow "emerges from" the
        # target rather than passing through it.
        arrow_start_x = tgt_x - target_radius * cos_a
        arrow_start_y = tgt_y - target_radius * sin_a
        # Arrow END — start + length × (-cos α, -sin α).
        arrow_end_x = arrow_start_x - arrow_length * cos_a
        arrow_end_y = arrow_start_y - arrow_length * sin_a

        # Closest-approach distance per the geometry (matches
        # physics/geometry_family.py's truncation rules). Always
        # formatted in metres for consistency across the row — mixing
        # "750 m" with "1.06 km" was visually jarring.
        if alpha_deg == 0.0:
            closest_m = R_min_m
        elif alpha_deg >= 90.0:
            closest_m = R_detect_m
        else:
            closest_m = R_detect_m * sin_a
        line1 = f"Closest approach: {closest_m:.0f} m"

        # Per-card SVG. We use a unique marker id per card so the
        # arrowhead picks up the angle-specific colour. Stroke + fill
        # come straight from the active palette.
        marker_id = f"hel-geom-arrow-{int(alpha_deg)}"
        gun_color = palette["fg.primary"]
        target_color = palette["fg.secondary"]
        los_color = palette["border.strong"]
        label_color = palette["fg.tertiary"]
        svg = f"""
<svg viewBox="0 0 140 90" class="hel-geometry-card-svg"
     xmlns="http://www.w3.org/2000/svg">
  <defs>
    <marker id="{marker_id}" viewBox="0 0 10 10"
            refX="9" refY="5" markerWidth="6" markerHeight="6"
            orient="auto-start-reverse">
      <path d="M 0 0 L 10 5 L 0 10 z" fill="{arrow_color}"/>
    </marker>
  </defs>
  <!-- Line of sight (dashed, faint) -->
  <line x1="{gun_x}" y1="{gun_y}" x2="{tgt_x}" y2="{tgt_y}"
        stroke="{los_color}" stroke-width="1"
        stroke-dasharray="3,3"/>
  <!-- Beam director (filled circle) + label. Short label "BD" inside
       the small SVG; captions / intro use the full "beam director"
       wording. -->
  <circle cx="{gun_x}" cy="{gun_y}" r="4" fill="{gun_color}"/>
  <text x="{gun_x}" y="{gun_y + 18:.1f}" text-anchor="middle"
        font-size="9" fill="{label_color}">BD</text>
  <!-- Target (open circle) + label -->
  <circle cx="{tgt_x}" cy="{tgt_y}" r="{target_radius}" fill="none"
          stroke="{target_color}" stroke-width="1.5"/>
  <text x="{tgt_x}" y="{tgt_y + 18:.1f}" text-anchor="middle"
        font-size="9" fill="{label_color}">Target</text>
  <!-- Velocity arrow (angle-coloured). Starts at the target circle
       EDGE (not the centre) so it visually "emerges from" the target. -->
  <line x1="{arrow_start_x:.2f}" y1="{arrow_start_y:.2f}"
        x2="{arrow_end_x:.2f}" y2="{arrow_end_y:.2f}"
        stroke="{arrow_color}" stroke-width="2.5"
        marker-end="url(#{marker_id})"/>
</svg>
"""
        cards_html.append(
            f'<div class="hel-geometry-card">'
            f'  <div class="hel-geometry-card-title">{title}</div>'
            f'  {svg}'
            f'  <div class="hel-geometry-card-caption">'
            f'    <div class="hel-geometry-card-caption-line1">{line1}</div>'
            f'    <div class="hel-geometry-card-caption-line2">{line2}</div>'
            f'  </div>'
            f'</div>'
        )

    st.markdown(
        f'<div class="hel-geometry-row">{"".join(cards_html)}</div>',
        unsafe_allow_html=True,
    )


def render_tab_geometry_comparison(result: dict) -> None:
    """Render the Geometry tab — Plot P (peak irradiance vs engagement
    time, family of approach angles).

    Reads the chain's by_module + trajectory_t / trajectory_I_peak
    series directly from the merged result dict (no recompute, no
    cache helper). The reference-family compute is sub-second
    closed-form arithmetic per cell so we render inline. Same
    fall-through pattern as Plot O / Plot N: KeyError → info banner;
    any other compute failure → warning banner; the rest of the
    tab degrades cleanly.
    """
    section_header(
        "Approach geometry — how Peak irradiance varies with target angle"
    )
    explanation(EXPLANATIONS["plot_p_intro_pre"])

    if "engagement_geometry" not in result:
        st.info(
            "Geometry-comparison plot is not available for this "
            "scenario — v2.0 trajectory keys are missing."
        )
        return

    # Render the 5-card illustration row BEFORE the plot. Closest-
    # approach distances on the cards come from the actual chain
    # inputs so a non-canonical scenario shows correct numbers.
    from ui.plots import _active_palette
    R_detect_m = float(result.get("R_detect") or result.get("R", 0.0))
    R_min_m = float(result.get("R_min", 100.0))
    if R_detect_m > 0:
        _render_geometry_diagrams(_active_palette(), R_detect_m, R_min_m)

    try:
        from physics.geometry_family import compute_geometry_family_curves
        curves = compute_geometry_family_curves(result)
    except KeyError as exc:
        st.info(f"Geometry-comparison plot skipped: {exc}")
        return
    except Exception as exc:  # pragma: no cover — defensive
        st.warning(f"Geometry-comparison compute failed: {exc!s}")
        return

    from ui import plots
    from ui.theme import PLOTLY_MODEBAR_CONFIG

    fig = plots.plot_p_peak_irradiance_vs_geometry(curves)
    st.plotly_chart(
        fig, use_container_width=True, config=PLOTLY_MODEBAR_CONFIG,
    )
    explanation(EXPLANATIONS["plot_p_intro"], variant="plot")


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
# Phase B (2026-04-28) — active filter-chip selection in the math tab.
# Either "All" (default) or one of TAB_ORDER values.
_MATH_FILTER_KEY = "_math_section_filter"


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


def _resolve_label_and_unit(key: str) -> tuple[str, str]:
    """Look up (human-readable label, SI unit) for any variable key
    appearing in a formula's `formula_dependencies` or
    `sensitivity_inputs`. Used by `_substitute_formula_values` to
    annotate each substituted value (Phase A.1, 2026-04-28).

    Lookup order:
      1. MATH_CONTENT[key] — outputs that have a math-tab entry
         (display_name + unit_si).
      2. INPUT_LABELS[key] — raw user inputs (label + _INPUT_SI_UNITS).
      3. OUTPUT_LABELS[key] — computed metrics without a math entry
         (label only; unit is the display unit, used as a fallback).
      4. Fallback: empty label + empty unit.
    """
    from ui.labels import INPUT_LABELS, OUTPUT_LABELS
    from ui.math_content import MATH_CONTENT

    # 1. MATH_CONTENT — primary source for outputs that have a math entry.
    entry = MATH_CONTENT.get(key)
    if entry is not None:
        return entry.display_name, entry.unit_si or ""

    # 2. INPUT_LABELS — raw user inputs.
    if key in INPUT_LABELS:
        label = INPUT_LABELS[key].get("label", "")
        si_unit = _INPUT_SI_UNITS.get(key, "")
        return label, si_unit

    # 3. OUTPUT_LABELS — computed metrics without a math entry.
    if key in OUTPUT_LABELS:
        label = OUTPUT_LABELS[key].get("label", "")
        # No SI unit available here; leave blank.
        return label, ""

    # 4. Fallback — defensive.
    return "", ""


def _substitute_formula_values(
    entry, result: dict, *, compact: bool = False,
) -> str | None:
    """Build the 'with current values' substituted-formula block for the
    Full view. Returns None when substitution doesn't make sense
    (categorical metrics, solver-based metrics).

    Phase A.1 (2026-04-28): output is now a Markdown bullet list, one
    line per variable, including the human-readable label and SI unit.
    Each bullet reads:

      - **key** = value unit — *human label*

    Example for I_peak:
        - **P_exit** = 2550 W — *Beam-director exit power*
        - **tau_atm** = 0.8087 — *Atmospheric transmission*
        - **S_TB** = 0.9743 — *Strehl ratio from thermal blooming*
        - ...

    Phase C.1 (2026-04-28): added ``compact`` mode. When True, only the
    formula's *direct* variables (``formula_dependencies``) are listed
    — the upstream user inputs from ``sensitivity_inputs`` are
    suppressed. This is the right shape for the per-card "Show formula"
    popover, where the reader wants to match exactly what's in the
    formula, not the broader ±10 % perturbation set. Math-tab Full
    view still uses the non-compact form (default) since that's the
    deeper context.
    """
    from ui.math_content import MetricEntry
    if not isinstance(entry, MetricEntry):
        return None
    if entry.is_categorical or entry.is_solver_based:
        return None
    if entry.formula_text is None:
        return None

    # Walk dependencies (+ inputs, when not in compact mode), building
    # one bullet per variable. Skip duplicates: a key appearing in both
    # lists renders only once.
    seen: set[str] = set()
    bullets: list[str] = []
    if compact:
        # Only the formula's literal variables. Used by the per-card
        # "Show formula" popover where extraneous inputs would confuse
        # the reader. When the entry has no formula_dependencies (the
        # formula uses raw inputs directly, e.g. theta_diff_pure =
        # 4·λ/(π·D)), fall back to sensitivity_inputs so the popover
        # shows λ and D rather than zero bullets.
        if entry.formula_dependencies:
            ordered_keys = list(entry.formula_dependencies)
        else:
            ordered_keys = list(entry.sensitivity_inputs)
    else:
        # Formula variables AND upstream user inputs — full context for
        # the Math tab's Full view.
        ordered_keys = list(entry.formula_dependencies) + [
            k for k in entry.sensitivity_inputs
            if k not in entry.formula_dependencies
        ]
    for key in ordered_keys:
        if key in seen:
            continue
        seen.add(key)
        v = result.get(key)
        if v is None or isinstance(v, (str, bool)):
            # Skip non-numeric / missing values for now — categorical
            # inputs (cn2_model, material, …) clutter the substitution
            # block without telling the reader anything about the
            # number that came out.
            continue
        label, si_unit = _resolve_label_and_unit(key)
        value_text = f"{float(v):.4g}"
        if si_unit:
            value_str = f"{value_text} {si_unit}"
        else:
            value_str = value_text
        if label:
            bullets.append(f"- **{key}** = {value_str} — *{label}*")
        else:
            bullets.append(f"- **{key}** = {value_str}")

    if not bullets:
        return None
    return "\n".join(bullets)


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


# ---------------------------------------------------------------------------
# Engagement-envelope plots — background-compute pattern.
#
# Each of the two envelope sweeps (operational + atmospheric) runs ~100
# orchestrator calls per click — long enough that a synchronous compute
# locks the entire UI for the duration. Instead:
#   1. Click → submit the compute to a background ThreadPoolExecutor.
#   2. Store the Future + start time in st.session_state.
#   3. Wrap the section in @st.fragment(run_every=...) so it re-polls
#      every 2 seconds without re-running the rest of the page.
#   4. While the future is pending, render an "elapsed: Xs" placeholder
#      and a Cancel button. The rest of the page (other plots, other
#      tabs) renders normally and remains interactive.
#   5. When the future completes, swap the placeholder for the rendered
#      2D + 3D plots.
#
# Cache semantics: instead of @st.cache_data, we cache the result in
# session_state keyed on the current frozen-inputs tuple. Input changes
# (different scenario) cancel the running job and clear the result.
# ---------------------------------------------------------------------------

# Session-state key prefixes for the two envelope kinds. The full keys
# are ``{prefix}_<kind>`` where kind is "operational" or "atmospheric".
_ENV_JOB_KEY = "_envelope_job"
_ENV_RESULT_KEY = "_envelope_result"
_ENV_INPUTS_KEY = "_envelope_inputs"
_ENV_START_KEY = "_envelope_start_at"
_ENV_ERROR_KEY = "_envelope_error"
# threading.Event paired with each future. When the user changes
# inputs or hits Cancel, we ``set()`` the event so the worker stops
# at the next cell-loop boundary and frees its slot in the
# ThreadPoolExecutor. ``Future.cancel()`` alone is insufficient —
# Python's ThreadPool can't kill a running task without
# cooperation from the worker.
_ENV_CANCEL_TOKEN_KEY = "_envelope_cancel_token"


def _envelope_state_machine(
    *,
    kind: str,
    frozen: tuple,
    intro_pre_key: str,
    intro_2d_key: str,
    intro_3d_key: str,
    button_caption: str,
    compute_fn,
    plot_2d_fn,
    plot_3d_fn,
    n_cells: int,
) -> None:
    """Render-state machine shared by the operational and atmospheric
    envelope plots.

    Holds the per-kind state in ``st.session_state``. On each call,
    transitions are evaluated FIRST (so a freshly-completed future is
    immediately recognised as "done"), and rendering happens AFTER —
    this keeps the widget tree shape stable from the perspective of
    Streamlit's frontend reconciler.

    Critical for fragment correctness: button-click handlers MUST NOT
    call ``st.rerun(scope="fragment")``. Streamlit already triggers a
    fragment rerun on button click; an explicit ``st.rerun()`` causes
    a double-rerun that races with the polling timer and can produce
    "Bad message format / setIn index" reconciliation errors on the
    frontend. State mutations happen inline; the next natural rerun
    reads the new state.

    Caller is responsible for wrapping the call in an
    ``@st.fragment(run_every="2s")`` decorator so this section
    re-polls itself without re-running the parent script.
    """
    import time
    import concurrent.futures
    import threading

    job_key = f"{_ENV_JOB_KEY}_{kind}"
    result_key = f"{_ENV_RESULT_KEY}_{kind}"
    inputs_key = f"{_ENV_INPUTS_KEY}_{kind}"
    start_key = f"{_ENV_START_KEY}_{kind}"
    error_key = f"{_ENV_ERROR_KEY}_{kind}"
    cancel_token_key = f"{_ENV_CANCEL_TOKEN_KEY}_{kind}"

    ss = st.session_state
    # Defaults — using setdefault keeps the keys present across reruns,
    # which helps Streamlit's session-state diff stay clean.
    for k in (job_key, result_key, inputs_key, start_key, error_key,
              cancel_token_key):
        ss.setdefault(k, None)

    # ── Input change → set cancel token AND drop our reference to
    # the old job. Setting the token causes the worker to raise
    # CancelledError at its next inter-cell check, freeing the slot
    # in ~1-2 seconds. Without this, the worker keeps running until
    # all 64 cells finish, eating CPU and a worker slot — symptom
    # the user sees as "everything was stuck again" when they
    # tweaked a sidebar input.
    if ss[inputs_key] != frozen:
        ss[inputs_key] = frozen
        old_job = ss[job_key]
        old_token: threading.Event | None = ss[cancel_token_key]
        if old_job is not None and not old_job.done():
            old_job.cancel()  # polite first
            if old_token is not None:
                old_token.set()  # cooperative second
        ss[job_key] = None
        ss[cancel_token_key] = None
        ss[result_key] = None
        ss[error_key] = None
        ss[start_key] = None

    # ── Transition: future is done → pull result up to session_state
    # BEFORE rendering. This keeps the post-render widget tree
    # reflecting the actual current state, not the previous tick's.
    job: concurrent.futures.Future | None = ss[job_key]
    if job is not None and job.done():
        try:
            ss[result_key] = job.result(timeout=0)
            ss[error_key] = None
        except concurrent.futures.CancelledError:
            pass
        except Exception as exc:  # pragma: no cover — defensive
            ss[error_key] = str(exc)
        ss[job_key] = None
        ss[start_key] = None
        job = None

    envelope = ss[result_key]
    error_msg = ss[error_key]

    explanation(EXPLANATIONS[intro_pre_key])

    # All dynamic content lives inside one stable container. The
    # container is the same DOM anchor across every fragment rerun;
    # only its contents change. This is what Streamlit's reconciler
    # needs to keep messages well-ordered.
    body = st.container()

    with body:
        # ── State A: result available → render 2D + 3D + Re-compute.
        if envelope is not None:
            from ui.theme import PLOTLY_MODEBAR_CONFIG
            st.plotly_chart(
                plot_2d_fn(envelope),
                use_container_width=True,
                config=PLOTLY_MODEBAR_CONFIG,
            )
            explanation(EXPLANATIONS[intro_2d_key], variant="plot")

            if hasattr(envelope, "R_detect_axis"):
                n_total = (
                    len(envelope.R_detect_axis) * len(envelope.v_tgt_axis)
                )
            else:
                n_total = len(envelope.cn2_axis) * len(envelope.V_km_axis)
            st.caption(
                f"Computed {n_total} engagements · "
                f"{envelope.n_kills} closed with margin · "
                f"{envelope.n_failures} hit a validator boundary"
            )

            st.plotly_chart(
                plot_3d_fn(envelope),
                use_container_width=True,
                config=PLOTLY_MODEBAR_CONFIG,
            )
            explanation(EXPLANATIONS[intro_3d_key], variant="plot")

            if st.button(
                "Re-compute envelope",
                key=f"_envelope_recompute_{kind}",
            ):
                ss[result_key] = None
                ss[error_key] = None
                # No explicit rerun — the button click triggers it.
            return

        # ── State B: error from a previous run → show + offer retry.
        if error_msg:
            st.error(
                f"Envelope compute failed: {error_msg}. Click below to "
                "retry."
            )
            if st.button("Retry compute", key=f"_envelope_retry_{kind}"):
                ss[error_key] = None
                # Natural button-click rerun.
            return

        # ── State C: job is pending → placeholder + Cancel.
        if job is not None and not job.done():
            elapsed = max(0.0, time.time() - (ss[start_key] or time.time()))
            st.info(
                f"Computing in the background — {elapsed:.0f} s "
                f"elapsed. Typical runtime is 30–90 seconds for "
                f"{n_cells} engagements on Streamlit Cloud. Cells "
                f"with very long dwell windows (>5 simulated min) "
                f"are skipped automatically and rendered gray. You "
                f"can keep using other plots and tabs while this "
                f"runs; the section will refresh automatically when "
                f"the result is ready."
            )
            if st.button("Cancel", key=f"_envelope_cancel_{kind}"):
                # Set the cancel token so the worker stops at the
                # next cell boundary and frees its executor slot.
                cancel_token: threading.Event | None = ss[cancel_token_key]
                if cancel_token is not None:
                    cancel_token.set()
                job.cancel()
                ss[job_key] = None
                ss[cancel_token_key] = None
                ss[start_key] = None
                # Natural button-click rerun.
            return

        # ── State D: idle → Compute button + caption.
        st.caption(button_caption)
        if st.button("Compute envelope", key=f"_envelope_btn_{kind}"):
            from ui.background_jobs import submit_compute
            # Create a cancel token, store it alongside the future,
            # and pass it through to the compute function.
            cancel_token = threading.Event()
            ss[cancel_token_key] = cancel_token
            ss[job_key] = submit_compute(compute_fn, dict(frozen), cancel_token)
            ss[start_key] = time.time()
            ss[error_key] = None
            # Explicit rerun: Streamlit's natural button-click rerun
            # renders State D one more time before the new state is
            # read at the top of the function. Without this rerun,
            # the spinner only appears on the next 2-second polling
            # tick — long enough that the user perceives "nothing
            # happened." Safe to call here because the stable
            # `st.container()` anchor (set above) keeps the widget
            # tree reconcilable across the State D → State C
            # transition. (Reintroducing this rerun on Cancel /
            # Re-compute paths is what caused the prior "Bad setIn
            # index" reconciliation issue; we keep it confined to
            # this single click path.)
            #
            # Try fragment-scope first (cheaper — only the fragment
            # reruns, parent script untouched). Fall back to full
            # rerun when scope="fragment" is not allowed in the
            # current execution context — most notably under
            # Streamlit's ``AppTest`` framework, which runs the
            # script synchronously and never establishes the
            # fragment-only rerun context that scope="fragment"
            # requires.
            from streamlit.errors import StreamlitAPIException
            try:
                st.rerun(scope="fragment")
            except StreamlitAPIException:
                st.rerun()


@st.fragment(run_every="2s")
def _operational_envelope_fragment(frozen: tuple) -> None:
    """Polling fragment for the operational envelope — re-runs every
    2 seconds while the worker thread is computing, then swaps to
    the rendered plots once the future completes."""
    from physics.operational_envelope import compute_operational_envelope
    from ui import plots  # used below as plot_*_fn references
    _envelope_state_machine(
        kind="operational",
        frozen=frozen,
        intro_pre_key="plot_k_intro_pre",
        intro_2d_key="plot_k_intro",
        intro_3d_key="plot_k_3d_intro",
        button_caption=(
            "Computes a 6 × 6 (R_detect × v_tgt) grid of "
            "engagement outcomes (36 full-trajectory runs). Runs in "
            "the background — you can keep using other tabs and "
            "plots while it computes."
        ),
        compute_fn=lambda inputs, cancel_token: compute_operational_envelope(
            inputs, n_R=6, n_v=6, cancel_token=cancel_token,
        ),
        plot_2d_fn=plots.plot_k_operational_envelope,
        plot_3d_fn=plots.plot_k_operational_envelope_3d,
        n_cells=36,
    )


@st.fragment(run_every="2s")
def _atmospheric_envelope_fragment(frozen: tuple) -> None:
    """Polling fragment for the atmospheric envelope — same pattern
    as the operational one, different physics."""
    from physics.operational_envelope import compute_atmospheric_envelope
    from ui import plots  # used below as plot_*_fn references
    _envelope_state_machine(
        kind="atmospheric",
        frozen=frozen,
        intro_pre_key="plot_m_intro_pre",
        intro_2d_key="plot_m_intro",
        intro_3d_key="plot_m_3d_intro",
        button_caption=(
            "Holds R_detect and v_tgt fixed; sweeps Cn² × visibility "
            "on a 6 × 6 grid (36 full-trajectory runs). Runs in the "
            "background — you can keep using other tabs and plots "
            "while it computes."
        ),
        compute_fn=lambda inputs, cancel_token: compute_atmospheric_envelope(
            inputs, n_cn2=6, n_V=6, cancel_token=cancel_token,
        ),
        plot_2d_fn=plots.plot_m_atmospheric_envelope,
        plot_3d_fn=plots.plot_m_atmospheric_envelope_3d,
        n_cells=36,
    )


def _render_operational_envelope_plot(result: dict) -> None:
    """Render the operational-envelope plots — entry point called by
    ``render_tab_engagement``. Builds the frozen-inputs tuple, then
    delegates to the polling fragment."""
    section_header("Operational envelope")
    frozen = _frozen_inputs_for_envelope(result)
    if frozen is None:
        st.warning(
            "Operational envelope cannot be computed — the current "
            "input set is missing v2.0 trajectory keys."
        )
        return
    _operational_envelope_fragment(frozen)


def _render_atmospheric_envelope_plot(result: dict) -> None:
    """Render the atmospheric-envelope plots — entry point called by
    ``render_tab_engagement``."""
    section_header("Atmospheric envelope")
    frozen = _frozen_inputs_for_envelope(result)
    if frozen is None:
        st.warning(
            "Atmospheric envelope cannot be computed — the current "
            "input set is missing v2.0 trajectory keys."
        )
        return
    _atmospheric_envelope_fragment(frozen)


# ---------------------------------------------------------------------------
# Jitter target visualizer (SPEC §8.7) — animation showing the laser
# spot wandering on the target due to beam-pointing jitter, with a
# persistent fluence heat map. Loops continuously.
# ---------------------------------------------------------------------------

@st.cache_data(max_entries=4, show_spinner="Building jitter animation…")
def _cached_jitter_frames(inputs: tuple):
    """Cache wrapper for the jitter-animation frame generator.

    Inputs tuple is hashable (rounded floats + strings); cached at
    most 4 entries (~24 MB at uint8 quantization). On a cache miss
    the generator runs in ~0.5 s on the canonical scenario.
    """
    from physics.jitter_animation import generate_jitter_animation
    kwargs = dict(inputs)
    return generate_jitter_animation(**kwargs)


def _jitter_inputs_tuple(result: dict) -> tuple | None:
    """Build the cache-key + generator-kwargs tuple from the merged
    orchestrator result.

    Returns None when any required input is missing or non-numeric
    (e.g., infeasible-geometry stub before any trajectory has run).
    Floats are rounded to 6 decimals so floating-point noise on
    re-renders doesn't miss the cache.
    """
    by = result.get("by_module", {})
    m7 = by.get("m7", {}) if isinstance(by, dict) else {}

    # w_inst = √(w_diff² + w_turb² + w_bloom²) — instantaneous spot
    # without the jitter contribution.
    w_diff = m7.get("w_diff")
    w_turb = m7.get("w_turb")
    w_bloom = m7.get("w_bloom") or 0.0
    if w_diff is None or w_turb is None:
        return None
    try:
        w_inst_m = math.sqrt(
            float(w_diff) ** 2
            + float(w_turb) ** 2
            + float(w_bloom) ** 2
        )
    except (TypeError, ValueError):
        return None

    # In-bucket optical power = P0 · η_opt · τ_atm · PIB.
    P0 = result.get("P0")
    eta_opt = result.get("eta_opt")
    tau_atm = m7.get("tau_atm") or by.get("m4", {}).get("tau_atm")
    PIB = m7.get("PIB_fraction")
    if any(v is None for v in (P0, eta_opt, tau_atm, PIB)):
        return None
    try:
        P_in_bucket_w = (
            float(P0) * float(eta_opt) * float(tau_atm) * float(PIB)
        )
    except (TypeError, ValueError):
        return None
    if P_in_bucket_w <= 0:
        return None

    # σ_jit and slant range: σ_jit is per-axis radians; we use the
    # reference range for the visualizer (consistent with how the
    # rest of the Engagement tab interprets "the spot at this range").
    sigma_jit_rad = result.get("sigma_jit")
    R_m = result.get("R_detect") or result.get("R")
    d_aim_m = result.get("d_aim")
    if any(v is None for v in (sigma_jit_rad, R_m, d_aim_m)):
        return None

    # Target silhouette dimensions — fall back to 2.3 m × 2.3 m
    # (NATO target) when not supplied. Future SPEC extension could
    # plumb target_w / target_h through the input panel.
    target_w_m = float(result.get("target_w_m") or 2.3)
    target_h_m = float(result.get("target_h_m") or 2.3)

    # E_fail (lumped-mass) — same lookup Plot J uses. May be None.
    material = result.get("material")
    thickness = result.get("thickness")
    T_amb = float(result.get("T_ambient", 293.0))
    E_fail_jpcm2: float | None = None
    try:
        from physics.m8_material_tables import MATERIAL_PROPERTIES
        if material in MATERIAL_PROPERTIES and thickness:
            props = MATERIAL_PROPERTIES[material]
            T_fail = props["T_fail"]
            E_fail_jpm2 = (
                props["rho"] * props["c_p"]
                * float(thickness) * (T_fail - T_amb)
            )
            E_fail_jpcm2 = E_fail_jpm2 * 1e-4
    except Exception:
        E_fail_jpcm2 = None

    tau_BT_s_raw = result.get("tau_BT")
    tau_BT_s: float | None
    if tau_BT_s_raw is None:
        tau_BT_s = None
    else:
        try:
            tau_val = float(tau_BT_s_raw)
        except (TypeError, ValueError):
            tau_val = float("nan")
        tau_BT_s = tau_val if math.isfinite(tau_val) and tau_val > 0 else None

    return tuple(sorted({
        "w_inst_m": round(float(w_inst_m), 6),
        "sigma_jit_rad": round(float(sigma_jit_rad), 9),
        "R_m": round(float(R_m), 3),
        "d_aim_m": round(float(d_aim_m), 6),
        "target_w_m": round(target_w_m, 3),
        "target_h_m": round(target_h_m, 3),
        "P_in_bucket_w": round(P_in_bucket_w, 3),
        "E_fail_jpcm2": (
            round(float(E_fail_jpcm2), 3)
            if E_fail_jpcm2 is not None else None
        ),
        "tau_BT_s": (
            round(tau_BT_s, 4) if tau_BT_s is not None else None
        ),
    }.items()))


def _render_jitter_animation(result: dict) -> None:
    """Render the SPEC §8.7 jitter target visualizer.

    Single-mode (current σ_jit only, per the v3 plan). Loops forever.
    Speed control 1× / 0.5× / 0.2×. No comparison toggle, no auto-scale.
    """
    section_header("Jitter visualizer")
    explanation(EXPLANATIONS["jitter_animation_intro"])

    inputs = _jitter_inputs_tuple(result)
    if inputs is None:
        st.info(
            "Jitter visualizer not available — required spot / power "
            "inputs are missing for this scenario."
        )
        return

    # Speed control.
    speed = st.radio(
        "Playback speed",
        options=(1.0, 0.5, 0.2),
        format_func=lambda x: f"{x}×",
        horizontal=True,
        index=0,
        key="_jitter_animation_speed",
    )

    try:
        frames = _cached_jitter_frames(inputs)
    except ValueError as exc:
        st.warning(f"Jitter visualizer skipped: {exc}")
        return

    from ui import plots
    from ui.theme import PLOTLY_MODEBAR_CONFIG

    fig = plots.plot_jitter_target_animation(frames, speed=float(speed))
    st.plotly_chart(
        fig, use_container_width=True, config=PLOTLY_MODEBAR_CONFIG,
    )

    # Tip-caption (small-wander hint) removed 2026-04-27 per user
    # request. The visualizer's main caption already invites users
    # to bump σ_jit if they want a more dramatic wander.


# ---------------------------------------------------------------------------
# Plot N — Burn-through time vs Jitter (SPEC §5.2.2). Sub-second
# closed-form sweep using lumped-mass τ_BT (skips M6 + M8 PDE per
# cell). The user's "you are here" star uses the chain's PDE-accurate
# τ_BT — same number as the headline metric. Renders inline; no
# Compute button or background-job machinery needed at this scale.
# ---------------------------------------------------------------------------

def _render_cn2_family_plot(result: dict) -> None:
    """Render Plot O — peak irradiance vs detection range for a
    family of Cn² atmospheres — directly under Plot A.

    Reads chain outputs (``by_module``) from the merged result dict
    so M1's w0/zR and M2's P_exit are reused (not recomputed). Per-
    cell loops M4+M5+M7 only with ``S_TB=1, w_bloom=0`` (skip M6/M8/
    M9-M11). Sub-second closed-form arithmetic, ~400 ms total —
    rendered inline without a Compute button.
    """
    section_header("Peak irradiance — sensitivity to atmospheric turbulence")
    explanation(EXPLANATIONS["plot_o_intro_pre"])

    if "engagement_geometry" not in result:
        st.info(
            "Cn²-family plot not available for this scenario — "
            "v2.0 trajectory keys are missing."
        )
        return

    try:
        from physics.cn2_family import compute_cn2_family_curves
        curves = compute_cn2_family_curves(result)
    except KeyError as exc:
        st.info(f"Cn²-family plot skipped: {exc}")
        return
    except Exception as exc:  # pragma: no cover — defensive
        st.warning(f"Cn²-family compute failed: {exc!s}")
        return

    from ui import plots
    from ui.theme import PLOTLY_MODEBAR_CONFIG

    fig = plots.plot_o_peak_irradiance_vs_cn2(curves)
    st.plotly_chart(
        fig, use_container_width=True, config=PLOTLY_MODEBAR_CONFIG,
    )
    explanation(EXPLANATIONS["plot_o_intro"], variant="plot")


def _render_jitter_sensitivity(result: dict) -> None:
    """Render Plot N — Burn-through time vs Jitter — at the absolute
    bottom of the Engagement tab.

    The curve module reads chain outputs (``by_module``, ``tau_BT``,
    ``available_dwell``) directly from the merged result dict. We do
    NOT route through ``_frozen_inputs_for_envelope`` because that
    helper strips chain outputs (it's designed for envelope sweeps
    that re-run the chain per cell). Compute is sub-millisecond
    closed-form arithmetic so no cache is needed.
    """
    section_header("Burn-through time vs Jitter")
    explanation(EXPLANATIONS["plot_n_intro_pre"])

    if "engagement_geometry" not in result:
        st.info(
            "Burn-through-vs-jitter plot is not available for this "
            "scenario — v2.0 trajectory keys are missing."
        )
        return

    try:
        from physics.jitter_sensitivity import compute_jitter_sensitivity
        curve = compute_jitter_sensitivity(result)
    except KeyError as exc:
        st.info(f"Burn-through-vs-jitter plot skipped: {exc}")
        return
    except Exception as exc:  # pragma: no cover — defensive
        st.warning(f"Burn-through-vs-jitter compute failed: {exc!s}")
        return

    from ui import plots
    from ui.theme import PLOTLY_MODEBAR_CONFIG

    fig = plots.plot_n_jitter_sensitivity(curve)
    st.plotly_chart(
        fig, use_container_width=True, config=PLOTLY_MODEBAR_CONFIG,
    )
    explanation(EXPLANATIONS["plot_n_intro"], variant="plot")


def _frozen_inputs_for_envelope(result: dict) -> tuple | None:
    """Frozen-inputs tuple for the operational-envelope cache. Same
    shape as ``_frozen_inputs_for_sensitivity`` but R_detect / v_tgt
    are excluded (they're swept per cell, not held fixed)."""
    user_input_keys = (
        "P0", "M2", "D", "wavelength", "eta_opt", "sigma_jit",
        "H_e", "R_detect", "R_min", "H_t", "v_tgt",
        "engagement_geometry",
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
        if isinstance(v, (int, float, str, bool)):
            items.append((k, v))
        else:
            return None
    return tuple(items)


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


def _render_metric_row(entry, result: dict, *, view_mode: str = "Full") -> None:
    """Render one metric (one row). Layout per plan §3:

    Always-visible (top of card):
       1. Bold display name + symbol + (unit) on the left, value on the
          right of the same row.
       2. LaTeX formula below.
       3. "What it means" plain-language sentence below.
       4. "Also shown in: X" cross-reference badge (when applicable).

    Full-derivation expander (per-card, collapsed by default):
       5. Substituted formula with this run's input values.
       6. Citation, code reference, derivation link.
       7. Depends-on intermediates list.
       8. Provenance badges (audit-pinned / HIGH UNCERTAINTY / replicated).
       9. Assumptions list.

    Phase B (2026-04-28): the global Simple/Full radio toggle was
    removed in favour of always rendering the per-card expander. The
    `view_mode` parameter is kept for back-compat (defaulting to
    "Full") but no longer gates anything — the expander always
    renders, collapsed by default. Users with the previous "Simple"
    preference simply leave the expander closed; users wanting the
    full derivation click to expand. No "did I miss the Full view?"
    confusion.

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

    # "Also shown in: X" cross-reference badge (Phase A, v3.7).
    # When the metric appears on tabs other than its primary tab, show
    # a small caption pointing the reader at those other contexts.
    # Cheap addition that turns the math tab into a navigable graph
    # (the user reading I_peak under Engagement learns it's also a
    # headline on Overview, etc.).
    if getattr(entry, "also_in", ()):
        also_pretty = ", ".join(entry.also_in)
        st.caption(f"Also shown in: {also_pretty}")

    # Per-card "Show full derivation" expander. Always rendered (Phase B,
    # 2026-04-28) — the previous global Simple/Full toggle was removed in
    # favour of letting each user decide per-metric. Collapsed by default
    # so the page stays scannable; one click expands the deeper context.
    # The `view_mode == "Full"` gate is preserved as a defensive fall-
    # through in case any downstream caller still passes view_mode="Simple"
    # to suppress the expander entirely (none do today).
    if view_mode == "Full":
        with st.expander("Show full derivation", expanded=False):
            # Substituted formula with this run's values.
            # Phase A.1: `sub` is now a Markdown bullet list (one bullet
            # per variable, with label + SI unit); render the heading
            # and the bullets as separate markdown blocks.
            sub = _substitute_formula_values(entry, result)
            if sub:
                st.markdown("**With this run's values:**")
                st.markdown(sub)

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


def _tab_anchor(tab_id: str) -> str:
    """Slug-case a TAB_ORDER value to a stable HTML anchor id.

    Used by render_tab_math (v3.7+) so the quick-jump list and the
    section headers share consistent anchor names.
    """
    return "tab-" + tab_id.lower().replace(" ", "-")


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

    v3.7 (Phase A, 2026-04-28): sections are now grouped by **tab-of-
    origin** (Overview / Engagement / Target effects / Atmosphere /
    Safety / Diagnostics) instead of by physics module (M1–M11). The
    new layout matches the user's mental model — "I saw this number
    on the Engagement tab, where's the formula?" — instead of
    requiring them to know which physics module computed it.

    Sections:
      1. Header + explanation
      2. View-mode toggle (Simple / Full) — preserved verbatim in
         Phase A; revisited in Phase B
      3. Search filter — preserved verbatim
      4. Quick-jump navigation — now lists tab-of-origin sections
      5. Glossary expander — preserved verbatim
      6. Per-tab sections (anchored markdown headers, ordered by
         TAB_ORDER from ui.math_content)
      7. Constants & sources, worked example, markdown export

    The user's current run feeds every "Value" cell so the math tab and
    the per-tab metric cards can never disagree on a number.
    """
    from ui.glossary import GLOSSARY
    from ui.math_content import MATH_CONTENT, TAB_ORDER, TAB_TITLES

    section_header("How it's calculated")
    explanation(EXPLANATIONS["math_intro"])

    # --- Search box ------------------------------------------------------
    # Phase B (2026-04-28): the previous "Simple / Full" radio toggle
    # was removed; each metric now carries its own collapsed
    # "Show full derivation" expander, which the user clicks per-metric
    # rather than flipping a global mode. Less "did I miss the Full
    # view?" confusion. The view_mode argument to _render_metric_row
    # defaults to "Full" so the per-card expander always renders.
    view_mode = "Full"
    search_query = st.text_input(
        "Search",
        placeholder="Filter by metric name, symbol, or term…",
        key=_MATH_SEARCH_KEY,
    )

    # --- Filter chips (Phase B, 2026-04-28) -------------------------------
    # Quick-narrow widget: one button per tab-of-origin section, plus an
    # "All" button. Click → set st.session_state[_MATH_FILTER_KEY] →
    # the section-render loop below shows ONLY the matching section.
    # Composes with the search box: chip narrows by section,
    # search narrows by text — both apply.
    st.markdown(
        "<div class='hel-math-chip-row-label'>Quick filter:</div>",
        unsafe_allow_html=True,
    )
    chip_cols = st.columns(len(TAB_ORDER) + 1)
    active_filter = st.session_state.get(_MATH_FILTER_KEY, "All")
    with chip_cols[0]:
        # Use Streamlit's primary button styling to mark the active
        # chip — sidesteps the copy-style linter (which forbids emoji
        # indicators in user-facing strings) and gets a visually
        # distinct chip for free.
        if st.button(
            "All",
            key="_math_chip_All",
            type=("primary" if active_filter == "All" else "secondary"),
            use_container_width=True,
        ):
            st.session_state[_MATH_FILTER_KEY] = "All"
            active_filter = "All"
    for idx, tab_id in enumerate(TAB_ORDER):
        with chip_cols[idx + 1]:
            if st.button(
                TAB_TITLES[tab_id],
                key=f"_math_chip_{tab_id}",
                type=("primary" if active_filter == tab_id else "secondary"),
                use_container_width=True,
            ):
                st.session_state[_MATH_FILTER_KEY] = tab_id
                active_filter = tab_id

    # --- Quick-jump --------------------------------------------------------
    # Lists tab-of-origin sections that actually have entries; skips
    # empty buckets (Diagnostics may be small but never empty in
    # practice — defensive check is cheap).
    quick_targets: list[str] = ["[Glossary](#glossary)"]
    for tab_id in TAB_ORDER:
        if any(e.primary_tab == tab_id for e in MATH_CONTENT.values()):
            anchor = _tab_anchor(tab_id)
            quick_targets.append(f"[{TAB_TITLES[tab_id]}](#{anchor})")
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

    # --- Per-tab sections (Phase A) ---------------------------------------
    # Group entries by primary_tab and render in TAB_ORDER. Within each
    # section, entries appear in their MATH_CONTENT-dict insertion order
    # (which preserves the existing M1 → M2 → … flow within tab groups,
    # so dependency arrows still read top-to-bottom).
    for tab_id in TAB_ORDER:
        # Phase B chip filter — when the user has clicked a chip,
        # hide every section except the active one. "All" (default)
        # leaves every section visible.
        if active_filter != "All" and tab_id != active_filter:
            continue
        section_entries = [
            e for e in MATH_CONTENT.values() if e.primary_tab == tab_id
        ]
        if not section_entries:
            continue
        # Filter by search.
        visible = [e for e in section_entries if _matches_search(e, search_query)]
        if not visible:
            continue

        anchor = _tab_anchor(tab_id)
        st.markdown(f"<a id='{anchor}'></a>", unsafe_allow_html=True)
        st.markdown(
            f"### {TAB_TITLES[tab_id]} — {len(section_entries)} metrics"
        )

        for entry in visible:
            _render_metric_row(entry, result, view_mode=view_mode)
            st.divider()

    # --- Constants & sources section --------------------------------------
    _render_constants_section()

    # --- Worked example ---------------------------------------------------
    _render_worked_example()

    # --- Bibliography & references (last content block) ------------------
    _render_bibliography_section()

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


def _render_bibliography_section() -> None:
    """Render the math-tab Bibliography section — 13 primary references
    (cited in physics-module docstrings + SPEC.md Appendix B) plus 10
    supplementary canonical books (web-search-verified 2026-04-28).

    Shape mirrors ``_render_constants_section``: anchor link, header,
    short caption, then a Markdown table per group. Two sub-headings
    separate the cited works from the supplementary reading so users
    can quickly locate "what we used" vs "what to read next".
    """
    from ui.bibliography import (
        PRIMARY_REFERENCES, SUPPLEMENTARY_REFERENCES,
    )

    st.markdown("<a id='bibliography'></a>", unsafe_allow_html=True)
    st.markdown("### Bibliography & references")
    st.caption(
        "Every formula in this tool traces to one of the primary "
        "references below. Supplementary works are widely-used "
        "canonical texts for users who want to study the field deeper."
    )

    def _table(entries) -> None:
        # Markdown table — same format as the constants section so
        # spacing, theming, and font weight read consistently across
        # the math tab.
        st.markdown(
            "| # | Author(s) | Title | Year | Publisher | Where used / topic |\n"
            "|---|---|---|---|---|---|"
        )
        for i, e in enumerate(entries, start=1):
            cells = [
                str(i),
                e.authors.replace("|", "\\|"),
                f"*{e.title.replace('|', '\\|')}*",
                e.year.replace("|", "\\|"),
                e.publisher.replace("|", "\\|"),
                e.used_for.replace("|", "\\|"),
            ]
            st.markdown("| " + " | ".join(cells) + " |")

    st.markdown("**Primary references (cited in physics modules)**")
    _table(PRIMARY_REFERENCES)
    st.markdown("**Supplementary reading**")
    _table(SUPPLEMENTARY_REFERENCES)


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


# =============================================================================
# DRI Analyzer tab — independent of the HEL physics chain
# =============================================================================


def render_tab_dri_analyzer(
    result: dict,
    *,
    dri_sweeps: dict[str, list[dict]] | None = None,
    dri_target_size_sweeps: dict[str, list[dict]] | None = None,
    dri_cn2_sweeps: dict[str, list[dict]] | None = None,
    dri_frozen: tuple | None = None,
    dri_heatmap_runner=None,
    dri_atmospheric_heatmap_runner=None,
) -> None:
    """Render the DRI Analyzer tab.

    Reads:
        - The DRI inputs from the merged result dict (sidebar sections 7–9).
        - The DRI compute outputs (dri_R_detection_m / _recognition_m /
          _identification_m, binding labels, atmospheric / optical
          diagnostics, assumptions_flagged).
        - dri_sweeps (optional) — pre-computed FOV-sweep dicts keyed by
          {"Detection", "Recognition", "Identification"}; built by
          ``ui.app.run_dri_fov_sweep_cached``. PR 3.
    Writes:
        - A 3-card headline row of D / R / I ranges at NFOV.
        - A verdict chip naming the limiting term per level.
        - Three required FOV-sweep plots (D / R / I).
        - A small diagnostics row (atmospheric ceiling, IFOV components).
        - The methodology / assumptions panel.

    PR 4 will add four optional plots (target-size sweep, transmission
    curve, Cn² sweep, heatmap).
    """
    from ui.components import status_chip

    # If compute() didn't run (e.g. validation error upstream), the DRI
    # keys won't be in the result. Fall back to a friendly notice.
    if "dri_R_detection_m" not in result:
        st.warning(
            "DRI analysis not available — check the DRI sensor / "
            "atmosphere / target sections in the sidebar for invalid inputs."
        )
        return

    section_header("DRI ranges at narrow field of view")
    explanation(EXPLANATIONS["dri_intro"])

    R_d = result["dri_R_detection_m"]
    R_r = result["dri_R_recognition_m"]
    R_i = result["dri_R_identification_m"]

    c1, c2, c3 = st.columns(3)
    with c1:
        _card("dri_R_detection_m", R_d)
    with c2:
        _card("dri_R_recognition_m", R_r)
    with c3:
        _card("dri_R_identification_m", R_i)

    # --- Verdict chip — which limit is binding per level? -------------------
    binding_d = result.get("dri_binding_detection")
    binding_r = result.get("dri_binding_recognition")
    binding_i = result.get("dri_binding_identification")

    atm_count = sum(b == "atmosphere" for b in (binding_d, binding_r, binding_i))
    if atm_count == 3:
        chip_text = "All three ranges atmosphere-limited"
        chip_severity = "warn"
    elif atm_count == 0:
        chip_text = "All three ranges geometry-limited"
        chip_severity = "ok"
    else:
        # Mixed — call out which level(s) hit atmosphere.
        levels_atm = []
        if binding_d == "atmosphere":
            levels_atm.append("Detection")
        if binding_r == "atmosphere":
            levels_atm.append("Recognition")
        if binding_i == "atmosphere":
            levels_atm.append("Identification")
        chip_text = "Atmosphere-limited at " + ", ".join(levels_atm)
        chip_severity = "info"
    status_chip(chip_text, chip_severity)

    # --- Required FOV-sweep plots (D / R / I) ------------------------------
    if dri_sweeps:
        from ui import plots
        from ui.theme import PLOTLY_MODEBAR_CONFIG

        section_header("DRI distance vs field of view")
        explanation(EXPLANATIONS["dri_plot_fov_intro"])

        nfov_deg = result.get("dri_nfov_deg")
        for level in ("Detection", "Recognition", "Identification"):
            sweep = dri_sweeps.get(level) or []
            st.plotly_chart(
                plots.plot_dri_distance_vs_fov(
                    sweep, level=level, nfov_deg=nfov_deg,
                ),
                use_container_width=True,
                config=PLOTLY_MODEBAR_CONFIG,
            )

    # --- Optional plot DRI-4: range vs target size at NFOV ------------------
    if dri_target_size_sweeps:
        from ui import plots
        from ui.theme import PLOTLY_MODEBAR_CONFIG

        section_header("DRI distance vs target size")
        explanation(EXPLANATIONS["dri_plot_target_size_intro"])
        st.plotly_chart(
            plots.plot_dri_distance_vs_target_size(
                dri_target_size_sweeps.get("Detection") or [],
                dri_target_size_sweeps.get("Recognition") or [],
                dri_target_size_sweeps.get("Identification") or [],
            ),
            use_container_width=True,
            config=PLOTLY_MODEBAR_CONFIG,
        )

    # --- Optional plot DRI-5: atmospheric transmission vs range -------------
    if "dri_alpha_per_km" in result:
        from ui import plots
        from ui.theme import PLOTLY_MODEBAR_CONFIG

        section_header("Atmospheric transmission")
        explanation(EXPLANATIONS["dri_plot_atmospheric_transmission_intro"])
        # Show out to 2× the atmospheric ceiling so the falloff is visible.
        R_max_km = max(2.0, 2.0 * (result.get("dri_R_atm_m", 0.0) / 1000.0))
        R_max_km = min(R_max_km, 100.0)
        st.plotly_chart(
            plots.plot_dri_atmospheric_transmission(
                alpha_per_km=result.get("dri_alpha_per_km"),
                R_max_km=R_max_km,
            ),
            use_container_width=True,
            config=PLOTLY_MODEBAR_CONFIG,
        )

    # --- Optional plot DRI-6: range vs Cn² ----------------------------------
    if dri_cn2_sweeps:
        from ui import plots
        from ui.theme import PLOTLY_MODEBAR_CONFIG

        section_header("DRI distance vs atmospheric turbulence")
        explanation(EXPLANATIONS["dri_plot_cn2_intro"])
        st.plotly_chart(
            plots.plot_dri_distance_vs_cn2(
                dri_cn2_sweeps.get("Detection") or [],
                dri_cn2_sweeps.get("Recognition") or [],
                dri_cn2_sweeps.get("Identification") or [],
            ),
            use_container_width=True,
            config=PLOTLY_MODEBAR_CONFIG,
        )

    # --- Optional Plot DRI-7 + DRI-8: operational envelope -----------------
    # Single Compute button drives both the 2D heatmap and the 3D surface
    # — same data, two complementary views (heatmap = precision readout,
    # surface = curvature readout).
    if dri_frozen is not None and dri_heatmap_runner is not None:
        from ui import plots
        from ui.theme import PLOTLY_MODEBAR_CONFIG

        section_header("Operational envelope — FOV × target size")
        explanation(EXPLANATIONS["dri_plot_heatmap_intro"])

        button_key = "_dri_heatmap_compute_clicked"
        if button_key not in st.session_state:
            st.session_state[button_key] = False

        col_btn, col_note = st.columns([1, 3])
        with col_btn:
            if st.button("Compute envelope", key="_dri_heatmap_btn"):
                st.session_state[button_key] = True
        with col_note:
            st.caption(
                "Computes a 20 × 20 (FOV × target size) grid at the user's "
                "current sensor / atmosphere settings. Takes ~0.5 s on the "
                "first click; cached afterwards. Renders both the 2D "
                "heatmap (precision view) and the 3D surface (gradient "
                "view)."
            )

        if st.session_state[button_key]:
            wfov_deg = float(result.get("dri_wfov_deg", 25.0))
            nfov_deg = float(result.get("dri_nfov_deg", 1.5))
            n = 20
            # Log-spaced grids — match the heatmap axis types.
            fov_grid = tuple(
                nfov_deg * ((wfov_deg / nfov_deg) ** (i / (n - 1)))
                for i in range(n)
            )
            target_grid = tuple(
                0.10 * (10.0 ** (i / (n - 1)))   # 0.10 → 1.0 → 10.0 m
                for i in range(n)
            )
            try:
                grid = dri_heatmap_runner(
                    dri_frozen, fov_grid, target_grid, "Detection",
                )
                # Convert to km for display.
                grid_km = [
                    [v / 1000.0 for v in row] for row in grid
                ]
                # 2D heatmap (precision-readout view).
                st.plotly_chart(
                    plots.plot_dri_heatmap_fov_vs_target(
                        fov_grid_deg=list(fov_grid),
                        target_grid_m=list(target_grid),
                        grid_km=grid_km,
                    ),
                    use_container_width=True,
                    config=PLOTLY_MODEBAR_CONFIG,
                )
                # 3D operational-envelope surface (gradient-readout view).
                explanation(
                    EXPLANATIONS["dri_plot_3d_operational_envelope_intro"],
                    variant="plot",
                )
                st.plotly_chart(
                    plots.plot_dri_3d_operational_envelope(
                        fov_grid_deg=list(fov_grid),
                        target_grid_m=list(target_grid),
                        grid_km=grid_km,
                    ),
                    use_container_width=True,
                    config=PLOTLY_MODEBAR_CONFIG,
                )
            except Exception as exc:  # pragma: no cover — defensive
                st.error(f"Operational-envelope compute failed: {exc!s}")

    # --- Optional Plot DRI-9: 3D atmospheric envelope (Cn² × visibility) ---
    if (dri_frozen is not None
            and dri_atmospheric_heatmap_runner is not None):
        from ui import plots
        from ui.theme import PLOTLY_MODEBAR_CONFIG

        section_header(
            "Atmospheric envelope (3D) — Cn² × visibility"
        )
        explanation(EXPLANATIONS["dri_plot_3d_atmospheric_envelope_intro"])

        atm_button_key = "_dri_atmospheric_envelope_compute_clicked"
        if atm_button_key not in st.session_state:
            st.session_state[atm_button_key] = False

        col_btn, col_note = st.columns([1, 3])
        with col_btn:
            if st.button(
                "Compute atmospheric envelope",
                key="_dri_atmospheric_envelope_btn",
            ):
                st.session_state[atm_button_key] = True
        with col_note:
            st.caption(
                "Computes a 15 × 15 (Cn² × visibility) grid at the user's "
                "current FOV (NFOV) and target. Takes ~0.25 s on the "
                "first click; cached afterwards."
            )

        if st.session_state[atm_button_key]:
            n = 15
            # Cn² log-spaced from 1e-16 to 5e-13 (the seven preset bookends
            # plus interior fill).
            cn2_lo, cn2_hi = 1.0e-16, 5.0e-13
            cn2_grid = tuple(
                cn2_lo * ((cn2_hi / cn2_lo) ** (i / (n - 1)))
                for i in range(n)
            )
            # Visibility linear from 1 km (fog onset) to 60 km (very clear).
            vis_lo, vis_hi = 1.0, 60.0
            visibility_grid = tuple(
                vis_lo + (vis_hi - vis_lo) * (i / (n - 1))
                for i in range(n)
            )
            try:
                grid_atm = dri_atmospheric_heatmap_runner(
                    dri_frozen, cn2_grid, visibility_grid, "Detection",
                )
                grid_atm_km = [
                    [v / 1000.0 for v in row] for row in grid_atm
                ]
                st.plotly_chart(
                    plots.plot_dri_3d_atmospheric_envelope(
                        cn2_grid=list(cn2_grid),
                        visibility_grid=list(visibility_grid),
                        grid_km=grid_atm_km,
                    ),
                    use_container_width=True,
                    config=PLOTLY_MODEBAR_CONFIG,
                )
            except Exception as exc:  # pragma: no cover — defensive
                st.error(
                    f"Atmospheric-envelope compute failed: {exc!s}"
                )

    # --- Diagnostics row ----------------------------------------------------
    section_header("Diagnostics")
    explanation(EXPLANATIONS["dri_methodology"])

    R_atm = result.get("dri_R_atm_m")
    alpha = result.get("dri_alpha_per_km")
    h_target = result.get("dri_h_target_m")

    c1, c2, c3 = st.columns(3)
    with c1:
        _card("dri_R_atm_m", R_atm, size="md")
    with c2:
        _card("dri_alpha_per_km", alpha, size="md")
    with c3:
        _card("dri_h_target_m", h_target, size="md")

    # IFOV decomposition row
    ifov_pix = result.get("dri_ifov_pixel_rad")
    theta_diff = result.get("dri_theta_diff_rad")
    theta_turb = result.get("dri_theta_turb_rad")
    ifov_eff = result.get("dri_ifov_eff_rad")
    c1, c2, c3, c4 = st.columns(4)
    with c1:
        _card("dri_ifov_pixel_rad", ifov_pix, size="md")
    with c2:
        _card("dri_theta_diff_rad", theta_diff, size="md")
    with c3:
        _card("dri_theta_turb_rad", theta_turb, size="md")
    with c4:
        _card("dri_ifov_eff_rad", ifov_eff, size="md")

    # --- Assumption flags ---------------------------------------------------
    flags = result.get("dri_assumptions_flagged", [])
    if flags:
        with st.expander("Assumptions flagged", expanded=False):
            for flag in flags:
                st.write(f"- {flag}")
